"""Les tirs humains, BT et RL exigent toujours une cible explicite."""

import copy
import unittest

import bot_ai
from rl.headless import HeadlessRunner
from rl.rl_control import apply_action


class TorpedoTargetRequirementTest(unittest.TestCase):
    def scene(self, boat_type: str = "destroyer") -> None:
        self.runner = HeadlessRunner(seed=73)
        self.sim = self.runner.sim
        self.world = self.runner.world
        self.world.update(islands=[], thermoclines=[], ground=dict(width=10000, depth=10000))
        sid = self.runner.spawn_bot(
            boat_type, external_control=True, position=(0, 0),
            rotation=0.0, team_id="owner")
        self.bot = self.sim.bots[sid]

    def test_sim_rejects_missing_target_without_consuming_ammo(self) -> None:
        for method, kind in (("spawn_bot_torpedo", "acoustic"),
                             ("spawn_bot_torpedo_autonomous", "autonomous")):
            with self.subTest(method=method):
                self.scene("submarine")
                ammo = self.sim._legacy.torpedo_ammo[self.bot["sid"]]
                before = copy.deepcopy(ammo)
                self.assertFalse(getattr(self.sim, method)(self.bot))
                self.assertEqual(before, ammo)
                self.assertFalse(self.sim.torpedoes)
                self.assertEqual(0, self.sim._legacy.next_torpedo_tid.get(self.bot["id"], 0))

    def test_rl_actions_without_contact_are_invalid_for_both_hulls(self) -> None:
        for boat_type in ("destroyer", "submarine"):
            for weapon in (1, 2):
                with self.subTest(boat=boat_type, weapon=weapon):
                    self.scene(boat_type)
                    action = ([2, 1, weapon, 0, 0] if boat_type == "destroyer"
                              else [2, 1, 2, weapon, 0])
                    ammo = copy.deepcopy(self.sim._legacy.torpedo_ammo[self.bot["sid"]])
                    cooldown = self.bot["next_torpedo_at"]
                    result = apply_action(self.bot, self.sim, action)
                    self.assertTrue(result["weapon_requested"])
                    self.assertTrue(result["weapon_invalid"])
                    self.assertFalse(result["weapon_fired"])
                    self.assertFalse(result["weapon_had_acquisition"])
                    self.assertTrue(result["weapon_without_acquisition"])
                    self.assertEqual(ammo, self.sim._legacy.torpedo_ammo[self.bot["sid"]])
                    self.assertFalse(self.sim.torpedoes)
                    self.assertEqual(cooldown, self.bot["next_torpedo_at"])

    def test_bt_direct_action_without_contact_fails_without_cooldown(self) -> None:
        self.scene()
        ctx = dict(bot=self.bot, now=self.sim.now(), deps=dict(
            bots_passive_get=lambda: False, UNIT_METERS_BOT=10,
            spawn_bot_torpedo=self.sim.spawn_bot_torpedo))
        cooldown = self.bot["next_torpedo_at"]
        self.assertEqual(bot_ai.Status.FAILURE, bot_ai.act_fire_torpedo_at_audible(ctx, {}))
        self.assertFalse(self.sim.torpedoes)
        self.assertEqual(cooldown, self.bot["next_torpedo_at"])

    def test_selected_live_or_observed_target_launches(self) -> None:
        for method in ("spawn_bot_torpedo", "spawn_bot_torpedo_autonomous"):
            for observed in (False, True):
                with self.subTest(method=method, observed=observed):
                    self.scene("submarine")
                    sid = self.runner.spawn_bot(
                        "destroyer", external_control=True,
                        position=(-100, 20), team_id="enemy")
                    live = self.sim.players[sid]
                    target = live if not observed else {
                        "id": live["id"], "sid": sid,
                        "position": dict(live["position"]),
                        "observed_at": self.sim.now(), "tracked": False,
                    }
                    self.assertTrue(getattr(self.sim, method)(self.bot, target))
                    torpedo = next(iter(self.sim.torpedoes.values()))
                    self.assertEqual(tuple(target["position"][axis] for axis in ("x", "y", "z")),
                                     torpedo["initialTarget"])
                    self.assertEqual(None if observed else live["id"], torpedo["targetId"])

    def test_rl_fires_with_a_fresh_selected_contact(self) -> None:
        for boat_type in ("destroyer", "submarine"):
            with self.subTest(boat_type=boat_type):
                self.scene(boat_type)
                enemy_type = "submarine" if boat_type == "destroyer" else "destroyer"
                sid = self.runner.spawn_bot(
                    enemy_type, external_control=True,
                    position=(-100, 0), team_id="enemy")
                enemy = self.sim.players[sid]
                self.bot["rl_contact"] = {
                    "id": enemy["id"], "sid": sid,
                    "x": enemy["position"]["x"], "y": enemy["position"]["y"],
                    "z": enemy["position"]["z"], "at": self.sim.now(),
                    "boat": dict(enemy.get("boat") or {}),
                }
                self.bot["rl_contact_tracked"] = True
                action = ([2, 1, 1, 0, 0] if boat_type == "destroyer"
                          else [2, 1, 2, 1, 0])
                result = apply_action(self.bot, self.sim, action)
                self.assertTrue(result["weapon_fired"])
                self.assertFalse(result["weapon_invalid"])
                self.assertTrue(result["weapon_had_acquisition"])


if __name__ == "__main__":
    unittest.main()
