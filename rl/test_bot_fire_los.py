"""Perception LOS et tirs sur snapshots : vrais bots et armes Sim en headless."""

import copy
import math
import random
import unittest
from unittest.mock import patch

import bot_ai
from rl.headless import HeadlessRunner
from rl.rl_control import (
    DESTROYER_OBSERVATION_VERSION, DESTROYER_V1_OBSERVATION_VERSION,
    _contact_target, apply_action, build_observation,
)


class BotFireLosTest(unittest.TestCase):
    def setUp(self) -> None:
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        self.runner = HeadlessRunner(seed=73)
        self.runner.world.update(islands=[{"points": [
            {"x": x, "z": z} for x, z in
            ((-30.2, -1), (-30.1, -1), (-30.1, 1), (-30.2, 1))]}], thermoclines=[])
        self.scene()

    def scene(self, boat_type: str = "destroyer") -> None:
        self.runner.reset(seed=73)
        self.sim = self.runner.sim
        self.legacy = self.runner.legacy
        sid = self.runner.spawn_bot(boat_type, external_control=True,
                                   position=(0, 0), rotation=0, team_id="observer")
        target_sid = self.runner.spawn_bot("destroyer", external_control=True,
                                          position=(-60, 20), rotation=0, team_id="enemy")
        self.bot = self.sim.bots[sid]
        self.bot["rl_control_version"] = DESTROYER_OBSERVATION_VERSION
        self.target = self.sim.players[target_sid]
        self.target["speedRatio"] = 1.0
        self.ctx = {"bot": self.bot, "world": self.runner.world, "dt": 0.0,
                    "now": self.sim.now(), "deps": self.legacy._get_bt_deps()}
        self.sim.drain_events()

    def move_target(self, x: float = -60, z: float = 0) -> None:
        for target in (self.target, self.sim.bots[self.target["sid"]]):
            target["position"] = {"x": x, "y": -0.2, "z": z}

    def firing_state(self) -> dict:
        return copy.deepcopy({
            "ammo": {name: value for name, value in vars(self.legacy).items()
                     if name.endswith("_ammo") or name.startswith("next_")},
            "cooldowns": {name: value for name, value in self.bot.items()
                          if name in ("next_torpedo_at", "next_cannon_at", "next_aa_at",
                                      "next_grenade_at", "aa_per_drone")},
            "torpedoes": self.sim.torpedoes, "grenades": self.sim.grenades,
            "drones": self.sim.drones, "hits": self.sim.cannon_shells,
            "events": self.sim._events, "integrity": self.target["integrity"],
        })

    def fire(self, weapon: str):
        if weapon == "grenade":
            pos = self.target["position"]
            return self.sim.spawn_grenade(self.bot["sid"], self.sim.players[self.bot["sid"]],
                                         {"targetX": pos["x"], "targetZ": pos["z"], "depthMeters": 5})
        if weapon == "aa":
            return self.sim.bot_fire_aa(self.bot, dict(self.target["position"],
                                                      ownerPlayerId=self.target["id"], did=1))
        method = {"acoustic": self.sim.spawn_bot_torpedo,
                  "autonomous": self.sim.spawn_bot_torpedo_autonomous,
                  "cannon": self.sim.bot_fire_cannon}[weapon]
        return method(self.bot, self.target)

    def test_id_damage_endpoints_reject_hidden_targets_without_effects(self) -> None:
        for weapon in ("aa",):
            for x, z in ((-60, 0), (-30.1, 0), (-30.1, 1)):
                with self.subTest(weapon=weapon, endpoint=(x, z)):
                    self.scene()
                    self.move_target(x, z)
                    before = self.firing_state()
                    with patch.object(self.legacy.socketio, "start_background_task") as task:
                        self.assertFalse(self.fire(weapon))
                        task.assert_not_called()
                    self.assertEqual(before, self.firing_state())
                    self.runner._time = 10.0
                    self.sim.update_cannon_shells()
                    self.assertEqual(before, self.firing_state())
                    self.move_target(z=20)
                    self.fire(weapon)
                    self.assertNotEqual(before, self.firing_state())

    def test_point_launch_endpoints_allow_island_occlusion(self) -> None:
        for weapon in ("acoustic", "autonomous", "grenade", "cannon"):
            for x, z in ((-60, 0), (-30.1, 0), (-30.1, 1)):
                with self.subTest(weapon=weapon, endpoint=(x, z)):
                    self.scene()
                    self.move_target(x, z)
                    before = self.firing_state()
                    self.fire(weapon)
                    self.assertNotEqual(before, self.firing_state())
                    self.assertTrue(self.sim.torpedoes or self.sim.grenades or self.sim.cannon_shells)

    def test_human_manual_grenade_point_fire_is_unchanged(self) -> None:
        self.move_target()
        sid = self.bot["sid"]
        self.sim.bots.pop(sid)
        self.sim.players[sid]["is_bot"] = False
        self.fire("grenade")
        self.assertEqual(1, len(self.sim.grenades))

    def test_rl_memory_launch_invariant_across_hidden_positions(self) -> None:
        for boat_type, version, weapons in (
                ("submarine", None, (1, 2)),
                ("destroyer", DESTROYER_V1_OBSERVATION_VERSION, (1, 2, 3, 4)),
                ("destroyer", DESTROYER_OBSERVATION_VERSION, (1, 2, 3, 4))):
            for weapon in weapons:
                with self.subTest(boat=boat_type, version=version, weapon=weapon):
                    launches = []
                    for x, y in ((-60, -0.2), (-200, -15)):
                        self.scene(boat_type)
                        self.bot["rl_control_version"] = version
                        build_observation(self.bot, self.sim, self.runner.world)
                        snapshot = _contact_target(self.bot, self.sim)
                        self.assertIsNot(self.target, snapshot)
                        memory = copy.deepcopy(self.bot["rl_contact"])
                        self.move_target(x)
                        self.target["position"]["y"] = y
                        self.sim.bots[self.target["sid"]]["position"]["y"] = y
                        self.runner._time = 0.25
                        build_observation(self.bot, self.sim, self.runner.world)
                        self.assertEqual(memory, self.bot["rl_contact"])
                        self.assertFalse(_contact_target(self.bot, self.sim)["tracked"])
                        action = ([2, 1, 0, weapon, 0] if boat_type == "submarine"
                                  else [2, 1, weapon, 0, 0] +
                                  ([0] if version == DESTROYER_OBSERVATION_VERSION else []))
                        before = self.firing_state()
                        result = apply_action(self.bot, self.sim, action)
                        self.assertTrue(result["weapon_fired"])
                        self.assertFalse(result["weapon_invalid"])
                        self.assertNotEqual(before["ammo"], self.firing_state()["ammo"])
                        launches.append(copy.deepcopy((self.sim.torpedoes, self.sim.grenades,
                                                       self.sim._events)))
                        for torpedo in self.sim.torpedoes.values():
                            self.assertEqual(tuple(snapshot["position"][axis] for axis in ("x", "y", "z")),
                                             torpedo["initialTarget"])
                            self.assertIsNone(torpedo["targetId"])
                            self.assertFalse(torpedo["acquired"])
                        self.runner._time = 10
                        self.sim.update_cannon_shells()
                        self.assertEqual(before["integrity"], self.target["integrity"])
                    self.assertEqual(launches[0], launches[1])

    def test_bt_memory_launch_invariant_across_hidden_positions(self) -> None:
        for action in (bot_ai.act_fire_torpedo_at_audible,
                       bot_ai.act_fire_cannon_at_surface_enemy,
                       bot_ai.act_attack_torpedo_at_known,
                       bot_ai.act_combat_react):
            with self.subTest(action=action.__name__):
                launches = []
                for x, y in ((-60, -0.2), (-200, -15)):
                    self.scene()
                    bot_ai.act_passive_detection(self.ctx, {})
                    memory = copy.deepcopy(self.bot["bb"]["last_enemy_pos"])
                    self.move_target(x)
                    self.target["position"]["y"] = y
                    if action in (bot_ai.act_combat_react, bot_ai.act_attack_torpedo_at_known):
                        self.runner._time = self.ctx["now"] = 2
                        bot_ai.act_passive_detection(self.ctx, {})
                        self.assertFalse(self.bot["last_detected_ids"])
                    before = self.firing_state()
                    action(self.ctx, {"min_dist_destroyer_m": 0})
                    self.assertEqual(memory, self.bot["bb"]["last_enemy_pos"])
                    self.assertEqual(memory["target"]["position"], bot_ai._find_attacker_player(
                        {"ownerPlayerId": self.target["id"]}, self.ctx["deps"], self.bot,
                        self.ctx["now"])["position"])
                    if action is bot_ai.act_fire_cannon_at_surface_enemy:
                        self.assertEqual(1, len(self.sim.cannon_shells))
                        self.assertNotEqual(before["ammo"], self.firing_state()["ammo"])
                    else:
                        self.assertEqual(1, len(self.sim.torpedoes))
                        self.assertNotEqual(before["ammo"], self.firing_state()["ammo"])
                    launches.append(copy.deepcopy(self.sim.torpedoes))
                self.assertEqual(launches[0], launches[1])

    def test_bt_detection_skips_hidden_target_and_selects_visible_candidate(self) -> None:
        for action in (bot_ai.act_fire_torpedo_at_audible,
                       bot_ai.act_fire_cannon_at_surface_enemy,
                       bot_ai.act_attack_torpedo_at_known, bot_ai.act_combat_react):
            with self.subTest(action=action.__name__):
                self.scene()
                bot_ai.act_passive_detection(self.ctx, {})
                self.move_target()
                sid = self.runner.spawn_bot("destroyer", external_control=True,
                                            position=(-80, 30), team_id="enemy")
                self.sim.players[sid]["speedRatio"] = 1.0
                self.runner._time = self.ctx["now"] = 1.0
                bot_ai.act_passive_detection(self.ctx, {})
                self.assertNotIn(self.target["id"], self.bot["last_detected_ids"])
                action(self.ctx, {"min_dist_destroyer_m": 0})
                self.assertTrue(self.sim.torpedoes or self.sim.cannon_shells)
                if self.sim.cannon_shells:
                    self.assertEqual(-80, self.sim.cannon_shells[0]["end_x"])
                    self.assertEqual(30, self.sim.cannon_shells[0]["end_z"])
                for torpedo in self.sim.torpedoes.values():
                    self.assertAlmostEqual(-math.cos(self.bot["rotation"]), torpedo["dirX"])
                    self.assertAlmostEqual(math.sin(self.bot["rotation"]), torpedo["dirZ"])
                    self.assertEqual((-80, self.sim.players[sid]["position"]["y"], 30),
                                     torpedo["initialTarget"])

    def test_torpedo_acquisition_requires_sensor_los_not_remembered_id(self) -> None:
        for weapon in (1, 2):
            with self.subTest(weapon=weapon):
                self.scene()
                build_observation(self.bot, self.sim, self.runner.world)
                aim = _contact_target(self.bot, self.sim)["position"]
                self.move_target()
                self.assertTrue(apply_action(self.bot, self.sim, [2, 1, weapon, 0, 0, 0])["weapon_fired"])
                torpedo = next(iter(self.sim.torpedoes.values()))
                torpedo["activation"] = 0
                torpedo["radarHalfAngle"] = math.pi
                self.assertIsNone(self.sim._pick_radar(torpedo, self.runner.world))
                self.assertIsNone(self.sim._pick_acoustic(torpedo)["pos"])
                self.sim.drain_events()
                self.sim._emit_torpedo_state(torpedo)
                events = copy.deepcopy(self.sim.drain_events())
                self.move_target(-200)
                self.sim._emit_torpedo_state(torpedo)
                self.assertEqual(events, self.sim.drain_events())
                self.assertEqual((aim["x"], aim["y"], aim["z"]), torpedo["initialTarget"])
                self.move_target(z=20)
                if weapon == 2:
                    self.assertIsNotNone(self.sim._pick_radar(torpedo, self.runner.world))
                else:
                    self.assertIsNotNone(self.sim._pick_acoustic(torpedo)["pos"])

    def test_memory_durations_and_cannon_without_tracking(self) -> None:
        build_observation(self.bot, self.sim, self.runner.world)
        bot_ai.act_passive_detection(self.ctx, {})
        memory = copy.deepcopy(self.bot["rl_contact"])
        self.move_target()
        self.runner._time = self.ctx["now"] = 1.0
        build_observation(self.bot, self.sim, self.runner.world)
        bot_ai.act_passive_detection(self.ctx, {})
        self.assertIsNotNone(_contact_target(self.bot, self.sim))
        self.runner._time = 1.001
        self.assertIsNone(_contact_target(self.bot, self.sim))
        self.assertTrue(list(bot_ai._known_targets(self.bot, 29.999, 30)))
        self.assertFalse(list(bot_ai._known_targets(self.bot, 30, 30)))
        self.runner._time = 30
        build_observation(self.bot, self.sim, self.runner.world)
        self.assertEqual(memory, self.bot["rl_contact"])
        self.runner._time = 30.001
        build_observation(self.bot, self.sim, self.runner.world)
        self.assertNotIn("rl_contact", self.bot)
        remembered = memory | {"position": {axis: memory[axis] for axis in ("x", "y", "z")},
                               "observed_at": memory["at"], "tracked": False}
        self.move_target(z=20)
        before = self.firing_state()
        self.assertTrue(self.sim.bot_fire_cannon(self.bot, remembered))
        self.assertNotEqual(before["ammo"], self.firing_state()["ammo"])

    def test_bt_sonar_copies_depth_and_legacy_uses_snapshot(self) -> None:
        self.move_target(z=10)
        bot_ai.act_sonar_ping(self.ctx, {})
        self.assertNotIn("detected_targets", self.bot)
        self.runner._time = self.ctx["now"] = 0.5
        self.sim.step(0, self.runner.world)
        bot_ai.act_passive_detection(self.ctx, {})
        snapshot = copy.deepcopy(self.bot["detected_targets"][self.target["id"]])
        self.assertEqual(self.target["position"], snapshot["position"])
        self.move_target()
        self.target["position"]["y"] = -15
        self.assertEqual(snapshot, self.bot["detected_targets"][self.target["id"]])
        self.bot["next_detect_at"] = 1
        self.sim.update_bot_legacy(self.bot, 0, self.runner.world)
        torpedo = next(iter(self.sim.torpedoes.values()))
        self.assertEqual(tuple(snapshot["position"][axis] for axis in ("x", "y", "z")),
                         torpedo["initialTarget"])
        self.assertIsNone(torpedo["targetId"])

    def test_bt_tick_aa_rejects_hidden_drone_without_cooldown_or_delayed_kill(self) -> None:
        self.bot["external_control"] = False
        self.bot["ai_tree"] = bot_ai.Action("fire_aa_at_human_drone", {})
        self.bot["aa_per_drone"] = {}
        self.target["is_bot"] = False
        drone = {"x": -60, "y": 2, "z": 0, "ownerPlayerId": self.target["id"], "did": 1}
        self.sim.drones[(self.target["id"], 1)] = drone
        before = self.firing_state()
        with patch.object(self.legacy.socketio, "start_background_task") as task:
            self.assertFalse(bot_ai.cond_has_human_drone_in_range(self.ctx, {}))
            self.sim.update_bot(self.bot, 0.0, self.runner.world)
            task.assert_not_called()
        self.assertEqual(before, self.firing_state())
        drone["z"] = 20
        self.assertTrue(bot_ai.cond_has_human_drone_in_range(self.ctx, {}))
        self.sim.update_bot(self.bot, 0.0, self.runner.world)
        self.assertGreater(self.bot["next_aa_at"], self.sim.now())
        self.assertTrue(self.sim._events)

    def test_active_reveal_stays_timed_but_hidden_coordinates_are_not_selected(self) -> None:
        self.move_target(z=0)
        self.runner.world["islands"] = []
        self.sim.bot_sonar_ping(self.bot, self.runner.world)
        self.runner._time = 0.5
        self.sim.step(0.0)
        build_observation(self.bot, self.sim, self.runner.world)
        memory = copy.deepcopy(self.bot["rl_contact"])
        self.assertIn("active_detected_until", memory)
        self.runner.world["islands"] = [{"points": [
            {"x": x, "z": z} for x, z in
            ((-30.2, -1), (-30.1, -1), (-30.1, 1), (-30.2, 1))]}]
        self.move_target(-70)
        self.runner._time = 0.6
        build_observation(self.bot, self.sim, self.runner.world)
        self.assertEqual(memory, self.bot["rl_contact"])
        self.assertEqual(memory["x"], _contact_target(self.bot, self.sim)["position"]["x"])
        self.assertFalse(_contact_target(self.bot, self.sim)["tracked"])
        reveal = self.sim.active_sonar_contacts(self.bot)[0]
        self.assertEqual(memory["x"], reveal["x"])
        self.assertEqual(memory["y"], reveal["y"])
        self.assertEqual(memory["at"], reveal["observed_at"])
        self.assertEqual(memory["active_detected_until"], reveal["active_detected_until"])
        self.assertFalse(reveal["tracked"])


if __name__ == "__main__":
    unittest.main()
