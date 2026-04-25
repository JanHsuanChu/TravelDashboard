#!/usr/bin/env python3
"""Fetch RestCountries v3.1 and write shiny_app/www/data/countries_slim.json (cca2, name, aliases)."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "shiny_app" / "www" / "data" / "countries_slim.json"
URL = "https://restcountries.com/v3.1/all?fields=name,cca2,altSpellings"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": "TravelDashboard-build/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    slim: list[dict] = []
    for c in data:
        if not isinstance(c, dict):
            continue
        cca2 = (c.get("cca2") or "").upper()
        if len(cca2) != 2:
            continue
        nm = c.get("name") or {}
        common = (nm.get("common") or "").strip()
        official = (nm.get("official") or "").strip()
        aliases: list[str] = []
        for x in c.get("altSpellings") or []:
            if x and x not in aliases:
                aliases.append(x)
        if common and common not in aliases:
            aliases.insert(0, common)
        if official and official not in aliases:
            aliases.append(official)
        slim.append({"cca2": cca2, "name": common or official, "aliases": aliases})
    slim.sort(key=lambda x: x["name"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": URL, "countries": slim}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(slim)} countries to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
