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
```

## Stack

- [Vite](https://vitejs.dev/) + [React](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)

## Layout

All app code lives under this directory (`TravelDashboard/`). Add routes, API clients, and components under `src/` as the product grows.
