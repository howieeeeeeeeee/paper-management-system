from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


PAPERHUB_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PAPERHUB_ROOT
    / ".claude/skills/paperhub-obsidian/scripts/sync_upstream.py"
)
SPEC = importlib.util.spec_from_file_location("paperhub_obsidian_sync", SCRIPT_PATH)
assert SPEC and SPEC.loader
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_source(root: Path, skills: tuple[str, ...] = ("alpha",)) -> Path:
    source = root / "source"
    write(source / "LICENSE", "MIT fixture\n")
    for name in skills:
        write(
            source / f"skills/{name}/SKILL.md",
            f"---\nname: {name}\ndescription: Fixture skill.\n---\n\n# {name}\n",
        )
    write(source / f"skills/{skills[0]}/references/DETAILS.md", "Details\n")
    return source


class ObsidianUpstreamSyncTests(unittest.TestCase):
    def test_initial_import_is_exact_and_records_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            source = make_source(root)

            report = sync.apply_snapshot(skill, source, "a" * 40)
            lock = json.loads((skill / "upstream-lock.json").read_text())

            self.assertTrue(report["applied"])
            self.assertEqual(lock["commit"], "a" * 40)
            self.assertEqual(lock["skills"], ["alpha"])
            self.assertEqual(
                (skill / "skills/alpha/SKILL.md").read_bytes(),
                (source / "skills/alpha/SKILL.md").read_bytes(),
            )
            self.assertEqual(
                lock["files"]["skills/alpha/SKILL.md"],
                sync.sha256_file(source / "skills/alpha/SKILL.md"),
            )

    def test_no_change_check_reports_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            source = make_source(root)
            sync.apply_snapshot(skill, source, "a" * 40)

            report = sync.build_report(skill, source, "a" * 40)

            self.assertEqual(report["status"], "current")
            self.assertFalse(report["added_files"])
            self.assertFalse(report["modified_files"])
            self.assertFalse(report["removed_files"])

    def test_content_update_is_detected_and_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            source = make_source(root)
            sync.apply_snapshot(skill, source, "a" * 40)
            write(source / "skills/alpha/SKILL.md", "updated upstream\n")

            report = sync.build_report(skill, source, "b" * 40)
            sync.apply_snapshot(skill, source, "b" * 40)

            self.assertEqual(report["status"], "update_available")
            self.assertEqual(report["modified_files"], ["skills/alpha/SKILL.md"])
            self.assertEqual(
                (skill / "skills/alpha/SKILL.md").read_text(),
                "updated upstream\n",
            )

    def test_local_drift_refuses_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            source = make_source(root)
            sync.apply_snapshot(skill, source, "a" * 40)
            write(skill / "skills/alpha/SKILL.md", "local customization\n")

            report = sync.build_report(skill, source, "b" * 40)

            self.assertEqual(report["status"], "local_drift")
            self.assertIn("skills/alpha/SKILL.md", report["local_drift"])
            with self.assertRaises(sync.SyncError):
                sync.apply_snapshot(skill, source, "b" * 40)

    def test_structural_change_requires_explicit_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            source = make_source(root)
            sync.apply_snapshot(skill, source, "a" * 40)
            make_source(root, ("alpha", "beta"))

            report = sync.build_report(skill, source, "b" * 40)

            self.assertTrue(report["structural"])
            self.assertEqual(report["added_skills"], ["beta"])
            with self.assertRaises(sync.SyncError):
                sync.apply_snapshot(skill, source, "b" * 40)
            sync.apply_snapshot(
                skill,
                source,
                "b" * 40,
                allow_structural=True,
            )
            self.assertTrue((skill / "skills/beta/SKILL.md").is_file())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            os.symlink(
                source / "skills/alpha/SKILL.md",
                source / "skills/alpha/references/linked.md",
            )

            with self.assertRaises(sync.SyncError):
                sync.validate_source_tree(source)

    def test_maintainer_gate_requires_private_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(sync.SyncError):
                sync.require_maintainer(root)
            write(
                root / ".claude/skills/public-template-sync/SKILL.md",
                "maintainer marker\n",
            )
            sync.require_maintainer(root)

    def test_apply_preserves_router_and_update_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skill"
            source = make_source(root)
            preserved = {
                "SKILL.md": "router\n",
                "UPSTREAM.md": "workflow\n",
                "scripts/sync_upstream.py": "script\n",
                "agents/openai.yaml": "interface: {}\n",
            }
            for relative, content in preserved.items():
                write(skill / relative, content)

            sync.apply_snapshot(skill, source, "a" * 40)

            for relative, content in preserved.items():
                self.assertEqual((skill / relative).read_text(), content)


class ObsidianRouterIntegrityTests(unittest.TestCase):
    def test_router_targets_and_upstream_references_exist(self) -> None:
        skill_root = PAPERHUB_ROOT / ".claude/skills/paperhub-obsidian"
        expected = [
            "skills/obsidian-markdown/SKILL.md",
            "skills/obsidian-bases/SKILL.md",
            "skills/json-canvas/SKILL.md",
            "skills/obsidian-cli/SKILL.md",
            "skills/defuddle/SKILL.md",
            "UPSTREAM.md",
            "LICENSE",
            "upstream-lock.json",
        ]
        for relative in expected:
            self.assertTrue((skill_root / relative).is_file(), relative)

        references = [
            "skills/obsidian-markdown/references/CALLOUTS.md",
            "skills/obsidian-markdown/references/EMBEDS.md",
            "skills/obsidian-markdown/references/PROPERTIES.md",
            "skills/obsidian-bases/references/FUNCTIONS_REFERENCE.md",
            "skills/json-canvas/references/EXAMPLES.md",
        ]
        for relative in references:
            self.assertTrue((skill_root / relative).is_file(), relative)

    def test_router_keeps_paper_and_optional_tool_boundaries(self) -> None:
        router = (
            PAPERHUB_ROOT
            / ".claude/skills/paperhub-obsidian/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Never route a paper", router)
        self.assertIn("URL through it", router)
        self.assertIn("paper-organizer", router)
        self.assertIn("never install its global npm dependency", router)
        self.assertIn("run `obsidian help`", router)


if __name__ == "__main__":
    unittest.main()
