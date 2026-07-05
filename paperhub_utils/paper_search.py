"""Rank organized papers against fuzzy recall terms and print a compact digest.

Backend for the `paper-finder` skill: the agent expands a vague "I remember a
paper about..." description into several search terms, calls this script once,
and reasons over the token-bounded digest it prints.

Scans every `organized/<label>/<label>.md` (plus the sibling `ai_summary.md`
body at low weight) live on each run -- no index to maintain. ~6 MB scans in
well under a second.

Usage (from paperhub_utils/):
    uv run python paper_search.py --terms "moral wiggle room" "dictator game" \
        --top 15 --detail 5

Output: detailed cards for the first `--detail` matches (metadata, abstract
snippet, ai_summary snippet), one-line entries for the rest up to `--top`.
Papers with zero matching terms are omitted.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

# Field weights: where a term hits matters more than how often.
FIELD_WEIGHTS = {
    "title": 3.0,
    "tags": 2.5,
    "authors": 2.5,
    "abstract": 1.5,
    "meta_body": 1.0,
    "summary": 0.5,
}
# Cap per-field occurrence counts so one repeated word cannot dominate.
COUNT_CAP = 5
# Bonus per distinct matched term: coverage beats raw frequency.
COVERAGE_BONUS = 2.0
# Exclude-term hits are subtracted at 2x the positive field weights.
EXCLUDE_PENALTY = 2.0

ABSTRACT_WORDS = 80
SUMMARY_WORDS = 100
BRIEF_TITLE_WORDS = 12


def project_root() -> Path:
    env_root = os.environ.get("PAPERHUB_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Lenient: bad YAML yields an empty dict."""
    if text.startswith("---"):
        parts = text.split("\n---", 2)
        if len(parts) >= 2:
            raw = parts[0].lstrip("-\n")
            body = parts[1]
            if len(parts) == 3:
                body += parts[2]
            # Drop the first line remnant ("---") if split left one.
            try:
                meta = yaml.safe_load(raw) or {}
                if not isinstance(meta, dict):
                    meta = {}
            except yaml.YAMLError:
                meta = {}
            return meta, body
    return {}, text


