# Source syntax boundary

Use pinned standard Tree-sitter grammars for Python, C# and TypeScript/TSX.
Parse at most 1 MiB with cancellation and a five-second deadline. Reject error
or missing nodes. Parsing never imports, compiles or executes application code.
CGO stays in the CLI workflow, outside the existing CGO-disabled MCP servers.
Syntax success is not type resolution, executable lowering or equivalence.
