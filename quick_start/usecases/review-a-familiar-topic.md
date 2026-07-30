# Review a Familiar Topic from Your PaperHub

Use this workflow when you have already read many papers on a similar topic, stored them in PaperHub, and want a quick review of what you know before writing or returning to the project. It retrieves and reorganizes knowledge already present in your library.

Do not use this workflow to learn an unfamiliar topic. Its coverage is limited by the papers and notes already in PaperHub, and the resulting synthesis is not a substitute for reading the literature yourself.

## Prepare the Request

Provide:

- A familiar topic or research question.
- The absolute path of the Markdown note to create or update.
- The points you want refreshed, such as where the literature stands, experimental designs, competing mechanisms, or documented disagreements.

## Build the Review Note

Replace the placeholders in this prompt:

```text
I want a structured review of a familiar topic using papers already in my PaperHub.

Topic: <topic or research question>
Target note: <absolute path to note.md>
Focus: <what I want to refresh>

Use paper-finder in details mode and paperhub-obsidian to complete this task:

1. Search the entire PaperHub library using the topic, close synonyms, mechanisms, outcomes, and experimental terms.
2. Retrieve every meaningfully relevant paper rather than stopping at an arbitrary top 10.
3. Read the available metadata, AI summaries, and additional notes for the matched papers. Use ask-knowledge-base as well only when relevant non-paper notes in the vault should be included.
4. Synthesize the material into the target note. Cover the state of the literature, how the main experiments or empirical designs work, important disagreements, and the limits of the available evidence.
5. Cite papers with their existing PaperHub wikilinks. Distinguish documented findings from your own synthesis, and do not invent missing details.
6. Preserve useful existing content if the target note already exists, and keep the structure concise and readable in Obsidian.
7. Stay within the existing library and vault. Do not search for or import new papers. If coverage is thin, say what is missing instead of filling the gap from outside sources. Do not generate speculative research questions or claim a gap unless the reviewed material establishes it.

Report the number of papers reviewed, the main organizing themes, and any important gaps in the existing library.
```

The resulting note is a retrieval aid: use it to reactivate connections among papers you have already encountered, identify what to reread, and prepare for your own analysis.
