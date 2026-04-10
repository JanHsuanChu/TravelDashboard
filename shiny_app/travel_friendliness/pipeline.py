"""End-to-end friendliness computation for the Shiny app."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .country_resolve import resolve_country_to_wb_id
from .report import build_report_markdown, markdown_to_html_document
from .scoring import fetch_indicator_frame, score_dataset_with_reference_bounds
from .wb_api import get_indicator_names

_DATA_DIR = Path(__file__).resolve().parent / "data"
_BOUNDS_PATH = _DATA_DIR / "wb_indicator_bounds.json"


@dataclass
class FriendlinessResult:
    ok: bool
    error_message: str | None = None
    primary_label: str = ""
    primary_total: float | None = None
    primary_summary: str = ""
    compare_rows: list[dict[str, Any]] = field(default_factory=list)
    report_html: str | None = None
    reference_snapshot: str = ""
    small_print: str = ""


def _load_bounds() -> tuple[dict[str, dict[str, float]], str]:
    if not _BOUNDS_PATH.is_file():
        raise FileNotFoundError(
            f"Missing reference bounds file: {_BOUNDS_PATH}. Run scripts/build_wb_indicator_bounds.py",
        )
    with open(_BOUNDS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    snap = str(raw.get("snapshot_date", "unknown"))
    bounds_raw = raw.get("bounds", {})
    bounds: dict[str, dict[str, float]] = {}
    for iid, b in bounds_raw.items():
        bounds[iid] = {"vmin": float(b["vmin"]), "vmax": float(b["vmax"])}
    return bounds, snap


def _maybe_llm_report_narratives(
    payload: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Optional LLM prose for report Purpose + Recommendations (50–100 words each)."""
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        return None, None
    try:
        import requests

        url = "https://ollama.com/api/chat"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        prompt = (
            "You are writing two sections for a travel analytics report. Use ONLY facts supported by the JSON; "
            "do not invent indicator values or country names.\n\n"
            "1) **Purpose** — 50 to 100 words: explain what this report compares and why World Bank indicators matter for travelers.\n"
            "2) **Recommendations and conclusion** — 50 to 100 words: actionable takeaways comparing the destinations' scores.\n\n"
            "Return valid JSON only with keys purpose and recommendations (strings). Example: "
            '{"purpose":"...","recommendations":"..."}\n\n'
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )
        body = {
            "model": os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud"),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        r = requests.post(url, headers=headers, json=body, timeout=90)
        r.raise_for_status()
        js = r.json()
        text = js.get("message", {}).get("content") or ""
        text = text.strip()
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        parsed = json.loads(text)
        purpose = (parsed.get("purpose") or "").strip()
        rec = (parsed.get("recommendations") or "").strip()
        return purpose or None, rec or None
    except Exception:
        return None, None


def _deterministic_primary_summary(
    primary_name: str,
    criteria_scores: pd.DataFrame,
    total_score: float,
) -> str:
    ts = max(0.0, min(100.0, float(total_score)))
    cc = criteria_scores.query("country == @primary_name")
    if len(cc) == 0:
        return f"{primary_name}: overall score {ts:.0f}/100 (World Bank indicators, reference-normalized)."
    cc = cc.sort_values("criteria_score", ascending=False)
    top = cc.iloc[0]
    bot = cc.iloc[-1]
    top_s = max(0.0, min(100.0, float(top["criteria_score"])))
    bot_s = max(0.0, min(100.0, float(bot["criteria_score"])))
    return (
        f"{primary_name} — overall {ts:.0f}/100. "
        f"Strongest: {top['criteria']} ({top_s:.1f}); "
        f"lowest: {bot['criteria']} ({bot_s:.1f})."
    )


def compute_friendliness(
    dest_country: str,
    cmp1_country: str,
    cmp2_country: str,
) -> FriendlinessResult:
    """
    dest_country required. Compare fields optional (strip empty).
    Uses country names only (cities ignored).
    """
    small = (
        "Comparison uses World Bank indicators (latest year per series), grouped into: "
        + ", ".join(
            [
                "Air Quality",
                "Water Quality",
                "Security",
                "Female Friendliness",
                "Human Rights",
                "Tourism Strength",
                "Currency Affordability",
            ]
        )
        + ". Scores are 0–100 per indicator using a fixed reference min/max panel; missing values use 50 (neutral)."
    )

    dest = (dest_country or "").strip()
    if not dest:
        return FriendlinessResult(ok=False, error_message="Enter a destination country.", small_print=small)

    pid, pname, dest_err = resolve_country_to_wb_id(dest)
    if not pid:
        return FriendlinessResult(
            ok=False,
            error_message=dest_err or f"Could not match destination “{dest}” to a World Bank country.",
            small_print=small,
        )

    countries: list[dict[str, str]] = [{"id": pid, "name": pname}]

    for label, raw in (("compare1", cmp1_country), ("compare2", cmp2_country)):
        s = (raw or "").strip()
        if not s:
            continue
        cid, cname, cmp_err = resolve_country_to_wb_id(s)
        if not cid:
            return FriendlinessResult(
                ok=False,
                error_message=cmp_err or f"Could not match “{s}” ({label}) to a World Bank country.",
                small_print=small,
            )
        if any(c["id"] == cid for c in countries):
            continue
        countries.append({"id": cid, "name": cname})

    try:
        bounds, ref_snap = _load_bounds()
    except FileNotFoundError as e:
        return FriendlinessResult(ok=False, error_message=str(e), small_print=small)

    try:
        indicator_names = get_indicator_names()
        data = fetch_indicator_frame(countries, indicator_names)
        scored, criteria_scores, total_scores = score_dataset_with_reference_bounds(data, bounds)
    except Exception as e:
        return FriendlinessResult(
            ok=False,
            error_message=f"Travel friendliness data error: {e}",
            small_print=small,
            reference_snapshot=ref_snap,
        )

    ts_p = total_scores.query("country == @pname")
    primary_total = float(ts_p.iloc[0]["total_score"]) if len(ts_p) else None
    if primary_total is not None:
        primary_total = max(0.0, min(100.0, primary_total))
    if primary_total is None:
        return FriendlinessResult(
            ok=False,
            error_message="No total score for primary destination.",
            small_print=small,
            reference_snapshot=ref_snap,
        )

    crit_p = criteria_scores.query("country == @pname")
    # Card summary stays deterministic so displayed scores always match 0–100 totals (no LLM hallucination).
    summary = _deterministic_primary_summary(pname, criteria_scores, primary_total)

    compare_rows: list[dict[str, Any]] = []
    for c in countries[1:]:
        cn = c["name"]
        trow = total_scores[total_scores["country"] == cn]
        if len(trow):
            compare_rows.append(
                {
                    "label": cn,
                    "score": max(0.0, min(100.0, float(trow.iloc[0]["total_score"]))),
                }
            )

    country_order = [c["name"] for c in countries]
    report_payload = {
        "primary_destination": pname,
        "primary_total_0_to_100": round(float(primary_total), 2),
        "countries_compared": country_order,
        "total_scores_by_country": total_scores[["country", "total_score"]].to_dict(orient="records"),
        "criteria_scores_sample": criteria_scores.head(40).to_dict(orient="records"),
        "reference_bounds_snapshot": ref_snap,
    }
    purpose_llm, rec_llm = _maybe_llm_report_narratives(report_payload)
    report_md = build_report_markdown(
        data,
        scored,
        criteria_scores,
        total_scores,
        indicator_names,
        country_order=country_order,
        reference_snapshot=ref_snap,
        purpose_text=purpose_llm,
        recommendations_text=rec_llm,
    )
    report_html = markdown_to_html_document(report_md)

    small = small + f" Reference bounds: {ref_snap}."

    return FriendlinessResult(
        ok=True,
        primary_label=pname,
        primary_total=primary_total,
        primary_summary=summary,
        compare_rows=compare_rows,
        report_html=report_html,
        reference_snapshot=ref_snap,
        small_print=small,
    )
