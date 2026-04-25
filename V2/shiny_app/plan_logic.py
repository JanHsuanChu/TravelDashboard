# plan_logic.py
# Build plan payload and Ollama prompts (browser-only; no HTTP API).

from __future__ import annotations

from typing import Any


def build_trip_context(inputs: dict[str, Any]) -> dict[str, Any]:
    """Snapshot of non-persisted trip UI (for LLM and display)."""
    mode = inputs.get("when_mode")
    when: dict[str, Any] = {"mode": mode}
    if mode == "season":
        when["season"] = inputs.get("when_season")
    elif mode == "month":
        when["month"] = inputs.get("when_month")

    return {
        "destination": {
            "country": inputs.get("dest_country"),
            "country_iso2": inputs.get("dest_country_iso2"),
            "city": inputs.get("dest_city"),
        },
        "compare": [
            {
                "country": inputs.get("cmp1_country"),
                "country_iso2": inputs.get("cmp1_country_iso2"),
                "city": inputs.get("cmp1_city"),
            },
            {
                "country": inputs.get("cmp2_country"),
                "country_iso2": inputs.get("cmp2_country_iso2"),
                "city": inputs.get("cmp2_city"),
            },
        ],
        "when": when,
        "food": {
            "like_tags": inputs.get("like_tags") or [],
            "dislike_tags": inputs.get("dislike_tags") or [],
            "dietary_tags": inputs.get("dietary_tags") or [],
            "food_like_text": inputs.get("food_like_text") or "",
            "food_dislike_text": inputs.get("food_dislike_text") or "",
            "dietary_restrictions": inputs.get("dietary_restrictions_text") or "",
        },
    }


SYSTEM_JSON_INSTRUCTION = """
You assist the Travel Dashboard. Return ONLY one JSON object (no markdown fences):
{
  "dining": {
    "dishes": [{"title": "...", "note": "1 short sentence", "badge": "$ | $$ | $$$"}],
    "places": [{"title": "...", "note": "1 short sentence", "badge": "..."}]
  },
  "essential": {
    "travel_advisory": "≤2 short sentences (server may replace travel_advisory with live U.S. State Dept table + summary after Generate)",
    "weather": "1–2 short sentences (see Essential — weather below)"
  },
  "friendliness": {
    "primary": {"score": 0-100, "label": "short"},
    "comparisons": [{"label": "country or city", "score": 0-100}]
  }
}
Placeholder text is OK if live data unknown; keep everything brief. Scores are illustrative (UI may override).

Essential — weather (strict on essential.weather):
- **1–2 sentences only**, slightly shorter than a paragraph: typical conditions that help travelers **pack and plan** (layers, rain/heat/snow expectations). Illustrative climatology for the destination — **not** a live forecast.
- **Mention the trip timing in the prose:** if `trip_and_food.when.mode` is `"season"`, name that **season** explicitly (e.g. winter / spring / summer / fall or Northern summer); if `"month"`, name that **calendar month** (e.g. "In **March**, …"). Tie conditions to that season or month so the reader sees which window you mean.
- **Geography:** If `trip_and_food.destination.city` is empty or missing, summarize **country-level** climate for that country. If a **city** is present (e.g. Tokyo), include **both** country context and **city-relevant** notes (coastal vs inland, urban heat, rainy season timing) in the same 1–2 sentences. Do **not** leave `essential.weather` blank or whitespace-only.

Dining — dietary (strict on dining.dishes):
- dietary_tags + dietary_restrictions override generic likes (e.g. no seafood if vegetarian).
- Vegetarian / vegan / halal / kosher / gluten-free: only compliant dishes when those tags apply.
"""

# Agent 2 (recommendation): dining must use Agent 1 retrieval from Google Places + user preferences.
AGENT2_DINING_GROUNDING = """
Agent 1 supplied real Google Places venues (preference-ranked). You are Agent 2.

"dining.places": ONLY names from agent1_restaurants; "title" = exact "name". Up to 5 places, ≥3 if list has 3+.
"dining.dishes": 4–6 dishes, destination + preferences; respect dietary_tags/restrictions; meat-heavy venues → offer veg-safe options.
"dishes"[].badge: exactly "$", "$$", or "$$$" only.
"places"[].badge: if rag_match_score given, use percent (e.g. 0.89 → "89% match"); never raw decimals; no "$" here.
"note": one tight sentence; places may use address or a provided review line only (no invented ratings).

If agent1_restaurants is empty, generic dining only (no live-place claims).
"""


def _trim_agent1_for_llm(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Smaller user message: fewer tokens to the plan model."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        es = (r.get("editorial_summary") or "")[:220]
        snippets = r.get("review_snippets") or []
        if isinstance(snippets, list):
            sn = [str(s)[:140] for s in snippets[:2] if s]
        else:
            sn = []
        out.append(
            {
                "name": r.get("name"),
                "formatted_address": (r.get("formatted_address") or "")[:180],
                "editorial_summary": es,
                "review_snippets": sn,
                "rag_match_score": r.get("rag_match_score"),
            }
        )
    return out


def user_prompt_from_context(ctx: dict[str, Any], agent1_restaurants: list[dict[str, Any]] | None = None) -> str:
    import json

    raw = agent1_restaurants or []
    payload: dict[str, Any] = {
        "trip_and_food": ctx,
        "agent1_restaurants": _trim_agent1_for_llm(raw) if raw else [],
    }
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        "Fill the JSON schema from the system message using this data only.\n"
        "trip_and_food = destination, timing, food prefs. agent1_restaurants = ranked venues (use names exactly).\n"
        "essential.weather: non-empty string; if destination.city is absent/empty use country-only climate; "
        "if city is set, combine country + city-relevant conditions in 1–2 sentences.\n\n"
        + compact
    )
