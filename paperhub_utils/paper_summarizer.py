#!/usr/bin/env python3
"""
Paper Summarizer - Automated Research Paper Organization

This script processes PDF research papers using the OpenRouter API to generate
structured metadata and summaries, then organizes them into a standardized
folder structure.

Usage:
    python paper_summarizer.py <pdf_path> [<pdf_path> ...] [options]

Options:
    --model         OpenRouter model ID
    --output-dir    Output directory for organized papers
    --instruction   Additional instructions to inject into the analysis prompt
    --summary-mode  full (default) or metadata-only
    --no-git        Skip git commit step
    --dry-run       Generate JSON only, don't create files
    --verbose       Enable verbose logging
"""

import argparse
import base64
import json
import logging
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not found. Install with: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
    load_dotenv()
except ImportError:
    # dotenv is optional, will use environment variables directly
    pass

# Configuration - import from config.py
from config import (
    AGY_CLI_MODEL,
    AGY_CLI_MODEL_LIST,
    DEFAULT_MODEL,
    MODEL_LIST,
    DEFAULT_PDF_ENGINE,
    DEFAULT_OUTPUT_DIR,
    OPENROUTER_API_URL,
    MAX_RETRIES,
    METADATA_ONLY_PAGE_LIMIT,
    MY_RESEARCH_INTERESTS,
    PAPERHUB_ROOT,
)
from prompt.builder import build_prompt
from cli_workflow.agy import (
    AGY_RESPONSE_BEGIN,
    AGY_RESPONSE_END,
    agy_model_label,
    agy_settings_path,
    configure_agy_cli_model,
    extract_agy_response_block,
    resolve_agy_cli_model,
    validate_agy_cli_run,
)
from cli_workflow.gemini import validate_gemini_cli_run
from cli_workflow.pdf import (
    CLI_WORK_DIR,
    create_first_pages_pdf,
    ensure_safe_cli_cleanup_path,
    gemini_at_path,
    repo_relative_path,
)
from cli_workflow.utils import (
    parse_metadata_first_markdown,
    parse_metadata_only_markdown,
)


SUMMARY_MODE_FULL = "full"
SUMMARY_MODE_METADATA_ONLY = "metadata-only"
SUMMARY_MODES = (SUMMARY_MODE_FULL, SUMMARY_MODE_METADATA_ONLY)


def resolve_model_config(model_arg) -> dict:
    """Resolve a model argument into {"model_id": str, "provider": dict}.

    Accepts either a dict (from DEFAULT_MODEL) or a string model ID
    (from --model CLI arg). If a string, looks up provider from MODEL_LIST.
    """
    if isinstance(model_arg, dict):
        return model_arg
    # String model ID — look up provider from MODEL_LIST
    for entry in MODEL_LIST:
        if entry["model_id"] == model_arg:
            return entry
    # Not in MODEL_LIST — use with no provider preference
    return {"model_id": model_arg, "provider": {}}


def resolve_pdf_input_config(model_config: dict) -> dict:
    """Return a validated PDF input strategy for an OpenRouter model."""
    raw_config = model_config.get("pdf_input", "openrouter_file_parser")
    if isinstance(raw_config, str):
        mode = raw_config
        extractor = "pymupdf4llm"
    elif isinstance(raw_config, dict):
        mode = raw_config.get("mode", "openrouter_file_parser")
        extractor = raw_config.get("extractor", "pymupdf4llm")
    else:
        raise ValueError(
            f"pdf_input must be a string or dict, got {type(raw_config).__name__}"
        )

    if mode not in {"openrouter_file_parser", "text_extraction"}:
        raise ValueError(f"Unsupported pdf_input mode: {mode}")
    if mode == "text_extraction" and extractor != "pymupdf4llm":
        raise ValueError(f"Unsupported PDF text extractor: {extractor}")

    resolved = {"mode": mode}
    if mode == "text_extraction":
        resolved["extractor"] = extractor
    return resolved


# Setup logging
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging with appropriate level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


logger = setup_logging()


def get_api_key() -> str:
    """Get OpenRouter API key from environment."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        # Try loading from .env file in home directory
        env_file = Path.home() / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip("\"'")
                        break

    if not api_key:
        logger.error(
            "OPENROUTER_API_KEY not found in environment, paperhub_utils/.env, or ~/.env"
        )
        sys.exit(1)

    return api_key


def encode_pdf_to_base64(pdf_path: Path) -> str:
    """Read PDF file and encode to base64."""
    logger.info(f"Reading PDF: {pdf_path}")
    try:
        file_size = pdf_path.stat().st_size
        file_size_mb = file_size / 1024 / 1024
        logger.info(f"PDF file size: {file_size_mb:.2f} MB ({file_size:,} bytes)")

        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
            if len(pdf_data) != file_size:
                logger.warning(
                    f"Read {len(pdf_data)} bytes but expected {file_size} bytes"
                )

            encoded = base64.standard_b64encode(pdf_data).decode("utf-8")
            logger.debug(f"Encoded PDF to base64 (length: {len(encoded)} characters)")
            return encoded
    except FileNotFoundError:
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    except PermissionError:
        raise PermissionError(f"Permission denied reading PDF: {pdf_path}")
    except MemoryError:
        raise MemoryError(
            f"Out of memory while reading PDF: {pdf_path} (size: {file_size_mb:.2f} MB)"
        )
    except Exception as e:
        raise Exception(
            f"Unexpected error reading PDF {pdf_path}: {type(e).__name__}: {e}"
        )


def create_analysis_prompt(
    additional_instruction: str = "",
    summary_mode: str = SUMMARY_MODE_FULL,
) -> str:
    """Create the prompt for analyzing the paper. Delegates to prompt.builder."""
    if summary_mode not in SUMMARY_MODES:
        raise ValueError(f"Unknown summary mode: {summary_mode}")
    today = datetime.now().strftime("%Y-%m-%d")
    return build_prompt(
        summary_mode,
        today=today,
        research_interests=MY_RESEARCH_INTERESTS,
        additional_instruction=additional_instruction,
    )


def extract_text_from_file_annotations(error_body: dict) -> str:
    """Flatten OpenRouter parsed PDF annotations into plain text."""
    annotations = (
        error_body.get("error", {})
        .get("metadata", {})
        .get("file_annotations", [])
    )
    text_parts: list[str] = []

    if not isinstance(annotations, list):
        return ""

    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        file_info = annotation.get("file", {})
        if not isinstance(file_info, dict):
            continue
        for part in file_info.get("content", []):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                text_parts.append(part["text"])

    return "\n\n".join(text_parts).strip()


def extract_pdf_context(pdf_path: Path, extractor: str) -> str:
    """Convert a PDF into Markdown/text context for text-only model calls."""
    if extractor == "pymupdf4llm":
        try:
            import pymupdf4llm
        except ImportError as e:
            raise RuntimeError(
                "Missing dependency: install pymupdf4llm to use PDF text extraction"
            ) from e

        logger.info("Extracting PDF context with pymupdf4llm: %s", pdf_path)
        text = pymupdf4llm.to_markdown(str(pdf_path))
    else:
        raise ValueError(f"Unsupported PDF text extractor: {extractor}")

    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"PDF text extraction produced no content: {pdf_path}")
    return text.strip()


def build_pdf_text_context_prompt(
    prompt: str,
    pdf_text: str,
    source_note: str,
) -> str:
    """Create a text-only prompt from extracted PDF content."""
    return (
        f"{source_note} Use the extracted paper content below as the attached PDF.\n\n"
        "<paper_pdf_text>\n"
        f"{pdf_text}\n"
        "</paper_pdf_text>\n\n"
        f"{prompt}"
    )


def build_parsed_pdf_fallback_prompt(prompt: str, parsed_text: str) -> str:
    """Create a text-only prompt from OpenRouter's parsed PDF content."""
    return build_pdf_text_context_prompt(
        prompt,
        parsed_text,
        (
            "OpenRouter parsed the PDF into text, but the downstream provider "
            "cannot accept the original PDF file block."
        ),
    )


def build_local_pdf_text_prompt(prompt: str, pdf_text: str, extractor: str) -> str:
    """Create a text-only prompt from locally extracted PDF content."""
    return build_pdf_text_context_prompt(
        prompt,
        pdf_text,
        f"The PDF was converted to Markdown locally with {extractor}.",
    )


