"""Configuration for PaperHub utility scripts.

User-editable onboarding/runtime settings live in config/config.json.
"""

import json
import os
from pathlib import Path

UTILS_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = UTILS_ROOT / "config"
USER_CONFIG_PATH = CONFIG_DIR / "config.json"
ONBOARDING_STATE_PATH = CONFIG_DIR / "onboarding.json"


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
    Path(os.environ.get("PAPERHUB_ROOT", UTILS_ROOT.parent))
    .expanduser()
    .resolve()
)
TO_BE_ORGANIZED_DIR = PAPERHUB_ROOT / "to_be_organized"
DEFAULT_ORGANIZED_DIR = PAPERHUB_ROOT / "organized"
DEFAULT_TAGS_DIR = PAPERHUB_ROOT / "tags"
SAMPLE_BOARD_PATH = PAPERHUB_ROOT / "SamplePaperBoard.base"
# Git versioning lives in a separate out-of-iCloud "backup" repo; the vault itself
# holds no .git. Settings live under the "git" block, with a legacy fallback to the
# old top-level "use_git" key so pre-schema-2 configs keep working.
_GIT_CONFIG = USER_CONFIG.get("git")
if not isinstance(_GIT_CONFIG, dict):
    _GIT_CONFIG = {}

USE_GIT = _config_bool(_GIT_CONFIG, "use_git", _config_bool(USER_CONFIG, "use_git", True))
_USE_GIT_ENV = os.environ.get("PAPERHUB_USE_GIT")
if _USE_GIT_ENV is not None:
    USE_GIT = _USE_GIT_ENV.strip().lower() in {"1", "true", "yes", "on"}

# When true, the versioning-with-git skill pulls before and pushes after each commit.
SYNC_TO_REMOTE_GIT = _config_bool(_GIT_CONFIG, "sync_to_remote", False)
_SYNC_REMOTE_ENV = os.environ.get("PAPERHUB_SYNC_TO_REMOTE_GIT")
if _SYNC_REMOTE_ENV is not None:
    SYNC_TO_REMOTE_GIT = _SYNC_REMOTE_ENV.strip().lower() in {"1", "true", "yes", "on"}

# Absolute path of the out-of-iCloud git backup repo (None when unset).
_git_backup = os.environ.get("PAPERHUB_GIT_BACKUP") or _GIT_CONFIG.get("backup_abs_path")
GIT_BACKUP_ABS_PATH = (
    _git_backup.strip() if isinstance(_git_backup, str) and _git_backup.strip() else None
)

# API Configuration
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
# Set to None to disable reasoning, or choose an effort from REASONING_EFFORTS.
# "exclude" keeps reasoning tokens out of the returned assistant message.
DEFAULT_REASONING = {"effort": "high", "exclude": True}

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

# Agy CLI model used by skills/paper-summarizer/engines/agy_cli.md.
# Override via config/config.json's "agy_cli_model".
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

# Codex CLI model/reasoning pairs used by
# skills/paper-summarizer/engines/codex_cli.md. Override via
# config/config.json's "codex_cli_model" and "codex_cli_reasoning_effort".
CODEX_CLI_MODEL_REASONING_PAIRS = (
    ("gpt-5.5", "low"),
    ("gpt-5.5", "medium"),
    ("gpt-5.5", "high"),
    ("gpt-5.5", "xhigh"),
)
CODEX_CLI_MODEL_LIST = tuple(
    dict.fromkeys(model for model, _ in CODEX_CLI_MODEL_REASONING_PAIRS)
)
CODEX_CLI_REASONING_EFFORT_LIST = tuple(
    dict.fromkeys(effort for _, effort in CODEX_CLI_MODEL_REASONING_PAIRS)
)
_CODEX_CLI_MODEL_DEFAULT = "gpt-5.5"
_CODEX_CLI_REASONING_EFFORT_DEFAULT = "xhigh"
_codex_cli_model_value = USER_CONFIG.get("codex_cli_model")
CODEX_CLI_MODEL = (
    _codex_cli_model_value.strip()
    if isinstance(_codex_cli_model_value, str) and _codex_cli_model_value.strip()
    else _CODEX_CLI_MODEL_DEFAULT
)
_codex_cli_reasoning_effort_value = USER_CONFIG.get("codex_cli_reasoning_effort")
CODEX_CLI_REASONING_EFFORT = (
    _codex_cli_reasoning_effort_value.strip()
    if (
        isinstance(_codex_cli_reasoning_effort_value, str)
        and _codex_cli_reasoning_effort_value.strip()
    )
    else _CODEX_CLI_REASONING_EFFORT_DEFAULT
)
CODEX_CLI_YOLO = _config_bool(USER_CONFIG, "codex_cli_yolo", True)

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
MY_RESEARCH_INTERESTS = ""
