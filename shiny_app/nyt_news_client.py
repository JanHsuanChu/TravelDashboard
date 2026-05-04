# nyt_news_client.py
# NY Times Article Search API — destination headlines for the Essential info card.
# Server-side only; failures return empty lists (no user-facing errors).
#
# Two slots, **country only** (city input is ignored): (1) news ``sort=relevance``,
# (2) Travel section (``sort=relevance``), URL-deduped vs slot 1 when needed.
#
# **Recall-first:** try ``q`` = country / aliases with ``fq=None``, then section filters,
# then stricter news scope; **``glocations`` AND scope** only after that. Many stories
# never match a tight ``glocations`` + desk intersection. Short sleep between API calls.

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

NYT_ARTICLE_SEARCH_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"

_NEWS_SCOPE_FQ = '(news_desk:("Foreign" "National" "Politics" "Business") OR section_name:("World"))'
_Q_FALLBACK_SECTIONS_FQ = 'section_name:("World" "U.S." "Business" "Travel")'
_TRAVEL_SECTION_FQ = 'section_name:("Travel")'

_EU_ISO2 = frozenset(
    "FR DE IT ES NL BE AT CH SE NO DK FI PL PT IE IS CZ SK HU RO BG GR RS HR SI EE LV LT LU MT CY GB UA MK AL BA ME XK AD MC LI SM VA".split()
)
_ASIA_ISO2 = frozenset(
    "JP CN KR IN TH VN SG MY ID PH TW HK MO BD PK NP LK MM KH LA BN MN KZ UZ AE SA IL JO LB TR IQ IR KW QA OM BH YE AF BT GE AM AZ TM KG TJ".split()
)
_AMERICAS_ISO2 = frozenset(
    "US CA MX BR AR CL CO PE VE EC BO PY UY CR PA GT HN NI SV DO CU JM TT BS BZ HT GP MQ GF SR GY".split()
)
_AFRICA_ISO2 = frozenset(
    "EG ZA NG KE MA DZ TN GH ET TZ UG ZW BW NA MU RW SN CI CM CD AO MZ SD LY SO ET ER DJ SS CF TD NE BF ML SN GM GW GN SL LR CI TG BJ NE CM GA CG CD AO ZM MW MG SC KM MU RE YT".split()
)

_SLOT_PAUSE_SEC = 0.5


def _api_key() -> str:
    return (os.environ.get("NYT_API_KEY") or "").strip()


def _days_ago_ymd(days: int) -> str:
    utc_today = datetime.now(timezone.utc).date()
    return (utc_today - timedelta(days=days)).strftime("%Y%m%d")


def _fq_escape(s: str) -> str:
    return (s or "").replace('"', "").strip()


def _slot_gap() -> None:
    time.sleep(_SLOT_PAUSE_SEC)


def _continent_for_iso2(iso2: str | None) -> str | None:
    i = (iso2 or "").strip().upper()
    if len(i) != 2:
        return None
    if i in _EU_ISO2:
        return "EUROPE"
    if i in _ASIA_ISO2:
        return "ASIA"
    if i in _AMERICAS_ISO2:
        return "AMERICAS"
    if i in _AFRICA_ISO2:
        return "AFRICA"
    return None


def _glocations_token_candidates(*, country: str, country_iso2: str | None) -> list[str]:
    """Ordered ``glocations:…`` tokens for the destination **country** only."""
    c = _fq_escape(country)
    iso = (country_iso2 or "").strip().upper()
    seen: set[str] = set()
    out: list[str] = []

    def add(fragment_body: str) -> None:
        frag = f"glocations:{fragment_body}"
        if frag not in seen:
            seen.add(frag)
            out.append(frag)

    if not c:
        return out

    cu = c.upper()
    add(f'("{c}")')
    if iso == "US" or "UNITED STATES" in cu or c.strip().upper() in ("USA", "U.S.A.", "U.S."):
        add("UNITED STATES")

    # Quote ``COUNTRY (CONTINENT)`` so Lucene does not treat ``(EUROPE)`` as a separate clause
    # (unquoted ``glocations:POLAND (EUROPE)`` often matches nothing).
    cont = _continent_for_iso2(iso)
    if cont:
        add(f'("{cu} ({cont})")')

    for cont2 in ("EUROPE", "ASIA", "AMERICAS", "AFRICA", "MIDDLE EAST"):
        if cont2 != cont:
            add(f'("{cu} ({cont2})")')

    return out


def _country_q_candidates(country: str, country_iso2: str | None) -> list[str]:
    c = _fq_escape(country)
    seen: set[str] = set()
    out: list[str] = []

    def add(s: str) -> None:
        t = (s or "").strip()
        if t and t.lower() not in {x.lower() for x in seen}:
            seen.add(t)
            out.append(t)

    add(c)
    lk = c.lower()
    if lk in ("south korea", "republic of korea", "korea, south"):
        add("Korea")
        add("Seoul")
    elif lk in ("north korea", "korea, north", "democratic people's republic of korea"):
        add("North Korea")
    elif lk in ("united kingdom", "great britain", "britain", "uk"):
        add("United Kingdom")
        add("Britain")
    elif lk in ("united states", "usa", "u.s.", "u.s.a."):
        add("United States")
    elif lk == "czechia" or lk == "czech republic":
        add("Czech Republic")
    elif lk == "viet nam" or lk == "vietnam":
        add("Vietnam")

    iso = (country_iso2 or "").strip().upper()
    if iso == "KR" and all("korea" not in x.lower() for x in out):
        add("Korea")

    return out


