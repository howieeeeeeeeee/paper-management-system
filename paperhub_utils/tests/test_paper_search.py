from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import paper_search
from scripts.paper_search import search


class PaperSearchTests(unittest.TestCase):
    def write_paper(
        self,
        root: Path,
        label: str,
        *,
        title: str = "Example Paper",
        metadata_body: str = "General metadata body.",
        summary: str | None = None,
    ) -> Path:
        folder = root / label
        folder.mkdir(parents=True)
        (folder / f"{label}.md").write_text(
            "---\n"
            f"title: {title}\n"
            "authors:\n"
            "  - Example Author\n"
            "year: 2026\n"
            "status: unread\n"
            "interest: medium\n"
            "tags:\n"
            "  - example\n"
            "---\n\n"
            "## Abstract\n\n"
            f"{metadata_body}\n",
            encoding="utf-8",
        )
        if summary is not None:
            (folder / "ai_summary.md").write_text(summary, encoding="utf-8")
        return folder

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

    def test_extra_markdown_only_match_surfaces_parent_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "example2026", summary="Unrelated summary.")
            note = folder / "lecture notes.md"
            note.write_text(
                "The seminar emphasized selective exposure and asymmetric attention.\n",
                encoding="utf-8",
            )

            results = search("selective exposure", organized_dir=root)

        self.assertEqual([result.label for result in results], ["example2026"])
        self.assertGreater(results[0].score_detail["extra_markdown"], 0)
        self.assertEqual(len(results[0].matched_markdown), 1)
        self.assertEqual(results[0].matched_markdown[0].relative_path, "lecture notes.md")

    def test_all_sources_combine_into_one_paper_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(
                root,
                "combined2026",
                metadata_body="The paper studies strategic disclosure.",
                summary="The main mechanism is endogenous attention.",
            )
            (folder / "experiment.md").write_text(
                "The experiment measures costly information acquisition.\n",
                encoding="utf-8",
            )
            (folder / "presentation.md").write_text(
                "The presentation connects information acquisition to welfare.\n",
                encoding="utf-8",
            )

            results = search(
                "strategic disclosure endogenous attention information acquisition",
                organized_dir=root,
            )

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertGreater(result.score_detail["metadata"], 0)
        self.assertGreater(result.score_detail["summary"], 0)
        self.assertGreater(result.score_detail["extra_markdown"], 0)
        self.assertEqual(
            [match.relative_path for match in result.matched_markdown],
            ["experiment.md", "presentation.md"],
        )

    def test_extra_markdown_is_one_capped_scoring_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "duplicates2026")
            for index in range(10):
                (folder / f"note_{index}.md").write_text(
                    "quasiexperimental appears in this supporting note.\n",
                    encoding="utf-8",
                )

            result = search("quasiexperimental", organized_dir=root)[0]

        self.assertEqual(len(result.matched_markdown), 10)
        self.assertEqual(result.score_detail["extra_markdown"], 3.0)

    def test_extra_markdown_exclude_terms_penalize_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "penalty2026")
            (folder / "review.md").write_text(
                "The attention mechanism appears in a broad survey.\n",
                encoding="utf-8",
            )

            baseline = search("attention mechanism", organized_dir=root)[0]
            penalized = search(
                "attention mechanism",
                organized_dir=root,
                exclude_keywords=["survey"],
            )[0]

        self.assertLess(penalized.score, baseline.score)
        self.assertIn("survey", penalized.excluded_terms)
        self.assertIn("survey", penalized.matched_markdown[0].excluded_terms)

    def test_recursive_visible_and_legacy_markdown_are_searched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "recursive2026")
            nested = folder / "seminar" / "Visible Note.MD"
            nested.parent.mkdir()
            nested.write_text("A phosphorescent mechanism appears here.\n", encoding="utf-8")
            (folder / "summary.md").write_text(
                "A legacy discussion of phosphorescent evidence.\n",
                encoding="utf-8",
            )

            result = search("phosphorescent", organized_dir=root)[0]

        self.assertEqual(
            [match.relative_path for match in result.matched_markdown],
            ["seminar/Visible Note.MD", "summary.md"],
        )

    def test_hidden_symlink_non_markdown_and_invalid_utf8_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "ignored2026")
            hidden = folder / ".private" / "hidden.md"
            hidden.parent.mkdir()
            hidden.write_text("concealedtoken\n", encoding="utf-8")
            (folder / "plain.txt").write_text("plaintexttoken\n", encoding="utf-8")
            (folder / "invalid.md").write_bytes(b"invalidtoken\xff")
            outside = root / "outside.md"
            outside.write_text("symlinktoken\n", encoding="utf-8")
            (folder / "linked.md").symlink_to(outside)

            for term in ["concealedtoken", "plaintexttoken", "invalidtoken", "symlinktoken"]:
                self.assertEqual(search(term, organized_dir=root), [])

    def test_unreadable_extra_markdown_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "unreadable2026")
            unreadable = folder / "unreadable.md"
            unreadable.write_text("unreadabletoken\n", encoding="utf-8")
            original_read_text = paper_search.read_text

            def fake_read_text(path: Path) -> str:
                if path == unreadable:
                    return ""
                return original_read_text(path)

            with patch("scripts.paper_search.read_text", side_effect=fake_read_text):
                results = search("unreadabletoken", organized_dir=root)

        self.assertEqual(results, [])

    def test_folder_without_canonical_metadata_is_not_a_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "invalid2026"
            folder.mkdir()
            (folder / "notes.md").write_text("orphanedtoken\n", encoding="utf-8")

            results = search("orphanedtoken", organized_dir=root)

        self.assertEqual(results, [])

    def test_normal_output_labels_each_context_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(
                root,
                "output2026",
                metadata_body="Metadata includes the calibration result.",
                summary=None,
            )
            (folder / "presentation.md").write_text(
                "The calibration result anchors the presentation.\n",
                encoding="utf-8",
            )
            result = search("calibration result", organized_dir=root)[0]
            output = StringIO()
            with redirect_stdout(output):
                paper_search.print_human(
                    [result],
                    detail_count=1,
                    show_score_detail=True,
                    full=False,
                    max_extra_full_chars=60000,
                )

        text = output.getvalue()
        self.assertIn("metadata_excerpt:", text)
        self.assertIn("ai_summary_excerpt:\n     [not available]", text)
        self.assertIn("matched_markdown:", text)
        self.assertIn("presentation.md", text)
        self.assertIn('"extra_markdown"', text)

    def test_full_output_limits_extra_notes_and_excludes_unmatched_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "full2026", summary="Canonical summary body.")
            (folder / "a.md").write_text(
                "targetterm " + "A" * 80,
                encoding="utf-8",
            )
            (folder / "b.md").write_text(
                "targetterm " + "B" * 80,
                encoding="utf-8",
            )
            (folder / "unmatched.md").write_text(
                "This content must not appear in full output.",
                encoding="utf-8",
            )
            result = search("targetterm", organized_dir=root)[0]

            limited = StringIO()
            with redirect_stdout(limited):
                paper_search.print_full_context(result, max_extra_full_chars=40)
            unbounded = StringIO()
            with redirect_stdout(unbounded):
                paper_search.print_full_context(result, max_extra_full_chars=0)

        limited_text = limited.getvalue()
        unbounded_text = unbounded.getvalue()
        self.assertIn("truncated after", limited_text)
        self.assertIn("omitted_after_limit:", limited_text)
        self.assertIn("- b.md", limited_text)
        self.assertIn("file=a.md", unbounded_text)
        self.assertIn("file=b.md", unbounded_text)
        self.assertNotIn("unmatched.md", unbounded_text)
        self.assertNotIn("This content must not appear", unbounded_text)

    def test_json_contains_bounded_matched_markdown_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self.write_paper(root, "json2026")
            (folder / "research.md").write_text(
                "jsonkeyword " + "context " * 80 + "PRIVATE_FULL_TAIL",
                encoding="utf-8",
            )
            old_argv = paper_search.sys.argv
            paper_search.sys.argv = [
                "paper_search.py",
                "--organized-dir",
                str(root),
                "--terms",
                "jsonkeyword",
                "--json",
                "--full",
            ]
            try:
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = paper_search.main()
            finally:
                paper_search.sys.argv = old_argv

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        self.assertIn('"matched_markdown"', text)
        self.assertIn('"relative_path": "research.md"', text)
        self.assertNotIn("PRIVATE_FULL_TAIL", text)

    def test_equal_scores_are_sorted_by_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_paper(root, "zeta2026", metadata_body="equaltoken")
            self.write_paper(root, "alpha2026", metadata_body="equaltoken")

            results = search("equaltoken", organized_dir=root)

        self.assertEqual([result.label for result in results], ["alpha2026", "zeta2026"])


if __name__ == "__main__":
    unittest.main()
