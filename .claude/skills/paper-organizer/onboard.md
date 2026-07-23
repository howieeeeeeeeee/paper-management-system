# Onboarding Flow

Read `onboarding_questionnaire.md` first. Use it as the source of truth, verify the setup, ask only for missing or conflicting values, update the project configuration and onboarding ledger, then delete `onboarding_questionnaire.md` when onboarding is complete.

Goal: make this folder usable as a paper-library project inside an Obsidian vault. The root folder can have any name; do not assume it is named `PaperHub`. Onboarding should persist local choices, initialize the tag system, configure Obsidian Bases when possible, and leave the user with a small first run: drop PDFs into `to_be_organized/` and run metadata-only organization.

This is a questionnaire-first workflow. The user's main setup surface is the root `onboarding_questionnaire.md` file. The agent's job is to read that file, verify what is true on disk, fill gaps from existing config/artifacts, ask only about blockers, update the project, and then delete the questionnaire after onboarding completes.

## Source precedence

Use values in this order:

1. Explicit values in the user's current message.
2. Completed or partially completed answers in root `onboarding_questionnaire.md`.
3. Existing valid project config and filesystem artifacts.
4. Safe defaults documented in this skill.
5. `AskUserQuestion`, only for missing or conflicting values that block setup.

Do not guess the user's API key, external-engine availability, starter taxonomy, or Git preference. The current coding agent is the only automatic engine default. Do not ask about values already answered in the questionnaire and verified as valid. Never print or echo secrets from `.env`. Never ask the user for the Obsidian vault path up front: find it yourself by walking up parent directories from the paper-library root until one contains `.obsidian/` (details in section 1, step 2), and ask only if that search finds nothing.

## 0. Load questionnaire, state, and config

1. Find the paper-library root: nearest parent containing `paperhub_utils/paperhub/config.py`, `.claude/skills/paper-organizer/SKILL.md`, `SamplePaperBoard.base`, or `onboarding_questionnaire.md`.
2. If `onboarding_questionnaire.md` exists at the root, read it before asking anything.
   - Parse its frontmatter `status`.
   - Accepted statuses: `not_started`, `in_progress`, `ready_for_agent`, `done`.
   - If status is not `ready_for_agent` but the user explicitly asked to onboard now, proceed with any valid answers and ask only for blockers.
   - Treat checkbox answers and filled text blocks as user intent. Empty sections mean "unknown", not "no".
   - The questionnaire must never contain a real API key. If it appears to include one, tell the user to rotate it, remove it from the file, and use `paperhub_utils/config/.env` instead.
3. Parse the user's current onboarding request for inline overrides:
   - `My Obsidian vault is "..."`
   - starter tag notes such as fields, methodologies, topics, courses, seminars, reading lists, or workflow labels
   - one or more engine selections, Git, page-depth, paper-label, or Bases preferences
4. Read `paperhub_utils/config/onboarding.json` as the resumable progress ledger and `paperhub_utils/config/config.json` as the user-editable runtime config.
5. If either JSON file is missing, recreate it with the same schema and keys from the repository template.
6. If `onboarding.json` includes an `apply_questionnaire` step, mark it `done` after mapping valid questionnaire answers, or `skipped` if the questionnaire is absent because onboarding was already completed.
7. Record the parsed questionnaire status in `context.questionnaire_status`. At successful completion, set `context.questionnaire_deleted` to `true` after deleting the file.
8. Before doing work, verify any step marked `done` against the filesystem/config. If the artifact is missing or the config no longer matches, set that step back to `pending` with a short note.
9. Summarize what is already done and what remains before continuing.
10. When starting a step, mark it `in_progress`. When it finishes, update it to `done`, `skipped`, or `blocked`, set `completed_at` for finished/skipped steps, update relevant `context` fields, and save the JSON immediately.
11. If a step changes a real project setting, update `paperhub_utils/config/config.json` too. For example, Git preferences belong in JSON under the `git` block (`use_git`, `sync_to_remote`, `backup_abs_path`); `paperhub_utils/paperhub/config.py` exposes them as `USE_GIT`, `SYNC_TO_REMOTE_GIT`, and `GIT_BACKUP_ABS_PATH` for Python code.

