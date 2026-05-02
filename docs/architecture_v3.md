This doc is **Architecture V3** for TravelDashboard.

It updates the prior `docs/architecture.md` diagrams/terminology to reflect the implemented **agentic loop Orchestrator** that wraps the existing recommendation components.

Key terminology:
- **Agentic loop**: a bounded controller that runs Agent 1 + Agent 2 with deterministic validation/repair and a bounded QC loop (QC Agent).
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
- surface status/QC evidence in chat UI and status widgets.

```mermaid
---
config:
  layout: dagre
---
flowchart TB
    DashIn["Dashboard inputs\n(ui.py widgets + server.py observe)\nTrip · compare · when · food · identity\nSave · Generate · Food Guide send"]
    DashOut["Dashboard outputs\n(render.ui reactive)\nDishes dining map · Essential · Friendliness\nFood Guide panel · QC / status"]
    Supabase[("Supabase\nusers + preferences")]
    Orchestrator["Orchestrator (agent_loop.py)\nAgent 1 → Agent 2\nGuardrails + QC loop"]

    RestaurantData["Restaurant data\nGoogle Places API (New)"]
    Agent1["Agent 1 (Deterministic)\nPlaces retrieval + embeddings RAG\nCandidate ranking"]
    Agent2["Agent 2 (LLM)\nPlan JSON: dining + essential"]

    MacroData["Macro data\nWorld Bank API"]
    FriendlinessPipe["Friendliness pipeline\nDeterministic scoring + HTML report\n(Optional single LLM call for prose)"]

    DashIn <-->|"Save · preload"| Supabase

    DashIn -->|"Generate · Food Guide Send"| Orchestrator

    Orchestrator --> Agent1
    Agent1 --> RestaurantData

    Orchestrator --> Agent2
    Agent1 -->|"ranked candidates"| Agent2
    Agent2 -->|"plan JSON\n(validate / QC / repair)"| Orchestrator

    Orchestrator -->|"accepted plan + markers\n(write reactive state)"| DashOut

    DashIn -->|"Generate parallel thread"| FriendlinessPipe
    FriendlinessPipe --> MacroData
    FriendlinessPipe -->|"scores + report"| DashOut

    classDef Rose stroke-width:1px, stroke-dasharray:none, stroke:#FF5978, fill:#FFDFE5, color:#8E2236
    style DashIn fill:#f4d7d7
    style DashOut fill:#f4d7d7
    style Supabase fill:#e8e8e8
    style Orchestrator stroke:#000000,color:#000000,fill:#f4d7d7
    style RestaurantData fill:#e8e8e8
    style Agent1 fill:#f4d7d7
    style Agent2 fill:#f4d7d7
    style MacroData fill:#e8e8e8
    style FriendlinessPipe fill:#f4d7d7
```

**How the app actually wires this:** **`DashIn`** is what the user edits and clicks; **`DashOut`** is what Shiny redraws from `reactive` values. Agent 2 runs **inside** `run_orchestrator_loop`. The loop returns finalized JSON to **`server.py`**, which runs **`validate_plan_guardrails`**, then updates **`plan_state` / markers** so **`DashOut`** refreshes Dining + Essential. **Supabase** hooks only **Save · preload** (inputs path). **Friendliness** starts from **Generate** on the inputs side in parallel with the orchestrator—not from `agent_loop.py`.

---

## Responsibilities

### Orchestrator (agentic loop)
- **Hard guardrails** (no user feedback required)
  - **Dietary**: do not pass recommendations unless compliant; if uncertain, treat as non-compliant.
  - **Location**: do not pass venues outside the destination.
- **Quality loop**
  - Runs Agent 2 in bounded turns and retries on guardrail failures.
  - Runs QC Agent (up to 3 turns) and feeds QC evidence back to Agent 2 when needed.
  - Supports clarification state (`needs_clarification`) and chat refinements post-Generate.
- **Budgets**
  - LLM turns: default **min 2 / max 6**.
  - Deterministic retrieval reruns per request: bounded (`LoopBudgets.max_retrieval_reruns`, currently 6 from server calls).
  - QC Agent turns: max **3**.
- **Persistence / evidence**
  - Persists QC evidence logs to `shiny_app/data/qc_logs/`.
  - **Supabase is not accessed here.** Save / preload is **`DashIn`** ↔ **`server.py`** ↔ Supabase; Food Guide continuity is **`reactive` state** consumed by **`DashOut`**.
- **Food Guide (chat) refinements** (post-Generate)
  - Each successful Send reruns **`run_orchestrator_loop`** (Agent 1 → Agent 2 → guardrails → optional QC), then copies the finalized plan **and** Agent 1 marker list into reactive state so **Dining — recommended places** and Food Guide recommendation cards stay aligned.
  - The user’s message is fed into Agent 1 as **`chat_refinement`**: it leads the **embedding query**, adds keyword tokens for lexical boost, and (when present) adds an extra **Places Text Search** phrase (`"{refinement} {destination}"`) alongside the baseline restaurant queries (`shiny_app/restaurant_rag.py`).
  - When phrasing implies **alternative / fresh picks** (e.g. “different recommendations”, “other restaurants”), the server excludes current **`dining.places` titles from the prior plan** before ranking and asks Agent 1 for a **larger `top_k`**, reducing repeat venues when Google returns enough breadth.

### Agent 1 (existing)
- Google Places retrieval + Place Details + embedding similarity ranking; optional **`chat_refinement`** augment for Food Guide turns (above).

### Agent 2 (existing)
- Produces the structured JSON plan used by the UI.

### Friendliness pipeline (existing; not agentic)
- Deterministic scoring from macro indicators; optional single LLM call for narrative prose.

---

## Current implementation mapping (Shiny)

- Agent 1: `shiny_app/restaurant_rag.py` + `shiny_app/google_places_client.py`
- Agent 2: `shiny_app/plan_logic.py` + `shiny_app/ollama_client.py` (invoked from `shiny_app/server.py`)
- Friendliness pipeline: `shiny_app/travel_friendliness/` (World Bank scoring + report) — wired from **`server.py` Generate** in parallel with the orchestrator future, not inside `agent_loop.py`
- Orchestrator: `shiny_app/agent_loop.py` called from **`shiny_app/server.py`** on **Generate** and Food Guide **Send**
- Food Guide UX: **`shiny_app/server.py`** (chat reactive state, quick replies, auxiliary-model follow-up prose via **OTHER / `resolved_model_other()`** — separate from Agent 2 plan JSON)

