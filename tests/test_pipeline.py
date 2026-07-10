"""Tests for the ingest pipeline: incremental rebuilds and source routing."""

from pathlib import Path

from memvana.pipeline import ingest_sources, store_documents
from memvana.workspace import Workspace


def test_unchanged_files_are_skipped_on_second_run(tmp_path: Path):
    (tmp_path / "notes.md").write_text("# Notes\n\nHello.", encoding="utf-8")
    workspace = Workspace(tmp_path).ensure()

    first = ingest_sources(workspace, [str(tmp_path)])
    store_documents(workspace, first.converted)
    second = ingest_sources(workspace, [str(tmp_path)])

    assert len(first.converted) == 1 and not first.unchanged
    assert not second.converted and len(second.unchanged) == 1


def test_modified_file_is_reingested(tmp_path: Path):
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\nversion one", encoding="utf-8")
    workspace = Workspace(tmp_path).ensure()
    store_documents(workspace, ingest_sources(workspace, [str(source)]).converted)

    source.write_text("# Notes\n\nversion two", encoding="utf-8")
    result = ingest_sources(workspace, [str(source)])

    assert len(result.converted) == 1
    assert not result.unchanged


def test_missing_source_is_reported_skipped(tmp_path: Path):
    workspace = Workspace(tmp_path).ensure()

    result = ingest_sources(workspace, [str(tmp_path / "ghost.md")])

    assert result.skipped == [str(tmp_path / "ghost.md")]
