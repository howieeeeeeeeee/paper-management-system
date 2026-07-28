from __future__ import annotations

import json
import unittest
from pathlib import Path

from paperhub.config import (
    CITATION_CURRENT_AGENT_SEARCH_MISSING_LINK,
    CITATION_RESOLVE_AFTER_ORGANIZE,
)


ROOT = Path(__file__).resolve().parents[2]


class CitationOrganizerIntegrationTests(unittest.TestCase):
    def test_config_uses_schema_four_with_a_well_formed_citations_block(self) -> None:
        """Check config *shape*, never the user's chosen values.

        ``resolve_after_organize`` is a per-user setting whose whole purpose is
        to be turned on, so asserting a particular value here would fail for
        exactly the adopters who use the feature.
        """
        config = json.loads(
            (ROOT / "paperhub_utils/config/config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["schema_version"], 4)
        citations = config["citations"]
        self.assertIsInstance(citations["resolve_after_organize"], bool)
        self.assertIsInstance(citations["current_agent_search_missing_link"], bool)
        self.assertIsInstance(citations["preferred_style"], str)
        self.assertIsInstance(CITATION_RESOLVE_AFTER_ORGANIZE, bool)
        self.assertIsInstance(CITATION_CURRENT_AGENT_SEARCH_MISSING_LINK, bool)
        self.assertEqual(
            CITATION_RESOLVE_AFTER_ORGANIZE, citations["resolve_after_organize"]
        )

    def test_hook_is_best_effort_excludes_enrich_and_limits_external_engines(self) -> None:
        text = (
            ROOT
            / ".claude/skills/paper-organizer/shared/post_ai.md"
        ).read_text(encoding="utf-8")
        self.assertIn("skip this section completely", text)
        self.assertIn("Do not run it for `enrich`", text)
        self.assertIn("external", text)
        self.assertIn("never browse or search for a link", text)
        self.assertIn("Never retry", text)
        self.assertIn("block tags and", text)

    def test_public_sanitizer_forces_disabled_default(self) -> None:
        sanitizer_skill = ROOT / ".claude/skills/public-template-sync/SKILL.md"
        if not sanitizer_skill.exists():
            self.skipTest("maintainer-only public-template-sync skill is not shipped")
        text = sanitizer_skill.read_text(encoding="utf-8")
        self.assertIn('c["schema_version"] = 4', text)
        self.assertIn('"resolve_after_organize": False', text)
        self.assertIn(
            'assert c["citations"]["resolve_after_organize"] is False',
            text,
        )


if __name__ == "__main__":
    unittest.main()
