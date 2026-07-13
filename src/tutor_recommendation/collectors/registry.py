from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any

from ..teacher_match_targets import TARGETS


# A plain function name resolves against the compatibility first-pass namespace.
# New collectors should use "package.module:function" so they can live in this package
# without making the legacy first-pass module larger.
COLLECTOR_BY_TARGET: dict[str, str] = {
    "sjtu_cs": "fetch_sjtu_cs_directory",
    "sjtu_ai": "fetch_sjtu_ai_directory",
    "nju_cs": "fetch_nju_cs_directory",
    "nju_ai": "fetch_nju_ai_directory",
    "ruc_gsai": "fetch_ruc_gsai_directory",
    "ruc_ssai": "fetch_ruc_ssai_directory",
    "ruc_info": "fetch_ruc_info_directory",
    "nju_ra": "fetch_nju_ra_directory",
    "nju_is": "fetch_nju_is_directory",
    "nju_ic": "fetch_nju_ic_directory",
    "fudan_ciram": "fetch_fudan_ciram_directory",
    "fudan_ai": "fetch_fudan_ai_directory",
    "seu_cse": "fetch_seu_directory",
    "seu_software": "fetch_seu_directory",
    "seu_ai": "fetch_seu_directory",
    "tongji_cs": "fetch_tongji_cs_directory",
    "tongji_see": "fetch_tongji_see_directory",
    "zju_cs": "fetch_zju_cs_directory",
    "zju_ai": "fetch_zju_ai_directory",
    "ustc_ai_ds": "fetch_ustc_ai_ds_directory",
    "zju_uiuc": "fetch_zju_uiuc_directory",
    "zju_cse": "fetch_zju_cse_directory",
}


def validate_registry() -> None:
    missing = sorted(set(TARGETS) - set(COLLECTOR_BY_TARGET))
    extra = sorted(set(COLLECTOR_BY_TARGET) - set(TARGETS))
    if missing or extra:
        raise RuntimeError(f"collector registry mismatch: missing={missing}, extra={extra}")


def resolve_collector(target_key: str, namespace: Mapping[str, Any]) -> Callable[..., list[dict[str, Any]]]:
    validate_registry()
    try:
        function_name = COLLECTOR_BY_TARGET[target_key]
    except KeyError as exc:
        raise KeyError(f"target {target_key!r} has no official-directory collector binding") from exc
    if ":" in function_name:
        module_name, attribute = function_name.split(":", 1)
        collector = getattr(import_module(module_name), attribute, None)
    else:
        collector = namespace.get(function_name)
    if not callable(collector):
        raise RuntimeError(f"collector {function_name!r} for target {target_key!r} is not implemented")
    return collector
