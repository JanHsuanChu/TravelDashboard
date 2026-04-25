# server.py
# Reactive server: load Supabase on connect, save preferences, generate via Ollama Cloud.

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

# Load .env before reading TD_* / API keys. Search upward so keys work from repo root or TravelDashboard/.
_SHINY_APP_DIR = Path(__file__).resolve().parent
for _env_path in (
    _SHINY_APP_DIR.parent.parent / ".env",
    _SHINY_APP_DIR.parent / ".env",
    _SHINY_APP_DIR / ".env",
):
    if _env_path.is_file():
        load_dotenv(_env_path, override=True)

from shiny import reactive, render, ui

import shiny_app.tags as tagdata
from shiny_app.context import load_architecture_markdown
from shiny_app.components import food_preference_combined_content
from shiny_app.iso2_bridge import friendliness_country_query, is_known_iso2
from shiny_app.ollama_client import extract_json_object, ollama_chat, resolved_model_agent2, resolved_model_other
from shiny_app.plan_logic import (
    AGENT2_DINING_GROUNDING,
    SYSTEM_JSON_INSTRUCTION,
    build_trip_context,
    user_prompt_from_context,
)
from shiny_app.agent_loop import LoopBudgets, run_orchestrator_loop, validate_plan_guardrails
from shiny_app.restaurant_rag import (
    preference_narrative_from_supabase_row,
    preference_narrative_from_trip_food,
    run_agent1_places_rag,
)
from shiny_app.supabase_client import (
    fetch_user_and_latest_preference,
    get_or_create_user,
    insert_preference,
    normalize_email,
)
from shiny_app.travel_friendliness.pipeline import FriendlinessResult, compute_friendliness
from shiny_app.us_travel_advisory import (
    build_travel_advisory_markdown,
    get_advisory_snapshot,
    match_advisory_row,
    summarize_advisory_with_ollama,
)
from shiny_app.validators import validate_food_text, validate_when_mode, valid_email_shape

logger = logging.getLogger(__name__)


def _travel_friendliness_disabled() -> bool:
    """Skip World Bank + optional report LLM when TD_DISABLE_TRAVEL_FRIENDLINESS is truthy."""
    v = (os.environ.get("TD_DISABLE_TRAVEL_FRIENDLINESS") or "").strip()
    if v.startswith("\ufeff"):
        v = v.lstrip("\ufeff").strip()
    v = v.strip('"').strip("'").strip().lower()
    return v in ("1", "true", "yes", "on")


def _light_arch_context_enabled() -> bool:
    """Shorter system prompt for Agent 2 when TD_LIGHT_ARCH_CONTEXT is truthy."""
    v = (os.environ.get("TD_LIGHT_ARCH_CONTEXT") or "").strip().strip('"').strip("'").lower()
    return v in ("1", "true", "yes", "on")


def _architecture_for_plan_llm() -> str:
    if _light_arch_context_enabled():
        return (
            "Travel Dashboard (Shiny): Agent 1 may supply Google Places restaurants + RAG scores. "
            "You are Agent 2: return only the JSON shape from the system rules. "
            "friendliness fields in JSON are ignored by the UI (scores come from World Bank)."
        )
    return load_architecture_markdown()


def _validate_trip_country_iso2(*, label: str, display_name: str, iso2: str) -> str | None:
    """Return error message if a country field is partially filled without a valid list pick."""
    d = (display_name or "").strip()
    i = (iso2 or "").strip().upper()
    if not d and not i:
        return None
    if len(i) != 2 or not is_known_iso2(i):
        return f"{label}: choose a country from the suggestion list (typing alone is not enough)."
    return None


def _as_tag_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val]
    return [str(val)] if val else []


_DECIMAL_MATCH_BADGE_RE = re.compile(r"^(\d*\.?\d+)\s+match$", re.IGNORECASE)

def _format_dining_match_badge(badge: str | None) -> str:
    """Show RAG-style scores as percentages (0.48 match → 48% match)."""
    s = (badge or "").strip()
    if not s or s == "—":
        return s or "—"
    m = _DECIMAL_MATCH_BADGE_RE.match(s)
    if not m:
        return s
    try:
        val = float(m.group(1))
    except ValueError:
        return s
    if 0 <= val <= 1:
        return f"{round(val * 100)}% match"
    return s


def _format_dining_badge_display(badge: str | None) -> str:
    """Normalize LLM placeholders; then percent-style match badges for places."""
    raw = (badge or "").strip()
    if not raw:
        return "—"
    u = raw.upper().replace(" ", "")
    if u in ("N/A", "NA", "N.A.", "NONE", "NULL", "—", "-"):
        return "—"
    return _format_dining_match_badge(raw)


def _format_place_list_badge(
    llm_badge: str | None,
    *,
    rag_score,
    price_tier: str | None,
) -> str:
    """RAG % from server when available; Google $/$$/$$$; fallback to LLM badge text."""
    tier = (price_tier or "").strip()
    match_part = ""
    if rag_score is not None and rag_score != "":
        try:
            rs = float(rag_score)
            if 0 <= rs <= 1:
                match_part = f"{round(rs * 100)}% match"
        except (TypeError, ValueError):
            pass
    if not match_part:
        match_part = _format_dining_badge_display(llm_badge)
        if match_part == "—":
            match_part = ""
    if tier and match_part:
        return f"{match_part} · {tier}"
    if tier:
        return tier
    return match_part or "—"


_DISH_PRICE_ONLY_DOLLARS_RE = re.compile(r"^\s*(\$+)\s*$")


def _format_dish_price_tier_badge(badge: str | None) -> str:
    """Normalize dish badge to $, $$, or $$$."""
    raw = (badge or "").strip()
    if not raw:
        return "—"
    u = raw.upper().replace(" ", "")
    if u in ("N/A", "NA", "N.A.", "NONE", "NULL", "—", "-"):
        return "—"
    m = _DISH_PRICE_ONLY_DOLLARS_RE.match(raw)
    if m:
        n = min(len(m.group(1)), 3)
        return "$" * max(1, n)
    dc = raw.count("$")
    if dc >= 3:
        return "$$$"
    if dc == 2:
        return "$$"
    if dc == 1:
        return "$"
    low = raw.lower()
    if any(
        p in low
        for p in (
            "fine dining",
            "fine-dining",
            "michelin",
            "tasting menu",
            "degustation",
            "white tablecloth",
            "$$$$",
        )
    ) or any(p in low for p in ("upscale", "premium", "splurge", "luxury", "high-end", "high end")):
        return "$$$"
    if any(
        p in low
        for p in (
            "mid-range",
            "mid range",
            "moderate",
            "bistro",
            "everyday",
            "neighborhood",
        )
    ):
        return "$$"
    if any(
        p in low
        for p in (
            "budget",
            "cheap",
            "street food",
            "night market",
            "stall",
            "hawker",
            "snack",
        )
    ):
        return "$"
    if "casual" in low and "upscale" not in low and "fine" not in low:
        return "$$"
    return "—"


def _default_plan() -> dict:
    return {
        "dining": {
            "dishes": [
                {"title": "Sample dish", "note": "Run Generate with Ollama configured.", "badge": "$$"},
            ],
            "places": [
                {"title": "Sample place", "note": "Placeholder until agents and data sources are wired.", "badge": "—"},
            ],
        },
        "essential": {
            "travel_advisory": "No live advisory feed yet.",
            "weather": "No live weather yet.",
        },
        "friendliness": {
            "primary": {"score": 0, "label": "Not computed"},
            "comparisons": [
                {"label": "Compare 1", "score": 0},
                {"label": "Compare 2", "score": 0},
            ],
        },
    }


def _place_id_from_resource_name(resource_name: str) -> str:
    s = (resource_name or "").strip()
    if "/" in s:
        return s.split("/", 1)[1].strip()
    return s


def _markers_from_candidates(candidates: list[dict] | None) -> list[dict]:
    """Lat/lng, place_id (for Maps Embed), and matching fields (names align with LLM titles)."""
    out: list[dict] = []
    for c in candidates or []:
        out.append(
            {
                "title": (c.get("name") or "").strip(),
                "place_id": _place_id_from_resource_name(str(c.get("place_resource_name") or "")),
                "lat": c.get("latitude"),
                "lng": c.get("longitude"),
                "address": (c.get("formatted_address") or "").strip(),
                "maps_uri": (c.get("google_maps_uri") or "").strip(),
                "price_tier": (c.get("price_tier") or "").strip(),
                "rag_match_score": c.get("rag_match_score"),
            }
        )
    return out


