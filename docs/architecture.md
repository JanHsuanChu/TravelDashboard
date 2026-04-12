The **first** diagram is the **target** pipeline (multi-agent orchestration, RAG, external tools). The **second** diagram is the **current** Shiny app data flow (Supabase, optional Google Places + embedding RAG, Ollama, injected architecture context).

#### Target pipeline (agentic orchestration, RAG, tool calling)

This is the roadmap: specialized agents, retrieval from reviews and location APIs, and a report path to the dashboard UI.

```mermaid
---
config:
  layout: dagre
---
flowchart TB
    Dashboard@{ label: "Travel Dashboard (input)<br>-Enter user preference<br>-Select location and info to display<br>-Q: 'Suggest restaurant based on my preference and public reviews" } -- API --> Database[("Database<br>-Supabase<br>-User preference")]
    Agent2["Agent 3 Analyst<br>Travel friendliness scoring"] --> Agent3["(Tentative) Agent 4 Report Writer"]
    Agent1["Agent 1<br> RAG, tool calling"] --> n1["Agent 2<br> Recommendation Engine"]
    Agent3 --> SummaryReport["Travel Dashboard (display)<br>-Recommendations<br>-FriendliessScore<br>-Selected location info"]
    n2["Restaurant review data"] -- API --> Agent1
    Database -- API --> Agent1
    n3["Location data<br> (World Bank, World Monitor, NYTimes)"] -- API --> Agent2
    n1 --> Agent3
    Dashboard -- API --> n3
    Dashboard -- API --> n2

    Dashboard@{ shape: rect}
    Agent2@{ shape: rect}
    n2@{ shape: rect}
    n3@{ shape: rect}
     n1:::Rose
    classDef Rose stroke-width:1px, stroke-dasharray:none, stroke:#FF5978, fill:#FFDFE5, color:#8E2236
    style Dashboard fill:#f4d7d7
    style Database fill:#e8e8e8
    style Agent2 fill:#f4d7d7
    style Agent3 fill:#f4d7d7
    style Agent1 fill:#f4d7d7
    style n1 stroke:#000000,color:#000000,fill:#f4d7d7
    style SummaryReport fill:#f4d7d7
    style n2 fill:#e8e8e8
    style n3 fill:#e8e8e8
```

#### Legend (target pipeline)

| Area | Role |
|------|------|
| **Travel Dashboard (input)** | Preferences, location selection, display choices, natural-language questions (e.g. restaurant suggestions). |
| **Supabase** | Stores user preferences; feeds Agent 1. |
| **Restaurant review data** | External/API input to Agent 1 (RAG + tools). |
| **Location data** | World Bank, World Monitor, NYTimes, etc. → Agent 3 Analyst (friendliness scoring). |
| **Agent 1 → Agent 2** | RAG/tool calling → recommendation engine. |
| **Agent 3 → Agent 4** | Analyst → (tentative) report writer. |
| **Travel Dashboard (display)** | Recommendations, friendliness score, selected location info. |

#### Current implementation (Shiny prototype — data flow)

What runs today on **Generate**:

1. **Travel friendliness** — World Bank indicators (deterministic; not from the LLM).
2. **Agent 1** (optional, when `GOOGLE_PLACES_API_KEY` is set) — **Places API (New)** Text Search for restaurants near the destination, then **embedding RAG** (`sentence-transformers` MiniLM) to rank candidates against a preference narrative, plus Place Details (address, reviews snippets, **price level**, coordinates). A second search query can incorporate **food-like** free text (e.g. “beef noodle”) to widen retrieval.
3. **Agent 2** — One **Ollama Cloud** chat completion: system message includes `docs/architecture.md` and JSON rules; user message includes `trip_and_food` and the **`agent1_restaurants`** list when present. The model returns JSON for **dishes** (price tier `$` / `$$` / `$$$`), **places** (must use retrieved venue names), **essential** blurbs, and illustrative friendliness fields (the UI ignores LLM friendliness in favor of World Bank scores).
4. **Maps Embed API** — embedded map for the selected recommended place (browser loads the iframe; same API key as Places).

```mermaid
flowchart LR
    subgraph ui [Shiny UI]
        Form[Trip + food inputs]
        Btn[Generate]
        Save[Save preferences]
    end
    subgraph server [Python server]
        Ctx[build_trip_context]
        Arch[load_architecture_markdown]
        A1[Agent 1: Places + embedding RAG]
        Prompt[System + user JSON + restaurants]
    end
    SB[(Supabase REST)]
    GPlaces[[Google Places API New]]
    Ollama[[Ollama Cloud /api/chat]]
    Form --> Ctx
    Btn --> A1
    Btn --> Prompt
    A1 --> GPlaces
    A1 --> Prompt
    Arch --> Prompt
    Ctx --> Prompt
    Prompt --> Ollama
    Ollama -->|JSON plan| Out[Dishes / Places+map / Essential / Friendliness]
    Save --> SB
    SB -->|Recent rows| Table[Preferences table]
```
