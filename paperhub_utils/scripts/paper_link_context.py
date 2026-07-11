#!/usr/bin/env python3
"""Build offline PaperHub context files from public paper links."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paperhub.link_context import extract_urls, prepare_link_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", action="append", help="Paper URL; repeat for a batch")
    source.add_argument("--link-file", help="Markdown or plain-text file containing URLs")
    parser.add_argument("--heading", help="Optional Markdown heading to scope --link-file")
    parser.add_argument(
        "--requested-mode",
        choices=("auto", "metadata-only", "full"),
        default="metadata-only",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.heading and not args.link_file:
        raise SystemExit("--heading requires --link-file")
    if args.link_file:
        path = Path(args.link_file).expanduser().resolve()
        urls = extract_urls(path.read_text(encoding="utf-8"), args.heading)
    else:
        urls = args.url or []
    if not urls:
        raise SystemExit("No HTTP(S) URLs found")
    result = prepare_link_batch(urls, args.requested_mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
