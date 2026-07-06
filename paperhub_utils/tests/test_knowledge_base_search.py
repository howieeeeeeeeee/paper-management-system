from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import knowledge_base_search
from scripts.knowledge_base_search import (
    is_paper_markdown,
    iter_markdown_notes,
    search,
)


class KnowledgeBaseSearchTests(unittest.TestCase):
    def test_search_finds_visible_markdown_and_formats_wikilink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "projects" / "seminar_notes.md"
            note.parent.mkdir()
            note.write_text(
                "---\n"
                "title: Seminar Notes\n"
                "---\n\n"
                "# Seminar Notes\n\n"
                "These notes discuss moral wiggle room and strategic ignorance.\n",
                encoding="utf-8",
            )

            results = search("strategic ignorance", vault_root=root)

        self.assertTrue(results)
        self.assertEqual(results[0].relative_path, "projects/seminar_notes.md")
        self.assertEqual(results[0].wikilink, "[[projects/seminar_notes|Seminar Notes]]")
        self.assertIn("strategic", results[0].matched_terms)

    def test_hidden_dot_directories_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidden = root / ".claude" / "secret.md"
            hidden.parent.mkdir()
            hidden.write_text("moral wiggle room only hidden here\n", encoding="utf-8")
            visible = root / "visible.md"
            visible.write_text("unrelated note\n", encoding="utf-8")

            notes = iter_markdown_notes(root)
            results = search("moral wiggle", vault_root=root)

        self.assertEqual(notes, [visible])
        self.assertEqual(results, [])

    def test_standard_paper_metadata_note_uses_label_wikilink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "organized" / "danaetal2007moralwiggle"
            paper.mkdir(parents=True)
            (paper / "danaetal2007moralwiggle.md").write_text(
                "---\n"
                "title: Exploiting Moral Wiggle Room\n"
                "---\n\n"
                "Dictators avoid payoff information.\n",
                encoding="utf-8",
            )

            results = search("dictators payoff", vault_root=root)

        self.assertTrue(results)
        self.assertEqual(results[0].wikilink, "[[danaetal2007moralwiggle]]")

    def test_ignore_papers_skips_metadata_and_ai_summary_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "organized" / "flowerman2026llmbelief"
            paper.mkdir(parents=True)
            metadata = paper / "flowerman2026llmbelief.md"
            summary = paper / "ai_summary.md"
            legacy_summary = paper / "summary.md"
            project_note = paper / "experiment notes.md"
            metadata.write_text(
                "# LLM Belief Paper\n\nConfirmation bias appears in large language model belief updates.\n",
                encoding="utf-8",
            )
            summary.write_text(
                "# AI Summary\n\nConfirmation bias appears in large language model behavior.\n",
                encoding="utf-8",
            )
            legacy_summary.write_text(
                "# Summary\n\nConfirmation bias appears in large language model agents.\n",
                encoding="utf-8",
            )
            project_note.write_text(
                "# Experiment Notes\n\nConfirmation bias appears in large language model pilots.\n",
                encoding="utf-8",
            )

            default_notes = iter_markdown_notes(root)
            notes_only = iter_markdown_notes(root, ignore_paper_markdown=True)
            results = search(
                "confirmation bias large language model",
                vault_root=root,
                ignore_paper_markdown=True,
            )

        self.assertTrue(is_paper_markdown(metadata, root))
        self.assertTrue(is_paper_markdown(summary, root))
        self.assertTrue(is_paper_markdown(legacy_summary, root))
        self.assertFalse(is_paper_markdown(project_note, root))
        self.assertIn(metadata, default_notes)
        self.assertIn(summary, default_notes)
        self.assertIn(legacy_summary, default_notes)
        self.assertNotIn(metadata, notes_only)
        self.assertNotIn(summary, notes_only)
        self.assertNotIn(legacy_summary, notes_only)
        self.assertIn(project_note, notes_only)
        self.assertEqual(
            [result.relative_path for result in results],
            ["organized/flowerman2026llmbelief/experiment notes.md"],
        )

    def test_default_top_is_ten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(12):
                (root / f"note_{index}.md").write_text(
                    f"# Note {index}\n\nshared keyword appears here.\n",
                    encoding="utf-8",
                )

            results = search("shared keyword", vault_root=root)

        self.assertEqual(len(results), 10)

    def test_cli_terms_full_and_detail_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research.md").write_text(
                "# Research Log\n\nStrategic ignorance creates moral wiggle room.\n",
                encoding="utf-8",
            )

            old_argv = knowledge_base_search.sys.argv
            knowledge_base_search.sys.argv = [
                "knowledge_base_search.py",
                "--vault-root",
                str(root),
                "--terms",
                "moral wiggle room",
                "strategic ignorance",
                "--top",
                "3",
                "--detail",
                "1",
                "--full",
                "--max-full-chars",
                "500",
            ]
            try:
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = knowledge_base_search.main()
            finally:
                knowledge_base_search.sys.argv = old_argv

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        self.assertIn("[[research|Research Log]]", text)
        self.assertIn("full_context:", text)

    def test_cli_ignore_papers_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "organized" / "flowerman2026llmbelief"
            paper.mkdir(parents=True)
            (paper / "flowerman2026llmbelief.md").write_text(
                "# LLM Belief Paper\n\nConfirmation bias appears in large language model belief updates.\n",
                encoding="utf-8",
            )
            (root / "research.md").write_text(
                "# Research Log\n\nConfirmation bias appears in large language model notes.\n",
                encoding="utf-8",
            )

            old_argv = knowledge_base_search.sys.argv
            knowledge_base_search.sys.argv = [
                "knowledge_base_search.py",
                "--vault-root",
                str(root),
                "--terms",
                "confirmation bias",
                "large language model",
                "--top",
                "5",
                "--detail",
                "5",
                "--ignore-papers",
            ]
            try:
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = knowledge_base_search.main()
            finally:
                knowledge_base_search.sys.argv = old_argv

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        self.assertIn("[[research|Research Log]]", text)
        self.assertNotIn("[[flowerman2026llmbelief]]", text)


if __name__ == "__main__":
    unittest.main()
