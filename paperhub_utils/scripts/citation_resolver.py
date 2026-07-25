#!/usr/bin/env python3
"""Audit or resolve PaperHub ``citation.csl.json`` files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from paperhub.citation_resolution import audit_citations, resolve_citations
from paperhub.config import DEFAULT_ORGANIZED_DIR
from paperhub.metadata_notes import atomic_write_json


def _load_json(path: str) -> Any:
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def _load_labels(args: argparse.Namespace) -> list[str]:
    labels = list(args.label or [])
    if args.labels_file:
        value = _load_json(args.labels_file)
        if isinstance(value, dict):
            value = value.get("labels")
        if not isinstance(value, list):
            raise ValueError("Labels file must contain a list or an object with a labels list")
        labels.extend(str(label).strip() for label in value if str(label).strip())
    labels = list(dict.fromkeys(label for label in labels if label))
    if not labels:
        raise ValueError("At least one --label or --labels-file is required")
    return labels


def _load_candidate_links(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    value = _load_json(path)
    if isinstance(value, dict) and isinstance(value.get("candidate_links"), dict):
        value = value["candidate_links"]
    if not isinstance(value, dict):
        raise ValueError("Candidate-links file must contain a label-to-URL object")
    return {
        str(label).strip(): str(url).strip()
        for label, url in value.items()
        if str(label).strip() and str(url).strip()
    }


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--label", action="append", default=[], help="Paper label; repeat")
    parser.add_argument("--labels-file", help="JSON list or selection manifest")
    parser.add_argument("--organized-dir", default=str(DEFAULT_ORGANIZED_DIR))
    parser.add_argument("--report-file", help="Optional JSON report path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="Read-only citation coverage audit")
    _add_common(audit)
    resolve = subparsers.add_parser("resolve", help="Resolve missing or invalid citations")
    _add_common(resolve)
    resolve.add_argument("--candidate-links-file")
    resolve.add_argument("--best-effort", action="store_true")
    resolve.add_argument("--refresh", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        labels = _load_labels(args)
        if args.command == "audit":
            result = audit_citations(labels, organized_dir=Path(args.organized_dir))
            result["success"] = True
            result["mode"] = "audit"
        else:
            result = resolve_citations(
                labels,
                candidate_links=_load_candidate_links(args.candidate_links_file),
                organized_dir=Path(args.organized_dir),
                refresh=args.refresh,
            )
            result["mode"] = "resolve"
        if args.report_file:
            atomic_write_json(Path(args.report_file).expanduser().resolve(), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "resolve" and result.get("fatal_write_errors"):
            return 2
        if args.command == "resolve" and not result["success"] and not args.best_effort:
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
