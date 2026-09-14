"""Tests de non-régression du pipeline d'entraînement RL."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from rl.headless import HeadlessRunner
from rl.rl_control import (
    DESTROYER_ACTION_NVECS,
    DESTROYER_OBS_DIM,
    DESTROYER_OBSERVATION_VERSION,
    DESTROYER_V3_OBS_DIM,
    DESTROYER_V1_ACTION_NVECS,
    DESTROYER_V1_OBS_DIM,
    OBS_DIM,
    apply_action,
    build_observation,
)


NEUTRAL_ACTION = np.array([2, 1, 2, 0, 0], dtype=np.int64)
DESTROYER_NEUTRAL_ACTION = np.array([2, 1, 0, 0, 0], dtype=np.int64)


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
        from rl.rl_env import SubmarineDuelEnv

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

    def test_final_interfaces_reward_sinking_the_opponent(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

        for boat_type, version, action in (
                ("submarine", "sub_duel_v2", [2, 1, 2, 0, 0]),
                ("destroyer", "destroyer_duel_v4", [2, 1, 0, 0, 0])):
            with self.subTest(boat_type=boat_type):
                env = SubmarineDuelEnv(
                    agent_boat_type=boat_type, control_version=version,
                    frame_skip=1, reward={
                        "win": 7.0, "damage_dealt": 0.0, "decision_cost": 0.0,
                    })
                try:
                    env.reset(seed=41)
                    opponent = env._opponent()
                    agent_id = env._agent()["id"]
                    env.runner.step = lambda _dt: env.runner.sim.sink_bot(
                        env.opponent_sid, opponent, agent_id)
                    _, reward, terminated, truncated, info = env.step(action)
                    self.assertEqual(7.0, reward)
                    self.assertTrue(terminated)
                    self.assertFalse(truncated)
                    self.assertEqual("win", info["outcome"])
                finally:
                    env.close()

    def test_no_target_and_stationary_penalties_are_reported(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

        def run(reward):
            env = SubmarineDuelEnv(
                seed=31, frame_skip=1, max_physics_steps=1,
                spawn_min_m=1800.0, spawn_max_m=2000.0, reward=reward)
            try:
                env.reset(seed=31)
                return env.step(np.array([2, 1, 2, 2, 0], dtype=np.int64))
            finally:
                env.close()

        _, baseline, _, truncated, baseline_info = run({})
        _, penalized, _, _, info = run({
            "weapon_without_acquisition": -0.4,
            "stationary_unengaged": -0.2,
        })
        self.assertTrue(truncated)
        self.assertAlmostEqual(baseline - 0.5, penalized)
        self.assertEqual(0, info["unacquired_weapons"])
        self.assertEqual(1, info["invalid_weapons"])
        self.assertEqual(1, info["stationary_decisions"])
        self.assertEqual(1, info["stationary_unengaged_decisions"])
        self.assertEqual(0, baseline_info["acquired_weapons"])

    def test_lure_without_detected_torpedo_uses_dedicated_penalty(self) -> None:
        from rl.rl_env import DEFAULT_REWARD, SubmarineDuelEnv

        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["lure_without_threat"] = -0.1
        for detected, expected in ((False, -0.1), (True, 0.0)):
            with self.subTest(detected=detected):
                env = SubmarineDuelEnv(frame_skip=1, reward=reward)
                try:
                    env.reset(seed=43)
                    env._agent()["rl_torpedo_detected"] = detected
                    with patch.object(env, "_predict_opponent"):
                        _, value, _, _, _ = env.step(np.array([2, 1, 2, 0, 1]))
                    self.assertTrue(env.runner.sim.lures)
                    self.assertEqual(expected, value)
                finally:
                    env.close()

    def test_behavior_pilot_configs_create_matching_environments(self) -> None:
        from rl.train_ai import load_config, make_env

        root = Path(__file__).resolve().parent
        expected_shapes = {
            "aisub_v16_acquisition.json": (32,),
            "aisub_v16b_acquisition_strong.json": (32,),
            "aidest_v8_mobility.json": (DESTROYER_V3_OBS_DIM,),
        }
        for filename, shape in expected_shapes.items():
            with self.subTest(config=filename):
                config = load_config(str(root / "configs" / filename))
                env = make_env(
                    config, seed=int(config["training"]["seed"]), stage="scripted",
                    curriculum_decisions=0, league_dir=root / "models_rl" / "unused")()
                try:
                    observation, _ = env.reset(seed=int(config["training"]["seed"]))
                    self.assertEqual(shape, observation.shape)
                    self.assertTrue(env.observation_space.contains(observation))
                finally:
                    env.close()

    def test_recurrent_ppo_smoke_training(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv

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

    def test_resume_updates_rollout_discount_parameters(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv
        from rl.train_ai import configure_loaded_model

        env = SubmarineDuelEnv(seed=13, max_physics_steps=20)
        try:
            model = RecurrentPPO(
                "MlpLstmPolicy", env, n_steps=8, batch_size=8, n_epochs=1,
                gamma=0.99, gae_lambda=0.95,
                policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                device="cpu", seed=13, verbose=0)
            with TemporaryDirectory() as directory:
                path = Path(directory) / "policy.zip"
                model.save(path)
                loaded = RecurrentPPO.load(path, env=env, device="cpu")
                configure_loaded_model(loaded, {"training": {
                    "n_steps": 8, "batch_size": 8, "learning_rate": 0.00005,
                    "n_epochs": 1, "gamma": 0.9, "gae_lambda": 0.8,
                    "clip_range": 0.2, "ent_coef": 0.003,
                    "vf_coef": 0.5, "max_grad_norm": 0.5,
                }})
                self.assertEqual(0.9, loaded.rollout_buffer.gamma)
                self.assertEqual(0.8, loaded.rollout_buffer.gae_lambda)
                loaded.rollout_buffer.reset()
                self.assertEqual(loaded.gamma, loaded.rollout_buffer.gamma)
                self.assertEqual(loaded.gae_lambda, loaded.rollout_buffer.gae_lambda)
                loaded.learn(total_timesteps=8)
        finally:
            env.close()

    def test_match_score_evaluation_saves_best_model(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv
        from rl.train_ai import (
            MatchScoreEvalCallback,
            behavior_gate_report,
            match_score,
            validate_behavior_gates,
            weighted_match_score,
        )

        low = {"episodes": 10, "wins": 2, "losses": 6, "draws": 2}
        high = {"episodes": 10, "wins": 6, "losses": 2, "draws": 2}
        self.assertEqual(0.3, match_score(low))
        self.assertAlmostEqual(
            0.6, weighted_match_score(((low, 0.25), (high, 0.75))))
        with self.assertRaises(ValueError):
            match_score({"episodes": 10, "wins": 4, "losses": 4, "draws": 1})
        with self.assertRaises(ValueError):
            weighted_match_score(((low, -1.0),))
        gate_config = {"evaluation": {"behavior_gates": {
            "max_unacquired_weapon_fraction": 0.05,
            "max_stationary_unengaged_fraction": 0.35,
            "min_mean_acquired_weapons": 0.5,
        }}}
        details = [{"selection_weight": 1.0, "unacquired_weapon_fraction": 0.1,
                    "stationary_unengaged_fraction": 0.2, "mean_acquired_weapons": 1.0}]
        behavior = behavior_gate_report(gate_config, details)
        self.assertFalse(behavior["passed"])
        self.assertEqual(["max_unacquired_weapon_fraction"], behavior["failures"])
        with self.assertRaises(ValueError):
            validate_behavior_gates({"evaluation": {"behavior_gates": {"unknown": 1}}})

        env = SubmarineDuelEnv(
            seed=26, frame_skip=2, max_physics_steps=20,
            spawn_min_m=400.0, spawn_max_m=700.0)
        config = {
            "env": {
                "agent_boat_type": "submarine", "max_physics_steps": 20,
                "frame_skip": 2, "spawn_min_m": 400.0, "spawn_max_m": 700.0,
            },
            "reward": {},
            "evaluation": {
                "map_name": "testCombats",
                "opponents": [
                    {"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
            },
        }
        try:
            model = RecurrentPPO(
                "MlpLstmPolicy", env, n_steps=8, batch_size=8, n_epochs=1,
                policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                device="cpu", seed=26, verbose=0)
            with TemporaryDirectory() as directory:
                output_dir = Path(directory)
                callback = MatchScoreEvalCallback(
                    config, output_dir, every_steps=8, episodes=2, seed=26)
                model.learn(total_timesteps=8, callback=callback)
                self.assertTrue((output_dir / "best" / "best_model.zip").is_file())
                self.assertTrue((output_dir / "best" / "selection.json").is_file())
                self.assertTrue((output_dir / "evaluation" / "match_scores.jsonl").is_file())
                resumed = MatchScoreEvalCallback(
                    config, output_dir, every_steps=8, episodes=2, seed=26)
                resumed.init_callback(model)
                self.assertEqual(callback.best_score, resumed.best_score)
        finally:
            env.close()

    def test_destroyer_opponent_is_spawned_explicitly(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

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

    def test_destroyer_agent_uses_its_own_spaces(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

        env = SubmarineDuelEnv(
            agent_boat_type="destroyer",
            opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
            seed=18, frame_skip=2, max_physics_steps=10,
            spawn_min_m=400.0, spawn_max_m=700.0)
        try:
            observation, _ = env.reset(seed=18)
            self.assertEqual((DESTROYER_V1_OBS_DIM,), observation.shape)
            self.assertTrue(env.action_space.contains(DESTROYER_NEUTRAL_ACTION))
            self.assertEqual(tuple(DESTROYER_V1_ACTION_NVECS), tuple(env.action_space.nvec))
            self.assertEqual("destroyer", env._agent()["boatType"])
        finally:
            env.close()

    def test_destroyer_rl_can_ping_and_fire_cannon_with_passive_contact(self) -> None:
        runner = HeadlessRunner(seed=19)
        destroyer_sid = runner.spawn_bot(
            boat_type="destroyer", external_control=True, ai=None,
            position=(100.0, 100.0), rotation=np.pi, team_id="destroyer")
        target_sid = runner.spawn_bot(
            boat_type="submarine", external_control=True, ai=None,
            position=(105.0, 100.0), rotation=0.0, team_id="submarine")
        destroyer = runner.legacy.bots[destroyer_sid]
        target = runner.legacy.bots[target_sid]
        target["position"]["y"] = -0.2
        target["speed"] = target["max_speed_us"]
        runner.legacy.players[target_sid]["position"] = dict(target["position"])
        runner.legacy.players[target_sid]["speed"] = target["speed"]

        observation = build_observation(destroyer, runner.sim, runner.world)
        self.assertEqual((DESTROYER_V1_OBS_DIM,), observation.shape)
        result = apply_action(destroyer, runner.sim, [2, 1, 3, 0, 1])
        self.assertTrue(result["sonar_pinged"])
        self.assertTrue(result["weapon_fired"])
        self.assertEqual(49, runner.legacy.cannon_ammo[destroyer_sid]["cannon"])
        result = apply_action(destroyer, runner.sim, [2, 1, 3, 0, 1])
        self.assertFalse(result["sonar_pinged"])
        self.assertFalse(result["sonar_invalid"])
        self.assertFalse(result["weapon_fired"])
        self.assertFalse(result["weapon_invalid"])

        target["position"]["y"] = -3.0
        runner.legacy.players[target_sid]["position"] = dict(target["position"])
        build_observation(destroyer, runner.sim, runner.world)
        result = apply_action(destroyer, runner.sim, [2, 1, 4, 0, 0])
        self.assertTrue(result["weapon_fired"])
        self.assertEqual(49, runner.legacy.grenade_ammo[destroyer_sid])

        destroyer["rl_control_version"] = DESTROYER_OBSERVATION_VERSION
        observation = build_observation(destroyer, runner.sim, runner.world)
        self.assertEqual((DESTROYER_OBS_DIM,), observation.shape)
        destroyer["next_grenade_at"] = 0.0
        build_observation(destroyer, runner.sim, runner.world)
        result = apply_action(destroyer, runner.sim, [2, 1, 4, 0, 0, 3])
        self.assertTrue(result["weapon_fired"])
        self.assertFalse(result["mine_placed"])
        self.assertEqual({}, runner.legacy.mines_server)
        result = apply_action(destroyer, runner.sim, [2, 1, 0, 0, 0, 3])
        self.assertTrue(result["mine_placed"])
        self.assertEqual("suspended", result["mine_kind"])
        self.assertEqual(39, runner.legacy.mine_ammo[destroyer_sid]["suspended"])

    def test_destroyer_v2_agent_exposes_mine_controls(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

        env = SubmarineDuelEnv(
            agent_boat_type="destroyer", control_version=DESTROYER_OBSERVATION_VERSION,
            opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
            seed=22, frame_skip=2, max_physics_steps=10,
            spawn_min_m=400.0, spawn_max_m=700.0)
        try:
            observation, _ = env.reset(seed=22)
            self.assertEqual((DESTROYER_OBS_DIM,), observation.shape)
            self.assertEqual(tuple(DESTROYER_ACTION_NVECS), tuple(env.action_space.nvec))
            self.assertTrue(env.action_space.contains(np.array([2, 1, 0, 0, 0, 0])))
        finally:
            env.close()

    def test_destroyer_smoke_training_against_frozen_submarine(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv

        with TemporaryDirectory() as directory:
            pool_dir = Path(directory)
            submarine_env = SubmarineDuelEnv(
                seed=20, frame_skip=2, max_physics_steps=20,
                spawn_min_m=400.0, spawn_max_m=700.0)
            try:
                submarine_model = RecurrentPPO(
                    "MlpLstmPolicy", submarine_env, n_steps=8, batch_size=8, n_epochs=1,
                    policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                    device="cpu", seed=20, verbose=0)
                submarine_model.save(pool_dir / "submarine")
            finally:
                submarine_env.close()

            destroyer_env = SubmarineDuelEnv(
                agent_boat_type="destroyer",
                opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
                fixed_opponent_pool_dir=str(pool_dir),
                fixed_opponent_boat_type="submarine", fixed_policy_probability=1.0,
                seed=21, frame_skip=2, max_physics_steps=20,
                spawn_min_m=400.0, spawn_max_m=700.0)
            try:
                _, info = destroyer_env.reset(seed=21)
                self.assertEqual("policy", info["opponent_kind"])
                self.assertEqual("submarine", info["opponent_boat_type"])
                destroyer_model = RecurrentPPO(
                    "MlpLstmPolicy", destroyer_env, n_steps=8, batch_size=8, n_epochs=1,
                    policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                    device="cpu", seed=21, verbose=0)
                destroyer_model.learn(total_timesteps=16)
            finally:
                destroyer_env.close()

    def test_submarine_smoke_training_against_frozen_destroyer(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv

        with TemporaryDirectory() as directory:
            pool_dir = Path(directory)
            destroyer_env = SubmarineDuelEnv(
                agent_boat_type="destroyer", control_version=DESTROYER_OBSERVATION_VERSION,
                seed=24, frame_skip=2, max_physics_steps=20,
                spawn_min_m=400.0, spawn_max_m=700.0)
            try:
                destroyer_model = RecurrentPPO(
                    "MlpLstmPolicy", destroyer_env, n_steps=8, batch_size=8, n_epochs=1,
                    policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                    device="cpu", seed=24, verbose=0)
                destroyer_model.save(pool_dir / "destroyer")
            finally:
                destroyer_env.close()

            submarine_env = SubmarineDuelEnv(
                opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
                fixed_opponent_pool_dir=str(pool_dir),
                fixed_opponent_boat_type="destroyer", fixed_policy_probability=1.0,
                seed=25, frame_skip=2, max_physics_steps=20,
                spawn_min_m=400.0, spawn_max_m=700.0)
            try:
                _, info = submarine_env.reset(seed=25)
                self.assertEqual("policy", info["opponent_kind"])
                self.assertEqual("destroyer", info["opponent_boat_type"])
                submarine_model = RecurrentPPO(
                    "MlpLstmPolicy", submarine_env, n_steps=8, batch_size=8, n_epochs=1,
                    policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                    device="cpu", seed=25, verbose=0)
                submarine_model.learn(total_timesteps=16)
            finally:
                submarine_env.close()

    def test_invalid_opponent_configuration_is_rejected(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

        with self.assertRaises(ValueError):
            SubmarineDuelEnv(opponents=[])
        with self.assertRaises(ValueError):
            SubmarineDuelEnv(
                opponents=[{"boat_type": "carrier", "ai": "default", "weight": 1.0}])
        with self.assertRaises(ValueError):
            SubmarineDuelEnv(
                opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 0.0}])

    def test_weighted_opponent_sequence_is_seeded(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

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
        from rl.rl_env import SubmarineDuelEnv

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
        self.assertEqual(70.0, target["integrity"])
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
        self.assertEqual([], detected)
        self.runner.step(0.05)
        detected = self.runner.sim.active_sonar_contacts(self.runner.legacy.bots[destroyer_sid])
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

    def test_weapon_without_contact_is_rejected_without_hidden_aim(self) -> None:
        agent = self.runner.legacy.bots[self.agent_sid]
        result = apply_action(agent, self.runner.sim, [2, 1, 2, 1, 0])
        self.assertFalse(result["weapon_fired"])
        self.assertTrue(result["weapon_invalid"])
        self.assertFalse(result["weapon_had_acquisition"])
        self.assertTrue(result["weapon_without_acquisition"])
        self.assertIsNone(result["weapon_contact_age_s"])
        self.assertIsNone(result["weapon_bearing_error_deg"])
        self.assertFalse(self.runner.legacy.torpedoes_server)

        opponent = self.runner.legacy.bots[self.opponent_sid]
        agent["next_torpedo_at"] = 0.0
        agent["rl_contact"] = {
            "id": opponent["id"], "sid": opponent["sid"],
            "x": opponent["position"]["x"], "y": opponent["position"]["y"],
            "z": opponent["position"]["z"], "at": self.runner.sim.now(),
            "boat": opponent["boat"],
        }
        agent["rl_contact_tracked"] = True
        acquired = apply_action(agent, self.runner.sim, [2, 1, 2, 2, 0])
        self.assertTrue(acquired["weapon_fired"])
        self.assertTrue(acquired["weapon_had_acquisition"])
        self.assertFalse(acquired["weapon_without_acquisition"])
        self.assertEqual(0.0, acquired["weapon_contact_age_s"])
        self.assertAlmostEqual(180.0, acquired["weapon_bearing_error_deg"])
        self.assertTrue(acquired["weapon_misaligned"])


if __name__ == "__main__":
    unittest.main()
