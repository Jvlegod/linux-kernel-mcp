# linux-kernel-mcp

`linux-kernel-mcp` is an MCP server for Linux kernel documentation lookup,
local-tree code search, upstream source comparison, and early-stage driver
scaffold planning.

## Documentation strategy

The codebase now uses:

- module-level docstrings
- function-level docstrings for public MCP tools
- typed dataclasses for reusable result structures
- an explicit subsystem template registry for future driver generation

That gives you a stable place to hang generated documentation later, instead of
trying to document one oversized `server.py` file.

## Generate docs

The project now ships with an `MkDocs + mkdocstrings` pipeline.

Install documentation dependencies:

```bash
uv sync --group docs
```

Preview the site locally:

```bash
uv run mkdocs serve
```

Build static documentation:

```bash
uv run mkdocs build
```

The generated reference pages read Python docstrings and type annotations from:

- `linux_kernel_mcp.server`
- `linux_kernel_mcp.models`
- `linux_kernel_mcp.templates`

## Driver-generation direction

The new template registry does not emit code yet. It records the subsystem-level
knowledge required for later generation, including:

- common headers
- typical file placement
- Kconfig and Makefile touch points
- probe-flow expectations
- version-sensitive checks
- suggested local research steps

That lets Codex query the blueprint first and only then compose a kernel-version-
aware driver scaffold.