def make_openrouter_headers(api_key: str) -> dict:
    """Return common headers for OpenRouter chat-completions calls."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "Paper Summarizer",
    }


def parse_openrouter_success_response(response: requests.Response) -> dict:
    """Parse a successful OpenRouter response into normalized content/usage."""
    result = response.json()
    content = (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    usage = result.get("usage", {})
    if usage:
        logger.info(
            "Token usage - prompt: %s, completion: %s, total: %s",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
    return {"success": True, "content": content, "usage": usage}


def call_openrouter_text_api(
    api_key: str,
    model_id: str,
    prompt: str,
    pdf_text: str,
    provider: dict | None = None,
    reasoning: dict | None = None,
    extractor: str = "pymupdf4llm",
) -> dict:
    """Call OpenRouter with locally extracted PDF text instead of a file block."""
    headers = make_openrouter_headers(api_key)
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": build_local_pdf_text_prompt(prompt, pdf_text, extractor),
            }
        ],
        "max_tokens": 16000,
        "temperature": 0,
    }

    if reasoning:
        payload["reasoning"] = reasoning
    if provider:
        payload["provider"] = provider

    logger.info("Request details:")
    logger.info("  URL: %s", OPENROUTER_API_URL)
    logger.info("  Model: %s", model_id)
    if provider:
        logger.info("  Provider: %s", provider)
    logger.info("  PDF input: local text extraction (%s)", extractor)
    logger.info("  Extracted text length: %s characters", len(pdf_text))
    logger.info("  Max tokens: %s", payload["max_tokens"])
    logger.debug("  Prompt length: %s characters", len(prompt))

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(
                "Calling OpenRouter API with extracted text "
                "(attempt %s/%s)...",
                attempt + 1,
                MAX_RETRIES,
            )
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=300,
            )
            if response.status_code == 200:
                try:
                    result = parse_openrouter_success_response(response)
                    result["pdf_input_mode"] = "text_extraction"
                    result["pdf_text_extractor"] = extractor
                    logger.info("API call successful")
                    return result
                except (ValueError, KeyError, IndexError) as parse_error:
                    return {
                        "success": False,
                        "error": f"Failed to parse successful API response: {parse_error}",
                        "status_code": response.status_code,
                        "response_preview": response.text[:500],
                    }

            try:
                error_body = response.json()
                error_message = error_body.get("error", {}).get(
                    "message", "Unknown error"
                )
                error_details = {
                    "status_code": response.status_code,
                    "status_reason": response.reason,
                    "headers": dict(response.headers),
                    "error_body": error_body,
                }
            except ValueError:
                error_message = f"HTTP {response.status_code}: {response.reason}"
                error_details = {
                    "status_code": response.status_code,
                    "status_reason": response.reason,
                    "headers": dict(response.headers),
                    "response_text": response.text[:2000],
                }

            logger.error("API Error Response:")
            logger.error("  Status: %s %s", response.status_code, response.reason)
            logger.error("  Error Message: %s", error_message)
            if attempt < MAX_RETRIES - 1:
                import time

                wait_time = 2**attempt
                logger.warning("Retrying in %s seconds...", wait_time)
                time.sleep(wait_time)
                continue

            return {
                "success": False,
                "error": error_message,
                "error_details": error_details,
                "status_code": response.status_code,
            }
        except requests.exceptions.RequestException as e:
            logger.error(
                "Request exception (attempt %s/%s): %s",
                attempt + 1,
                MAX_RETRIES,
                e,
            )
            if attempt < MAX_RETRIES - 1:
                import time

                wait_time = 2**attempt
                logger.warning("Retrying in %s seconds...", wait_time)
                time.sleep(wait_time)
                continue
            return {
                "success": False,
                "error": f"Request exception: {type(e).__name__}",
                "error_type": type(e).__name__,
                "error_details": str(e),
            }

    return {
        "success": False,
        "error": "API call failed after all retries",
        "max_retries": MAX_RETRIES,
    }


def call_openrouter_text_fallback(
    headers: dict,
    model_id: str,
    prompt: str,
    parsed_text: str,
    provider: dict | None,
    max_tokens: int,
    temperature: float,
    reasoning: dict | None,
) -> dict:
    """Retry OpenRouter with parsed PDF text instead of a PDF file block."""
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": build_parsed_pdf_fallback_prompt(prompt, parsed_text),
            }
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    if reasoning:
        payload["reasoning"] = reasoning
    if provider:
        payload["provider"] = provider

    response = requests.post(
        OPENROUTER_API_URL,
        headers=headers,
        json=payload,
        timeout=300,
    )
    if response.status_code != 200:
        try:
            error_body = response.json()
        except ValueError:
            error_body = {"response_text": response.text[:2000]}
        return {
            "success": False,
            "error": f"Text fallback failed: HTTP {response.status_code}",
            "status_code": response.status_code,
            "error_details": error_body,
        }

    try:
        result = response.json()
        content = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return {
            "success": True,
            "content": content,
            "usage": result.get("usage", {}),
            "pdf_fallback": "parsed_text",
        }
    except (ValueError, KeyError, IndexError) as parse_error:
        return {
            "success": False,
            "error": f"Failed to parse text fallback response: {parse_error}",
            "status_code": response.status_code,
            "response_preview": response.text[:500],
        }


def call_openrouter_api(
    api_key: str,
    model_id: str,
    pdf_base64: str,
    prompt: str,
    pdf_engine: str,
    provider: dict | None = None,
    reasoning: dict | None = None,
) -> dict:
    """Call OpenRouter API with PDF content."""
    headers = make_openrouter_headers(api_key)

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "file",
                        "file": {
                            "filename": "paper.pdf",
                            "file_data": f"data:application/pdf;base64,{pdf_base64}",
                        },
                    },
                ],
            }
        ],
        "plugins": [
            {
                "id": "file-parser",
                "pdf": {"engine": pdf_engine},
            }
        ],
        "max_tokens": 16000,
        "temperature": 0,
    }

    if reasoning:
        payload["reasoning"] = reasoning
    if provider:
        payload["provider"] = provider

    pdf_size_mb = len(pdf_base64) * 3 / 4 / 1024 / 1024  # Approximate size in MB
    logger.info(f"Request details:")
    logger.info(f"  URL: {OPENROUTER_API_URL}")
    logger.info(f"  Model: {model_id}")
    if provider:
        logger.info(f"  Provider: {provider}")
    logger.info(f"  PDF engine: {pdf_engine}")
    logger.info(f"  PDF size: ~{pdf_size_mb:.2f} MB")
    logger.info(f"  Max tokens: {payload['max_tokens']}")
    logger.debug(f"  Prompt length: {len(prompt)} characters")

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(
                f"Calling OpenRouter API (attempt {attempt + 1}/{MAX_RETRIES})..."
            )

            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=300,  # 5 minute timeout for large PDFs
            )

            logger.debug(f"Response status code: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")

            if response.status_code == 200:
                try:
                    result = parse_openrouter_success_response(response)
                    logger.info("API call successful")
                    return result
                except (ValueError, KeyError, IndexError) as parse_error:
                    error_msg = (
                        f"Failed to parse successful API response: {parse_error}"
                    )
                    logger.error(error_msg)
                    logger.error(
                        f"Response content (first 1000 chars): {response.text[:1000]}"
                    )
                    return {
                        "success": False,
                        "error": error_msg,
                        "status_code": response.status_code,
                        "response_preview": response.text[:500],
                    }
            else:
                # Non-200 status code - log detailed error information
                error_details = {
                    "status_code": response.status_code,
                    "status_reason": response.reason,
                    "headers": dict(response.headers),
                }

                try:
                    error_body = response.json()
                    error_details["error_body"] = error_body
                    error_message = error_body.get("error", {}).get(
                        "message", "Unknown error"
                    )
                    error_type = error_body.get("error", {}).get("type", "Unknown")
                    logger.error(f"API Error Response:")
                    logger.error(f"  Status: {response.status_code} {response.reason}")
                    logger.error(f"  Error Type: {error_type}")
                    logger.error(f"  Error Message: {error_message}")
                    if "error" in error_body and "code" in error_body["error"]:
                        logger.error(f"  Error Code: {error_body['error']['code']}")
                    logger.debug(
                        f"  Full error response: {json.dumps(error_body, indent=2)}"
                    )
                    parsed_text = extract_text_from_file_annotations(error_body)
                    if parsed_text:
                        logger.warning(
                            "OpenRouter parsed the PDF but the provider rejected "
                            "the file payload; retrying with parsed text only"
                        )
                        fallback_result = call_openrouter_text_fallback(
                            headers=headers,
                            model_id=model_id,
                            prompt=prompt,
                            parsed_text=parsed_text,
                            provider=provider,
                            max_tokens=payload["max_tokens"],
                            temperature=payload["temperature"],
                            reasoning=payload.get("reasoning"),
                        )
                        if fallback_result.get("success"):
                            logger.info("Parsed-text fallback succeeded")
                            return fallback_result
                        logger.error(
                            "Parsed-text fallback failed: %s",
                            fallback_result.get("error"),
                        )
                        error_details["text_fallback"] = fallback_result
                except (ValueError, KeyError):
                    # Response is not JSON, log as text
                    error_details["response_text"] = response.text
                    logger.error(f"API Error Response (non-JSON):")
                    logger.error(f"  Status: {response.status_code} {response.reason}")
                    logger.error(
                        f"  Response body (first 2000 chars): {response.text[:2000]}"
                    )
                    error_message = f"HTTP {response.status_code}: {response.reason}"

                if attempt < MAX_RETRIES - 1:
                    import time

                    wait_time = 2**attempt  # Exponential backoff
                    logger.warning(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    # Last attempt failed
                    return {
                        "success": False,
                        "error": (
                            error_message
                            if "error_message" in locals()
                            else f"HTTP {response.status_code}: {response.reason}"
                        ),
                        "error_details": error_details,
                        "status_code": response.status_code,
                    }

        except requests.exceptions.Timeout as e:
            error_msg = f"Request timed out after 300 seconds (attempt {attempt + 1}/{MAX_RETRIES})"
            logger.error(error_msg)
            logger.error(f"Timeout exception details: {type(e).__name__}: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                import time

                wait_time = 2**attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": "Timeout",
                    "timeout_seconds": 300,
                }
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error (attempt {attempt + 1}/{MAX_RETRIES})"
            logger.error(error_msg)
            logger.error(f"Connection error details: {type(e).__name__}: {str(e)}")
            if hasattr(e, "request"):
                logger.error(f"Request URL: {e.request.url if e.request else 'N/A'}")
            if attempt < MAX_RETRIES - 1:
                import time

                wait_time = 2**attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": "ConnectionError",
                    "error_details": str(e),
                }
        except requests.exceptions.RequestException as e:
            error_msg = f"Request exception (attempt {attempt + 1}/{MAX_RETRIES})"
            logger.error(error_msg)
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(
                    f"Response text (first 1000 chars): {e.response.text[:1000]}"
                )
            if attempt < MAX_RETRIES - 1:
                import time

                wait_time = 2**attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                }
        except Exception as e:
            # Catch any other unexpected exceptions
            import traceback

            error_msg = f"Unexpected error during API call (attempt {attempt + 1}/{MAX_RETRIES})"
            logger.error(error_msg)
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception message: {str(e)}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            if attempt < MAX_RETRIES - 1:
                import time

                wait_time = 2**attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                    "traceback": traceback.format_exc(),
                }

    return {
        "success": False,
        "error": "API call failed after all retries",
        "max_retries": MAX_RETRIES,
    }


def parse_markdown_sections(
    content: str,
    summary_mode: str = SUMMARY_MODE_FULL,
) -> dict:
    """Parse Markdown response into paper_label, metadata, and ai_summary.

    Supports two formats:
    1. Exact headings: # paper_label, # metadata, # ai_summary
    2. Flexible: first # heading is the label itself (e.g., # melitz2003trade),
       content between label and # ai_summary is metadata.
    """
    required_sections = ["paper_label", "metadata"]
    if summary_mode == SUMMARY_MODE_FULL:
        required_sections.append("ai_summary")

    # Try exact section heading matching first
    pattern = re.compile(
        r"^#\s*(paper_label|metadata|ai_summary)\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    matches = list(pattern.finditer(content))
    found_sections = [match.group(1).lower() for match in matches]

    if all(s in found_sections for s in required_sections):
        # All exact headings found - parse normally
        sections: dict[str, str] = {}
        for idx, match in enumerate(matches):
            key = match.group(1).lower()
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
            section_text = content[start:end].strip()
            if not section_text:
                logger.warning(f"Section '{key}' is empty")
            sections[key] = section_text
        if "paper_label" in sections:
            sections["paper_label"] = sections["paper_label"].strip().strip("`").strip()
        return sections

    if summary_mode == SUMMARY_MODE_METADATA_ONLY:
        metadata_only = parse_metadata_only_markdown(content)
        if metadata_only:
            return metadata_only

        metadata_heading = re.search(
            r"^#\s*metadata\s*$",
            content,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if metadata_heading:
            before_metadata = content[: metadata_heading.start()].strip()
            metadata_text = content[metadata_heading.end() :].strip()
            label_match = re.search(r"^#\s+(.+?)\s*$", before_metadata, re.MULTILINE)
            if label_match:
                label_candidate = label_match.group(1).strip().strip("`")
                if re.match(r"^[a-z]+\d{4}[a-z_]+$", label_candidate):
                    logger.info(
                        "Metadata-only flexible parse: label='%s', metadata=%s chars",
                        label_candidate,
                        len(metadata_text),
                    )
                    return {
                        "paper_label": label_candidate,
                        "metadata": metadata_text,
                    }

        found_headings = re.findall(r"^#+\s*(.+?)\s*$", content, re.MULTILINE)
        raise ValueError(
            f"Missing required Markdown headings. Expected: {required_sections}. "
            f"Found headings: {found_headings[:10]}"
        )

    # Flexible fallback: look for # ai_summary and infer label from first heading
    ai_summary_pattern = re.compile(
        r"^#\s*ai_summary\s*$", flags=re.IGNORECASE | re.MULTILINE
    )
    ai_match = ai_summary_pattern.search(content)
    if not ai_match:
        found_headings = re.findall(r"^#+\s*(.+?)\s*$", content, re.MULTILINE)
        raise ValueError(
            f"Missing required Markdown headings. Expected: {required_sections}. "
            f"Found {len(found_headings)} headings but none match required sections: "
            f"{found_headings[:10]}"
        )

    before_summary = content[: ai_match.start()].strip()
    after_summary = content[ai_match.end() :].strip()

    # Check if first non-empty line is a bare label (no # prefix)
    lines = before_summary.split("\n")
    first_line = lines[0].strip().strip("`") if lines else ""
    if re.match(r"^[a-z]+\d{4}[a-z_]+$", first_line):
        metadata_text = "\n".join(lines[1:]).strip()
        # Strip leading "# metadata" heading if present
        metadata_text = re.sub(
            r"^#\s*metadata\s*\n", "", metadata_text, flags=re.IGNORECASE
        )
        logger.info(
            f"Flexible parse (bare label): label='{first_line}', "
            f"metadata={len(metadata_text)} chars, "
            f"ai_summary={len(after_summary)} chars"
        )
        return {
            "paper_label": first_line,
            "metadata": metadata_text,
            "ai_summary": after_summary,
        }

    # First level-1 heading before ai_summary is the paper label
    label_pattern = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
    label_match = label_pattern.search(before_summary)
    if label_match:
        label_candidate = label_match.group(1).strip().strip("`")
        # Accept if it looks like authorYearTopic (lowercase with digits)
        if re.match(r"^[a-z]+\d{4}[a-z_]+$", label_candidate):
            metadata_text = before_summary[label_match.end() :].strip()
            # Strip leading "# metadata" heading if present (common in Gemini output)
            metadata_text = re.sub(
                r"^#\s*metadata\s*\n", "", metadata_text, flags=re.IGNORECASE
            )
            logger.info(
                f"Flexible parse: label='{label_candidate}', "
                f"metadata={len(metadata_text)} chars, "
                f"ai_summary={len(after_summary)} chars"
            )
            return {
                "paper_label": label_candidate,
                "metadata": metadata_text,
                "ai_summary": after_summary,
            }

    metadata_first = parse_metadata_first_markdown(content)
    if metadata_first:
        return metadata_first

    found_headings = re.findall(r"^#+\s*(.+?)\s*$", content, re.MULTILINE)
    raise ValueError(
        f"Could not extract paper_label from headings. "
        f"Found headings: {found_headings[:10]}"
    )


def parse_api_response(
    content: str,
    summary_mode: str = SUMMARY_MODE_FULL,
) -> dict:
    """Parse response from API (Markdown or JSON)."""
    if not content or not content.strip():
        raise ValueError("API response is empty or contains only whitespace")

    logger.debug(f"Parsing API response (length: {len(content)} characters)")

    # Remove markdown code blocks if present
    content = re.sub(r"^```json\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"^```\s*$", "", content, flags=re.MULTILINE)
    content = content.strip()

    # Prefer Markdown section parsing if headings are present
    markdown_heading_pattern = r"^#\s*(paper_label|metadata|ai_summary)\s*$"
    if re.search(markdown_heading_pattern, content, re.MULTILINE):
        logger.debug("Detected Markdown format with section headings")
        try:
            parsed = parse_markdown_sections(content, summary_mode)
            logger.debug(
                f"Successfully parsed Markdown sections: {list(parsed.keys())}"
            )
            return parsed
        except ValueError as e:
            logger.error(f"Failed to parse Markdown response: {e}")
            logger.error(f"Content preview (first 1000 chars): {content[:1000]}")
            # Check which sections are missing
            found_sections = re.findall(markdown_heading_pattern, content, re.MULTILINE)
            expected_sections = ["paper_label", "metadata"]
            if summary_mode == SUMMARY_MODE_FULL:
                expected_sections.append("ai_summary")
            missing_sections = [s for s in expected_sections if s not in found_sections]
            if missing_sections:
                logger.error(f"Missing required sections: {missing_sections}")
            raise ValueError(
                f"Failed to parse Markdown sections: {e}. Found sections: {found_sections}, Missing: {missing_sections}"
            )

    if summary_mode == SUMMARY_MODE_METADATA_ONLY:
        metadata_only = parse_metadata_only_markdown(content)
        if metadata_only:
            return metadata_only

    # Fallback to JSON parsing for backward compatibility
    logger.debug("Attempting JSON parsing as fallback")
    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        json_content = json_match.group()
        logger.debug(f"Extracted JSON content (length: {len(json_content)} characters)")
    else:
        json_content = content

    try:
        parsed = json.loads(json_content)
        logger.debug(f"Successfully parsed JSON response")
        return parsed
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"JSON decode error at position {e.pos}: {e.msg}")
        logger.error(
            f"Content around error position: {json_content[max(0, e.pos-100):e.pos+100]}"
        )
        logger.error(f"Raw content preview (first 1000 chars): {content[:1000]}")
        raise ValueError(
            f"Invalid API response format - neither Markdown sections nor valid JSON found. "
            f"JSON error: {e.msg} at position {e.pos}. "
            f"Response appears to be neither Markdown with required headings nor valid JSON."
        )


def clean_markdown_content(content: str) -> str:
    """Remove artifacts and clean markdown content."""
    # Remove citation artifacts
    artifacts = [
        r"\[cite_start\]",
        r"\[cite_end\]",
        r"\[/cite\]",
        r"<cite_start>",
        r"<cite_end>",
        r"</cite>",
        r"\[ref\]",
        r"\[/ref\]",
        r"<ref>",
        r"</ref>",
        r"cite_start",
        r"cite_end",
    ]

    for artifact in artifacts:
        content = re.sub(artifact, "", content, flags=re.IGNORECASE)

    # Clean up extra whitespace
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def normalize_metadata_markdown(content: str) -> str:
    """Ensure metadata files keep required PaperHub fields."""
    content = content.strip()

    frontmatter_match = re.match(r"(?s)^---\n(.*?)\n---", content)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        body = content[frontmatter_match.end() :].lstrip()
        lines = frontmatter.splitlines()
        normalized_lines = []
        has_contributions = False
        skip_contribution_value = False

        for line in lines:
            if re.match(r"^contributions\s*:", line):
                normalized_lines.append("contributions:")
                has_contributions = True
                skip_contribution_value = True
                continue
            if skip_contribution_value and (
                line.startswith(" ") or line.startswith("\t")
            ):
                continue
            skip_contribution_value = False
            normalized_lines.append(line)

        if not has_contributions:
            insert_at = len(normalized_lines)
            for idx, line in enumerate(normalized_lines):
                if re.match(r"^interest\s*:", line):
                    insert_at = idx + 1
                    break
            normalized_lines.insert(insert_at, "contributions:")

        content = "---\n" + "\n".join(normalized_lines).rstrip() + "\n---\n\n" + body

    if not re.search(r"^##\s+Abstract\s*$", content, flags=re.IGNORECASE | re.MULTILINE):
        abstract_section = (
            "## Abstract\n"
            "[Abstract not found in provided pages]\n\n"
        )
        title_match = re.search(r"^#\s+.+$", content, flags=re.MULTILINE)
        if title_match:
            insert_at = title_match.end()
            content = content[:insert_at] + "\n\n" + abstract_section + content[insert_at:].lstrip()
        elif frontmatter_match:
            second_fence = re.match(r"(?s)^---\n.*?\n---", content)
            if second_fence:
                insert_at = second_fence.end()
                content = content[:insert_at] + "\n\n" + abstract_section + content[insert_at:].lstrip()
        else:
            content = abstract_section + content

    return content.strip()


def generate_metadata_markdown(data: dict) -> str:
    """Generate the metadata markdown file content."""
    meta = data.get("metadata", {})
    today = datetime.now().strftime("%Y-%m-%d")

    # Build YAML frontmatter
    authors_yaml = "\n".join(f"  - {author}" for author in meta.get("authors", []))
    tags_yaml = "\n".join(f"  - {tag}" for tag in meta.get("tags", []))

    # Build related papers section
    related_papers = meta.get("related_papers", [])
    related_section = ""
    if related_papers:
        related_items = [
            f"- [[{p.get('label', '')}]] - {p.get('context', '')}"
            for p in related_papers
        ]
        related_section = "\n".join(related_items)
    else:
        related_section = "[To be added]"

    content = f"""---
