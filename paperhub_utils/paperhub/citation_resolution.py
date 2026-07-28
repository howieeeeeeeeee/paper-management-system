"""Audit and resolve per-paper CSL-JSON citation files."""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import requests

from paperhub.config import DEFAULT_ORGANIZED_DIR
from paperhub.link_context import (
    fetch_public_resource,
    parse_landing_page,
    validate_public_url,
)
from paperhub.metadata_notes import (
    MetadataNote,
    MetadataNoteError,
    atomic_write_json,
    extract_arxiv_id,
    extract_doi,
    fill_blank_link,
    is_syntactically_usable_public_link,
    load_citation_sidecar,
    read_metadata_note,
    set_citation_exist,
)
from paperhub.metadata_resolution import (
    CONTACT_EMAIL,
    PaperMetadata,
    build_session,
    normalize_doi,
    resolve_by_arxiv,
)


CITATION_FILENAME = "citation.csl.json"
CSL_JSON_ACCEPT = "application/vnd.citationstyles.csl+json"
DOI_CSL_MAX_BYTES = 2 * 1024 * 1024
WEB_DISCOVERED_TITLE_THRESHOLD = 0.90
EXISTING_LINK_TITLE_THRESHOLD = 0.85
COMPATIBLE_YEAR_DELTA = 1
AUDIT_CATEGORIES = (
    "ready",
    "needs_citation_from_link",
    "needs_link_then_citation",
    "blocked",
)
CROSSREF_TO_CSL_TYPES = {
    "book-chapter": "chapter",
    "dissertation": "thesis",
    "journal-article": "article-journal",
    "posted-content": "manuscript",
    "proceedings-article": "paper-conference",
}


class CitationResolutionError(RuntimeError):
    """Citation resolution failed without modifying a valid citation file."""


class IdentityMismatchError(CitationResolutionError):
    """Resolved citation data does not identify the selected paper."""


@dataclass(frozen=True)
class CitationFileState:
    status: str
    data: dict[str, Any] | None
    errors: tuple[str, ...]


def validate_csl_object(
    value: Any,
    *,
    expected_label: str | None = None,
) -> tuple[bool, tuple[str, ...]]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return False, ("CSL root must be an object",)
    for field in ("id", "type", "title"):
        if not isinstance(value.get(field), str) or not str(value[field]).strip():
            errors.append(f"{field} must be a nonempty string")
    if expected_label and value.get("id") != expected_label:
        errors.append(f"id must equal paper label {expected_label}")

    for field in ("author", "editor"):
        people = value.get(field)
        if people is None:
            continue
        if not isinstance(people, list):
            errors.append(f"{field} must be a list")
            continue
        for index, person in enumerate(people):
            if not isinstance(person, dict):
                errors.append(f"{field}[{index}] must be an object")
                continue
            if not any(
                isinstance(person.get(key), str) and person[key].strip()
                for key in ("family", "given", "literal")
            ):
                errors.append(f"{field}[{index}] has no name fields")

    issued = value.get("issued")
    if issued is not None:
        date_parts = issued.get("date-parts") if isinstance(issued, dict) else None
        if (
            not isinstance(date_parts, list)
            or not date_parts
            or not all(
                isinstance(part, list)
                and part
                and all(
                    isinstance(component, int) and not isinstance(component, bool)
                    for component in part
                )
                for part in date_parts
            )
        ):
            errors.append("issued.date-parts must contain nonempty integer date lists")
    return not errors, tuple(errors)


def inspect_citation_file(
    path: Path,
    *,
    expected_label: str | None = None,
) -> CitationFileState:
    if not path.is_file():
        return CitationFileState("missing", None, ())
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CitationFileState("invalid", None, (f"{type(exc).__name__}: {exc}",))
    valid, errors = validate_csl_object(value, expected_label=expected_label)
    return CitationFileState("valid" if valid else "invalid", value if isinstance(value, dict) else None, errors)


