"""Shared helpers for tag_utils scripts.

Walks the PaperHub `organized/` tree, locates each paper's main metadata file
(the `.md` file whose stem matches its parent folder), and parses YAML
frontmatter robustly.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml

from config import DEFAULT_ORGANIZED_DIR, DEFAULT_TAGS_DIR

INTERNAL_SUBDIR = "_internal"  # system files (registry, names lists, history)

FRONTMATTER_DELIM = "---"


@dataclass
class PaperMeta:
    path: Path
    paper_label: str  # parent folder name
    frontmatter: dict
    body: str
    parse_error: str | None = None
    tags: list[str] = field(default_factory=list)


def iter_main_metadata_files(organized_dir: Path = DEFAULT_ORGANIZED_DIR) -> Iterator[Path]:
    """Yield the main `.md` file for each paper folder.

    Convention: each paper has a folder under `organized/`, and the main
    metadata file shares the folder's name (e.g.,
    `organized/ACF2015/ACF2015.md`). Auxiliary files like `summary.md`,
    `ai_summary.md`, lecture notes, etc. are skipped.

    Folders without a matching main file are silently skipped (rare; logged
    by callers if needed).
    """
    for folder in sorted(organized_dir.iterdir()):
        if not folder.is_dir():
            continue
        candidate = folder / f"{folder.name}.md"
        if candidate.is_file():
            yield candidate


def parse_frontmatter(md_path: Path) -> PaperMeta:
    """Parse a metadata `.md` file's YAML frontmatter and tags.

    Returns a PaperMeta with parse_error set if frontmatter is malformed.
    Tags are normalized to a list of strings (handles scalar `tags:` too).
    """
    paper_label = md_path.parent.name
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError as e:
        return PaperMeta(
            path=md_path,
            paper_label=paper_label,
            frontmatter={},
            body="",
            parse_error=f"read failed: {e}",
        )

    if not text.lstrip().startswith(FRONTMATTER_DELIM):
        return PaperMeta(
            path=md_path,
            paper_label=paper_label,
            frontmatter={},
            body=text,
            parse_error="no frontmatter",
        )

    # Split on the first two `---` delimiters.
    parts = text.split(f"\n{FRONTMATTER_DELIM}", 1)
    if len(parts) != 2:
        return PaperMeta(
            path=md_path,
            paper_label=paper_label,
            frontmatter={},
            body=text,
            parse_error="unterminated frontmatter",
        )
    raw_fm = parts[0].lstrip().removeprefix(FRONTMATTER_DELIM).lstrip("\n")
    body = parts[1].lstrip("\n")

    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError as e:
        return PaperMeta(
            path=md_path,
            paper_label=paper_label,
            frontmatter={},
            body=body,
            parse_error=f"YAML parse error: {e}",
        )

    if not isinstance(fm, dict):
        return PaperMeta(
            path=md_path,
            paper_label=paper_label,
            frontmatter={},
            body=body,
            parse_error=f"frontmatter is not a mapping (got {type(fm).__name__})",
        )

    tags = _coerce_tag_list(fm.get("tags"))
    return PaperMeta(
        path=md_path,
        paper_label=paper_label,
        frontmatter=fm,
        body=body,
        tags=tags,
    )


def _coerce_tag_list(raw) -> list[str]:
    """Tolerant coercion of the `tags` field to a list of stripped strings.

    Handles the three forms seen in the wild: list of strings, single scalar
    string, or missing/None.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    return []


def warn(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---- Surgical YAML tag-block editing ----
#
# Used by both the per-batch register_tag flow (rename a single tag in one
# paper) and the periodic apply_renames flow (bulk merges across the library).
# Line-based instead of full YAML re-emit to keep diffs minimal and preserve
# unrelated frontmatter formatting.

TAG_ITEM_RE = re.compile(r"^(\s+-\s+)(['\"]?)(?P<tag>[^\s#'\"]+)\2(\s*(?:#.*)?)$")


def find_tags_block(lines: list[str]) -> tuple[int, int] | None:
    """Locate the `tags:` block in frontmatter. Returns (start, end) where
    start is the line index of `tags:` and end is one past the last list
    item line. Returns None if no tags block found.
    """
    in_fm = False
    fm_close = None
    for i, line in enumerate(lines):
        if line.rstrip() == "---":
            if not in_fm:
                in_fm = True
            else:
                fm_close = i
                break
    if not in_fm or fm_close is None:
        return None

    for i in range(fm_close):
        if re.match(r"^tags\s*:\s*$", lines[i]):
            j = i + 1
            while j < fm_close:
                ln = lines[j]
                if ln.strip() == "":
                    break
                if not TAG_ITEM_RE.match(ln):
                    break
                j += 1
            return (i, j)
    return None


def rewrite_tags(text: str, merges: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    """Apply merges to the tags block. Returns (new_text, changes).

    Merges are dict {old: new}. Tags not in the dict pass through unchanged.
    Resulting tag list is deduplicated (a paper that had both `IO` and
    `industrial_organization` ends up with one canonical entry).
    """
    lines = text.splitlines(keepends=True)
    block = find_tags_block(lines)
    if block is None:
        return text, []
    start, end = block

    seen: set[str] = set()
    new_block_lines: list[str] = []
    changes: list[tuple[str, str]] = []

    for ln in lines[start + 1 : end]:
        m = TAG_ITEM_RE.match(ln)
        if not m:
            new_block_lines.append(ln)
            continue
        prefix = m.group(1)
        quote = m.group(2)
        tag = m.group("tag")
        # Group 4 captures `\s*(?:#.*)?` — strip trailing whitespace
        # (including consumed newline) to avoid double-emitting it.
        suffix = (m.group(4) or "").rstrip()
        nl = "\n" if ln.endswith("\n") else ""

        new_tag = merges.get(tag, tag)
        if new_tag != tag:
            changes.append((tag, new_tag))
        if new_tag in seen:
            continue
        seen.add(new_tag)
        new_block_lines.append(f"{prefix}{quote}{new_tag}{quote}{suffix}{nl}")

    if not changes and len(new_block_lines) == (end - start - 1):
        return text, []

    new_lines = lines[: start + 1] + new_block_lines + lines[end:]
    return "".join(new_lines), changes
