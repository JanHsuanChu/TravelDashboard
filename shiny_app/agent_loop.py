from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import logging
import re

from shiny_app.ollama_client import extract_json_object, ollama_chat, resolved_model_agent2
from shiny_app.plan_logic import AGENT2_DINING_GROUNDING, SYSTEM_JSON_INSTRUCTION, user_prompt_from_context
from shiny_app.restaurant_rag import run_agent1_places_rag
from shiny_app.tags import DIETARY_CHOICES


LoopStatus = Literal["final", "needs_clarification", "error"]

logger = logging.getLogger(__name__)

def _norm_title(s: str) -> str:
    t = (s or "").strip().lower()
    # Unicode-safe normalization: keep letters/digits across scripts (e.g., Japanese),
    # collapse punctuation/whitespace to single spaces.
    t = re.sub(r"[^\w]+", " ", t, flags=re.UNICODE)
    return " ".join(t.split())


def _best_candidate_for_title(title: str, *, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Robust matching between Agent2 place titles and Agent1 candidate names.
    Prefer exact normalized matches, then token-overlap similarity.
    """
    t_norm = _norm_title(title)
    if not t_norm:
        return None
    by_norm: dict[str, dict[str, Any]] = {}
    for c in candidates:
        n = _norm_title(str(c.get("name") or ""))
        if n:
            by_norm.setdefault(n, c)
    if t_norm in by_norm:
        return by_norm[t_norm]

    t_tokens = set(t_norm.split())
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for n, c in by_norm.items():
        n_tokens = set(n.split())
        if not n_tokens:
            continue
        score = len(t_tokens & n_tokens) / max(1, len(t_tokens | n_tokens))
        if score > best[0]:
            best = (score, c)
    if best[1] is None or best[0] < 0.35:
        return None
    best_tokens = set(_norm_title(str(best[1].get("name") or "")).split())
    # For languages without spaces, the whole name can be one token; allow that as overlap.
    if not (t_tokens & best_tokens):
        return None
    shared = {x for x in (t_tokens & best_tokens) if len(x) >= 2}
    return best[1] if shared else best[1]


def _candidate_note(c: dict[str, Any]) -> str:
    sn = c.get("review_snippets") or []
    if isinstance(sn, list):
        for s in sn:
            t = str(s or "").strip()
            if t:
                return t
    es = str(c.get("editorial_summary") or "").strip()
    return es


def _badge_from_rag_score(v: Any) -> str:
    try:
        x = float(v)
    except Exception:
        return "—"
    if not (0 <= x <= 1):
        return "—"
    return f"{round(x * 100)}% match"


def _snap_dining_places_to_candidates(
    *,
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> bool:
    """
    Deterministic self-heal: ensure dining.places are backed by Agent1 candidates.
    This avoids brittle name drift causing hard guardrail failures.
    """
    dining = plan.get("dining") if isinstance(plan.get("dining"), dict) else None
    if dining is None:
        return False
    places = dining.get("places") if isinstance(dining.get("places"), list) else None
    if not places or not candidates:
        return False

    used_names: set[str] = set()
    changed = False
    for p in places:
        if not isinstance(p, dict):
            continue
        title = str(p.get("title") or "").strip()
        cand = _best_candidate_for_title(title, candidates=candidates) if title else None
        if cand is None:
            # Pick next unused candidate (already destination-filtered upstream).
            cand = next((c for c in candidates if str(c.get("name") or "").strip() and str(c.get("name") or "").strip() not in used_names), None)
        if cand is None:
            continue
        name = str(cand.get("name") or "").strip()
        if not name:
            continue
        used_names.add(name)

        if title != name:
            p["title"] = name
            changed = True
        # Recompute badge/note to align with snapped candidate.
        new_badge = _badge_from_rag_score(cand.get("rag_match_score"))
        if p.get("badge") != new_badge and new_badge != "—":
            p["badge"] = new_badge
            changed = True
        new_note = _candidate_note(cand)
        if new_note and p.get("note") != new_note:
            p["note"] = new_note
            changed = True

    return changed


@dataclass
class LoopBudgets:
    min_llm_turns: int = 2
    max_llm_turns: int = 6
    max_retrieval_reruns: int = 2


@dataclass
class LoopResult:
    status: LoopStatus
    session_id: str
    plan: dict[str, Any] | None
    agent1_candidates: list[dict[str, Any]]
    question: str | None = None
    detail: str | None = None
    llm_turns_used: int = 0
    retrieval_attempts: int = 0


def new_session_id() -> str:
    return str(uuid.uuid4())


def _safe_json_dumps(obj: Any, *, max_chars: int = 4000) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(s) > max_chars:
        return s[:max_chars] + "…"
    return s


def _should_ask_quality_question(ctx: dict[str, Any]) -> str | None:
    """Return a single targeted question, or None if enough signal."""
    food = (ctx.get("food") or {}) if isinstance(ctx.get("food"), dict) else {}
    like_tags = list(food.get("like_tags") or [])
    dislike_tags = list(food.get("dislike_tags") or [])
    dietary_tags = list(food.get("dietary_tags") or [])
    like_text = (food.get("food_like_text") or "").strip()
    dislike_text = (food.get("food_dislike_text") or "").strip()

    if dietary_tags:
        # Dietary is a hard constraint; don't ask for it as “quality”.
        return None

    has_any = bool(like_tags or dislike_tags or like_text or dislike_text)
    if not has_any:
        return "What kind of food are you in the mood for (2–3 cuisines or dishes), and what should I avoid?"
    if not like_tags and not like_text:
        return "What are 2–3 foods/cuisines you *love* right now for this trip?"
    return None


def _dietary_tags_from_ctx(ctx: dict[str, Any]) -> list[str]:
    food = (ctx.get("food") or {}) if isinstance(ctx.get("food"), dict) else {}
    raw = food.get("dietary_tags") or []
    out: list[str] = []
    for x in raw if isinstance(raw, list) else [raw]:
        s = str(x).strip()
        if s and s in DIETARY_CHOICES:
            out.append(s)
    return out


def _destination_location_tokens(ctx: dict[str, Any]) -> tuple[str, str]:
    dest = (ctx.get("destination") or {}) if isinstance(ctx.get("destination"), dict) else {}
    city = str(dest.get("city") or "").strip()
    country = str(dest.get("country") or "").strip()
    return city, country


def _candidate_matches_destination(c: dict[str, Any], *, city: str, country: str) -> bool:
    """Hard location check using formatted address. Conservative: if uncertain, treat as mismatch."""
    addr = str(c.get("formatted_address") or "").strip().lower()
    if not addr:
        return False
    city_l = (city or "").strip().lower()
    country_l = (country or "").strip().lower()
    # If city provided, require either city or country to appear.
    if city_l:
        return (city_l in addr) or (country_l and country_l in addr)
    # If only country provided, require country string in address.
    if country_l:
        return country_l in addr
    # No destination tokens: cannot validate.
    return False


def _disallowed_food_tokens(dietary_tags: list[str]) -> set[str]:
    """Coarse deterministic blockers for dish text. Unknown => block by asking clarifying Q."""
    tags = set(dietary_tags or [])
    banned: set[str] = set()
    if "vegetarian" in tags or "vegan" in tags:
        banned |= {
            "beef",
            "pork",
            "chicken",
            "duck",
            "lamb",
            "goat",
            "bacon",
            "ham",
            "sausage",
            "prosciutto",
            "salami",
            "pepperoni",
            "fish",
            "salmon",
            "tuna",
            "sardine",
            "anchovy",
            "shrimp",
            "prawn",
            "crab",
            "lobster",
            "oyster",
            "mussel",
            "clam",
        }
    if "vegan" in tags:
        banned |= {"egg", "eggs", "milk", "cheese", "butter", "yogurt", "cream", "honey"}
    return banned


def validate_plan_guardrails(
    *,
    plan: dict[str, Any],
    ctx: dict[str, Any],
    agent1_candidates: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """
    Hard guardrails:
    - Places must be a subset of Agent 1 candidates (by exact name/title).
    - Dietary tags are enforced by a coarse token blacklist over dish titles/notes.

    If a rule fails, return (False, reason). The Orchestrator must not pass recommendations.
    """
    dining = plan.get("dining") if isinstance(plan.get("dining"), dict) else {}
    places = dining.get("places") if isinstance(dining.get("places"), list) else []
    dishes = dining.get("dishes") if isinstance(dining.get("dishes"), list) else []

    allowed_place_titles = {
        (c.get("name") or "").strip() for c in agent1_candidates if (c.get("name") or "").strip()
    }
    city, country = _destination_location_tokens(ctx)
    # Validate that any recommended place is not only from Agent 1, but also in the destination.
    for p in places:
        if not isinstance(p, dict):
            continue
        t = (p.get("title") or "").strip()
        if not t:
            continue
        cand = _best_candidate_for_title(t, candidates=agent1_candidates) if agent1_candidates else None
        if allowed_place_titles and cand is None:
            return False, f"Guardrail: dining.places includes {t!r} not present in Agent 1 candidates."
        if city or country:
            if not cand:
                return False, f"Guardrail: could not locate candidate details for {t!r}."
            if not _candidate_matches_destination(cand, city=city, country=country):
                return (
                    False,
                    f"Guardrail: place {t!r} appears outside destination (addr={cand.get('formatted_address')!r}).",
                )

    dietary_tags = _dietary_tags_from_ctx(ctx)
    if dietary_tags:
        banned = _disallowed_food_tokens(dietary_tags)
        for d in dishes:
            if not isinstance(d, dict):
                continue
            blob = " ".join(str(d.get(k) or "") for k in ("title", "note")).lower()
            for tok in banned:
                if tok in blob:
                    return (
                        False,
                        f"Guardrail: dietary={dietary_tags} but dish appears non-compliant (token {tok!r}).",
                    )
    return True, None


def run_orchestrator_loop(
    *,
    ctx: dict[str, Any],
    architecture_md: str,
    destination_label: str,
    preference_narrative: str,
    budgets: LoopBudgets | None = None,
    session_id: str | None = None,
    user_message: str | None = None,
) -> LoopResult:
    """
    Additive wrapper that coordinates:
    - Agent 1: Places + embeddings ranking (deterministic)
    - Agent 2: Plan LLM JSON

    It may pause for a clarifying question and should be resumed by passing `session_id` and `user_message`.
    """
    b = budgets or LoopBudgets()
    sid = (session_id or "").strip() or new_session_id()
    logger.info(
        "loop_start session=%s has_resume=%s budgets=%s",
        sid[:8],
        bool(session_id),
        {"min": b.min_llm_turns, "max": b.max_llm_turns, "reruns": b.max_retrieval_reruns},
    )

    # If resuming and user gave new info, fold it into a lightweight preference narrative tail.
    pref = (preference_narrative or "").strip()
    if user_message and user_message.strip():
        pref = (pref + " " + f"User follow-up: {user_message.strip()}").strip()

    # Note: Conversation starts after Generate (UI). This loop focuses on producing a compliant plan JSON.

    # Step 1: retrieval (Agent 1) with bounded reruns.
    candidates: list[dict[str, Any]] = []
    retrieval_attempts = 0
    last_err: str | None = None
    city, country = _destination_location_tokens(ctx)
    for attempt in range(1, max(1, b.max_retrieval_reruns) + 2):
        retrieval_attempts = attempt
        logger.info("retrieve_attempt session=%s attempt=%s", sid[:8], attempt)
        candidates, last_err = run_agent1_places_rag(
            destination_label=destination_label,
            preference_narrative=pref,
            learned_weights=None,
        )
        if candidates and (city or country):
            before = len(candidates)
            candidates = [c for c in candidates if _candidate_matches_destination(c, city=city, country=country)]
            if len(candidates) != before:
                logger.info(
                    "location_filter session=%s before=%s after=%s city=%s country=%s",
                    sid[:8],
                    before,
                    len(candidates),
                    bool(city),
                    bool(country),
                )
        logger.info(
            "candidates_summary session=%s n=%s err=%s",
            sid[:8],
            len(candidates or []),
            bool(last_err),
        )
        # If Places is not configured or returns empty, do not spin forever.
        if candidates:
            break
        if last_err:
            break
        if attempt >= 1 + b.max_retrieval_reruns:
            break

    # Step 2: plan LLM (Agent 2). Keep messages stable; do not alter Agent 2 schema.
    city, country = _destination_location_tokens(ctx)
    when = (ctx.get("when") or {}) if isinstance(ctx.get("when"), dict) else {}
    food = (ctx.get("food") or {}) if isinstance(ctx.get("food"), dict) else {}
    silent_facts = {
        "destination_city": city,
        "destination_country": country,
        "when_mode": when.get("mode"),
        "when_season": when.get("season"),
        "when_month": when.get("month"),
        "dietary_tags": list(food.get("dietary_tags") or []),
        "dislike_tags": list(food.get("dislike_tags") or []),
        "dietary_restrictions": (food.get("dietary_restrictions") or ""),
    }

    system_parts = [
        (
            "Silent context (do not ask the user to repeat these facts unless the form changes):\n"
            + _safe_json_dumps(silent_facts, max_chars=2000)
            + "\n\n"
            "Policy: never recommend a place outside the destination; never recommend non-compliant dishes.\n\n"
            f"Architecture context:\n\n{architecture_md}\n\n{SYSTEM_JSON_INSTRUCTION}"
        ),
    ]
    if candidates:
        system_parts.append(AGENT2_DINING_GROUNDING.strip())

    messages = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": user_prompt_from_context(ctx, candidates)},
    ]

    # Bound the “agentic” part: allow 1–N LLM turns; today we do draft + optional self-check.
    llm_turns_used = 0
    raw = ""
    parsed: dict[str, Any] | None = None
    start = time.time()
    for _ in range(max(1, b.max_llm_turns)):
        llm_turns_used += 1
        logger.info("agent2_call session=%s turn=%s model=%s", sid[:8], llm_turns_used, resolved_model_agent2())
        raw = ollama_chat(messages, model=resolved_model_agent2())
        parsed = extract_json_object(raw)
        if parsed and isinstance(parsed, dict):
            # Deterministic self-heal for place-title drift before guardrail validation.
            try:
                if _snap_dining_places_to_candidates(plan=parsed, candidates=candidates):
                    logger.info("snap_places session=%s changed=true", sid[:8])
            except Exception as snap_exc:
                logger.warning("snap_places session=%s err=%s", sid[:8], snap_exc)

            # Guardrail check: if it fails, instruct the model to repair and try again.
            ok_guard, guard_err = validate_plan_guardrails(
                plan=parsed, ctx=ctx, agent1_candidates=candidates
            )
            if not ok_guard:
                logger.info("guardrail_result session=%s pass=false reason=%s", sid[:8], guard_err or "unknown")
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your JSON failed a hard guardrail and must be fixed before it can be shown.\n"
                            f"- Failure: {guard_err}\n\n"
                            "For dining.places, choose ONLY from agent1_restaurants and copy the name EXACTLY.\n"
                            "Return corrected JSON only. If dietary tags imply a restriction, remove or replace any non-compliant "
                            "dishes with compliant alternatives (do not mention the guardrail)."
                        ),
                    }
                )
                continue

            logger.info("guardrail_result session=%s pass=true", sid[:8])

            # stop policy: if min turns satisfied, accept.
            if llm_turns_used >= max(1, b.min_llm_turns):
                logger.info("decision session=%s action=finalize reason=min_turns_met", sid[:8])
                break

            # else: push a self-check instruction (still useful for references/format polish).
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Quick self-check: ensure dining places are only from agent1_restaurants, "
                        "respect dietary tags/restrictions, and keep notes factual. Return corrected JSON only."
                    ),
                }
            )
            continue
        # If model didn't return JSON, nudge once.
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": "Return ONLY one JSON object matching the schema. No markdown. Try again.",
            }
        )

    if not parsed or not isinstance(parsed, dict):
        logger.warning("loop_error session=%s reason=invalid_json", sid[:8])
        return LoopResult(
            status="error",
            session_id=sid,
            plan=None,
            agent1_candidates=candidates,
            detail=f"Model did not return valid JSON. last_output={_safe_json_dumps(raw)}",
            llm_turns_used=llm_turns_used,
            retrieval_attempts=retrieval_attempts,
        )

    # If we have JSON but still failing guardrails after all turns, block.
    ok_guard, guard_err = validate_plan_guardrails(plan=parsed, ctx=ctx, agent1_candidates=candidates)
    if not ok_guard:
        logger.warning("loop_error session=%s reason=guardrail_unresolved", sid[:8])
        return LoopResult(
            status="error",
            session_id=sid,
            plan=None,
            agent1_candidates=candidates,
            detail=guard_err or "Guardrail failure could not be resolved within the turn budget.",
            llm_turns_used=llm_turns_used,
            retrieval_attempts=retrieval_attempts,
        )

    # Note: guardrails are implemented in server-side validation layer (separate step).
    parsed = dict(parsed)
    parsed.pop("friendliness", None)
    elapsed = round((time.time() - start) * 1000)
    parsed.setdefault("_meta", {})
    if isinstance(parsed["_meta"], dict):
        parsed["_meta"].update(
            {
                "session_id": sid,
                "llm_turns_used": llm_turns_used,
                "retrieval_attempts": retrieval_attempts,
                "elapsed_ms": elapsed,
            }
        )

    return LoopResult(
        status="final",
        session_id=sid,
        plan=parsed,
        agent1_candidates=candidates,
        llm_turns_used=llm_turns_used,
        retrieval_attempts=retrieval_attempts,
    )

