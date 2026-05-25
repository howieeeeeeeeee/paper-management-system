"""Normalize `interest:` and `status:` frontmatter fields.

Conventions (matching dominant form + prompt/shared/metadata_template.txt):
- `interest:` is a **scalar**.    Examples: `interest: none`, `interest: high`
- `status:`   is a **list**.      Example:  `status:\n  - done`

Rewrites:
- `interest:` list-form -> scalar (takes the first non-empty list value)
- `status:`   scalar-form -> list  (single item)
- Missing `interest:` -> adds `interest: none`
- Missing `status:`   -> adds `status:\n  - initiated`

Surgical line edits — does not touch other fields. Idempotent.

Usage:
    uv run python -m tag_utils.normalize_fields --dry-run
    uv run python -m tag_utils.normalize_fields --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from tag_utils.common import DEFAULT_ORGANIZED_DIR, iter_main_metadata_files


SCALAR_FIELD_RE = re.compile(r"^(?P<key>interest|status)\s*:\s*(?P<val>.+?)\s*$")
LIST_FIELD_RE = re.compile(r"^(?P<key>interest|status)\s*:\s*$")
LIST_ITEM_RE = re.compile(r"^(\s+-\s+)(['\"]?)(?P<val>[^\s#'\"][^\s#]*?)\2(\s*(?:#.*)?)$")


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int] | None:
    in_fm = False
    for i, line in enumerate(lines):
        if line.rstrip() == "---":
            if not in_fm:
                in_fm = True
                start = i
            else:
                return (start, i)
    return None


def _find_field(lines: list[str], fm_start: int, fm_end: int, key: str) -> tuple[int, int, str | list[str]] | None:
    """Locate a field. Returns (start, end, value) or None.

    For scalar form: end == start + 1, value is the scalar string.
    For list form: end is one past last list item, value is list of strings.
    """
    for i in range(fm_start + 1, fm_end):
        ln = lines[i]
        m_scalar = SCALAR_FIELD_RE.match(ln)
        if m_scalar and m_scalar.group("key") == key:
            val = m_scalar.group("val").strip()
            # Strip surrounding quotes if present.
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            return (i, i + 1, val)
        m_list = LIST_FIELD_RE.match(ln)
        if m_list and m_list.group("key") == key:
            j = i + 1
            items: list[str] = []
            while j < fm_end:
                m_item = LIST_ITEM_RE.match(lines[j])
                if not m_item:
                    if lines[j].strip() == "":
                        break
                    break
                items.append(m_item.group("val"))
                j += 1
            return (i, j, items)
    return None


def normalize(text: str) -> tuple[str, list[str]]:
    """Apply normalization. Returns (new_text, changes_log)."""
    lines = text.splitlines(keepends=True)
    bounds = _frontmatter_bounds(lines)
    if bounds is None:
        return text, []
    fm_start, fm_end = bounds

    changes: list[str] = []

    # --- interest ---
    interest = _find_field(lines, fm_start, fm_end, "interest")
    if interest is None:
        # Insert before frontmatter close: append `interest: none` line.
        new_line = "interest: none\n"
        lines = lines[:fm_end] + [new_line] + lines[fm_end:]
        fm_end += 1
        changes.append("added missing interest: none")
    elif isinstance(interest[2], list):
        i_start, i_end, items = interest
        scalar_val = items[0] if items else "none"
        new_line = f"interest: {scalar_val}\n"
        lines = lines[:i_start] + [new_line] + lines[i_end:]
        delta = i_end - i_start - 1
        fm_end -= delta
        changes.append(f"interest list -> scalar ({scalar_val})")

    # Re-bound after potential edits.
    bounds = _frontmatter_bounds(lines)
    if bounds is None:
        return "".join(lines), changes
    fm_start, fm_end = bounds

    # --- status ---
    status = _find_field(lines, fm_start, fm_end, "status")
    if status is None:
        new_lines = ["status:\n", "  - initiated\n"]
        lines = lines[:fm_end] + new_lines + lines[fm_end:]
        fm_end += 2
        changes.append("added missing status: [- initiated]")
    elif isinstance(status[2], str):
        s_start, s_end, val = status
        # Convert scalar to list. Preserve indentation of `  - val` style.
        replacement = ["status:\n", f"  - {val}\n"]
        lines = lines[:s_start] + replacement + lines[s_end:]
        changes.append(f"status scalar -> list ({val})")

    return "".join(lines), changes


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--organized", type=Path, default=DEFAULT_ORGANIZED_DIR)
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--apply", action="store_true")
    args = p.parse_args()

    n_files_changed = 0
    counts: dict[str, int] = {}
    for md_path in iter_main_metadata_files(args.organized):
        text = md_path.read_text(encoding="utf-8")
        new_text, changes = normalize(text)
        if new_text == text:
            continue
        n_files_changed += 1
        for c in changes:
            counts[c] = counts.get(c, 0) + 1
        if args.apply:
            md_path.write_text(new_text, encoding="utf-8")
        else:
            rel = md_path.parent.name + "/" + md_path.name
            for c in changes:
                print(f"  {rel}: {c}")

    print()
    print(f"=== {'APPLIED' if args.apply else 'DRY-RUN'} SUMMARY ===")
    print(f"Files changed: {n_files_changed}")
    for c, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cnt:4d}  {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
