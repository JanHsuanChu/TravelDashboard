"""Frozen World Bank economy display names for UI datalist (no runtime API call)."""

from __future__ import annotations

import json
from pathlib import Path

_JSON = Path(__file__).resolve().parent / "data" / "wb_country_names.json"


def load_wb_country_names() -> list[str]:
    """Sorted unique economy names as returned by the WB country list API."""
    if not _JSON.is_file():
        return []
    with open(_JSON, encoding="utf-8") as f:
        data = json.load(f)
    names = data.get("names") if isinstance(data, dict) else data
    if not isinstance(names, list):
        return []
    return sorted({str(n).strip() for n in names if str(n).strip()})
