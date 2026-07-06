# Ask Knowledge Base

Use `ask-knowledge-base` when you want an answer from existing visible Markdown notes in your Obsidian vault, not from the web.

## Ask Across Vault Notes

```text
\ask-knowledge-base: what do my notes say about strategic ignorance and moral wiggle room?
```

For a broader source set:

```text
\ask-knowledge-base: search 20 notes for how I connect belief updating, motivated reasoning, and information avoidance.
```

For a deeper synthesis:

```text
\ask-knowledge-base: give me a detailed synthesis of my notes on zero-sum thinking and political economy.
```

Output: an answer grounded in the returned notes, with Obsidian wikilinks such as `[[projects/literature_map|Literature Map]]` or `[[danaetal2007moralwiggle]]`.

The skill searches visible `.md` files and skips dot-prefixed folders such as `.claude/`, `.agents/`, `.obsidian/`, `.git/`, and `.venv/`.
