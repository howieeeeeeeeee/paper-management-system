from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperhub.tag_utils.registry import (
    RegistryError,
    load_registry,
    parse_tags_summary,
    registry_tag_names,
)


SUMMARY = """# Tags Summary

**2 canonical tags**, 7 occurrences across 3 papers.

## Overview

| type | unique tags | occurrences |
|---|---:|---:|
| field | 1 | 5 |
| topic | 0 | 0 |
| methodology | 1 | 2 |
| meta | 0 | 0 |

## All tags

| tag | type | count | notes |
|---|---|---:|---|
| `behavioral_economics` | field | 5 |  |
| `experimental` | methodology | 2 | introduced by example |
"""


class RegistryTests(unittest.TestCase):
    def test_parse_tags_summary_to_registry_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tags_dir = Path(tmp)
            (tags_dir / "tags_summary.md").write_text(SUMMARY, encoding="utf-8")

            registry = parse_tags_summary(tags_dir)

        self.assertEqual(registry["scanned"], 3)
        self.assertEqual(registry["total_tags"], 2)
        self.assertEqual(
            registry["by_type"]["field"][0]["tag"],
            "behavioral_economics",
        )
        self.assertEqual(registry["by_type"]["methodology"][0]["count"], 2)

    def test_load_registry_falls_back_when_json_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tags_dir = Path(tmp)
            internal_dir = tags_dir / "_internal"
            internal_dir.mkdir()
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
            (tags_dir / "tags_summary.md").write_text(SUMMARY, encoding="utf-8")

            loaded = load_registry(tags_dir, require_populated=True)

        self.assertTrue(loaded.source.endswith("tags_summary.md"))
        self.assertIn("registry.json has no tags", loaded.warnings)
        self.assertEqual(
            registry_tag_names(loaded.data),
            {"behavioral_economics", "experimental"},
        )

    def test_load_registry_raises_without_any_usable_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tags_dir = Path(tmp)
            (tags_dir / "_internal").mkdir()
            (tags_dir / "_internal" / "registry.json").write_text(
                "{",
                encoding="utf-8",
            )

            with self.assertRaises(RegistryError):
                load_registry(tags_dir, require_populated=True)


if __name__ == "__main__":
    unittest.main()
