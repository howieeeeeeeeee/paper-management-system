#!/usr/bin/env python3
"""Enrich existing paper folders with an AI summary (and patch missing meta).

Usage:

    # OpenRouter engine (single command, uses API):
    uv run python enrich.py --folder ACF2015 [--folder OTHER] \\
        --engine openrouter [--no-summary] [--force] \\
        [--instruction "..."] [--use-past-summary] [--model MODEL_ID]

    # External CLI engine — two-step handshake (mirrors paper_summarizer.py):
    uv run python enrich.py --engine agy-cli --prepare-cli-input --folder ACF2015 \\
        [--no-summary] [--use-past-summary] [--instruction "..."]
    # ... orchestrator runs agy on the printed prompt + pdf path ...
    uv run python enrich.py --engine agy-cli --from-response --folder ACF2015 \\
        --response-file /tmp/resp.txt [--agy-stderr-file ...] [--no-summary]

The PRIMARY task is generating `ai_summary.md`. Patching missing metadata fields
(title/authors/year/journal/link/tags + abstract placeholder) is a secondary,
opportunistic step done in the same AI call.

When `--use-past-summary` is passed (or `--past-summary-file PATH` for an
explicit override), an existing `ai_summary.md` is embedded in the prompt as a
reference draft so the AI can polish it instead of starting from scratch.
Combine with `--instruction` to tell the AI which parts to emphasize, expand,
or tighten.

Never touched: `contributions`, `status`, `interest`. Never overwrites a
non-empty existing field.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import yaml

from config import (
    AGY_CLI_MODEL,
    AGY_CLI_MODEL_LIST,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PDF_ENGINE,
    METADATA_ONLY_PAGE_LIMIT,
    MODEL_LIST,
    MY_RESEARCH_INTERESTS,
    PAPERHUB_ROOT,
)
from prompt.builder import MODE_ENRICH, build_prompt
from cli_workflow.agy import (
    AGY_RESPONSE_BEGIN,
    AGY_RESPONSE_END,
    agy_model_label,
    agy_settings_path,
    configure_agy_cli_model,
    extract_agy_response_block,
    resolve_agy_cli_model,
    validate_agy_cli_run,
)
from cli_workflow.gemini import validate_gemini_cli_run
from cli_workflow.pdf import (
    CLI_WORK_DIR,
    ensure_safe_cli_cleanup_path,
    gemini_at_path,
    repo_relative_path,
)
from paper_summarizer import (
    call_openrouter_api,
    call_openrouter_text_api,
    encode_pdf_to_base64,
    extract_pdf_context,
    format_yaml_model_value,
    get_api_key,
    resolve_pdf_input_config,
    resolve_model_config,
    save_raw_content,
)


logger = logging.getLogger("paperhub.enrich")

REQUIRED_SCALAR_KEYS = ("title", "year", "journal")
REQUIRED_LIST_KEYS = ("authors", "tags")
OPTIONAL_FILLABLE_KEYS = ("link",)
USER_CURATED_BLOCKLIST = ("contributions", "status", "interest")

ABSTRACT_PLACEHOLDER_RE = re.compile(
    r"^\s*\[Abstract not found in provided pages\]\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class FolderArtifacts:
    folder: Path
    paper_label: str
    pdf_path: Path
    meta_path: Path
    summary_path: Path | None  # ai_summary.md or summary.md if present


class EnrichParseError(ValueError):
    """Raised when an AI enrich response cannot be parsed."""

    def __init__(self, message: str, raw_content_file: Path | None = None):
        super().__init__(message)
        self.raw_content_file = raw_content_file


# ---------- discovery ----------


def find_artifacts(folder_arg: str, output_dir: Path) -> FolderArtifacts:
    """Resolve a --folder argument (name or path) to its artifacts."""
    folder = Path(folder_arg)
    if not folder.is_absolute():
        folder = output_dir / folder
    folder = folder.resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder does not exist: {folder}")

    paper_label = folder.name
    meta_path = folder / f"{paper_label}.md"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Metadata file not found: {meta_path}")

    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF found in folder: {folder}")
    if len(pdfs) > 1:
        logger.warning("Multiple PDFs in %s; using %s", folder, pdfs[0].name)

    summary_path = None
    for candidate in ("ai_summary.md", "summary.md"):
        p = folder / candidate
        if p.is_file():
            summary_path = p
            break

    return FolderArtifacts(
        folder=folder,
        paper_label=paper_label,
        pdf_path=pdfs[0],
        meta_path=meta_path,
        summary_path=summary_path,
    )


# ---------- meta parsing ----------


def split_frontmatter(text: str) -> tuple[str, str, str]:
    """Return (pre, frontmatter_yaml, body). pre is empty if frontmatter is at start."""
    m = re.match(r"(?s)^(---\s*\n)(.*?)\n(---\s*\n)", text)
    if not m:
        return "", "", text
    return "", m.group(2), text[m.end():]


def is_blank_value(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, list) and not v:
        return True
    return False


def compute_missing_keys(fm: dict, body: str) -> tuple[list[str], bool]:
    """Determine which keys to fill and whether to emit a fresh abstract."""
    missing: list[str] = []
    for key in REQUIRED_SCALAR_KEYS:
        v = fm.get(key)
        if is_blank_value(v) or (key == "year" and v in (0, "0")):
            missing.append(key)
    for key in REQUIRED_LIST_KEYS:
        if is_blank_value(fm.get(key)):
            missing.append(key)
    for key in OPTIONAL_FILLABLE_KEYS:
        if is_blank_value(fm.get(key)):
            missing.append(key)

    abstract_match = re.search(
        r"^##\s+Abstract\s*$(.*?)(?=^##\s+|\Z)",
        body,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not abstract_match:
        emit_abstract = True
    else:
        section_body = abstract_match.group(1).strip()
        emit_abstract = (
            not section_body
            or bool(ABSTRACT_PLACEHOLDER_RE.match(section_body))
            or section_body.lower().startswith("[abstract not found")
        )
    return missing, emit_abstract


# ---------- past summary ----------


def read_past_summary_body(path: Path) -> str:
    """Return the body of an existing ai_summary.md with frontmatter stripped."""
    text = path.read_text(encoding="utf-8")
    _, _, body = split_frontmatter(text)
    return body.strip()


def resolve_past_summary_text(
    art: FolderArtifacts,
    use_past_summary: bool,
    past_summary_file: Path | None,
) -> str:
    """Resolve the past-summary text to embed in the prompt.

    Precedence: `--past-summary-file` (explicit) > `--use-past-summary` (auto).
    Returns "" when nothing applies or the source is empty.
    """
    if past_summary_file is not None:
        if not past_summary_file.is_file():
            raise FileNotFoundError(f"--past-summary-file not found: {past_summary_file}")
        return read_past_summary_body(past_summary_file)
    if use_past_summary and art.summary_path is not None:
        return read_past_summary_body(art.summary_path)
    return ""


# ---------- response parsing ----------


@dataclass
class EnrichResponse:
    paper_label: str
    patch_text: str  # raw text under # metadata_patch (yaml-ish)
    abstract: str | None
    ai_summary: str | None


_HEADING_RE = re.compile(
    r"^#\s*(paper_label|metadata_patch|ai_summary)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_enrich_response(content: str) -> EnrichResponse:
    sections: dict[str, str] = {}
    matches = list(_HEADING_RE.finditer(content))
    if not matches:
        raise ValueError("No # metadata_patch / # ai_summary headings found")
    for idx, m in enumerate(matches):
        key = m.group(1).lower()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        sections[key] = content[start:end].strip()

    paper_label = sections.get("paper_label", "").strip().strip("`").strip()

    patch_text = sections.get("metadata_patch", "")
    abstract: str | None = None
    abstract_match = re.search(
        r"^##\s+Abstract\s*$(.*)\Z",
        patch_text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if abstract_match:
        abstract = abstract_match.group(1).strip()
        patch_text = patch_text[: abstract_match.start()].rstrip()

    ai_summary = sections.get("ai_summary")
    if ai_summary is not None:
        ai_summary = ai_summary.strip() or None

    return EnrichResponse(
        paper_label=paper_label,
        patch_text=patch_text,
        abstract=abstract,
        ai_summary=ai_summary,
    )


def parse_patch_yaml(patch_text: str) -> dict:
    text = patch_text.strip()
    if not text:
        return {}
    text = re.sub(r"^```(?:yaml|yml)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    text = text.strip().strip("-").strip()  # tolerate stray --- fences
    if not text:
        return {}
    # Re-parse cleanly
    text = re.sub(r"^---\s*\n", "", patch_text.strip())
    text = re.sub(r"\n---\s*$", "", text)
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse metadata_patch YAML: {e}\n--- patch ---\n{patch_text}")
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"metadata_patch did not parse to a mapping (got {type(loaded).__name__})")
    return loaded


# ---------- merge ----------


def render_yaml_value(key: str, value) -> str:
    """Render a single YAML key:value pair using PaperHub's conventions."""
    if isinstance(value, list):
        items = "\n".join(f"  - {v}" for v in value)
        return f"{key}:\n{items}"
    if isinstance(value, int):
        return f"{key}: {value}"
    s = str(value).strip()
    if not s:
        return f"{key}:"
    if key in ("title", "journal"):
        s_q = s.replace('"', '\\"')
        return f'{key}: "{s_q}"'
    return f"{key}: {s}"


