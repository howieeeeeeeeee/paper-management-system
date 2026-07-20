---
status: not_started
schema_version: 1
---

# PaperHub Onboarding Questionnaire

Fill this file before asking your coding agent to run onboarding. The goal is to give the agent enough context to configure PaperHub for your vault, your preferred AI engine, and your paper organization style.

When you are ready, change `status` in the frontmatter to `ready_for_agent`.

Do not paste API keys into this file or into chat. Store secrets only in `paperhub_utils/config/.env`. The setup instructions below show how to put the key in that file from Terminal.

## 1. Readiness

This section helps the agent confirm that it is working in the correct folder and will not accidentally organize papers somewhere else.

- [ ] I cloned or copied this repository into the Obsidian vault, or into the folder where I want my paper library to live.
- [ ] I opened Terminal at the PaperHub folder.
- [ ] I understand this paper-library folder should **not** keep a `.git` inside it — especially under iCloud, where a live `.git` gets corrupted. If I copied a template that came with a `.git`, I will let onboarding remove it. Version history is kept in a **separate git backup folder** (configured in Section 3, "Git behavior") that lives **outside** iCloud.
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

Nothing to fill in here. The agent finds your Obsidian vault automatically during onboarding: it walks up from the PaperHub folder through its parent folders until it finds the one containing `.obsidian/`, and works out both the vault path and where PaperHub sits inside the vault. It will only ask you for a path if PaperHub is not inside an Obsidian vault — for example, if you have not yet opened the surrounding folder as a vault in Obsidian, so no `.obsidian/` folder exists.

**Strongly recommended: keep your Obsidian vault inside iCloud (or another cloud sync).** That way your paper library syncs across your devices automatically. If you do, also set the vault folder to **"Keep Downloaded"** (in Finder, right-click the vault folder → **Keep Downloaded**) so every file is stored locally as a real file, not an `.icloud` placeholder. The git backup step copies real files; if the vault is not fully downloaded, placeholders would be backed up instead of your actual notes.

**Just as important: the git backup folder (Section 3) must NOT live inside iCloud/Dropbox/any cloud folder.** A live `.git` inside a cloud-synced folder gets corrupted. Put the backup folder somewhere plain and local, such as `~/Personal/PaperHub` or `~/git/PaperHub`.

## 3. Engine And Runtime

PaperHub organizes PDFs and public paper links with different AI engines. Pick your preferred one(s); if it is not available, the agent asks before changing
engines. Link runs prepare public metadata as local text before calling an engine, so external engines do not browse the link themselves.

**Preferred AI engine** (pick one):

- [ ] OpenRouter — simplest for the full workflow; just needs an API key (recommended)
- [ ] Agy CLI — direct Google/Antigravity CLI (recommended if subscribing to Google AI Pro, only if already installed)
- [ ] Codex CLI — OpenAI `codex exec` (only if already installed)
- [ ] Current coding agent — allow full summaries (no separate service; higher token use)
- [ ] Current coding agent — metadata-only first, ask before full summaries
- [ ] Not sure — let the agent infer a working option

**Set up only the engine you picked:**

