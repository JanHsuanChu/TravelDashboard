# Travel Dashboard — architecture (reference)

This diagram captures the intended data flow and agent pipeline. Use it when planning features, APIs, and UI surfaces.

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

## Legend (quick read)

| Area | Role |
|------|------|
| **Travel Dashboard (input)** | Preferences, location selection, display choices, natural-language questions (e.g. restaurant suggestions). |
| **Supabase** | Stores user preferences; feeds Agent 1. |
| **Restaurant review data** | External/API input to Agent 1 (RAG + tools). |
| **Location data** | World Bank, World Monitor, NYTimes, etc. → Agent 3 Analyst (friendliness scoring). |
| **Agent 1 → Agent 2** | RAG/tool calling → recommendation engine. |
| **Agent 3 → Agent 4** | Analyst → (tentative) report writer. |
| **Travel Dashboard (display)** | Recommendations, friendliness score, selected location info. |
