# server.py
# Reactive server: load Supabase on connect, save preferences, generate via Ollama Cloud.

from __future__ import annotations

import os
import re
from urllib.parse import quote

from shiny import reactive, render, ui

import tags as tagdata
from context import load_architecture_markdown
from ollama_client import extract_json_object, ollama_chat
from plan_logic import (
    AGENT2_DINING_GROUNDING,
    SYSTEM_JSON_INSTRUCTION,
    build_trip_context,
    user_prompt_from_context,
)
from restaurant_rag import (
    preference_narrative_from_supabase_row,
    preference_narrative_from_trip_food,
    run_agent1_places_rag,
)
from supabase_client import (
    fetch_user_and_latest_preference,
    get_or_create_user,
    insert_preference,
    normalize_email,
)
from travel_friendliness.pipeline import FriendlinessResult, compute_friendliness
from validators import validate_food_text, validate_when_mode, valid_email_shape


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
            "news": "No live headlines yet.",
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


def _format_essential(plan: dict) -> str:
    e = plan.get("essential") or {}
    return "\n\n".join(
        [
            f"**Travel advisory**  \n{e.get('travel_advisory', '—')}",
            f"**Weather**  \n{e.get('weather', '—')}",
            f"**News**  \n{e.get('news', '—')}",
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

        dc = (input.dest_country() or "").strip()
        if not dc:
            ui.notification_show(
                ui.span("Enter a destination country before generating."),
                type="warning",
                session=session,
            )
            return

        err = _validate_food_fields(input)
        if err:
            ui.notification_show(ui.span(err), type="error", session=session)
            return

        fr = compute_friendliness(
            dc,
            (input.cmp1_country() or "").strip(),
            (input.cmp2_country() or "").strip(),
        )
        friendliness_state.set(fr)
        if not fr.ok and fr.error_message:
            ui.notification_show(
                ui.span(f"Travel friendliness: {fr.error_message}"),
                type="warning",
                session=session,
            )

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
                "dest_city": input.dest_city(),
                "cmp1_country": input.cmp1_country(),
                "cmp1_city": input.cmp1_city(),
                "cmp2_country": input.cmp2_country(),
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
        if os.environ.get("GOOGLE_PLACES_API_KEY", "").strip():
            agent1_candidates, rag_err = run_agent1_places_rag(
                destination_label=dest_label or (input.dest_country() or "").strip(),
                preference_narrative=pref_narrative,
            )
            if rag_err:
                places_error_state.set(rag_err)
                ui.notification_show(
                    ui.span(
                        "Restaurant retrieval failed — full message is in the red box "
                        "under Dining — recommended places (scroll if needed)."
                    ),
                    type="warning",
                    duration=12,
                    session=session,
                )

        arch = load_architecture_markdown()
        system_parts = [
            f"Architecture context:\n\n{arch}\n\n{SYSTEM_JSON_INSTRUCTION}",
        ]
        if agent1_candidates:
            system_parts.append(AGENT2_DINING_GROUNDING.strip())
        messages = [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {
                "role": "user",
                "content": user_prompt_from_context(ctx, agent1_candidates),
            },
        ]
        try:
            raw = ollama_chat(messages)
            parsed = extract_json_object(raw)
            if parsed and isinstance(parsed, dict):
                parsed = dict(parsed)
                parsed.pop("friendliness", None)
                plan_state.set(parsed)
                map_places_state.set(_markers_from_candidates(agent1_candidates))
                ui.update_text("map_place_pick", value="0", session=session)
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
            else:
                ui.notification_show(
                    ui.span("Model did not return valid JSON; showing previous outputs."),
                    type="warning",
                    session=session,
                )
        except Exception as e:
            ui.notification_show(
                ui.span(f"Generate failed (check OLLAMA_API_KEY): {e}"),
                type="error",
                session=session,
            )

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
