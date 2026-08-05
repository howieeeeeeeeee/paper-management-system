from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.related_paper_candidates import (
    author_signatures,
    extract_related_links,
    scan_related_paper_candidates,
)


ROOT = Path(__file__).resolve().parents[2]


def write_note(
    organized: Path,
    label: str,
    *,
    title: str = "Example Paper",
    authors: list[str] | None = None,
    year: int | str = 2025,
    body: str = "## Abstract\nAn example abstract.",
    malformed: bool = False,
) -> Path:
    folder = organized / label
    folder.mkdir(parents=True)
    path = folder / f"{label}.md"
    if malformed:
        path.write_text("---\ntitle: [broken\n---\n", encoding="utf-8")
        return path
    author_lines = "\n".join(f"  - {author}" for author in (authors or ["Ada Example"]))
    path.write_text(
        f"""---
title: "{title}"
authors:
{author_lines}
year: {year}
tags:
  - test
contributions:
---

# {title}

{body}
""",
        encoding="utf-8",
    )
    return path


def digest_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class RelatedPaperSectionTests(unittest.TestCase):
    def test_exact_heading_bullets_aliases_and_boundaries(self) -> None:
        text = """# Source

## Related Papers
- [[old1999topic|Readable name]] - Core comparison.
Plain [[ignored2000paper]] link.
### Subgroup
* [[other2001work]]: Another comparison.

## Research Ideas
- [[outside2002paper]] - Not part of Related Papers.
"""
        found, links = extract_related_links(text)
        self.assertTrue(found)
        self.assertEqual([link.target_label for link in links], ["old1999topic", "other2001work"])
        self.assertEqual(links[0].description, "Core comparison.")
        self.assertEqual(links[0].line, 4)

    def test_heading_text_is_exact_and_horizontal_rule_stops_section(self) -> None:
        no_match, links = extract_related_links(
            "## Related Literature\n- [[old1999topic]] - No.\n"
        )
        self.assertFalse(no_match)
        self.assertEqual(links, [])

        found, links = extract_related_links(
            "## Related Papers\n- [[old1999topic]] - Yes.\n---\n- [[outside2000paper]]\n"
        )
        self.assertTrue(found)
        self.assertEqual([link.target_label for link in links], ["old1999topic"])


class AuthorSignatureTests(unittest.TestCase):
    def test_one_two_and_multi_author_standard_variants(self) -> None:
        self.assertEqual(set(author_signatures(["Marc Melitz"])), {"melitz"})
        self.assertEqual(
            set(author_signatures(["David Card", "Alan Krueger"])),
            {"cardkrueger", "cardetal"},
        )
        signatures = author_signatures(
            ["David Autor", "David Dorn", "Gordon Hanson", "Jae Song"]
        )
        for expected in (
            "autoretal",
            "autordornetal",
            "autordornhansonetal",
            "autordornhanson",
            "autordornhansonsong",
        ):
            self.assertIn(expected, signatures)


class RelatedPaperWorkflowIntegrationTests(unittest.TestCase):
    def test_reconciliation_runs_after_tags_and_before_versioning(self) -> None:
        text = (
            ROOT / ".claude/skills/paper-organizer/shared/post_ai.md"
        ).read_text(encoding="utf-8")
        tag_position = text.index("## 4. Tag flow handoff")
        related_position = text.index("## 5. Related-paper label reconciliation")
        version_position = text.index("## 6. Version")
        self.assertLess(tag_position, related_position)
        self.assertLess(related_position, version_position)
        self.assertIn(
            "python -m scripts.related_paper_candidates --pretty", text
        )


