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

# supabase-py 2.15.x only accepts JWT-shaped keys (legacy anon / service_role). New dashboard keys
# (sb_publishable_… / sb_secret_…) fail its local validation with "Invalid API key" before any HTTP call.
# sb_secret_* also needs a non-browser User-Agent at the gateway; we set both via SyncClientOptions.
_SERVER_UA = "TravelDashboard-Shiny/1.0 (Python; server; supabase-py)"

# Mirrors supabase._sync.client.SyncClient __init__ check (so we can raise a clearer error).
_SUPABASE_PY_JWT_KEY_RE = re.compile(
    r"^[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$"
)


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
    global _client
    _load_dotenv()
    if _client is None:
        url = _env_clean("SUPABASE_URL").rstrip("/")
        key = _env_clean("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Set SUPABASE_URL and SUPABASE_KEY in shiny_app/.env")
        if not _SUPABASE_PY_JWT_KEY_RE.match(key):
            raise ValueError(
                "SUPABASE_KEY must be a legacy JWT (anon or service_role — usually starts with 'eyJ'). "
                "The supabase-py version in this project does not accept new dashboard keys "
                "(sb_publishable_… or sb_secret_…). In Supabase: Project Settings → API → "
                "copy the anon (legacy) JWT, or service_role for server-only use."
            )
        opts = SyncClientOptions(
            headers={
                "User-Agent": _SERVER_UA,
                "X-Client-Info": "travel-dashboard-shiny",
            },
        )
        _client = create_client(url, key, opts)
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
