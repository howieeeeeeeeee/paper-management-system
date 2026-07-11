---
name: paper-downloader
description: Download and cite NEW research papers from the web, then hand off to paper-organizer. Triggers when users want to fetch, download, get, pull, or grab a paper (or several) they do NOT yet have, by title/author, DOI, arXiv ID, or URL; resolve a citation/BibTeX; or process the "papers to find.md" backlog. Searches open-access APIs (arXiv/OpenAlex/Crossref/Unpaywall) and, for paywalled journals, drives the local gstack browser over the user's school VPN for legitimate institutional access. Real published version first, free working-paper version as fallback. Always writes a citation sidecar and offers to organize. NOT for locating papers already in organized/ — that is the paper-finder skill.
---

# Research Paper Downloader

The project's root folder contains a `.claude` directory. Open `.claude/skills/paper-downloader/SKILL.md` (from that root) for the canonical workflow and rules.

Routes the request to one mode (`auto` / `open-access` / `browser` / `citation-only`) and one input type (title / DOI / arXiv / URL / batch), then delegates to the per-doc playbook under `.claude/skills/paper-downloader/`. **Read only the doc(s) you need.** Every mode calls `cd paperhub_utils && uv run python -m scripts.paper_fetcher` and writes a `{stem}.citation.md` sidecar next to the downloaded PDF in `to_be_organized/`, then offers to hand off to `paper-organizer`. Legitimate access only — never circumvent paywalls.

## Local uv environment

The virtual environment is disposable local state. In iCloud-synced vaults, do not try to preserve or share `.venv` across machines. Run commands from `paperhub_utils/`. If a normal `uv` command fails because the environment is stale or broken, first run:

```bash
uv sync
```

If that still fails, rebuild the local environment:

```bash
rm -rf .venv
uv sync
```

`pyproject.toml` and `uv.lock` are the source of truth; `.venv` can always be recreated on each computer.
