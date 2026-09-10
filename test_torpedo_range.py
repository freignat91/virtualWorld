"""Portee cumulee des torpilles dans la simulation partagee, sans reseau."""

import math
import unittest

from events import SonarBeaconDestroyed, TorpedoDead, TorpedoExploded
from rl.headless import HeadlessRunner


class TorpedoRangeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = HeadlessRunner(seed=73)
        self.sim = self.runner.sim
        self.world = self.runner.world
        self.world.update(islands=[], thermoclines=[])
        sid = self.runner.spawn_bot("submarine", external_control=True,
                                    position=(0, 0), team_id="owner")
        self.bot = self.sim.bots[sid]
        self.target = {"id": "point", "position": dict(x=100, y=-10, z=0),
                       "observed_at": 0.0}
        self.assertTrue(self.sim.spawn_bot_torpedo(self.bot, self.target))
        self.t = next(iter(self.sim.torpedoes.values()))
        self.t.update(x=0.0, y=-10.0, z=0.0, dirX=1.0, dirZ=0.0,
                      initialTarget=None, activation=0)
        self.sim.players.clear()
        self.sim.bots.clear()
        self.sim.drain_events()

    def test_terminal_step_all_kinds_and_pitch(self) -> None:
        for kind in ("acoustic", "autonomous", "wireGuided"):
            for dt in (0.05, 0.25, 1.0):
                for pitch in (0.0, -0.3):
                    with self.subTest(kind=kind, dt=dt, pitch=pitch):
                        self.setUp()
                        spec = self.bot["boat"]["torpedoes"][kind]
                        max_range = spec["maxRangeMeters"] / 10
                        self.t.update(kind=kind, pitch=pitch, activation=3000,
                                      speed=spec["speed"] * 0.514444 / 10,
                                      traveled=max_range - 0.01, maxRange=max_range)
                        key = (self.t["ownerPlayerId"], self.t["tid"])
                        if kind == "wireGuided":
                            self.sim._active_wire[key[0]] = key
                        self.sim.update_server_torpedoes(dt, self.world)
                        self.assertEqual(max_range, self.t["traveled"])
                        self.assertAlmostEqual(0.01, math.dist(
                            (0, -10, 0), tuple(self.t[k] for k in ("x", "y", "z"))))
                        self.assertNotIn(key, self.sim.torpedoes)
                        self.assertNotIn(key[0], self.sim._active_wire)
                        events = self.sim.drain_events()
                        explosion = next(e for e in events if isinstance(e, TorpedoExploded))
                        self.assertEqual(0, explosion.damage)
                        self.assertEqual((self.t["x"], self.t["y"], self.t["z"]),
                                         (explosion.x, explosion.y, explosion.z))
                        self.assertEqual(1, sum(isinstance(e, TorpedoDead) for e in events))

    def test_collision_segment_stops_at_remaining_range(self) -> None:
        for beacon_x, hit in ((0.05, True), (1.2, False)):
            with self.subTest(beacon_x=beacon_x):
                self.setUp()
                self.t.update(speed=40.0, traveled=9.9, maxRange=10.0)
                self.sim.beacons[1] = dict(x=beacon_x, z=0)
                self.sim.update_server_torpedoes(0.05, self.world)
                events = self.sim.drain_events()
                self.assertEqual(hit, any(isinstance(e, SonarBeaconDestroyed) for e in events))
                self.assertFalse(self.sim.torpedoes)
                if not hit:
                    self.assertAlmostEqual(0.1, self.t["x"])

    def test_turning_and_diving_consume_cumulative_range(self) -> None:
        self.t.update(kind="wireGuided", speed=2.0, pitch=-0.2,
                      wireYaw=1, minTurnRadius=1.0, activation=0.5, maxRange=2.05)
        key = (self.t["ownerPlayerId"], self.t["tid"])
        self.sim._active_wire[key[0]] = key
        path = 0.0
        previous = (0, -10, 0)
        for _ in range(21):
            self.sim.update_server_torpedoes(0.05, self.world)
            position = tuple(self.t[k] for k in ("x", "y", "z"))
            path += math.dist(previous, position)
            previous = position
            self.assertAlmostEqual(path, self.t["traveled"])
        self.assertAlmostEqual(2.05, path)
        self.assertLess(math.dist((0, -10, 0), previous), path)
        self.assertFalse(self.sim.torpedoes)

    def test_bot_launches_use_boat_specs(self) -> None:
        for boat_type in ("destroyer", "submarine"):
            for kind in ("acoustic", "autonomous"):
                with self.subTest(boat_type=boat_type, kind=kind):
                    self.setUp()
                    sid = self.runner.spawn_bot(boat_type, external_control=True,
                                                position=(0, 0), team_id="owner")
                    bot = self.sim.bots[sid]
                    self.sim.torpedoes.clear()
                    spawn = (self.sim.spawn_bot_torpedo if kind == "acoustic"
                             else self.sim.spawn_bot_torpedo_autonomous)
                    self.assertTrue(spawn(bot, self.target))
                    t = next(iter(self.sim.torpedoes.values()))
                    spec = bot["boat"]["torpedoes"][kind]
                    self.assertEqual(spec["maxRangeMeters"] / 10, t["maxRange"])
                    self.assertEqual(0, t["traveled"])
                    self.assertAlmostEqual(spec["speed"] * 0.514444 / 10, t["speed"])


if __name__ == "__main__":
    unittest.main()
