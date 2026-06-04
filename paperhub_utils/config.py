"""Configuration for Paper Summarizer.

User-editable onboarding/runtime settings live in misc/config.json.
"""

import json
import os
from pathlib import Path

MISC_DIR = Path(__file__).parent / "misc"
USER_CONFIG_PATH = MISC_DIR / "config.json"
ONBOARDING_STATE_PATH = MISC_DIR / "onboarding.json"


def _load_user_config() -> dict:
    try:
        data = json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _config_bool(config: dict, key: str, default: bool) -> bool:
    value = config.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _config_int(config: dict, key: str, default: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(0, value)


USER_CONFIG = _load_user_config()
TAG_PROMPT_CONFIG = USER_CONFIG.get("tag_prompt", {})
if not isinstance(TAG_PROMPT_CONFIG, dict):
    TAG_PROMPT_CONFIG = {}

# Root and workflow settings
PAPERHUB_ROOT = (
    Path(os.environ.get("PAPERHUB_ROOT", Path(__file__).resolve().parents[1]))
    .expanduser()
    .resolve()
)
TO_BE_ORGANIZED_DIR = PAPERHUB_ROOT / "to_be_organized"
DEFAULT_ORGANIZED_DIR = PAPERHUB_ROOT / "organized"
DEFAULT_TAGS_DIR = PAPERHUB_ROOT / "tags"
SAMPLE_BOARD_PATH = PAPERHUB_ROOT / "SamplePaperBoard.base"
USE_GIT = _config_bool(USER_CONFIG, "use_git", True)
_USE_GIT_ENV = os.environ.get("PAPERHUB_USE_GIT")
if _USE_GIT_ENV is not None:
    USE_GIT = _USE_GIT_ENV.strip().lower() in {"1", "true", "yes", "on"}

# API Configuration
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
# Set to None to disable reasoning, or choose an effort from REASONING_EFFORTS.
# "exclude" keeps reasoning tokens out of the returned assistant message.
DEFAULT_REASONING = {"effort": "medium", "exclude": True}

# pdf_input options:
# - "openrouter_file_parser": send the PDF file through OpenRouter's file-parser.
# - "text_extraction": convert the PDF locally with pymupdf4llm and send that text.
DEFAULT_MODEL = {
    "model_id": "qwen/qwen3.7-max",
    "provider": {},
    "reasoning": DEFAULT_REASONING,
    "pdf_input": "text_extraction",
}
MODEL_LIST = [
    {
        "model_id": "qwen/qwen3.7-max",
        "provider": {},
        "reasoning": DEFAULT_REASONING,
        "pdf_input": "text_extraction",
    },
    {
        "model_id": "deepseek/deepseek-v4-pro",
        "provider": {},
        "reasoning": DEFAULT_REASONING,
        "pdf_input": "text_extraction",
    },
    {
        "model_id": "moonshotai/kimi-k2.6",
        "provider": {},
        "reasoning": DEFAULT_REASONING,
        "pdf_input": "openrouter_file_parser",
    },
    {
        "model_id": "google/gemini-3.1-pro-preview",
        "provider": {},
        "reasoning": DEFAULT_REASONING,
        "pdf_input": "openrouter_file_parser",
    },
]

# Gemini CLI model used by skills/paper-summarizer/engines/gemini_cli.md.
# Override via misc/config.json's "gemini_cli_model".
_GEMINI_CLI_MODEL_DEFAULT = "gemini-3.1-pro-preview"
_gemini_cli_model_value = USER_CONFIG.get("gemini_cli_model")
GEMINI_CLI_MODEL = (
    _gemini_cli_model_value.strip()
    if isinstance(_gemini_cli_model_value, str) and _gemini_cli_model_value.strip()
    else _GEMINI_CLI_MODEL_DEFAULT
)

# Agy CLI model used by skills/paper-summarizer/engines/agy_cli.md.
# Override via misc/config.json's "agy_cli_model".
AGY_CLI_MODEL_LIST = (
    "Gemini 3.1 Pro (High)",
    "Gemini 3.1 Pro (Low)",
    "Gemini 3.5 Flash (High)",
    "Gemini 3.5 Flash (Medium)",
    "Gemini 3 Flash",
    "Claude Sonnet 4.6 (Thinking)",
    "Claude Opus 4.6 (Thinking)",
    "GPT-OSS 120B (Medium)",
    "GPT-OSS-120b",
)
_AGY_CLI_MODEL_DEFAULT = "Gemini 3.1 Pro (High)"
_agy_cli_model_value = USER_CONFIG.get("agy_cli_model")
AGY_CLI_MODEL = (
    _agy_cli_model_value.strip()
    if isinstance(_agy_cli_model_value, str) and _agy_cli_model_value.strip()
    else _AGY_CLI_MODEL_DEFAULT
)

DEFAULT_PDF_ENGINE = "mistral-ocr"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 2
METADATA_ONLY_PAGE_LIMIT = _config_int(
    USER_CONFIG,
    "metadata_only_page_limit",
    1,
)
METADATA_ONLY_PAGE_LIMIT = max(1, METADATA_ONLY_PAGE_LIMIT)

# Prompt-time tag registry context
# The prompt builder sends the top canonical tags from tags/_internal/registry.json
# to the AI so it can reuse existing tags before inventing new ones.
INCLUDE_TAG_CONTEXT_IN_PROMPT = _config_bool(
    TAG_PROMPT_CONFIG,
    "include_context",
    True,
)
TAG_PROMPT_TOP_FIELD = _config_int(TAG_PROMPT_CONFIG, "top_field", 5)
TAG_PROMPT_TOP_TOPIC = _config_int(TAG_PROMPT_CONFIG, "top_topic", 50)
TAG_PROMPT_TOP_METHODOLOGY = _config_int(TAG_PROMPT_CONFIG, "top_methodology", 20)
TAG_PROMPT_TOP_META = _config_int(TAG_PROMPT_CONFIG, "top_meta", 5)

# Output Configuration
DEFAULT_OUTPUT_DIR = str(DEFAULT_ORGANIZED_DIR)

# Your Research Interests
# This will be used by the AI to generate connections between papers and your work.
# Be specific about your research topics, methodologies, and questions of interest.
MY_RESEARCH_INTERESTS = """
## Research Fields
- **Behavioral Economics**: Biases in decision-making (present bias, zero-sum thinking, correlation neglect), norms of cooperation, experimental methods
- **Information Economics**: Information asymmetry, belief formation, information acquisition, signaling and labeling, rating systems


## Key Topics of Interest
1. How behavioral biases (correlation neglect, present bias, zero-sum thinking) affect economic decisions and aggregate outcomes
2. Information frictions in markets: how information asymmetry shapes consumer behavior, firm decisions, and welfare
3. Political economy: how micro-level beliefs aggregate to political outcomes
4. The role of institutions and norms in shaping economic behavior (historical persistence, cultural transmission)

"""
