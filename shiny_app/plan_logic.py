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
    "dishes": [{"title": "...", "note": "...", "badge": "exactly one of: $ | $$ | $$$ (price tier for that dish)"}],
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

Dining — dietary compliance (always apply to "dining.dishes", even if other food fields conflict):
- trip_and_food.food.dietary_tags and trip_and_food.food.dietary_restrictions are strict requirements, not loose hints. They override generic "likes" (e.g. do not suggest seafood if the traveler is vegetarian).
- Vegetarian: no meat, poultry, fish, or shellfish; avoid dishes where those are central (broth, lard, fish sauce, etc. when relevant).
- Vegan: only plant-based dishes; no meat, fish, dairy, eggs, or honey.
- Halal / kosher / gluten-free: only recommend dishes that plausibly comply when those tags are present.
"""

# Agent 2 (recommendation): dining must use Agent 1 retrieval from Google Places + user preferences.
AGENT2_DINING_GROUNDING = """
Agent pipeline: Agent 1 already retrieved real restaurants (Google Places) ranked for the user's food preferences.
You are Agent 2 (recommendation engine).

Rules for "dining":
- "places": use ONLY venues from the provided agent1_restaurants list. Each item's "name" must appear as place "title" (exact string) for exactly one entry per chosen venue. Prefer up to 5 places; at least 3 when the list has 3+.
- "dishes": recommend specific dishes or meal styles that fit the destination cuisine AND the user's food preferences, and map them to the vibe of those venues where possible (e.g. street food vs fine dining). Include 4–8 dishes total. Every dish must satisfy trip_and_food.food.dietary_tags and dietary_restrictions; if a venue is meat-heavy, suggest clearly vegetarian/vegan-safe options (sides, modified classics, or plant-forward local dishes) rather than defaulting to meat mains.
- "dishes"[]."badge": REQUIRED — exactly one token: "$" (budget / street / simple), "$$" (mid-range / everyday sit-down), or "$$$" (upscale / fine-dining–style). Infer from typical local cost and setting for that dish; no other text, no "N/A", no percent match (dishes have no rag_match_score).
- "places"[]."badge": when rag_match_score is present, echo as percent match (e.g. "89% match" from 0.89 — never "0.89 match"). The app also shows Google's price tier ($/$$/$$$) next to the match when available. Never "N/A". Omit dollar tiers from this field (price comes from Google).
- "note": one or two sentences; for places, cite address or a review snippet when provided (do not invent ratings).

If agent1_restaurants is empty or missing, fall back to generic dining suggestions without claiming live place data.
"""


def user_prompt_from_context(ctx: dict[str, Any], agent1_restaurants: list[dict[str, Any]] | None = None) -> str:
    import json

    payload: dict[str, Any] = {"trip_and_food": ctx, "agent1_restaurants": agent1_restaurants or []}
    return (
        "Using the following JSON, fill the required top-level JSON structure.\n"
        "- trip_and_food: traveler destination, timing, and food preferences.\n"
        "- agent1_restaurants: ranked restaurants from Google Places + embedding RAG (name, address, summaries, review_snippets, rag_match_score).\n\n"
        + json.dumps(payload, indent=2)
    )
