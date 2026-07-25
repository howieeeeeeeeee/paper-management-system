"""Deterministically select PaperHub papers by labels, tags, and citation status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from paperhub.config import DEFAULT_ORGANIZED_DIR
from paperhub.metadata_notes import MetadataNoteError, iter_metadata_notes, read_metadata_note


CITATION_STATUS_FILTERS = {"any", "ready", "missing", "invalid", "unresolved"}


class SelectionError(ValueError):
    """Selection criteria are invalid or reference unknown labels."""


@dataclass(frozen=True)
class PaperSelection:
    labels: tuple[str, ...]
    explicit_labels: tuple[str, ...]
    all_tags: tuple[str, ...]
    any_tags: tuple[str, ...]
    citation_status: str

    def to_manifest(self) -> dict:
        return {
            "labels": list(self.labels),
            "criteria": {
                "explicit_labels": list(self.explicit_labels),
                "all_tags": list(self.all_tags),
                "any_tags": list(self.any_tags),
                "citation_status": self.citation_status,
            },
        }


def _normalize_terms(values: Iterable[str] | None) -> tuple[str, ...]:
    ordered: list[str] = []
    for value in values or ():
        normalized = str(value).strip().casefold()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return tuple(ordered)


def _matches_citation_status(label: str, folder: Path, requested: str) -> bool:
    if requested == "any":
        return True
    from paperhub.citation_resolution import inspect_citation_file

    state = inspect_citation_file(folder / "citation.csl.json", expected_label=label)
    if requested == "ready":
        return state.status == "valid"
    if requested == "missing":
        return state.status == "missing"
    if requested == "invalid":
        return state.status == "invalid"
    return state.status in {"missing", "invalid"}


def select_papers(
    *,
    explicit_labels: Iterable[str] | None = None,
    all_tags: Iterable[str] | None = None,
    any_tags: Iterable[str] | None = None,
    citation_status: str = "any",
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
) -> PaperSelection:
    organized_dir = Path(organized_dir).expanduser().resolve()
    explicit = tuple(dict.fromkeys(str(label).strip() for label in explicit_labels or () if str(label).strip()))
    required = _normalize_terms(all_tags)
    alternatives = _normalize_terms(any_tags)
    requested_status = str(citation_status).strip().casefold() or "any"
    if requested_status not in CITATION_STATUS_FILTERS:
        raise SelectionError(f"Unsupported citation status: {citation_status}")

    if explicit:
        notes = []
        for label in explicit:
            try:
                notes.append(read_metadata_note(label, organized_dir))
            except MetadataNoteError as exc:
                raise SelectionError(str(exc)) from exc
    else:
        notes = list(iter_metadata_notes(organized_dir))

    labels: list[str] = []
    for note in notes:
        normalized_tags = {tag.strip().casefold() for tag in note.tags if tag.strip()}
        if required and not set(required).issubset(normalized_tags):
            continue
        if alternatives and not set(alternatives).intersection(normalized_tags):
            continue
        if not _matches_citation_status(note.label, note.folder, requested_status):
            continue
        labels.append(note.label)

    return PaperSelection(
        labels=tuple(labels),
        explicit_labels=explicit,
        all_tags=required,
        any_tags=alternatives,
        citation_status=requested_status,
    )
