from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PAPERHUB_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = (
    PAPERHUB_ROOT
    / ".claude"
    / "skills"
    / "paper-organizer"
    / "update-label-format"
    / "label_migration.py"
)
SPEC = importlib.util.spec_from_file_location("paperhub_label_migration_tool", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
TOOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TOOL
SPEC.loader.exec_module(TOOL)


class LabelMigrationToolTests(unittest.TestCase):
    def test_safe_label_validation(self) -> None:
        self.assertEqual(TOOL.validate_label("Huynh_etal2026LLMCooperation"), "Huynh_etal2026LLMCooperation")
        for unsafe in ("../paper", "paper-label", "paper label", "Köbis2025AI"):
            with self.assertRaises(TOOL.MigrationError):
                TOOL.validate_label(unsafe)

    def test_synthetic_manifest_apply_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary) / "Vault"
            paperhub = vault / "PaperHub"
            organized = paperhub / "organized"
            source = organized / "foo2020topic"
            source.mkdir(parents=True)
            metadata = source / "foo2020topic.md"
            metadata.write_text(
                """---
title: Topic Paper
authors:
  - Alice Foo
year: 2020
created: 2026-01-01
---

[[foo2020topic|Back]]
""",
                encoding="utf-8",
            )
            (source / "ai_summary.md").write_text(
                "[[foo2020topic|Back to Metadata]]\n",
                encoding="utf-8",
            )
            pdf = source / "paper.pdf"
            pdf.write_bytes(b"unchanged-pdf")
            external = vault / "Topic.canvas"
            external.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "node-1",
                                "type": "file",
                                "file": "PaperHub/organized/foo2020topic/foo2020topic.md",
                                "x": 0,
                                "y": 0,
                                "width": 100,
                                "height": 100,
                            }
                        ],
                        "edges": [],
                    }
                ),
                encoding="utf-8",
            )
            work = paperhub / ".paperhub_tmp" / "migration"
            paths = TOOL.Paths(paperhub, vault, organized, work)

            prepared = TOOL.make_batches(paths, 1, True)
            self.assertEqual(prepared["record_count"], 1)
            input_path = work / "batches" / "batch_01.input.jsonl"
            output_path = work / "batches" / "batch_01.output.jsonl"
            row = TOOL.read_jsonl(input_path)[0]
            row.update(
                {
                    "action": "rename",
                    "proposed_label": "Foo2020Topic",
                    "confidence": "high",
                    "notes": "Synthetic test.",
                    "review_flags": [],
                }
            )
            TOOL.atomic_jsonl(output_path, [row])

            merged = TOOL.merge_command(paths, True)
            self.assertEqual(merged["rename_count"], 1)
            self.assertEqual(TOOL.apply_command(paths, False)["would_apply"], True)
            applied = TOOL.apply_command(paths, True)
            self.assertEqual(applied["verification"]["status"], "pass")

            target = organized / "Foo2020Topic"
            self.assertTrue((target / "Foo2020Topic.md").is_file())
            self.assertEqual((target / "paper.pdf").read_bytes(), b"unchanged-pdf")
            self.assertIn("Foo2020Topic", (target / "ai_summary.md").read_text(encoding="utf-8"))
            self.assertIn("Foo2020Topic", external.read_text(encoding="utf-8"))
            self.assertEqual(TOOL.verify_command(paths, True)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
