"""Guard against Home Assistant OptionsFlowWithReload/update-listener conflict.

HA Core rejects config entries using both reload mechanisms when the options
flow submits. The old versions therefore showed "Unknown error occurred" for
all settings, independently of decimal formatting.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "house_climate_monitor"


class OptionsFlowRegressionTests(unittest.TestCase):
    def test_one_reload_mechanism_only(self):
        setup = (ROOT / "__init__.py").read_text(encoding="utf-8")
        flow = (ROOT / "config_flow.py").read_text(encoding="utf-8")
        self.assertIn("class HouseClimateOptionsFlow(config_entries.OptionsFlowWithReload):", flow)
        # HA 2026+ raises ValueError on options completion if both are present.
        self.assertNotIn("add_update_listener(", setup)
        self.assertNotIn("async_update_options(", setup)
        self.assertIn("async_on_unload(hass.bus.async_listen(", setup)

    def test_submitting_temperature_values_keeps_other_settings(self):
        # Exercise the actual _form implementation in isolation: no HA
        # installation or dependency stubs are needed for this unit test.
        src = ast.parse((ROOT / "config_flow.py").read_text(encoding="utf-8"))
        cls = next(n for n in src.body if isinstance(n, ast.ClassDef)
                   and n.name == "HouseClimateOptionsFlow")
        fn = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "_form")
        fn.decorator_list = []
        module = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(module)
        namespace = {"vol": SimpleNamespace(Schema=lambda schema: schema)}
        exec(compile(module, "config_flow.py", "exec"), namespace)
        class FakeOptions:
            config_entry = SimpleNamespace(options={
                "notify_entity": "notify.email_family",
                "humidity_high": 70,
                "temp_low_c": 17.5,
            })
            def async_create_entry(self, *, title, data):
                return {"title": title, "data": data}
            def async_show_form(self, *, step_id, data_schema):
                return {"step_id": step_id, "schema": data_schema}

        result = asyncio.run(namespace["_form"](
            FakeOptions(), "temperature", [],
            {"temp_low_c": 17.0, "temp_low_minutes": 15,
             "temp_recovery_c": 17.5, "temp_recovery_minutes": 10}))
        self.assertEqual(result["data"]["temp_low_c"], 17.0)
        self.assertEqual(result["data"]["temp_recovery_c"], 17.5)
        self.assertEqual(result["data"]["humidity_high"], 70)
        self.assertEqual(result["data"]["notify_entity"], "notify.email_family")

    def test_all_options_sections_use_common_save_flow(self):
        src = ast.parse((ROOT / "config_flow.py").read_text(encoding="utf-8"))
        cls = next(n for n in src.body if isinstance(n, ast.ClassDef)
                   and n.name == "HouseClimateOptionsFlow")
        pages = [n for n in cls.body if isinstance(n, ast.AsyncFunctionDef)
                 and n.name.startswith("async_step_") and n.name != "async_step_init"]
        self.assertGreaterEqual(len(pages), 6)
        for step in pages:
            self.assertTrue(any(isinstance(c, ast.Attribute) and c.attr == "_form"
                                for c in ast.walk(step)),
                            f"{step.name} does not use the shared save path")


if __name__ == "__main__":
    unittest.main()