title: "{meta.get('title', '')}"
authors: 
{authors_yaml}
year: {meta.get('year', '')}
journal: "{meta.get('journal', '')}"
link: {meta.get('link', '')}
status:
  - initiated
tags:
{tags_yaml}
created: {today}
interest: none
contributions:
---

# {meta.get('title', '')}

## Abstract
{meta.get('abstract', '[Abstract not found in provided pages]')}

## Key Takeaways for My Research

**Main Contribution:**
{meta.get('main_contribution', '[To be filled]')}

**Methodology/Technique:**
{meta.get('methodology_technique', '[To be filled]')}

**Relevance to My Work:** 
[To be filled]

## Quick Reference
{meta.get('quick_reference', '[To be filled]')}

## Related Papers
{related_section}

## Research Ideas
[To be added]
"""

    return clean_markdown_content(content)


def generate_summary_markdown(data: dict) -> str:
    """Generate the AI summary markdown file content."""
    meta = data.get("metadata", {})
    summary = data.get("ai_summary", {})
    today = datetime.now().strftime("%Y-%m-%d")

    # Helper to safely get nested values
    def get_nested(d, *keys, default="[Not available]"):
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key, {})
            else:
                return default
        return d if d else default

    # Build methodology section
    methodology = summary.get("methodology", {})
    data_section = methodology.get("data", {})
    model_section = methodology.get("model_framework", {})
    ident_section = methodology.get("identification_strategy", {})

    # Build findings section
    findings = summary.get("main_findings", {})
    secondary = findings.get("secondary_findings", [])
    secondary_text = (
        "\n".join(f"{i+1}. {f}" for i, f in enumerate(secondary))
        if secondary
        else "[Not specified]"
    )

    magnitudes = findings.get("quantitative_magnitudes", [])
    magnitudes_text = (
        "\n".join(f"- {m}" for m in magnitudes) if magnitudes else "[Not specified]"
    )

    # Build literature context
    lit_context = summary.get("literature_context", {})
    builds_on = lit_context.get("builds_on", [])
    builds_on_text = (
        "\n".join(f"- {p}" for p in builds_on) if builds_on else "[Not specified]"
    )

    # Build policy implications
    implications = summary.get("policy_implications", [])
    implications_text = (
        "\n".join(f"- {imp}" for imp in implications)
        if implications
        else "[Not specified]"
    )

    # Build limitations
    limitations = summary.get("limitations", [])
    limitations_text = (
        "\n".join(f"{i+1}. {lim}" for i, lim in enumerate(limitations))
        if limitations
        else "[Not specified]"
    )

    # Build tables/figures
    tables_figures = summary.get("key_tables_figures", [])
    tables_text = ""
    for tf in tables_figures:
        tables_text += f"""
