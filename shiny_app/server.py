# server.py
# Reactive server: load Supabase on connect, save preferences, generate via Ollama Cloud.

from __future__ import annotations

from shiny import reactive, render, ui

import tags as tagdata
from context import load_architecture_markdown
from ollama_client import extract_json_object, ollama_chat
from plan_logic import SYSTEM_JSON_INSTRUCTION, build_trip_context, user_prompt_from_context
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
                parsed = dict(parsed)
                parsed.pop("friendliness", None)
                plan_state.set(parsed)
                if skipped_persist:
                    ui.notification_show(
                        ui.span(
                            "Recommendations updated. Add your first name and email to save these preferences for next time.",
                        ),
                        type="message",
                        session=session,
                    )
                else:
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