Do not use `onboarding.json` as the only source of truth. It is a progress ledger; always verify important setup artifacts.

## 1. Discover and prepare the local project

1. Resolve the paper-library root and utilities directory. The utilities directory is usually `{paper_library_root}/paperhub_utils/`. Run `uv sync` and script checks from there.
2. Resolve the Obsidian vault root. Do not ask the user for this path up front — it is discoverable from the filesystem:
   - Prefer an explicit user message value (validate it before using it).
   - Otherwise auto-discover it: walk up from the paper-library root through its parent directories until one contains `.obsidian/`; that directory is the vault root. Record its absolute path, for example:

     ```bash
     d="$PWD"; while [ "$d" != "/" ]; do [ -d "$d/.obsidian" ] && { echo "$d"; break; }; d=$(dirname "$d"); done
     ```

   - Otherwise use `obsidian.vault_abs_path` from `paperhub_utils/config/config.json` if valid, or a vault path written in an older questionnaire.
   - If discovery finds nothing, the paper library is probably not inside an Obsidian vault (or the folder has never been opened in Obsidian, so `.obsidian/` does not exist yet). Ask the user for the vault root or ask them to open the surrounding folder as a vault in Obsidian, then retry discovery. Skip Bases only when the user explicitly asks to skip it.
3. Validate that the vault path exists and contains `.obsidian/`. If not, ask the user to confirm or correct it.
4. Derive the vault-relative paper-library path:
   - If the paper-library folder is inside the vault, derive it automatically (the paper-library root's path relative to the vault root, with forward slashes).
   - The agent should discover the paper-library root from the working directory or nearest project marker; do not ask the user for the PaperHub path during normal onboarding.
   - If the paper-library folder is not inside the provided vault and Bases setup is requested, ask where the library will live inside the vault before editing `.base` files.
   - Persist both resolved values into `paperhub_utils/config/config.json` under the `obsidian` block (`vault_abs_path`, `vault_relative_paper_library_path`) — `scripts/knowledge_base_search.py` reads `vault_abs_path` to search the whole vault and silently falls back to the paper-library root when it is null. Mirror `context.obsidian_vault_abs_path` and `context.vault_relative_paper_library_path` in `onboarding.json`. If the library is not inside a vault, leave both as `null`.
5. Confirm these folders exist or create them if missing: `to_be_organized/`, `organized/`, and `tags/`.
6. Read `paperhub_utils/config/config.json` for `available_engines`, the `git` block (`use_git`, `sync_to_remote`, `backup_abs_path`), `metadata_only_page_limit`, `tag_prompt`, and `obsidian`.
7. Read `paperhub_utils/paperhub/config.py` for exported script constants: `PAPERHUB_ROOT`, `TO_BE_ORGANIZED_DIR`, `DEFAULT_ORGANIZED_DIR`, `DEFAULT_TAGS_DIR`, `SAMPLE_BOARD_PATH`, `USER_CONFIG_PATH`, `ONBOARDING_STATE_PATH`, `AVAILABLE_ENGINES`, `SUPPORTED_ENGINE_IDS`, `USE_GIT`, `SYNC_TO_REMOTE_GIT`, `GIT_BACKUP_ABS_PATH`, `METADATA_ONLY_PAGE_LIMIT`, `INCLUDE_TAG_CONTEXT_IN_PROMPT`, `TAG_PROMPT_TOP_FIELD`, `TAG_PROMPT_TOP_TOPIC`, `TAG_PROMPT_TOP_METHODOLOGY`, `TAG_PROMPT_TOP_META`, `MODEL_LIST`, `AGY_CLI_MODEL`, `CODEX_CLI_MODEL`, `CODEX_CLI_REASONING_EFFORT`, `CODEX_CLI_MODEL_REASONING_PAIRS`, `CODEX_CLI_YOLO`, and `MY_RESEARCH_INTERESTS`.
8. **Make sure `uv` is here.** Every other step in this skill calls `uv run python ...`; if `uv` is not on `PATH`, nothing else works — even when `paperhub_utils/.venv/` already exists from a previous machine. This check is non-optional.

   ```bash
   command -v uv && uv --version
   ```

   If both commands succeed, skip to step 9. Otherwise `uv` is missing and must be installed before continuing — do not attempt to "work around" a missing `uv` by activating `.venv` manually, because downstream skill scripts hardcode `uv run`.

   **Get `uv` installed.** Prefer the official standalone installer on macOS; it works regardless of Homebrew Python's PEP 668 lockdown, which makes `python3 -m pip install uv` fail on system Pythons:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   The installer writes `uv` to `~/.local/bin/uv`. If that directory is not already on `PATH`, either restart the shell or export it for the current session: `export PATH="$HOME/.local/bin:$PATH"`.

   Fallbacks, in order:
   - `brew install uv` if Homebrew is available and the user prefers it.
   - `python3 -m pip install --user uv` only if a pip-managed Python is in use (not Homebrew/system Python — those will reject the install under PEP 668).
   - If none of the above succeed, read `setup/python_uv_recovery.md` and follow that recovery flow.

   After installing, verify again before moving on:

   ```bash
   uv --version
   ```

9. **Run `uv sync` to get the venv.** This is required even when `paperhub_utils/.venv/` already exists — without it, the lockfile and installed packages can drift, and a stale `.venv` from an iCloud-synced machine may be missing dependencies the current Python expects.

   ```bash
   cd "{paperhub_utils_dir}"
   uv sync
   ```

   If `uv sync` fails because the local environment is stale or broken, rebuild only the disposable local `.venv` and retry:

   ```bash
   rm -rf .venv
   uv sync
   ```

   Do not preserve or share `.venv` across iCloud-synced machines. `pyproject.toml` and `uv.lock` are the reproducible source of truth.

   Quick smoke test that the environment is usable:

   ```bash
   uv run python -c "from paperhub.config import AVAILABLE_ENGINES, AGY_CLI_MODEL, CODEX_CLI_MODEL, CODEX_CLI_REASONING_EFFORT, CODEX_CLI_YOLO; print(AVAILABLE_ENGINES, AGY_CLI_MODEL, CODEX_CLI_MODEL, CODEX_CLI_REASONING_EFFORT, CODEX_CLI_YOLO)"
   ```

## 2. Apply setup choices from the questionnaire

Ask only for missing or conflicting information.

- **Root path**: if the discovered root conflicts with `paperhub/config.py`, ask whether to use the detected root or the configured root.
- **Git (out-of-vault versioning)**: the vault must hold **no** `.git` — a live `.git` under
  iCloud gets corrupted. History lives in a separate git backup folder outside iCloud, driven by
  the `versioning-with-git` skill. Settings live in `config.json` under the `git` block:
  `use_git`, `sync_to_remote`, `backup_abs_path`. Parse the questionnaire's Section 3 "Git
  behavior" (three answers) and:
  - **If the questionnaire says not to use git versioning**, set `git.use_git = false`, update
    `context.use_git = false`, and skip the rest of the Git steps.
  - **If git versioning is requested**, set `git.use_git = true` and resolve the backup folder:
    - Take `git.backup_abs_path` from the questionnaire's "Git backup folder" answer. If blank,
      ask the user for an absolute path (`AskUserQuestion`).
    - **Validate it is outside any cloud folder.** If the path contains `Mobile Documents`,
      `Dropbox`, `Google Drive`, or `OneDrive`, warn and ask for a plain local path instead —
      do not proceed with a cloud path.
    - Set `sync_to_remote` from the "Sync to a remote" answer. Local-only versioning is the
      recommended and sufficient choice for most users; remote sync is optional.
    - If remote sync is selected, read the questionnaire's remote choice and optional URL:
      - If the user supplied a URL, retain it for remote setup. Treat it as a repository URL,
        never as authorization to store a password, personal access token, or other secret.
      - If the user says the backup folder already has a working remote, verify that `origin`
        exists with `git -C "{backup_abs_path}" remote get-url origin`. Do not replace a valid
        existing remote.
      - If neither a URL nor a verifiable existing `origin` is available, ask for the remote URL.
    - Persist all three into `config.json`'s `git` block and mirror `context.use_git`,
      `context.sync_to_remote`, `context.git_backup_abs_path` in `onboarding.json`.
  - **Set up the backup repo (first-time).** Verify `git --version`. If the backup folder has no
    `.git`, run the `versioning-with-git` skill's *First-time setup* (create the folder, mirror
    the vault in, `git init -b main`, initial commit). If `sync_to_remote` is true, use the
    questionnaire URL or a verified existing `origin`; ask only when neither is available, and
    never invent a URL.
  - **Remove any legacy in-vault `.git`.** If a `.git` exists at the paper-library root, tell the
    user it must be removed (its history is preserved in the backup folder + remote) and, once the
    backup repo holds the current state, `rm -rf` it from the vault. Never `git init` inside the
    vault.
  - **If git is requested but unavailable**, ask the user to install/configure git and rerun
    onboarding; set `git.use_git = false` until git is available.