def extract_abstract(body: str) -> tuple[str, str]:
    """Return (abstract text, body without the abstract section)."""
    match = re.search(r"^## Abstract\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not match:
        return "", body
    abstract = match.group(1).strip()
    rest = body[: match.start()] + body[match.end() :]
    return abstract, rest


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(as_text(v) for v in value if v is not None)
    return str(value).strip()


def first_words(text: str, n: int) -> str:
    words = text.split()
    clipped = " ".join(words[:n])
    return clipped + " ..." if len(words) > n else clipped


def load_papers(organized: Path) -> list[dict]:
    papers = []
    for folder in sorted(organized.iterdir()):
        if not folder.is_dir():
            continue
        meta_file = folder / f"{folder.name}.md"
        if not meta_file.is_file():
            candidates = [
                p for p in folder.glob("*.md") if p.name != "ai_summary.md"
            ]
            if not candidates:
                continue
            meta_file = candidates[0]
        try:
            meta, body = split_frontmatter(
                meta_file.read_text(encoding="utf-8", errors="ignore")
            )
        except OSError as exc:
            print(f"warning: skipping {meta_file}: {exc}", file=sys.stderr)
            continue
        abstract, meta_body = extract_abstract(body)

        summary = ""
        summary_file = folder / "ai_summary.md"
        if summary_file.is_file():
            try:
                _, summary = split_frontmatter(
                    summary_file.read_text(encoding="utf-8", errors="ignore")
                )
            except OSError:
                pass

        tags = as_text(meta.get("tags"))
        papers.append(
            {
                "label": folder.name,
                "meta": meta,
                "fields": {
                    "title": as_text(meta.get("title")),
                    "tags": tags + " " + tags.replace("_", " "),
                    "authors": as_text(meta.get("authors")),
                    "abstract": abstract,
                    "meta_body": meta_body + " " + as_text(meta.get("journal")),
                    "summary": summary,
                },
                "abstract": abstract,
                "summary": summary.strip(),
            }
        )
    return papers


def compile_terms(terms: list[str]) -> list[re.Pattern]:
    """Compile each term into a whole-token, case-insensitive regex."""
    return [
        re.compile(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)")
        for t in terms
    ]


def score_paper(
    paper: dict,
    patterns: list[re.Pattern],
    exclude_patterns: list[re.Pattern] = (),
) -> float:
    total = 0.0
    matched_terms = 0
    lowered = {
        name: text.lower() for name, text in paper["fields"].items() if text
    }
    for pattern in patterns:
        term_score = 0.0
        for name, text in lowered.items():
            count = len(pattern.findall(text))
            if count:
                term_score += min(count, COUNT_CAP) * FIELD_WEIGHTS[name]
        if term_score > 0:
            matched_terms += 1
            total += term_score
    if matched_terms:
        total += COVERAGE_BONUS * matched_terms
    # Exclude terms deduct score (soft penalty): mirror the field-weighted
    # count, scaled up so an unwanted keyword pushes a paper down or off.
    for pattern in exclude_patterns:
        for name, text in lowered.items():
            count = len(pattern.findall(text))
            if count:
                total -= EXCLUDE_PENALTY * min(count, COUNT_CAP) * FIELD_WEIGHTS[name]
    return total


def meta_line(meta: dict) -> str:
    status = as_text(meta.get("status")) or "-"
    interest = as_text(meta.get("interest")) or "-"
    importance = as_text(meta.get("importance")) or "-"
    return f"status: {status} | interest: {interest} | importance: {importance}"


def print_card(rank: int, score: float, paper: dict) -> None:
    meta = paper["meta"]
    year = as_text(meta.get("year"))
    journal = as_text(meta.get("journal"))
    byline = paper["fields"]["authors"] or "-"
    suffix = ", ".join(p for p in (year, journal) if p)
    if suffix:
        byline += f" ({suffix})"
    print(f"=== {rank}. {paper['label']} (score {score:.1f}) ===")
    print(f"title:    {paper['fields']['title'] or '-'}")
    print(f"authors:  {byline}")
    print(meta_line(meta))
    print(f"tags:     {as_text(meta.get('tags')) or '-'}")
    abstract = first_words(paper["abstract"], ABSTRACT_WORDS)
    summary = first_words(paper["summary"], SUMMARY_WORDS)
    print(f"abstract: {abstract or '(none)'}")
    print(f"summary:  {summary or '(no ai_summary.md)'}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--terms",
        nargs="+",
        required=True,
        help="case-insensitive search terms/phrases (quote multi-word phrases)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="case-insensitive keywords to penalize / deduct score (quote phrases)",
    )
    parser.add_argument("--top", type=int, default=15, help="max results")
    parser.add_argument(
        "--detail", type=int, default=5, help="how many results get full cards"
    )
    args = parser.parse_args()

    organized = project_root() / "organized"
    if not organized.is_dir():
        print(f"error: organized/ not found at {organized}", file=sys.stderr)
        return 1

    patterns = compile_terms(args.terms)
    exclude_patterns = compile_terms(args.exclude)
    papers = load_papers(organized)
    scored = [(score_paper(p, patterns, exclude_patterns), p) for p in papers]
    hits = sorted(
        ((s, p) for s, p in scored if s > 0),
        key=lambda sp: (-sp[0], sp[1]["label"]),
    )

    header = (
        f"scanned {len(papers)} papers | {len(hits)} matched | "
        f"terms: {', '.join(args.terms)}"
    )
    if args.exclude:
        header += f" | excluding: {', '.join(args.exclude)}"
    print(header)
    print()
    if not hits:
        print("no matches -- try broader or alternative terms")
        return 0

    for rank, (score, paper) in enumerate(hits[: args.top], start=1):
        if rank <= args.detail:
            print_card(rank, score, paper)
        else:
            if rank == args.detail + 1:
                print("--- more candidates ---")
            title = first_words(
                paper["fields"]["title"] or "-", BRIEF_TITLE_WORDS
            )
            year = as_text(paper["meta"].get("year"))
            year_str = f", {year}" if year else ""
            print(
                f"{rank}. {paper['label']} (score {score:.1f}) -- "
                f"{title}{year_str}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
