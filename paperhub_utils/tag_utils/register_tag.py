"""Per-batch tag registration. Called by the paper-summarizer skill after a
batch finishes, once per new tag, after the user has decided what to do.

Three operations:

  --suggest-merge TAG --type T [--top-k N] [--threshold F]
      Load the canonical registry safely and print top-K similar existing tags
      as JSON. The skill calls this to surface merge candidates without pulling
      the full names list into LLM context — only the tiny JSON output (a
      handful of candidates) gets read. If no candidate exceeds the threshold,
      output is `{"similar": []}`.

  --add TAG --type T [--from-paper LABEL]
      Append a brand-new tag to tags_summary.md, _internal/<type>_names.txt,
      and _internal/registry.json with count=1. Used when no similar tag
      exists, OR after the user declined a suggested merge.

  --rename OLD NEW --paper LABEL
      Rewrite the `tags:` block of a single paper's metadata file, replacing
      OLD with NEW. Used when the user accepted a suggested merge. Does NOT
      touch the registry counts (those re-sync at the next periodic check).

Token-light by design: never returns the full registry to stdout, only the
score-filtered top-K candidates. The skill never has to read the names file
itself.

Examples:
    # 1. Skill: I think 'info_asym' is type 'topic'. Are there similar tags?
    uv run python -m tag_utils.register_tag \\
        --suggest-merge info_asym --type topic
    # -> {"new_tag": "info_asym", "type": "topic", "similar": [
    #      {"tag": "information_asymmetry", "score": 0.9}]}

    # 2a. User said "yes merge" -> rewrite the paper's YAML
    uv run python -m tag_utils.register_tag \\
        --rename info_asym information_asymmetry --paper alsobay2025

    # 2b. User said "no, keep new" -> register as fresh tag
    uv run python -m tag_utils.register_tag \\
        --add info_asym --type topic --from-paper alsobay2025
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from tag_utils.common import (
    DEFAULT_ORGANIZED_DIR,
    DEFAULT_TAGS_DIR,
    rewrite_tags,
)
from tag_utils.registry import INTERNAL_SUBDIR, VALID_TYPES, load_registry


def _similarity(a: str, b: str) -> float:
    """Score 0-1 between two tag names. Combines:
    - exact match -> 1.0
    - one is a substring of the other -> 0.9
    - token-prefix overlap (split on _ and -, e.g. info_asym vs
      information_asymmetry: info<>information, asym<>asymmetry) -> 0.6-0.9
    - difflib SequenceMatcher ratio as fallback
    """
    a_low, b_low = a.lower(), b.lower()
    if a_low == b_low:
        return 1.0
    # Punctuation-equivalent
    if a_low.replace("-", "_") == b_low.replace("-", "_"):
        return 0.95
    # Substring match — require the shorter side >= 3 chars to avoid spurious
    # hits like "io" matching "behavioral" via "viOral".
    shorter, longer = (a_low, b_low) if len(a_low) <= len(b_low) else (b_low, a_low)
    if len(shorter) >= 3 and shorter in longer:
        return 0.9
    a_tokens = [t for t in re.split(r"[_\-]+", a_low) if t]
    b_tokens = [t for t in re.split(r"[_\-]+", b_low) if t]
    matched = 0
    for at in a_tokens:
        for bt in b_tokens:
            if at == bt:
                matched += 1
                break
            if len(at) >= 3 and bt.startswith(at):
                matched += 1
                break
            if len(bt) >= 3 and at.startswith(bt):
                matched += 1
                break
    if a_tokens:
        token_score = 0.6 + 0.3 * (matched / max(len(a_tokens), len(b_tokens)))
        if matched / len(a_tokens) < 0.5:
            token_score = 0.0
    else:
        token_score = 0.0
    seq_score = SequenceMatcher(None, a_low, b_low).ratio()
    return max(token_score, seq_score)


def cmd_suggest_merge(
    tags_dir: Path, tag: str, ttype: str, top_k: int, threshold: float
) -> int:
    """Search ALL four type files, return top-K matches as JSON.

    Searching across all types is cheap (the script reads at most ~10KB total)
    and guards against the caller having mistyped the new tag. Each result
    carries its `existing_type` so the caller knows what type the candidate is.
    """
    if ttype not in VALID_TYPES:
        print(f"ERROR: type must be one of {VALID_TYPES}", file=sys.stderr)
        return 2

    registry = load_registry(
        tags_dir,
        allow_summary_fallback=True,
        require_populated=True,
    ).data

    candidates = []
    for t in VALID_TYPES:
        rows = registry.get("by_type", {}).get(t, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            n = str(row.get("tag", "")).strip()
            if not n or n == tag:
                continue
            score = _similarity(tag, n)
            if score >= threshold:
                candidates.append(
                    {"tag": n, "existing_type": t, "score": round(score, 3)}
                )
    candidates.sort(key=lambda c: -c["score"])
    candidates = candidates[:top_k]

    print(json.dumps(
        {"new_tag": tag, "guessed_type": ttype, "similar": candidates},
        ensure_ascii=False,
    ))
    return 0


def cmd_add(tags_dir: Path, tag: str, ttype: str, from_paper: str | None) -> int:
    if ttype not in VALID_TYPES:
        print(f"ERROR: type must be one of {VALID_TYPES}", file=sys.stderr)
        return 2

    internal_dir = tags_dir / INTERNAL_SUBDIR
    internal_dir.mkdir(parents=True, exist_ok=True)
    registry_path = internal_dir / "registry.json"
    registry = load_registry(
        tags_dir,
        allow_summary_fallback=True,
        require_populated=True,
    ).data

    # Idempotent: refuse silently if tag already in registry.
    for t in VALID_TYPES:
        for row in registry["by_type"].get(t, []):
            if row["tag"] == tag:
                print(
                    f"NOTE: tag '{tag}' already in registry under type '{t}'. "
                    "No changes.",
                    file=sys.stderr,
                )
                return 0

    note = f"introduced by {from_paper}" if from_paper else ""
    registry["by_type"].setdefault(ttype, []).append(
        {"tag": tag, "count": 1, "notes": note}
    )
    registry["total_tags"] = sum(len(registry["by_type"][t]) for t in VALID_TYPES)
    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Append to _internal/<type>_names.txt (cheap append).
    names_path = internal_dir / f"{ttype}_names.txt"
    with names_path.open("a", encoding="utf-8") as f:
        f.write(f"{tag}\n")

    # Append to tags_summary.md (one new row at the bottom of the data table).
    # Order/grouping resyncs at next bootstrap run; here we just append cheaply.
    md_path = tags_dir / "tags_summary.md"
    md_text = md_path.read_text(encoding="utf-8")
    if not md_text.endswith("\n"):
        md_text += "\n"
    md_text += f"| `{tag}` | {ttype} | 1 | {note} |\n"
    md_path.write_text(md_text, encoding="utf-8")

    print(f"Added '{tag}' as {ttype}.")
    return 0


def cmd_rename(organized: Path, old: str, new: str, paper_label: str) -> int:
    md_path = organized / paper_label / f"{paper_label}.md"
    if not md_path.is_file():
        print(f"ERROR: not found: {md_path}", file=sys.stderr)
        return 2

    text = md_path.read_text(encoding="utf-8")
    new_text, changes = rewrite_tags(text, {old: new})
    if not changes:
        print(
            f"NOTE: tag '{old}' not present in {paper_label}. No changes.",
            file=sys.stderr,
        )
        return 0
    md_path.write_text(new_text, encoding="utf-8")
    print(f"{paper_label}: {old} -> {new}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tags-dir", type=Path, default=DEFAULT_TAGS_DIR)
    p.add_argument("--organized", type=Path, default=DEFAULT_ORGANIZED_DIR)

    sub = p.add_mutually_exclusive_group(required=True)
    sub.add_argument("--suggest-merge", metavar="TAG",
                     help="Print top-K similar existing tags as JSON.")
    sub.add_argument("--add", metavar="TAG",
                     help="Add a new tag to the registry.")
    sub.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"),
                     help="Rewrite OLD -> NEW in one paper's metadata.")

    p.add_argument("--type", choices=VALID_TYPES,
                   help="Type for --add or --suggest-merge.")
    p.add_argument("--from-paper", metavar="LABEL",
                   help="Paper label that introduced this tag (note in registry).")
    p.add_argument("--paper", metavar="LABEL",
                   help="Paper label whose metadata to rewrite (for --rename).")
    p.add_argument("--top-k", type=int, default=3,
                   help="Max suggestions for --suggest-merge (default 3).")
    p.add_argument("--threshold", type=float, default=0.7,
                   help="Min similarity score for --suggest-merge (default 0.7).")

    args = p.parse_args()

    if args.suggest_merge:
        if not args.type:
            print("ERROR: --suggest-merge requires --type", file=sys.stderr)
            return 2
        return cmd_suggest_merge(
            args.tags_dir, args.suggest_merge, args.type, args.top_k, args.threshold
        )

    if args.add:
        if not args.type:
            print("ERROR: --add requires --type", file=sys.stderr)
            return 2
        return cmd_add(args.tags_dir, args.add, args.type, args.from_paper)

    if args.rename:
        if not args.paper:
            print("ERROR: --rename requires --paper LABEL", file=sys.stderr)
            return 2
        return cmd_rename(args.organized, args.rename[0], args.rename[1], args.paper)

    return 2  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