- **Available AI engines**:
  - Canonical engine IDs are `coding-agent`, `openrouter`, `agy-cli`, and `codex-cli`.
  - Start the resolved list with every external engine selected under **Preferred AI engines** or explicitly requested in its Advanced Settings subsection. Multiple selections are valid.
  - Always include `coding-agent`, even when it was not written in the questionnaire or existing config. The current coding agent requires no installation check.
  - Verify every selected external engine before adding it:
    - `openrouter`: verify the API key as described below without printing it.
    - `agy-cli`: verify `agy` exists, then use the questionnaire confirmation or ask the user to confirm it launches and is signed in.
    - `codex-cli`: verify `command -v codex && codex exec --help`; use the questionnaire confirmation or ask the user to confirm authentication.
  - If verification fails, do not add that engine. Ask whether the user wants to configure it now or continue with the other verified engines.
  - Persist all verified IDs, preserving questionnaire order, to `config.json` as `available_engines`. Append `coding-agent` if it is absent. Mirror the same list to `context.available_engines` in `onboarding.json`.
- **OpenRouter API key**:
  - If the questionnaire selects or configures OpenRouter, verify that `OPENROUTER_API_KEY` is available from the environment or `paperhub_utils/config/.env`.
  - Verify without printing the key:

    ```bash
    uv run python -c "import os; from pathlib import Path; from dotenv import load_dotenv; load_dotenv(Path('config') / '.env'); print(bool(os.getenv('OPENROUTER_API_KEY')))"
    ```

  - If the key is missing, ask the user to edit `paperhub_utils/config/.env` and add exactly:

    ```text
    OPENROUTER_API_KEY=sk-or-v1-...
    ```

  - Do not ask the user to paste the key into chat except as a last resort, and label that path as not recommended because it puts the secret in the transcript.
