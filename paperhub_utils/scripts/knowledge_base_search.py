#!/usr/bin/env python3
"""Search visible Markdown notes in the configured Obsidian vault.

This is a local knowledge-base helper for agent answers. It scans Markdown
files under the configured Obsidian vault, skips hidden dot-prefixed folders,
ranks matching notes, and prints bounded context. It does not call an API.
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

from paperhub.config import PAPERHUB_ROOT, USER_CONFIG

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]{2,}")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
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
    "note",
    "notes",
    "paper",
    "papers",
    "that",
    "the",
    "their",
    "there",
    "this",
    "vault",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
PAPER_SUMMARY_STEMS = {"aisummary", "summary"}


@dataclass(frozen=True)
class NoteResult:
    score: float
    path: str
    relative_path: str
    wikilink: str
    title: str
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


def normalize_phrase(text: str) -> str:
    return " ".join(extract_terms(text))


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def parse_frontmatter(text: str) -> dict[str, Any]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def headings_for(text: str) -> list[str]:
    return [match.group(2).strip() for match in HEADING_RE.finditer(strip_frontmatter(text))]


def title_for(path: Path, text: str) -> str:
    meta = parse_frontmatter(text)
    title = meta.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    headings = headings_for(text)
    if headings:
        return headings[0]
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.stem


def configured_vault_root() -> Path:
    obsidian_config = USER_CONFIG.get("obsidian")
    if isinstance(obsidian_config, dict):
        value = obsidian_config.get("vault_abs_path")
        if isinstance(value, str) and value.strip():
            path = Path(value).expanduser()
            if path.exists() and path.is_dir():
                return path.resolve()
    return PAPERHUB_ROOT


def has_hidden_segment(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def is_standard_paper_folder(path: Path, vault_root: Path) -> bool:
    try:
        rel_path = path.relative_to(vault_root)
    except ValueError:
        return False
    return len(rel_path.parts) == 2 and rel_path.parts[0] == "organized"


def is_paper_metadata_note(path: Path, vault_root: Path) -> bool:
    return is_standard_paper_folder(path.parent, vault_root) and path.stem == path.parent.name


def is_paper_summary_note(path: Path, vault_root: Path) -> bool:
    normalized_stem = re.sub(r"[\s_-]+", "", path.stem).lower()
    return is_standard_paper_folder(path.parent, vault_root) and normalized_stem in PAPER_SUMMARY_STEMS


def is_paper_markdown(path: Path, vault_root: Path) -> bool:
    return is_paper_metadata_note(path, vault_root) or is_paper_summary_note(path, vault_root)


def iter_markdown_notes(vault_root: Path, *, ignore_paper_markdown: bool = False) -> list[Path]:
    if not vault_root.exists():
        return []
    paths = set()
    for suffix in MARKDOWN_SUFFIXES:
        paths.update(vault_root.rglob(f"*{suffix}"))
    notes = []
    for path in sorted(paths):
        try:
            rel_path = path.relative_to(vault_root)
        except ValueError:
            continue
        if not path.is_file():
            continue
        if has_hidden_segment(rel_path):
            continue
        if ignore_paper_markdown and is_paper_markdown(path, vault_root):
            continue
        notes.append(path)
    return notes


def count_token(text: str, term: str) -> int:
    normalized = " ".join(extract_terms(text))
    if not normalized:
        return 0
    return normalized.split().count(term)


def count_phrase(text: str, phrase: str) -> int:
    normalized = normalize_phrase(text)
    normalized_phrase = normalize_phrase(phrase)
    if not normalized or not normalized_phrase or " " not in normalized_phrase:
        return 0
    return normalized.count(normalized_phrase)


def snippets_for(text: str, terms: list[str], phrases: list[str], limit: int = 3) -> list[str]:
    snippets = []
    normalized_phrases = [normalize_phrase(phrase) for phrase in phrases if " " in normalize_phrase(phrase)]
    for raw_line in strip_frontmatter(text).splitlines():
        line = raw_line.strip()
        if not line or len(line) < 20:
            continue
        normalized_line = normalize_phrase(line)
        line_terms = set(normalized_line.split())
        if line_terms.intersection(terms) or any(phrase in normalized_line for phrase in normalized_phrases):
            snippets.append(line[:300])
        if len(snippets) >= limit:
            break
    return snippets


def obsidian_wikilink(path: Path, vault_root: Path, title: str) -> str:
    rel_path = path.relative_to(vault_root).with_suffix("").as_posix()
    parts = path.relative_to(vault_root).parts
    if len(parts) == 3 and parts[0] == "organized" and parts[1] == path.stem:
        return f"[[{path.stem}]]"
    if title and title != path.stem:
        return f"[[{rel_path}|{title}]]"
    return f"[[{rel_path}]]"


def score_note(
    path: Path,
    vault_root: Path,
    terms: list[str],
    phrases: list[str],
    exclude_terms: list[str],
    exclude_phrases: list[str],
) -> NoteResult:
    text = read_text(path)
    rel_path = path.relative_to(vault_root).as_posix()
    title = title_for(path, text)
    headings = " ".join(headings_for(text))
    fields = {
        "filename": path.stem,
        "path": rel_path,
        "title": title,
        "headings": headings,
        "body": strip_frontmatter(text),
    }
    weights = {
        "filename": 3.0,
        "path": 2.0,
        "title": 3.0,
        "headings": 2.0,
        "body": 1.0,
    }

    detail: dict[str, float] = {}
    matched_terms = set()
    excluded_matches = set()
    score = 0.0
    for field, field_text in fields.items():
        field_score = 0.0
        for term in terms:
            hits = count_token(field_text, term)
            if hits:
                matched_terms.add(term)
                field_score += weights[field] * min(3.0, 1.0 + math.log(hits))
        for phrase in phrases:
            hits = count_phrase(field_text, phrase)
            if hits:
                matched_terms.add(normalize_phrase(phrase))
                field_score += 1.5 * weights[field] * min(3.0, 1.0 + math.log(hits))
        for term in exclude_terms:
            hits = count_token(field_text, term)
            if hits:
                excluded_matches.add(term)
                field_score -= 2.0 * weights[field] * min(3.0, 1.0 + math.log(hits))
        for phrase in exclude_phrases:
            hits = count_phrase(field_text, phrase)
            if hits:
                excluded_matches.add(normalize_phrase(phrase))
                field_score -= 3.0 * weights[field] * min(3.0, 1.0 + math.log(hits))
        detail[field] = round(field_score, 3)
        score += field_score

    if terms or phrases:
        wanted = set(terms) | {normalize_phrase(phrase) for phrase in phrases if normalize_phrase(phrase)}
        coverage = len(matched_terms.intersection(wanted)) / max(1, len(wanted))
        coverage_bonus = round(4.0 * coverage, 3)
        detail["coverage_bonus"] = coverage_bonus
        score += coverage_bonus

    snippets = snippets_for(text, terms, phrases)
    return NoteResult(
        score=round(score, 3),
        path=str(path),
        relative_path=rel_path,
        wikilink=obsidian_wikilink(path, vault_root, title),
        title=title,
        matched_terms=sorted(matched_terms),
        excluded_terms=sorted(excluded_matches),
        snippets=snippets,
        score_detail=detail,
    )


def dedupe_preserve_order(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def search(
    query: str,
    *,
    vault_root: Path | None = None,
    keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    limit: int = 10,
    ignore_paper_markdown: bool = False,
) -> list[NoteResult]:
    root = (vault_root or configured_vault_root()).expanduser().resolve()
    raw_terms = dedupe_preserve_order((keywords or []) + ([query] if query else []))
    phrases = [term for term in raw_terms if len(extract_terms(term)) > 1]
    terms = dedupe_preserve_order(extract_terms(" ".join(raw_terms)))
    raw_exclude = dedupe_preserve_order(exclude_keywords or [])
    exclude_phrases = [term for term in raw_exclude if len(extract_terms(term)) > 1]
    exclude_terms = dedupe_preserve_order(extract_terms(" ".join(raw_exclude)))
    if not terms and not phrases:
        return []

    results = [
        score_note(path, root, terms, phrases, exclude_terms, exclude_phrases)
        for path in iter_markdown_notes(root, ignore_paper_markdown=ignore_paper_markdown)
    ]
    results = [result for result in results if result.score > 0]
    return sorted(results, key=lambda item: item.score, reverse=True)[: max(1, limit)]


def print_full_context(result: NoteResult, *, max_chars: int) -> None:
    text = read_text(Path(result.path)).rstrip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n...[truncated]"
    print("   full_context:")
    for line in text.splitlines():
        print(f"     {line}")


def print_human(
    results: list[NoteResult],
    *,
    detail_count: int,
    show_score_detail: bool,
    full: bool,
    max_full_chars: int,
) -> None:
    if not results:
        print("No matching notes found.")
        return
    for index, result in enumerate(results, start=1):
        if index > detail_count:
            print(f"{index}. {result.wikilink} - {result.title} score={result.score}")
            continue
        print(f"{index}. {result.wikilink}  score={result.score}")
        print(f"   title={result.title}")
        print(f"   path={result.relative_path}")
        print("   matched=" + ", ".join(result.matched_terms))
        if result.excluded_terms:
            print("   exclude_penalty=" + ", ".join(result.excluded_terms))
        for snippet in result.snippets:
            print(f"   - {snippet}")
        if show_score_detail:
            print("   detail=" + json.dumps(result.score_detail, sort_keys=True))
        if full:
            print_full_context(result, max_chars=max_full_chars)
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*", help="question or description to search for")
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
    parser.add_argument("--vault-root", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="maximum number of results")
    parser.add_argument("--top", type=int, default=None, help="alias for --limit")
    parser.add_argument("--detail", type=int, default=10, help="number of full cards to print")
    parser.add_argument("--detailed", action="store_true", help="print score details")
    parser.add_argument("--full", action="store_true", help="include bounded full text for detailed cards")
    parser.add_argument("--max-full-chars", type=int, default=12000)
    parser.add_argument(
        "--ignore-papers",
        action="store_true",
        help="skip PaperHub metadata notes and generated summaries under organized/",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    term_args = [term for group in args.terms for term in group]
    query = " ".join(args.query).strip()
    if not query and term_args:
        query = " ".join(term_args)
    limit = args.top if args.top is not None else args.limit
    limit = max(1, limit or 10)
    detail_count = max(0, min(args.detail, limit))
    results = search(
        query,
        vault_root=args.vault_root,
        keywords=args.keyword + term_args,
        exclude_keywords=[term for group in args.exclude for term in group],
        limit=limit,
        ignore_paper_markdown=args.ignore_papers,
    )
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        print_human(
            results,
            detail_count=detail_count,
            show_score_detail=args.detailed,
            full=args.full,
            max_full_chars=max(500, args.max_full_chars),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
