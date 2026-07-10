"""Tests for graph building and querying."""

from pathlib import Path

from memvana.graph.builder import build_graph
from memvana.graph.model import KnowledgeGraph
from memvana.graph.query import communities, explain, search, shortest_path
from memvana.ingest.converter import ingest_path


def _docs(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Demo Project\n\n## Setup\n\nUses **FastAPI** and **SQLite**.\n"
        "See [docs](https://example.com/docs).\n",
        encoding="utf-8",
    )
    app = tmp_path / "app.py"
    app.write_text(
        "import os\n\n"
        "class BaseHandler:\n"
        '    """Base for handlers."""\n'
        "    def handle(self):\n"
        "        return validate()\n\n"
        "def validate():\n"
        '    """Validate input."""\n'
        "    return True\n",
        encoding="utf-8",
    )
    return [ingest_path(readme), ingest_path(app)]


def test_builds_document_and_section_nodes(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))

    types = {node.type for node in graph.nodes.values()}
    assert {"document", "section", "module", "class", "function"} <= types
    labels = {node.label for node in graph.nodes.values()}
    assert "Demo Project" in labels
    assert "Setup" in labels
    assert "BaseHandler" in labels
    assert "validate" in labels


def test_python_extraction_produces_expected_edges(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))

    relations = {edge.relation for edge in graph.edges}
    assert {"contains", "mentions", "imports", "defines", "calls"} <= relations
    # handle() calls validate() -> resolved cross-entity as inferred
    call_edges = [e for e in graph.edges if e.relation == "calls"]
    assert call_edges and all(e.confidence == "inferred" for e in call_edges)


def test_search_ranks_exact_match_first(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))

    hits = search(graph, "validate")

    assert hits and hits[0].node.label == "validate"


def test_shortest_path_connects_doc_concept_to_code(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))

    path = shortest_path(graph, "handle", "validate")

    assert path is not None
    assert path[0][0].label == "handle"
    assert path[-1][0].label == "validate"


def test_explain_lists_connections(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))

    result = explain(graph, "BaseHandler")

    assert result is not None
    outgoing_labels = {other.label for _, other in result.outgoing}
    assert "handle" in outgoing_labels


def test_python_document_is_connected_to_its_module(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))

    # app.py's document node must reach its code entities.
    path = shortest_path(graph, "app.py", "BaseHandler")

    assert path is not None


def test_communities_cover_all_nodes(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))

    groups = communities(graph)

    grouped_ids = {nid for members in groups.values() for nid in members}
    assert grouped_ids == set(graph.nodes)


def test_graph_round_trips_through_json(tmp_path: Path):
    graph = build_graph(_docs(tmp_path))
    target = tmp_path / "graph.json"

    graph.save(target)
    loaded = KnowledgeGraph.load(target)

    assert set(loaded.nodes) == set(graph.nodes)
    assert len(loaded.edges) == len(graph.edges)


def test_load_missing_graph_returns_empty(tmp_path: Path):
    loaded = KnowledgeGraph.load(tmp_path / "missing.json")

    assert not loaded.nodes and not loaded.edges
