"""Memvana command-line interface.

    memvana build [path]          ingest a directory and build the graph
    memvana ingest <src...>       ingest files or URLs and update the graph
    memvana ask <term>            search graph and memory together
    memvana query <term>          search the knowledge graph
    memvana path <a> <b>          shortest connection between two things
    memvana explain <term>        everything connected to one node
    memvana html [-o file]        export the interactive graph viewer
    memvana remember <text>       store a memory
    memvana recall <query>        search memories (compact index)
    memvana show <id>             full content of one memory
    memvana sessions              list memory sessions
    memvana status                workspace statistics
    memvana hook <event>          Claude Code hook endpoint
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from memvana import __version__
from memvana.graph.html_export import export_html
from memvana.graph.model import KnowledgeGraph
from memvana.graph.query import communities, explain, search, shortest_path
from memvana.memory.hooks import HANDLERS
from memvana.memory.store import MemoryStore
from memvana.pipeline import ingest_sources, rebuild_graph, store_documents
from memvana.tokens import corpus_tokens, estimate_tokens, savings_line
from memvana.workspace import Workspace, find_workspace


def _graph(workspace: Workspace) -> KnowledgeGraph:
    graph = KnowledgeGraph.load(workspace.graph_path)
    if not graph.nodes:
        print("Graph is empty. Run `memvana build .` first.", file=sys.stderr)
    return graph


def _stamp(epoch: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))


def cmd_build(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    workspace = Workspace(root).ensure()
    result = ingest_sources(workspace, [str(root)])
    store_documents(workspace, result.converted)
    graph = rebuild_graph(workspace)
    print(f"Ingested {len(result.converted)} documents "
          f"({len(result.unchanged)} unchanged, {len(result.skipped)} skipped).")
    print(f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
    print(f"Workspace: {workspace.base_dir}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    workspace = find_workspace().ensure()
    result = ingest_sources(workspace, args.files)
    if not result.converted and not result.unchanged:
        print("Nothing ingested (unsupported or unreadable sources).",
              file=sys.stderr)
        return 1
    store_documents(workspace, result.converted)
    graph = rebuild_graph(workspace)
    for doc in result.converted:
        print(f"+ {doc.title} ({doc.kind}) <- {doc.source}")
    for path in result.unchanged:
        print(f"= unchanged {path}")
    for item in result.skipped:
        print(f"~ skipped {item}", file=sys.stderr)
    print(f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    graph = _graph(find_workspace())
    hits = search(graph, " ".join(args.term))
    if not hits:
        print("No matches.")
        return 1
    for hit in hits:
        node = hit.node
        location = f"  ({node.source})" if node.source else ""
        print(f"[{node.type:>8}] {node.label}{location}")
        if node.detail:
            print(f"           {node.detail.splitlines()[0][:100]}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    graph = _graph(find_workspace())
    path = shortest_path(graph, args.start, args.end)
    if path is None:
        print(f"No path found between '{args.start}' and '{args.end}'.")
        return 1
    for node, edge in path:
        if edge is None:
            print(f"{node.label} ({node.type})")
        else:
            marker = "?" if edge.confidence == "inferred" else "-"
            print(f"  --{marker}[{edge.relation}]--> {node.label} ({node.type})")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    workspace = find_workspace()
    graph = _graph(workspace)
    result = explain(graph, " ".join(args.term))
    if result is None:
        print(f"No node matching '{' '.join(args.term)}'.")
        return 1
    node = result.node
    print(f"{node.label}  [{node.type}]")
    if node.source:
        print(f"source: {node.source}")
    if node.detail:
        print(f"detail: {node.detail[:300]}")
    if result.outgoing:
        print("\noutgoing:")
        for edge, other in result.outgoing[:25]:
            suffix = " (inferred)" if edge.confidence == "inferred" else ""
            print(f"  {edge.relation} -> {other.label}{suffix}")
    if result.incoming:
        print("\nincoming:")
        for edge, other in result.incoming[:25]:
            suffix = " (inferred)" if edge.confidence == "inferred" else ""
            print(f"  {other.label} -{edge.relation}->{suffix}")
    _print_related_memories(workspace, node.label)
    return 0


def _print_related_memories(workspace: Workspace, label: str) -> None:
    """Show memories mentioning a graph node — graph and memory in one view."""
    if not workspace.memory_db_path.is_file():
        return
    with MemoryStore(workspace.memory_db_path) as store:
        memories = store.recall(label, limit=5)
    if memories:
        print("\nmemories:")
        for observation in memories:
            print(f"  [{observation.id}] {_stamp(observation.created_at)} "
                  f"{observation.summary}")


def cmd_ask(args: argparse.Namespace) -> int:
    """Unified search: knowledge graph and memory answered together."""
    term = " ".join(args.term)
    workspace = find_workspace()
    lines: list[str] = []

    graph = KnowledgeGraph.load(workspace.graph_path)
    hits = search(graph, term)
    if hits:
        lines.append("knowledge graph:")
        for hit in hits[:8]:
            node = hit.node
            location = f"  ({node.source})" if node.source else ""
            lines.append(f"  [{node.type:>8}] {node.label}{location}")

    if workspace.memory_db_path.is_file():
        with MemoryStore(workspace.memory_db_path) as store:
            memories = store.recall(term, limit=8)
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
        print(f"Nothing in the graph or memory matches '{term}'.")
        return 1
    output = "\n".join(lines)
    print(output)
    print("\n" + savings_line(estimate_tokens(output), corpus_tokens(workspace)))
    return 0


def cmd_html(args: argparse.Namespace) -> int:
    workspace = find_workspace()
    graph = _graph(workspace)
    output = Path(args.output) if args.output else workspace.base_dir / "graph.html"
    export_html(graph, output)
    print(f"Wrote {output}")
    return 0


def cmd_remember(args: argparse.Namespace) -> int:
    workspace = find_workspace().ensure()
    with MemoryStore(workspace.memory_db_path) as store:
        observation = store.remember(
            " ".join(args.text), kind=args.kind, tags=args.tags
        )
    print(f"Remembered [{observation.id}] {observation.summary}")
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    workspace = find_workspace()
    with MemoryStore(workspace.memory_db_path) as store:
        results = store.recall(" ".join(args.query), limit=args.limit)
    if not results:
        print("No memories match.")
        return 1
    for observation in results:
        print(f"[{observation.id}] {_stamp(observation.created_at)} "
              f"({observation.kind}) {observation.summary}")
        if args.full:
            print(observation.content)
            print("-" * 40)
    if not args.full:
        print("\nUse `memvana show <id>` or `--full` for complete content.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    workspace = find_workspace()
    with MemoryStore(workspace.memory_db_path) as store:
        observation = store.get_observation(args.id)
    if observation is None:
        print(f"No memory with id '{args.id}'.")
        return 1
    print(f"id:      {observation.id}")
    print(f"session: {observation.session_id}")
    print(f"time:    {_stamp(observation.created_at)}")
    print(f"kind:    {observation.kind}")
    if observation.tags:
        print(f"tags:    {observation.tags}")
    print(f"\n{observation.content}")
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    workspace = find_workspace()
    with MemoryStore(workspace.memory_db_path) as store:
        rows = store.list_sessions()
    if not rows:
        print("No sessions yet.")
        return 0
    for session_id, started, ended, title, count in rows:
        state = _stamp(ended) if ended else "open"
        print(f"[{session_id}] {_stamp(started)} -> {state}  "
              f"{count} observations  {title}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = find_workspace()
    print(f"Workspace: {workspace.base_dir} "
          f"({'exists' if workspace.exists else 'not initialized'})")
    graph = KnowledgeGraph.load(workspace.graph_path)
    print(f"Graph:     {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    total = corpus_tokens(workspace)
    if total:
        print(f"Corpus:    ~{total:,} tokens ingested "
              f"(queries return a tiny slice of this)")
    if graph.nodes:
        groups = communities(graph)
        largest = sorted(groups.values(), key=len, reverse=True)[:5]
        print(f"Communities: {len(groups)} "
              f"(largest: {', '.join(str(len(g)) for g in largest)})")
    if workspace.memory_db_path.is_file():
        with MemoryStore(workspace.memory_db_path) as store:
            print(f"Memory:    {store.count()} observations")
    else:
        print("Memory:    empty")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    handler = HANDLERS.get(args.event)
    if handler is None:
        print(f"Unknown hook event '{args.event}'. "
              f"Expected one of: {', '.join(HANDLERS)}", file=sys.stderr)
        return 1
    return handler()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memvana",
        description="Universal ingestion -> knowledge graph -> persistent memory.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="ingest a directory and build the graph")
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("ingest", help="ingest files or URLs and update the graph")
    p.add_argument("files", nargs="+", metavar="source")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ask", help="search graph and memory together")
    p.add_argument("term", nargs="+")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("query", help="search the knowledge graph")
    p.add_argument("term", nargs="+")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("path", help="shortest connection between two nodes")
    p.add_argument("start")
    p.add_argument("end")
    p.set_defaults(func=cmd_path)

    p = sub.add_parser("explain", help="describe one node and its connections")
    p.add_argument("term", nargs="+")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("html", help="export interactive HTML graph viewer")
    p.add_argument("-o", "--output", default=None)
    p.set_defaults(func=cmd_html)

    p = sub.add_parser("remember", help="store a memory")
    p.add_argument("text", nargs="+")
    p.add_argument("--kind", default="note")
    p.add_argument("--tags", default="")
    p.set_defaults(func=cmd_remember)

    p = sub.add_parser("recall", help="search memories")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--full", action="store_true")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("show", help="full content of one memory")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("sessions", help="list memory sessions")
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser("status", help="workspace statistics")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("hook", help="Claude Code hook endpoint")
    p.add_argument("event", help="session-start | post-tool | session-end")
    p.set_defaults(func=cmd_hook)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
