#!/usr/bin/env python3
"""Regenerate WB country name list + id/name JSON for datalist and offline resolver."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_NAMES = ROOT / "shiny_app" / "travel_friendliness" / "data" / "wb_country_names.json"
OUT_COUNTRIES = ROOT / "shiny_app" / "travel_friendliness" / "data" / "wb_countries.json"

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


def main() -> None:
    rows_out: list[dict[str, str]] = []
    page = 1
    while True:
        r = requests.get(
            "https://api.worldbank.org/v2/country",
            params={"format": "json", "per_page": 1000, "page": page},
            timeout=90,
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
            n = (c.get("name") or "").strip()
            if n:
                rows_out.append({"id": cid, "name": n})
        if len(chunk) < 1000:
            break
        page += 1
        time.sleep(0.05)

    unique_names = sorted({r["name"] for r in rows_out})
    OUT_NAMES.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_NAMES, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_note": "WB /v2/country economy names for browser datalist autocomplete.",
                "names": unique_names,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(OUT_COUNTRIES, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_note": "WB /v2/country id+name for offline resolver; regenerate with this script.",
                "countries": rows_out,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Wrote {len(unique_names)} names to {OUT_NAMES}", file=sys.stderr)
    print(f"Wrote {len(rows_out)} id/name rows to {OUT_COUNTRIES}", file=sys.stderr)


if __name__ == "__main__":
    main()
