#!/usr/bin/env python3
"""Select PaperHub paper labels by exact tags and citation status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from paperhub.config import DEFAULT_ORGANIZED_DIR
from paperhub.metadata_notes import atomic_write_json
from paperhub.paper_selection import CITATION_STATUS_FILTERS, SelectionError, select_papers


def _read_labels(path: str | None) -> list[str]:
    if not path:
        return []
    value: Any = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("labels")
    if not isinstance(value, list):
        raise SelectionError("Labels file must contain a list or an object with a labels list")
    return [str(label).strip() for label in value if str(label).strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", action="append", default=[], help="Explicit paper label; repeat")
    parser.add_argument("--labels-file", help="JSON list or selection manifest")
    parser.add_argument("--all-tag", action="append", default=[], help="Required exact tag; repeat")
    parser.add_argument("--any-tag", action="append", default=[], help="Alternative exact tag; repeat")
    parser.add_argument(
        "--citation-status",
        choices=sorted(CITATION_STATUS_FILTERS),
        default="any",
    )
    parser.add_argument("--organized-dir", default=str(DEFAULT_ORGANIZED_DIR))
    parser.add_argument("--output-manifest", help="Optional JSON output path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        explicit = [*args.label, *_read_labels(args.labels_file)]
        selection = select_papers(
            explicit_labels=explicit,
            all_tags=args.all_tag,
            any_tags=args.any_tag,
            citation_status=args.citation_status,
            organized_dir=Path(args.organized_dir),
        )
        result = selection.to_manifest()
        result["selected_papers"] = len(selection.labels)
        if args.output_manifest:
            atomic_write_json(Path(args.output_manifest).expanduser().resolve(), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
