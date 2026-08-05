#!/usr/bin/env python3
"""Find existing PaperHub labels that may match Related Papers wikilinks.

This command is deliberately read-only. It uses canonical metadata frontmatter
to build an in-memory author/year index, then emits only the compact candidate
context that a coding agent needs for semantic review.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from paperhub.config import DEFAULT_ORGANIZED_DIR
from paperhub.paper_labels import (
    ascii_transliterate,
    author_surname_component,
    is_safe_paper_label,
)
from paperhub.tag_utils.common import iter_main_metadata_files, parse_frontmatter


YEAR_RE = re.compile(r"(?<!\d)((?:1[5-9]|20|21)\d{2})(?!\d)")
HEADING_RE = re.compile(r"^(?P<marks>#{1,6})[ \t]+Related Papers[ \t]*$")
ANY_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})[ \t]+")
LIST_ITEM_RE = re.compile(r"^[ \t]*[-*+][ \t]+")
WIKILINK_RE = re.compile(r"\[\[(?P<inside>[^\]\n]+)\]\]")
HORIZONTAL_RULE_RE = re.compile(r"^[ \t]*---[ \t]*$")
TIMESTAMP_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}$")
PLACEHOLDER_RE = re.compile(
    r"^\[(?:abstract (?:not found|unavailable)|to be (?:added|filled))",
    re.IGNORECASE,
)

CONTEXT_LIMIT = 1600


@dataclass(frozen=True)
class RelatedLink:
    line: int
    original_wikilink: str
    original_target: str
    target_label: str
    bullet: str
    description: str


@dataclass(frozen=True)
class PaperIdentity:
    label: str
    path: Path
    title: str
    authors: tuple[str, ...]
    metadata_year: int | None
    label_years: tuple[int, ...]
    body: str
    parse_error: str | None

    @property
    def years(self) -> set[int]:
        values = set(self.label_years)
        if self.metadata_year is not None:
            values.add(self.metadata_year)
        return values


def normalize_component(value: object) -> str:
    """Normalize label components across case, accents, and separators."""
    return re.sub(r"[^a-z0-9]", "", ascii_transliterate(value).casefold())


def extract_year(value: object) -> int | None:
    match = YEAR_RE.search(ascii_transliterate(value))
    return int(match.group(1)) if match else None


def extract_label_years(label: str) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(match.group(1)) for match in YEAR_RE.finditer(label)))


def coerce_authors(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    if isinstance(raw, list):
        return tuple(str(value).strip() for value in raw if str(value).strip())
    return ()


def read_identities(organized_dir: Path) -> tuple[list[PaperIdentity], list[str]]:
    """Read canonical identities; keep malformed notes as warnings, not failures."""
    identities: list[PaperIdentity] = []
    warnings: list[str] = []
    for path in iter_main_metadata_files(organized_dir):
        parsed = parse_frontmatter(path)
        frontmatter = parsed.frontmatter
        metadata_year = extract_year(frontmatter.get("year"))
        identity = PaperIdentity(
            label=path.parent.name,
            path=path.resolve(),
            title=str(frontmatter.get("title") or "").strip(),
            authors=coerce_authors(frontmatter.get("authors")),
            metadata_year=metadata_year,
            label_years=extract_label_years(path.parent.name),
            body=parsed.body,
            parse_error=parsed.parse_error,
        )
        identities.append(identity)
        if parsed.parse_error:
            warnings.append(f"{identity.label}: {parsed.parse_error}")
    return identities, warnings


def clean_target(inside: str) -> tuple[str, str]:
    target = inside.split("|", 1)[0].split("#", 1)[0].strip()
    leaf = target.rsplit("/", 1)[-1]
    if leaf.casefold().endswith(".md"):
        leaf = leaf[:-3]
    return target, leaf.strip()


def _description_from_bullet(line: str, wikilink: str) -> str:
    text = LIST_ITEM_RE.sub("", line, count=1).replace(wikilink, "", 1).strip()
    return text.strip(" \t-:–—")


def extract_related_links(text: str) -> tuple[bool, list[RelatedLink]]:
    """Return bullet wikilinks under the exact ``Related Papers`` heading."""
    lines = text.splitlines()
    active = False
    heading_level = 0
    heading_found = False
    links: list[RelatedLink] = []

    for index, line in enumerate(lines, start=1):
        heading = HEADING_RE.fullmatch(line)
        if heading:
            active = True
            heading_level = len(heading.group("marks"))
            heading_found = True
            continue

        if not active:
            continue
        if HORIZONTAL_RULE_RE.fullmatch(line):
            active = False
            continue
        next_heading = ANY_HEADING_RE.match(line)
        if next_heading and len(next_heading.group("marks")) <= heading_level:
            active = False
            continue
        if not LIST_ITEM_RE.match(line):
            continue

        for match in WIKILINK_RE.finditer(line):
            original_wikilink = match.group(0)
            original_target, target_label = clean_target(match.group("inside"))
            links.append(
                RelatedLink(
                    line=index,
                    original_wikilink=original_wikilink,
                    original_target=original_target,
                    target_label=target_label,
                    bullet=line,
                    description=_description_from_bullet(line, original_wikilink),
                )
            )
    return heading_found, links


def author_signatures(authors: Sequence[str]) -> dict[str, tuple[str, int]]:
    """Return accepted author prefixes mapped to (evidence label, rank)."""
    surnames = [
        normalize_component(component)
        for author in authors
        if (component := author_surname_component(author))
    ]
    if not surnames:
        return {}

    signatures: dict[str, tuple[str, int]] = {}

    def add(value: str, evidence: str, rank: int) -> None:
        current = signatures.get(value)
        if value and (current is None or rank < current[1]):
            signatures[value] = (evidence, rank)

    if len(surnames) == 1:
        add(surnames[0], "single_author", 0)
        return signatures

    if len(surnames) == 2:
        add("".join(surnames), "two_authors", 0)
        # PaperHub's first_author_etal preset permits this non-default form.
        add(f"{surnames[0]}etal", "two_author_etal", 2)
        return signatures

    add(f"{surnames[0]}etal", "first_author_etal", 0)
    for count in range(2, len(surnames)):
        add("".join(surnames[:count]) + "etal", "leading_authors_etal", 1)
    for count in range(3, len(surnames) + 1):
        evidence = "all_authors" if count == len(surnames) else "leading_authors"
        rank = 0 if count == len(surnames) else 1
        add("".join(surnames[:count]), evidence, rank)
    return signatures


def split_related_target(target_label: str) -> tuple[str, int] | None:
    transliterated = ascii_transliterate(target_label)
    match = YEAR_RE.search(transliterated)
    if not match:
        return None
    author_key = normalize_component(transliterated[: match.start()])
    if not author_key:
        return None
    return author_key, int(match.group(1))


def _section_excerpt(body: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ims)^##[ \t]+{re.escape(heading)}[ \t]*\r?\n(.*?)(?=^##[ \t]+|\Z)"
    )
    match = pattern.search(body)
    if not match:
        return ""
    text = re.sub(r"\s+", " ", match.group(1)).strip()
    if not text or PLACEHOLDER_RE.match(text):
        return ""
    return text[:CONTEXT_LIMIT]


def _main_contribution_excerpt(body: str) -> str:
    match = re.search(
        r"(?ims)^\*\*Main Contribution:\*\*[ \t]*(.*?)(?=^\*\*[^\n]+:\*\*|^#{1,6}[ \t]+|\Z)",
        body,
    )
    if not match:
        return ""
    text = re.sub(r"\s+", " ", match.group(1)).strip()
    return text[:CONTEXT_LIMIT]


def candidate_context(identity: PaperIdentity) -> tuple[str, str]:
    abstract = _section_excerpt(identity.body, "Abstract")
    if abstract:
        return "abstract", abstract
    contribution = _main_contribution_excerpt(identity.body)
    if contribution:
        return "main_contribution", contribution
    return "none", ""


def candidate_for(
    identity: PaperIdentity,
    *,
    author_key: str,
    year: int,
) -> dict[str, Any] | None:
    if identity.parse_error or not identity.authors or year not in identity.years:
        return None
    signature = author_signatures(identity.authors).get(author_key)
    if signature is None:
        return None
    author_evidence, rank = signature
    if identity.metadata_year == year and year in identity.label_years:
        year_evidence = "metadata_and_label"
    elif identity.metadata_year == year:
        year_evidence = "metadata"
    else:
        year_evidence = "label"
    context_type, context = candidate_context(identity)
    return {
        "paper_label": identity.label,
        "metadata_path": str(identity.path),
        "title": identity.title,
        "authors": list(identity.authors),
        "metadata_year": identity.metadata_year,
        "label_years": list(identity.label_years),
        "context_type": context_type,
        "context": context,
        "author_evidence": author_evidence,
        "year_evidence": year_evidence,
        "_rank": rank,
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
    label = str(candidate["paper_label"])
    return (
        int(candidate["_rank"]),
        1 if TIMESTAMP_SUFFIX_RE.search(label) else 0,
        label.casefold(),
    )


def scan_related_paper_candidates(
    labels: Sequence[str],
    *,
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
) -> dict[str, Any]:
    organized_dir = Path(organized_dir).expanduser().resolve()
    identities, warnings = read_identities(organized_dir)
    by_label = {identity.label: identity for identity in identities}
    exact_labels = set(by_label)
    review: list[dict[str, Any]] = []
    counts = {
        "papers_requested": len(labels),
        "papers_scanned": 0,
        "headings_found": 0,
        "links_seen": 0,
        "already_resolved": 0,
        "review_candidates": 0,
        "ambiguous_candidates": 0,
        "no_candidate": 0,
        "self_links": 0,
        "missing_or_invalid_papers": 0,
    }

    for source_label in labels:
        if not is_safe_paper_label(source_label):
            warnings.append(f"{source_label}: unsafe paper label")
            counts["missing_or_invalid_papers"] += 1
            continue
        source = by_label.get(source_label)
        if source is None:
            warnings.append(f"{source_label}: canonical metadata note not found")
            counts["missing_or_invalid_papers"] += 1
            continue
        if source.parse_error:
            warnings.append(f"{source_label}: source metadata is malformed")
            counts["missing_or_invalid_papers"] += 1
            continue

        try:
            source_text = source.path.read_text(encoding="utf-8")
        except OSError as exc:
            warnings.append(f"{source_label}: read failed: {exc}")
            counts["missing_or_invalid_papers"] += 1
            continue

        counts["papers_scanned"] += 1
        heading_found, related_links = extract_related_links(source_text)
        if not heading_found:
            continue
        counts["headings_found"] += 1

        for related in related_links:
            counts["links_seen"] += 1
            if related.target_label == source_label:
                counts["self_links"] += 1
                continue
            if related.target_label in exact_labels:
                counts["already_resolved"] += 1
                continue

            split = split_related_target(related.target_label)
            if split is None:
                counts["no_candidate"] += 1
                continue
            author_key, year = split
            candidates = []
            for identity in identities:
                if identity.label == source_label:
                    continue
                candidate = candidate_for(identity, author_key=author_key, year=year)
                if candidate is not None:
                    candidates.append(candidate)
            candidates.sort(key=_candidate_sort_key)
            for candidate in candidates:
                candidate.pop("_rank", None)

            if not candidates:
                counts["no_candidate"] += 1
                continue
            counts["review_candidates"] += 1
            if len(candidates) > 1:
                counts["ambiguous_candidates"] += 1
            review.append(
                {
                    "source_label": source_label,
                    "source_metadata_path": str(source.path),
                    "line": related.line,
                    "original_wikilink": related.original_wikilink,
                    "original_target": related.original_target,
                    "description": related.description,
                    "bullet": related.bullet,
                    "author_key": author_key,
                    "year": year,
                    "candidates": candidates,
                }
            )

    return {
        "schema_version": 1,
        "organized_dir": str(organized_dir),
        "labels": list(labels),
        "counts": counts,
        "review": review,
        "warnings": sorted(set(warnings)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find local author/year candidates for Related Papers links (read-only)."
    )
    parser.add_argument("labels", nargs="+", help="Just-processed PaperHub labels")
    parser.add_argument(
        "--organized-dir",
        type=Path,
        default=DEFAULT_ORGANIZED_DIR,
        help="Override the organized papers directory",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    result = scan_related_paper_candidates(
        args.labels,
        organized_dir=args.organized_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
