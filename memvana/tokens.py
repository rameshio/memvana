"""Token accounting: show how much context a query returned vs. what
reading the raw sources would have cost.

Estimates use the ~4 characters/token heuristic common to modern LLM
tokenizers. Close enough to make savings visible; not billing-grade.
"""

from __future__ import annotations

from memvana.workspace import Workspace

CHARS_PER_TOKEN = 4
BAR_WIDTH = 20


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def corpus_tokens(workspace: Workspace) -> int:
    """Estimated tokens of the entire ingested corpus."""
    if not workspace.documents_dir.is_dir():
        return 0
    total_bytes = sum(
        path.stat().st_size for path in workspace.documents_dir.glob("*.md")
    )
    return total_bytes // CHARS_PER_TOKEN


def savings_line(returned_tokens: int, total_tokens: int) -> str:
    """One-line meter: tokens returned vs. reading the whole corpus.

    Example:
        tokens: ~120 returned instead of ~48,300 [#-------------------] 99.8% saved
    """
    if total_tokens <= 0 or returned_tokens >= total_tokens:
        return f"tokens: ~{returned_tokens:,} returned"
    used_ratio = returned_tokens / total_tokens
    filled = max(1, round(used_ratio * BAR_WIDTH))
    bar = "#" * filled + "-" * (BAR_WIDTH - filled)
    saved_pct = (1 - used_ratio) * 100
    return (
        f"tokens: ~{returned_tokens:,} returned instead of ~{total_tokens:,} "
        f"[{bar}] {saved_pct:.1f}% saved"
    )
