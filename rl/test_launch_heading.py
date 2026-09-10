"""Cap initial commun et guidage normal sur un point observe, sans visee cachee."""

import copy
import math
import random
import unittest

from rl.headless import HeadlessRunner


class LaunchHeadingTest(unittest.TestCase):
    def test_snapshot_heading_offset_pitch_and_bounded_guidance(self) -> None:
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        for method in ("spawn_bot_torpedo", "spawn_bot_torpedo_autonomous"):
            for rotation in (0.0, 0.7, -1.2):
                for bearing in (math.pi / 2, math.pi):
                    with self.subTest(method=method, rotation=rotation, bearing=bearing):
                        outcomes = []
                        for hidden in ((300, 300), (-300, -300)):
                            runner = HeadlessRunner(seed=73)
                            runner.world.update(islands=[], thermoclines=[])
                            sim = runner.sim
                            sid = runner.spawn_bot("destroyer", external_control=True,
                                position=(0, 0), rotation=rotation, team_id="owner")
                            enemy_sid = runner.spawn_bot("destroyer", external_control=True,
                                position=hidden, team_id="enemy")
                            bot = sim.bots[sid]
                            snapshot = {"id": sim.players[enemy_sid]["id"],
                                "observed_at": sim.now(), "tracked": False,
                                "position": {"x": -60 * math.cos(rotation + bearing),
                                             "y": -10, "z": 60 * math.sin(rotation + bearing)}}
                            self.assertTrue(getattr(sim, method)(bot, snapshot))
                            t = next(iter(sim.torpedoes.values()))
                            forward = (-math.cos(rotation), math.sin(rotation))
                            self.assertEqual(forward, (t["dirX"], t["dirZ"]))
                            self.assertAlmostEqual(0.4 * forward[0], t["x"])
                            self.assertAlmostEqual(0.4 * forward[1], t["z"])
                            self.assertEqual(min(-0.2, bot["position"]["y"]), t["y"])
                            self.assertEqual(0, t["pitch"])
                            self.assertIsNone(t["targetId"])
                            self.assertFalse(t["inAcquisition"])
                            point = tuple(snapshot["position"][axis] for axis in ("x", "y", "z"))
                            self.assertEqual(point, t["initialTarget"])
                            snapshot["position"]["x"] = 999
                            self.assertEqual(point, t["initialTarget"])
                            outcomes.append(copy.deepcopy((t, sim.drain_events())))
                            # Phase initiale sur point : pas de capteur ni de virage instantane.
                            t["activation"] = 100
                            previous = math.atan2(t["dirZ"], t["dirX"])
                            for _ in range(3):
                                sim.update_server_torpedoes(0.05, runner.world)
                                current = math.atan2(t["dirZ"], t["dirX"])
                                delta = abs((current - previous + math.pi) % (2 * math.pi) - math.pi)
                                self.assertGreater(delta, 0)
                                self.assertLessEqual(delta, t["speed"] * 0.05 / t["minTurnRadius"] + 1e-12)
                                self.assertFalse(t["inAcquisition"])
                                self.assertIsNone(t["targetId"])
                                previous = current
                            outcomes.append(copy.deepcopy(t))
                        self.assertEqual(outcomes[0], outcomes[2])
                        self.assertEqual(outcomes[1], outcomes[3])


if __name__ == "__main__":
    unittest.main()
