---
status: not_started
---

# PaperHub Onboarding Questionnaire

Complete the required choices below, then ask your coding agent to run PaperHub onboarding. Most questions only require checking one or more options. Technical setup instructions are collected under [[#9. Advanced Settings]] so you can focus on your PaperHub preferences first.

When you are ready, change `status` in the frontmatter from `not_started` to `ready_for_agent`. If you are unsure about an answer, leave it blank; the agent will ask only when the missing choice blocks setup.

Never paste API keys, access tokens, or other secrets into this file or into chat. Store them only in `paperhub_utils/config/.env`.

## Table of Contents

- [[#1. Before You Start]]
- [[#2. Project Paths]]
- [[#3. Engine, Model, and Git Behavior]]
- [[#4. Research Interests]]
- [[#5. Starter Tag Taxonomy]]
- [[#6. Paper Label Format]]
- [[#7. Obsidian Bases]]
- [[#8. Anything Else the Agent Should Know]]
- [[#9. Advanced Settings]]
- [[#Agent Handoff]]

## 1. Before You Start

Confirm both items:

- [ ] PaperHub is inside the Obsidian vault, or folder, where I want my paper library to live.
- [ ] I opened my coding agent from the PaperHub folder so it can see and configure this project.

The agent will verify the folder and create `to_be_organized/`, `organized/`, and `tags/` if needed.

If your Obsidian vault is in iCloud or another cloud service, keep the vault fully downloaded. On macOS, right-click the vault folder in Finder and choose **Keep Downloaded**. PaperHub's separate Git backup folder must remain outside every cloud-synced folder.

## 2. Project Paths

Nothing to fill in here. The agent will:

- Find the PaperHub project root from the current working folder.
- Walk upward until it finds the Obsidian vault's `.obsidian/` folder.
- Derive PaperHub's vault-relative path for Obsidian Bases.

The agent will ask for the Obsidian vault path only if automatic discovery fails, such as when the surrounding folder has never been opened as an Obsidian vault.

## 3. Engine, Model, and Git Behavior

Review the external AI services, select one model option, and complete the Git settings. You may select more than one engine.

### Preferred AI engines

Choose any external AI services you want to set up. You may select more than one, and it is fine to leave them all unchecked for now.

- [ ] OpenRouter — API-based access to supported models. Requires an API key; see [[#OpenRouter API key]].
- [ ] Agy CLI — use an existing signed-in Google/Antigravity CLI installation.
- [ ] Codex CLI — use an existing signed-in OpenAI Codex CLI installation.

The agent will check each selected option during onboarding. You can ask the agent to help set up another engine later.

### Model choice

PaperHub's onboarding defaults are:

- **Agy CLI:** `Gemini 3.1 Pro (High)`.
- **Codex CLI:** `gpt-5.6-sol` with `high` reasoning.

Choose one:

- [ ] Use the onboarding defaults for my selected external engines (recommended).
- [ ] I want a different Codex CLI model or reasoning level; I selected it under [[#Codex CLI readiness, permissions, and model override]].

The agent will verify that each selected engine supports the resolved model and reasoning level.

### Git behavior

PaperHub can keep version history by mirroring the library into a separate Git repository outside the Obsidian vault. It never initializes Git inside an iCloud-synced vault.

**1. Use Git versioning?** Choose one:

- [ ] Yes — mirror and commit my library into a separate Git backup folder.
- [ ] No — do not use Git versioning for this library.

**2. Git backup folder.** Required only when choosing **Yes** above. Enter an absolute path outside iCloud, Dropbox, Google Drive, OneDrive, or any other cloud folder. The folder can be empty or not exist yet.

```text

```

Examples: `/Users/you/Personal/PaperHub` or `/Users/you/git/PaperHub`

**3. Sync to a remote Git repository?** Required only when using Git versioning. A local backup is enough for normal PaperHub version history, so **No is recommended for most users**.

- [ ] No — keep version history only in the local backup folder (recommended and sufficient for most users).
- [ ] Yes — pull before and push after each versioning run.

If you selected **Yes**, complete one of these:

- [ ] Use the remote URL entered below.
- [ ] The Git backup folder already has a working `origin` remote; ask the agent to verify it.

Remote repository URL, if needed:

```text

```

Provide only the repository URL, such as an HTTPS or SSH Git URL. Never put a password, personal access token, or other secret in this questionnaire.

## 4. Research Interests

This is optional but recommended. PaperHub uses it to explain how each paper connects to your work. A rough description is enough, such as "international trade, firm dynamics, and development economics."

```text

```

Leave this blank if you do not want personalized relevance notes yet.

## 5. Starter Tag Taxonomy

Reviewing the starter taxonomy is a required onboarding step. Choose one:

- [ ] Keep the starter taxonomy exactly as shown below.
- [ ] I reviewed and edited the lists below for my research.

Use lowercase tags with underscores, such as `international_trade` or `field_experiment`. You can change the taxonomy later as your library grows.

### Field tags

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

### Methodology tags

```text
diff_in_diff
simulated_method_of_moments
experimental
field_experiment
lab_experiment
regression_discontinuity
structural_estimation
```

### Topic tags

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

Paper labels become folder names, metadata-note names, and Obsidian link targets. Choose one required format:

- [ ] Compact author-year-title keywords: `melitz2003heterogeneousfirms`, `cardkrueger1994minimumwage`, `autoretal2020importcompetition`.
- [ ] First-author plus `etal` for multi-author papers: `melitz2003heterogeneous`, `cardetal1994minimum`, `autoretal2020trade`.
- [ ] Author-year only: `melitz2003`, `cardkrueger1994`, `autoretal2020`.
- [ ] Readable snake case: `melitz_2003_heterogeneous`, `card_krueger_1994_minimum`, `autor_etal_2020_trade`.
- [ ] Zotero-style capitalized: `Melitz2003Heterogeneous`, `CardKrueger1994Minimum`, `AutorEtAl2020Trade`.
- [ ] Keep the current `paperhub_utils/prompts/shared/paper_label.txt` rules.
- [ ] Custom, described below.

For a custom format, describe the pattern and include examples for papers with one author, two authors, and three or more authors.

```text

```

## 7. Obsidian Bases

PaperHub already includes `SamplePaperBoard.base`, which provides database-style views of your paper notes and properties. During onboarding, the agent will find your Obsidian vault and update the Base's folder paths so it can display the papers in your library. You do not need to configure the path or choose an option here.

After setup, open `SamplePaperBoard.base` in your Obsidian vault to see the configured views. If Obsidian asks, enable the **Bases** core plugin.

Optional notes about the Base, filters, or views:

```text

```

## 8. Anything Else the Agent Should Know

Add any preferences that do not fit above, such as where existing PDFs are stored, which papers to organize first, or anything the agent should not change.

```text

```

## 9. Advanced Settings

Complete only the subsections relevant to your selected engine or desired customization. The core Git, model, and tag decisions plus automatic Bases setup remain in the sections above.

### OpenRouter API key

Use this section if you want to use OpenRouter. The agent will verify the key during setup.

1. Create an API key at [OpenRouter](https://openrouter.ai/).
2. Copy `paperhub_utils/config/.env.example` to `paperhub_utils/config/.env`.
3. Open `.env` in a text editor and replace the placeholder with:

   ```text
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

You may also create the file from Terminal while standing in the PaperHub folder:

```bash
cp paperhub_utils/config/.env.example paperhub_utils/config/.env
nano paperhub_utils/config/.env
```

Never put the real key in this questionnaire or paste it into chat. The agent will verify that a key is available without printing it.

### Agy CLI readiness

Use this section if you want to use Agy CLI:

- [ ] I ran `agy` in Terminal and confirmed that it launches and is signed in.

### Codex CLI readiness, permissions, and model override

Use this section if you want to use Codex CLI:

- [ ] I ran `codex` in Terminal and confirmed that it launches and is signed in.
- [ ] Use local yolo/full-access mode from this trusted PaperHub folder. Leave unchecked to keep Codex CLI sandboxed/read-only.

The onboarding default is `gpt-5.6-sol` with `high` reasoning. To override it, choose one model and one reasoning level below:

**Model — choose one:**

- [ ] `gpt-5.6-sol`.
- [ ] `gpt-5.6-terra`.
- [ ] `gpt-5.5`.

**Reasoning level — choose one:**

- [ ] `low`.
- [ ] `medium`.
- [ ] `high`.
- [ ] `xhigh`.

### Metadata-only page limit

Choose how many PDF pages PaperHub should inspect in metadata-only mode. This does not affect ordinary public-link metadata runs.

- [ ] 2 pages — faster first-run triage.
- [ ] 4 pages — more introduction context and higher token use.
- [ ] Custom number:

```text

```

If left blank, the agent will use the configured default.

## Agent Handoff

After completing the questionnaire, change the frontmatter `status` to `ready_for_agent`, open your coding agent from the PaperHub folder, and send:

```text
Use the paper-organizer skill to onboard this project using onboarding_questionnaire.md.
```
