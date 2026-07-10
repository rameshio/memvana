"""Claude Code hook handlers.

Wire these into .claude/settings.json to give any Claude Code session
persistent memory:

    SessionStart  -> memvana hook session-start   (prints recent context)
    PostToolUse   -> memvana hook post-tool       (records tool activity)
    SessionEnd    -> memvana hook session-end     (closes the session)

Each handler reads the hook payload JSON from stdin when present and never
raises: a broken memory hook must not break the coding session.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from memvana.memory.store import MemoryStore
from memvana.workspace import find_workspace

CONTEXT_OBSERVATIONS = 8
# Tools whose invocations are worth remembering; read-only lookups are noise.
RECORDED_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash", "PowerShell"}
MAX_INPUT_PREVIEW = 200


def _read_payload() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _store(root: Path | None = None) -> MemoryStore:
    workspace = find_workspace(root).ensure()
    return MemoryStore(workspace.memory_db_path)


def handle_session_start(root: Path | None = None) -> int:
    """Open a session and print recent memory as context for the agent."""
    payload = _read_payload()
    try:
        with _store(root) as store:
            store.start_session(title=payload.get("source", "claude-code"))
            recent = store.recent(CONTEXT_OBSERVATIONS)
        if recent:
            print("## Memvana: memory from previous sessions")
            for observation in recent:
                stamp = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(observation.created_at)
                )
                print(f"- [{stamp}] ({observation.kind}) {observation.summary}")
            print(
                "\nUse `memvana recall <query>` for details on any of these."
            )
    except Exception as error:  # noqa: BLE001 - hooks must never crash the host
        print(f"memvana: session-start hook skipped ({error})", file=sys.stderr)
    return 0


def handle_post_tool(root: Path | None = None) -> int:
    """Record a one-line observation about a mutating tool call."""
    payload = _read_payload()
    tool_name = payload.get("tool_name", "")
    if tool_name not in RECORDED_TOOLS:
        return 0
    tool_input = payload.get("tool_input", {})
    target = (
        tool_input.get("file_path")
        or tool_input.get("command")
        or json.dumps(tool_input)[:MAX_INPUT_PREVIEW]
    )
    try:
        with _store(root) as store:
            store.remember(
                f"{tool_name}: {str(target)[:MAX_INPUT_PREVIEW]}",
                kind="tool",
                tags=tool_name.lower(),
            )
    except Exception as error:  # noqa: BLE001
        print(f"memvana: post-tool hook skipped ({error})", file=sys.stderr)
    return 0


def handle_session_end(root: Path | None = None) -> int:
    """Close the open session."""
    try:
        with _store(root) as store:
            store.end_session(store.current_session())
    except Exception as error:  # noqa: BLE001
        print(f"memvana: session-end hook skipped ({error})", file=sys.stderr)
    return 0


HANDLERS = {
    "session-start": handle_session_start,
    "post-tool": handle_post_tool,
    "session-end": handle_session_end,
}
