"""Read PaperHub metadata notes and edit only a blank frontmatter link."""

from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

from paperhub.config import DEFAULT_ORGANIZED_DIR
from paperhub.metadata_resolution import normalize_arxiv_id, normalize_doi
from paperhub.tag_utils.common import iter_main_metadata_files, parse_frontmatter


SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]*$")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s?#]+", re.IGNORECASE)
ARXIV_RE = re.compile(
    r"(?:(?:https?://)?arxiv\.org/(?:abs|pdf)/|arxiv:\s*)"
    r"([^\s?#]+?)(?:\.pdf)?(?:[?#].*)?$",
    re.IGNORECASE,
)
LINK_LINE_RE = re.compile(
    r"^(?P<prefix>link[ \t]*:[ \t]*)(?P<value>.*?)(?P<newline>\r?\n|$)",
    re.IGNORECASE,
)
CITATION_EXIST_LINE_RE = re.compile(
    r"^(?P<prefix>citation_exist[ \t]*:[ \t]*)(?P<value>.*?)(?P<newline>\r?\n|$)",
    re.IGNORECASE,
)
BLANK_YAML_VALUES = {"", '""', "''", "~", "null"}


class MetadataNoteError(ValueError):
    """A metadata note cannot be read or edited safely."""


@dataclass(frozen=True)
class MetadataNote:
    label: str
    folder: Path
    path: Path
    text: str
    frontmatter: dict[str, Any]
    tags: tuple[str, ...]
    parse_error: str | None
    has_link_field: bool

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or "").strip()

    @property
    def authors(self) -> tuple[str, ...]:
        raw = self.frontmatter.get("authors")
        if isinstance(raw, str):
            return (raw.strip(),) if raw.strip() else ()
        if isinstance(raw, list):
            return tuple(str(value).strip() for value in raw if str(value).strip())
        return ()

    @property
    def year(self) -> int | None:
        match = re.search(r"\b(?:18|19|20|21)\d{2}\b", str(self.frontmatter.get("year") or ""))
        return int(match.group(0)) if match else None

    @property
    def link(self) -> str:
        return str(self.frontmatter.get("link") or "").strip()

    @property
    def citation_path(self) -> Path:
        return self.folder / "citation.csl.json"


def _validate_label(label: str) -> str:
    candidate = str(label).strip()
    if not SAFE_LABEL_RE.fullmatch(candidate):
        raise MetadataNoteError(f"Unsafe paper label: {label!r}")
    return candidate


def read_metadata_note(
    label: str,
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
) -> MetadataNote:
    label = _validate_label(label)
    folder = Path(organized_dir).expanduser().resolve() / label
    path = folder / f"{label}.md"
    if not folder.is_dir() or not path.is_file():
        raise MetadataNoteError(f"Canonical metadata note not found for {label}")
    parsed = parse_frontmatter(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MetadataNoteError(f"Could not read {path}: {exc}") from exc
    lines = text.splitlines(keepends=True)
    delimiters = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"---[ \t]*(?:\r?\n)?", line)
    ]
    link_field_count = 0
    if len(delimiters) >= 2 and delimiters[0] == 0:
        link_field_count = sum(
            bool(LINK_LINE_RE.match(lines[index]))
            for index in range(delimiters[0] + 1, delimiters[1])
        )
    parse_error = parsed.parse_error
    if parse_error is None and link_field_count > 1:
        parse_error = "duplicate top-level link fields"
    return MetadataNote(
        label=label,
        folder=folder,
        path=path,
        text=text,
        frontmatter=parsed.frontmatter,
        tags=tuple(parsed.tags),
        parse_error=parse_error,
        has_link_field=link_field_count == 1 and "link" in parsed.frontmatter,
    )


def iter_metadata_notes(
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
) -> Iterator[MetadataNote]:
    organized_dir = Path(organized_dir).expanduser().resolve()
    if not organized_dir.is_dir():
        return
    for path in iter_main_metadata_files(organized_dir):
        yield read_metadata_note(path.parent.name, organized_dir)


def extract_doi(value: str | None) -> str | None:
    match = DOI_RE.search(str(value or ""))
    return normalize_doi(match.group(0).rstrip(".,;)")) if match else None


def extract_arxiv_id(value: str | None) -> str | None:
    match = ARXIV_RE.search(str(value or "").strip())
    return normalize_arxiv_id(match.group(1)) if match else None


