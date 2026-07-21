from __future__ import annotations

import unittest

from paperhub.config import (
    AVAILABLE_ENGINES,
    CURRENT_AGENT_ENGINE_ID,
    SUPPORTED_ENGINE_IDS,
    _config_available_engines,
)


class AvailableEnginesConfigTests(unittest.TestCase):
    def test_current_agent_is_always_available(self) -> None:
        self.assertEqual(_config_available_engines(None), (CURRENT_AGENT_ENGINE_ID,))
        self.assertEqual(
            _config_available_engines(["openrouter"]),
            ("openrouter", CURRENT_AGENT_ENGINE_ID),
        )

    def test_normalizes_aliases_deduplicates_and_ignores_unknown_values(self) -> None:
        resolved = _config_available_engines(
            ["Codex", "agy", "openrouter-api", "codex-cli", "unknown", 42]
        )
        self.assertEqual(
            resolved,
            ("codex-cli", "agy-cli", "openrouter", CURRENT_AGENT_ENGINE_ID),
        )

    def test_loaded_engines_are_supported_and_include_current_agent(self) -> None:
        self.assertIn(CURRENT_AGENT_ENGINE_ID, AVAILABLE_ENGINES)
        self.assertTrue(set(AVAILABLE_ENGINES).issubset(SUPPORTED_ENGINE_IDS))


if __name__ == "__main__":
    unittest.main()
