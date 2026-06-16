"""Typed models shared across linux-kernel-mcp tools.

The MCP protocol only requires tool handlers to return JSON-serializable data.
This module gives that data an explicit internal structure so the project can:

- keep tool responses consistent enough for future refactors
- expose meaningful Python API documentation from docstrings and types
- reuse driver-template metadata across multiple MCP tools
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LineSnippet:
    """One line of source or document text.

    Attributes:
        line: One-based line number in the source snippet.
        text: Raw line text.
    """

    line: int
    text: str


@dataclass(slots=True)
class SearchMatch:
    """A single ripgrep-style search result.

    Attributes:
        file: Absolute path of the matched file.
        line: One-based line number.
        column: One-based column number reported by ripgrep.
        text: Trimmed line text that matched.
    """

    file: str
    line: int
    column: int
    text: str


@dataclass(slots=True)
class DriverTemplateBlueprint:
    """Metadata describing a driver scaffold family.

    The blueprint is intentionally higher level than generated code. It records
    the structural expectations of a Linux driver subsystem so Codex can later
    turn the blueprint into a version-aware scaffold.

    Attributes:
        subsystem: Stable subsystem key, for example ``platform`` or ``i2c``.
        template_id: Internal blueprint identifier.
        summary: Short human-readable description.
        supported_bus_types: Bus or attachment models expected by this template.
        target_directories: Typical kernel directories for generated source.
        required_source_files: Files usually touched when landing a new driver.
        common_headers: Headers commonly needed for the subsystem skeleton.
        required_kconfig_symbols: Kconfig symbols usually involved.
        typical_probe_flow: Ordered checklist of probe-time tasks.
        dts_required: Whether a Device Tree node is usually required.
        example_search_terms: Suggested local or upstream searches.
        prompt_hints: Guidance for future prompt-driven code generation.
        extensibility_notes: Notes for evolving the template registry.
    """

    subsystem: str
    template_id: str
    summary: str
    supported_bus_types: list[str]
    target_directories: list[str]
    required_source_files: list[str]
    common_headers: list[str]
    required_kconfig_symbols: list[str]
    typical_probe_flow: list[str]
    dts_required: bool
    example_search_terms: list[str]
    prompt_hints: list[str]
    extensibility_notes: list[str]


@dataclass(slots=True)
class DriverScaffoldPlan:
    """Plan returned for future driver-code generation workflows.

    Attributes:
        driver_name: Requested driver basename.
        subsystem: Target Linux driver subsystem.
        kernel_version: Kernel version string supplied by the caller.
        template_id: Blueprint chosen for the scaffold.
        recommended_target_directory: Preferred source directory.
        generated_file_names: Files a future generator would likely create.
        required_updates: Existing files that usually need edits.
        compatibility_notes: Version-sensitive notes gathered from heuristics.
        local_research_steps: Local-tree lookups to perform before generation.
        prompt_hints: Prompt fragments useful for Codex-driven generation.
    """

    driver_name: str
    subsystem: str
    kernel_version: str
    template_id: str
    recommended_target_directory: str
    generated_file_names: list[str]
    required_updates: list[str]
    compatibility_notes: list[str]
    local_research_steps: list[str]
    prompt_hints: list[str]
