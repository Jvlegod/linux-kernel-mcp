"""MCP server for Linux kernel documentation, source lookup, and scaffold planning.

This module intentionally keeps tool handlers thin and well documented so the
project can grow in two directions:

- generate user-facing documentation from Python docstrings and type hints
- add higher-level kernel engineering workflows without turning tool handlers
  into a monolithic script
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx
from mcp.server.fastmcp import FastMCP

from .models import DriverScaffoldPlan, DriverTemplateBlueprint, LineSnippet, SearchMatch
from .templates import (
    build_driver_scaffold_plan,
    get_driver_template_blueprint,
    list_driver_template_blueprints,
)

DOCS_BASE = "https://docs.kernel.org"
KERNEL_RELEASES_JSON = "https://www.kernel.org/releases.json"
ELIXIR_SEARCH = "https://elixir.bootlin.com/linux/latest/source"
GITILES_BASE = "https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/master"
DEFAULT_LOCAL_KERNEL_ENV = os.environ.get("LINUX_KERNEL_TREE")
DEFAULT_LOCAL_KERNEL = (
    Path(DEFAULT_LOCAL_KERNEL_ENV).expanduser().resolve() if DEFAULT_LOCAL_KERNEL_ENV else None
)
CURRENT_KERNEL_ROOT = DEFAULT_LOCAL_KERNEL

mcp = FastMCP("linux-kernel-mcp")


def _http_get(url: str, params: dict[str, Any] | None = None) -> str:
    """Fetch a text response from an upstream HTTP endpoint."""

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(url, params=params, headers={"User-Agent": "linux-kernel-mcp/0.1"})
        response.raise_for_status()
        return response.text


def _resolve_kernel_root(root: str | None = None) -> Path | None:
    """Resolve an explicit or session-default local kernel root.

    Remote-only workflows are valid. When no local kernel tree has been
    configured, this function returns ``None`` instead of assuming the server's
    startup directory is a Linux source tree.
    """

    if root:
        return Path(root).expanduser().resolve()
    return CURRENT_KERNEL_ROOT


def _require_kernel_root(root: str | None = None) -> Path | None:
    """Return a kernel root or ``None`` if local-tree features are unavailable."""

    resolved = _resolve_kernel_root(root)
    if resolved is None:
        return None
    return resolved


def _serialize_lines(lines: list[LineSnippet]) -> list[dict[str, Any]]:
    """Convert line snippet models into JSON-serializable dictionaries."""

    return [asdict(line) for line in lines]


def _serialize_matches(matches: list[SearchMatch]) -> list[dict[str, Any]]:
    """Convert search result models into JSON-serializable dictionaries."""

    return [asdict(match) for match in matches]


def _missing_kernel_root_error() -> dict[str, Any]:
    """Return a consistent error when local-tree tools are used without a root."""

    return {
        "error": (
            "No local Linux kernel tree is configured. Set LINUX_KERNEL_TREE before startup "
            "or call set_kernel_root(path) before using local source-tree tools."
        )
    }


def _run_rg(pattern: str, root: Path, glob: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Run ripgrep against the selected kernel tree and normalize the result."""

    if not root.exists():
        return {"error": f"Local kernel tree not found: {root}"}

    cmd = ["rg", "-n", "--no-heading", "--color", "never", "-m", str(limit), pattern, str(root)]
    if glob:
        cmd[1:1] = ["-g", glob]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"error": "rg is not installed on this machine"}

    if proc.returncode not in (0, 1):
        return {"error": proc.stderr.strip() or "rg failed"}

    matches: list[SearchMatch] = []
    for line in proc.stdout.splitlines():
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        file_path, line_no, col_no, content = parts
        matches.append(
            SearchMatch(
                file=file_path,
                line=int(line_no),
                column=int(col_no),
                text=content.strip(),
            )
        )
    return {"root": str(root), "count": len(matches), "matches": _serialize_matches(matches)}


def _read_local_file(path: Path, start_line: int = 1, max_lines: int = 80) -> dict[str, Any]:
    """Read a bounded file snippet from the local filesystem."""

    if not path.exists():
        return {"error": f"File not found: {path}"}

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, start_line)
    end = min(len(lines), start + max_lines - 1)
    snippet = [LineSnippet(line=idx, text=lines[idx - 1]) for idx in range(start, end + 1)]
    return {"path": str(path), "start_line": start, "end_line": end, "snippet": _serialize_lines(snippet)}