- **AI engine models**:
  - The questionnaire's onboarding defaults are `Gemini 3.1 Pro (High)` for Agy CLI and
    `gpt-5.6-sol` with `high` reasoning for Codex CLI. When the user selects the onboarding
    default, persist the applicable value instead of inheriting a different local override.
  - If Codex CLI is selected, persist `codex_cli_model`, `codex_cli_reasoning_effort`, and `codex_cli_yolo` in `paperhub_utils/config/config.json`. When the user leaves any unspecified, fall back to the resolved defaults from `paperhub/config.py` (`CODEX_CLI_MODEL`, `CODEX_CLI_REASONING_EFFORT`, `CODEX_CLI_YOLO`) rather than hardcoding literals here.
  - Validate the selected Codex pair against `CODEX_CLI_MODEL_REASONING_PAIRS`; reject or ask about invalid pairs instead of silently changing the thinking level.
  - Verify Codex CLI availability without starting a paper run:

    ```bash
    command -v codex && codex exec --help
    ```
  - Explain that link ingestion first runs `scripts.paper_link_context`. Agy,
    Codex, and OpenRouter receive the completed local text and keep their web
    tools disabled. Browsing by the invoking coding agent is an optional
    preprocessing fallback; missing public facts may remain placeholders.
- **Metadata page depth**:
  - Use the questionnaire value if present.
  - Recommended values are `2` for fast first-run triage or `4` for more introduction/context.
  - Persist the integer to `paperhub_utils/config/config.json` as `metadata_only_page_limit`.

