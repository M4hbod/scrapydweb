#!/bin/sh
# When started as root, fix ownership of the data dir (bind mounts come in as
# root:root and override the image's chown) and drop to the unprivileged app
# user. When the image is already run as a non-root user, just exec.
set -e

if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 "${DATA_PATH:-/data}" 2>/dev/null || true
    exec gosu 1000:1000 "$@"
fi

exec "$@"