def _strip_html(html: str) -> str:
    """Collapse a docs.kernel.org HTML page into plain text."""

    text = re.sub(r"(?is)<script.*?>.*?</script>", "", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _slice_lines(text: str, start_line: int = 1, max_lines: int = 80) -> dict[str, Any]:
    """Slice plain text into numbered line snippets."""

    lines = text.splitlines()
    start = max(1, start_line)
    end = min(len(lines), start + max_lines - 1)
    snippet = [LineSnippet(line=idx, text=lines[idx - 1]) for idx in range(start, end + 1)]
    return {"start_line": start, "end_line": end, "snippet": _serialize_lines(snippet)}


def _serialize_blueprint(blueprint: DriverTemplateBlueprint) -> dict[str, Any]:
    """Convert a driver template blueprint into plain JSON data."""

    return asdict(blueprint)


def _serialize_scaffold_plan(plan: DriverScaffoldPlan) -> dict[str, Any]:
    """Convert a driver scaffold plan into plain JSON data."""

    return asdict(plan)


@mcp.tool()
def get_kernel_root() -> dict[str, Any]:
    """Return the active and default local kernel source roots.

    Returns:
        A JSON object with the session-local source root and the process-default
        root chosen from ``LINUX_KERNEL_TREE`` when present.
    """

    return {
        "current_kernel_root": str(CURRENT_KERNEL_ROOT) if CURRENT_KERNEL_ROOT else None,
        "default_kernel_root": str(DEFAULT_LOCAL_KERNEL) if DEFAULT_LOCAL_KERNEL else None,
        "local_root_configured": CURRENT_KERNEL_ROOT is not None,
    }


@mcp.tool()
def set_kernel_root(path: str) -> dict[str, Any]:
    """Set the active local kernel source root for the current MCP session.

    Args:
        path: Absolute or user-relative directory path to a Linux kernel tree.

    Returns:
        A confirmation object containing the updated active root, or an ``error``
        field if the directory is invalid.
    """

    global CURRENT_KERNEL_ROOT
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return {"error": f"Path does not exist: {resolved}"}
    if not resolved.is_dir():
        return {"error": f"Path is not a directory: {resolved}"}
    CURRENT_KERNEL_ROOT = resolved
    return {
        "message": "Source root updated for current MCP session",
        "current_kernel_root": str(CURRENT_KERNEL_ROOT),
        "local_root_configured": True,
    }


@mcp.tool()
def latest_kernel_releases() -> dict[str, Any]:
    """Return the latest stable and mainline Linux releases from kernel.org."""

    data = json.loads(_http_get(KERNEL_RELEASES_JSON))
    latest_stable = data.get("latest_stable", {})
    latest_mainline = data.get("latest_mainline", {})
    return {
        "latest_stable": latest_stable,
        "latest_mainline": latest_mainline,
        "releases_url": KERNEL_RELEASES_JSON,
    }


@mcp.tool()
def search_kernel_docs(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the latest kernel documentation hosted on docs.kernel.org."""

    html = _http_get(
        f"{DOCS_BASE}/search.html",
        params={"q": query, "check_keywords": "yes", "area": "default"},
    )

    links = re.findall(r'href="([^"]+)"', html)
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in links:
        if "/search.html" in link:
            continue
        absolute = link if link.startswith("http") else f"{DOCS_BASE}/{link.lstrip('/')}"
        if absolute in seen:
            continue
        seen.add(absolute)
        results.append({"url": absolute})
        if len(results) >= max_results:
            break

    return {"query": query, "results": results}


@mcp.tool()
def fetch_kernel_doc(url: str) -> dict[str, Any]:
    """Fetch a docs.kernel.org page and return a plain-text excerpt."""

    if not url.startswith(DOCS_BASE):
        return {"error": f"Only docs.kernel.org URLs are allowed: {url}"}
    html = _http_get(url)
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else url
    text = _strip_html(html)
    return {"url": url, "title": title, "excerpt": text[:4000]}


@mcp.tool()
def search_local_kernel_code(
    pattern: str,
    glob: str | None = None,
    limit: int = 20,
    root: str | None = None,
) -> dict[str, Any]:
    """Search the local Linux tree with ripgrep and return structured matches."""

    search_root = _require_kernel_root(root)
    if search_root is None:
        return _missing_kernel_root_error()
    return _run_rg(pattern=pattern, root=search_root, glob=glob, limit=limit)


@mcp.tool()
def read_local_kernel_file(
    relative_path: str,
    start_line: int = 1,
    max_lines: int = 80,
    root: str | None = None,
) -> dict[str, Any]:
    """Read a bounded snippet from a file under the active kernel root."""

    base = _require_kernel_root(root)
    if base is None:
        return _missing_kernel_root_error()
    path = (base / relative_path).resolve()
    if base not in path.parents and path != base:
        return {"error": "Path escapes kernel root"}
    return _read_local_file(path=path, start_line=start_line, max_lines=max_lines)


@mcp.tool()
def search_local_kernel_api(symbol: str, root: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Search likely declarations, definitions, and call sites for a symbol."""

    search_root = _require_kernel_root(root)
    if search_root is None:
        return _missing_kernel_root_error()
    patterns = [
        rf"\b{re.escape(symbol)}\s*\(",
        rf"\b{re.escape(symbol)}\b",
    ]
    merged: list[SearchMatch] = []
    seen: set[tuple[str, int, int]] = set()
    for pattern in patterns:
        result = _run_rg(pattern=pattern, root=search_root, limit=limit)
        for match in result.get("matches", []):
            key = (match["file"], match["line"], match["column"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(SearchMatch(**match))
    return {
        "symbol": symbol,
        "root": str(search_root),
        "count": len(merged),
        "matches": _serialize_matches(merged[:limit]),
    }


@mcp.tool()
def search_online_kernel_code(symbol: str) -> dict[str, Any]:
    """Return online source-browsing entry points for a kernel symbol."""

    bootlin_url = f"{ELIXIR_SEARCH}?q={quote_plus(symbol)}"
    gitiles_search = f"{GITILES_BASE}/?format=JSON"
    return {
        "symbol": symbol,
        "bootlin_search_url": bootlin_url,
        "gitiles_repo_url": gitiles_search,
        "note": "Bootlin provides latest online source browsing; Gitiles provides the upstream Torvalds tree.",
    }


@mcp.tool()
def fetch_upstream_kernel_file(
    relative_path: str,
    ref: str = "master",
    start_line: int = 1,
    max_lines: int = 80,
) -> dict[str, Any]:
    """Fetch a file snippet from the upstream Torvalds tree via Gitiles."""

    safe_path = relative_path.lstrip("/")
    url = f"{GITILES_BASE}/{ref}/{safe_path}?format=TEXT"

    try:
        encoded = _http_get(url).strip()
        decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception as exc:
        return {"error": str(exc), "url": url}

    return {
        "path": safe_path,
        "ref": ref,
        "url": url,
        **_slice_lines(decoded, start_line=start_line, max_lines=max_lines),
    }


@mcp.tool()
def plan_kernel_implementation(task: str, interfaces: list[str] | None = None) -> dict[str, Any]:
    """Return a checklist for implementing a kernel-facing task.

    This tool is intentionally generic. It complements the more structured
    driver-template tools when the user is exploring a task rather than asking
    for a subsystem scaffold.
    """

    interfaces = interfaces or []
    steps = [
        "Clarify target subsystem, kernel version, and whether the work is driver, DTS, core-kernel, or userspace-facing.",
        "Use search_local_kernel_api on the listed interfaces to locate declarations, callers, and example implementations when a local tree is available.",
        "Use search_kernel_docs with the subsystem name and interface names to collect the latest upstream semantics and constraints.",
        "Use fetch_upstream_kernel_file on the matching upstream file when you need to compare your local tree with the latest mainline pattern.",
        "Read neighboring source files with read_local_kernel_file to copy the version-appropriate calling pattern from the local tree.",
        "Draft the change against the local tree first, then compare with online latest docs or code when behavior may have changed upstream.",
        "Verify build dependencies, Kconfig symbols, headers, locking context, error paths, and probe/remove or init/exit symmetry.",
    ]
    return {"task": task, "interfaces": interfaces, "implementation_plan": steps}


@mcp.tool()
def list_driver_template_blueprints_tool() -> dict[str, Any]:
    """List supported Linux driver subsystem blueprints.

    The result is designed as an index of future generation capabilities. Each
    entry describes what the MCP knows about a subsystem family before any code
    is emitted.
    """

    blueprints = list_driver_template_blueprints()
    return {
        "count": len(blueprints),
        "blueprints": [_serialize_blueprint(blueprint) for blueprint in blueprints],
    }


@mcp.tool()
def get_driver_template_blueprint_tool(subsystem: str) -> dict[str, Any]:
    """Return the blueprint metadata for a specific Linux driver subsystem."""

    blueprint = get_driver_template_blueprint(subsystem)
    if blueprint is None:
        return {"error": f"Unsupported driver subsystem: {subsystem}"}
    return _serialize_blueprint(blueprint)


@mcp.tool()
def plan_driver_scaffold(
    subsystem: str,
    driver_name: str,
    kernel_version: str,
) -> dict[str, Any]:
    """Plan a future version-aware Linux driver scaffold.

    Args:
        subsystem: Driver family such as ``platform``, ``i2c``, or ``spi``.
        driver_name: Basename for the driver source file.
        kernel_version: Target kernel version or BSP release identifier.

    Returns:
        A structured scaffold plan that future Codex prompts or code generators
        can consume. The plan highlights version-sensitive checks rather than
        pretending generation is safe without local validation.
    """

    plan = build_driver_scaffold_plan(
        subsystem=subsystem,
        driver_name=driver_name,
        kernel_version=kernel_version,
    )
    if plan is None:
        return {"error": f"Unsupported driver subsystem: {subsystem}"}
    return _serialize_scaffold_plan(plan)


def main() -> None:
    """Run the FastMCP server over the configured transport."""

    mcp.run()


if __name__ == "__main__":
    main()
