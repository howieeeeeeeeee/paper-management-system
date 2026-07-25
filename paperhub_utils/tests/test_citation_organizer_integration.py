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
    def test_default_is_disabled_and_personal_config_uses_schema_four(self) -> None:
        config = json.loads(
            (ROOT / "paperhub_utils/config/config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["schema_version"], 4)
        self.assertFalse(config["citations"]["resolve_after_organize"])
        self.assertFalse(CITATION_RESOLVE_AFTER_ORGANIZE)
        self.assertTrue(CITATION_CURRENT_AGENT_SEARCH_MISSING_LINK)

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
