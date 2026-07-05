"""Classify a just-summarized batch's tags as reused or new candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paperhub.tag_utils.common import (
    DEFAULT_ORGANIZED_DIR,
    DEFAULT_TAGS_DIR,
    parse_frontmatter,
)
from paperhub.tag_utils.registry import (
    RegistryError,
    load_registry,
    registry_tag_count,
    registry_tag_names,
)


def classify_batch_tags(
    labels: list[str],
    *,
    organized_dir: Path,
    tags_dir: Path,
) -> dict:
    loaded = load_registry(
        tags_dir,
        allow_summary_fallback=True,
        require_populated=True,
    )
    existing_tags = registry_tag_names(loaded.data)

    papers: dict[str, list[str]] = {}
    unique_tags: list[str] = []
    seen: set[str] = set()
    errors: list[dict[str, str]] = []

    for label in labels:
        md_path = organized_dir / label / f"{label}.md"
        meta = parse_frontmatter(md_path)
        if meta.parse_error:
            errors.append({"paper_label": label, "error": meta.parse_error})
            papers[label] = []
            continue
        papers[label] = meta.tags
        for tag in meta.tags:
            if tag in seen:
                continue
            seen.add(tag)
            unique_tags.append(tag)

    reused = [tag for tag in unique_tags if tag in existing_tags]
    candidates = [tag for tag in unique_tags if tag not in existing_tags]

    return {
        "registry_source": loaded.source,
        "registry_warnings": list(loaded.warnings),
        "registry_total_tags": registry_tag_count(loaded.data),
        "papers": papers,
        "unique_tags": unique_tags,
        "reused": reused,
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", nargs="+", help="Paper labels just summarized")
    parser.add_argument("--organized", type=Path, default=DEFAULT_ORGANIZED_DIR)
    parser.add_argument("--tags-dir", type=Path, default=DEFAULT_TAGS_DIR)
    parser.add_argument("--pretty", action="store_true", help="Indent JSON output")
    args = parser.parse_args()

    try:
        result = classify_batch_tags(
            args.labels,
            organized_dir=args.organized,
            tags_dir=args.tags_dir,
        )
    except RegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    indent = 2 if args.pretty else None
    print(json.dumps(result, indent=indent, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
