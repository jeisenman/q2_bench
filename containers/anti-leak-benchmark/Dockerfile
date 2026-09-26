FROM ghcr.io/astral-sh/uv:0.8.15-python3.11-bookworm-slim

RUN groupadd --gid 10001 benchmark \
    && useradd --no-create-home --uid 10001 --gid 10001 benchmark

WORKDIR /benchmark

COPY src/workspaces/data_engineering/benchmarks/anti_leak/dates/09-26-26/assets \
    /benchmark/assets

USER benchmark

ENTRYPOINT ["python", "-m", "json.tool"]
CMD ["/benchmark/assets/container_snapshot.json"]
