#!/usr/bin/env python3
"""Update PaperHub skills and utility files from the public template repo.

The updater is intentionally conservative. It can replace framework files that
are unchanged locally, but prompt fragments and locally edited framework files
are surfaced for agent review instead of being overwritten.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_URL = "https://github.com/howieeeeeeeeee/paper-management-system"
DEFAULT_VERSION = "2026.07.06.2"
CURRENT_CONFIG_SCHEMA = 4
CITATION_CONFIG_DEFAULTS = {
    "resolve_after_organize": False,
    "current_agent_search_missing_link": True,
    "preferred_style": "chicago-author-date",
}
STATE_PATH = Path("paperhub_utils/config/utility_state.json")
CONFIG_PATH = Path("paperhub_utils/config/config.json")
REPORT_DIR = Path("paperhub_utils/output/update_reports")
BACKUP_DIR = Path("paperhub_utils/output/update_backups")

DEFAULT_MANIFEST: dict[str, Any] = {
    "schema_version": 1,
    "version": DEFAULT_VERSION,
    "source_url": DEFAULT_SOURCE_URL,
    "path_policy": {
        "replaceable_utility_code": [
            "paperhub_utils/scripts/**",
            "paperhub_utils/paperhub/**",
            "paperhub_utils/tests/**",
            "paperhub_utils/pyproject.toml",
            "paperhub_utils/uv.lock",
        ],
        "merge_aware_defaults": [
            "paperhub_utils/prompts/**",
        ],
        "preserve_user_config": [
            "paperhub_utils/config/.env",
            "paperhub_utils/config/config.json",
            "paperhub_utils/config/onboarding.json",
            "paperhub_utils/config/utility_state.json",
            "paperhub_utils/output/**",
        ],
    },
    "managed_paths": [
        ".agents/skills/**",
        ".claude/skills/**",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "SamplePaperBoard.base",
        "onboarding_questionnaire.md",
        "quick_start/**",
        "paperhub_utils/README.md",
        "paperhub_utils/config/.env.example",
        "paperhub_utils/config/default_tags.yaml",
        "paperhub_utils/paperhub/**",
        "paperhub_utils/prompts/**",
        "paperhub_utils/scripts/**",
        "paperhub_utils/utility_changelog.json",
        "paperhub_utils/utility_manifest.json",
        "paperhub_utils/tests/**",
        "paperhub_utils/pyproject.toml",
        "paperhub_utils/uv.lock",
    ],
    "prompt_paths": [
        "paperhub_utils/prompts/**/*.txt",
    ],
    "protected_paths": [
        ".git/**",
        ".obsidian/**",
        ".agents/skills/public-template-sync/**",
        ".claude/settings.local.json",
        ".claude/scheduled_tasks*",
        ".claude/skills/public-template-sync/**",
        "Papers.base",
        "organized/**",
        "tags/_internal/**",
        "to_be_organized/**",
        "paperhub_utils/config/.env",
        "paperhub_utils/config/config.json",
        "paperhub_utils/config/onboarding.json",
        "paperhub_utils/config/utility_state.json",
        "paperhub_utils/config/.env",
        "paperhub_utils/.venv/**",
        "paperhub_utils/.pytest_cache/**",
        "paperhub_utils/__pycache__/**",
        "paperhub_utils/config/config.json",
        "paperhub_utils/config/onboarding.json",
        "paperhub_utils/misc/utility_state.json",
        "paperhub_utils/output/**",
        "paperhub_utils/output/raw_outputs/**",
    ],
}


@dataclass(frozen=True)
class FileDecision:
    path: str
    action: str
    reason: str
    local_sha256: str | None = None
    upstream_sha256: str | None = None
    installed_sha256: str | None = None


@dataclass(frozen=True)
class UpdatePlan:
    source_url: str
    version: str
    installed_version: str | None
    generated_at: str
    changelog_entries: list[dict[str, Any]]
    decisions: list[FileDecision]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for decision in self.decisions:
            out[decision.action] = out.get(decision.action, 0) + 1
        return out

    def verdict(self) -> str:
        """Summarize how much of this copy the user has diverged from upstream.

        Drives how much the updater needs to ask:

        ``clean``             nothing locally modified — apply everything silently.
        ``prompts-only``      only prompt files diverge — merge those, rest is safe.
        ``framework-modified`` skills or utility code diverge — needs decisions.
        ``no-baseline``       no recorded install state, so local edits are
                              indistinguishable from upstream drift. Treated as
                              modified: without this, every differing file would
                              silently fall through to ``replace``.
        """
        actions = {decision.action for decision in self.decisions}
        if any(
            decision.installed_sha256 is None
            and decision.action not in {"add", "unchanged"}
            for decision in self.decisions
        ):
            return "no-baseline"
        if actions & {"needs_review"}:
            return "framework-modified"
        if actions & {"needs_agent_merge", "preserve_local"}:
            return "prompts-only"
        return "clean"

    def needs_decisions(self) -> list[FileDecision]:
        """Files the agent must resolve with the user before recording the update."""
        return [
            decision
            for decision in self.decisions
            if decision.action in {"needs_agent_merge", "needs_review"}
        ]


def repo_root_from_script() -> Path:
    """Return the PROJECT root, the base every path constant is relative to.

    This file is ``<project>/paperhub_utils/scripts/update_utils.py``, so the
    project root is two levels up. Returning ``parents[1]`` (``paperhub_utils/``)
    makes every managed path resolve one level too deep — managed files look
    missing, so they are "added" into a nested ``paperhub_utils/paperhub_utils/``
    tree, the install state is never found, and ``README.md`` resolves onto
    ``paperhub_utils/README.md`` and overwrites it.
    """
    return Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "paperhub_utils/utility_manifest.json"
    manifest = load_json(manifest_path, DEFAULT_MANIFEST)
    merged = dict(DEFAULT_MANIFEST)
    merged.update(manifest)
    for key in ("managed_paths", "prompt_paths", "protected_paths"):
        if not isinstance(merged.get(key), list):
            merged[key] = DEFAULT_MANIFEST[key]
    return merged


def installed_version_from_state_or_config(
    local_root: Path,
    state: dict[str, Any],
) -> str | None:
    value = state.get("installed_version")
    if isinstance(value, str) and value.strip():
        return value.strip()

    config = load_json(local_root / CONFIG_PATH, {})
    utility_config = config.get("paperhub_utils")
    if isinstance(utility_config, dict):
        value = utility_config.get("installed_version")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def version_key(version: str | None) -> tuple[int, ...]:
    """Return a sortable key for YYYY.MM.DD.N-style versions.

    Legacy date-only versions such as 2026.07.05 sort before 2026.07.05.1.
    """
    if not version:
        return ()
    parts = [int(part) for part in re.findall(r"\d+", version)]
    if len(parts) == 3:
        parts.append(0)
    return tuple(parts)


def load_changelog(root: Path) -> dict[str, Any]:
    return load_json(root / "paperhub_utils/utility_changelog.json", {})


def changelog_entries_between(
    changelog: dict[str, Any],
    installed_version: str | None,
    latest_version: str,
) -> list[dict[str, Any]]:
    entries = changelog.get("entries")
    if not isinstance(entries, dict):
        return []

    lower = version_key(installed_version)
    upper = version_key(latest_version)
    selected: list[dict[str, Any]] = []
    for version, raw_entry in sorted(entries.items(), key=lambda item: version_key(item[0])):
        key = version_key(version)
        if lower and key <= lower:
            continue
        if upper and key > upper:
            continue
        if not isinstance(raw_entry, dict):
            continue
        entry = dict(raw_entry)
        entry["version"] = version
        selected.append(entry)
    return selected


def clone_or_copy_source(source_url: str, destination: Path) -> None:
    source_path = Path(source_url).expanduser()
    if source_path.exists():
        shutil.copytree(
            source_path,
            destination,
            ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"),
        )
        return

    subprocess.run(
        ["git", "clone", "--depth", "1", source_url, str(destination)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def path_matches(rel_path: str, patterns: list[str]) -> bool:
    rel_path = rel_path.strip("/")
    for pattern in patterns:
        pattern = pattern.strip("/")
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if rel_path == prefix or rel_path.startswith(prefix + "/"):
                return True
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def expand_managed_files(root: Path, manifest: dict[str, Any]) -> list[str]:
    protected = manifest["protected_paths"]
    files: set[str] = set()
    for pattern in manifest["managed_paths"]:
        pattern = str(pattern).strip("/")
        if pattern.endswith("/**"):
            base = root / pattern[:-3].rstrip("/")
            candidates = base.rglob("*") if base.exists() else []
        elif any(ch in pattern for ch in "*?["):
            candidates = root.glob(pattern)
        else:
            candidate = root / pattern
            if candidate.is_dir():
                candidates = candidate.rglob("*")
            else:
                candidates = [candidate]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            rel_path = candidate.relative_to(root).as_posix()
            if path_matches(rel_path, protected):
                continue
            files.add(rel_path)
    return sorted(files)


def installed_file_state(state: dict[str, Any], rel_path: str) -> str | None:
    files = state.get("files")
    if not isinstance(files, dict):
        return None
    row = files.get(rel_path)
    if isinstance(row, dict):
        value = row.get("sha256")
        return value if isinstance(value, str) else None
    if isinstance(row, str):
        return row
    return None


def build_update_plan(
    local_root: Path,
    upstream_root: Path,
    manifest: dict[str, Any],
    state: dict[str, Any],
    source_url: str | None = None,
) -> UpdatePlan:
    decisions: list[FileDecision] = []
    prompt_paths = manifest["prompt_paths"]
    protected_paths = manifest["protected_paths"]
    version = str(manifest.get("version") or DEFAULT_VERSION)
    installed_version = installed_version_from_state_or_config(local_root, state)
    changelog = load_changelog(upstream_root)
    changelog_entries = changelog_entries_between(
        changelog,
        installed_version,
        version,
    )
    upstream_files = expand_managed_files(upstream_root, manifest)

    for rel_path in upstream_files:
        if path_matches(rel_path, protected_paths):
            continue
        local_path = local_root / rel_path
        upstream_path = upstream_root / rel_path
        upstream_sha = sha256_file(upstream_path)
        installed_sha = installed_file_state(state, rel_path)

        if not local_path.exists():
            decisions.append(
                FileDecision(
                    path=rel_path,
                    action="add",
                    reason="file exists upstream but not locally",
                    upstream_sha256=upstream_sha,
                    installed_sha256=installed_sha,
                )
            )
            continue

        local_sha = sha256_file(local_path)
        if local_sha == upstream_sha:
            decisions.append(
                FileDecision(
                    path=rel_path,
                    action="unchanged",
                    reason="local file already matches upstream",
                    local_sha256=local_sha,
                    upstream_sha256=upstream_sha,
                    installed_sha256=installed_sha,
                )
            )
            continue

        is_prompt = path_matches(rel_path, prompt_paths)
        if is_prompt:
            if installed_sha and local_sha == installed_sha:
                action = "replace"
                reason = "prompt was not locally customized since last install"
            elif installed_sha and upstream_sha == installed_sha:
                action = "preserve_local"
                reason = "local prompt changed and upstream prompt did not"
            else:
                action = "needs_agent_merge"
                reason = "local prompt and upstream prompt differ"
        elif installed_sha and local_sha != installed_sha and upstream_sha != installed_sha:
            action = "needs_review"
            reason = "local framework file changed since last install"
        else:
            action = "replace"
            reason = "framework file differs from upstream"

        decisions.append(
            FileDecision(
                path=rel_path,
                action=action,
                reason=reason,
                local_sha256=local_sha,
                upstream_sha256=upstream_sha,
                installed_sha256=installed_sha,
            )
        )

    return UpdatePlan(
        source_url=source_url or str(manifest.get("source_url") or DEFAULT_SOURCE_URL),
        version=version,
        installed_version=installed_version,
        generated_at=utc_now(),
        changelog_entries=changelog_entries,
        decisions=decisions,
    )


def backup_local_file(local_root: Path, rel_path: str, backup_root: Path) -> None:
    source = local_root / rel_path
    if not source.exists():
        return
    destination = backup_root / rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


RESEARCH_INTERESTS_REL = "paperhub_utils/config/research_interests.md"
# Onboarding documented a triple-quoted block, but hand-edited copies may hold a
# plain one-line string. Try the triple forms first so a `"""` is never matched
# as an empty `"` pair; the single-line body must not cross a newline.
LEGACY_INTERESTS_RE = re.compile(
    r"^MY_RESEARCH_INTERESTS[ \t]*=[ \t]*"
    r"(?:"
    r"(?P<triple>\"\"\"|''')(?P<triple_body>.*?)(?P=triple)"
    r"|"
    r"(?P<quote>[\"'])(?P<line_body>(?:[^\\\n]|\\.)*?)(?P=quote)"
    r")",
    re.MULTILINE | re.DOTALL,
)