### Figure/Table {tf.get('number', 'X')}: {tf.get('title', 'Title')}
**Key Takeaway:** {tf.get('takeaway', '[Key insight]')}
**Location:** Page {tf.get('page', 'X')}
"""
    if not tables_text:
        tables_text = "[To be identified during reading]"

    # Build quotes
    quotes = summary.get("important_quotes", [])
    quotes_text = ""
    for q in quotes:
        quotes_text += f"""
> "{q.get('text', '')}"  
> — Page {q.get('page', 'X')}

**Why important:** {q.get('importance', '[Significance]')}
"""
    if not quotes_text:
        quotes_text = "[To be added during reading]"

    # Build technical notes
    tech_notes = summary.get("technical_notes", [])
    tech_text = (
        "\n".join(f"- {note}" for note in tech_notes) if tech_notes else "[To be added]"
    )

    # Build action items
    actions = summary.get("action_items", [])
    actions_text = (
        "\n".join(f"- [ ] {action}" for action in actions)
        if actions
        else "- [ ] [To be added]"
    )

    content = f"""# {meta.get('title', 'Paper Title')} - Summary

---

## Core Research Question

{summary.get('core_research_question', '[To be filled]')}

---

## Main Contribution

{summary.get('main_contribution', '[To be filled]')}

