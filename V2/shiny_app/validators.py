# validators.py
# Word limits and when-mode checks for Travel Dashboard Shiny app.

from __future__ import annotations

MAX_WORDS_FOOD_TEXT = 50


def word_count(text: str) -> int:
    if not text or not text.strip():
        return 0
    return len(text.split())


def valid_email_shape(email: str) -> bool:
    """Minimal check: non-empty local and domain around a single @."""
    s = (email or "").strip()
    if "@" not in s:
        return False
    parts = s.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts[0], parts[1]
    return bool(local.strip()) and bool(domain.strip()) and "." in domain


def validate_food_text(text: str, label: str) -> str | None:
    """Return error message if invalid, else None."""
    n = word_count(text)
    if n > MAX_WORDS_FOOD_TEXT:
        return f"{label} must be at most {MAX_WORDS_FOOD_TEXT} words (currently {n})."
    return None


def validate_when_mode(when_mode: str, when_season: str | None, when_month: str | None) -> str | None:
    if when_mode == "season":
        if not when_season:
            return "Select a season, or switch to Month."
        return None
    if when_mode == "month":
        if not when_month:
            return "Select a month, or switch to Season."
        return None
    return "Choose whether you are planning by season or month."
