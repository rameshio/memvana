"""Graph data model with JSON persistence.

Every edge carries a confidence tag:
  * ``extracted`` - stated explicitly in the source (an import, a heading, a link)
  * ``inferred``  - derived by Memvana (name resolution, co-occurrence)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

EXTRACTED = "extracted"
INFERRED = "inferred"

NODE_TYPES = (
    "document", "section", "module", "class", "function", "concept", "url",
)
RELATIONS = (
    "contains", "links_to", "mentions", "imports", "defines", "calls",
    "inherits", "related_to",
)


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    type: str
    source: str = ""          # originating file path, when known
    detail: str = ""          # short human-readable context (docstring, heading text)


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str
    confidence: str = EXTRACTED


@dataclass
class KnowledgeGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    _edge_keys: set[tuple[str, str, str]] = field(
        default_factory=set, repr=False, compare=False
    )

    def add_node(self, node: Node) -> None:
        """Insert a node; an existing node with detail wins over a bare one."""
        existing = self.nodes.get(node.id)
        if existing is None or (not existing.detail and node.detail):
            self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Insert an edge, deduplicating on (source, target, relation)."""
        key = (edge.source, edge.target, edge.relation)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(edge)

    def neighbors(self, node_id: str) -> list[tuple[Edge, str]]:
        """All edges touching node_id, paired with the far-end node id."""
        result: list[tuple[Edge, str]] = []
        for edge in self.edges:
            if edge.source == node_id:
                result.append((edge, edge.target))
            elif edge.target == node_id:
                result.append((edge, edge.source))
        return result

    def degree(self, node_id: str) -> int:
        return len(self.neighbors(node_id))

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "nodes": [asdict(node) for node in self.nodes.values()],
            "edges": [asdict(edge) for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "KnowledgeGraph":
        graph = cls()
        for raw in payload.get("nodes", []):
            graph.add_node(Node(**raw))
        for raw in payload.get("edges", []):
            graph.add_edge(Edge(**raw))
        return graph

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "KnowledgeGraph":
        if not path.is_file():
            return cls()
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