---

## Methodology

### Research Design
{methodology.get('research_design', '[To be filled]')}

### Data (if empirical)
- **Source:** {data_section.get('source', '[Not applicable or not specified]') if isinstance(data_section, dict) else data_section}
- **Details:** {data_section.get('details', '[Not specified]') if isinstance(data_section, dict) else ''}

### Model/Framework (if theoretical, please be detailed)
- **Setup:** {model_section.get('setup', '[Not applicable or not specified]') if isinstance(model_section, dict) else model_section}
- **Mechanism:** {model_section.get('mechanism', '[Not specified]') if isinstance(model_section, dict) else ''}
- **Solution Concept:** {model_section.get('solution_concept', '[Not specified]') if isinstance(model_section, dict) else ''}

### Identification Strategy (if causal, please be detailed)
- **Approach:** {ident_section.get('approach', '[Not applicable or not specified]') if isinstance(ident_section, dict) else ident_section}
- **Exogenous Variation:** {ident_section.get('exogenous_variation', '[Not specified]') if isinstance(ident_section, dict) else ''}
- **Identifying Assumptions:** {ident_section.get('identifying_assumptions', '[Not specified]') if isinstance(ident_section, dict) else ''}

---

## Main Findings

### Primary Result
{findings.get('primary_result', '[To be filled]')}

### Secondary Findings
{secondary_text}

### Quantitative Magnitudes (if applicable)
{magnitudes_text}

### Robustness
{findings.get('robustness', '[Not specified]')}

---

## Literature Context

### What it builds on
{builds_on_text}

### How it differs
{lit_context.get('how_it_differs', '[Not specified]')}

---

## Policy/Practical Implications

{implications_text}

---

## Limitations & Critiques

{limitations_text}

---

## Connections to My Research

