"""Tests for the persistent memory store."""

from pathlib import Path

import pytest

from memvana.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path: Path):
    with MemoryStore(tmp_path / "memory.db") as memory_store:
        yield memory_store


def test_remember_and_recall_by_keyword(store: MemoryStore):
    store.remember("Fixed the login redirect bug in auth.py", tags="bugfix")
    store.remember("Deployed version 1.2 to staging")

    results = store.recall("login")

    assert len(results) == 1
    assert "login redirect" in results[0].content


def test_recall_survives_reopening_database(tmp_path: Path):
    db = tmp_path / "memory.db"
    with MemoryStore(db) as first:
        first.remember("Persistent fact about the API rate limit")
    with MemoryStore(db) as second:
        results = second.recall("rate limit")

    assert len(results) == 1


def test_private_content_is_stripped(store: MemoryStore):
    store.remember("Set env var <private>API_KEY=sk-secret-123</private> on server")

    results = store.recall("server")

    assert len(results) == 1
    assert "sk-secret-123" not in results[0].content
    assert "[private content removed]" in results[0].content


def test_empty_content_is_rejected(store: MemoryStore):
    with pytest.raises(ValueError):
        store.remember("   ")


def test_summary_truncates_long_first_line(store: MemoryStore):
    observation = store.remember("word " * 100)

    assert len(observation.summary) <= 120
    assert observation.summary.endswith("...")


def test_sessions_track_observations(store: MemoryStore):
    session_id = store.start_session(title="test run")
    store.remember("observation one", session_id=session_id)
    store.remember("observation two", session_id=session_id)
    store.end_session(session_id)

    sessions = store.list_sessions()

    assert sessions[0][0] == session_id
    assert sessions[0][4] == 2  # observation count
    assert sessions[0][2] is not None  # ended_at set


def test_recall_falls_back_on_bad_fts_syntax(store: MemoryStore):
    store.remember('Note about "quoted (weird) syntax" handling')

    results = store.recall('"quoted (weird')

    assert len(results) == 1


def test_get_observation_returns_full_content(store: MemoryStore):
    observation = store.remember("line one\nline two with detail")

    fetched = store.get_observation(observation.id)

    assert fetched is not None
    assert fetched.content == "line one\nline two with detail"
