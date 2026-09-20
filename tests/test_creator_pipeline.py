import importlib.util
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "creator_pipeline" / "creator_pipeline.py"
spec = importlib.util.spec_from_file_location("creator_pipeline", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class CreatorPipelineTests(unittest.TestCase):
    def test_token_resolution(self):
        ctx={"workdir":"/tmp/x","stage.out":"/tmp/x/a.json"}
        self.assertEqual(
            mod.resolve_string("{{workdir}}/{{stage.out}}",ctx),
            "/tmp/x//tmp/x/a.json",
        )

    def test_dry_run_registers_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            cfg={
                "variables":{"INPUT":"in.json"},
                "stages":[{
                    "id":"x",
                    "script":str(root/"fake.py"),
                    "args":["{{INPUT}}","{{workdir}}/out.json"],
                    "outputs":{"result":"{{workdir}}/out.json"}
                }],
                "compose":False,
            }
            report=mod.execute_pipeline(cfg,workdir=root/"work",dry_run=True)
            self.assertTrue(report["success"])
            self.assertEqual(report["stages"][0]["status"],"planned")
            self.assertIn("x.result",report["artifacts"])

    def test_executes_and_composes_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            writer=root/"writer.py"
            writer.write_text(textwrap.dedent(
                """
                import json,sys,pathlib
                out=pathlib.Path(sys.argv[1])
                out.parent.mkdir(parents=True,exist_ok=True)
                out.write_text(json.dumps({
                    "format":"update-p5-ai-edit",
                    "version":1,
                    "steps":[
                        {"id":"save","tool":"kdenlive_save_project","arguments":{}}
                    ]
                }),encoding="utf-8")
                """
            ),encoding="utf-8")
            cfg={
                "title":"Test",
                "stages":[{
                    "id":"one",
                    "script":str(writer),
                    "args":["{{workdir}}/one.edit.json"],
                    "outputs":{"plan":"{{workdir}}/one.edit.json"},
                    "plan_output":"{{one.plan}}"
                }],
                "compose":{"output":"final.edit.json"}
            }
            report=mod.execute_pipeline(cfg,workdir=root/"work")
            self.assertTrue(report["success"])
            final=Path(report["final_plan"])
            self.assertTrue(final.exists())
            data=json.loads(final.read_text(encoding="utf-8"))
            self.assertEqual(data["format"],"update-p5-ai-edit")


if __name__=="__main__":
    unittest.main()
