# scrapydweb (FastAPI / uv) task runner -- https://github.com/casey/just
# Run `just` to list recipes.

# Where the test scrapyd stores logs; MUST equal LOCAL_SCRAPYD_LOGS_DIR for the suite.
logs_dir := env_var('HOME') / "logs"
scrapyd_dir := "/tmp/scrapyd_run"

# Env the integration suite expects: bypass any local proxy for the fake node, and
# disable alerts (no tokens configured in tests).
export NO_PROXY := "scrapydweb-fake-domain.com,127.0.0.1,localhost"
export no_proxy := "scrapydweb-fake-domain.com,127.0.0.1,localhost"
export ENABLE_SLACK_ALERT := "False"
export ENABLE_TELEGRAM_ALERT := "False"
export ENABLE_EMAIL_ALERT := "False"

# List recipes
default:
    @just --list

# Sync the uv environment (runtime + test deps)
install:
    uv sync

# Re-resolve the lockfile
lock:
    uv lock

# Serve the app via uvicorn (reads ./scrapydweb_settings_v11.py if present)
run:
    uv run scrapydweb

# Dev server with auto-reload at http://127.0.0.1:{{port}} (Ctrl-C to stop).
# Override servers: `SCRAPYD_SERVERS=admin:12345@127.0.0.1:6800 just dev`
dev port="5000":
    uv run uvicorn scrapydweb.asgi:app --reload --host 127.0.0.1 --port {{port}}

# Start a local Scrapyd for the test suite (foreground; Ctrl-C to stop)
scrapyd:
    mkdir -p {{scrapyd_dir}} {{logs_dir}}
    printf '[scrapyd]\nbind_address = 127.0.0.1\nhttp_port = 6800\nusername = admin\npassword = 12345\nlogs_dir = {{logs_dir}}\npoll_interval = 1.0\n' > {{scrapyd_dir}}/scrapyd.conf
    rm -f {{scrapyd_dir}}/twistd.pid
    cd {{scrapyd_dir}} && exec uv --project {{justfile_directory()}} run scrapyd

# Run the integration tests (needs a Scrapyd from `just scrapyd` in another shell).
# Pass extra pytest args: `just test tests/test_api.py -x`
test *args:
    uv run pytest {{ if args == "" { "tests/" } else { args } }} -q -p no:cacheprovider

# Quick non-integration check: the app imports and boots
smoke:
    uv run python -c "from scrapydweb import create_app; create_app({'SCRAPYD_SERVERS': ['127.0.0.1:6800']}); print('OK')"

# Remove caches and build artifacts
clean:
    rm -rf .pytest_cache build dist *.egg-info
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