def _legacy_interests_body(text: str) -> str:
    match = LEGACY_INTERESTS_RE.search(text)
    if not match:
        return ""
    body = match.group("triple_body")
    if body is None:
        body = match.group("line_body") or ""
    return body.strip()


def migrate_research_interests(local_root: Path) -> dict[str, Any]:
    """Rescue research interests from the pre-2026.07.28 location.

    They used to live inline in ``paperhub/config.py``, which is update-managed,
    so applying an update would overwrite them. Extract any local value into the
    protected ``config/research_interests.md`` *before* config.py is replaced.
    No-ops once the protected file exists, so it is safe to call every run.
    """
    target = local_root / RESEARCH_INTERESTS_REL
    if target.exists():
        return {"migrated": False, "reason": "protected file already present"}

    config_py = local_root / "paperhub_utils/paperhub/config.py"
    try:
        text = config_py.read_text(encoding="utf-8")
    except OSError:
        return {"migrated": False, "reason": "no local config.py to migrate from"}

    body = _legacy_interests_body(text)
    if not body:
        return {"migrated": False, "reason": "no inline research interests found"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body + "\n", encoding="utf-8")
    return {"migrated": True, "path": RESEARCH_INTERESTS_REL, "characters": len(body)}


def apply_update_plan(
    local_root: Path,
    upstream_root: Path,
    plan: UpdatePlan,
) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = local_root / BACKUP_DIR / timestamp
    applied: list[str] = []
    skipped: list[str] = []

    # Must run before any file is replaced.
    research_interests = migrate_research_interests(local_root)

    for decision in plan.decisions:
        if decision.action not in {"add", "replace"}:
            if decision.action in {"needs_agent_merge", "needs_review"}:
                skipped.append(decision.path)
            continue
        local_path = local_root / decision.path
        upstream_path = upstream_root / decision.path
        if local_path.exists():
            backup_local_file(local_root, decision.path, backup_root)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(upstream_path, local_path)
        applied.append(decision.path)

    result = {
        "applied": applied,
        "skipped": skipped,
        "backup_dir": str(backup_root.relative_to(local_root)) if applied else None,
        "research_interests_migration": research_interests,
    }
    return result


