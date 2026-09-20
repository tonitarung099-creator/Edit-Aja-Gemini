import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "capability_registry" / "capability_registry.py"
spec = importlib.util.spec_from_file_location("capability_registry", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class CapabilityRegistryTests(unittest.TestCase):
    def test_load_registry(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"registry.json"
            p.write_text(json.dumps({"capabilities":[]}),encoding="utf-8")
            got=mod.load_registry(p)
            self.assertEqual(got["capabilities"],[])

    def test_summary(self):
        items=[
            {"available":True,"optional":False},
            {"available":False,"optional":False},
            {"available":False,"optional":True},
        ]
        s=mod.summary(items)
        self.assertEqual(s["available"],1)
        self.assertEqual(s["missing_required"],1)
        self.assertEqual(s["missing_optional"],1)
        self.assertFalse(s["ready"])

    def test_inspect_script_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            script=root/"tool.py"
            script.write_text("print('ok')\n",encoding="utf-8")
            cap={
                "id":"x","name":"X","category":"test",
                "script":"tool.py","executables":[],"python_modules":[]
            }
            got=mod.inspect_capability(cap,root)
            self.assertTrue(got["available"])


if __name__=="__main__":
    unittest.main()