**Relevant for:**
- [To be filled]
- [Methodology you might use or adapt]
- [Theory you're building on]

---


## Key Tables & Figures
{tables_text}

---

## Important Quotes
{quotes_text}

---

## Technical Notes

{tech_text}

---

## Action Items

{actions_text}

---

**Summary Completed:** {today}
"""

    return clean_markdown_content(content)


def create_directory_structure(output_dir: Path, paper_label: str) -> Path:
    """Create the paper directory structure."""
    paper_dir = output_dir / paper_label

    if paper_dir.exists():
        logger.warning(f"Directory already exists: {paper_dir}")
        # Add timestamp suffix to avoid overwriting
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        paper_dir = output_dir / f"{paper_label}_{timestamp}"
        logger.info(f"Using alternative directory: {paper_dir}")

    paper_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created directory: {paper_dir}")

    return paper_dir


def move_pdf(source_path: Path, dest_dir: Path) -> Path:
    """Move PDF to destination directory (preserving original filename)."""
    dest_path = dest_dir / source_path.name
    shutil.move(str(source_path), str(dest_path))
    logger.info(f"Moved PDF to: {dest_path}")
    return dest_path


def write_file(path: Path, content: str) -> None:
    """Write content to file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Created file: {path}")


RAW_OUTPUTS_DIR = Path(__file__).parent / "raw_outputs"


def format_yaml_model_value(model_id: str) -> str:
    """YAML frontmatter scalar for model id; quote if @ appears (email-like / reserved)."""
    if "@" in model_id:
        return json.dumps(model_id)
    return model_id


def save_raw_content(
    pdf_path: Path,
    content: str,
    usage: dict,
    model_label: str | None = None,
    pdf_engine: str | None = None,
    summary_mode: str | None = None,
) -> Path:
    """Save raw API content to file for manual processing by the skill."""
    RAW_OUTPUTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(pdf_path).stem
    raw_path = RAW_OUTPUTS_DIR / f"{stem}_{timestamp}.md"
    # Prepend usage metadata as YAML frontmatter
    header = f'---\npdf_path: "{pdf_path}"\n'
    if model_label:
        header += f"model: {format_yaml_model_value(model_label)}\n"
    if pdf_engine:
        header += f"pdf_engine: {pdf_engine}\n"
    if summary_mode:
        header += f"summary_mode: {summary_mode}\n"
    if usage:
        header += f"prompt_tokens: {usage.get('prompt_tokens', 'N/A')}\n"
        header += f"completion_tokens: {usage.get('completion_tokens', 'N/A')}\n"
        header += f"total_tokens: {usage.get('total_tokens', 'N/A')}\n"
        header += f"cost: {usage.get('cost', 'N/A')}\n"
    header += "---\n\n"
    raw_path.write_text(header + content, encoding="utf-8")
    logger.info(f"Saved raw content to: {raw_path}")
    return raw_path


def delete_raw_file(raw_path: Path) -> bool:
    """Delete a raw content file after successful processing."""
    try:
        raw_path.unlink()
        logger.info(f"Deleted raw content file: {raw_path}")
        # Remove raw_outputs dir if empty
        if RAW_OUTPUTS_DIR.exists() and not any(RAW_OUTPUTS_DIR.iterdir()):
            RAW_OUTPUTS_DIR.rmdir()
        return True
    except FileNotFoundError:
        logger.warning(f"Raw content file not found: {raw_path}")
        return False


def validate_pdf_path(pdf_path: Path) -> str | None:
    """Validate PDF path and return error message if invalid."""
    if not pdf_path.exists():
        return f"PDF file not found: {pdf_path}"
    if not pdf_path.suffix.lower() == ".pdf":
        return f"File is not a PDF: {pdf_path}"
    return None


SIDECAR_SUFFIXES = (".citation.md",)


def find_sidecar_for_pdf(pdf_path: Path) -> Path | None:
    """Return a citation sidecar sharing the PDF's stem in the same directory.

    The paper-finder skill drops a ``{stem}.citation.md`` next to each downloaded
    PDF; this pairs them so the citation can be used as authoritative context.
    """
    for suffix in SIDECAR_SUFFIXES:
        candidate = pdf_path.with_name(pdf_path.stem + suffix)
        if candidate.exists():
            return candidate
    return None


def fold_sidecar_into_instruction(pdf_path: Path, instruction: str) -> str:
    """Prepend citation-sidecar context (if any) to the user instruction."""
    sidecar = find_sidecar_for_pdf(pdf_path)
    if sidecar is None:
        return instruction
    try:
        citation = sidecar.read_text(encoding="utf-8").strip()
    except OSError:
        return instruction
    if not citation:
        return instruction
    block = (
        "Authoritative bibliographic metadata for this paper was retrieved from a "
        "citation database. Use it to fill title/authors/year/journal/DOI accurately "
        "and do not contradict it:\n\n"
        f"{citation}"
    )
    return f"{block}\n\n{instruction}".strip() if instruction else block


def organize_from_response(
    content: str,
    pdf_path: Path,
    model_label: str,
    pdf_engine: str,
    output_dir: Path,
    usage: dict | None = None,
    summary_mode: str = SUMMARY_MODE_FULL,
    metadata_only_page_limit: int | None = None,
    pages_sent: int | None = None,
    total_pdf_pages: int | None = None,
) -> dict:
    """Parse AI response and create organized output files.

    Shared by both the normal OpenRouter workflow and the --from-response mode.
    Returns a result dict with success status and file info.
    """
    if summary_mode not in SUMMARY_MODES:
        raise ValueError(f"Unknown summary mode: {summary_mode}")
    usage = usage or {}

    # Parse response
    try:
        content_length = len(content)
        logger.info(f"Parsing AI response (length: {content_length} characters)")
        parsed_data = parse_api_response(content, summary_mode)
        logger.info("Successfully parsed AI response")
    except ValueError as e:
        logger.error("=" * 60)
        logger.error("AI RESPONSE PARSING FAILED")
        logger.error("=" * 60)
        logger.error(f"PDF file: {pdf_path}")
        logger.error(f"Model: {model_label}")
        logger.error(f"Error: {e}")
        content_preview = content[:2000]
        logger.error(f"Response content preview (first 2000 chars):\n{content_preview}")
        logger.error(f"Full response length: {len(content)} characters")

        if content.startswith("```"):
            logger.error("Response appears to be wrapped in code fences")
        if "paper_label" not in content.lower() and "metadata" not in content.lower():
            logger.warning(
                "Response doesn't appear to contain expected sections (paper_label, metadata)"
            )
        logger.error("=" * 60)

        # Save raw content for manual processing
        error_payload = {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": f"Failed to parse AI response: {e}",
            "error_type": "ParseError",
            "model": model_label,
            "response_length": len(content),
            "usage": usage,
            "summary_mode": summary_mode,
        }
        if content.strip():
            raw_path = save_raw_content(
                pdf_path,
                content,
                usage,
                model_label=model_label,
                pdf_engine=pdf_engine,
                summary_mode=summary_mode,
            )
            error_payload["raw_content_file"] = str(raw_path)
            logger.info(f"Raw content saved for manual processing: {raw_path}")
        return error_payload

    paper_label = parsed_data.get("paper_label", "unknown_paper")
    logger.info(f"Paper label: {paper_label}")

    # Create output files
    try:
        paper_dir = create_directory_structure(output_dir, paper_label)
        actual_label = paper_dir.name

        sidecar_src = find_sidecar_for_pdf(pdf_path)
        new_pdf_path = move_pdf(pdf_path, paper_dir)
        if sidecar_src is not None and sidecar_src.exists():
            sidecar_dest = paper_dir / sidecar_src.name
            shutil.move(str(sidecar_src), str(sidecar_dest))
            logger.info(f"Moved citation sidecar to: {sidecar_dest}")

        # Generate and write metadata
        metadata_value = parsed_data.get("metadata")
        if isinstance(metadata_value, str):
            metadata_content = metadata_value.strip()
            metadata_content = re.sub(
                r"^```(?:yaml)?\s*\n", "", metadata_content, flags=re.MULTILINE
            )
            metadata_content = re.sub(r"\n```\s*$", "", metadata_content)
            metadata_content = metadata_content.strip()
            if not metadata_content.startswith("---"):
                metadata_content = "---\n" + metadata_content
        else:
            metadata_content = generate_metadata_markdown(parsed_data)
        metadata_content = normalize_metadata_markdown(metadata_content)
        metadata_path = paper_dir / f"{actual_label}.md"
        write_file(metadata_path, metadata_content)

        files_created = [f"{actual_label}.md"]

        if summary_mode == SUMMARY_MODE_FULL:
            # Generate and write summary
            summary_value = parsed_data.get("ai_summary")
            if isinstance(summary_value, str):
                summary_content = summary_value.strip()
            else:
                summary_content = generate_summary_markdown(parsed_data)

            # Add metadata frontmatter to summary
            summary_metadata = f"""---
model: {format_yaml_model_value(model_label)}
pdf_engine: {pdf_engine}
tokens_prompt: {usage.get('prompt_tokens', 'N/A')}
tokens_completion: {usage.get('completion_tokens', 'N/A')}
total_tokens: {usage.get('total_tokens', 'N/A')}
cost: {usage.get('cost', 'N/A')}
generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
---

"""
            summary_content = summary_metadata + summary_content
            summary_path = paper_dir / "ai_summary.md"
            write_file(summary_path, summary_content)
            files_created.append("ai_summary.md")

        result = {
            "success": True,
            "model": model_label,
            "pdf_engine": pdf_engine,
            "summary_mode": summary_mode,
            "paper_label": actual_label,
            "output_dir": str(paper_dir),
            "files_created": files_created,
            "pdf_moved": True,
            "pdf_path": str(new_pdf_path),
            "errors": [],
            "warnings": [],
        }
        if summary_mode == SUMMARY_MODE_METADATA_ONLY:
            result["metadata_only_page_limit"] = (
                metadata_only_page_limit or METADATA_ONLY_PAGE_LIMIT
            )
            if pages_sent is not None:
                result["pages_sent"] = pages_sent
            if total_pdf_pages is not None:
                result["total_pdf_pages"] = total_pdf_pages
        if usage:
            result["usage"] = usage

        logger.info("Paper organization complete!")
        return result

    except Exception as e:
        import traceback

        error_msg = f"Failed to create output files: {type(e).__name__}: {e}"
        logger.error("=" * 60)
        logger.error("OUTPUT CREATION FAILED")
        logger.error("=" * 60)
        logger.error(f"PDF file: {pdf_path}")
        logger.error(f"Paper label: {paper_label}")
        logger.error(f"Error: {error_msg}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        logger.error("=" * 60)
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "paper_label": paper_label,
            "error": error_msg,
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


def process_pdf(
    pdf_path: Path,
    api_key: str,
    model: str,
    pdf_engine: str,
    output_dir: Path,
    verbose: bool,
    additional_instruction: str = "",
    summary_mode: str = SUMMARY_MODE_FULL,
) -> dict:
    """Process a single PDF and return a result dict."""
    # Validate PDF path
    error = validate_pdf_path(pdf_path)
    if error:
        logger.error(error)
        return {"success": False, "pdf_path": str(pdf_path), "error": error}

    if summary_mode not in SUMMARY_MODES:
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": f"Unknown summary mode: {summary_mode}",
            "error_type": "ValueError",
        }

    # Resolve model config before preparing the PDF because models choose how
    # PDF content enters the OpenRouter request.
    model_config = resolve_model_config(model)
    model_id = model_config["model_id"]
    provider = model_config.get("provider", {})
    reasoning = model_config.get("reasoning")
    pdf_input = resolve_pdf_input_config(model_config)
    pdf_input_mode = pdf_input["mode"]
    pdf_text_extractor = pdf_input.get("extractor")
    effective_pdf_engine = (
        pdf_text_extractor
        if pdf_input_mode == "text_extraction"
        else pdf_engine
    )

    temp_pdf_dir = None
    pdf_for_ai = pdf_path
    sample_info = None
    pdf_base64 = None
    pdf_text = None
    try:
        if summary_mode == SUMMARY_MODE_METADATA_ONLY:
            temp_pdf_dir = TemporaryDirectory(prefix="paperhub_metadata_only_")
            sample_info = create_first_pages_pdf(
                pdf_path=pdf_path,
                page_limit=METADATA_ONLY_PAGE_LIMIT,
                output_dir=Path(temp_pdf_dir.name),
            )
            pdf_for_ai = sample_info.sample_path
            logger.info(
                "Metadata-only mode: sending first %s/%s pages from %s",
                sample_info.pages_sent,
                sample_info.total_pages,
                pdf_path.name,
            )

        if pdf_input_mode == "text_extraction":
            pdf_text = extract_pdf_context(pdf_for_ai, pdf_text_extractor)
        else:
            pdf_base64 = encode_pdf_to_base64(pdf_for_ai)
    except FileNotFoundError as e:
        error = f"PDF file not found: {e}"
        logger.error(error)
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": error,
            "error_type": "FileNotFoundError",
        }
    except PermissionError as e:
        error = f"Permission denied reading PDF: {e}"
        logger.error(error)
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": error,
            "error_type": "PermissionError",
        }
    except MemoryError as e:
        error = f"Out of memory while reading PDF: {e}"
        logger.error(error)
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": error,
            "error_type": "MemoryError",
        }
    except Exception as e:
        import traceback

        error = f"Failed to prepare PDF input: {type(e).__name__}: {e}"
        logger.error(error)
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": error,
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }
    finally:
        if temp_pdf_dir is not None:
            temp_pdf_dir.cleanup()
            temp_pdf_dir = None

    # Call API
    additional_instruction = fold_sidecar_into_instruction(pdf_path, additional_instruction)
    prompt = create_analysis_prompt(additional_instruction, summary_mode)
    logger.info(f"Processing PDF: {pdf_path.name}")
    try:
        if pdf_input_mode == "text_extraction":
            api_result = call_openrouter_text_api(
                api_key=api_key,
                model_id=model_id,
                prompt=prompt,
                pdf_text=pdf_text or "",
                provider=provider,
                reasoning=reasoning,
                extractor=pdf_text_extractor,
            )
        else:
            api_result = call_openrouter_api(
                api_key,
                model_id,
                pdf_base64 or "",
                prompt,
                pdf_engine,
                provider,
                reasoning,
            )
        if not api_result.get("success"):
            error = api_result.get("error", "Unknown API error")
            error_type = api_result.get("error_type", "Unknown")
            status_code = api_result.get("status_code")
            error_details = api_result.get("error_details", {})

            logger.error("=" * 60)
            logger.error("API CALL FAILED")
            logger.error("=" * 60)
            logger.error(f"PDF file: {pdf_path}")
            logger.error(f"Model: {model_id}")
            logger.error(f"PDF input: {pdf_input_mode}")
            logger.error(f"PDF engine: {effective_pdf_engine}")
            logger.error(f"Error type: {error_type}")
            logger.error(f"Error message: {error}")
            if status_code:
                logger.error(f"HTTP status code: {status_code}")
            if error_details:
                logger.error(f"Error details: {json.dumps(error_details, indent=2)}")
            if "response_preview" in api_result:
                logger.error(f"Response preview: {api_result['response_preview']}")
            logger.error("=" * 60)

            return {
                "success": False,
                "pdf_path": str(pdf_path),
                "error": error,
                "error_type": error_type,
                "status_code": status_code,
                "error_details": error_details,
                "model": model_id,
                "pdf_engine": effective_pdf_engine,
                "pdf_input_mode": pdf_input_mode,
                "summary_mode": summary_mode,
            }

        # Delegate parsing and file creation to shared helper
        return organize_from_response(
            content=api_result.get("content") or "",
            pdf_path=pdf_path,
            model_label=model_id,
            pdf_engine=effective_pdf_engine,
            output_dir=output_dir,
            usage=api_result.get("usage"),
            summary_mode=summary_mode,
            metadata_only_page_limit=METADATA_ONLY_PAGE_LIMIT,
            pages_sent=sample_info.pages_sent if sample_info else None,
            total_pdf_pages=sample_info.total_pages if sample_info else None,
        )
    finally:
        if temp_pdf_dir is not None:
            temp_pdf_dir.cleanup()


