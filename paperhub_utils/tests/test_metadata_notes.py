from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperhub.metadata_notes import (
    MetadataNoteError,
    atomic_write_json,
    extract_arxiv_id,
    extract_doi,
    fill_blank_link,
    is_syntactically_usable_public_link,
    read_metadata_note,
    set_citation_exist,
)


def write_note(root: Path, label: str, *, link_line: str = "link:") -> Path:
    folder = root / label
    folder.mkdir(parents=True)
    path = folder / f"{label}.md"
    path.write_text(
        "---\n"
        "title: A Paper\n"
        "authors:\n"
        "  - Jane Smith\n"
        "year: 2025\n"
        f"{link_line}\n"
        "tags:\n"
        "  - Experiments\n"
        "---\n"
        "\n"
        "## Abstract\n"
        "Body stays unchanged.\n",
        encoding="utf-8",
    )
    return path


class MetadataNotesTests(unittest.TestCase):
    def test_reads_canonical_note_and_normalizes_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            organized = Path(temporary) / "organized"
            write_note(
                organized,
                "Smith2025Paper",
                link_line="link: https://doi.org/10.1234/Example.",
            )

            note = read_metadata_note("Smith2025Paper", organized)

        self.assertEqual(note.title, "A Paper")
        self.assertEqual(note.authors, ("Jane Smith",))
        self.assertEqual(note.year, 2025)
        self.assertEqual(note.tags, ("Experiments",))
        self.assertEqual(extract_doi(note.link), "10.1234/Example")
        self.assertEqual(
            extract_arxiv_id("https://arxiv.org/pdf/2501.01234.pdf?download=1"),
            "2501.01234",
        )

    def test_blank_link_edit_is_surgical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            organized = Path(temporary) / "organized"
            path = write_note(
                organized,
                "Smith2025Paper",
                link_line="link:   # intentionally blank",
            )
            before = path.read_text(encoding="utf-8")
            note = read_metadata_note("Smith2025Paper", organized)

            changed = fill_blank_link(note, "https://doi.org/10.1234/example")
            after = path.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertEqual(
            after,
            before.replace(
                "link:   # intentionally blank",
                "link:   https://doi.org/10.1234/example # intentionally blank",
            ),
        )

    def test_citation_exist_is_inserted_after_link_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            organized = Path(temporary) / "organized"
            path = write_note(
                organized,
                "Smith2025Paper",
                link_line="link: https://doi.org/10.1234/example",
            )
            before = path.read_text(encoding="utf-8")

            note = read_metadata_note("Smith2025Paper", organized)
            first = set_citation_exist(note)
            after = path.read_text(encoding="utf-8")

            # A second pass must not duplicate the field or rewrite the note.
            second = set_citation_exist(read_metadata_note("Smith2025Paper", organized))
            settled = path.read_text(encoding="utf-8")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(after, settled)
        self.assertEqual(
            after,
            before.replace(
                "link: https://doi.org/10.1234/example",
                "link: https://doi.org/10.1234/example\ncitation_exist: true",
            ),
        )
        self.assertIn("Body stays unchanged.", after)

    def test_citation_exist_upgrades_a_false_flag_and_tolerates_missing_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            organized = Path(temporary) / "organized"
            path = write_note(
                organized,
                "Smith2025Paper",
                link_line="link: https://doi.org/10.1234/example\ncitation_exist: false",
            )

            changed = set_citation_exist(read_metadata_note("Smith2025Paper", organized))
            after = path.read_text(encoding="utf-8")

            # No link field at all: the flag lands inside the frontmatter block.
            other = organized / "Jones2025Paper"
            other.mkdir(parents=True)
            note_path = other / "Jones2025Paper.md"
            note_path.write_text(
                "---\ntitle: No Link\nyear: 2025\n---\n\n## Abstract\nText.\n",
                encoding="utf-8",
            )
            set_citation_exist(read_metadata_note("Jones2025Paper", organized))
            fallback = note_path.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertIn("citation_exist: true", after)
        self.assertNotIn("citation_exist: false", after)
        self.assertEqual(
            fallback,
            "---\ntitle: No Link\nyear: 2025\ncitation_exist: true\n---\n\n## Abstract\nText.\n",
        )

    def test_nonblank_link_and_unsafe_labels_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            organized = Path(temporary) / "organized"
            write_note(
                organized,
                "Smith2025Paper",
                link_line="link: https://example.org/paper",
            )
            note = read_metadata_note("Smith2025Paper", organized)
            with self.assertRaises(MetadataNoteError):
                fill_blank_link(note, "https://doi.org/10.1234/example")
            with self.assertRaises(MetadataNoteError):
                read_metadata_note("../escape", organized)

    def test_duplicate_link_fields_are_marked_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            organized = Path(temporary) / "organized"
            path = write_note(organized, "Smith2025Paper")
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "link:\n",
                    "link:\nlink: https://example.org/duplicate\n",
                ),
                encoding="utf-8",
            )

            note = read_metadata_note("Smith2025Paper", organized)

        self.assertEqual(note.parse_error, "duplicate top-level link fields")
        self.assertFalse(note.has_link_field)

    def test_public_link_syntax_rejects_local_and_non_http_targets(self) -> None:
        self.assertTrue(is_syntactically_usable_public_link("https://example.org/paper"))
        self.assertTrue(is_syntactically_usable_public_link("arXiv:2501.01234"))
        self.assertFalse(is_syntactically_usable_public_link("file:///tmp/paper.pdf"))
        self.assertFalse(is_syntactically_usable_public_link("http://localhost/paper"))
        self.assertFalse(is_syntactically_usable_public_link("http://127.0.0.1/paper"))
        self.assertFalse(is_syntactically_usable_public_link("https://user:pass@example.org"))

    def test_atomic_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "nested" / "citation.csl.json"
            atomic_write_json(output, {"id": "Ångström2025", "type": "book", "title": "T"})
            text = output.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertIn('  "id": "Ångström2025"', text)
            self.assertEqual(json.loads(text)["type"], "book")
            self.assertEqual(list(output.parent.glob(f".{output.name}.*")), [])
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
