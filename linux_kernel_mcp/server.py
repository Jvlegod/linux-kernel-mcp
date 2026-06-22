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

    cmd = ["rg", "-n", "--column", "--no-heading", "--color", "never", "-m", str(limit), pattern, str(root)]
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


def _path_for_response(path: Path, root: Path) -> str:
    """Return a root-relative path when possible."""

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _read_kernel_makefile_version(root: Path) -> dict[str, Any]:
    """Extract VERSION/PATCHLEVEL/SUBLEVEL/EXTRAVERSION from the kernel Makefile."""

    makefile = root / "Makefile"
    if not makefile.exists():
        return {"error": f"Kernel Makefile not found: {makefile}"}

    values: dict[str, str] = {}
    for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)\s*=\s*(.*)$", line)
        if match:
            values[match.group(1).lower()] = match.group(2).strip()

    version = values.get("version")
    patchlevel = values.get("patchlevel")
    sublevel = values.get("sublevel")
    extraversion = values.get("extraversion", "")
    release = root / "include" / "config" / "kernel.release"
    local_release = None
    if release.exists():
        local_release = release.read_text(encoding="utf-8", errors="replace").strip()

    parsed = ".".join(part for part in [version, patchlevel, sublevel] if part is not None)
    if extraversion:
        parsed = f"{parsed}{extraversion}"

    return {
        "version": version,
        "patchlevel": patchlevel,
        "sublevel": sublevel,
        "extraversion": extraversion,
        "makefile_release": parsed or None,
        "configured_release": local_release,
    }


def _rg_matches(pattern: str, root: Path, glob: str | None = None, limit: int = 20) -> list[SearchMatch]:
    """Return normalized ripgrep matches, raising no exception on no-match."""

    result = _run_rg(pattern=pattern, root=root, glob=glob, limit=limit)
    return [SearchMatch(**match) for match in result.get("matches", [])]


def _first_match(pattern: str, root: Path, glob: str | None = None) -> SearchMatch | None:
    """Return the first ripgrep match for a pattern."""

    matches = _rg_matches(pattern=pattern, root=root, glob=glob, limit=1)
    return matches[0] if matches else None


def _api_presence(root: Path, name: str) -> dict[str, Any]:
    """Detect whether a symbol exists in the selected kernel tree."""

    match = _first_match(rf"\b{re.escape(name)}\b", root=root, glob="*.{c,h}")
    if match is None:
        return {"available": False}
    return {
        "available": True,
        "file": _path_for_response(Path(match.file), root),
        "line": match.line,
        "text": match.text,
    }


def _struct_callback_signature(root: Path, struct_name: str, callback: str) -> dict[str, Any]:
    """Find a callback field inside a kernel struct declaration."""

    struct_match = _first_match(rf"struct\s+{re.escape(struct_name)}\s*\{{", root=root, glob="include/linux/*.h")
    if struct_match is None:
        struct_match = _first_match(rf"struct\s+{re.escape(struct_name)}\s*\{{", root=root, glob="**/*.h")
    if struct_match is None:
        return {"available": False, "note": f"struct {struct_name} not found"}

    header_path = Path(struct_match.file)
    lines = header_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(0, struct_match.line - 1)
    for idx in range(start, min(len(lines), start + 220)):
        line = lines[idx].strip()
        if re.search(rf"\(\*{re.escape(callback)}\)\s*\(", line):
            return {
                "available": True,
                "file": _path_for_response(header_path, root),
                "line": idx + 1,
                "signature": line,
                "returns_int": line.startswith("int "),
                "returns_void": line.startswith("void "),
            }
        if idx > start and line.startswith("};"):
            break
    return {
        "available": False,
        "file": _path_for_response(header_path, root),
        "note": f"{callback} callback not found in struct {struct_name}",
    }


