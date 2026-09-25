FROM ghcr.io/astral-sh/uv:0.8.15-python3.11-bookworm-slim

ENV HOME=/home/agentbench \
    PATH=/workspace/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN groupadd --gid 1000 agentbench \
    && useradd --create-home --uid 1000 --gid 1000 agentbench

RUN apt-get update \
    && apt-get install --yes --no-install-recommends nodejs npm \
    && npm install --global @openai/codex@0.156.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev \
    && mkdir -p /workspace/var /home/agentbench/.aws \
        /home/agentbench/.bedrock_codex \
    && chown -R agentbench:agentbench /workspace/var /home/agentbench

USER agentbench

ENTRYPOINT ["uv", "run", "--no-sync"]
CMD ["agentbench", "--help"]
