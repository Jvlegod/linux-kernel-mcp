"""Subsystem template registry for future Linux driver generation.

Today this module returns structured guidance rather than emitting C code.
That is deliberate: the first requirement is to preserve subsystem knowledge in
an inspectable form that Codex can query and later feed into generation.
"""

from __future__ import annotations

from .models import DriverScaffoldPlan, DriverTemplateBlueprint

_TEMPLATE_REGISTRY: dict[str, DriverTemplateBlueprint] = {
    "platform": DriverTemplateBlueprint(
        subsystem="platform",
        template_id="platform_basic",
        summary="Generic platform_driver skeleton for MMIO, IRQ, clock, reset, and DT-backed devices.",
        supported_bus_types=["platform"],
        target_directories=["drivers/misc", "drivers/soc", "drivers/clk", "drivers/watchdog"],
        required_source_files=["drivers/<subsystem>/<driver>.c", "drivers/<subsystem>/Kconfig", "drivers/<subsystem>/Makefile"],
        common_headers=["linux/module.h", "linux/platform_device.h", "linux/of.h", "linux/mod_devicetable.h"],
        required_kconfig_symbols=["OF", "HAS_IOMEM"],
        typical_probe_flow=[
            "Match against of_device_id and module device table.",
            "Allocate driver-private state with devm helpers.",
            "Map MMIO resources and optional IRQ lines.",
            "Acquire clocks, resets, regulators, or GPIOs needed by hardware.",
            "Register subsystem-specific child objects before returning success.",
        ],
        dts_required=True,
        example_search_terms=["module_platform_driver", "of_match_table", "devm_platform_ioremap_resource"],
        prompt_hints=[
            "Prefer devm-managed resources unless the local subsystem pattern shows otherwise.",
            "Keep probe/remove symmetry aligned with the local kernel version.",
        ],
        extensibility_notes=[
            "Split this into MMIO-only and IRQ-heavy variants if generation prompts start diverging.",
            "Attach kernel-version-specific compatibility rules for probe helpers as the registry grows.",
        ],
    ),
    "i2c": DriverTemplateBlueprint(
        subsystem="i2c",
        template_id="i2c_client_basic",
        summary="I2C client driver skeleton for DT or ID-table matched devices.",
        supported_bus_types=["i2c"],
        target_directories=["drivers/i2c", "drivers/hwmon", "drivers/input", "drivers/misc"],
        required_source_files=["drivers/<subsystem>/<driver>.c", "drivers/<subsystem>/Kconfig", "drivers/<subsystem>/Makefile"],
        common_headers=["linux/module.h", "linux/i2c.h", "linux/of.h", "linux/mod_devicetable.h"],
        required_kconfig_symbols=["I2C"],
        typical_probe_flow=[
            "Provide i2c_device_id and optional of_device_id tables.",
            "Validate bus functionality before register access.",
            "Initialize register map or low-level transfer helpers.",
            "Register the subsystem-facing interface exposed by the device.",
        ],
        dts_required=True,
        example_search_terms=["module_i2c_driver", "i2c_check_functionality", "of_match_ptr"],
        prompt_hints=[
            "Prefer regmap when the local tree already uses it for the device family.",
            "Check whether remove callback is void or int in the target kernel branch.",
        ],
        extensibility_notes=[
            "Add SMBus-only variants if probe logic needs narrower transfer assumptions.",
        ],
    ),
    "spi": DriverTemplateBlueprint(
        subsystem="spi",
        template_id="spi_device_basic",
        summary="SPI device driver skeleton for controller-attached peripherals.",
        supported_bus_types=["spi"],
        target_directories=["drivers/spi", "drivers/iio", "drivers/input", "drivers/misc"],
        required_source_files=["drivers/<subsystem>/<driver>.c", "drivers/<subsystem>/Kconfig", "drivers/<subsystem>/Makefile"],
        common_headers=["linux/module.h", "linux/spi/spi.h", "linux/of.h", "linux/mod_devicetable.h"],
        required_kconfig_symbols=["SPI"],
        typical_probe_flow=[
            "Provide spi_device_id and optional of_device_id tables.",
            "Configure mode, bits-per-word, and max frequency if required.",
            "Initialize register access helpers and optional IRQ handling.",
            "Register the subsystem-facing interface after hardware sanity checks.",
        ],
        dts_required=True,
        example_search_terms=["module_spi_driver", "spi_sync", "devm_request_threaded_irq"],
        prompt_hints=[
            "Confirm whether the local subsystem prefers direct SPI transfers or regmap-backed access.",
        ],
        extensibility_notes=[
            "Add controller-driver templates separately; peripheral-driver assumptions differ.",
        ],
    ),
}


def list_driver_template_blueprints() -> list[DriverTemplateBlueprint]:
    """Return all known driver-template blueprints.

    The registry is intentionally explicit instead of auto-discovered so the
    project can document supported subsystems clearly.
    """

    return list(_TEMPLATE_REGISTRY.values())


def get_driver_template_blueprint(subsystem: str) -> DriverTemplateBlueprint | None:
    """Return the blueprint for a subsystem key, if available."""

    return _TEMPLATE_REGISTRY.get(subsystem.strip().lower())


def build_driver_scaffold_plan(
    subsystem: str,
    driver_name: str,
    kernel_version: str,
) -> DriverScaffoldPlan | None:
    """Build a version-aware scaffold plan for a Linux driver family.

    This does not generate source code yet. It packages the subsystem blueprint
    and a few version-sensitive heuristics into a result shape that a future
    code generator or prompt composer can consume.
    """

    blueprint = get_driver_template_blueprint(subsystem)
    if blueprint is None:
        return None

    compatibility_notes = [
        f"Validate helper signatures against kernel {kernel_version} before emitting code.",
        "Check local-tree examples first; downstream BSP kernels often diverge from mainline helper usage.",
    ]
    if subsystem in {"i2c", "spi"}:
        compatibility_notes.append(
            "Verify whether remove callbacks return int or void in the target tree. This changed across kernel eras."
        )
    if subsystem == "platform":
        compatibility_notes.append(
            "Confirm whether devm_platform_ioremap_resource() exists in the target branch or if open-coded mapping is needed."
        )

    local_research_steps = [
        f"Search the local tree for module registration helpers related to {subsystem} drivers.",
        f"Read at least two in-tree {subsystem} drivers near the target hardware domain before generating code.",
        "Inspect local Kconfig and Makefile placement under the intended driver directory.",
        "Check DTS binding and compatible string conventions used by sibling drivers.",
    ]

    generated_file_names = [f"{driver_name}.c"]
    required_updates = ["Kconfig", "Makefile"]
    if blueprint.dts_required:
        required_updates.append("Device Tree source (.dts/.dtsi)")

    return DriverScaffoldPlan(
        driver_name=driver_name,
        subsystem=blueprint.subsystem,
        kernel_version=kernel_version,
        template_id=blueprint.template_id,
        recommended_target_directory=blueprint.target_directories[0],
        generated_file_names=generated_file_names,
        required_updates=required_updates,
        compatibility_notes=compatibility_notes,
        local_research_steps=local_research_steps,
        prompt_hints=blueprint.prompt_hints,
    )
