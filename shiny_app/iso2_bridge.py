"""Map ISO 3166-1 alpha-2 to strings usable by World Bank friendliness resolution."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_JSON = Path(__file__).resolve().parent / "www" / "data" / "countries_slim.json"


@lru_cache(maxsize=1)
def _cca2_to_name() -> dict[str, str]:
    if not _JSON.is_file():
        return {}
    with open(_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    countries = raw.get("countries") if isinstance(raw, dict) else raw
    if not isinstance(countries, list):
        return {}
    out: dict[str, str] = {}
    for c in countries:
        if not isinstance(c, dict):
            continue
        cca2 = (c.get("cca2") or "").strip().upper()
        name = (c.get("name") or "").strip()
        if len(cca2) == 2 and name:
            out[cca2] = name
    return out


def display_name_for_iso2(iso2: str | None) -> str | None:
    """Return RestCountries common name for ISO2, or None if unknown."""
    if not iso2:
        return None
    return _cca2_to_name().get(iso2.strip().upper())


def friendliness_country_query(iso2: str | None, fallback_display: str) -> str:
    """
    World Bank resolver uses free-text country names. Prefer canonical name from ISO2
    when the user picked from our strict list; else use visible label.
    """
    n = display_name_for_iso2(iso2)
    if n:
        return n
    return (fallback_display or "").strip()


def is_known_iso2(iso2: str | None) -> bool:
    if not iso2 or len(iso2.strip()) != 2:
        return False
    return iso2.strip().upper() in _cca2_to_name()
