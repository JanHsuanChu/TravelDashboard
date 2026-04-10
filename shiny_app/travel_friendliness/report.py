"""Markdown + HTML report (style aligned with caucasus script export)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from .constants import CRITERIA_MAP


def format_value(x) -> str:
    if pd.isna(x):
        return "NA"
    if abs(float(x)) >= 1000:
        return "{:,.0f}".format(float(x))
    return "{:.2f}".format(float(x))


def _deterministic_purpose_block(country_order: list[str], reference_snapshot: str) -> str:
    names = ", ".join(country_order)
    return (
        f"This report compares travel-relevant development outcomes for: {names}. "
        "It uses publicly available World Bank indicators—covering environmental quality, governance, inclusion, "
        "tourism-related economic activity, and price conditions—so travelers can see how destinations differ on "
        "dimensions that often matter for comfort and planning. Each indicator is mapped to a 0–100 score using a "
        f"fixed reference normalization panel (snapshot {reference_snapshot}), so scores stay comparable even when "
        "only one country is selected. The methodology favors transparency: equal weights across indicators, "
        "neutral fill for missing values, and inversion where lower raw values are better (for example air pollution "
        "and inflation). Together, these scores summarize structural conditions—not subjective reviews—and should be "
        "read alongside visas, safety, and personal preferences."
    )


def _deterministic_recommendations_block(
    country_order: list[str],
    total_scores: pd.DataFrame,
    reference_snapshot: str,
) -> str:
    ts = total_scores.sort_values("total_score", ascending=False)
    if len(ts) < 1:
        return "Insufficient data for recommendations."
    top = ts.iloc[0]
    lines = [
        f"Highest overall score: **{top['country']}** at {top['total_score']:.1f}/100. "
        "Use the criteria breakdowns to see whether that lead is driven by environment, governance, tourism receipts, "
        "or affordability—dimensions matter differently for each trip. "
        f"Normalization uses reference bounds from {reference_snapshot}; if two destinations are close, treat the gap as "
        "directional rather than exact. "
    ]
    if len(ts) > 1:
        second = ts.iloc[1]
        lines.append(
            f"**{second['country']}** follows at {second['total_score']:.1f}/100; compare criteria tables before choosing "
            "based on what you prioritize (e.g. air quality vs. exchange-rate pressure). "
        )
    lines.append(
        "Missing data are scored neutrally (50), so sparse series can pull totals toward the middle; check the appendix "
        "for raw values and years. Always cross-check with official travel guidance and your own constraints."
    )
    return "".join(lines)


def build_report_markdown(
    data: pd.DataFrame,
    scored: pd.DataFrame,
    criteria_scores: pd.DataFrame,
    total_scores: pd.DataFrame,
    indicator_names: dict[str, str],
    country_order: list[str],
    reference_snapshot: str,
    purpose_text: str | None = None,
    recommendations_text: str | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    def df_to_markdown_table(df: pd.DataFrame) -> str:
        df = df.copy()
        cols = df.columns.tolist()

        def esc(v):
            s = "" if v is None else str(v)
            return s.replace("\n", " ").replace("|", "\\|")

        header = "| " + " | ".join([esc(c) for c in cols]) + " |"
        sep = "| " + " | ".join(["---" for _ in cols]) + " |"
        rows = ["| " + " | ".join([esc(v) for v in row]) + " |" for row in df.itertuples(index=False)]
        return "\n".join([header, sep] + rows)

    def section_divider() -> str:
        return "\n---\n\n"

    indicator_lookup_rows = []
    for criteria, indicator_ids in CRITERIA_MAP.items():
        for iid in indicator_ids:
            indicator_lookup_rows.append(
                {
                    "Criteria": criteria,
                    "Full Indicator Name": indicator_names.get(iid, iid),
                    "API Field Name": iid,
                }
            )
    indicator_lookup_df = pd.DataFrame(indicator_lookup_rows)

    summary_table_rows = []
    for criteria in CRITERIA_MAP.keys():
        row: dict[str, str] = {"Criteria": criteria}
        for cname in country_order:
            crit_score = criteria_scores.query("country == @cname & criteria == @criteria")
            if len(crit_score) > 0:
                score_val = crit_score.iloc[0]["criteria_score"]
                row[cname] = f"{score_val:.1f}"
            else:
                row[cname] = "N/A"
        summary_table_rows.append(row)

    total_row: dict[str, str] = {"Criteria": "**Total Score**"}
    for cname in country_order:
        tot_score = total_scores.query("country == @cname")
        if len(tot_score) > 0:
            score_val = tot_score.iloc[0]["total_score"]
            total_row[cname] = f"**{score_val:.1f}**"
        else:
            total_row[cname] = "N/A"
    summary_table_rows.append(total_row)
    summary_table_df = pd.DataFrame(summary_table_rows)

    country_summaries = {}
    n = len(country_order)
    rank_map = {name: i + 1 for i, name in enumerate(total_scores.sort_values("total_score", ascending=False)["country"].tolist())}

    for c in country_order:
        c_crit = criteria_scores.query("country == @c").copy()
        ts = total_scores.query("country == @c")
        if len(ts) == 0:
            country_summaries[c] = f"{c}: no score data."
            continue
        c_total = ts.iloc[0]["total_score"]
        if len(c_crit) == 0:
            country_summaries[c] = f"{c} has an overall score of {c_total:.1f}/100."
            continue
        c_crit_sorted = c_crit.sort_values("criteria_score", ascending=False)
        top_crit = c_crit_sorted.iloc[0]
        bottom_crit = c_crit_sorted.iloc[-1]
        rk = rank_map.get(c, n)
        ordinals = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
        ord_txt = ordinals.get(rk, f"#{rk}")
        country_summaries[c] = (
            f"{c} achieves an overall travel friendliness score of {c_total:.1f}/100, ranking {ord_txt} among the {n} destination(s) compared. "
            f"The strongest area is {top_crit['criteria']} ({top_crit['criteria_score']:.1f}/100); "
            f"{bottom_crit['criteria']} scores lowest ({bottom_crit['criteria_score']:.1f}/100)."
        )

    purpose_body = (purpose_text or "").strip() or _deterministic_purpose_block(country_order, reference_snapshot)
    recommendations = (recommendations_text or "").strip() or _deterministic_recommendations_block(
        country_order, total_scores, reference_snapshot
    )

    title_countries = " vs ".join(country_order)
    md: list[str] = []
    md.append(f"# Travel Friendliness Report: {title_countries}\n")
    md.append(f"_Generated: {now} (local time) · Reference bounds snapshot: {reference_snapshot}_\n")

    md.append("\n**Purpose**\n\n")
    md.append(purpose_body + "\n")

    md.append(section_divider())
    md.append("## Indicators and Criteria\n")
    crit_table_rows = []
    for criteria, indicator_ids in CRITERIA_MAP.items():
        full_names = [indicator_names.get(iid, iid) for iid in indicator_ids]
        crit_table_rows.append(
            {
                "Criteria": criteria,
                "Full Indicator Name(s)": " | ".join(full_names),
            }
        )
    crit_table_df = pd.DataFrame(crit_table_rows)
    md.append(df_to_markdown_table(crit_table_df))
    md.append("\n\n")
    md.append(section_divider())

    md.append("## Country Summaries\n")
    for c in country_order:
        md.append(f"### {c}\n\n")
        md.append(f"{country_summaries.get(c, '')}\n\n")
        c_crit = criteria_scores.query("country == @c").copy()
        if len(c_crit) == 0:
            continue
        c_crit["criteria_score"] = c_crit["criteria_score"].round(1)
        crit_lines = "\n".join(
            [
                "- **{}**: {} / 100 (missing {}/{})".format(
                    r["criteria"], r["criteria_score"], int(r["n_missing"]), int(r["n_indicators"])
                )
                for _, r in c_crit.iterrows()
            ]
        )
        md.append("**Criteria summary (0–100)**\n\n")
        md.append(crit_lines + "\n\n")

    md.append(section_divider())
    md.append("## Comparison Summary\n")
    md.append("Travel friendliness scores by criteria (0–100 scale):\n\n")
    md.append(df_to_markdown_table(summary_table_df))
    md.append("\n")

    md.append("\n<small>\n")
    md.append("**Scoring method:**\n")
    md.append(
        f"- **Reference normalization**: Each indicator is scaled to 0–100 using min/max bounds from a **reference panel** (see snapshot date). "
    )
    md.append("For PM2.5, exchange rate, and inflation, **lower raw values are better** (inverted scaling).\n")
    md.append("- **Equal weights**: Total score is the mean of all 12 indicator scores.\n")
    md.append("- **Missing data**: Missing raw values receive **50 (neutral)** for that indicator.\n")
    md.append("</small>\n\n")

    md.append(section_divider())
    md.append("## Recommendations and Conclusion\n\n")
    md.append(f"{recommendations}\n\n")
    md.append(section_divider())

    md.append("## Appendix: Latest Indicator Values\n\n")
    latest_table = (
        data.assign(value_fmt=data["value"].map(format_value))
        .loc[:, ["country", "criteria", "indicator_id", "indicator_name", "year", "value_fmt"]]
        .sort_values(["country", "criteria", "indicator_id"])
    )
    md.append(df_to_markdown_table(latest_table))
    md.append("\n\n")
    md.append("### Indicator Lookup (Full Name ↔ API Field Name)\n\n")
    md.append(df_to_markdown_table(indicator_lookup_df))
    md.append("\n")

    return "\n".join(md)


def markdown_to_html_document(report_md: str) -> str:
    import markdown

    html_content = markdown.markdown(report_md, extensions=["tables"])
    html_content = html_content.replace(
        "<hr />",
        '<hr style="border: 2px solid rgba(172, 133, 233, 0.45); margin: 30px 0;" />',
    )
    idx = html_content.find("<h2>Appendix: Latest Indicator Values</h2>")
    if idx >= 0:
        html_content = html_content[:idx] + '<div class="appendix">' + html_content[idx:] + "</div>"

    return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Travel Friendliness Report</title>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" />
  <style>
    /* Travel Dashboard brand palette (aligned with shiny_app/www/custom.css) */
    body {{
      font-family: Inter, system-ui, -apple-system, sans-serif;
      max-width: 980px;
      margin: 40px auto;
      padding: 24px;
      background: linear-gradient(
        165deg,
        #fef6ff 0%,
        #f6f4fb 28%,
        #f0fdff 55%,
        #fffbeb 85%,
        #f6f4fb 100%
      );
      color: #2d1b4e;
    }}
    h1 {{
      color: #ac85e9;
      border-bottom: 3px solid #ff6c9d;
      padding-bottom: 10px;
    }}
    h2 {{
      color: #2d1b4e;
      margin-top: 28px;
      border-bottom: 2px solid rgba(172, 133, 233, 0.45);
      padding-bottom: 5px;
    }}
    h3 {{
      color: #2d1b4e;
      margin-top: 20px;
    }}
    hr {{
      border: 2px solid rgba(172, 133, 233, 0.45);
      margin: 30px 0;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 15px 0;
      background-color: #ffffff;
      border: 1px solid #e8e4f2;
    }}
    th, td {{
      border: 1px solid #e8e4f2;
      padding: 8px 12px;
    }}
    th {{
      background: linear-gradient(90deg, rgba(172, 133, 233, 0.95), rgba(255, 108, 157, 0.85));
      color: #ffffff;
      text-align: left;
      font-weight: 600;
    }}
    tr:nth-child(even) {{
      background-color: rgba(172, 133, 233, 0.04);
    }}
    small {{
      font-size: 0.85em;
      color: #6b5f7e;
      display: block;
      margin-top: 10px;
    }}
    .appendix {{
      color: #6b5f7e;
      font-size: 0.9em;
    }}
    .appendix table {{
      font-size: 0.9em;
    }}
    .appendix h2, .appendix h3 {{
      color: #2d1b4e;
      border-bottom-color: rgba(172, 133, 233, 0.35);
    }}
  </style>
</head>
<body>
{0}
</body>
</html>""".format(html_content)