def record_current_state(
    local_root: Path,
    upstream_root: Path,
    manifest: dict[str, Any],
    version: str,
) -> dict[str, Any]:
    state_files: dict[str, dict[str, str]] = {}
    for rel_path in expand_managed_files(upstream_root, manifest):
        local_path = local_root / rel_path
        if local_path.is_file():
            state_files[rel_path] = {"sha256": sha256_file(local_path)}

    state = {
        "schema_version": 1,
        "installed_version": version,
        "updated_at": utc_now(),
        "files": state_files,
    }
    write_json(local_root / STATE_PATH, state)
    update_config_version(local_root, version=version, pending_version=None)
    return state


def update_config_version(
    local_root: Path,
    *,
    version: str | None = None,
    pending_version: str | None = None,
) -> None:
    config_path = local_root / CONFIG_PATH
    config = load_json(config_path, {"schema_version": 1})
    try:
        current_schema = int(config.get("schema_version", 1))
    except (TypeError, ValueError):
        current_schema = 1
    config["schema_version"] = max(current_schema, CURRENT_CONFIG_SCHEMA)
    citation_config = config.get("citations")
    if not isinstance(citation_config, dict):
        citation_config = {}
    for key, default in CITATION_CONFIG_DEFAULTS.items():
        citation_config.setdefault(key, default)
    config["citations"] = citation_config
    utility_config = config.get("paperhub_utils")
    if not isinstance(utility_config, dict):
        utility_config = {}
    if version is not None:
        utility_config["installed_version"] = version
    utility_config["last_update_check"] = utc_now()
    utility_config["pending_version"] = pending_version
    config["paperhub_utils"] = utility_config
    write_json(config_path, config)


