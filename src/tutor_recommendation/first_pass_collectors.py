from __future__ import annotations

from collections.abc import Callable

from .teacher_match_targets import TARGETS


def _build_configured_target(target_key: str) -> None:
    from . import first_pass_research

    if target_key not in first_pass_research.TARGETS:
        raise SystemExit(f"Target {target_key!r} is not implemented in the first-pass collector yet.")
    first_pass_research.build_target(first_pass_research.TARGETS[target_key])


TARGET_BUILDERS: dict[str, Callable[[], None]] = {
    "sjtu_cs": lambda: _build_configured_target("sjtu_cs"),
    "sjtu_ai": lambda: _build_configured_target("sjtu_ai"),
    "nju_cs": lambda: _build_configured_target("nju_cs"),
    "nju_ai": lambda: _build_configured_target("nju_ai"),
    "ruc_gsai": lambda: _build_configured_target("ruc_gsai"),
    "ruc_ssai": lambda: _build_configured_target("ruc_ssai"),
    "ruc_info": lambda: _build_configured_target("ruc_info"),
    "ruc_isbd": lambda: _build_configured_target("ruc_isbd"),
    "nju_ra": lambda: _build_configured_target("nju_ra"),
    "nju_is": lambda: _build_configured_target("nju_is"),
    "nju_ic": lambda: _build_configured_target("nju_ic"),
    "fudan_ciram": lambda: _build_configured_target("fudan_ciram"),
    "fudan_ai": lambda: _build_configured_target("fudan_ai"),
    "seu_cse": lambda: _build_configured_target("seu_cse"),
    "seu_software": lambda: _build_configured_target("seu_software"),
    "seu_ai": lambda: _build_configured_target("seu_ai"),
    "tongji_cs": lambda: _build_configured_target("tongji_cs"),
    "tongji_see": lambda: _build_configured_target("tongji_see"),
    "zju_cs": lambda: _build_configured_target("zju_cs"),
    "zju_ai": lambda: _build_configured_target("zju_ai"),
    "ustc_ai_ds": lambda: _build_configured_target("ustc_ai_ds"),
    "zju_uiuc": lambda: _build_configured_target("zju_uiuc"),
    "zju_cse": lambda: _build_configured_target("zju_cse"),
}

if set(TARGET_BUILDERS) != set(TARGETS):
    missing = sorted(set(TARGETS) - set(TARGET_BUILDERS))
    extra = sorted(set(TARGET_BUILDERS) - set(TARGETS))
    raise RuntimeError(f"first-pass builder registry mismatch: missing={missing}, extra={extra}")


def build_target(target_key: str) -> None:
    try:
        builder = TARGET_BUILDERS[target_key]
    except KeyError as exc:
        raise SystemExit(f"Unknown target {target_key!r}. Available: {', '.join(TARGETS)}") from exc
    builder()


def build_targets(target_keys: list[str]) -> None:
    from . import first_pass_research

    configs = []
    for target_key in target_keys:
        if target_key not in first_pass_research.TARGETS:
            raise SystemExit(f"Target {target_key!r} is not implemented in the first-pass collector yet.")
        configs.append(first_pass_research.TARGETS[target_key])

    rows_by_target = {config.key: first_pass_research.fetch_target_rows(config) for config in configs}
    rows_by_target = first_pass_research.deduplicate_targets_rows(rows_by_target, configs)
    for config in configs:
        first_pass_research.build_workbook(config, rows_by_target[config.key])