def _rg_file_list(patterns: list[str], root: Path, glob: str, limit: int = 200) -> set[Path]:
    """Return files matching any pattern."""

    files: set[Path] = set()
    for pattern in patterns:
        cmd = ["rg", "-l", "--color", "never", "-g", glob, pattern, "."]
        try:
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return files
        if proc.returncode not in (0, 1):
            continue
        for line in proc.stdout.splitlines():
            files.add((root / line).resolve())
            if len(files) >= limit:
                return files
    return files


def _driver_example_search_profile(subsystem: str) -> dict[str, Any] | None:
    """Return directory and registration-helper hints for a driver subsystem."""

    profiles: dict[str, dict[str, Any]] = {
        "platform": {
            "globs": ["drivers/**/*.c"],
            "helpers": ["module_platform_driver", "platform_driver_register", "struct platform_driver"],
        },
        "i2c": {
            "globs": ["drivers/**/*.c"],
            "helpers": ["module_i2c_driver", "i2c_add_driver", "struct i2c_driver"],
        },
        "spi": {
            "globs": ["drivers/**/*.c"],
            "helpers": ["module_spi_driver", "spi_register_driver", "struct spi_driver"],
        },
        "gpio": {
            "globs": ["drivers/gpio/**/*.c", "drivers/**/*.c"],
            "helpers": ["struct gpio_chip", "devm_gpiochip_add_data", "gpiochip_add_data"],
        },
        "pwm": {
            "globs": ["drivers/pwm/**/*.c", "drivers/**/*.c"],
            "helpers": ["struct pwm_chip", "pwmchip_add", "devm_pwmchip_add"],
        },
        "input": {
            "globs": ["drivers/input/**/*.c", "drivers/**/*.c"],
            "helpers": ["input_register_device", "devm_input_allocate_device"],
        },
        "leds": {
            "globs": ["drivers/leds/**/*.c", "drivers/**/*.c"],
            "helpers": ["led_classdev_register", "devm_led_classdev_register"],
        },
        "watchdog": {
            "globs": ["drivers/watchdog/**/*.c", "drivers/**/*.c"],
            "helpers": ["watchdog_register_device", "devm_watchdog_register_device"],
        },
        "iio": {
            "globs": ["drivers/iio/**/*.c", "drivers/**/*.c"],
            "helpers": ["iio_device_register", "devm_iio_device_register"],
        },
        "misc": {
            "globs": ["drivers/misc/**/*.c", "drivers/**/*.c"],
            "helpers": ["misc_register", "struct miscdevice"],
        },
    }
    return profiles.get(subsystem.strip().lower())


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
def inspect_kernel_capabilities(root: str | None = None) -> dict[str, Any]:
    """Inspect local kernel version and driver-facing API capabilities.

    This tool reads the selected local kernel tree and reports version metadata,
    common helper availability, and callback signatures that affect generated
    driver code.
    """

    search_root = _require_kernel_root(root)
    if search_root is None:
        return _missing_kernel_root_error()
    if not search_root.exists():
        return {"error": f"Local kernel tree not found: {search_root}"}

    callback_signatures = {
        "platform_driver.remove": _struct_callback_signature(search_root, "platform_driver", "remove"),
        "i2c_driver.remove": _struct_callback_signature(search_root, "i2c_driver", "remove"),
        "spi_driver.remove": _struct_callback_signature(search_root, "spi_driver", "remove"),
        "spi_driver.probe": _struct_callback_signature(search_root, "spi_driver", "probe"),
    }
    helper_names = [
        "devm_platform_ioremap_resource",
        "devm_platform_get_and_ioremap_resource",
        "devm_request_threaded_irq",
        "devm_clk_get_enabled",
        "devm_reset_control_get_optional_exclusive",
        "devm_regulator_get_enable",
        "devm_gpiod_get",
        "gpiod_set_value_cansleep",
        "devm_ioremap_resource",
        "module_platform_driver",
        "module_i2c_driver",
        "module_spi_driver",
        "of_match_ptr",
    ]

    config_files = {
        "generated_autoconf": (search_root / "include" / "generated" / "autoconf.h").exists(),
        "legacy_autoconf": (search_root / "include" / "linux" / "autoconf.h").exists(),
        "kernel_release": (search_root / "include" / "config" / "kernel.release").exists(),
    }

    return {
        "root": str(search_root),
        "kernel_version": _read_kernel_makefile_version(search_root),
        "config_files": config_files,
        "helpers": {name: _api_presence(search_root, name) for name in helper_names},
        "callback_signatures": callback_signatures,
        "notes": [
            "Use callback_signatures to decide probe/remove prototypes before generating code.",
            "Use helpers availability to avoid emitting APIs missing from older BSP kernels.",
        ],
    }


