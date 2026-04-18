# MCP Architecture

Canonical docs:

- `humeo-core/docs/ARCHITECTURE.md`
- `humeo-core/docs/MCP_USAGE.md`

Short version:

- `humeo-core` is the engine
- it owns schemas, primitives, and the MCP server
- the root app `src/humeo` calls into it

This top-level file remains only to preserve old references.
