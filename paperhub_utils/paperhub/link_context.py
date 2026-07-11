"""Prepare bounded, public link context for PaperHub engines.

This module performs deterministic citation lookup and public HTTP retrieval.
It never authenticates, supplies cookies, drives a browser, or bypasses access
controls. External AI engines receive only the generated text context.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from datetime import date
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from uuid import uuid4

import requests

from paperhub.config import PAPERHUB_ROOT
from scripts.paper_fetcher import (
    CONTACT_EMAIL,
    PaperMetadata,
    build_session,
    normalize_doi,
    resolve_by_doi,
    resolve_by_title,
    resolve_by_url,
)


MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 60 * 1024 * 1024
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = 30
CORE_FIELDS = ("title", "authors", "year", "journal", "abstract")
URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)


class UnsafeUrlError(ValueError):
    """Raised when a URL could reach a non-public network destination."""


class _LandingPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.canonical_url: str | None = None
        self._json_ld_depth = 0
        self._json_ld_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(k).lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            key = (values.get("name") or values.get("property") or "").lower()
            content = values.get("content", "").strip()
            if key and content:
                self.meta.setdefault(key, []).append(content)
        elif tag.lower() == "link" and values.get("rel", "").lower() == "canonical":
            href = values.get("href", "").strip()
            if href:
                self.canonical_url = href
        elif tag.lower() == "script" and "ld+json" in values.get("type", "").lower():
            self._json_ld_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._json_ld_depth:
            self._json_ld_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._json_ld_depth:
            self._json_ld_chunks.append(data)

    @property
    def json_ld_text(self) -> str:
        return "\n".join(self._json_ld_chunks).strip()


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def validate_public_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("Only HTTP(S) URLs are supported")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs containing credentials are not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")

    host = parsed.hostname.rstrip(".")
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise UnsafeUrlError("Localhost URLs are not allowed")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise UnsafeUrlError("Non-public IP addresses are not allowed")

    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Hostname could not be resolved: {host}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise UnsafeUrlError(f"Hostname resolves to a non-public address: {host}")
    return canonicalize_url(url)


def _read_bounded_response(response: requests.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Response exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_public_resource(
    url: str,
    session: requests.Session,
) -> tuple[str, str, bytes]:
    """Fetch a public URL with redirect and size guards."""
    current = validate_public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        response = session.get(
            current,
            allow_redirects=False,
            stream=True,
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.5"},
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Redirect response has no Location header")
            current = validate_public_url(urljoin(current, location))
            continue
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        max_bytes = (
            MAX_PDF_BYTES
            if content_type in {"application/pdf", "application/octet-stream"}
            else MAX_HTML_BYTES
        )
        body = _read_bounded_response(response, max_bytes)
        response.close()
        if body.startswith(b"%PDF-"):
            content_type = "application/pdf"
        elif content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"Unsupported content type: {content_type or 'unknown'}")
        return current, content_type, body
    raise ValueError(f"Too many redirects (maximum {MAX_REDIRECTS})")


def public_google_drive_download_url(url: str) -> str | None:
    """Return Google's unauthenticated download URL for a public Drive file."""
    parsed = urlsplit(url)
    if (parsed.hostname or "").lower() != "drive.google.com":
        return None
    match = re.fullmatch(r"/file/d/([^/]+)/?(?:view)?/?", parsed.path)
    if not match:
        return None
    query = urlencode({"id": match.group(1), "export": "download", "confirm": "t"})
    return f"https://drive.usercontent.google.com/download?{query}"


