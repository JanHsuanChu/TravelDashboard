# Agent 3 — plan critique

Thinking Process:

1.  **Analyze the Request:**
    *   **Role:** Skeptical Senior Engineer.
    *   **Task:** Review a development plan against a provided brief and UI mockup details.
    *   **Input:**
        *   Brief (JSON): Project goal, components (DB, API, UI, AI, Deployment), specific UI layout notes (Top half input, Bottom half output, 3 boxes).
        *   Agent 2 Plan (JSON): Development plan details (DB schema, API endpoints, UI tech stack & layout, AI model, Deployment), Cursor Prompt, Open Questions.
    *   **Output Format:** Markdown with specific sections (`## Overall`, `## Component ratings`, `## Top risks`, `## Suggested changes`, `--- VERDICT`, `REVISION_INSTRUCTIONS`).
    *   **Constraint:** Check that brief clarifications and UI mockup details are reflected. Be skeptical.

2.  **Analyze the Brief vs. Plan:**

    *   **Project Goal:** Travel Dashboard (food prefs, destination, timing -> dining, advisories, score).
        *   *Plan:* Matches goal.
    *   **Database:**
        *   *Brief:* Store user prefs, destination data, seasonal metadata, output content.
        *   *Plan:* PostgreSQL + Prisma. Schema includes `users`, `preferences`, `trips`, `trip_outputs`.
        *   *Critique:* Seems solid. `trip_outputs` storing AI generation results is good for caching/history.
    *   **API:**
        *   *Brief:* External APIs (weather, news, restaurant), Internal API (score calculation).
        *   *Plan:* Next.js API Routes. Endpoints: `/api/plan`, `/api/compare`, `/api/preferences`.
        *   *Critique:* Missing explicit mention of *external* API integration in the endpoints outline. The brief specifically mentions weather, news, restaurant data. The plan relies heavily on AI (`llama3.2`) to generate this. This is a risk (hallucination vs. real data).
    *   **App UI:**
        *   *Brief:* Top half input (Preference, Where, When, Compare), Bottom half output (3 side-by-side boxes: Dining, Advisories, Score).
        *   *Plan:* Next.js 14 + Tailwind + Shadcn. Layout: Top 50% input, Bottom 50% three equal-width output cards. Responsive (stack on mobile).
        *   *Critique:* Matches the brief well. "Compare where I'm going with" from brief is mentioned in `/api/compare` endpoint but not explicitly detailed in UI components (needs a second destination input?). The brief says "Compare where I'm going with" in the input section. The plan mentions `/api/compare` but the UI layout plan says "InputForm (Destination, Dates, Prefs)". It might miss the "Compare" input field visually.
    *   **AI Reporter:**
        *   *Brief:* Generate dining recommendations, calculate score.
        *   *Plan:* `llama3.2`. JSON schema enforcement.
        *   *Critique:* `llama3.2` is a good choice for structured output. However, relying solely on LLM for "weather forecasts" and "news headlines" (mentioned in Brief API notes) is risky. LLMs hallucinate real-time data. The brief says "Likely requires external APIs for weather forecasts, news headlines". The plan says "AI... generating JSON-structured recommendations". This is a discrepancy. The plan ignores the external data requirement in favor of pure generation.
    *   **Deployment:**
        *   *Brief:* Assumed web-based.
        *   *Plan:* Vercel + AI Provider.
        *   *Critique:* Standard and acceptable.

