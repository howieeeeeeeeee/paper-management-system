from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperhub.note_navigation import (
    AI_SUMMARY_LINK,
    add_ai_summary_link_to_metadata,
    add_metadata_link_to_summary,
    ensure_navigation_links,
)
from scripts.enrich import apply_response, find_artifacts
from scripts.paper_summarizer import (
    SUMMARY_MODE_FULL,
    SUMMARY_MODE_METADATA_ONLY,
    organize_from_response,
)


METADATA = """---
title: "Example Paper"
authors:
  - Ada Example
year: 2026
journal: Test Journal
tags:
  - testing
contributions:
---

# Example Paper

## Abstract
An abstract.
"""


class NoteNavigationUnitTests(unittest.TestCase):
    def test_metadata_appends_exact_footer_and_preserves_content(self) -> None:
        updated = add_ai_summary_link_to_metadata(METADATA)

        self.assertTrue(
            updated.endswith(
                "---\n### Related Docs\n[[ai_summary|Link to AI Summary]]\n"
            )
        )
        self.assertIn("## Abstract\nAn abstract.", updated)

    def test_metadata_normalizes_only_related_docs_summary_link(self) -> None:
        metadata = (
            METADATA
            + "\nSee [[archive/ai_summary|an inline research note]].\n\n"
            + "---\n### Related Docs\n"
            + "[[ExampleVault/PaperHub/organized/example2026/ai_summary]]\n"
        )

        updated = add_ai_summary_link_to_metadata(metadata)

        self.assertIn("[[archive/ai_summary|an inline research note]]", updated)
        self.assertTrue(updated.endswith(f"{AI_SUMMARY_LINK}\n"))
        self.assertNotIn("organized/example2026/ai_summary", updated)

    def test_summary_link_follows_frontmatter(self) -> None:
        summary = "---\nmodel: test\n---\n\n# Summary\nBody.\n"

        updated = add_metadata_link_to_summary(summary, "example2026paper")

        self.assertEqual(
            updated,
            "---\nmodel: test\n---\n\n"
            "[[example2026paper|Back to Metadata]]\n\n"
            "# Summary\nBody.\n",
        )

    def test_summary_link_is_first_line_without_frontmatter(self) -> None:
        summary = "# Summary\nBody.\n"

        updated = add_metadata_link_to_summary(summary, "example2026paper")

        self.assertEqual(
            updated,
            "[[example2026paper|Back to Metadata]]\n\n# Summary\nBody.\n",
        )

    def test_file_update_is_idempotent_and_rejects_legacy_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            metadata = folder / "example2026paper.md"
            summary = folder / "ai_summary.md"
            legacy = folder / "summary.md"
            metadata.write_text(METADATA, encoding="utf-8")
            summary.write_text("# Summary\nBody.\n", encoding="utf-8")
            legacy.write_text("Legacy.\n", encoding="utf-8")

            first = ensure_navigation_links(metadata, summary)
            first_metadata = metadata.read_text(encoding="utf-8")
            first_summary = summary.read_text(encoding="utf-8")
            second = ensure_navigation_links(metadata, summary)

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertEqual(metadata.read_text(encoding="utf-8"), first_metadata)
            self.assertEqual(summary.read_text(encoding="utf-8"), first_summary)
            with self.assertRaisesRegex(ValueError, "only for ai_summary.md"):
                ensure_navigation_links(metadata, legacy)

    def test_unclosed_summary_frontmatter_is_rejected_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            metadata = folder / "example2026paper.md"
            summary = folder / "ai_summary.md"
            metadata.write_text(METADATA, encoding="utf-8")
            summary.write_text("---\nmodel: test\n# Summary\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unclosed YAML frontmatter"):
                ensure_navigation_links(metadata, summary)

            self.assertEqual(metadata.read_text(encoding="utf-8"), METADATA)


class NoteNavigationIntegrationTests(unittest.TestCase):
    def test_full_output_gets_both_links(self) -> None:
        response = f"""# paper_label
example2026paper
# metadata
{METADATA}
# ai_summary
# Detailed Summary
Summary body.
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"not read by organize_from_response")
            result = organize_from_response(
                response,
                pdf_path=pdf,
                model_label="test-model",
                pdf_engine="test",
                output_dir=root / "organized",
                summary_mode=SUMMARY_MODE_FULL,
            )

            self.assertTrue(result["success"])
            folder = Path(result["output_dir"])
            metadata = (folder / "example2026paper.md").read_text(encoding="utf-8")
            summary = (folder / "ai_summary.md").read_text(encoding="utf-8")

        self.assertTrue(metadata.endswith(f"{AI_SUMMARY_LINK}\n"))
        self.assertIn(
            "\n---\n\n[[example2026paper|Back to Metadata]]\n\n# Detailed Summary",
            summary,
        )

    def test_metadata_only_output_has_no_navigation(self) -> None:
        response = f"""# paper_label
example2026paper
# metadata
{METADATA}
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"not read by organize_from_response")
            result = organize_from_response(
                response,
                pdf_path=pdf,
                model_label="test-model",
                pdf_engine="test",
                output_dir=root / "organized",
                summary_mode=SUMMARY_MODE_METADATA_ONLY,
            )

            self.assertTrue(result["success"])
            folder = Path(result["output_dir"])
            metadata = (folder / "example2026paper.md").read_text(encoding="utf-8")
            self.assertFalse((folder / "ai_summary.md").exists())

        self.assertNotIn("Link to AI Summary", metadata)

    def test_enrich_output_gets_both_links(self) -> None:
        response = """# metadata_patch

# ai_summary
# Enriched Summary
Summary body.
"""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "organized"
            folder = output / "example2026paper"
            folder.mkdir(parents=True)
            metadata_path = folder / "example2026paper.md"
            metadata_path.write_text(METADATA, encoding="utf-8")
            (folder / "paper.pdf").write_bytes(b"not read by apply_response")
            artifacts = find_artifacts("example2026paper", output)

            result = apply_response(
                artifacts,
                response,
                include_summary=True,
                missing_keys=[],
                emit_abstract=False,
                model_label="test-model",
                pdf_engine="test",
                usage={},
            )
            metadata = metadata_path.read_text(encoding="utf-8")
            summary = (folder / "ai_summary.md").read_text(encoding="utf-8")

        self.assertEqual(result["summary"], "generated")
        self.assertTrue(metadata.endswith(f"{AI_SUMMARY_LINK}\n"))
        self.assertIn(
            "\n---\n\n[[example2026paper|Back to Metadata]]\n\n# Enriched Summary",
            summary,
        )


if __name__ == "__main__":
    unittest.main()
