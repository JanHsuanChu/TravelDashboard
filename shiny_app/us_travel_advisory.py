# us_travel_advisory.py
# U.S. State Department travel advisory table: fetch, 24h cache with stale-while-error, HTML/JSON parse, match, Ollama blurb.

from __future__ import annotations

import difflib
import html as html_module
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Historical JSON path (often 301 → HTML); we still try JSON-shaped bodies first after fetch.
US_ADVISORY_JSON_URL = (
    "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html/"
    "_jcr_content/ada/parsys/table_1464634926/table-data.json"
)
# Canonical page that embeds the full advisory table (same data after JSON redirect).
US_ADVISORY_HTML_URL = "https://travel.state.gov/en/international-travel/travel-advisories.html"

_DEFAULT_CACHE_SECONDS = 86400
_REQUEST_TIMEOUT = 45
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_HTML_ROW_RE = re.compile(
    r'<th scope="row"><a[^>]*>([^<]+)</a></th>\s*'
    r'<td><p><span class="level-badge level-badge-(\d)"></span>([^<]+)</p></td>\s*'
    r"<td>(.*?)</td>\s*"
    r"<td><p>(\d{2}/\d{2}/\d{4})</p></td>",
    re.DOTALL,
)
_RISK_PILL_RE = re.compile(r'<span class="tsg-utility-risk-pill">([^<]+)</span>')


def _cache_ttl_seconds() -> int:
    raw = (os.environ.get("TD_US_ADVISORY_CACHE_SECONDS") or "").strip()
    if raw.isdigit():
        return max(60, int(raw))
    return _DEFAULT_CACHE_SECONDS


@dataclass
class AdvisoryRow:
    country: str
    level: int
    level_label: str
    date_issued: str
    risk_indicators: list[str] = field(default_factory=list)


@dataclass
class AdvisoryTableSnapshot:
    rows: list[AdvisoryRow]
    loaded_at_utc: datetime
    source: str  # "html" | "json"
    fetch_used_stale_cache: bool
    last_refresh_error: str | None


_cached_snapshot: AdvisoryTableSnapshot | None = None
_cache_monotonic_at: float = 0.0
_last_refresh_error: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_key(s: str) -> str:
    t = html_module.unescape(s or "").casefold().replace("-", " ")
    return " ".join(t.split())


def _http_get(url: str) -> tuple[str, str]:
    """Return (text, final_url). Raises on HTTP error."""
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
    r = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text, str(r.url)


def _parse_rows_from_html(html: str) -> list[AdvisoryRow]:
    rows: list[AdvisoryRow] = []
    for m in _HTML_ROW_RE.finditer(html):
        country, lvl_s, level_label, risk_cell, date_issued = m.groups()
        try:
            level = int(lvl_s)
        except ValueError:
            continue
        pills = [
            html_module.unescape(p).strip() for p in _RISK_PILL_RE.findall(risk_cell) if p.strip()
        ]
        rows.append(
            AdvisoryRow(
                country=html_module.unescape(country.strip()),
                level=level,
                level_label=html_module.unescape(level_label.strip()),
                date_issued=date_issued.strip(),
                risk_indicators=pills,
            )
        )
    return rows


def _parse_rows_from_json(data: Any) -> list[AdvisoryRow]:
    """Best-effort AEM / table JSON shapes; returns empty if unknown."""
    rows: list[AdvisoryRow] = []
    if isinstance(data, list):
        iterable = data
    elif isinstance(data, dict):
        for key in ("data", "rows", "tableData", "body"):
            if key in data and isinstance(data[key], list):
                iterable = data[key]
                break
        else:
            return []
    else:
        return []

    level_re = re.compile(r"level\s*(\d)", re.I)
    for item in iterable:
        if not isinstance(item, dict):
            continue
        # Guess keys (schema varies)
        country = (
            item.get("destination")
            or item.get("country")
            or item.get("name")
            or item.get("title")
            or ""
        )
        if not isinstance(country, str):
            country = str(country)
        country = country.strip()
        if not country:
            continue
        raw_level = item.get("level") or item.get("advisoryLevel") or item.get("travel_advisory_level")
        level: int | None = None
        if isinstance(raw_level, int) and 1 <= raw_level <= 4:
            level = raw_level
        elif isinstance(raw_level, str):
            mm = level_re.search(raw_level)
            if mm:
                level = int(mm.group(1))
        if level is None:
            for k, v in item.items():
                if isinstance(v, str) and "level" in k.lower():
                    mm = level_re.search(v)
                    if mm:
                        level = int(mm.group(1))
                        break
        if level is None or not (1 <= level <= 4):
            continue
        level_label = ""
        for k, v in item.items():
            if isinstance(v, str) and "level" in k.lower() and len(v) > 8:
                level_label = v.strip()
                break
        if not level_label:
            level_label = f"Level {level}"
        date_issued = str(
            item.get("dateIssued")
            or item.get("date")
            or item.get("lastUpdated")
            or item.get("updated")
            or ""
        ).strip()
        risks = item.get("riskIndicators") or item.get("risks") or []
        pills: list[str] = []
        if isinstance(risks, list):
            pills = [str(x).strip() for x in risks if str(x).strip()]
        rows.append(
            AdvisoryRow(
                country=country,
                level=level,
                level_label=level_label,
                date_issued=date_issued,
                risk_indicators=pills,
            )
        )
    return rows


