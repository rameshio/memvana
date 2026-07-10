"""MCP server: Memvana for Claude Desktop and any other MCP client.

Tool logic lives in plain functions so it is testable without the MCP SDK;
``serve()`` wraps them in a FastMCP stdio server (install: memvana[mcp]).

Without a ``project_dir`` argument, tools use a global workspace at
``~/.memvana`` — right for desktop chats that aren't tied to one project.
"""

from __future__ import annotations

import time
from pathlib import Path

from memvana.graph.model import KnowledgeGraph
from memvana.graph.query import explain as graph_explain
from memvana.graph.query import search, shortest_path
from memvana.memory.store import MemoryStore
from memvana.pipeline import ingest_sources, rebuild_graph, store_documents
from memvana.tokens import corpus_tokens, estimate_tokens, savings_line
from memvana.workspace import Workspace

SERVER_INSTRUCTIONS = (
    "Memvana turns local files, URLs, and decisions into a queryable "
    "knowledge graph with persistent memory. Ingest documents the user "
    "mentions, answer connection questions with ask/explain/path_between, "
    "and store or retrieve decisions with remember/recall. Content is "
    "converted locally once; queries return small token-cheap slices."
)


def _workspace(project_dir: str = "") -> Workspace:
    root = Path(project_dir).expanduser() if project_dir else Path.home()
    return Workspace(root.resolve())


def _stamp(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))


def ingest(sources: list[str], project_dir: str = "") -> str:
    """Ingest local files, directories, or URLs (PDF, Office, HTML, images,
    audio, code...) into the knowledge graph. Conversion happens locally and
    costs no tokens; afterwards the content is queryable with ask/explain."""
    workspace = _workspace(project_dir).ensure()
    result = ingest_sources(workspace, sources)
    store_documents(workspace, result.converted)
    graph = rebuild_graph(workspace)
    lines = [f"+ {doc.title} ({doc.kind}) <- {doc.source}"
             for doc in result.converted]
    lines += [f"= unchanged {path}" for path in result.unchanged]
    lines += [f"~ skipped (unsupported/unreadable): {item}"
              for item in result.skipped]
    lines.append(f"Graph now has {len(graph.nodes)} nodes, "
                 f"{len(graph.edges)} edges "
                 f"(~{corpus_tokens(workspace):,} tokens ingested).")
    return "\n".join(lines)


def ask(query: str, project_dir: str = "") -> str:
    """Search the knowledge graph AND persistent memory together. Best first
    tool for any question about ingested content or past decisions."""
    workspace = _workspace(project_dir)
    lines: list[str] = []

    graph = KnowledgeGraph.load(workspace.graph_path)
    hits = search(graph, query)
    if hits:
        lines.append("knowledge graph:")
        for hit in hits[:8]:
            node = hit.node
            location = f"  ({node.source})" if node.source else ""
            lines.append(f"  [{node.type:>8}] {node.label}{location}")

    if workspace.memory_db_path.is_file():
        with MemoryStore(workspace.memory_db_path) as store:
            memories = store.recall(query, limit=8)
        if memories:
            if lines:
                lines.append("")
            lines.append("memories:")
            for observation in memories:
                lines.append(
                    f"  [{observation.id}] {_stamp(observation.created_at)} "
                    f"({observation.kind}) {observation.summary}"
                )

    if not lines:
        return (f"Nothing in the graph or memory matches '{query}'. "
                "Ingest content first, or try a different term.")
    output = "\n".join(lines)
    return output + "\n\n" + savings_line(
        estimate_tokens(output), corpus_tokens(workspace)
    )


