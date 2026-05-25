"""Prompt composition for paper-summarizer modes.

All three modes (`full`, `metadata-only`, `enrich`) compose their prompt from
the same fragments under `prompt/shared/` and `prompt/aspect/`. Dynamic
context (today's date, research interests, user instructions, tag registry
summary) is injected at composition time.

Shared fragments:
    shared/style.txt              — writing style rules
    shared/paper_label.txt        — `# paper_label` section
    shared/metadata_template.txt  — `# metadata` section and YAML fields
    shared/tags_guidelines.txt    — tag selection rules

Aspect fragments:
    aspect/summary_full.txt       — `# ai_summary` body (full / enrich modes)
    aspect/enrich_intro.txt       — enrich-mode preamble
    aspect/past_summary.txt       — optional existing-summary reference

Public API:

    build_prompt(mode, *, today, research_interests, additional_instruction,
                 paper_label=None, existing_meta_text=None,
                 missing_keys=None, emit_abstract=False,
                 include_summary=True, past_summary_text="") -> str

`mode` is one of MODE_FULL, MODE_METADATA_ONLY, MODE_ENRICH.
"""

from __future__ import annotations

from pathlib import Path

from config import (
    DEFAULT_TAGS_DIR,
    INCLUDE_TAG_CONTEXT_IN_PROMPT,
    TAG_PROMPT_TOP_FIELD,
    TAG_PROMPT_TOP_META,
    TAG_PROMPT_TOP_METHODOLOGY,
    TAG_PROMPT_TOP_TOPIC,
)
from tag_utils.registry import RegistryError, load_registry

MODE_FULL = "full"
MODE_METADATA_ONLY = "metadata-only"
MODE_ENRICH = "enrich"
MODES = (MODE_FULL, MODE_METADATA_ONLY, MODE_ENRICH)

_PROMPT_DIR = Path(__file__).resolve().parent
_SHARED_DIR = _PROMPT_DIR / "shared"
_ASPECT_DIR = _PROMPT_DIR / "aspect"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_research_section(research_interests: str) -> str:
    """Render the reader's research interests block, or empty string."""
    if not research_interests or "[PLEASE FILL IN" in research_interests:
        return ""
    return (
        "\n**IMPORTANT - Reader's Research Interests:**\n"
        "The following describes the reader's research interests. Use this to generate specific, \n"
        'relevant connections in the "Relevance to My Work" and "Connections to My Research" '
        "sections (use bullet list, keep it short and concise):\n\n"
        f"``` \n{research_interests}\n```\n"
    )


def render_instruction_section(additional_instruction: str) -> str:
    """Render the user's additional instruction block, or empty string."""
    if not additional_instruction or not additional_instruction.strip():
        return ""
    return (
        "\n**ADDITIONAL INSTRUCTIONS FROM USER:**\n"
        f"{additional_instruction.strip()}\n"
    )


def render_past_summary_section(past_summary_text: str) -> str:
    """Render the optional past-summary reference block (enrich mode only)."""
    if not past_summary_text or not past_summary_text.strip():
        return ""
    template = _read(_ASPECT_DIR / "past_summary.txt").rstrip("\n")
    return template.format(past_summary_text=past_summary_text.strip())


