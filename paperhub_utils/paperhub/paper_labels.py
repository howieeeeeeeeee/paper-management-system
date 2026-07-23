"""Paper-label validation and Hybrid PascalCase formatting."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence


LABEL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "can",
    "do",
    "does",
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
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "without",
}

_KNOWN_ACRONYMS = {
    "ai": "AI",
    "covid": "COVID",
    "did": "DID",
    "dsge": "DSGE",
    "gdp": "GDP",
    "io": "IO",
    "iv": "IV",
    "llm": "LLM",
    "llms": "LLMs",
    "ml": "ML",
    "nlp": "NLP",
    "ols": "OLS",
    "rct": "RCT",
    "rcts": "RCTs",
    "rd": "RD",
    "rl": "RL",
}

_ACRONYM_PHRASES = (
    (re.compile(r"\blarge[\s-]+language[\s-]+models?\b", re.IGNORECASE), "LLM"),
    (
        re.compile(
            r"\brandomi[sz]ed[\s-]+controlled[\s-]+trials?\b",
            re.IGNORECASE,
        ),
        "RCT",
    ),
    (re.compile(r"\bartificial[\s-]+intelligence\b", re.IGNORECASE), "AI"),
    (re.compile(r"\bmachine[\s-]+learning\b", re.IGNORECASE), "ML"),
)

_SURNAME_PARTICLES = {
    "abdel",
    "al",
    "bin",
    "da",
    "dal",
    "de",
    "del",
    "della",
    "der",
    "di",
    "du",
    "la",
    "le",
    "st",
    "ter",
    "van",
    "von",
}
_AUTHOR_SUFFIXES = {"ii", "iii", "iv", "jr", "junior", "sr", "senior"}
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]*$")
_PAPER_LABEL_SHAPE_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*\d{4}[A-Za-z0-9_]*$"
)


def ascii_transliterate(value: object) -> str:
    """Return an ASCII transliteration while preserving the input's letter case."""
    text = str(value).translate(
        str.maketrans(
            {
                "ı": "i",
                "Ł": "L",
                "ł": "l",
                "Đ": "D",
                "đ": "d",
                "Ø": "O",
                "ø": "o",
            }
        )
    )
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def is_safe_paper_label(value: object) -> bool:
    """Return whether *value* is a path-safe ASCII alphanumeric/underscore label."""
    return isinstance(value, str) and bool(_SAFE_LABEL_RE.fullmatch(value))


def require_safe_paper_label(value: object) -> str:
    """Return a safe label unchanged, or raise ``ValueError``."""
    if not is_safe_paper_label(value):
        raise ValueError(
            "paper_label must contain only ASCII letters, digits, and underscores "
            "and must begin with a letter or digit"
        )
    return str(value)


def looks_like_paper_label(value: object) -> bool:
    """Return whether *value* is safe and contains an author/year label shape."""
    return isinstance(value, str) and bool(_PAPER_LABEL_SHAPE_RE.fullmatch(value))


def _pascal_token(token: str) -> str:
    if not token:
        return ""
    known = _KNOWN_ACRONYMS.get(token.lower())
    if known:
        return known
    letters = "".join(char for char in token if char.isalpha())
    if len(letters) >= 2 and letters.isupper():
        return token
    if any(char.isupper() for char in token[1:]):
        return token[0].upper() + token[1:]
    return token[0].upper() + token[1:].lower()


def _component(value: object) -> str:
    ascii_value = ascii_transliterate(value)
    return "".join(
        _pascal_token(token)
        for token in re.findall(r"[A-Za-z0-9]+", ascii_value)
    )


def pascal_label_component(value: object) -> str:
    """Return a PascalCase ASCII component without inferring name structure."""
    return _component(value)


def author_surname_component(author: object) -> str:
    """Extract and PascalCase a surname, retaining common surname particles."""
    text = ascii_transliterate(author).strip()
    if not text:
        return ""

    if "," in text:
        surname = text.split(",", 1)[0]
        return _component(surname)

    name_parts = text.split()
    while name_parts:
        suffix = re.sub(r"[^A-Za-z0-9]", "", name_parts[-1]).lower()
        if suffix not in _AUTHOR_SUFFIXES:
            break
        name_parts.pop()
    if not name_parts:
        return ""

    start = len(name_parts) - 1
    while start > 0:
        preceding = re.sub(r"[^A-Za-z0-9]", "", name_parts[start - 1]).lower()
        if preceding not in _SURNAME_PARTICLES:
            break
        start -= 1
    return _component(" ".join(name_parts[start:]))


def title_topic_component(title: object, *, max_words: int = 2) -> str:
    """Build a short PascalCase topic from the first meaningful title words."""
    if max_words < 1:
        raise ValueError("max_words must be at least 1")

    text = ascii_transliterate(title)
    for pattern, acronym in _ACRONYM_PHRASES:
        text = pattern.sub(acronym, text)

    chosen: list[str] = []
    for token in re.findall(r"[A-Za-z0-9]+", text):
        if token.lower() in LABEL_STOPWORDS:
            continue
        chosen.append(_pascal_token(token))
        if len(chosen) == max_words:
            break
    return "".join(chosen) or "Paper"


def format_hybrid_paper_label(
    authors: Sequence[object] | object,
    year: object,
    title: object,
    *,
    topic_words: int = 2,
) -> str:
    """Format ``Surname(s)YearTopic`` using the Hybrid PascalCase convention."""
    if isinstance(authors, (str, bytes)) or not isinstance(authors, Sequence):
        author_values = [authors]
    else:
        author_values = list(authors)

    surnames = [
        component
        for author in author_values
        if (component := author_surname_component(author))
    ]
    if not surnames:
        raise ValueError("Cannot derive paper_label: at least one author is required")

    year_text = str(year).strip()
    if not re.fullmatch(r"\d{4}", year_text):
        raise ValueError("Cannot derive paper_label: year must contain four digits")

    topic = title_topic_component(title, max_words=topic_words)
    if len(surnames) == 1:
        author_part = surnames[0]
    elif len(surnames) == 2:
        author_part = "".join(surnames)
    else:
        author_part = f"{surnames[0]}_etal"

    return require_safe_paper_label(f"{author_part}{year_text}{topic}")
