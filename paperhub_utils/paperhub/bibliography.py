"""Build stable BibTeX or best-effort formatted bibliographies from CSL files."""

from __future__ import annotations

import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from paperhub.citation_resolution import audit_citations, inspect_citation_file
from paperhub.config import CITATION_PREFERRED_STYLE, DEFAULT_ORGANIZED_DIR
from paperhub.metadata_notes import MetadataNoteError, atomic_write_text, read_metadata_note


CSL_TO_BIBTEX_TYPE = {
    "article-journal": "article",
    "book": "book",
    "chapter": "incollection",
    "paper-conference": "inproceedings",
    "thesis": "phdthesis",
    "report": "techreport",
    "manuscript": "unpublished",
}


class BibliographyError(RuntimeError):
    """Bibliography preflight or output validation failed."""


class MissingCitationsError(BibliographyError):
    """Selected papers include unresolved citations."""

    def __init__(self, audit: dict[str, Any]):
        super().__init__("Selected papers include unresolved citations")
        self.audit = audit


def _person_to_bibtex(person: dict[str, Any]) -> str:
    literal = str(person.get("literal") or "").strip()
    if literal:
        return literal
    family = str(person.get("family") or "").strip()
    given = str(person.get("given") or "").strip()
    if family and given:
        return f"{family}, {given}"
    return family or given