def merge_metadata_patch(
    meta_path: Path,
    patch: dict,
    abstract: str | None,
    allowed_keys: set[str],
) -> list[str]:
    """Apply patch to meta_path. Returns list of keys actually changed."""
    text = meta_path.read_text(encoding="utf-8")
    pre, fm, body = split_frontmatter(text)
    if not fm:
        raise ValueError(f"No frontmatter in {meta_path}")

    fm_lines = fm.splitlines()
    changed: list[str] = []

    # Drop user-curated and disallowed keys from the patch
    safe_patch = {
        k: v
        for k, v in patch.items()
        if k in allowed_keys and k not in USER_CURATED_BLOCKLIST
    }

    for key, value in safe_patch.items():
        if value is None:
            continue
        new_block = render_yaml_value(key, value)
        new_block_lines = new_block.splitlines()

        idx = _find_key_line(fm_lines, key)
        if idx is None:
            # Insert before contributions: line if present, else append
            insert_at = _find_key_line(fm_lines, "contributions")
            if insert_at is None:
                insert_at = len(fm_lines)
            fm_lines = fm_lines[:insert_at] + new_block_lines + fm_lines[insert_at:]
            changed.append(key)
            continue

        # Replace the existing key block (key line + any indented continuation lines)
        end = idx + 1
        while end < len(fm_lines) and (
            fm_lines[end].startswith(" ") or fm_lines[end].startswith("\t")
        ):
            end += 1
        fm_lines[idx:end] = new_block_lines
        changed.append(key)

    new_fm = "\n".join(fm_lines)
    new_body = body
    if abstract is not None:
        new_body = _replace_abstract(body, abstract)
        if new_body != body:
            changed.append("## Abstract")

    new_text = f"---\n{new_fm}\n---\n\n{new_body.lstrip()}"
    if not new_text.endswith("\n"):
        new_text += "\n"
    meta_path.write_text(new_text, encoding="utf-8")
    return changed


