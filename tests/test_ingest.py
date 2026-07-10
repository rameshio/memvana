"""Tests for the ingestion layer."""

from pathlib import Path

from memvana.ingest.converter import ingest_path, scan_directory


def test_ingests_markdown_directly(tmp_path: Path):
    # Arrange
    source = tmp_path / "notes.md"
    source.write_text("# Project Notes\n\nSome **ideas** here.", encoding="utf-8")

    # Act
    doc = ingest_path(source)

    # Assert
    assert doc is not None
    assert doc.kind == "markdown"
    assert doc.title == "Project Notes"
    assert "**ideas**" in doc.markdown


def test_wraps_python_code_in_fence(tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text("def greet():\n    return 'hi'\n", encoding="utf-8")

    doc = ingest_path(source)

    assert doc is not None
    assert doc.kind == "python"
    assert "```python" in doc.markdown
    assert "def greet():" in doc.markdown


def test_returns_none_for_unsupported_extension(tmp_path: Path):
    source = tmp_path / "binary.exe"
    source.write_bytes(b"\x00\x01")

    assert ingest_path(source) is None


def test_doc_id_is_stable_for_same_path(tmp_path: Path):
    source = tmp_path / "stable.md"
    source.write_text("# A", encoding="utf-8")

    first = ingest_path(source)
    second = ingest_path(source)

    assert first is not None and second is not None
    assert first.doc_id == second.doc_id


def test_scan_skips_vendored_directories(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    (tmp_path / ".memvana").mkdir()
    (tmp_path / ".memvana" / "leftover.md").write_text("x", encoding="utf-8")

    found = scan_directory(tmp_path)

    assert [p.name for p in found] == ["main.py"]