class CandidateScanTests(unittest.TestCase):
    def test_format_tolerant_two_author_match_and_read_only_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            organized = Path(tmp) / "organized"
            write_note(
                organized,
                "Card_Krueger_1994_Minimum",
                title="Minimum Wages and Employment",
                authors=["David Card", "Alan B. Krueger"],
                year=1994,
                body="## Abstract\nWe study minimum wages and employment.",
            )
            write_note(
                organized,
                "Source2025Paper",
                body=(
                    "## Abstract\nSource abstract.\n\n"
                    "## Related Papers\n"
                    "- [[cardkrueger1994minimum]] - A minimum-wage comparison.\n"
                ),
            )
            before = digest_tree(organized)
            result = scan_related_paper_candidates(
                ["Source2025Paper"], organized_dir=organized
            )
            after = digest_tree(organized)

        self.assertEqual(before, after)
        self.assertEqual(result["counts"]["review_candidates"], 1)
        candidate = result["review"][0]["candidates"][0]
        self.assertEqual(candidate["paper_label"], "Card_Krueger_1994_Minimum")
        self.assertEqual(candidate["author_evidence"], "two_authors")
        self.assertEqual(candidate["context_type"], "abstract")

    def test_two_author_etal_is_weak_but_bare_first_author_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            organized = Path(tmp) / "organized"
            write_note(
                organized,
                "CardKrueger1994Minimum",
                authors=["David Card", "Alan Krueger"],
                year=1994,
            )
            write_note(
                organized,
                "Source2025Paper",
                body=(
                    "## Related Papers\n"
                    "- [[CardEtAl1994Minimum]] - Abbreviated preset.\n"
                    "- [[Card1994Minimum]] - Invalid two-author abbreviation.\n"
                ),
            )
            result = scan_related_paper_candidates(
                ["Source2025Paper"], organized_dir=organized
            )

        self.assertEqual(result["counts"]["review_candidates"], 1)
        self.assertEqual(result["counts"]["no_candidate"], 1)
        candidate = result["review"][0]["candidates"][0]
        self.assertEqual(candidate["author_evidence"], "two_author_etal")

    def test_multi_author_variants_accents_and_main_contribution_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            organized = Path(tmp) / "organized"
            write_note(
                organized,
                "AlosFerrer_etal2023Choice",
                title="Choice and Response Times",
                authors=["Carlos Alós-Ferrer", "Anna Granic", "Bo Example"],
                year=2023,
                body=(
                    "## Key Takeaways for My Research\n\n"
                    "**Main Contribution:**\n"
                    "This paper studies choice and response times.\n\n"
                    "**Methodology/Technique:**\nExperiment.\n"
                ),
            )
            write_note(
                organized,
                "Source2025Paper",
                body=(
                    "### Related Papers\n"
                    "- [[Alós-FerrerEtAl2023Choice]] - Choice and response times.\n"
                    "- [[Alos-FerrerGranicExample2023Choice]] - Same paper, all authors.\n"
                ),
            )
            result = scan_related_paper_candidates(
                ["Source2025Paper"], organized_dir=organized
            )

        self.assertEqual(result["counts"]["review_candidates"], 2)
        for item in result["review"]:
            self.assertEqual(item["candidates"][0]["paper_label"], "AlosFerrer_etal2023Choice")
            self.assertEqual(item["candidates"][0]["context_type"], "main_contribution")

    def test_ambiguity_self_links_exact_links_missing_year_and_malformed_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            organized = Path(tmp) / "organized"
            write_note(
                organized,
                "Wang_etal2025First",
                authors=["Wei Wang", "Ada One", "Bob One"],
                year=2025,
            )
            write_note(
                organized,
                "Wang_etal2025Second",
                authors=["Wei Wang", "Ada Two", "Bob Two"],
                year=2025,
            )
            write_note(organized, "Broken2025Paper", malformed=True)
            write_note(
                organized,
                "Source2026Paper",
                body=(
                    "## Related Papers\n"
                    "- [[WangEtAl2025Topic]] - Ambiguous.\n"
                    "- [[Wang_etal2025First]] - Already exact.\n"
                    "- [[Source2026Paper]] - Self link.\n"
                    "- [[NoYearPaper]] - Missing year.\n"
                ),
            )
            result = scan_related_paper_candidates(
                ["Source2026Paper", "Missing2025Paper"], organized_dir=organized
            )

        self.assertEqual(result["counts"]["ambiguous_candidates"], 1)
        self.assertEqual(len(result["review"][0]["candidates"]), 2)
        self.assertEqual(result["counts"]["already_resolved"], 1)
        self.assertEqual(result["counts"]["self_links"], 1)
        self.assertEqual(result["counts"]["no_candidate"], 1)
        self.assertEqual(result["counts"]["missing_or_invalid_papers"], 1)
        self.assertTrue(any("Broken2025Paper" in warning for warning in result["warnings"]))

    def test_label_year_can_match_when_metadata_year_changed_and_base_duplicate_sorts_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            organized = Path(tmp) / "organized"
            for label in (
                "HeeseChen2024Information",
                "HeeseChen2024Information_20260101_010101",
            ):
                write_note(
                    organized,
                    label,
                    title="Fishing for Good News",
                    authors=["Carl Heese", "Si Chen"],
                    year=2026,
                )
            write_note(
                organized,
                "Source2025Paper",
                body=(
                    "## Related Papers\n"
                    "- [[HeeseChen2024Fishing]] - Motivated information acquisition.\n"
                ),
            )
            result = scan_related_paper_candidates(
                ["Source2025Paper"], organized_dir=organized
            )

        candidates = result["review"][0]["candidates"]
        self.assertEqual(candidates[0]["paper_label"], "HeeseChen2024Information")
        self.assertEqual(candidates[0]["year_evidence"], "label")
        self.assertEqual(
            candidates[1]["paper_label"],
            "HeeseChen2024Information_20260101_010101",
        )


if __name__ == "__main__":
    unittest.main()