def _parse_document(text: str, _final_url: str) -> tuple[list[AdvisoryRow], str]:
    t = text.lstrip()
    if t.startswith("{") or t.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            jrows = _parse_rows_from_json(data)
            if jrows:
                return jrows, "json"
    if 'id="htmlTable"' in text or "level-badge level-badge-" in text:
        hrows = _parse_rows_from_html(text)
        return hrows, "html"
    return [], "unknown"


@lru_cache(maxsize=1)
def _country_slim_path() -> Path:
    return Path(__file__).resolve().parent / "www" / "data" / "countries_slim.json"


def _alias_strings_for_iso2(iso2: str) -> list[str]:
    """Names and aliases from countries_slim for matching State Dept labels."""
    p = _country_slim_path()
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    countries = raw.get("countries") if isinstance(raw, dict) else raw
    if not isinstance(countries, list):
        return []
    iso2u = iso2.strip().upper()
    out: list[str] = []
    for c in countries:
        if not isinstance(c, dict):
            continue
        if (c.get("cca2") or "").strip().upper() != iso2u:
            continue
        name = (c.get("name") or "").strip()
        if name:
            out.append(name)
        for a in c.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                out.append(a.strip())
        break
    # De-dupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for s in out:
        k = _norm_key(s)
        if k and k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq


def match_advisory_row(rows: list[AdvisoryRow], *, iso2: str, display_country: str) -> AdvisoryRow | None:
    """Match by normalized country name against HTML destination labels and local aliases."""
    if not rows:
        return None
    iso2u = (iso2 or "").strip().upper()
    candidates: list[str] = []
    if display_country.strip():
        candidates.append(display_country.strip())
    candidates.extend(_alias_strings_for_iso2(iso2u))
    cand_norms = [_norm_key(c) for c in candidates if c.strip()]

    def _best_ratio_for_row(r: AdvisoryRow) -> float:
        cn = _norm_key(r.country)
        top = 0.0
        for cand in cand_norms:
            if not cand:
                continue
            if cand == cn:
                return 1.0
            top = max(top, difflib.SequenceMatcher(a=cn, b=cand).ratio())
        return top

    for r in rows:
        cn = _norm_key(r.country)
        for cand in cand_norms:
            if not cand:
                continue
            if cand == cn:
                return r

    # Substring: e.g. "ivory coast" inside "côte d'ivoire (ivory coast)". Resolve ambiguity if several rows hit.
    subs: list[AdvisoryRow] = []
    for r in rows:
        cn = _norm_key(r.country)
        for cand in cand_norms:
            if not cand or len(cand) < 5:
                continue
            if cand in cn:
                subs.append(r)
                break
    if len(subs) == 1:
        return subs[0]
    if len(subs) > 1:
        subs.sort(key=_best_ratio_for_row, reverse=True)
        if _best_ratio_for_row(subs[0]) >= 0.55:
            return subs[0]

    for r in rows:
        cn = _norm_key(r.country)
        for cand in cand_norms:
            if not cand:
                continue
            if len(cn) >= 6 and len(cand) >= 8 and cn in cand:
                return r

    best: AdvisoryRow | None = None
    best_score = 0.0
    for r in rows:
        sc = _best_ratio_for_row(r)
        if sc > best_score:
            best_score = sc
            best = r
    if best is not None and best_score >= 0.86:
        return best
    return None


