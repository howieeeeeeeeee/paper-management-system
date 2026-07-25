from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperhub.bibliography import (
    BibliographyError,
    MissingCitationsError,
    build_bibliography,
    csl_to_bibtex_entry,
    duplicate_doi_warnings,
    render_bibtex,
    render_markdown,
    render_reference_data,
)


def citation(
    label: str,
    *,
    csl_type: str = "article-journal",
    doi: str = "10.1234/example",
    year: int = 2025,
) -> dict:
    return {
        "id": label,
        "type": csl_type,
        "title": "Trade & Productivity_{測試}",
        "author": [
            {"family": "Smith", "given": "Jane"},
            {"literal": "Research Group"},
        ],
        "editor": [{"family": "Jones", "given": "Alex"}],
        "issued": {"date-parts": [[year]]},
        "container-title": "Journal of Tests",
        "volume": "12",
        "issue": "3",
        "page": "100-125",
        "publisher": "Example Press",
        "publisher-place": "Taipei",
        "DOI": doi,
        "URL": f"https://doi.org/{doi}",
    }


def add_paper(root: Path, label: str, value: dict | None = None) -> None:
    folder = root / label
    folder.mkdir(parents=True)
    (folder / f"{label}.md").write_text(
        "---\n"
        f"title: {label}\n"
        "authors:\n"
        "  - Jane Smith\n"
        "year: 2025\n"
        "link:\n"
        "tags:\n"
        "  - trade\n"
        "---\n",
        encoding="utf-8",
    )
    if value is not None:
        (folder / "citation.csl.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class BibliographyTests(unittest.TestCase):
    def test_type_and_field_mapping_with_people_and_sensitive_characters(self) -> None:
        entry = csl_to_bibtex_entry(citation("Smith2025"))
        self.assertEqual(entry["ENTRYTYPE"], "article")
        self.assertEqual(entry["ID"], "Smith2025")
        self.assertEqual(entry["author"], "Smith, Jane and Research Group")
        self.assertEqual(entry["editor"], "Jones, Alex")
        self.assertEqual(entry["year"], "2025")
        self.assertEqual(entry["journal"], "Journal of Tests")
        self.assertEqual(entry["number"], "3")
        self.assertEqual(entry["pages"], "100-125")
        self.assertEqual(entry["address"], "Taipei")
        self.assertIn(r"\&", entry["title"])
        self.assertIn(r"\_", entry["title"])
        self.assertIn(r"\{測試\}", entry["title"])
        self.assertIn("測試", entry["title"])

        chapter = csl_to_bibtex_entry(citation("Chapter2025", csl_type="chapter"))
        self.assertEqual(chapter["ENTRYTYPE"], "incollection")
        self.assertIn("booktitle", chapter)
        self.assertNotIn("journal", chapter)

    def test_stable_order_and_duplicate_doi_warning_without_omission(self) -> None:
        first = citation("Zulu2025")
        second = citation("Alpha2025", doi="10.1234/EXAMPLE")
        output = render_bibtex([first, second])
        self.assertLess(output.index("@article{Alpha2025"), output.index("@article{Zulu2025"))
        self.assertEqual(
            duplicate_doi_warnings([first, second]),
            [{"doi": "10.1234/example", "labels": ["Zulu2025", "Alpha2025"]}],
        )
        self.assertIn("@article{Alpha2025", output)
        self.assertIn("@article{Zulu2025", output)

    def test_missing_checkpoint_partial_build_and_overwrite_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            organized = root / "organized"
            add_paper(organized, "Ready2025", citation("Ready2025"))
            add_paper(organized, "Missing2025")
            output = root / "references.bib"

            with self.assertRaises(MissingCitationsError):
                build_bibliography(
                    ["Ready2025", "Missing2025"],
                    output=output,
                    organized_dir=organized,
                )

            result = build_bibliography(
                ["Ready2025", "Missing2025"],
                output=output,
                organized_dir=organized,
                allow_partial=True,
            )
            self.assertTrue(result["partial"])
            self.assertEqual(result["included_labels"], ["Ready2025"])
            self.assertEqual(result["omitted_labels"], ["Missing2025"])
            self.assertIn("@article{Ready2025", output.read_text(encoding="utf-8"))

            with self.assertRaises(BibliographyError):
                build_bibliography(
                    ["Ready2025"],
                    output=output,
                    organized_dir=organized,
                )
            overwritten = build_bibliography(
                ["Ready2025"],
                output=output,
                organized_dir=organized,
                overwrite=True,
            )
            self.assertFalse(overwritten["partial"])

    def test_output_must_be_absolute(self) -> None:
        with self.assertRaises(BibliographyError):
            build_bibliography(["Paper"], output=Path("references.bib"))

    def test_unsafe_label_is_rejected_before_any_path_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(BibliographyError):
                build_bibliography(
                    ["../escape"],
                    output=Path(temporary).resolve() / "references.bib",
                    organized_dir=Path(temporary) / "organized",
                    allow_partial=True,
                )

    def test_existing_output_directory_gets_the_default_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            organized = root / "organized"
            destination = root / "exports"
            destination.mkdir()
            add_paper(organized, "Ready2025", citation("Ready2025"))

            result = build_bibliography(
                ["Ready2025"],
                output=destination,
                organized_dir=organized,
            )

            self.assertEqual(
                result["output"],
                str((destination / "references.bib").resolve()),
            )
            self.assertTrue((destination / "references.bib").is_file())

    def test_chicago_style_and_same_author_year_render_best_effort(self) -> None:
        try:
            rendered = render_markdown(
                [
                    citation("Smith2025A", year=2025),
                    {
                        **citation("Smith2025B", year=2025),
                        "title": "A Second Paper",
                        "DOI": "10.1234/second",
                    },
                ],
                style="chicago-author-date",
            )
        except BibliographyError as exc:
            if "formatted-citations" in str(exc):
                self.skipTest("formatted-citations optional extra is not installed")
            raise
        self.assertTrue(rendered.startswith("# References\n\n- "))
        self.assertIn("<i>Journal of Tests</i>", rendered)
        self.assertIn("Trade", rendered)
        self.assertIn("Second Paper", rendered)
        # citeproc-py is best-effort and may not add year suffixes (2025a/2025b).
        self.assertGreaterEqual(rendered.count("2025"), 2)

        footnotes = render_markdown(
            [citation("Smith2025A"), citation("Smith2025B", doi="10.1234/second")],
            style="chicago-author-date",
            footnote_definitions=True,
        )
        self.assertIn("[^Smith2025A]:", footnotes)
        self.assertIn("[^Smith2025B]:", footnotes)

    def test_reference_data_is_dependency_free_and_agent_readable(self) -> None:
        rendered = render_reference_data([citation("Smith2025")])

        self.assertTrue(rendered.startswith("# Reference Data\n\n## Smith2025\n"))
        self.assertIn("- **Authors:** Jane Smith; Research Group", rendered)
        self.assertIn("- **Editors:** Alex Jones", rendered)
        self.assertIn("- **Issued:** 2025", rendered)
        self.assertIn("- **Title:** Trade & Productivity_{測試}", rendered)
        self.assertIn("- **Container:** Journal of Tests", rendered)
        self.assertIn("- **DOI:** 10.1234/example", rendered)
        self.assertNotIn("<i>", rendered)


if __name__ == "__main__":
    unittest.main()
