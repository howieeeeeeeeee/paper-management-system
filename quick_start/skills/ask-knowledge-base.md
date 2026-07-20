# Ask Knowledge Base

Use `ask-knowledge-base` when you want an answer from existing visible Markdown notes in your Obsidian vault, not from the web.

## Ask Across Vault Notes

```text
/ask-knowledge-base: what do my notes say about strategic ignorance and moral wiggle room?
```

For a broader source set:

```text
/ask-knowledge-base: search 20 notes for how I connect belief updating, motivated reasoning, and information avoidance.
```

For a deeper synthesis:

```text
/ask-knowledge-base: give me a detailed synthesis of my notes on zero-sum thinking and political economy.
```

To search your own notes while skipping generated paper metadata and AI summaries:

```text
/ask-knowledge-base: search my notes about confirmation bias and large language models, without papers.
```

Output: an answer grounded in the returned notes, with Obsidian wikilinks such as `[[projects/literature_map|Literature Map]]` or `[[danaetal2007moralwiggle]]`.

The skill searches visible Markdown files and skips dot-prefixed folders such as `.claude/`, `.agents/`, `.obsidian/`, `.git/`, and `.venv/`. When you ask for "without papers" or "ignore papers", it skips standard PaperHub paper metadata notes, `ai_summary.md`, and legacy `summary.md` paper summaries while keeping regular hand-written notes.
