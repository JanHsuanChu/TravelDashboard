# supabase_client.py
# Supabase REST client for Travel Dashboard (server-side; use service_role or anon per your RLS).

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

_client: Client | None = None
# Recreate client when URL or normalized key changes (fixes stale client after .env edits without restart).
_client_env_sig: tuple[str, str] | None = None

try:
    from supabase._sync.client import SupabaseException as _SupabaseClientException
except ImportError:  # pragma: no cover
    _SupabaseClientException = Exception

# supabase-py 2.15.x only accepts JWT-shaped keys (legacy anon / service_role). New dashboard keys
# (sb_publishable_… / sb_secret_…) fail its local validation with "Invalid API key" before any HTTP call.
# sb_secret_* also needs a non-browser User-Agent at the gateway; we set both via SyncClientOptions.
_SERVER_UA = "TravelDashboard-Shiny/1.0 (Python; server; supabase-py)"


def _normalize_supabase_key(raw: str) -> str:
    """Strip BOM, wrapping quotes, whitespace, and invisible Unicode (common copy/paste from dashboards)."""
    v = (raw or "").strip()
    if v.startswith("\ufeff"):
        v = v.lstrip("\ufeff").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    # ZWSP/ZWJ/ZWNJ, BOM, NBSP, narrow NBSP, word joiner — can sit inside "eyJ" and break JWT checks.
    v = re.sub(r"[\u200b-\u200d\ufeff\u00a0\u202f\u2060]+", "", v)
    v = "".join(v.split())
    return v


def _supabase_key_hint(key: str) -> str:
    """Non-secret hint so users can see what the process actually read."""
    if not key:
        return "The loaded SUPABASE_KEY is empty — check the file that wins last (see below)."
    if key.startswith("eyJ"):
        return (
            "Key looks JWT-shaped (eyJ…) but the client still rejected it — often invisible characters "
            "from copy/paste, a truncated line in .env, or a stale value until the server process restarts."
        )
    if key.startswith("sb_publishable"):
        return (
            "Loaded key is a new Publishable key (sb_publishable_…). This app needs the Legacy anon JWT (eyJ…). "
            "Dashboard: Project Settings → API Keys → Legacy API keys → anon."
        )
    if key.startswith("sb_secret"):
        return (
            "Loaded key is a new Secret key (sb_secret_…). Use Legacy anon or service_role (eyJ…) for supabase-py."
        )
    return "Loaded key does not match a legacy JWT (expected a long anon or service_role value starting with eyJ)."


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        # override=True: a stale/wrong SUPABASE_* in the shell or OS must not beat shiny_app/.env
        load_dotenv(env, override=True)


