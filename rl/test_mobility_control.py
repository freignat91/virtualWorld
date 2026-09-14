"""Regressions des interfaces definitives et de la phase de mobilite."""

import math
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

import geometry
from nav_graph import build_nav_graph
import simulation
from rl.headless import HeadlessRunner
from rl.mobility_env import (
    DEFAULT_REWARD,
    METRIC_EXEMPTION_M,
    MobilityEnv,
)
from rl.rl_control import (
    CONTACT_DEPTH_MAX_M,
    DIRECTIONAL_RAY_DIRECTIONS_DEG,
    LONG_RANGE_RAY_DIRECTIONS_DEG,
    LONG_RANGE_RAY_MAX_M,
    DESTROYER_V4_ACTION_NVECS,
    DESTROYER_V4_GRENADE_START,
    DESTROYER_V4_OBS_DIM,
    DESTROYER_V4_OBSERVATION_VERSION,
    DESTROYER_V4_RAY_START,
    DESTROYER_V4_TORPEDO_START,
    DESTROYER_V5_ACTION_NVECS,
    DESTROYER_V5_CONTACT_START,
    DESTROYER_V5_GRENADE_START,
    DESTROYER_V5_LURE_START,
    DESTROYER_V5_OBS_DIM,
    DESTROYER_V5_OBSERVATION_VERSION,
    DESTROYER_V5_RAY_START,
    DESTROYER_V5_TORPEDO_START,
    DESTROYER_V5_WAYPOINT_START,
    DESTROYER_V6_ACTION_NVECS,
    DESTROYER_V6_LONG_RAY_START,
    DESTROYER_V6_OBS_DIM,
    DESTROYER_V6_OBSERVATION_VERSION,
    DESTROYER_V6_WAYPOINT_START,
    MOBILITY_GRENADE_SLOT_DIM,
    MOBILITY_DIRECTIONAL_LURE_SLOT_DIM,
    MOBILITY_DIRECTIONAL_GRENADE_SLOT_DIM,
    MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM,
    MOBILITY_TORPEDO_SLOT_DIM,
    SUBMARINE_V2_ACTION_NVECS,
    SUBMARINE_V2_GRENADE_START,
    SUBMARINE_V2_OBS_DIM,
    SUBMARINE_V2_OBSERVATION_VERSION,
    SUBMARINE_V2_RAY_START,
    SUBMARINE_V2_TORPEDO_START,
    SUBMARINE_V3_ACTION_NVECS,
    SUBMARINE_V3_CONTACT_START,
    SUBMARINE_V3_GRENADE_START,
    SUBMARINE_V3_LURE_START,
    SUBMARINE_V3_OBS_DIM,
    SUBMARINE_V3_OBSERVATION_VERSION,
    SUBMARINE_V3_RAY_START,
    SUBMARINE_V3_TORPEDO_START,
    SUBMARINE_V3_WAYPOINT_START,
    SUBMARINE_V4_ACTION_NVECS,
    SUBMARINE_V4_LONG_RAY_START,
    SUBMARINE_V4_OBS_DIM,
    SUBMARINE_V4_OBSERVATION_VERSION,
    SUBMARINE_V4_WAYPOINT_START,
    _ratio,
    apply_action,
    build_observation,
    control_spec,
    control_version_for_spaces,
)
from rl.navigable_path import (
    DESTINATION_CLEARANCE_M,
    NavigablePathMetric,
    ROUTE_CLEARANCE_M,
    ROUTE_LONG_SEGMENT_M,
    ROUTE_NODE_MARGIN_M,
    plan_segmented_route,
    segment_route,
)
from rl.waypoints import (
    RLWaypointManager,
    WAYPOINT_ISLAND_CLEARANCE_M,
    WAYPOINT_MAX_DISTANCE_M,
    WAYPOINT_MIN_DISTANCE_M,
    waypoint_distance_m,
)


class FinalControlObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = HeadlessRunner(seed=61542)
        self.runner.reset(seed=61542)
        self.runner.world["islands"] = []
        self.runner.world["thermoclines"] = []

    def _spawn(self, boat_type: str, version: str) -> dict:
        sid = self.runner.spawn_bot(
            boat_type=boat_type, external_control=True, ai=None,
            position=(0.0, 0.0), rotation=0.0, team_id="agent")
        bot = self.runner.legacy.bots[sid]
        bot["rl_control_version"] = version
        return bot

    def _torpedo(self, bot: dict, kind: str) -> dict:
        return {
            "ownerPlayerId": "enemy", "tid": 1,
            "x": -10.0, "y": bot["position"].get("y", 0.0), "z": 0.0,
            "dirX": 1.0, "dirZ": 0.0, "speed": 1.0,
            "kind": kind, "acquiredBoatId": bot["id"], "targetId": "private",
        }

    def test_unsigned_ratio_clamp_handles_extreme_values(self) -> None:
        cases = (
            (float("-inf"), 0.0), (-1.0, 0.0), (0.0, 0.0),
            (0.5, 0.5), (1.0, 1.0), (2.0, 1.0),
            (float("inf"), 1.0), (float("nan"), 0.0),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(expected, _ratio(value))

    def test_new_schemas_use_full_reverse_without_changing_legacy_throttle(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V2_OBSERVATION_VERSION,
             (-0.35, 0.0, 0.35, 0.65, 1.0)),
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             (-1.0, 0.0, 0.35, 0.65, 1.0)),
            ("destroyer", DESTROYER_V4_OBSERVATION_VERSION,
             (-0.35, 0.0, 0.35, 0.65, 1.0)),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             (-1.0, 0.0, 0.35, 0.65, 1.0)),
        )
        for boat_type, version, expected_levels in cases:
            with self.subTest(boat_type=boat_type, version=version):
                self.runner.reset(seed=61542)
                bot = self._spawn(boat_type, version)
                for throttle_index, expected in enumerate(expected_levels):
                    action = ([2, throttle_index, 2, 0, 0]
                              if boat_type == "submarine" else
                              [2, throttle_index, 0, 0, 0])
                    apply_action(bot, self.runner.sim, action)
                    self.assertEqual(expected, bot["control_target_speed_ratio"])

    def test_new_schemas_observe_throttle_request_separately_from_speed(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             [2, 0, 2, 0, 0]),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             [2, 0, 0, 0, 0]),
        )
        for boat_type, version, action in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                bot = self._spawn(boat_type, version)
                bot["speed"] = 0.0
                apply_action(bot, self.runner.sim, action)
                observation = build_observation(bot, self.runner.sim, self.runner.world)
                self.assertEqual(0.0, observation[0])
                self.assertEqual(-1.0, observation[1])

    def test_new_schemas_observe_actual_signed_yaw_rate_ratio(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION),
        )
        for boat_type, version in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                bot = self._spawn(boat_type, version)
                bot["speed"] = float(bot["max_speed_us"]) * 0.5
                bot["rudder"] = float(bot["rudder_max"])
                bot["control_target_rudder"] = -1.0
                forward = build_observation(bot, self.runner.sim, self.runner.world)
                self.assertAlmostEqual(0.5, forward[2], places=6)

                bot["speed"] *= -1.0
                reverse = build_observation(bot, self.runner.sim, self.runner.world)
                self.assertAlmostEqual(-0.5, reverse[2], places=6)

    def test_new_schemas_append_waypoint_bearing_and_distance(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_WAYPOINT_START),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_WAYPOINT_START),
        )
        for boat_type, version, start in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                bot = self._spawn(boat_type, version)
                bot["rotation"] = 0.0
                bot["rl_waypoint"] = {"x": -300.0, "z": 400.0}
                observation = build_observation(bot, self.runner.sim, self.runner.world)
                np.testing.assert_allclose(
                    observation[start:start + 3], (0.8, 0.6, 1.0), atol=1e-6)

    def test_runtime_selects_waypoint_before_model_inference(self) -> None:
        from rl.rl_runtime import RuntimeController

        class Model:
            def __init__(self, action):
                self.action = np.asarray(action)
                self.observation = None

            def predict(self, observation, **_kwargs):
                self.observation = observation.copy()
                return self.action, None

        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_WAYPOINT_START, [2, 1, 2, 0, 0]),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_WAYPOINT_START, [2, 1, 0, 0, 0]),
        )
        for boat_type, version, start, action in cases:
            with self.subTest(boat_type=boat_type):
                runner = HeadlessRunner(map_name="world", seed=61542)
                runner.reset(seed=61542)
                position = runner.random_ocean_position(margin=500.0)
                sid = runner.spawn_bot(
                    boat_type=boat_type, external_control=True, ai=None,
                    position=position, rotation=0.0, team_id="agent")
                bot = runner.legacy.bots[sid]
                bot["rl_control_version"] = version
                model = Model(action)
                RuntimeController(model, waypoint_seed=91).tick(
                    bot, runner.sim, runner.world, 0.05)
                self.assertIsNotNone(bot.get("rl_waypoint"))
                self.assertIsNotNone(model.observation)
                self.assertGreater(model.observation[start + 2], 0.0)

    def test_runtime_manual_checkpoint_pauses_runs_and_stops_at_arrival(self) -> None:
        from rl.rl_runtime import RuntimeController

        class Model:
            def __init__(self, action):
                self.action = np.asarray(action)
                self.calls = 0

            def predict(self, observation, **_kwargs):
                self.calls += 1
                return self.action, None

        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION, [2, 1, 2, 0, 0]),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION, [2, 1, 0, 0, 0]),
        )
        for boat_type, version, action in cases:
            with self.subTest(boat_type=boat_type):
                runner = HeadlessRunner(map_name="world", seed=61543)
                runner.reset(seed=61543)
                sid = runner.spawn_bot(
                    boat_type=boat_type, external_control=True, ai=None,
                    position=runner.random_ocean_position(margin=500.0),
                    rotation=0.0, team_id="agent")
                bot = runner.legacy.bots[sid]
                bot.update(rl_control_version=version, rl_manual_checkpoint=True,
                           rl_waypoint=None, speed=1.0, rudder=0.2,
                           vertical_speed_us=0.1)
                model = Model(action)
                controller = RuntimeController(model, waypoint_seed=92)

                controller.tick(bot, runner.sim, runner.world, 0.05)
                self.assertEqual(0, model.calls)
                self.assertEqual(0.0, bot["speed"])
                self.assertEqual(0.0, bot["rudder"])
                if boat_type == "submarine":
                    self.assertEqual(0.0, bot["vertical_speed_us"])

                first = {
                    "x": bot["position"]["x"] + 100.0,
                    "z": bot["position"]["z"],
                }
                destination = {
                    "x": bot["position"]["x"] + 200.0,
                    "z": bot["position"]["z"],
                }
                bot["rl_waypoint"] = first
                bot["rl_destination"] = destination
                bot["rl_route_waypoints"] = [destination]
                controller.next_decision_at = 0.0
                controller.tick(bot, runner.sim, runner.world, 0.05)
                self.assertEqual(1, model.calls)

                bot["position"].update({"x": first["x"] - 45.0, "z": first["z"]})
                controller.next_decision_at = 0.0
                controller.tick(bot, runner.sim, runner.world, 0.05)
                self.assertEqual(2, model.calls)
                self.assertEqual(destination, bot["rl_waypoint"])
                self.assertEqual([], bot["rl_route_waypoints"])

                bot["position"].update({
                    "x": destination["x"] - 19.0, "z": destination["z"]})
                controller.next_decision_at = 0.0
                controller.tick(bot, runner.sim, runner.world, 0.05)
                self.assertEqual(2, model.calls)
                self.assertIsNone(bot["rl_waypoint"])
                self.assertEqual(2, bot["rl_waypoints_reached"])
                self.assertEqual(0.0, bot["speed"])

    def test_submarine_observes_actual_signed_vertical_speed_ratio(self) -> None:
        bot = self._spawn("submarine", SUBMARINE_V3_OBSERVATION_VERSION)
        bot["position"]["y"] = -1.0
        bot["control_target_depth_y"] = -2.0
        self.runner.sim.update_bot_external(bot, 0.2, self.runner.world)
        descending = build_observation(bot, self.runner.sim, self.runner.world)
        self.assertAlmostEqual(-1.0, descending[3], places=6)

        bot["control_target_depth_y"] = -0.2
        self.runner.sim.update_bot_external(bot, 0.2, self.runner.world)
        ascending = build_observation(bot, self.runner.sim, self.runner.world)
        self.assertAlmostEqual(1.0, ascending[3], places=6)

        bot["control_target_depth_y"] = bot["position"]["y"]
        self.runner.sim.update_bot_external(bot, 0.2, self.runner.world)
        stable = build_observation(bot, self.runner.sim, self.runner.world)
        self.assertEqual(0.0, stable[3])

    def test_new_spaces_are_unambiguous_and_runtime_identifiable(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_OBS_DIM, SUBMARINE_V3_ACTION_NVECS),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_OBS_DIM, DESTROYER_V5_ACTION_NVECS),
            ("submarine", SUBMARINE_V4_OBSERVATION_VERSION,
             SUBMARINE_V4_OBS_DIM, SUBMARINE_V4_ACTION_NVECS),
            ("destroyer", DESTROYER_V6_OBSERVATION_VERSION,
             DESTROYER_V6_OBS_DIM, DESTROYER_V6_ACTION_NVECS),
        )
        for boat_type, version, dimension, nvec in cases:
            with self.subTest(boat_type=boat_type):
                self.assertEqual((version, dimension, tuple(nvec)), (
                    control_spec(boat_type, version)[0],
                    control_spec(boat_type, version)[1],
                    tuple(control_spec(boat_type, version)[2])))
                self.assertEqual(
                    version, control_version_for_spaces(boat_type, dimension, nvec))

    def test_directional_spaces_are_runtime_identifiable(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_OBS_DIM, SUBMARINE_V3_ACTION_NVECS),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_OBS_DIM, DESTROYER_V5_ACTION_NVECS),
        )
        for boat_type, version, dimension, nvec in cases:
            with self.subTest(boat_type=boat_type):
                self.assertEqual(
                    (version, dimension, tuple(nvec)),
                    (control_spec(boat_type, version)[0],
                     control_spec(boat_type, version)[1],
                     tuple(control_spec(boat_type, version)[2])))
                self.assertEqual(version, control_version_for_spaces(
                    boat_type, dimension, nvec, version))
                self.assertEqual(version, control_version_for_spaces(
                    boat_type, dimension, nvec))

    def test_directional_torpedo_slots_encode_bearing_distance_cpa_and_type(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_TORPEDO_START, SUBMARINE_V3_LURE_START),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_TORPEDO_START, DESTROYER_V5_LURE_START),
        )
        expected_types = {
            "acoustic": (1.0, 0.0, 0.0),
            "autonomous": (0.0, 1.0, 0.0),
            "wireGuided": (0.0, 0.0, 1.0),
        }
        for boat_type, version, start, lure_start in cases:
            for kind, type_one_hot in expected_types.items():
                with self.subTest(boat_type=boat_type, kind=kind):
                    self.runner.reset(seed=61542)
                    self.runner.world["islands"] = []
                    self.runner.world["thermoclines"] = []
                    bot = self._spawn(boat_type, version)
                    torpedo = self._torpedo(bot, kind)
                    self.runner.sim.torpedoes[("enemy", 1)] = torpedo
                    observation = build_observation(
                        bot, self.runner.sim, self.runner.world)
                    slot = observation[start:start + MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM]
                    self.assertEqual(MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM, len(slot))
                    self.assertEqual(1.0, slot[0])
                    self.assertAlmostEqual(0.0, slot[1], places=6)
                    self.assertAlmostEqual(1.0, slot[2], places=6)
                    self.assertAlmostEqual(0.01, slot[3], places=6)
                    self.assertAlmostEqual(-0.1, slot[4], places=6)
                    self.assertAlmostEqual(0.0, slot[5], places=6)
                    self.assertAlmostEqual(0.0, slot[6], places=6)
                    self.assertAlmostEqual(1.0, slot[7], places=6)
                    np.testing.assert_array_equal(type_one_hot, slot[8:11])
                    self.assertEqual(
                        6 * MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM,
                        lure_start - start)

    def test_directional_lure_slots_encode_bearing_distance_lifetime_and_owner(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_LURE_START, SUBMARINE_V3_GRENADE_START),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_LURE_START, DESTROYER_V5_GRENADE_START),
        )
        for boat_type, version, start, grenade_start in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                self.runner.world["islands"] = []
                self.runner.world["thermoclines"] = []
                bot = self._spawn(boat_type, version)
                self.runner.sim.lures[(bot["id"], 1)] = {
                    "ownerId": bot["id"], "lid": 1,
                    "x": -3.0, "y": 0.0, "z": 4.0, "expiresAt": 60.0,
                }
                self.runner.sim.lures[("enemy", 2)] = {
                    "ownerId": "enemy", "lid": 2,
                    "x": -6.0, "y": 0.0, "z": 8.0, "expiresAt": 30.0,
                }
                observation = build_observation(
                    bot, self.runner.sim, self.runner.world)
                own = observation[start:start + MOBILITY_DIRECTIONAL_LURE_SLOT_DIM]
                foreign = observation[
                    start + MOBILITY_DIRECTIONAL_LURE_SLOT_DIM:
                    start + 2 * MOBILITY_DIRECTIONAL_LURE_SLOT_DIM]
                np.testing.assert_allclose(
                    (1.0, 0.8, 0.6, 0.005, 0.5, 1.0), own, atol=1e-6)
                np.testing.assert_allclose(
                    (1.0, 0.8, 0.6, 0.01, 0.25, -1.0), foreign, atol=1e-6)
                self.assertEqual(
                    6 * MOBILITY_DIRECTIONAL_LURE_SLOT_DIM,
                    grenade_start - start)

    def test_directional_grenade_slots_encode_bearing_trajectory_and_effect(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_GRENADE_START, SUBMARINE_V3_RAY_START),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_GRENADE_START, DESTROYER_V5_RAY_START),
        )
        for boat_type, version, start, ray_start in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                self.runner.world["islands"] = []
                self.runner.world["thermoclines"] = []
                bot = self._spawn(boat_type, version)
                grenade = {
                    "ownerPlayerId": bot["id"], "gid": 1, "phase": "water",
                    "x": -3.0, "y": -1.0, "z": 4.0,
                    "vx": 2.0, "vy": 0.0, "vz": 4.0,
                    "targetDepthU": 5.0, "sinkSpeedU": 0.5,
                    "effectRadiusU": 20.0,
                }
                self.runner.sim.grenades[(bot["id"], 1)] = grenade
                observation = build_observation(
                    bot, self.runner.sim, self.runner.world)
                slot = observation[start:start + MOBILITY_DIRECTIONAL_GRENADE_SLOT_DIM]
                max_depth_u = max(
                    1.0, float(bot.get("max_depth_m", 200.0))) / simulation.UNIT_METERS_BOT
                expected_depth = max(-1.0, min(
                    1.0,
                    (-5.0 - float(bot["position"].get("y", 0.0))) / max_depth_u))
                np.testing.assert_allclose((
                    1.0, 0.8, 0.6, 0.005, -0.001, 0.002,
                    expected_depth, 8.0 / 120.0, 0.4, 1.0,
                ), slot, atol=1e-6)
                grenade["ownerPlayerId"] = "enemy"
                foreign = build_observation(
                    bot, self.runner.sim, self.runner.world)
                self.assertEqual(-1.0, foreign[start + 9])
                self.assertEqual(
                    6 * MOBILITY_DIRECTIONAL_GRENADE_SLOT_DIM,
                    ray_start - start)

    def test_directional_obstacle_rays_are_dense_ahead_and_encode_proximity(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION, SUBMARINE_V3_RAY_START),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION, DESTROYER_V5_RAY_START),
        )
        expected_angles = (
            -150, -120, -90, -60, -45, -30, -15, 0,
            15, 30, 45, 60, 90, 120, 150, 180,
        )
        self.assertEqual(expected_angles, DIRECTIONAL_RAY_DIRECTIONS_DEG)
        for boat_type, version, start in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                self.runner.world["islands"] = []
                self.runner.world["thermoclines"] = []
                bot = self._spawn(boat_type, version)
                clear = build_observation(
                    bot, self.runner.sim, self.runner.world)[start:start + 16]
                np.testing.assert_array_equal(np.zeros(16), clear)

                self.runner.world["islands"] = [{"points": [
                    {"x": -12.0, "z": -2.0}, {"x": -8.0, "z": -2.0},
                    {"x": -8.0, "z": 2.0}, {"x": -12.0, "z": 2.0},
                ]}]
                front = build_observation(
                    bot, self.runner.sim, self.runner.world)[start:start + 16]
                self.assertAlmostEqual(0.9, front[7], places=6)

                self.runner.world["islands"] = [{"points": [
                    {"x": 8.0, "z": -2.0}, {"x": 12.0, "z": -2.0},
                    {"x": 12.0, "z": 2.0}, {"x": 8.0, "z": 2.0},
                ]}]
                rear = build_observation(
                    bot, self.runner.sim, self.runner.world)[start:start + 16]
                self.assertAlmostEqual(0.9, rear[15], places=6)

    def test_v14_long_range_rays_reveal_a_distant_front_obstacle(self) -> None:
        self.assertEqual((-90, -60, -30, 0, 30, 60, 90),
                         LONG_RANGE_RAY_DIRECTIONS_DEG)
        self.assertEqual(2500.0, LONG_RANGE_RAY_MAX_M)
        cases = (
            ("submarine", SUBMARINE_V4_OBSERVATION_VERSION,
             SUBMARINE_V4_LONG_RAY_START, SUBMARINE_V4_WAYPOINT_START),
            ("destroyer", DESTROYER_V6_OBSERVATION_VERSION,
             DESTROYER_V6_LONG_RAY_START, DESTROYER_V6_WAYPOINT_START),
        )
        for boat_type, version, start, waypoint_start in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                self.runner.world["islands"] = [{"points": [
                    {"x": -155.0, "z": -5.0}, {"x": -150.0, "z": -5.0},
                    {"x": -150.0, "z": 5.0}, {"x": -155.0, "z": 5.0},
                ]}]
                self.runner.world["thermoclines"] = []
                bot = self._spawn(boat_type, version)
                bot["rl_waypoint"] = {"x": -400.0, "z": 0.0}
                observation = build_observation(bot, self.runner.sim, self.runner.world)
                rays = observation[start:waypoint_start]
                self.assertEqual(7, len(rays))
                self.assertAlmostEqual(0.38, rays[3], places=6)
                np.testing.assert_allclose(
                    (0.0, 1.0, 0.8), observation[waypoint_start:], atol=1e-7)

    def test_navigable_path_rewards_the_correct_side_of_an_island(self) -> None:
        world = {
            "ground": {"width": 100.0, "depth": 100.0},
            "islands": [{"points": [
                {"x": -5.0, "z": -10.0}, {"x": 5.0, "z": -10.0},
                {"x": 5.0, "z": 10.0}, {"x": -5.0, "z": 10.0},
            ]}],
        }
        world["nav_graph"] = build_nav_graph(
            world, margin_m=10.0, unit_meters=simulation.UNIT_METERS_BOT)
        metric = NavigablePathMetric(world)
        goal = (15.0, 0.0)
        before = (-15.0, 0.0)
        after = (-15.0, 1.0)
        metric.set_goal(goal)

        self.assertGreater(math.hypot(after[0] - goal[0], after[1] - goal[1]),
                           math.hypot(before[0] - goal[0], before[1] - goal[1]))
        self.assertLess(metric.distance_m(after), metric.distance_m(before))

    def test_runtime_route_uses_distant_open_waypoints(self) -> None:
        world = {
            "ground": {"width": 400.0, "depth": 400.0},
            "islands": [{"points": [
                {"x": -5.0, "z": -10.0}, {"x": 5.0, "z": -10.0},
                {"x": 5.0, "z": 10.0}, {"x": -5.0, "z": 10.0},
            ]}],
        }
        start, goal = (-80.0, 0.0), (80.0, 0.0)
        route = plan_segmented_route(world, start, goal)
        metric = NavigablePathMetric(
            world, clearance_m=ROUTE_CLEARANCE_M,
            endpoint_clearance_m=DESTINATION_CLEARANCE_M,
            node_margin_m=ROUTE_NODE_MARGIN_M)

        self.assertEqual(500.0, ROUTE_CLEARANCE_M)
        self.assertEqual(600.0, ROUTE_NODE_MARGIN_M)
        self.assertTrue(metric.nodes)
        self.assertTrue(all(
            geometry.min_distance_to_islands(
                node["x"], node["z"], world) * simulation.UNIT_METERS_BOT
            > ROUTE_CLEARANCE_M
            for node in metric.nodes))
        self.assertFalse(geometry.line_of_sight_clear(*start, *goal, world))
        self.assertEqual((goal,), route)
        with self.assertRaisesRegex(ValueError, "zone navigable"):
            metric.set_goal((15.0, 0.0))
        with self.assertRaisesRegex(ValueError, "zone navigable"):
            metric.set_goal((190.0, 0.0))

        segmented = segment_route((
            (0.0, 0.0), (300.0, 0.0), (600.0, 0.0),
            (900.0, 0.0), (900.0, 300.0)))
        self.assertEqual(((600.0, 0.0), (900.0, 300.0)), segmented)
        all_points = ((0.0, 0.0), *segmented)
        lengths_m = [
            math.hypot(right[0] - left[0], right[1] - left[1])
            * simulation.UNIT_METERS_BOT
            for left, right in zip(all_points, all_points[1:])
        ]
        self.assertLessEqual(max(lengths_m), ROUTE_LONG_SEGMENT_M)

    def test_segmented_evaluation_completes_only_at_final_destination(self) -> None:
        from rl.train_mobility import env_kwargs, load_config

        config = load_config(
            Path(__file__).resolve().parent
            / "configs/aidest_mobility_runtime_v14.json")
        env = MobilityEnv(**env_kwargs(config), seed=91542, segmented_routes=True)
        try:
            _, reset_info = env.reset(seed=91542, options={
                "route_category": "visible",
                "position": (-100.0, 600.0),
                "rotation": math.pi,
                "waypoint": {"x": 410.0, "z": 600.0},
            })
            bot = env._agent()
            self.assertEqual("visible", reset_info["route_category"])
            self.assertEqual([{"x": 410.0, "z": 600.0}], bot["rl_route"])
            for waypoint in bot["rl_route"][:-1]:
                bot["position"].update(waypoint)
                self.assertTrue(env._ensure_waypoint(bot))
                self.assertFalse(env._route_arrived)
            bot["position"].update(bot["rl_route"][-1])
            _, _, terminated, truncated, info = env.step([2, 1, 0, 0, 0])
            self.assertTrue(terminated)
            self.assertFalse(truncated)
            self.assertEqual("completed", info["outcome"])
            self.assertTrue(info["route_arrived"])
            self.assertIsNone(bot["rl_waypoint"])
        finally:
            env.close()

    def test_directional_contact_encodes_bearing_and_memory_presence(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION, "destroyer",
             SUBMARINE_V3_CONTACT_START),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION, "submarine",
             DESTROYER_V5_CONTACT_START),
        )
        for boat_type, version, enemy_type, contact_start in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                self.runner.world["islands"] = []
                self.runner.world["thermoclines"] = []
                observer = self._spawn(boat_type, version)
                enemy_sid = self.runner.spawn_bot(
                    boat_type=enemy_type, external_control=True, ai=None,
                    position=(-3.0, 4.0), rotation=0.0, team_id="enemy")
                enemy = self.runner.legacy.bots[enemy_sid]
                for boat in (observer, enemy):
                    flotation = float(boat["boat"].get("flotation", 2.0))
                    boat["position"]["y"] = -flotation / simulation.UNIT_METERS_BOT
                    self.runner.legacy.players[boat["sid"]]["position"]["y"] = (
                        boat["position"]["y"])

                with (patch.object(self.runner.sim, "detect_enemies_passive", return_value=[]),
                      patch.object(self.runner.sim, "active_sonar_contacts", return_value=[])):
                    visible = build_observation(observer, self.runner.sim, self.runner.world)
                    self.assertEqual(1.0, visible[contact_start])
                    self.assertAlmostEqual(0.8, visible[contact_start + 1], places=6)
                    self.assertAlmostEqual(0.6, visible[contact_start + 2], places=6)
                    self.assertAlmostEqual(0.01, visible[contact_start + 3], places=6)
                    expected_depth = (
                        -float(enemy["position"]["y"]) * simulation.UNIT_METERS_BOT
                        / CONTACT_DEPTH_MAX_M)
                    self.assertAlmostEqual(
                        expected_depth, visible[contact_start + 5], places=6)

                    enemy["position"]["y"] -= 1.0
                    self.runner.legacy.players[enemy_sid]["position"]["y"] = (
                        enemy["position"]["y"])
                    with patch.object(self.runner.sim, "now", return_value=5.0):
                        remembered = build_observation(
                            observer, self.runner.sim, self.runner.world)
                    self.assertEqual(1.0, remembered[contact_start])
                    self.assertAlmostEqual(1.0 / 6.0, remembered[contact_start + 4], places=6)

                    with patch.object(self.runner.sim, "now", return_value=31.0):
                        expired = build_observation(observer, self.runner.sim, self.runner.world)
                    np.testing.assert_array_equal(
                        np.zeros(7), expired[contact_start:contact_start + 7])

    def test_torpedo_kind_is_one_hot_but_private_lock_is_ignored(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V2_OBSERVATION_VERSION,
             SUBMARINE_V2_TORPEDO_START),
            ("destroyer", DESTROYER_V4_OBSERVATION_VERSION,
             DESTROYER_V4_TORPEDO_START),
        )
        kinds = {"acoustic": (1.0, 0.0, 0.0),
                 "autonomous": (0.0, 1.0, 0.0),
                 "wireGuided": (0.0, 0.0, 1.0)}
        for boat_type, version, start in cases:
            for kind, expected in kinds.items():
                with self.subTest(boat_type=boat_type, kind=kind):
                    self.runner.reset(seed=61542)
                    self.runner.world["islands"] = []
                    self.runner.world["thermoclines"] = []
                    bot = self._spawn(boat_type, version)
                    torpedo = self._torpedo(bot, kind)
                    self.runner.sim.torpedoes[("enemy", 1)] = torpedo
                    observation = build_observation(bot, self.runner.sim, self.runner.world)
                    self.assertTrue(bot["rl_torpedo_detected"])
                    slot = observation[start:start + MOBILITY_TORPEDO_SLOT_DIM]
                    np.testing.assert_array_equal(expected, slot[7:10])
                    baseline = observation.copy()
                    torpedo["acquiredBoatId"] = None
                    torpedo["targetId"] = "another-private-target"
                    np.testing.assert_array_equal(
                        baseline, build_observation(bot, self.runner.sim, self.runner.world))

    def test_hidden_torpedo_does_not_fill_a_typed_slot(self) -> None:
        bot = self._spawn("submarine", SUBMARINE_V2_OBSERVATION_VERSION)
        torpedo = self._torpedo(bot, "wireGuided")
        self.runner.sim.torpedoes[("enemy", 1)] = torpedo
        self.runner.world["islands"] = [{"points": [
            {"x": -6.0, "z": -2.0}, {"x": -4.0, "z": -2.0},
            {"x": -4.0, "z": 2.0}, {"x": -6.0, "z": 2.0},
        ]}]
        observation = build_observation(bot, self.runner.sim, self.runner.world)
        self.assertFalse(bot["rl_torpedo_detected"])
        np.testing.assert_array_equal(
            np.zeros(MOBILITY_TORPEDO_SLOT_DIM),
            observation[SUBMARINE_V2_TORPEDO_START:
                        SUBMARINE_V2_TORPEDO_START + MOBILITY_TORPEDO_SLOT_DIM])

    def test_public_grenade_trajectory_integrity_and_rays_are_present(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V2_OBSERVATION_VERSION, SUBMARINE_V2_OBS_DIM,
             SUBMARINE_V2_GRENADE_START, SUBMARINE_V2_RAY_START, 3),
            ("destroyer", DESTROYER_V4_OBSERVATION_VERSION, DESTROYER_V4_OBS_DIM,
             DESTROYER_V4_GRENADE_START, DESTROYER_V4_RAY_START, 2),
        )
        for boat_type, version, dimension, grenade_start, ray_start, integrity_index in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                self.runner.world["islands"] = []
                self.runner.world["thermoclines"] = []
                bot = self._spawn(boat_type, version)
                bot["integrity"] = bot["maxIntegrity"] / 2.0
                self.runner.sim.grenades[("enemy", 1)] = {
                    "ownerPlayerId": "enemy", "gid": 1, "phase": "water",
                    "x": -10.0, "y": -1.0, "z": 0.0,
                    "vx": 0.0, "vy": 0.0, "vz": 0.0,
                    "targetDepthU": 5.0, "sinkSpeedU": 0.4,
                    "effectRadiusU": 20.0,
                }
                observation = build_observation(bot, self.runner.sim, self.runner.world)
                self.assertEqual((dimension,), observation.shape)
                self.assertEqual(np.float32, observation.dtype)
                self.assertAlmostEqual(0.5, observation[integrity_index])
                self.assertEqual(1.0, observation[grenade_start])
                self.assertEqual(-1.0, observation[
                    grenade_start + MOBILITY_GRENADE_SLOT_DIM - 1])
                self.assertEqual(8, len(observation[ray_start:]))
                self.assertTrue(np.all(observation >= -1.0))
                self.assertTrue(np.all(observation <= 1.0))

    def test_visual_contact_requires_two_surface_boats_and_clear_geometry(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V2_OBSERVATION_VERSION, "destroyer", 10),
            ("destroyer", DESTROYER_V4_OBSERVATION_VERSION, "submarine", 14),
        )
        for boat_type, version, enemy_type, contact_start in cases:
            with self.subTest(boat_type=boat_type):
                self.runner.reset(seed=61542)
                self.runner.world["islands"] = []
                observer = self._spawn(boat_type, version)
                enemy_sid = self.runner.spawn_bot(
                    boat_type=enemy_type, external_control=True, ai=None,
                    position=(-10.0, 0.0), rotation=0.0, team_id="enemy")
                enemy = self.runner.legacy.bots[enemy_sid]
                for boat in (observer, enemy):
                    flotation = float(boat["boat"].get("flotation", 2.0))
                    boat["position"]["y"] = -flotation / simulation.UNIT_METERS_BOT
                    self.runner.legacy.players[boat["sid"]]["position"]["y"] = (
                        boat["position"]["y"])
                with (patch.object(self.runner.sim, "detect_enemies_passive", return_value=[]),
                      patch.object(self.runner.sim, "active_sonar_contacts", return_value=[])):
                    visible = build_observation(observer, self.runner.sim, self.runner.world)
                    self.assertEqual(1.0, visible[contact_start])
                    self.assertAlmostEqual(10.0 / 300.0, visible[contact_start + 1], places=6)

                    observer["position"]["y"] -= 0.1
                    hidden_observer = build_observation(
                        observer, self.runner.sim, self.runner.world)
                    self.assertEqual(0.0, hidden_observer[contact_start])
                    observer["position"]["y"] += 0.1

                    enemy["position"]["y"] -= 0.1
                    self.runner.legacy.players[enemy_sid]["position"]["y"] = (
                        enemy["position"]["y"])
                    hidden_enemy = build_observation(observer, self.runner.sim, self.runner.world)
                    self.assertEqual(0.0, hidden_enemy[contact_start])
                    enemy["position"]["y"] += 0.1
                    self.runner.legacy.players[enemy_sid]["position"]["y"] = (
                        enemy["position"]["y"])

                    self.runner.world["islands"] = [{"points": [
                        {"x": -6.0, "z": -2.0}, {"x": -4.0, "z": -2.0},
                        {"x": -4.0, "z": 2.0}, {"x": -6.0, "z": 2.0},
                    ]}]
                    occluded = build_observation(observer, self.runner.sim, self.runner.world)
                    self.assertEqual(0.0, occluded[contact_start])


