# scrapydweb (FastAPI / uv) task runner -- https://github.com/casey/just
# Run `just` to list recipes.
#
# Easiest way to run everything: `just up`   (docker compose: app + scrapyd + postgres)
# Local dev loop:                `just up` then `just dev` (app local, infra in docker)

# Where the test scrapyd stores logs (served over HTTP; the central stats
# collector parses them). The compose scrapyd binds this same dir.
logs_dir := env_var('HOME') / "logs"
scrapyd_dir := "/tmp/scrapyd_run"

# Env the integration suite expects: bypass any local proxy for the fake node, and
# disable alerts (no tokens configured in tests).
export NO_PROXY := "scrapydweb-fake-domain.com,127.0.0.1,localhost"
export no_proxy := "scrapydweb-fake-domain.com,127.0.0.1,localhost"
export ENABLE_SLACK_ALERT := "False"
export ENABLE_TELEGRAM_ALERT := "False"
export ENABLE_EMAIL_ALERT := "False"

# PostgreSQL (the compose `postgres` service publishes 127.0.0.1:5432)
export DATABASE_URL := env_var_or_default('DATABASE_URL', 'postgres://scrapydweb:scrapydweb@127.0.0.1:5432')

# List recipes
default:
    @just --list

# Bring up the whole stack (app + scrapyd + postgres) in docker
up:
    docker compose up -d --build

# Tear the stack down (keep volumes/data)
down:
    docker compose down

# Tail the stack logs
dc-logs *args:
    docker compose logs -f {{args}}

# Bring up only the infra (postgres + scrapyd) for local `just dev` / `just test`
infra:
    docker compose up -d --build postgres scrapyd

# Sync the uv environment (runtime + test deps)
install:
    uv sync

# Re-resolve the lockfile
lock:
    uv lock

# Serve the app via uvicorn (settings: env vars + DB-persisted UI edits)
run:
    uv run scrapydweb

# Dev server with auto-reload at http://127.0.0.1:{{port}} (Ctrl-C to stop).
# Override servers: `SCRAPYD_SERVERS=admin:12345@127.0.0.1:6800 just dev`
dev port="5000":
    uv run uvicorn scrapydweb.asgi:app --reload --host 127.0.0.1 --port {{port}}

# Apply pending DB migrations (also runs automatically at app startup)
migrate:
    uv run alembic upgrade head

# Autogenerate a migration from model changes: just revision m="add foo column"
revision m:
    uv run alembic revision --autogenerate -m "{{m}}"

# Start a local Scrapyd for the test suite (foreground; Ctrl-C to stop)
scrapyd:
    mkdir -p {{scrapyd_dir}} {{logs_dir}}
    printf '[scrapyd]\nbind_address = 127.0.0.1\nhttp_port = 6800\nusername = admin\npassword = 12345\nlogs_dir = {{logs_dir}}\npoll_interval = 1.0\n' > {{scrapyd_dir}}/scrapyd.conf
    rm -f {{scrapyd_dir}}/twistd.pid
    cd {{scrapyd_dir}} && exec uv --project {{justfile_directory()}} run scrapyd

# Run the integration tests (needs scrapyd + postgres: `just infra` or `just scrapyd`).
# SCRAPYDWEB_TESTMODE drops + recreates the 4 postgres DBs once per session.
# The dockerized app is stopped first: its logparser/poll/metadata writes would race
# the suite over the shared postgres DBs and ~/logs/stats.json. `just up` restarts it.
# Pass extra pytest args: `just test tests/test_api.py -x`
test *args:
    -docker compose stop scrapydweb 2>/dev/null
    SCRAPYDWEB_TESTMODE=True uv run pytest {{ if args == "" { "tests/" } else { args } }} -q -p no:cacheprovider

# Install the React frontend toolchain (Node, in frontend/)
ui-install:
    cd frontend && npm ci

# Vite dev server on :5173 (proxies API calls to :5000 -- run `just dev` too)
ui-dev:
    cd frontend && npm run dev

# Production build -> frontend/dist (served by the FastAPI app)
ui-build:
    cd frontend && npm run build

# Playwright smoke over the built SPA (needs `just ui-build` + a running app on :5000)
e2e base_url="http://127.0.0.1:5000":
    BASE_URL={{base_url}} uv run --with playwright python tests/e2e/smoke.py

# Quick non-integration check: the app imports and boots
smoke:
    uv run python -c "from scrapydweb import create_app; create_app({'SCRAPYD_SERVERS': ['127.0.0.1:6800']}); print('OK')"

# Remove caches and build artifacts
clean:
    rm -rf .pytest_cache build dist *.egg-info
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