def _metadata_block_reason(note: MetadataNote) -> str | None:
    if note.parse_error:
        return f"malformed_metadata: {note.parse_error}"
    if not note.title:
        return "malformed_metadata: missing title"
    if not note.authors and note.year is None:
        return "malformed_metadata: both authors and year are missing"
    if not note.has_link_field:
        return "malformed_metadata: missing link field"
    return None


def audit_citations(
    labels: Iterable[str],
    *,
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
) -> dict[str, Any]:
    """Classify citation coverage without network requests or file writes."""
    ordered_labels = tuple(dict.fromkeys(str(label).strip() for label in labels if str(label).strip()))
    categories = {category: [] for category in AUDIT_CATEGORIES}
    items: list[dict[str, Any]] = []
    invalid_count = 0

    for label in ordered_labels:
        item: dict[str, Any] = {"label": label}
        try:
            note = read_metadata_note(label, organized_dir)
        except MetadataNoteError as exc:
            category = "blocked"
            item.update(reason=f"malformed_metadata: {exc}", citation_status="unknown")
        else:
            citation = inspect_citation_file(note.citation_path, expected_label=label)
            item["citation_status"] = citation.status
            item["citation_errors"] = list(citation.errors)
            if citation.status == "invalid":
                invalid_count += 1
            if citation.status == "valid":
                category = "ready"
            elif reason := _metadata_block_reason(note):
                category = "blocked"
                item["reason"] = reason
            elif note.link:
                if is_syntactically_usable_public_link(note.link):
                    category = "needs_citation_from_link"
                else:
                    category = "blocked"
                    item["reason"] = "malformed_or_nonpublic_link"
            else:
                category = "needs_link_then_citation"
            item["link"] = note.link
        item["category"] = category
        categories[category].append(label)
        items.append(item)

    return {
        "selected_papers": len(ordered_labels),
        "counts": {category: len(categories[category]) for category in AUDIT_CATEGORIES},
        "invalid_existing_citation_files": invalid_count,
        "categories": categories,
        "items": items,
        "files_changed": 0,
    }


def _normalize_title(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def _surname(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        return ""
    if "," in normalized:
        return _normalize_title(normalized.split(",", 1)[0]).replace(" ", "")
    parts = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]+", normalized)
    return _normalize_title(parts[-1]).replace(" ", "") if parts else ""


def _csl_first_surname(csl: dict[str, Any]) -> str:
    authors = csl.get("author")
    if not isinstance(authors, list) or not authors or not isinstance(authors[0], dict):
        return ""
    first = authors[0]
    return _surname(str(first.get("family") or first.get("literal") or ""))


def _csl_year(csl: dict[str, Any]) -> int | None:
    try:
        value = csl["issued"]["date-parts"][0][0]
        return int(value)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def validate_identity(
    note: MetadataNote,
    csl: dict[str, Any],
    *,
    agent_discovered: bool,
) -> dict[str, Any]:
    threshold = (
        WEB_DISCOVERED_TITLE_THRESHOLD
        if agent_discovered
        else EXISTING_LINK_TITLE_THRESHOLD
    )
    similarity = SequenceMatcher(
        None,
        _normalize_title(note.title),
        _normalize_title(str(csl.get("title") or "")),
    ).ratio()
    note_surname = _surname(note.authors[0]) if note.authors else ""
    csl_surname = _csl_first_surname(csl)
    surname_match = bool(note_surname and csl_surname and note_surname == csl_surname)
    resolved_year = _csl_year(csl)
    year_match = bool(
        note.year is not None
        and resolved_year is not None
        and abs(note.year - resolved_year) <= COMPATIBLE_YEAR_DELTA
    )
    expected_doi = extract_doi(str(note.frontmatter.get("doi") or "")) or extract_doi(note.link)
    resolved_doi = extract_doi(str(csl.get("DOI") or ""))
    doi_match = not expected_doi or (resolved_doi == expected_doi)
    valid = similarity >= threshold and (surname_match or year_match) and doi_match
    return {
        "valid": valid,
        "title_similarity": round(similarity, 4),
        "required_title_similarity": threshold,
        "surname_match": surname_match,
        "year_match": year_match,
        "doi_match": doi_match,
        "expected_doi": expected_doi,
        "resolved_doi": resolved_doi,
    }


def _person_from_name(value: str) -> dict[str, str]:
    name = re.sub(r"\s+", " ", str(value)).strip()
    if not name:
        return {"literal": "[Unknown author]"}
    if "," in name:
        family, given = (part.strip() for part in name.split(",", 1))
    else:
        parts = name.split()
        family, given = parts[-1], " ".join(parts[:-1])
    result = {"family": family}
    if given:
        result["given"] = given
    return result


def paper_metadata_to_csl(meta: PaperMetadata) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": "temporary",
        "type": (
            "article-journal"
            if meta.journal and meta.journal.casefold() != "arxiv preprint"
            else "manuscript"
        ),
        "title": meta.title or "[Unknown title]",
        "author": [_person_from_name(author) for author in meta.authors],
    }
    if meta.year:
        value["issued"] = {"date-parts": [[meta.year]]}
    if meta.journal:
        value["container-title"] = meta.journal
    if meta.doi:
        value["DOI"] = normalize_doi(meta.doi)
    if meta.url:
        value["URL"] = meta.url
    return value


