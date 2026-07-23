# Handoff instruction: change my paper-label format

Copy the message below into a new agent conversation. Replace any bracketed
details you already know; leave the rest for the agent to discover with
read-only inspection. Concrete examples are the most reliable way to describe a
label format.

```text
Use the paper-organizer `update-label-format` toolkit to help me redesign my
PaperHub paper labels, let me choose the final convention, migrate my existing
library safely, and make the chosen convention the default for future papers.

My current labels look like:
- One author: [example, or discover it]
- Two authors: [example, or discover it]
- Three or more authors: [example, or discover it]

My initial preference, if any:
- One author: [desired example or “show me options”]
- Two authors: [desired example or “show me options”]
- Three or more authors: [desired example or “show me options”]

Preferences or constraints:
- Author rule: [optional]
- Topic/title rule: [optional]
- Casing and separators: [optional]
- Acronyms: [optional]
- Accents, surname particles, and hyphens: [optional]
- Existing labels to preserve: [optional]
- Duplicate/timestamp preference: [optional]

Work in these phases.

Phase 1 — understand and propose:

1. Inspect the existing organized-paper folders, representative metadata notes,
   metadata quality, timestamped labels, intentional legacy labels, and all
   current label-generation or parsing assumptions in `paperhub_utils`, the
   onboarding material, paper-organizer/downloader instructions, tests, and
   public examples.
2. Discover the configured Obsidian vault root and distinguish PaperHub files
   from active notes elsewhere in the same vault.
3. Summarize the current convention and its readability/compatibility issues.
4. Propose several concrete naming options. For every option, show worked
   examples for one author, two authors, and three or more authors, plus rules
   for acronyms, accents, surname particles, hyphens, topic words, legacy
   labels, and collisions.
5. Recommend one option with tradeoffs, write the options to the note I name if
   requested, and wait for my explicit choice. Do not rename anything or change
   future defaults before I choose.

Phase 2 — plan, map, and review after I choose:

6. Turn my choice into an exact specification and implementation plan. Include
   the existing-library migration, vault-wide reference update, future personal
   default, onboarding choice, public-template default if requested,
   verification, versioning, release, and temporary cleanup.
7. Re-inventory immediately before mapping.
8. Create stable JSONL batches under a temporary work directory. You may
   delegate mapping batches concurrently, but each mapping agent must own one
   separate output file and follow MAPPING_AGENT_PROMPT.md.
9. Derive authors and year from metadata. Use title, abstract, and tags only to
   recover topic word boundaries, acronyms, and enough extra words to avoid a
   collision. Do not silently change the topic meaning.
10. As the root agent, review every proposed label yourself. Do not ask me to
   review the manifest unless I explicitly request it.
11. Audit every collision and timestamp proposal bibliographically using title,
   authors, year, DOI/URL, abstract, created date, and local PDF hashes. Never
   merge or delete papers.
12. Use the bundled `label_migration.py` for inventory, batching, manifest
    validation, vault-wide replacement, rollback, and verification. Adapt the
    engine only if my requested format exposes a real unsupported case. Keep
    editorial mapping decisions in reviewable JSONL rather than embedding them
    invisibly in code.
13. Build a frozen manifest, consolidated review, preflight report, and
   verification report. Abort if source paths, metadata, folder contents,
   reference counts, or target uniqueness change after approval.

Phase 3 — apply the existing-library migration:

14. Rename folders and canonical metadata notes through globally unique
   temporary names. Leave PDFs, ai_summary.md, and hand-written filenames
   unchanged.
15. Rewrite exact old labels and complete old paths across the entire configured
   Obsidian vault in active Markdown, Canvas, and Base files. Use one-pass
   longest-match replacement, explicit path mappings, NFC/NFD aliases, and
   atomic writes. Exclude settings, caches, trash, virtual environments, Git
   internals, and migration artifacts.
16. Back up every external vault file that will change before writing. On any
    failure, restore external preimages and reverse completed path renames.
17. Verify exact folder/metadata casing, case-insensitive uniqueness, zero old
   references, unchanged non-Markdown hashes, valid Markdown frontmatter/Base
   YAML, valid Canvas JSON, and unchanged Canvas node/edge topology. Run the
   complete PaperHub test suite.

Phase 4 — update future label behavior:

18. Update `paperhub_utils/prompts/shared/paper_label.txt` to express the chosen
    convention with one-, two-, and multi-author examples.
19. Add or update a shared safe-label/formatting helper. Update PDF, CLI,
    link-ingestion, response-parser, and paper-downloader paths so the chosen
    casing and acronyms survive while legacy labels remain accepted.
20. Make the chosen convention the first recommended onboarding option with a
    stable style ID. Update coding-agent instructions, tests, the beginner
    README example, questionnaire, quick-start documentation, utility
    changelog, and utility manifest when applicable.
21. Treat future defaults as prospective: do not make adopters’ existing labels
    auto-migrate.

Phase 5 — verify and release:

22. Rerun the full suite plus migration verification after all framework and
    documentation changes.
23. Use `versioning-with-git` and `public-template-sync` only if I ask for release.
    Never edit the public template first.
24. Keep all temporary scripts, mappings, reviews, preimages, and reports until
    I explicitly say “all pass.” After that confirmation, verify once more,
    remove the temporary artifacts and links, leave a short permanent summary,
    and version the cleanup.

Before the write, summarize the exact candidate count, preserved count, skipped
count, touched vault files, files outside PaperHub, replacement count,
collision result, and rollback coverage. Then continue with the requested
migration when all safety gates pass.
```
