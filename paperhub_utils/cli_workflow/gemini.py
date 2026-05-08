"""Gemini CLI workflow guards."""

from __future__ import annotations

import json
from pathlib import Path


GEMINI_CLI_FATAL_STDERR_MARKERS = (
    "Path not in workspace",
    "No valid file paths found in @ commands",
    "No valid file paths, resources, or agents found in @ commands",
    "Error executing tool read_file",
    "Error reading files",
    "file read failed",
    "file access failed",
    "skipping access to",
    "read_many_files tool returned no content",
)


def validate_gemini_cli_run(
    stderr_path: Path | None = None,
    output_json_path: Path | None = None,
) -> list[str]:
    """Return problems indicating Gemini CLI did not reliably read the PDF."""
    problems: list[str] = []

    if stderr_path is not None:
        if not stderr_path.exists():
            problems.append(f"Gemini stderr file not found: {stderr_path}")
        else:
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
            for marker in GEMINI_CLI_FATAL_STDERR_MARKERS:
                if marker in stderr_text:
                    problems.append(
                        f"Gemini stderr indicates PDF read failure: {marker}"
                    )

    if output_json_path is not None:
        if not output_json_path.exists():
            problems.append(f"Gemini output JSON file not found: {output_json_path}")
        else:
            problems.extend(validate_gemini_cli_stats(output_json_path))

    return problems


def validate_gemini_cli_stats(output_json_path: Path) -> list[str]:
    """Return problems from Gemini CLI JSON stats."""
    try:
        gemini_output = json.loads(output_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"Gemini output JSON is invalid: {e}"]

    problems: list[str] = []
    tools = gemini_output.get("stats", {}).get("tools", {}).get("byName", {})

    for tool_name in ("read_file", "read_many_files"):
        failures = tools.get(tool_name, {}).get("fail", 0) or 0
        if failures:
            problems.append(f"Gemini reported failed {tool_name} calls: {failures}")

    web_search_count = tools.get("google_web_search", {}).get("count", 0) or 0
    if web_search_count:
        problems.append(
            "Gemini used google_web_search; refusing to organize "
            "because the summary must come from the attached PDF"
        )

    return problems