def write_report(local_root: Path, plan: UpdatePlan, result: dict[str, Any] | None) -> Path:
    report = {
        "plan": {
            "source_url": plan.source_url,
            "version": plan.version,
            "installed_version": plan.installed_version,
            "generated_at": plan.generated_at,
            "changelog_entries": plan.changelog_entries,
            "counts": plan.counts(),
            "decisions": [asdict(decision) for decision in plan.decisions],
        },
        "result": result,
    }
    report_dir = local_root / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    write_json(report_path, report)
    return report_path


def plan_to_json(plan: UpdatePlan, result: dict[str, Any] | None = None) -> str:
    payload = {
        "source_url": plan.source_url,
        "version": plan.version,
        "installed_version": plan.installed_version,
        "generated_at": plan.generated_at,
        "changelog_entries": plan.changelog_entries,
        "verdict": plan.verdict(),
        "counts": plan.counts(),
        "decisions": [asdict(decision) for decision in plan.decisions],
        "result": result,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


VERDICT_GUIDANCE = {
    "clean": "No local modifications. Safe to apply everything without asking.",
    "prompts-only": "Only prompt files diverge. Merge those; everything else is safe.",
    "framework-modified": (
        "Skills or utility code were edited locally. Resolve each file with the user "
        "before recording the update."
    ),
    "no-baseline": (
        "No recorded install state, so local edits cannot be told apart from upstream "
        "drift. Treat every differing file as locally modified and confirm before "
        "replacing it."
    ),
}


def print_human_summary(plan: UpdatePlan, result: dict[str, Any] | None = None) -> None:
    print(f"PaperHub utility update: {plan.version}")
    print(f"Installed version: {plan.installed_version or 'unknown'}")
    print(f"Source: {plan.source_url}")
    verdict = plan.verdict()
    print(f"\nVerdict: {verdict}")
    print(f"  {VERDICT_GUIDANCE[verdict]}")
    if plan.changelog_entries:
        print("\nRelevant changelog entries:")
        for entry in plan.changelog_entries:
            print(
                f"  {entry.get('version')}: {entry.get('title', 'Untitled')} "
                f"({entry.get('update_kind', 'unspecified')})"
            )
            how_to_apply = str(entry.get("how_to_apply") or "").strip()
            if how_to_apply:
                print(f"    How to apply: {how_to_apply}")
    else:
        print("\nRelevant changelog entries: none")
    print("Actions:")
    for action, count in sorted(plan.counts().items()):
        print(f"  {action}: {count}")
    blocking = [
        decision for decision in plan.decisions
        if decision.action in {"needs_agent_merge", "needs_review"}
    ]
    if blocking:
        print("\nNeeds agent review:")
        for decision in blocking:
            print(f"  {decision.path}: {decision.reason}")
    if result:
        print("\nApplied:")
        print(f"  files: {len(result.get('applied', []))}")
        if result.get("backup_dir"):
            print(f"  backup: {result['backup_dir']}")
        if result.get("skipped"):
            print(f"  skipped: {len(result['skipped'])} (must be resolved before recording)")
        migration = result.get("research_interests_migration") or {}
        if migration.get("migrated"):
            print(f"  research interests rescued to: {migration['path']}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--check", action="store_true", help="show the update plan")
    parser.add_argument("--apply", action="store_true", help="apply safe updates")
    parser.add_argument(
        "--record-current",
        action="store_true",
        help="record current managed files as the installed version after manual merges",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    local_root = repo_root_from_script()
    state = load_json(local_root / STATE_PATH, {})

    with tempfile.TemporaryDirectory(prefix="paperhub_update_") as tmp:
        upstream_root = Path(tmp) / "upstream"
        try:
            clone_or_copy_source(args.source_url, upstream_root)
        except subprocess.CalledProcessError as exc:
            print("Failed to fetch update source.", file=sys.stderr)
            if exc.stderr:
                print(exc.stderr.strip(), file=sys.stderr)
            return 2

        manifest = load_manifest(upstream_root)
        plan = build_update_plan(
            local_root=local_root,
            upstream_root=upstream_root,
            manifest=manifest,
            state=state,
            source_url=args.source_url,
        )
        result = None
        if args.apply:
            result = apply_update_plan(local_root, upstream_root, plan)
            pending = result["skipped"] or None
            if pending:
                update_config_version(
                    local_root,
                    version=None,
                    pending_version=plan.version,
                )
            else:
                record_current_state(local_root, upstream_root, manifest, plan.version)
        if args.record_current:
            record_current_state(local_root, upstream_root, manifest, plan.version)
        report_path = write_report(local_root, plan, result)

    if args.json:
        print(plan_to_json(plan, result))
    else:
        print_human_summary(plan, result)
        print(f"\nReport: {report_path.relative_to(local_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