def _find_key_line(fm_lines: list[str], key: str) -> int | None:
    pat = re.compile(rf"^{re.escape(key)}\s*:")
    for i, line in enumerate(fm_lines):
        if pat.match(line):
            return i
    return None


def _replace_abstract(body: str, new_abstract: str) -> str:
    """Replace the body of an existing ## Abstract section, or insert one."""
    new_abstract = new_abstract.strip() + "\n"
    pattern = re.compile(
        r"(^##\s+Abstract\s*\n)(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if pattern.search(body):
        return pattern.sub(lambda m: f"{m.group(1)}{new_abstract}\n", body, count=1)
    # No abstract section — insert after first H1, or at top of body
    h1 = re.search(r"^#\s+.+\n", body, re.MULTILINE)
    insert = f"\n## Abstract\n{new_abstract}\n"
    if h1:
        return body[: h1.end()] + insert + body[h1.end():]
    return f"## Abstract\n{new_abstract}\n" + body


# ---------- summary write ----------


def write_summary(
    folder: Path,
    ai_summary: str,
    model_label: str,
    pdf_engine: str,
    usage: dict | None,
) -> Path:
    usage = usage or {}
    header = (
        f"---\n"
        f"model: {format_yaml_model_value(model_label)}\n"
        f"pdf_engine: {pdf_engine}\n"
        f"tokens_prompt: {usage.get('prompt_tokens', 'N/A')}\n"
        f"tokens_completion: {usage.get('completion_tokens', 'N/A')}\n"
        f"total_tokens: {usage.get('total_tokens', 'N/A')}\n"
        f"cost: {usage.get('cost', 'N/A')}\n"
        f"generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"enriched: true\n"
        f"---\n\n"
    )
    out = folder / "ai_summary.md"
    out.write_text(header + ai_summary.strip() + "\n", encoding="utf-8")
    return out


# ---------- interactive prompt ----------


def ask_existing_summary_action(folder_name: str) -> str:
    """Return 'overwrite' | 'meta_only' | 'skip'."""
    while True:
        msg = (
            f"\n[{folder_name}] ai_summary.md already exists. Choose:\n"
            f"  [O] Overwrite the summary (and patch missing meta)\n"
            f"  [E] meta-fill only — leave the summary as-is\n"
            f"  [S] Skip this folder\n"
            f"Choice [O/E/S]: "
        )
        sys.stderr.write(msg)
        sys.stderr.flush()
        ans = sys.stdin.readline().strip().lower()
        if ans in ("o", "overwrite"):
            return "overwrite"
        if ans in ("e", "meta", "meta_only"):
            return "meta_only"
        if ans in ("s", "skip", ""):
            return "skip"


# ---------- prompt construction ----------


def build_enrich_prompt_for_folder(
    art: FolderArtifacts,
    include_summary: bool,
    additional_instruction: str,
    past_summary_text: str = "",
) -> tuple[str, list[str], bool]:
    """Returns (prompt, missing_keys, emit_abstract)."""
    text = art.meta_path.read_text(encoding="utf-8")
    _, fm_text, body = split_frontmatter(text)
    fm = yaml.safe_load(fm_text) if fm_text else {}
    if not isinstance(fm, dict):
        fm = {}
    missing_keys, emit_abstract = compute_missing_keys(fm, body)

    today = datetime.now().strftime("%Y-%m-%d")
    prompt = build_prompt(
        MODE_ENRICH,
        today=today,
        research_interests=MY_RESEARCH_INTERESTS,
        additional_instruction=additional_instruction,
        paper_label=art.paper_label,
        existing_meta_text=text.strip(),
        missing_keys=missing_keys,
        emit_abstract=emit_abstract,
        include_summary=include_summary,
        past_summary_text=past_summary_text if include_summary else "",
    )
    return prompt, missing_keys, emit_abstract


# ---------- engines ----------


def run_openrouter(
    art: FolderArtifacts,
    prompt: str,
    model_arg,
    pdf_engine: str,
) -> tuple[str, str, dict, str]:
    """Returns (response_text, model_label, usage, effective_pdf_engine)."""
    api_key = get_api_key()
    cfg = resolve_model_config(model_arg)
    model_id = cfg["model_id"]
    provider = cfg.get("provider", {})
    reasoning = cfg.get("reasoning")
    pdf_input = resolve_pdf_input_config(cfg)
    if pdf_input["mode"] == "text_extraction":
        extractor = pdf_input["extractor"]
        pdf_text = extract_pdf_context(art.pdf_path, extractor)
        result = call_openrouter_text_api(
            api_key=api_key,
            model_id=model_id,
            prompt=prompt,
            pdf_text=pdf_text,
            provider=provider,
            reasoning=reasoning,
            extractor=extractor,
        )
        effective_pdf_engine = extractor
    else:
        pdf_b64 = encode_pdf_to_base64(art.pdf_path)
        result = call_openrouter_api(
            api_key, model_id, pdf_b64, prompt, pdf_engine, provider, reasoning
        )
        effective_pdf_engine = pdf_engine
    if not result.get("success"):
        raise RuntimeError(
            f"OpenRouter call failed for {art.paper_label}: {result.get('error')}"
        )
    return result.get("content") or "", model_id, result.get("usage") or {}, effective_pdf_engine


def prepare_cli_input(
    art: FolderArtifacts,
    include_summary: bool,
    additional_instruction: str,
    past_summary_text: str = "",
    external_cli_engine: str = "gemini-cli",
    agy_model: str | None = None,
) -> dict:
    """Mirror paper_summarizer.prepare_cli_input for enrich mode."""
    if external_cli_engine not in {"gemini-cli", "agy-cli"}:
        raise ValueError(f"Unknown external CLI engine: {external_cli_engine}")

    resolved_agy_model = None
    if external_cli_engine == "agy-cli":
        resolved_agy_model = configure_agy_cli_model(
            agy_model,
            default_model=AGY_CLI_MODEL,
            allowed_models=AGY_CLI_MODEL_LIST,
        )

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    engine_slug = external_cli_engine.replace("-cli", "")
    work_dir = CLI_WORK_DIR / f"enrich_{engine_slug}_{art.paper_label}_{run_id}"
    work_dir.mkdir(parents=True, exist_ok=False)
    try:
        prompt, missing_keys, emit_abstract = build_enrich_prompt_for_folder(
            art, include_summary, additional_instruction, past_summary_text
        )
        prompt_path = work_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        result = {
            "success": True,
            "external_cli_engine": external_cli_engine,
            "mode": MODE_ENRICH,
            "include_summary": include_summary,
            "paper_label": art.paper_label,
            "folder": str(art.folder),
            "prompt_path": str(prompt_path),
            "pdf_for_ai_path": str(art.pdf_path),
            "pdf_for_ai_repo_relative": repo_relative_path(art.pdf_path),
            "pdf_for_ai_gemini_path": gemini_at_path(art.pdf_path),
            "pdf_for_ai_agy_path": str(art.pdf_path.resolve()),
            "missing_keys": missing_keys,
            "emit_abstract": emit_abstract,
            "past_summary_used": bool(past_summary_text and past_summary_text.strip()),
            "cleanup_dir": str(work_dir),
        }
        if resolved_agy_model is not None:
            result["paperhub_root"] = str(PAPERHUB_ROOT)
            result["agy_cli_model"] = resolved_agy_model
            result["agy_model_label"] = agy_model_label(resolved_agy_model)
            result["agy_settings_path"] = str(agy_settings_path())
            result["response_begin"] = AGY_RESPONSE_BEGIN
            result["response_end"] = AGY_RESPONSE_END
        return result
    except Exception:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)
        raise


