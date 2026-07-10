"""Workspace: the .memvana/ data directory that holds all persistent state.

Layout:
    .memvana/
        documents/   ingested markdown, one file per source
        graph.json   the knowledge graph
        memory.db    SQLite database for sessions and observations
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WORKSPACE_DIR_NAME = ".memvana"
DOCUMENTS_DIR_NAME = "documents"
GRAPH_FILE_NAME = "graph.json"
MEMORY_DB_NAME = "memory.db"


@dataclass(frozen=True)
class Workspace:
    """Paths for one Memvana workspace, rooted at a project directory."""

    root: Path

    @property
    def base_dir(self) -> Path:
        return self.root / WORKSPACE_DIR_NAME

    @property
    def documents_dir(self) -> Path:
        return self.base_dir / DOCUMENTS_DIR_NAME

    @property
    def graph_path(self) -> Path:
        return self.base_dir / GRAPH_FILE_NAME

    @property
    def memory_db_path(self) -> Path:
        return self.base_dir / MEMORY_DB_NAME

    def ensure(self) -> "Workspace":
        """Create the workspace directories if they do not exist."""
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def exists(self) -> bool:
        return self.base_dir.is_dir()


def find_workspace(start: Path | None = None) -> Workspace:
    """Locate the nearest workspace at or above ``start``.

    Falls back to a workspace rooted at ``start`` itself when no existing
    ``.memvana`` directory is found, so callers can always write.
    """
    origin = (start or Path.cwd()).resolve()
    for candidate in [origin, *origin.parents]:
        workspace = Workspace(candidate)
        if workspace.exists:
            return workspace
    return Workspace(origin)
