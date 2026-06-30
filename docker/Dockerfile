# scrapydweb application image
# Stage 1 builds the React SPA (Vite); stage 2 is the uv-managed Python runtime.

# ---------------------------------------------------------------- ui bundle
FROM --platform=$BUILDPLATFORM public.ecr.aws/docker/library/node:22-alpine AS ui
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM public.ecr.aws/docker/library/python:3.13-slim AS app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Cap glibc malloc arenas. scrapydweb runs two BackgroundScheduler thread
    # pools (timer tasks + system jobs) plus uvicorn; on a many-core host glibc
    # would otherwise spread freed memory across ~8*ncores arenas and never
    # return it, so RSS ratchets upward for days even with no logical leak (the
    # collector parses multi-MB log bodies as transients). 2 arenas + a low trim
    # threshold keep RSS flat.
    MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=131072
# git: the "deploy from git" feature. gosu: entrypoint drops root -> app user.
RUN apt-get update && apt-get install -y --no-install-recommends git gosu \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY scrapydweb ./scrapydweb
# Runtime deps only: the "test" dependency-group (scrapy/scrapyd/Twisted) is for the
# live integration suite, not the app.
RUN uv sync --frozen --no-dev --no-group test

COPY --from=ui /build/dist ./frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Writable data dir + non-root (host-uid) app user so bind-mounted scrapyd logs
# the in-container logparser touches stay owned by the developer. The container
# starts as root only so the entrypoint can chown a fresh bind mount, then drops
# to uid 1000 before exec'ing uvicorn.
ENV DATA_PATH=/data
RUN mkdir -p /data && chown -R 1000:1000 /data /app

EXPOSE 5000
ENV HOME=/app
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/app/.venv/bin/uvicorn", "scrapydweb.asgi:app", "--host", "0.0.0.0", "--port", "5000"]
