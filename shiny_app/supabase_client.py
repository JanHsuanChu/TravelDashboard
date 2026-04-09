# supabase_client.py
# Supabase REST client for Travel Dashboard (server-side; use service_role or anon per your RLS).

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

_client: Client | None = None


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        load_dotenv(env)


def get_supabase() -> Client:
    global _client
    _load_dotenv()
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            raise ValueError("Set SUPABASE_URL and SUPABASE_KEY in shiny_app/.env")
        _client = create_client(url, key)
    return _client


def fetch_recent_preferences(limit: int = 50) -> list[dict[str, Any]]:
    sb = get_supabase()
    r = (
        sb.table("preference")
        .select(
            "preference_id, user_id, created_at, food_like_text, food_dislike_text, "
            "dietary_restrictions, food_tags, dining_preference"
        )
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return r.data or []


def get_or_create_user(*, email: str, first_name: str) -> str:
    """Return app_user.user_id (UUID string)."""
    sb = get_supabase()
    r = sb.table("app_user").select("user_id").eq("email", email.strip()).limit(1).execute()
    if r.data:
        return str(r.data[0]["user_id"])
    ins = (
        sb.table("app_user")
        .insert({"email": email.strip(), "first_name": first_name.strip()})
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
