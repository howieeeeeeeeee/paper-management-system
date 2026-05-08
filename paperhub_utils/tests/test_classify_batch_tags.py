from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tag_utils.classify_batch_tags import classify_batch_tags


SUMMARY = """# Tags Summary

**8 canonical tags**, 42 occurrences across 2 papers.

## All tags

| tag | type | count | notes |
|---|---|---:|---|
| `behavioral_economics` | field | 10 |  |
| `finance` | field | 3 |  |
| `macroecon` | field | 4 |  |
| `political_economy` | field | 2 |  |
| `llm` | topic | 6 |  |
| `ai` | methodology | 7 |  |
| `experimental` | methodology | 5 |  |
| `empirical` | methodology | 5 |  |
"""


def write_meta(organized_dir: Path, label: str, tags: list[str]) -> None:
    folder = organized_dir / label
    folder.mkdir(parents=True)
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    (folder / f"{label}.md").write_text(
        f"""---
title: Example
authors:
  - Example Author
year: 2026
tags:
{tag_lines}
---

## Abstract
Example.
""",
        encoding="utf-8",
    )


class ClassifyBatchTagsTests(unittest.TestCase):
    def test_empty_registry_uses_summary_for_reused_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            organized_dir = root / "organized"
            tags_dir = root / "tags"
            internal_dir = tags_dir / "_internal"
            internal_dir.mkdir(parents=True)
            (tags_dir / "tags_summary.md").write_text(SUMMARY, encoding="utf-8")
            (internal_dir / "registry.json").write_text(
                json.dumps(
                    {
                        "scanned": 0,
                        "total_tags": 0,
                        "by_type": {
                            "field": [],
                            "topic": [],
                            "methodology": [],
                            "meta": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            write_meta(
                organized_dir,
                "caoetal2026llm",
                ["llm", "ai", "behavioral_economics", "finance", "experimental"],
            )
            write_meta(
                organized_dir,
                "fan2026geopolitics",
                ["macroecon", "political_economy", "llm", "ai", "empirical"],
            )

            result = classify_batch_tags(
                ["caoetal2026llm", "fan2026geopolitics"],
                organized_dir=organized_dir,
                tags_dir=tags_dir,
            )

        self.assertTrue(result["registry_source"].endswith("tags_summary.md"))
        self.assertEqual(result["candidates"], [])
        self.assertEqual(
            result["reused"],
            [
                "llm",
                "ai",
                "behavioral_economics",
                "finance",
                "experimental",
                "macroecon",
                "political_economy",
                "empirical",
            ],
        )


if __name__ == "__main__":
    unittest.main()
