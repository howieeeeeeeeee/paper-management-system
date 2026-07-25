from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperhub.paper_selection import SelectionError, select_papers


def add_paper(root: Path, label: str, tags: list[str], citation: object | None = None) -> None:
    folder = root / label
    folder.mkdir(parents=True)
    tag_lines = "".join(f"  - {tag}\n" for tag in tags)
    (folder / f"{label}.md").write_text(
        "---\n"
        f"title: {label}\n"
        "authors:\n"
        "  - Jane Smith\n"
        "year: 2025\n"
        "link:\n"
        "tags:\n"
        f"{tag_lines}"
        "---\n",
        encoding="utf-8",
    )
    if citation is not None:
        (folder / "citation.csl.json").write_text(
            json.dumps(citation, indent=2) + "\n",
            encoding="utf-8",
        )


def valid_citation(label: str) -> dict:
    return {"id": label, "type": "article-journal", "title": label}


class PaperSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.organized = Path(self.temporary.name) / "organized"
        add_paper(
            self.organized,
            "Alpha2025",
            ["Behavioral_Economics", "experiments", "ambiguity"],
            valid_citation("Alpha2025"),
        )
        add_paper(
            self.organized,
            "Beta2025",
            ["behavioral_economics", "experiments", "beliefs"],
        )
        add_paper(
            self.organized,
            "Gamma2025",
            ["behavioral_economics", "theory", "beliefs"],
            {"id": "wrong", "type": "article-journal", "title": "Gamma2025"},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_and_or_and_combined_conditions(self) -> None:
        self.assertEqual(
            select_papers(
                all_tags=["behavioral_economics", "EXPERIMENTS"],
                organized_dir=self.organized,
            ).labels,
            ("Alpha2025", "Beta2025"),
        )
        self.assertEqual(
            select_papers(
                any_tags=["ambiguity", "beliefs"],
                organized_dir=self.organized,
            ).labels,
            ("Alpha2025", "Beta2025", "Gamma2025"),
        )
        self.assertEqual(
            select_papers(
                all_tags=["behavioral_economics", "experiments"],
                any_tags=["beliefs"],
                organized_dir=self.organized,
            ).labels,
            ("Beta2025",),
        )

    def test_explicit_order_and_citation_statuses(self) -> None:
        selection = select_papers(
            explicit_labels=["Gamma2025", "Alpha2025", "Gamma2025"],
            organized_dir=self.organized,
        )
        self.assertEqual(selection.labels, ("Gamma2025", "Alpha2025"))
        self.assertEqual(
            select_papers(citation_status="ready", organized_dir=self.organized).labels,
            ("Alpha2025",),
        )
        self.assertEqual(
            select_papers(citation_status="missing", organized_dir=self.organized).labels,
            ("Beta2025",),
        )
        self.assertEqual(
            select_papers(citation_status="invalid", organized_dir=self.organized).labels,
            ("Gamma2025",),
        )
        self.assertEqual(
            select_papers(citation_status="unresolved", organized_dir=self.organized).labels,
            ("Beta2025", "Gamma2025"),
        )

    def test_unknown_explicit_label_is_an_argument_error(self) -> None:
        with self.assertRaises(SelectionError):
            select_papers(explicit_labels=["Missing2025"], organized_dir=self.organized)


if __name__ == "__main__":
    unittest.main()
