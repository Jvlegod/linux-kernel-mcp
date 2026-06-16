# API Guide

This page is the human-oriented guide for the MCP tool surface. The generated
reference pages describe Python symbols directly; this page explains what each
tool is for, what arguments it accepts, what it returns, and when to use it.

## Tool groups

Lookup and environment tools:

- `get_kernel_root`
- `set_kernel_root`
- `latest_kernel_releases`
- `search_kernel_docs`
- `fetch_kernel_doc`
- `search_local_kernel_code`
- `read_local_kernel_file`
- `search_local_kernel_api`
- `search_online_kernel_code`
- `fetch_upstream_kernel_file`
- `plan_kernel_implementation`

Driver-planning tools:

- `list_driver_template_blueprints_tool`
- `get_driver_template_blueprint_tool`
- `plan_driver_scaffold`

## Shared response patterns

Most tools return a JSON object.

Successful responses usually contain:

- plain metadata fields such as `root`, `path`, `symbol`, or `query`
- one structured payload such as `matches`, `results`, `snippet`, `blueprints`,
  or `implementation_plan`

Error responses usually contain:

- `error`: a readable error message

Typical examples:

```json
{
  "root": "/path/to/linux",
  "count": 2,
  "matches": [
    {
      "file": "/path/to/linux/drivers/foo.c",
      "line": 42,
      "column": 7,
      "text": "module_platform_driver(foo_driver);"
    }
  ]
}
```

```json
{
  "error": "Path does not exist: /bad/path"
}
```

## Environment tools

### `get_kernel_root`

Returns the current session root and the default root chosen from the
`LINUX_KERNEL_TREE` environment variable when present.

Arguments:

- none

Returns:

- `current_kernel_root`: active root used by local-tree tools, or `null`
- `default_kernel_root`: startup default root, or `null`
- `local_root_configured`: boolean indicating whether local-tree tools are usable

Use it when you need to confirm whether local-tree tools are available and, if
so, which kernel tree they will search.

Remote-only usage is valid. If no local kernel tree has been configured yet,
this tool returns `null` roots and local source-tree tools will report a clear
configuration error instead of blocking upstream-doc workflows.

Example:

```json
{
  "current_kernel_root": "/work/linux",
  "default_kernel_root": "/work/linux"
}
```

### `set_kernel_root`

Updates the active local kernel tree for the current MCP session. Remote-only
users do not need to call this unless they want local source inspection.

Arguments:

- `path`: absolute path or `~`-expanded path to a kernel source tree

Returns on success:

- `message`
- `current_kernel_root`

Possible errors:

- path does not exist
- path is not a directory

Example:

```json
{
  "message": "Source root updated for current MCP session",
  "current_kernel_root": "/home/user/linux-imx"
}
```

## Upstream docs and release tools

### `latest_kernel_releases`

Queries `kernel.org` release metadata.

Arguments:

- none

Returns:

- `latest_stable`
- `latest_mainline`
- `releases_url`

Use this when later scaffold planning or code comparison depends on the latest
mainline/stable version numbers.

### `search_kernel_docs`

Searches `docs.kernel.org`.

Arguments:

- `query`: search string
- `max_results`: optional integer, defaults to `5`

Returns:

- `query`
- `results`: list of objects containing `url`

This tool is useful when you know the subsystem or framework name but not the
exact document path.

### `fetch_kernel_doc`

Fetches one `docs.kernel.org` page and strips it down to a text excerpt.

Arguments:

- `url`: must begin with `https://docs.kernel.org`

Returns:

- `url`
- `title`
- `excerpt`

Possible errors:

- URL is outside `docs.kernel.org`
- upstream request failure

Typical workflow:

1. Call `search_kernel_docs`
2. Pick one result URL
3. Call `fetch_kernel_doc`

## Local source-tree tools

### `search_local_kernel_code`

Runs `ripgrep` on the active or explicit kernel root. This tool requires a
configured local kernel tree.

Arguments:

- `pattern`: regular expression or plain text passed to `rg`
- `glob`: optional filename filter, for example `*.c` or `arch/arm/boot/dts/*.dts*`
- `limit`: maximum match count to collect
- `root`: optional override root for this call only

Returns:

- `root`
- `count`
- `matches`

Each `matches` entry contains:

