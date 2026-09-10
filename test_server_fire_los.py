"""Vraies fonctions serveur extraites par AST, sans import Flask ni serveur live."""

import ast
import copy
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import simulation


class ServerFireLosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = ast.parse(Path(__file__).with_name("server.py").read_text())
        names = {"spawn_torpedo", "fire_cannon_intent", "boat_cannon_specs",
                 "hit_probability", "handle_torpedo_fire", "handle_cannon_fire"}
        functions = [node for node in source.body
                     if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in functions:
            node.decorator_list = []
        cls.code = compile(ast.Module(body=functions, type_ignores=[]), "server.py", "exec")

    def setUp(self) -> None:
        self.world = {"islands": [{"points": [{"x": x, "z": z} for x, z in
                      ((-30.2, -1), (-30.1, -1), (-30.1, 1), (-30.2, 1))]}]}
        self.sim = simulation.Sim(self.world)
        self.shooter = {"id": "human", "boatType": "destroyer",
                        "position": {"x": 0, "y": -0.2, "z": 0},
                        "boat": {"torpedoes": {k: {"count": 5} for k in
                                 ("acoustic", "autonomous", "wireGuided")},
                                 "cannon": {"ammunition": 5}, "antiAircraft": {"ammunition": 5}}}
        self.position = {"x": -60, "y": -0.2, "z": 0}
        self.target = {"id": "enemy", "position": self.position}
        self.io = Mock()
        self.ns = {"sim": self.sim, "players": {"sid": self.shooter, "enemy": self.target},
                   "bots": {}, "torpedoes_server": {}, "next_torpedo_tid": {},
                   "active_wire_torpedoes": {}, "torpedo_ammo": {"sid": {
                       k: 5 for k in ("acoustic", "autonomous", "wireGuided")}},
                   "cannon_ammo": {"sid": {"cannon": 5, "antiAircraft": 5}},
                   "drones_server": {("enemy", 1): self.position},
                   "sonar_beacons": {1: self.position},
                   "passive_sonar_beacons": {1: self.position},
                   "mines_server": {("enemy", 1): dict(self.position, kind="surface")},
                   "boat_torpedo_specs": simulation.boat_torpedo_specs,
                   "UNIT_METERS_BOT": simulation.UNIT_METERS_BOT,
                   "CANNON_SHELL_SPEED_MS": 500, "AA_BULLET_SPEED_MS": 800,
                   "socketio": self.io, "logging": logging,
                   "time": SimpleNamespace(time=lambda: 1.0),
                   "random": SimpleNamespace(random=lambda: 0.0),
                   "request": SimpleNamespace(sid="sid"),
                   "resolve_acting_sid": lambda sid, data: sid}
        for name in ("emit_torpedo_counts", "emit_torpedo_state_broadcast",
                     "notify_shooter_torpedo_status", "notify_torpedo_acquisition",
                     "emit_cannon_counts", "init_torpedo_ammo_for_sid", "init_cannon_ammo_for_sid"):
            self.ns[name] = getattr(self.io, name)
        exec(self.code, self.ns)
        self.sim._legacy = SimpleNamespace(**self.ns)
        self.sim.players = self.ns["players"]

    def state(self) -> dict:
        return copy.deepcopy({name: self.ns[name] for name in (
            "players", "torpedo_ammo", "cannon_ammo", "torpedoes_server",
            "next_torpedo_tid", "active_wire_torpedoes", "drones_server",
            "sonar_beacons", "passive_sonar_beacons", "mines_server")})

    def intents(self) -> list:
        return [("handle_torpedo_fire", {"kind": k, "targetId": "enemy", "antiTorpedo": anti})
                for k in ("acoustic", "autonomous", "wireGuided") for anti in (False, True)] + [
            ("handle_cannon_fire", {"kind": k, "targetType": t, "targetId": "enemy",
                                    "ownerId": "enemy", "did": 1, "mid": 1, "bid": 1})
            for k in ("cannon", "antiAircraft")
            for t in ("boat", "beacon", "passive_beacon", "mine", "drone")
            if t != "drone" or k == "antiAircraft"]

    def test_hidden_id_rejected_without_ammo_events_or_tasks(self) -> None:
        for handler, intent in self.intents():
            for x, z in ((-60, 0), (-30.1, 0), (-30.1, 1)):
                for initialized in (False, True):
                    with self.subTest(intent=intent, endpoint=(x, z), initialized=initialized):
                        self.setUp()
                        self.position.update(x=x, z=z)
                        self.ns["mines_server"][("enemy", 1)].update(x=x, z=z)
                        if not initialized:
                            self.ns["torpedo_ammo"].clear()
                            self.ns["cannon_ammo"].clear()
                        before = self.state()
                        self.ns[handler](intent | {"fixedTarget": {"x": -10, "z": 20}})
                        self.assertEqual(before, self.state())
                        self.assertEqual([], self.io.mock_calls)

    def test_visible_id_still_fires(self) -> None:
        for handler, intent in self.intents():
            with self.subTest(intent=intent):
                self.setUp()
                self.position["z"] = 20
                self.ns["mines_server"][("enemy", 1)]["z"] = 20
                before = self.state()
                self.ns[handler](intent)
                self.assertNotEqual(before, self.state())
                self.assertTrue(self.io.mock_calls)
                if handler == "handle_cannon_fire" and intent["kind"] == "antiAircraft":
                    self.io.start_background_task.assert_called_once()
                elif handler == "handle_cannon_fire":
                    self.io.start_background_task.assert_not_called()
                    self.assertEqual(1, len(self.sim.cannon_shells))

    def test_fixed_point_fire_stays_allowed_and_ignores_hidden_live_position(self) -> None:
        for kind in ("acoustic", "autonomous", "wireGuided"):
            for anti in (False, True):
                launches = []
                for x, y in ((-60, -0.2), (-200, -15)):
                    self.setUp()
                    self.position.update(x=x, y=y)
                    self.ns["handle_torpedo_fire"]({"kind": kind, "antiTorpedo": anti,
                                                   "fixedTarget": {"x": -60, "z": 0}})
                    launches.append(copy.deepcopy(self.ns["torpedoes_server"]))
                    torpedo = next(iter(launches[-1].values()))
                    self.assertEqual((-60, 0.0, 0), torpedo["initialTarget"])
                    self.assertIsNone(torpedo["targetId"])
                self.assertEqual(launches[0], launches[1])

    def test_unknown_id_does_not_fall_back_to_point_with_fake_alert(self) -> None:
        self.ns["handle_torpedo_fire"]({"kind": "acoustic", "targetId": "missing",
                                       "fixedTarget": {"x": -60, "z": 0}})
        self.assertFalse(self.ns["torpedoes_server"])
        self.assertEqual([], self.io.mock_calls)

    def test_blind_all_kinds_and_explicit_invalid_ids(self) -> None:
        for kind in ("acoustic", "autonomous", "wireGuided"):
            launches = []
            for x in (-60, -200):
                self.setUp()
                self.position["x"] = x
                self.ns["handle_torpedo_fire"]({"kind": kind})
                t = next(iter(self.ns["torpedoes_server"].values()))
                self.assertIsNone(t["initialTarget"])
                self.assertIsNone(t["targetId"])
                self.assertEqual((-1, 0, 0), (t["dirX"], t["dirZ"], t["pitch"]))
                self.assertEqual(4, self.ns["torpedo_ammo"]["sid"][kind])
                self.assertFalse(t["inAcquisition"])
                launches.append(copy.deepcopy(t))
                if kind == "wireGuided":
                    self.assertIn("human", self.ns["active_wire_torpedoes"])
                    self.ns["handle_torpedo_fire"]({"kind": kind})
                    self.assertEqual(1, len(self.ns["torpedoes_server"]))
            self.assertEqual(*launches)
            for invalid in ("missing", "", False, 0):
                self.setUp()
                before = self.state()
                self.ns["handle_torpedo_fire"]({"kind": kind, "targetId": invalid})
                self.assertEqual(before, self.state())
                self.assertEqual([], self.io.mock_calls)

    def test_human_launch_range_uses_actual_boat_specs(self) -> None:
        for boat_type in ("destroyer", "submarine"):
            boat = json.loads((Path(__file__).parent / "boats" / (boat_type + ".json")).read_text())
            for kind, spec in boat["torpedoes"].items():
                with self.subTest(boat_type=boat_type, kind=kind):
                    self.setUp()
                    self.shooter.update(boatType=boat_type, boat=boat)
                    self.ns["spawn_torpedo"]("sid", self.shooter, {
                        "kind": kind, "fixedTarget": {"x": -60, "z": 0}})
                    t = next(iter(self.ns["torpedoes_server"].values()))
                    self.assertEqual(spec["maxRangeMeters"] / 10, t["maxRange"])
                    self.assertEqual(0, t["traveled"])
                    self.assertAlmostEqual(spec["speed"] * 0.514444 / 10, t["speed"])

    def test_blind_wire_keeps_manual_steering_in_real_sim(self) -> None:
        import random
        from rl.headless import HeadlessRunner

        state = random.getstate()
        self.addCleanup(random.setstate, state)
        runner = HeadlessRunner(seed=73)
        runner.world.update(islands=[], thermoclines=[])
        self.ns["handle_torpedo_fire"]({"kind": "wireGuided"})
        t = next(iter(self.ns["torpedoes_server"].values()))
        key = (t["ownerPlayerId"], t["tid"])
        runner.sim.torpedoes[key] = t
        runner.sim._active_wire[t["ownerPlayerId"]] = key
        t.update(wireYaw=1, wirePitch=-1)
        runner.sim.update_server_torpedoes(0.1, runner.world)
        self.assertGreater(t["dirZ"], 0)
        self.assertLess(t["pitch"], 0)
        self.assertLess(t["y"], -0.3)
        self.assertIsNone(t["initialTarget"])
        self.assertIsNone(t["acquiredBoatId"])

    def test_blind_launch_uses_native_human_depth_and_activation(self) -> None:
        for boat_type in ("destroyer", "submarine"):
            boat = json.loads((Path(__file__).parent / "boats" / (boat_type + ".json")).read_text())
            for kind, spec in boat["torpedoes"].items():
                for activation in (None, 123.0):
                    self.setUp()
                    self.shooter.update(boatType=boat_type, boat=boat)
                    self.shooter["position"]["y"] = -12.0
                    self.ns["handle_torpedo_fire"]({"kind": kind, "targetId": None,
                                                   "activationMeters": activation})
                    t = next(iter(self.ns["torpedoes_server"].values()))
                    self.assertEqual(-0.3 if boat_type == "destroyer" else -12.0, t["y"])
                    self.assertEqual((spec["activation"] if activation is None else activation) / 10,
                                     t["activation"])
                    self.assertEqual(spec["maxRangeMeters"] / 10, t["maxRange"])
                    self.assertEqual(-1.5, t["x"])
                    self.assertIsNone(t["initialTarget"])


if __name__ == "__main__":
    unittest.main()
