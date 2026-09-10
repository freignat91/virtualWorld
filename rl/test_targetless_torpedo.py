"""Tirs sans contact : vrai Sim, actions RL/BT et capteurs natifs."""

import copy
import math
import random
import unittest
from unittest.mock import patch

import bot_ai
from events import TorpedoDead
from rl.headless import HeadlessRunner
from rl.rl_control import apply_action, build_observation


class TargetlessTorpedoTest(unittest.TestCase):
    def setUp(self) -> None:
        state = random.getstate()
        self.addCleanup(random.setstate, state)

    def scene(self, boat_type: str = "destroyer") -> None:
        self.runner = HeadlessRunner(seed=73)
        self.sim = self.runner.sim
        self.world = self.runner.world
        self.world.update(islands=[], thermoclines=[], ground=dict(width=10000, depth=10000))
        sid = self.runner.spawn_bot(boat_type, external_control=True,
                                    position=(0, 0), rotation=0.0, team_id="owner")
        self.bot = self.sim.bots[sid]

    def test_rl_actions_ammo_cooldown_and_shapes(self) -> None:
        for boat_type in ("destroyer", "submarine"):
            for weapon in (1, 2):
                with self.subTest(boat=boat_type, weapon=weapon):
                    self.scene(boat_type)
                    shape = build_observation(self.bot, self.sim, self.world).shape
                    action = [0, 0, weapon, 0, 0] if boat_type == "destroyer" else [0, 0, 0, weapon, 0]
                    kind = "acoustic" if weapon == 1 else "autonomous"
                    ammo = self.sim._legacy.torpedo_ammo[self.bot["sid"]]
                    before = ammo[kind]
                    result = apply_action(self.bot, self.sim, action)
                    self.assertTrue(result["weapon_fired"])
                    self.assertFalse(result["weapon_invalid"])
                    self.assertEqual(before - 1, ammo[kind])
                    t = next(iter(self.sim.torpedoes.values()))
                    self.assertIsNone(t["initialTarget"])
                    self.assertIsNone(t["targetId"])
                    self.assertEqual(self.bot["boat"]["torpedoes"][kind]["activation"] / 10, t["activation"])
                    self.assertEqual(self.sim.now() + 4, self.bot["next_torpedo_at"])
                    self.assertFalse(apply_action(self.bot, self.sim, action)["weapon_fired"])
                    self.assertEqual(before - 1, ammo[kind])
                    self.runner._time += 4.0
                    self.assertTrue(apply_action(self.bot, self.sim, action)["weapon_fired"])
                    self.runner._time += 4.0
                    ammo[kind] = 0
                    self.assertTrue(apply_action(self.bot, self.sim, action)["weapon_invalid"])
                    self.assertEqual(shape, build_observation(self.bot, self.sim, self.world).shape)

    def test_bt_direct_action_without_contact_obeys_cooldown(self) -> None:
        self.scene()
        ctx = dict(bot=self.bot, now=self.sim.now(), deps=dict(
            bots_passive_get=lambda: False, UNIT_METERS_BOT=10,
            spawn_bot_torpedo=self.sim.spawn_bot_torpedo))
        self.assertEqual(bot_ai.Status.SUCCESS, bot_ai.act_fire_torpedo_at_audible(ctx, {}))
        self.assertIsNone(next(iter(self.sim.torpedoes.values()))["initialTarget"])
        self.assertEqual(bot_ai.Status.FAILURE, bot_ai.act_fire_torpedo_at_audible(ctx, {}))
        self.assertEqual(1, len(self.sim.torpedoes))

    def test_hidden_positions_cannot_affect_launch_or_pre_activation(self) -> None:
        for method in ("spawn_bot_torpedo", "spawn_bot_torpedo_autonomous"):
            outcomes = []
            for position in ((-100, 0), (200, 80)):
                self.scene("submarine")
                self.runner.spawn_bot("destroyer", external_control=True,
                                      position=position, team_id="enemy")
                self.assertTrue(getattr(self.sim, method)(self.bot))
                t = next(iter(self.sim.torpedoes.values()))
                depth = t["y"]
                with patch.object(self.sim, "_pick_acoustic", side_effect=AssertionError), \
                     patch.object(self.sim, "_pick_radar", side_effect=AssertionError):
                    self.sim.update_server_torpedoes(1, self.world)
                self.assertEqual((-1, 0, 0, depth), (t["dirX"], t["dirZ"], t["pitch"], t["y"]))
                outcomes.append(copy.deepcopy(t))
            self.assertEqual(*outcomes)

    def test_activation_then_native_range_and_los(self) -> None:
        for method in ("spawn_bot_torpedo", "spawn_bot_torpedo_autonomous"):
            self.scene()
            sid = self.runner.spawn_bot("destroyer", external_control=True,
                                        position=(-100, 0), team_id="enemy")
            enemy = self.sim.players[sid]
            enemy["speedRatio"] = 1.0
            self.assertTrue(getattr(self.sim, method)(self.bot))
            t = next(iter(self.sim.torpedoes.values()))
            self.sim.update_server_torpedoes(0.05, self.world)
            self.assertIsNone(t["acquiredBoatId"])
            t["traveled"] = t["activation"]
            t["x"] -= t["activation"]
            self.world["islands"] = [{"points": [dict(x=x, z=z) for x, z in
                ((-75, -50), (-74, -50), (-74, 50), (-75, 50))]}]
            self.sim.update_server_torpedoes(0.05, self.world)
            self.assertIsNone(t["acquiredBoatId"])
            self.world["islands"] = []
            enemy["position"]["x"] = -100000
            self.sim.update_server_torpedoes(0.05, self.world)
            self.assertIsNone(t["acquiredBoatId"])
            enemy["position"]["x"] = -100
            self.sim.update_server_torpedoes(0.05, self.world)
            self.assertEqual(enemy["id"], t["acquiredBoatId"])

    def test_empty_world_coasts_until_range_or_bounds(self) -> None:
        for method in ("spawn_bot_torpedo", "spawn_bot_torpedo_autonomous"):
            for bounded in (False, True):
                self.scene()
                if bounded:
                    self.world["ground"]["width"] = 40
                self.assertTrue(getattr(self.sim, method)(self.bot))
                t = next(iter(self.sim.torpedoes.values()))
                depth = t["y"]
                self.sim.drain_events()
                for _ in range(2000):
                    self.sim.update_server_torpedoes(1, self.world)
                    self.assertTrue(all(math.isfinite(t[k]) for k in ("x", "y", "z", "traveled")))
                    self.assertEqual(depth, t["y"])
                    if not self.sim.torpedoes:
                        break
                self.assertFalse(self.sim.torpedoes)
                deaths = [e for e in self.sim.drain_events() if isinstance(e, TorpedoDead)]
                self.assertEqual(1, len(deaths))
                if bounded:
                    self.assertEqual("map_bounds", deaths[0].reason)
                else:
                    self.assertAlmostEqual(t["maxRange"], t["traveled"])


if __name__ == "__main__":
    unittest.main()
