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


def _normalize_ollama_host(raw: str | None) -> str:
    """Base URL only; client appends /api/chat. Strips accidental /api or /api/chat suffix (avoids 404)."""
    h = (raw or "").strip().strip('"').strip("'").rstrip("/")
    if not h:
        return "https://ollama.com"
    for suf in ("/api/chat", "/api"):
        if h.lower().endswith(suf):
            h = h[: -len(suf)].rstrip("/")
    return h or "https://ollama.com"


_OLLAMA_HOST = _normalize_ollama_host(os.environ.get("OLLAMA_HOST"))
OLLAMA_CHAT_URL = _OLLAMA_HOST + "/api/chat"

# Agent 2 = plan JSON (dining + essential scaffold). Agent 1 in this app = Places + embeddings only (no Ollama).
DEFAULT_MODEL_AGENT2 = "nemotron-3-nano:30b-cloud"
# Travel advisory micro-summary, friendliness HTML report prose, and any generic ollama_chat without an explicit model.
DEFAULT_MODEL_OTHER = "gpt-oss:20b-cloud"


def resolved_model_agent1() -> str:
    """Reserved for a future Agent 1 LLM step. Today Agent 1 does not call Ollama (same tier as Agent 2 when added)."""
    v = (os.environ.get("OLLAMA_MODEL_AGENT1") or "").strip()
    if v:
        return v
    return resolved_model_agent2()


def resolved_model_agent2() -> str:
    """Plan LLM (Agent 2): main Generate JSON."""
    v = (os.environ.get("OLLAMA_MODEL_AGENT2") or "").strip()
    if v:
        return v
    v = (os.environ.get("OLLAMA_MODEL_AGENTS") or "").strip()
    if v:
        return v
    return DEFAULT_MODEL_AGENT2


def resolved_model_other() -> str:
    """All non–Agent-2 chat calls (advisory blurb, friendliness report helper, etc.)."""
    v = (os.environ.get("OLLAMA_MODEL_OTHER") or "").strip()
    if v:
        return v
    v = (os.environ.get("OLLAMA_MODEL_AUXILIARY") or "").strip()
    if v:
        return v
    v = (os.environ.get("OLLAMA_MODEL") or "").strip()
    if v:
        return v
    return DEFAULT_MODEL_OTHER


def resolved_chat_model(explicit: str | None = None) -> str:
    """Backward-compatible alias: explicit wins; else auxiliary (OTHER) tier."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return resolved_model_other()


def ollama_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    timeout: int = 120,
    num_predict: int | None = None,
) -> str:
    key = os.environ.get("OLLAMA_API_KEY", "")
    if not key:
        raise ValueError("OLLAMA_API_KEY is not set.")

    m = (model or "").strip() or resolved_model_other()
    body: dict[str, Any] = {
        "model": m,
        "messages": messages,
        "stream": False,
    }
    np_val: int | None = num_predict
    if np_val is None:
        np_raw = (os.environ.get("OLLAMA_NUM_PREDICT") or "").strip()
        if np_raw.isdigit():
            np_val = int(np_raw)
    if np_val is not None:
        body["options"] = {"num_predict": int(np_val)}
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(OLLAMA_CHAT_URL, headers=headers, json=body, timeout=timeout)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        if resp.status_code == 404:
            raise ValueError(
                f"Ollama HTTP 404 for {OLLAMA_CHAT_URL!r}. If OLLAMA_HOST is set, use the base host only "
                f"(e.g. https://ollama.com), not …/api or …/api/chat. "
                f"Confirm the model name exists on that host (see OLLAMA_MODEL_AGENT2 / OLLAMA_MODEL_OTHER / OLLAMA_MODEL)."
            ) from e
        raise
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