def render_tag_context_section() -> str:
    """Render a compact live tag-registry block for prompt-time reuse."""
    if not INCLUDE_TAG_CONTEXT_IN_PROMPT:
        return ""

    try:
        loaded = load_registry(
            DEFAULT_TAGS_DIR,
            allow_summary_fallback=True,
            require_populated=True,
        )
    except RegistryError:
        return ""

    registry = loaded.data
    by_type = registry.get("by_type")
    if not isinstance(by_type, dict):
        return ""

    limits = {
        "field": _coerce_limit(TAG_PROMPT_TOP_FIELD),
        "topic": _coerce_limit(TAG_PROMPT_TOP_TOPIC),
        "methodology": _coerce_limit(TAG_PROMPT_TOP_METHODOLOGY),
        "meta": _coerce_limit(TAG_PROMPT_TOP_META),
    }
    lines = [
        "",
        "**Canonical Tag Registry Context:**",
        (
            "Prefer reusing these existing tags when they fit. Preserve the exact "
            "spelling shown. Create a new lowercase underscore tag only when none "
            "of the existing tags fit."
        ),
    ]

    rendered_any = False
    for tag_type in ("field", "topic", "methodology", "meta"):
        limit = limits[tag_type]
        if limit <= 0:
            continue
        rows = by_type.get(tag_type, [])
        if not isinstance(rows, list):
            continue
        normalized_rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            tag = str(row.get("tag", "")).strip()
            if not tag:
                continue
            try:
                count = int(row.get("count", 0))
            except (TypeError, ValueError):
                count = 0
            normalized_rows.append({"tag": tag, "count": count})
        normalized_rows.sort(key=lambda item: (-item["count"], item["tag"].lower()))
        selected = normalized_rows[:limit]
        if not selected:
            continue
        rendered_any = True
        tags = ", ".join(f"`{item['tag']}` ({item['count']})" for item in selected)
        lines.append(f"- {tag_type} top {len(selected)}: {tags}")

    if not rendered_any:
        return ""
    return "\n".join(lines) + "\n"