## 3. Initialize or validate the tag system

Read `tags/initialize_tag_system.md` and follow it. Key behavior:

- If no `tags/_internal/registry.json` exists, seed it from the questionnaire's "Starter Tag Taxonomy" section when present. If no questionnaire starter taxonomy is available, fall back to `paperhub_utils/config/default_tags.yaml`.
- Treat the questionnaire starter taxonomy as the first-run source of truth. Do not create `tags/tag_initialization.md` just to carry onboarding starter tags.
- `tags/tag_initialization.md` is optional and only for later bulk additions after onboarding. If it exists and has `status: ready`, process it; otherwise skip it silently.
- Do not interrogate the user about their domain or taxonomy. The questionnaire is the intake surface; empty tag sections mean no personal additions right now.
- Do not ask the user to choose tag prompt counts. The prompt builder already sends configured top existing tags to the AI prompt when `INCLUDE_TAG_CONTEXT_IN_PROMPT = True`.

After the tag flow finishes, update the `initialize_tag_system` step in `paperhub_utils/config/onboarding.json`.

## 4. Capture research interests

1. Prefer the questionnaire's "Research Interests" section.
2. If it is filled, overwrite `MY_RESEARCH_INTERESTS` in `paperhub_utils/paperhub/config.py` with that text as a triple-quoted string, preserving newlines.
3. If the questionnaire explicitly leaves research interests blank or the user asks to skip, set `MY_RESEARCH_INTERESTS = ""`.
4. If no questionnaire answer exists and the setup status is pending, use `AskUserQuestion`:

   > Set your research interests now? The AI uses them to generate connections between each paper and your work in the metadata file.

   Options:
   - **Yes, I'll describe them**: user supplies text; encourage fields, key topics, and methodologies.
   - **Skip, leave empty**.

5. Verify the change from the utilities directory:

   ```bash
   uv run python -c "import paperhub.config as cfg; print(repr(cfg.MY_RESEARCH_INTERESTS)[:200])"
   ```

6. Update `paperhub_utils/config/onboarding.json`: mark `configure_research_interests` as `done` or `skipped`, set `completed_at`, and record a one-line `notes` summary such as `set custom`, `kept existing`, or `skipped, left empty`.

## 5. Configure paper label format

The paper-label spec lives in `paperhub_utils/prompts/shared/paper_label.txt` and controls how AI summaries name new paper folders.

