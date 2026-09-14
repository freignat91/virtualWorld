"""Tests du premier curriculum de navigation sans combat."""

import math
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from stable_baselines3.common.env_checker import check_env
from sb3_contrib import RecurrentPPO

import geometry
import simulation
from rl.navigation_env import NAVIGATION_OBS_DIM, NavigationEnv
from rl.rl_control import RUDDER_LEVELS, THROTTLE_LEVELS
from rl.train_navigation import (
    load_config,
    NavigationEvalCallback,
    navigation_gate_report,
    validate_navigation_gates,
)


class NavigationEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = NavigationEnv(seed=11542)
        self.addCleanup(self.env.close)

    def test_reset_builds_reachable_blocked_route_without_combat(self) -> None:
        observation, info = self.env.reset(seed=11542)

        self.assertEqual((NAVIGATION_OBS_DIM,), observation.shape)
        self.assertTrue(self.env.observation_space.contains(observation))
        self.assertTrue(info["direct_path_blocked"])
        self.assertGreaterEqual(info["shortest_path_m"], self.env.min_route_m)
        self.assertEqual(1, len(self.env.runner.legacy.bots))
        self.assertFalse(self.env.runner.legacy.torpedoes_server)
        self.assertFalse(self.env.runner.legacy.grenades_server)

    def test_gymnasium_contract(self) -> None:
        check_env(self.env, warn=True)

    def test_route_sampling_is_deterministic(self) -> None:
        _, first = self.env.reset(seed=91)
        _, second = self.env.reset(seed=91)
        self.assertEqual(first, second)

    def test_open_routes_have_no_blocking_island(self) -> None:
        env = NavigationEnv(
            seed=12542, route_mode="open", min_route_m=300.0, max_route_m=800.0)
        self.addCleanup(env.close)
        _, info = env.reset(seed=12542)
        self.assertFalse(info["direct_path_blocked"])
        self.assertEqual(0, info["blocking_islands"])

    def test_single_island_routes_have_exactly_one_blocker(self) -> None:
        env = NavigationEnv(
            seed=13542, route_mode="single_island",
            min_route_m=400.0, max_route_m=1200.0)
        self.addCleanup(env.close)
        for seed in range(242542, 242642):
            with self.subTest(seed=seed):
                _, info = env.reset(seed=seed)
                self.assertTrue(info["direct_path_blocked"])
                self.assertEqual(1, info["blocking_islands"])

    def test_easy_single_island_routes_bound_the_required_detour(self) -> None:
        env = NavigationEnv(
            seed=282542, route_mode="single_island", max_detour_ratio=1.3,
            min_route_m=600.0, max_route_m=1200.0)
        self.addCleanup(env.close)
        for seed in (*range(282542, 282642), *range(292542, 292642)):
            with self.subTest(seed=seed):
                _, info = env.reset(seed=seed)
                start, goal = info["start"], info["goal"]
                direct_m = (math.hypot(goal[0] - start[0], goal[1] - start[1])
                            * simulation.UNIT_METERS_BOT)
                self.assertLessEqual(info["shortest_path_m"] / direct_m, 1.3 + 1e-9)

    def test_rejects_invalid_detour_ratio(self) -> None:
        with self.assertRaises(ValueError):
            NavigationEnv(max_detour_ratio=0.99)

    def test_safe_waypoint_replaces_blocked_goal_without_changing_spaces(self) -> None:
        env = NavigationEnv(
            seed=342542, route_mode="single_island", guidance_mode="safe_waypoint",
            max_detour_ratio=1.3, min_route_m=600.0, max_route_m=1200.0)
        self.addCleanup(env.close)

        observation, info = env.reset(seed=342542)

        self.assertEqual("navigation_v2", info["observation_version"])
        self.assertNotEqual(info["goal"], info["guidance_target"])
        self.assertTrue(geometry.line_of_sight_clear(
            *info["start"], *info["guidance_target"], env.runner.world))
        next_target = env._guidance_target(tuple(info["guidance_target"]))
        self.assertNotEqual(tuple(info["guidance_target"]), next_target)
        self.assertEqual((NAVIGATION_OBS_DIM,), observation.shape)
        self.assertEqual((5, 5), tuple(env.action_space.nvec))

    def test_rejects_unknown_guidance_mode(self) -> None:
        with self.assertRaises(ValueError):
            NavigationEnv(guidance_mode="omniscient")
        with self.assertRaises(ValueError):
            NavigationEnv(progress_mode="shortcut")
        with self.assertRaises(ValueError):
            NavigationEnv(waypoint_lookahead_m=0.0)
        with self.assertRaises(ValueError):
            NavigationEnv(coastal_safety_clearance_m=-1.0)
        with self.assertRaises(ValueError):
            NavigationEnv(coastal_safety_horizon_s=0.0)

    def test_lookahead_waypoint_previews_the_next_segment(self) -> None:
        common = {
            "seed": 342542,
            "route_mode": "single_island",
            "guidance_clearance_m": 50.0,
            "max_detour_ratio": 1.3,
            "min_route_m": 600.0,
            "max_route_m": 1200.0,
        }
        current = NavigationEnv(guidance_mode="safe_waypoint", **common)
        lookahead = NavigationEnv(
            guidance_mode="lookahead_waypoint", waypoint_lookahead_m=100.0, **common)
        self.addCleanup(current.close)
        self.addCleanup(lookahead.close)

        _, info = current.reset(seed=342542)
        start = tuple(info["start"])
        goal = tuple(info["goal"])
        target = tuple(info["guidance_target"])
        lookahead.reset(options={"start": start, "goal": goal})
        dx, dz = start[0] - target[0], start[1] - target[1]
        scale = 7.5 / math.hypot(dx, dz)
        before_target = (target[0] + dx * scale, target[1] + dz * scale)

        self.assertEqual("navigation_v3", lookahead.observation_version)
        self.assertEqual(target, current._guidance_target(before_target))
        self.assertNotEqual(target, lookahead._guidance_target(before_target))

    def test_geometric_progress_keeps_the_legacy_shortest_path(self) -> None:
        env = NavigationEnv(
            seed=382542, route_mode="single_island", guidance_mode="lookahead_waypoint",
            guidance_clearance_m=50.0, waypoint_lookahead_m=100.0,
            progress_mode="geometric", max_detour_ratio=1.3,
            min_route_m=600.0, max_route_m=1200.0)
        self.addCleanup(env.close)

        _, info = env.reset(seed=382542)
        start, goal = tuple(info["start"]), tuple(info["goal"])

        self.assertAlmostEqual(
            env._shortest_distance_u(start, goal) * simulation.UNIT_METERS_BOT,
            info["shortest_path_m"])

    def test_waypoint_guidance_respects_segment_clearance(self) -> None:
        env = NavigationEnv(
            seed=382542, route_mode="single_island", guidance_mode="safe_waypoint",
            guidance_clearance_m=50.0, max_detour_ratio=1.3,
            min_route_m=600.0, max_route_m=1200.0)
        self.addCleanup(env.close)

        _, info = env.reset(seed=382542)

        self.assertTrue(env._segment_has_guidance_clearance(
            tuple(info["start"]), tuple(info["guidance_target"])))
        self.assertFalse(env._segment_has_guidance_clearance(
            tuple(info["start"]), tuple(info["goal"])))

    def test_waypoint_progress_uses_the_guidance_clearance_path(self) -> None:
        env = NavigationEnv(
            seed=382542, route_mode="single_island", guidance_mode="safe_waypoint",
            guidance_clearance_m=50.0, max_detour_ratio=1.3,
            min_route_m=600.0, max_route_m=1200.0)
        self.addCleanup(env.close)

        _, info = env.reset(seed=382542)
        start, goal = tuple(info["start"]), tuple(info["goal"])
        guidance_shortest_u = env._shortest_distance_u(start, goal, guidance=True)

        self.assertAlmostEqual(
            guidance_shortest_u * simulation.UNIT_METERS_BOT,
            info["shortest_path_m"])

        target = tuple(info["guidance_target"])
        transition = None
        for index in range(1, 100):
            ratio = index / 100.0
            point = (start[0] + (target[0] - start[0]) * ratio,
                     start[1] + (target[1] - start[1]) * ratio)
            if (geometry.line_of_sight_clear(*point, *goal, env.runner.world)
                    and not env._segment_has_guidance_clearance(point, goal)):
                transition = point
                break
        self.assertIsNotNone(transition)
        assert transition is not None
        direct_u = math.hypot(goal[0] - transition[0], goal[1] - transition[1])
        self.assertAlmostEqual(direct_u, env._shortest_distance_u(transition, goal))
        self.assertGreater(
            env._shortest_distance_u(transition, goal, guidance=True), direct_u)

    def test_corridor_routes_cover_both_evaluation_banks(self) -> None:
        env = NavigationEnv(
            seed=402542, route_mode="single_island", guidance_mode="safe_waypoint",
            guidance_clearance_m=50.0, max_detour_ratio=1.3,
            min_route_m=600.0, max_route_m=1200.0)
        self.addCleanup(env.close)
        for seed in (*range(402542, 402552), *range(412542, 412552)):
            with self.subTest(seed=seed):
                _, info = env.reset(seed=seed)
                self.assertTrue(env._segment_has_guidance_clearance(
                    tuple(info["start"]), tuple(info["guidance_target"])))

    def test_guidance_clearance_is_optional_and_validated(self) -> None:
        env = NavigationEnv(guidance_clearance_m=0.0)
        self.addCleanup(env.close)
        self.assertTrue(env._segment_has_guidance_clearance((0.0, 990.0), (10.0, 990.0)))
        with self.assertRaises(ValueError):
            NavigationEnv(guidance_clearance_m=-1.0)

    def test_submarine_navigation_keeps_fixed_depth_and_separate_spaces(self) -> None:
        env = NavigationEnv(
            boat_type="submarine", seed=14542, route_mode="open",
            min_route_m=300.0, max_route_m=800.0)
        self.addCleanup(env.close)
        observation, _ = env.reset(seed=14542)
        initial_depth = env._agent()["position"]["y"]
        observation, _, _, _, _ = env.step(np.array([0, 4]))
        self.assertEqual(initial_depth, env._agent()["position"]["y"])
        self.assertEqual((NAVIGATION_OBS_DIM,), observation.shape)
        self.assertEqual((5, 5), tuple(env.action_space.nvec))

    def test_coastal_safety_replaces_a_predicted_unsafe_action(self) -> None:
        env = NavigationEnv(
            seed=11542, coastal_safety_clearance_m=50.0,
            coastal_safety_horizon_s=5.0)
        self.addCleanup(env.close)
        env.reset(seed=11542)
        bot = env._agent()
        island = env.runner.world["islands"][2]
        points = island["points"]
        center_x = sum(point["x"] for point in points) / len(points)
        center_z = sum(point["z"] for point in points) / len(points)
        vertex = points[0]
        outward_x = vertex["x"] - center_x
        outward_z = vertex["z"] - center_z
        norm = math.hypot(outward_x, outward_z)
        outward_x /= norm
        outward_z /= norm
        bot["position"].update(
            x=vertex["x"] + outward_x * 10.0,
            z=vertex["z"] + outward_z * 10.0)
        toward_x, toward_z = -outward_x, -outward_z
        bot["rotation"] = math.atan2(toward_z, -toward_x)
        bot["speed"] = bot["max_speed_us"]
        requested = np.asarray([2, 4], dtype=np.int64)
        initial_clearance_m = env._clearance_u((
            bot["position"]["x"], bot["position"]["z"]
        )) * simulation.UNIT_METERS_BOT
        requested_clearance = env._predicted_action_clearance(
            bot, 0.0, 1.0, initial_clearance_m)

        safe, intervened = env._safe_action(bot, requested)
        safe_clearance = env._predicted_action_clearance(
            bot, RUDDER_LEVELS[int(safe[0])], THROTTLE_LEVELS[int(safe[1])],
            initial_clearance_m)

        self.assertLess(requested_clearance[0], env.coastal_safety_clearance_m)
        self.assertTrue(intervened, (requested_clearance, safe_clearance, safe.tolist()))
        self.assertGreater(safe_clearance, requested_clearance)
        self.assertGreaterEqual(safe_clearance[0], env.coastal_safety_clearance_m)

    def test_native_coastal_damage_is_exposed_to_navigation(self) -> None:
        island = self.env.runner.world["islands"][0]
        points = island["points"]
        center_x = sum(point["x"] for point in points) / len(points)
        center_z = sum(point["z"] for point in points) / len(points)
        vertex = points[0]
        dx, dz = vertex["x"] - center_x, vertex["z"] - center_z
        norm = math.hypot(dx, dz)
        start = (vertex["x"] + dx / norm * 1.5, vertex["z"] + dz / norm * 1.5)
        self.assertFalse(geometry.point_on_any_island(*start, self.env.runner.world))
        self.assertTrue(self.env.runner.sim.is_in_danger_zone(*start, self.env.runner.world))
        self.env.reset(seed=11542)
        bot = self.env._agent()
        bot["position"].update(x=start[0], z=start[1])
        self.env.runner.sim.players[self.env.agent_sid]["position"].update(
            x=start[0], z=start[1])

        _, reward, terminated, truncated, info = self.env.step(np.array([2, 1]))

        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertAlmostEqual(0.25, info["coastal_damage"])
        self.assertLess(reward, -0.24)

    def test_coastal_proximity_penalty_precedes_native_damage(self) -> None:
        env = NavigationEnv(
            seed=11542, max_episode_seconds=0.25,
            reward={"coastal_proximity": -1.0})
        self.addCleanup(env.close)
        island = env.runner.world["islands"][2]
        points = island["points"]
        center_x = sum(point["x"] for point in points) / len(points)
        center_z = sum(point["z"] for point in points) / len(points)
        vertex = points[0]
        dx, dz = vertex["x"] - center_x, vertex["z"] - center_z
        norm = math.hypot(dx, dz)
        start = (vertex["x"] + dx / norm * 5.0, vertex["z"] + dz / norm * 5.0)
        self.assertFalse(env.runner.sim.is_in_danger_zone(*start, env.runner.world))
        self.assertLess(env._clearance_u(start) * simulation.UNIT_METERS_BOT, 100.0)
        env.reset(seed=11542)
        bot = env._agent()
        bot["position"].update(x=start[0], z=start[1])
        env.runner.sim.players[env.agent_sid]["position"].update(x=start[0], z=start[1])

        _, reward, _, truncated, info = env.step(np.array([2, 0]))

        self.assertTrue(truncated)
        self.assertEqual(0.0, info["coastal_damage"])
        self.assertGreater(info["near_coast_fraction"], 0.0)
        self.assertLess(reward, -0.1)

    def test_arrival_terminates_with_behavior_metrics(self) -> None:
        self.env.reset(seed=11542)
        bot = self.env._agent()
        self.env.goal = (bot["position"]["x"], bot["position"]["z"])
        self.env._goal_connections = self.env._visible_nodes(self.env.goal)

        _, reward, terminated, truncated, info = self.env.step(np.array([2, 1]))

        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertGreater(reward, 9.0)
        self.assertEqual("arrived", info["outcome"])
        self.assertTrue(info["success"])
        self.assertIn("path_efficiency", info)
        self.assertIn("safety_intervention_fraction", info)

    def test_config_and_behavior_gates(self) -> None:
        configs = Path(__file__).with_name("configs")
        config = load_config(configs / "aidest_navigation_v1.json")
        metrics = {
            "success_rate": 0.99,
            "coastal_damage_episode_fraction": 0.0,
            "stuck_rate": 0.01,
            "timeout_rate": 0.0,
            "stationary_fraction": 0.04,
            "mean_success_path_efficiency": 1.4,
            "mean_coastal_damage": 0.0,
            "episodes": 100.0,
        }
        self.assertTrue(navigation_gate_report(config, metrics)["passed"])
        metrics["coastal_damage_episode_fraction"] = 0.01
        report = navigation_gate_report(config, metrics)
        self.assertFalse(report["passed"])
        self.assertEqual(["max_coastal_damage_episode_fraction"], report["failures"])
        with self.assertRaises(ValueError):
            validate_navigation_gates({"evaluation": {"behavior_gates": {"victories": 1}}})

        open_config = load_config(configs / "aidest_navigation_open_v1.json")
        continuation = load_config(configs / "aidest_navigation_open_v1_continue.json")
        submarine = load_config(configs / "aisub_navigation_open_v1.json")
        single_island = load_config(configs / "aidest_navigation_single_island_v1.json")
        submarine_island = load_config(configs / "aisub_navigation_single_island_v1.json")
        island_continuation = load_config(
            configs / "aidest_navigation_single_island_v1_continue.json")
        submarine_island_continuation = load_config(
            configs / "aisub_navigation_single_island_v1_continue.json")
        destroyer_safe = load_config(
            configs / "aidest_navigation_single_island_safe_v1_continue.json")
        submarine_safe = load_config(
            configs / "aisub_navigation_single_island_safe_v1_continue.json")
        destroyer_waypoint = load_config(configs / "aidest_navigation_waypoint_v2.json")
        destroyer_waypoint_continuation = load_config(
            configs / "aidest_navigation_waypoint_v2_continue.json")
        submarine_waypoint = load_config(configs / "aisub_navigation_waypoint_v2.json")
        submarine_waypoint_continuation = load_config(
            configs / "aisub_navigation_waypoint_v2_continue.json")
        destroyer_corridor = load_config(
            configs / "aidest_navigation_waypoint_safe_v2.json")
        submarine_corridor = load_config(
            configs / "aisub_navigation_waypoint_safe_v2.json")
        destroyer_lookahead = load_config(configs / "aidest_navigation_lookahead_v3.json")
        submarine_lookahead = load_config(configs / "aisub_navigation_lookahead_v3.json")
        destroyer_shield = load_config(configs / "aidest_navigation_shield_v2.json")
        submarine_shield = load_config(configs / "aisub_navigation_shield_v2.json")
        for section in ("model", "env", "reward"):
            self.assertEqual(open_config[section], continuation[section])
        self.assertNotEqual(open_config["training"]["seed"], continuation["training"]["seed"])
        self.assertNotEqual(open_config["evaluation"]["seed"], continuation["evaluation"]["seed"])
        self.assertEqual("submarine", submarine["env"]["boat_type"])
        for section in ("model", "reward"):
            self.assertEqual(open_config[section], submarine[section])
            self.assertEqual(open_config[section], single_island[section])
        self.assertEqual("single_island", single_island["env"]["route_mode"])
        self.assertEqual("single_island", submarine_island["env"]["route_mode"])
        self.assertEqual("submarine", submarine_island["env"]["boat_type"])
        for section in ("model", "env", "reward"):
            self.assertEqual(single_island[section], island_continuation[section])
            self.assertEqual(
                submarine_island[section], submarine_island_continuation[section])
        self.assertEqual(150, destroyer_safe["env"]["coastal_clearance_m"])
        self.assertEqual(100, submarine_safe["env"]["coastal_clearance_m"])
        self.assertEqual(-0.1, destroyer_safe["reward"]["coastal_proximity"])
        self.assertEqual(-0.1, submarine_safe["reward"]["coastal_proximity"])
        for first, second in (
                (destroyer_waypoint, destroyer_waypoint_continuation),
                (submarine_waypoint, submarine_waypoint_continuation)):
            for section in ("model", "env", "reward"):
                self.assertEqual(first[section], second[section])
        for corridor in (destroyer_corridor, submarine_corridor):
            self.assertEqual(50, corridor["env"]["guidance_clearance_m"])
            self.assertEqual(25000, corridor["training"]["checkpoint_every_steps"])
            self.assertEqual(25000, corridor["evaluation"]["every_steps"])
        self.assertEqual(150, destroyer_lookahead["env"]["waypoint_lookahead_m"])
        self.assertEqual("geometric", destroyer_lookahead["env"]["progress_mode"])
        self.assertEqual(100, submarine_lookahead["env"]["waypoint_lookahead_m"])
        self.assertEqual("guidance", submarine_lookahead["env"]["progress_mode"])
        for shield in (destroyer_shield, submarine_shield):
            self.assertEqual(50, shield["env"]["coastal_safety_clearance_m"])
            self.assertEqual(5, shield["env"]["coastal_safety_horizon_s"])

    def test_smoke_training_selects_only_on_navigation_report(self) -> None:
        config = deepcopy(load_config(
            Path(__file__).with_name("configs") / "aidest_navigation_v1.json"))
        config["env"]["max_episode_seconds"] = 0.25
        config["env"]["stuck_seconds"] = 0.2
        config["evaluation"].update(every_steps=8, episodes=1, seed=45, behavior_gates={})
        env = NavigationEnv(**{
            "map_name": "world", "boat_type": "destroyer", "frame_skip": 5,
            "max_episode_seconds": 0.25, "stuck_seconds": 0.2,
            "goal_radius_m": 50, "min_route_m": 800, "max_route_m": 3000,
            "route_mode": "blocked", "ray_max_m": 1000,
            "reward": config["reward"], "seed": 45,
        })
        self.addCleanup(env.close)
        model = RecurrentPPO(
            "MlpLstmPolicy", env, n_steps=8, batch_size=8, n_epochs=1,
            policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
            device="cpu", seed=45, verbose=0)
        with TemporaryDirectory() as directory:
            output = Path(directory)
            model.learn(total_timesteps=8, callback=NavigationEvalCallback(config, output))
            self.assertTrue((output / "best" / "best_model.zip").is_file())
            self.assertTrue((output / "candidate" / "candidate_model.zip").is_file())
            selection = (output / "best" / "selection.json").read_text()
            self.assertNotIn("win", selection.lower())
            self.assertTrue((output / "evaluation" / "navigation.jsonl").is_file())

        config["evaluation"]["behavior_gates"] = {"min_success_rate": 1.0}
        with TemporaryDirectory() as directory:
            output = Path(directory)
            model.learn(total_timesteps=8, callback=NavigationEvalCallback(config, output))
            self.assertTrue((output / "candidate" / "candidate_model.zip").is_file())
            self.assertFalse((output / "best").exists())


if __name__ == "__main__":
    unittest.main()
