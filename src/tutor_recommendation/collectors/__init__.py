"""Official faculty-directory collector registry and school-specific implementations."""

from .registry import COLLECTOR_BY_TARGET, resolve_collector, validate_registry

__all__ = ["COLLECTOR_BY_TARGET", "resolve_collector", "validate_registry"]
