from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cli_workflow.agy import (
    AGY_RESPONSE_BEGIN,
    AGY_RESPONSE_END,
    agy_model_label,
    configure_agy_cli_model,
    extract_agy_response_block,
    validate_agy_cli_run,
)
from cli_workflow.pdf import CLI_WORK_DIR
from config import AGY_CLI_MODEL, AGY_CLI_MODEL_LIST
from enrich import (
    find_artifacts,
    prepare_cli_input as prepare_enrich_cli_input,
)
from paper_summarizer import (
    SUMMARY_MODE_FULL,
    SUMMARY_MODE_METADATA_ONLY,
    cleanup_cli_input,
    prepare_cli_input as prepare_paper_cli_input,
)


def _write_blank_pdf(path: Path, pages: int = 1) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)


class AgyWorkflowTests(unittest.TestCase):
    def test_default_model_comes_from_paperhub_config(self) -> None:
        self.assertEqual(AGY_CLI_MODEL, "Gemini 3.1 Pro (High)")
        self.assertIn(AGY_CLI_MODEL, AGY_CLI_MODEL_LIST)

    def test_settings_update_preserves_existing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "enableTelemetry": False,
                        "model": "Gemini 3.5 Flash (Medium)",
                        "trustedWorkspaces": ["/Users/example"],
                    }
                ),
                encoding="utf-8",
            )

            resolved = configure_agy_cli_model(
                None,
                default_model=AGY_CLI_MODEL,
                allowed_models=AGY_CLI_MODEL_LIST,
                settings_path=settings,
            )

            loaded = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(resolved, "Gemini 3.1 Pro (High)")
        self.assertEqual(loaded["model"], "Gemini 3.1 Pro (High)")
        self.assertEqual(loaded["trustedWorkspaces"], ["/Users/example"])
        self.assertIs(loaded["enableTelemetry"], False)

    def test_explicit_model_validates_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"

            resolved = configure_agy_cli_model(
                "Gemini 3.5 Flash (Medium)",
                default_model=AGY_CLI_MODEL,
                allowed_models=AGY_CLI_MODEL_LIST,
                settings_path=settings,
            )

            loaded = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(resolved, "Gemini 3.5 Flash (Medium)")
        self.assertEqual(loaded["model"], "Gemini 3.5 Flash (Medium)")

    def test_invalid_model_refuses_before_mutating_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            original = {"model": "Gemini 3.1 Pro (High)", "other": "kept"}
            settings.write_text(json.dumps(original), encoding="utf-8")

            with self.assertRaises(ValueError):
                configure_agy_cli_model(
                    "Not A Real Model",
                    default_model=AGY_CLI_MODEL,
                    allowed_models=AGY_CLI_MODEL_LIST,
                    settings_path=settings,
                )

            loaded = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(loaded, original)

    def test_extract_response_block_ignores_noisy_stdout(self) -> None:
        stdout = (
            "I will inspect the attached file first.\n"
            f"{AGY_RESPONSE_BEGIN}\n"
            "# paper_label\n"
            "sample2026paper\n"
            f"{AGY_RESPONSE_END}\n"
            "Done."
        )

        self.assertEqual(
            extract_agy_response_block(stdout),
            "# paper_label\nsample2026paper",
        )

    def test_validate_agy_run_catches_missing_sentinel_and_timeout(self) -> None:
        problems = validate_agy_cli_run(
            stdout_text="Error: timed out waiting for response"
        )

        self.assertTrue(any("timed out" in problem for problem in problems))
        self.assertTrue(any(AGY_RESPONSE_BEGIN in problem for problem in problems))

    def test_agy_model_label(self) -> None:
        self.assertEqual(
            agy_model_label("Gemini 3.1 Pro (High)"),
            "Gemini 3.1 Pro (High) (Agy CLI)",
        )

    def test_prepare_full_mode_agy_input(self) -> None:
        with tempfile.TemporaryDirectory(dir=CLI_WORK_DIR) as tmp, tempfile.TemporaryDirectory() as settings_tmp:
            settings_path = Path(settings_tmp) / "settings.json"
            previous = os.environ.get("AGY_CLI_SETTINGS_PATH")
            os.environ["AGY_CLI_SETTINGS_PATH"] = str(settings_path)
            try:
                pdf_path = Path(tmp) / "full_mode.pdf"
                _write_blank_pdf(pdf_path)

                result = prepare_paper_cli_input(
                    pdf_path=pdf_path,
                    summary_mode=SUMMARY_MODE_FULL,
                    external_cli_engine="agy-cli",
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["external_cli_engine"], "agy-cli")
                self.assertEqual(result["summary_mode"], SUMMARY_MODE_FULL)
                self.assertEqual(result["pdf_for_ai_agy_path"], str(pdf_path.resolve()))
                self.assertEqual(result["agy_model_label"], "Gemini 3.1 Pro (High) (Agy CLI)")
                self.assertEqual(
                    json.loads(settings_path.read_text(encoding="utf-8"))["model"],
                    "Gemini 3.1 Pro (High)",
                )
                self.assertNotIn("pages_sent", result)
                self.assertTrue(cleanup_cli_input(Path(result["cleanup_dir"])))
            finally:
                _restore_env("AGY_CLI_SETTINGS_PATH", previous)

    def test_prepare_metadata_only_mode_agy_input_uses_first_pages_pdf(self) -> None:
        with tempfile.TemporaryDirectory(dir=CLI_WORK_DIR) as tmp, tempfile.TemporaryDirectory() as settings_tmp:
            settings_path = Path(settings_tmp) / "settings.json"
            previous = os.environ.get("AGY_CLI_SETTINGS_PATH")
            os.environ["AGY_CLI_SETTINGS_PATH"] = str(settings_path)
            try:
                pdf_path = Path(tmp) / "metadata_mode.pdf"
                _write_blank_pdf(pdf_path, pages=3)

                result = prepare_paper_cli_input(
                    pdf_path=pdf_path,
                    summary_mode=SUMMARY_MODE_METADATA_ONLY,
                    external_cli_engine="agy-cli",
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["external_cli_engine"], "agy-cli")
                self.assertEqual(result["summary_mode"], SUMMARY_MODE_METADATA_ONLY)
                self.assertEqual(result["pages_sent"], 2)
                self.assertEqual(result["total_pdf_pages"], 3)
                self.assertNotEqual(result["pdf_for_ai_agy_path"], str(pdf_path.resolve()))
                self.assertTrue(Path(result["pdf_for_ai_agy_path"]).exists())
                self.assertTrue(cleanup_cli_input(Path(result["cleanup_dir"])))
            finally:
                _restore_env("AGY_CLI_SETTINGS_PATH", previous)

    def test_prepare_enrich_mode_agy_input(self) -> None:
        with tempfile.TemporaryDirectory(dir=CLI_WORK_DIR) as tmp, tempfile.TemporaryDirectory() as settings_tmp:
            settings_path = Path(settings_tmp) / "settings.json"
            previous = os.environ.get("AGY_CLI_SETTINGS_PATH")
            os.environ["AGY_CLI_SETTINGS_PATH"] = str(settings_path)
            try:
                output_dir = Path(tmp) / "organized"
                folder = output_dir / "sample2026paper"
                folder.mkdir(parents=True)
                (folder / "sample2026paper.md").write_text(
                    "---\ntitle: Sample\n"
                    "authors:\n  - Example Author\n"
                    "year: 2026\njournal: Test\n"
                    "tags:\n  - testing\ncontributions:\n---\n\n"
                    "## Abstract\n[Abstract not found in provided pages]\n",
                    encoding="utf-8",
                )
                pdf_path = folder / "paper.pdf"
                _write_blank_pdf(pdf_path)

                art = find_artifacts("sample2026paper", output_dir)
                result = prepare_enrich_cli_input(
                    art,
                    include_summary=True,
                    additional_instruction="",
                    external_cli_engine="agy-cli",
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["external_cli_engine"], "agy-cli")
                self.assertEqual(result["mode"], "enrich")
                self.assertEqual(result["pdf_for_ai_agy_path"], str(pdf_path.resolve()))
                self.assertEqual(result["agy_model_label"], "Gemini 3.1 Pro (High) (Agy CLI)")
                self.assertFalse(result["past_summary_used"])
                self.assertTrue(cleanup_cli_input(Path(result["cleanup_dir"])))
            finally:
                _restore_env("AGY_CLI_SETTINGS_PATH", previous)
                shutil.rmtree(Path(tmp), ignore_errors=True)


def _restore_env(key: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


if __name__ == "__main__":
    unittest.main()
