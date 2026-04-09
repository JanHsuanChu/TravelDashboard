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
            "city": inputs.get("dest_city"),
        },
        "compare": [
            {
                "country": inputs.get("cmp1_country"),
                "city": inputs.get("cmp1_city"),
            },
            {
                "country": inputs.get("cmp2_country"),
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
You are assisting with the Travel Dashboard described in the architecture context above.
Return ONLY a single JSON object (no markdown fences) with this shape:
{
  "dining": {
    "dishes": [{"title": "...", "note": "...", "badge": "..."}],
    "places": [{"title": "...", "note": "...", "badge": "..."}]
  },
  "essential": {
    "travel_advisory": "paragraph",
    "weather": "paragraph",
    "news": "paragraph"
  },
  "friendliness": {
    "primary": {"score": 0-100, "label": "short"},
    "comparisons": [{"label": "country or city", "score": 0-100}]
  }
}
Use concise placeholder content if you lack real-time data. Scores are illustrative.
"""


def user_prompt_from_context(ctx: dict[str, Any]) -> str:
    import json

    return (
        "Using the following trip and food context, fill the JSON structure.\n\n"
        + json.dumps(ctx, indent=2)
    )
