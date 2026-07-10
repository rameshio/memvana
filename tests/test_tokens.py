"""Tests for token estimation and the savings meter."""

from pathlib import Path

from memvana.tokens import corpus_tokens, estimate_tokens, savings_line
from memvana.workspace import Workspace


def test_estimate_tokens_uses_four_chars_per_token():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd" * 100) == 100


def test_corpus_tokens_sums_stored_documents(tmp_path: Path):
    workspace = Workspace(tmp_path).ensure()
    (workspace.documents_dir / "a.md").write_text("x" * 400, encoding="utf-8")
    (workspace.documents_dir / "b.md").write_text("y" * 400, encoding="utf-8")

    assert corpus_tokens(workspace) == 200


def test_savings_line_shows_percentage_and_bar():
    line = savings_line(100, 50_000)

    assert "% saved" in line
    assert "[" in line and "#" in line
    assert "~100 returned" in line


def test_savings_line_degrades_without_corpus():
    assert savings_line(100, 0) == "tokens: ~100 returned"