def _is_lat_lng_pair(s: str) -> bool:
    parts = s.split(",")
    if len(parts) != 2:
        return False
    try:
        float(parts[0].strip())
        float(parts[1].strip())
        return True
    except ValueError:
        return False


def _maps_embed_url(
    api_key: str,
    *,
    place_id: str,
    lat,
    lng,
    query: str,
) -> str | None:
    """Maps Embed API — always use `place` mode so `q` is always set (Google rejects some calls without it).

    See https://developers.google.com/maps/documentation/embed/embedding-map#place_mode
    `q` may be a place name, `place_id:ChIJ…`, or lat,lng coordinates.
    """
    if not api_key:
        return None
    q_val: str | None = None
    pid = (place_id or "").strip()
    if pid:
        q_val = f"place_id:{pid}"
    elif lat is not None and lng is not None:
        try:
            la, ln = float(lat), float(lng)
            q_val = f"{la},{ln}"
        except (TypeError, ValueError):
            pass
    if not q_val:
        q_val = (query or "").strip() or None
    if not q_val:
        return None
    if q_val.startswith("place_id:"):
        q_enc = quote(q_val, safe=":")
    elif _is_lat_lng_pair(q_val):
        q_enc = quote(q_val.strip(), safe=",.-")
    else:
        q_enc = quote(q_val)
    return (
        "https://www.google.com/maps/embed/v1/place"
        f"?key={quote(api_key)}&q={q_enc}&zoom=16"
    )


def _merge_places_rows(plan: dict, markers: list[dict]) -> list[dict]:
    """Join model dining.places with Agent 1 coordinates (by exact title, then index)."""
    plan_places = (plan.get("dining") or {}).get("places") or []
    by_title = {(m.get("title") or "").strip(): m for m in markers if (m.get("title") or "").strip()}
    rows: list[dict] = []
    for i, p in enumerate(plan_places):
        title = (p.get("title") or "").strip()
        m = by_title.get(title)
        if m is None and i < len(markers):
            m = markers[i]
        elif m is None:
            m = {}
        rows.append(
            {
                "title": title or "—",
                "badge": p.get("badge") or "—",
                "note": p.get("note") or "",
                "address": m.get("address", ""),
                "maps_uri": m.get("maps_uri", ""),
                "place_id": (m.get("place_id") or "").strip(),
                "lat": m.get("lat"),
                "lng": m.get("lng"),
                "price_tier": (m.get("price_tier") or "").strip(),
                "rag_match_score": m.get("rag_match_score"),
            }
        )
    return rows


def _dish_item_block(it: dict) -> ui.Tag:
    return ui.div(
        ui.div(
            ui.h4(it.get("title") or "—"),
            ui.span(
                _format_dish_price_tier_badge(it.get("badge")),
                class_="td-dining-item-badge",
            ),
            class_="td-dining-item-title",
        ),
        ui.p(it.get("note") or "", class_="td-dining-item-note"),
        class_="td-dining-item",
    )


def _dining_dishes_only_ui(plan: dict) -> ui.Tag:
    d = plan.get("dining") or {}
    dishes = d.get("dishes") or []
    dish_section = (
        ui.div(*(_dish_item_block(i) for i in dishes))
        if dishes
        else ui.p("No dishes yet.", class_="td-muted")
    )
    return ui.div(
        ui.div("Dishes", class_="td-output-subhead"),
        dish_section,
        class_="td-dining-out",
    )


def _place_address_line(r: dict) -> ui.Tag:
    addr = (r.get("address") or "").strip()
    uri = (r.get("maps_uri") or "").strip()
    if uri and addr:
        return ui.p(
            ui.tags.a(addr, href=uri, target="_blank", rel="noopener noreferrer"),
            class_="td-dining-place-address",
        )
    if addr:
        return ui.p(addr, class_="td-dining-place-address")
    return ui.div()


def _dining_places_list_ui(plan: dict, markers: list[dict], selected_idx: int) -> ui.Tag:
    rows = _merge_places_rows(plan, markers)
    if not rows:
        return ui.p("Run Generate to see recommended places.", class_="td-muted")
    blocks: list[ui.Tag] = []
    for i, r in enumerate(rows):
        active = i == selected_idx
        blocks.append(
            ui.div(
                ui.div(
                    ui.h4(r["title"]),
                    ui.span(
                        _format_place_list_badge(
                            r.get("badge"),
                            rag_score=r.get("rag_match_score"),
                            price_tier=r.get("price_tier"),
                        ),
                        class_="td-dining-item-badge",
                    ),
                    class_="td-dining-item-title",
                ),
                ui.p(r["note"], class_="td-dining-item-note"),
                _place_address_line(r),
                class_="td-dining-item td-dining-place-item td-place-row-selectable"
                + (" td-place-row-active" if active else ""),
                **{"data-td-place-idx": str(i)},
            )
        )
    return ui.div(*blocks, class_="td-dining-places-list-inner")


def _essential_md_field(raw, *, default: str = "—") -> str:
    """Model JSON often uses \"\" for missing text; .get(k, default) would not substitute."""
    if raw is None:
        return default
    s = str(raw).strip()
    return s if s else default


def _format_essential(plan: dict) -> str:
    e = plan.get("essential") or {}
    # Use ### so Essential card CSS can style section labels like Travel friendliness (.td-friendliness-section-label).
    return "\n\n".join(
        [
            f"### Travel advisory\n\n{_essential_md_field(e.get('travel_advisory'))}",
            f"### Weather\n\n{_essential_md_field(e.get('weather'))}",
        ]
    )


def _validate_food_fields(input) -> str | None:
    lt = input.food_like_text() or ""
    dt = input.food_dislike_text() or ""
    dr = input.dietary_restrictions_text() or ""
    for text, label in (
        (lt, "Food I like (text)"),
        (dt, "Food I dislike (text)"),
        (dr, "Dietary restrictions (text)"),
    ):
        err = validate_food_text(text, label)
        if err:
            return err
    return None


def _food_tags_from_input(input) -> dict:
    return {
        "like": _as_tag_list(input.like_tags()),
        "dislike": _as_tag_list(input.dislike_tags()),
        "dietary": _as_tag_list(input.dietary_tags()),
    }


def _identity_complete(input) -> bool:
    fn = (input.user_first_name() or "").strip()
    em = normalize_email(input.user_email() or "")
    return bool(fn and em and valid_email_shape(em))


def _validate_identity_for_save(input) -> str | None:
    fn = (input.user_first_name() or "").strip()
    em_raw = (input.user_email() or "").strip()
    em = normalize_email(em_raw)
    if not fn or not em:
        return "Enter first name and email before saving."
    if not valid_email_shape(em):
        return "Enter a valid email address."
    return None


def _persist_preferences(input) -> None:
    """Insert preference row; assumes identity and food validations already passed."""
    fn = (input.user_first_name() or "").strip()
    em = normalize_email(input.user_email() or "")
    lt = input.food_like_text() or ""
    dt = input.food_dislike_text() or ""
    dr = input.dietary_restrictions_text() or ""
    tags = _food_tags_from_input(input)
    uid = get_or_create_user(email=em, first_name=fn)
    insert_preference(
        user_id=uid,
        food_like_text=lt or None,
        food_dislike_text=dt or None,
        dietary_restrictions=dr or None,
        food_tags=tags,
    )


def _filter_pref_tags(ft: dict | None) -> tuple[list[str], list[str], list[str]]:
    ft = ft or {}
    like = [x for x in (ft.get("like") or []) if x in tagdata.FOOD_LIKE_CHOICES]
    dislike = [x for x in (ft.get("dislike") or []) if x in tagdata.FOOD_DISLIKE_CHOICES]
    dietary = [x for x in (ft.get("dietary") or []) if x in tagdata.DIETARY_CHOICES]
    return like, dislike, dietary


