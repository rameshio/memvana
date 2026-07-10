"""End-to-end CLI tests: build -> query -> path -> remember -> recall."""

import os
from pathlib import Path

import pytest

from memvana.cli import main


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "README.md").write_text(
        "# Sample App\n\n## Architecture\n\nBuilt on **Flask**.\n",
        encoding="utf-8",
    )
    (tmp_path / "server.py").write_text(
        "def start_server():\n"
        '    """Boot the app."""\n'
        "    return configure()\n\n"
        "def configure():\n"
        "    return {}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_build_creates_workspace(project: Path, capsys: pytest.CaptureFixture):
    exit_code = main(["build", "."])

    assert exit_code == 0
    assert (project / ".memvana" / "graph.json").is_file()
    output = capsys.readouterr().out
    assert "Ingested 2 documents" in output


def test_query_finds_function(project: Path, capsys: pytest.CaptureFixture):
    main(["build", "."])

    exit_code = main(["query", "start_server"])

    assert exit_code == 0
    assert "start_server" in capsys.readouterr().out


def test_path_connects_functions(project: Path, capsys: pytest.CaptureFixture):
    main(["build", "."])

    exit_code = main(["path", "start_server", "configure"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "start_server" in output and "configure" in output


def test_explain_shows_node(project: Path, capsys: pytest.CaptureFixture):
    main(["build", "."])

    exit_code = main(["explain", "Sample App"])

    assert exit_code == 0
    assert "Sample App" in capsys.readouterr().out


def test_remember_then_recall(project: Path, capsys: pytest.CaptureFixture):
    main(["remember", "Chose", "Flask", "over", "Django", "--tags", "decision"])
    capsys.readouterr()

    exit_code = main(["recall", "Flask"])

    assert exit_code == 0
    assert "Chose Flask over Django" in capsys.readouterr().out


def test_html_export(project: Path, capsys: pytest.CaptureFixture):
    main(["build", "."])

    exit_code = main(["html"])

    assert exit_code == 0
    assert (project / ".memvana" / "graph.html").is_file()


def test_status_reports_counts(project: Path, capsys: pytest.CaptureFixture):
    main(["build", "."])
    main(["remember", "a", "fact"])
    capsys.readouterr()

    exit_code = main(["status"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "nodes" in output and "observations" in output
