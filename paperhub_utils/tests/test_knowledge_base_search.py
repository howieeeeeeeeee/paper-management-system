from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import knowledge_base_search
from scripts.knowledge_base_search import iter_markdown_notes, search


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


if __name__ == "__main__":
    unittest.main()
