# MCP Architecture

Canonical docs:

- `humeo-mcp/docs/ARCHITECTURE.md`
- `humeo-mcp/docs/MCP_USAGE.md`

Short version:

- `humeo-mcp` is the engine
- it owns schemas, primitives, and the MCP server
- the root app `src/humeo` calls into it

This top-level file remains only to preserve old references.
