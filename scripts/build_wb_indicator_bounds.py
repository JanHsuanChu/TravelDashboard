#!/usr/bin/env python3
"""
Build reference min/max per World Bank indicator across a diverse country panel.
Writes shiny_app/travel_friendliness/data/wb_indicator_bounds.json

Run from repo root: python3 scripts/build_wb_indicator_bounds.py
Requires network. Does not modify TravelFriendliness-repo.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shiny_app"))

from travel_friendliness.constants import INDICATOR_IDS  # noqa: E402
from travel_friendliness.wb_api import get_latest_value  # noqa: E402

# Diverse ISO3 codes (World Bank operational countries) — not aggregates
# Smaller panel = faster CI; widen by editing this list and re-running.
REFERENCE_COUNTRY_IDS = [
    "USA",
    "CHN",
    "JPN",
    "DEU",
    "FRA",
    "GBR",
    "IND",
    "BRA",
    "RUS",
    "CAN",
    "AUS",
    "KOR",
    "MEX",
    "IDN",
    "TUR",
    "ZAF",
    "THA",
    "NLD",
    "ESP",
    "ITA",
    "ARG",
    "CHL",
    "EGY",
    "VNM",
    "BGD",
    "AZE",
    "GEO",
    "ARM",
    "NZL",
]


def main() -> None:
    out_path = ROOT / "shiny_app" / "travel_friendliness" / "data" / "wb_indicator_bounds.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    values_by_indicator: dict[str, list[float]] = {iid: [] for iid in INDICATOR_IDS}

    for cid in REFERENCE_COUNTRY_IDS:
        for iid in INDICATOR_IDS:
            val, _yr = get_latest_value(cid, iid)
            if val is not None:
                try:
                    values_by_indicator[iid].append(float(val))
                except (TypeError, ValueError):
                    pass
            time.sleep(0.05)

    bounds: dict[str, dict[str, float]] = {}
    for iid, vals in values_by_indicator.items():
        if not vals:
            bounds[iid] = {"vmin": 0.0, "vmax": 1.0}
            continue
        bounds[iid] = {"vmin": min(vals), "vmax": max(vals)}
        if bounds[iid]["vmin"] == bounds[iid]["vmax"]:
            bounds[iid]["vmax"] = bounds[iid]["vmin"] + 1e-9

    payload = {
        "snapshot_date": date.today().isoformat(),
        "reference_countries_n": len(REFERENCE_COUNTRY_IDS),
        "bounds": bounds,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
