from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import paper_search
from scripts.paper_search import search


class PaperSearchTests(unittest.TestCase):
    def test_search_finds_vague_moral_wiggle_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "danaetal2007moralwiggle"
            folder.mkdir()
            (folder / "danaetal2007moralwiggle.md").write_text(
                "---\n"
                "title: Exploiting Moral Wiggle Room\n"
                "authors:\n"
                "  - Jason Dana\n"
                "year: 2007\n"
                "status: unread\n"
                "interest: high\n"
                "tags:\n"
                "  - moral_wiggle_room\n"
                "---\n\n"
                "Dictators can avoid information about the recipient payoff.\n",
                encoding="utf-8",
            )
            (folder / "ai_summary.md").write_text(
                "The experiment studies strategic ignorance. Dictators avoid "
                "knowing the recipient's payoff to preserve moral wiggle room.\n",
                encoding="utf-8",
            )

            results = search(
                "which paper had dictators avoid knowing the recipient payoff",
                organized_dir=root,
            )

        self.assertTrue(results)
        self.assertEqual(results[0].label, "danaetal2007moralwiggle")
        self.assertIn("dictator", results[0].matched_terms)

    def test_exclude_terms_penalize_neighboring_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "danaetal2007moralwiggle"
            target.mkdir()
            (target / "danaetal2007moralwiggle.md").write_text(
                "---\n"
                "title: Exploiting Moral Wiggle Room\n"
                "authors:\n"
                "  - Jason Dana\n"
                "year: 2007\n"
                "tags:\n"
                "  - moral_wiggle_room\n"
                "---\n\n"
                "Dictators can avoid payoff information.\n",
                encoding="utf-8",
            )
            (target / "ai_summary.md").write_text(
                "Strategic ignorance in a dictator game creates moral wiggle room.\n",
                encoding="utf-8",
            )

            neighbor = root / "survey2020moralbehavior"
            neighbor.mkdir()
            (neighbor / "survey2020moralbehavior.md").write_text(
                "---\n"
                "title: A Survey of Moral Behavior\n"
                "authors:\n"
                "  - Example Author\n"
                "year: 2020\n"
                "tags:\n"
                "  - moral_behavior\n"
                "  - survey\n"
                "---\n\n"
                "A survey of moral behavior and dictator game results.\n",
                encoding="utf-8",
            )
            (neighbor / "ai_summary.md").write_text(
                "This survey reviews moral behavior in dictator games.\n",
                encoding="utf-8",
            )

            results = search(
                "moral dictator game",
                organized_dir=root,
                exclude_keywords=["survey"],
            )

        self.assertTrue(results)
        self.assertEqual(results[0].label, "danaetal2007moralwiggle")

    def test_cli_terms_and_detail_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "danaetal2007moralwiggle"
            folder.mkdir()
            (folder / "danaetal2007moralwiggle.md").write_text(
                "---\n"
                "title: Exploiting Moral Wiggle Room\n"
                "authors:\n"
                "  - Jason Dana\n"
                "year: 2007\n"
                "tags:\n"
                "  - moral_wiggle_room\n"
                "---\n\n"
                "Dictators avoid knowing recipient payoffs.\n",
                encoding="utf-8",
            )
            (folder / "ai_summary.md").write_text(
                "Moral wiggle room is created through strategic ignorance.\n",
                encoding="utf-8",
            )

            old_argv = paper_search.sys.argv
            paper_search.sys.argv = [
                "paper_search.py",
                "--organized-dir",
                str(root),
                "--terms",
                "moral wiggle room",
                "dictator game",
                "--top",
                "3",
                "--detail",
                "1",
            ]
            try:
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = paper_search.main()
            finally:
                paper_search.sys.argv = old_argv

        self.assertEqual(exit_code, 0)
        self.assertIn("danaetal2007moralwiggle", output.getvalue())


if __name__ == "__main__":
    unittest.main()
