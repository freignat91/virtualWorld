"""Sonar RL reel Sim/headless, selon le ping local humain (sans reseau)."""

import copy
import json
import math
import random
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import bot_ai
from events import SonarPinged
from game_trace import GameTrace
from rl.headless import HeadlessRunner
from rl.rl_control import (
    DESTROYER_OBSERVATION_VERSION, DESTROYER_V1_OBSERVATION_VERSION,
    apply_action, build_observation,
)
from rl.rl_env import SubmarineDuelEnv
from rl.rl_runtime import RuntimeController


class ActiveSonarTest(unittest.TestCase):
    def setUp(self) -> None:
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        self.runner = HeadlessRunner(seed=73)
        self.runner.world.update(islands=[], thermoclines=[])
        self.runner.world["ground"].update(width=10000, depth=10000)
        self.scene()

    def scene(self, distance_m: float = 1000.0) -> None:
        self.runner.reset(seed=73)
        sid = self.runner.spawn_bot(
            "destroyer", external_control=True, position=(0.0, 0.0),
            rotation=0.0, team_id="observer")
        target_sid = self.runner.spawn_bot(
            external_control=True, position=(-distance_m / 10, 0.0),
            rotation=0.0, team_id="enemy")
        self.bot = self.runner.sim.bots[sid]
        self.bot["rl_control_version"] = DESTROYER_OBSERVATION_VERSION
        self.target = self.runner.sim.bots[target_sid]

    def observe(self) -> np.ndarray:
        return build_observation(self.bot, self.runner.sim, self.runner.world)

    def at(self, seconds: float) -> None:
        # Horloge exacte pour tester les frontieres sans erreur d'accumulation.
        self.runner._time = seconds
        self.runner.sim.step(0.0, self.runner.world)

    def move_target(self, x: float, z: float = 0.0, y: float = -3.0) -> None:
        self.target["position"] = {"x": x, "y": y, "z": z}
        self.target["control_target_depth_y"] = y
        self.runner.sim.players[self.target["sid"]]["position"] = dict(self.target["position"])

    def ping(self) -> dict:
        return apply_action(self.bot, self.runner.sim, [2, 1, 0, 0, 1, 0])

    def test_wavefront_distances_and_strict_expiry_both_schemas(self) -> None:
        for version, index in ((DESTROYER_V1_OBSERVATION_VERSION, 14),
                               (DESTROYER_OBSERVATION_VERSION, 18)):
            for distance, arrival in ((50, 0.03125), (1000, 0.625), (4000, 2.5), (7999, 4.999375)):
                with self.subTest(version=version, distance=distance):
                    self.scene(distance)
                    self.bot["rl_control_version"] = version
                    action = [2, 1, 1, 0, 1] + ([0] if index == 18 else [])
                    result = apply_action(self.bot, self.runner.sim, action)
                    self.assertTrue(result["sonar_pinged"])
                    self.assertTrue(result["weapon_fired"])
                    self.assertFalse(result["weapon_invalid"])
                    torpedo = next(iter(self.runner.sim.torpedoes.values()))
                    self.assertIsNone(torpedo["initialTarget"])
                    self.assertIsNone(torpedo["targetId"])
                    np.testing.assert_array_equal(np.zeros(7), self.observe()[index:index + 7])
                    self.at(arrival - 1e-6)
                    self.assertEqual(0, self.observe()[index])
                    self.at(arrival)
                    self.assertEqual(1, self.observe()[index])
                    self.assertEqual(self.target["id"], self.bot["rl_contact"]["id"])
                    self.assertEqual(arrival + 10, self.bot["rl_contact"]["active_detected_until"])
        for distance in (8000, 8001):
            self.scene(distance)
            self.ping()
            for t in (4.999, 5.0, 5.1):
                self.at(t)
                self.assertEqual(0, self.observe()[18])
            self.assertFalse(self.runner.sim._pending_sonar_pings)

    def test_current_target_and_fixed_origin_cone(self) -> None:
        self.ping()
        self.move_target(-400)
        self.at(0.625)
        self.assertEqual(0, self.observe()[18])
        self.assertNotIn("rl_contact", self.bot)
        # Le bateau emetteur peut tourner : le cone emis reste fixe.
        self.bot["rotation"] = math.pi
        self.at(2.5)
        self.assertEqual(1, self.observe()[18])
        self.assertEqual(-400, self.bot["rl_contact"]["x"])
        self.scene(9000)
        self.ping()
        self.at(2.0)
        self.move_target(-100)
        self.at(2.1)
        self.assertEqual(1, self.observe()[18])
        self.scene()
        self.ping()
        self.move_target(100)
        self.at(1.0)
        self.assertEqual(0, self.observe()[18])
        self.move_target(-100)
        self.at(1.1)
        self.assertEqual(1, self.observe()[18])

    def test_bow_and_cone_edges_at_multiple_headings_and_depths(self) -> None:
        for heading in range(0, 360, 45):
            for distance_m in (2000, 3000):
                for depth_y in (-0.2, -25.0):
                    for offset in (0, -14.99, 14.99, -15.01, 15.01):
                        for control in ("bt", "rl"):
                            with self.subTest(heading=heading, distance_m=distance_m,
                                              depth_y=depth_y, offset=offset, control=control):
                                self.scene(distance_m)
                                self.bot["rotation"] = math.radians(heading)
                                bearing = math.radians(heading + offset)
                                self.move_target(-math.cos(bearing) * distance_m / 10,
                                                 math.sin(bearing) * distance_m / 10,
                                                 depth_y)
                                if control == "bt":
                                    bot_ai.act_sonar_ping({"bot": self.bot, "now": 0,
                                        "world": self.runner.world,
                                        "deps": self.runner.legacy._get_bt_deps()}, {})
                                else:
                                    self.ping()
                                self.assertEqual([], self.runner.sim.active_sonar_contacts(self.bot))
                                self.at(distance_m / 1600 + 0.01)
                                contacts = self.runner.sim.active_sonar_contacts(self.bot)
                                expected = [self.target["id"]] if abs(offset) < 15 else []
                                self.assertEqual(expected, [c["id"] for c in contacts])
                                self.assertEqual(bool(expected), bool(self.observe()[18]))

    def test_reveal_tracks_then_expires_without_hidden_aim_or_extension(self) -> None:
        self.ping()
        self.at(0.625)
        self.assertEqual(1, self.observe()[18])
        until = self.bot["rl_contact"]["active_detected_until"]
        for t in (1.0, 2.0, 4.9):
            self.at(t)
            self.assertEqual(1, self.observe()[18])
            self.assertEqual(until, self.bot["rl_contact"]["active_detected_until"])
        self.move_target(1800, 100, -20)
        self.at(until - 0.01)
        self.assertEqual(1, self.observe()[18])
        self.assertEqual((1800, 100, -20), tuple(self.bot["rl_contact"][k] for k in ("x", "z", "y")))
        self.move_target(1900, 200, -30)
        self.at(until)
        self.assertEqual(0, self.observe()[18])
        self.assertEqual(1800, self.bot["rl_contact"]["x"])
        # Meme un souvenir de moins d'une seconde ne suit pas la cible expiree.
        result = apply_action(self.bot, self.runner.sim, [2, 1, 1, 0, 0, 0])
        self.assertTrue(result["weapon_fired"])
        torpedo = next(iter(self.runner.sim.torpedoes.values()))
        self.assertIsNone(torpedo["initialTarget"])
        self.assertIsNone(torpedo["targetId"])
        self.at(until + 30)
        np.testing.assert_array_equal(np.zeros(7), self.observe()[18:25])
        self.assertNotIn("rl_contact", self.bot)

    def test_thermocline_roll_once_per_target_and_dynamic_crossing(self) -> None:
        self.runner.world["thermoclines"] = [{"depthMeters": 10, "points": [
            {"x": x, "z": z} for x, z in ((-1000, -1000), (1000, -1000), (1000, 1000), (-1000, 1000))]}]
        for roll, detected in ((0.05, True), (0.5, False)):
            self.scene()
            with patch("simulation.random.random", return_value=roll) as rng:
                self.ping()
                self.at(0.5)
                rng.assert_not_called()
                for t in (0.625, 1.0, 2.0, 4.9):
                    self.at(t)
                    self.assertEqual(detected, bool(self.observe()[18]))
                self.assertEqual(1, rng.call_count)
                if not detected:
                    self.move_target(-100, y=-0.2)
                    self.at(4.95)
                    self.assertEqual(1, self.observe()[18])
                    self.assertEqual(1, rng.call_count)

    def test_reveal_freezes_hidden_xyz_and_time_then_reacquires(self) -> None:
        self.ping()
        self.at(0.625)
        self.observe()
        original = self.runner.sim.active_sonar_contacts(self.bot)[0]
        self.runner.world["islands"] = [{"points": [
            {"x": x, "z": z} for x, z in ((-60, -20), (-40, -20), (-40, 20), (-60, 20))]}]
        for t, x, y in ((0.7, -110, -10), (2.0, -150, -30), (5.1, -180, -40)):
            self.move_target(x, y=y)
            self.at(t)
            self.observe()
            contact = self.runner.sim.active_sonar_contacts(self.bot)[0]
            self.assertFalse(contact["tracked"])
            for key in ("x", "y", "z", "observed_at", "active_detected_until"):
                self.assertEqual(original[key], contact[key])
            self.assertEqual(0.625, self.bot["rl_contact"]["at"])
            self.assertFalse(self.bot["rl_contact_tracked"])
        # Le retour en LOS autorise le suivi, sans nouveau ping ni prolongation.
        self.move_target(-100, z=100, y=-20)
        self.at(6.0)
        self.observe()
        contact = self.runner.sim.active_sonar_contacts(self.bot)[0]
        self.assertTrue(contact["tracked"])
        self.assertEqual((-100, -20, 100), tuple(contact[k] for k in ("x", "y", "z")))
        self.assertEqual(original["active_detected_until"], contact["active_detected_until"])
        self.at(original["active_detected_until"])
        self.assertEqual([], self.runner.sim.active_sonar_contacts(self.bot))

    def test_ping_event_copies_actual_emitter_depth(self) -> None:
        self.bot["position"]["y"] = -17.5
        self.assertEqual([], self.runner.sim.bot_sonar_ping(self.bot, self.runner.world))
        event = next(e for e in self.runner.sim.drain_events() if isinstance(e, SonarPinged))
        self.bot["position"]["y"] = -25
        self.assertEqual(-17.5, event.y)
        self.assertEqual((8000, 15000), (event.range_m, event.reveal_m))

    def test_los_reveal_range_and_target_eligibility(self) -> None:
        self.bot["boat"]["activeSonar"]["reveal"] = 500
        self.ping()
        self.at(0.625)
        self.assertEqual(0, self.observe()[18])
        self.bot["position"]["x"] = -60
        self.at(0.7)
        self.assertEqual(1, self.observe()[18])
        for barrier in ("island", "thin_island", "ally", "sunk"):
            self.scene()
            self.runner.world["islands"] = []
            if barrier == "island":
                self.runner.world["islands"] = [{"points": [
                    {"x": x, "z": z} for x, z in ((-60, -20), (-40, -20), (-40, 20), (-60, 20))]}]
            elif barrier == "thin_island":
                self.runner.world["islands"] = [{"points": [
                    {"x": x, "z": z} for x, z in (
                        (-1.02, -20), (-1.01, -20), (-1.01, 20), (-1.02, 20))]}]
            elif barrier == "ally":
                self.target["team_id"] = self.bot["team_id"]
            else:
                self.target["sunk"] = True
            self.ping()
            self.at(1.0)
            self.assertEqual(0, self.observe()[18])
            if barrier == "thin_island":
                self.runner.world["islands"] = []
                self.at(1.1)
                self.assertEqual(1, self.observe()[18])

    def test_event_cooldown_reset_and_human_target(self) -> None:
        # Les humains n'ont pas necessairement de champ sid dans leur objet.
        sid = self.target["sid"]
        human = self.runner.sim.players[sid]
        human["is_bot"] = False
        human.pop("sid", None)
        del self.runner.sim.bots[sid]
        self.assertTrue(self.ping()["sonar_pinged"])
        self.assertEqual(30, self.bot["bb"]["next_sonar_ping_at"])
        events = [e for e in self.runner.sim.drain_events() if isinstance(e, SonarPinged)]
        self.assertEqual(1, len(events))
        self.assertEqual((8000, 15000, 30), (events[0].range_m, events[0].reveal_m, events[0].cone_deg))
        self.at(0.625)
        self.assertEqual(1, self.observe()[18])
        self.assertEqual(1, len(self.runner.sim.active_sonar_contacts(self.bot)))
        self.assertFalse(self.ping()["sonar_pinged"])
        self.assertFalse(any(isinstance(e, SonarPinged) for e in self.runner.sim.drain_events()))
        self.at(29.99)
        self.assertFalse(self.ping()["sonar_pinged"])
        self.at(30)
        self.assertTrue(self.ping()["sonar_pinged"])
        old_bot = self.bot
        self.scene()
        self.assertFalse(self.runner.sim._pending_sonar_pings)
        self.assertFalse(self.runner.sim._sonar_reveals)
        self.assertEqual([], self.runner.sim.active_sonar_contacts(old_bot))
        self.at(1.0)
        np.testing.assert_array_equal(np.zeros(7), self.observe()[18:25])

    def test_live_runtime_uses_shared_timing(self) -> None:
        observations = []

        class Policy:
            def predict(self, observation, **kwargs):
                observations.append((runner.sim.now(), observation.copy()))
                return np.array([2, 1, 1, 0, 1, 0]), None

        runner = self.runner
        self.bot["rl_controller"] = RuntimeController(Policy())
        for t in (0, 0.25, 0.5, 0.625):
            self.at(t)
        self.assertEqual(1, len(runner.sim.torpedoes))
        torpedo = next(iter(runner.sim.torpedoes.values()))
        self.assertIsNone(torpedo["initialTarget"])
        self.assertIsNone(torpedo["targetId"])
        self.at(0.75)
        self.assertEqual(1, len(runner.sim.torpedoes))
        self.assertEqual([0, 0, 0, 1], [obs[18] for _, obs in observations])

    def test_distinct_targets_roll_once_and_reset_clears_pending_and_revealed(self) -> None:
        self.runner.world["thermoclines"] = [{"depthMeters": 10, "points": [
            {"x": x, "z": z} for x, z in ((-1000, -1000), (1000, -1000), (1000, 1000), (-1000, 1000))]}]
        second_sid = self.runner.spawn_bot(
            external_control=True, position=(-200.0, 0.0), team_id="enemy")
        with patch("simulation.random.random", side_effect=[0.05, 0.5]) as rng:
            self.ping()
            self.at(0.625)
            self.assertEqual(1, rng.call_count)
            self.at(1.25)
            self.at(2.0)
            self.assertEqual(2, rng.call_count)
        contacts = self.runner.sim.active_sonar_contacts(self.bot)
        self.assertEqual([self.target["id"]], [c["id"] for c in contacts])
        self.assertNotIn("pinged_at", self.runner.sim.bots[second_sid].get("bb", {}))
        old_bot = self.bot
        self.assertTrue(self.runner.sim._pending_sonar_pings)
        self.assertTrue(self.runner.sim._sonar_reveals)
        self.scene()
        self.assertFalse(self.runner.sim._pending_sonar_pings)
        self.assertFalse(self.runner.sim._sonar_reveals)
        self.assertEqual([], self.runner.sim.active_sonar_contacts(old_bot))
        self.at(1.25)
        np.testing.assert_array_equal(np.zeros(7), self.observe()[18:25])

    def test_pending_emitter_removal_and_revealed_target_removal(self) -> None:
        self.ping()
        del self.runner.sim.bots[self.bot["sid"]]
        self.at(1.0)
        self.assertFalse(self.runner.sim._pending_sonar_pings)
        self.assertFalse(self.runner.sim._sonar_reveals)
        self.scene()
        self.ping()
        self.at(0.625)
        self.assertEqual(1, self.observe()[18])
        del self.runner.sim.bots[self.target["sid"]]
        del self.runner.sim.players[self.target["sid"]]
        self.at(0.7)
        self.assertFalse(self.runner.sim._sonar_reveals)
        self.assertEqual(0, self.observe()[18])

    def test_same_id_replacement_does_not_revive_stale_sonar(self) -> None:
        for role in ("emitter", "target", "human"):
            for acquired in (False, True):
                with self.subTest(role=role, acquired=acquired):
                    self.scene()
                    sim = self.runner.sim
                    if role == "human":
                        sid = self.target["sid"]
                        self.target = sim.players[sid]
                        self.target["is_bot"] = False
                        del sim.bots[sid]
                    self.ping()
                    if acquired:
                        self.at(0.625)
                        self.assertEqual(1, len(sim.active_sonar_contacts(self.bot)))
                    old = self.bot if role == "emitter" else self.target
                    sid = self.bot["sid"] if role == "emitter" else next(
                        key for key, value in sim.players.items() if value["id"] == old["id"])
                    registry = sim.players if role == "human" else sim.bots
                    replacement = copy.deepcopy(old)
                    replacement["position"] = {"x": 2000, "y": -3, "z": 0}
                    registry[sid] = replacement
                    # Le miroir conserve le meme ID ; seul l'objet canonique change.
                    self.assertEqual([], sim.active_sonar_contacts(self.bot))
                    self.at(1.0)
                    self.assertFalse(sim._sonar_reveals)
                    if role == "emitter":
                        self.assertFalse(sim._pending_sonar_pings)
                        self.assertEqual([], sim.active_sonar_contacts(replacement))

    def test_runtime_and_trace_reveal_survive_wave_until_original_deadline(self) -> None:
        observations = []

        class Policy:
            def predict(self, observation, **kwargs):
                observations.append(float(observation[18]))
                return np.array([2, 1, 0, 0, 1, 0]), None

        self.bot["rl_controller"] = RuntimeController(Policy())
        server = SimpleNamespace(passive_sonar_beacons={}, sim_tick_multiplier=1,
                                 bots_passive=False)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            trace = GameTrace(enabled=True, path=path)
            self.addCleanup(trace.close)
            for t in (0, 0.625, 1.0, 4.9, 5.0, 5.25, 10.375, 10.625):
                self.at(t)
                trace.observe(self.runner.sim, server, 0.0)
                if 0.625 <= t < 10.625:
                    self.assertEqual(10.625, next(iter(
                        self.runner.sim._sonar_reveals.values()))["until"])
                    self.assertEqual(0.625, self.target["bb"]["pinged_at"])
            self.assertTrue(trace.enabled)
            trace.close()
            contacts = [row for row in map(json.loads, path.read_text().splitlines())
                        if row["type"] == "sonar_contact"]
        self.assertEqual([0, 1, 1, 1, 1, 1, 0], observations)
        self.assertEqual([(0.625, True), (10.625, False)],
                         [(row["sim_time"], row["data"]["acquired"]) for row in contacts])

    def test_environment_rewards_contact_once_and_resets(self) -> None:
        env = SubmarineDuelEnv(agent_boat_type="destroyer",
                               control_version=DESTROYER_OBSERVATION_VERSION, seed=73)
        self.addCleanup(env.close)
        env.reset(seed=73)
        self.runner = env.runner
        self.runner.world.update(islands=[], thermoclines=[])
        self.bot = env._agent()
        self.bot["position"] = {"x": 0.0, "y": -0.2, "z": 0.0}
        self.bot["rotation"] = 0.0
        self.target = self.runner.sim.bots[env.opponent_sid]
        self.target["external_control"] = True
        self.move_target(-100)
        self.bot.pop("rl_contact", None)
        env._had_contact = False
        rewards = []
        for _ in range(48):
            obs, reward, terminated, truncated, _ = env.step([2, 1, 0, 0, 1, 0])
            self.assertFalse(terminated or truncated)
            rewards.append(reward)
        self.assertEqual(1, env._stats["contacts"])
        self.assertEqual(1, env._stats["sonars"])
        self.assertEqual(0, obs[18])
        self.assertAlmostEqual(48 * env.reward_cfg["decision_cost"]
                               + env.reward_cfg["sonar_pinged"] + env.reward_cfg["new_contact"], sum(rewards))
        env.reset(seed=73)
        self.assertFalse(env.runner.sim._pending_sonar_pings)
        self.assertFalse(env.runner.sim._sonar_reveals)
        self.assertEqual(0, env._stats["contacts"])


class ServerShapedActiveSonarTest(ActiveSonarTest):
    """Meme Sim, mais objets distincts comme server.spawn_bot, sans serveur."""

    def scene(self, distance_m: float = 1000.0) -> None:
        super().scene(distance_m)
        for sid, bot in self.runner.sim.bots.items():
            self.runner.sim.players[sid] = {
                key: copy.deepcopy(bot[key]) for key in
                ("id", "boatType", "boat", "position", "rotation", "team_id")}
            self.runner.sim.players[sid]["is_bot"] = True
            bot.pop("is_bot", None)
            self.assertIsNot(bot, self.runner.sim.players[sid])
            self.assertEqual(bot["id"], self.runner.sim.players[sid]["id"])


if __name__ == "__main__":
    unittest.main()