def _people_to_bibtex(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    names = [_person_to_bibtex(person) for person in value if isinstance(person, dict)]
    names = [name for name in names if name]
    return " and ".join(names) if names else None


def _person_to_readable(person: dict[str, Any]) -> str:
    literal = str(person.get("literal") or "").strip()
    if literal:
        return literal
    family = str(person.get("family") or "").strip()
    given = str(person.get("given") or "").strip()
    return " ".join(part for part in (given, family) if part)


def _people_to_readable(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    names = [_person_to_readable(person) for person in value if isinstance(person, dict)]
    names = [name for name in names if name]
    return "; ".join(names) if names else None


def _issued_year(value: Any) -> str | None:
    try:
        return str(value["date-parts"][0][0])
    except (KeyError, IndexError, TypeError):
        return None


def _issued_date(value: Any) -> str | None:
    try:
        parts = value["date-parts"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(parts, list) or not parts:
        return None
    cleaned = [str(part).strip() for part in parts if str(part).strip()]
    return "-".join(cleaned) if cleaned else None


def _readable_scalar(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        parts = [str(part).strip() for part in value if str(part).strip()]
        text = "; ".join(parts)
    else:
        text = str(value).strip()
    return " ".join(text.split()) if text else None


def _bibtex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in text)


def csl_to_bibtex_entry(csl: dict[str, Any]) -> dict[str, str]:
    key = str(csl.get("id") or "").strip()
    if not key:
        raise BibliographyError("CSL object has no PaperHub id")
    csl_type = str(csl.get("type") or "").strip()
    entry_type = CSL_TO_BIBTEX_TYPE.get(csl_type, "misc")
    if csl_type == "thesis":
        genre = str(csl.get("genre") or "").casefold()
        entry_type = "mastersthesis" if "master" in genre else "phdthesis"

    entry: dict[str, str] = {"ID": key, "ENTRYTYPE": entry_type}
    direct_fields = {
        "title": "title",
        "volume": "volume",
        "issue": "number",
        "page": "pages",
        "publisher": "publisher",
        "publisher-place": "address",
        "DOI": "doi",
        "URL": "url",
    }
    for csl_field, bibtex_field in direct_fields.items():
        value = csl.get(csl_field)
        if value not in (None, ""):
            entry[bibtex_field] = _bibtex_escape(value)

    container = csl.get("container-title")
    if container:
        field = "booktitle" if entry_type in {"incollection", "inproceedings"} else "journal"
        entry[field] = _bibtex_escape(container)
    author = _people_to_bibtex(csl.get("author"))
    editor = _people_to_bibtex(csl.get("editor"))
    year = _issued_year(csl.get("issued"))
    if author:
        entry["author"] = _bibtex_escape(author)
    if editor:
        entry["editor"] = _bibtex_escape(editor)
    if year:
        entry["year"] = year
    return entry


def _load_ready_citations(
    labels: Iterable[str],
    organized_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    ready: list[dict[str, Any]] = []
    omitted: list[str] = []
    for label in labels:
        try:
            note = read_metadata_note(label, organized_dir)
        except MetadataNoteError as exc:
            if str(exc).startswith("Unsafe paper label:"):
                raise BibliographyError(str(exc)) from exc
            omitted.append(label)
            continue
        state = inspect_citation_file(
            note.citation_path,
            expected_label=label,
        )
        if state.status == "valid" and state.data is not None:
            ready.append(state.data)
        else:
            omitted.append(label)
    ready.sort(key=lambda item: str(item["id"]).casefold())
    return ready, omitted


def duplicate_doi_warnings(citations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_doi: dict[str, list[str]] = defaultdict(list)
    for citation in citations:
        doi = str(citation.get("DOI") or "").strip().casefold()
        if doi:
            by_doi[doi].append(str(citation.get("id") or ""))
    return [
        {"doi": doi, "labels": labels}
        for doi, labels in sorted(by_doi.items())
        if len(labels) > 1
    ]


def render_bibtex(citations: Iterable[dict[str, Any]]) -> str:
    try:
        from bibtexparser.bibdatabase import BibDatabase
        from bibtexparser.bwriter import BibTexWriter
    except ImportError as exc:
        raise BibliographyError(
            "bibtexparser is required; run `uv sync` in paperhub_utils"
        ) from exc

    database = BibDatabase()
    database.entries = [
        csl_to_bibtex_entry(citation)
        for citation in sorted(citations, key=lambda item: str(item["id"]).casefold())
    ]
    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = ("ID",)
    writer.add_trailing_comma = True
    return writer.write(database)


def render_reference_data(citations: Iterable[dict[str, Any]]) -> str:
    """Render stable, agent-readable citation facts without applying a CSL style."""
    lines = ["# Reference Data", ""]
    field_map = (
        ("Title", "title"),
        ("Type", "type"),
        ("Container", "container-title"),
        ("Collection", "collection-title"),
        ("Publisher", "publisher"),
        ("Publisher place", "publisher-place"),
        ("Volume", "volume"),
        ("Issue", "issue"),
        ("Number", "number"),
        ("Pages", "page"),
        ("Edition", "edition"),
        ("Genre", "genre"),
        ("DOI", "DOI"),
        ("URL", "URL"),
    )
    for citation in sorted(citations, key=lambda item: str(item["id"]).casefold()):
        citation_id = str(citation["id"])
        lines.append(f"## {citation_id}")
        authors = _people_to_readable(citation.get("author"))
        editors = _people_to_readable(citation.get("editor"))
        issued = _issued_date(citation.get("issued"))
        if authors:
            lines.append(f"- **Authors:** {authors}")
        if editors:
            lines.append(f"- **Editors:** {editors}")
        if issued:
            lines.append(f"- **Issued:** {issued}")
        for label, key in field_map:
            value = _readable_scalar(citation.get(key))
            if value:
                lines.append(f"- **{label}:** {value}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@contextmanager
def _citeproc_compatible_style(style_path: str):
    """Adapt newer Chicago page-range metadata unsupported by citeproc-py 0.9."""
    path = Path(style_path)
    text = path.read_text(encoding="utf-8")
    compatible = text.replace(
        'page-range-format="chicago-16"',
        'page-range-format="chicago"',
    ).replace(
        'page-range-format="chicago-15"',
        'page-range-format="chicago"',
    )
    if compatible == text:
        yield style_path
        return
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csl",
        encoding="utf-8",
    ) as temporary:
        temporary.write(compatible)
        temporary.flush()
        yield temporary.name


def render_markdown(
    citations: list[dict[str, Any]],
    *,
    style: str = CITATION_PREFERRED_STYLE,
    footnote_definitions: bool = False,
) -> str:
    try:
        from citeproc import (
            Citation,
            CitationItem,
            CitationStylesBibliography,
            CitationStylesStyle,
            formatter,
        )
        from citeproc.source.json import CiteProcJSON
        from citeproc_styles import get_style_filepath
    except ImportError as exc:
        raise BibliographyError(
            "Formatted citations require `uv sync --extra formatted-citations`"
        ) from exc

    source_style_path = get_style_filepath(style)
    with _citeproc_compatible_style(source_style_path) as style_path:
        if footnote_definitions:
            lines = ["# References", ""]
            for citation in citations:
                citation_id = str(citation["id"])
                bibliography = CitationStylesBibliography(
                    CitationStylesStyle(style_path, validate=False),
                    CiteProcJSON([citation]),
                    formatter.html,
                )
                bibliography.register(Citation([CitationItem(citation_id)]))
                entries = bibliography.bibliography()
                if len(entries) != 1:
                    raise BibliographyError(
                        f"CSL style did not render exactly one entry for {citation_id}"
                    )
                lines.append(f"[^{citation_id}]: {entries[0]}")
        else:
            source = CiteProcJSON(citations)
            bibliography = CitationStylesBibliography(
                CitationStylesStyle(style_path, validate=False),
                source,
                formatter.html,
            )
            for citation in citations:
                bibliography.register(Citation([CitationItem(str(citation["id"]))]))
            rendered = [str(entry) for entry in bibliography.bibliography()]
            lines = ["# References", ""]
            lines.extend(f"- {entry}" for entry in rendered)
    return "\n".join(lines) + "\n"


def build_bibliography(
    labels: Iterable[str],
    *,
    output: Path,
    output_format: str = "bibtex",
    organized_dir: Path = DEFAULT_ORGANIZED_DIR,
    allow_partial: bool = False,
    overwrite: bool = False,
    style: str = CITATION_PREFERRED_STYLE,
    footnote_definitions: bool = False,
) -> dict[str, Any]:
    ordered_labels = tuple(dict.fromkeys(str(label).strip() for label in labels if str(label).strip()))
    organized_dir = Path(organized_dir).expanduser().resolve()
    output = Path(output).expanduser()
    if not output.is_absolute():
        raise BibliographyError("Output path must be absolute")
    output = output.resolve()
    if output.is_dir():
        output = output / (
            "references.bib" if output_format == "bibtex" else "references.md"
        )
    if output.exists() and not overwrite:
        raise BibliographyError(f"Output exists; explicit overwrite approval required: {output}")
    if output_format not in {"bibtex", "markdown", "reference-data"}:
        raise BibliographyError(f"Unsupported bibliography format: {output_format}")

    audit = audit_citations(ordered_labels, organized_dir=organized_dir)
    citations, omitted = _load_ready_citations(ordered_labels, organized_dir)
    if omitted and not allow_partial:
        raise MissingCitationsError(audit)
    if not citations:
        raise BibliographyError("No ready citation records were selected")

    duplicate_warnings = duplicate_doi_warnings(citations)
    if output_format == "bibtex":
        content = render_bibtex(citations)
    elif output_format == "markdown":
        try:
            content = render_markdown(
                citations,
                style=style,
                footnote_definitions=footnote_definitions,
            )
        except BibliographyError:
            raise
        except Exception as exc:
            raise BibliographyError(
                f"Best-effort CSL formatting failed: {type(exc).__name__}: {exc}"
            ) from exc
    else:
        content = render_reference_data(citations)
    atomic_write_text(output, content)
    return {
        "success": True,
        "format": output_format,
        "output": str(output),
        "included_labels": [str(citation["id"]) for citation in citations],
        "omitted_labels": omitted,
        "partial": bool(omitted),
        "duplicate_doi_warnings": duplicate_warnings,
        "style": style if output_format == "markdown" else None,
        "formatted_output_best_effort": output_format == "markdown",
    }
