"""Build a knowledge graph from ingested documents.

Two deterministic extractors, no LLM required:
  * Markdown structure: headings, links, [[wiki-links]], **bold concepts**
  * Python code: modules, classes, functions, imports, calls, inheritance (via ast)

Cross-file call/import resolution by name is tagged ``inferred``; everything
stated directly in the source is tagged ``extracted``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from memvana.graph.model import EXTRACTED, INFERRED, Edge, KnowledgeGraph, Node
from memvana.ingest.converter import IngestedDocument

JS_KINDS = {"javascript", "typescript"}
JS_IMPORT_PATTERN = re.compile(
    r"""(?:import\s+(?:[\w{},*\s]+\s+from\s+)?|require\(\s*)['"]([^'"]+)['"]"""
)
JS_FUNCTION_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)
JS_ARROW_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=[^;\n]*=>", re.MULTILINE
)
JS_CLASS_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+([\w.]+))?",
    re.MULTILINE,
)

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
BOLD_CONCEPT_PATTERN = re.compile(r"\*\*([A-Za-z][^*]{2,60})\*\*")
CODE_FENCE_PATTERN = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


def build_graph(documents: list[IngestedDocument]) -> KnowledgeGraph:
    """Build a fresh graph from all documents."""
    graph = KnowledgeGraph()
    python_sources: list[tuple[IngestedDocument, str]] = []

    for doc in documents:
        doc_node_id = f"doc:{doc.doc_id}"
        graph.add_node(
            Node(doc_node_id, doc.title, "document", doc.source, kind_detail(doc))
        )
        if doc.kind == "python":
            code = _extract_fenced_code(doc.markdown) or doc.markdown
            python_sources.append((doc, code))
        elif doc.kind in JS_KINDS:
            code = _extract_fenced_code(doc.markdown) or doc.markdown
            _extract_js_entities(graph, doc, code)
        else:
            _extract_markdown_structure(graph, doc, doc_node_id)

    for doc, code in python_sources:
        _extract_python_entities(graph, doc, code)
    _resolve_cross_file_calls(graph)
    _link_imports_to_modules(graph)
    return graph


def kind_detail(doc: IngestedDocument) -> str:
    return f"{doc.kind} document"


def _extract_fenced_code(markdown: str) -> str | None:
    match = CODE_FENCE_PATTERN.search(markdown)
    return match.group(2) if match else None


def _extract_markdown_structure(
    graph: KnowledgeGraph, doc: IngestedDocument, doc_node_id: str
) -> None:
    section_ids_in_doc: list[str] = []

    for match in HEADING_PATTERN.finditer(doc.markdown):
        heading = match.group(2).strip()
        section_id = f"sec:{doc.doc_id}:{_slug(heading)}"
        graph.add_node(Node(section_id, heading, "section", doc.source))
        graph.add_edge(Edge(doc_node_id, section_id, "contains", EXTRACTED))
        section_ids_in_doc.append(section_id)

    for match in MARKDOWN_LINK_PATTERN.finditer(doc.markdown):
        text, target = match.group(1).strip(), match.group(2).strip()
        if target.startswith(("http://", "https://")):
            target_id = f"url:{_slug(target)}"
            graph.add_node(Node(target_id, target, "url", detail=text))
        else:
            target_id = f"concept:{_slug(text)}"
            graph.add_node(Node(target_id, text, "concept"))
        graph.add_edge(Edge(doc_node_id, target_id, "links_to", EXTRACTED))

    concept_ids: list[str] = []
    for pattern in (WIKI_LINK_PATTERN, BOLD_CONCEPT_PATTERN):
        for match in pattern.finditer(doc.markdown):
            concept = match.group(1).strip()
            concept_id = f"concept:{_slug(concept)}"
            graph.add_node(Node(concept_id, concept, "concept"))
            graph.add_edge(Edge(doc_node_id, concept_id, "mentions", EXTRACTED))
            concept_ids.append(concept_id)

    # Concepts mentioned in the same document are likely related.
    unique_concepts = sorted(set(concept_ids))
    for first, second in zip(unique_concepts, unique_concepts[1:]):
        graph.add_edge(Edge(first, second, "related_to", INFERRED))


def _extract_python_entities(
    graph: KnowledgeGraph, doc: IngestedDocument, code: str
) -> None:
    module_name = Path(doc.source).stem
    module_id = f"mod:{doc.doc_id}"
    graph.add_node(Node(module_id, module_name, "module", doc.source))
    graph.add_edge(Edge(f"doc:{doc.doc_id}", module_id, "contains", EXTRACTED))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _add_import(graph, module_id, alias.name, doc.source)
        elif isinstance(node, ast.ImportFrom) and node.module:
            _add_import(graph, module_id, node.module, doc.source)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_id = f"class:{doc.doc_id}:{node.name}"
            graph.add_node(
                Node(class_id, node.name, "class", doc.source,
                     ast.get_docstring(node) or "")
            )
            graph.add_edge(Edge(module_id, class_id, "defines", EXTRACTED))
            for base in node.bases:
                base_name = _name_of(base)
                if base_name:
                    base_id = f"concept:{_slug(base_name)}"
                    graph.add_node(Node(base_id, base_name, "concept"))
                    graph.add_edge(Edge(class_id, base_id, "inherits", EXTRACTED))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _add_function(graph, doc, class_id, item)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _add_function(graph, doc, module_id, node)


def _extract_js_entities(
    graph: KnowledgeGraph, doc: IngestedDocument, code: str
) -> None:
    """Lightweight regex extraction for JavaScript/TypeScript.

    Not a real parser: catches top-level functions, arrow-function
    assignments, classes (with extends), and import/require targets.
    """
    module_name = Path(doc.source).stem
    module_id = f"mod:{doc.doc_id}"
    graph.add_node(Node(module_id, module_name, "module", doc.source))
    graph.add_edge(Edge(f"doc:{doc.doc_id}", module_id, "contains", EXTRACTED))

    for match in JS_IMPORT_PATTERN.finditer(code):
        imported = match.group(1).strip().lstrip("./")
        if imported:
            _add_import(graph, module_id, imported, doc.source)

    for pattern in (JS_FUNCTION_PATTERN, JS_ARROW_PATTERN):
        for match in pattern.finditer(code):
            function_id = f"func:{doc.doc_id}:{match.group(1)}"
            graph.add_node(
                Node(function_id, match.group(1), "function", doc.source)
            )
            graph.add_edge(Edge(module_id, function_id, "defines", EXTRACTED))

    for match in JS_CLASS_PATTERN.finditer(code):
        class_id = f"class:{doc.doc_id}:{match.group(1)}"
        graph.add_node(Node(class_id, match.group(1), "class", doc.source))
        graph.add_edge(Edge(module_id, class_id, "defines", EXTRACTED))
        if match.group(2):
            base_id = f"concept:{_slug(match.group(2))}"
            graph.add_node(Node(base_id, match.group(2), "concept"))
            graph.add_edge(Edge(class_id, base_id, "inherits", EXTRACTED))


def _add_import(
    graph: KnowledgeGraph, module_id: str, imported: str, source: str
) -> None:
    imported_id = f"import:{imported}"
    graph.add_node(Node(imported_id, imported, "module", detail="imported module"))
    graph.add_edge(Edge(module_id, imported_id, "imports", EXTRACTED))


def _add_function(
    graph: KnowledgeGraph,
    doc: IngestedDocument,
    parent_id: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> None:
    function_id = f"func:{doc.doc_id}:{node.name}"
    graph.add_node(
        Node(function_id, node.name, "function", doc.source,
             ast.get_docstring(node) or "")
    )
    graph.add_edge(Edge(parent_id, function_id, "defines", EXTRACTED))
    for called in _called_names(node):
        graph.add_edge(
            Edge(function_id, f"callname:{called}", "calls", EXTRACTED)
        )


def _called_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func)
            if name:
                names.append(name.split(".")[-1])
    return names


def _name_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _resolve_cross_file_calls(graph: KnowledgeGraph) -> None:
    """Rewrite call placeholders to real function nodes where names match.

    A match by bare name across files is a guess, so those edges are inferred.
    Unresolved placeholders are dropped to keep the graph clean.
    """
    functions_by_name: dict[str, list[str]] = {}
    for node in graph.nodes.values():
        if node.type == "function":
            functions_by_name.setdefault(node.label, []).append(node.id)

    kept: list[Edge] = []
    keys: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        if not edge.target.startswith("callname:"):
            resolved = edge
        else:
            called_name = edge.target.removeprefix("callname:")
            targets = functions_by_name.get(called_name, [])
            if not targets:
                continue
            resolved = Edge(edge.source, targets[0], "calls", INFERRED)
        key = (resolved.source, resolved.target, resolved.relation)
        if key not in keys:
            keys.add(key)
            kept.append(resolved)

    graph.edges = kept
    graph._edge_keys = keys


def _link_imports_to_modules(graph: KnowledgeGraph) -> None:
    """Connect ``import foo.bar`` placeholders to real module nodes.

    Matching the trailing segment of an import to a module filename is a
    heuristic, so these edges are inferred. Placeholder nodes left with no
    remaining edges are dropped.
    """
    modules_by_name = {
        node.label: node.id
        for node in graph.nodes.values()
        if node.type == "module" and node.id.startswith("mod:")
    }
    for edge in list(graph.edges):
        if edge.relation != "imports" or not edge.target.startswith("import:"):
            continue
        imported = edge.target.removeprefix("import:")
        # Trailing segment of either "pkg.sub.module" or "path/to/module".
        tail = imported.split("/")[-1].split(".")[-1]
        target_module = modules_by_name.get(tail)
        if target_module and target_module != edge.source:
            graph.add_edge(Edge(edge.source, target_module, "imports", INFERRED))

    referenced = {edge.source for edge in graph.edges} | {
        edge.target for edge in graph.edges
    }
    orphaned = [
        node_id
        for node_id, node in graph.nodes.items()
        if node_id.startswith("import:") and node_id not in referenced
    ]
    for node_id in orphaned:
        del graph.nodes[node_id]
