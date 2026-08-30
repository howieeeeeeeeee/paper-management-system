"""Codex CLI workflow helpers."""

from __future__ import annotations

from pathlib import Path


CODEX_RESPONSE_BEGIN = "PAPERHUB_RESPONSE_BEGIN"
CODEX_RESPONSE_END = "PAPERHUB_RESPONSE_END"
CODEX_CLI_MODEL_SUFFIX = " (Codex CLI)"

CODEX_CLI_HARD_FATAL_MARKERS = (
    "not authenticated",
    "not logged in",
    "authentication failed",
    "rate limit",
    "permission denied",
    "no such file or directory",
    "failed to read",
)


def resolve_codex_cli_model(
    requested_model: str | None,
    *,
    default_model: str,
    allowed_models: tuple[str, ...],
) -> str:
    """Resolve and validate the Codex model id for a PaperHub run."""
    model = requested_model if requested_model is not None else default_model
    model = model.strip() if isinstance(model, str) else ""
    if not model:
        raise ValueError("Codex CLI model cannot be empty")
    if model not in allowed_models:
        allowed = ", ".join(allowed_models)
        raise ValueError(f"Unsupported Codex CLI model: {model}. Allowed: {allowed}")
    return model


def resolve_codex_cli_reasoning_effort(
    requested_effort: str | None,
    *,
    default_effort: str,
    allowed_efforts: tuple[str, ...],
) -> str:
    """Resolve and validate the Codex reasoning effort for a PaperHub run."""
    effort = requested_effort if requested_effort is not None else default_effort
    effort = effort.strip() if isinstance(effort, str) else ""
    if not effort:
        raise ValueError("Codex CLI reasoning effort cannot be empty")
    if effort not in allowed_efforts:
        allowed = ", ".join(allowed_efforts)
        raise ValueError(
            f"Unsupported Codex CLI reasoning effort: {effort}. Allowed: {allowed}"
        )
    return effort


def resolve_codex_cli_settings(
    requested_model: str | None,
    requested_reasoning_effort: str | None,
    *,
    default_model: str,
    default_reasoning_effort: str,
    allowed_model_reasoning_pairs: tuple[tuple[str, str], ...],
) -> tuple[str, str]:
    """Resolve and validate the Codex model/reasoning pair for a run."""
    allowed_models = tuple(
        dict.fromkeys(model for model, _ in allowed_model_reasoning_pairs)
    )
    allowed_efforts = tuple(
        dict.fromkeys(effort for _, effort in allowed_model_reasoning_pairs)
    )
    model = resolve_codex_cli_model(
        requested_model,
        default_model=default_model,
        allowed_models=allowed_models,
    )
    effort = resolve_codex_cli_reasoning_effort(
        requested_reasoning_effort,
        default_effort=default_reasoning_effort,
        allowed_efforts=allowed_efforts,
    )
    if (model, effort) not in allowed_model_reasoning_pairs:
        allowed = ", ".join(
            f"{allowed_model}+{allowed_effort}"
            for allowed_model, allowed_effort in allowed_model_reasoning_pairs
        )
        raise ValueError(
            "Unsupported Codex CLI model/reasoning pair: "
            f"{model}+{effort}. Allowed: {allowed}"
        )
    return model, effort


def codex_model_label(model: str, reasoning_effort: str | None = None) -> str:
    """Return the model label used in PaperHub output frontmatter."""
    if model.endswith(CODEX_CLI_MODEL_SUFFIX):
        return model
    if reasoning_effort:
        return f"{model} ({reasoning_effort} reasoning){CODEX_CLI_MODEL_SUFFIX}"
    return f"{model}{CODEX_CLI_MODEL_SUFFIX}"


def extract_codex_response_block(stdout_text: str) -> str:
    """Extract the sentinel-delimited PaperHub response from Codex stdout."""
    begin = stdout_text.find(CODEX_RESPONSE_BEGIN)
    if begin < 0:
        raise ValueError(f"Codex output is missing {CODEX_RESPONSE_BEGIN}")
    content_start = begin + len(CODEX_RESPONSE_BEGIN)
    end = stdout_text.find(CODEX_RESPONSE_END, content_start)
    if end < 0:
        raise ValueError(f"Codex output is missing {CODEX_RESPONSE_END}")
    return stdout_text[content_start:end].strip()


def validate_codex_cli_run(
    *,
    stdout_text: str | None = None,
    stderr_path: Path | None = None,
) -> list[str]:
    """Return problems indicating Codex did not produce grounded output."""
    problems: list[str] = []

    if stdout_text is not None:
        try:
            response = extract_codex_response_block(stdout_text)
        except ValueError as e:
            problems.append(str(e))
        else:
            if not response:
                problems.append("Codex response block is empty")

    if stderr_path is not None:
        if not stderr_path.exists():
            problems.append(f"Codex stderr file not found: {stderr_path}")
        else:
            text = stderr_path.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                problems.append(
                    f"Codex stderr is empty: {stderr_path}. A real Codex run always "
                    "writes progress output, so this indicates Codex never ran and the "
                    "response file may be stale. Do not create or blank a stderr file "
                    "to satisfy this check - re-run Codex instead."
                )
            problems.extend(_scan_text_for_markers(text, "Codex stderr"))

    return problems


def _scan_text_for_markers(text: str, source_label: str) -> list[str]:
    lowered = "\n".join(
        line.lower()
        for line in text.splitlines()
        if not (
            "warn codex_core::shell_snapshot: failed to delete shell snapshot"
            in line.lower()
            and "no such file or directory" in line.lower()
        )
    )
    return [
        f"{source_label} indicates Codex failure: {marker}"
        for marker in CODEX_CLI_HARD_FATAL_MARKERS
        if marker in lowered
    ]