1. Prefer the questionnaire's paper-label choice.
2. Supported presets:
   - **Hybrid PascalCase with preserved acronyms (recommended)** (`hybrid_pascal`): `Melitz2003HeterogeneousFirms`, `AnDu2026MoralAlignment`, `Huynh_etal2026LLMCooperation`.
     - Single author: `{Surname}{Year}{TopicWords}`.
     - Two authors: `{Surname1}{Surname2}{Year}{TopicWords}`.
     - Three or more authors: `{Surname1}_etal{Year}{TopicWords}`.
     - Transliterate accents to ASCII. Use PascalCase for surnames and topic words, preserve familiar title/metadata acronyms such as `AI`, `LLM`, and `RCT` in uppercase, and use no separator except lowercase `_etal`.
   - **Compact author-year-topic** (`compact_topic`): `melitz2003heterogeneous`, `cardkrueger1994minimum`, `autoretal2020trade`.
     - Single author: `{first_author}{year}{topic_keyword}`.
     - Two authors: `{first_author}{second_author}{year}{topic_keyword}`.
     - Three or more authors: `{first_author}etal{year}{topic_keyword}`.
     - Use lowercase ASCII letters and numbers only, no spaces or separators.
   - **Compact author-year-title keywords** (`compact_title`): `melitz2003heterogeneousfirms`, `cardkrueger1994minimumwage`, `autoretal2020importcompetition`.
     - Same author/year rules as `compact_topic`.
     - Use one to three short title keywords instead of a broad topic keyword.
     - Use lowercase ASCII letters and numbers only, no spaces or separators.
   - **First-author plus etal for multi-author papers** (`first_author_etal`): `melitz2003heterogeneous`, `cardetal1994minimum`, `autoretal2020trade`.
     - Single author: `{first_author}{year}{topic_keyword}`.
     - Two or more authors: `{first_author}etal{year}{topic_keyword}`.
     - Use lowercase ASCII letters and numbers only, no spaces or separators.
   - **Author-year only** (`author_year`): `melitz2003`, `cardkrueger1994`, `autoretal2020`.
     - Single author: `{first_author}{year}`.
     - Two authors: `{first_author}{second_author}{year}`.
     - Three or more authors: `{first_author}etal{year}`.
     - Warn that this is concise but has higher collision risk.
   - **Readable snake_case** (`snake_case`): `melitz_2003_heterogeneous`, `card_krueger_1994_minimum`, `autor_etal_2020_trade`.
     - Separate components with underscores.
     - Single author: `{first_author}_{year}_{topic_keyword}`.
     - Two authors: `{first_author}_{second_author}_{year}_{topic_keyword}`.
     - Three or more authors: `{first_author}_etal_{year}_{topic_keyword}`.
   - **Zotero-style capitalized**: `Melitz2003Heterogeneous`, `CardKrueger1994Minimum`, `AutorEtAl2020Trade`.
     - Single author: `{FirstAuthor}{Year}{TopicKeyword}`.
     - Two authors: `{FirstAuthor}{SecondAuthor}{Year}{TopicKeyword}`.
     - Three or more authors: `{FirstAuthor}EtAl{Year}{TopicKeyword}`.
     - Use PascalCase components, no spaces or separators.
   - **Keep current**: leave `paperhub_utils/prompts/shared/paper_label.txt` unchanged.
   - **Custom**: use the user's written rules.
3. If the questionnaire has no paper-label choice, if multiple choices are checked, or if the checked choice conflicts with written custom rules, ask one concise follow-up.
4. If the questionnaire says Custom but the rules are ambiguous, ask only for the missing dimensions:
   - Single-author pattern and one worked example.
   - Two-author pattern and one worked example.
   - Three-or-more-author pattern and one worked example.
   - Casing.
   - Whether to keep a topic or title keyword and where it sits relative to the year.
   - Separator between components.
   - Whether to use `etal`, and for which author counts.
   - Collision handling if the label would duplicate an existing folder.
5. For Custom, read the resolved scheme back to the user as one confirmation summary with all three worked examples and wait for explicit confirmation before writing.
6. For any preset except **Keep current**, rewrite `paperhub_utils/prompts/shared/paper_label.txt` so the `# paper_label` heading is preserved and the body reflects the chosen rules with one worked example per author-count case. For **Keep current**, leave the file unchanged.
7. Record the resolved choice in `paperhub_utils/config/onboarding.json`:
   - Set `context.paper_label_format` to `hybrid_pascal`, `compact_topic`, `compact_title`, `first_author_etal`, `author_year`, `snake_case`, `zotero_capital`, `current`, or `custom`.
   - For custom, add a one-line plain-text summary in `notes` on the `configure_paper_label` step.
   - Mark `configure_paper_label` as `done`, set `completed_at`, and save the JSON immediately.
8. Treat the selection as the default for future papers only. Do not rename existing paper folders during onboarding, and continue accepting existing lowercase and legacy labels.

## 6. Configure Obsidian Bases

