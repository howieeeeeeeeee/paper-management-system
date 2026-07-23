#!/usr/bin/env python3
"""Manifest-driven migration engine for user-defined PaperHub label formats.

The engine never chooses labels. Mapping agents fill batch outputs; this script
validates, freezes, applies, verifies, and rolls back those reviewed decisions.
Every mutating command requires an explicit ``--apply`` flag.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import yaml


SCHEMA_VERSION = 1
SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]*$")
YEAR_RE = re.compile(r"(?<!\d)((?:18|19|20|21)\d{2})(?!\d)")
TEXT_SUFFIXES = {".md", ".canvas", ".base"}
EXCLUDED_DIR_NAMES = {
    ".cache",
    ".caches",
    ".git",
    ".obsidian",
    ".paperhub_tmp",
    ".trash",
    ".venv",
    "__pycache__",
    "cache",
    "caches",
    "node_modules",
    "trash",
}
METADATA_KEYS = {"title", "authors", "year", "journal", "link", "tags", "created"}


class MigrationError(RuntimeError):
    """A safety check failed."""


@dataclass(frozen=True)
class Paths:
    paperhub: Path
    vault: Path
    organized: Path
    work: Path

    @property
    def batches(self) -> Path:
        return self.work / "batches"

    @property
    def inventory(self) -> Path:
        return self.work / "inventory.json"

    @property
    def manifest(self) -> Path:
        return self.work / "manifest.jsonl"

    @property
    def preflight(self) -> Path:
        return self.work / "preflight.json"

    @property
    def review(self) -> Path:
        return self.work / "review.md"

    @property
    def state(self) -> Path:
        return self.work / "apply_state.json"

    @property
    def verification(self) -> Path:
        return self.work / "verification.json"

    @property
    def non_text_hashes(self) -> Path:
        return self.work / "non_text_hashes.jsonl"


def default_paperhub_root() -> Path:
    return Path(__file__).resolve().parents[4]


def discover_vault_root(paperhub: Path) -> Path:
    config_path = paperhub / "paperhub_utils" / "config" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return paperhub
    obsidian = config.get("obsidian")
    if isinstance(obsidian, dict):
        candidate = obsidian.get("vault_abs_path")
        if isinstance(candidate, str) and candidate.strip():
            path = Path(candidate).expanduser().resolve()
            if path.is_dir():
                return path
    return paperhub


def resolve_paths(args: argparse.Namespace) -> Paths:
    paperhub = Path(args.paperhub_root or default_paperhub_root()).expanduser().resolve()
    vault = Path(args.vault_root).expanduser().resolve() if args.vault_root else discover_vault_root(paperhub)
    organized_arg = Path(args.organized_dir)
    organized = organized_arg.resolve() if organized_arg.is_absolute() else paperhub / organized_arg
    work_arg = Path(args.work_dir)
    work = work_arg.resolve() if work_arg.is_absolute() else paperhub / work_arg
    if not paperhub.is_dir() or not organized.is_dir() or not vault.is_dir():
        raise MigrationError("PaperHub root, organized directory, and vault root must exist")
    return Paths(paperhub, vault, organized, work)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(encoded.encode("utf-8"))


def relative(path: Path, parent: Path) -> str:
    return path.relative_to(parent).as_posix()


def atomic_text(path: Path, text: str, *, mode_from: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode_from is not None and mode_from.exists():
            os.chmod(temporary, mode_from.stat().st_mode)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def atomic_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    atomic_text(
        path,
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines(keepends=True)
    delimiters = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"---[ \t]*(?:\r?\n)?", line)
    ]
    merged: dict[str, Any] = {}
    for start, end in zip(delimiters, delimiters[1:]):
        try:
            loaded = yaml.safe_load("".join(lines[start + 1 : end])) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(loaded, dict) or not (set(map(str, loaded)) & METADATA_KEYS):
            continue
        for key, value in loaded.items():
            if value not in (None, "", [], {}) or key not in merged:
                merged[str(key)] = value
    return merged


def author_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def tag_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def abstract_from(text: str) -> str:
    match = re.search(r"(?ims)^##[ \t]+Abstract[ \t]*\r?\n(.*?)(?=^##[ \t]+|\Z)", text)
    return re.sub(r"\s+", " ", match.group(1)).strip()[:6000] if match else ""


def canonical_metadata(folder: Path) -> tuple[Path | None, str, dict[str, Any]]:
    candidates = [
        path
        for path in folder.glob("*.md")
        if path.name.casefold() != "ai_summary.md"
    ]
    exact = folder / f"{folder.name}.md"
    if exact in candidates:
        candidates.remove(exact)
        candidates.insert(0, exact)
    scored: list[tuple[int, str, Path, str, dict[str, Any]]] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        metadata = frontmatter(text)
        score = sum(bool(metadata.get(key)) for key in ("title", "authors", "year"))
        score += 4 if path.name == exact.name else 0
        scored.append((score, path.name.casefold(), path, text, metadata))
    if not scored:
        return None, "", {}
    _, _, path, text, metadata = max(scored, key=lambda item: (item[0], item[1]))
    return path, text, metadata


def folder_signature(folder: Path) -> str:
    snapshot = []
    for path in sorted(folder.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            stat = path.stat()
            snapshot.append(
                {
                    "path": relative(path, folder),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
    return json_digest(snapshot)


def inventory(paths: Paths) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for folder in sorted(paths.organized.iterdir(), key=lambda item: item.name.casefold()):
        if not folder.is_dir():
            continue
        metadata_path, text, metadata = canonical_metadata(folder)
        if metadata_path is None:
            skipped.append(
                {
                    "label": folder.name,
                    "reason": "empty_folder" if not any(folder.iterdir()) else "no_metadata_note",
                }
            )
            continue
        year_match = YEAR_RE.search(str(metadata.get("year") or ""))
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "old_label": folder.name,
                "source_folder_rel": relative(folder, paths.paperhub),
                "source_metadata_rel": relative(metadata_path, paths.paperhub),
                "metadata_sha256": sha256_bytes(text.encode("utf-8")),
                "folder_signature": folder_signature(folder),
                "metadata": {
                    "title": str(metadata.get("title") or "").strip(),
                    "authors": author_list(metadata.get("authors")),
                    "year": int(year_match.group(0)) if year_match else None,
                    "journal": str(metadata.get("journal") or "").strip(),
                    "link": str(metadata.get("link") or "").strip(),
                    "created": str(metadata.get("created") or "").strip(),
                    "tags": tag_list(metadata.get("tags")),
                    "abstract": abstract_from(text),
                },
            }
        )
    return records, skipped


def inventory_digest(records: Sequence[Mapping[str, Any]], skipped: Sequence[Mapping[str, Any]]) -> str:
    compact = [
        (
            row["old_label"],
            row["source_metadata_rel"],
            row["metadata_sha256"],
            row["folder_signature"],
        )
        for row in records
    ]
    return json_digest({"records": compact, "skipped": skipped})


def inventory_command(paths: Paths) -> dict[str, Any]:
    records, skipped = inventory(paths)
    return {
        "paperhub_root": str(paths.paperhub),
        "vault_root": str(paths.vault),
        "organized_directory_count": len(records) + len(skipped),
        "mappable_record_count": len(records),
        "skipped_count": len(skipped),
        "skipped": skipped,
    }


def make_batches(paths: Paths, count: int, do_apply: bool) -> dict[str, Any]:
    if count < 1:
        raise MigrationError("batch-count must be positive")
    records, skipped = inventory(paths)
    size, remainder = divmod(len(records), count)
    batches: list[list[dict[str, Any]]] = []
    offset = 0
    for index in range(count):
        width = size + (1 if index < remainder else 0)
        batch = []
        for batch_index, record in enumerate(records[offset : offset + width], 1):
            batch.append(
                {
                    **record,
                    "batch_id": index + 1,
                    "batch_index": batch_index,
                    "action": None,
                    "proposed_label": None,
                    "confidence": None,
                    "notes": "",
                    "review_flags": [],
                }
            )
        batches.append(batch)
        offset += width
    result = {
        "record_count": len(records),
        "batch_count": count,
        "batch_sizes": [len(batch) for batch in batches],
        "skipped": skipped,
        "would_apply": not do_apply,
    }
    if not do_apply:
        return result
    paths.batches.mkdir(parents=True, exist_ok=True)
    for stale in paths.batches.glob("batch_*.input.jsonl"):
        stale.unlink()
    for stale in paths.batches.glob("batch_*.output.jsonl"):
        stale.unlink()
    for index, batch in enumerate(batches, 1):
        atomic_jsonl(paths.batches / f"batch_{index:02d}.input.jsonl", batch)
    atomic_json(
        paths.inventory,
        {
            **inventory_command(paths),
            "created_at": now(),
            "inventory_sha256": inventory_digest(records, skipped),
        },
    )
    return result


def validate_label(value: Any) -> str:
    if not isinstance(value, str) or not SAFE_LABEL_RE.fullmatch(value):
        raise MigrationError(f"Unsafe paper label: {value!r}")
    return value


def load_decisions(paths: Paths) -> list[dict[str, Any]]:
    inputs = sorted(paths.batches.glob("batch_*.input.jsonl"))
    if not inputs:
        raise MigrationError("No batch inputs; run make-batches --apply first")
    decisions: list[dict[str, Any]] = []
    for input_path in inputs:
        output_path = input_path.with_name(input_path.name.replace(".input.", ".output."))
        if not output_path.exists():
            raise MigrationError(f"Missing mapping output: {output_path}")
        expected = {row["old_label"] for row in read_jsonl(input_path)}
        output = read_jsonl(output_path)
        found = [str(row.get("old_label") or "") for row in output]
        if len(found) != len(expected) or set(found) != expected or len(found) != len(set(found)):
            raise MigrationError(f"Coverage mismatch in {output_path}")
        decisions.extend(output)
    return decisions


@dataclass(frozen=True)
class Replacement:
    target: str
    old_label: str


class Replacer:
    def __init__(self, rows: Sequence[Mapping[str, Any]], paths: Paths):
        replacements: dict[str, Replacement] = {}

        def add(source: str, target: str, old_label: str) -> None:
            if not source or source == target:
                return
            for alias in {source, unicodedata.normalize("NFC", source), unicodedata.normalize("NFD", source)}:
                previous = replacements.get(alias)
                value = Replacement(target, old_label)
                if previous is not None and previous != value:
                    raise MigrationError(f"Ambiguous replacement source: {alias!r}")
                replacements[alias] = value

        try:
            root_rel = relative(paths.paperhub, paths.vault)
        except ValueError:
            root_rel = ""
        for row in rows:
            old, new = str(row["old_label"]), str(row["new_label"])
            source_folder = str(row["source_folder_rel"])
            target_folder = str(row["target_folder_rel"])
            source_meta = str(row["source_metadata_rel"])
            target_meta = str(row["target_metadata_rel"])
            pairs = {
                old: new,
                source_folder: target_folder,
                str(paths.paperhub / source_folder): str(paths.paperhub / target_folder),
                source_meta: target_meta,
                str(paths.paperhub / source_meta): str(paths.paperhub / target_meta),
                Path(source_meta).stem: new,
            }
            if root_rel:
                pairs[f"{root_rel}/{source_folder}"] = f"{root_rel}/{target_folder}"
                pairs[f"{root_rel}/{source_meta}"] = f"{root_rel}/{target_meta}"
            for source, target in pairs.items():
                add(source, target, old)
        self.replacements = replacements
        alternatives = sorted(replacements, key=lambda value: (-len(value), value))
        self.pattern = (
            re.compile(
                r"(?<![A-Za-z0-9_])(?:"
                + "|".join(re.escape(value) for value in alternatives)
                + r")(?![A-Za-z0-9_])"
            )
            if alternatives
            else None
        )

    def replace(self, text: str) -> tuple[str, Counter[str]]:
        counts: Counter[str] = Counter()
        if self.pattern is None:
            return text, counts

        def substitute(match: re.Match[str]) -> str:
            replacement = self.replacements[match.group(0)]
            counts[replacement.old_label] += 1
            return replacement.target

        return self.pattern.sub(substitute, text), counts


def active_text_files(paths: Paths) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(paths.vault):
        dirnames[:] = [
            name
            for name in dirnames
            if name.casefold() not in EXCLUDED_DIR_NAMES
            and not name.casefold().endswith(".cache")
        ]
        directory = Path(dirpath)
        for filename in filenames:
            path = directory / filename
            if path.suffix.casefold() in TEXT_SUFFIXES and path.is_file():
                yield path


def canvas_invariant(loaded: Any) -> dict[str, Any]:
    if not isinstance(loaded, dict):
        raise MigrationError("Canvas root is not an object")
    nodes, edges = loaded.get("nodes", []), loaded.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise MigrationError("Canvas nodes or edges are malformed")
    return {
        "node_ids": sorted(str(node.get("id")) for node in nodes if isinstance(node, dict)),
        "edge_topology": [
            list(item)
            for item in sorted(
                (
                    str(edge.get("id")),
                    str(edge.get("fromNode")),
                    str(edge.get("fromSide")),
                    str(edge.get("toNode")),
                    str(edge.get("toSide")),
                )
                for edge in edges
                if isinstance(edge, dict)
            )
        ],
    }


def parse_structured(path: Path, text: str) -> dict[str, Any] | None:
    suffix = path.suffix.casefold()
    if suffix == ".canvas":
        return canvas_invariant(json.loads(text))
    if suffix == ".base":
        yaml.safe_load(text)
    elif suffix == ".md" and text.startswith("---"):
        closing = re.search(r"(?m)^---[ \t]*(?:\r?\n|$)", text[4:])
        if closing is None:
            raise MigrationError(f"Unclosed Markdown frontmatter: {path}")
        yaml.safe_load(text[4 : 4 + closing.start()])
    return None


def scan_references(
    paths: Paths, rows: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, int], list[dict[str, Any]], dict[Path, str]]:
    replacer = Replacer(rows, paths)
    totals: Counter[str] = Counter()
    touched: list[dict[str, Any]] = []
    changed: dict[Path, str] = {}
    invalid: list[str] = []
    for path in active_text_files(paths):
        text = path.read_text(encoding="utf-8")
        new_text, counts = replacer.replace(text)
        if new_text == text:
            continue
        try:
            invariant = parse_structured(path, text)
        except (json.JSONDecodeError, yaml.YAMLError, MigrationError) as exc:
            invalid.append(f"{path}: {exc}")
            continue
        totals.update(counts)
        item = {
            "vault_rel": relative(path, paths.vault),
            "sha256": sha256_bytes(text.encode("utf-8")),
            "replacement_count": sum(counts.values()),
            "counts": dict(sorted(counts.items())),
            "external_to_paperhub": not path.is_relative_to(paths.paperhub),
        }
        if invariant is not None and path.suffix.casefold() == ".canvas":
            item["canvas_invariant"] = invariant
        touched.append(item)
        changed[path] = new_text
    if invalid:
        raise MigrationError("Invalid structured source files:\n- " + "\n- ".join(invalid))
    return dict(totals), touched, changed


def build_manifest(paths: Paths) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    records, skipped = inventory(paths)
    by_old = {row["old_label"]: row for row in records}
    decisions = load_decisions(paths)
    decision_by_old = {str(row.get("old_label") or ""): row for row in decisions}
    if len(decision_by_old) != len(decisions) or set(decision_by_old) != set(by_old):
        raise MigrationError("Mapping outputs do not cover the current inventory exactly")

    targets: dict[str, str] = {}
    all_rows: list[dict[str, Any]] = []
    changed_rows: list[dict[str, Any]] = []
    occupied_unmanaged = {str(item["label"]).casefold(): str(item["label"]) for item in skipped}
    for old in sorted(by_old, key=str.casefold):
        record, decision = by_old[old], decision_by_old[old]
        action = str(decision.get("action") or "").strip().casefold()
        proposed = decision.get("proposed_label")
        if action not in {"rename", "preserve"}:
            action = "preserve" if proposed == old else "rename"
        new = old if action == "preserve" else validate_label(proposed)
        if action == "preserve" and proposed not in (None, "", old):
            raise MigrationError(f"Preserve row proposes a different label: {old}")
        folded = new.casefold()
        if folded in targets:
            raise MigrationError(f"Case-insensitive target collision: {new}, {targets[folded]}")
        if folded in occupied_unmanaged:
            raise MigrationError(f"Target {new} collides with skipped folder {occupied_unmanaged[folded]}")
        targets[folded] = new
        summary = {
            "old_label": old,
            "new_label": new,
            "action": action,
            "confidence": decision.get("confidence"),
            "notes": str(decision.get("notes") or "").strip(),
            "review_flags": [str(flag) for flag in decision.get("review_flags", []) if str(flag)],
        }
        all_rows.append(summary)
        if new == old:
            continue
        target_folder = paths.organized / new
        target_meta = target_folder / f"{new}.md"
        changed_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                **summary,
                "source_folder_rel": record["source_folder_rel"],
                "target_folder_rel": relative(target_folder, paths.paperhub),
                "source_metadata_rel": record["source_metadata_rel"],
                "target_metadata_rel": relative(target_meta, paths.paperhub),
                "metadata_sha256": record["metadata_sha256"],
                "folder_signature": record["folder_signature"],
                "metadata": {
                    key: record["metadata"][key]
                    for key in ("title", "authors", "year", "created")
                },
            }
        )

    counts, touched, _ = scan_references(paths, changed_rows)
    for row in changed_rows:
        row["expected_reference_count"] = counts.get(row["old_label"], 0)
    preflight = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now(),
        "paperhub_root": str(paths.paperhub),
        "vault_root": str(paths.vault),
        "inventory_sha256": inventory_digest(records, skipped),
        "manifest_sha256": json_digest(changed_rows),
        "mapped_record_count": len(records),
        "rename_count": len(changed_rows),
        "preserve_count": len(records) - len(changed_rows),
        "skipped": skipped,
        "expected_reference_counts": dict(sorted(counts.items())),
        "expected_reference_count": sum(counts.values()),
        "touched_files": touched,
        "touched_file_count": len(touched),
        "external_touched_file_count": sum(bool(row["external_to_paperhub"]) for row in touched),
    }
    flagged = [row for row in all_rows if row["review_flags"]]
    review_lines = [
        "# Paper-label migration review",
        "",
        f"- Mapped records: {len(records)}",
        f"- Rename proposals: {len(changed_rows)}",
        f"- Preserved labels: {len(records) - len(changed_rows)}",
        f"- Skipped directories: {len(skipped)}",
        f"- Active vault files to rewrite: {len(touched)}",
        f"- Files outside PaperHub to rewrite: {preflight['external_touched_file_count']}",
        f"- Exact replacement matches: {sum(counts.values())}",
        f"- Flagged decisions: {len(flagged)}",
        "",
        "## Flagged decisions",
        "",
        "| Old | Proposed | Action | Confidence | Flags | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for row in flagged:
        cells = [
            row["old_label"],
            row["new_label"],
            row["action"],
            str(row["confidence"] or ""),
            ", ".join(row["review_flags"]),
            row["notes"],
        ]
        review_lines.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in cells) + " |")
    review_lines.extend(["", "## Complete mapping", "", "| Old | New | Action |", "|---|---|---|"])
    for row in all_rows:
        review_lines.append(f"| `{row['old_label']}` | `{row['new_label']}` | {row['action']} |")
    return changed_rows, preflight, "\n".join(review_lines) + "\n"


def merge_command(paths: Paths, do_apply: bool) -> dict[str, Any]:
    rows, preflight, review = build_manifest(paths)
    result = {
        "mapped_record_count": preflight["mapped_record_count"],
        "rename_count": len(rows),
        "preserve_count": preflight["preserve_count"],
        "touched_file_count": preflight["touched_file_count"],
        "external_touched_file_count": preflight["external_touched_file_count"],
        "replacement_count": preflight["expected_reference_count"],
        "validated": True,
        "would_apply": not do_apply,
    }
    if do_apply:
        paths.work.mkdir(parents=True, exist_ok=True)
        atomic_jsonl(paths.manifest, rows)
        atomic_json(paths.preflight, preflight)
        atomic_text(paths.review, review)
    return result


def validate_current(
    paths: Paths, rows: Sequence[Mapping[str, Any]], preflight: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[Path, str]]:
    records, skipped = inventory(paths)
    if inventory_digest(records, skipped) != preflight.get("inventory_sha256"):
        raise MigrationError("Library inventory changed after manifest approval; rebuild it")
    if json_digest(rows) != preflight.get("manifest_sha256"):
        raise MigrationError("Manifest changed after preflight; rebuild it")
    counts, touched, changed = scan_references(paths, rows)
    expected_counts = {str(key): int(value) for key, value in preflight["expected_reference_counts"].items()}
    if counts != expected_counts:
        raise MigrationError("Reference counts changed after manifest approval")
    expected_files = {item["vault_rel"]: item["sha256"] for item in preflight["touched_files"]}
    actual_files = {item["vault_rel"]: item["sha256"] for item in touched}
    if actual_files != expected_files:
        raise MigrationError("A vault file changed after manifest approval")
    return touched, changed


def non_text_snapshot(paths: Paths, rows: Sequence[Mapping[str, Any]], *, targets: bool) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        folder_rel = row["target_folder_rel"] if targets else row["source_folder_rel"]
        folder = paths.paperhub / str(folder_rel)
        for path in sorted(folder.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_file() and path.suffix.casefold() not in TEXT_SUFFIXES:
                result.append(
                    {
                        "old_label": row["old_label"],
                        "relative_path": relative(path, folder),
                        "size": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
    return result


def backup_touched(paths: Paths, touched: Sequence[Mapping[str, Any]]) -> None:
    backup_root = paths.work / "preimage" / "vault"
    index = []
    for item in touched:
        source = paths.vault / str(item["vault_rel"])
        destination = backup_root / str(item["vault_rel"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        index.append(
            {
                "vault_rel": item["vault_rel"],
                "backup_rel": relative(destination, paths.work),
                "sha256": sha256_file(destination),
            }
        )
    atomic_json(paths.work / "preimage" / "index.json", index)


def remap_path(path: Path, rows: Sequence[Mapping[str, Any]], paths: Paths) -> Path:
    for row in rows:
        source_folder = paths.paperhub / str(row["source_folder_rel"])
        try:
            inside = path.relative_to(source_folder)
        except ValueError:
            continue
        if path == paths.paperhub / str(row["source_metadata_rel"]):
            return paths.paperhub / str(row["target_metadata_rel"])
        return paths.paperhub / str(row["target_folder_rel"]) / inside
    return path


def restore_preimages(paths: Paths) -> None:
    index_path = paths.work / "preimage" / "index.json"
    if not index_path.exists():
        return
    for item in read_json(index_path):
        source = paths.work / str(item["backup_rel"])
        target = paths.vault / str(item["vault_rel"])
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def rollback(paths: Paths, rows: Sequence[Mapping[str, Any]], state: Mapping[str, Any]) -> None:
    token = str(state.get("token") or "rollback")
    actual_folders = {path.name: path for path in paths.organized.iterdir() if path.is_dir()}
    holding: list[tuple[Path, Path]] = []
    for index, row in enumerate(rows):
        source = paths.paperhub / str(row["source_folder_rel"])
        target_name = Path(str(row["target_folder_rel"])).name
        temp_name = f".__paperhub_label_tmp__{token}_{index:04d}"
        current = actual_folders.get(target_name) or actual_folders.get(temp_name)
        if current is None:
            continue
        temporary = paths.organized / f".__paperhub_rollback__{token}_{index:04d}"
        os.replace(current, temporary)
        holding.append((temporary, source))
    for temporary, source in holding:
        os.replace(temporary, source)
    for index, row in enumerate(rows):
        folder = paths.paperhub / str(row["source_folder_rel"])
        wanted = paths.paperhub / str(row["source_metadata_rel"])
        actual = {path.name: path for path in folder.iterdir()}
        if wanted.name in actual:
            continue
        current = actual.get(f"{row['new_label']}.md") or actual.get(
            f".__paperhub_meta_tmp__{token}_{index:04d}.md"
        )
        if current is not None:
            temporary = folder / f".__paperhub_metadata_rollback__{token}_{index:04d}.md"
            os.replace(current, temporary)
            os.replace(temporary, wanted)


def old_reference_files(paths: Paths, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    replacer = Replacer(rows, paths)
    found = []
    for path in active_text_files(paths):
        _, counts = replacer.replace(path.read_text(encoding="utf-8"))
        if counts:
            found.append(f"{relative(path, paths.vault)}: {sum(counts.values())}")
    return found


def verify_applied(
    paths: Paths, rows: Sequence[Mapping[str, Any]], state: Mapping[str, Any]
) -> dict[str, Any]:
    errors: list[str] = []
    actual_folders = [path.name for path in paths.organized.iterdir() if path.is_dir()]
    folded: dict[str, list[str]] = defaultdict(list)
    for name in actual_folders:
        folded[name.casefold()].append(name)
    collisions = [names for names in folded.values() if len(names) > 1]
    if collisions:
        errors.append(f"case-insensitive folder collisions: {collisions}")
    for row in rows:
        source_name = Path(str(row["source_folder_rel"])).name
        target_name = Path(str(row["target_folder_rel"])).name
        target_meta_name = Path(str(row["target_metadata_rel"])).name
        if source_name in actual_folders:
            errors.append(f"old folder remains: {source_name}")
        if target_name not in actual_folders:
            errors.append(f"target folder missing: {target_name}")
        elif target_meta_name not in {path.name for path in (paths.organized / target_name).iterdir()}:
            errors.append(f"canonical metadata missing: {target_name}/{target_meta_name}")
    old_refs = old_reference_files(paths, rows)
    if old_refs:
        errors.append(f"old references remain in {len(old_refs)} files")
    before = read_jsonl(paths.non_text_hashes)
    after = non_text_snapshot(paths, rows, targets=True)
    comparable = lambda values: sorted(
        (item["old_label"], item["relative_path"], item["size"], item["sha256"])
        for item in values
    )
    if comparable(before) != comparable(after):
        errors.append("non-text paper files changed")
    preflight = read_json(paths.preflight)
    canvas_expected = {
        item["vault_rel"]: item["canvas_invariant"]
        for item in preflight["touched_files"]
        if "canvas_invariant" in item
    }
    structured_errors = []
    for after_rel in state.get("changed_files_after", []):
        path = paths.vault / str(after_rel)
        try:
            invariant = parse_structured(path, path.read_text(encoding="utf-8"))
            if invariant is not None and path.suffix.casefold() == ".canvas":
                before_rel = next(
                    (
                        old_rel
                        for old_rel in state.get("changed_files_before", [])
                        if remap_path(paths.vault / str(old_rel), rows, paths) == path
                    ),
                    after_rel,
                )
                if canvas_expected.get(before_rel) != invariant:
                    raise MigrationError("Canvas IDs or edge topology changed")
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError, MigrationError) as exc:
            structured_errors.append(f"{after_rel}: {exc}")
    if structured_errors:
        errors.append(f"{len(structured_errors)} structured files failed: {structured_errors[:10]}")
    return {
        "schema_version": SCHEMA_VERSION,
        "verified_at": now(),
        "status": "pass" if not errors else "fail",
        "rename_count": len(rows),
        "organized_directory_count": len(actual_folders),
        "case_insensitive_collision_count": len(collisions),
        "old_reference_file_count": len(old_refs),
        "non_text_file_count": len(after),
        "changed_structured_file_count": len(state.get("changed_files_after", [])),
        "errors": errors,
    }


def apply_command(paths: Paths, do_apply: bool) -> dict[str, Any]:
    if not paths.manifest.exists() or not paths.preflight.exists():
        raise MigrationError("Run merge --apply before apply")
    rows, preflight = read_jsonl(paths.manifest), read_json(paths.preflight)
    if paths.state.exists() and read_json(paths.state).get("status") == "applied":
        raise MigrationError("Migration is already applied; run verify")
    touched, changed = validate_current(paths, rows, preflight)
    preview = {
        "validated": True,
        "rename_count": len(rows),
        "touched_file_count": len(touched),
        "external_touched_file_count": sum(bool(item["external_to_paperhub"]) for item in touched),
        "replacement_count": sum(item["replacement_count"] for item in touched),
        "would_apply": not do_apply,
    }
    if not do_apply:
        return preview
    paths.work.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(paths.non_text_hashes, non_text_snapshot(paths, rows, targets=False))
    backup_touched(paths, touched)
    token = uuid.uuid4().hex
    state = {
        "schema_version": SCHEMA_VERSION,
        "status": "applying",
        "started_at": now(),
        "token": token,
        "changed_files_before": [item["vault_rel"] for item in touched],
        "changed_files_after": [],
    }
    atomic_json(paths.state, state)
    try:
        for index, row in enumerate(rows):
            source_folder = paths.paperhub / str(row["source_folder_rel"])
            source_meta = paths.paperhub / str(row["source_metadata_rel"])
            temp_meta = source_folder / f".__paperhub_meta_tmp__{token}_{index:04d}.md"
            os.replace(source_meta, temp_meta)
            temp_folder = paths.organized / f".__paperhub_label_tmp__{token}_{index:04d}"
            os.replace(source_folder, temp_folder)
        for index, row in enumerate(rows):
            temp_folder = paths.organized / f".__paperhub_label_tmp__{token}_{index:04d}"
            target_folder = paths.paperhub / str(row["target_folder_rel"])
            os.replace(temp_folder, target_folder)
            temp_meta = target_folder / f".__paperhub_meta_tmp__{token}_{index:04d}.md"
            os.replace(temp_meta, paths.paperhub / str(row["target_metadata_rel"]))
        changed_after = []
        for old_path, new_text in changed.items():
            final_path = remap_path(old_path, rows, paths)
            if not final_path.exists():
                raise MigrationError(f"Rewrite target disappeared: {final_path}")
            atomic_text(final_path, new_text, mode_from=final_path)
            changed_after.append(relative(final_path, paths.vault))
        state["changed_files_after"] = changed_after
        atomic_json(paths.state, state)
        report = verify_applied(paths, rows, state)
        atomic_json(paths.verification, report)
        if report["status"] != "pass":
            raise MigrationError("Post-apply verification failed: " + "; ".join(report["errors"]))
        state["status"] = "applied"
        state["completed_at"] = now()
        atomic_json(paths.state, state)
        return {**preview, "would_apply": False, "verification": report}
    except BaseException:
        with contextlib.suppress(Exception):
            rollback(paths, rows, state)
        with contextlib.suppress(Exception):
            restore_preimages(paths)
        state["status"] = "rolled_back_after_error"
        state["rolled_back_at"] = now()
        with contextlib.suppress(Exception):
            atomic_json(paths.state, state)
        raise


def verify_command(paths: Paths, do_write: bool) -> dict[str, Any]:
    rows = read_jsonl(paths.manifest)
    state = read_json(paths.state)
    if state.get("status") != "applied":
        raise MigrationError("Migration is not marked applied")
    report = verify_applied(paths, rows, state)
    if do_write:
        atomic_json(paths.verification, report)
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--paperhub-root")
    result.add_argument("--vault-root")
    result.add_argument("--organized-dir", default="organized")
    result.add_argument("--work-dir", default=".paperhub_tmp/update_label_format")
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    batches = subparsers.add_parser("make-batches")
    batches.add_argument("--batch-count", type=int, default=10)
    batches.add_argument("--apply", action="store_true")
    merge = subparsers.add_parser("merge")
    merge.add_argument("--apply", action="store_true")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--apply", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--apply", action="store_true", help="refresh verification.json")
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        paths = resolve_paths(args)
        if args.command == "inventory":
            result = inventory_command(paths)
        elif args.command == "make-batches":
            result = make_batches(paths, args.batch_count, args.apply)
        elif args.command == "merge":
            result = merge_command(paths, args.apply)
        elif args.command == "apply":
            result = apply_command(paths, args.apply)
        elif args.command == "verify":
            result = verify_command(paths, args.apply)
        else:  # pragma: no cover
            raise MigrationError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except (MigrationError, OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"ABORTED: {exc}") from exc


if __name__ == "__main__":
    main()
