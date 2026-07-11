#!/usr/bin/env python3
"""Canonical PaperHub PDF and link organizer entrypoint.

PDF arguments retain the legacy ``scripts.paper_summarizer`` interface. Link
metadata uses a prepared ``source_context.txt`` and never enables engine web
tools.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from paperhub.cli_workflow.agy import (
    AGY_RESPONSE_BEGIN,
    AGY_RESPONSE_END,
    agy_model_label,
    extract_agy_response_block,
    resolve_agy_cli_model,
    validate_agy_cli_run,
)
from paperhub.cli_workflow.codex import (
    CODEX_RESPONSE_BEGIN,
    CODEX_RESPONSE_END,
    codex_model_label,
    extract_codex_response_block,
    resolve_codex_cli_settings,
    validate_codex_cli_run,
)
from paperhub.cli_workflow.pdf import CLI_WORK_DIR
from paperhub.config import (
    AGY_CLI_MODEL,
    AGY_CLI_MODEL_LIST,
    CODEX_CLI_MODEL,
    CODEX_CLI_MODEL_REASONING_PAIRS,
    CODEX_CLI_REASONING_EFFORT,
    CODEX_CLI_YOLO,
    DEFAULT_MODEL,
    DEFAULT_ORGANIZED_DIR,
    PAPERHUB_ROOT,
)
from paperhub.link_ingestion import (
    create_link_prompt,
    find_existing_link,
    load_link_context,
    materialize_public_pdf_sidecar,
    normalize_link_key,
    organize_link_response,
)
from scripts import paper_summarizer as legacy
from scripts.paper_summarizer import *  # noqa: F403 - canonical compatibility surface


LINK_FLAGS = {"--link-context", "--prepare-link-input", "--from-link-response"}


def save_raw_link_content(
    context_path: Path,
    content: str,
    model_label: str,
    usage: dict | None,
) -> Path:
    legacy.RAW_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = legacy.RAW_OUTPUTS_DIR / f"link_{context_path.parent.name}_{timestamp}.md"
    header = {
        "context_path": str(context_path),
        "model": model_label,
        "summary_mode": "link-metadata",
        **(usage or {}),
    }
    raw_path.write_text(
        "---\n" + "\n".join(f"{key}: {json.dumps(value)}" for key, value in header.items())
        + "\n---\n\n" + content,
        encoding="utf-8",
    )
    return raw_path


def _uses_link_interface(argv: list[str]) -> bool:
    return any(flag in argv for flag in LINK_FLAGS)


def build_link_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--link-context",
        action="append",
        required=True,
        help="Prepared source_context.txt; repeat for a parallel batch",
    )
    parser.add_argument(
        "--engine",
        choices=("openrouter", "agy-cli", "codex-cli"),
        default="openrouter",
        help="Managed pure-link engine (default: openrouter)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum parallel engine calls (1-8; default: 4)",
    )
    parser.add_argument(
        "--pdf-mode",
        choices=("metadata-only", "full"),
        help="Resolve pdf-pending-mode contexts for grouped PDF processing",
    )
    parser.add_argument("--prepare-link-input", action="store_true")
    parser.add_argument("--from-link-response", action="store_true")
    parser.add_argument("--response-file")
    parser.add_argument(
        "--external-cli-engine",
        choices=("agy-cli", "codex-cli", "coding-agent"),
    )
    parser.add_argument("--agy-model")
    parser.add_argument("--codex-model")
    parser.add_argument("--codex-reasoning-effort")
    parser.add_argument("--model")
    parser.add_argument("--model-label", default="unknown")
    parser.add_argument("--instruction", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_ORGANIZED_DIR))
    parser.add_argument("--agy-stderr-file")
    parser.add_argument("--agy-log-file")
    parser.add_argument("--codex-stderr-file")
    parser.add_argument("--tokens-prompt", type=int)
    parser.add_argument("--tokens-completion", type=int)
    parser.add_argument("--tokens-total", type=int)
    parser.add_argument("--verbose", action="store_true")
    return parser


def _link_engine_prompt(prompt: str) -> str:
    return (
        "You are running the PaperHub offline link-metadata workflow.\n\n"
        "Use only the supplied text below. Do not browse, fetch URLs, call web "
        "tools, read files, or edit files.\n\n"
        "Return the complete PaperHub response between these exact sentinel lines:\n"
        f"{AGY_RESPONSE_BEGIN}\n"
        "[response]\n"
        f"{AGY_RESPONSE_END}\n\n"
        f"{prompt}"
    )


def run_parallel_link_generation(
    jobs: list[dict[str, Any]],
    max_workers: int,
    generator: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Run model generation concurrently and preserve input-index mapping."""
    generated: dict[int, dict[str, Any]] = {}
    if not jobs:
        return generated
    with ThreadPoolExecutor(max_workers=min(max_workers, len(jobs))) as executor:
        futures = {executor.submit(generator, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "error_type": type(exc).__name__,
                }
            generated[int(job["index"])] = result
    return generated


def _generate_openrouter_link(
    job: dict[str, Any],
    *,
    api_key: str,
    model_config: dict[str, Any],
    instruction: str,
) -> dict[str, Any]:
    started = time.monotonic()
    prompt = create_link_prompt(Path(job["context_path"]), instruction)
    api_result = legacy.call_openrouter_prompt_api(
        api_key=api_key,
        model_id=model_config["model_id"],
        prompt=prompt,
        provider=model_config.get("provider"),
        reasoning=model_config.get("reasoning"),
    )
    if not api_result.get("success"):
        return {
            "success": False,
            "error": api_result.get("error", "OpenRouter request failed"),
            "error_details": api_result.get("error_details"),
            "generation_seconds": round(time.monotonic() - started, 3),
        }
    return {
        "success": True,
        "content": api_result.get("content") or "",
        "model_label": model_config["model_id"],
        "usage": api_result.get("usage") or {},
        "generation_seconds": round(time.monotonic() - started, 3),
    }


def _run_cli_process(
    command: list[str],
    *,
    work_dir: Path,
    timeout_seconds: int,
) -> tuple[int, Path, Path, float]:
    response_path = work_dir / "response.txt"
    stderr_path = work_dir / "stderr.txt"
    started = time.monotonic()
    try:
        with response_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_file:
            completed = subprocess.run(
                command,
                cwd=str(PAPERHUB_ROOT),
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        return (
            completed.returncode,
            response_path,
            stderr_path,
            round(time.monotonic() - started, 3),
        )
    except subprocess.TimeoutExpired:
        with stderr_path.open("a", encoding="utf-8") as stderr_file:
            stderr_file.write(f"\nPaperHub timeout after {timeout_seconds} seconds\n")
        return 124, response_path, stderr_path, round(time.monotonic() - started, 3)


def _generate_agy_link(
    job: dict[str, Any],
    *,
    model: str,
    instruction: str,
) -> dict[str, Any]:
    work_dir = CLI_WORK_DIR / f"link_agy_batch_{uuid4().hex[:10]}"
    work_dir.mkdir(parents=True, exist_ok=False)
    log_path = work_dir / "agy.log"
    prompt = _link_engine_prompt(
        create_link_prompt(Path(job["context_path"]), instruction)
    )
    command = [
        "agy",
        "--model",
        model,
        "--log-file",
        str(log_path),
        "--print-timeout",
        "10m",
        "--print",
        prompt,
    ]
    returncode, response_path, stderr_path, elapsed = _run_cli_process(
        command,
        work_dir=work_dir,
        timeout_seconds=660,
    )
    raw = response_path.read_text(encoding="utf-8", errors="replace") if response_path.exists() else ""
    problems = validate_agy_cli_run(
        stdout_text=raw,
        stderr_path=stderr_path,
        log_path=log_path,
    )
    if returncode != 0:
        problems.append(f"Agy CLI exited with status {returncode}")
    if problems:
        return {
            "success": False,
            "error": "Agy CLI did not produce a reliable offline link response",
            "problems": problems,
            "diagnostic_dir": str(work_dir),
            "response_file": str(response_path),
            "stderr_file": str(stderr_path),
            "log_file": str(log_path),
            "generation_seconds": elapsed,
        }
    return {
        "success": True,
        "content": extract_agy_response_block(raw),
        "model_label": agy_model_label(model),
        "usage": {},
        "diagnostic_dir": str(work_dir),
        "response_file": str(response_path),
        "stderr_file": str(stderr_path),
        "log_file": str(log_path),
        "generation_seconds": elapsed,
    }


def _generate_codex_link(
    job: dict[str, Any],
    *,
    model: str,
    effort: str,
    instruction: str,
) -> dict[str, Any]:
    work_dir = CLI_WORK_DIR / f"link_codex_batch_{uuid4().hex[:10]}"
    work_dir.mkdir(parents=True, exist_ok=False)
    prompt = _link_engine_prompt(
        create_link_prompt(Path(job["context_path"]), instruction)
    )
    command = [
        "codex",
        "exec",
        "--cd",
        str(PAPERHUB_ROOT),
        "--sandbox",
        "read-only",
        "-c",
        'approval_policy="never"',
        "--skip-git-repo-check",
        "--ephemeral",
        "--model",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "-c",
        'web_search="disabled"',
        prompt,
    ]
    returncode, response_path, stderr_path, elapsed = _run_cli_process(
        command,
        work_dir=work_dir,
        timeout_seconds=900,
    )
    raw = response_path.read_text(encoding="utf-8", errors="replace") if response_path.exists() else ""
    problems = validate_codex_cli_run(
        stdout_text=raw,
        stderr_path=stderr_path,
    )
    if returncode != 0:
        problems.append(f"Codex CLI exited with status {returncode}")
    if problems:
        return {
            "success": False,
            "error": "Codex CLI did not produce a reliable offline link response",
            "problems": problems,
            "diagnostic_dir": str(work_dir),
            "response_file": str(response_path),
            "stderr_file": str(stderr_path),
            "generation_seconds": elapsed,
        }
    return {
        "success": True,
        "content": extract_codex_response_block(raw),
        "model_label": codex_model_label(model, effort),
        "usage": {},
        "diagnostic_dir": str(work_dir),
        "response_file": str(response_path),
        "stderr_file": str(stderr_path),
        "generation_seconds": elapsed,
    }


def _resolved_pdf_route(source: dict[str, Any], pdf_mode: str | None) -> str:
    route = str(source.get("route") or "link-metadata")
    if not source.get("public_pdf_path"):
        return "link-metadata"
    if route in {"pdf-metadata", "pdf-full"}:
        return route
    requested_mode = source.get("requested_mode")
    if route == "pdf-pending-mode" or requested_mode == "auto":
        return f"pdf-{pdf_mode}" if pdf_mode else "pdf-pending-mode"
    if requested_mode == "full":
        return "pdf-full"
    if requested_mode == "metadata-only":
        return "pdf-metadata"
    return f"pdf-{pdf_mode}" if pdf_mode else "pdf-pending-mode"


def _preflight_link_batch(
    context_paths: list[Path],
    *,
    output_dir: Path,
    pdf_mode: str | None,
) -> tuple[list[dict[str, Any] | None], list[dict[str, Any]]]:
    results: list[dict[str, Any] | None] = [None] * len(context_paths)
    jobs: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, context_path in enumerate(context_paths):
        try:
            _, source = load_link_context(context_path)
            canonical_url = str(
                source.get("canonical_url") or source.get("input_url") or ""
            )
            if not canonical_url:
                raise ValueError("Link context has no canonical or input URL")
            canonical_key = normalize_link_key(canonical_url)
            if canonical_key in seen:
                results[index] = {
                    "success": True,
                    "skipped": True,
                    "duplicate_in_batch": True,
                    "duplicate_of_index": seen[canonical_key],
                    "input_index": index,
                    "context_path": str(context_path),
                    "canonical_url": canonical_url,
                    "route": "link-metadata",
                    "warnings": ["Duplicate canonical link in this batch; no engine call was made"],
                }
                continue
            seen[canonical_key] = index

            existing = find_existing_link(canonical_url, output_dir)
            if existing:
                results[index] = {
                    "success": True,
                    "skipped": True,
                    "already_exists": True,
                    "input_index": index,
                    "context_path": str(context_path),
                    "canonical_url": canonical_url,
                    "paper_label": existing["paper_label"],
                    "metadata_path": existing["metadata_path"],
                    "route": "link-metadata",
                    "warnings": ["Canonical link already exists; no engine call was made"],
                }
                continue

            route = _resolved_pdf_route(source, pdf_mode)
            if route == "pdf-pending-mode":
                results[index] = {
                    "success": False,
                    "needs_pdf_mode": True,
                    "error": "A public PDF was found; choose metadata-only or full mode",
                    "error_type": "PdfModeRequired",
                    "input_index": index,
                    "context_path": str(context_path),
                    "canonical_url": canonical_url,
                    "route": route,
                    "pdf_path": source.get("public_pdf_path"),
                }
                continue
            if route in {"pdf-metadata", "pdf-full"}:
                sidecar_path = materialize_public_pdf_sidecar(context_path, route=route)
                results[index] = {
                    "success": True,
                    "routed": True,
                    "input_kind": "public-pdf-link",
                    "input_index": index,
                    "context_path": str(context_path),
                    "canonical_url": canonical_url,
                    "route": route,
                    "summary_mode": "metadata-only" if route == "pdf-metadata" else "full",
                    "pdf_path": source.get("public_pdf_path"),
                    "citation_sidecar_path": str(sidecar_path),
                    "warnings": [],
                }
                continue

            jobs.append(
                {
                    "index": index,
                    "context_path": str(context_path),
                    "canonical_url": canonical_url,
                    "source": source,
                }
            )
        except Exception as exc:
            results[index] = {
                "success": False,
                "input_index": index,
                "context_path": str(context_path),
                "error": f"{type(exc).__name__}: {exc}",
                "error_type": type(exc).__name__,
            }
    return results, jobs


def _managed_link_output(
    results: list[dict[str, Any] | None],
    *,
    engine: str,
    max_workers: int,
    started: float,
) -> dict[str, Any]:
    ordered_results = [result for result in results if result is not None]
    failures = [result for result in ordered_results if not result.get("success")]
    skipped = [result for result in ordered_results if result.get("skipped")]
    routed = [result for result in ordered_results if result.get("routed")]
    return {
        "success": not failures,
        "total": len(ordered_results),
        "succeeded": len(ordered_results) - len(failures),
        "skipped": len(skipped),
        "failed": len(failures),
        "routed_pdfs": len(routed),
        "engine": engine,
        "max_workers": max_workers,
        "duration_seconds": round(time.monotonic() - started, 3),
        "results": ordered_results,
    }


def run_managed_link_batch(
    args: argparse.Namespace,
    context_paths: list[Path],
) -> dict[str, Any]:
    started = time.monotonic()
    output_dir = Path(args.output_dir).expanduser().resolve()
    results, jobs = _preflight_link_batch(
        context_paths,
        output_dir=output_dir,
        pdf_mode=args.pdf_mode,
    )
    legacy.logger = legacy.setup_logging(args.verbose)
    if not jobs:
        return _managed_link_output(
            results,
            engine=args.engine,
            max_workers=args.max_workers,
            started=started,
        )

    if args.engine == "openrouter":
        api_key = legacy.get_api_key()
        model_config = legacy.resolve_model_config(args.model or DEFAULT_MODEL)

        def generator(job: dict[str, Any]) -> dict[str, Any]:
            return _generate_openrouter_link(
                job,
                api_key=api_key,
                model_config=model_config,
                instruction=args.instruction,
            )

    elif args.engine == "agy-cli":
        model = resolve_agy_cli_model(
            args.agy_model,
            default_model=AGY_CLI_MODEL,
            allowed_models=AGY_CLI_MODEL_LIST,
        )

        def generator(job: dict[str, Any]) -> dict[str, Any]:
            return _generate_agy_link(
                job,
                model=model,
                instruction=args.instruction,
            )

    else:
        model, effort = resolve_codex_cli_settings(
            args.codex_model,
            args.codex_reasoning_effort,
            default_model=CODEX_CLI_MODEL,
            default_reasoning_effort=CODEX_CLI_REASONING_EFFORT,
            allowed_model_reasoning_pairs=CODEX_CLI_MODEL_REASONING_PAIRS,
        )

        def generator(job: dict[str, Any]) -> dict[str, Any]:
            return _generate_codex_link(
                job,
                model=model,
                effort=effort,
                instruction=args.instruction,
            )

    generated = run_parallel_link_generation(jobs, args.max_workers, generator)
    for job in sorted(jobs, key=lambda item: int(item["index"])):
        index = int(job["index"])
        generation = generated[index]
        if not generation.get("success"):
            results[index] = {
                **generation,
                "success": False,
                "input_kind": "link",
                "input_index": index,
                "context_path": job["context_path"],
                "canonical_url": job["canonical_url"],
                "route": "link-metadata",
                "engine": args.engine,
            }
            continue
        try:
            organized = organize_link_response(
                content=str(generation.get("content") or ""),
                context_path=Path(job["context_path"]),
                model_label=str(generation.get("model_label") or "unknown"),
                output_dir=output_dir,
                usage=generation.get("usage") or None,
            )
            organized.update(
                {
                    "input_index": index,
                    "context_path": job["context_path"],
                    "route": "link-metadata",
                    "engine": args.engine,
                    "generation_seconds": generation.get("generation_seconds"),
                }
            )
            results[index] = organized
            diagnostic_dir = generation.get("diagnostic_dir")
            if diagnostic_dir:
                shutil.rmtree(str(diagnostic_dir), ignore_errors=True)
        except Exception as exc:
            failure = {
                "success": False,
                "input_kind": "link",
                "input_index": index,
                "context_path": job["context_path"],
                "canonical_url": job["canonical_url"],
                "route": "link-metadata",
                "engine": args.engine,
                "error": f"{type(exc).__name__}: {exc}",
                "error_type": type(exc).__name__,
                "generation_seconds": generation.get("generation_seconds"),
            }
            if generation.get("diagnostic_dir"):
                failure["diagnostic_dir"] = generation["diagnostic_dir"]
                failure["response_file"] = generation.get("response_file")
                failure["stderr_file"] = generation.get("stderr_file")
                if generation.get("log_file"):
                    failure["log_file"] = generation["log_file"]
            else:
                raw_path = save_raw_link_content(
                    Path(job["context_path"]),
                    str(generation.get("content") or ""),
                    str(generation.get("model_label") or "unknown"),
                    generation.get("usage") or None,
                )
                failure["raw_content_file"] = str(raw_path)
            results[index] = failure

    return _managed_link_output(
        results,
        engine=args.engine,
        max_workers=args.max_workers,
        started=started,
    )


def prepare_link_input(args: argparse.Namespace, context_path: Path) -> dict:
    engine = args.external_cli_engine
    if engine not in {"agy-cli", "codex-cli", "coding-agent"}:
        raise ValueError("--external-cli-engine is required with --prepare-link-input")
    work_dir = CLI_WORK_DIR / f"link_{engine.replace('-cli', '')}_{uuid4().hex[:10]}"
    work_dir.mkdir(parents=True, exist_ok=False)
    try:
        prompt_path = work_dir / "prompt.txt"
        prompt_path.write_text(
            create_link_prompt(context_path, args.instruction),
            encoding="utf-8",
        )
        result = {
            "success": True,
            "input_kind": "link",
            "mode": "link-metadata",
            "external_cli_engine": engine,
            "context_path": str(context_path),
            "prompt_path": str(prompt_path),
            "cleanup_dir": str(work_dir),
            "web_search": "disabled",
            "response_begin": AGY_RESPONSE_BEGIN if engine == "agy-cli" else CODEX_RESPONSE_BEGIN,
            "response_end": AGY_RESPONSE_END if engine == "agy-cli" else CODEX_RESPONSE_END,
        }
        if engine == "agy-cli":
            model = resolve_agy_cli_model(
                args.agy_model,
                default_model=AGY_CLI_MODEL,
                allowed_models=AGY_CLI_MODEL_LIST,
            )
            result["agy_cli_model"] = model
            result["model_label"] = agy_model_label(model)
        elif engine == "codex-cli":
            model, effort = resolve_codex_cli_settings(
                args.codex_model,
                args.codex_reasoning_effort,
                default_model=CODEX_CLI_MODEL,
                default_reasoning_effort=CODEX_CLI_REASONING_EFFORT,
                allowed_model_reasoning_pairs=CODEX_CLI_MODEL_REASONING_PAIRS,
            )
            result["codex_cli_model"] = model
            result["codex_cli_reasoning_effort"] = effort
            result["codex_cli_yolo"] = CODEX_CLI_YOLO
            result["model_label"] = codex_model_label(model, effort)
        else:
            result["model_label"] = "current-coding-agent"
        return result
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def _usage(args: argparse.Namespace) -> dict:
    result = {}
    if args.tokens_prompt is not None:
        result["prompt_tokens"] = args.tokens_prompt
    if args.tokens_completion is not None:
        result["completion_tokens"] = args.tokens_completion
    if args.tokens_total is not None:
        result["total_tokens"] = args.tokens_total
    return result


def organize_external_link(args: argparse.Namespace, context_path: Path) -> dict:
    if not args.response_file:
        raise ValueError("--response-file is required with --from-link-response")
    engine = args.external_cli_engine or "agy-cli"
    response_path = Path(args.response_file).expanduser().resolve()
    raw = response_path.read_text(encoding="utf-8")
    content = raw
    problems: list[str] = []
    if engine == "agy-cli":
        problems = validate_agy_cli_run(
            stdout_text=raw,
            stderr_path=Path(args.agy_stderr_file).resolve() if args.agy_stderr_file else None,
            log_path=Path(args.agy_log_file).resolve() if args.agy_log_file else None,
        )
        if not problems:
            content = extract_agy_response_block(raw)
    elif engine == "codex-cli":
        problems = validate_codex_cli_run(
            stdout_text=raw,
            stderr_path=Path(args.codex_stderr_file).resolve() if args.codex_stderr_file else None,
        )
        if not problems:
            content = extract_codex_response_block(raw)
    elif engine != "coding-agent":
        raise ValueError(f"Unsupported external engine: {engine}")
    if problems:
        return {
            "success": False,
            "input_kind": "link",
            "error": "External engine did not produce a reliable offline link response",
            "error_type": "ExternalCliLinkError",
            "problems": problems,
        }
    model_label = args.model_label
    if model_label == "unknown":
        if engine == "agy-cli":
            model_label = agy_model_label(AGY_CLI_MODEL)
        elif engine == "codex-cli":
            model_label = codex_model_label(CODEX_CLI_MODEL, CODEX_CLI_REASONING_EFFORT)
        else:
            model_label = "current-coding-agent"
    return organize_link_response(
        content=content,
        context_path=context_path,
        model_label=model_label,
        output_dir=Path(args.output_dir).expanduser().resolve(),
        usage=_usage(args) or None,
    )


def organize_openrouter_link(args: argparse.Namespace, context_path: Path) -> dict:
    legacy.logger = legacy.setup_logging(args.verbose)
    api_key = legacy.get_api_key()
    model_config = legacy.resolve_model_config(args.model or DEFAULT_MODEL)
    prompt = create_link_prompt(context_path, args.instruction)
    api_result = legacy.call_openrouter_prompt_api(
        api_key=api_key,
        model_id=model_config["model_id"],
        prompt=prompt,
        provider=model_config.get("provider"),
        reasoning=model_config.get("reasoning"),
    )
    if not api_result.get("success"):
        return {
            "success": False,
            "input_kind": "link",
            "error": api_result.get("error", "OpenRouter request failed"),
            "error_details": api_result.get("error_details"),
        }
    content = api_result.get("content") or ""
    try:
        return organize_link_response(
            content=content,
            context_path=context_path,
            model_label=model_config["model_id"],
            output_dir=Path(args.output_dir).expanduser().resolve(),
            usage=api_result.get("usage"),
        )
    except Exception as exc:
        raw_path = save_raw_link_content(
            context_path,
            content,
            model_config["model_id"],
            api_result.get("usage"),
        )
        return {
            "success": False,
            "input_kind": "link",
            "error": f"{type(exc).__name__}: {exc}",
            "error_type": type(exc).__name__,
            "raw_content_file": str(raw_path),
        }


def link_main(argv: list[str]) -> int:
    args = build_link_parser().parse_args(argv)
    if not 1 <= args.max_workers <= 8:
        raise SystemExit("--max-workers must be between 1 and 8")
    context_paths = [Path(value).expanduser().resolve() for value in args.link_context]
    missing = [path for path in context_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Link context not found: {missing[0]}")
    if (args.prepare_link_input or args.from_link_response) and len(context_paths) != 1:
        raise SystemExit(
            "Low-level --prepare-link-input/--from-link-response requires exactly one --link-context"
        )
    if not args.prepare_link_input and not args.from_link_response:
        output = run_managed_link_batch(args, context_paths)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0 if output["success"] else 1

    context_path = context_paths[0]
    try:
        if args.prepare_link_input:
            result = prepare_link_input(args, context_path)
        else:
            result = organize_external_link(args, context_path)
    except Exception as exc:
        result = {
            "success": False,
            "input_kind": "link",
            "error": f"{type(exc).__name__}: {exc}",
            "error_type": type(exc).__name__,
        }
    output = {
        "success": bool(result.get("success")),
        "total": 1,
        "succeeded": 1 if result.get("success") else 0,
        "failed": 0 if result.get("success") else 1,
        "results": [result],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["success"] else 1


def main() -> int:
    if sys.argv[1:] in (["--help"], ["-h"]):
        print(
            "Paper Organizer\n\n"
            "PDF compatibility:\n"
            "  python -m scripts.paper_organizer PDF [PDF ...] [legacy PDF options]\n\n"
            "Prepared link metadata:\n"
            "  python -m scripts.paper_organizer --link-context CONTEXT "
            "[--link-context CONTEXT ...] --engine ENGINE --max-workers 4\n"
            "  python -m scripts.paper_organizer --prepare-link-input "
            "--external-cli-engine ENGINE --link-context CONTEXT\n"
            "  python -m scripts.paper_organizer --from-link-response "
            "--external-cli-engine ENGINE --link-context CONTEXT --response-file FILE\n\n"
            "Build link context first with: python -m scripts.paper_link_context --help"
        )
        return 0
    if _uses_link_interface(sys.argv[1:]):
        return link_main(sys.argv[1:])
    legacy.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