3.  **Identify Gaps & Risks (Skeptical View):**

    *   **Real-time Data vs. LLM Hallucination:** The brief explicitly notes "external APIs for weather forecasts, news headlines". The plan proposes using `llama3.2` to generate recommendations and scores. LLMs cannot provide accurate real-time weather or news without tool use (RAG/Function Calling). The plan doesn't mention function calling or integrating specific weather/news APIs (e.g., OpenWeather, NewsAPI). It just says "AI... generating... recommendations". This is a major functional risk.
    *   **UI "Compare" Feature:** The brief input section includes "Compare where I'm going with". The plan's UI component list (`InputForm (Destination, Dates, Prefs)`) omits the comparison destination input. The API has `/api/compare`, but the UI plan doesn't explicitly show where the second destination enters the UI.
    *   **Authentication:** The plan asks "Is user authentication required...?" but the DB schema includes `users (id, email...)`. This is a contradiction. You can't have a `users` table with emails without auth. Needs clarification before schema finalization.
    *   **Model Choice:** `llama3.2` is good, but if this is running via Ollama locally (as hinted in deployment notes "local Ollama is viable for development"), production needs a reliable provider. The plan says "AI Provider API ensures uptime". This is fine, but needs cost estimation.
    *   **Latency:** Generating three distinct blocks of content (Dining, Advisories, Score) via LLM might be slow. Streaming or optimistic UI needed (Plan mentions loading skeletons, which is good).

4.  **Drafting the Review:**

    *   **Overall:** Plan is technically sound regarding stack (Next.js, Prisma, Tailwind), but misses critical data integrity requirements regarding external data sources (weather/news) vs. LLM generation. UI misses the "Compare" input field detail.
    *   **Ratings:**
        *   Database: 4/5 (Schema good, but auth dependency unclear).
        *   API: 3/5 (Missing external API integration strategy for real-time data).
        *   App UI: 4/5 (Matches layout, misses "Compare" input detail).
        *   AI Reporter: 3/5 (Risk of hallucination on factual data like weather/news).
        *   Deployment: 5/5 (Standard Vercel stack).
    *   **Top Risks:** Hallucinated weather/news, Auth vs. Schema contradiction, Missing UI input for comparison.
    *   **Suggested Changes:** Integrate specific external APIs (Weather/News) via tool use or separate endpoints. Clarify Auth requirement before DB build. Add "Compare Destination" input to UI spec.

5.  **Refining the Verdict:**
    *   Can I approve? No, the data integrity issue (Weather/News via LLM) is a showstopper for a "Travel Advisory" tool. If the weather is wrong, the tool is useless.
    *   Verdict: REVISE.

6.  **Formatting:** Ensure Markdown headers and specific sections match the prompt requirements.

    *   `## Overall`
    *   `## Component ratings (Database, API, App UI, AI reporter, Deployment: X/5 each)`
    *   `## Top risks`
    *   `## Suggested changes`
    *   `--- VERDICT: APPROVE | REVISE`
    *   `REVISION_INSTRUCTIONS: <empty or instructions>`

7.  **Final Polish:** Check tone (Skeptical Senior Engineer). Ensure specific brief details (UI layout, external API notes) are referenced.

    *   *Self-Correction on UI:* The brief says "Compare where I'm going with". The plan has `/api/compare`. The UI plan says "InputForm (Destination, Dates, Prefs)". It implies single destination. The comparison logic needs a second destination input in the UI.
    *   *Self-Correction on API:* The brief says "Likely requires external APIs for weather...". The plan ignores this and relies on AI. This is the biggest skepticism point.

8.  **Constructing the Output.** (Mental check of the markdown structure).
    *   Make sure ratings are formatted exactly as requested: `Database, API, App UI, AI reporter, Deployment: X/5 each`.
    *   Make sure Verdict line is exact.

    *   *Wait, one more check on DB:* The plan includes `users (id, email...)`. The open questions ask "Is user authentication required...?". If the answer is "No, local storage", the DB schema is wrong. If "Yes", auth needs to be implemented. This is a dependency risk.

    *   *AI Model:* `llama3.2` is recent. Good choice. But again, data source is the issue.

    *   *UI Layout:* Brief: "Top half for user input... bottom half for Output (three side-by-side boxes)". Plan: "Top 50% for input forms... Bottom 50% for three equal-width output cards." -> This matches well.

    *   *Open Questions:* The plan includes open questions for the human. I should acknowledge them but note that the plan proceeds with assumptions (DB schema) that depend on the answers.