# ---------- per-folder pipeline ----------


def apply_response(
    art: FolderArtifacts,
    response_text: str,
    include_summary: bool,
    missing_keys: list[str],
    emit_abstract: bool,
    model_label: str,
    pdf_engine: str,
    usage: dict | None,
    meta_only: bool = False,
) -> dict:
    try:
        parsed = parse_enrich_response(response_text)
    except ValueError as e:
        raw_path = None
        if response_text.strip():
            raw_path = save_raw_content(
                art.pdf_path,
                response_text,
                usage or {},
                model_label=model_label,
                pdf_engine=pdf_engine,
                summary_mode="enrich-meta-only" if meta_only else "enrich",
            )
        raise EnrichParseError(
            f"Failed to parse enrich response: {e}"
            + (f" (raw response saved to {raw_path})" if raw_path else ""),
            raw_content_file=raw_path,
        ) from e

    if parsed.paper_label and parsed.paper_label != art.paper_label:
        logger.warning(
            "AI returned paper_label '%s' but folder is '%s'; using folder name",
            parsed.paper_label,
            art.paper_label,
        )

    patch = parse_patch_yaml(parsed.patch_text)
    allowed = set(missing_keys)
    abstract_to_write = parsed.abstract if emit_abstract else None
    changed_keys = merge_metadata_patch(
        art.meta_path, patch, abstract_to_write, allowed_keys=allowed
    )

    summary_status = "skipped"
    summary_path: Path | None = None
    if include_summary and not meta_only and parsed.ai_summary:
        summary_path = write_summary(
            art.folder, parsed.ai_summary, model_label, pdf_engine, usage
        )
        summary_status = "generated" if art.summary_path is None else "overwritten"
    elif include_summary and not parsed.ai_summary:
        summary_status = "missing-from-response"

    return {
        "paper_label": art.paper_label,
        "folder": str(art.folder),
        "filled_keys": changed_keys,
        "summary": summary_status,
        "summary_path": str(summary_path) if summary_path else None,
        "model": model_label,
        "usage": usage or {},
    }


