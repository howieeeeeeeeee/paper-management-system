"""Generate the tag registry: one consolidated table + JSON mirror + cheap name lists.

Layout produced under `tags/`:
    tags_summary.md         single table of ALL tags     (| tag | type | count | notes |)
                            sorted by (type, -count). User-editable: change the
                            `type` column to reclassify a tag; next run re-sorts.
    _internal/registry.json full machine-readable mirror (one source of truth)
    _internal/field_names.txt        one tag per line (cheap token-light read)
    _internal/topic_names.txt
    _internal/methodology_names.txt
    _internal/meta_names.txt

Usage:
    uv run python -m paperhub.tag_utils.periodic.bootstrap_registry \\
        --scan /tmp/paperhub_tags_after.json \\
        --tags-dir ../tags

Per-type tables drop the `aliases` column — historical merges are recorded in
CHANGELOG.md, not the table. The `?` flag on the type column marks rows where
the heuristic was uncertain; user hand-edits the type to remove the flag.

Periodic only — the per-batch new-tag flow uses `tag_utils.register_tag`
instead. See `.claude/skills/paper-organizer/tags/post_summary_update.md`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from paperhub.tag_utils.registry import INTERNAL_SUBDIR, VALID_TYPES


# Round-1 merges are archived at `tags/round1_merges.json` for reproducibility.
# Future periodic rounds pass their own --merges-file to apply_renames.py.


# ---- Type heuristics ----

_FIELD = {
    "IO", "macroecon", "microecon", "behavioral_economics", "labor_economics",
    "finance", "trade", "public_economics", "development_economics",
    "health_economics", "information_economics", "environmental_economics",
    "media_economics", "urban", "education", "corporate_finance",
    "household_finance", "consumer_finance", "macrofinance", "macro_labor",
    "monetary_policy", "international_economics", "political_economy",
    "economic_history", "economic_growth", "growth", "endogenous_growth",
    "industrial_policy", "digital_economics", "energy_economics",
    "transport_economics", "applied_microeconomics", "micro_theory",
    "decision_theory", "game_theory", "auction_theory", "contract_theory",
    "mechanism_design", "search_theory", "matching_theory",
    "financial_economics", "AI_economics",
}

_METHODOLOGY = {
    "theoretical", "empirical", "experimental", "structural", "reduced-form",
    "reduced_form", "machine_learning", "ai", "econometrics", "simulation",
    "calibration", "computational_economics", "quantitative", "quantitative_macro",
    "quantitative_model", "rct", "field_experiment", "natural_experiment",
    "regression_discontinuity", "difference_in_differences", "instrumental_variables",
    "panel_data", "nonparametric", "partial_identification", "identification",
    "discrete_choice", "dynamic_discrete_choice", "demand_estimation",
    "agent_based_model", "bayesian", "moment_inequalities", "experimental_design",
    "policy_evaluation", "causal_inference", "decompositions", "review",
    "survey", "prediction", "forecasting", "statistical_decision_theory",
    "statistics", "measure_theory", "optimal_transport", "Wasserstein_distance",
    "survival_analysis", "computational_linguistics", "computational_social_science",
    "functional_data", "production_function",
}

_META: set[str] = set()  # nothing fixed; rule patterns below catch course/conf

_META_PATTERNS = [
    re.compile(r"^econ\d+$", re.IGNORECASE),
    re.compile(r"^\d{4}_"),
    re.compile(r"^LEMA$"),
    re.compile(r"^PSUAI$", re.IGNORECASE),
]


def classify(tag: str) -> tuple[str, bool]:
    """Return (type, confident). confident=False means user should review."""
    for pat in _META_PATTERNS:
        if pat.match(tag):
            return "meta", True
    if tag in _META:
        return "meta", True
    if tag in _FIELD:
        return "field", True
    if tag in _METHODOLOGY:
        return "methodology", True
    return "topic", False


TYPES = VALID_TYPES
TYPE_HEADERS = {
    "field": "Field tags",
    "topic": "Topic tags",
    "methodology": "Methodology tags",
    "meta": "Meta tags (course, conference, etc.)",
}


def _read_existing_types(tags_dir: Path) -> dict[str, tuple[str, str]]:
    """Parse the existing tags_summary.md to preserve user-edited types and notes.

    Reads only data rows of the main `| tag | type | count | notes |` table.
    Returns {tag: (type, notes)}. If the file is missing, the per-type
    overview table at the top is detected and skipped (it has 3 columns;
    the data table has 4).
    """
    existing: dict[str, tuple[str, str]] = {}
    p = tags_dir / "tags_summary.md"
    if not p.is_file():
        return existing
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        # Skip alignment rows like `|---|---|---:|---|`
        if set(line.strip()) <= set("|-: "):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) != 4:
            # 3-column overview table or malformed — ignore
            continue
        tag_cell, type_cell, _, notes_cell = cols
        tag = tag_cell.strip("`").strip()
        ttype = type_cell.lower()
        # Skip header row
        if tag.lower() == "tag" or ttype == "type":
            continue
        if not tag or ttype not in TYPES:
            continue
        existing[tag] = (ttype, notes_cell)
    return existing


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scan", type=Path, required=True, help="raw scan_tags JSON")
    p.add_argument("--tags-dir", type=Path, required=True, help="tags/ output dir")
    args = p.parse_args()

    args.tags_dir.mkdir(parents=True, exist_ok=True)
    internal_dir = args.tags_dir / INTERNAL_SUBDIR
    internal_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(args.scan.read_text(encoding="utf-8"))
    existing = _read_existing_types(args.tags_dir)

    counts: dict[str, int] = defaultdict(int)
    for tag, info in data["tags"].items():
        counts[tag] += info["count"]

    # Resolve type per tag: prefer existing user-set type, else heuristic.
    by_type: dict[str, list[dict]] = {t: [] for t in TYPES}
    flagged_uncertain = 0
    for tag, count in counts.items():
        if tag in existing:
            ttype, notes = existing[tag]
            confident = True
        else:
            ttype, confident = classify(tag)
            notes = ""
        if not confident:
            flagged_uncertain += 1
        by_type[ttype].append(
            {"tag": tag, "count": count, "notes": notes, "confident": confident}
        )
    for t in TYPES:
        by_type[t].sort(key=lambda r: (-r["count"], r["tag"]))

    # ---- write tags_summary.md (single consolidated table) ----
    total_tags = sum(len(by_type[t]) for t in TYPES)
    total_occ = sum(sum(r["count"] for r in by_type[t]) for t in TYPES)
    type_order = {t: i for i, t in enumerate(TYPES)}
    all_rows: list[dict] = []
    for ttype in TYPES:
        for r in by_type[ttype]:
            r2 = dict(r)
            r2["type"] = ttype
            all_rows.append(r2)
    all_rows.sort(key=lambda r: (type_order[r["type"]], -r["count"], r["tag"]))

    summary = ["# Tags Summary\n\n"]
    summary.append(
        f"**{total_tags} canonical tags**, {total_occ} occurrences across "
        f"{data['scanned']} papers.\n\n"
    )
    summary.append(
        "To reclassify a tag, edit the `type` column (one of `field`, `topic`, "
        "`methodology`, `meta`). The next run of "
        "`tag_utils.periodic.bootstrap_registry` re-sorts and regroups the table "
        "while preserving your edits.\n\n"
    )

    # Per-type overview (3 columns — distinguishable from the data table by
    # column count, so _read_existing_types ignores it).
    summary.append("## Overview\n\n")
    summary.append("| type | unique tags | occurrences |\n|---|---:|---:|\n")
    for ttype in TYPES:
        rows = by_type[ttype]
        summary.append(
            f"| {ttype} | {len(rows)} | {sum(r['count'] for r in rows)} |\n"
        )
    summary.append("\n")

    # Main data table.
    summary.append("## All tags\n\n")
    summary.append("| tag | type | count | notes |\n|---|---|---:|---|\n")
    for r in all_rows:
        summary.append(
            f"| `{r['tag']}` | {r['type']} | {r['count']} | {r['notes']} |\n"
        )
    summary.append(
        f"\n_System files (machine-readable mirror, cheap name lists, history) "
        f"live in `{INTERNAL_SUBDIR}/`._\n"
    )
    (args.tags_dir / "tags_summary.md").write_text("".join(summary), encoding="utf-8")

    # ---- write registry.json ----
    registry = {
        "scanned": data["scanned"],
        "total_tags": total_tags,
        "by_type": {
            t: [{"tag": r["tag"], "count": r["count"], "notes": r["notes"]}
                for r in by_type[t]]
            for t in TYPES
        },
    }
    (internal_dir / "registry.json").write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # ---- write per-type names files (cheap reads) ----
    for ttype in TYPES:
        names = "\n".join(r["tag"] for r in by_type[ttype]) + "\n"
        (internal_dir / f"{ttype}_names.txt").write_text(names, encoding="utf-8")

    msg = (
        f"Wrote {args.tags_dir}: {total_tags} canonical tags across {len(TYPES)} types"
    )
    if flagged_uncertain:
        msg += f" ({flagged_uncertain} new tags defaulted to topic — review the type column)"
    print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
