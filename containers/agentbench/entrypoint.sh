#!/bin/sh
set -eu

: "${CODEX_HOME:?CODEX_HOME must be configured}"
: "${CODEX_SOURCE_HOME:?CODEX_SOURCE_HOME must be configured}"

if [ ! -f /workspace/.env ]; then
    echo "Environment file is missing: /workspace/.env" >&2
    exit 1
fi
if [ ! -f /workspace/configurations.yaml ]; then
    echo "User configuration is missing: /workspace/configurations.yaml" >&2
    exit 1
fi

# Docker's env_file already supplies these values for normal compose runs.
# Loading here also supports direct entrypoint use, while preserving values
# explicitly supplied by the caller.
set -a
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        [[:space:]]*|''|\#*) continue ;;
    esac
    variable=${line%%=*}
    case "$variable" in
        ''|*[!A-Za-z_0-9]*) continue ;;
    esac
    if eval "[ -z \"\${$variable+x}\" ]"; then
        value=${line#*=}
        eval "export $variable=\${value}"
    fi
done < /workspace/.env
set +a

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
