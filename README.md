# linux-kernel-mcp

`linux-kernel-mcp` is an MCP server that lets Codex look up Linux kernel
documentation, upstream source files, release information, and optional local
kernel source trees.

Chinese documentation is available in [README.zh-CN.md](./README.zh-CN.md).

You do not need a local Linux checkout to use the remote documentation tools.
Local source-tree search is optional and can be enabled later when you have a
kernel tree on your machine.

## Quick Start

Register the server with Codex:

```bash
codex mcp add linux_kernel -- uvx linux-kernel-mcp
```

Restart Codex after adding the MCP server.

After that, ask Codex kernel-related questions such as:

```text
Search the latest Linux kernel docs for GPIO descriptor APIs.
```

```text
Fetch the upstream implementation of drivers/gpio/gpiolib.c around line 200.
```

```text
What is the latest stable Linux kernel release?
```

## What Works Without A Local Kernel Tree

These features work immediately after installation:

- Search `docs.kernel.org`
- Fetch and summarize a `docs.kernel.org` page
- Query latest stable and mainline releases from `kernel.org`
- Open online source-browsing entry points for kernel symbols
- Fetch files from the upstream Torvalds tree through Gitiles
- Build high-level implementation checklists for kernel-facing tasks

This is enough for documentation lookup, API research, and comparing against
latest upstream code.

## Optional Local Kernel Tree

If you also have a Linux kernel source tree locally, enable local inspection in
one of two ways.

Set a default before starting Codex:

```bash
export LINUX_KERNEL_TREE=/path/to/linux
```

Or set it during a Codex session:

```text
set_kernel_root("/path/to/linux")
```

Then local tools can search and read your tree:

```text
search_local_kernel_api("devm_gpiod_get")
```

```text
read_local_kernel_file("drivers/gpio/gpiolib.c", start_line=200)
```

Check the active local root:

```text
get_kernel_root()
```

Use a different tree for one call:

```text
search_local_kernel_api("platform_driver_register", root="/path/to/other/linux")
```

If no local tree is configured, local tools return a clear configuration error.
Remote documentation and upstream source tools continue to work.

## Available Tools

Remote lookup tools:

- `latest_kernel_releases`
- `search_kernel_docs`
- `fetch_kernel_doc`
- `search_online_kernel_code`
- `fetch_upstream_kernel_file`
- `plan_kernel_implementation`

Local source-tree tools:

- `get_kernel_root`
- `set_kernel_root`
- `search_local_kernel_code`
- `read_local_kernel_file`
- `search_local_kernel_api`

Driver-planning tools:

- `list_driver_template_blueprints_tool`
- `get_driver_template_blueprint_tool`
- `plan_driver_scaffold`

## Typical Workflow

1. Search the latest official docs for the subsystem or API.
2. Fetch upstream source snippets when the latest implementation matters.
3. Configure a local kernel tree only if you need version-specific local code.
4. Search nearby local examples and API call sites.
5. Ask Codex to plan the implementation and call out version-sensitive checks.

## Codex Configuration

The `codex mcp add` command writes this configuration for you:

```toml
[mcp_servers.linux_kernel]
command = "uvx"
args = ["linux-kernel-mcp"]
```

To make a project always use one local kernel tree, add:

```toml
[mcp_servers.linux_kernel.env]
LINUX_KERNEL_TREE = "/path/to/linux"
```

## Local Development

If you are working from a local checkout of this repository instead of the PyPI
package, register the checkout path:

```bash
codex mcp add linux_kernel -- uvx --from /path/to/linux-kernel-mcp linux-kernel-mcp
```

From inside the repository, you can build and test the package:

```bash
uv build
uvx --from dist/linux_kernel_mcp-0.1.0-py3-none-any.whl linux-kernel-mcp
```

The command starts an MCP stdio server and waits for a client handshake, so it
does not print normal CLI output.

## Limitations

- The server provides lookup and planning tools; it does not guarantee that a
  kernel patch is correct.
- Driver scaffold planning is metadata-first today; it does not emit final C
  source yet.
- Upstream source lookup fetches by file path rather than by a full symbol
  index.
- `set_kernel_root` is session-local state. After an MCP restart, set it again
  or provide `LINUX_KERNEL_TREE`.
