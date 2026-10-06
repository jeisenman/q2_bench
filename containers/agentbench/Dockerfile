FROM golang:1.25-bookworm AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY adapters ./adapters
COPY agentmemory ./agentmemory
COPY agents ./agents
COPY cmd ./cmd
COPY dependencyintelligence ./dependencyintelligence
COPY domain ./domain
COPY mcpapi ./mcpapi
COPY ports ./ports
COPY workflowharness ./workflowharness
COPY workflows ./workflows
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /q2-mcp ./cmd/q2-mcp

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 agentbench \
    && useradd --create-home --uid 1000 --gid 1000 agentbench

WORKDIR /workspace
COPY --from=build /q2-mcp /usr/local/bin/q2-mcp
USER agentbench
ENTRYPOINT ["q2-mcp"]
CMD ["--server", "prod-support", "--transport", "streamable-http", "--host", "0.0.0.0"]
