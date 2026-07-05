"""Reusable helpers for CLI response normalization."""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


LABEL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "without",
}


def normalize_label_part(text: str) -> str:
    """Return lowercase ASCII alphanumerics for paper labels."""
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "", ascii_text.lower())


def clean_yaml_scalar(value: str) -> str:
    """Strip light YAML scalar syntax used in model-generated frontmatter."""
    return value.strip().strip("\"'").strip()


def extract_frontmatter_scalar(frontmatter: str, key: str) -> str:
    match = re.search(
        rf"^{re.escape(key)}:\s*(.+?)\s*$",
        frontmatter,
        flags=re.MULTILINE,
    )
    return clean_yaml_scalar(match.group(1)) if match else ""


def extract_frontmatter_authors(frontmatter: str) -> list[str]:
    block_match = re.search(
        r"^authors:\s*\n((?:[ \t]+-\s+.+(?:\n|$))+)",
        frontmatter,
        flags=re.MULTILINE,
    )
    if block_match:
        return [
            clean_yaml_scalar(line.split("-", 1)[1])
            for line in block_match.group(1).splitlines()
            if "-" in line
        ]

    inline_authors = extract_frontmatter_scalar(frontmatter, "authors")
    if inline_authors.startswith("[") and inline_authors.endswith("]"):
        return [
            clean_yaml_scalar(part)
            for part in inline_authors.strip("[]").split(",")
            if part.strip()
        ]
    return [inline_authors] if inline_authors else []


def author_surname(author: str) -> str:
    if "," in author:
        surname = author.split(",", 1)[0]
    else:
        surname = author.split()[-1] if author.split() else ""
    return normalize_label_part(surname)


def title_keyword(title: str) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    )
    words = re.findall(r"[a-z0-9]+", ascii_title.lower())
    for word in words:
        if len(word) >= 3 and word not in LABEL_STOPWORDS:
            return normalize_label_part(word)
    return "paper"


def derive_paper_label_from_frontmatter(frontmatter: str) -> str:
    title = extract_frontmatter_scalar(frontmatter, "title")
    year = extract_frontmatter_scalar(frontmatter, "year")
    authors = extract_frontmatter_authors(frontmatter)

    if not title or not re.fullmatch(r"\d{4}", year) or not authors:
        raise ValueError(
            "Cannot derive paper_label from metadata-first response: "
            "frontmatter must include title, authors, and four-digit year"
        )

    surnames = [author_surname(author) for author in authors if author_surname(author)]
    if not surnames:
        raise ValueError(
            "Cannot derive paper_label from metadata-first response: "
            "author surname is empty"
        )

    if len(surnames) == 1:
        author_part = surnames[0]
    elif len(surnames) == 2:
        author_part = f"{surnames[0]}{surnames[1]}"
    else:
        author_part = f"{surnames[0]}etal"

    return f"{author_part}{year}{title_keyword(title)}"


def strip_leading_metadata_fence(content: str) -> str:
    """Remove a leading YAML/Markdown fence around metadata, if present."""
    return re.sub(
        r"^\s*```(?:yaml|yml|markdown|md)?\s*\n",
        "",
        content.strip(),
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def parse_metadata_first_markdown(content: str) -> dict | None:
    """Parse output that starts with metadata and later has # ai_summary."""
    content = strip_leading_metadata_fence(content)
    ai_summary_match = re.search(
        r"^#\s*ai_summary\s*$",
        content,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not ai_summary_match:
        return None

    metadata_text = content[: ai_summary_match.start()].strip()
    ai_summary = content[ai_summary_match.end() :].strip()
    frontmatter_match = re.search(
        r"(?s)^\s*(---\s*\n.*?\n---)",
        metadata_text,
    )
    if not frontmatter_match:
        return None

    paper_label = derive_paper_label_from_frontmatter(frontmatter_match.group(1))
    logger.info(
        "Metadata-first parse: label='%s', metadata=%s chars, ai_summary=%s chars",
        paper_label,
        len(metadata_text),
        len(ai_summary),
    )
    return {
        "paper_label": paper_label,
        "metadata": metadata_text,
        "ai_summary": ai_summary,
    }


def parse_metadata_only_markdown(content: str) -> dict | None:
    """Parse metadata-only output that starts with YAML frontmatter."""
    metadata_text = strip_leading_metadata_fence(content)
    frontmatter_match = re.search(
        r"(?s)^\s*(---\s*\n.*?\n---)",
        metadata_text,
    )
    if not frontmatter_match:
        return None

    paper_label = derive_paper_label_from_frontmatter(frontmatter_match.group(1))
    logger.info(
        "Metadata-only parse: label='%s', metadata=%s chars",
        paper_label,
        len(metadata_text),
    )
    return {
        "paper_label": paper_label,
        "metadata": metadata_text,
    }