def landing_metadata_to_csl(data: dict[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": "temporary",
        "type": "article-journal" if data.get("journal") else "article",
        "title": str(data.get("title") or "[Unknown title]"),
        "author": [_person_from_name(author) for author in data.get("authors") or []],
    }
    if data.get("year"):
        value["issued"] = {"date-parts": [[int(data["year"])]]}
    if data.get("journal"):
        value["container-title"] = str(data["journal"])
    if data.get("doi"):
        value["DOI"] = normalize_doi(str(data["doi"]))
    if data.get("canonical_url"):
        value["URL"] = str(data["canonical_url"])
    return value


def sidecar_to_csl(data: dict[str, Any]) -> dict[str, Any]:
    return landing_metadata_to_csl(
        {
            "title": data.get("title"),
            "authors": data.get("authors") or [],
            "year": data.get("year"),
            "journal": data.get("journal"),
            "doi": data.get("doi"),
            "canonical_url": data.get("link") or data.get("url"),
        }
    )


def normalize_csl(
    value: dict[str, Any],
    *,
    label: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    normalized = deepcopy(value)
    normalized["id"] = label
    source_type = str(normalized.get("type") or "").strip()
    if source_type:
        normalized["type"] = CROSSREF_TO_CSL_TYPES.get(source_type, source_type)
    doi = extract_doi(str(normalized.get("DOI") or normalized.get("doi") or ""))
    if doi:
        normalized["DOI"] = doi
        normalized.pop("doi", None)
        normalized["URL"] = f"https://doi.org/{doi}"
    elif source_url:
        normalized["URL"] = source_url
    return normalized


def fetch_doi_csl(
    doi: str,
    session: requests.Session,
) -> dict[str, Any]:
    doi = normalize_doi(doi)
    response = session.get(
        f"https://doi.org/{doi}",
        headers={"Accept": CSL_JSON_ACCEPT},
        timeout=30,
    )
    response.raise_for_status()
    content = getattr(response, "content", b"")
    if content and len(content) > DOI_CSL_MAX_BYTES:
        raise CitationResolutionError("DOI CSL response exceeds size limit")
    try:
        value = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise CitationResolutionError(f"DOI did not return CSL JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CitationResolutionError("DOI CSL response root is not an object")
    return value


def _resolve_sidecar(note: MetadataNote) -> dict[str, Any] | None:
    sidecar = load_citation_sidecar(note)
    return sidecar_to_csl(sidecar) if sidecar else None


def _resolve_link(
    note: MetadataNote,
    link: str,
    session: requests.Session,
    *,
    agent_discovered: bool,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    arxiv_id = extract_arxiv_id(link)
    doi = extract_doi(link)
    source_url = link
    if doi:
        csl = fetch_doi_csl(doi, session)
        source_url = f"https://doi.org/{doi}"
    elif arxiv_id:
        meta = resolve_by_arxiv(arxiv_id, session)
        if meta is None:
            raise CitationResolutionError("arXiv metadata lookup returned no record")
        csl = paper_metadata_to_csl(meta)
        source_url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        public_url = validate_public_url(link)
        final_url, content_type, body = fetch_public_resource(public_url, session)
        if content_type == "application/pdf":
            sidecar_csl = _resolve_sidecar(note)
            if sidecar_csl is None:
                raise CitationResolutionError("Linked resource is a PDF with no citation sidecar")
            csl = sidecar_csl
            source_url = final_url
        else:
            landing = parse_landing_page(body.decode("utf-8", errors="replace"), final_url)
            landing_doi = extract_doi(str(landing.get("doi") or ""))
            final_arxiv = extract_arxiv_id(final_url)
            if landing_doi:
                csl = fetch_doi_csl(landing_doi, session)
                source_url = f"https://doi.org/{landing_doi}"
            elif final_arxiv:
                meta = resolve_by_arxiv(final_arxiv, session)
                if meta is None:
                    raise CitationResolutionError("arXiv metadata lookup returned no record")
                csl = paper_metadata_to_csl(meta)
                source_url = f"https://arxiv.org/abs/{final_arxiv}"
            else:
                csl = landing_metadata_to_csl(landing)
                source_url = str(landing.get("canonical_url") or final_url)

    csl = normalize_csl(csl, label=note.label, source_url=source_url)
    identity = validate_identity(note, csl, agent_discovered=agent_discovered)
    if not identity["valid"]:
        raise IdentityMismatchError(
            "Resolved citation failed identity validation: "
            + json.dumps(identity, ensure_ascii=False, sort_keys=True)
        )
    valid, errors = validate_csl_object(csl, expected_label=note.label)
    if not valid:
        raise CitationResolutionError("Resolved CSL is invalid: " + "; ".join(errors))
    return csl, source_url, identity


#: Result statuses whose ``citation.csl.json`` is known-valid afterwards, and so
#: earn the derived ``citation_exist: true`` metadata flag.
CITATION_EXIST_STATUSES = frozenset({"resolved", "skipped_valid"})


def resolve_one(
    label: str,
    *,
    candidate_link: str | None = None,
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
    session: requests.Session | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Resolve one paper's citation and stamp the derived ``citation_exist`` flag.

    The flag is written here rather than by the calling skill so that every
    entry point — the citation-resolver skill and the paper-organizer post-AI
    hook alike — leaves identical metadata. Stamping never turns a successful
    resolution into a failure; a write problem is reported alongside the result.
    """
    result = _resolve_one(
        label,
        candidate_link=candidate_link,
        organized_dir=organized_dir,
        session=session,
        refresh=refresh,
    )
    if result.get("status") in CITATION_EXIST_STATUSES:
        try:
            note = read_metadata_note(label, organized_dir)
            result["citation_exist_written"] = set_citation_exist(note)
        except (MetadataNoteError, OSError) as exc:
            result["citation_exist_written"] = False
            result["citation_exist_warning"] = f"{type(exc).__name__}: {exc}"
    return result


def _resolve_one(
    label: str,
    *,
    candidate_link: str | None = None,
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
    session: requests.Session | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    note = read_metadata_note(label, organized_dir)
    existing = inspect_citation_file(note.citation_path, expected_label=label)
    if existing.status == "valid" and not refresh:
        return {"label": label, "status": "skipped_valid", "citation_path": str(note.citation_path)}
    if reason := _metadata_block_reason(note):
        return {"label": label, "status": "blocked", "reason": reason}

    session = session or build_session(CONTACT_EMAIL)
    agent_discovered = False
    link = note.link
    sidecar_csl = _resolve_sidecar(note)
    if not link and sidecar_csl is not None:
        csl = normalize_csl(sidecar_csl, label=label)
        identity = validate_identity(note, csl, agent_discovered=False)
        if not identity["valid"]:
            return {
                "label": label,
                "status": "identity_mismatch",
                "reason": "Legacy citation sidecar did not match metadata",
                "identity": identity,
            }
        valid, errors = validate_csl_object(csl, expected_label=label)
        if not valid:
            return {"label": label, "status": "failed", "reason": "; ".join(errors)}
        try:
            atomic_write_json(note.citation_path, csl)
        except OSError as exc:
            return {
                "label": label,
                "status": "failed",
                "error_kind": "write_error",
                "reason": f"write failed: {exc}",
            }
        return {
            "label": label,
            "status": "resolved",
            "source": "citation_sidecar",
            "citation_path": str(note.citation_path),
            "link_updated": False,
        }

    if not link:
        if not candidate_link:
            return {"label": label, "status": "needs_candidate_link"}
        if not is_syntactically_usable_public_link(candidate_link):
            return {"label": label, "status": "blocked", "reason": "malformed_or_nonpublic_candidate"}
        link = candidate_link
        agent_discovered = True
    elif not is_syntactically_usable_public_link(link):
        return {"label": label, "status": "blocked", "reason": "malformed_or_nonpublic_link"}

    try:
        csl, source_url, identity = _resolve_link(
            note,
            link,
            session,
            agent_discovered=agent_discovered,
        )
    except IdentityMismatchError as exc:
        return {
            "label": label,
            "status": "identity_mismatch" if agent_discovered else "link_conflict",
            "reason": str(exc),
        }
    except Exception as exc:
        return {
            "label": label,
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}",
        }

    link_updated = False
    if agent_discovered:
        preferred_link = (
            f"https://doi.org/{csl['DOI']}"
            if csl.get("DOI")
            else source_url
        )
        try:
            link_updated = fill_blank_link(note, preferred_link)
        except (MetadataNoteError, OSError) as exc:
            return {
                "label": label,
                "status": "failed",
                "error_kind": "write_error" if isinstance(exc, OSError) else "metadata_error",
                "reason": str(exc),
            }
    try:
        atomic_write_json(note.citation_path, csl)
    except OSError as exc:
        return {
            "label": label,
            "status": "failed",
            "error_kind": "write_error",
            "reason": f"write failed: {exc}",
            "link_updated": link_updated,
        }
    return {
        "label": label,
        "status": "resolved",
        "source": "agent_candidate" if agent_discovered else "metadata_link",
        "source_url": source_url,
        "citation_path": str(note.citation_path),
        "link_updated": link_updated,
        "identity": identity,
        "repaired_invalid": existing.status == "invalid",
    }


def resolve_citations(
    labels: Iterable[str],
    *,
    candidate_links: dict[str, str] | None = None,
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
    session: requests.Session | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    ordered = tuple(dict.fromkeys(str(label).strip() for label in labels if str(label).strip()))
    candidates = candidate_links or {}
    shared_session = session or build_session(CONTACT_EMAIL)
    results: list[dict[str, Any]] = []
    for label in ordered:
        try:
            result = resolve_one(
                label,
                candidate_link=candidates.get(label),
                organized_dir=organized_dir,
                session=shared_session,
                refresh=refresh,
            )
        except MetadataNoteError as exc:
            if str(exc).startswith("Unsafe paper label:"):
                raise
            result = {
                "label": label,
                "status": "blocked",
                "reason": f"malformed_metadata: {exc}",
            }
        except Exception as exc:
            result = {
                "label": label,
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        results.append(result)
    success_statuses = {"resolved", "skipped_valid"}
    failures = [result for result in results if result["status"] not in success_statuses]
    fatal_write_errors = [
        result for result in results if result.get("error_kind") == "write_error"
    ]
    return {
        "selected_papers": len(ordered),
        "resolved": sum(result["status"] == "resolved" for result in results),
        "skipped_valid": sum(result["status"] == "skipped_valid" for result in results),
        "failed": len(failures),
        "fatal_write_errors": len(fatal_write_errors),
        "success": not failures,
        "results": results,
    }
