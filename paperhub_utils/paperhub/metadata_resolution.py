"""Resolve research-paper metadata through public bibliographic APIs.

This importable module provides the metadata model and deterministic citation
lookup used by PaperHub's public-link ingestion flow. It does not download
files, authenticate, drive a browser, or write library artifacts.
"""

from __future__ import annotations

import difflib
import html
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

logger = logging.getLogger("paperhub.metadata_resolution")

# --- API endpoints --------------------------------------------------------
OPENALEX_WORKS = "https://api.openalex.org/works"
CROSSREF_WORKS = "https://api.crossref.org/works"
ARXIV_API = "https://export.arxiv.org/api/query"
UNPAYWALL = "https://api.unpaywall.org/v2/{doi}"
ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}.pdf"

DEFAULT_TIMEOUT = 30
CONTACT_EMAIL = os.environ.get("PAPERHUB_CONTACT_EMAIL", "howie.zhchien@gmail.com")

VERSION_PUBLISHED = "published"
VERSION_WORKING_PAPER = "working_paper"

_ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
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
            "User-Agent": f"PaperHub/1.0 (mailto:{email})",
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