def _refresh_from_network() -> tuple[list[AdvisoryRow], str, str | None]:
    """Fetch and parse; returns (rows, source, error_message)."""
    errors: list[str] = []
    for url in (US_ADVISORY_JSON_URL, US_ADVISORY_HTML_URL):
        try:
            text, final = _http_get(url)
            rows, source = _parse_document(text, final)
            if rows:
                return rows, source, None
            errors.append(f"{url} → parsed 0 rows (final {final})")
            logger.error("US advisory parse returned 0 rows after 200 OK (%s)", url)
        except requests.RequestException as e:
            msg = f"{url}: {e}"
            errors.append(msg)
            logger.warning("US advisory fetch failed: %s", msg)
        except Exception as e:
            msg = f"{url}: {e}"
            errors.append(msg)
            logger.warning("US advisory fetch/parse error: %s", msg, exc_info=True)
    return [], "unknown", "; ".join(errors) if errors else "unknown error"


def get_advisory_snapshot() -> AdvisoryTableSnapshot:
    """
    Return cached advisory rows (24h TTL default). Stale-while-error: failed refresh keeps prior rows.
    """
    global _cached_snapshot, _cache_monotonic_at, _last_refresh_error
    now = time.monotonic()
    ttl = _cache_ttl_seconds()
    need_refresh = _cached_snapshot is None or (now - _cache_monotonic_at) >= ttl

    if not need_refresh and _cached_snapshot is not None:
        return AdvisoryTableSnapshot(
            rows=list(_cached_snapshot.rows),
            loaded_at_utc=_cached_snapshot.loaded_at_utc,
            source=_cached_snapshot.source,
            fetch_used_stale_cache=False,
            last_refresh_error=None,
        )

    rows, source, err = _refresh_from_network()
    if rows:
        snap = AdvisoryTableSnapshot(
            rows=rows,
            loaded_at_utc=_utc_now(),
            source=source,
            fetch_used_stale_cache=False,
            last_refresh_error=None,
        )
        _cached_snapshot = snap
        _cache_monotonic_at = now
        _last_refresh_error = None
        return snap

    # Failed refresh — reuse stale cache if any
    _last_refresh_error = err
    if _cached_snapshot is not None:
        logger.warning("US advisory refresh failed; using stale cache: %s", err)
        return AdvisoryTableSnapshot(
            rows=list(_cached_snapshot.rows),
            loaded_at_utc=_cached_snapshot.loaded_at_utc,
            source=_cached_snapshot.source,
            fetch_used_stale_cache=True,
            last_refresh_error=err,
        )

    logger.warning("US advisory: no data and no cache: %s", err)
    return AdvisoryTableSnapshot(
        rows=[],
        loaded_at_utc=_utc_now(),
        source="unknown",
        fetch_used_stale_cache=False,
        last_refresh_error=err,
    )


def format_loaded_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _level_display_line(level: int, level_label: str) -> str:
    """Hero block: large advisory level digit + caption (HTML; mirrors friendliness score layout)."""
    label = (level_label or "").strip()
    lv = max(1, min(4, int(level)))
    m = re.match(rf"Level\s*{level}\s*:\s*(.+)", label, re.I | re.DOTALL)
    if m:
        caption = m.group(1).strip()
    elif label:
        caption = label
    else:
        caption = "U.S. State Department travel advisory level"
    cap_esc = html_module.escape(caption)
    return (
        '<div class="td-advisory-hero">'
        '<div class="td-advisory-hero-kicker">Level</div>'
        f'<div class="td-advisory-hero-level">{lv}</div>'
        f'<div class="td-advisory-hero-caption">{cap_esc}</div>'
        "</div>"
    )


