# Memvana

**Universal ingestion → knowledge graph → persistent memory. One tool that turns anything into a queryable graph that remembers.**

Memvana combines the three jobs you normally need three separate tools for:

| Job | Inspired by | What Memvana does |
|-----|-------------|-------------------|
| Ingest anything | [MarkItDown](https://github.com/microsoft/markitdown) | Converts PDF, Word, PowerPoint, Excel, HTML, images, audio, code, and more into clean Markdown |
| Understand it | [Graphify](https://github.com/Graphify-Labs/graphify) | Builds a knowledge graph — documents, sections, modules, classes, functions, concepts — with `query`, `path`, and `explain` commands |
| Remember it | [claude-mem](https://github.com/thedotmack/claude-mem) | Persistent, searchable memory across sessions, with Claude Code hooks that inject past context automatically |

Everything runs **locally**. Code and Markdown analysis is fully deterministic — no LLM, no API calls, nothing leaves your machine.

## Install

```bash
pip install memvana            # core (text, code, HTML, and common rich formats)
pip install "memvana[all]"     # every format MarkItDown supports (PDF, Office, audio, ...)
```

## Quick start

```bash
cd your-project

# 1. Ingest everything and build the knowledge graph
memvana build .

# 2. Ask the graph questions
memvana query PaymentService
memvana path checkout.py DatabasePool     # how are these two connected?
memvana explain validate_user             # everything around one node

# 3. Explore visually (self-contained HTML, no internet needed)
memvana html

# 4. Remember things across sessions
memvana remember "Chose Postgres over MySQL for JSONB support" --tags decision
memvana recall postgres
```

Add individual files anytime — any format:

```bash
memvana ingest design-spec.pdf meeting-notes.docx architecture.png
```

## How it works

```
 anything          .memvana/                queryable
┌─────────┐      ┌────────────────┐       ┌──────────────┐
│ PDF     │      │ documents/*.md │       │ query        │
│ Office  │ ───► │ graph.json     │  ───► │ path         │
│ HTML    │      │ memory.db      │       │ explain      │
│ images  │      └────────────────┘       │ recall       │
│ audio   │       one workspace,          │ graph.html   │
│ code    │       all persistent          └──────────────┘
└─────────┘
```

1. **Ingest** — text and code are read directly; rich formats go through MarkItDown. Everything is stored as Markdown in `.memvana/documents/`.
2. **Graph** — Markdown structure (headings, links, `[[wiki-links]]`, **bold concepts**) and Python code (imports, classes, functions, calls, inheritance via AST) become nodes and edges. Every edge is tagged **extracted** (stated in the source) or **inferred** (derived by name resolution or co-occurrence), so you always know how much to trust a connection. Communities are detected by label propagation.
3. **Memory** — observations live in SQLite with FTS5 full-text search. `recall` returns a compact index first (cheap); `show <id>` fetches full content only when needed — progressive disclosure keeps context token-efficient for AI agents. Anything wrapped in `<private>...</private>` is stripped before it ever reaches disk.

## Claude Code integration

Give every Claude Code session persistent memory by wiring three hooks into `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "memvana hook session-start" }] }],
    "PostToolUse":  [{ "hooks": [{ "type": "command", "command": "memvana hook post-tool" }] }],
    "SessionEnd":   [{ "hooks": [{ "type": "command", "command": "memvana hook session-end" }] }]
  }
}
```

On session start, Memvana prints recent memory as context. During the session it records what the agent changes. Hooks never raise — a memory failure will never break your coding session.

## Command reference

| Command | Purpose |
|---------|---------|
| `memvana build [path]` | Ingest a directory and build the graph |
| `memvana ingest <file...>` | Ingest specific files (any format) and update the graph |
| `memvana query <term>` | Search graph nodes |
| `memvana path <a> <b>` | Shortest connection between two things |
| `memvana explain <term>` | One node and everything connected to it |
| `memvana html [-o file]` | Export interactive graph viewer |
| `memvana remember <text>` | Store a memory (`--tags`, `--kind`) |
| `memvana recall <query>` | Search memories (`--full`, `--limit`) |
| `memvana show <id>` | Full content of one memory |
| `memvana sessions` | List memory sessions |
| `memvana status` | Workspace statistics |
| `memvana hook <event>` | Claude Code hook endpoint |

## Development

```bash
git clone https://github.com/ramesh-aiorchestrator/memvana
cd memvana
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE)