def _coerce_limit(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def build_prompt(
    mode: str,
    *,
    today: str,
    research_interests: str = "",
    additional_instruction: str = "",
    paper_label: str | None = None,
    existing_meta_text: str | None = None,
    missing_keys: list[str] | None = None,
    emit_abstract: bool = False,
    include_summary: bool = True,
    past_summary_text: str = "",
) -> str:
    if mode not in MODES:
        raise ValueError(f"Unknown prompt mode: {mode}")

    research_section = render_research_section(research_interests)
    tag_context_section = render_tag_context_section()
    instruction_section = render_instruction_section(additional_instruction)

    if mode == MODE_FULL:
        return _build_full_or_metadata_only(
            today=today,
            research_section=research_section,
            tag_context_section=tag_context_section,
            instruction_section=instruction_section,
            metadata_only=False,
        )
    if mode == MODE_METADATA_ONLY:
        return _build_full_or_metadata_only(
            today=today,
            research_section=research_section,
            tag_context_section=tag_context_section,
            instruction_section=instruction_section,
            metadata_only=True,
        )
    return _build_enrich(
        today=today,
        research_section=research_section,
        tag_context_section=tag_context_section,
        instruction_section=instruction_section,
        paper_label=paper_label or "",
        existing_meta_text=existing_meta_text or "",
        missing_keys=missing_keys or [],
        emit_abstract=emit_abstract,
        include_summary=include_summary,
        past_summary_section=render_past_summary_section(past_summary_text),
    )


def _build_full_or_metadata_only(
    *,
    today: str,
    research_section: str,
    tag_context_section: str,
    instruction_section: str,
    metadata_only: bool,
) -> str:
    """Compose `full` / `metadata-only` prompt from shared + aspect fragments.

    Full mode emits three top-level sections: `# paper_label`, `# metadata`,
    `# ai_summary`. Metadata-only emits the first two and explicitly forbids
    the third.
    """
    style = _read(_SHARED_DIR / "style.txt").rstrip("\n")
    paper_label = _read(_SHARED_DIR / "paper_label.txt").rstrip("\n")
    metadata_template = _read(_SHARED_DIR / "metadata_template.txt").rstrip("\n")
    metadata_template = metadata_template.replace("{today}", today)
    tags_guidelines = _read(_SHARED_DIR / "tags_guidelines.txt").rstrip("\n")

    parts: list[str] = []
    if metadata_only:
        parts.append(
            "Analyze the attached first pages of this research paper and return "
            "Markdown with two top-level sections."
        )
    else:
        parts.append(
            "Analyze this research paper and return Markdown with three "
            "top-level sections."
        )
    parts.append("")
    parts.append(style)
    if research_section:
        parts.append(research_section.rstrip("\n"))
    if tag_context_section:
        parts.append(tag_context_section.rstrip("\n"))
    parts.append("")
    if metadata_only:
        parts.append(
            "Use exactly these two level-1 headings "
            "(no code fences, no extra text outside):"
        )
        parts.append("")
        parts.append("# paper_label")
        parts.append("# metadata")
    else:
        parts.append(
            "Use exactly these level-1 headings "
            "(no code fences, no extra text outside):"
        )
        parts.append("")
        parts.append("# paper_label")
        parts.append("# metadata")
        parts.append("# ai_summary")
    parts.append("")
    parts.append(paper_label)
    parts.append("")
    parts.append(metadata_template)
    parts.append("")
    parts.append(tags_guidelines)

    if not metadata_only:
        summary_full = _read(_ASPECT_DIR / "summary_full.txt").rstrip("\n")
        parts.append("")
        parts.append(summary_full)
    else:
        parts.append("")
        parts.append(
            "Do not write an AI summary, abstract, methodology summary, or "
            "additional top-level sections. Return only # paper_label and # metadata."
        )

    parts.append("")
    parts.append("---")
    parts.append("")
    footer = f"**Summary Completed:** {today}"
    if instruction_section:
        footer += instruction_section
    parts.append(footer)

    return "\n".join(parts)


def _build_enrich(
    *,
    today: str,
    research_section: str,
    tag_context_section: str,
    instruction_section: str,
    paper_label: str,
    existing_meta_text: str,
    missing_keys: list[str],
    emit_abstract: bool,
    include_summary: bool,
    past_summary_section: str = "",
) -> str:
    """Compose enrich-mode prompt from shared + aspect fragments.

    Primary task: write `# ai_summary` for an existing folder.
    Secondary task: emit a `# metadata_patch` block with ONLY the listed missing keys.
    """
    style = _read(_SHARED_DIR / "style.txt").rstrip("\n")
    tags_guidelines = _read(_SHARED_DIR / "tags_guidelines.txt").rstrip("\n")
    enrich_intro = _read(_ASPECT_DIR / "enrich_intro.txt").rstrip("\n")

    enrich_intro = enrich_intro.format(
        paper_label=paper_label,
        existing_meta_text=existing_meta_text,
        missing_keys_list=", ".join(missing_keys) if missing_keys else "(none — metadata is complete)",
        emit_abstract="true" if emit_abstract else "false",
    )

    parts: list[str] = []
    parts.append(
        "Analyze the attached PDF to enrich an EXISTING paper folder in our library."
    )
    parts.append("")
    parts.append(style)
    if research_section:
        # research_section starts with "\n" and ends with "\n"; insert as-is
        parts.append(research_section.rstrip("\n"))
    if tag_context_section:
        parts.append(tag_context_section.rstrip("\n"))
    parts.append("")
    if include_summary:
        parts.append("Use exactly these level-1 headings (no code fences, no extra text outside):")
        parts.append("")
        parts.append("# metadata_patch")
        parts.append("# ai_summary")
    else:
        parts.append("Use exactly this level-1 heading (no code fences, no extra text outside):")
        parts.append("")
        parts.append("# metadata_patch")
    parts.append("")
    parts.append(enrich_intro)
    parts.append("")
    parts.append(tags_guidelines)

    if include_summary:
        summary_full = _read(_ASPECT_DIR / "summary_full.txt").rstrip("\n")
        parts.append("")
        parts.append(summary_full)
        if past_summary_section:
            parts.append("")
            parts.append(past_summary_section)
    else:
        parts.append("")
        parts.append(
            "Do NOT write a `# ai_summary` section. Return only `# metadata_patch`."
        )

    parts.append("")
    parts.append("---")
    parts.append("")
    footer = f"**Summary Completed:** {today}"
    if instruction_section:
        footer += instruction_section
    parts.append(footer)

    return "\n".join(parts)
