# ScrapydWeb frontend

The single-page app for ScrapydWeb: React 19 + TypeScript, Vite, Tailwind v4,
shadcn/ui, TanStack Query/Table, react-router v7.

## Develop

```bash
npm ci          # or: just ui-install
npm run dev     # Vite dev server on :5173 (or: just ui-dev)
```

The dev server proxies `/api` and the scrapyd-proxy routes to the FastAPI backend on
`:5000`, so run `just dev` alongside it.

## Build

```bash
npm run build   # type-check + Vite build -> dist/  (or: just ui-build)
npm run lint
```

The FastAPI app serves the contents of `dist/` in production.

## Layout

- `src/pages/` — one component per route (dashboard, jobs, deploy, schedule, alerts,
  settings, log viewer, code viewer, …)
- `src/components/` — shared UI; `components/ui/` is shadcn/ui primitives
- `src/lib/api.ts` — typed client for the backend JSON API
- `src/lib/node-context.tsx` — current scrapyd node selection
