"""Reference-bound 0–100 scoring (per indicator), then criteria + total means."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .constants import CRITERIA_MAP, INDICATOR_IDS, LOWER_IS_BETTER


def indicator_to_criteria(indicator_id: str) -> str:
    for criteria, ids in CRITERIA_MAP.items():
        if indicator_id in ids:
            return criteria
    return "Other"


def score_value_to_0_100(
    value: float,
    vmin: float,
    vmax: float,
    lower_is_better: bool,
) -> float:
    if pd.isna(value):
        return float("nan")
    if vmax == vmin:
        return 50.0
    if lower_is_better:
        raw = 100.0 * (vmax - float(value)) / (vmax - vmin)
    else:
        raw = 100.0 * (float(value) - vmin) / (vmax - vmin)
    # Raw values outside the reference panel can produce scores outside 0–100; clamp for display and totals.
    return max(0.0, min(100.0, raw))


def score_dataset_with_reference_bounds(
    data: pd.DataFrame,
    bounds: dict[str, dict[str, float]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    data: columns country, country_id, criteria, indicator_id, indicator_name, value, year
    bounds: indicator_id -> {vmin, vmax}
    """
    rows = []
    for _, r in data.iterrows():
        iid = r["indicator_id"]
        v = r["value"]
        b = bounds.get(iid, {})
        vmin = float(b.get("vmin", float("nan")))
        vmax = float(b.get("vmax", float("nan")))
        lower = iid in LOWER_IS_BETTER
        if pd.isna(v):
            score_raw = float("nan")
        elif pd.isna(vmin) or pd.isna(vmax):
            score_raw = 50.0
        else:
            score_raw = score_value_to_0_100(
                pd.to_numeric(v, errors="coerce"),
                vmin,
                vmax,
                lower,
            )

        rows.append(
            {
                **{k: r[k] for k in r.index},
                "score_raw": score_raw,
            }
        )

    scored = pd.DataFrame(rows)
    scored["is_missing_value"] = scored["value"].isna()
    scored["score"] = scored["score_raw"].fillna(50.0)

    criteria_scores = (
        scored.groupby(["country", "criteria"], as_index=False)
        .agg(criteria_score=("score", "mean"), n_missing=("is_missing_value", "sum"), n_indicators=("score", "size"))
        .sort_values(["country", "criteria"])
    )
    criteria_scores["criteria_score"] = criteria_scores["criteria_score"].clip(0.0, 100.0)

    total_scores = (
        scored.groupby("country", as_index=False)
        .agg(total_score=("score", "mean"), n_missing=("is_missing_value", "sum"), n_indicators=("score", "size"))
        .sort_values("total_score", ascending=False)
    )
    total_scores["total_score"] = total_scores["total_score"].clip(0.0, 100.0)

    return scored, criteria_scores, total_scores


def fetch_indicator_frame(
    countries: list[dict[str, str]],
    indicator_names: dict[str, str],
) -> pd.DataFrame:
    """countries: list of {id, name}."""
    import time

    from .wb_api import get_latest_value

    rows = []
    for c in countries:
        for indicator_id in INDICATOR_IDS:
            value, year = get_latest_value(c["id"], indicator_id)
            rows.append(
                {
                    "country": c["name"],
                    "country_id": c["id"],
                    "criteria": indicator_to_criteria(indicator_id),
                    "indicator_id": indicator_id,
                    "indicator_name": indicator_names.get(indicator_id, indicator_id),
                    "value": value,
                    "year": year,
                }
            )
            time.sleep(0.05)
    data = pd.DataFrame(rows)
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    return data
