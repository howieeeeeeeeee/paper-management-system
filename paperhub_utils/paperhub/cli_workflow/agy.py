"""Agy CLI workflow helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path


AGY_RESPONSE_BEGIN = "PAPERHUB_RESPONSE_BEGIN"
AGY_RESPONSE_END = "PAPERHUB_RESPONSE_END"
AGY_CLI_MODEL_SUFFIX = " (Agy CLI)"
AGY_CLI_SETTINGS_ENV = "AGY_CLI_SETTINGS_PATH"

# Always fatal: PDF-read failures, workspace errors, timeouts, and web-search
# contamination mean the output is not reliably grounded in the attached PDF.
AGY_CLI_HARD_FATAL_MARKERS = (
    "Error: timed out waiting for response",
    "Print mode: timed out",
    "failed to read file",
    "Path not in workspace",
    "No valid file paths found in @ commands",
    "No valid file paths, resources, or agents found in @ commands",
    "error executing cascade step",
    "google_web_search",
    "web_search",
)

# Recoverable: Gemini frequently emits spurious agentic tool-call steps in print
# mode, and Agy's arg-marshalling bugs make them fail and log these markers. The
# model usually recovers and still produces a complete response, so these are
# only fatal when no valid sentinel response was produced.
AGY_CLI_RECOVERABLE_MARKERS = (
    "invalid tool call error",
    "Model output error",
)

AGY_CLI_FATAL_MARKERS = AGY_CLI_HARD_FATAL_MARKERS + AGY_CLI_RECOVERABLE_MARKERS


def agy_settings_path() -> Path:
    """Return the Agy settings path, with an env override for tests."""
    override = os.environ.get(AGY_CLI_SETTINGS_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def resolve_agy_cli_model(
    requested_model: str | None,
    *,
    default_model: str,
    allowed_models: tuple[str, ...],
) -> str:
    """Resolve and validate the Agy model label for a PaperHub run."""
    model = requested_model if requested_model is not None else default_model
    model = model.strip() if isinstance(model, str) else ""
    if not model:
        raise ValueError("Agy CLI model cannot be empty")
    if model not in allowed_models:
        allowed = ", ".join(allowed_models)
        raise ValueError(f"Unsupported Agy CLI model: {model}. Allowed: {allowed}")
    return model


def agy_model_label(model: str) -> str:
    """Return the model label used in PaperHub output frontmatter."""
    return model if model.endswith(AGY_CLI_MODEL_SUFFIX) else f"{model}{AGY_CLI_MODEL_SUFFIX}"


def set_agy_cli_model(model: str, settings_path: Path | None = None) -> Path:
    """Persist the selected Agy model while preserving other settings keys."""
    path = (settings_path or agy_settings_path()).expanduser()
    data: dict
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Agy settings JSON is invalid: {path}: {e}") from e
        if not isinstance(loaded, dict):
            raise ValueError(f"Agy settings JSON must be an object: {path}")
        data = loaded
    else:
        data = {}

    data["model"] = model
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def configure_agy_cli_model(
    requested_model: str | None,
    *,
    default_model: str,
    allowed_models: tuple[str, ...],
    settings_path: Path | None = None,
) -> str:
    """Validate and persist the Agy model, returning the resolved label."""
    model = resolve_agy_cli_model(
        requested_model,
        default_model=default_model,
        allowed_models=allowed_models,
    )
    set_agy_cli_model(model, settings_path=settings_path)
    return model


def extract_agy_response_block(stdout_text: str) -> str:
    """Extract the sentinel-delimited PaperHub response from Agy stdout."""
    begin = stdout_text.find(AGY_RESPONSE_BEGIN)
    if begin < 0:
        raise ValueError(f"Agy output is missing {AGY_RESPONSE_BEGIN}")
    content_start = begin + len(AGY_RESPONSE_BEGIN)
    end = stdout_text.find(AGY_RESPONSE_END, content_start)
    if end < 0:
        raise ValueError(f"Agy output is missing {AGY_RESPONSE_END}")
    return stdout_text[content_start:end].strip()


def validate_agy_cli_run(
    *,
    stdout_text: str | None = None,
    stderr_path: Path | None = None,
    log_path: Path | None = None,
) -> list[str]:
    """Return problems indicating Agy did not reliably produce PDF-grounded output.

    Hard-fatal markers always count. Recoverable markers (spurious tool-call
    failures the model recovers from) only count when no valid, non-empty
    sentinel response was produced.
    """
    problems: list[str] = []
    recoverable_problems: list[str] = []
    has_valid_response = False

    if stdout_text is not None:
        problems.extend(
            _scan_text_for_markers(stdout_text, "Agy stdout", AGY_CLI_HARD_FATAL_MARKERS)
        )
        recoverable_problems.extend(
            _scan_text_for_markers(stdout_text, "Agy stdout", AGY_CLI_RECOVERABLE_MARKERS)
        )
        try:
            response = extract_agy_response_block(stdout_text)
        except ValueError as e:
            problems.append(str(e))
        else:
            if response:
                has_valid_response = True
            else:
                problems.append("Agy response block is empty")

    checked_streams = 0
    empty_streams: list[str] = []
    for label, path in (("Agy stderr", stderr_path), ("Agy log", log_path)):
        if path is None:
            continue
        if not path.exists():
            problems.append(f"{label} file not found: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        checked_streams += 1
        if not text.strip():
            empty_streams.append(label)
        problems.extend(_scan_text_for_markers(text, label, AGY_CLI_HARD_FATAL_MARKERS))
        recoverable_problems.extend(
            _scan_text_for_markers(text, label, AGY_CLI_RECOVERABLE_MARKERS)
        )

    # A real Agy run always writes progress output to at least one stream. Agy
    # may legitimately leave stderr empty while logging normally, so only treat
    # *every* provided stream being empty as evidence the run never happened and
    # the response file is stale from an earlier session.
    if checked_streams and len(empty_streams) == checked_streams:
        problems.append(
            f"All Agy diagnostic streams are empty ({', '.join(empty_streams)}). A real "
            "Agy run always writes progress output, so this indicates Agy never ran and "
            "the response file may be stale. Do not create or blank a diagnostic file to "
            "satisfy this check - re-run Agy instead."
        )

    if not has_valid_response:
        problems.extend(recoverable_problems)

    return problems


def _scan_text_for_markers(
    text: str, source_label: str, markers: tuple[str, ...]
) -> list[str]:
    return [
        f"{source_label} indicates Agy failure: {marker}"
        for marker in markers
        if marker in text
    ]
