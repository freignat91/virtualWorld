"""Guidage capteur reel : perte, evitement local, reacquisition et tirages."""

import copy
import math
import unittest
from unittest.mock import patch

from rl.headless import HeadlessRunner


class TorpedoGuidanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scene()

    def scene(self) -> None:
        self.runner = HeadlessRunner(seed=73)
        self.world = self.runner.world
        self.world.update(islands=[], thermoclines=[])
        self.sim = self.runner.sim
        sid = self.runner.spawn_bot("destroyer", external_control=True,
                                    position=(0, 0), team_id="owner")
        target_sid = self.runner.spawn_bot("destroyer", external_control=True,
                                           position=(100, 30), team_id="enemy")
        self.target = self.sim.players[target_sid]
        self.target["position"]["y"] = -10.0
        self.target["speedRatio"] = 1.0
        self.assertTrue(self.sim.spawn_bot_torpedo(self.sim.bots[sid], self.target))
        self.t = next(iter(self.sim.torpedoes.values()))
        self.t.update(x=10.0, y=-2.0, z=0.0, dirX=1.0, dirZ=0.0,
                      activation=0, radarRange=500, radarHalfAngle=math.pi / 2,
                      minTurnRadius=2.0, speed=2.0, minNoise=0.01)
        self.sim.drain_events()

    def island(self, x: float = 50.1, width: float = 100.0) -> None:
        self.world["islands"] = [{"points": [
            {"x": px, "z": pz} for px, pz in
            ((x, -width), (x + 0.01, -width), (x + 0.01, width), (x, width))]}]

    def tick(self) -> None:
        self.runner._time += 0.05
        self.sim.update_server_torpedoes(0.05, self.world)

    def test_loss_holds_heading_and_depth_then_visible_reacquisition(self) -> None:
        original = copy.deepcopy(self.t)
        for kind in ("acoustic", "autonomous"):
            with self.subTest(kind=kind):
                self.t.clear()
                self.t.update(copy.deepcopy(original), kind=kind)
                self.world["islands"] = []
                self.tick()
                self.assertTrue(self.t["inAcquisition"])
                self.assertEqual(self.target["id"], self.t["acquiredBoatId"])
                self.assertLess(self.t["pitch"], 0)
                remembered = self.t["lastAcquiredPos"]
                heading = (self.t["dirX"], self.t["dirZ"])
                depth = self.t["y"]
                traveled = self.t["traveled"]
                max_range = self.t["maxRange"]
                self.island()
                for tick in range(1, 4):
                    self.tick()
                    self.assertAlmostEqual(traveled + tick * self.t["speed"] * 0.05,
                                           self.t["traveled"])
                    self.assertEqual(max_range, self.t["maxRange"])
                    self.assertFalse(self.t["inAcquisition"])
                    self.assertFalse(self.t["acquired"])
                    self.assertIsNone(self.t["lockedKey"])
                    self.assertIsNone(self.t["acquiredBoatId"])
                    self.assertEqual(remembered, self.t["lastAcquiredPos"])
                    self.assertAlmostEqual(heading[0], self.t["dirX"])
                    self.assertAlmostEqual(heading[1], self.t["dirZ"])
                    self.assertEqual(depth, self.t["y"])
                    self.assertEqual(0, self.t["pitch"])
                self.world["islands"] = []
                self.tick()
                self.assertTrue(self.t["inAcquisition"])
                self.assertLess(self.t["pitch"], 0)

    def test_hidden_motion_cannot_change_guidance_or_payload(self) -> None:
        for kind in ("acoustic", "autonomous"):
            for acquired in (False, True):
                with self.subTest(kind=kind, acquired=acquired):
                    self.scene()
                    self.t["kind"] = kind
                    if acquired:
                        self.tick()
                    baseline = copy.deepcopy(self.t)
                    self.island()
                    outcomes = []
                    for x, y, z in ((100, -10, 30), (200, -25, -30)):
                        self.t.clear()
                        self.t.update(copy.deepcopy(baseline))
                        self.target["position"] = dict(x=x, y=y, z=z)
                        self.runner._time = 1.0
                        self.sim.drain_events()
                        self.tick()
                        self.sim._emit_torpedo_state(self.t)
                        outcomes.append(copy.deepcopy((self.t, self.sim.drain_events())))
                        self.assertFalse(self.t["inAcquisition"])
                        self.assertEqual(baseline["y"], self.t["y"])
                    self.assertEqual(outcomes[0], outcomes[1])

    def test_local_avoidance_without_contact(self) -> None:
        for kind in ("acoustic", "autonomous"):
            with self.subTest(kind=kind):
                self.scene()
                self.t["kind"] = kind
                self.tick()
                self.island(12.1, 0.5)
                self.target["position"] = dict(x=100, y=-10, z=0)
                heading = self.t["dirZ"]
                depth = self.t["y"]
                self.tick()
                self.assertFalse(self.t["inAcquisition"])
                self.assertNotAlmostEqual(heading, self.t["dirZ"])
                self.assertEqual(depth, self.t["y"])
                self.assertIn(self.t, self.sim.torpedoes.values())

    def test_radar_and_acoustic_all_entity_los_branches(self) -> None:
        for entity in ("boat", "lure", "torp"):
            for tracking in (False, True):
                with self.subTest(entity=entity, tracking=tracking):
                    self.scene()
                    target = self.target
                    key = "radar:" + target["id"]
                    if entity != "boat":
                        self.sim.players.pop(target["sid"])
                        obj = dict(x=100, y=-2, z=0)
                        if entity == "lure":
                            obj.update(ownerId="enemy", lid=1, noise=100, expiresAt=100)
                            self.sim.lures[("enemy", 1)] = obj
                            key = "radar_lure:enemy:1"
                        else:
                            self.sim.torpedoes[("enemy", 1)] = obj
                            self.t["antiTorpedo"] = True
                            key = "radar_torp:enemy:1"
                    self.t["lockedKey"] = key if tracking else None
                    self.island()
                    self.assertIsNone(self.sim._pick_radar(self.t, self.world))
                    self.assertIsNone(self.sim._pick_acoustic(self.t)["pos"])
                    self.world["islands"] = []
                    self.assertEqual(key, self.sim._pick_radar(self.t, self.world)["key"])

    def test_payload_never_resolves_unacquired_live_id(self) -> None:
        self.t["initialTarget"] = None
        self.sim._emit_torpedo_state(self.t)
        event = self.sim.drain_events()[0]
        self.assertIsNone(event.target_x)
        self.assertIsNone(event.target_y)
        self.assertIsNone(event.target_z)

    def test_manual_wire_pitch_is_not_levelled_on_missing_contact(self) -> None:
        self.t.update(kind="wireGuided", pitch=-0.2, wireYaw=1)
        self.sim._active_wire[self.t["ownerPlayerId"]] = (self.t["ownerPlayerId"], self.t["tid"])
        self.island()
        depth = self.t["y"]
        self.tick()
        self.assertEqual(-0.2, self.t["pitch"])
        self.assertLess(self.t["y"], depth)
        self.assertNotEqual(0, self.t["dirZ"])

    def test_penetration_once_per_entity_per_pass_and_retry_next_pass(self) -> None:
        self.sim.players.clear()
        self.target["position"] = dict(x=100, y=-10, z=0)
        self.sim.players["enemy"] = self.target
        self.t.update(thermoclinePenetration=0.5, antiTorpedo=True,
                      lockedKey="radar:" + self.target["id"])
        self.sim.lures[("enemy", 1)] = dict(
            x=100, y=-10, z=0, ownerId="enemy", lid=1, noise=100, expiresAt=100)
        self.sim.torpedoes[("enemy", 1)] = dict(x=100, y=-10, z=0)
        for key in ("radar:" + self.target["id"], "radar_lure:enemy:1", "radar_torp:enemy:1"):
            with self.subTest(key=key):
                self.t["lockedKey"] = key
                with patch.object(self.runner.legacy, "count_thermoclines_crossed", return_value=1), \
                        patch("simulation.random.random", return_value=0.9) as roll:
                    self.assertIsNone(self.sim._pick_radar(self.t, self.world))
                    self.assertEqual(3, roll.call_count)
                    self.assertIsNone(self.sim._pick_radar(self.t, self.world))
                    self.assertEqual(6, roll.call_count)
                    roll.return_value = 0.1
                    self.assertIsNotNone(self.sim._pick_radar(self.t, self.world))
                    self.assertEqual(7, roll.call_count)


if __name__ == "__main__":
    unittest.main()