def _first(meta: dict[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        values = meta.get(key.lower()) or []
        for value in values:
            cleaned = re.sub(r"\s+", " ", value).strip()
            if cleaned:
                return cleaned
    return None


def _year(value: str | None) -> int | None:
    match = re.search(r"\b(18|19|20)\d{2}\b", value or "")
    return int(match.group(0)) if match else None


def _walk_json_ld(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        records.append(value)
        for child in value.values():
            records.extend(_walk_json_ld(child))
    elif isinstance(value, list):
        for child in value:
            records.extend(_walk_json_ld(child))
    return records


def parse_landing_page(html_text: str, base_url: str) -> dict[str, Any]:
    parser = _LandingPageParser()
    parser.feed(html_text)
    meta = parser.meta
    authors = [
        re.sub(r"\s+", " ", value).strip()
        for value in meta.get("citation_author", [])
        if value.strip()
    ]
    data: dict[str, Any] = {
        "title": _first(meta, "citation_title", "dc.title", "og:title"),
        "authors": authors,
        "year": _year(_first(meta, "citation_publication_date", "dc.date", "article:published_time")),
        "journal": _first(meta, "citation_journal_title", "prism.publicationname"),
        "doi": _first(meta, "citation_doi", "dc.identifier", "prism.doi"),
        "abstract": _first(meta, "citation_abstract", "dc.description", "description", "og:description"),
        "canonical_url": urljoin(base_url, parser.canonical_url) if parser.canonical_url else base_url,
        "pdf_url": _first(meta, "citation_pdf_url"),
    }

    if parser.json_ld_text:
        try:
            loaded = json.loads(parser.json_ld_text)
        except json.JSONDecodeError:
            loaded = None
        for record in _walk_json_ld(loaded):
            record_type = record.get("@type")
            if isinstance(record_type, list):
                types = {str(item).lower() for item in record_type}
            else:
                types = {str(record_type).lower()}
            if not types.intersection({"scholarlyarticle", "article", "creativework"}):
                continue
            data["title"] = data["title"] or record.get("headline") or record.get("name")
            data["abstract"] = data["abstract"] or record.get("abstract") or record.get("description")
            data["year"] = data["year"] or _year(str(record.get("datePublished") or ""))
            data["doi"] = data["doi"] or record.get("doi")
            author_value = record.get("author")
            if not data["authors"] and author_value:
                author_rows = author_value if isinstance(author_value, list) else [author_value]
                data["authors"] = [
                    str(row.get("name") if isinstance(row, dict) else row).strip()
                    for row in author_rows
                    if str(row.get("name") if isinstance(row, dict) else row).strip()
                ]
            break

    if data["doi"]:
        match = re.search(r"10\.\d{4,9}/\S+", str(data["doi"]))
        data["doi"] = normalize_doi(match.group(0).rstrip(".,;)") if match else str(data["doi"]))
    if data["pdf_url"]:
        data["pdf_url"] = urljoin(base_url, str(data["pdf_url"]))
    data["canonical_url"] = canonicalize_url(str(data["canonical_url"]))
    return data


def _merge_metadata(primary: PaperMetadata | None, landing: dict[str, Any]) -> PaperMetadata:
    meta = primary or PaperMetadata()
    for field_name in ("title", "authors", "year", "journal", "abstract"):
        current = getattr(meta, field_name)
        incoming = landing.get(field_name)
        if not current and incoming:
            setattr(meta, field_name, incoming)
    if not meta.doi and landing.get("doi"):
        meta.doi = landing["doi"]
    meta.url = landing.get("canonical_url") or meta.url
    meta.oa_pdf_url = landing.get("pdf_url") or meta.oa_pdf_url
    return meta


def _fallback_label(canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:8]
    return f"unresolved{digest}"


def prepare_link_context(
    url: str,
    requested_mode: str,
    *,
    root: Path = PAPERHUB_ROOT,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    if requested_mode not in {"auto", "metadata-only", "full"}:
        raise ValueError(f"Unsupported requested mode: {requested_mode}")
    session = session or build_session()
    input_url = validate_public_url(url)
    run_id = uuid4().hex[:8]
    work_dir = root / ".paperhub_tmp" / f"link_{hashlib.sha256(input_url.encode()).hexdigest()[:10]}_{run_id}"
    work_dir.mkdir(parents=True, exist_ok=False)
    warnings: list[str] = []
    landing: dict[str, Any] = {"canonical_url": input_url}
    public_pdf_path: Path | None = None

    try:
        final_url, content_type, body = fetch_public_resource(input_url, session)
        landing["canonical_url"] = final_url
        if content_type == "application/pdf":
            public_pdf_path = work_dir / "public_paper.pdf"
            public_pdf_path.write_bytes(body)
        else:
            landing = parse_landing_page(body.decode("utf-8", errors="replace"), final_url)
    except Exception as exc:
        warnings.append(f"Landing-page fetch failed: {type(exc).__name__}: {exc}")

    canonical_url = landing.get("canonical_url") or input_url
    api_meta: PaperMetadata | None = None
    try:
        api_meta = resolve_by_url(canonical_url, session, CONTACT_EMAIL)
    except Exception as exc:
        warnings.append(f"Bibliographic URL lookup failed: {type(exc).__name__}: {exc}")

    if landing.get("doi"):
        try:
            doi_meta = resolve_by_doi(landing["doi"], session, CONTACT_EMAIL)
        except Exception as exc:
            warnings.append(f"DOI lookup failed: {type(exc).__name__}: {exc}")
        else:
            if doi_meta:
                api_meta = doi_meta

    meta = _merge_metadata(api_meta, landing)
    if meta.title and (not meta.authors or not meta.year or not meta.journal or not meta.abstract):
        try:
            title_meta = resolve_by_title(
                meta.title,
                meta.authors[0] if meta.authors else None,
                meta.year,
                session,
                CONTACT_EMAIL,
            )
        except Exception as exc:
            warnings.append(f"Title lookup failed: {type(exc).__name__}: {exc}")
        else:
            if title_meta and title_meta.title:
                similarity = SequenceMatcher(None, meta.title.lower(), title_meta.title.lower()).ratio()
                if similarity >= 0.85:
                    meta = _merge_metadata(title_meta, {**landing, "canonical_url": meta.url or canonical_url})

    if meta.doi:
        canonical_url = f"https://doi.org/{normalize_doi(meta.doi)}"
    else:
        canonical_url = canonicalize_url(meta.url or canonical_url)
    meta.url = canonical_url

    pdf_candidate = None if public_pdf_path else (
        landing.get("pdf_url")
        or meta.oa_pdf_url
        or public_google_drive_download_url(input_url)
    )
    if pdf_candidate:
        try:
            _, content_type, body = fetch_public_resource(str(pdf_candidate), session)
            if content_type != "application/pdf":
                raise ValueError("Public PDF candidate did not return a PDF")
            public_pdf_path = work_dir / "public_paper.pdf"
            public_pdf_path.write_bytes(body)
        except Exception as exc:
            warnings.append(f"Public PDF download failed: {type(exc).__name__}: {exc}")

    missing_fields = [field for field in CORE_FIELDS if not getattr(meta, field)]
    fallback_label = _fallback_label(canonical_url)
    if public_pdf_path and requested_mode == "auto":
        route = "pdf-pending-mode"
    elif public_pdf_path and requested_mode == "metadata-only":
        route = "pdf-metadata"
    elif public_pdf_path and requested_mode == "full":
        route = "pdf-full"
    else:
        route = "link-metadata"
    summary_skipped = requested_mode == "full" and public_pdf_path is None
    if summary_skipped:
        warnings.append("Full summary skipped because no public PDF was available")

    machine_context = {
        "input_url": input_url,
        "canonical_url": canonical_url,
        "metadata": {
            "title": meta.title,
            "authors": meta.authors,
            "year": meta.year,
            "journal": meta.journal,
            "doi": meta.doi,
            "abstract": meta.abstract,
        },
        "missing_fields": missing_fields,
        "fallback_label": fallback_label,
        "public_pdf_path": str(public_pdf_path) if public_pdf_path else None,
        "route": route,
        "requested_mode": requested_mode,
        "summary_skipped": summary_skipped,
    }
    context_lines = [
        "# PaperHub Link Context",
        "",
        f"Input URL: {input_url}",
        f"Canonical URL: {canonical_url}",
        f"Retrieved: {date.today().isoformat()}",
        "",
        "## Citation Metadata",
        f"Title: {meta.title or '[Unknown title]'}",
        f"Authors: {', '.join(meta.authors) if meta.authors else '[Unknown authors]'}",
        f"Year: {meta.year or '[Unknown year]'}",
        f"Journal: {meta.journal or '[Unknown journal]'}",
        f"DOI: {meta.doi or '[Unknown DOI]'}",
        "",
        "## Abstract",
        meta.abstract or "[Abstract not available from public sources]",
        "",
    ]
    context_lines.extend([
        "## Missing Fields",
        ", ".join(missing_fields) if missing_fields else "None",
        "",
        "## Source Evidence",
        f"- Landing or DOI URL: {canonical_url}",
        "",
        "## Coding-Agent Additions",
        "[If needed, replace this line with a fenced JSON object containing "
        "metadata, canonical_url, and source_urls. Only add publicly verified facts.]",
        "",
        "## Machine-Readable Context",
        "```json",
        json.dumps(machine_context, ensure_ascii=False, indent=2),
        "```",
        "",
    ])
    context_path = work_dir / "source_context.txt"
    context_path.write_text("\n".join(context_lines), encoding="utf-8")

    return {
        "success": True,
        "input_url": input_url,
        "canonical_url": canonical_url,
        "context_path": str(context_path),
        "missing_fields": missing_fields,
        "public_pdf_path": str(public_pdf_path) if public_pdf_path else None,
        "route": route,
        "summary_skipped": summary_skipped,
        "cleanup_dir": str(work_dir),
        "warnings": warnings,
    }


def _extract_heading_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    target = heading.strip().lstrip("#").strip().casefold()
    start = None
    level = None
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        if start is None and match.group(2).strip().casefold() == target:
            start = index + 1
            level = len(match.group(1))
            continue
        if start is not None and len(match.group(1)) <= int(level):
            return "\n".join(lines[start:index])
    if start is None:
        raise ValueError(f"Markdown heading not found: {heading}")
    return "\n".join(lines[start:])


def extract_urls(text: str, heading: str | None = None) -> list[str]:
    scope = _extract_heading_section(text, heading) if heading else text
    ordered: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(scope):
        raw = match.group(0).rstrip(".,;:!?")
        canonical = canonicalize_url(raw)
        if canonical not in seen:
            seen.add(canonical)
            ordered.append(raw)
    return ordered


def prepare_link_batch(
    urls: list[str],
    requested_mode: str,
    *,
    root: Path = PAPERHUB_ROOT,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for url in urls:
        try:
            results.append(prepare_link_context(url, requested_mode, root=root))
        except Exception as exc:
            results.append(
                {
                    "success": False,
                    "input_url": url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    failures = [item for item in results if not item.get("success")]
    return {
        "success": not failures,
        "total": len(results),
        "succeeded": len(results) - len(failures),
        "failed": len(failures),
        "results": results,
    }
