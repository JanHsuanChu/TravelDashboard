# Travel Dashboard

Web app for planning trips, tracking places, and viewing travel context in one UI.

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

## Development

This repository is **Shiny for Python** only. Run the dashboard from [`shiny_app/`](shiny_app/) (see below).

To regenerate the root `README.md` after editing [`README.template.md`](README.template.md) or [`docs/architecture.md`](docs/architecture.md):

```bash
python3 scripts/build_readme.py
```

## Stack

- [Shiny for Python](https://shiny.posit.co/py/) — dashboard in [`shiny_app/`](shiny_app/) (Bootstrap-style cards via `ui.card` / `ui.layout_columns`)

## Python Shiny dashboard

Browser-only app: trip/compare/when inputs (UI-only for now), food preferences saved to Supabase `preference`, optional **Generate** calls **Ollama Cloud** `gpt-oss:20b-cloud` with [`docs/architecture.md`](docs/architecture.md) as context.

**Paths:** `requirements.txt` and `app.py` live in **`shiny_app/`** inside this repo. If `cd TravelDashboard/shiny_app` fails, your shell is not in the parent of `TravelDashboard` (for example you might be in `TravelDashboard` already — then use `cd shiny_app` only, or use the absolute path to `TravelDashboard/shiny_app`).

**Do not** run `export SUPABASE_*=...` in zsh with a bare `*` — set real names, e.g. `export SUPABASE_URL="..."` and `export SUPABASE_KEY="..."`, or put them in `shiny_app/.env`.

```bash
# From the TravelDashboard repo root (the folder that contains shiny_app/):
cd shiny_app
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add SUPABASE_URL, SUPABASE_KEY, OLLAMA_API_KEY
shiny run app.py --reload
```

Or from the repo root, after the venv above exists and `shiny` is on your PATH:

```bash
chmod +x run_shiny.sh
./run_shiny.sh
```

Open the URL Shiny prints (usually `http://127.0.0.1:8000`).

## Architecture

The diagram and legend below are **generated** from [`docs/architecture.md`](docs/architecture.md). Edit that file, then run `python3 scripts/build_readme.py` to refresh `README.md`. CI also regenerates `README.md` when `docs/architecture.md` or `README.template.md` changes.

{{ARCHITECTURE_BODY}}

## Supabase

**Project URL:** `https://stnfxxjktzznvlfhczcz.supabase.co`  
**Project reference (for MCP):** `stnfxxjktzznvlfhczcz`

### Schema

#### `app_user`

| Column | Type | Constraints |
|--------|------|-------------|
| `user_id` | `UUID` | Primary key, default `gen_random_uuid()` |
| `first_name` | `TEXT` | not null |
| `email` | `TEXT` | not null, unique |
| `created_at` | `TIMESTAMPTZ` | not null, default `now()` |

#### `preference`

| Column | Type | Constraints |
|--------|------|-------------|
| `preference_id` | `BIGINT` | Primary key, generated identity |
| `user_id` | `UUID` | not null, FK → `app_user(user_id)` (cascade on delete) |
| `created_at` | `TIMESTAMPTZ` | not null, default `now()` |
| `dietary_restrictions` | `TEXT` | nullable (third food free-text field; UI max 50 words) |
| `dining_preference` | `TEXT` | nullable |
| `food_like_text` | `TEXT` | nullable (UI max 50 words) |
| `food_dislike_text` | `TEXT` | nullable (UI max 50 words) |
| `food_tags` | `JSONB` | not null, default `{}` — preset checkbox slugs: `like` / `dislike` / `dietary` arrays |

Index: `idx_preference_user_created_at` on `(user_id, created_at DESC)`.

### Apply migrations

Run in order:

1. [`supabase/migrations/001_app_user_preference.sql`](supabase/migrations/001_app_user_preference.sql)
2. [`supabase/migrations/002_preference_food_text.sql`](supabase/migrations/002_preference_food_text.sql)

- **Option A: Supabase Dashboard (SQL Editor)**: paste each file and **Run**.
- **Option B: Supabase MCP**: `apply_migration` / `execute_sql` with the same SQL.

## Layout

- **Shiny (Python):** [`shiny_app/`](shiny_app/) — `app.py`, `ui.py`, `server.py`, [`components/`](shiny_app/components/), [`www/custom.css`](shiny_app/www/custom.css)
- **SQL:** [`supabase/migrations/`](supabase/migrations/)
