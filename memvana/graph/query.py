"""Query engine: search, shortest path, explain, and community detection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from memvana.graph.model import Edge, KnowledgeGraph, Node

MAX_SEARCH_RESULTS = 20
COMMUNITY_PASSES = 5


@dataclass(frozen=True)
class SearchHit:
    node: Node
    score: float


def search(graph: KnowledgeGraph, term: str) -> list[SearchHit]:
    """Rank nodes by label match quality, breaking ties by connectedness."""
    needle = term.lower().strip()
    if not needle:
        return []
    hits: list[SearchHit] = []
    for node in graph.nodes.values():
        label = node.label.lower()
        if needle == label:
            base = 100.0
        elif label.startswith(needle):
            base = 60.0
        elif needle in label:
            base = 40.0
        elif needle in node.detail.lower():
            base = 20.0
        else:
            continue
        hits.append(SearchHit(node, base + min(graph.degree(node.id), 20)))
    hits.sort(key=lambda hit: (-hit.score, hit.node.label))
    return hits[:MAX_SEARCH_RESULTS]


def resolve_node(graph: KnowledgeGraph, term: str) -> Node | None:
    """Best-match a user-supplied name or id to a node."""
    if term in graph.nodes:
        return graph.nodes[term]
    hits = search(graph, term)
    if not hits and "." in term:
        # "cli.py" should still find the module named "cli".
        hits = search(graph, term.rsplit(".", 1)[0])
    return hits[0].node if hits else None


def shortest_path(
    graph: KnowledgeGraph, start_term: str, end_term: str
) -> list[tuple[Node, Edge | None]] | None:
    """Undirected BFS between two nodes.

    Returns the path as (node, edge-that-led-here) pairs, or None when either
    endpoint is missing or no path exists.
    """
    start = resolve_node(graph, start_term)
    end = resolve_node(graph, end_term)
    if start is None or end is None:
        return None

    adjacency: dict[str, list[tuple[str, Edge]]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source, []).append((edge.target, edge))
        adjacency.setdefault(edge.target, []).append((edge.source, edge))

    came_from: dict[str, tuple[str, Edge]] = {}
    queue: deque[str] = deque([start.id])
    visited = {start.id}
    while queue:
        current = queue.popleft()
        if current == end.id:
            break
        for neighbor, edge in adjacency.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                came_from[neighbor] = (current, edge)
                queue.append(neighbor)
    if end.id not in visited:
        return None

    path: list[tuple[Node, Edge | None]] = []
    cursor = end.id
    while cursor != start.id:
        previous, edge = came_from[cursor]
        path.append((graph.nodes[cursor], edge))
        cursor = previous
    path.append((start, None))
    path.reverse()
    return path


@dataclass(frozen=True)
class Explanation:
    node: Node
    outgoing: list[tuple[Edge, Node]]
    incoming: list[tuple[Edge, Node]]


def explain(graph: KnowledgeGraph, term: str) -> Explanation | None:
    """Summarize one node: what it points at and what points at it."""
    node = resolve_node(graph, term)
    if node is None:
        return None
    outgoing = [
        (edge, graph.nodes[edge.target])
        for edge in graph.edges
        if edge.source == node.id and edge.target in graph.nodes
    ]
    incoming = [
        (edge, graph.nodes[edge.source])
        for edge in graph.edges
        if edge.target == node.id and edge.source in graph.nodes
    ]
    return Explanation(node, outgoing, incoming)


def communities(graph: KnowledgeGraph) -> dict[str, list[str]]:
    """Group nodes into communities via label propagation.

    Deterministic: nodes are visited in sorted order for a fixed number of
    passes, and ties go to the smallest community label.
    """
    labels = {node_id: node_id for node_id in graph.nodes}
    adjacency: dict[str, list[str]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source, []).append(edge.target)
        adjacency.setdefault(edge.target, []).append(edge.source)

    for _ in range(COMMUNITY_PASSES):
        changed = False
        for node_id in sorted(graph.nodes):
            neighbor_labels = [
                labels[n] for n in adjacency.get(node_id, []) if n in labels
            ]
            if not neighbor_labels:
                continue
            counts: dict[str, int] = {}
            for label in neighbor_labels:
                counts[label] = counts.get(label, 0) + 1
            best = min(
                counts, key=lambda label: (-counts[label], label)
            )
            if best != labels[node_id]:
                labels[node_id] = best
                changed = True
        if not changed:
            break

    grouped: dict[str, list[str]] = {}
    for node_id, label in labels.items():
        grouped.setdefault(label, []).append(node_id)
    return grouped
