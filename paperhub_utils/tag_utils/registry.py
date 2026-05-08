"""Safe loading helpers for the canonical tag registry.

The machine mirror at ``tags/_internal/registry.json`` is fast to read, but it
can be missing, truncated, or temporarily stale. The human-facing
``tags_summary.md`` table carries enough information to recover tag names,
types, counts, and notes for prompt-time reuse and post-batch classification.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VALID_TYPES = ("field", "topic", "methodology", "meta")
INTERNAL_SUBDIR = "_internal"


class RegistryError(RuntimeError):
    """Raised when neither registry.json nor tags_summary.md is usable."""


@dataclass(frozen=True)
class LoadedRegistry:
    data: dict[str, Any]
    source: str
    warnings: tuple[str, ...] = ()


def load_registry(
    tags_dir: Path,
    *,
    allow_summary_fallback: bool = True,
    require_populated: bool = False,
) -> LoadedRegistry:
    """Load a registry, falling back to ``tags_summary.md`` when needed.

    ``require_populated`` is for workflows where an empty registry would cause
    every paper tag to be misclassified as new. If the JSON file is empty but a
    populated summary table exists, the summary table wins.
    """
    tags_dir = Path(tags_dir)
    registry_path = tags_dir / INTERNAL_SUBDIR / "registry.json"
    json_warning = ""

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        _validate_registry_shape(registry)
        if not require_populated or registry_tag_count(registry) > 0:
            return LoadedRegistry(data=registry, source=str(registry_path))
        json_warning = "registry.json has no tags"
    except (OSError, json.JSONDecodeError, RegistryError) as exc:
        json_warning = f"registry.json invalid: {exc}"

    if allow_summary_fallback:
        try:
            summary_registry = parse_tags_summary(tags_dir)
        except RegistryError:
            summary_registry = None
        if summary_registry is not None and (
            not require_populated or registry_tag_count(summary_registry) > 0
        ):
            warnings = (json_warning,) if json_warning else ()
            return LoadedRegistry(
                data=summary_registry,
                source=str(tags_dir / "tags_summary.md"),
                warnings=warnings,
            )

    if json_warning:
        raise RegistryError(json_warning)
    raise RegistryError(f"unable to load registry under {tags_dir}")


def parse_tags_summary(tags_dir: Path) -> dict[str, Any]:
    """Parse ``tags_summary.md`` into the registry JSON shape."""
    summary_path = Path(tags_dir) / "tags_summary.md"
    try:
        text = summary_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryError(f"cannot read tags_summary.md: {exc}") from exc

    by_type: dict[str, list[dict[str, Any]]] = {
        tag_type: [] for tag_type in VALID_TYPES
    }
    scanned = _parse_scanned_count(text)

    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if set(line.strip()) <= set("|-: "):
            continue
        cols = [col.strip() for col in line.strip().strip("|").split("|")]
        if len(cols) != 4:
            continue

        tag_cell, type_cell, count_cell, notes_cell = cols
        tag = tag_cell.strip("`").strip()
        tag_type = type_cell.lower()
        if tag.lower() == "tag" or tag_type == "type":
            continue
        if not tag or tag_type not in VALID_TYPES:
            continue

        try:
            count = int(count_cell)
        except ValueError:
            raise RegistryError(f"invalid count for tag '{tag}': {count_cell}")
        by_type[tag_type].append({"tag": tag, "count": count, "notes": notes_cell})

    total_tags = sum(len(rows) for rows in by_type.values())
    if total_tags == 0:
        raise RegistryError("tags_summary.md has no parseable tag rows")

    return {"scanned": scanned, "total_tags": total_tags, "by_type": by_type}


def registry_tag_count(registry: dict[str, Any]) -> int:
    by_type = registry.get("by_type", {})
    if not isinstance(by_type, dict):
        return 0
    return sum(
        len(rows)
        for rows in by_type.values()
        if isinstance(rows, list)
    )


def registry_tag_names(registry: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    by_type = registry.get("by_type", {})
    if not isinstance(by_type, dict):
        return names
    for rows in by_type.values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                tag = str(row.get("tag", "")).strip()
                if tag:
                    names.add(tag)
    return names


def _validate_registry_shape(registry: Any) -> None:
    if not isinstance(registry, dict):
        raise RegistryError("registry root is not an object")
    by_type = registry.get("by_type")
    if not isinstance(by_type, dict):
        raise RegistryError("missing by_type object")
    for tag_type in VALID_TYPES:
        rows = by_type.get(tag_type)
        if not isinstance(rows, list):
            raise RegistryError(f"missing by_type.{tag_type} list")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise RegistryError(f"by_type.{tag_type}[{index}] is not an object")
            if not str(row.get("tag", "")).strip():
                raise RegistryError(f"by_type.{tag_type}[{index}] has no tag")


def _parse_scanned_count(text: str) -> int:
    match = re.search(r"occurrences across\s+(\d+)\s+papers", text)
    if not match:
        return 0
    return int(match.group(1))
