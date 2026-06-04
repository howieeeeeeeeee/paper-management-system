from __future__ import annotations

import unittest

from config import DEFAULT_MODEL
from paper_summarizer import (
    build_local_pdf_text_prompt,
    build_parsed_pdf_fallback_prompt,
    extract_text_from_file_annotations,
    resolve_pdf_input_config,
    resolve_model_config,
)


class OpenRouterPdfFallbackTests(unittest.TestCase):
    def test_qwen_default_uses_text_extraction_and_reasoning_effort(self) -> None:
        qwen = resolve_model_config("qwen/qwen3.7-max")
        pdf_input = resolve_pdf_input_config(qwen)

        self.assertEqual(DEFAULT_MODEL["model_id"], "qwen/qwen3.7-max")
        self.assertEqual(qwen.get("reasoning"), {"effort": "medium", "exclude": True})
        self.assertEqual(pdf_input["mode"], "text_extraction")
        self.assertEqual(pdf_input["extractor"], "pymupdf4llm")
        self.assertEqual(DEFAULT_MODEL["pdf_input"], "text_extraction")

    def test_configured_models_resolve_pdf_input_strategy(self) -> None:
        deepseek = resolve_model_config("deepseek/deepseek-v4-pro")
        kimi = resolve_model_config("moonshotai/kimi-k2.6")
        gemini = resolve_model_config("google/gemini-3.1-pro-preview")

        self.assertEqual(deepseek.get("reasoning"), {"effort": "medium", "exclude": True})
        self.assertEqual(resolve_pdf_input_config(deepseek)["mode"], "text_extraction")
        self.assertEqual(resolve_pdf_input_config(kimi)["mode"], "openrouter_file_parser")
        self.assertEqual(resolve_pdf_input_config(gemini)["mode"], "openrouter_file_parser")

    def test_extracts_text_from_error_file_annotations(self) -> None:
        error_body = {
            "error": {
                "metadata": {
                    "file_annotations": [
                        {
                            "type": "file",
                            "file": {
                                "content": [
                                    {"type": "text", "text": "<file name=\"paper.pdf\">"},
                                    {"type": "text", "text": "Paper title\nAbstract text"},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": "data:image/png;base64,..."},
                                    },
                                ]
                            },
                        }
                    ]
                }
            }
        }

        self.assertEqual(
            extract_text_from_file_annotations(error_body),
            "<file name=\"paper.pdf\">\n\nPaper title\nAbstract text",
        )

    def test_fallback_prompt_wraps_parsed_text_and_original_prompt(self) -> None:
        prompt = build_parsed_pdf_fallback_prompt(
            "Return # paper_label.",
            "Journal title\nPaper body",
        )

        self.assertIn(
            "<paper_pdf_text>\nJournal title\nPaper body\n</paper_pdf_text>",
            prompt,
        )
        self.assertTrue(prompt.endswith("Return # paper_label."))

    def test_local_pdf_text_prompt_names_extractor(self) -> None:
        prompt = build_local_pdf_text_prompt(
            "Return # paper_label.",
            "Markdown paper body",
            "pymupdf4llm",
        )

        self.assertIn("converted to Markdown locally with pymupdf4llm", prompt)
        self.assertIn("<paper_pdf_text>\nMarkdown paper body\n</paper_pdf_text>", prompt)
        self.assertTrue(prompt.endswith("Return # paper_label."))


if __name__ == "__main__":
    unittest.main()