class MobilityEnvironmentTest(unittest.TestCase):
    def _environment(self, boat_type: str, **kwargs) -> MobilityEnv:
        options = {
            "boat_type": boat_type,
            "seed": 62542,
            "frame_skip": 2,
            "max_episode_seconds": 1.0,
            "obstacle_probability_start": 0.0,
            "obstacle_probability_end": 0.0,
        }
        options.update(kwargs)
        env = MobilityEnv(**options)
        env.runner.world["islands"] = []
        env.runner.world["thermoclines"] = []
        return env

    def test_defaults_use_final_runtime_spaces(self) -> None:
        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION,
             SUBMARINE_V3_OBS_DIM, SUBMARINE_V3_ACTION_NVECS),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             DESTROYER_V5_OBS_DIM, DESTROYER_V5_ACTION_NVECS),
        )
        for boat_type, version, dimension, nvec in cases:
            with self.subTest(boat_type=boat_type):
                env = self._environment(boat_type)
                try:
                    observation, info = env.reset(
                        seed=62542, options={"position": (100.0, 80.0),
                                             "rotation": 0.0, "obstacle": False})
                    self.assertEqual(version, env.control_version)
                    self.assertEqual(version, info["control_version"])
                    self.assertEqual((dimension,), observation.shape)
                    self.assertEqual(tuple(nvec), tuple(env.action_space.nvec))
                    self.assertTrue(env.observation_space.contains(observation))
                finally:
                    env.close()

    def test_v14_configs_use_path_progress_and_route_curriculum(self) -> None:
        from stable_baselines3.common.env_checker import check_env
        from rl.train_mobility import load_config, make_env

        root = Path(__file__).resolve().parent
        cases = (
            ("configs/aisub_mobility_runtime_v14.json", "submarine",
             SUBMARINE_V4_OBSERVATION_VERSION),
            ("configs/aidest_mobility_runtime_v14.json", "destroyer",
             DESTROYER_V6_OBSERVATION_VERSION),
        )
        expected_routes = {
            "visible": 0.2,
            "small_obstruction": 0.25,
            "behind_island": 0.3,
            "long_detour": 0.15,
            "complex": 0.1,
        }
        for filename, boat_type, version in cases:
            with self.subTest(boat_type=boat_type):
                config = load_config(root / filename)
                self.assertEqual(version, config["env"]["control_version"])
                self.assertEqual("navigable_path", config["env"]["progress_mode"])
                self.assertEqual(expected_routes, config["env"]["route_curriculum"])
                self.assertEqual(0.25, config["reward"]["clearance_progress"])
                self.assertEqual(
                    0.7, config["evaluation"]["behavior_gates"][
                        "min_waypoint_arrival_rate"])
                env = make_env(config, int(config["training"]["seed"]))()
                try:
                    check_env(env, warn=True)
                finally:
                    env.close()

    def test_v14_curriculum_samples_each_requested_route_category(self) -> None:
        from rl.navigable_path import blocking_island_count
        from rl.train_mobility import load_config, make_env

        root = Path(__file__).resolve().parent
        config = load_config(root / "configs/aidest_mobility_runtime_v14.json")
        env = make_env(config, int(config["training"]["seed"]))()
        try:
            for index, category in enumerate(config["env"]["route_curriculum"]):
                with self.subTest(category=category):
                    _, info = env.reset(
                        seed=90542 + index, options={"route_category": category})
                    bot = env._agent()
                    start = (float(bot["position"]["x"]), float(bot["position"]["z"]))
                    waypoint = bot["rl_waypoint"]
                    goal = (float(waypoint["x"]), float(waypoint["z"]))
                    direct_m = math.hypot(
                        goal[0] - start[0], goal[1] - start[1]) * simulation.UNIT_METERS_BOT
                    blockers = blocking_island_count(start, goal, env.runner.world)
                    path_m = env._path_metric.distance_m(start)
                    self.assertEqual(category, info["route_category"])
                    self.assertTrue(math.isfinite(path_m))
                    self.assertTrue(env._route_matches(
                        category, blockers, path_m / direct_m))
        finally:
            env.close()

    def test_gym_contract_and_fresh_configs(self) -> None:
        from stable_baselines3.common.env_checker import check_env
        from rl.train_mobility import load_config, make_env

        root = Path(__file__).resolve().parent
        cases = (
            ("configs/aisub_mobility_runtime_v13.json", "submarine",
             SUBMARINE_V3_OBSERVATION_VERSION),
            ("configs/aidest_mobility_runtime_v13.json", "destroyer",
             DESTROYER_V5_OBSERVATION_VERSION),
        )
        for filename, boat_type, version in cases:
            with self.subTest(boat_type=boat_type):
                config = load_config(root / filename)
                self.assertEqual(version, config["env"]["control_version"])
                self.assertNotIn("movement_per_meter", config["reward"])
                self.assertEqual(0.005, config["reward"]["waypoint_progress_per_meter"])
                self.assertEqual(5.0, config["reward"]["waypoint_reached"])
                self.assertEqual(-0.002, config["reward"]["rudder_change"])
                self.assertEqual(-0.05, config["reward"]["coastal_proximity"])
                self.assertEqual(1.0, config["reward"]["clearance_progress"])
                self.assertEqual(-10.0, config["reward"]["coastal_damage"])
                self.assertEqual(250, config["env"]["coastal_clearance_m"])
                self.assertEqual(600, config["env"]["max_episode_seconds"])
                self.assertEqual(100000, config["evaluation"]["every_steps"])
                self.assertEqual(20, config["evaluation"]["episodes"])
                for key in (
                        "silent_speed_ratio", "noisy_speed_ratio", "reverse_per_meter",
                        "rudder_use", "rudder_without_threat", "depth_change_per_meter",
                        "weapon_request", "weapon_without_acquisition", "lure_request",
                        "lure_without_threat", "sonar_request"):
                    self.assertEqual(0.0, config["reward"][key])
                self.assertEqual(
                    0.01,
                    config["evaluation"]["behavior_gates"][
                        "max_coastal_damage_episode_fraction"])
                gates = config["evaluation"]["behavior_gates"]
                self.assertEqual(0, gates["max_sunk_count"])
                self.assertEqual(2, gates["max_stuck_count"])
                self.assertEqual(0.5, gates["min_mean_straightness"])
                self.assertNotIn("min_completion_rate", gates)
                self.assertNotIn("min_open_completion_rate", gates)
                self.assertNotIn("min_obstacle_completion_rate", gates)
                self.assertNotIn("max_stuck_rate", gates)
                env = make_env(config, int(config["training"]["seed"]))()
                try:
                    check_env(env, warn=True)
                    observation, _ = env.reset(
                        seed=int(config["training"]["seed"]),
                        options={"obstacle": False})
                    self.assertTrue(env.observation_space.contains(observation))
                finally:
                    env.close()

        for filename in (
                "configs/aisub_mobility_runtime_v14.json",
                "configs/aidest_mobility_runtime_v14.json"):
            config = load_config(root / filename)
            self.assertEqual(1200, config["env"]["max_episode_seconds"])

    def test_delayed_entropy_schedule_starts_after_100k(self) -> None:
        from rl.train_ai import EntropyScheduleCallback

        callback = EntropyScheduleCallback(0.003, 0.0003, 200000, 100000)
        callback.model = type("Model", (), {"ent_coef": None})()
        for timesteps, expected in (
                (0, 0.003), (100000, 0.003),
                (150000, 0.00165), (200000, 0.0003)):
            with self.subTest(timesteps=timesteps):
                callback.num_timesteps = timesteps
                self.assertTrue(callback._on_step())
                self.assertAlmostEqual(expected, callback.model.ent_coef)

    def test_one_percent_coastal_gate_is_inclusive(self) -> None:
        from rl.train_mobility import mobility_gate_report

        config = {"evaluation": {"behavior_gates": {
            "max_coastal_damage_episode_fraction": 0.01,
        }}}
        self.assertTrue(mobility_gate_report(config, {
            "coastal_damage_episode_fraction": 0.01,
        })["passed"])
        self.assertFalse(mobility_gate_report(config, {
            "coastal_damage_episode_fraction": 0.010001,
        })["passed"])

    def test_count_gates_split_sunk_and_stuck_outcomes(self) -> None:
        from rl.train_mobility import mobility_gate_report, validate_mobility_gates

        config = {"evaluation": {"behavior_gates": {
            "max_sunk_count": 0,
            "max_stuck_count": 2,
        }}}
        self.assertTrue(mobility_gate_report(config, {
            "sunk_count": 0.0,
            "stuck_count": 2.0,
        })["passed"])
        report = mobility_gate_report(config, {
            "sunk_count": 1.0,
            "stuck_count": 3.0,
        })
        self.assertEqual(
            ["max_sunk_count", "max_stuck_count"], report["failures"])
        with self.assertRaisesRegex(ValueError, "hors limites"):
            validate_mobility_gates({"evaluation": {"behavior_gates": {
                "max_stuck_count": 1.5,
            }}})

    def test_actions_reach_authoritative_targets_without_override(self) -> None:
        cases = (
            ("submarine", np.array([0, 4, 4, 0, 0]), -1.0, 1.0),
            ("destroyer", np.array([4, 4, 0, 0, 0]), 1.0, 1.0),
        )
        for boat_type, action, rudder, throttle in cases:
            with self.subTest(boat_type=boat_type):
                env = self._environment(boat_type)
                try:
                    env.reset(seed=62542, options={
                        "position": (100.0, 80.0), "rotation": 0.0,
                        "obstacle": False})
                    env.step(action)
                    bot = env._agent()
                    self.assertEqual(rudder, bot["control_target_rudder"])
                    self.assertEqual(throttle, bot["control_target_speed_ratio"])
                    if boat_type == "submarine":
                        self.assertAlmostEqual(
                            -(0.70 * bot["max_depth_m"]) / simulation.UNIT_METERS_BOT,
                            bot["control_target_depth_y"])
                finally:
                    env.close()

    def test_waypoint_sampling_is_deterministic_safe_and_direct(self) -> None:
        env = self._environment("destroyer")
        try:
            env.runner.world["islands"] = [{"points": [
                {"x": 180.0, "z": -400.0}, {"x": 220.0, "z": -400.0},
                {"x": 220.0, "z": 400.0}, {"x": 180.0, "z": 400.0},
            ]}]
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0, "obstacle": False})
            bot = env._agent()
            first = RLWaypointManager(random.Random(77)).sample(bot, env.runner.world)
            second = RLWaypointManager(random.Random(77)).sample(bot, env.runner.world)
            self.assertEqual(first, second)
            distance_m = waypoint_distance_m(bot, first)
            self.assertGreaterEqual(distance_m, WAYPOINT_MIN_DISTANCE_M)
            self.assertLessEqual(distance_m, WAYPOINT_MAX_DISTANCE_M)
            self.assertGreaterEqual(
                geometry.min_distance_to_islands(first["x"], first["z"], env.runner.world)
                * simulation.UNIT_METERS_BOT,
                WAYPOINT_ISLAND_CLEARANCE_M)
            self.assertTrue(geometry.line_of_sight_clear(
                bot["position"]["x"], bot["position"]["z"],
                first["x"], first["z"], env.runner.world))
        finally:
            env.close()

    def test_weapon_requests_without_contact_never_launch_or_activate_threat_slots(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["weapon_without_acquisition"] = -0.1
        cases = (
            ("submarine", SUBMARINE_V3_TORPEDO_START,
              np.array([2, 1, 2, 1, 0])),
            ("destroyer", DESTROYER_V5_TORPEDO_START,
              np.array([2, 1, 1, 0, 0])),
        )
        for boat_type, start, action in cases:
            with self.subTest(boat_type=boat_type):
                env = self._environment(boat_type, frame_skip=1, reward=reward)
                try:
                    env.reset(seed=62542, options={
                        "position": (100.0, 80.0), "rotation": 0.0,
                        "obstacle": False})
                    observation, value, _, _, _ = env.step(action)
                    self.assertFalse(env.runner.sim.torpedoes)
                    self.assertEqual(-0.1, value)
                    np.testing.assert_array_equal(
                        np.zeros(6 * MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM),
                        observation[
                            start:start + 6 * MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM])
                finally:
                    env.close()

    def test_lure_request_without_detected_torpedo_has_dedicated_penalty(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["lure_without_threat"] = -0.2
        cases = (
            ("submarine", np.array([2, 1, 2, 0, 1])),
            ("destroyer", np.array([2, 1, 0, 1, 0])),
        )
        for boat_type, action in cases:
            for detected, expected in ((False, -0.2), (True, 0.0)):
                with self.subTest(boat_type=boat_type, detected=detected):
                    env = self._environment(boat_type, frame_skip=1, reward=reward)
                    try:
                        env.reset(seed=62542, options={
                            "position": (100.0, 80.0), "rotation": 0.0,
                            "obstacle": False})
                        env._agent()["rl_torpedo_detected"] = detected
                        _, value, _, _, _ = env.step(action)
                        self.assertTrue(env.runner.sim.lures)
                        self.assertEqual(expected, value)
                        env._agent()["rl_torpedo_detected"] = detected
                        _, cooldown_value, _, _, _ = env.step(action)
                        self.assertEqual(expected, cooldown_value)
                    finally:
                        env.close()

    def test_rudder_change_penalizes_selected_command_delta_once(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["rudder_change"] = -0.002
        env = self._environment("destroyer", frame_skip=1, reward=reward)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0,
                "obstacle": False})
            _, first, _, _, first_info = env.step(np.array([4, 1, 0, 0, 0]))
            _, second, _, _, second_info = env.step(np.array([4, 1, 0, 0, 0]))
            self.assertEqual(-0.002, first)
            self.assertEqual(1.0, first_info["rudder_change"])
            self.assertEqual(0.0, second)
            self.assertEqual(0.0, second_info["rudder_change"])
        finally:
            env.close()

    def test_forward_speed_reward_has_lower_slope_above_silent_limit(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward.update(silent_speed_ratio=0.02, noisy_speed_ratio=0.005)

        def run(boat_type: str, speed_ratio: float, throttle_index: int) -> float:
            env = self._environment(boat_type, frame_skip=1, reward=reward)
            try:
                env.reset(seed=62542, options={
                    "position": (100.0, 80.0), "rotation": 0.0,
                    "obstacle": False})
                bot = env._agent()
                bot["speed"] = bot["max_speed_us"] * speed_ratio
                action = ([2, throttle_index, 2, 0, 0] if boat_type == "submarine"
                          else [2, throttle_index, 0, 0, 0])
                return env.step(np.array(action))[1]
            finally:
                env.close()

        self.assertAlmostEqual(0.007, run("destroyer", 0.35, 2))
        self.assertAlmostEqual(0.011, run("destroyer", 1.0, 4))
        self.assertAlmostEqual(0.007, run("submarine", 0.35, 2))
        self.assertAlmostEqual(0.017, run("submarine", 1.0, 4))
        self.assertEqual(0.0, run("submarine", -0.35, 0))

    def test_waypoint_progress_rewards_approach_and_penalizes_retreat(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["waypoint_progress_per_meter"] = 0.005
        env = self._environment("destroyer", frame_skip=1, reward=reward)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0,
                "obstacle": False})
            bot = env._agent()
            bot["rl_waypoint"] = {"x": 0.0, "z": 80.0}

            def approach(_dt):
                bot["position"]["x"] -= 0.1

            with patch.object(env.runner, "step", side_effect=approach), \
                    patch.object(env, "_clearances_m", return_value=(1000.0, 1000.0)):
                _, approach_reward, _, _, approach_info = env.step(
                    np.array([2, 1, 0, 0, 0]))

            def retreat(_dt):
                bot["position"]["x"] += 0.1

            with patch.object(env.runner, "step", side_effect=retreat), \
                    patch.object(env, "_clearances_m", return_value=(1000.0, 1000.0)):
                _, retreat_reward, _, _, retreat_info = env.step(
                    np.array([2, 1, 0, 0, 0]))
            self.assertAlmostEqual(1.0, approach_info["waypoint_progress_m_during_frame_skip"])
            self.assertAlmostEqual(0.005, approach_reward)
            self.assertAlmostEqual(-1.0, retreat_info["waypoint_progress_m_during_frame_skip"])
            self.assertAlmostEqual(-0.005, retreat_reward)
        finally:
            env.close()

    def test_v14_reward_uses_navigable_progress_when_direct_distance_worsens(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["waypoint_progress_per_meter"] = 0.005
        env = self._environment(
            "destroyer", control_version=DESTROYER_V6_OBSERVATION_VERSION,
            frame_skip=1, progress_mode="navigable_path", reward=reward)

        class PathMetric:
            def set_goal(self, _goal) -> None:
                return None

            def distance_m(self, start) -> float:
                return 1000.0 - float(start[1]) * simulation.UNIT_METERS_BOT

        env._path_metric = PathMetric()
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0,
                "obstacle": False, "waypoint": {"x": 100.0, "z": 0.0},
            })
            bot = env._agent()
            direct_before = waypoint_distance_m(bot, bot["rl_waypoint"])

            def correct_detour(_dt):
                bot["position"]["z"] += 0.1

            with patch.object(env.runner, "step", side_effect=correct_detour), \
                    patch.object(env, "_clearances_m", return_value=(1000.0, 1000.0)):
                _, value, _, _, info = env.step(np.array([2, 1, 0, 0, 0]))

            self.assertGreater(waypoint_distance_m(bot, bot["rl_waypoint"]), direct_before)
            self.assertAlmostEqual(1.0, info["waypoint_progress_m_during_frame_skip"])
            self.assertAlmostEqual(0.005, value)
        finally:
            env.close()

    def test_reached_waypoint_is_rewarded_counted_and_replaced(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["waypoint_reached"] = 5.0
        env = self._environment("destroyer", frame_skip=1, reward=reward)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0,
                "obstacle": False})
            bot = env._agent()
            old_waypoint = {"x": 119.0, "z": 80.0}
            new_waypoint = {"x": 500.0, "z": 80.0}
            bot["rl_waypoint"] = old_waypoint
            self.assertAlmostEqual(190.0, waypoint_distance_m(bot, old_waypoint))
            with patch.object(env._waypoint_manager, "sample", return_value=new_waypoint):
                _, value, _, _, info = env.step(np.array([2, 1, 0, 0, 0]))
            self.assertEqual(5.0, value)
            self.assertEqual(1, info["waypoints_reached_during_frame_skip"])
            self.assertEqual(1, env._waypoints_reached)
            self.assertEqual(new_waypoint, bot["rl_waypoint"])
        finally:
            env.close()

    def test_terminal_metrics_include_last_movement(self) -> None:
        env = self._environment("destroyer", max_episode_seconds=0.1)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0, "obstacle": False})
            _, _, terminated, truncated, info = env.step(np.array([2, 4, 0, 0, 0]))
            self.assertFalse(terminated)
            self.assertTrue(truncated)
            self.assertEqual("completed", info["outcome"])
            self.assertGreater(info["displacement_m"], 0.0)
            self.assertGreater(info["speed_path_length_m"], 0.0)
            self.assertGreater(info["speed_elapsed_seconds"], 0.0)
            self.assertGreater(info["forward_path_length_m"], 0.0)
            self.assertAlmostEqual(1.0, info["straightness"])
        finally:
            env.close()

    def test_near_coast_movement_is_excluded_from_speed_and_straightness(self) -> None:
        env = self._environment("destroyer", max_episode_seconds=0.1)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0, "obstacle": False})
            with patch.object(
                    env, "_clearances_m",
                    return_value=(METRIC_EXEMPTION_M, METRIC_EXEMPTION_M)):
                _, _, terminated, truncated, info = env.step(
                    np.array([2, 4, 0, 0, 0]))
            self.assertFalse(terminated)
            self.assertTrue(truncated)
            self.assertGreater(info["path_length_m"], 0.0)
            self.assertEqual(0.0, info["speed_path_length_m"])
            self.assertEqual(0.0, info["speed_elapsed_seconds"])
            self.assertEqual(0.0, info["forward_path_length_m"])
            self.assertEqual(0.0, info["straightness"])
            self.assertEqual(0.0, info["mean_speed_ratio"])
        finally:
            env.close()

    def test_coastal_turn_splits_straightness_into_independent_segments(self) -> None:
        env = self._environment("destroyer")
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0, "obstacle": False})
            env._record_open_water_motion(10.0, 10.0, 10.0, 0.0, 1.0, 150.0)
            env._record_open_water_motion(2.0, 2.0, 0.0, 2.0, 1.0, 100.0)
            env._record_open_water_motion(10.0, 10.0, -10.0, 0.0, 1.0, 150.0)
            info = env._terminal_info("completed")
            self.assertEqual(20.0, info["speed_path_length_m"])
            self.assertEqual(2.0, info["speed_elapsed_seconds"])
            self.assertEqual(20.0, info["forward_path_length_m"])
            self.assertEqual(20.0, info["forward_displacement_m"])
            self.assertEqual(1.0, info["straightness"])
        finally:
            env.close()

    def test_reverse_segments_do_not_contribute_to_straightness(self) -> None:
        env = self._environment("destroyer", max_episode_seconds=0.1)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0, "obstacle": False})
            bot = env._agent()
            bot["speed"] = -0.35 * bot["max_speed_us"]
            _, _, terminated, truncated, info = env.step(np.array([2, 0, 0, 0, 0]))
            self.assertFalse(terminated)
            self.assertTrue(truncated)
            self.assertGreater(info["path_length_m"], 0.0)
            self.assertGreater(info["reverse_moved_m"], 0.0)
            self.assertEqual(0.0, info["forward_path_length_m"])
            self.assertEqual(0.0, info["forward_displacement_m"])
            self.assertEqual(0.0, info["straightness"])
        finally:
            env.close()

    def test_frame_skip_separates_forward_and_reverse_motion(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        env = self._environment("destroyer", frame_skip=5, reward=reward)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0,
                "obstacle": False})
            bot = env._agent()
            speeds = iter((1.0, 1.0, -1.0, -1.0, -1.0))

            def move_one_tick(_dt):
                bot["position"]["x"] += 0.1
                bot["speed"] = next(speeds)

            with patch.object(env.runner, "step", side_effect=move_one_tick), \
                    patch.object(env, "_clearances_m", return_value=(1000.0, 1000.0)):
                _, value, _, _, info = env.step(np.array([2, 1, 0, 0, 0]))
            self.assertAlmostEqual(2.0, info["forward_moved_m_during_frame_skip"])
            self.assertAlmostEqual(3.0, info["reverse_moved_m_during_frame_skip"])
            self.assertAlmostEqual(0.0, value)
            self.assertAlmostEqual(3.0, env._reverse_moved_m)
        finally:
            env.close()

    def test_coastal_proximity_uses_minimum_frame_skip_clearance(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["coastal_proximity"] = -0.05
        env = self._environment(
            "destroyer", frame_skip=5, coastal_clearance_m=250.0, reward=reward)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0,
                "obstacle": False})
            clearances = iter((300.0, 280.0, 100.0, 50.0, 120.0, 200.0))
            with patch.object(
                    env, "_clearances_m",
                    side_effect=lambda _point: (next(clearances), 1000.0)):
                _, value, _, _, info = env.step(np.array([2, 1, 0, 0, 0]))
            self.assertEqual(300.0, info["clearance_before_m"])
            self.assertEqual(200.0, info["clearance_after_m"])
            self.assertEqual(50.0, info["minimum_clearance_m_during_frame_skip"])
            self.assertAlmostEqual(-0.032, value)
        finally:
            env.close()

    def test_clearance_progress_compares_observation_and_final_state(self) -> None:
        reward = {key: 0.0 for key in DEFAULT_REWARD}
        reward["clearance_progress"] = 1.0
        env = self._environment(
            "destroyer", frame_skip=1, coastal_clearance_m=250.0, reward=reward)
        try:
            env.reset(seed=62542, options={
                "position": (100.0, 80.0), "rotation": 0.0,
                "obstacle": False})
            clearances = iter((100.0, 150.0))
            with patch.object(
                    env, "_clearances_m",
                    side_effect=lambda _point: (next(clearances), 1000.0)):
                _, value, _, _, _ = env.step(np.array([2, 1, 0, 0, 0]))
            self.assertAlmostEqual(0.2, value)
        finally:
            env.close()

    def test_integrity_loss_is_normalized_by_hull_capacity(self) -> None:
        for boat_type, lost_hp in (("destroyer", 20.0), ("submarine", 10.0)):
            with self.subTest(boat_type=boat_type):
                reward = {key: 0.0 for key in DEFAULT_REWARD}
                reward["coastal_damage"] = -10.0
                env = self._environment(boat_type, frame_skip=1, reward=reward)
                try:
                    env.reset(seed=62542, options={
                        "position": (100.0, 80.0), "rotation": 0.0,
                        "obstacle": False})
                    bot = env._agent()

                    def damage_one_tick(_dt):
                        bot["integrity"] -= lost_hp

                    with patch.object(env.runner, "step", side_effect=damage_one_tick), \
                            patch.object(
                                env, "_clearances_m", return_value=(1000.0, 1000.0)):
                        _, value, _, _, info = env.step(
                            np.array([2, 1, 2, 0, 0]) if boat_type == "submarine"
                            else np.array([2, 1, 0, 0, 0]))
                    self.assertAlmostEqual(0.1, info["integrity_loss_ratio"])
                    self.assertAlmostEqual(-1.0, value)
                finally:
                    env.close()

    def test_fresh_policy_spaces_transfer_unchanged_to_duel(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.masked_recurrent_policy import SituationMaskedMlpLstmPolicy
        from rl.rl_env import SubmarineDuelEnv

        cases = (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION, "destroyer", "autodest"),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION, "submarine", "autosub"),
        )
        for boat_type, version, opponent_type, opponent_ai in cases:
            with self.subTest(boat_type=boat_type):
                mobility = self._environment(boat_type)
                duel = None
                try:
                    model = RecurrentPPO(
                        SituationMaskedMlpLstmPolicy, mobility, n_steps=4, batch_size=4,
                        n_epochs=1, policy_kwargs={"net_arch": [16],
                                                   "lstm_hidden_size": 16,
                                                   "control_version": version},
                        device="cpu", seed=62542, verbose=0)
                    with TemporaryDirectory() as directory:
                        path = Path(directory) / "fresh.zip"
                        model.save(path)
                        duel = SubmarineDuelEnv(
                            agent_boat_type=boat_type, control_version=version,
                            opponents=[{"boat_type": opponent_type, "ai": opponent_ai,
                                        "weight": 1.0}],
                            seed=62542, frame_skip=2, max_physics_steps=10,
                            spawn_min_m=400.0, spawn_max_m=700.0)
                        loaded = RecurrentPPO.load(path, env=duel, device="cpu")
                        self.assertEqual(model.observation_space, loaded.observation_space)
                        self.assertEqual(model.action_space, loaded.action_space)
                finally:
                    if duel is not None:
                        duel.close()
                    mobility.close()


if __name__ == "__main__":
    unittest.main()
