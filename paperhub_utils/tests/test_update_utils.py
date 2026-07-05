from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.update_utils import (
    DEFAULT_MANIFEST,
    apply_update_plan,
    build_update_plan,
    changelog_entries_between,
    load_changelog,
    record_current_state,
    sha256_file,
    version_key,
)


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
