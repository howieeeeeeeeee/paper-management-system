---
name: obsidian-html-visuals
description: Create restrained, theme-compatible raw HTML visuals inside Obsidian Markdown notes. Use for aligned process boxes, compact flowcharts that would be too long or wide in Mermaid, comparison tables, experiment flows, and subject-view schematics that should render well in both dark and light mode.
---

# Obsidian HTML Visuals

Use raw HTML only when it makes a relationship clearer than ordinary prose, a Markdown table, or a callout. Keep visuals compact and close to the explanation they support.

## Choose Mermaid or HTML

- Prefer Mermaid first for a conventional flowchart when its rendered layout is compact and easy to scan.
- Switch to raw HTML when Mermaid would render the chart too long or wide, produce awkward connectors or label wrapping, or otherwise obscure the flow. Use HTML to recompose the structure into a compact readable layout rather than reproducing the same unwieldy row.
- Use HTML for other relationships that benefit from controlled alignment, including process boxes, cycles, comparisons, timelines, experiment flows, and subject-view schematics.
- Plot every substantive relationship inside the visual. For a feedback cycle, draw a return connector from the source node to the target node; a prose note below the chart is not a substitute for the missing edge.

## Workflow

1. Choose a fixed-layout table for aligned rows and columns, a small grid for repeated cards, or one framed panel for a subject view.
2. Use Obsidian theme variables rather than fixed colors.
3. Keep substantive equations outside HTML.
4. Verify the result in Reading View when possible.

Read [references/PATTERNS.md](references/PATTERNS.md) only when a reusable starting pattern would help.

## Style

- Prefer `var(--background-primary)`, `var(--background-secondary)`, `var(--background-modifier-border)`, `var(--text-normal)`, and `var(--text-muted)`.
- Use one-pixel borders, modest 4–6 px corner radii, consistent 6–10 px gaps, and equal-width or fixed-layout columns.
- Avoid gradients, shadows, decorative icons, colored arrows, and treatment-specific colors.
- Use an overflow wrapper when a fixed-width table would otherwise become cramped.
- Do not restyle existing HTML unless the user asks or the requested edit requires it.

## Obsidian constraints

- Do not use JavaScript, iframes, external assets, or embedded `<style>` blocks.
- Do not rely on Markdown or MathJax rendering inside raw HTML. Use HTML tags for formatting and Unicode such as `θ`, `b₁`, and `b₂`; place math outside with `$...$` or `$$...$$`.
- Label reconstructions as schematics. Keep analyst annotations separate from what a participant actually saw.
- Preserve PaperHub metadata, links, tags, and user-owned content.

## Verify

- Check balanced tags, aligned repeated elements, and the absence of `\(...\)` or `\[...\]`.
- Confirm that hidden or omitted information is not presented as subject-visible.
- Inspect both light and dark mode when a live Obsidian view is available; otherwise use only the theme variables above.