Obsidian Bases is a core plugin for database-like views over Markdown files and properties. A base is saved as a `.base` file, and the file content is YAML. By default a base includes every file in the vault, so onboarding must add filters that narrow the board to this paper library.

Obsidian `file.inFolder(...)` filters must use vault-relative paths, not absolute filesystem paths. Use forward slashes and preserve the user's actual folder casing.

1. Configure the bundled Base automatically. The questionnaire intentionally has no Bases checkbox or path field; its text explains that the agent will update the existing Base and provides only an optional notes box. Do not ask the user to choose whether to configure Bases during normal onboarding.
2. Skip Bases only when the user explicitly asks to skip it. In that case, record `configure_obsidian_bases` as `skipped` and continue.
3. Inspect root `*.base` files. The repository already includes `SamplePaperBoard.base`, so the normal onboarding task is to update its paths, not create another Base.
4. Derive the paper-library folder path relative to the Obsidian vault from the discovered project root and the vault absolute path.
5. If no valid vault absolute path is available after auto-discovery, ask for that path or ask the user to open the surrounding folder as an Obsidian vault before editing `.base` files. If the project root is outside the vault, ask where the paper library should live inside the vault.
6. After the vault path is settled, update the `is in path` filter shown by Obsidian Bases in `SamplePaperBoard.base`. In YAML this is the `file.inFolder(...)` path; set it to the path from the vault root to the intake folder, such as `file.inFolder("{vault_relative_paper_library}/to_be_organized")`. Never use an absolute filesystem path.
7. Update base filters so examples match the user's machine:
   - intake papers waiting to be organized: `file.inFolder("{vault_relative_paper_library}/to_be_organized")`
   - organized papers: `file.inFolder("{vault_relative_paper_library}/organized")`
   - all papers in this library: `file.inFolder("{vault_relative_paper_library}")`
8. Only create `SamplePaperBoard.base` if it is genuinely missing from the project.
9. Validate edited `.base` files as YAML. Tell the user they can open `SamplePaperBoard.base` in their vault to see the configured views. If Obsidian does not recognize `.base` files, tell the user to enable the Bases core plugin; do not edit `.obsidian/` settings unless the user explicitly asks.

## 7. Verify the setup

Run these checks from the utilities directory:

```bash
uv run python -m py_compile paperhub/config.py paperhub/prompt/builder.py scripts/paper_summarizer.py scripts/enrich.py
uv run python -c "from prompt.builder import render_tag_context_section; print(render_tag_context_section())"
```

The tag context output may be empty only if tag prompt context is disabled or the registry is intentionally minimal.

## 8. Finish and remove the questionnaire

End onboarding with:

1. The resolved paper-library root, utilities directory, organized directory, tags directory, vault-relative base path, and the Git settings (versioning on/off, backup folder path, remote sync on/off).
2. The final `available_engines` list, noting that current-agent processing is always available.
3. A short instruction to add PDFs to `to_be_organized/` or paste/save public
   paper links in a Markdown/plain-text note.
4. Two recommended first requests: metadata-only on one PDF, and link metadata
   for one pasted URL or a named section of `papers to find.md`.
5. A note that `full` mode creates `ai_summary.md` when a PDF is available,
   link metadata writes YAML plus abstract only, and `enrich` adds or refreshes
   summaries for folders that already exist.
6. A short done/remaining summary from `paperhub_utils/config/onboarding.json`.

If onboarding is complete and `onboarding_questionnaire.md` still exists, delete it from the root after recording the final state. Do not delete it if onboarding is blocked, if required answers remain unresolved, or if the user explicitly asks to keep it.

Onboarding is complete when config paths are valid, `available_engines` is explicit in `paperhub_utils/config/config.json` and contains `coding-agent`, the `git` block is explicit (and, when `use_git` is true, `backup_abs_path` points to an initialized out-of-iCloud repo and no `.git` remains in the vault), the tag registry exists, base files are configured or explicitly skipped, and the `uv` environment is installed in `paperhub_utils/`.
