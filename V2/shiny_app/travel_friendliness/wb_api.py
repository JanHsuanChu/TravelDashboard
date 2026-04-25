"""World Bank API helpers."""

from __future__ import annotations

import time
from typing import Any

import requests

from .constants import INDICATOR_IDS

_BASE = "https://api.worldbank.org/v2"


def get_latest_value(country_id: str, indicator_id: str) -> tuple[Any | None, str | None]:
    """Most recent non-null value for country/indicator."""
    url = f"{_BASE}/country/{country_id}/indicator/{indicator_id}"
    for attempt in range(3):
        try:
            r = requests.get(url, params={"format": "json", "per_page": 500}, timeout=90)
            break
        except requests.RequestException:
            time.sleep(0.4 * (attempt + 1))
    else:
        return None, None
    if r.status_code != 200:
        return None, None
    js = r.json()
    data = js[1] if len(js) > 1 and js[1] is not None else []
    with_value = [d for d in data if d.get("value") is not None]
    if not with_value:
        return None, None
    with_value.sort(key=lambda d: d.get("date") or "", reverse=True)
    rec = with_value[0]
    return rec.get("value"), rec.get("date")


_indicator_names_cache: dict[str, str] | None = None


def get_indicator_names() -> dict[str, str]:
    """Fetch human-readable indicator names (cached in-process)."""
    global _indicator_names_cache
    if _indicator_names_cache is not None:
        return _indicator_names_cache
    names: dict[str, str] = {}
    for iid in INDICATOR_IDS:
        url = f"{_BASE}/indicator/{iid}"
        r = requests.get(url, params={"format": "json"}, timeout=30)
        if r.status_code == 200:
            js = r.json()
            if len(js) > 1 and js[1]:
                names[iid] = js[1][0].get("name", iid)
            else:
                names[iid] = iid
        else:
            names[iid] = iid
        time.sleep(0.05)
    _indicator_names_cache = names
    return names