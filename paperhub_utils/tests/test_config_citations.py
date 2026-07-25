from __future__ import annotations

import unittest

from paperhub.config import DEFAULT_CITATION_CONFIG, _config_citations


class CitationConfigTests(unittest.TestCase):
    def test_missing_or_malformed_block_uses_defaults(self) -> None:
        self.assertEqual(_config_citations(None), DEFAULT_CITATION_CONFIG)
        self.assertEqual(_config_citations(["wrong"]), DEFAULT_CITATION_CONFIG)
        self.assertEqual(
            _config_citations(
                {
                    "resolve_after_organize": 1,
                    "current_agent_search_missing_link": "not-a-boolean",
                }
            ),
            DEFAULT_CITATION_CONFIG,
        )

    def test_existing_values_are_normalized_and_preserved(self) -> None:
        self.assertEqual(
            _config_citations(
                {
                    "resolve_after_organize": "yes",
                    "current_agent_search_missing_link": False,
                    "preferred_style": "apa",
                }
            ),
            {
                "resolve_after_organize": True,
                "current_agent_search_missing_link": False,
                "preferred_style": "apa",
            },
        )

    def test_missing_keys_and_blank_style_are_seeded(self) -> None:
        self.assertEqual(
            _config_citations({"resolve_after_organize": True, "preferred_style": "  "}),
            {
                "resolve_after_organize": True,
                "current_agent_search_missing_link": True,
                "preferred_style": "chicago-author-date",
            },
        )


if __name__ == "__main__":
    unittest.main()
