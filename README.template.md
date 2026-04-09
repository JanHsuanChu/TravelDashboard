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

Requires [Node.js](https://nodejs.org/) 18+ and npm.

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`).

```bash
npm run build    # production build to dist/
npm run preview  # serve dist locally
npm run readme    # regenerate README.md from docs/architecture.md (see Architecture section)
```

## Stack

- [Vite](https://vitejs.dev/) + [React](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)

## Architecture

The diagram and legend below are **generated** from [`docs/architecture.md`](docs/architecture.md). Edit that file, then run `npm run readme` to refresh `README.md`. CI also regenerates `README.md` when `docs/architecture.md` or `README.template.md` changes.

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
| `dietary_restrictions` | `TEXT` | nullable |
| `dining_preference` | `TEXT` | nullable |

Index: `idx_preference_user_created_at` on `(user_id, created_at DESC)`.

### Apply migrations

The migration is in [`supabase/migrations/001_app_user_preference.sql`](supabase/migrations/001_app_user_preference.sql).

- **Option A: Supabase Dashboard (SQL Editor)**: open SQL Editor, paste the file contents, click **Run**.
- **Option B: Supabase MCP**: configure MCP with `https://mcp.supabase.com/mcp?project_ref=stnfxxjktzznvlfhczcz`, then run `apply_migration` / `execute_sql` with the file contents.

## Layout

All app code lives under this directory (`TravelDashboard/`). Add routes, API clients, and components under `src/` as the product grows.
