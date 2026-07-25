#!/usr/bin/env python3
"""Build a PaperHub BibTeX database or formatted Markdown bibliography."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from paperhub.bibliography import (
    BibliographyError,
    MissingCitationsError,
    build_bibliography,
)
from paperhub.config import CITATION_PREFERRED_STYLE, DEFAULT_ORGANIZED_DIR


def _load_labels(path: str) -> list[str]:
    value: Any = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("labels")
    if not isinstance(value, list):
        raise BibliographyError("Labels file must contain a list or an object with a labels list")
    return [str(label).strip() for label in value if str(label).strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-file", required=True)
    parser.add_argument("--organized-dir", default=str(DEFAULT_ORGANIZED_DIR))
    parser.add_argument(
        "--format",
        choices=("bibtex", "markdown", "reference-data"),
        default="bibtex",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--style", default=CITATION_PREFERRED_STYLE)
    parser.add_argument("--footnote-definitions", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_bibliography(
            _load_labels(args.labels_file),
            output=Path(args.output),
            output_format=args.format,
            organized_dir=Path(args.organized_dir),
            allow_partial=args.allow_partial,
            overwrite=args.overwrite,
            style=args.style,
            footnote_definitions=args.footnote_definitions,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except MissingCitationsError as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "requires_checkpoint": True,
                    "audit": exc.audit,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3
    except (OSError, ValueError, json.JSONDecodeError, BibliographyError) as exc:
        print(json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
