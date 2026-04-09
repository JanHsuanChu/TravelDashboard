# ollama_client.py
# Ollama Cloud chat — template aligned with dsai/03_query_ai/03_ollama_cloud.py

from __future__ import annotations

import json
import os
from typing import Any

import requests

OLLAMA_CHAT_URL = os.environ.get("OLLAMA_HOST", "https://ollama.com").rstrip("/") + "/api/chat"
DEFAULT_MODEL = "gpt-oss:20b-cloud"


def ollama_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    timeout: int = 180,
) -> str:
    key = os.environ.get("OLLAMA_API_KEY", "")
    if not key:
        raise ValueError("OLLAMA_API_KEY is not set.")

    body: dict[str, Any] = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
    }
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