def explain_node(term: str, project_dir: str = "") -> str:
    """Describe one thing in the graph: its type, source, docstring, every
    connection in and out, and memories that mention it."""
    workspace = _workspace(project_dir)
    graph = KnowledgeGraph.load(workspace.graph_path)
    result = graph_explain(graph, term)
    if result is None:
        return f"No node matching '{term}'."
    node = result.node
    lines = [f"{node.label}  [{node.type}]"]
    if node.source:
        lines.append(f"source: {node.source}")
    if node.detail:
        lines.append(f"detail: {node.detail[:300]}")
    if result.outgoing:
        lines.append("outgoing:")
        for edge, other in result.outgoing[:25]:
            suffix = " (inferred)" if edge.confidence == "inferred" else ""
            lines.append(f"  {edge.relation} -> {other.label}{suffix}")
    if result.incoming:
        lines.append("incoming:")
        for edge, other in result.incoming[:25]:
            suffix = " (inferred)" if edge.confidence == "inferred" else ""
            lines.append(f"  {other.label} -{edge.relation}->{suffix}")
    if workspace.memory_db_path.is_file():
        with MemoryStore(workspace.memory_db_path) as store:
            memories = store.recall(node.label, limit=5)
        if memories:
            lines.append("memories:")
            for observation in memories:
                lines.append(f"  [{observation.id}] {observation.summary}")
    return "\n".join(lines)


def path_between(start: str, end: str, project_dir: str = "") -> str:
    """Shortest connection between two things in the graph (functions,
    documents, concepts...). Edges marked '?' are inferred guesses."""
    graph = KnowledgeGraph.load(_workspace(project_dir).graph_path)
    path = shortest_path(graph, start, end)
    if path is None:
        return f"No path found between '{start}' and '{end}'."
    lines = []
    for node, edge in path:
        if edge is None:
            lines.append(f"{node.label} ({node.type})")
        else:
            marker = "?" if edge.confidence == "inferred" else "-"
            lines.append(f"  --{marker}[{edge.relation}]--> "
                         f"{node.label} ({node.type})")
    return "\n".join(lines)


def remember(text: str, tags: str = "", project_dir: str = "") -> str:
    """Store a fact or decision in persistent memory so it survives across
    chats. Wrap sensitive parts in <private>...</private> to keep them off
    disk."""
    workspace = _workspace(project_dir).ensure()
    with MemoryStore(workspace.memory_db_path) as store:
        observation = store.remember(text, tags=tags)
    return f"Remembered [{observation.id}] {observation.summary}"


def recall(query: str, limit: int = 10, project_dir: str = "") -> str:
    """Search persistent memory. Returns a compact index; use get_memory
    for the full content of a specific entry."""
    workspace = _workspace(project_dir)
    if not workspace.memory_db_path.is_file():
        return "No memories stored yet."
    with MemoryStore(workspace.memory_db_path) as store:
        results = store.recall(query, limit=limit)
    if not results:
        return f"No memories match '{query}'."
    return "\n".join(
        f"[{o.id}] {_stamp(o.created_at)} ({o.kind}) {o.summary}"
        for o in results
    )


def get_memory(memory_id: str, project_dir: str = "") -> str:
    """Full content of one memory, by the id shown in recall results."""
    workspace = _workspace(project_dir)
    if not workspace.memory_db_path.is_file():
        return "No memories stored yet."
    with MemoryStore(workspace.memory_db_path) as store:
        observation = store.get_observation(memory_id)
    if observation is None:
        return f"No memory with id '{memory_id}'."
    return (f"[{observation.id}] {_stamp(observation.created_at)} "
            f"({observation.kind}, tags: {observation.tags or '-'})\n"
            f"{observation.content}")


def status(project_dir: str = "") -> str:
    """Workspace statistics: graph size, ingested corpus tokens, memory
    count. Use to check whether anything has been ingested yet."""
    workspace = _workspace(project_dir)
    graph = KnowledgeGraph.load(workspace.graph_path)
    lines = [
        f"Workspace: {workspace.base_dir}",
        f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges",
        f"Corpus: ~{corpus_tokens(workspace):,} tokens ingested",
    ]
    if workspace.memory_db_path.is_file():
        with MemoryStore(workspace.memory_db_path) as store:
            lines.append(f"Memory: {store.count()} observations")
    else:
        lines.append("Memory: empty")
    return "\n".join(lines)


TOOLS = (
    ingest, ask, explain_node, path_between,
    remember, recall, get_memory, status,
)


def serve() -> None:
    """Run the stdio MCP server (blocks until the client disconnects)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "The MCP SDK is required for `memvana mcp`. "
            "Install it with: pip install 'memvana[mcp]'"
        ) from error
    server = FastMCP("memvana", instructions=SERVER_INSTRUCTIONS)
    for tool in TOOLS:
        server.tool()(tool)
    server.run()
