# Travel Dashboard

Web app for planning trips, capturing food preferences, and generating structured travel recommendations in one UI. This README includes **app description**, **process diagrams**, and **technical documentation** for developers and stakeholders.

<p align="center">
  <img src="docs/readme_palette.svg" alt="Brand palette: #AC85E9, #FF6C9D, #FFA3C8, #FDE164, #01E1F2" width="520" />
</p>

| | Purple | Pink | Soft | Yellow | Cyan |
| :-- | :--: | :--: | :--: | :--: | :--: |
| **Hex** | `#AC85E9` | `#FF6C9D` | `#FFA3C8` | `#FDE164` | `#01E1F2` |

These colors match the Shiny UI (`shiny_app/www/custom.css`) and documentation visuals.

## Repository

Source of truth on GitHub: [https://github.com/JanHsuanChu/TravelDashboard](https://github.com/JanHsuanChu/TravelDashboard)

Clone:

```bash
git clone https://github.com/JanHsuanChu/TravelDashboard.git
cd TravelDashboard
```

If you already have this folder inside another workspace, push from here:

```bash
cd TravelDashboard
git remote -v   # should show origin -> JanHsuanChu/TravelDashboard
git push -u origin main
```

(Create an empty repo on GitHub first if it does not exist yet, then push.)

## App description and documentation

### Description

**What it does:** The Travel Dashboard is a **Shiny for Python** browser app where users enter a destination, optional compare locations, season or month, and detailed **food preferences** (preset tags plus short free text, including **dietary restrictions** that recommendations must honor). It also surfaces **essential destination information** for the country you pick—travel advisory, illustrative weather, and (when configured) Times headlines—alongside dining and trip context. Users can **save** preferences to the database, **generate** recommendations, and refine results through an in-app assistant:

- **Local Dishes to Try** — Card title for **`dining.dishes`**: **Agent 2** fills a flat list of suggested **mains**, **desserts**, and **beverages** (each row has **`category`**: `main`, `dessert`, or `beverage`, plus a short **note** and an illustrative **price tier** badge only: **`$`**, **`$$`**, or **`$$$`**). Picks are **destination-led** (country and city from the trip form) and **preference-aware** (tags and free text, including dietary); they are **independent** of the **Agent 1** restaurant list and of **`dining.places`**—dishes are not venue menus. The UI groups rows under **Mains**, **Desserts**, and **Beverages** ([`shiny_app/server.py`](shiny_app/server.py)); the card shell is [`shiny_app/components/dining_dishes_card.py`](shiny_app/components/dining_dishes_card.py). Prompt rules are in [`shiny_app/plan_logic.py`](shiny_app/plan_logic.py) (`SYSTEM_JSON_INSTRUCTION`, `AGENT2_DINING_GROUNDING`).
- **Dining — recommended places** — When **Google Places** is configured, the app runs **Agent 1**: real restaurants from **Text Search**, ranked with **embedding similarity** (sentence-transformers) to the user’s preferences, then **Agent 2** (Ollama) writes place notes using that list. Each place shows **retrieval match %** (from RAG scores) and **Google price level** as **`$` / `$$` / `$$$`** when the API returns it. A **Google Map** (Embed API) shows the selected venue.
- **Essential info** — **Travel advisory** uses live U.S. State Department table data plus a short **auxiliary-model** summary; **weather** comes from the **Agent 2** plan JSON (illustrative climatology for the trip season or month, not a live forecast); **destination news** uses the **New York Times Article Search API** with **`NYT_API_KEY`** (deterministic server-side queries; **no** LLM).
- **Travel friendliness** — **World Bank**–based scores and HTML report shell in [`shiny_app/travel_friendliness/`](shiny_app/travel_friendliness/); numeric scores are **not** from the LLM. Optional **auxiliary-model** prose fills report Purpose/Recommendations when enabled.
- **Food Guide (chat refinement assistant)** — A floating chat opens after Generate. Each Send can rerun the **orchestrator** (Agent 1 + Agent 2 + guardrails + QC budget). The typed line is wired into Agent 1 as **`chat_refinement`** (stronger embeddings + optional extra Places query). Messages that ask for **different / alternative recommendations** exclude the current **`dining.places` names** server-side before reranking. The finalized JSON and Places markers update **both** **Local Dishes to Try** / **`dining.dishes`** and **Dining — recommended places** and in-chat recommendation cards. Quick replies and short follow-up prose use the auxiliary (**OTHER**) model; they must align with grounded place names when cards are shown.
- **Guardrails (hard safety constraints)** — Server-side validation enforces destination and dietary constraints before recommendations are accepted. If a result violates guardrails, the orchestrator repairs/retries instead of showing non-compliant output.
- **QC Evidence (quality transparency panel)** — A user-visible panel summarizes QC Agent checks (initial/final scores, validation results, error rates, QC turns, latency). It is evidence from the same orchestrator run, not a separate recommendation flow.

Without a Places API key, dining places are generic LLM suggestions and the map stays empty; **Local Dishes to Try** and friendliness still work.

**APIs in use:**

| API / service | Purpose |
|----------------|---------|
| **Supabase** (PostgREST via `supabase-py`) | Persist `app_user` and `preference` rows; resolve returning users and load latest preferences by email. |
| **Ollama Cloud** (`POST …/api/chat`) | **Agent 2** model: plan JSON (dining + essential scaffold). **Auxiliary** model: U.S. advisory blurb + optional friendliness report prose. See [LLM model usage](#llm-model-usage). |
| **World Bank API** (`api.worldbank.org/v2`) | Travel friendliness scoring and detailed HTML report (see [`docs/travel_friendliness.md`](docs/travel_friendliness.md)). |
| **The New York Times** ([Article Search API](https://developer.nytimes.com/docs/articlesearch-product/1/overview)) | **Destination news** in Essential info: server-side HTTP to `svc/search/v2/articlesearch.json` with **`NYT_API_KEY`** ([`shiny_app/nyt_news_client.py`](shiny_app/nyt_news_client.py)). |
| **Google Places API (New)** | Server-side **Text Search** and **Place Details** for restaurant retrieval (`places.googleapis.com`). |
| **Google Maps Embed API** | In-browser embedded map for the selected recommended place (same API key as Places in this app). |
| **sentence-transformers** (local, PyTorch) | Embedding model **all-MiniLM-L6-v2** for Agent 1 ranking over place name, address, types, editorial summary (downloaded on first use). |

**Features and how they add value:**

| Capability | Status | Value |
|------------|--------|--------|
| **Preference storage** | Implemented | Food likes/dislikes/dietary tags and text; segment users via `food_tags` JSONB. |
| **Generate recommendations** | Implemented | **Agent 2** Ollama call for plan JSON (parallel with advisory table fetch); optional **auxiliary** calls for advisory summary + friendliness report prose; optional Places-backed list for Agent 2. |
| **Food Guide chat** | Implemented | Post-Generate Send reruns orchestrator; refinement steers Places/RAG (`chat_refinement`); alternative-intent excludes prior picks; Dining + chat share one `plan_state` / markers after success (see **`docs/architecture_v3.md`**). |
| **Guardrails (dietary + location)** | Implemented | Blocks non-compliant outputs and triggers orchestrator repair/retry so users only see destination- and dietary-safe recommendations. |
| **QC Evidence** | Implemented | Exposes QC Agent metrics (scores, validation, error rates, turns, latency) so users can inspect recommendation quality signals. |
| **Architecture context in the prompt** | Implemented | `docs/architecture.md` is injected into Agent 2’s system bundle (diagrams/process narrative lives in **`docs/architecture_v3.md`** → generated README sections). |
| **Agent 1 — Places + embedding RAG** | Implemented (optional) | Live restaurant candidates, semantic ranking, preference-aware search queries; details include `priceLevel` and review snippets for the LLM. |
| **Agent 2 — Dining copy** | Implemented | **`dining.dishes`**: categorized mains/desserts/beverages from destination + prefs (`$`/`$$`/`$$$`), independent of Agent 1. **`dining.places`**: copy aligned to Agent 1 names when Places is configured. |
| **Full multi-agent orchestration** | Partial / evolving | Two-stage dining pipeline today; broader tool calling and review corpora remain roadmap (see target diagram). |

**Stakeholders:** **Travelers** get a single place for preferences and AI-assisted suggestions; **developers** get a small, inspectable stack (Shiny + Supabase + **Ollama Cloud** with **separate default models** for plan vs auxiliary calls) that can grow toward the multi-agent design in `docs/architecture.md`.

**Preference UX (identity, returning users, Save vs Generate):** see [`docs/ui_flow_preferences.md`](docs/ui_flow_preferences.md).

### Process diagram and architecture reference

The content below is **generated** from [`docs/architecture_v3.md`](docs/architecture_v3.md). It includes the **target** pipeline (agents, RAG, tools) and implementation mapping. Edit that file, then run `python3 scripts/build_readme.py` to refresh `README.md`. CI also regenerates `README.md` when `docs/architecture_v3.md` or `README.template.md` changes.

{{ARCHITECTURE_BODY}}

### Technical documentation

#### System architecture (roles and workflow)

| Piece | Responsibility |
|-------|------------------|
| **UI** ([`shiny_app/ui.py`](shiny_app/ui.py), [`shiny_app/components/`](shiny_app/components/)) | Plan form, outputs grid (**Local Dishes to Try**, essential, friendliness), full-width dining places + map. |
| **Server** ([`shiny_app/server.py`](shiny_app/server.py)) | **Save** → Supabase user + preference; debounced-email preload; **Generate** and chat refinement → orchestrator loop + guardrails + status/QC widgets, plus friendliness thread, optional auto-save, map markers and embed URL. |
| **`validators`** ([`shiny_app/validators.py`](shiny_app/validators.py)) | Food text, when-mode (season/month), and email shape checks for Save / Generate. |
| **`plan_logic`** ([`shiny_app/plan_logic.py`](shiny_app/plan_logic.py)) | `build_trip_context`, user/system JSON instructions (dietary rules, **`dining.dishes`** categories + independence from Agent 1, dish `$`/`$$`/`$$$`, **`dining.places`** alignment to Agent 1). |
| **`agent_loop`** ([`shiny_app/agent_loop.py`](shiny_app/agent_loop.py)) | Bounded orchestration: Agent 1 retrieval retries, Agent 2 JSON repair loop, hard guardrail validation, and QC Agent evidence loop. |
| **`restaurant_rag`** ([`shiny_app/restaurant_rag.py`](shiny_app/restaurant_rag.py)) | Trip preference narrative → Places Text Search (**baseline + food-hint**; Food Guide adds **refinement-phrased query** when `chat_refinement` set), embedding cosine rank + optional keyword boost, Place Details, `price_tier` + `rag_match_score` on candidates. |
| **`google_places_client`** ([`shiny_app/google_places_client.py`](shiny_app/google_places_client.py)) | Places API (New): `searchText`, GET Place Details, field masks. |
| **`context`** ([`shiny_app/context.py`](shiny_app/context.py)) | Reads repo-root [`docs/architecture.md`](docs/architecture.md) for the plan LLM when the server uses full architecture context (bypassed when `TD_LIGHT_ARCH_CONTEXT` supplies a short stub). |
| **`supabase_client`** ([`shiny_app/supabase_client.py`](shiny_app/supabase_client.py)) | Supabase client, users, preferences. |
| **`ollama_client`** ([`shiny_app/ollama_client.py`](shiny_app/ollama_client.py)) | Ollama Cloud chat + JSON extraction. |
| **`travel_friendliness`** ([`shiny_app/travel_friendliness/`](shiny_app/travel_friendliness/)) | World Bank fetch, scoring, HTML report. |
| **`nyt_news_client`** ([`shiny_app/nyt_news_client.py`](shiny_app/nyt_news_client.py)) | Article Search HTTP for **Destination news** (`NYT_API_KEY`). |

**Workflow (high level):** On **Generate**, **travel friendliness** is submitted on a **background thread** (unless `TD_DISABLE_TRAVEL_FRIENDLINESS`) while the server may auto-save prefs, run **Agent 1** (if `GOOGLE_PLACES_API_KEY`), and run the **orchestrator loop** (`agent_loop.py`) for Agent 2 JSON generation + guardrail repair + QC Agent turns. The handler waits for both orchestrator output and the friendliness future before updating the UI. If the Places key is set, Agent 2 receives **`agent1_restaurants`** for **`dining.places`** only; **`dining.dishes`** stays destination- and preference-grounded per `plan_logic.py`. The UI merges place rows with coordinates, shows **% match · $tier** when available, and embeds the map. System context is **full `docs/architecture.md`** or a **short stub** when `TD_LIGHT_ARCH_CONTEXT` is set.

#### RAG and tool implementation

| Topic | Implementation today | Roadmap (aligned with target diagram) |
|-------|----------------------|----------------------------------------|
| **RAG (restaurants)** | **Embedding retrieval** over **Places Text Search** results (name, address, types, editorial summary, rating line); Food Guide **`chat_refinement`** prefixes the semantic query and can add another search variant. Review text is **not** embedded for ranking; snippets are passed to the LLM after ranking. Optional **keyword overlap** boost from “food I like” **and refinement** tokens. | Richer signals (menus if licensed), multi-query fusion, optional re-rank with reviews. |
| **Architecture “RAG”** | Full [`docs/architecture.md`](docs/architecture.md) via [`shiny_app/context.py`](shiny_app/context.py), **or** a short in-code stub when `TD_LIGHT_ARCH_CONTEXT` is set ([`shiny_app/server.py`](shiny_app/server.py)). | Same. |
| **Tool calling** | **No** LLM-invoked tools; Places, World Bank, and **NYT Article Search** (with `NYT_API_KEY`) are **server-orchestrated** HTTP calls. | Model-driven tool use if product needs it. |

If you add tools later, document **name**, **purpose**, **parameters**, and **return shape** here and in code docstrings.

#### Local dishes to try — how this is generated

**Agent 2** emits `dining.dishes` in the same JSON response as **`dining.places`** and **`essential`**. The orchestrator’s user payload includes **`trip_and_food`** (destination, when, food prefs) and a trimmed **`agent1_restaurants`** list; prompts in [`shiny_app/plan_logic.py`](shiny_app/plan_logic.py) state explicitly that **dishes must not** be derived from or tied to that restaurant list (places still must copy **Agent 1** names exactly). Each dish includes **`category`** (`main` \| `dessert` \| `beverage`); [`shiny_app/server.py`](shiny_app/server.py) buckets rows for display. **Guardrails** validate **`dining.places`** against candidates and scan dish **title**/**note** for banned tokens when dietary tags apply—same loop as the rest of the plan, with model repair messages on failure.

#### Essential info

The **Essential info** card (see [`shiny_app/components/essential_info_card.py`](shiny_app/components/essential_info_card.py)) scrolls **travel advisory**, **weather**, and **destination news** together.

- **Travel advisory** — On **Generate**, the server pulls the U.S. State Department’s **public** travel advisory listing (the official page embeds the table; a legacy JSON URL may redirect to HTML, which the client parses). Results are **cached** for about **24 hours** by default (`TD_US_ADVISORY_CACHE_SECONDS`); if a refresh fails, the app can still use the **last successful snapshot** so the run does not hard-fail on transient network or HTML changes. The **destination country** you pick is matched to a row using **ISO2** plus name **aliases** from [`shiny_app/www/data/countries_slim.json`](shiny_app/www/data/countries_slim.json) (with fuzzy name fallback when needed). The matched advisory level and official text feed **Essential → Travel advisory** as markdown. A small **auxiliary** Ollama call (same **OTHER** tier as friendliness prose; see [LLM model usage](#llm-model-usage)) adds a **brief plain-language summary** (grounded in the matched row, not a substitute for the official advisory). Wiring lives in [`shiny_app/server.py`](shiny_app/server.py); fetch, cache, parse, and match logic are in [`shiny_app/us_travel_advisory.py`](shiny_app/us_travel_advisory.py).

- **Weather** — The **Weather** subsection shows **`essential.weather`** from the **Agent 2** plan JSON: **one or two short sentences** of **illustrative** climatology for the destination (packing / planning guidance), explicitly tied to the trip **season** or **calendar month** from the trip form. It is **not** wired to a live weather API; treat it as narrative context unless you add a separate forecast source. The orchestrator prompt in [`shiny_app/plan_logic.py`](shiny_app/plan_logic.py) constrains how Agent 2 writes this field.

- **Destination news** — Sourced from the **New York Times Article Search API** using **deterministic** queries in [`shiny_app/nyt_news_client.py`](shiny_app/nyt_news_client.py): **no LLM** and **no** model-in-the-loop for ranking or copy. After **Generate**, a background thread calls the API with **`NYT_API_KEY`**. The destination label is the **canonical English country name** resolved from **ISO2** via the same [`countries_slim.json`](shiny_app/www/data/countries_slim.json) bridge as travel friendliness (`friendliness_country_query` in [`shiny_app/iso2_bridge.py`](shiny_app/iso2_bridge.py)), so the text search stays aligned with the country pick. **Query strategy (recall-first):** for each slot the client tries full-text **`q`** on the country name (plus a small alias list for special cases such as UK / Korea) while stepping **`fq`** from **none** → broad **section_name** filters → a tighter “news desk + World” scope; only if those miss does it fall back to **`glocations`** tokens (including quoted continent-style facets when ISO2 is known) **AND** the tighter news filter. **Slot 1** is one **general** article with **`begin_date`** ≈ last **90 days** and **`sort=relevance`**. **Slot 2** is one **travel-leaning** article (`q` includes “{country} travel” / tourism variants), **`begin_date`** ≈ last **two years**, **`sort=relevance`**, with **URL deduplication** against the first hit so links are not repeated. Failures (missing key, HTTP errors, rate limits, empty hits) are **silent** in the UI (no headlines). A short **`sleep`** between NYT calls paces burst traffic.

#### Travel friendliness

**Travel friendliness** runs on **Generate** (unless disabled with `TD_DISABLE_TRAVEL_FRIENDLINESS`): **World Bank** indicator data is fetched and scored **deterministically**; the card summary line is **not** from the main plan LLM. An optional **auxiliary** Ollama pass can add longer **Purpose** / **Recommendations** prose to the downloadable HTML report. For indicator bounds, normalization, when it runs, and file layout, see **[`docs/travel_friendliness.md`](docs/travel_friendliness.md)**.

#### Technical details

**Environment variables** (set in [`shiny_app/.env`](shiny_app/.env); copy from [`shiny_app/.env.example`](shiny_app/.env.example)):

| Variable | Required | Purpose |
|----------|----------|---------|
| `SUPABASE_URL` | Yes (save / load) | Supabase project URL. |
| `SUPABASE_KEY` | Yes (save / load) | JWT-style API key (`eyJ…`) for `app_user` / `preference` (see `.env.example` for legacy key note). |
| `OLLAMA_API_KEY` | Yes (**Generate**) | Bearer token for Ollama Cloud. |
| `OLLAMA_HOST` | No | API host only (default `https://ollama.com`); the client posts to `{host}/api/chat`. |
| `OLLAMA_MODEL_AGENT2` | No | Model for **Agent 2** (main Generate JSON). Default `nemotron-3-nano:30b-cloud`. |
| `OLLAMA_MODEL_OTHER` | No | Auxiliary calls (advisory blurb, friendliness report prose). Default `gpt-oss:20b-cloud`. Alias: `OLLAMA_MODEL_AUXILIARY`. |
| `OLLAMA_MODEL_AGENTS` | No | Optional: one value for both agent tiers when `OLLAMA_MODEL_AGENT2` unset. |
| `OLLAMA_MODEL_AGENT1` | No | Reserved (Agent 1 is Places+embeddings only). |
| `OLLAMA_MODEL` | No | Fallback for **OTHER** tier only (not Agent 2). |
| `OLLAMA_NUM_PREDICT` | No | Optional cap on completion tokens for the **main** plan call (`ollama_client`). |
| `TD_DISABLE_TRAVEL_FRIENDLINESS` | No | When truthy, skips the World Bank friendliness thread during **Generate** (UI shows a disabled message; dining still runs). |
| `TD_FRIENDLINESS_SKIP_REPORT_LLM` | No | When truthy, keeps World Bank scores and HTML report shell but skips the **extra** Ollama call for report Purpose/Recommendations prose. |
| `TD_LIGHT_ARCH_CONTEXT` | No | When truthy, uses a short system stub instead of loading full `docs/architecture.md` for the plan model. |
| `NYT_API_KEY` | Yes | **Destination news** (NYT Article Search) in Essential info — the headline links are empty without this key. Advisory and weather do not use it. |
| `GOOGLE_PLACES_API_KEY` | No† | Agent 1 restaurant retrieval, Google **price level** on places, **RAG % match** from retrieval scores, and **Maps Embed** iframe. |

†**Why “No”?** The Shiny app **starts** and **Generate** still works without this key: you get LLM-written **`dining.dishes`** (**Local Dishes to Try**), **essential** text, and **travel friendliness** (World Bank). You do **not** get real venue lookup, the **embedded map**, or server-backed **% match · $** on recommended places—those need `GOOGLE_PLACES_API_KEY`. Treat it as **required** if you want the full dining + map experience described in this README.

#### LLM model usage

Ollama is invoked from a **shared host** (`OLLAMA_HOST`, default `https://ollama.com`) with **model names chosen by tier** in [`shiny_app/ollama_client.py`](shiny_app/ollama_client.py).

| Tier | Default model | Where it runs | What it does |
|------|----------------|-----------------|---------------|
| **Agent 2** | `nemotron-3-nano:30b-cloud` | [`agent_loop.py`](shiny_app/agent_loop.py) orchestrated from [`server.py`](shiny_app/server.py) on **Generate** and chat refinement | Multiple `ollama_chat` calls may occur inside the bounded orchestrator loop (draft + repair/self-check turns) to produce compliant **plan JSON** (`dining`, `essential`). `friendliness` in that JSON is discarded; scores come from World Bank. |
| **QC Agent** | `gpt-oss:20b-cloud` (OTHER tier default) | [`agent_loop.py`](shiny_app/agent_loop.py) inside the orchestrator QC loop | Runs QC scoring/details over Agent 2 outputs. Deterministic checks remain hard evidence; LLM output is used as bounded quality assistance and explanation. |
| **Auxiliary (“OTHER”)** | `gpt-oss:20b-cloud` | [`us_travel_advisory.py`](shiny_app/us_travel_advisory.py), [`travel_friendliness/pipeline.py`](shiny_app/travel_friendliness/pipeline.py), [`server.py`](shiny_app/server.py) (**Food Guide** follow-up + quick-reply chips) | (1) **U.S. travel advisory** — after the State Dept row is matched, a short plain-text summary (separate `ollama_chat` with a small `num_predict` cap). (2) **Friendliness HTML report** — optional **Purpose** / **Recommendations** paragraphs; skipped when `TD_FRIENDLINESS_SKIP_REPORT_LLM` is set or when `OLLAMA_API_KEY` is missing. (3) **Food Guide** — bounded short assistant paragraph and chip suggestions (not Agent 2’s plan JSON). |

**Agent 1** (restaurant retrieval) uses **Google Places** + **sentence-transformers** embeddings only — **no** Ollama. `OLLAMA_MODEL_AGENT1` and `resolved_model_agent1()` are reserved for a future Agent 1 LLM step.

**How env vars map to tiers**

- **Agent 2:** `OLLAMA_MODEL_AGENT2` → else `OLLAMA_MODEL_AGENTS` → else default `nemotron-3-nano:30b-cloud`. **`OLLAMA_MODEL` does not apply** to Agent 2 (so plan and auxiliary defaults stay independent).
- **QC Agent + Auxiliary:** `OLLAMA_MODEL_OTHER` or `OLLAMA_MODEL_AUXILIARY` → else `OLLAMA_MODEL` → else default `gpt-oss:20b-cloud`.
- **Agent 1 (reserved):** `OLLAMA_MODEL_AGENT1` → else same chain as Agent 2 when a call site uses `resolved_model_agent1()`.

**`OLLAMA_NUM_PREDICT`:** When set, it is applied to `ollama_chat` requests that do not pass an explicit `num_predict` (the main plan call; advisory summary uses its own cap in code).

**Endpoints (app as client):**

- Supabase: project REST URL (used by `supabase-py`).
- Ollama Cloud: `{OLLAMA_HOST or https://ollama.com}/api/chat` — [`shiny_app/ollama_client.py`](shiny_app/ollama_client.py).
- Google: `https://places.googleapis.com/v1/places:searchText`, Place Details, and `https://www.google.com/maps/embed/v1/place` — [`shiny_app/google_places_client.py`](shiny_app/google_places_client.py).
- New York Times: `https://api.nytimes.com/svc/search/v2/articlesearch.json` — [`shiny_app/nyt_news_client.py`](shiny_app/nyt_news_client.py) (`NYT_API_KEY`).

#### Google Cloud: Places and Maps Embed setup

Use **one Google Cloud project** and **one API key** for both server-side Places calls and the browser-loaded Embed map (as configured in this repo).

1. **Create or select a project** in [Google Cloud Console](https://console.cloud.google.com/) and ensure **billing** is enabled for that project.

2. **Enable APIs** (APIs & Services → Library):
   - **Places API (New)** — required for `places.googleapis.com` Text Search and Place Details. Do not rely on only the legacy “Places API” name if your console lists them separately; the app targets the **New** Places endpoints.
   - **Maps Embed API** — required for the dining map iframe (`maps/embed/v1/place`).

3. **Create an API key** (APIs & Services → Credentials → Create credentials → API key).

4. **Restrict the key (recommended)**  
   - Under **API restrictions**, choose “Restrict key” and select at least **Places API (New)** and **Maps Embed API**.  
   - Under **Application restrictions**:  
     - **Server-side Places** requests come from your **Python process** (Shiny server), not from the user’s browser tab. **HTTP referrer (website) restrictions** often **break** those calls (`API_KEY_SERVICE_BLOCKED` or 403). For local development, **Application restrictions: None** is the simplest path while keeping **API restrictions** on the key.  
     - For production, common patterns are: **no application restriction** + tight API restrictions; **separate keys** for server (IP restriction) vs browser (HTTP referrers for your deployed Shiny origin); or a small backend proxy so only server-side code holds the Places key.  
   - If you use **HTTP referrers** for the same key as the Embed iframe, add origins such as `http://127.0.0.1:8000/*` and `http://localhost:8000/*` for local Shiny; the server may still need a referrer-safe or separate key for Places (see [`shiny_app/google_places_client.py`](shiny_app/google_places_client.py) error hints).

5. **Set the key in the app:** copy [`shiny_app/.env.example`](shiny_app/.env.example) to `shiny_app/.env` and set `GOOGLE_PLACES_API_KEY=<your key>`.

6. **First run with RAG:** `pip install -r requirements.txt` pulls `sentence-transformers` (and typically PyTorch). The embedding model downloads on first **Generate**; allow network access once.

**Packages:** see [`shiny_app/requirements.txt`](shiny_app/requirements.txt) — `shiny`, `supabase`, `requests`, `python-dotenv`, `pandas`, `markdown`, `sentence-transformers`, `numpy`.

**Repository layout:**

- **Shiny app:** [`shiny_app/`](shiny_app/) — `app.py` (entrypoint; background warm of `all-MiniLM-L6-v2`), `ui.py`, `server.py`, `plan_logic.py`, `restaurant_rag.py`, `google_places_client.py`, `nyt_news_client.py`, `context.py`, `validators.py`, `supabase_client.py`, `ollama_client.py`, `components/`, `www/custom.css`
- **SQL:** [`supabase/migrations/`](supabase/migrations/)
- **Docs:** [`docs/architecture_v3.md`](docs/architecture_v3.md) (canonical **implemented** orchestrator narrative + diagram source for README); [`docs/architecture.md`](docs/architecture.md) (Agent 2 system-context text); [`docs/agentic_loop_readme.md`](docs/agentic_loop_readme.md) (Generate vs Food Guide chat, Supabase boundaries, interactive follow-ups)

**Deployment:** The documented path is **local** (`shiny run app.py`). You can host on **Posit Connect**, **Shiny Server**, or a **container**; configure the same environment variables on the host. There is **no app-level password** in this prototype—use platform auth, VPN, or network rules if you expose it beyond localhost.

#### Usage instructions

1. **Environment:** Python 3.10+ recommended. From the repo root:

```bash
cd shiny_app
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # set SUPABASE_*, OLLAMA_*, NYT_API_KEY; optional GOOGLE_PLACES_API_KEY
```

2. **Run:**

```bash
shiny run app.py --reload
```

Or from repo root (after venv is ready): `./run_shiny.sh`

3. **Open** the URL Shiny prints (commonly `http://127.0.0.1:8000`).

4. **Use the UI:** Enter **destination** (country required), optional **compare** cities, **when** (season or month), **food** tags and text (including **dietary** checkboxes and restrictions). **Save food preferences** requires first name + email. **Generate recommendations** refreshes **Local Dishes to Try** (**`dining.dishes`**), **recommended places** (+ map when Google is configured), **essential** blurbs, and **travel friendliness**. A recognized **email** (debounced or on blur) preloads saved preferences. After a successful **Generate** the plan card collapses to keep recommendations and the **Food Guide** chat in focus; click **New Trip** at the top to start a fresh trip.

**Password:** None for the default local app. If you deploy behind a platform that adds authentication, follow that platform’s login flow.

---

## Development

To regenerate the root `README.md` after editing [`README.template.md`](README.template.md) or [`docs/architecture_v3.md`](docs/architecture_v3.md):

```bash
python3 scripts/build_readme.py
```

## Stack

- [Shiny for Python](https://shiny.posit.co/py/) — dashboard in [`shiny_app/`](shiny_app/)

## Supabase

**Example project URL (public):** `https://stnfxxjktzznvlfhczcz.supabase.co`  
**Project reference (for MCP):** `stnfxxjktzznvlfhczcz`

### Schema

#### `app_user`

| Column | Type | Constraints |
|--------|------|-------------|
| `user_id` | `UUID` | Primary key, default `gen_random_uuid()` |
| `first_name` | `TEXT` | not null |
| `email` | `TEXT` | not null, unique |
| `email_hash` | `TEXT` | not null, unique (SHA-256 hex of normalized email; see migration 004) |
| `created_at` | `TIMESTAMPTZ` | not null, default `now()` |

#### `preference`

| Column | Type | Constraints |
|--------|------|-------------|
| `preference_id` | `BIGINT` | Primary key, generated identity |
| `user_id` | `UUID` | not null, FK → `app_user(user_id)` (cascade on delete) |
| `created_at` | `TIMESTAMPTZ` | not null, default `now()` |
| `food_like_text` | `TEXT` | nullable (UI max 50 words) |
| `food_dislike_text` | `TEXT` | nullable (UI max 50 words) |
| `dietary_restrictions` | `TEXT` | nullable (UI max 50 words) |
| `food_tags` | `JSONB` | not null, default `{}` — preset checkbox slugs: `like` / `dislike` / `dietary` arrays |

Index: `idx_preference_user_created_at` on `(user_id, created_at DESC)`.

#### UI ↔ database mapping (Save · qualifying Generate)

Each **Save**, and **Generate** when **first name** and a **valid email** are present, appends one `preference` row (append-only history) and ensures an `app_user` row. Trip fields (destination, compare, when) and **Generate** plan JSON are **not** persisted to these tables today.

| Supabase column / table | Shiny input(s) | Notes |
|-------------------------|----------------|--------|
| `app_user.first_name` | **First name** | Required on Save. |
| `app_user.email` | **Email** | Required on Save; used to find or create `app_user`. |
| `preference.food_like_text` | **Food I like** — detail textarea | Validated to max word count in UI. |
| `preference.food_dislike_text` | **Food I dislike** — detail textarea | Same. |
| `preference.dietary_restrictions` | **Dietary restrictions** — detail textarea | Same. |
| `preference.food_tags` | **Food I like / dislike / Dietary** checkbox groups | Stored as JSON: `{ "like": [...], "dislike": [...], "dietary": [...] }` (slug values from [`shiny_app/tags.py`](shiny_app/tags.py)). |

### Apply migrations

Run in order:

1. [`supabase/migrations/001_app_user_preference.sql`](supabase/migrations/001_app_user_preference.sql)
2. [`supabase/migrations/002_preference_food_text.sql`](supabase/migrations/002_preference_food_text.sql)
3. [`supabase/migrations/003_drop_dining_preference.sql`](supabase/migrations/003_drop_dining_preference.sql) — drops legacy unused `dining_preference` if present
4. [`supabase/migrations/004_app_user_email_hash.sql`](supabase/migrations/004_app_user_email_hash.sql) — adds `app_user.email_hash` (SHA-256 of normalized email) for stable identity

- **Option A: Supabase Dashboard (SQL Editor)**: paste each file and **Run**.
- **Option B: Supabase MCP**: `apply_migration` / `execute_sql` with the same SQL.

## Layout

- **Shiny (Python):** [`shiny_app/`](shiny_app/) — `app.py`, `ui.py`, `server.py`, [`components/`](shiny_app/components/), [`www/custom.css`](shiny_app/www/custom.css)
- **SQL:** [`supabase/migrations/`](supabase/migrations/)
