"""Sonar BT autoritaire en headless, sans serveur ni politique apprise."""

import ast
import copy
from pathlib import Path
import random
import unittest
from unittest.mock import patch

import bot_ai
import simulation
from events import SonarPinged
from rl.headless import HeadlessRunner


class BTSonarTest(unittest.TestCase):
    def setUp(self) -> None:
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        self.runner = HeadlessRunner(seed=73)
        self.runner.world.update(islands=[], thermoclines=[])
        self.runner.world["ground"].update(width=10000, depth=10000)
        self.scene()

    def scene(self, distance: float = 1000) -> None:
        self.runner.reset(seed=73)
        sid = self.runner.spawn_bot("destroyer", ai="autodest", position=(0, 0),
                                    rotation=0, team_id="observer")
        target_sid = self.runner.spawn_bot(external_control=True,
            position=(-distance / 10, 0), rotation=0, team_id="enemy")
        self.sim = self.runner.sim
        self.bot = self.sim.bots[sid]
        self.target = self.sim.bots[target_sid]
        # Les miroirs serveur n'ont pas necessairement de sid propre.
        for player in self.sim.players.values():
            player.pop("sid", None)
        self.sim.drain_events()

    def at(self, seconds: float) -> None:
        self.runner._time = seconds
        self.sim.step(0, self.runner.world)

    def test_actual_autodest_wave_arrival_and_no_same_tick_shot(self) -> None:
        for distance in (50, 1000, 4000, 7999, 8000):
            with self.subTest(distance=distance):
                self.scene(distance)
                with patch.object(self.sim, "update_bot_legacy") as fallback:
                    self.at(0)
                    self.assertFalse(self.bot["last_detected_ids"])
                    self.assertNotIn("last_enemy_pos", self.bot["bb"])
                    self.assertFalse(self.sim.torpedoes)
                    self.assertFalse(self.sim.cannon_shells)
                    self.assertEqual(20, self.bot["bb"]["next_sonar_ping_at"])
                    events = [e for e in self.sim.drain_events() if isinstance(e, SonarPinged)]
                    self.assertEqual(1, len(events))
                    arrival = distance / 8000 * 5
                    self.at(arrival - 1e-6)
                    self.assertFalse(self.bot["last_detected_ids"])
                    self.at(arrival)
                    self.assertEqual(distance < 8000, bool(self.bot["last_detected_ids"]))
                    if distance < 8000:
                        self.assertEqual(arrival, self.bot["bb"]["last_enemy_pos"]["t"])
                        self.assertEqual(self.target["position"],
                                         self.bot["detected_targets"][self.target["id"]]["position"])
                    if distance == 1000:
                        self.assertTrue(self.sim.torpedoes)
                    fallback.assert_not_called()

    def test_hidden_contact_freezes_xyz_time_and_expires_without_fresh_ids(self) -> None:
        self.runner.legacy.bots_passive = True
        self.at(0)
        self.at(0.625)
        memory = copy.deepcopy(self.bot["bb"]["last_enemy_pos"])
        self.runner.world["islands"] = [{"points": [
            {"x": x, "z": z} for x, z in ((-60, -20), (-40, -20), (-40, 20), (-60, 20))]}]
        for t, x, y in ((0.7, -110, -10), (2, -150, -30), (5.1, -180, -40)):
            self.target["position"].update(x=x, y=y)
            self.target["control_target_depth_y"] = y
            self.at(t)
            self.assertFalse(self.bot["last_detected_ids"])
            self.assertEqual(memory, self.bot["bb"]["last_enemy_pos"])
            self.assertEqual([], list(bot_ai._known_targets(self.bot, t)))
        self.target["position"].update(x=-100, z=100, y=-20)
        self.target["control_target_depth_y"] = -20
        self.at(6)
        self.assertEqual({self.target["id"]}, self.bot["last_detected_ids"])
        self.assertEqual(6, self.bot["bb"]["last_enemy_pos"]["t"])
        self.at(10.624)
        memory = copy.deepcopy(self.bot["bb"]["last_enemy_pos"])
        self.target["position"].update(x=-200, y=-30)
        self.at(10.625)
        self.assertFalse(self.bot["last_detected_ids"])
        self.assertFalse(self.bot["detected_targets"])
        self.assertEqual(memory, self.bot["bb"]["last_enemy_pos"])
        self.assertEqual([], self.sim.active_sonar_contacts(self.bot))

    def test_layers_roll_once_per_target_no_duplicate_actor_or_sensor(self) -> None:
        self.runner.legacy.bots_passive = True
        self.runner.world["thermoclines"] = [{"depthMeters": depth, "points": [
            {"x": x, "z": z} for x, z in ((-1000, -1000), (1000, -1000),
                                          (1000, 1000), (-1000, 1000))]}
            for depth in (10, 20)]
        second = self.runner.spawn_bot(external_control=True, position=(-200, 0), team_id="enemy")
        with patch("simulation.random.random", side_effect=[0.05, 0.5]) as rng, \
                patch.object(self.sim, "detect_enemies_passive", wraps=self.sim.detect_enemies_passive) as passive, \
                patch.object(self.sim, "active_sonar_contacts", wraps=self.sim.active_sonar_contacts) as active:
            self.at(0)
            self.at(0.5)
            rng.assert_not_called()
            self.at(0.625)
            self.assertEqual(1, rng.call_count)
            self.assertEqual({self.target["id"]}, self.bot["last_detected_ids"])
            for t in (1.25, 2, 4.9):
                self.at(t)
            self.assertEqual(2, rng.call_count)
            self.assertEqual(3, passive.call_count)
            self.assertEqual(6, active.call_count)
        self.assertEqual(1, len(self.sim.active_sonar_contacts(self.bot)))
        self.assertEqual(0.625, self.target["bb"]["pinged_at"])
        self.assertNotIn("pinged_at", self.sim.bots[second].get("bb", {}))
        self.assertEqual(1, sum(isinstance(e, SonarPinged) for e in self.sim.drain_events()))

    def test_bt_cooldowns_remain_configurable(self) -> None:
        ctx = {"bot": self.bot, "world": self.runner.world, "now": 0,
               "deps": self.runner.legacy._get_bt_deps()}
        for cooldown in (10, 20, 30):
            self.bot["bb"] = {}
            params = {} if cooldown == 30 else {"cooldown_s": cooldown}
            self.assertEqual(bot_ai.Status.SUCCESS, bot_ai.act_sonar_ping(ctx, params))
            self.assertEqual(cooldown, self.bot["bb"]["next_sonar_ping_at"])
            self.assertEqual(bot_ai.Status.FAILURE, bot_ai.act_sonar_ping(ctx, {}))
            self.assertFalse(self.bot["last_detected_ids"])
        self.assertEqual(3, len(self.sim._pending_sonar_pings))

    def test_server_dependencies_and_human_without_sid_use_same_wave(self) -> None:
        source = ast.parse(Path(__file__).with_name("server.py").read_text())
        functions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                     and node.name in {"_get_bt_deps", "bot_sonar_ping", "detect_enemies_passive"}]
        deps = self.runner.legacy._get_bt_deps()
        namespace = dict(deps, _BT_DEPS=None, sim=self.sim, simulation=simulation,
                         _bots_passive_get=deps["bots_passive_get"],
                         _ensure_island_bounds=deps["ensure_island_bounds"])
        exec(compile(ast.Module(body=functions, type_ignores=[]), "server.py", "exec"), namespace)
        server_deps = namespace["_get_bt_deps"]()
        self.assertEqual(self.sim.active_sonar_contacts, server_deps["active_sonar_contacts"])
        human = self.sim.players[self.target["sid"]]
        human["is_bot"] = False
        del self.sim.bots[self.target["sid"]]
        self.runner.legacy.bots_passive = True
        with patch.object(self.runner.legacy, "_get_bt_deps", return_value=server_deps), \
                patch.object(self.sim, "update_bot_legacy") as fallback:
            self.at(0)
            self.assertFalse(self.bot["last_detected_ids"])
            self.at(0.624)
            self.assertFalse(self.bot["last_detected_ids"])
            self.at(0.625)
            self.assertEqual({human["id"]}, self.bot["last_detected_ids"])
            snapshot = self.bot["detected_targets"][human["id"]]
            self.assertEqual(human["position"], snapshot["position"])
            self.assertEqual(self.target["sid"], snapshot["sid"])
            fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
