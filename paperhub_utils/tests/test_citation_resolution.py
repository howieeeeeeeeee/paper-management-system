from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from paperhub.citation_resolution import (
    CSL_JSON_ACCEPT,
    audit_citations,
    fetch_doi_csl,
    inspect_citation_file,
    normalize_csl,
    resolve_citations,
    resolve_one,
    validate_csl_object,
    validate_identity,
)
from paperhub.metadata_notes import read_metadata_note
from paperhub.metadata_resolution import PaperMetadata


def add_note(
    root: Path,
    label: str,
    *,
    title: str = "Trade and Productivity",
    author: str = "Jane Smith",
    year: int = 2025,
    link: str = "",
    include_link: bool = True,
) -> Path:
    folder = root / label
    folder.mkdir(parents=True)
    link_line = f"link: {link}\n" if include_link else ""
    path = folder / f"{label}.md"
    path.write_text(
        "---\n"
        f"title: {title}\n"
        "authors:\n"
        f"  - {author}\n"
        f"year: {year}\n"
        f"{link_line}"
        "tags:\n"
        "  - trade\n"
        "---\n"
        "\n"
        "## Abstract\n"
        "Keep this body.\n",
        encoding="utf-8",
    )
    return path


def csl(
    label: str,
    *,
    title: str = "Trade and Productivity",
    family: str = "Smith",
    year: int = 2025,
    doi: str | None = "10.1234/example",
) -> dict:
    value = {
        "id": label,
        "type": "article-journal",
        "title": title,
        "author": [{"family": family, "given": "Jane"}],
        "issued": {"date-parts": [[year]]},
        "container-title": "Journal of Tests",
        "volume": "12",
        "issue": "3",
        "page": "100-125",
        "editor": [{"family": "Jones", "given": "Alex"}],
    }
    if doi:
        value["DOI"] = doi
    return value


