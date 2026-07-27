"""PDF helpers shared by CLI-driven paper workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from paperhub.config import PAPERHUB_ROOT

REPO_ROOT = PAPERHUB_ROOT
CLI_WORK_DIR = REPO_ROOT / ".paperhub_tmp"


@dataclass(frozen=True)
class PdfSample:
    original_path: Path
    sample_path: Path
    pages_sent: int
    total_pages: int
    page_limit: int


def create_first_pages_pdf(
    pdf_path: Path,
    page_limit: int,
    output_dir: Path,
) -> PdfSample:
    """Create a temporary PDF containing the first configured pages."""
    if page_limit < 1:
        raise ValueError("metadata-only page limit must be at least 1")

    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as e:
        raise RuntimeError("Missing dependency: install pypdf to trim PDFs") from e

    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    if total_pages < 1:
        raise ValueError(f"PDF has no pages: {pdf_path}")

    pages_sent = min(page_limit, total_pages)
    writer = PdfWriter()
    for page_index in range(pages_sent):
        writer.add_page(reader.pages[page_index])

    output_dir.mkdir(parents=True, exist_ok=True)
    sample_path = output_dir / (
        f"{pdf_path.stem}_first_{pages_sent}_pages_{uuid4().hex[:10]}.pdf"
    )
    with sample_path.open("wb") as f:
        writer.write(f)

    return PdfSample(
        original_path=pdf_path,
        sample_path=sample_path,
        pages_sent=pages_sent,
        total_pages=total_pages,
        page_limit=page_limit,
    )


def _normalize_words(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def title_mismatch_problem(
    response_text: str,
    pdf_path: Path,
    *,
    pages: int = 2,
    threshold: float = 0.6,
) -> str | None:
    """Return a problem string when a response's title is absent from the PDF.

    Guards against applying a response that was generated for a different paper
    (for example a stale artifact file left over from an earlier run). Returns
    None when the check passes or cannot be performed, so PDFs without an
    extractable text layer are never rejected on this basis.
    """
    match = re.search(r'^title:\s*"?(.+?)"?\s*$', response_text, re.MULTILINE)
    if not match:
        return None

    title = match.group(1).strip()
    words = [w for w in _normalize_words(title).split() if len(w) > 3]
    if not words:
        return None

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        extracted = " ".join(
            (reader.pages[i].extract_text() or "")
            for i in range(min(pages, len(reader.pages)))
        )
    except Exception:
        return None

    haystack = _normalize_words(extracted)
    if len(haystack.split()) < 20:
        return None

    hits = sum(1 for w in words if w in haystack)
    ratio = hits / len(words)
    if ratio >= threshold:
        return None
    return (
        f"Response title does not match the PDF (only {ratio:.0%} of title words "
        f"found in the first {pages} pages of {pdf_path.name}). "
        f"Response title: {title!r}. "
        "The response was probably generated from a different PDF or is a stale artifact."
    )


def repo_relative_path(path: Path) -> str:
    """Return a POSIX repo-relative path for external CLI references."""
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def ensure_safe_cli_cleanup_path(path: Path) -> Path:
    """Resolve a cleanup path and ensure it stays under the CLI work dir."""
    resolved = path.resolve()
    work_dir = CLI_WORK_DIR.resolve()
    if resolved != work_dir and work_dir not in resolved.parents:
        raise ValueError(f"Refusing to clean up outside {work_dir}: {resolved}")
    return resolved
