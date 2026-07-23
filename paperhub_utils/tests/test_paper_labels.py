from __future__ import annotations

import unittest

from paperhub.cli_workflow.utils import derive_paper_label_from_frontmatter
from paperhub.paper_labels import (
    author_surname_component,
    format_hybrid_paper_label,
    is_safe_paper_label,
    looks_like_paper_label,
    require_safe_paper_label,
    title_topic_component,
)
from scripts.paper_summarizer import (
    SUMMARY_MODE_FULL,
    SUMMARY_MODE_METADATA_ONLY,
    parse_markdown_sections,
)


class PaperLabelFormattingTests(unittest.TestCase):
    def test_safe_validator_preserves_new_and_legacy_labels(self) -> None:
        for label in (
            "AnDu2026MoralAlignment",
            "Huynh_etal2026LLMCooperation",
            "andu2026moralalignment",
            "ACF2015",
        ):
            self.assertTrue(is_safe_paper_label(label))
            self.assertEqual(require_safe_paper_label(label), label)
            self.assertTrue(looks_like_paper_label(label))

    def test_safe_validator_rejects_path_and_non_ascii_characters(self) -> None:
        for label in ("../paper", "An-Du2026Topic", "Köbis2024AI", "_hidden", ""):
            self.assertFalse(is_safe_paper_label(label))
            with self.assertRaises(ValueError):
                require_safe_paper_label(label)

    def test_formats_one_two_and_many_authors(self) -> None:
        self.assertEqual(
            format_hybrid_paper_label(
                ["Marc Melitz"],
                2003,
                "Heterogeneous Firms and International Trade",
            ),
            "Melitz2003HeterogeneousFirms",
        )
        self.assertEqual(
            format_hybrid_paper_label(
                ["Tao An", "Xin Du"],
                "2026",
                "Moral Alignment in Strategic Decisions",
            ),
            "AnDu2026MoralAlignment",
        )
        self.assertEqual(
            format_hybrid_paper_label(
                ["Huynh, Anh", "Ada Example", "Bob Example"],
                2026,
                "LLM Cooperation and Collective Action",
            ),
            "Huynh_etal2026LLMCooperation",
        )

    def test_transliterates_accents_hyphens_and_particles(self) -> None:
        self.assertEqual(author_surname_component("Nils Köbis"), "Kobis")
        self.assertEqual(author_surname_component("Pelin Boyacı"), "Boyaci")
        self.assertEqual(author_surname_component("Ernesto Dal Bó"), "DalBo")
        self.assertEqual(author_surname_component("Fadi Abdel Haq"), "AbdelHaq")
        self.assertEqual(author_surname_component("Jane Smith-Jones"), "SmithJones")
        self.assertEqual(author_surname_component("Lina van der Meer"), "VanDerMeer")
        self.assertEqual(author_surname_component("McDonald, Jane"), "McDonald")

    def test_preserves_and_recovers_common_title_acronyms(self) -> None:
        self.assertEqual(title_topic_component("LLM cooperation at scale"), "LLMCooperation")
        self.assertEqual(
            title_topic_component("Large Language Models Cooperate"),
            "LLMCooperate",
        )
        self.assertEqual(
            title_topic_component("Randomized controlled trials of AI advice"),
            "RCTAI",
        )

    def test_metadata_first_cli_fallback_uses_hybrid_format(self) -> None:
        frontmatter = """---
title: "LLM Cooperation in Social Dilemmas"
authors:
  - Anh Huynh
  - Ada Example
  - Bob Example
year: 2026
---"""
        self.assertEqual(
            derive_paper_label_from_frontmatter(frontmatter),
            "Huynh_etal2026LLMCooperation",
        )


class PaperLabelParserTests(unittest.TestCase):
    def test_full_flexible_parser_accepts_hybrid_label(self) -> None:
        content = """# Huynh_etal2026LLMCooperation
# metadata
---
title: LLM Cooperation
---
# ai_summary
Summary.
"""
        parsed = parse_markdown_sections(content, SUMMARY_MODE_FULL)
        self.assertEqual(parsed["paper_label"], "Huynh_etal2026LLMCooperation")

    def test_metadata_only_flexible_parser_keeps_legacy_label(self) -> None:
        content = """# huynhetal2026llmcooperation
# metadata
---
title: LLM Cooperation
---
"""
        parsed = parse_markdown_sections(content, SUMMARY_MODE_METADATA_ONLY)
        self.assertEqual(parsed["paper_label"], "huynhetal2026llmcooperation")

    def test_exact_parser_rejects_unsafe_label(self) -> None:
        content = """# paper_label
../escape
# metadata
---
title: Unsafe
---
"""
        with self.assertRaises(ValueError):
            parse_markdown_sections(content, SUMMARY_MODE_METADATA_ONLY)


if __name__ == "__main__":
    unittest.main()
