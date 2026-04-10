# Travel friendliness (World Bank)

The **Travel friendliness** card and downloadable HTML report use the [World Bank API](https://api.worldbank.org/v2/) (indicator series), **not** the Ollama JSON block for numeric scores. Indicator and total scores are **clamped to 0–100** after reference normalization. The card’s one-line summary is **deterministic** from those scores (no LLM). When `OLLAMA_API_KEY` is set, the model may draft longer **Purpose** and **Recommendations** sections in the HTML report; otherwise deterministic prose is used.

Country fields use a browser **datalist** fed from `data/wb_country_names.json` (regenerate with `scripts/build_wb_country_names.py`). Name resolution prefers exact matches and high-confidence fuzzy matches; **Taiwan is not listed** as a separate economy in the World Bank country list used by the API—users should pick another economy from the suggestions.

## When it runs

Scores compute on **Generate**, after trip timing and destination country validation, using **destination country** and optional **compare country** fields only (city inputs are ignored for this panel).

## Normalization

Indicator values are mapped to **0–100** using a **fixed reference min/max** per indicator (`shiny_app/travel_friendliness/data/wb_indicator_bounds.json`). That avoids the “single country ⇒ everything is 50” artifact of min–max normalization within one slice. The JSON includes a **snapshot date** for the bounds; regenerate with:

```bash
cd /path/to/TravelDashboard
python3 scripts/build_wb_indicator_bounds.py
```

(Network access to the World Bank API is required for a full regeneration.)

## Code layout

| Area | Path |
|------|------|
| Scoring + report | `shiny_app/travel_friendliness/` |
| Bounds asset | `shiny_app/travel_friendliness/data/wb_indicator_bounds.json` |
| Country datalist + offline resolver | `wb_country_names.json`, `wb_countries.json` (see `scripts/build_wb_country_names.py`) |
| Build script | `scripts/build_wb_indicator_bounds.py` |
| Server wiring | `shiny_app/server.py` (`friendliness_state`, `out_friendliness`, `friendliness_download_area`, `dl_friendliness_report`) |

The reference caucasus script under `TravelFriendliness-repo/` is **read-only** for this product; logic was ported into `TravelDashboard` only.
