"""PDF helpers shared by CLI-driven paper workflows."""

from __future__ import annotations

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
