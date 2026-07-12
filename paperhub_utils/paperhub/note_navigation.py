"""Reciprocal navigation links for PaperHub metadata and AI summaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


AI_SUMMARY_LINK = "[[ai_summary|Link to AI Summary]]"
RELATED_DOCS_HEADING = "### Related Docs"
METADATA_FOOTER = f"---\n{RELATED_DOCS_HEADING}\n{AI_SUMMARY_LINK}\n"

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n.*?^---[ \t]*\r?\n",
    re.MULTILINE | re.DOTALL,
)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


@dataclass(frozen=True)
class NavigationUpdate:
    """Which side of a metadata/summary pair changed."""

    metadata_changed: bool
    summary_changed: bool

    @property
    def changed(self) -> bool:
        return self.metadata_changed or self.summary_changed


def _is_ai_summary_target(target: str) -> bool:
    normalized = target.strip().replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1]
    if name.lower().endswith(".md"):
        name = name[:-3]
    return name.lower() == "ai_summary"


def add_ai_summary_link_to_metadata(text: str) -> str:
    """Ensure the metadata note ends with the canonical AI-summary link.

    An existing summary link is normalized only when it appears in the final
    ``### Related Docs`` section. Links elsewhere in the note are user content
    and are intentionally left untouched.
    """

    heading_start = text.rfind(RELATED_DOCS_HEADING)
    if heading_start >= 0:
        footer = text[heading_start:]
        for match in _WIKILINK_RE.finditer(footer):
            if _is_ai_summary_target(match.group(1)):
                absolute_start = heading_start + match.start()
                absolute_end = heading_start + match.end()
                return text[:absolute_start] + AI_SUMMARY_LINK + text[absolute_end:]

    base = text.rstrip()
    if base:
        return f"{base}\n\n{METADATA_FOOTER}"
    return METADATA_FOOTER


def add_metadata_link_to_summary(text: str, metadata_stem: str) -> str:
    """Place the canonical metadata backlink at the top of visible content."""

    if not metadata_stem.strip():
        raise ValueError("metadata_stem must not be blank")

    backlink = f"[[{metadata_stem}|Back to Metadata]]"
    frontmatter = _FRONTMATTER_RE.match(text)
    if text.startswith("---") and frontmatter is None:
        raise ValueError("ai_summary.md starts with unclosed YAML frontmatter")

    if frontmatter:
        prefix = frontmatter.group(0)
        body = text[frontmatter.end():].lstrip("\r\n")
    else:
        prefix = ""
        body = text.lstrip("\r\n")

    if body == backlink or body.startswith(f"{backlink}\n") or body.startswith(
        f"{backlink}\r\n"
    ):
        return text

    separator = "\n" if prefix else ""
    if body:
        return f"{prefix}{separator}{backlink}\n\n{body}"
    return f"{prefix}{separator}{backlink}\n"


def ensure_navigation_links(
    metadata_path: Path,
    summary_path: Path,
) -> NavigationUpdate:
    """Add reciprocal links to an explicit metadata/``ai_summary.md`` pair."""

    metadata_path = Path(metadata_path)
    summary_path = Path(summary_path)
    if summary_path.name != "ai_summary.md":
        raise ValueError("navigation is supported only for ai_summary.md")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
    if not summary_path.is_file():
        raise FileNotFoundError(f"AI summary file not found: {summary_path}")

    metadata_text = metadata_path.read_text(encoding="utf-8")
    summary_text = summary_path.read_text(encoding="utf-8")
    new_metadata = add_ai_summary_link_to_metadata(metadata_text)
    new_summary = add_metadata_link_to_summary(summary_text, metadata_path.stem)

    metadata_changed = new_metadata != metadata_text
    summary_changed = new_summary != summary_text
    if metadata_changed:
        metadata_path.write_text(new_metadata, encoding="utf-8")
    if summary_changed:
        summary_path.write_text(new_summary, encoding="utf-8")

    return NavigationUpdate(
        metadata_changed=metadata_changed,
        summary_changed=summary_changed,
    )