def server(input, output, session):
    plan_state = reactive.Value(_default_plan())
    dining_badge_state = reactive.Value("")
    places_error_state = reactive.Value("")
    map_places_state = reactive.Value([])
    friendliness_state = reactive.Value[FriendlinessResult | None](None)
    last_lookup_email = reactive.Value(None)
    last_saved_iso = reactive.Value("")
    last_welcome_key = reactive.Value(None)
    agent_session_id = reactive.Value("")
    agent_pending_question = reactive.Value("")
    agent_status_msg = reactive.Value("")
    food_collapsed = reactive.Value(False)
    chat_messages = reactive.Value([])  # list[dict{role, content, includes_recs, chips, saved_notice}]
    chat_assistant_turns = reactive.Value(0)
    quick_replies_state = reactive.Value([])  # list[dict{label,message}]
    status_panel_open = reactive.Value(True)
    status_drawer_open = reactive.Value(False)
    saved_pref_notice = reactive.Value("")  # one-line last notice for UI

    def _append_chat(role: str, content: str, *, includes_recs: bool = False) -> None:
        rows = list(chat_messages() or [])
        rows.append({"role": role, "content": content, "includes_recs": bool(includes_recs)})
        chat_messages.set(rows)
        if role == "assistant":
            chat_assistant_turns.set(int(chat_assistant_turns() or 0) + 1)

    def _tag_label_map(d: dict[str, str], slugs: list[str]) -> list[str]:
        out = []
        for s in slugs or []:
            if s in d:
                out.append(d[s])
        return out

    def _text_to_chips(text: str) -> list[str]:
        """
        Split free-text into multiple short chips. Simple fallback:
        - split on comma/semicolon/newline
        - also split on ' and ' for short lists
        """
        raw = (text or "").strip()
        if not raw:
            return []
        s = raw.replace("\r\n", "\n").replace(";", ",")
        parts: list[str] = []
        for line in s.split("\n"):
            for chunk in line.split(","):
                c = " ".join(chunk.split()).strip()
                if not c:
                    continue
                parts.append(c)
        out: list[str] = []
        for p in parts:
            if len(p) > 46:
                p = p[:46].rsplit(" ", 1)[0] if " " in p[:46] else p[:46]
            if p and p.lower() not in {x.lower() for x in out}:
                out.append(p)
        return out[:8]

    def _context_tags_for_ui() -> dict[str, list[str]]:
        wm = input.when_mode()
        ws = input.when_season() if wm == "season" else None
        wmth = input.when_month() if wm == "month" else None
        loc = ", ".join(
            p
            for p in (
                (input.dest_city() or "").strip(),
                (input.dest_country() or "").strip(),
            )
            if p
        )
        when_tag = ""
        if wm == "season" and ws:
            when_tag = str(tagdata.SEASON_CHOICES.get(str(ws), ws))
        elif wm == "month" and wmth:
            when_tag = str(tagdata.MONTH_CHOICES.get(str(wmth), wmth))
        like = _tag_label_map(tagdata.FOOD_LIKE_CHOICES, _as_tag_list(input.like_tags()))
        dislike = _tag_label_map(tagdata.FOOD_DISLIKE_CHOICES, _as_tag_list(input.dislike_tags()))
        dietary = _tag_label_map(tagdata.DIETARY_CHOICES, _as_tag_list(input.dietary_tags()))
        # Free-text chips: include in UI/status; dietary text is treated as blocker context.
        like_text_chips = _text_to_chips(input.food_like_text() or "")
        dislike_text_chips = _text_to_chips(input.food_dislike_text() or "")
        dietary_text_chips = _text_to_chips(input.dietary_restrictions_text() or "")
        return {
            "location": [x for x in (loc, when_tag) if x],
            "dietary": dietary + dietary_text_chips,
            "like": like + like_text_chips,
            "dislike": dislike + dislike_text_chips,
        }

    def _maybe_generate_quick_replies(*, ctx: dict, plan: dict, last_user_message: str | None = None) -> None:
        """
        LLM-generated quick reply chips (validated server-side).
        """
        def _fallback_chips(*, last_user_message: str | None) -> list[dict[str, str]]:
            m = (last_user_message or "").strip().lower()
            facts = _context_tags_for_ui()
            out: list[dict[str, str]] = [
                {"label": "Cheaper options", "message": "Show me cheaper options."},
                {"label": "More like #1", "message": "More like #1, please."},
                {"label": "Different area", "message": "Try a different area in the city."},
            ]
            if any(x in m for x in ("dessert", "sweet", "cake", "pastry", "ice cream")):
                out.append({"label": "Desserts", "message": "Prioritize places with great desserts."})
            if any(x in m for x in ("not spicy", "less spicy", "mild", "avoid spicy")) or ("Spicy" in (facts.get("like") or [])):
                out.append({"label": "Less spicy", "message": "Less spicy options, please."})
            if any("vegetarian" in str(x).lower() or "vegan" in str(x).lower() for x in (facts.get("dietary") or [])):
                out.append({"label": "Veg-friendly", "message": "More vegetarian/vegan-friendly options."})
            if any(x in m for x in ("walk in", "walk-in", "no reservation", "no reservations")):
                out.append({"label": "Walk-in ok", "message": "No reservation needed (walk-in friendly)."})
            # Keep 3–6 chips.
            return out[:6]

        last_msg = (last_user_message or "").strip()
        try:
            places = ((plan.get("dining") or {}).get("places") or [])[:3]
            top = [str(p.get("title") or "").strip() for p in places if isinstance(p, dict) and (p.get("title") or "").strip()]
            facts = _context_tags_for_ui()
            sys = (
                "You propose quick reply chips for a travel dining recommender.\n"
                "Return ONLY one JSON object:\n"
                '{"chips":[{"label":"...","message":"..."}]}\n'
                "Rules:\n"
                "- 3 to 6 chips\n"
                "- label <= 24 chars; message <= 80 chars\n"
                "- No URLs\n"
                "- Messages should be short user intents (e.g. 'cheaper options', 'more like #1', 'different area')\n"
                "- Use the form context; do not ask for location/dietary/dislikes.\n"
                "- Avoid repeating the same chips every turn.\n"
            )
            user = (
                "Context:\n"
                + str({"location": facts["location"], "dietary": facts["dietary"], "likes": facts["like"], "dislikes": facts["dislike"]})
                + "\nLast user message:\n"
                + (last_msg or "(none)")
                + "\nTop places:\n"
                + ", ".join(top)
            )
            raw = ollama_chat(
                [{"role": "system", "content": sys}, {"role": "user", "content": user}],
                model=resolved_model_other(),
            )
            obj = extract_json_object(raw) or {}
            chips = obj.get("chips") if isinstance(obj, dict) else None
            out = []
            if isinstance(chips, list):
                for c in chips[:6]:
                    if not isinstance(c, dict):
                        continue
                    label = str(c.get("label") or "").strip()
                    message = str(c.get("message") or "").strip()
                    if not label or not message:
                        continue
                    if "http://" in message or "https://" in message:
                        continue
                    if len(label) > 24 or len(message) > 80:
                        continue
                    out.append({"label": label, "message": message})
            if len(out) >= 3:
                logger.info("chips_llm_ok n=%s", len(out))
                quick_replies_state.set(out)
                return
            logger.warning("chips_llm_invalid raw=%s", _safe_text_snippet(raw))
        except Exception as e:
            logger.warning("chips_llm_fallback err=%s", e)
        quick_replies_state.set(_fallback_chips(last_user_message=last_msg))

    def _safe_text_snippet(s: str | None, *, max_chars: int = 400) -> str:
        t = (s or "").strip().replace("\n", " ")
        return (t[:max_chars] + "…") if len(t) > max_chars else t

    def _assistant_followup_message(*, ctx: dict, user_message: str, plan: dict, cards_shown: bool) -> str:
        """
        LLM-written follow-up: 1–3 sentences. May ask one clarifying question when needed.
        """
        places = ((plan.get("dining") or {}).get("places") or [])[:3]
        top = [str(p.get("title") or "").strip() for p in places if isinstance(p, dict) and (p.get("title") or "").strip()]
        facts = _context_tags_for_ui()
        sys = (
            "You are the Food guide assistant in a travel dashboard chat widget.\n"
            "Write a short reply (1–3 sentences) responding to the user's latest message.\n"
            "Rules:\n"
            "- Do NOT re-ask location, timing, dietary restrictions, or dislikes.\n"
            "- If you need more info, ask at most ONE clarifying question.\n"
            "- If recommendations were refreshed, say so briefly.\n"
            "- No bullet lists.\n"
        )
        user = (
            "From the form (read-only):\n"
            + str({"location": facts["location"], "dietary": facts["dietary"], "likes": facts["like"], "dislikes": facts["dislike"]})
            + "\nUser message:\n"
            + user_message.strip()
            + "\nTop places:\n"
            + ", ".join(top)
            + "\nCards shown:\n"
            + ("yes" if cards_shown else "no")
        )
        try:
            raw = ollama_chat(
                [{"role": "system", "content": sys}, {"role": "user", "content": user}],
                model=resolved_model_other(),
            )
            msg = (raw or "").strip()
            if msg:
                logger.info("followup_llm_ok chars=%s", len(msg))
                return msg
        except Exception as e:
            logger.warning("followup_llm_fallback err=%s", e)
        # Deterministic fallback if LLM fails.
        short = user_message.strip()
        short = short[:120] + "…" if len(short) > 120 else short
        return f"Got it — {short}"

    def _maybe_save_durable_delta(*, msg: str, ctx: dict) -> None:
        """
        Save durable deltas to the preference table (append-only).
        De-dup against current form values and latest stored preference.
        """
        if not _identity_complete(input):
            return
        m = (msg or "").strip().lower()
        if not m:
            return

        # Example durable delta: "avoid spicy"
        avoid_spicy = ("avoid spicy" in m) or ("no spicy" in m) or ("not spicy" in m)
        if not avoid_spicy:
            # Example durable delta: "no raw fish"
            if "no raw fish" in m or "avoid raw fish" in m:
                # For now store this as a dislike text hint (append-only preference row).
                em = normalize_email(input.user_email() or "")
                _, pref_row = fetch_user_and_latest_preference(em)
                stored_dr = (pref_row.get("dietary_restrictions") or "") if pref_row else ""
                if "raw fish" in stored_dr.lower():
                    return
                uid = get_or_create_user(email=em, first_name=(input.user_first_name() or "").strip())
                insert_preference(
                    user_id=uid,
                    food_like_text=(input.food_like_text() or "") or None,
                    food_dislike_text=(input.food_dislike_text() or "") or None,
                    dietary_restrictions=((input.dietary_restrictions_text() or "") + " No raw fish.").strip() or None,
                    food_tags=_food_tags_from_input(input),
                )
                saved_pref_notice.set('✓ "No raw fish" saved to your profile')
            return

        # De-dup: if already selected as dislike or not present as a like, skip.
        cur_like = set(_as_tag_list(input.like_tags()))
        cur_dislike = set(_as_tag_list(input.dislike_tags()))
        if "spicy" in cur_dislike:
            return

        em = normalize_email(input.user_email() or "")
        _, pref_row = fetch_user_and_latest_preference(em)
        stored_dislike = set()
        stored_like = set()
        if pref_row and isinstance(pref_row.get("food_tags"), dict):
            ft = pref_row.get("food_tags") or {}
            stored_like = set(ft.get("like") or [])
            stored_dislike = set(ft.get("dislike") or [])
        if "spicy" in stored_dislike:
            return

        # Merge: remove from likes if present, add to dislikes.
        new_like = [x for x in cur_like if x != "spicy"]
        new_dislike = sorted(list(cur_dislike | {"spicy"}))
        new_tags = {
            "like": new_like,
            "dislike": new_dislike,
            "dietary": _as_tag_list(input.dietary_tags()),
        }
        uid = get_or_create_user(email=em, first_name=(input.user_first_name() or "").strip())
        insert_preference(
            user_id=uid,
            food_like_text=(input.food_like_text() or "") or None,
            food_dislike_text=(input.food_dislike_text() or "") or None,
            dietary_restrictions=(input.dietary_restrictions_text() or "") or None,
            food_tags=new_tags,
        )
        saved_pref_notice.set('✓ "Avoid spicy" saved to your profile')

    def _food_summary_from_ctx(ctx: dict) -> str:
        food = ctx.get("food") or {}
        like = ", ".join(str(x) for x in (food.get("like_tags") or []) if x)
        dislike = ", ".join(str(x) for x in (food.get("dislike_tags") or []) if x)
        dietary = ", ".join(str(x) for x in (food.get("dietary_tags") or []) if x)
        parts = []
        if like:
            parts.append(f"Likes: {like}")
        if dislike:
            parts.append(f"Dislikes: {dislike}")
        if dietary:
            parts.append(f"Dietary: {dietary}")
        return " · ".join(parts) if parts else "No food preferences set."

    def _opening_message(ctx: dict, plan: dict) -> str:
        dest = (ctx.get("destination") or {})
        when = (ctx.get("when") or {})
        food = (ctx.get("food") or {})
        city = (dest.get("city") or "").strip()
        country = (dest.get("country") or "").strip()
        loc = ", ".join(x for x in (city, country) if x) or "your destination"
        mode = (when.get("mode") or "").strip()
        timing = ""
        if mode == "season" and when.get("season"):
            timing = str(tagdata.SEASON_CHOICES.get(str(when.get("season")), when.get("season")))
        elif mode == "month" and when.get("month"):
            timing = str(tagdata.MONTH_CHOICES.get(str(when.get("month")), when.get("month")))

        dietary_labels = _tag_label_map(tagdata.DIETARY_CHOICES, list(food.get("dietary_tags") or []))
        like_labels = _tag_label_map(tagdata.FOOD_LIKE_CHOICES, list(food.get("like_tags") or []))

        timing_phrase = f"in {timing}" if timing else ""
        dietary_phrase = f" as a {', '.join(dietary_labels)}" if dietary_labels else ""

        like_phrase = ""
        if like_labels:
            top = like_labels[:2]
            if len(top) == 1:
                like_phrase = f" You love {top[0].lower()}."
            else:
                like_phrase = f" You love {top[0].lower()} and {top[1].lower()}."

        places = ((plan.get("dining") or {}).get("places") or [])[:3]
        starters = "\n".join(f"- {(p.get('title') or '—').strip()}" for p in places if isinstance(p, dict))
        starters = starters or "- (No places yet — enable Google Places or try again.)"
        head = f"You're heading to {loc} {timing_phrase}{dietary_phrase}."
        head = " ".join(head.split())
        return head + like_phrase + "\n\nHere are 3 spots to start with:"

    @render.text
    def last_saved_hint():
        s = last_saved_iso()
        return f"Last saved: {s[:10]}" if s else ""

    @reactive.effect
    def _preload_from_debounced_email():
        raw = input.user_email_debounced() or ""
        key = normalize_email(raw)
        prev = last_lookup_email()
        if prev is not None and key == prev:
            return
        last_lookup_email.set(key)

        if not key or not valid_email_shape(key):
            last_saved_iso.set("")
            return

        try:
            user, pref = fetch_user_and_latest_preference(key)
        except Exception as e:
            ui.notification_show(
                ui.span(f"Could not look up preferences: {e}"),
                type="warning",
                session=session,
            )
            return

        if not user:
            last_saved_iso.set("")
            return

        ui.update_text("user_first_name", label="First name", value=user.get("first_name") or "")
        ui.update_text("user_email", label="Email", value=user.get("email") or key)

        if pref:
            ca = pref.get("created_at")
            last_saved_iso.set(str(ca) if ca else "")
            ui.update_text_area("food_like_text", label="More detail (optional)", value=pref.get("food_like_text") or "")
            ui.update_text_area("food_dislike_text", label="More detail (optional)", value=pref.get("food_dislike_text") or "")
            ui.update_text_area(
                "dietary_restrictions_text",
                label="Allergies or other restrictions (optional)",
                value=pref.get("dietary_restrictions") or "",
            )
            like, dislike, dietary = _filter_pref_tags(pref.get("food_tags"))
            ui.update_checkbox_group("like_tags", selected=like)
            ui.update_checkbox_group("dislike_tags", selected=dislike)
            ui.update_checkbox_group("dietary_tags", selected=dietary)

            wk = last_welcome_key()
            if wk != key:
                first = (user.get("first_name") or "").strip() or "there"
                ui.notification_show(
                    ui.span(
                        f"Welcome back, {first}! We loaded your last preferences.",
                    ),
                    type="message",
                    session=session,
                )
                last_welcome_key.set(key)
        else:
            last_saved_iso.set("")

    @reactive.effect
    @reactive.event(input.btn_save)
    def _save_food():
        err = _validate_identity_for_save(input)
        if err:
            ui.notification_show(ui.span(err), type="warning", session=session)
            return
        err = _validate_food_fields(input)
        if err:
            ui.notification_show(ui.span(err), type="error", session=session)
            return
        try:
            _persist_preferences(input)
            ui.notification_show(ui.span("Saved food preferences."), type="message", session=session)
        except Exception as e:
            ui.notification_show(
                ui.span(f"Save failed: {e}"),
                type="error",
                session=session,
            )

    @reactive.effect
    @reactive.event(input.btn_generate)
    def _generate():
        wm = input.when_mode()
        ws = input.when_season() if wm == "season" else None
        wmth = input.when_month() if wm == "month" else None
        err = validate_when_mode(wm, ws, wmth)
        if err:
            ui.notification_show(ui.span(err), type="warning", session=session)
            return

        dc_iso = (input.dest_country_iso2() or "").strip().upper()
        dc_name = (input.dest_country() or "").strip()
        err_trip = _validate_trip_country_iso2(
            label="Destination country", display_name=dc_name, iso2=dc_iso
        )
        if err_trip:
            ui.notification_show(ui.span(err_trip), type="warning", session=session)
            return
        if not dc_iso or len(dc_iso) != 2:
            ui.notification_show(
                ui.span("Enter a destination country before generating (pick from the country list)."),
                type="warning",
                session=session,
            )
            return

        err = _validate_food_fields(input)
        if err:
            ui.notification_show(ui.span(err), type="error", session=session)
            return

        cmp1_name = (input.cmp1_country() or "").strip()
        cmp1_iso = (input.cmp1_country_iso2() or "").strip().upper()
        cmp2_name = (input.cmp2_country() or "").strip()
        cmp2_iso = (input.cmp2_country_iso2() or "").strip().upper()
        for lab, n, i in (
            ("Compare 1 country", cmp1_name, cmp1_iso),
            ("Compare 2 country", cmp2_name, cmp2_iso),
        ):
            e2 = _validate_trip_country_iso2(label=lab, display_name=n, iso2=i)
            if e2:
                ui.notification_show(ui.span(e2), type="warning", session=session)
                return

        dc = friendliness_country_query(dc_iso, dc_name)
        cmp1_c = friendliness_country_query(cmp1_iso, cmp1_name) if cmp1_iso else ""
        cmp2_c = friendliness_country_query(cmp2_iso, cmp2_name) if cmp2_iso else ""

        friend_pool: ThreadPoolExecutor | None = None
        fr_fut = None  # Future from background compute_friendliness when enabled
        if _travel_friendliness_disabled():
            friendliness_state.set(
                FriendlinessResult(
                    ok=False,
                    error_message=(
                        "Travel friendliness is disabled (TD_DISABLE_TRAVEL_FRIENDLINESS). "
                        "Remove or unset that variable to restore World Bank scores and the HTML report."
                    ),
                )
            )
        else:
            friend_pool = ThreadPoolExecutor(max_workers=1)
            fr_fut = friend_pool.submit(compute_friendliness, dc, cmp1_c, cmp2_c)

        try:
            food_collapsed.set(False)
            chat_messages.set([])
            chat_assistant_turns.set(0)
            quick_replies_state.set([])
            saved_pref_notice.set("")
            skipped_persist = not _identity_complete(input)
            if not skipped_persist:
                try:
                    _persist_preferences(input)
                except Exception as e:
                    ui.notification_show(
                        ui.span(f"Could not save preferences before generating: {e}"),
                        type="error",
                        session=session,
                    )
                    return

            ctx = build_trip_context(
                {
                    "dest_country": input.dest_country(),
                    "dest_country_iso2": input.dest_country_iso2(),
                    "dest_city": input.dest_city(),
                    "cmp1_country": input.cmp1_country(),
                    "cmp1_country_iso2": input.cmp1_country_iso2(),
                    "cmp1_city": input.cmp1_city(),
                    "cmp2_country": input.cmp2_country(),
                    "cmp2_country_iso2": input.cmp2_country_iso2(),
                    "cmp2_city": input.cmp2_city(),
                    "when_mode": wm,
                    "when_season": ws,
                    "when_month": wmth,
                    "like_tags": _as_tag_list(input.like_tags()),
                    "dislike_tags": _as_tag_list(input.dislike_tags()),
                    "dietary_tags": _as_tag_list(input.dietary_tags()),
                    "food_like_text": input.food_like_text(),
                    "food_dislike_text": input.food_dislike_text(),
                    "dietary_restrictions_text": input.dietary_restrictions_text(),
                }
            )

            dest_label = ", ".join(
                p
                for p in (
                    (input.dest_city() or "").strip(),
                    (input.dest_country() or "").strip(),
                )
                if p
            )
            dining_badge_state.set(
                (input.dest_city() or "").strip() or (input.dest_country() or "").strip() or "Destination"
            )

            trip_food_narrative = preference_narrative_from_trip_food(ctx["food"])
            pref_narrative = trip_food_narrative
            if _identity_complete(input):
                try:
                    _, pref_row = fetch_user_and_latest_preference(normalize_email(input.user_email()))
                    db_narrative = preference_narrative_from_supabase_row(pref_row).strip()
                    if db_narrative:
                        # Trip-first so current checkboxes (e.g. vegetarian) always influence RAG, even if DB is stale.
                        pref_narrative = " ".join(
                            x for x in (trip_food_narrative.strip(), db_narrative) if x
                        ).strip()
                except Exception:
                    pass
            if not pref_narrative.strip():
                pref_narrative = trip_food_narrative

            places_error_state.set("")
            agent1_candidates: list = []
            generated_ok = False
            try:
                arch = _architecture_for_plan_llm()
                budgets = LoopBudgets(min_llm_turns=2, max_llm_turns=6, max_retrieval_reruns=6)
                res = run_orchestrator_loop(
                    ctx=ctx,
                    architecture_md=arch,
                    destination_label=dest_label or (input.dest_country() or "").strip(),
                    preference_narrative=pref_narrative,
                    budgets=budgets,
                )
                agent_session_id.set(res.session_id)
                if res.status == "needs_clarification":
                    agent_pending_question.set(res.question or "")
                    agent_status_msg.set("Waiting for your answer.")
                    _append_chat("assistant", res.question or "One quick question to improve the picks:", includes_recs=False)
                    ui.notification_show(
                        ui.span("I have a quick question to improve the recommendations—answer below and press Send."),
                        type="message",
                        duration=10,
                        session=session,
                    )
                    return
                if res.status != "final" or not res.plan:
                    raise RuntimeError(res.detail or "Orchestrator failed.")

                parsed = dict(res.plan)
                agent1_candidates = list(res.agent1_candidates or [])
                ok_guard, guard_err = validate_plan_guardrails(
                    plan=parsed, ctx=ctx, agent1_candidates=agent1_candidates
                )
                if not ok_guard:
                    agent_status_msg.set(guard_err or "Guardrail blocked the recommendation.")
                    ui.notification_show(ui.span("Guardrail blocked the recommendation; see status box."), type="error", session=session)
                    return

                with ThreadPoolExecutor(max_workers=1) as _adv_pool:
                    fut_snap = _adv_pool.submit(get_advisory_snapshot)
                    snap = fut_snap.result()
                    matched = match_advisory_row(
                        snap.rows,
                        iso2=dc_iso,
                        display_country=dc_name,
                    )
                    summary_advisory = ""
                    if matched:
                        try:
                            summary_advisory = summarize_advisory_with_ollama(matched)
                        except Exception as sum_exc:
                            logger.warning("Travel advisory Ollama summary failed: %s", sum_exc)
                    ess = parsed.get("essential")
                    if not isinstance(ess, dict):
                        ess = {}
                    ess = dict(ess)
                    ess.pop("news", None)
                    ess["travel_advisory"] = build_travel_advisory_markdown(
                        matched,
                        snap,
                        summary_advisory,
                    )
                    parsed["essential"] = ess
                    plan_state.set(parsed)
                    map_places_state.set(_markers_from_candidates(agent1_candidates))
                    ui.update_text("map_place_pick", value="0", session=session)
                    agent_pending_question.set("")
                    agent_status_msg.set(
                        f"Done. session={res.session_id[:8]} turns={res.llm_turns_used} retrieval={res.retrieval_attempts}"
                    )
                    food_collapsed.set(True)
                    _append_chat("assistant", _opening_message(ctx, parsed), includes_recs=True)
                    generated_ok = True
                    _maybe_generate_quick_replies(ctx=ctx, plan=parsed, last_user_message=None)
                    if skipped_persist:
                        ui.notification_show(
                            ui.span(
                                "Recommendations updated. Add your first name and email to save these preferences for next time.",
                            ),
                            type="message",
                            session=session,
                        )
                    else:
                        msg = (
                            "Updated outputs (dining uses Google Places + RAG when configured)."
                            if agent1_candidates
                            else "Updated outputs from model."
                        )
                        ui.notification_show(ui.span(msg), type="message", session=session)
            except Exception as e:
                if generated_ok:
                    # Late-stage error after recommendations were already produced.
                    # Keep outputs/chat, but surface the failure in the status box and a toast.
                    detail = str(e).strip()
                    if detail:
                        msg_detail = f"{type(e).__name__}: {detail}"
                    else:
                        msg_detail = f"{type(e).__name__}: {repr(e)}"
                    agent_status_msg.set(f"Generate warning: {msg_detail}")
                    ui.notification_show(ui.span(f"Generate warning: {msg_detail}"), type="warning", session=session)
                    return
                detail = str(e).strip()
                if detail:
                    msg_detail = f"{type(e).__name__}: {detail}"
                else:
                    msg_detail = f"{type(e).__name__}: {repr(e)}"
                agent_status_msg.set(f"Generate failed: {msg_detail}")
                _append_chat(
                    "assistant",
                    "I couldn't generate recommendations just now.\n\n"
                    f"**Error**: `{msg_detail}`\n\n"
                    "Try again in a moment. If this keeps happening, check that your API keys are set and the network is available.",
                    includes_recs=False,
                )
                ui.notification_show(
                    ui.span(f"Generate failed: {msg_detail}"),
                    type="error",
                    session=session,
                )
        finally:
            if fr_fut is not None:
                try:
                    fr = fr_fut.result()
                except Exception as e:
                    fr = FriendlinessResult(ok=False, error_message=f"Travel friendliness error: {e}")
                friendliness_state.set(fr)
                if not fr.ok and fr.error_message:
                    ui.notification_show(
                        ui.span(f"Travel friendliness: {fr.error_message}"),
                        type="warning",
                        session=session,
                    )
            if friend_pool is not None:
                friend_pool.shutdown(wait=True)

    @render.ui
    def dining_dest_badge():
        t = dining_badge_state().strip()
        if not t:
            return ui.span()
        return ui.span(t, class_="td-out-destination-tag")

    @render.ui
    def places_retrieval_error():
        msg = places_error_state().strip()
        if not msg:
            return ui.div()
        return ui.div(
            ui.p("Restaurant retrieval (Agent 1 — Google Places)", class_="td-places-error-title"),
            ui.tags.pre(msg, class_="td-places-error-body"),
            class_="td-places-error-banner",
        )

    @render.ui
    def out_dining_dishes():
        return _dining_dishes_only_ui(plan_state())

    @render.ui
    def out_dining_places_list():
        try:
            sel = int(str(input.map_place_pick() or "0").strip())
        except ValueError:
            sel = 0
        rows = _merge_places_rows(plan_state(), map_places_state())
        if rows and (sel < 0 or sel >= len(rows)):
            sel = 0
        return _dining_places_list_ui(plan_state(), map_places_state(), sel)

    @render.ui
    def out_dining_places_map():
        key = (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
        try:
            idx = int(str(input.map_place_pick() or "0").strip())
        except ValueError:
            idx = 0
        rows = _merge_places_rows(plan_state(), map_places_state())
        if not rows:
            return ui.div(
                ui.p("Generate recommendations to see an embedded map.", class_="td-gmap-placeholder"),
                class_="td-gmap-root",
            )
        if idx < 0 or idx >= len(rows):
            idx = 0
        row = rows[idx]
        q = ", ".join(x for x in (row.get("title"), row.get("address")) if x)
        src = _maps_embed_url(
            key,
            place_id=row.get("place_id") or "",
            lat=row.get("lat"),
            lng=row.get("lng"),
            query=q,
        )
        if not key:
            return ui.div(
                ui.p(
                    "Set GOOGLE_PLACES_API_KEY and enable Maps Embed API on the same Google Cloud project.",
                    class_="td-gmap-placeholder",
                ),
                class_="td-gmap-root",
            )
        if not src:
            return ui.div(
                ui.p("Not enough location data to embed this place.", class_="td-gmap-placeholder"),
                class_="td-gmap-root",
            )
        return ui.div(
            ui.p(
                "The map is interactive inside the frame: use the pin to open Google’s place details. "
                "Click a restaurant in the list to switch locations.",
                class_="td-gmap-help td-muted",
            ),
            ui.tags.iframe(
                src=src,
                width="100%",
                class_="td-gmap-iframe",
                allowfullscreen=True,
                loading="lazy",
                referrerpolicy="strict-origin-when-cross-origin",
                **{"aria-label": "Embedded Google Map for selected restaurant"},
            ),
            class_="td-gmap-root",
        )

    @render.ui
    def out_essential():
        return ui.markdown(_format_essential(plan_state()))

    @reactive.effect
    @reactive.event(input.btn_agent_send)
    def _agent_send():
        sid = (agent_session_id() or "").strip()
        q = (agent_pending_question() or "").strip()
        msg = (input.agent_chat_input() or "").strip()
        if not sid or not q:
            # Conversation starts after Generate; allow send as refinement even without a pending question.
            if not sid:
                ui.notification_show(ui.span("Use Generate first."), type="warning", session=session)
                return
        if not msg:
            ui.notification_show(ui.span("Type a message before sending."), type="warning", session=session)
            return
        if int(chat_assistant_turns() or 0) >= 6:
            ui.notification_show(ui.span("Turn cap reached for this session."), type="warning", session=session)
            return
        _append_chat("user", msg, includes_recs=False)
        try:
            arch = _architecture_for_plan_llm()
            # Rebuild ctx + narrative from current inputs; keep additive.
            wm = input.when_mode()
            ws = input.when_season() if wm == "season" else None
            wmth = input.when_month() if wm == "month" else None
            ctx = build_trip_context(
                {
                    "dest_country": input.dest_country(),
                    "dest_country_iso2": input.dest_country_iso2(),
                    "dest_city": input.dest_city(),
                    "cmp1_country": input.cmp1_country(),
                    "cmp1_country_iso2": input.cmp1_country_iso2(),
                    "cmp1_city": input.cmp1_city(),
                    "cmp2_country": input.cmp2_country(),
                    "cmp2_country_iso2": input.cmp2_country_iso2(),
                    "cmp2_city": input.cmp2_city(),
                    "when_mode": wm,
                    "when_season": ws,
                    "when_month": wmth,
                    "like_tags": _as_tag_list(input.like_tags()),
                    "dislike_tags": _as_tag_list(input.dislike_tags()),
                    "dietary_tags": _as_tag_list(input.dietary_tags()),
                    "food_like_text": input.food_like_text(),
                    "food_dislike_text": input.food_dislike_text(),
                    "dietary_restrictions_text": input.dietary_restrictions_text(),
                }
            )
            dest_label = ", ".join(
                p
                for p in (
                    (input.dest_city() or "").strip(),
                    (input.dest_country() or "").strip(),
                )
                if p
            )
            trip_food_narrative = preference_narrative_from_trip_food(ctx["food"])
            pref_narrative = trip_food_narrative
            budgets = LoopBudgets(min_llm_turns=2, max_llm_turns=6, max_retrieval_reruns=6)
            res = run_orchestrator_loop(
                ctx=ctx,
                architecture_md=arch,
                destination_label=dest_label or (input.dest_country() or "").strip(),
                preference_narrative=pref_narrative,
                budgets=budgets,
                session_id=sid,
                user_message=msg,
            )
            if res.status == "needs_clarification":
                agent_pending_question.set(res.question or "")
                agent_status_msg.set("Waiting for your answer.")
                _append_chat("assistant", res.question or "One quick question to improve the picks:", includes_recs=False)
                return
            if res.status != "final" or not res.plan:
                raise RuntimeError(res.detail or "Orchestrator failed.")
            parsed = dict(res.plan)
            agent1_candidates = list(res.agent1_candidates or [])
            ok_guard, guard_err = validate_plan_guardrails(
                plan=parsed, ctx=ctx, agent1_candidates=agent1_candidates
            )
            if not ok_guard:
                agent_status_msg.set(guard_err or "Guardrail blocked the recommendation.")
                return
            prev_titles = [str(p.get("title") or "").strip() for p in (((plan_state() or {}).get("dining") or {}).get("places") or [])[:3] if isinstance(p, dict)]
            plan_state.set(parsed)
            map_places_state.set(_markers_from_candidates(agent1_candidates))
            ui.update_text("map_place_pick", value="0", session=session)
            agent_pending_question.set("")
            agent_status_msg.set(
                f"Done. session={res.session_id[:8]} turns={res.llm_turns_used} retrieval={res.retrieval_attempts}"
            )
            new_titles = [str(p.get("title") or "").strip() for p in (((parsed.get("dining") or {}).get("places")) or [])[:3] if isinstance(p, dict)]
            m = msg.lower()
            intent_refresh = any(x in m for x in ("dessert", "sweet", "cheaper", "budget", "different area", "another area", "near", "close to", "more like"))
            includes = bool(intent_refresh or (new_titles and new_titles != prev_titles))
            followup = _assistant_followup_message(ctx=ctx, user_message=msg, plan=parsed, cards_shown=includes)
            _append_chat("assistant", followup, includes_recs=includes)
            _maybe_save_durable_delta(msg=msg, ctx=ctx)
            _maybe_generate_quick_replies(ctx=ctx, plan=parsed, last_user_message=msg)
            ui.update_text("agent_chat_input", value="", session=session)
        except Exception as e:
            agent_status_msg.set(f"Send failed: {e}")

    @render.ui
    def agent_question_box():
        q = (agent_pending_question() or "").strip()
        if not q:
            return ui.div()
        return ui.div(
            ui.div("Assistant question", class_="td-output-subhead"),
            ui.p(q),
            class_="td-card",
        )

    @render.ui
    def agent_status_box():
        # Debug/status surface used inside the status panel (not the chat column).
        s = (agent_status_msg() or "").strip()
        if not s:
            return ui.div()
        return ui.div(
            ui.div("Status", class_="td-output-subhead"),
            ui.tags.pre(s, class_="td-places-error-body"),
            class_="td-places-error-banner",
        )

    @render.ui
    def food_section_ui():
        # Collapse-to-summary behavior after Generate; expand on user request.
        if not food_collapsed():
            return food_preference_combined_content()
        wm = input.when_mode()
        ws = input.when_season() if wm == "season" else None
        wmth = input.when_month() if wm == "month" else None
        ctx = build_trip_context(
            {
                "dest_country": input.dest_country(),
                "dest_country_iso2": input.dest_country_iso2(),
                "dest_city": input.dest_city(),
                "cmp1_country": input.cmp1_country(),
                "cmp1_country_iso2": input.cmp1_country_iso2(),
                "cmp1_city": input.cmp1_city(),
                "cmp2_country": input.cmp2_country(),
                "cmp2_country_iso2": input.cmp2_country_iso2(),
                "cmp2_city": input.cmp2_city(),
                "when_mode": wm,
                "when_season": ws,
                "when_month": wmth,
                "like_tags": _as_tag_list(input.like_tags()),
                "dislike_tags": _as_tag_list(input.dislike_tags()),
                "dietary_tags": _as_tag_list(input.dietary_tags()),
                "food_like_text": input.food_like_text(),
                "food_dislike_text": input.food_dislike_text(),
                "dietary_restrictions_text": input.dietary_restrictions_text(),
            }
        )
        return ui.div(
            ui.div(
                ui.p("Food preferences", class_="td-input-label td-food-row-title"),
                ui.p(_food_summary_from_ctx(ctx), class_="td-muted"),
                ui.input_action_button("btn_food_expand", "Edit food preferences", class_="btn td-btn-secondary"),
                class_="td-food-preferences-header-with-note",
            ),
            class_="td-input-group td-food-combined",
        )

    @reactive.effect
    @reactive.event(input.btn_food_expand)
    def _expand_food():
        food_collapsed.set(False)

    def _chat_place_cards_ui(*, max_cards: int = 3) -> ui.Tag:
        rows = _merge_places_rows(plan_state(), map_places_state())[:max_cards]
        if not rows:
            return ui.div()
        blocks: list[ui.Tag] = []
        for i, r in enumerate(rows):
            blocks.append(
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h4(r.get("title") or "—"),
                            ui.span(
                                _format_place_list_badge(
                                    r.get("badge"),
                                    rag_score=r.get("rag_match_score"),
                                    price_tier=r.get("price_tier"),
                                ),
                                class_="td-dining-item-badge",
                            ),
                            class_="td-dining-item-title",
                        ),
                        ui.p(r.get("note") or "", class_="td-dining-item-note"),
                        class_="td-dining-item td-dining-place-item",
                    ),
                    class_="td-agent-rec-card",
                    **{"data-td-agent-rec-idx": str(i + 1)},
                )
            )
        return ui.div(*blocks, class_="td-agent-rec-cards")

    @render.ui
    def chat_area_ui():
        # Proper chat UI: context bar + bubbles + cards + quick reply pills + pinned input.
        rows = list(chat_messages() or [])
        if not rows:
            return ui.div()

        tags = _context_tags_for_ui()
        ctx_parts: list[ui.Tag] = [ui.span("From your form:", class_="td-agent-ctx-label")]
        for t in (tags.get("location") or []):
            ctx_parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-loc"))
        for t in (tags.get("dietary") or []):
            ctx_parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-diet"))
        for t in (tags.get("like") or []):
            ctx_parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-like"))
        for t in (tags.get("dislike") or []):
            ctx_parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-dislike"))
        context_bar = ui.div(*ctx_parts, class_="td-agent-contextbar")

        header = ui.div(
            ui.div("FG", class_="td-chat-avatar"),
            ui.div(
                ui.div("Food guide", class_="td-chat-title"),
                ui.div("Personalized dining help", class_="td-chat-subtitle"),
                class_="td-chat-header-info",
            ),
            ui.tags.button("×", type="button", id="td-chat-close", class_="td-chat-close"),
            class_="td-chat-widget-header",
        )

        # Find last assistant message index for chip placement
        last_asst_idx = -1
        for i, r in enumerate(rows):
            if r.get("role") == "assistant":
                last_asst_idx = i

        bubbles: list[ui.Tag] = []
        for i, r in enumerate(rows):
            role = r.get("role")
            is_user = role == "user"
            row_cls = "td-chat-row td-chat-user" if is_user else "td-chat-row td-chat-agent"
            bubble_cls = "td-chat-bubble td-chat-bubble-user" if is_user else "td-chat-bubble td-chat-bubble-agent"
            content = ui.markdown(r.get("content") or "")

            extra = ui.div()
            if (not is_user) and bool(r.get("includes_recs")):
                extra = ui.div(_chat_place_cards_ui(max_cards=3), class_="td-chat-bubble-extra")
            if (not is_user) and i == last_asst_idx:
                chips = list(quick_replies_state() or [])
                chip_buttons = []
                for c in chips:
                    if not isinstance(c, dict):
                        continue
                    chip_buttons.append(
                        ui.tags.button(
                            str(c.get("label") or "Chip"),
                            type="button",
                            class_="td-chat-pill",
                            **{"data-td-agent-chip": str(c.get("message") or "").strip()},
                        )
                    )
                chip_row = ui.div(*chip_buttons, class_="td-chat-pill-row") if chip_buttons else ui.div()
                notice = (saved_pref_notice() or "").strip()
                save_notice_ui = ui.div(notice, class_="td-chat-save-notice") if notice else ui.div()
                recs = _chat_place_cards_ui(max_cards=3) if bool(r.get("includes_recs")) else ui.div()
                extra = ui.div(recs, chip_row, save_notice_ui, class_="td-chat-bubble-extra")

            bubbles.append(ui.div(ui.div(content, extra, class_=bubble_cls), class_=row_cls))

        drawer_open = bool(status_drawer_open())
        drawer_toggle = "▾" if drawer_open else "▸"
        drawer = ui.div(
            ui.div(
                ui.span("Agent status", class_="td-status-drawer-title"),
                ui.input_action_button(
                    "btn_toggle_status_drawer",
                    drawer_toggle,
                    class_="btn td-btn-secondary td-status-drawer-toggle",
                ),
                class_="td-status-drawer-header",
            ),
            ui.div(
                ui.output_ui("agent_status_panel_ui") if drawer_open else ui.div(),
                class_="td-status-drawer-body",
            ),
            class_="td-status-drawer",
        )

        return ui.div(
            header,
            context_bar,
            drawer,
            ui.div(*bubbles, class_="td-chat-messages"),
            ui.div(
                ui.input_text("agent_chat_input", None, value="", placeholder="Refine, ask follow-ups, or say 'done'…"),
                ui.input_action_button("btn_agent_send", "Send", class_="btn td-btn-primary-mockup"),
                class_="td-chat-inputbar",
            ),
            class_="td-chat-shell",
        )

    @reactive.effect
    @reactive.event(input.agent_quick_reply)
    def _chip_click():
        msg = (input.agent_quick_reply() or "").strip()
        if msg:
            ui.update_text("agent_chat_input", value=msg, session=session)
            # No toast: chips should feel instant and quiet.

    # Drawer replaces the old right-side status panel toggle inside the widget.
    # Keep status_panel_open reactive value for backwards compatibility (unused by widget).

    @reactive.effect
    @reactive.event(input.btn_toggle_status_drawer)
    def _toggle_status_drawer():
        status_drawer_open.set(not status_drawer_open())

    @reactive.effect
    @reactive.event(input.btn_new_location)
    def _new_location():
        # Clear destination fields only; keep saved preferences.
        ui.update_text("dest_country", value="", session=session)
        ui.update_text("dest_country_iso2", value="", session=session)
        ui.update_text("dest_city", value="", session=session)
        food_collapsed.set(False)
        chat_messages.set([])
        chat_assistant_turns.set(0)
        quick_replies_state.set([])
        agent_session_id.set("")
        agent_status_msg.set("")
        agent_pending_question.set("")
        saved_pref_notice.set("")
        ui.notification_show(ui.span("Pick a new destination, then Generate again."), type="message", duration=6, session=session)

    @render.ui
    def context_bar_ui():
        tags = _context_tags_for_ui()
        parts = [ui.span("From your form:", class_="td-agent-ctx-label")]
        for t in tags.get("location") or []:
            parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-loc"))
        for t in tags.get("dietary") or []:
            parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-diet"))
        for t in tags.get("like") or []:
            parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-like"))
        for t in tags.get("dislike") or []:
            parts.append(ui.span(str(t), class_="td-agent-ctx-tag td-agent-ctx-dislike"))
        return ui.div(*parts, class_="td-agent-contextbar")

    @render.ui
    def agent_status_panel_ui():
        tags = _context_tags_for_ui()
        # Preference match: average over top 3 place badges when possible.
        rows = _merge_places_rows(plan_state(), map_places_state())
        scores = []
        for r in rows[:3]:
            try:
                sc = float(r.get("rag_match_score"))
                if 0 <= sc <= 1:
                    scores.append(sc)
            except Exception:
                pass
        avg = round(sum(scores) / len(scores) * 100) if scores else None
        match_line = f"{avg}% avg match (top 3)" if avg is not None else "Match: —"

        # Guardrail traffic lights (green when armed; warnings if missing).
        loc_ok = bool(tags.get("location"))
        diet_list = tags.get("dietary") or []
        guard_rows = [
            ui.div(
                ui.div(class_="td-agent-dot td-agent-dot-on" if loc_ok else "td-agent-dot td-agent-dot-warn"),
                ui.span("Location filter", class_="td-agent-status-row-label"),
                ui.span(", ".join(tags.get("location") or []) or "—", class_="td-agent-status-row-value"),
                class_="td-agent-status-traffic-row",
            )
        ]
        for d in (diet_list or ["(none)"]):
            guard_rows.append(
                ui.div(
                    ui.div(class_="td-agent-dot td-agent-dot-on"),
                    ui.span("Dietary", class_="td-agent-status-row-label"),
                    ui.span(str(d), class_="td-agent-status-row-value"),
                    class_="td-agent-status-traffic-row",
                )
            )

        guard = ui.div(
            ui.div("Guardrails (blockers)", class_="td-agent-status-title"),
            *guard_rows,
            class_="td-agent-status-card",
        )
        def _pref_match_pct(label: str) -> str:
            """
            Lightweight per-preference match:
            - base on avg top-3 rag score when available
            - add small bonus if the label text appears in any of the top-3 place docs
            """
            base = avg if avg is not None else None
            if base is None:
                return "—"
            lab = (label or "").strip().lower()
            bonus = 0
            if lab:
                for r in rows[:3]:
                    blob = " ".join(
                        str(r.get(k) or "")
                        for k in ("title", "note", "address")
                    ).lower()
                    if lab in blob:
                        bonus = 6
                        break
            return f"{min(100, int(base) + bonus)}%"

        prefs = ui.div(
            ui.div("Preferences", class_="td-agent-status-title"),
            ui.div(match_line, class_="td-agent-status-row"),
            ui.div(
                *[
                    ui.div(
                        ui.span(x, class_="td-agent-status-row-label"),
                        ui.span(_pref_match_pct(x), class_="td-agent-status-row-value"),
                        class_="td-agent-status-match-row",
                    )
                    for x in (tags.get("like") or [])
                ],
                class_="td-agent-status-group",
            )
            if (tags.get("like") or [])
            else ui.div(ui.span("Likes"), ui.span("—"), class_="td-agent-status-row"),
            ui.div(
                *[
                    ui.div(
                        ui.span("Avoid: " + x, class_="td-agent-status-row-label"),
                        ui.span(_pref_match_pct(x), class_="td-agent-status-row-value"),
                        class_="td-agent-status-match-row",
                    )
                    for x in (tags.get("dislike") or [])
                ],
                class_="td-agent-status-group",
            )
            if (tags.get("dislike") or [])
            else ui.div(ui.span("Dislikes"), ui.span("—"), class_="td-agent-status-row"),
            class_="td-agent-status-card",
        )
        conv = ui.div(
            ui.div("Conversation state", class_="td-agent-status-title"),
            ui.div(f"Round {int(chat_assistant_turns() or 0)} of refinement", class_="td-agent-status-row"),
            ui.div("Awaiting user input" if (int(chat_assistant_turns() or 0) >= 1) else "Ready after Generate", class_="td-agent-status-row"),
            ui.div(f"Turns remaining: {max(0, 6 - int(chat_assistant_turns() or 0))}", class_="td-agent-status-row"),
            class_="td-agent-status-card",
        )
        return ui.div(guard, prefs, conv, ui.output_ui("agent_status_box"), class_="td-agent-status-body")

    @render.ui
    def out_friendliness():
        fr = friendliness_state()
        if fr is None:
            return ui.div(
                ui.p(
                    "Run Generate to compute travel friendliness from World Bank indicators (scores are not from the LLM).",
                    class_="td-friendliness-placeholder",
                ),
                class_="td-friendliness-body",
            )
        if not fr.ok:
            return ui.div(
                ui.p(fr.error_message or "Travel friendliness could not be computed.", class_="td-friendliness-error"),
                class_="td-friendliness-body",
            )
        pt = float(fr.primary_total or 0)
        pt = max(0.0, min(100.0, pt))
        score = int(round(pt))
        blocks = [
            ui.div(
                ui.div("Where I am going", class_="td-friendliness-section-label"),
                ui.div(str(score), class_="td-friendliness-hero-score"),
                ui.div(fr.primary_label, class_="td-friendliness-hero-country"),
                ui.p(fr.primary_summary, class_="td-friendliness-summary"),
                class_="td-friendliness-hero",
            )
        ]
        if fr.compare_rows:
            rows = [
                ui.div(
                    ui.span(row["label"], class_="td-friendliness-compare-name"),
                    ui.span(str(int(round(max(0.0, min(100.0, float(row["score"])))))), class_="td-friendliness-compare-score"),
                    class_="td-friendliness-compare-row",
                )
                for row in fr.compare_rows
            ]
            blocks.append(
                ui.div(
                    ui.div("Compared with", class_="td-friendliness-section-label"),
                    *rows,
                    class_="td-friendliness-compare",
                )
            )
        blocks.append(ui.p(fr.small_print, class_="td-friendliness-smallprint"))
        return ui.div(*blocks, class_="td-friendliness-body")

    @render.ui
    def friendliness_download_area():
        fr = friendliness_state()
        if fr is None or not fr.ok or not fr.report_html:
            return ui.div()
        return ui.download_button(
            "dl_friendliness_report",
            "Download detailed HTML report",
            class_="btn btn-sm td-btn-friendliness-dl",
        )

    @render.download(filename="travel_friendliness_report.html", media_type="text/html; charset=utf-8")
    def dl_friendliness_report():
        fr = friendliness_state()
        if fr and fr.ok and fr.report_html:
            yield fr.report_html.encode("utf-8")
        else:
            yield (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Travel friendliness</title></head>"
                "<body><p>No report yet. Run Generate with a valid destination country.</p></body></html>"
            ).encode("utf-8")
