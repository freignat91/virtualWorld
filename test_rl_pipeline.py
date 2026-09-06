"""Tests de non-régression du pipeline d'entraînement RL."""

import unittest
from unittest.mock import patch

import numpy as np

from headless import HeadlessRunner
from rl_control import OBS_DIM, apply_action, build_observation


NEUTRAL_ACTION = np.array([2, 1, 2, 0, 0], dtype=np.int64)


class ExternalControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = HeadlessRunner(seed=7)
        self.agent_sid = self.runner.spawn_bot(
            external_control=True, ai=None, position=(100.0, 80.0),
            rotation=0.0, team_id="agent")
        self.opponent_sid = self.runner.spawn_bot(
            external_control=True, ai=None, position=(120.0, 80.0),
            rotation=3.14, team_id="opponent")

    def test_external_bot_has_no_behavior_tree_or_automatic_fire(self) -> None:
        agent = self.runner.legacy.bots[self.agent_sid]
        opponent = self.runner.legacy.bots[self.opponent_sid]
        self.assertIsNone(agent["ai_tree"])
        opponent["speed"] = opponent["max_speed_us"]
        self.runner.legacy.players[self.opponent_sid]["speed"] = opponent["speed"]
        build_observation(agent, self.runner.sim, self.runner.world)
        for _ in range(200):
            apply_action(agent, self.runner.sim, NEUTRAL_ACTION)
            self.runner.step(0.05)
        self.assertEqual({}, self.runner.legacy.torpedoes_server)


class GymEnvironmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = HeadlessRunner(seed=7)
        self.agent_sid = self.runner.spawn_bot(
            external_control=True, ai=None, position=(100.0, 80.0),
            rotation=0.0, team_id="agent")
        self.opponent_sid = self.runner.spawn_bot(
            external_control=True, ai=None, position=(120.0, 80.0),
            rotation=3.14, team_id="opponent")

    def test_environment_reset_and_truncation(self) -> None:
        from stable_baselines3.common.env_checker import check_env
        from rl_env import SubmarineDuelEnv

        env = SubmarineDuelEnv(
            seed=11, frame_skip=5, max_physics_steps=10,
            spawn_min_m=400.0, spawn_max_m=700.0)
        try:
            with self.assertNoLogs(level="ERROR"):
                check_env(env, warn=True)
                observation, info = env.reset(seed=11)
                self.assertEqual((OBS_DIM,), observation.shape)
                self.assertIn("opponent", info)
                terminated = truncated = False
                while not (terminated or truncated):
                    observation, reward, terminated, truncated, info = env.step(NEUTRAL_ACTION)
            self.assertTrue(terminated or truncated)
            self.assertIn("outcome", info)
        finally:
            env.close()

    def test_recurrent_ppo_smoke_training(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl_env import SubmarineDuelEnv

        env = SubmarineDuelEnv(
            seed=13, frame_skip=2, max_physics_steps=20,
            spawn_min_m=400.0, spawn_max_m=700.0)
        try:
            model = RecurrentPPO(
                "MlpLstmPolicy", env, n_steps=8, batch_size=8, n_epochs=1,
                policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                device="cpu", seed=13, verbose=0)
            model.learn(total_timesteps=16)
            observation, _ = env.reset(seed=14)
            action, _ = model.predict(observation, deterministic=True)
            self.assertTrue(env.action_space.contains(action))
        finally:
            env.close()

    def test_destroyer_opponent_is_spawned_explicitly(self) -> None:
        from rl_env import SubmarineDuelEnv

        env = SubmarineDuelEnv(
            opponents=[{"boat_type": "destroyer", "ai": "autodest", "weight": 1.0}],
            seed=17, frame_skip=2, max_physics_steps=10,
            spawn_min_m=400.0, spawn_max_m=700.0)
        try:
            _, info = env.reset(seed=17)
            self.assertEqual("submarine", env._agent()["boatType"])
            self.assertEqual("destroyer", env._opponent()["boatType"])
            self.assertEqual("autodest", env._opponent()["ai_name"])
            self.assertEqual("bt:destroyer/autodest", info["opponent"])
            self.assertEqual("destroyer", info["opponent_boat_type"])
        finally:
            env.close()

    def test_invalid_opponent_configuration_is_rejected(self) -> None:
        from rl_env import SubmarineDuelEnv

        with self.assertRaises(ValueError):
            SubmarineDuelEnv(opponents=[])
        with self.assertRaises(ValueError):
            SubmarineDuelEnv(
                opponents=[{"boat_type": "carrier", "ai": "default", "weight": 1.0}])
        with self.assertRaises(ValueError):
            SubmarineDuelEnv(
                opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 0.0}])

    def test_weighted_opponent_sequence_is_seeded(self) -> None:
        from rl_env import SubmarineDuelEnv

        opponents = [
            {"boat_type": "submarine", "ai": "autosub", "weight": 1.0},
            {"boat_type": "destroyer", "ai": "autodest", "weight": 1.0},
        ]
        sequences = []
        for _ in range(2):
            env = SubmarineDuelEnv(
                opponents=opponents, seed=23, frame_skip=1, max_physics_steps=1,
                spawn_min_m=400.0, spawn_max_m=700.0)
            try:
                sequences.append([
                    env.reset(seed=23 + index)[1]["opponent_boat_type"]
                    for index in range(20)
                ])
            finally:
                env.close()
        self.assertEqual(sequences[0], sequences[1])
        self.assertEqual({"submarine", "destroyer"}, set(sequences[0]))

    def test_unknown_behavior_tree_fails_on_reset(self) -> None:
        from rl_env import SubmarineDuelEnv

        env = SubmarineDuelEnv(
            opponents=[{"boat_type": "submarine", "ai": "missing", "weight": 1.0}])
        try:
            with self.assertRaises(ValueError):
                env.reset(seed=19)
        finally:
            env.close()

    def test_destroyer_cannon_consumes_ammo_and_damages_bot(self) -> None:
        destroyer_sid = self.runner.spawn_bot(
            boat_type="destroyer", external_control=True, ai=None,
            position=(100.0, 100.0), rotation=3.14, team_id="destroyer")
        target_sid = self.runner.spawn_bot(
            boat_type="submarine", external_control=True, ai=None,
            position=(105.0, 100.0), rotation=0.0, team_id="submarine")
        destroyer = self.runner.legacy.bots[destroyer_sid]
        target = self.runner.legacy.bots[target_sid]
        target["position"]["y"] = -0.2
        target["control_target_depth_y"] = -0.2
        self.runner.legacy.players[target_sid]["position"]["y"] = -0.2

        with patch("simulation.random.random", return_value=0.0):
            self.assertTrue(self.runner.sim.bot_fire_cannon(
                destroyer, self.runner.legacy.players[target_sid]))
        self.assertEqual(49, self.runner.legacy.cannon_ammo[destroyer_sid]["cannon"])
        self.assertEqual(100.0, target["integrity"])
        self.runner.step(0.05)
        self.assertEqual(100.0, target["integrity"])
        self.runner.step(0.1)
        self.assertEqual(70.0, target["integrity"])

    def test_active_sonar_reports_each_bot_once(self) -> None:
        destroyer_sid = self.runner.spawn_bot(
            boat_type="destroyer", external_control=True, ai=None,
            position=(100.0, 100.0), rotation=np.pi, team_id="destroyer")
        target_sid = self.runner.spawn_bot(
            boat_type="submarine", external_control=True, ai=None,
            position=(105.0, 100.0), rotation=0.0, team_id="submarine")
        target = self.runner.legacy.bots[target_sid]
        target["position"]["y"] = -0.2
        self.runner.legacy.players[target_sid]["position"]["y"] = -0.2

        detected = self.runner.sim.bot_sonar_ping(
            self.runner.legacy.bots[destroyer_sid], self.runner.world)
        self.assertEqual([target["id"]], [item["id"] for item in detected])

    def test_observation_keeps_only_last_detected_position(self) -> None:
        agent = self.runner.legacy.bots[self.agent_sid]
        opponent = self.runner.legacy.bots[self.opponent_sid]
        hidden = build_observation(agent, self.runner.sim, self.runner.world)
        self.assertEqual((OBS_DIM,), hidden.shape)
        self.assertEqual(0.0, hidden[10])
        self.assertTrue(np.allclose(hidden[11:17], 0.0))

        opponent["speed"] = opponent["max_speed_us"]
        self.runner.legacy.players[self.opponent_sid]["speed"] = opponent["speed"]
        detected = build_observation(agent, self.runner.sim, self.runner.world)
        self.assertEqual(1.0, detected[10])
        last_x = agent["rl_contact"]["x"]

        opponent["speed"] = 0.0
        opponent["position"]["x"] += 10.0
        sync = self.runner.legacy.players[self.opponent_sid]
        sync["speed"] = 0.0
        sync["position"] = dict(opponent["position"])
        remembered = build_observation(agent, self.runner.sim, self.runner.world)
        self.assertEqual(0.0, remembered[10])
        self.assertEqual(last_x, agent["rl_contact"]["x"])

    def test_weapon_requires_a_fresh_contact(self) -> None:
        agent = self.runner.legacy.bots[self.agent_sid]
        result = apply_action(agent, self.runner.sim, [2, 1, 2, 1, 0])
        self.assertFalse(result["weapon_fired"])
        self.assertTrue(result["weapon_invalid"])
        self.assertEqual({}, self.runner.legacy.torpedoes_server)


if __name__ == "__main__":
    unittest.main()