def prepare_cli_input(
    pdf_path: Path,
    summary_mode: str,
    additional_instruction: str = "",
    external_cli_engine: str = "gemini-cli",
    agy_model: str | None = None,
) -> dict:
    """Prepare prompt and CLI-readable PDF input for an external CLI run."""
    error = validate_pdf_path(pdf_path)
    if error:
        return {"success": False, "pdf_path": str(pdf_path), "error": error}
    if summary_mode not in SUMMARY_MODES:
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": f"Unknown summary mode: {summary_mode}",
            "error_type": "ValueError",
        }
    if external_cli_engine not in {"gemini-cli", "agy-cli"}:
        return {
            "success": False,
            "pdf_path": str(pdf_path),
            "error": f"Unknown external CLI engine: {external_cli_engine}",
            "error_type": "ValueError",
        }

    resolved_agy_model = None
    if external_cli_engine == "agy-cli":
        resolved_agy_model = configure_agy_cli_model(
            agy_model,
            default_model=AGY_CLI_MODEL,
            allowed_models=AGY_CLI_MODEL_LIST,
        )

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    work_dir = CLI_WORK_DIR / f"{external_cli_engine.replace('-cli', '')}_{pdf_path.stem}_{run_id}"
    work_dir.mkdir(parents=True, exist_ok=False)

    try:
        additional_instruction = fold_sidecar_into_instruction(pdf_path, additional_instruction)
        prompt = create_analysis_prompt(additional_instruction, summary_mode)
        prompt_path = work_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        sample_info = None
        pdf_for_ai = pdf_path
        if summary_mode == SUMMARY_MODE_METADATA_ONLY:
            sample_info = create_first_pages_pdf(
                pdf_path=pdf_path,
                page_limit=METADATA_ONLY_PAGE_LIMIT,
                output_dir=work_dir,
            )
            pdf_for_ai = sample_info.sample_path

        pdf_for_ai_repo_relative = repo_relative_path(pdf_for_ai)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    result = {
        "success": True,
        "external_cli_engine": external_cli_engine,
        "summary_mode": summary_mode,
        "prompt_path": str(prompt_path),
        "pdf_for_ai_path": str(pdf_for_ai),
        "pdf_for_ai_repo_relative": pdf_for_ai_repo_relative,
        "pdf_for_ai_gemini_path": gemini_at_path(pdf_for_ai),
        "pdf_for_ai_agy_path": str(pdf_for_ai.resolve()),
        "original_pdf_path": str(pdf_path),
        "cleanup_dir": str(work_dir),
        "metadata_only_page_limit": METADATA_ONLY_PAGE_LIMIT,
    }
    if resolved_agy_model is not None:
        result["paperhub_root"] = str(PAPERHUB_ROOT)
        result["agy_cli_model"] = resolved_agy_model
        result["agy_model_label"] = agy_model_label(resolved_agy_model)
        result["agy_settings_path"] = str(agy_settings_path())
        result["response_begin"] = AGY_RESPONSE_BEGIN
        result["response_end"] = AGY_RESPONSE_END
    if sample_info:
        result["pages_sent"] = sample_info.pages_sent
        result["total_pdf_pages"] = sample_info.total_pages
    return result


