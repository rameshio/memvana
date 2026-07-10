"""Pipeline: ingest sources into the workspace and (re)build the graph.

Stored layout: each ingested document lives at
.memvana/documents/<doc_id>.md, with its metadata recorded in
.memvana/manifest.json so the graph can be rebuilt without the originals.
"""

from __future__ import annotations

import json
from pathlib import Path

from memvana.graph.builder import build_graph
from memvana.graph.model import KnowledgeGraph
from memvana.ingest.converter import IngestedDocument, ingest_path, scan_directory
from memvana.workspace import Workspace

MANIFEST_NAME = "manifest.json"


def _manifest_path(workspace: Workspace) -> Path:
    return workspace.base_dir / MANIFEST_NAME


def _load_manifest(workspace: Workspace) -> dict[str, dict]:
    path = _manifest_path(workspace)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(workspace: Workspace, manifest: dict[str, dict]) -> None:
    _manifest_path(workspace).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def store_documents(
    workspace: Workspace, documents: list[IngestedDocument]
) -> None:
    workspace.ensure()
    manifest = _load_manifest(workspace)
    for doc in documents:
        (workspace.documents_dir / doc.stored_name).write_text(
            doc.markdown, encoding="utf-8"
        )
        manifest[doc.doc_id] = {
            "source": doc.source,
            "kind": doc.kind,
            "title": doc.title,
        }
    _save_manifest(workspace, manifest)


def load_stored_documents(workspace: Workspace) -> list[IngestedDocument]:
    manifest = _load_manifest(workspace)
    documents: list[IngestedDocument] = []
    for doc_id, meta in manifest.items():
        stored = workspace.documents_dir / f"{doc_id}.md"
        if not stored.is_file():
            continue
        documents.append(
            IngestedDocument(
                source=meta["source"],
                doc_id=doc_id,
                kind=meta["kind"],
                title=meta["title"],
                markdown=stored.read_text(encoding="utf-8"),
            )
        )
    return documents


def ingest_files(
    workspace: Workspace, paths: list[Path]
) -> tuple[list[IngestedDocument], list[Path]]:
    """Ingest files; returns (converted documents, skipped paths)."""
    converted: list[IngestedDocument] = []
    skipped: list[Path] = []
    for path in paths:
        if path.is_dir():
            directory_docs, directory_skipped = ingest_files(
                workspace, scan_directory(path)
            )
            converted.extend(directory_docs)
            skipped.extend(directory_skipped)
            continue
        document = ingest_path(path) if path.is_file() else None
        if document is None:
            skipped.append(path)
        else:
            converted.append(document)
    return converted, skipped


def rebuild_graph(workspace: Workspace) -> KnowledgeGraph:
    """Rebuild the whole graph from stored documents and save it."""
    graph = build_graph(load_stored_documents(workspace))
    graph.save(workspace.graph_path)
    return graph
