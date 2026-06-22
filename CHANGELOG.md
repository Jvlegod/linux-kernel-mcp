# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows semantic versioning where practical.

## [Unreleased]

### Added

- Added release workflow validation and automatic version tagging for manually triggered package releases.
- Added `inspect_kernel_capabilities` for local Linux kernel trees. It reports kernel Makefile version metadata, generated config markers, common driver helper availability, and bus-driver callback signatures that affect BSP-specific driver code.
- Added `find_driver_examples` for finding similar in-tree driver examples by subsystem, helper usage, keywords, and i.MX/FSL/Freescale relevance.
- Documented the new local source-tree tools in `README.md`, `README.zh-CN.md`, and `docs/api.md`.

### Fixed

- Added `--column` to local `rg` searches so structured search results include the column field expected by the parser.
