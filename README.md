# ScrapydWeb

[![CI](https://github.com/M4hbod/scrapydweb/actions/workflows/ci.yml/badge.svg)](https://github.com/M4hbod/scrapydweb/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/M4hbod/scrapydweb.svg)](LICENSE)

Web UI and JSON API for managing a [Scrapyd](https://github.com/scrapy/scrapyd) cluster:
deploy projects, run and schedule spiders, watch jobs, read parsed logs, and get
alerted when crawls go wrong.

This is a ground-up rewrite of the original [my8100/scrapydweb](https://github.com/my8100/scrapydweb):
a **FastAPI** backend (async, SQLAlchemy 2.0, PostgreSQL) serving a **React** single-page
app (Vite, Tailwind v4, shadcn/ui). The legacy Flask app, server-rendered templates, and
SQLite support have been removed.

![Dashboard](screenshots/dashboard.png)

## Features

- **Cluster dashboard** — per-node KPIs (running/pending/finished, pages, items), 14-day
  throughput chart, recent-activity feed.
- **Jobs** — live job table backed by a local database (survives scrapyd restarts),
  with the egg version each job ran recorded and linked to a code viewer.
- **Deploy** — upload an egg, build from a project folder, or deploy from a Git repo;
  push to multiple nodes at once with per-node results and deploy history. Optional
  **GitHub webhook auto-deploy** (HMAC-verified) per registered repo.
- **Run Spider** — structured Scrapy-settings editor (searchable catalog, type-aware
  inputs) and spider arguments, a live request summary with equivalent `curl`, and
  one-click run or cron-scheduled **timer tasks**.
- **Log viewer** — fetches job logs over HTTP and parses them with
  [logparser](https://github.com/my8100/logparser); a background collector stores stats
  centrally (no per-host daemons).
- **Alerts** — Slack / Telegram / Email on log thresholds, finish, or a running
  interval, with per-project/spider rules that overlay the global settings; can stop or
  force-stop offending jobs.
- **Auth & settings** — single-admin session login; all settings are DB-backed and
  editable from the UI (env vars seed the defaults).

| Jobs | Run Spider | Deploy |
|---|---|---|
| ![Jobs](screenshots/jobs.png) | ![Run Spider](screenshots/run-spider.png) | ![Deploy](screenshots/deploy.png) |

## Requirements

- Python 3.11+ and [uv](https://github.com/astral-sh/uv)
- Node 20+ (to build the SPA)
- A PostgreSQL (or MySQL) server — **required**, set via `DATABASE_URL`
- One or more Scrapyd servers to manage
- Optional: Docker + Docker Compose, and [just](https://github.com/casey/just) for the
  task runner

## Quick start (prebuilt image)

No build, no clone — pull the published image from GHCR and run the app + PostgreSQL,
pointed at your own Scrapyd node:

```bash
curl -O https://raw.githubusercontent.com/M4hbod/scrapydweb/main/docker-compose.deploy.yml
SCRAPYD_SERVERS=admin:12345@host.docker.internal:6800 \
  docker compose -f docker-compose.deploy.yml up -d
# open http://127.0.0.1:5000  (first visit creates the admin account)
```

The `ghcr.io/m4hbod/scrapydweb` image is built and pushed by CI on every push to
`main` (tag `latest`) and on version tags (`vX.Y.Z`). Pin a version with
`SCRAPYDWEB_TAG=v1.0.0`. You can also leave `SCRAPYD_SERVERS` unset and add nodes from
the Settings page once the app is running.

## Build it yourself (Docker Compose)

Builds the image locally and includes a demo Scrapyd node for trying it out:

```bash
just up          # docker compose up -d --build
# open http://127.0.0.1:5000
```

## Local development

```bash
just infra       # postgres + scrapyd containers only
just install     # uv sync (backend deps)
just ui-install  # npm ci (frontend deps)

just dev         # FastAPI on :5000 (auto-reload)
just ui-dev      # Vite dev server on :5173, proxies the API to :5000
```

Build the SPA into `frontend/dist` (served by the app in production):

```bash
just ui-build
```

`DATABASE_URL` defaults to `postgres://scrapydweb:scrapydweb@127.0.0.1:5432`. The app
creates a single database named `scrapydweb` and runs Alembic migrations on startup.
Add Scrapyd servers from the Settings page (or seed them via the `SCRAPYD_SERVERS`
environment variable).

## Database migrations

Schema is managed by Alembic and applied automatically when the app boots.

```bash
just revision m="add a column"   # autogenerate from model changes
just migrate                     # alembic upgrade head
```

## Tests

The fast suite runs against an in-process fake Scrapyd — no real Scrapyd needed, only
PostgreSQL:

```bash
just test        # fast suite (~20s)
just cov         # fast suite + coverage report
just test-live   # full suite incl. live-Scrapyd integration tests (needs `just infra`)
just e2e         # Playwright smoke over the built SPA (needs a running app)
```

## Continuous integration

One workflow, `.github/workflows/ci.yml`, on every push/PR:

1. **Backend tests** — the fast suite against a PostgreSQL service (in-process fake
   Scrapyd, no real Scrapyd needed).
2. **Frontend** — type-check + build the SPA.
3. **Docker image** — only runs once (1) and (2) pass, so a red suite blocks the image.
   On `main` and `vX.Y.Z` tags it pushes `ghcr.io/m4hbod/scrapydweb` to GHCR (tags:
   `latest`, the short SHA, semver on releases); on PRs it just validates the build.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE). Original work
© the [my8100/scrapydweb](https://github.com/my8100/scrapydweb) authors.
