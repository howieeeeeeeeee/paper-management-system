#!/usr/bin/env python3
"""
Paper Fetcher - Search, resolve, and download research papers.

The front-end to scripts.paper_organizer: given a paper's title/author, DOI,
arXiv ID, or URL, this resolves bibliographic metadata via free APIs (OpenAlex,
Crossref, arXiv, Unpaywall), downloads an available PDF into to_be_organized/,
and writes a `{stem}.citation.md` sidecar holding the citation. The summarizer
later auto-detects that sidecar and uses it as authoritative context.

Real-paper-first policy: the published/journal version is the goal. A free
working-paper version (NBER/SSRN/RePEc/author site) is a fallback, but the
sidecar always carries the latest published citation.

This module does NO browser automation. For paywalled journals it reports
`needs_browser_fallback` and a `browser_hint`; the paper-downloader skill drives the
local gstack browser over the user's VPN and calls back here with
`--url <pdf_url> --cookies <jar>` to download the bytes.

Usage:
    python -m scripts.paper_fetcher --arxiv 2504.09343 [--mode auto]
    python -m scripts.paper_fetcher --doi 10.1257/aer.20181169 --citation-only
    python -m scripts.paper_fetcher --title "Behavioral Attenuation" --author Enke
    python -m scripts.paper_fetcher --url "https://.../paper.pdf" --cookies jar.json --stem enke2025

Always prints a single JSON object to stdout; logs go to stderr.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

# Make `from paperhub.config import ...` work regardless of the caller's cwd.
UTILS_ROOT = Path(__file__).resolve().parents[1]
if str(UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(UTILS_ROOT))

try:
    import requests
except ImportError:
    print(
        json.dumps(
            {
                "success": False,
                "errors": ["'requests' package not found. Run: uv sync"],
            }
        )
    )
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None

try:
    from paperhub.config import TO_BE_ORGANIZED_DIR
except Exception:  # pragma: no cover - config should always import
    TO_BE_ORGANIZED_DIR = UTILS_ROOT.parent / "to_be_organized"

logger = logging.getLogger("paper_fetcher")

# --- API endpoints --------------------------------------------------------
OPENALEX_WORKS = "https://api.openalex.org/works"
CROSSREF_WORKS = "https://api.crossref.org/works"
ARXIV_API = "https://export.arxiv.org/api/query"
UNPAYWALL = "https://api.unpaywall.org/v2/{doi}"
ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}.pdf"

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_BYTES = 60 * 1024 * 1024
CONTACT_EMAIL = os.environ.get("PAPERHUB_CONTACT_EMAIL", "howie.zhchien@gmail.com")

VERSION_PUBLISHED = "published"
VERSION_WORKING_PAPER = "working_paper"

_ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "on", "in", "to", "for", "with",
    "from", "by", "is", "are", "at", "as", "via", "into", "over", "under",
    "do", "does", "how", "why", "what", "when", "new", "evidence",
}


# --- data model -----------------------------------------------------------
@dataclass
class PaperMetadata:
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    url: str | None = None
    oa_pdf_url: str | None = None       # publisher / open-access "real paper" PDF
    wp_pdf_url: str | None = None       # repository / working-paper PDF
    source: str | None = None           # openalex | crossref | arxiv | url
    version: str | None = None          # published | working_paper
    publisher: str | None = None        # elsevier | springer | jstor | ...

    def is_empty(self) -> bool:
        return not (self.title or self.doi or self.arxiv_id or self.url)


# --- small helpers --------------------------------------------------------
def build_session(email: str = CONTACT_EMAIL) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": f"PaperHub-paper-downloader/1.0 (mailto:{email})",
            "Accept": "application/json",
        }
    )
    return session


def _get_json(session: requests.Session, url: str, params: dict | None = None) -> dict | None:
    try:
        resp = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("GET %s -> HTTP %s", url, resp.status_code)
            return None
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _strip_abstract_label(text: str | None) -> str | None:
    """Drop a leading 'Abstract' heading that sources glue onto the first word."""
    if not text:
        return text
    return re.sub(r"^\s*Abstract(?=[:\sA-Z])[:\s]*", "", text, count=1) or text


def _strip_jats(text: str | None) -> str | None:
    """Crossref abstracts arrive as JATS XML; strip the tags."""
    if not text:
        return None
    text = re.sub(r"</?jats:[^>]+>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return _strip_abstract_label(_clean(text))


def _year_from_parts(parts: list) -> int | None:
    try:
        return int(parts[0][0])
    except (IndexError, TypeError, ValueError):
        return None


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild plain text from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort(key=lambda p: p[0])
    return _strip_abstract_label(_clean(" ".join(word for _, word in positions)))


def _surname(full_name: str) -> str:
    parts = full_name.replace(",", " ").split()
    return parts[-1] if parts else full_name


def _sanitize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _publisher_from_host(host: str | None) -> str | None:
    if not host:
        return None
    host = host.lower()
    table = {
        "elsevier": "elsevier",
        "sciencedirect": "elsevier",
        "springer": "springer",
        "wiley": "wiley",
        "jstor": "jstor",
        "oxford": "oup",
        "cambridge": "cup",
        "american economic": "aea",
        "aeaweb": "aea",
        "university of chicago": "chicago",
        "sage": "sage",
        "taylor": "tandf",
        "informs": "informs",
    }
    for key, val in table.items():
        if key in host:
            return val
    return None


# --- bibtex + stem --------------------------------------------------------
def _bibtex_key(meta: PaperMetadata) -> str:
    surname = _sanitize(_surname(meta.authors[0])) if meta.authors else "anon"
    year = str(meta.year) if meta.year else "nd"
    first_word = ""
    if meta.title:
        for word in re.split(r"[^A-Za-z]+", meta.title):
            if word and word.lower() not in _STOPWORDS:
                first_word = word.lower()
                break
    return f"{surname}{year}{first_word}" or "ref"


def make_bibtex(meta: PaperMetadata) -> str:
    key = _bibtex_key(meta)
    entry_type = "article" if (meta.journal and meta.doi) else "misc"
    lines = [f"@{entry_type}{{{key},"]
    if meta.title:
        lines.append(f"  title = {{{meta.title}}},")
    if meta.authors:
        lines.append(f"  author = {{{' and '.join(meta.authors)}}},")
    if meta.year:
        lines.append(f"  year = {{{meta.year}}},")
    if meta.journal and entry_type == "article":
        lines.append(f"  journal = {{{meta.journal}}},")
    elif meta.journal:
        lines.append(f"  howpublished = {{{meta.journal}}},")
    if meta.doi:
        lines.append(f"  doi = {{{meta.doi}}},")
    if meta.url:
        lines.append(f"  url = {{{meta.url}}},")
    lines.append("}")
    return "\n".join(lines)


def compute_stem(meta: PaperMetadata) -> str:
    surname = _sanitize(_surname(meta.authors[0])) if meta.authors else ""
    year = str(meta.year) if meta.year else ""
    topic = ""
    if meta.title:
        for word in re.split(r"[^A-Za-z]+", meta.title):
            if word and word.lower() not in _STOPWORDS:
                topic = word.lower()
                break
    if surname and year:
        return f"{surname}{year}{topic}"[:60]
    if meta.arxiv_id:
        return f"arxiv_{meta.arxiv_id}"
    if meta.doi:
        return "doi_" + re.sub(r"[^a-z0-9]+", "_", meta.doi.lower()).strip("_")
    if meta.title:
        return _sanitize(meta.title)[:40] or "paper"
    return "paper"


def unique_stem(preferred: str, out_dir: Path) -> str:
    def taken(stem: str) -> bool:
        return (out_dir / f"{stem}.pdf").exists() or (
            out_dir / f"{stem}.citation.md"
        ).exists()

    if not taken(preferred):
        return preferred
    i = 2
    while taken(f"{preferred}-{i}"):
        i += 1
    return f"{preferred}-{i}"


# --- candidate scoring ----------------------------------------------------
def _score_candidate(
    cand_title: str | None,
    cand_year: int | None,
    cand_authors: list[str],
    want_title: str,
    want_author: str | None,
    want_year: int | None,
) -> float:
    if not cand_title:
        return 0.0
    score = difflib.SequenceMatcher(
        None, cand_title.lower(), want_title.lower()
    ).ratio()
    if want_year and cand_year:
        if cand_year == want_year:
            score += 0.15
        elif abs(cand_year - want_year) == 1:
            score += 0.05
    if want_author:
        surname = _surname(want_author).lower()
        if any(surname in a.lower() for a in cand_authors):
            score += 0.15
    return score


# --- resolvers ------------------------------------------------------------
def normalize_arxiv_id(value: str) -> str:
    return re.sub(r"(?i)^arxiv:", "", value).strip()


def normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"(?i)^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"(?i)^doi:", "", value)
    return value.strip()


def _arxiv_minimal(arxiv_id: str) -> PaperMetadata:
    """A usable record when the arXiv API is throttled: enough to download."""
    return PaperMetadata(
        arxiv_id=arxiv_id,
        journal="arXiv preprint",
        url=f"https://arxiv.org/abs/{arxiv_id}",
        oa_pdf_url=ARXIV_PDF.format(arxiv_id=arxiv_id),
        wp_pdf_url=ARXIV_PDF.format(arxiv_id=arxiv_id),
        source="arxiv",
        version=VERSION_WORKING_PAPER,
    )


def resolve_by_arxiv(arxiv_id: str, session: requests.Session) -> PaperMetadata | None:
    arxiv_id = normalize_arxiv_id(arxiv_id)
    root = None
    for attempt in range(3):
        try:
            resp = session.get(
                ARXIV_API,
                params={"id_list": arxiv_id},
                headers={"Accept": "application/atom+xml"},
                timeout=DEFAULT_TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            break
        except (requests.RequestException, ET.ParseError) as exc:
            logger.warning("arXiv lookup attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))

    if root is None:
        logger.warning("arXiv metadata unavailable; using minimal record for %s", arxiv_id)
        return _arxiv_minimal(arxiv_id)

    entry = root.find("atom:entry", _ARXIV_NS)
    if entry is None:
        return _arxiv_minimal(arxiv_id)

    def text(tag: str, ns: str = "atom") -> str | None:
        el = entry.find(f"{ns}:{tag}", _ARXIV_NS)
        return _clean(el.text) if el is not None and el.text else None

    authors = [
        _clean(name.text)
        for a in entry.findall("atom:author", _ARXIV_NS)
        if (name := a.find("atom:name", _ARXIV_NS)) is not None and name.text
    ]
    id_url = text("id") or ""
    resolved_id = id_url.rsplit("/abs/", 1)[-1] if "/abs/" in id_url else arxiv_id
    published = text("published")
    year = int(published[:4]) if published and published[:4].isdigit() else None
    journal_ref = text("journal_ref", "arxiv")
    doi = text("doi", "arxiv")

    return PaperMetadata(
        title=text("title"),
        authors=[a for a in authors if a],
        year=year,
        journal=journal_ref or "arXiv preprint",
        doi=normalize_doi(doi) if doi else None,
        arxiv_id=resolved_id,
        abstract=text("summary"),
        url=id_url or f"https://arxiv.org/abs/{resolved_id}",
        oa_pdf_url=ARXIV_PDF.format(arxiv_id=resolved_id),
        wp_pdf_url=ARXIV_PDF.format(arxiv_id=resolved_id),
        source="arxiv",
        version=VERSION_WORKING_PAPER,
    )


def unpaywall_locations(
    doi: str, session: requests.Session, email: str
) -> tuple[str | None, str | None, str | None]:
    """Return (publisher_pdf_url, repository_pdf_url, landing_url)."""
    data = _get_json(session, UNPAYWALL.format(doi=doi), params={"email": email})
    if not data:
        return None, None, None
    publisher_pdf = None
    repo_pdf = None
    landing = None
    for loc in data.get("oa_locations") or []:
        pdf = loc.get("url_for_pdf")
        host = loc.get("host_type")
        landing = landing or loc.get("url_for_landing_page")
        if host == "publisher" and pdf and not publisher_pdf:
            publisher_pdf = pdf
        elif host == "repository" and pdf and not repo_pdf:
            repo_pdf = pdf
    return publisher_pdf, repo_pdf, landing


def resolve_by_doi(
    doi: str, session: requests.Session, email: str
) -> PaperMetadata | None:
    doi = normalize_doi(doi)
    data = _get_json(session, f"{CROSSREF_WORKS}/{doi}", params={"mailto": email})
    msg = (data or {}).get("message") if data else None
    if not msg:
        return None

    titles = msg.get("title") or []
    containers = msg.get("container-title") or []
    authors = [
        _clean(f"{a.get('given', '')} {a.get('family', '')}".strip())
        for a in msg.get("author", [])
    ]
    year = _year_from_parts((msg.get("issued") or {}).get("date-parts") or [])

    pub_pdf, repo_pdf, landing = unpaywall_locations(doi, session, email)

    return PaperMetadata(
        title=_clean(titles[0]) if titles else None,
        authors=[a for a in authors if a],
        year=year,
        journal=_clean(containers[0]) if containers else None,
        doi=doi,
        abstract=_strip_jats(msg.get("abstract")),
        url=msg.get("URL") or landing or f"https://doi.org/{doi}",
        oa_pdf_url=pub_pdf,
        wp_pdf_url=repo_pdf,
        source="crossref",
        version=VERSION_PUBLISHED,
        publisher=_publisher_from_host(msg.get("publisher")),
    )


def _openalex_to_meta(work: dict, email: str, session: requests.Session) -> PaperMetadata:
    doi = work.get("doi")
    doi = normalize_doi(doi) if doi else None
    authors = [
        _clean((a.get("author") or {}).get("display_name"))
        for a in work.get("authorships", [])
    ]
    host = (work.get("primary_location") or {}).get("source") or {}
    journal = _clean(host.get("display_name"))

    oa_pdf = None
    wp_pdf = None
    for loc in work.get("locations", []):
        pdf = loc.get("pdf_url")
        if not pdf or not loc.get("is_oa"):
            continue
        src_type = ((loc.get("source") or {}).get("type") or "").lower()
        if src_type == "journal" and not oa_pdf:
            oa_pdf = pdf
        elif src_type == "repository" and not wp_pdf:
            wp_pdf = pdf
    best = work.get("best_oa_location") or {}
    if not oa_pdf and not wp_pdf and best.get("pdf_url"):
        if ((best.get("source") or {}).get("type") or "").lower() == "repository":
            wp_pdf = best.get("pdf_url")
        else:
            oa_pdf = best.get("pdf_url")

    # Fill OA gaps via Unpaywall when we have a DOI.
    if doi and not (oa_pdf and wp_pdf):
        pub_pdf, repo_pdf, _ = unpaywall_locations(doi, session, email)
        oa_pdf = oa_pdf or pub_pdf
        wp_pdf = wp_pdf or repo_pdf

    return PaperMetadata(
        title=_clean(work.get("display_name") or work.get("title")),
        authors=[a for a in authors if a],
        year=work.get("publication_year"),
        journal=journal,
        doi=doi,
        abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
        url=(work.get("primary_location") or {}).get("landing_page_url")
        or (f"https://doi.org/{doi}" if doi else None),
        oa_pdf_url=oa_pdf,
        wp_pdf_url=wp_pdf,
        source="openalex",
        version=VERSION_PUBLISHED if journal else VERSION_WORKING_PAPER,
        publisher=_publisher_from_host(host.get("host_organization_name")),
    )


def resolve_by_title(
    title: str,
    author: str | None,
    year: int | None,
    session: requests.Session,
    email: str,
) -> PaperMetadata | None:
    # Title-focused search first (precise); broad search only as a fallback.
    data = _get_json(
        session,
        OPENALEX_WORKS,
        params={"filter": f"title.search:{title}", "per-page": 10, "mailto": email},
    )
    results = (data or {}).get("results") or []
    if not results:
        query = title if not author else f"{title} {author}"
        data = _get_json(
            session,
            OPENALEX_WORKS,
            params={"search": query, "per-page": 10, "mailto": email},
        )
        results = (data or {}).get("results") or []
    if results:
        scored = [
            (
                _score_candidate(
                    _clean(w.get("display_name")),
                    w.get("publication_year"),
                    [
                        (a.get("author") or {}).get("display_name", "")
                        for a in w.get("authorships", [])
                    ],
                    title,
                    author,
                    year,
                ),
                w,
            )
            for w in results
        ]
        scored.sort(key=lambda s: s[0], reverse=True)
        best_score, best_work = scored[0]
        meta = _openalex_to_meta(best_work, email, session)
        if best_score < 0.6:
            logger.warning(
                "Low-confidence title match (score=%.2f): %r", best_score, meta.title
            )
        return meta

    # Crossref bibliographic fallback.
    data = _get_json(
        session,
        CROSSREF_WORKS,
        params={"query.bibliographic": query, "rows": 5, "mailto": email},
    )
    items = ((data or {}).get("message") or {}).get("items") or []
    if not items:
        return None
    best = max(
        items,
        key=lambda it: _score_candidate(
            _clean((it.get("title") or [None])[0]),
            _year_from_parts((it.get("issued") or {}).get("date-parts") or []),
            [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in it.get("author", [])
            ],
            title,
            author,
            year,
        ),
    )
    doi = best.get("DOI")
    if doi:
        return resolve_by_doi(doi, session, email)
    return None


def resolve_by_url(url: str, session: requests.Session, email: str) -> PaperMetadata | None:
    arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:\.pdf)?(?:[?#]|$)", url)
    if arxiv_match:
        return resolve_by_arxiv(arxiv_match.group(1), session)
    doi_match = re.search(r"(10\.\d{4,9}/[^\s?#]+)", url)
    if doi_match:
        meta = resolve_by_doi(doi_match.group(1), session, email)
        if meta:
            return meta
    # Unknown landing/PDF URL: minimal metadata so the caller can still download.
    is_pdf = url.lower().split("?")[0].endswith(".pdf")
    return PaperMetadata(
        url=url,
        oa_pdf_url=url if is_pdf else None,
        source="url",
        version=VERSION_PUBLISHED,
    )


# --- download -------------------------------------------------------------
def _load_cookies(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Could not read cookies file %s: %s", path, exc)
        return None
    if isinstance(data, dict):
        # Either {name: value} or a wrapper {"cookies": [...]}.
        if "cookies" in data and isinstance(data["cookies"], list):
            data = data["cookies"]
        else:
            return {str(k): str(v) for k, v in data.items()}
    if isinstance(data, list):
        return {
            c["name"]: c["value"]
            for c in data
            if isinstance(c, dict) and "name" in c and "value" in c
        }
    return None


def download_pdf(
    url: str,
    dest_path: Path,
    session: requests.Session,
    cookies: dict | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[bool, str]:
    headers = {"Accept": "application/pdf,*/*"}
    try:
        resp = session.get(
            url,
            stream=True,
            timeout=DEFAULT_TIMEOUT,
            headers=headers,
            cookies=cookies,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return False, f"request failed: {exc}"

    chunks = resp.iter_content(chunk_size=8192)
    first = next(chunks, b"")
    ctype = resp.headers.get("Content-Type", "").lower()
    if first[:5] != b"%PDF-" and "pdf" not in ctype:
        resp.close()
        return False, f"not a PDF (content-type={ctype!r}, head={first[:12]!r})"

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(dest_path.name + ".part")
    total = 0
    try:
        with open(tmp_path, "wb") as fh:
            if first:
                fh.write(first)
                total += len(first)
            for chunk in chunks:
                fh.write(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise IOError(f"exceeded max size {max_bytes} bytes")
    except (IOError, OSError) as exc:
        tmp_path.unlink(missing_ok=True)
        return False, str(exc)
    finally:
        resp.close()

    if total < 1024:
        tmp_path.unlink(missing_ok=True)
        return False, f"suspiciously small file ({total} bytes)"
    os.replace(tmp_path, dest_path)
    logger.info("Downloaded %s bytes -> %s", total, dest_path)
    return True, "ok"


# --- sidecar --------------------------------------------------------------
def write_sidecar(meta: PaperMetadata, stem: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = out_dir / f"{stem}.citation.md"

    front = {
        "title": meta.title or "",
        "authors": meta.authors or [],
        "year": meta.year or "",
        "journal": meta.journal or "",
        "doi": meta.doi or "",
        "arxiv": meta.arxiv_id or "",
        "url": meta.url or "",
        "source": meta.source or "",
        "version": meta.version or "",
        "fetched": date.today().isoformat(),
    }
    if yaml is not None:
        front_yaml = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    else:  # pragma: no cover - pyyaml is a declared dependency
        front_yaml = "\n".join(f"{k}: {json.dumps(v)}" for k, v in front.items())

    body = [
        "---",
        front_yaml,
        "---",
        "",
        f"# {meta.title or stem}",
        "",
        "## Abstract",
        meta.abstract or "[Abstract not available from metadata source]",
        "",
        "## BibTeX",
        "```bibtex",
        make_bibtex(meta),
        "```",
        "",
    ]
    sidecar_path.write_text("\n".join(body), encoding="utf-8")
    logger.info("Wrote sidecar: %s", sidecar_path)
    return sidecar_path


# --- orchestrator ---------------------------------------------------------
def _resolve_metadata(args, session: requests.Session) -> tuple[PaperMetadata | None, dict]:
    if args.arxiv:
        return resolve_by_arxiv(args.arxiv, session), {"kind": "arxiv", "value": args.arxiv}
    if args.doi:
        return resolve_by_doi(args.doi, session, args.email), {"kind": "doi", "value": args.doi}
    if args.url:
        return resolve_by_url(args.url, session, args.email), {"kind": "url", "value": args.url}
    if args.title:
        return (
            resolve_by_title(args.title, args.author, args.year, session, args.email),
            {"kind": "title", "value": args.title},
        )
    return None, {"kind": "none", "value": None}


def resolve(args) -> dict:
    session = build_session(args.email)
    out_dir = Path(args.out_dir).expanduser().resolve()
    cookies = _load_cookies(args.cookies)
    mode = "citation-only" if args.citation_only else args.mode

    meta, input_info = _resolve_metadata(args, session)
    result: dict = {
        "success": False,
        "input": input_info,
        "mode": mode,
        "metadata": None,
        "chosen_source": None,
        "oa_pdf_url": None,
        "wp_pdf_url": None,
        "downloaded_path": None,
        "sidecar_path": None,
        "needs_browser_fallback": False,
        "browser_hint": None,
        "warnings": [],
        "errors": [],
    }

    if meta is None or meta.is_empty():
        result["errors"].append("Could not resolve any metadata for the given input.")
        return result

    stem = args.stem or unique_stem(compute_stem(meta), out_dir)
    result["metadata"] = {
        k: v
        for k, v in asdict(meta).items()
        if k not in {"oa_pdf_url", "wp_pdf_url", "publisher"}
    }
    result["chosen_source"] = meta.source
    result["oa_pdf_url"] = meta.oa_pdf_url
    result["wp_pdf_url"] = meta.wp_pdf_url

    pdf_path = out_dir / f"{stem}.pdf"

    # --- download policy: real paper first --------------------------------
    if mode != "citation-only":
        # 1. Publisher / open-access "real paper".
        if meta.oa_pdf_url:
            ok, reason = download_pdf(meta.oa_pdf_url, pdf_path, session, cookies)
            if ok:
                result["downloaded_path"] = str(pdf_path)
                meta.version = (
                    VERSION_PUBLISHED if meta.journal and meta.doi else meta.version
                )
            else:
                result["warnings"].append(f"OA PDF download failed: {reason}")

        # 2. Working-paper fallback (open-access mode only auto-grabs this;
        #    auto mode defers to the skill's browser/VPN attempt first).
        if not result["downloaded_path"] and mode == "open-access" and meta.wp_pdf_url:
            ok, reason = download_pdf(meta.wp_pdf_url, pdf_path, session, cookies)
            if ok:
                result["downloaded_path"] = str(pdf_path)
                meta.version = VERSION_WORKING_PAPER
            else:
                result["warnings"].append(f"Working-paper download failed: {reason}")

        # 3. Nothing free obtained: signal the browser path for the real paper.
        if not result["downloaded_path"]:
            if mode == "auto" and (meta.doi or meta.url):
                result["needs_browser_fallback"] = True
                result["browser_hint"] = {
                    "landing_url": meta.url or (f"https://doi.org/{meta.doi}" if meta.doi else None),
                    "publisher": meta.publisher,
                    "wp_pdf_url": meta.wp_pdf_url,
                }

    sidecar_path = write_sidecar(meta, stem, out_dir)
    result["sidecar_path"] = str(sidecar_path)
    # Reflect any version finalization back into the reported metadata.
    if result["metadata"] is not None:
        result["metadata"]["version"] = meta.version
    result["success"] = True
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search, resolve, and download a paper.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--title", help="Paper title (free-text search)")
    src.add_argument("--doi", help="DOI (with or without https://doi.org/ prefix)")
    src.add_argument("--arxiv", help="arXiv ID, e.g. 2504.09343 or 2504.09343v1")
    src.add_argument("--url", help="Direct PDF or landing-page URL")
    parser.add_argument("--author", help="Author hint to disambiguate a title search")
    parser.add_argument("--year", type=int, help="Publication year hint")
    parser.add_argument(
        "--mode",
        choices=["auto", "open-access", "citation-only"],
        default="auto",
    )
    parser.add_argument("--citation-only", action="store_true", help="Alias for --mode citation-only")
    parser.add_argument("--out-dir", default=str(TO_BE_ORGANIZED_DIR))
    parser.add_argument("--email", default=CONTACT_EMAIL, help="Polite-pool contact email")
    parser.add_argument("--stem", help="Override the output filename stem")
    parser.add_argument("--cookies", help="Path to a cookie JSON (for VPN/browser bridge)")
    parser.add_argument("--json", action="store_true", help="Emit JSON (default; always on)")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    result = resolve(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
