"""Pipeline: ingest sources into the workspace and (re)build the graph.

Stored layout: each ingested document lives at
.memvana/documents/<doc_id>.md, with its metadata (including a content hash)
recorded in .memvana/manifest.json. Unchanged files are skipped on rebuild,
which matters when conversion involves heavy formats like PDF or Office.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from memvana.graph.builder import build_graph
from memvana.graph.model import KnowledgeGraph
from memvana.ingest.converter import (
    IngestedDocument,
    content_hash,
    doc_id_for,
    ingest_path_verbose,
    ingest_url,
    scan_directory,
)
from memvana.workspace import Workspace

MANIFEST_NAME = "manifest.json"


@dataclass
class IngestResult:
    converted: list[IngestedDocument] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


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
        source_path = Path(doc.source)
        manifest[doc.doc_id] = {
            "source": doc.source,
            "kind": doc.kind,
            "title": doc.title,
            "sha1": content_hash(source_path) if source_path.is_file() else "",
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


def _is_unchanged(
    workspace: Workspace, manifest: dict[str, dict], path: Path
) -> bool:
    entry = manifest.get(doc_id_for(path))
    if entry is None or not entry.get("sha1"):
        return False
    stored = workspace.documents_dir / f"{doc_id_for(path)}.md"
    if not stored.is_file():
        return False
    try:
        return content_hash(path) == entry["sha1"]
    except OSError:
        return False


def ingest_sources(workspace: Workspace, sources: list[str]) -> IngestResult:
    """Ingest files, directories, and URLs, skipping unchanged files."""
    manifest = _load_manifest(workspace)
    result = IngestResult()

    def _walk(items: list[str]) -> None:
        for item in items:
            if item.startswith(("http://", "https://")):
                document = ingest_url(item)
                if document is None:
                    result.skipped.append(
                        f"{item} — URL fetch or conversion failed"
                    )
                else:
                    result.converted.append(document)
                continue
            path = Path(item)
            if path.is_dir():
                _walk([str(p) for p in scan_directory(path)])
                continue
            if not path.is_file():
                result.skipped.append(
                    f"{item} — not found on this machine's disk"
                )
                continue
            if _is_unchanged(workspace, manifest, path):
                result.unchanged.append(path)
                continue
            document, reason = ingest_path_verbose(path)
            if document is None:
                result.skipped.append(f"{item} — {reason}")
            else:
                result.converted.append(document)

    _walk(sources)
    return result


def rebuild_graph(workspace: Workspace) -> KnowledgeGraph:
    """Rebuild the whole graph from stored documents and save it."""
    graph = build_graph(load_stored_documents(workspace))
    graph.save(workspace.graph_path)
    return graph
