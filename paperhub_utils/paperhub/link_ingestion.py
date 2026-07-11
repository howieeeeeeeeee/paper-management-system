"""Build prompts and organize link-only PaperHub responses."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from paperhub.config import DEFAULT_ORGANIZED_DIR, MY_RESEARCH_INTERESTS
from paperhub.prompt.builder import MODE_LINK_METADATA, build_prompt


MACHINE_CONTEXT_RE = re.compile(
    r"^## Machine-Readable Context\s*\n```json\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)
CODING_ADDITIONS_RE = re.compile(
    r"^## Coding-Agent Additions\s*\n```json\s*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def _merge_coding_agent_additions(
    source: dict[str, Any],
    additions: dict[str, Any],
) -> dict[str, Any]:
    verified = source.get("metadata")
    if not isinstance(verified, dict):
        verified = {}
        source["metadata"] = verified
    added_metadata = additions.get("metadata")
    if isinstance(added_metadata, dict):
        for field in ("title", "authors", "year", "journal", "doi", "abstract"):
            if added_metadata.get(field):
                verified[field] = added_metadata[field]
    added_canonical = additions.get("canonical_url")
    if isinstance(added_canonical, str) and added_canonical.strip():
        source["canonical_url"] = added_canonical.strip()
    source["missing_fields"] = [
        field
        for field in ("title", "authors", "year", "journal", "abstract")
        if not verified.get(field)
    ]
    return source


def load_link_context(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    match = MACHINE_CONTEXT_RE.search(text)
    if not match:
        raise ValueError(f"Link context has no machine-readable JSON block: {path}")
    data = json.loads(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("Machine-readable link context must be a JSON object")
    additions_match = CODING_ADDITIONS_RE.search(text)
    if additions_match:
        additions = json.loads(additions_match.group(1))
        if not isinstance(additions, dict):
            raise ValueError("Coding-Agent Additions JSON must be an object")
        data = _merge_coding_agent_additions(data, additions)
    return text, data


def create_link_prompt(context_path: Path, additional_instruction: str = "") -> str:
    context_text, _ = load_link_context(context_path)
    return build_prompt(
        MODE_LINK_METADATA,
        today=date.today().isoformat(),
        research_interests=MY_RESEARCH_INTERESTS,
        additional_instruction=additional_instruction,
        link_context_text=context_text,
    )


def materialize_public_pdf_sidecar(
    context_path: Path,
    route: str | None = None,
) -> Path:
    """Write authoritative merged link metadata beside a downloaded public PDF."""
    _, source = load_link_context(context_path)
    public_pdf_value = source.get("public_pdf_path")
    if not public_pdf_value:
        raise ValueError(f"Link context has no public PDF: {context_path}")
    public_pdf = Path(str(public_pdf_value)).expanduser().resolve()
    if not public_pdf.exists() or not public_pdf.is_file():
        raise FileNotFoundError(f"Public PDF not found: {public_pdf}")
    verified = source.get("metadata")
    if not isinstance(verified, dict):
        verified = {}
    sidecar_data = {
        "paperhub_link_context": True,
        "title": verified.get("title"),
        "authors": verified.get("authors") or [],
        "year": verified.get("year"),
        "journal": verified.get("journal"),
        "doi": verified.get("doi"),
        "link": source.get("canonical_url") or source.get("input_url"),
        "abstract": verified.get("abstract"),
        "route": route or source.get("route"),
    }
    sidecar_path = public_pdf.with_name(public_pdf.stem + ".citation.md")
    sidecar_path.write_text(
        "---\n"
        + yaml.safe_dump(
            sidecar_data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).strip()
        + "\n---\n",
        encoding="utf-8",
    )
    return sidecar_path


def normalize_link_key(url: str) -> str:
    raw = str(url).strip()
    doi_match = re.fullmatch(
        r"(?:(?:https?://)?(?:dx\.)?doi\.org/|doi:\s*)?(10\.\d{4,9}/\S+)",
        raw,
        flags=re.IGNORECASE,
    )
    if doi_match:
        return f"doi:{doi_match.group(1).rstrip('.,;)').lower()}"
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    netloc = host
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def find_existing_link(canonical_url: str, organized_dir: Path) -> dict[str, str] | None:
    target = normalize_link_key(canonical_url)
    if not organized_dir.exists():
        return None
    for folder in sorted(path for path in organized_dir.iterdir() if path.is_dir()):
        metadata_path = folder / f"{folder.name}.md"
        if not metadata_path.exists():
            continue
        text = metadata_path.read_text(encoding="utf-8", errors="replace")
        match = re.match(r"(?s)^---\n(.*?)\n---", text)
        if not match:
            continue
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            continue
        existing = frontmatter.get("link")
        if existing and normalize_link_key(str(existing)) == target:
            return {"paper_label": folder.name, "metadata_path": str(metadata_path)}
    return None


def _parse_engine_metadata(metadata_text: str) -> tuple[dict[str, Any], str | None]:
    frontmatter: dict[str, Any] = {}
    abstract = None
    match = re.match(r"(?s)^---\n(.*?)\n---", metadata_text.strip())
    if match:
        loaded = yaml.safe_load(match.group(1)) or {}
        if isinstance(loaded, dict):
            frontmatter = loaded
    abstract_match = re.search(
        r"^##\s+Abstract\s*$\n(.*?)(?=^##\s+|\Z)",
        metadata_text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if abstract_match:
        abstract = abstract_match.group(1).strip()
    return frontmatter, abstract


def _parse_link_response(content: str) -> dict[str, str]:
    from scripts.paper_summarizer import parse_api_response

    try:
        return parse_api_response(content, "metadata-only")
    except ValueError:
        match = re.match(
            r"\s*#\s+(?!paper_label\s*$)([^\n]+)\s*\n"
            r"#\s+metadata\s*\n(.*)\Z",
            content,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        if not match:
            raise
        return {
            "paper_label": match.group(1).strip(),
            "metadata": match.group(2).strip(),
        }


def _clean_label(label: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]", "", str(label).strip().lower())
    return cleaned if cleaned else fallback


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return yaml.safe_dump(value, allow_unicode=True, default_flow_style=True).strip()


def build_link_metadata_markdown(
    source: dict[str, Any],
    engine_frontmatter: dict[str, Any],
    engine_abstract: str | None,
) -> str:
    verified = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    title = verified.get("title") or engine_frontmatter.get("title") or "[Unknown title]"
    authors = verified.get("authors") or engine_frontmatter.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    year = verified.get("year") or engine_frontmatter.get("year") or None
    journal = verified.get("journal") or engine_frontmatter.get("journal") or ""
    canonical_url = source.get("canonical_url") or engine_frontmatter.get("link") or ""
    tags = engine_frontmatter.get("tags") or ["untagged"]
    if isinstance(tags, str):
        tags = [tags]
    tags = [re.sub(r"\s+", "_", str(tag).strip()) for tag in tags if str(tag).strip()]
    tags = tags[:5] or ["untagged"]
    abstract = verified.get("abstract") or engine_abstract
    if not abstract:
        abstract = "[Abstract not available from public sources]"

    lines = [
        "---",
        f"title: {_yaml_scalar(str(title))}",
        "authors:",
    ]
    if authors:
        lines.extend(f"  - {_yaml_scalar(str(author))}" for author in authors)
    else:
        lines[-1] = "authors: []"
    lines.extend(
        [
            f"year: {year if year is not None else ''}",
            f"journal: {_yaml_scalar(str(journal))}",
            f"link: {_yaml_scalar(str(canonical_url))}",
            "status:",
            "  - initiated",
            "tags:",
        ]
    )
    lines.extend(f"  - {_yaml_scalar(tag)}" for tag in tags)
    lines.extend(
        [
            f"created: {date.today().isoformat()}",
            "interest: none",
            "importance: none",
            "contributions:",
            "---",
            "",
            f"# {title}",
            "",
            "## Abstract",
            str(abstract).strip(),
            "",
        ]
    )
    return "\n".join(lines)


def organize_link_response(
    *,
    content: str,
    context_path: Path,
    model_label: str,
    output_dir: Path = DEFAULT_ORGANIZED_DIR,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context_text, source = load_link_context(context_path)
    del context_text
    canonical_url = str(source.get("canonical_url") or source.get("input_url") or "")
    existing = find_existing_link(canonical_url, output_dir)
    if existing:
        return {
            "success": True,
            "skipped": True,
            "already_exists": True,
            "paper_label": existing["paper_label"],
            "metadata_path": existing["metadata_path"],
            "canonical_url": canonical_url,
            "files_created": [],
            "warnings": ["Canonical link already exists; no files were changed"],
        }

    parsed = _parse_link_response(content)
    fallback = str(source.get("fallback_label") or "")
    if not fallback:
        fallback = f"unresolved{hashlib.sha256(canonical_url.encode()).hexdigest()[:8]}"
    label = _clean_label(parsed.get("paper_label", ""), fallback)
    paper_dir = output_dir / label
    if paper_dir.exists():
        raise FileExistsError(f"Output folder already exists: {paper_dir}")

    metadata_text = parsed.get("metadata")
    if not isinstance(metadata_text, str):
        raise ValueError("Link engine response did not contain Markdown metadata")
    engine_frontmatter, engine_abstract = _parse_engine_metadata(metadata_text)
    final_metadata = build_link_metadata_markdown(source, engine_frontmatter, engine_abstract)

    paper_dir.mkdir(parents=True, exist_ok=False)
    metadata_path = paper_dir / f"{label}.md"
    files_created = [metadata_path.name]
    pdf_path = None
    try:
        metadata_path.write_text(final_metadata, encoding="utf-8")
        public_pdf = source.get("public_pdf_path")
        if public_pdf:
            source_pdf = Path(str(public_pdf))
            if source_pdf.exists():
                pdf_path = paper_dir / source_pdf.name
                shutil.move(str(source_pdf), str(pdf_path))
                files_created.append(pdf_path.name)
    except Exception:
        shutil.rmtree(paper_dir, ignore_errors=True)
        raise

    result: dict[str, Any] = {
        "success": True,
        "input_kind": "link",
        "summary_mode": "link-metadata",
        "model": model_label,
        "paper_label": label,
        "canonical_url": canonical_url,
        "output_dir": str(paper_dir),
        "metadata_path": str(metadata_path),
        "files_created": files_created,
        "pdf_moved": pdf_path is not None,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "summary_skipped": bool(source.get("summary_skipped")),
        "missing_fields": source.get("missing_fields") or [],
        "warnings": [],
        "errors": [],
    }
    if usage:
        result["usage"] = usage
    return result
