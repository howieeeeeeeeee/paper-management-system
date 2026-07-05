---
status: not_started
schema_version: 1
---

# PaperHub Onboarding Questionnaire

Fill this file before asking your coding agent to run onboarding. The goal is to give the agent enough context to configure PaperHub for your vault, your preferred AI engine, and your paper organization style.

When you are ready, change `status` in the frontmatter to `ready_for_agent`.

Do not paste API keys into this file or into chat. Store secrets only in `paperhub_utils/.env`. The setup instructions below show how to put the key in that file from Terminal.

## 1. Readiness

This section helps the agent confirm that it is working in the correct folder and will not accidentally organize papers somewhere else.

- [ ] I cloned or copied this repository into the Obsidian vault, or into the folder where I want my paper library to live.
- [ ] I opened Terminal at the PaperHub folder.
- [ ] I removed the upstream Git history and initialized my own local repository, or I intentionally do not want Git. This keeps my private paper library separate from the original template repository.

_Note: Complete the three steps above after pasting the git command from the README in your chosen folder._

- [ ] I opened my coding agent from the PaperHub folder, so file changes happen inside this project.

If you are not sure whether Terminal is at the PaperHub folder, run this command:

```bash
pwd
```

The output should end with `PaperHub`. If it does not, run this command after replacing the path with your actual PaperHub location:

```bash
cd "/path/to/PaperHub"
```

## 2. Project Paths

The agent uses this path to connect PaperHub to your Obsidian vault and configure Obsidian views correctly. Paste the full absolute path, not a shortened path.

On macOS, one easy way to get the full path is to drag the Obsidian vault folder into Terminal. Terminal will paste the absolute path for you.

If PaperHub is inside your Obsidian vault, paste the path to the vault folder itself, not just the `PaperHub` folder.

Obsidian vault absolute path:

```text

```

## 3. Engine And Runtime

PaperHub can summarize papers with different AI engines. OpenRouter is usually the simplest option for full summaries because it only needs an API key. Antigravity CLI and Codex CLI can work if you already have them installed and authenticated. The current coding agent can also run PaperHub directly, including full-summary mode, but full summaries may use a lot of tokens.

Preferred AI engine:

- [ ] OpenRouter
- [ ] Antigravity CLI
- [ ] Codex CLI
- [ ] Current coding agent, full summaries
- [ ] Current coding agent, metadata-only first
- [ ] Not sure, ask me only if the agent cannot infer a working option

Choose OpenRouter if you want full AI-written paper summaries and you are comfortable creating an API key. Choose Antigravity CLI only if you already know it is installed on your machine (highly recommended, since Gemini 3.1 Pro is excellent at understanding papers and provides a generous amount of quota). Choose Codex CLI if you already use OpenAI Codex locally and want PaperHub to run through `codex exec`. Choose the current coding agent if you want to run onboarding without setting up a separate AI service. If you choose the current coding agent for full summaries, expect substantially higher token usage, especially for long PDFs or batches of many papers.

OpenRouter setup:

- [ ] I want to use OpenRouter for full summaries and enrich runs.
- [ ] I do not want OpenRouter now.

If you want to use OpenRouter:

