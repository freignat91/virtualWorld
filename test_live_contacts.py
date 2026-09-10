"""Contrats transport et client sans demarrer Flask ni installer Node."""

import ast
from dataclasses import asdict
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from events import SonarPinged


ROOT = Path(__file__).resolve().parent
JS = (ROOT / "static/game.js").read_text()
SERVER = ast.parse((ROOT / "server.py").read_text())


class LiveContactsTest(unittest.TestCase):
    def test_ping_dispatch_preserves_xyz_and_meter_ranges(self) -> None:
        function = next(n for n in SERVER.body
                        if isinstance(n, ast.FunctionDef) and n.name == "_dispatch_sonar_pinged")
        sent = []
        namespace = {"_emit_one": lambda *args: sent.append(args)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "server.py", "exec"), namespace)
        event = SonarPinged(player_id="sub", x=12, y=-17.5, z=25, range_m=8000, reveal_m=15000)
        self.assertEqual(-17.5, asdict(event)["y"])
        namespace[function.name](event)
        self.assertEqual([("sonar_pinged", {
            "id": "sub", "x": 12, "y": -17.5, "z": 25,
            "coneDeg": 360, "rotation": 0, "range": 8000, "reveal": 15000,
        })], sent)
        human = next(n for n in SERVER.body
                     if isinstance(n, ast.FunctionDef) and n.name == "handle_sonar_ping")
        payload = next(n.args[1] for n in ast.walk(human)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id == "emit" and n.args[0].value == "sonar_pinged")
        values = {k.value: ast.unparse(v) for k, v in zip(payload.keys, payload.values)}
        self.assertEqual("float((p.get('position') or {}).get('y', 0))", values["y"])
        self.assertEqual(("range_m", "reveal_m"), (values["range"], values["reveal"]))

    def test_client_source_contracts(self) -> None:
        def body(name: str) -> str:
            return re.search(r"^function " + name + r"\([\s\S]*?^}", JS, re.M)[0]

        received = JS.split('socket.on("sonar_pinged", (data) => {', 1)[1].split('\n});', 1)[0]
        self.assertEqual(1, received.count("metersToUnits(data.range)"))
        self.assertEqual(1, received.count("metersToUnits(data.reveal)"))
        self.assertIn("const pingRange = range ?? revealRange ?? Infinity", received)
        self.assertIn("isLineOfSightClearBetween(data.x, data.z", received)
        self.assertIn("range: rangeUnits", body("triggerSonarPing"))
        self.assertIn("rangeMeters: rangeUnits * UNIT_METERS", body("triggerSonarPing"))
        self.assertNotIn("metersToUnits(ping.range)", body("pingRangeUnits"))
        self.assertNotIn("metersToUnits(ping.reveal)", body("pingRevealUnits"))
        self.assertIn("r && isTorpedoRadarVisible(r)", body("updateRadarTooltip"))
        self.assertIn("t && isTorpedoRadarVisible(t)", body("fireTorpedo"))
        self.assertIn("addTorpedoTrail(r, torpVisible);", body("updateRemoteTorpedoes"))
        self.assertNotIn("if (torpVisible) addTorpedoTrail", JS)
        self.assertIn("if (visible &&", body("addTorpedoTrail"))
        self.assertNotIn("cur.visual || cur.sonar", body("renderRadar"))
        self.assertIn("remembered: true", body("renderRadar"))
        for name in ("toggleGrenadeAiming", "fireGrenadeSalve", "fireTorpedo"):
            self.assertIn("selectedBoatContact()", body(name))
            self.assertNotIn("targetMesh.position", body(name))

    @unittest.skipUnless(shutil.which("node"), "Node.js indisponible")
    def test_javascript_live_contacts(self) -> None:
        result = subprocess.run([shutil.which("node"), str(ROOT / "tests/test_live_contacts.js")],
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
