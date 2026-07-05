# PaperHub

PaperHub is an Obsidian-first paper library built around one rule: one paper, one folder, one metadata file.

```text
organized/
`-- melitz2003trade/
    |-- melitz_2003.pdf
    |-- melitz2003trade.md
    `-- ai_summary.md
```

The folder keeps the PDF, metadata, reading status, tags, and optional AI summary together. This makes the library easy to browse, link, and manage in Obsidian, especially through Obsidian Bases.

AI integration handles the organizing work. Drop PDFs into `to_be_organized/`, run the `paper-summarizer` skill in your coding agent, and PaperHub creates the folder, metadata note, canonical tags, and optional `ai_summary.md` automatically.

New to the workflow? Start with [Obsidian 101](quick_start/obsidian_101.md), then open [SamplePaperBoard.base](SamplePaperBoard.base) in Obsidian to browse the library.

## Onboarding

Use the best model available for this one-time setup. Routine paper runs can use a faster or cheaper model.

1. Check prerequisites:
  - Git is installed and configured.
  - You have a coding agent such as Claude Code, Codex, or Cursor.
  - You have an Obsidian vault where this paper library should live.
2. Open Terminal and move to the parent folder where `PaperHub` should be created. This should be your Obsidian vault, or a folder inside your Obsidian vault:
  ```bash
   cd "/path/to/your/ObsidianVault"
  ```
3. Clone the template into that folder:
  ```bash
   git clone --depth 1 https://github.com/howieeeeeeeeee/paper-management-system.git PaperHub
   cd PaperHub
   rm -rf .git
   git init -b main
   git add -A
   git commit -m "chore(setup): initialize PaperHub"
  ```
4. Go to your Obsidian, open [onboarding_questionnaire.md](onboarding_questionnaire.md), fill the sections that matter to you, and change the frontmatter status to:
  ```yaml
   status: ready_for_agent
  ```
5. Open your coding agent from the `PaperHub` folder and paste:
  ```text
   Use the paper-summarizer skill to onboard this project from scratch.
  ```

## First Run

After onboarding, add one or a few PDFs to `to_be_organized/`, then ask your coding agent:

```text
paper-summarizer: metadata-only batch for everything in to_be_organized/.
```


## Quick launch

Save a terminal snippet (e.g. Alfred *Terminal Command* with keyword, or Raycast). For example:

```bash
cd "/path/to/your/PaperHub" && claude --model claude-haiku-4-5-20251001
```

Optional: append `--dangerously-skip-permissions` if permission prompts break long skill runs—only when you fully trust that session.

## Use cases

Run all commands from the repository root. Reference paths are relative pointers only: use `to_be_organized/` for new PDFs and `organized/<folder>/` for existing paper folders.

| Scenario                  | Reference          | Mode            | Prompt                                                                      |
| ------------------------- | ------------------ | --------------- | --------------------------------------------------------------------------- |
| Many papers, ingest first | `to_be_organized/` | `metadata-only` | `paper-summarizer: metadata-only batch for everything in to_be_organized/.` |
| Metadata plus summaries   | `to_be_organized/` | `full`          | `paper-summarizer: organize new PDFs in to_be_organized/ - full summary.`   |

For enrich runs, extra instructions, citation hints, and model-specific examples, see [quick_start/use-cases.md](quick_start/use-cases.md).

## Finding a half-remembered paper

If you know a paper is somewhere in the library but can't recall which one, describe what you remember:

```text
paper-finder: which paper was it where dictators avoided knowing the recipient's payoff?
```

The `paper-finder` skill expands your description into search terms, ranks every organized paper with a fast local script (`paperhub_utils/paper_search.py`, no API calls), and shows the top candidates with their metadata labels, status, interest, and summary snippets. If none fit, it broadens the terms and searches again.

You can also steer it *away* from a neighboring literature that keeps surfacing:

```text
paper-finder: the correlation-neglect paper, but not the survey-based ones
```

Phrases like "but not the survey ones" become **exclude keywords** that deduct score (a soft penalty, not a hard filter), pushing unwanted matches down or off the list while genuinely strong matches still surface.

## Output Layout

```text
organized/
`-- melitz2003trade/
    |-- melitz_2003.pdf
    |-- melitz2003trade.md
    `-- ai_summary.md
```

Each paper folder contains the original PDF and a metadata note. Full and enrich runs also create or refresh `ai_summary.md`.

## Tag system

Four tag types are stored in each paper's YAML `tags:`: `field`, `methodology`, `topic`, and `meta`.

Two ways to shape tags:

- `onboarding_questionnaire.md`: the first-run starter taxonomy. Edit the "Starter Tag Taxonomy" section before onboarding; the agent uses those lists directly when it creates the initial tag registry.
- `tags/tag_initialization.md`: optional later bulk additions after onboarding. Ask the agent to create or process this file, then edit one tag per line under each `## type` heading and set the frontmatter to `status: ready`.
- Edit a paper metadata file directly in Obsidian. Open any organized paper's `{paperlabel}.md` file and add a tag to its YAML `tags:` list. New tags are incorporated into the canonical registry on the next tag-update flow.

While generating the metadata for a paper PDF, the model is nudged to reuse canonical tag strings during summarization.

`tags/tags_summary.md` is the human-facing table. For now, you can change a tag's `type` there to reclassify it. The skill keeps `tags/_internal/registry.json` in sync when tag flows run.

## Obsidian tips

- [Obsidian 101](quick_start/obsidian_101.md) explains the core workflow: link papers with their metadata note label, edit properties like `status`, `interest`, and `tags`, and use Bases as the dashboard.
- To customize AI-generated metadata fields, edit [paperhub_utils/prompt/shared/metadata_template.txt](paperhub_utils/prompt/shared/metadata_template.txt). For summary shape and style, see [paperhub_utils/README.md](paperhub_utils/README.md).

## Creating your own Obsidian Base

[SamplePaperBoard.base](SamplePaperBoard.base) is a starter dashboard with common views (reading queue, by topic, by interest level). Feel free to duplicate it and modify the filters and layouts to match your workflow. Each base file is a JSON snapshot of your Obsidian Base configuration — you can create as many as you like for different perspectives on your library.

## Important Files

- [quick_start/obsidian_101.md](quick_start/obsidian_101.md): short guide to Obsidian links, paper metadata, and using Bases.
- [quick_start/use-cases.md](quick_start/use-cases.md): complete prompt cookbook for common paper workflows.
- [SamplePaperBoard.base](SamplePaperBoard.base): starter Obsidian Base dashboard — duplicate and customize for your own views.
- [onboarding_questionnaire.md](onboarding_questionnaire.md): user-facing onboarding intake, deleted after successful onboarding.
- [paperhub_utils/.env.example](paperhub_utils/.env.example): template for local API keys; copy it to `paperhub_utils/.env`.
- [paperhub_utils/misc/config.json](paperhub_utils/misc/config.json): runtime preferences.
- [paperhub_utils/config.py](paperhub_utils/config.py): script constants and research interests.
