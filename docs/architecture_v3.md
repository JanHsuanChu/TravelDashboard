This doc is **Architecture V3** for TravelDashboard.

It updates the prior `docs/architecture.md` diagrams/terminology to reflect an **agentic loop Orchestrator** that wraps the existing recommendation components.

Key terminology:
- **Agentic loop**: a bounded multi-turn controller that can (a) rerun retrieval/rerank, (b) ask the user clarifying questions for quality, (c) enforce hard guardrails, and (d) decide when to stop.
- **Agent 1**: deterministic restaurant retrieval + embedding ranking (Google Places + local embedding similarity).
- **Agent 2**: plan LLM that produces the structured JSON used by the UI.
- **Friendliness pipeline**: mostly deterministic scoring + report generation (may include an optional single LLM call for prose). This is **not** an agentic loop.

---

## Target pipeline (Orchestrator + multi-component)

The Orchestrator runs **inside the Shiny app** (same UI) and controls whether to:
- rerun Agent 1 retrieval/rerank,
- call Agent 2 to draft a recommendation plan,
- apply hard guardrails (dietary + location) before any recommendation is shown,
- ask the user a targeted question to improve quality,
- stop and finalize,
- store turns + feedback in Supabase to improve future reranking.

```mermaid
---
config:
  layout: dagre
---
flowchart TB
    Dashboard["Travel Dashboard (UI)\n-Trip + food prefs\n-Chat + feedback"]
    Supabase[("Supabase\n-users, preferences\n-agent_sessions/turns/feedback/weights")]
    Orchestrator["Orchestrator (Agentic Loop)\n-Ask/stop policy\n-Retry retrieval/rerank\n-Guardrails\n-Persist memory"]

    RestaurantData["Restaurant data\nGoogle Places API (New)"]
    Agent1["Agent 1 (Deterministic)\nPlaces retrieval + embeddings RAG\nCandidate ranking"]
    Agent2["Agent 2 (LLM)\nPlan JSON: dining + essential"]

    MacroData["Macro data\nWorld Bank API"]
    FriendlinessPipe["Friendliness pipeline\nDeterministic scoring + HTML report\n(Optional single LLM call for prose)"]

    Output["Dashboard display\n-Dining + Essential\n-Friendliness\n-Map/place selection"]

    Dashboard --> Orchestrator
    Orchestrator <--> Supabase

    Orchestrator --> Agent1
    Agent1 --> RestaurantData

    Orchestrator --> Agent2
    Agent1 -->|"ranked candidates"| Agent2

    Orchestrator --> FriendlinessPipe
    FriendlinessPipe --> MacroData

    Agent2 -->|"plan JSON"| Output
    FriendlinessPipe -->|"scores + report"| Output
    Orchestrator -->|"guardrailed + finalized"| Output
```

---

## Responsibilities

### Orchestrator (agentic loop)
- **Hard guardrails** (no user feedback required)
  - **Dietary**: do not pass recommendations unless compliant; if uncertain, treat as non-compliant.
  - **Location**: do not pass venues outside the destination.
- **Quality conversation** (feedback for better recommendations)
  - Ask 1 targeted question when preferences are underspecified or the user signals dissatisfaction.
  - Decide whether to **auto-rerun retrieval/rerank** vs **ask the user**.
- **Budgets**
  - LLM turns: default **min 2 / max 6**.
  - Deterministic retrieval reruns per request: cap at **2**.
- **Memory**
  - Store session turns + feedback; update lightweight ranking weights for future reranks.

### Agent 1 (existing)
- Google Places retrieval + Place Details + embedding similarity ranking.

### Agent 2 (existing)
- Produces the structured JSON plan used by the UI.

### Friendliness pipeline (existing; not agentic)
- Deterministic scoring from macro indicators; optional single LLM call for narrative prose.

---

## Current implementation mapping (Shiny)

- Agent 1: `shiny_app/restaurant_rag.py` + `shiny_app/google_places_client.py`
- Agent 2: `shiny_app/plan_logic.py` + `shiny_app/ollama_client.py` (invoked from `shiny_app/server.py`)
- Friendliness pipeline: `shiny_app/travel_friendliness/` (World Bank scoring + report)
- Orchestrator (new): `shiny_app/agent_loop.py` (proposed) called from `shiny_app/server.py` Generate handler

