# context.py
# Load architecture.md for Ollama system context (path relative to TravelDashboard root).

from __future__ import annotations

from pathlib import Path

_MAX_CHARS = 24_000  # keep prompt bounded; architecture file is small today


def travel_dashboard_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_architecture_markdown() -> str:
    path = travel_dashboard_root() / "docs" / "architecture.md"
    if not path.exists():
        return "(architecture.md not found)"
    text = path.read_text(encoding="utf-8")
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n\n[truncated]"
    return text
