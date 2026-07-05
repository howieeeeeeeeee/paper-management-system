"""Scan the `organized/` tree, count tag usage, and emit JSON.

Usage:
    uv run python -m paperhub.tag_utils.scan_tags                   # JSON to stdout
    uv run python -m paperhub.tag_utils.scan_tags --pretty          # human-readable
    uv run python -m paperhub.tag_utils.scan_tags --out FILE.json   # write to file
    uv run python -m paperhub.tag_utils.scan_tags --organized DIR   # override scan root

Output schema:
    {
      "scanned": int,                  # number of metadata files parsed
      "errors": [{"path": str, "error": str}, ...],
      "tags": {                        # one entry per unique tag string
        "<tag>": {
          "count": int,
          "papers": ["<paper_label>", ...]
        }
      },
      "interest_forms": {"scalar": int, "list": int, "missing": int},
      "status_forms": {"scalar": int, "list": int, "missing": int}
    }

Read-only. Never edits any metadata file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from paperhub.tag_utils.common import (
    DEFAULT_ORGANIZED_DIR,
    iter_main_metadata_files,
    parse_frontmatter,
)


def _classify_form(value) -> str:
    if value is None:
        return "missing"
    if isinstance(value, list):
        return "list"
    return "scalar"


def scan(organized_dir: Path) -> dict:
    tag_counts: dict[str, list[str]] = defaultdict(list)
    errors: list[dict] = []
    scanned = 0
    interest_forms = {"scalar": 0, "list": 0, "missing": 0}
    status_forms = {"scalar": 0, "list": 0, "missing": 0}

    for md_path in iter_main_metadata_files(organized_dir):
        meta = parse_frontmatter(md_path)
        scanned += 1
        if meta.parse_error:
            errors.append({"path": str(md_path), "error": meta.parse_error})
            continue
        for tag in meta.tags:
            tag_counts[tag].append(meta.paper_label)
        interest_forms[_classify_form(meta.frontmatter.get("interest"))] += 1
        status_forms[_classify_form(meta.frontmatter.get("status"))] += 1

    tags_sorted = dict(
        sorted(
            (
                (tag, {"count": len(papers), "papers": papers})
                for tag, papers in tag_counts.items()
            ),
            key=lambda kv: (-kv[1]["count"], kv[0]),
        )
    )

    return {
        "scanned": scanned,
        "errors": errors,
        "tags": tags_sorted,
        "interest_forms": interest_forms,
        "status_forms": status_forms,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--organized",
        type=Path,
        default=DEFAULT_ORGANIZED_DIR,
        help="Path to organized/ directory",
    )
    p.add_argument("--out", type=Path, default=None, help="Write JSON to file")
    p.add_argument("--pretty", action="store_true", help="Indent JSON")
    args = p.parse_args()

    if not args.organized.is_dir():
        print(f"ERROR: not a directory: {args.organized}", file=sys.stderr)
        return 2

    result = scan(args.organized)

    indent = 2 if args.pretty else None
    payload = json.dumps(result, indent=indent, ensure_ascii=False)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(
            f"Scanned {result['scanned']} files, found {len(result['tags'])} unique tags, "
            f"{len(result['errors'])} parse errors. Wrote {args.out}",
            file=sys.stderr,
        )
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
