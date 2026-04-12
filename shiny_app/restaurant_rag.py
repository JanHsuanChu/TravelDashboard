# restaurant_rag.py
# Agent 1: Google Places (New) + semantic ranking (embedding RAG pattern from dsai/07_rag lab_embed_rag.py).
# Agent 2 consumes the structured candidate list via the LLM user prompt (plan_logic).

from __future__ import annotations

import re
from typing import Any

import numpy as np

import google_places_client as places
import tags as tagdata

_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer

        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


def _embed_texts(texts: list[str]) -> np.ndarray:
    m = _get_embed_model()
    vecs = m.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    if vecs.ndim == 1:
        vecs = vecs.reshape(1, -1)
    return vecs.astype(np.float64)


def _cosine_scores(query_vec: np.ndarray, doc_matrix: np.ndarray) -> np.ndarray:
    q = query_vec.flatten()
    d = doc_matrix
    qn = np.linalg.norm(q)
    dn = np.linalg.norm(d, axis=1)
    dn = np.where(dn == 0, 1e-12, dn)
    sim = (d @ q) / (qn * dn + 1e-12)
    return sim


def _tag_labels(slugs: list[str], choices: dict[str, str]) -> list[str]:
    return [choices[s] for s in slugs if s in choices]


def preference_narrative_from_supabase_row(pref: dict[str, Any] | None) -> str:
    """Human-readable preference string from a preference table row (Supabase)."""
    if not pref:
        return ""
    ft = pref.get("food_tags") or {}
    like = _tag_labels(list(ft.get("like") or []), tagdata.FOOD_LIKE_CHOICES)
    dislike = _tag_labels(list(ft.get("dislike") or []), tagdata.FOOD_DISLIKE_CHOICES)
    dietary = _tag_labels(list(ft.get("dietary") or []), tagdata.DIETARY_CHOICES)
    parts: list[str] = []
    if like:
        parts.append("Food I like (tags): " + ", ".join(like) + ".")
    if dislike:
        parts.append("Food I dislike (tags): " + ", ".join(dislike) + ".")
    if dietary:
        parts.append("Dietary: " + ", ".join(dietary) + ".")
    lt = (pref.get("food_like_text") or "").strip()
    dt = (pref.get("food_dislike_text") or "").strip()
    dr = (pref.get("dietary_restrictions") or "").strip()
    if lt:
        parts.append(f"More about likes: {lt}")
    if dt:
        parts.append(f"More about dislikes: {dt}")
    if dr:
        parts.append(f"Restrictions / allergies: {dr}")
    return " ".join(parts).strip()


def preference_narrative_from_trip_food(food: dict[str, Any]) -> str:
    """Same shape as build_trip_context()['food'] when no DB row is used."""
    like = _tag_labels(list(food.get("like_tags") or []), tagdata.FOOD_LIKE_CHOICES)
    dislike = _tag_labels(list(food.get("dislike_tags") or []), tagdata.FOOD_DISLIKE_CHOICES)
    dietary = _tag_labels(list(food.get("dietary_tags") or []), tagdata.DIETARY_CHOICES)
    parts: list[str] = []
    if like:
        parts.append("Food I like (tags): " + ", ".join(like) + ".")
    if dislike:
        parts.append("Food I dislike (tags): " + ", ".join(dislike) + ".")
    if dietary:
        parts.append("Dietary: " + ", ".join(dietary) + ".")
    lt = (food.get("food_like_text") or "").strip()
    dt = (food.get("food_dislike_text") or "").strip()
    dr = (food.get("dietary_restrictions") or "").strip()
    if lt:
        parts.append(f"More about likes: {lt}")
    if dt:
        parts.append(f"More about dislikes: {dt}")
    if dr:
        parts.append(f"Restrictions / allergies: {dr}")
    return " ".join(parts).strip()


# Google Text Search limit is generous; keep queries short and readable.
_PLACES_TEXT_QUERY_MAX = 200
_KEYWORD_BOOST_PER_HIT = 0.04
_KEYWORD_BOOST_CAP = 0.14

_FOOD_QUERY_STOPWORDS = frozenset(
    """
    the and for with that this from have has are was were been being
    food like likes love enjoy want some any very also not but just more
    about their they them when where what which who how than then only
    into over such both each few other same such than too can could would
    should good great really nice best favorite favourite
    """.split()
)


