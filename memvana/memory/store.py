"""SQLite-backed memory store with FTS5 full-text search.

Progressive disclosure keeps recall token-cheap: ``recall`` returns a compact
index (id, time, one-line summary); ``get_observation`` fetches full content
only for the entries the caller actually wants.

Text wrapped in <private>...</private> is stripped before storage so secrets
never reach disk.
"""

from __future__ import annotations

import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

PRIVATE_PATTERN = re.compile(r"<private>.*?</private>", re.DOTALL | re.IGNORECASE)
SUMMARY_LENGTH = 120
DEFAULT_RECALL_LIMIT = 10

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL,
    title TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    created_at REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'note',
    tags TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
    content, tags, content='observations', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
    INSERT INTO observations_fts(rowid, content, tags)
    VALUES (new.rowid, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, content, tags)
    VALUES ('delete', old.rowid, old.content, old.tags);
END;
"""


@dataclass(frozen=True)
class Observation:
    id: str
    session_id: str
    created_at: float
    kind: str
    tags: str
    content: str

    @property
    def summary(self) -> str:
        first_line = self.content.strip().splitlines()[0] if self.content.strip() else ""
        if len(first_line) > SUMMARY_LENGTH:
            return first_line[: SUMMARY_LENGTH - 3] + "..."
        return first_line


def _strip_private(text: str) -> str:
    return PRIVATE_PATTERN.sub("[private content removed]", text)


class MemoryStore:
    """One memory database. Open with a context manager or call close()."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_path))
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- sessions ----------------------------------------------------------

    def start_session(self, title: str = "") -> str:
        session_id = uuid.uuid4().hex[:12]
        self._connection.execute(
            "INSERT INTO sessions (id, started_at, title) VALUES (?, ?, ?)",
            (session_id, time.time(), title),
        )
        self._connection.commit()
        return session_id

    def end_session(self, session_id: str) -> None:
        self._connection.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (time.time(), session_id),
        )
        self._connection.commit()

    def current_session(self) -> str:
        """Latest open session id, creating one when none is open."""
        row = self._connection.execute(
            "SELECT id FROM sessions WHERE ended_at IS NULL "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else self.start_session()

    def list_sessions(self, limit: int = 20) -> list[tuple[str, float, float | None, str, int]]:
        """(id, started_at, ended_at, title, observation_count) rows, newest first."""
        rows = self._connection.execute(
            """
            SELECT s.id, s.started_at, s.ended_at, s.title, COUNT(o.id)
            FROM sessions s LEFT JOIN observations o ON o.session_id = s.id
            GROUP BY s.id ORDER BY s.started_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return rows

    # -- observations ------------------------------------------------------

    def remember(
        self,
        content: str,
        kind: str = "note",
        tags: str = "",
        session_id: str | None = None,
    ) -> Observation:
        cleaned = _strip_private(content).strip()
        if not cleaned:
            raise ValueError("Cannot remember empty content")
        observation = Observation(
            id=uuid.uuid4().hex[:12],
            session_id=session_id or self.current_session(),
            created_at=time.time(),
            kind=kind,
            tags=tags,
            content=cleaned,
        )
        self._connection.execute(
            "INSERT INTO observations (id, session_id, created_at, kind, tags, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                observation.id, observation.session_id, observation.created_at,
                observation.kind, observation.tags, observation.content,
            ),
        )
        self._connection.commit()
        return observation

    def recall(self, query: str, limit: int = DEFAULT_RECALL_LIMIT) -> list[Observation]:
        """Full-text search, newest-relevant first. Falls back to substring
        matching when the FTS query syntax is invalid (e.g. stray quotes)."""
        try:
            rows = self._connection.execute(
                """
                SELECT o.id, o.session_id, o.created_at, o.kind, o.tags, o.content
                FROM observations_fts f JOIN observations o ON o.rowid = f.rowid
                WHERE observations_fts MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = self._connection.execute(
                """
                SELECT id, session_id, created_at, kind, tags, content
                FROM observations WHERE content LIKE ? OR tags LIKE ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        return [Observation(*row) for row in rows]

    def get_observation(self, observation_id: str) -> Observation | None:
        row = self._connection.execute(
            "SELECT id, session_id, created_at, kind, tags, content "
            "FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
        return Observation(*row) if row else None

    def recent(self, limit: int = DEFAULT_RECALL_LIMIT) -> list[Observation]:
        rows = self._connection.execute(
            "SELECT id, session_id, created_at, kind, tags, content "
            "FROM observations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [Observation(*row) for row in rows]

    def count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()[0]
