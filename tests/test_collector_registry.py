from __future__ import annotations

import unittest

from tutor_recommendation.collectors.registry import COLLECTOR_BY_TARGET, resolve_collector, validate_registry
from tutor_recommendation.teacher_match_targets import TARGETS


class CollectorRegistryTests(unittest.TestCase):
    def test_every_target_has_explicit_collector_binding(self) -> None:
        validate_registry()
        self.assertEqual(set(COLLECTOR_BY_TARGET), set(TARGETS))

    def test_resolve_collector_rejects_missing_implementation(self) -> None:
        with self.assertRaises(RuntimeError):
            resolve_collector("sjtu_cs", {})

    def test_new_collector_can_use_module_function_binding(self) -> None:
        original = COLLECTOR_BY_TARGET["sjtu_cs"]
        try:
            COLLECTOR_BY_TARGET["sjtu_cs"] = "tutor_recommendation.collectors.registry:validate_registry"
            self.assertIs(resolve_collector("sjtu_cs", {}), validate_registry)
        finally:
            COLLECTOR_BY_TARGET["sjtu_cs"] = original


if __name__ == "__main__":
    unittest.main()
