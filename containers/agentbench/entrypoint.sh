#!/bin/sh
set -eu

: "${CODEX_HOME:?CODEX_HOME must be configured}"
: "${CODEX_SOURCE_HOME:?CODEX_SOURCE_HOME must be configured}"

if [ ! -d "$CODEX_SOURCE_HOME" ]; then
    echo "Codex source configuration is missing: $CODEX_SOURCE_HOME" >&2
    exit 1
fi
if [ ! -w "$CODEX_HOME" ]; then
    echo "Codex runtime home is not writable: $CODEX_HOME" >&2
    exit 1
fi

tar --warning=no-file-changed --exclude='./ipc' -C "$CODEX_SOURCE_HOME" -cf - . |
    tar -C "$CODEX_HOME" -xf -
chmod -R u+rwX "$CODEX_HOME"

if [ "${1:-}" = "codex" ]; then
    exec "$@"
fi
exec uv run --no-sync "$@"