def process_folder_openrouter(
    art: FolderArtifacts,
    *,
    force: bool,
    include_summary: bool,
    additional_instruction: str,
    past_summary_text: str,
    model_arg,
    pdf_engine: str,
) -> dict:
    meta_only = False
    if art.summary_path and not force:
        action = ask_existing_summary_action(art.paper_label)
        if action == "skip":
            return {"paper_label": art.paper_label, "skipped": True, "reason": "user_skip"}
        if action == "meta_only":
            meta_only = True
            include_summary = False
            past_summary_text = ""

    prompt, missing_keys, emit_abstract = build_enrich_prompt_for_folder(
        art, include_summary, additional_instruction, past_summary_text
    )
    if not missing_keys and not emit_abstract and not include_summary:
        return {
            "paper_label": art.paper_label,
            "skipped": True,
            "reason": "nothing_to_do",
        }

    response, model_label, usage, effective_pdf_engine = run_openrouter(
        art, prompt, model_arg, pdf_engine
    )
    result = apply_response(
        art,
        response,
        include_summary=include_summary,
        missing_keys=missing_keys,
        emit_abstract=emit_abstract,
        model_label=model_label,
        pdf_engine=effective_pdf_engine,
        usage=usage,
        meta_only=meta_only,
    )
    if past_summary_text and past_summary_text.strip():
        result["past_summary_used"] = True
    return result


