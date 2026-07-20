#!/usr/bin/env python3
"""Check or refresh PaperHub's pinned kepano/obsidian-skills snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_URL = "https://github.com/kepano/obsidian-skills.git"
SOURCE_REF = "main"
LOCK_NAME = "upstream-lock.json"
MIRROR_NAME = "skills"
LICENSE_NAME = "LICENSE"


class SyncError(RuntimeError):
    """A safe, user-actionable upstream synchronization failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_lock(skill_root: Path) -> dict[str, Any] | None:
    path = skill_root / LOCK_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"cannot read {LOCK_NAME}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SyncError(f"unsupported or malformed {LOCK_NAME}")
    return payload


def _safe_relative(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise SyncError(f"unsafe path outside source root: {path}") from exc
    if relative.is_absolute() or ".." in relative.parts:
        raise SyncError(f"unsafe relative path: {relative}")
    return relative.as_posix()


def validate_source_tree(source_root: Path) -> tuple[list[str], dict[str, str]]:
    skills_root = source_root / MIRROR_NAME
    license_path = source_root / LICENSE_NAME
    if not skills_root.is_dir():
        raise SyncError("upstream source has no skills/ directory")
    if not license_path.is_file() or license_path.is_symlink():
        raise SyncError("upstream LICENSE is missing or is a symlink")

    hashes: dict[str, str] = {LICENSE_NAME: sha256_file(license_path)}
    skill_names: list[str] = []
    for child in sorted(skills_root.iterdir(), key=lambda item: item.name):
        if child.is_symlink():
            raise SyncError(f"upstream contains a symlink: {child.name}")
        if not child.is_dir():
            raise SyncError(f"unexpected non-directory in skills/: {child.name}")
        if not (child / "SKILL.md").is_file():
            raise SyncError(f"upstream skill lacks SKILL.md: {child.name}")
        skill_names.append(child.name)

    for path in sorted(skills_root.rglob("*")):
        _safe_relative(path, source_root)
        if path.is_symlink():
            raise SyncError(
                f"upstream contains a symlink: {_safe_relative(path, source_root)}"
            )
        if path.is_file():
            hashes[_safe_relative(path, source_root)] = sha256_file(path)

    if not skill_names:
        raise SyncError("upstream skills/ directory is empty")
    return skill_names, hashes


def local_snapshot(skill_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    license_path = skill_root / LICENSE_NAME
    if license_path.is_symlink():
        raise SyncError("local LICENSE is a symlink")
    if license_path.is_file():
        hashes[LICENSE_NAME] = sha256_file(license_path)

    mirror_root = skill_root / MIRROR_NAME
    if mirror_root.is_symlink():
        raise SyncError("local skills mirror is a symlink")
    if mirror_root.exists() and not mirror_root.is_dir():
        raise SyncError("local skills mirror is not a directory")
    if mirror_root.is_dir():
        for path in sorted(mirror_root.rglob("*")):
            _safe_relative(path, skill_root)
            if path.is_symlink():
                raise SyncError(
                    f"local mirror contains a symlink: {_safe_relative(path, skill_root)}"
                )
            if path.is_file():
                hashes[_safe_relative(path, skill_root)] = sha256_file(path)
    return hashes


def local_drift(skill_root: Path, lock: dict[str, Any] | None) -> list[str]:
    if lock is None:
        return []
    expected = lock.get("files")
    if not isinstance(expected, dict):
        raise SyncError(f"malformed files map in {LOCK_NAME}")
    actual = local_snapshot(skill_root)
    drift: list[str] = []
    for path in sorted(set(actual) | set(expected)):
        if actual.get(path) != expected.get(path):
            drift.append(path)
    return drift


def build_report(
    skill_root: Path,
    source_root: Path,
    candidate_commit: str,
) -> dict[str, Any]:
    candidate_skills, candidate_files = validate_source_tree(source_root)
    lock = load_lock(skill_root)
    installed_files = lock.get("files", {}) if lock else {}
    installed_skills = lock.get("skills", []) if lock else []
    if not isinstance(installed_files, dict) or not isinstance(installed_skills, list):
        raise SyncError(f"malformed {LOCK_NAME}")

    added = sorted(set(candidate_files) - set(installed_files))
    removed = sorted(set(installed_files) - set(candidate_files))
    modified = sorted(
        path
        for path in set(candidate_files) & set(installed_files)
        if candidate_files[path] != installed_files[path]
    )
    added_skills = sorted(set(candidate_skills) - set(installed_skills))
    removed_skills = sorted(set(installed_skills) - set(candidate_skills))
    drift = local_drift(skill_root, lock)

    if lock is None:
        status = "not_installed"
    elif drift:
        status = "local_drift"
    elif added or modified or removed:
        status = "update_available"
    elif lock.get("commit") != candidate_commit:
        status = "source_advanced_without_mirrored_changes"
    else:
        status = "current"

    return {
        "schema_version": 1,
        "source_url": SOURCE_URL,
        "ref": SOURCE_REF,
        "installed_commit": lock.get("commit") if lock else None,
        "candidate_commit": candidate_commit,
        "status": status,
        "structural": bool(lock and (added_skills or removed_skills)),
        "added_skills": added_skills,
        "removed_skills": removed_skills,
        "added_files": added,
        "modified_files": modified,
        "removed_files": removed,
        "local_drift": drift,
        "candidate_skills": candidate_skills,
        "candidate_files": candidate_files,
    }


def require_maintainer(repo_root: Path) -> None:
    marker = repo_root / ".claude/skills/public-template-sync/SKILL.md"
    if not marker.is_file():
        raise SyncError(
            "direct upstream refresh is maintainer-only; run "
            "update-paperhub-utils to receive reviewed PaperHub updates"
        )


def clone_upstream(destination: Path) -> str:
    try:
        completed = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                SOURCE_REF,
                SOURCE_URL,
                str(destination),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SyncError("git is required to fetch the upstream skills") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "git clone failed").strip()
        raise SyncError(f"failed to fetch upstream: {detail}") from exc
    if completed.returncode != 0:
        raise SyncError("failed to fetch upstream")
    try:
        result = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SyncError("failed to resolve the upstream commit") from exc
    commit = result.stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise SyncError(f"unexpected upstream commit value: {commit!r}")
    return commit


def _replace_snapshot(skill_root: Path, source_root: Path) -> None:
    mirror = skill_root / MIRROR_NAME
    license_path = skill_root / LICENSE_NAME
    staged_mirror = skill_root / f".{MIRROR_NAME}.next"
    staged_license = skill_root / f".{LICENSE_NAME}.next"
    previous_mirror = skill_root / f".{MIRROR_NAME}.previous"
    previous_license = skill_root / f".{LICENSE_NAME}.previous"

    for transient in (staged_mirror, staged_license, previous_mirror, previous_license):
        if transient.exists():
            raise SyncError(f"stale synchronization artifact exists: {transient.name}")

    shutil.copytree(source_root / MIRROR_NAME, staged_mirror, copy_function=shutil.copy2)
    shutil.copy2(source_root / LICENSE_NAME, staged_license)
    moved_mirror = False
    moved_license = False
    try:
        if mirror.exists():
            os.replace(mirror, previous_mirror)
            moved_mirror = True
        if license_path.exists():
            os.replace(license_path, previous_license)
            moved_license = True
        os.replace(staged_mirror, mirror)
        os.replace(staged_license, license_path)
    except Exception:
        if mirror.exists() and moved_mirror:
            shutil.rmtree(mirror)
        if moved_mirror and previous_mirror.exists():
            os.replace(previous_mirror, mirror)
        if license_path.exists() and moved_license:
            license_path.unlink()
        if moved_license and previous_license.exists():
            os.replace(previous_license, license_path)
        raise
    finally:
        if staged_mirror.exists():
            shutil.rmtree(staged_mirror)
        if staged_license.exists():
            staged_license.unlink()

    if previous_mirror.exists():
        shutil.rmtree(previous_mirror)
    if previous_license.exists():
        previous_license.unlink()


def apply_snapshot(
    skill_root: Path,
    source_root: Path,
    candidate_commit: str,
    *,
    allow_structural: bool = False,
) -> dict[str, Any]:
    report = build_report(skill_root, source_root, candidate_commit)
    if report["local_drift"]:
        raise SyncError(
            "local mirror differs from upstream-lock.json; review the drift before applying"
        )
    if report["structural"] and not allow_structural:
        raise SyncError(
            "upstream skill set changed; review it and rerun with --allow-structural"
        )

    _replace_snapshot(skill_root, source_root)
    skill_names, file_hashes = validate_source_tree(source_root)
    lock = {
        "schema_version": 1,
        "source_url": SOURCE_URL,
        "ref": SOURCE_REF,
        "commit": candidate_commit,
        "imported_at": utc_now(),
        "skills": skill_names,
        "files": file_hashes,
    }
    write_json_atomic(skill_root / LOCK_NAME, lock)
    report["status"] = "applied"
    report["applied"] = True
    report.pop("candidate_files", None)
    return report


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[4]


def skill_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report available changes")
    mode.add_argument("--apply", action="store_true", help="apply the reviewed snapshot")
    parser.add_argument(
        "--allow-structural",
        action="store_true",
        help="allow added or removed top-level upstream skills",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = repo_root_from_script()
    skill_root = skill_root_from_script()
    try:
        require_maintainer(repo_root)
        with tempfile.TemporaryDirectory(prefix="paperhub_obsidian_upstream_") as tmp:
            source_root = Path(tmp) / "upstream"
            candidate_commit = clone_upstream(source_root)
            if args.apply:
                report = apply_snapshot(
                    skill_root,
                    source_root,
                    candidate_commit,
                    allow_structural=args.allow_structural,
                )
            else:
                report = build_report(skill_root, source_root, candidate_commit)
                report.pop("candidate_files", None)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except SyncError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
