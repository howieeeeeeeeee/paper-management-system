#!/usr/bin/env python3
"""Search organized PaperHub papers from a vague description.

This is a local recall helper: it reads metadata notes and summaries under
`organized/`, ranks candidates, and prints the best matches. It does not call
an API.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

UTILS_ROOT = Path(__file__).resolve().parents[1]
if str(UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(UTILS_ROOT))

from paperhub.config import DEFAULT_ORGANIZED_DIR

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]{2,}")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "because",
    "been",
    "being",
    "but",
    "can",
    "could",
    "did",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "into",
    "its",
    "like",
    "more",
    "not",
    "paper",
    "papers",
    "that",
    "the",
    "their",
    "there",
    "this",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
}


@dataclass(frozen=True)
class SearchResult:
    label: str
    score: float
    path: str
    title: str
    authors: list[str]
    year: str
    status: str
    interest: str
    tags: list[str]
    matched_terms: list[str]
    excluded_terms: list[str]
    snippets: list[str]
    score_detail: dict[str, float]


def normalize_token(token: str) -> str:
    token = token.lower().strip("_'-")
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 3 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def extract_terms(text: str) -> list[str]:
    terms = []
    seen = set()
    for raw in WORD_RE.findall(text):
        term = normalize_token(raw)
        if term in STOPWORDS or len(term) < 3:
            continue
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def parse_metadata(text: str) -> dict[str, Any]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def iter_papers(organized_dir: Path) -> list[dict[str, Any]]:
    papers = []
    if not organized_dir.exists():
        return papers
    for folder in sorted(path for path in organized_dir.iterdir() if path.is_dir()):
        metadata_path = folder / f"{folder.name}.md"
        if not metadata_path.exists():
            continue
        metadata_text = read_text(metadata_path)
        summary_path = folder / "ai_summary.md"
        summary_text = read_text(summary_path)
        meta = parse_metadata(metadata_text)
        papers.append(
            {
                "label": folder.name,
                "folder": folder,
                "metadata_path": metadata_path,
                "metadata_text": metadata_text,
                "summary_text": summary_text,
                "title": str(meta.get("title") or ""),
                "authors": coerce_list(meta.get("authors")),
                "year": str(meta.get("year") or ""),
                "status": str(meta.get("status") or ""),
                "interest": str(meta.get("interest") or ""),
                "tags": coerce_list(meta.get("tags")),
            }
        )
    return papers


def count_term(text: str, term: str) -> int:
    normalized = " ".join(extract_terms(text))
    if not normalized:
        return 0
    return normalized.split().count(term)


def snippets_for(text: str, terms: list[str], limit: int = 2) -> list[str]:
    snippets = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) < 20:
            continue
        normalized_line_terms = set(extract_terms(line))
        if normalized_line_terms.intersection(terms):
            snippets.append(line[:280])
        if len(snippets) >= limit:
            break
    return snippets


def score_paper(
    paper: dict[str, Any],
    terms: list[str],
    query: str,
    exclude_terms: list[str],
) -> SearchResult:
    fields = {
        "title": paper["title"],
        "authors": " ".join(paper["authors"]),
        "tags": " ".join(paper["tags"]),
        "abstract": extract_abstract(paper["metadata_text"]),
        "metadata": paper["metadata_text"],
        "summary": paper["summary_text"],
    }
    weights = {
        "title": 3.0,
        "authors": 2.5,
        "tags": 2.5,
        "abstract": 1.5,
        "metadata": 1.0,
        "summary": 0.5,
    }
    detail: dict[str, float] = {}
    matched_terms = set()
    excluded_matches = set()
    score = 0.0
    for field, text in fields.items():
        field_score = 0.0
        for term in terms:
            hits = count_term(text, term)
            if hits:
                matched_terms.add(term)
                field_score += weights[field] * min(3.0, 1.0 + math.log(hits))
        for term in exclude_terms:
            hits = count_term(text, term)
            if hits:
                excluded_matches.add(term)
                field_score -= 2.0 * weights[field] * min(3.0, 1.0 + math.log(hits))
        detail[field] = round(field_score, 3)
        score += field_score

    if terms:
        coverage = len(matched_terms) / len(terms)
        coverage_bonus = round(4.0 * coverage, 3)
        detail["coverage_bonus"] = coverage_bonus
        score += coverage_bonus

    normalized_query = " ".join(extract_terms(query))
    combined = " ".join([paper["metadata_text"], paper["summary_text"]]).lower()
    if normalized_query and normalized_query in combined:
        detail["phrase"] = 4.0
        score += 4.0

    snippets = snippets_for(paper["summary_text"], terms)
    if len(snippets) < 2:
        snippets.extend(snippets_for(paper["metadata_text"], terms, limit=2 - len(snippets)))

    return SearchResult(
        label=paper["label"],
        score=round(score, 3),
        path=str(paper["metadata_path"]),
        title=paper["title"],
        authors=paper["authors"],
        year=paper["year"],
        status=paper["status"],
        interest=paper["interest"],
        tags=paper["tags"],
        matched_terms=sorted(matched_terms),
        excluded_terms=sorted(excluded_matches),
        snippets=snippets,
        score_detail=detail,
    )


def search(
    query: str,
    *,
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
    keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    limit: int = 8,
) -> list[SearchResult]:
    query_terms = extract_terms(query)
    keyword_terms = extract_terms(" ".join(keywords or []))
    exclude_terms = extract_terms(" ".join(exclude_keywords or []))
    terms = list(dict.fromkeys(keyword_terms + query_terms))
    if not terms:
        return []
    results = [
        score_paper(paper, terms, query, exclude_terms)
        for paper in iter_papers(organized_dir)
    ]
    results = [result for result in results if result.score > 0]
    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


def extract_abstract(metadata_text: str) -> str:
    match = re.search(
        r"^## Abstract\s*\n(?P<body>.*?)(?=^## |\Z)",
        metadata_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group("body") if match else ""


def read_summary_for_metadata_path(metadata_path: str) -> str:
    path = Path(metadata_path)
    return read_text(path.with_name("ai_summary.md"))


def print_full_context(result: SearchResult) -> None:
    metadata_text = read_text(Path(result.path))
    summary_text = read_summary_for_metadata_path(result.path)
    print("   metadata_note:")
    for line in metadata_text.rstrip().splitlines():
        print(f"     {line}")
    if summary_text.strip():
        print("   ai_summary:")
        for line in summary_text.rstrip().splitlines():
            print(f"     {line}")


def print_human(
    results: list[SearchResult],
    *,
    detail_count: int,
    show_score_detail: bool,
    full: bool,
) -> None:
    if not results:
        print("No matching papers found.")
        return
    for index, result in enumerate(results, start=1):
        if index > detail_count:
            print(f"{index}. {result.label} - {result.title} ({result.year}) score={result.score}")
            continue
        authors = ", ".join(result.authors[:3])
        if len(result.authors) > 3:
            authors += ", et al."
        print(f"{index}. {result.label}  score={result.score}")
        print(f"   {result.title}")
        if authors or result.year:
            print(f"   {authors} ({result.year})".strip())
        bits = []
        if result.status:
            bits.append(f"status={result.status}")
        if result.interest:
            bits.append(f"interest={result.interest}")
        if result.tags:
            bits.append("tags=" + ", ".join(result.tags[:8]))
        if bits:
            print("   " + " | ".join(bits))
        print(f"   path={result.path}")
        print("   matched=" + ", ".join(result.matched_terms))
        if result.excluded_terms:
            print("   exclude_penalty=" + ", ".join(result.excluded_terms))
        for snippet in result.snippets:
            print(f"   - {snippet}")
        if show_score_detail:
            print("   detail=" + json.dumps(result.score_detail, sort_keys=True))
        if full:
            print_full_context(result)
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*", help="description of the remembered paper")
    parser.add_argument(
        "--terms",
        nargs="+",
        action="append",
        default=[],
        help="explicit search terms or phrases; can be used without positional query",
    )
    parser.add_argument("--keyword", action="append", default=[], help="explicit keyword boost")
    parser.add_argument(
        "--exclude",
        nargs="+",
        action="append",
        default=[],
        help="terms or phrases to penalize, not hard-filter",
    )
    parser.add_argument("--organized-dir", type=Path, default=DEFAULT_ORGANIZED_DIR)
    parser.add_argument("--limit", type=int, default=None, help="maximum number of results")
    parser.add_argument("--top", type=int, default=None, help="alias for --limit")
    parser.add_argument("--detail", type=int, default=5, help="number of full cards to print")
    parser.add_argument("--detailed", action="store_true", help="print score details")
    parser.add_argument("--full", action="store_true", help="include full metadata and ai_summary for detailed cards")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    term_args = [term for group in args.terms for term in group]
    query = " ".join(args.query).strip()
    if not query and term_args:
        query = " ".join(term_args)
    limit = args.top if args.top is not None else args.limit
    limit = max(1, limit or 8)
    detail_count = max(0, min(args.detail, limit))
    results = search(
        query,
        organized_dir=args.organized_dir,
        keywords=args.keyword + term_args,
        exclude_keywords=[term for group in args.exclude for term in group],
        limit=limit,
    )
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        print_human(
            results,
            detail_count=detail_count,
            show_score_detail=args.detailed,
            full=args.full,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