def _article_search_docs(
    *,
    fq: str | None,
    q: str | None,
    begin_date: str,
    sort: str,
    api_key: str,
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """Return ``response.docs`` (up to 10) or empty list on failure."""
    if not fq and not q:
        return []
    try:
        params: dict[str, Any] = {
            "begin_date": begin_date,
            "sort": sort,
            "fl": "headline,web_url",
            "api-key": api_key,
        }
        if fq:
            params["fq"] = fq
        if q:
            params["q"] = q
        resp = requests.get(NYT_ARTICLE_SEARCH_URL, params=params, timeout=timeout)
        if not resp.ok:
            return []
        data = resp.json()
        if isinstance(data, dict) and data.get("fault"):
            return []
        resp_obj = data.get("response") if isinstance(data, dict) else None
        if not isinstance(resp_obj, dict):
            return []
        docs = resp_obj.get("docs")
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


def _pick_first_usable_doc(docs: list[dict[str, Any]], exclude_urls: set[str]) -> dict[str, Any] | None:
    for d in docs:
        p = _headline_and_url(d)
        if p and p[1] not in exclude_urls:
            return d
    return None


def _headline_and_url(doc: dict[str, Any]) -> tuple[str, str] | None:
    url = str(doc.get("web_url") or "").strip()
    if not url:
        return None
    hl = doc.get("headline")
    main = ""
    if isinstance(hl, dict):
        main = str(hl.get("main") or "").strip()
    elif isinstance(hl, str):
        main = hl.strip()
    if not main:
        return None
    return main, url


def _country_news_doc(
    *,
    location_tokens: list[str],
    and_fq: str,
    q_candidates: list[str],
    fq_chain: list[str | None],
    begin_date: str,
    sort: str,
    api_key: str,
    exclude_urls: set[str],
    max_gloc: int = 5,
) -> dict[str, Any] | None:
    """One country-scoped news article: ``q`` full-text first, then ``glocations`` + scope."""
    for q in q_candidates:
        if not (q or "").strip():
            continue
        qs = q.strip()
        for fq_opt in fq_chain:
            docs = _article_search_docs(
                fq=fq_opt,
                q=qs,
                begin_date=begin_date,
                sort=sort,
                api_key=api_key,
            )
            hit = _pick_first_usable_doc(docs, exclude_urls)
            if hit:
                return hit

    for loc in location_tokens[:max_gloc]:
        fq = f"{loc} AND {and_fq}"
        docs = _article_search_docs(fq=fq, q=None, begin_date=begin_date, sort=sort, api_key=api_key)
        hit = _pick_first_usable_doc(docs, exclude_urls)
        if hit:
            return hit
    return None


def _country_travel_doc(
    *,
    location_tokens: list[str],
    q_candidates: list[str],
    fq_chain: list[str | None],
    begin_date: str,
    api_key: str,
    exclude_urls: set[str],
    max_gloc: int = 5,
) -> dict[str, Any] | None:
    """Travel-leaning article: ``q`` (e.g. ``Brazil travel``) first, then ``glocations`` + Travel."""
    for q in q_candidates:
        if not (q or "").strip():
            continue
        qs = q.strip()
        for fq_opt in fq_chain:
            docs = _article_search_docs(
                fq=fq_opt,
                q=qs,
                begin_date=begin_date,
                sort="relevance",
                api_key=api_key,
            )
            hit = _pick_first_usable_doc(docs, exclude_urls)
            if hit:
                return hit

    travel_and = _TRAVEL_SECTION_FQ
    for loc in location_tokens[:max_gloc]:
        fq = f"{loc} AND {travel_and}"
        docs = _article_search_docs(fq=fq, q=None, begin_date=begin_date, sort="relevance", api_key=api_key)
        hit = _pick_first_usable_doc(docs, exclude_urls)
        if hit:
            return hit
    return None


def fetch_destination_news(country: str, country_iso2: str | None = None) -> list[dict[str, str]]:
    """
    Return up to two items: ``{"headline": str, "url": str}`` (country only; no city).

    (1) General news, ``sort=relevance``. (2) Travel-leaning, deduped vs (1) by URL.
    """
    key = _api_key()
    country_clean = _fq_escape(country)
    if not key or not country_clean:
        return []

    iso = (country_iso2 or "").strip().upper() or None
    tokens = _glocations_token_candidates(country=country_clean, country_iso2=iso)
    q_cands = _country_q_candidates(country_clean, iso)
    q_fq_chain: list[str | None] = [None, _Q_FALLBACK_SECTIONS_FQ, _NEWS_SCOPE_FQ]

    begin_90 = _days_ago_ymd(90)
    begin_730 = _days_ago_ymd(730)

    out: list[dict[str, str]] = []
    used: set[str] = set()

    # --- Slot 1: most relevant news ---
    doc1 = _country_news_doc(
        location_tokens=tokens,
        and_fq=_NEWS_SCOPE_FQ,
        q_candidates=q_cands,
        fq_chain=q_fq_chain,
        begin_date=begin_90,
        sort="relevance",
        api_key=key,
        exclude_urls=used,
    )
    p1 = _headline_and_url(doc1) if doc1 else None
    if p1:
        h1, u1 = p1
        used.add(u1)
        out.append({"headline": h1, "url": u1})

    _slot_gap()

    # --- Travel ---
    q_travel = [f"{country_clean} travel", f"{country_clean} tourism", country_clean]
    doc3 = _country_travel_doc(
        location_tokens=tokens,
        q_candidates=q_travel,
        fq_chain=[None, _TRAVEL_SECTION_FQ, _Q_FALLBACK_SECTIONS_FQ],
        begin_date=begin_730,
        api_key=key,
        exclude_urls=used,
    )
    p3 = _headline_and_url(doc3) if doc3 else None
    if p3:
        h3, u3 = p3
        if u3 not in used:
            used.add(u3)
            out.append({"headline": h3, "url": u3})

    return out
