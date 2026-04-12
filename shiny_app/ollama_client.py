# ollama_client.py
# Ollama Cloud chat — template aligned with dsai/03_query_ai/03_ollama_cloud.py

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "https://ollama.com").rstrip("/")
OLLAMA_CHAT_URL = _OLLAMA_HOST + "/api/chat"

# Faster default than 20B cloud; override with OLLAMA_MODEL (e.g. gpt-oss:20b-cloud for prior behavior).
DEFAULT_CHAT_MODEL = "llama3.2:3b"


def resolved_chat_model(explicit: str | None = None) -> str:
    """Explicit arg wins, then OLLAMA_MODEL env, then DEFAULT_CHAT_MODEL."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env = (os.environ.get("OLLAMA_MODEL") or "").strip()
    return env or DEFAULT_CHAT_MODEL


def ollama_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    timeout: int = 120,
) -> str:
    key = os.environ.get("OLLAMA_API_KEY", "")
    if not key:
        raise ValueError("OLLAMA_API_KEY is not set.")

    body: dict[str, Any] = {
        "model": resolved_chat_model(model),
        "messages": messages,
        "stream": False,
    }
    np_raw = (os.environ.get("OLLAMA_NUM_PREDICT") or "").strip()
    if np_raw.isdigit():
        body["options"] = {"num_predict": int(np_raw)}
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(OLLAMA_CHAT_URL, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    thinking = (msg.get("thinking") or "").strip()
    if not content and thinking:
        return thinking
    return content


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse first JSON object from model output (handles optional fences)."""
    text = text.strip()
    if "```" in text:
        start = text.find("```")
        rest = text[start + 3 :]
        if rest.lower().startswith("json"):
            rest = rest[4:]
        end = rest.find("```")
        if end != -1:
            text = rest[:end].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try substring between first { and last }
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b > a:
            try:
                return json.loads(text[a : b + 1])
            except json.JSONDecodeError:
                pass
    return None
