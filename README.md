# PaperHub

PaperHub turns PDFs into an Obsidian-ready paper library. Drop PDFs into `to_be_organized/`, run the `paper-summarizer` skill in your coding agent, and get organized folders with metadata, optional `ai_summary.md`, canonical tags, and Bases-ready notes.

New to the workflow? Start with [Obsidian 101](quick_start/obsidian_101.md), then open [Papers.base](Papers.base) in Obsidian to browse the library.

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

Save a terminal snippet (e.g. Alfred *Terminal Command* with keyword `pp`, or Raycast). Command:

```bash
cd "/path/to/your/ObsidianVault/PaperHub" && claude --model claude-haiku-4-5-20251001
```

Optional: append `--dangerously-skip-permissions` if permission prompts break long skill runs—only when you fully trust that session.

## Use cases

Run all commands from the repository root. Reference paths are relative pointers only: use `to_be_organized/` for new PDFs and `organized/<folder>/` for existing paper folders.


| Scenario                  | Reference          | Mode            | Prompt                                                                      |
| ------------------------- | ------------------ | --------------- | --------------------------------------------------------------------------- |
| Many papers, ingest first | `to_be_organized/` | `metadata-only` | `paper-summarizer: metadata-only batch for everything in to_be_organized/.` |
| Metadata plus summaries   | `to_be_organized/` | `full`          | `paper-summarizer: organize new PDFs in to_be_organized/ - full summary.`   |

For enrich runs, extra instructions, citation hints, and model-specific examples, see [quick_start/use-cases.md](quick_start/use-cases.md).

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

- `tags/tag_initialization.md`: the bulk seed path for tags you want available upfront, such as niche fields and topics. Edit one tag per line under each `## type` heading, set the frontmatter to `status: ready`, and the agent registers them on the next onboarding or tag pass.
- Edit a paper metadata file directly in Obsidian. Open any organized paper's `{paperlabel}.md` file and add a tag to its YAML `tags:` list. New tags are incorporated into the canonical registry on the next tag-update flow.

While generating the metadata for a paper PDF, the model is nudged to reuse canonical tag strings during summarization.

`tags/tags_summary.md` is the human-facing table. For now, you can change a tag's `type` there to reclassify it. The skill keeps `tags/_internal/registry.json` in sync when tag flows run.

## Obsidian tips

- [Obsidian 101](quick_start/obsidian_101.md) explains the core workflow: link papers with their metadata note label, edit properties like `status`, `interest`, and `tags`, and use Bases as the dashboard.
- To customize AI-generated metadata fields, edit [paperhub_utils/prompt/shared/metadata_template.txt](paperhub_utils/prompt/shared/metadata_template.txt). For summary shape and style, see [paperhub_utils/README.md](paperhub_utils/README.md).

## Important Files

- [quick_start/obsidian_101.md](quick_start/obsidian_101.md): short guide to Obsidian links, paper metadata, and `Papers.base`.
- [quick_start/use-cases.md](quick_start/use-cases.md): complete prompt cookbook for common paper workflows.
- [Papers.base](Papers.base): main Obsidian Bases dashboard for reading queues and topic views.
- [onboarding_questionnaire.md](onboarding_questionnaire.md): user-facing onboarding intake, deleted after successful onboarding.
- [paperhub_utils/.env.example](paperhub_utils/.env.example): template for local API keys; copy it to `paperhub_utils/.env`.
- [paperhub_utils/misc/config.json](paperhub_utils/misc/config.json): runtime preferences.
- [paperhub_utils/config.py](paperhub_utils/config.py): script constants and research interests.