def is_syntactically_usable_public_link(value: str | None) -> bool:
    """Check link syntax without DNS or network access."""
    raw = str(value or "").strip()
    if not raw:
        return False
    if extract_arxiv_id(raw):
        return True
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if parsed.username or parsed.password or not parsed.hostname:
        return False
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return address.is_global


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fill_blank_link(note: MetadataNote, link: str) -> bool:
    """Replace one blank ``link:`` scalar while preserving all other note text."""
    if note.parse_error:
        raise MetadataNoteError(f"Malformed metadata for {note.label}: {note.parse_error}")
    if not note.has_link_field:
        raise MetadataNoteError(f"Metadata note has no link field: {note.label}")
    if note.link:
        raise MetadataNoteError(f"Refusing to replace nonblank link for {note.label}")
    if not is_syntactically_usable_public_link(link):
        raise MetadataNoteError(f"Candidate link is not syntactically public: {link}")

    lines = note.text.splitlines(keepends=True)
    delimiters = [
        index for index, line in enumerate(lines) if re.fullmatch(r"---[ \t]*(?:\r?\n)?", line)
    ]
    if len(delimiters) < 2 or delimiters[0] != 0:
        raise MetadataNoteError(f"Malformed frontmatter delimiters: {note.path}")

    matches: list[tuple[int, re.Match[str]]] = []
    for index in range(delimiters[0] + 1, delimiters[1]):
        match = LINK_LINE_RE.match(lines[index])
        if match:
            matches.append((index, match))
    if len(matches) != 1:
        raise MetadataNoteError(f"Expected exactly one link field in {note.path}")

    index, match = matches[0]
    raw_value = match.group("value")
    scalar, separator, comment = raw_value.partition("#")
    if scalar.strip().casefold() not in BLANK_YAML_VALUES:
        raise MetadataNoteError(f"Refusing to replace nonblank link for {note.label}")
    suffix = f" #{comment}" if separator else ""
    lines[index] = f"{match.group('prefix')}{link}{suffix}{match.group('newline')}"
    atomic_write_text(note.path, "".join(lines))
    return True


def _frontmatter_bounds(note: MetadataNote, lines: list[str]) -> tuple[int, int]:
    delimiters = [
        index for index, line in enumerate(lines) if re.fullmatch(r"---[ \t]*(?:\r?\n)?", line)
    ]
    if len(delimiters) < 2 or delimiters[0] != 0:
        raise MetadataNoteError(f"Malformed frontmatter delimiters: {note.path}")
    return delimiters[0], delimiters[1]


def set_citation_exist(note: MetadataNote) -> bool:
    """Mark ``citation_exist: true`` in one note, preserving all other text.

    Returns True when the note was rewritten, False when it already said
    ``true``. Only ever writes ``true`` — clearing the flag is deliberately not
    supported, so a failed or skipped resolution can never downgrade a note.
    """
    if note.parse_error:
        raise MetadataNoteError(f"Malformed metadata for {note.label}: {note.parse_error}")

    lines = note.text.splitlines(keepends=True)
    start, end = _frontmatter_bounds(note, lines)

    matches = [
        index
        for index in range(start + 1, end)
        if CITATION_EXIST_LINE_RE.match(lines[index])
    ]
    if len(matches) > 1:
        raise MetadataNoteError(f"Expected at most one citation_exist field in {note.path}")

    if matches:
        index = matches[0]
        match = CITATION_EXIST_LINE_RE.match(lines[index])
        assert match is not None
        if match.group("value").strip().casefold() == "true":
            return False
        lines[index] = f"{match.group('prefix')}true{match.group('newline')}"
        atomic_write_text(note.path, "".join(lines))
        return True

    # Insert after ``link:`` to match the established note layout; fall back to
    # the end of the frontmatter block when no link field is present.
    insert_at = end
    for index in range(start + 1, end):
        if LINK_LINE_RE.match(lines[index]):
            insert_at = index + 1
            break

    newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
    lines.insert(insert_at, f"citation_exist: true{newline}")
    atomic_write_text(note.path, "".join(lines))
    return True


def load_citation_sidecar(note: MetadataNote) -> dict[str, Any] | None:
    """Return the first valid legacy ``*.citation.md`` frontmatter mapping."""
    for path in sorted(note.folder.glob("*.citation.md"), key=lambda item: item.name.casefold()):
        parsed = parse_frontmatter(path)
        if parsed.parse_error is None and isinstance(parsed.frontmatter, dict):
            return parsed.frontmatter
    return None
