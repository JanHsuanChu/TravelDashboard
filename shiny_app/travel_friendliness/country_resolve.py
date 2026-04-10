"""Resolve free-text country names to World Bank ISO3 codes."""

from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Any

import requests

_COUNTRIES_CACHE: list[dict[str, Any]] | None = None

_DATA_DIR = Path(__file__).resolve().parent / "data"
_LOCAL_COUNTRIES_JSON = _DATA_DIR / "wb_countries.json"

# Common WB aggregate codes (not visitable countries)
_AGGREGATE_IDS = frozenset(
    {
        "WLD",
        "HIC",
        "MIC",
        "LIC",
        "LMC",
        "UMC",
        "EUU",
        "OED",
        "SSF",
        "TEA",
        "ECS",
        "LCN",
        "MEA",
        "EAS",
        "NAC",
        "SSA",
        "INX",
        "EMU",
        "PST",
        "EAR",
        "CEB",
        "CHI",
        "XKX",
    }
)

# Common user typos / synonyms -> WB official English name substring to prefer
_ALIASES: dict[str, str] = {
    "usa": "United States",
    "u.s.a.": "United States",
    "United States of America": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "south korea": "Korea, Rep.",
    "north korea": "Korea, Dem. People's Rep.",
    "russia": "Russian Federation",
    "czech republic": "Czechia",
}

# Minimum similarity (0–1) to accept a fuzzy match when there is no substring hit
_FUZZY_MIN_RATIO = 0.82


def _name_ratio(query_lower: str, name: str) -> float:
    return SequenceMatcher(None, query_lower, name.lower()).ratio()


def _load_wb_countries_from_disk() -> list[dict[str, Any]] | None:
    if not _LOCAL_COUNTRIES_JSON.is_file():
        return None
    try:
        with open(_LOCAL_COUNTRIES_JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except OSError:
        return None
    countries = raw.get("countries") if isinstance(raw, dict) else raw
    if not isinstance(countries, list) or not countries:
        return None
    rows: list[dict[str, Any]] = []
    for c in countries:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        name = (c.get("name") or "").strip()
        if not cid or not name:
            continue
        rows.append({"id": cid, "name": name, "capitalCity": ""})
    return rows if rows else None


def _load_wb_countries() -> list[dict[str, Any]]:
    global _COUNTRIES_CACHE
    if _COUNTRIES_CACHE is not None:
        return _COUNTRIES_CACHE

    cached = _load_wb_countries_from_disk()
    if cached is not None:
        _COUNTRIES_CACHE = cached
        return _COUNTRIES_CACHE

    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        r = requests.get(
            "https://api.worldbank.org/v2/country",
            params={"format": "json", "per_page": 1000, "page": page},
            timeout=60,
        )
        r.raise_for_status()
        js = r.json()
        chunk = js[1] if len(js) > 1 and js[1] else []
        if not chunk:
            break
        for c in chunk:
            cid = c.get("id")
            if not cid or len(cid) != 3 or not cid.isalpha():
                continue
            if cid in _AGGREGATE_IDS:
                continue
            rows.append(
                {
                    "id": cid,
                    "name": c.get("name") or "",
                    "capitalCity": c.get("capitalCity") or "",
                }
            )
        if len(chunk) < 1000:
            break
        page += 1
        time.sleep(0.05)
    _COUNTRIES_CACHE = rows
    return rows


def normalize_query(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def resolve_country_to_wb_id(user_input: str) -> tuple[str | None, str | None, str | None]:
    """
    Return (wb_iso3, display_name, error_message).

    On success: (id, name, None).
    On failure: (None, None, user-facing error string).
    """
    q = normalize_query(user_input)
    if not q:
        return None, None, "Enter a country name."

    ql = q.lower()

    # Taiwan is not listed as a separate economy in the WB country list used by the API.
    if "taiwan" in ql:
        return (
            None,
            None,
            "The World Bank country list used here does not include Taiwan as a separate economy. "
            "Choose a name from the suggestions (e.g. Hong Kong SAR, China, China, Korea, Rep.), "
            "or another country in the list.",
        )

    if ql in _ALIASES:
        q = _ALIASES[ql]
        ql = q.lower()

    countries = _load_wb_countries()
    names = [c["name"] for c in countries]

    # Exact ISO3
    if len(q) == 3 and q.isalpha():
        u = q.upper()
        for c in countries:
            if c["id"] == u:
                return c["id"], c["name"], None

    # Exact name (case-insensitive)
    for c in countries:
        if c["name"].lower() == ql:
            return c["id"], c["name"], None

    # Alias table value
    for key, val in _ALIASES.items():
        if key == ql:
            for c in countries:
                if val.lower() == c["name"].lower():
                    return c["id"], c["name"], None

    # Substring: query contained in official name (disambiguate by best ratio)
    sub_hits = [c for c in countries if ql in c["name"].lower()]
    if len(sub_hits) == 1:
        c = sub_hits[0]
        return c["id"], c["name"], None
    if len(sub_hits) > 1:
        sub_hits.sort(key=lambda c: _name_ratio(ql, c["name"]), reverse=True)
        best = sub_hits[0]
        if _name_ratio(ql, best["name"]) >= 0.55:
            return best["id"], best["name"], None

    # Fuzzy: close names, then re-rank by SequenceMatcher (avoids "Taiwan" -> "Thailand")
    matches = get_close_matches(q, names, n=25, cutoff=0.5)
    if matches:
        matches.sort(key=lambda m: _name_ratio(ql, m), reverse=True)
        best_name = matches[0]
        ratio = _name_ratio(ql, best_name)
        if ratio >= _FUZZY_MIN_RATIO:
            for c in countries:
                if c["name"] == best_name:
                    return c["id"], c["name"], None

    return (
        None,
        None,
        f"No confident match for “{user_input.strip()}”. Pick a country from the suggestion list, "
        "or type the official World Bank name (e.g. Korea, Rep. for South Korea).",
    )
