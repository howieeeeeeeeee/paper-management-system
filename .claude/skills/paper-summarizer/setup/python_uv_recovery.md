# Python and uv Recovery

Read this only during onboarding when `uv` is missing and `python3 -m pip install --user uv` / `python -m pip install --user uv` cannot be used.

Goal: get a working Python with pip, install `uv`, then return to `onboard.md` and run `uv sync` from `paperhub_utils/`.

## 1. Diagnose

Run:

```bash
command -v python3
python3 --version
python3 -m pip --version
command -v pyenv
command -v brew
```

If `python3` exists but pip is missing, try:

```bash
python3 -m ensurepip --upgrade
python3 -m pip install --user uv
```

If that works, return to `onboard.md`.

If pip reports a successful `uv` install but `uv --version` still fails, check the user install bin path:

```bash
python3 -m site --user-base
```

The executable is usually under that directory's `bin/`. Ask before editing shell startup files; otherwise tell the user to add that `bin/` directory to `PATH` or use the `uv` executable by absolute path for onboarding.

## 2. Prefer pyenv

If `pyenv` exists, install the newest available Python `3.14.x` and set it locally for the paper-library root:

```bash
pyenv install -l | rg '^\s*3\.14\.'
pyenv install 3.14.x
cd "{paper_library_root}"
pyenv local 3.14.x
python -m pip install --upgrade pip
python -m pip install --user uv
uv --version
```

Replace `3.14.x` with the newest listed patch release, for example `3.14.1`.

## 3. If pyenv is missing

Use `AskUserQuestion` before installing anything:

- `Install pyenv with Homebrew` - recommended for better Python version management.
- `Install Python with Homebrew` - more straightforward, less flexible.

If the user chooses pyenv:

```bash
brew install pyenv
pyenv install -l | rg '^\s*3\.14\.'
pyenv install 3.14.x
cd "{paper_library_root}"
pyenv local 3.14.x
python -m pip install --upgrade pip
python -m pip install --user uv
uv --version
```

If the user chooses Homebrew Python:

```bash
brew install python@3.14
python3.14 -m pip install --upgrade pip
python3.14 -m pip install --user uv
uv --version
```

If `brew` is also missing, ask the user to install Homebrew or Python manually. Do not silently choose a system-wide installer.

## 4. Finish

When `uv --version` succeeds, return to `onboard.md` and continue:

```bash
cd "{paperhub_utils_dir}"
uv sync
```
