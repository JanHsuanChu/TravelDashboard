# google_places_client.py
# Places API (New): Text Search + Place Details — see
# https://developers.google.com/maps/documentation/places/web-service/text-search
# https://developers.google.com/maps/documentation/places/web-service/place-details

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_BASE = "https://places.googleapis.com/v1"

# Text Search (New): field mask paths use the "places." prefix.
SEARCH_FIELD_MASK = (
    "places.name,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.rating,"
    "places.userRatingCount,"
    "places.types,"
    "places.editorialSummary"
)

DETAIL_FIELD_MASK = (
    "id,"
    "name,"
    "displayName,"
    "formattedAddress,"
    "location,"
    "rating,"
    "userRatingCount,"
    "types,"
    "editorialSummary,"
    "reviews,"
    "websiteUri,"
    "googleMapsUri,"
    "priceLevel"
)


def _api_key() -> str:
    return (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()


def _details_contain_reason(details: Any, reason: str) -> bool:
    if not isinstance(details, list):
        return False
    for item in details:
        if not isinstance(item, dict):
            continue
        if item.get("reason") == reason:
            return True
        meta = item.get("metadata")
        if isinstance(meta, dict) and meta.get("reason") == reason:
            return True
    return False


def _format_places_api_error(resp: requests.Response, operation: str) -> str:
    """Human-readable error including Google JSON body when present."""
    url = getattr(resp, "url", "") or ""
    parts = [f"{operation} failed: HTTP {resp.status_code}."]
    details: Any = None
    try:
        data = resp.json()
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            if err.get("message"):
                parts.append(f"message: {err['message']}")
            if err.get("status"):
                parts.append(f"status: {err['status']}")
            details = err.get("details")
            if details:
                try:
                    det_s = json.dumps(details, default=str)[:1500]
                except (TypeError, ValueError):
                    det_s = str(details)[:1500]
                parts.append(f"details: {det_s}")
        else:
            parts.append(resp.text[:2000] if resp.text else "(empty body)")
    except (json.JSONDecodeError, ValueError):
        parts.append((resp.text or "(no body)")[:2000])

    if url:
        parts.append(f"URL: {url}")

    if resp.status_code == 403 and _details_contain_reason(details, "API_KEY_SERVICE_BLOCKED"):
        parts.append(
            "Fix API_KEY_SERVICE_BLOCKED: (1) APIs & Services → Library → enable “Places API (New)” "
            "(places.googleapis.com — not only the older “Places API” if listed separately). "
            "(2) APIs & Services → Credentials → your API key → API restrictions: either “Don’t restrict key” "
            "or explicitly allow “Places API (New)” / places.googleapis.com (legacy “Places API” alone may not cover SearchText). "
            "(3) If you use Application restrictions, avoid “HTTP referrers” for this Python app—use “None” or IP. "
            "Save and wait a few minutes."
        )
    elif resp.status_code == 403:
        parts.append(
            "403 often means: billing enabled; “Places API (New)” enabled; API key allowed for that API; "
            "and application restrictions not blocking server-side calls (avoid HTTP referrers for Shiny)."
        )

    return " ".join(parts)


def _raise_for_places_status(resp: requests.Response, operation: str) -> None:
    if resp.ok:
        return
    msg = _format_places_api_error(resp, operation)
    err = requests.HTTPError(msg)
    err.response = resp
    raise err


def search_restaurants(
    text_query: str,
    *,
    api_key: str | None = None,
    page_size: int = 20,
    language_code: str = "en",
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """
    POST places:searchText with includedType=restaurant.
    Returns raw Place objects (JSON dicts) from the API.
    """
    key = api_key if api_key is not None else _api_key()
    if not key:
        raise ValueError("GOOGLE_PLACES_API_KEY is not set.")

    body: dict[str, Any] = {
        "textQuery": text_query,
        "includedType": "restaurant",
        "languageCode": language_code,
        "pageSize": min(max(page_size, 1), 20),
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
    }
    r = requests.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=timeout)
    if r.status_code == 400 and "includedType" in body:
        body.pop("includedType", None)
        r = requests.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=timeout)
    _raise_for_places_status(r, "Google Places Text Search (places:searchText)")
    data = r.json()
    return list(data.get("places") or [])


def get_place_details(
    place_resource_name: str,
    *,
    api_key: str | None = None,
    language_code: str = "en",
    timeout: int = 30,
) -> dict[str, Any]:
    """
    GET Place by resource name, e.g. places/ChIJ...

    Correct URL: https://places.googleapis.com/v1/places/{placeId}
    Do not call quote() on the full "places/..." string (that produces places%2F... → 404).
    """
    key = api_key if api_key is not None else _api_key()
    if not key:
        raise ValueError("GOOGLE_PLACES_API_KEY is not set.")

    raw = unquote((place_resource_name or "").strip())
    if raw.startswith("places/"):
        place_id = raw.removeprefix("places/")
    else:
        place_id = raw
    place_id = place_id.strip("/")
    if not place_id:
        raise ValueError("Empty place id for Place Details.")
    # Encode only the id segment (ChIJ… ids are usually safe; quote handles edge cases).
    url = f"{PLACES_BASE}/places/{quote(place_id, safe='')}"
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": DETAIL_FIELD_MASK,
    }
    params = {}
    if language_code:
        params["languageCode"] = language_code
    r = requests.get(url, headers=headers, params=params or None, timeout=timeout)
    _raise_for_places_status(r, "Google Places Place Details")
    return r.json()


def localized_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict) and "text" in obj:
        return str(obj.get("text") or "").strip()
    return ""