1. Go to [openrouter.ai](https://openrouter.ai/).
2. Sign in or create an account.
3. Create an API key.
4. Open Terminal at the PaperHub folder.
5. Copy the example environment file:

```bash
cp paperhub_utils/.env.example paperhub_utils/.env
```

6. Open the copied `.env` file and replace `YOUR_OPENROUTER_API_KEY` with your real key:

```bash
nano paperhub_utils/.env
```

In nano, save with `Ctrl+O`, press `Enter`, then exit with `Ctrl+X`. After saving, confirm that the file exists:

```bash
ls paperhub_utils/.env
```

Do not paste the real API key into this questionnaire or into chat.

Antigravity CLI setup:

- [ ] I already installed and authenticated Antigravity CLI on this machine.
- [ ] I do not know what Antigravity CLI is, so do not assume it is available.

Codex CLI setup:

- [ ] I already installed and authenticated Codex CLI on this machine.
- [ ] I want Codex CLI to use local yolo/full-access mode for smoother PaperHub runs from this trusted folder.
- [ ] Keep Codex CLI sandboxed/read-only instead of yolo mode.
- [ ] I do not know what Codex CLI is, so do not assume it is available.

Codex CLI model and thinking default:

- [ ] `gpt-5.5` + `high` reasoning, recommended default
- [ ] `gpt-5.5` + `medium` reasoning
- [ ] `gpt-5.5` + `xhigh` reasoning
- [ ] Custom allowed pair:

```text

```

Current coding agent setup:

- [ ] Use the current coding agent for full summaries. I understand this may use a lot of tokens.
- [ ] Use the current coding agent for metadata-only first, then ask me before full summaries.
- [ ] Stop and ask me before using the current coding agent for full-summary mode.

Git behavior:

Git lets the agent save clean checkpoints after organizing papers, editing configuration, or updating generated files. If you are new to Git, it is fine to choose "Do not use Git commits" for now.

- [ ] Use Git commits for organized papers, tag updates, and setup changes.
- [ ] Do not use Git commits for this library.

Metadata-only page limit:

This controls how many pages the agent reads during the metadata-only mode. A smaller number is cheaper and faster. A larger number gives the agent more context for titles, abstracts, introductions, and tags.

- [ ] 2 pages, fast first-run triage
- [ ] 4 pages, more context for tagging, more token usage
- [ ] Custom:

```text

```

## 4. Research Interests

The agent writes this into `paperhub_utils/config.py` as `MY_RESEARCH_INTERESTS`. The AI uses it to connect each paper to your work when writing summaries and relevance notes.

You can leave this blank if you are not sure yet. A rough description is enough, such as "international trade, firm dynamics, and development economics".

Research interests:

```text

```

## 5. Starter Tag Taxonomy

PaperHub comes with the default starter taxonomy below from `paperhub_utils/seeds/default_tags.yaml`. These tags give the agent a conservative economics-PhD vocabulary before it has seen your own paper library.

Please review and modify these lists before onboarding. Delete tags you do not want, add tags you know you will use, and leave any section blank if you do not have a preference yet. Lowercase with underscores is easiest to maintain, such as `international_trade`, `labor`, `field_experiment`, or `reading_list_macro`.

Field tags:

```text
applied_micro
econometrics
industrial_organization
labor
macroeconomics
market_design
theory
international_trade
```

Methodology tags:

```text
diff_in_diff
simulated_method_of_moments
experimental
field_experiment
lab_experiment
regression_discontinuity
structural_estimation
```

Topic tags:

```text
bargaining
human_capital
inequality
information_design
innovation
mechanism_design
search_frictions
decision_making
```

Meta tags, such as courses, reading lists, seminars, projects, or workflow labels:

```text

```

## 6. Paper Label Format

Paper labels become folder names, file names, and Obsidian link targets. For example, a paper by Melitz from 2003 might become `melitz2003heterogeneous`. Compact lowercase labels are recommended for maximum compatibility, but any option below is fine if it matches your existing system.

Choose one:

- [ ] Recommended compact author-year-topic: `melitz2003heterogeneous`, `cardkrueger1994minimum`, `autoretal2020trade`
- [ ] Compact author-year-title keywords: `melitz2003heterogeneousfirms`, `cardkrueger1994minimumwage`, `autoretal2020importcompetition`
- [ ] First-author plus etal for multi-author papers: `melitz2003heterogeneous`, `cardetal1994minimum`, `autoretal2020trade`
- [ ] Author-year only, shortest labels: `melitz2003`, `cardkrueger1994`, `autoretal2020`
- [ ] Readable snake_case: `melitz_2003_heterogeneous`, `card_krueger_1994_minimum`, `autor_etal_2020_trade`
- [ ] Zotero-style capitalized: `Melitz2003Heterogeneous`, `CardKrueger1994Minimum`, `AutorEtAl2020Trade`
- [ ] Keep the current `paperhub_utils/prompt/shared/paper_label.txt`
- [ ] Custom, described below

Custom paper label rules, if any. Avoid spaces and characters that are awkward in filenames. Include examples for one-author, two-author, and three-or-more-author papers if possible.

```text

```

## 7. Obsidian Bases

Obsidian Bases are optional database-style views inside Obsidian. If you use them, the agent can configure root `.base` files so you can browse papers by tags, fields, status, or other metadata. If you do not know what Bases are, choose "I am not using Obsidian Bases yet."

- [ ] Ask the agent to configure root `.base` files for me using the Obsidian vault path above.
- [ ] I am not using Obsidian Bases yet.

Notes for Bases filters or views, if any:

```text

```

## 8. Anything Else The Agent Should Know

Use this space for preferences that do not fit above. Examples: where PDFs are currently stored, whether you use Zotero, papers you want organized first, naming preferences, or anything you do not want the agent to change.

```text

```

## Agent Handoff

After filling the questionnaire, paste this into your coding agent, make sure you have `cd` to the `PaperHub` folder:

```text
Use the paper-summarizer skill to onboard this project from scratch.
```
