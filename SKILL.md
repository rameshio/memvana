---
name: memvana
description: Use whenever the user shares a file (PDF, Word, Excel, PowerPoint, image, audio, HTML, code) or URL that should be understood or kept, asks how parts of a project connect ("how does X relate to Y", "what uses this", "explain this module"), or wants something remembered or recalled across sessions ("remember this decision", "what did we decide about..."). Turns anything into a queryable knowledge graph with persistent memory via the memvana CLI.
---

# Memvana

Memvana is a local CLI that combines three jobs: universal ingestion (any file
→ Markdown), a knowledge graph (query/path/explain), and persistent memory
(remember/recall across sessions). All state lives in the project's
`.memvana/` directory. Everything runs locally and deterministically.

## Setup check

Run `memvana --version`. If missing, install with:

```bash
pip install "memvana[all]"
```

If `memvana status` shows an empty graph and the user is working in a
project, build it once with `memvana build .`

## When the user shares a file or URL

Ingest it immediately — any format works (PDF, docx, xlsx, pptx, images,
audio, HTML, code, URLs):

```bash
memvana ingest <path-or-url> [more...]
```

The content becomes part of the knowledge graph. Then answer the user's
question about it using the query commands below.

## When the user asks how things connect

Prefer graph queries over grepping:

```bash
memvana ask <term>          # best first move: graph + memory in one answer
memvana query <term>        # graph nodes matching a term
memvana path <a> <b>        # shortest connection between two things
memvana explain <term>      # one node, all its edges, related memories
memvana html                # interactive visual graph (.memvana/graph.html)
```

Edges marked `(inferred)` or `?` are derived guesses (name resolution,
co-occurrence); unmarked edges were stated explicitly in the source. Say so
when an answer rests on inferred edges.

## When the user wants something remembered or recalled

```bash
memvana remember "<text>" --tags <tags>   # store a decision/fact
memvana recall <query>                    # compact index of matches
memvana show <id>                         # full content of one memory
```

Recall is progressive: start with the compact index, fetch full content with
`show` only for entries that matter. Wrap anything sensitive the user asks
you to store in `<private>...</private>` — Memvana strips it before disk.

## Automatic memory (offer once, don't push)

If the user wants memory to persist automatically across Claude Code
sessions, add to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "memvana hook session-start" }] }],
    "PostToolUse":  [{ "hooks": [{ "type": "command", "command": "memvana hook post-tool" }] }],
    "SessionEnd":   [{ "hooks": [{ "type": "command", "command": "memvana hook session-end" }] }]
  }
}
```