# ---------- CLI ----------


def main() -> None:
    p = argparse.ArgumentParser(description="Enrich existing paper folders with AI summary.")
    p.add_argument("--folder", action="append", default=[], required=False,
                   help="Folder name under organized/ or absolute path. Repeat for multiple.")
    p.add_argument("--engine", choices=("openrouter", "gemini-cli", "agy-cli"), default="openrouter")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--model", default=None, help="OpenRouter model id (defaults to config DEFAULT_MODEL)")
    p.add_argument("--agy-model", default=None, help="Agy CLI model label; defaults to config AGY_CLI_MODEL")
    p.add_argument("--pdf-engine", default=DEFAULT_PDF_ENGINE)
    p.add_argument("--instruction", default="", help="Additional instruction for the AI "
                   "(e.g., which parts to emphasize when polishing a past summary)")
    p.add_argument("--no-summary", action="store_true",
                   help="Patch missing meta only; do not generate ai_summary.md")
    p.add_argument("--force", action="store_true",
                   help="Skip the interactive prompt when ai_summary.md already exists; overwrite it")
    p.add_argument("--use-past-summary", action="store_true",
                   help="If a folder already has ai_summary.md, embed it in the prompt as a "
                        "reference draft so the AI can polish it instead of starting from scratch. "
                        "No-op for folders without an existing summary, or when --no-summary is set.")
    p.add_argument("--past-summary-file", default=None,
                   help="Explicit path to a past summary file to embed as reference. "
                        "Overrides --use-past-summary auto-detection. Only valid with a single --folder.")
    p.add_argument("--verbose", action="store_true")

    # External CLI handshake (mirrors paper_summarizer.py)
    p.add_argument("--prepare-cli-input", action="store_true",
                   help="Prepare prompt + PDF path for an external CLI; print JSON and exit. "
                        "Requires exactly one --folder.")
    p.add_argument("--from-response", action="store_true",
                   help="Apply a pre-generated AI response to the folder. "
                        "Requires --response-file and exactly one --folder.")
    p.add_argument("--response-file", help="Path to AI response text (with --from-response)")
    p.add_argument("--model-label", default="unknown",
                   help="Model label for ai_summary.md frontmatter (with --from-response)")
    p.add_argument("--gemini-stderr-file", help="Gemini CLI stderr file to validate (with --from-response)")
    p.add_argument("--gemini-output-json", help="Gemini CLI JSON output to validate (with --from-response)")
    p.add_argument("--agy-stderr-file", help="Agy CLI stderr file to validate (with --from-response)")
    p.add_argument("--agy-log-file", help="Agy CLI log file to validate (with --from-response)")
    p.add_argument("--tokens-prompt", type=int)
    p.add_argument("--tokens-completion", type=int)
    p.add_argument("--tokens-thinking", type=int)
    p.add_argument("--tokens-cached", type=int)
    p.add_argument("--tokens-total", type=int)
    p.add_argument("--cleanup-cli-input", metavar="PATH",
                   help="Delete a repo-local external CLI temp dir created by --prepare-cli-input")

    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    output_dir = Path(args.output_dir).resolve()

    if args.cleanup_cli_input:
        path = ensure_safe_cli_cleanup_path(Path(args.cleanup_cli_input))
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        print(json.dumps({"success": True, "deleted": str(path)}))
        return

    if args.prepare_cli_input:
        if len(args.folder) != 1:
            p.error("--prepare-cli-input requires exactly one --folder")
        art = find_artifacts(args.folder[0], output_dir)
        past_summary_text = ""
        if not args.no_summary:
            past_summary_text = resolve_past_summary_text(
                art,
                use_past_summary=args.use_past_summary,
                past_summary_file=Path(args.past_summary_file).resolve() if args.past_summary_file else None,
            )
        result = prepare_cli_input(
            art,
            include_summary=not args.no_summary,
            additional_instruction=args.instruction,
            past_summary_text=past_summary_text,
            external_cli_engine="agy-cli" if args.engine == "agy-cli" else "gemini-cli",
            agy_model=args.agy_model,
        )
        print(json.dumps(result, indent=2))
        return

    if args.from_response:
        if len(args.folder) != 1:
            p.error("--from-response requires exactly one --folder")
        if not args.response_file:
            p.error("--from-response requires --response-file")
        art = find_artifacts(args.folder[0], output_dir)
        is_coding_agent = args.model_label.startswith("current-coding-agent")
        external_cli_engine = args.engine
        if is_coding_agent:
            external_cli_engine = "coding-agent"
        elif (
            args.engine == "agy-cli"
            or args.agy_stderr_file
            or args.agy_log_file
            or args.model_label.endswith(" (Agy CLI)")
        ):
            external_cli_engine = "agy-cli"
        elif args.engine != "gemini-cli":
            external_cli_engine = "gemini-cli"

        response = Path(args.response_file).read_text(encoding="utf-8")
        problems: list[str] = []
        if external_cli_engine == "gemini-cli":
            problems = validate_gemini_cli_run(
                stderr_path=Path(args.gemini_stderr_file).resolve() if args.gemini_stderr_file else None,
                output_json_path=Path(args.gemini_output_json).resolve() if args.gemini_output_json else None,
            )
        elif external_cli_engine == "agy-cli":
            problems = validate_agy_cli_run(
                stdout_text=response,
                stderr_path=Path(args.agy_stderr_file).resolve() if args.agy_stderr_file else None,
                log_path=Path(args.agy_log_file).resolve() if args.agy_log_file else None,
            )
            if not problems:
                response = extract_agy_response_block(response)
        if problems:
            print(json.dumps({"success": False, "problems": problems}, indent=2))
            sys.exit(1)

        model_label = args.model_label
        if external_cli_engine == "agy-cli" and model_label == "unknown":
            resolved_agy_model = resolve_agy_cli_model(
                args.agy_model,
                default_model=AGY_CLI_MODEL,
                allowed_models=AGY_CLI_MODEL_LIST,
            )
            model_label = agy_model_label(resolved_agy_model)

        pdf_engine = {
            "agy-cli": "agy-native",
            "coding-agent": "coding-agent",
        }.get(external_cli_engine, "gemini-native")

        # We don't have missing_keys/emit_abstract from prepare here; recompute.
        text = art.meta_path.read_text(encoding="utf-8")
        _, fm_text, body = split_frontmatter(text)
        fm = yaml.safe_load(fm_text) if fm_text else {}
        missing_keys, emit_abstract = compute_missing_keys(fm if isinstance(fm, dict) else {}, body)
        usage = {}
        for k, attr in (
            ("prompt_tokens", "tokens_prompt"),
            ("completion_tokens", "tokens_completion"),
            ("thinking_tokens", "tokens_thinking"),
            ("cached_tokens", "tokens_cached"),
            ("total_tokens", "tokens_total"),
        ):
            v = getattr(args, attr)
            if v is not None:
                usage[k] = v
        result = apply_response(
            art,
            response,
            include_summary=not args.no_summary,
            missing_keys=missing_keys,
            emit_abstract=emit_abstract,
            model_label=model_label,
            pdf_engine=pdf_engine,
            usage=usage or None,
        )
        print(json.dumps(result, indent=2))
        return

    # Default path: openrouter, possibly multiple folders
    if not args.folder:
        p.error("at least one --folder is required (unless using --cleanup-cli-input)")
    if args.engine in {"gemini-cli", "agy-cli"}:
        p.error(f"--engine {args.engine} requires --prepare-cli-input then --from-response (one folder at a time)")
    if args.past_summary_file and len(args.folder) != 1:
        p.error("--past-summary-file is only valid with a single --folder; use --use-past-summary for batches")

    model_arg = args.model if args.model is not None else DEFAULT_MODEL
    explicit_past_summary_file = (
        Path(args.past_summary_file).resolve() if args.past_summary_file else None
    )
    results = []
    for folder_arg in args.folder:
        try:
            art = find_artifacts(folder_arg, output_dir)
            past_summary_text = ""
            if not args.no_summary:
                past_summary_text = resolve_past_summary_text(
                    art,
                    use_past_summary=args.use_past_summary,
                    past_summary_file=explicit_past_summary_file,
                )
            res = process_folder_openrouter(
                art,
                force=args.force,
                include_summary=not args.no_summary,
                additional_instruction=args.instruction,
                past_summary_text=past_summary_text,
                model_arg=model_arg,
                pdf_engine=args.pdf_engine,
            )
            results.append(res)
        except EnrichParseError as e:
            logger.exception("Failed: %s", folder_arg)
            payload = {
                "folder": folder_arg,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            if e.raw_content_file:
                payload["raw_content_file"] = str(e.raw_content_file)
            results.append(payload)
        except Exception as e:
            logger.exception("Failed: %s", folder_arg)
            results.append({"folder": folder_arg, "error": str(e), "error_type": type(e).__name__})

    summary = {
        "total": len(results),
        "succeeded": sum(1 for r in results if "error" not in r and not r.get("skipped")),
        "skipped": sum(1 for r in results if r.get("skipped")),
        "failed": sum(1 for r in results if "error" in r),
        "results": results,
    }
    print(json.dumps(summary, indent=2))
    if summary["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
