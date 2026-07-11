from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperhub.cli_workflow.codex import (
    CODEX_RESPONSE_BEGIN,
    CODEX_RESPONSE_END,
    codex_model_label,
    extract_codex_response_block,
    resolve_codex_cli_model,
    resolve_codex_cli_settings,
    validate_codex_cli_run,
)
from paperhub.cli_workflow.pdf import CLI_WORK_DIR
from paperhub.config import (
    CODEX_CLI_MODEL,
    CODEX_CLI_MODEL_LIST,
    CODEX_CLI_MODEL_REASONING_PAIRS,
    CODEX_CLI_REASONING_EFFORT,
    CODEX_CLI_REASONING_EFFORT_LIST,
    CODEX_CLI_YOLO,
)
from scripts.enrich import (
    find_artifacts,
    prepare_cli_input as prepare_enrich_cli_input,
)
from scripts.paper_summarizer import (
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


class CodexWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        CLI_WORK_DIR.mkdir(parents=True, exist_ok=True)

    def test_default_model_comes_from_paperhub_config(self) -> None:
        self.assertEqual(CODEX_CLI_MODEL, "gpt-5.6-sol")
        self.assertIn(CODEX_CLI_REASONING_EFFORT, CODEX_CLI_REASONING_EFFORT_LIST)
        self.assertTrue(CODEX_CLI_YOLO)
        self.assertEqual(
            CODEX_CLI_MODEL_LIST,
            tuple(dict.fromkeys(model for model, _ in CODEX_CLI_MODEL_REASONING_PAIRS)),
        )
        self.assertIn(CODEX_CLI_MODEL, CODEX_CLI_MODEL_LIST)
        self.assertIn(
            (CODEX_CLI_MODEL, CODEX_CLI_REASONING_EFFORT),
            CODEX_CLI_MODEL_REASONING_PAIRS,
        )

    def test_invalid_model_refuses(self) -> None:
        with self.assertRaises(ValueError):
            resolve_codex_cli_model(
                "gpt-5.4",
                default_model=CODEX_CLI_MODEL,
                allowed_models=CODEX_CLI_MODEL_LIST,
            )

    def test_invalid_reasoning_pair_refuses(self) -> None:
        with self.assertRaises(ValueError):
            resolve_codex_cli_settings(
                "gpt-5.5",
                "minimal",
                default_model=CODEX_CLI_MODEL,
                default_reasoning_effort=CODEX_CLI_REASONING_EFFORT,
                allowed_model_reasoning_pairs=CODEX_CLI_MODEL_REASONING_PAIRS,
            )

    def test_extract_response_block_ignores_noisy_stdout(self) -> None:
        stdout = (
            "Codex progress text\n"
            f"{CODEX_RESPONSE_BEGIN}\n"
            "# paper_label\n"
            "sample2026paper\n"
            f"{CODEX_RESPONSE_END}\n"
            "Done."
        )

        self.assertEqual(
            extract_codex_response_block(stdout),
            "# paper_label\nsample2026paper",
        )

    def test_validate_codex_run_catches_missing_sentinel(self) -> None:
        problems = validate_codex_cli_run(stdout_text="no sentinels here")

        self.assertTrue(any(CODEX_RESPONSE_BEGIN in problem for problem in problems))

    def test_validate_codex_run_catches_stderr_failure_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stderr = Path(tmp) / "codex_stderr.txt"
            stderr.write_text("Permission denied while reading paper.pdf\n", encoding="utf-8")
            stdout = (
                f"{CODEX_RESPONSE_BEGIN}\n"
                "# paper_label\nsample2026paper\n"
                f"{CODEX_RESPONSE_END}\n"
            )

            problems = validate_codex_cli_run(stdout_text=stdout, stderr_path=stderr)

        self.assertTrue(any("permission denied" in p for p in problems))

    def test_codex_model_label(self) -> None:
        self.assertEqual(
            codex_model_label("gpt-5.5", "high"),
            "gpt-5.5 (high reasoning) (Codex CLI)",
        )

    def test_prepare_full_mode_codex_input(self) -> None:
        with tempfile.TemporaryDirectory(dir=CLI_WORK_DIR) as tmp:
            pdf_path = Path(tmp) / "full_mode.pdf"
            _write_blank_pdf(pdf_path)

            result = prepare_paper_cli_input(
                pdf_path=pdf_path,
                summary_mode=SUMMARY_MODE_FULL,
                external_cli_engine="codex-cli",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["external_cli_engine"], "codex-cli")
            self.assertEqual(result["summary_mode"], SUMMARY_MODE_FULL)
            self.assertEqual(result["pdf_for_ai_codex_path"], str(pdf_path.resolve()))
            self.assertEqual(result["codex_cli_model"], CODEX_CLI_MODEL)
            self.assertEqual(
                result["codex_cli_reasoning_effort"],
                CODEX_CLI_REASONING_EFFORT,
            )
            self.assertTrue(result["codex_cli_yolo"])
            self.assertEqual(result["codex_cli_web_search"], "disabled")
            self.assertEqual(
                result["codex_model_label"],
                codex_model_label(CODEX_CLI_MODEL, CODEX_CLI_REASONING_EFFORT),
            )
            self.assertEqual(result["response_begin"], CODEX_RESPONSE_BEGIN)
            self.assertEqual(result["response_end"], CODEX_RESPONSE_END)
            self.assertNotIn("pages_sent", result)
            self.assertTrue(cleanup_cli_input(Path(result["cleanup_dir"])))

    def test_prepare_metadata_only_mode_codex_input_uses_first_pages_pdf(self) -> None:
        with tempfile.TemporaryDirectory(dir=CLI_WORK_DIR) as tmp:
            pdf_path = Path(tmp) / "metadata_mode.pdf"
            _write_blank_pdf(pdf_path, pages=3)

            result = prepare_paper_cli_input(
                pdf_path=pdf_path,
                summary_mode=SUMMARY_MODE_METADATA_ONLY,
                external_cli_engine="codex-cli",
                codex_reasoning_effort="high",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["external_cli_engine"], "codex-cli")
            self.assertEqual(result["summary_mode"], SUMMARY_MODE_METADATA_ONLY)
            self.assertEqual(result["pages_sent"], 2)
            self.assertEqual(result["total_pdf_pages"], 3)
            self.assertEqual(result["codex_cli_reasoning_effort"], "high")
            self.assertNotEqual(result["pdf_for_ai_codex_path"], str(pdf_path.resolve()))
            self.assertTrue(Path(result["pdf_for_ai_codex_path"]).exists())
            self.assertTrue(cleanup_cli_input(Path(result["cleanup_dir"])))

    def test_prepare_enrich_mode_codex_input(self) -> None:
        with tempfile.TemporaryDirectory(dir=CLI_WORK_DIR) as tmp:
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
                external_cli_engine="codex-cli",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["external_cli_engine"], "codex-cli")
            self.assertEqual(result["mode"], "enrich")
            self.assertEqual(result["pdf_for_ai_codex_path"], str(pdf_path.resolve()))
            self.assertEqual(result["codex_cli_model"], CODEX_CLI_MODEL)
            self.assertEqual(
                result["codex_cli_reasoning_effort"],
                CODEX_CLI_REASONING_EFFORT,
            )
            self.assertTrue(result["codex_cli_yolo"])
            self.assertEqual(
                result["codex_model_label"],
                codex_model_label(CODEX_CLI_MODEL, CODEX_CLI_REASONING_EFFORT),
            )
            self.assertFalse(result["past_summary_used"])
            self.assertTrue(cleanup_cli_input(Path(result["cleanup_dir"])))


if __name__ == "__main__":
    unittest.main()
