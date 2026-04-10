The **first** diagram is the **target** pipeline (multi-agent orchestration, RAG, external tools). The **second** diagram is the **current** Shiny prototype (single LLM call, Supabase, injected architecture context).

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

What runs today: one **Ollama Cloud** chat completion per **Generate** click; **no** separate agent processes, **no** vector RAG index. `docs/architecture.md` is loaded **in full** as static system context (prompt injection), not retrieved by similarity search.

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
        Prompt[System + user JSON prompt]
    end
    SB[(Supabase REST)]
    Ollama[[Ollama Cloud API /api/chat]]
    Form --> Ctx
    Btn --> Prompt
    Arch --> Prompt
    Ctx --> Prompt
    Prompt --> Ollama
    Ollama -->|JSON in reply| Out[Dining / Essential / Friendliness UI]
    Save --> SB
    SB -->|Recent rows| Table[Preferences table]
```