def _env_clean(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if v.startswith("\ufeff"):
        v = v.lstrip("\ufeff").strip()
    return v


def get_supabase() -> Client:
    global _client, _client_env_sig
    _load_dotenv()
    url = _env_clean("SUPABASE_URL").rstrip("/")
    # Prefer a server-side key when available (avoids RLS blocking reads on app_user/preference).
    # SUPABASE_SERVICE_KEY must be a legacy JWT (starts with eyJ) like service_role.
    raw_key = _env_clean("SUPABASE_SERVICE_KEY") or _env_clean("SUPABASE_KEY")
    key = _normalize_supabase_key(raw_key)
    if not url or not key:
        raise ValueError("Set SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_KEY) in shiny_app/.env")

    sig = (url, key)
    if _client is not None and _client_env_sig == sig:
        return _client

    _client = None
    _client_env_sig = None

    if key.startswith(("sb_publishable_", "sb_secret_")):
        raise ValueError(
            "SUPABASE_KEY is a new-style Publishable/Secret key (sb_…). supabase-py needs the Legacy anon "
            "or service_role JWT (starts with eyJ). Dashboard: Project Settings → API Keys → Legacy API keys. "
            "https://supabase.com/docs/guides/api/api-keys#where-to-find-keys"
        )

    opts = SyncClientOptions(
        headers={
            "User-Agent": _SERVER_UA,
            "X-Client-Info": "travel-dashboard-shiny",
        },
    )
    try:
        _client = create_client(url, key, opts)
    except _SupabaseClientException as e:
        msg = str(e).strip() or repr(e)
        if "Invalid API key" in msg or "API key" in msg:
            hint = _supabase_key_hint(key)
            raise ValueError(
                f"Supabase rejected this API key ({msg}). {hint} "
                "If the key looks correct, re-copy the Legacy anon JWT from the dashboard (no spaces or line breaks), "
                "save shiny_app/.env, and fully restart the Shiny process (not only browser refresh). "
                "Parent-folder .env files load before shiny_app/.env — a blank or sb_* SUPABASE_KEY there can be "
                "overridden only if this file defines SUPABASE_KEY on its own line."
            ) from e
        raise
    _client_env_sig = sig
    return _client


def normalize_email(email: str) -> str:
    """Trim and lowercase for storage and hashing."""
    return (email or "").strip().lower()


def email_hash_normalized(normalized_email: str) -> str:
    """SHA-256 hex of UTF-8 bytes (matches migration 004 in Postgres)."""
    return hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()


def email_hash_raw(email: str) -> str:
    """Hash of normalized email from raw input."""
    return email_hash_normalized(normalize_email(email))


def fetch_user_and_latest_preference(
    email: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Return (app_user row, latest preference row or None) for this email identity.
    Lookup by email_hash first; fallback to email equality on normalized form.
    """
    em = normalize_email(email)
    if not em or "@" not in em:
        return None, None
    h = email_hash_normalized(em)
    sb = get_supabase()
    r = sb.table("app_user").select("user_id, first_name, email, email_hash").eq("email_hash", h).limit(1).execute()
    if not r.data:
        r = sb.table("app_user").select("user_id, first_name, email, email_hash").eq("email", em).limit(1).execute()
    if not r.data:
        return None, None
    user = r.data[0]
    uid = user["user_id"]
    pr = (
        sb.table("preference")
        .select(
            "preference_id, user_id, created_at, food_like_text, food_dislike_text, "
            "dietary_restrictions, food_tags"
        )
        .eq("user_id", uid)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    pref = pr.data[0] if pr.data else None
    return user, pref


def get_or_create_user(*, email: str, first_name: str) -> str:
    """Return app_user.user_id (UUID string). Sets email_hash on insert."""
    em = normalize_email(email)
    if not em:
        raise ValueError("email required")
    h = email_hash_normalized(em)
    sb = get_supabase()
    r = sb.table("app_user").select("user_id").eq("email_hash", h).limit(1).execute()
    if r.data:
        return str(r.data[0]["user_id"])
    r2 = sb.table("app_user").select("user_id").eq("email", em).limit(1).execute()
    if r2.data:
        return str(r2.data[0]["user_id"])
    ins = (
        sb.table("app_user")
        .insert({"email": em, "first_name": first_name.strip(), "email_hash": h})
        .execute()
    )
    if ins.data:
        row = ins.data[0] if isinstance(ins.data, list) else ins.data
        return str(row["user_id"])
    raise RuntimeError("Could not create or load app_user.")


def insert_preference(
    *,
    user_id: str,
    food_like_text: str | None,
    food_dislike_text: str | None,
    dietary_restrictions: str | None,
    food_tags: dict[str, Any],
) -> dict[str, Any]:
    sb = get_supabase()
    row = {
        "user_id": user_id,
        "food_like_text": food_like_text or None,
        "food_dislike_text": food_dislike_text or None,
        "dietary_restrictions": dietary_restrictions or None,
        "food_tags": food_tags,
    }
    ins = sb.table("preference").insert(row).execute()
    if ins.data:
        return ins.data[0] if isinstance(ins.data, list) else ins.data
    raise RuntimeError("Insert failed (no data returned).")


# ----------------------------
# Agentic loop memory helpers
# ----------------------------


def upsert_agent_session(
    *,
    session_id: str,
    user_id: str | None,
    destination: dict[str, Any] | None,
) -> dict[str, Any]:
    sb = get_supabase()
    row = {
        "session_id": session_id,
        "user_id": user_id,
        "destination": destination or None,
        "last_active_at": "now()",
    }
    # supabase-py doesn't expose PostgREST "now()" well; let DB default handle on insert.
    # For updates we can just omit last_active_at; a trigger can manage it if desired.
    ins = sb.table("agent_sessions").upsert(
        {"session_id": session_id, "user_id": user_id, "destination": destination or None}
    ).execute()
    if ins.data:
        return ins.data[0] if isinstance(ins.data, list) else ins.data
    return {"session_id": session_id, "user_id": user_id, "destination": destination or None}


def insert_agent_turn(
    *,
    session_id: str,
    turn_idx: int,
    role: str,
    content: str,
    json_payload: dict[str, Any] | None = None,
) -> None:
    sb = get_supabase()
    sb.table("agent_turns").insert(
        {
            "session_id": session_id,
            "turn_idx": int(turn_idx),
            "role": role,
            "content": content,
            "json_payload": json_payload,
        }
    ).execute()


def insert_agent_feedback(
    *,
    session_id: str,
    user_id: str | None,
    venue_name: str | None,
    signal_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    sb = get_supabase()
    sb.table("agent_feedback").insert(
        {
            "session_id": session_id,
            "user_id": user_id,
            "venue_name": venue_name,
            "signal_type": signal_type,
            "details": details,
        }
    ).execute()


def fetch_user_reco_weights(*, user_id: str) -> dict[str, Any]:
    sb = get_supabase()
    r = sb.table("user_reco_weights").select("weights").eq("user_id", user_id).limit(1).execute()
    if r.data:
        row = r.data[0]
        w = row.get("weights") if isinstance(row, dict) else None
        return w if isinstance(w, dict) else {}
    return {}


def upsert_user_reco_weights(*, user_id: str, weights: dict[str, Any]) -> None:
    sb = get_supabase()
    sb.table("user_reco_weights").upsert({"user_id": user_id, "weights": weights}).execute()