def _clean_advisory_llm_output(raw: str) -> str:
    """
    Some cloud models prepend chain-of-thought in the same string as the answer.
    Keep 1–2 traveler-facing sentences; drop planning / meta lines.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    # Answer sometimes appears inside straight or curly quotes
    for m in re.finditer(r"['\"“]([^'\"”]{25,800})['\"”]", raw):
        cand = m.group(1).strip()
        cl = cand.lower()
        if "state department" in cl or "travel advisory" in cl or "u.s. citizens" in cl:
            return _trim_to_two_sentences(cand)

    for key in ("the u.s. state department", "u.s. state department", "the state department"):
        i = low.find(key)
        if i != -1:
            rest = raw[i:].strip()
            return _trim_to_two_sentences(rest)

    parts = re.split(r"(?<=[.!?])\s+", raw)
    bad_open = re.compile(
        r"^(we need|we must|let'?s|i'?ll|the user|output plain|do not|no markdown|"
        r"that'?s fine|this is one|no other|use only|must use|summarize for)",
        re.I,
    )
    good: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) < 12:
            continue
        if bad_open.match(p):
            continue
        if "we need to" in p.lower() or "we must" in p.lower()[:30]:
            continue
        good.append(p)
    out = " ".join(good[:2]).strip()
    if len(out) >= 20:
        return out
    return _trim_to_two_sentences(raw)


def _protect_abbrevs(s: str) -> str:
    """Avoid splitting sentences on dots in U.S., U.N., etc."""
    s = re.sub(r"\bU\.S\.(?=[\s,])", "U_S_", s)
    s = re.sub(r"\bU\.N\.(?=[\s,])", "U_N_", s)
    s = re.sub(r"\bE\.U\.(?=[\s,])", "E_U_", s)
    return s


def _unprotect_abbrevs(s: str) -> str:
    return s.replace("U_S_", "U.S.").replace("U_N_", "U.N.").replace("E_U_", "E.U.")


def _to_plain_advisory_blurb(s: str) -> str:
    """Advisory summary is shown inside markdown UI; strip * so half-finished **bold** does not break rendering."""
    return re.sub(r"[*_`#]+", "", (s or "")).strip()


def _trim_to_two_sentences(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", _protect_abbrevs(s))
    out = []
    for c in chunks:
        c = _unprotect_abbrevs(c.strip())
        if not c:
            continue
        out.append(c)
        if len(out) >= 2:
            break
    return " ".join(out) if out else s[:500]


def build_travel_advisory_markdown(
    row: AdvisoryRow | None,
    snapshot: AdvisoryTableSnapshot,
    summary_text: str,
) -> str:
    """Markdown body for essential.travel_advisory (under **Travel advisory** heading)."""
    lines: list[str] = []
    loaded = format_loaded_timestamp(snapshot.loaded_at_utc)
    hours = max(1, _cache_ttl_seconds() // 3600)
    lines.append(
        f"> U.S. advisory list loaded {loaded} · refresh at most every {hours} h.\n"
    )
    if snapshot.fetch_used_stale_cache and snapshot.last_refresh_error:
        lines.append("> Live refresh failed; showing last successful download.\n")
    if not snapshot.rows:
        lines.append(
            "Advisory feed could not be read; verify on [travel.state.gov](https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html)."
        )
        if snapshot.last_refresh_error:
            lines.append(f"*({snapshot.last_refresh_error[:200]})*")
        return "\n\n".join(lines)

    if row is None:
        lines.append("Could not match this destination to a row in the current U.S. travel advisory table.")
        return "\n\n".join(lines)

    lines.append(_level_display_line(row.level, row.level_label))
    if row.risk_indicators:
        lines.append("*Risk indicators:* " + ", ".join(row.risk_indicators) + ".")
    st = _to_plain_advisory_blurb(summary_text)
    if st:
        lines.append(st)
    return "\n\n".join(lines)


def _advisory_num_predict() -> int:
    raw = (os.environ.get("OLLAMA_ADVISORY_NUM_PREDICT") or "").strip()
    if raw.isdigit():
        return max(64, int(raw))
    return 512


def summarize_advisory_with_ollama(row: AdvisoryRow, *, num_predict: int | None = None) -> str:
    """1–2 plain sentences using the auxiliary Ollama model (resolved_model_other / ollama_chat default)."""
    from ollama_client import ollama_chat

    facts = {
        "country": row.country,
        "level": row.level,
        "level_label": row.level_label,
        "date_issued": row.date_issued,
        "risk_indicators": row.risk_indicators,
    }
    payload = json.dumps(facts, ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "You write brief travel guidance for U.S. citizens. "
                "Reply with ONLY the final summary: exactly one or two complete sentences, plain text. "
                "The user JSON is the authoritative U.S. State Department advisory row: never contradict "
                "its country, numeric level, level_label, date_issued, or risk_indicators. "
                "Do not only repeat the level wording; add concise, practical traveler context that fits "
                "that advisory—e.g. what the risk indicators imply for behavior, situational awareness, or "
                "sensible precautions—using general knowledge where it clearly aligns with those facts. "
                "No planning or meta commentary, no bullet lists, no markdown (no asterisks), "
                "no quotation marks wrapping your whole reply."
            ),
        },
        {
            "role": "user",
            "content": (
                "Draft the 1–2 sentences for someone planning a trip. JSON facts:\n"
                f"{payload}\n\n"
                "Be specific to this destination and advisory; avoid generic filler that ignores the indicators."
            ),
        },
    ]
    np = num_predict if num_predict is not None else _advisory_num_predict()
    raw = ollama_chat(messages, num_predict=np, timeout=90)
    text = _to_plain_advisory_blurb(_clean_advisory_llm_output(raw))
    text = _trim_to_two_sentences(text)
    return text
