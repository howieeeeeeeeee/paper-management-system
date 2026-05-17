# Python and uv Recovery

Read this only during onboarding when `uv` is missing or `uv sync` cannot create a working environment.

Goal: install `uv`, let `uv` manage the project Python environment, then return to `onboard.md` and run `uv sync` from `paperhub_utils/`.

`pyenv` is not required for PaperHub setup. If a user already uses `pyenv`, it is fine for their shell to provide Python, but do not recommend installing `pyenv` just to onboard this project.

## 1. Diagnose Existing Tools

Run:

```bash
command -v brew
command -v uv
uv --version
```

If `uv --version` works, skip to [3. Sync the project](#3-sync-the-project).

## 2. Install uv

Prefer Homebrew on macOS when available:

```bash
brew install uv
uv --version
```

If Homebrew is missing or the user does not want to use it, use the official standalone installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

If the standalone installer succeeds but `uv --version` still fails, the shell may not have the install directory on `PATH`. Ask before editing shell startup files; otherwise tell the user to restart their terminal or add the installer-reported bin directory to `PATH`.

If both Homebrew and the standalone installer are unavailable, ask the user to install either Homebrew or `uv` manually from the official uv documentation. Do not silently choose another system-wide installer.

## 3. Sync the project

Return to `onboard.md` and run setup from the utilities directory:

```bash
cd "{paperhub_utils_dir}"
uv sync
```

`uv sync` should create `.venv` and use a compatible Python for the project. The project requires Python `>=3.11`; `uv` can download and manage Python when needed.

If `uv sync` fails because no compatible Python is installed or downloadable automatically, install one through `uv`:

```bash
uv python install 3.12
uv sync
```

If the project later pins a Python version with `.python-version`, use that version instead of `3.12`:

```bash
uv python install
uv sync
```

If `uv sync` fails because the local environment is stale or broken, rebuild only the disposable local `.venv`:

```bash
rm -rf .venv
uv sync
```

Never preserve or share `.venv` across iCloud-synced machines. `pyproject.toml` and `uv.lock` are the reproducible source of truth.

## 4. Finish

When setup succeeds, verify the environment from `paperhub_utils/`:

```bash
uv run python --version
uv run python -m py_compile config.py prompt/builder.py paper_summarizer.py enrich.py
```
