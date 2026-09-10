"""Radar/CPA partage Sim, RL et BT, sans serveur ni dependance RL."""

import copy
import unittest

import bot_ai
import simulation


class TorpedoThreatVisibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.world = {"islands": [], "thermoclines": []}
        self.sim = simulation.Sim(self.world)
        self.bot = {"id": "observer", "position": {"x": 0, "y": 0, "z": 0},
                    "boat": {"radarRangeMeters": 1000}}
        self.torpedo = {"ownerPlayerId": "enemy", "tid": 1, "x": -60, "y": 0,
                        "z": 0, "dirX": 1, "dirZ": 0, "speed": 10}
        self.sim.torpedoes[("enemy", 1)] = self.torpedo
        self.deps = {"UNIT_METERS_BOT": 10, "torpedoes_server": self.sim.torpedoes,
                     "bot_torpedoes_threat": self.sim.bot_torpedoes_threat}
        self.ctx = {"bot": self.bot, "world": self.world, "deps": self.deps, "now": 0}
        self.polygon = [{"x": x, "z": z} for x, z in
                        ((-30.2, -1), (-30.1, -1), (-30.1, 1), (-30.2, 1))]

    def test_hidden_threats_do_not_enter_bt_or_sim_even_when_locked(self) -> None:
        for barrier in ("island", "edge", "vertex", "thermocline", "range"):
            with self.subTest(barrier=barrier):
                self.setUp()
                if barrier in ("island", "edge", "vertex"):
                    self.world["islands"] = [{"points": self.polygon}]
                    if barrier != "island":
                        self.torpedo.update(x=-30.1, z=1 if barrier == "vertex" else 0)
                elif barrier == "thermocline":
                    self.world["thermoclines"] = [{"points": [
                        {"x": x, "z": z} for x, z in
                        ((-40, -1), (-20, -1), (-20, 1), (-40, 1))], "depthMeters": 5}]
                    self.torpedo["y"] = -1
                else:
                    self.torpedo["x"] = -100.01
                self.torpedo["acquiredBoatId"] = self.bot["id"]
                self.assertIsNone(simulation.torpedo_radar_threat(self.bot, self.torpedo, self.world))
                self.assertFalse(self.sim.bot_torpedoes_threat(self.bot))
                self.assertFalse(bot_ai._bot_threats(self.bot, self.deps))
                self.assertFalse(bot_ai.cond_torpedo_incoming(self.ctx, {}))
                self.assertFalse(bot_ai.cond_torpedo_acquired(self.ctx, {}))
                self.assertFalse(bot_ai.cond_combat_active(self.ctx, {}))
                self.assertFalse(bot_ai.cond_combat_should_continue(self.ctx, {}))

    def test_visible_metrics_and_metadata_invariance(self) -> None:
        baseline = self.sim.bot_torpedoes_threat(self.bot)
        self.assertEqual((600, 0, 6), simulation.torpedo_radar_threat(
            self.bot, self.torpedo, self.world))
        self.assertTrue(bot_ai.cond_combat_active(self.ctx, {}))
        for kind in ("acoustic", "autonomous", "wireGuided"):
            for lock in (None, "observer", "other"):
                self.torpedo.update(kind=kind, acquiredBoatId=lock, lockedKey=("boat", lock))
                self.assertEqual(baseline, self.sim.bot_torpedoes_threat(self.bot))
                self.assertEqual(baseline, bot_ai._bot_threats(self.bot, self.deps))
        self.torpedo["x"] = -100
        self.assertIsNotNone(simulation.torpedo_radar_threat(self.bot, self.torpedo, self.world))
        self.torpedo["ownerPlayerId"] = self.bot["id"]
        self.assertFalse(self.sim.bot_torpedoes_threat(self.bot))
        self.assertTrue(bot_ai.cond_combat_active(self.ctx, {}))

    def test_no_lock_bypass_of_cpa_speed_or_order(self) -> None:
        baseline = copy.deepcopy(self.sim.bot_torpedoes_threat(self.bot))
        self.sim.torpedoes[("other", 1)] = dict(self.torpedo, ownerPlayerId="other",
                                             x=-80, acquiredBoatId="observer")
        threats = self.sim.bot_torpedoes_threat(self.bot)
        self.assertEqual([6, 8], [t["eta_s"] for t in threats])
        self.assertEqual(baseline[0], threats[0])
        self.torpedo.update(acquiredBoatId="observer", speed=0)
        self.assertIsNone(simulation.torpedo_radar_threat(self.bot, self.torpedo, self.world))
        self.torpedo.update(speed=10, dirX=0, dirZ=1)
        self.assertIsNone(simulation.torpedo_radar_threat(self.bot, self.torpedo, self.world))

    def test_passed_contact_tangent_and_horizon_keep_existing_safety_filter(self) -> None:
        for x, z, expected in ((0, 0, (0, 0, 0)), (0, 20, (200, 200, 0)),
                               (20, 0, (200, 200, 0)), (20.01, 0, None),
                               (-120, 0, (1200, 200, 10)), (-120.01, 0, None)):
            with self.subTest(x=x, z=z):
                self.bot["boat"]["radarRangeMeters"] = 2000
                self.torpedo.update(x=x, z=z, dirX=1, dirZ=0, speed=10)
                self.assertEqual(simulation.torpedo_radar_threat(
                    self.bot, self.torpedo, self.world), expected)
        self.torpedo.update(x=1, z=0)
        self.assertTrue(bot_ai.cond_torpedo_incoming(self.ctx, {}))
        self.assertTrue(bot_ai.cond_combat_active(self.ctx, {}))


if __name__ == "__main__":
    unittest.main()
