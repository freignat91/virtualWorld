"""Sortie de carte autoritaire, sans serveur ni modele charge."""

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from autogame import AutogameEnd
from events import BoatSunk, SonarBeaconDestroyed, TorpedoDead, TorpedoExploded
from game_trace import GameTrace
import test_torpedo_range


class TorpedoBoundsTest(unittest.TestCase):
    def setUp(self) -> None:
        test_torpedo_range.TorpedoRangeTest.setUp(self)
        self.world["ground"] = dict(width=20, depth=12)
        self.t.update(speed=100, maxRange=0, traveled=0, activation=3000)
        self.key = (self.t["ownerPlayerId"], self.t["tid"])

    def dead(self) -> list:
        self.assertFalse(self.sim.torpedoes)
        self.assertNotIn(self.key[0], self.sim._active_wire)
        events = self.sim.drain_events()
        deaths = [e for e in events if isinstance(e, TorpedoDead)]
        self.assertEqual(1, len(deaths))
        self.assertEqual("map_bounds", deaths[0].reason)
        self.assertFalse(any(isinstance(e, TorpedoExploded) for e in events))
        self.sim.update_server_torpedoes(1, self.world)
        self.assertFalse(self.sim.drain_events())
        return events

    def test_four_edges_corners_all_kinds_large_steps_and_pitch(self) -> None:
        for kind in ("acoustic", "autonomous", "wireGuided"):
            for x, z in ((10, 0), (-10, 0), (0, 6), (0, -6),
                         (10, 6), (10, -6), (-10, 6), (-10, -6), (10, 3)):
                for pitch in (0, -0.3):
                    with self.subTest(kind=kind, x=x, z=z, pitch=pitch):
                        self.setUp()
                        length = math.hypot(x, z)
                        self.t.update(kind=kind, dirX=x / length, dirZ=z / length, pitch=pitch)
                        if kind == "wireGuided":
                            self.sim._active_wire[self.key[0]] = self.key
                        self.sim.update_server_torpedoes(100, self.world)
                        self.assertAlmostEqual(x, self.t["x"])
                        self.assertAlmostEqual(z, self.t["z"])
                        self.assertAlmostEqual(length / math.cos(pitch), self.t["traveled"])
                        self.assertAlmostEqual(-10 + math.tan(pitch) * length, self.t["y"])
                        self.dead()

    def test_boundary_inclusive_then_outward_or_inward(self) -> None:
        for direction in (-1, 1):
            self.setUp()
            self.t["speed"] = 10
            self.sim.update_server_torpedoes(1, self.world)
            self.assertIn(self.key, self.sim.torpedoes)
            self.assertEqual(10, self.t["x"])
            self.sim.drain_events()
            self.t["dirX"] = direction
            self.sim.update_server_torpedoes(0.1, self.world)
            if direction == 1:
                self.assertEqual(10, self.t["traveled"])
                self.dead()
            else:
                self.assertEqual(9, self.t["x"])
                self.assertIn(self.key, self.sim.torpedoes)

    def test_already_outside_purged_before_guidance_and_other_collisions(self) -> None:
        for kind in ("acoustic", "autonomous", "wireGuided"):
            self.setUp()
            self.t.update(kind=kind, x=10.01, dirX=-1, activation=0)
            self.sim._active_wire[self.key[0]] = self.key
            with patch.object(self.sim, "_pick_radar", side_effect=AssertionError), \
                 patch.object(self.sim, "_pick_acoustic", side_effect=AssertionError), \
                 patch("simulation.torpedo_avoid_island", side_effect=AssertionError):
                self.sim.update_server_torpedoes(1, self.world)
            self.assertEqual(10.01, self.t["x"])
            self.dead()

    def test_collisions_inside_and_at_edge_but_not_outside(self) -> None:
        for x, hit in ((5, True), (10, True), (10.01, False), (50, False)):
            with self.subTest(x=x):
                self.setUp()
                self.t.update(activation=0, kind="wireGuided")
                self.sim._active_wire[self.key[0]] = self.key
                self.sim.beacons[1] = dict(x=x, z=0)
                self.sim.update_server_torpedoes(1, self.world)
                if hit:
                    events = self.sim.drain_events()
                    self.assertTrue(any(isinstance(e, SonarBeaconDestroyed) for e in events))
                    self.assertEqual(x, self.t["x"])
                    self.assertEqual(1, sum(isinstance(e, TorpedoDead) for e in events))
                    self.assertFalse(self.sim.torpedoes)
                else:
                    self.dead()
                    self.assertIn(1, self.sim.beacons)

    def test_outside_boat_lure_mine_and_torpedo_cannot_trigger(self) -> None:
        for object_kind in ("boat", "lure", "mine", "torpedo"):
            with self.subTest(object_kind=object_kind):
                self.setUp()
                self.t.update(activation=0, kind="wireGuided", antiTorpedo=True)
                self.sim._active_wire[self.key[0]] = self.key
                obj = dict(x=10.01, y=-10, z=0)
                if object_kind == "boat":
                    self.sim.players["outside"] = dict(id="outside", position=obj)
                elif object_kind == "lure":
                    self.sim.lures[("outside", 1)] = dict(obj, expiresAt=1e20)
                elif object_kind == "mine":
                    self.sim.mines[("outside", 1)] = dict(obj, armed=True)
                else:
                    self.sim.torpedoes[("outside", 1)] = dict(
                        self.t, **obj, ownerPlayerId="outside", tid=1, notifiedTargets=set())
                self.sim.update_server_torpedoes(1, self.world)
                if object_kind == "torpedo":
                    events = self.sim.drain_events()
                    self.assertEqual(2, sum(isinstance(e, TorpedoDead) for e in events))
                    self.assertFalse(any(isinstance(e, TorpedoExploded) for e in events))
                    self.assertFalse(self.sim.torpedoes)
                else:
                    self.dead()

    def test_nearest_range_or_bounds_and_missing_ground(self) -> None:
        for max_range, reason, x in ((5, None, 5), (10, None, 10), (20, "map_bounds", 10)):
            self.setUp()
            self.t["maxRange"] = max_range
            self.sim.update_server_torpedoes(1, self.world)
            self.assertEqual(x, self.t["x"])
            events = self.sim.drain_events()
            self.assertEqual([reason], [e.reason for e in events if isinstance(e, TorpedoDead)])
        self.setUp()
        del self.world["ground"]
        self.sim.update_server_torpedoes(1, self.world)
        self.assertEqual(100, self.t["x"])
        self.assertIn(self.key, self.sim.torpedoes)

    def test_boundary_death_trace_and_autogame_settling(self) -> None:
        end = AutogameEnd({self.key[0]: "red", "survivor": "blue"},
                          dict(type="anyBoatSunk", waitForTorpedoes=True), None,
                          lambda: 100.0)
        end.record([BoatSunk(victim_id=self.key[0], attacker_id="survivor")])
        self.assertIsNone(end.evaluate(self.sim.torpedoes.values()))
        self.assertIsNotNone(end.settling)
        self.sim.update_server_torpedoes(1, self.world)
        events = self.dead()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            trace = GameTrace(path=path, enabled=True)
            try:
                for event in events:
                    trace.event(event, self.sim.players)
            finally:
                trace.close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            deaths = [r["data"]["fields"] for r in rows
                      if r["type"] == "event" and r["data"]["name"] == "TorpedoDead"]
            self.assertEqual(1, len(deaths))
            self.assertEqual("map_bounds", deaths[0]["reason"])
        end.record(events)
        self.assertEqual(["blue"], end.evaluate(self.sim.torpedoes.values())["winningTeamIds"])


if __name__ == "__main__":
    unittest.main()
