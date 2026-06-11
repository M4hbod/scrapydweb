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
    PYTHONUNBUFFERED=1
# git: used by the "deploy from git" feature
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY scrapydweb ./scrapydweb
# Runtime deps only: the "test" dependency-group (scrapy/scrapyd/Twisted) is for the
# live integration suite, not the app.
RUN uv sync --frozen --no-dev --no-group test

COPY --from=ui /build/dist ./frontend/dist

# Writable data dir + non-root (host-uid) user so bind-mounted scrapyd logs that
# the in-container logparser touches stay owned by the developer.
ENV DATA_PATH=/data
RUN mkdir -p /data && chown -R 1000:1000 /data /app
USER 1000:1000

EXPOSE 5000
ENV HOME=/app
CMD ["/app/.venv/bin/uvicorn", "scrapydweb.asgi:app", "--host", "0.0.0.0", "--port", "5000"]
