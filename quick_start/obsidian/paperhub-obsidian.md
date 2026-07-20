# PaperHub Obsidian Skill

Use `paperhub-obsidian` for general Obsidian authoring that is outside paper
ingestion, paper recall, or vault question answering. The router uses the
open-source [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills)
references with PaperHub-specific safeguards.

| Use case | Example prompt |
|---|---|
| Markdown, properties, wikilinks, embeds, or callouts | `/paperhub-obsidian: turn this note into clean Obsidian Markdown with properties and wikilinks.` |
| Base views, filters, formulas, or summaries | `/paperhub-obsidian: add a Base view for high-interest papers I am digesting.` |
| Canvas literature maps | `/paperhub-obsidian: create a Canvas map connecting these research notes.` |
| Live Obsidian or plugin/theme work | `/paperhub-obsidian: use the Obsidian CLI to inspect errors from this plugin.` |

The Obsidian CLI requires a running app. Defuddle is optional and applies only
to ordinary webpages; paper links always remain with `paper-organizer`.