class FakeResponse:
    def __init__(self, payload: object, *, content: bytes = b"{}") -> None:
        self.payload = payload
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class CitationResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.organized = Path(self.temporary.name) / "organized"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_csl_validation_and_identity_thresholds(self) -> None:
        add_note(self.organized, "Smith2025Trade")
        note = read_metadata_note("Smith2025Trade", self.organized)
        valid, errors = validate_csl_object(csl("Smith2025Trade"), expected_label="Smith2025Trade")
        self.assertTrue(valid)
        self.assertEqual(errors, ())
        malformed_date = csl("Smith2025Trade")
        malformed_date["issued"] = {"date-parts": [["2025"]]}
        self.assertFalse(validate_csl_object(malformed_date)[0])
        self.assertTrue(validate_identity(note, csl("Smith2025Trade"), agent_discovered=True)["valid"])
        mismatch = validate_identity(
            note,
            csl("Smith2025Trade", title="A Completely Different Subject", family="Jones", year=2010),
            agent_discovered=True,
        )
        self.assertFalse(mismatch["valid"])

    def test_audit_classifies_without_network_or_writes(self) -> None:
        ready_path = add_note(self.organized, "Ready2025")
        ready_citation = ready_path.parent / "citation.csl.json"
        ready_citation.write_text(json.dumps(csl("Ready2025")) + "\n", encoding="utf-8")
        add_note(
            self.organized,
            "Linked2025",
            link="https://doi.org/10.1234/example",
        )
        add_note(self.organized, "Blank2025")
        add_note(self.organized, "Blocked2025", include_link=False)
        invalid_path = add_note(self.organized, "Invalid2025", link="https://example.org")
        (invalid_path.parent / "citation.csl.json").write_text('{"id": "wrong"}\n', encoding="utf-8")
        before = {
            path: path.read_bytes()
            for path in self.organized.rglob("*")
            if path.is_file()
        }

        with patch(
            "paperhub.citation_resolution.build_session",
            side_effect=AssertionError("audit must not construct a network session"),
        ), patch(
            "paperhub.metadata_notes.atomic_write_text",
            side_effect=AssertionError("audit must not write"),
        ):
            result = audit_citations(
                ["Ready2025", "Linked2025", "Blank2025", "Blocked2025", "Invalid2025"],
                organized_dir=self.organized,
            )

        self.assertEqual(
            result["counts"],
            {
                "ready": 1,
                "needs_citation_from_link": 2,
                "needs_link_then_citation": 1,
                "blocked": 1,
            },
        )
        self.assertEqual(result["invalid_existing_citation_files"], 1)
        self.assertEqual(
            before,
            {path: path.read_bytes() for path in before},
        )

    def test_malformed_metadata_is_reported_not_raised(self) -> None:
        folder = self.organized / "Broken2025"
        folder.mkdir(parents=True)
        (folder / "Broken2025.md").write_text("---\ntitle: [broken\n---\n", encoding="utf-8")
        result = audit_citations(["Broken2025"], organized_dir=self.organized)
        self.assertEqual(result["categories"]["blocked"], ["Broken2025"])
        self.assertIn("malformed_metadata", result["items"][0]["reason"])

    def test_doi_content_negotiation_preserves_rich_csl(self) -> None:
        session = Mock()
        rich = csl("upstream")
        rich["ISBN"] = "978-1-234"
        session.get.return_value = FakeResponse(rich)

        result = fetch_doi_csl("10.1234/EXAMPLE", session)

        self.assertEqual(result["volume"], "12")
        self.assertEqual(result["editor"][0]["family"], "Jones")
        self.assertEqual(result["ISBN"], "978-1-234")
        _, kwargs = session.get.call_args
        self.assertEqual(kwargs["headers"]["Accept"], CSL_JSON_ACCEPT)

    def test_crossref_type_alias_is_normalized_without_losing_rich_fields(self) -> None:
        rich = csl("upstream")
        rich["type"] = "journal-article"
        rich["reference"] = [{"key": "ref-1", "DOI": "10.1234/cited"}]

        result = normalize_csl(rich, label="Smith2025Trade")

        self.assertEqual(result["type"], "article-journal")
        self.assertEqual(result["reference"], rich["reference"])
        self.assertEqual(result["id"], "Smith2025Trade")

    def test_resolves_doi_repairs_invalid_and_writes_atomically(self) -> None:
        label = "Smith2025Trade"
        note_path = add_note(
            self.organized,
            label,
            link="https://doi.org/10.1234/example",
        )
        citation_path = note_path.parent / "citation.csl.json"
        citation_path.write_text('{"id": "wrong"}\n', encoding="utf-8")
        session = Mock()
        session.get.return_value = FakeResponse(csl("upstream"))

        result = resolve_one(label, organized_dir=self.organized, session=session)

        self.assertEqual(result["status"], "resolved")
        self.assertTrue(result["repaired_invalid"])
        loaded = json.loads(citation_path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["id"], label)
        self.assertEqual(loaded["volume"], "12")
        self.assertEqual(loaded["URL"], "https://doi.org/10.1234/example")
        self.assertEqual(list(citation_path.parent.glob(f".{citation_path.name}.*")), [])

    def test_existing_valid_citation_is_skipped_without_fetching(self) -> None:
        label = "Smith2025Trade"
        note_path = add_note(
            self.organized,
            label,
            link="https://doi.org/10.1234/example",
        )
        citation_path = note_path.parent / "citation.csl.json"
        citation_path.write_text(json.dumps(csl(label)) + "\n", encoding="utf-8")
        session = Mock()

        result = resolve_one(label, organized_dir=self.organized, session=session)

        self.assertEqual(result["status"], "skipped_valid")
        session.get.assert_not_called()

    def test_agent_candidate_updates_only_blank_link_after_validation(self) -> None:
        label = "Smith2025Trade"
        note_path = add_note(self.organized, label)
        before_body = note_path.read_text(encoding="utf-8").split("---\n", 2)[-1]
        session = Mock()
        session.get.return_value = FakeResponse(csl("upstream"))

        result = resolve_one(
            label,
            candidate_link="https://doi.org/10.1234/example",
            organized_dir=self.organized,
            session=session,
        )

        self.assertEqual(result["status"], "resolved")
        self.assertTrue(result["link_updated"])
        after = note_path.read_text(encoding="utf-8")
        self.assertIn("link: https://doi.org/10.1234/example", after)
        self.assertEqual(after.split("---\n", 2)[-1], before_body)

    def test_identity_failure_does_not_update_blank_link_or_write_citation(self) -> None:
        label = "Smith2025Trade"
        note_path = add_note(self.organized, label)
        before = note_path.read_text(encoding="utf-8")
        session = Mock()
        session.get.return_value = FakeResponse(
            csl("upstream", title="Wrong Topic Entirely", family="Jones", year=2010)
        )

        result = resolve_one(
            label,
            candidate_link="https://doi.org/10.1234/example",
            organized_dir=self.organized,
            session=session,
        )

        self.assertEqual(result["status"], "identity_mismatch")
        self.assertEqual(note_path.read_text(encoding="utf-8"), before)
        self.assertFalse((note_path.parent / "citation.csl.json").exists())

    def test_nonblank_identity_failure_is_link_conflict_and_preserves_link(self) -> None:
        label = "Smith2025Trade"
        note_path = add_note(
            self.organized,
            label,
            link="https://doi.org/10.1234/wrong",
        )
        session = Mock()
        session.get.return_value = FakeResponse(
            csl("upstream", title="Wrong Topic Entirely", family="Jones", year=2010, doi="10.1234/wrong")
        )

        result = resolve_one(label, organized_dir=self.organized, session=session)

        self.assertEqual(result["status"], "link_conflict")
        self.assertIn("https://doi.org/10.1234/wrong", note_path.read_text(encoding="utf-8"))
        self.assertFalse((note_path.parent / "citation.csl.json").exists())

    def test_arxiv_and_landing_page_doi_paths(self) -> None:
        arxiv_label = "Smith2025Arxiv"
        add_note(
            self.organized,
            arxiv_label,
            link="https://arxiv.org/abs/2501.01234",
        )
        arxiv_meta = PaperMetadata(
            title="Trade and Productivity",
            authors=["Jane Smith"],
            year=2025,
            journal="arXiv preprint",
            doi=None,
            url="https://arxiv.org/abs/2501.01234",
        )
        with patch("paperhub.citation_resolution.resolve_by_arxiv", return_value=arxiv_meta):
            arxiv_result = resolve_one(
                arxiv_label,
                organized_dir=self.organized,
                session=Mock(),
            )
        self.assertEqual(arxiv_result["status"], "resolved")

        landing_label = "Smith2025Landing"
        add_note(
            self.organized,
            landing_label,
            link="https://publisher.example/article",
        )
        session = Mock()
        session.get.return_value = FakeResponse(csl("upstream"))
        with patch(
            "paperhub.citation_resolution.validate_public_url",
            return_value="https://publisher.example/article",
        ), patch(
            "paperhub.citation_resolution.fetch_public_resource",
            return_value=("https://publisher.example/article", "text/html", b"<html></html>"),
        ), patch(
            "paperhub.citation_resolution.parse_landing_page",
            return_value={
                "title": "Trade and Productivity",
                "authors": ["Jane Smith"],
                "year": 2025,
                "doi": "10.1234/example",
            },
        ):
            landing_result = resolve_one(
                landing_label,
                organized_dir=self.organized,
                session=session,
            )
        self.assertEqual(landing_result["status"], "resolved")
        self.assertEqual(session.get.call_args.args[0], "https://doi.org/10.1234/example")

    def test_legacy_sidecar_fallback_and_network_failure(self) -> None:
        sidecar_label = "Smith2025Sidecar"
        note_path = add_note(self.organized, sidecar_label)
        (note_path.parent / "source.citation.md").write_text(
            "---\n"
            "title: Trade and Productivity\n"
            "authors:\n"
            "  - Jane Smith\n"
            "year: 2025\n"
            "journal: Working Papers\n"
            "---\n",
            encoding="utf-8",
        )
        sidecar_result = resolve_one(
            sidecar_label,
            organized_dir=self.organized,
            session=Mock(),
        )
        self.assertEqual(sidecar_result["status"], "resolved")
        self.assertEqual(sidecar_result["source"], "citation_sidecar")

        failure_label = "Smith2025Failure"
        failure_path = add_note(
            self.organized,
            failure_label,
            link="https://doi.org/10.1234/example",
        )
        session = Mock()
        session.get.side_effect = RuntimeError("offline")
        failure_result = resolve_one(
            failure_label,
            organized_dir=self.organized,
            session=session,
        )
        self.assertEqual(failure_result["status"], "failed")
        self.assertFalse((failure_path.parent / "citation.csl.json").exists())

    def test_best_effort_batch_isolates_missing_metadata(self) -> None:
        label = "Smith2025Trade"
        add_note(
            self.organized,
            label,
            link="https://doi.org/10.1234/example",
        )
        session = Mock()
        session.get.return_value = FakeResponse(csl("upstream"))

        result = resolve_citations(
            ["Missing2025", label],
            organized_dir=self.organized,
            session=session,
        )

        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["results"][0]["status"], "blocked")
        self.assertEqual(
            inspect_citation_file(
                self.organized / label / "citation.csl.json",
                expected_label=label,
            ).status,
            "valid",
        )

    def test_write_failure_is_marked_fatal_for_cli_contract(self) -> None:
        label = "Smith2025Trade"
        add_note(
            self.organized,
            label,
            link="https://doi.org/10.1234/example",
        )
        session = Mock()
        session.get.return_value = FakeResponse(csl("upstream"))

        with patch(
            "paperhub.citation_resolution.atomic_write_json",
            side_effect=OSError("read-only destination"),
        ):
            result = resolve_citations(
                [label],
                organized_dir=self.organized,
                session=session,
            )

        self.assertEqual(result["fatal_write_errors"], 1)
        self.assertEqual(result["results"][0]["error_kind"], "write_error")
        self.assertFalse(
            (self.organized / label / "citation.csl.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
