from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from paperhub.link_ingestion import (
    create_link_prompt,
    load_link_context,
    materialize_public_pdf_sidecar,
    organize_link_response,
)
from scripts.paper_organizer import (
    _generate_agy_link,
    _generate_codex_link,
    _preflight_link_batch,
    prepare_link_input,
    run_managed_link_batch,
    run_parallel_link_generation,
    save_raw_link_content,
)
from scripts import paper_summarizer as legacy
from scripts.paper_summarizer import (
    apply_verified_sidecar_metadata,
    call_openrouter_prompt_api,
    load_verified_sidecar_metadata,
)


def _write_context(
    path: Path,
    *,
    public_pdf_path: str | None = None,
    canonical_url: str = "https://doi.org/10.1234/test.1",
    title: str = "Verified Title",
    route: str = "link-metadata",
    requested_mode: str = "metadata-only",
) -> None:
    machine = {
        "input_url": "https://example.com/input",
        "canonical_url": canonical_url,
        "metadata": {
            "title": title,
            "authors": ["Ada Example"],
            "year": 2025,
            "journal": "Verified Journal",
            "doi": "10.1234/test.1",
            "abstract": "Verified abstract text.",
        },
        "missing_fields": [],
        "fallback_label": "unresolved12345678",
        "public_pdf_path": public_pdf_path,
        "route": route,
        "requested_mode": requested_mode,
        "summary_skipped": False,
    }
    path.write_text(
        "# PaperHub Link Context\n\n"
        "## Coding-Agent Additions\n[None]\n\n"
        "## Machine-Readable Context\n```json\n"
        + json.dumps(machine, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


class LinkIngestionTests(unittest.TestCase):
    def test_prompt_is_offline_and_link_specific(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "source_context.txt"
            _write_context(context)
            prompt = create_link_prompt(context)
        self.assertIn("Do not browse, search, fetch", prompt)
        self.assertIn("<paperhub_link_context>", prompt)
        self.assertNotIn("## Related Papers", prompt)

    def test_coding_agent_additions_are_authoritative(self) -> None:
        additions = {
            "canonical_url": "https://doi.org/10.1234/added",
            "metadata": {
                "title": "Verified Added Title",
                "authors": ["Ada Example"],
                "year": 2026,
                "journal": "Journal of Tests",
                "doi": "10.1234/added",
                "abstract": "Verified added abstract.",
            },
            "source_urls": ["https://example.com/public-record"],
        }
        machine = {
            "input_url": "https://example.com/input",
            "canonical_url": "https://example.com/input",
            "metadata": {
                "title": "Unhelpful Download Filename.pdf",
                "authors": [],
                "year": None,
                "journal": None,
                "doi": None,
                "abstract": None,
            },
            "missing_fields": ["title", "authors", "year", "journal", "abstract"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "source_context.txt"
            context.write_text(
                "# Context\n\n## Coding-Agent Additions\n```json\n"
                + json.dumps(additions, indent=2)
                + "\n```\n\n## Machine-Readable Context\n```json\n"
                + json.dumps(machine, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            _, loaded = load_link_context(context)
        self.assertEqual(loaded["canonical_url"], additions["canonical_url"])
        self.assertEqual(loaded["metadata"]["title"], "Verified Added Title")
        self.assertEqual(loaded["missing_fields"], [])

    def test_public_pdf_sidecar_is_structured_and_authoritative(self) -> None:
        generated = """---
title: Wrong Title
authors:
  - Wrong Author
year: 1999
journal: Wrong Journal
link: https://wrong.example
status:
  - initiated
tags:
  - testing
created: 2026-01-01
interest: none
importance: none
contributions:
---

# Wrong Title

## Abstract
Wrong abstract.

## Reflections
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "public_paper.pdf"
            pdf.write_bytes(b"%PDF-1.4\nfixture")
            context = root / "source_context.txt"
            _write_context(
                context,
                public_pdf_path=str(pdf),
                route="pdf-pending-mode",
                requested_mode="auto",
            )
            sidecar = materialize_public_pdf_sidecar(context, route="pdf-metadata")
            verified = load_verified_sidecar_metadata(pdf)
            rendered = apply_verified_sidecar_metadata(generated, verified)
            frontmatter = yaml.safe_load(rendered.split("---\n", 2)[1])
        self.assertEqual(sidecar.name, "public_paper.citation.md")
        self.assertEqual(verified["route"], "pdf-metadata")
        self.assertEqual(frontmatter["title"], "Verified Title")
        self.assertEqual(frontmatter["authors"], ["Ada Example"])
        self.assertEqual(frontmatter["link"], "https://doi.org/10.1234/test.1")
        self.assertIn("Verified abstract text.", rendered)
        self.assertNotIn("Wrong abstract.", rendered)

    def test_preflight_splits_pure_links_duplicates_and_public_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contexts = []
            first = root / "first.txt"
            duplicate = root / "duplicate.txt"
            pdf_context = root / "pdf.txt"
            public_pdf = root / "public.pdf"
            public_pdf.write_bytes(b"%PDF-1.4\nfixture")
            _write_context(first, canonical_url="https://doi.org/10.1234/one")
            _write_context(duplicate, canonical_url="10.1234/one")
            _write_context(
                pdf_context,
                canonical_url="https://doi.org/10.1234/two",
                public_pdf_path=str(public_pdf),
                route="pdf-pending-mode",
                requested_mode="auto",
            )
            contexts.extend([first, duplicate, pdf_context])
            results, jobs = _preflight_link_batch(
                contexts,
                output_dir=root / "organized",
                pdf_mode="full",
            )
            sidecar = public_pdf.with_name("public.citation.md")
            self.assertTrue(sidecar.exists())
        self.assertEqual([job["index"] for job in jobs], [0])
        self.assertTrue(results[1]["duplicate_in_batch"])
        self.assertEqual(results[2]["route"], "pdf-full")
        self.assertEqual(results[2]["summary_mode"], "full")

    def test_pending_public_pdf_requires_one_mode_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public_pdf = root / "public.pdf"
            public_pdf.write_bytes(b"%PDF-1.4\nfixture")
            context = root / "context.txt"
            _write_context(
                context,
                public_pdf_path=str(public_pdf),
                route="pdf-pending-mode",
                requested_mode="auto",
            )
            results, jobs = _preflight_link_batch(
                [context],
                output_dir=root / "organized",
                pdf_mode=None,
            )
        self.assertEqual(jobs, [])
        self.assertTrue(results[0]["needs_pdf_mode"])
        self.assertEqual(results[0]["error_type"], "PdfModeRequired")

    def test_parallel_generation_overlaps_workers(self) -> None:
        active = 0
        max_active = 0
        lock = threading.Lock()

        def generator(job):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return {"success": True, "index": job["index"]}

        generated = run_parallel_link_generation(
            [{"index": index} for index in range(4)],
            4,
            generator,
        )
        self.assertEqual(sorted(generated), [0, 1, 2, 3])
        self.assertGreater(max_active, 1)

    @patch("scripts.paper_organizer._generate_openrouter_link")
    @patch("scripts.paper_organizer.legacy.resolve_model_config")
    @patch("scripts.paper_organizer.legacy.get_api_key")
    def test_managed_batch_finishes_partial_failure_in_input_order(
        self,
        get_api_key,
        resolve_model_config,
        generate,
    ) -> None:
        get_api_key.return_value = "test-key"
        resolve_model_config.return_value = {
            "model_id": "test/model",
            "provider": {},
            "reasoning": None,
        }

        def generated(job, **_kwargs):
            if job["index"] == 1:
                return {"success": False, "error": "fixture failure"}
            index = job["index"]
            return {
                "success": True,
                "model_label": "test/model",
                "usage": {"total_tokens": 10 + index},
                "generation_seconds": 0.01,
                "content": (
                    f"# paper_label\nfixture{index}2026paper\n# metadata\n"
                    "---\ntitle: Fixture\ntags:\n  - testing\n---\n\n"
                    "# Fixture\n\n## Abstract\nFixture abstract.\n"
                ),
            }

        generate.side_effect = generated
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contexts = []
            for index in range(3):
                context = root / f"context_{index}.txt"
                _write_context(
                    context,
                    canonical_url=f"https://doi.org/10.1234/batch{index}",
                    title=f"Verified Title {index}",
                )
                contexts.append(context)
            args = SimpleNamespace(
                output_dir=str(root / "organized"),
                pdf_mode=None,
                verbose=False,
                engine="openrouter",
                model=None,
                agy_model=None,
                codex_model=None,
                codex_reasoning_effort=None,
                instruction="",
                max_workers=3,
            )
            result = run_managed_link_batch(args, contexts)
            folders = sorted(path.name for path in (root / "organized").iterdir())
        self.assertFalse(result["success"])
        self.assertEqual(result["failed"], 1)
        self.assertEqual([item["input_index"] for item in result["results"]], [0, 1, 2])
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(folders, ["fixture02026paper", "fixture22026paper"])

    def test_organizes_strict_yaml_and_abstract_note(self) -> None:
        response = """# paper_label
wrong2020guess
# metadata
---
title: "Hallucinated Title"
authors:
  - Wrong Author
year: 2020
journal: "Wrong Journal"
link: https://wrong.example
status:
  - initiated
tags:
  - behavioral economics
  - information
created: 2026-01-01
interest: none
importance: none
contributions:
---

# Hallucinated Title

## Abstract
Hallucinated abstract.

## Related Papers
- Something
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            output = root / "organized"
            _write_context(context)
            result = organize_link_response(
                content=response,
                context_path=context,
                model_label="test-model",
                output_dir=output,
            )
            metadata = Path(result["metadata_path"]).read_text(encoding="utf-8")
            front = yaml.safe_load(metadata.split("---\n", 2)[1])
        self.assertEqual(front["title"], "Verified Title")
        self.assertEqual(front["authors"], ["Ada Example"])
        self.assertEqual(front["link"], "https://doi.org/10.1234/test.1")
        self.assertEqual(front["tags"][0], "behavioral_economics")
        self.assertIn("Verified abstract text.", metadata)
        self.assertNotIn("## Related Papers", metadata)
        self.assertNotIn("ai_summary.md", result["files_created"])

    def test_duplicate_link_is_skipped_without_new_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            output = root / "organized"
            existing = output / "existing2025paper"
            existing.mkdir(parents=True)
            (existing / "existing2025paper.md").write_text(
                "---\ntitle: Existing\nlink: https://doi.org/10.1234/test.1\n---\n",
                encoding="utf-8",
            )
            _write_context(context)
            result = organize_link_response(
                content="# paper_label\nnew2025paper\n# metadata\n---\ntitle: New\n---\n",
                context_path=context,
                model_label="test-model",
                output_dir=output,
            )
            folders = sorted(path.name for path in output.iterdir())
        self.assertTrue(result["already_exists"])
        self.assertEqual(folders, ["existing2025paper"])

    def test_bare_doi_duplicate_matches_canonical_doi_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            output = root / "organized"
            existing = output / "existing2025paper"
            existing.mkdir(parents=True)
            (existing / "existing2025paper.md").write_text(
                "---\ntitle: Existing\nlink: 10.1234/test.1\n---\n",
                encoding="utf-8",
            )
            _write_context(context)
            result = organize_link_response(
                content="not parsed because the canonical DOI already exists",
                context_path=context,
                model_label="test-model",
                output_dir=output,
            )
        self.assertTrue(result["already_exists"])
        self.assertEqual(result["paper_label"], "existing2025paper")

    def test_accepts_label_as_first_heading(self) -> None:
        response = """# example2025paper
# metadata
---
title: Engine Title
tags:
  - information
---

## Engine Title

### Abstract
Engine abstract.
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            _write_context(context)
            result = organize_link_response(
                content=response,
                context_path=context,
                model_label="test-model",
                output_dir=root / "organized",
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["paper_label"], "example2025paper")

    def test_preserves_hybrid_pascal_label_case(self) -> None:
        response = """# Example2025LLMCooperation
# metadata
---
title: Engine Title
tags:
  - information
---
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            _write_context(context)
            result = organize_link_response(
                content=response,
                context_path=context,
                model_label="test-model",
                output_dir=root / "organized",
            )
        self.assertEqual(result["paper_label"], "Example2025LLMCooperation")

    def test_unsafe_engine_label_uses_hybrid_metadata_fallback(self) -> None:
        response = """# paper_label
../unsafe
# metadata
---
title: Engine Title
tags:
  - information
---
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            _write_context(context, title="LLM Cooperation")
            result = organize_link_response(
                content=response,
                context_path=context,
                model_label="test-model",
                output_dir=root / "organized",
            )
        self.assertEqual(result["paper_label"], "Example2025LLMCooperation")

    def test_codex_link_prepare_keeps_web_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "source_context.txt"
            _write_context(context)
            args = SimpleNamespace(
                external_cli_engine="codex-cli",
                instruction="",
                agy_model=None,
                codex_model=None,
                codex_reasoning_effort=None,
            )
            result = prepare_link_input(args, context)
            prompt = Path(result["prompt_path"]).read_text(encoding="utf-8")
            shutil.rmtree(result["cleanup_dir"])
        self.assertEqual(result["web_search"], "disabled")
        self.assertIn("Do not browse, search, fetch", prompt)

    def test_managed_agy_uses_per_run_model_and_isolated_files(self) -> None:
        captured = {}

        def fake_run(command, *, work_dir, timeout_seconds):
            captured["command"] = command
            response = work_dir / "response.txt"
            stderr = work_dir / "stderr.txt"
            response.write_text(
                "PAPERHUB_RESPONSE_BEGIN\n# paper_label\nfixture2026paper\n"
                "# metadata\n---\ntitle: Fixture\n---\n"
                "PAPERHUB_RESPONSE_END\n",
                encoding="utf-8",
            )
            stderr.write_text("", encoding="utf-8")
            log_path = Path(command[command.index("--log-file") + 1])
            log_path.write_text("completed", encoding="utf-8")
            return 0, response, stderr, 0.01

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            _write_context(context)
            with patch("scripts.paper_organizer.CLI_WORK_DIR", root), patch(
                "scripts.paper_organizer._run_cli_process",
                side_effect=fake_run,
            ):
                result = _generate_agy_link(
                    {"index": 0, "context_path": str(context)},
                    model="Gemini 3.1 Pro (High)",
                    instruction="",
                )
            shutil.rmtree(result["diagnostic_dir"])
        self.assertTrue(result["success"])
        self.assertIn("--model", captured["command"])
        self.assertNotIn("--add-dir", captured["command"])

    def test_managed_codex_is_read_only_and_web_disabled(self) -> None:
        captured = {}

        def fake_run(command, *, work_dir, timeout_seconds):
            captured["command"] = command
            response = work_dir / "response.txt"
            stderr = work_dir / "stderr.txt"
            response.write_text(
                "PAPERHUB_RESPONSE_BEGIN\n# paper_label\nfixture2026paper\n"
                "# metadata\n---\ntitle: Fixture\n---\n"
                "PAPERHUB_RESPONSE_END\n",
                encoding="utf-8",
            )
            # Non-empty: an empty stderr is the "Codex never ran" staleness
            # signal, which validate_codex_cli_run treats as hard-fatal.
            stderr.write_text("codex: workspace ready\n", encoding="utf-8")
            return 0, response, stderr, 0.01

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "source_context.txt"
            _write_context(context)
            with patch("scripts.paper_organizer.CLI_WORK_DIR", root), patch(
                "scripts.paper_organizer._run_cli_process",
                side_effect=fake_run,
            ):
                result = _generate_codex_link(
                    {"index": 0, "context_path": str(context)},
                    model="gpt-5.6-sol",
                    effort="xhigh",
                    instruction="",
                )
            shutil.rmtree(result["diagnostic_dir"])
        self.assertTrue(result["success"])
        self.assertIn("read-only", captured["command"])
        self.assertIn('web_search="disabled"', captured["command"])
        self.assertIn("--ephemeral", captured["command"])

    @patch("scripts.paper_summarizer.requests.post")
    def test_openrouter_plain_prompt_has_no_tools(self, post) -> None:
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 1},
            },
        )
        post.return_value = response
        result = call_openrouter_prompt_api(
            api_key="test",
            model_id="test/model",
            prompt="offline context",
        )
        payload = post.call_args.kwargs["json"]
        self.assertTrue(result["success"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("plugins", payload)

    def test_link_parse_failure_artifact_uses_link_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = root / "link_example" / "source_context.txt"
            context.parent.mkdir()
            context.write_text("context", encoding="utf-8")
            with patch.object(legacy, "RAW_OUTPUTS_DIR", root / "raw_outputs"):
                raw_path = save_raw_link_content(
                    context,
                    "raw engine response",
                    "test/model",
                    {"total_tokens": 12},
                )
            text = raw_path.read_text(encoding="utf-8")
        self.assertIn(str(context), text)
        self.assertIn("raw engine response", text)


if __name__ == "__main__":
    unittest.main()