_OpenRouter._ Create a key at [openrouter.ai](https://openrouter.ai/), then in Terminal at the PaperHub folder copy the example env file and paste your key into it (never paste the key here or in chat):

```bash
cp paperhub_utils/config/.env.example paperhub_utils/config/.env
nano paperhub_utils/config/.env   # replace YOUR_OPENROUTER_API_KEY, then Ctrl+O, Enter, Ctrl+X
```

_Agy CLI._ Confirm it actually runs: type `agy` in your Terminal and check it launches and is signed in.

- [ ] I ran `agy` in Terminal and it works.

_Codex CLI._ Confirm it actually runs: type `codex` in your Terminal and check it launches and is signed in.

- [ ] I ran `codex` in Terminal and it works.
- [ ] Use local yolo/full-access mode (smoother from this trusted folder). Leave unchecked to keep it sandboxed/read-only.

Codex model + reasoning default:

- [ ] `gpt-5.6-sol` + `high` (recommended)
- [ ] `gpt-5.6-terra` + `high` 
- [ ] `gpt-5.5` + `high`


Git behavior:

Git lets the agent save clean checkpoints (versions) after organizing papers, editing configuration, or updating generated files, so you can look back or roll back. If you are new to Git, it is fine to choose "Do not use Git versioning" for now.

**How versioning works here:** because your library likely lives in iCloud, and a live `.git` inside an iCloud folder gets corrupted, PaperHub does **not** keep a `.git` in this folder. Instead it keeps a **separate git backup folder outside iCloud**. After each batch the agent copies (mirrors) your library into that folder and commits there. Three settings below control this.

**1. Use git versioning?**

- [ ] Yes — version my library (mirror + commit into a separate git backup folder).
- [ ] No — do not use git versioning for this library.

**2. Git backup folder — absolute path.**

Paste the absolute path of a **plain local folder outside iCloud/Dropbox/any cloud folder** where the git history should live (e.g. `/Users/you/Personal/PaperHub` or `/Users/you/git/PaperHub`). It can be empty or not exist yet — the agent will create and initialize it. If you leave this blank while choosing "Yes" above, the agent will ask for it during onboarding.

```text

```

**3. Sync to a remote (GitHub/GitLab)?**

If yes, each versioning run will `git pull` before and `git push` after, keeping a remote copy in sync.

- [ ] Yes — pull before and push after each versioning run. (After onboarding I will add the remote, e.g. `git remote add origin <url>`, and confirm I can push. The agent can help wire this up.)
- [ ] No — keep versions local in the backup folder only.

Metadata-only page limit:

This controls how many pages the agent reads during the metadata-only mode. A smaller number is cheaper and faster. A larger number gives the agent more context for titles, abstracts, introductions, and tags.

- [ ] 2 pages, fast first-run triage
- [ ] 4 pages, more context for tagging, more token usage
- [ ] Custom:

```text

```

Link inputs do not use this page limit unless a public PDF is downloaded for a full-summary request. Public link metadata is limited to citation fields and the
abstract. Missing facts remain explicit placeholders.

## 4. Research Interests

The agent writes this into `paperhub_utils/paperhub/config.py` as `MY_RESEARCH_INTERESTS`. The AI uses it to connect each paper to your work when writing summaries and relevance notes.

You can leave this blank if you are not sure yet. A rough description is enough, such as "international trade, firm dynamics, and development economics".

Research interests:

```text

```

## 5. Starter Tag Taxonomy

PaperHub comes with the default starter taxonomy below from `paperhub_utils/config/default_tags.yaml`. These tags give the agent a conservative vocabulary before it has seen your own paper library.

Please review and modify these lists before onboarding. Delete tags you do not want, add tags you know you will use, and leave any section blank if you do not have a preference yet. Lowercase with underscores is easiest to maintain, such as `international_trade`, `labor`, `field_experiment`.

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


## 6. Paper Label Format

Paper labels become folder names, file names, and Obsidian link targets. For example, a paper by Melitz from 2003 might become `melitz2003heterogeneousfirms`. Compact lowercase labels are recommended for maximum compatibility, but any option below is fine if it matches your existing system.

Choose one:

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

- [ ] Ask the agent to configure root `.base` files for me using the auto-detected Obsidian vault path.
- [ ] I am not using Obsidian Bases yet.

Notes for Bases filters or views, if any:

```text

```

## 8. Anything Else The Agent Should Know

Use this space for preferences that do not fit above. Examples: where PDFs are currently stored, papers you want organized first, naming preferences, or anything you do not want the agent to change.

```text

```

## Agent Handoff

After filling the questionnaire, paste this into your coding agent, make sure you have `cd` to the `PaperHub` folder:

```text
Use the /paper-organizer skill to onboard this project from scratch.
```