def _segment_after_prefix(narrative: str, start: str, end_markers: tuple[str, ...]) -> str:
    """Slice narrative after `start` until the earliest `end_markers` substring (or end)."""
    n = narrative or ""
    i = n.find(start)
    if i < 0:
        return ""
    chunk = n[i + len(start) :].strip()
    if not chunk:
        return ""
    cut = len(chunk)
    low_chunk = chunk.lower()
    for em in end_markers:
        j = low_chunk.find(em.lower())
        if j >= 0:
            cut = min(cut, j)
    return chunk[:cut].strip()


def _extract_likes_phrase(narrative: str) -> str:
    """Free-text and tag labels from 'Food I like' parts of the preference narrative."""
    n = (narrative or "").strip()
    if not n:
        return ""
    parts: list[str] = []
    m = re.search(r"Food I like \(tags\):\s*([^.]+)\.", n)
    if m:
        tag_blob = m.group(1).strip()
        if tag_blob:
            parts.append(tag_blob)
    free = _segment_after_prefix(
        n,
        "More about likes:",
        ("More about dislikes:", "Restrictions / allergies:", "Dietary:"),
    )
    if free:
        parts.append(free)
    return " ".join(parts).strip()


def _likes_search_query_fragment(narrative: str) -> str:
    """Short phrase for Places textQuery (dish/cuisine hints from likes)."""
    raw = _extract_likes_phrase(narrative)
    if not raw:
        return ""
    one_line = re.sub(r"\s+", " ", raw).strip()
    if len(one_line) > 120:
        one_line = one_line[:119].rsplit(" ", 1)[0].strip() or one_line[:120]
    return one_line


def _preference_keyword_tokens(narrative: str) -> list[str]:
    """Tokens from likes text for light lexical re-ranking (embedding stays primary)."""
    blob = _extract_likes_phrase(narrative)
    if not blob:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for tok in re.findall(r"[a-zA-Z]{3,}", blob.lower()):
        if tok in _FOOD_QUERY_STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    for tok in re.findall(r"[\u4e00-\u9fff]{2,}", blob):
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out[:24]


def _keyword_hit_count(doc: str, tokens: list[str]) -> int:
    if not doc or not tokens:
        return 0
    d = doc.lower()
    return sum(1 for t in tokens if t.lower() in d or t in doc)


