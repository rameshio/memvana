"""Universal converter: any file -> Markdown.

Text-like files (code, markdown, plain text) are read directly. Rich formats
(PDF, Office, HTML, images, audio, ...) are delegated to MarkItDown, which is
an optional heavy dependency loaded lazily on first use.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# Extensions we read directly as UTF-8 text, mapped to a document kind.
CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".sh": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".r": "r",
    ".lua": "lua",
}
TEXT_EXTENSIONS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".rst": "text",
    ".toml": "config",
    ".yaml": "config",
    ".yml": "config",
    ".ini": "config",
    ".cfg": "config",
    ".env.example": "config",
}
# Formats MarkItDown can convert. Anything else is skipped with a warning.
MARKITDOWN_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".json", ".xml",
    ".html", ".htm", ".epub", ".zip", ".msg", ".wav", ".mp3", ".m4a",
    ".jpg", ".jpeg", ".png", ".ipynb",
}
SKIP_DIRECTORIES = {
    ".git", ".memvana", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".pytest_cache", ".idea", ".vscode", "graphify-out",
}
MAX_TEXT_FILE_BYTES = 2_000_000


@dataclass(frozen=True)
class IngestedDocument:
    """One source file converted to Markdown."""

    source: str          # original path, as given
    doc_id: str          # stable short hash of the source path
    kind: str            # markdown | text | config | python | pdf | ...
    title: str
    markdown: str

    @property
    def stored_name(self) -> str:
        """Filename used inside .memvana/documents/."""
        return f"{self.doc_id}.md"


def doc_id_for(source: Path) -> str:
    """Stable document id derived from the absolute source path."""
    return hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:12]


def content_hash(source: Path) -> str:
    """SHA-1 of the file bytes, used to skip unchanged files on rebuild."""
    return hashlib.sha1(source.read_bytes()).hexdigest()


def _title_for(source: Path, markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return source.stem


def _convert_with_markitdown(source: str) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as error:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "MarkItDown is required for rich formats. "
            "Install it with: pip install 'memvana[all]'"
        ) from error
    result = MarkItDown(enable_plugins=False).convert(source)
    return result.text_content or ""


def ingest_url(url: str) -> IngestedDocument | None:
    """Fetch a web page (or YouTube URL, etc.) and convert it to Markdown."""
    try:
        markdown = _convert_with_markitdown(url)
    except Exception:
        return None
    if not markdown.strip():
        return None
    doc_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    title = next(
        (line[2:].strip() for line in markdown.splitlines()
         if line.strip().startswith("# ")),
        url,
    )
    return IngestedDocument(
        source=url, doc_id=doc_id, kind="url", title=title, markdown=markdown
    )


def ingest_path_verbose(source: Path) -> tuple[IngestedDocument | None, str]:
    """Convert a single file; on failure returns (None, human-readable reason)
    instead of raising, so directory scans keep going."""
    suffix = source.suffix.lower()
    if suffix in CODE_EXTENSIONS or suffix in TEXT_EXTENSIONS:
        if source.stat().st_size > MAX_TEXT_FILE_BYTES:
            return None, f"file larger than {MAX_TEXT_FILE_BYTES:,} bytes"
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            return None, f"unreadable: {error}"
        kind = CODE_EXTENSIONS.get(suffix) or TEXT_EXTENSIONS[suffix]
        if kind in ("markdown", "text", "config"):
            markdown = text
        else:
            markdown = f"# {source.name}\n\n```{kind}\n{text}\n```\n"
        return IngestedDocument(
            source=str(source),
            doc_id=doc_id_for(source),
            kind=kind,
            title=_title_for(source, markdown),
            markdown=markdown,
        ), ""

    if suffix in MARKITDOWN_EXTENSIONS:
        try:
            markdown = _convert_with_markitdown(str(source))
        except Exception as error:
            reason = f"conversion failed: {type(error).__name__}: {error}"
            return None, reason[:200]
        if not markdown.strip():
            return None, "conversion produced no text"
        return IngestedDocument(
            source=str(source),
            doc_id=doc_id_for(source),
            kind=suffix.lstrip("."),
            title=_title_for(source, markdown),
            markdown=markdown,
        ), ""

    return None, f"unsupported file type '{suffix or source.name}'"


def ingest_path(source: Path) -> IngestedDocument | None:
    """Convert a single file, or None on failure (see ingest_path_verbose)."""
    return ingest_path_verbose(source)[0]


def document_from_text(
    title: str, content: str, kind: str = "text", source: str = "chat"
) -> IngestedDocument:
    """Build a document from content already in hand (e.g. a file uploaded
    into a chat, which never touches the local disk)."""
    doc_id = hashlib.sha1(
        f"{source}:{title}".encode("utf-8")
    ).hexdigest()[:12]
    markdown = content
    if not content.lstrip().startswith("#"):
        markdown = f"# {title}\n\n{content}"
    return IngestedDocument(
        source=source, doc_id=doc_id, kind=kind, title=title, markdown=markdown
    )


def scan_directory(root: Path) -> list[Path]:
    """List ingestible files under root, skipping vendored/hidden directories."""
    supported = (
        set(CODE_EXTENSIONS) | set(TEXT_EXTENSIONS) | MARKITDOWN_EXTENSIONS
    )
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if path.suffix.lower() in supported:
            found.append(path)
    return found
