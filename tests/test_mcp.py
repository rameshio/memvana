"""Tests for MCP tool functions (plain functions, no SDK needed)."""

from pathlib import Path

from memvana import mcp_server


def _project(tmp_path: Path) -> str:
    (tmp_path / "notes.md").write_text(
        "# Job Search\n\n## Target Roles\n\nFocus on **Platform Engineering**.",
        encoding="utf-8",
    )
    return str(tmp_path)


def test_ingest_reports_documents_and_graph(tmp_path: Path):
    result = mcp_server.ingest([_project(tmp_path)], project_dir=str(tmp_path))

    assert "Job Search" in result
    assert "nodes" in result and "tokens ingested" in result


def test_ask_returns_graph_and_token_meter(tmp_path: Path):
    project = _project(tmp_path)
    mcp_server.ingest([project], project_dir=project)

    result = mcp_server.ask("Platform Engineering", project_dir=project)

    assert "knowledge graph:" in result
    assert "tokens:" in result


def test_ask_without_content_gives_guidance(tmp_path: Path):
    result = mcp_server.ask("anything", project_dir=str(tmp_path))

    assert "Ingest content first" in result


def test_remember_recall_get_memory_round_trip(tmp_path: Path):
    project = str(tmp_path)
    stored = mcp_server.remember(
        "Resume decision: lead with platform work", tags="resume",
        project_dir=project,
    )
    memory_id = stored.split("[")[1].split("]")[0]

    index = mcp_server.recall("resume", project_dir=project)
    full = mcp_server.get_memory(memory_id, project_dir=project)

    assert memory_id in index
    assert "lead with platform work" in full


def test_explain_node_shows_connections(tmp_path: Path):
    project = _project(tmp_path)
    mcp_server.ingest([project], project_dir=project)

    result = mcp_server.explain_node("Job Search", project_dir=project)

    assert "Job Search" in result
    assert "outgoing:" in result


def test_status_reports_counts(tmp_path: Path):
    project = _project(tmp_path)
    mcp_server.ingest([project], project_dir=project)

    result = mcp_server.status(project_dir=project)

    assert "nodes" in result and "Corpus" in result


def test_default_workspace_is_home(tmp_path: Path):
    workspace = mcp_server._workspace("")

    assert workspace.root == Path.home().resolve()