def cleanup_cli_input(path: Path) -> bool:
    """Remove repo-local external CLI temporary input files."""
    cleanup_path = ensure_safe_cli_cleanup_path(path)
    if cleanup_path.is_dir():
        shutil.rmtree(cleanup_path)
        return True
    if cleanup_path.exists():
        cleanup_path.unlink()
        return True
    return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Process research paper PDFs and generate organized documentation"
    )
    parser.add_argument(
        "pdf_path",
        nargs="*",
        help="Path(s) to the PDF file(s). Provide multiple paths to process in parallel.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenRouter model ID (default: {DEFAULT_MODEL['model_id']})",
    )
    parser.add_argument(
        "--pdf-engine",
        default=DEFAULT_PDF_ENGINE,
        help=f"PDF processing engine (default: {DEFAULT_PDF_ENGINE})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--instruction",
        default="",
        help="Additional instructions to inject into the analysis prompt",
    )
    parser.add_argument(
        "--summary-mode",
        choices=SUMMARY_MODES,
        default=SUMMARY_MODE_FULL,
        help="Summary mode: full writes ai_summary.md; metadata-only writes metadata only",
    )
    parser.add_argument(
        "--prepare-cli-input",
        action="store_true",
        help="Prepare prompt and external-CLI-readable PDF input, then print JSON and exit",
    )
    parser.add_argument(
        "--external-cli-engine",
        choices=("gemini-cli", "agy-cli", "coding-agent"),
        default=None,
        help="External engine used with --prepare-cli-input/--from-response",
    )
    parser.add_argument(
        "--agy-model",
        default=None,
        help="Agy CLI model label; defaults to config AGY_CLI_MODEL",
    )
    parser.add_argument(
        "--cleanup-cli-input",
        metavar="PATH",
        help="Delete a repo-local temporary input path created by --prepare-cli-input",
    )
    parser.add_argument(
        "--delete-raw",
        metavar="PATH",
        help="Delete a raw content file after manual processing",
    )
    # --from-response mode: organize files from a pre-generated AI response
    parser.add_argument(
        "--from-response",
        action="store_true",
        help="Organize files from a pre-generated AI response (skip API call)",
    )
    parser.add_argument(
        "--response-file",
        metavar="PATH",
        help="Path to file containing pre-generated AI response text (used with --from-response)",
    )
    parser.add_argument(
        "--pdf-path-arg",
        metavar="PATH",
        help="PDF path for --from-response mode (since positional pdf_path may be empty)",
    )
    parser.add_argument(
        "--model-label",
        default="unknown",
        help="Model label for ai_summary.md frontmatter (used with --from-response)",
    )
    parser.add_argument(
        "--tokens-prompt",
        type=int,
        default=None,
        help="Prompt token count (used with --from-response)",
    )
    parser.add_argument(
        "--tokens-completion",
        type=int,
        default=None,
        help="Completion token count (used with --from-response)",
    )
    parser.add_argument(
        "--tokens-thinking",
        type=int,
        default=None,
        help="Thinking token count (used with --from-response)",
    )
    parser.add_argument(
        "--tokens-cached",
        type=int,
        default=None,
        help="Cached token count (used with --from-response)",
    )
    parser.add_argument(
        "--tokens-total",
        type=int,
        default=None,
        help="Total token count (used with --from-response)",
    )
    parser.add_argument(
        "--gemini-stderr-file",
        metavar="PATH",
        help="Gemini CLI stderr file to inspect before organizing --from-response output",
    )
    parser.add_argument(
        "--gemini-output-json",
        metavar="PATH",
        help="Gemini CLI JSON output file to inspect before organizing --from-response output",
    )
    parser.add_argument(
        "--agy-stderr-file",
        metavar="PATH",
        help="Agy CLI stderr file to inspect before organizing --from-response output",
    )
    parser.add_argument(
        "--agy-log-file",
        metavar="PATH",
        help="Agy CLI log file to inspect before organizing --from-response output",
    )

    args = parser.parse_args()

    global logger
    logger = setup_logging(args.verbose)

    # Handle --cleanup-cli-input and exit
    if args.cleanup_cli_input:
        try:
            cleanup_path = Path(args.cleanup_cli_input)
            success = cleanup_cli_input(cleanup_path)
            result = {"success": success, "deleted": str(cleanup_path)}
        except Exception as e:
            result = {
                "success": False,
                "error": f"Failed to clean up CLI input: {type(e).__name__}: {e}",
            }
        print(json.dumps(result))
        sys.exit(0 if result.get("success") else 1)

    # Handle --delete-raw and exit
    if args.delete_raw:
        raw_path = Path(args.delete_raw).resolve()
        success = delete_raw_file(raw_path)
        result = {"success": success, "deleted": str(raw_path)}
        print(json.dumps(result))
        sys.exit(0 if success else 1)

    # Handle --prepare-cli-input and exit
    if args.prepare_cli_input:
        pdf_path_str = args.pdf_path_arg or (
            args.pdf_path[0] if args.pdf_path else None
        )
        if not pdf_path_str:
            parser.error(
                "PDF path is required with --prepare-cli-input "
                "(use --pdf-path-arg or positional)"
            )
        try:
            result = prepare_cli_input(
                pdf_path=Path(pdf_path_str).resolve(),
                summary_mode=args.summary_mode,
                additional_instruction=args.instruction,
                external_cli_engine=args.external_cli_engine or "gemini-cli",
                agy_model=args.agy_model,
            )
        except Exception as e:
            result = {
                "success": False,
                "pdf_path": str(Path(pdf_path_str).resolve()),
                "error": f"Failed to prepare CLI input: {type(e).__name__}: {e}",
                "error_type": type(e).__name__,
            }
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("success") else 1)

    # Handle --from-response mode
    if args.from_response:
        if not args.response_file:
            parser.error("--response-file is required with --from-response")
        pdf_path_str = args.pdf_path_arg or (
            args.pdf_path[0] if args.pdf_path else None
        )
        if not pdf_path_str:
            parser.error(
                "PDF path is required with --from-response (use --pdf-path-arg or positional)"
            )

        response_path = Path(args.response_file).resolve()
        if not response_path.exists():
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"Response file not found: {response_path}",
                    }
                )
            )
            sys.exit(1)

        raw_content = response_path.read_text(encoding="utf-8")
        pdf_path = Path(pdf_path_str).resolve()
        output_dir = Path(args.output_dir).resolve()

        external_cli_engine = args.external_cli_engine
        if external_cli_engine is None:
            if args.model_label.startswith("current-coding-agent"):
                external_cli_engine = "coding-agent"
            elif (
                args.agy_stderr_file
                or args.agy_log_file
                or args.model_label.endswith(" (Agy CLI)")
            ):
                external_cli_engine = "agy-cli"
            else:
                external_cli_engine = "gemini-cli"

        content = raw_content
        cli_problems: list[str] = []
        cli_error = "External CLI did not reliably read the PDF"
        cli_error_type = "ExternalCliPdfReadError"
        if external_cli_engine == "gemini-cli":
            cli_problems = validate_gemini_cli_run(
                stderr_path=Path(args.gemini_stderr_file).resolve()
                if args.gemini_stderr_file
                else None,
                output_json_path=Path(args.gemini_output_json).resolve()
                if args.gemini_output_json
                else None,
            )
            cli_error = "Gemini CLI did not reliably read the PDF"
            cli_error_type = "GeminiCliPdfReadError"
        elif external_cli_engine == "agy-cli":
            cli_problems = validate_agy_cli_run(
                stdout_text=raw_content,
                stderr_path=Path(args.agy_stderr_file).resolve()
                if args.agy_stderr_file
                else None,
                log_path=Path(args.agy_log_file).resolve() if args.agy_log_file else None,
            )
            cli_error = "Agy CLI did not reliably read the PDF"
            cli_error_type = "AgyCliPdfReadError"
            if not cli_problems:
                content = extract_agy_response_block(raw_content)
        elif external_cli_engine != "coding-agent":
            parser.error(f"Unknown external CLI engine: {external_cli_engine}")

        if cli_problems:
            result = {
                "success": False,
                "pdf_path": str(pdf_path),
                "error": cli_error,
                "error_type": cli_error_type,
                "problems": cli_problems,
            }
            output = {
                "success": False,
                "total": 1,
                "succeeded": 0,
                "failed": 1,
                "results": [result],
            }
            print(json.dumps(output, indent=2))
            sys.exit(1)

        model_label = args.model_label
        if external_cli_engine == "agy-cli" and model_label == "unknown":
            resolved_agy_model = resolve_agy_cli_model(
                args.agy_model,
                default_model=AGY_CLI_MODEL,
                allowed_models=AGY_CLI_MODEL_LIST,
            )
            model_label = agy_model_label(resolved_agy_model)

        pdf_engine = {
            "agy-cli": "agy-native",
            "coding-agent": "coding-agent",
        }.get(external_cli_engine, "gemini-native")

        usage = {}
        if args.tokens_prompt is not None:
            usage["prompt_tokens"] = args.tokens_prompt
        if args.tokens_completion is not None:
            usage["completion_tokens"] = args.tokens_completion
        if args.tokens_thinking is not None:
            usage["thinking_tokens"] = args.tokens_thinking
        if args.tokens_cached is not None:
            usage["cached_tokens"] = args.tokens_cached
        if args.tokens_total is not None:
            usage["total_tokens"] = args.tokens_total

        result = organize_from_response(
            content=content,
            pdf_path=pdf_path,
            model_label=model_label,
            pdf_engine=pdf_engine,
            output_dir=output_dir,
            usage=usage or None,
            summary_mode=args.summary_mode,
            metadata_only_page_limit=METADATA_ONLY_PAGE_LIMIT,
        )
        output = {
            "success": result.get("success", False),
            "total": 1,
            "succeeded": 1 if result.get("success") else 0,
            "failed": 0 if result.get("success") else 1,
            "results": [result],
        }
        print(json.dumps(output, indent=2))
        sys.exit(0 if result.get("success") else 1)

    if not args.pdf_path:
        parser.error(
            "pdf_path is required when not using --delete-raw or --from-response"
        )

    # Get API key
    api_key = get_api_key()

    pdf_paths = [Path(path).resolve() for path in args.pdf_path]
    output_dir = Path(args.output_dir).resolve()
    model = args.model if args.model is not None else DEFAULT_MODEL

    results = []
    max_workers = min(4, len(pdf_paths)) if pdf_paths else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_pdf,
                path,
                api_key,
                model,
                args.pdf_engine,
                output_dir,
                args.verbose,
                args.instruction,
                args.summary_mode,
            ): path
            for path in pdf_paths
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    successes = [r for r in results if r.get("success")]
    failures = [r for r in results if not r.get("success")]

    # Log summary
    logger.info("=" * 60)
    logger.info("PROCESSING SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total PDFs processed: {len(results)}")
    logger.info(f"Successful: {len(successes)}")
    logger.info(f"Failed: {len(failures)}")

    if failures:
        logger.error("\nFAILED PROCESSING DETAILS:")
        for i, failure in enumerate(failures, 1):
            logger.error(f"\n  Failure {i}:")
            logger.error(f"    PDF: {failure.get('pdf_path', 'Unknown')}")
            logger.error(f"    Error: {failure.get('error', 'Unknown error')}")
            logger.error(f"    Error Type: {failure.get('error_type', 'Unknown')}")
            if failure.get("status_code"):
                logger.error(f"    HTTP Status: {failure.get('status_code')}")
            if failure.get("model"):
                logger.error(f"    Model: {failure.get('model')}")
            if failure.get("error_details"):
                logger.error(
                    f"    Details: {json.dumps(failure.get('error_details'), indent=6)}"
                )

    output = {
        "success": len(failures) == 0,
        "total": len(results),
        "succeeded": len(successes),
        "failed": len(failures),
        "results": results,
    }
    print(json.dumps(output, indent=2))

    if failures:
        logger.error("=" * 60)
        logger.error(f"Exiting with error code 1 due to {len(failures)} failure(s)")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
