# PaperHub

PaperHub turns PDFs into an Obsidian-ready paper library. Drop PDFs into `to_be_organized/`, run the `paper-summarizer` skill in your coding agent, and get organized folders with metadata, optional `ai_summary.md`, canonical tags, and Bases-ready notes.

## Onboarding

Use the best model available for this one-time setup. Routine paper runs can use a faster or cheaper model.

1. Check prerequisites:
  - Git is installed and configured.
  - You have a coding agent such as Claude Code, Codex, or Cursor.
  - You have an Obsidian vault where this paper library should live.
2. Open the terminal, cd to the chosen parent folder, and clone the template into your vault:
  ```bash
   git clone --depth 1 https://github.com/howieeeeeeeeee/paper-management-system.git PaperHub
   cd PaperHub
   rm -rf .git
   git init -b main
   git add -A
   git commit -m "chore(setup): initialize PaperHub"
  ```
3. Go to your Obsidian, open `[onboarding_questionnaire.md](onboarding_questionnaire.md)`, fill the sections that matter to you, and change the frontmatter status to:
  ```yaml
   status: ready_for_agent
  ```
4. Open your coding agent from the `PaperHub` folder and paste:
  ```text
   Use the paper-summarizer skill to onboard this project from scratch.
  ```

## First Run

After onboarding, add one or a few PDFs to `to_be_organized/`, then ask your coding agent:

```text
paper-summarizer: metadata-only batch for everything in to_be_organized/.
```

## Use cases

Run all commands from the repository root. Reference paths are relative pointers only: use `to_be_organized/` for new PDFs and `organized/<folder>/` for existing paper folders.


| Scenario                               | Reference             | Mode            | Prompt                                                                      |
| -------------------------------------- | --------------------- | --------------- | --------------------------------------------------------------------------- |
| New paper(s)                           | `to_be_organized/`    | `full`          | `paper-summarizer: organize new PDFs in to_be_organized/ - full summary.`   |
| Many papers, ingest first              | `to_be_organized/`    | `metadata-only` | `paper-summarizer: metadata-only batch for everything in to_be_organized/.` |
| Polish / refresh `ai_summary.md`       | `organized/<folder>/` | `enrich`        | `paper-summarizer: enrich folder <folder> - refresh summary.`               |
| Summary with chosen model (OpenRouter) | `organized/<folder>/` | `enrich`        | `paper-summarizer: enrich <folder> via OpenRouter with model <model-name>.` |


Optional extra context: add free text in the same prompt when it helps the model use the right citation, emphasis, or summary shape.

- `... Extra: published in American Economic Review, 2024; PDF is still a working paper.`
- `... Extra: please spell out all model setup details (timing, equilibrium notion, parameter constraints) in ai_summary.md.`
- `... Extra: compare to Melitz (2003); our goal is exam notes on heterogeneity vs selection.`

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

Two ways to add tags:

- `tags/tag_initialization.md`: the bulk seed path for tags you want available upfront, such as courses, seminars, reading lists, projects, niche fields, and workflow labels. Edit one tag per line under each `## type` heading, set the frontmatter to `status: ready`, and the agent registers them on the next onboarding or tag pass.
- Edit a paper metadata file directly in Obsidian. Open any organized paper's `{paperlabel}.md` file and add a tag to its YAML `tags:` list. New tags are incorporated into the canonical registry on the next tag-update flow.

On first onboarding, the skill seeds the registry from `paperhub_utils/seeds/default_tags.yaml`. The model is nudged to reuse canonical tag strings during summarization; prompt-time limits live in `paperhub_utils/misc/config.json` under `tag_prompt`.

`tags/tags_summary.md` is the human-facing table. For now, you can change a tag's `type` there to reclassify it. The skill keeps `tags/_internal/registry.json` in sync when tag flows run.

## Obsidian tips

- Sync: keep the vault inside an iCloud Drive-synced folder, or another sync service you trust, so the same library is available on desktop and mobile. Avoid editing the same note on two devices before sync finishes, or you risk conflict copies.
- Overview: in Bases, combine filters such as status, tags, and interest with table or list views so one board can show active reading, methods shelves, or seminar queues. Start from `SamplePaperBoard.base` and branch views from there.

## Important Files

- `[onboarding_questionnaire.md](onboarding_questionnaire.md)`: user-facing onboarding intake, deleted after successful onboarding.
- `[paperhub_utils/misc/onboarding.json](paperhub_utils/misc/onboarding.json)`: agent progress ledger.
- `[paperhub_utils/misc/config.json](paperhub_utils/misc/config.json)`: runtime preferences.
- `[paperhub_utils/config.py](paperhub_utils/config.py)`: script constants and research interests.
- `[.claude/skills/paper-summarizer/onboard.md](.claude/skills/paper-summarizer/onboard.md)`: canonical agent onboarding workflow.