def _merge_places_by_resource(batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for p in batch:
            key = (p.get("name") or "").strip()
            if key and key not in by_key:
                by_key[key] = p
    return list(by_key.values())


def _place_search_document(p: dict[str, Any]) -> str:
    name = places.localized_text(p.get("displayName"))
    addr = (p.get("formattedAddress") or "").strip()
    summary = places.localized_text(p.get("editorialSummary"))
    types = p.get("types") or []
    type_str = ", ".join(str(t) for t in types[:8] if t and t != "restaurant")
    rating = p.get("rating")
    urc = p.get("userRatingCount")
    bits = [name, addr, type_str, summary]
    if rating is not None:
        bits.append(f"Rating {rating} ({urc or 0} reviews).")
    return " ".join(b for b in bits if b).strip()


def _price_tier_from_google_level(level: Any) -> str:
    """Map Places API (New) PriceLevel to $ / $$ / $$$."""
    if level is None:
        return ""
    s = str(level).strip()
    if not s or s == "PRICE_LEVEL_UNSPECIFIED":
        return ""
    m = {
        "PRICE_LEVEL_FREE": "$",
        "PRICE_LEVEL_INEXPENSIVE": "$",
        "PRICE_LEVEL_MODERATE": "$$",
        "PRICE_LEVEL_EXPENSIVE": "$$$",
        "PRICE_LEVEL_VERY_EXPENSIVE": "$$$",
    }
    return m.get(s, "")


def _review_snippets_from_detail(detail: dict[str, Any], max_reviews: int = 4, max_chars: int = 280) -> list[str]:
    out: list[str] = []
    for rev in (detail.get("reviews") or [])[:max_reviews]:
        t = places.localized_text((rev.get("text") or {}))
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            continue
        if len(t) > max_chars:
            t = t[: max_chars - 1] + "…"
        out.append(t)
    return out


def _candidate_from_detail(detail: dict[str, Any], *, rag_score: float | None) -> dict[str, Any]:
    name = places.localized_text(detail.get("displayName"))
    loc = detail.get("location") if isinstance(detail.get("location"), dict) else {}
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    try:
        lat_f = float(lat) if lat is not None else None
        lng_f = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat_f, lng_f = None, None
    return {
        "place_resource_name": detail.get("name") or "",
        "name": name,
        "formatted_address": (detail.get("formattedAddress") or "").strip(),
        "latitude": lat_f,
        "longitude": lng_f,
        "rating": detail.get("rating"),
        "user_rating_count": detail.get("userRatingCount"),
        "types": list(detail.get("types") or []),
        "editorial_summary": places.localized_text(detail.get("editorialSummary")),
        "review_snippets": _review_snippets_from_detail(detail),
        "website_uri": (detail.get("websiteUri") or "").strip(),
        "google_maps_uri": (detail.get("googleMapsUri") or "").strip(),
        "price_tier": _price_tier_from_google_level(detail.get("priceLevel")),
        "rag_match_score": round(rag_score, 4) if rag_score is not None else None,
    }


def run_agent1_places_rag(
    *,
    destination_label: str,
    preference_narrative: str,
    api_key: str | None = None,
    top_k: int = 5,
    search_page_size: int = 20,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Retrieve restaurant Places, rank by embedding similarity to preference + destination (RAG retrieval).
    Uses Google Text Search with the destination plus, when present, dish/cuisine hints from "Food I like"
    free text and tags — not only the generic query "restaurants in {dest}".
    Returns (candidates_for_agent2, error_message_or_none).
    """
    pref = (preference_narrative or "").strip()
    dest = (destination_label or "").strip()
    query = f"{pref} Looking for restaurants in {dest}." if pref else f"Restaurants matching traveler tastes in {dest}."

    like_fragment = _likes_search_query_fragment(pref)
    text_queries: list[str] = [f"restaurants in {dest}"]
    if like_fragment:
        dish_q = f"{like_fragment} {dest}".strip()
        if len(dish_q) > _PLACES_TEXT_QUERY_MAX:
            dish_q = dish_q[: _PLACES_TEXT_QUERY_MAX - 1].rsplit(" ", 1)[0].strip()
        if dish_q and dish_q != text_queries[0]:
            text_queries.append(dish_q)

    batches: list[list[dict[str, Any]]] = []
    search_err: str | None = None
    for tq in text_queries:
        try:
            batches.append(
                places.search_restaurants(
                    tq,
                    api_key=api_key,
                    page_size=search_page_size,
                )
            )
        except Exception as e:
            search_err = str(e)
            batches.append([])

    raw_places = _merge_places_by_resource(batches)
    if not raw_places and search_err:
        return [], f"Google Places search failed: {search_err}"
    if not raw_places:
        return [], "Google Places returned no restaurants for this destination."

    docs: list[str] = []
    for p in raw_places:
        d = _place_search_document(p)
        docs.append(d if d else places.localized_text(p.get("displayName")))

    try:
        qv = _embed_texts([query])
        dm = _embed_texts(docs)
        scores = _cosine_scores(qv[0], dm)
    except Exception as e:
        return [], f"Embedding model (sentence-transformers) failed: {e}"

    kw_tokens = _preference_keyword_tokens(pref)
    if kw_tokens:
        boosts = np.array([_keyword_hit_count(docs[i], kw_tokens) for i in range(len(docs))], dtype=np.float64)
        scores = scores + np.minimum(_KEYWORD_BOOST_CAP, boosts * _KEYWORD_BOOST_PER_HIT)

    order = np.argsort(-scores)
    seen: set[str] = set()
    ordered_names: list[tuple[str, float]] = []
    for idx in order.tolist():
        p = raw_places[idx]
        resource = (p.get("name") or "").strip()
        if not resource or resource in seen:
            continue
        seen.add(resource)
        ordered_names.append((resource, float(scores[idx])))
        if len(ordered_names) >= max(top_k * 3, top_k):
            break

    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    for resource, sc in ordered_names:
        if len(candidates) >= top_k:
            break
        try:
            detail = places.get_place_details(resource, api_key=api_key)
        except Exception as e:
            errors.append(str(e))
            continue
        candidates.append(_candidate_from_detail(detail, rag_score=sc))

    if not candidates and errors:
        return [], f"Place details failed: {errors[0]}"

    return candidates, None
