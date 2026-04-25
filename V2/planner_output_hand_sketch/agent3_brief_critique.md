# Agent 3 — brief critique

Thinking Process:

1.  **Analyze the Request:**
    *   **Role:** Senior Full-Stack Engineer.
    *   **Task:** Review a combined spec + UI brief (provided in JSON format).
    *   **Output Format:** Markdown with specific sections (`## Brief critique`, `## Clarifying questions — spec & functionality`, `## Clarifying questions — UI & layout`, `--- VERDICT: GOOD | NEEDS_WORK`).
    *   **Constraint:** Max 8 total clarifying questions.
    *   **Input:** A JSON object describing a "Travel Dashboard" project.

2.  **Analyze the Input Brief:**
    *   **Project Name:** Travel Dashboard.
    *   **Goal:** Plan trips via food prefs, destination, timing -> Output dining, advisories, friendliness score.
    *   **Components:**
        *   *Database:* Stores prefs, destination, seasonal metadata, output content.
        *   *API:* External (weather, news, restaurant), Internal (score calculation).
        *   *App UI:* Input (top half), Output (bottom half, 3 boxes). Specific components listed.
        *   *AI Reporter:* Generates recommendations/scores.
        *   *Deployment:* Assumed web-based.
    *   **Status:** `open_questions` arrays are empty in the JSON, `unresolved_sketch_elements` is empty.

3.  **Evaluate the Brief (Critique):**
    *   *Strengths:* Clear high-level goal, defined input/output structure, identified need for external APIs.
    *   *Weaknesses:*
        *   **Data Persistence:** Why store output content (dining places, advisories) in the DB? Is this static or dynamic? If dynamic (weather/news), storing it seems wrong or needs caching strategy.
        *   **API Specifics:** "News headlines" for travel advisories? Usually, travel advisories come from government sources (State Dept, etc.), not general news. Weather is seasonal, not necessarily forecast.
        *   **AI Role:** Vague. "May be used". Needs definition on prompt engineering, cost control, latency.
        *   **Comparison Logic:** "Compare where I'm going with" implies multiple destinations, but the input section says "destination (country, city)". How does comparison work visually and logically?
        *   **UI Layout:** "Bottom half for Output (three side-by-side boxes)" might break on mobile. No responsive strategy mentioned.
        *   **Authentication:** No mention of user accounts. How are preferences saved if there's no user profile?
        *   **Scoring Logic:** "Travel friendliness score" is subjective. What factors? Safety? Cost? Food quality? Needs definition.

4.  **Draft Clarifying Questions (Max 8 total):**
    *   *Spec & Functionality:*
        1.  How is the "Travel Friendliness Score" calculated? What specific weights (safety, cost, food variety) are involved?
        2.  Regarding the database storing "output content": Is this intended as a cache for API responses, or are we generating static content? How do we handle data freshness (e.g., weather/news)?
        3.  The goal mentions comparing destinations, but the UI input describes a single "country/city". How many destinations can a user compare simultaneously?
        4.  Is user authentication required to save preferences, or is this a stateless session-based tool?
    *   *UI & Layout:*
        5.  The brief specifies a "top half/bottom half" layout. What is the responsive strategy for mobile devices where side-by-side output boxes won't fit?
        6.  For the "Compare where I'm going with" input, how should the UI handle adding/removing comparison destinations dynamically?
        7.  Are there specific branding guidelines or a design system we should adhere to for the dashboard components?
        8.  What is the expected latency tolerance for the AI generation? Should we implement loading skeletons/streaming for the output panels?

    *Refining Questions to be high-impact:*
    1.  (Spec) Score logic is critical.
    2.  (Spec) DB storage of dynamic data is suspicious.
    3.  (Spec) Comparison logic vs Input design mismatch.
    4.  (Spec) Auth/Session state.
    5.  (UI) Responsive behavior for the 3-box layout.
    6.  (UI) Interaction for adding comparison destinations.
    7.  (UI) Loading states for AI/API calls.
    8.  (Spec) API sources for advisories (News vs Govt).

    *Let's select the top 8.*
    1.  Score calculation factors.
    2.  DB strategy for dynamic data (weather/news).
    3.  Comparison logic (single vs multi destination).
    4.  Auth/Session for preferences.
    5.  Responsive layout for 3-box output.
    6.  Advisory data source specificity.
    7.  AI latency/loading state handling.
    8.  Validation for food preferences (free text vs structured tags).

    *Wait, I need to split them into "Spec & Functionality" and "UI & Layout".*
    *Spec:* 1, 2, 3, 4, 6. (5 questions)
    *UI:* 5, 7, 8. (3 questions)
    *Total:* 8. Perfect.

5.  **Draft Critique:**
    *   Highlight the ambiguity in data persistence (dynamic vs static).
    *   Point out the conflict between "comparison" goal and single destination input.
    *   Note the lack of error handling/loading states in UI.
    *   Mention the vagueness of the AI implementation.

6.  **Final Review against Constraints:**
    *   Markdown format? Yes.
    *   Specific headers? Yes.
    *   Max 8 questions? Yes.
    *   Verdict? NEEDS_WORK (due to significant logical gaps in data flow and comparison logic).

7.  **Construct Output:** (Self-Correction during drafting)
    *   Ensure the tone is professional (Senior Engineer).
    *   Make sure the critique explains *why* it's an issue.
    *   Ensure questions are actionable.

    *Refining Question 2 (DB):* Instead of just "why", ask about the caching strategy.
    *Refining Question 3 (Comparison):* Ask about the max number of destinations.
    *Refining Question 5 (UI):* Ask about mobile stacking order.

    *Verdict:* Definitely NEEDS_WORK. The spec has logical contradictions (single input vs comparison goal) and technical risks (storing dynamic API data).

    *Let's finalize the questions
