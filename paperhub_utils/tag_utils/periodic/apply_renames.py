"""Apply tag renames across all metadata files (periodic bulk operation).

Reads a JSON merges file `{old_tag: new_tag}` and rewrites the `tags:` block
in every paper's main metadata file. Uses the surgical line-based editor in
`tag_utils.common.rewrite_tags`, so diffs are minimal.

Round 1 merges archived at `tags/round1_merges.json`.

Usage:
    uv run python -m tag_utils.periodic.apply_renames \\
        --merges-file PATH --dry-run
    uv run python -m tag_utils.periodic.apply_renames \\
        --merges-file PATH --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tag_utils.common import (
    DEFAULT_ORGANIZED_DIR,
    find_tags_block,
    iter_main_metadata_files,
    rewrite_tags,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--organized", type=Path, default=DEFAULT_ORGANIZED_DIR)
    p.add_argument("--merges-file", type=Path, required=True,
                   help="JSON file mapping {old_tag: new_tag}.")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true",
                     help="Show what would change; no files written.")
    grp.add_argument("--apply", action="store_true", help="Write changes.")
    args = p.parse_args()

    merges = json.loads(args.merges_file.read_text(encoding="utf-8"))
    if not isinstance(merges, dict):
        print(f"ERROR: merges file must be a JSON object {{old: new}}",
              file=sys.stderr)
        return 2

    n_files_changed = 0
    n_replacements = 0
    per_merge_count: dict[tuple[str, str], int] = {}
    files_with_no_tags_block: list[Path] = []

    for md_path in iter_main_metadata_files(args.organized):
        text = md_path.read_text(encoding="utf-8")
        new_text, changes = rewrite_tags(text, merges)
        if not changes and new_text == text:
            if find_tags_block(text.splitlines(keepends=True)) is None:
                files_with_no_tags_block.append(md_path)
            continue
        n_files_changed += 1
        n_replacements += len(changes)
        for c in changes:
            per_merge_count[c] = per_merge_count.get(c, 0) + 1
        if args.apply:
            md_path.write_text(new_text, encoding="utf-8")
        else:
            rel = md_path.parent.name + "/" + md_path.name
            for old, new in changes:
                print(f"  {rel}: {old} -> {new}")

    print()
    print(f"=== {'APPLIED' if args.apply else 'DRY-RUN'} SUMMARY ===")
    print(f"Files changed: {n_files_changed}")
    print(f"Total replacements: {n_replacements}")
    print(f"Files without tags block: {len(files_with_no_tags_block)}")
    if per_merge_count:
        print()
        print("Per-merge counts:")
        for (old, new), cnt in sorted(per_merge_count.items(), key=lambda x: -x[1]):
            print(f"  {cnt:4d}  {old} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
