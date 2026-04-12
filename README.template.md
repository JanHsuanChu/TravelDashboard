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

**What it does:** The Travel Dashboard is a **Shiny for Python** browser app where users enter a destination, optional compare locations, season or month, and detailed **food preferences** (preset tags plus short free text, including **dietary restrictions** that the model must honor). Users can **save** preferences to the database and **generate** a structured plan:

- **Dining — dishes** — LLM-suggested dishes with a **price tier** badge only: **`$`**, **`$$`**, or **`$$$`** (budget / mid-range / upscale–style; inferred, not live menu prices).
- **Dining — recommended places** — When **Google Places** is configured, the app runs **Agent 1**: real restaurants from **Text Search**, ranked with **embedding similarity** (sentence-transformers) to the user’s preferences, then **Agent 2** (Ollama) writes place notes using that list. Each place shows **retrieval match %** (from RAG scores) and **Google price level** as **`$` / `$$` / `$$$`** when the API returns it. A **Google Map** (Embed API) shows the selected venue.
- **Essential info** — Advisory / weather / news–style paragraphs from the LLM (illustrative unless you add live feeds).
- **Travel friendliness** — **World Bank**–based scores and HTML report (**not** from the LLM; deterministic pipeline in [`shiny_app/travel_friendliness/`](shiny_app/travel_friendliness/)).

Without a Places API key, dining places are generic LLM suggestions and the map stays empty; dishes and friendliness still work.

**APIs in use:**

| API / service | Purpose |
|----------------|---------|
| **Supabase** (PostgREST via `supabase-py`) | Persist `app_user` and `preference` rows; resolve returning users and load latest preferences by email. |
| **Ollama Cloud** (`POST …/api/chat`) | Chat completion that returns JSON for dining (dishes + places), essential text, and illustrative friendliness fields (UI uses World Bank for friendliness scores). |
| **World Bank API** (`api.worldbank.org/v2`) | Travel friendliness scoring and detailed HTML report (see [`docs/travel_friendliness.md`](docs/travel_friendliness.md)). |
| **Google Places API (New)** | Server-side **Text Search** and **Place Details** for restaurant retrieval (`places.googleapis.com`). |
| **Google Maps Embed API** | In-browser embedded map for the selected recommended place (same API key as Places in this app). |
| **sentence-transformers** (local, PyTorch) | Embedding model **all-MiniLM-L6-v2** for Agent 1 ranking over place name, address, types, editorial summary (downloaded on first use). |

**Features and how they add value:**

| Capability | Status | Value |
|------------|--------|--------|
| **Preference storage** | Implemented | Food likes/dislikes/dietary tags and text; segment users via `food_tags` JSONB. |
| **Generate recommendations** | Implemented | One Ollama call per Generate; optional Places-backed restaurant list injected into the prompt. |
| **Architecture context in the prompt** | Implemented | `docs/architecture.md` is injected into the system message. |
| **Agent 1 — Places + embedding RAG** | Implemented (optional) | Live restaurant candidates, semantic ranking, preference-aware search queries; details include `priceLevel` and review snippets for the LLM. |
| **Agent 2 — Dining copy** | Implemented | Structured dishes (`$`/`$$`/`$$$`) and places aligned to Agent 1 names when available. |
| **Full multi-agent orchestration** | Partial / evolving | Two-stage dining pipeline today; broader tool calling and review corpora remain roadmap (see target diagram). |

**Stakeholders:** **Travelers** get a single place for preferences and AI-assisted suggestions; **developers** get a small, inspectable stack (Shiny + Supabase + one LLM endpoint) that can grow toward the multi-agent design in `docs/architecture.md`.

**Preference UX (identity, returning users, Save vs Generate):** see [`docs/ui_flow_preferences.md`](docs/ui_flow_preferences.md).

### Process diagram and architecture reference

The content below is **generated** from [`docs/architecture.md`](docs/architecture.md). It includes the **target** pipeline (agents, RAG, tools) and a **current** Shiny data-flow diagram. Edit that file, then run `python3 scripts/build_readme.py` to refresh `README.md`. CI also regenerates `README.md` when `docs/architecture.md` or `README.template.md` changes.

{{ARCHITECTURE_BODY}}

### Technical documentation

#### System architecture (roles and workflow)

| Piece | Responsibility |
|-------|------------------|
| **UI** ([`shiny_app/ui.py`](shiny_app/ui.py), [`shiny_app/components/`](shiny_app/components/)) | Plan form, outputs grid (dishes, essential, friendliness), full-width dining places + map. |
| **Server** ([`shiny_app/server.py`](shiny_app/server.py)) | **Save** → Supabase user + preference; **Generate** → friendliness pipeline, optional Agent 1 Places RAG, build prompts, Ollama, parse JSON, map markers and embed URL. |
| **`plan_logic`** ([`shiny_app/plan_logic.py`](shiny_app/plan_logic.py)) | `build_trip_context`, user/system JSON instructions (dietary rules, dish `$`/`$$`/`$$$`, place alignment to Agent 1). |
| **`restaurant_rag`** ([`shiny_app/restaurant_rag.py`](shiny_app/restaurant_rag.py)) | Preference narrative → Places search (generic + food-hint query), embed query and place blurbs, cosine rank, Place Details, `price_tier` + `rag_match_score` on candidates. |
| **`google_places_client`** ([`shiny_app/google_places_client.py`](shiny_app/google_places_client.py)) | Places API (New): `searchText`, GET Place Details, field masks. |
| **`context`** ([`shiny_app/context.py`](shiny_app/context.py)) | Loads `docs/architecture.md` for the system prompt. |
| **`supabase_client`** ([`shiny_app/supabase_client.py`](shiny_app/supabase_client.py)) | Supabase client, users, preferences. |
| **`ollama_client`** ([`shiny_app/ollama_client.py`](shiny_app/ollama_client.py)) | Ollama Cloud chat + JSON extraction. |
| **`travel_friendliness`** ([`shiny_app/travel_friendliness/`](shiny_app/travel_friendliness/)) | World Bank fetch, scoring, HTML report. |

