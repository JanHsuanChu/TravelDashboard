# server.py
# Reactive server: load Supabase on connect, save preferences, generate via Ollama Cloud.

from __future__ import annotations

import pandas as pd
from shiny import reactive, render, ui

from context import load_architecture_markdown
from ollama_client import extract_json_object, ollama_chat
from plan_logic import SYSTEM_JSON_INSTRUCTION, build_trip_context, user_prompt_from_context
from supabase_client import fetch_recent_preferences, get_or_create_user, insert_preference
from validators import validate_food_text, validate_when_mode


def _as_tag_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val]
    return [str(val)] if val else []


def _default_plan() -> dict:
    return {
        "dining": {
            "dishes": [
                {"title": "Sample dish", "note": "Run Generate with Ollama configured.", "badge": "—"},
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


def _format_dining(plan: dict) -> str:
    d = plan.get("dining") or {}
    lines = ["#### Dishes", ""]
    for item in d.get("dishes") or []:
        lines.append(
            f"- **{item.get('title', '')}** _{item.get('badge', '')}_  \n  {item.get('note', '')}"
        )
    lines.extend(["", "#### Places", ""])
    for item in d.get("places") or []:
        lines.append(
            f"- **{item.get('title', '')}** _{item.get('badge', '')}_  \n  {item.get('note', '')}"
        )
    return "\n".join(lines) if lines else "_No data._"


def _format_essential(plan: dict) -> str:
    e = plan.get("essential") or {}
    return "\n\n".join(
        [
            f"**Travel advisory**  \n{e.get('travel_advisory', '—')}",
            f"**Weather**  \n{e.get('weather', '—')}",
            f"**News**  \n{e.get('news', '—')}",
        ]
    )


def _format_friendliness(plan: dict) -> str:
    f = plan.get("friendliness") or {}
    p = f.get("primary") or {}
    lines = [
        f"### Primary destination  \n**{p.get('score', '—')}** — {p.get('label', '')}",
        "",
        "### Comparisons",
        "",
    ]
    for c in f.get("comparisons") or []:
        lines.append(f"- **{c.get('label', '')}:** {c.get('score', '—')}")
    return "\n".join(lines)


def server(input, output, session):
    pref_rows = reactive.Value([])
    load_error = reactive.Value("")
    plan_state = reactive.Value(_default_plan())

    @reactive.effect
    def _load_on_start():
        try:
            pref_rows.set(fetch_recent_preferences(40))
            load_error.set("")
        except Exception as e:
            load_error.set(f"Could not load preferences: {e}")

    @render.table
    def prefs_table():
        rows = pref_rows()
        if not rows:
            return pd.DataFrame({"message": ["No preference rows loaded yet."]})
        slim = []
        for r in rows:
            ft = r.get("food_tags")
            slim.append(
                {
                    "id": r.get("preference_id"),
                    "created": str(r.get("created_at", ""))[:19],
                    "like_txt": (r.get("food_like_text") or "")[:40],
                    "tags": str(ft)[:80],
                }
            )
        return pd.DataFrame(slim)

    @render.text
    def load_status():
        return load_error()

    @reactive.effect
    @reactive.event(input.btn_save)
    def _save_food():
        fn = (input.user_first_name() or "").strip()
        em = (input.user_email() or "").strip()
        if not fn or not em:
            ui.notification_show(
                ui.span("Enter first name and email before saving."),
                type="warning",
                session=session,
            )
            return

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
                ui.notification_show(ui.span(err), type="error", session=session)
                return

        tags = {
            "like": _as_tag_list(input.like_tags()),
            "dislike": _as_tag_list(input.dislike_tags()),
            "dietary": _as_tag_list(input.dietary_tags()),
        }
        try:
            uid = get_or_create_user(email=em, first_name=fn)
            insert_preference(
                user_id=uid,
                food_like_text=lt or None,
                food_dislike_text=dt or None,
                dietary_restrictions=dr or None,
                food_tags=tags,
            )
            pref_rows.set(fetch_recent_preferences(40))
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
        arch = load_architecture_markdown()
        messages = [
            {
                "role": "system",
                "content": f"Architecture context:\n\n{arch}\n\n{SYSTEM_JSON_INSTRUCTION}",
            },
            {"role": "user", "content": user_prompt_from_context(ctx)},
        ]
        try:
            raw = ollama_chat(messages)
            parsed = extract_json_object(raw)
            if parsed and isinstance(parsed, dict):
                plan_state.set(parsed)
                ui.notification_show(ui.span("Updated outputs from model."), type="message", session=session)
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
    def out_dining():
        return ui.markdown(_format_dining(plan_state()))

    @render.ui
    def out_essential():
        return ui.markdown(_format_essential(plan_state()))

    @render.ui
    def out_friendliness():
        return ui.markdown(_format_friendliness(plan_state()))