- `file`
- `line`
- `column`
- `text`

Possible errors:

- no local kernel tree is configured
- root does not exist
- `rg` is not installed
- `rg` returns an execution error

### `read_local_kernel_file`

Reads a bounded file snippet from the active kernel root. This tool requires a
configured local kernel tree.

Arguments:

- `relative_path`: path relative to the selected root
- `start_line`: one-based start line
- `max_lines`: maximum number of lines to return
- `root`: optional one-call root override

Returns:

- `path`
- `start_line`
- `end_line`
- `snippet`

Each `snippet` entry contains:

- `line`
- `text`

Possible errors:

- no local kernel tree is configured
- file not found
- path escapes the selected kernel root

### `search_local_kernel_api`

Searches a symbol name as both a call-like pattern and a bare identifier. This
tool requires a configured local kernel tree.

Arguments:

- `symbol`: API or symbol name to search
- `root`: optional one-call root override
- `limit`: maximum number of merged matches returned

Returns:

- `symbol`
- `root`
- `count`
- `matches`

Use this tool when you want declarations, definitions, and nearby call sites
without manually crafting multiple grep patterns. If no local tree is set, use
remote docs or upstream source tools first.

## Online source-browsing tools

### `search_online_kernel_code`

Returns source-browsing entry points rather than raw code.

Arguments:

- `symbol`: symbol or string to search for online

Returns:

- `symbol`
- `bootlin_search_url`
- `gitiles_repo_url`
- `note`

Use this when you want to jump from the MCP response into Bootlin or upstream
Gitiles manually.

### `fetch_upstream_kernel_file`

Fetches a file snippet from the upstream Torvalds tree via Gitiles.

Arguments:

- `relative_path`: path inside the Linux tree
- `ref`: branch, tag, or commit-ish, default `master`
- `start_line`: one-based start line
- `max_lines`: maximum number of lines to return

Returns:

- `path`
- `ref`
- `url`
- `start_line`
- `end_line`
- `snippet`

Possible errors:

- upstream request failure
- base64 decode failure

Typical workflow:

1. Find a local implementation
2. Fetch the matching upstream file
3. Compare helper usage or subsystem patterns

## Planning tools

### `plan_kernel_implementation`

Returns a generic engineering checklist for a kernel-facing task.

Arguments:

- `task`: short task description
- `interfaces`: optional list of API names or interfaces to inspect

Returns:

- `task`
- `interfaces`
- `implementation_plan`

Use it when the user is still shaping an approach and is not yet asking for a
subsystem-specific scaffold.

## Driver-planning tools

### `list_driver_template_blueprints_tool`

Lists currently supported subsystem blueprints.

Arguments:

- none

Returns:

- `count`
- `blueprints`

Each blueprint contains metadata such as:

- `subsystem`
- `template_id`
- `summary`
- `target_directories`
- `common_headers`
- `typical_probe_flow`
- `prompt_hints`

### `get_driver_template_blueprint_tool`

Returns one subsystem blueprint.

Arguments:

- `subsystem`: current supported values include `platform`, `i2c`, and `spi`

Returns:

- one blueprint object

Possible errors:

- unsupported subsystem

Use it when you need to inspect the shape of a specific driver family before
planning code generation.

### `plan_driver_scaffold`

Builds a version-aware driver scaffold plan without generating final C source.

Arguments:

- `subsystem`: driver family, for example `platform`, `i2c`, or `spi`
- `driver_name`: basename for the intended driver
- `kernel_version`: target kernel version or BSP label

Returns:

- `driver_name`
- `subsystem`
- `kernel_version`
- `template_id`
- `recommended_target_directory`
- `generated_file_names`
- `required_updates`
- `compatibility_notes`
- `local_research_steps`
- `prompt_hints`

Possible errors:

- unsupported subsystem

This tool is the current bridge between lookup and future code generation. It
packages the subsystem blueprint into a result that Codex can later consume to
build a concrete driver skeleton.

## Internal structure

- `linux_kernel_mcp.server`
  MCP tool handlers and transport entrypoint.
- `linux_kernel_mcp.models`
  Typed dataclasses for line snippets, search matches, and driver-plan models.
- `linux_kernel_mcp.templates`
  Subsystem blueprint registry and scaffold-planning helpers.