@mcp.tool()
def find_driver_examples(
    subsystem: str,
    keywords: list[str] | None = None,
    root: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Find similar in-tree driver examples for a subsystem and keyword set.

    Args:
        subsystem: Driver family such as platform, i2c, spi, gpio, pwm, input,
            leds, watchdog, iio, or misc.
        keywords: Optional terms to prefer, for example vendor names, compatible
            fragments, IP block names, or helper APIs.
        root: Optional one-call kernel root override.
        limit: Maximum number of examples to return.

    Returns:
        Ranked local source files with matched helpers, keywords, and useful
        nearby lines for reading before writing a new driver.
    """

    search_root = _require_kernel_root(root)
    if search_root is None:
        return _missing_kernel_root_error()
    if not search_root.exists():
        return {"error": f"Local kernel tree not found: {search_root}"}

    profile = _driver_example_search_profile(subsystem)
    if profile is None:
        return {
            "error": f"Unsupported driver subsystem: {subsystem}",
            "supported_subsystems": ["platform", "i2c", "spi", "gpio", "pwm", "input", "leds", "watchdog", "iio", "misc"],
        }

    normalized_keywords = [kw.strip() for kw in (keywords or []) if kw.strip()]
    candidate_files: set[Path] = set()
    for glob in profile["globs"]:
        candidate_files.update(_rg_file_list(profile["helpers"], search_root, glob=glob, limit=300))
        if normalized_keywords:
            candidate_files.update(_rg_file_list(normalized_keywords, search_root, glob=glob, limit=300))

    examples: list[dict[str, Any]] = []
    for path in candidate_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matched_helpers = [helper for helper in profile["helpers"] if re.search(re.escape(helper), text)]
        matched_keywords = [kw for kw in normalized_keywords if re.search(re.escape(kw), text, re.IGNORECASE)]
        if not matched_helpers and not matched_keywords:
            continue

        score = (len(matched_helpers) * 10) + (len(matched_keywords) * 6)
        try:
            relative = path.relative_to(search_root)
        except ValueError:
            relative = path
        rel_text = str(relative)
        if rel_text.startswith(f"drivers/{subsystem}/"):
            score += 5
        if "imx" in rel_text.lower() or "fsl" in rel_text.lower() or "freescale" in text.lower():
            score += 3

        lines = text.splitlines()
        useful_lines: list[dict[str, Any]] = []
        markers = matched_helpers + matched_keywords
        for idx, line in enumerate(lines, start=1):
            if any(re.search(re.escape(marker), line, re.IGNORECASE) for marker in markers):
                useful_lines.append({"line": idx, "text": line.strip()})
            if len(useful_lines) >= 8:
                break

        examples.append(
            {
                "file": rel_text,
                "score": score,
                "matched_helpers": matched_helpers,
                "matched_keywords": matched_keywords,
                "useful_lines": useful_lines,
            }
        )

    examples.sort(key=lambda item: (-item["score"], item["file"]))
    max_examples = max(1, limit)
    return {
        "root": str(search_root),
        "subsystem": subsystem.strip().lower(),
        "keywords": normalized_keywords,
        "count": min(len(examples), max_examples),
        "examples": examples[:max_examples],
        "notes": [
            "Read the highest-scoring examples before generating a new driver.",
            "Prefer examples from the same target BSP over latest upstream style when APIs differ.",
        ],
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