**Workflow (high level):** On **Generate**, World Bank friendliness runs first. If `GOOGLE_PLACES_API_KEY` is set, **Agent 1** fetches and ranks restaurants, then **Agent 2** (Ollama) receives `trip_and_food` + `agent1_restaurants` and returns JSON. The UI merges place rows with coordinates, shows **% match · $tier** from server data when available, and embeds the map. **Architecture.md** is still injected as system context.

#### RAG and tool implementation

| Topic | Implementation today | Roadmap (aligned with target diagram) |
|-------|----------------------|----------------------------------------|
| **RAG (restaurants)** | **Embedding retrieval** over **Places Text Search** results (name, address, types, editorial summary, rating line). Review text is **not** embedded for ranking; snippets are passed to the LLM after ranking. Optional **keyword overlap** boost from “food I like” tokens. | Richer signals (menus if licensed), multi-query fusion, optional re-rank with reviews. |
| **Architecture “RAG”** | Full [`docs/architecture.md`](docs/architecture.md) in the **system** message (static injection). | Same. |
| **Tool calling** | **No** LLM-invoked tools; Places and World Bank are **server-orchestrated** HTTP calls. | Model-driven tool use if product needs it. |

If you add tools later, document **name**, **purpose**, **parameters**, and **return shape** here and in code docstrings.

#### Technical details

**Environment variables** (set in [`shiny_app/.env`](shiny_app/.env); copy from [`shiny_app/.env.example`](shiny_app/.env.example)):

| Variable | Required | Purpose |
|----------|----------|---------|
| `SUPABASE_URL` | Yes (save / load) | Supabase project URL. |
| `SUPABASE_KEY` | Yes (save / load) | JWT-style API key (`eyJ…`) for `app_user` / `preference` (see `.env.example` for legacy key note). |
| `OLLAMA_API_KEY` | Yes (**Generate**) | Bearer token for Ollama Cloud. |
| `OLLAMA_HOST` | No | Base URL for the API (default `https://ollama.com/api/chat`). |
| `GOOGLE_PLACES_API_KEY` | No† | Agent 1 restaurant retrieval, Google **price level** on places, **RAG % match** from retrieval scores, and **Maps Embed** iframe. |

†**Why “No”?** The Shiny app **starts** and **Generate** still works without this key: you get LLM-written **dishes**, **essential** text, and **travel friendliness** (World Bank). You do **not** get real venue lookup, the **embedded map**, or server-backed **% match · $** on recommended places—those need `GOOGLE_PLACES_API_KEY`. Treat it as **required** if you want the full dining + map experience described in this README.

**Endpoints (app as client):**

- Supabase: project REST URL (used by `supabase-py`).
- Ollama Cloud: `{OLLAMA_HOST or https://ollama.com}/api/chat` — [`shiny_app/ollama_client.py`](shiny_app/ollama_client.py).
- Google: `https://places.googleapis.com/v1/places:searchText`, Place Details, and `https://www.google.com/maps/embed/v1/place` — [`shiny_app/google_places_client.py`](shiny_app/google_places_client.py).

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

- **Shiny app:** [`shiny_app/`](shiny_app/) — `app.py`, `ui.py`, `server.py`, `plan_logic.py`, `restaurant_rag.py`, `google_places_client.py`, `components/`, `www/custom.css`
- **SQL:** [`supabase/migrations/`](supabase/migrations/)
- **Docs / prompt context:** [`docs/architecture.md`](docs/architecture.md)

**Deployment:** The documented path is **local** (`shiny run app.py`). You can host on **Posit Connect**, **Shiny Server**, or a **container**; configure the same environment variables on the host. There is **no app-level password** in this prototype—use platform auth, VPN, or network rules if you expose it beyond localhost.

#### Usage instructions

1. **Environment:** Python 3.10+ recommended. From the repo root:

```bash
cd shiny_app
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # set SUPABASE_*, OLLAMA_*; optional GOOGLE_PLACES_API_KEY
```

2. **Run:**

```bash
shiny run app.py --reload
```

Or from repo root (after venv is ready): `./run_shiny.sh`

3. **Open** the URL Shiny prints (commonly `http://127.0.0.1:8000`).

4. **Use the UI:** Enter **destination** (country required), optional **compare** cities, **when** (season or month), **food** tags and text (including **dietary** checkboxes and restrictions). **Save food preferences** requires first name + email. **Generate recommendations** refreshes **dishes**, **recommended places** (+ map when Google is configured), **essential** blurbs, and **travel friendliness**. A recognized **email** (debounced or on blur) preloads saved preferences.

**Password:** None for the default local app. If you deploy behind a platform that adds authentication, follow that platform’s login flow.

---

## Development

To regenerate the root `README.md` after editing [`README.template.md`](README.template.md) or [`docs/architecture.md`](docs/architecture.md):

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

#### UI ↔ database mapping (Save)

Saving **food preferences** writes one `preference` row and ensures an `app_user` row. Trip fields (destination, compare, when) and **Generate** output are **not** persisted to these tables today.

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
