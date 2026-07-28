from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.update_utils import (
    DEFAULT_MANIFEST,
    apply_update_plan,
    build_update_plan,
    changelog_entries_between,
    load_changelog,
    migrate_research_interests,
    record_current_state,
    sha256_file,
    update_config_version,
    version_key,
)

LEGACY_CONFIG_PY = '''"""Config."""

MY_RESEARCH_INTERESTS = """
## Research Fields
- **Labor**: search frictions
"""
'''


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class UpdateUtilsTests(unittest.TestCase):
    def test_protected_config_is_not_in_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            upstream = root / "upstream"
            write(upstream / "paperhub_utils/config/config.json", '{"new": true}\n')
            write(local / "paperhub_utils/config/config.json", '{"mine": true}\n')

            plan = build_update_plan(local, upstream, DEFAULT_MANIFEST, {})

        self.assertNotIn(
            "paperhub_utils/config/config.json",
            {decision.path for decision in plan.decisions},
        )

    def test_unchanged_prompt_can_be_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            upstream = root / "upstream"
            rel = "paperhub_utils/prompts/shared/style.txt"
            write(local / rel, "old prompt\n")
            old_sha = sha256_file(local / rel)
            write(upstream / rel, "new prompt\n")

            plan = build_update_plan(
                local,
                upstream,
                DEFAULT_MANIFEST,
                {"files": {rel: {"sha256": old_sha}}},
            )

        decision = next(item for item in plan.decisions if item.path == rel)
        self.assertEqual(decision.action, "replace")

    def test_custom_prompt_requires_agent_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            upstream = root / "upstream"
            rel = "paperhub_utils/prompts/shared/style.txt"
            write(local / rel, "user customized prompt\n")
            write(upstream / rel, "new upstream prompt\n")

            plan = build_update_plan(local, upstream, DEFAULT_MANIFEST, {})

        decision = next(item for item in plan.decisions if item.path == rel)
        self.assertEqual(decision.action, "needs_agent_merge")

    def test_apply_preserves_prompt_conflict_and_replaces_safe_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            upstream = root / "upstream"
            prompt = "paperhub_utils/prompts/shared/style.txt"
            script = "paperhub_utils/scripts/paper_search.py"
            write(local / prompt, "user prompt\n")
            write(upstream / prompt, "upstream prompt\n")
            write(local / script, "old script\n")
            write(upstream / script, "new script\n")

            plan = build_update_plan(local, upstream, DEFAULT_MANIFEST, {})
            result = apply_update_plan(local, upstream, plan)

            self.assertEqual((local / prompt).read_text(encoding="utf-8"), "user prompt\n")
            self.assertEqual((local / script).read_text(encoding="utf-8"), "new script\n")
            self.assertIn(prompt, result["skipped"])

    def test_record_current_state_preserves_config_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            upstream = root / "upstream"
            rel = "paperhub_utils/scripts/paper_search.py"
            write(local / rel, "script\n")
            write(upstream / rel, "script\n")
            write(
                local / "paperhub_utils/config/config.json",
                '{"schema_version": 1, "use_git": false}\n',
            )

            record_current_state(local, upstream, DEFAULT_MANIFEST, "2099.01.01")

            config = (local / "paperhub_utils/config/config.json").read_text(
                encoding="utf-8"
            )
            self.assertIn('"use_git": false', config)
            self.assertIn('"installed_version": "2099.01.01"', config)

    def test_schema_four_migration_seeds_citations_without_overwriting_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "paperhub_utils/config/config.json",
                '{"schema_version": 3, "citations": {'
                '"resolve_after_organize": true, "preferred_style": "apa"}}\n',
            )

            update_config_version(root)

            config = json.loads(
                (root / "paperhub_utils/config/config.json").read_text(encoding="utf-8")
            )
        self.assertEqual(config["schema_version"], 4)
        self.assertTrue(config["citations"]["resolve_after_organize"])
        self.assertEqual(config["citations"]["preferred_style"], "apa")
        self.assertTrue(config["citations"]["current_agent_search_missing_link"])

    def test_research_interests_are_rescued_before_config_py_is_replaced(self) -> None:
        """The pre-2026.07.28 inline location was update-managed, so an update
        would otherwise overwrite the user's own text."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "paperhub_utils/paperhub/config.py", LEGACY_CONFIG_PY)

            first = migrate_research_interests(root)
            rescued = (root / "paperhub_utils/config/research_interests.md").read_text(
                encoding="utf-8"
            )
            second = migrate_research_interests(root)

        self.assertTrue(first["migrated"])
        self.assertIn("search frictions", rescued)
        self.assertFalse(second["migrated"])

    def test_migration_handles_every_shape_interests_were_stored_in(self) -> None:
        """Onboarding documented a triple-quoted block, but hand-edited copies
        may hold a one-line string. Missing those loses the user's text."""
        cases = {
            'MY_RESEARCH_INTERESTS = """\nlabor\n"""\n': "labor",
            "MY_RESEARCH_INTERESTS = '''\nlabor\n'''\n": "labor",
            'MY_RESEARCH_INTERESTS = "labor, search"\n': "labor, search",
            "MY_RESEARCH_INTERESTS = 'labor, search'\n": "labor, search",
            'MY_RESEARCH_INTERESTS   =   """\nlabor\n"""\n': "labor",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    write(root / "paperhub_utils/paperhub/config.py", source)
                    result = migrate_research_interests(root)
                    rescued = (
                        root / "paperhub_utils/config/research_interests.md"
                    ).read_text(encoding="utf-8")
                self.assertTrue(result["migrated"])
                self.assertEqual(rescued.strip(), expected)

    def test_migration_ignores_empty_and_already_migrated_config(self) -> None:
        for source in (
            'MY_RESEARCH_INTERESTS = ""\n',
            'MY_RESEARCH_INTERESTS = """"""\n',
            "MY_RESEARCH_INTERESTS = _load_research_interests()\n",
        ):
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    write(root / "paperhub_utils/paperhub/config.py", source)
                    result = migrate_research_interests(root)
                    created = (
                        root / "paperhub_utils/config/research_interests.md"
                    ).exists()
                self.assertFalse(result["migrated"])
                self.assertFalse(created)

    def test_migration_does_not_invent_a_file_when_interests_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "paperhub_utils/paperhub/config.py", 'MY_RESEARCH_INTERESTS = ""\n')

            result = migrate_research_interests(root)
            exists = (root / "paperhub_utils/config/research_interests.md").exists()

        self.assertFalse(result["migrated"])
        self.assertFalse(exists)

    def test_migration_never_overwrites_an_existing_protected_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "paperhub_utils/paperhub/config.py", LEGACY_CONFIG_PY)
            target = root / "paperhub_utils/config/research_interests.md"
            write(target, "user's current interests\n")

            result = migrate_research_interests(root)
            preserved = target.read_text(encoding="utf-8")

        self.assertFalse(result["migrated"])
        self.assertEqual(preserved, "user's current interests\n")

    def _verdict_for(self, decisions: list[tuple[str, str | None]]) -> str:
        from scripts.update_utils import FileDecision, UpdatePlan

        return UpdatePlan(
            source_url="u",
            version="2026.01.01.1",
            installed_version=None,
            generated_at="now",
            changelog_entries=[],
            decisions=[
                FileDecision(
                    path=f"f{i}",
                    action=action,
                    reason="",
                    installed_sha256=installed,
                )
                for i, (action, installed) in enumerate(decisions)
            ],
        ).verdict()

    def test_verdict_reports_a_clean_copy(self) -> None:
        self.assertEqual(
            self._verdict_for([("unchanged", "abc"), ("replace", "abc")]), "clean"
        )

    def test_verdict_separates_prompt_drift_from_framework_drift(self) -> None:
        self.assertEqual(
            self._verdict_for([("needs_agent_merge", "abc")]), "prompts-only"
        )
        self.assertEqual(
            self._verdict_for([("needs_agent_merge", "abc"), ("needs_review", "abc")]),
            "framework-modified",
        )

    def test_missing_baseline_is_not_reported_as_clean(self) -> None:
        """Without a baseline a local edit is indistinguishable from upstream
        drift, and every differing file would otherwise silently be replaced."""
        self.assertEqual(self._verdict_for([("replace", None)]), "no-baseline")
        # A brand-new file has no baseline by definition; that is not ambiguity.
        self.assertEqual(
            self._verdict_for([("add", None), ("unchanged", None)]), "clean"
        )

    def test_repo_root_is_the_project_root_the_path_constants_assume(self) -> None:
        """Every path constant is project-root-relative. If this resolves to
        paperhub_utils/ instead, managed files look missing and get "added" into
        a nested paperhub_utils/paperhub_utils/ tree while nothing updates."""
        from scripts.update_utils import CONFIG_PATH, STATE_PATH, repo_root_from_script

        root = repo_root_from_script()
        self.assertTrue(
            (root / "paperhub_utils").is_dir(),
            f"{root} should contain paperhub_utils/, not be it",
        )
        self.assertTrue((root / STATE_PATH).parent.is_dir())
        self.assertTrue((root / CONFIG_PATH).exists())
        self.assertFalse((root / "paperhub_utils/paperhub_utils").exists())

    def test_shipped_manifest_protects_research_interests(self) -> None:
        manifest = json.loads(
            (Path(__file__).resolve().parents[1] / "utility_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn(
            "paperhub_utils/config/research_interests.md", manifest["protected_paths"]
        )

    def test_version_key_orders_same_day_iterations(self) -> None:
        self.assertLess(version_key("2026.07.05"), version_key("2026.07.05.1"))
        self.assertLess(version_key("2026.07.05.1"), version_key("2026.07.05.2"))
        self.assertLess(version_key("2026.07.05.9"), version_key("2026.07.06.1"))

    def test_load_json_changelog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "paperhub_utils/utility_changelog.json",
                '{"schema_version": 1, "entries": {"2026.07.05.1": {"title": "A"}}}\n',
            )
            payload = load_changelog(root)

        self.assertEqual(payload["entries"]["2026.07.05.1"]["title"], "A")

    def test_changelog_entries_between_installed_and_latest(self) -> None:
        changelog = {
            "entries": {
                "2026.07.05.1": {"title": "First"},
                "2026.07.05.2": {"title": "Second"},
                "2026.07.05.3": {"title": "Third"},
            }
        }

        entries = changelog_entries_between(
            changelog,
            installed_version="2026.07.05.1",
            latest_version="2026.07.05.3",
        )

        self.assertEqual([entry["version"] for entry in entries], ["2026.07.05.2", "2026.07.05.3"])

    def test_plan_includes_only_relevant_changelog_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            upstream = root / "upstream"
            rel = "paperhub_utils/scripts/paper_search.py"
            write(local / rel, "script\n")
            write(upstream / rel, "script\n")
            write(
                local / "paperhub_utils/config/config.json",
                '{"paperhub_utils": {"installed_version": "2026.07.05.1"}}\n',
            )
            write(
                upstream / "paperhub_utils/utility_changelog.json",
                '{"entries": {'
                '"2026.07.05.1": {"title": "Old"},'
                '"2026.07.05.2": {"title": "New", "update_kind": "content"}'
                "}}\n",
            )
            manifest = dict(DEFAULT_MANIFEST)
            manifest["version"] = "2026.07.05.2"

            plan = build_update_plan(local, upstream, manifest, {})

        self.assertEqual(len(plan.changelog_entries), 1)
        self.assertEqual(plan.changelog_entries[0]["version"], "2026.07.05.2")


if __name__ == "__main__":
    unittest.main()
