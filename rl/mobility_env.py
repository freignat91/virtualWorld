"""Environnement Gymnasium de mobilité compatible avec le runtime RL."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

import geometry
import simulation
from rl.headless import HeadlessRunner
from rl.rl_control import (
    DESTROYER_V5_OBSERVATION_VERSION,
    RUDDER_LEVELS,
    SUBMARINE_V3_OBSERVATION_VERSION,
    apply_action,
    build_observation,
    control_spec,
)
from rl.navigable_path import (
    DESTINATION_CLEARANCE_M,
    NavigablePathMetric,
    ROUTE_CLEARANCE_M,
    ROUTE_NODE_MARGIN_M,
    blocking_island_count,
    plan_segmented_route,
)
from rl.waypoints import (
    RLWaypointManager,
    WAYPOINT_ISLAND_CLEARANCE_M,
    WAYPOINT_MAX_DISTANCE_M,
    WAYPOINT_MIN_DISTANCE_M,
    waypoint_distance_m,
    waypoint_reached,
)


PHYSICS_DT = 0.05
METRIC_EXEMPTION_M = 100.0
ROUTE_CATEGORIES = (
    "visible", "small_obstruction", "behind_island", "long_detour", "complex",
)
SMALL_DETOUR_RATIO_MAX = 1.1
LONG_DETOUR_RATIO_MIN = 1.3
ROUTE_SAMPLE_ATTEMPTS = 5000
DEFAULT_REWARD = {
    "waypoint_progress_per_meter": 0.005,
    "waypoint_reached": 5.0,
    "silent_speed_ratio": 0.0,
    "noisy_speed_ratio": 0.0,
    "reverse_per_meter": 0.0,
    "rudder_use": 0.0,
    "rudder_without_threat": 0.0,
    "rudder_change": -0.002,
    "coastal_proximity": -0.05,
    "clearance_progress": 1.0,
    "coastal_damage": -10.0,
    "depth_change_per_meter": 0.0,
    "weapon_request": 0.0,
    "weapon_without_acquisition": 0.0,
    "lure_request": 0.0,
    "lure_without_threat": 0.0,
    "sonar_request": 0.0,
    "stuck": -5.0,
    "completion": 5.0,
    "decision_cost": -0.001,
}


class MobilityEnv(gym.Env):
    """Apprend à avancer sans collision, sans adversaire ni correction d'action."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        map_name: str = "world",
        boat_type: str = "submarine",
        control_version: Optional[str] = None,
        frame_skip: int = 5,
        max_episode_seconds: float = 60.0,
        stuck_seconds: float = 10.0,
        movement_anchor_m: float = 20.0,
        spawn_clearance_m: float = 100.0,
        obstacle_min_m: float = 250.0,
        obstacle_max_m: float = 700.0,
        obstacle_probability_start: float = 0.2,
        obstacle_probability_end: float = 0.8,
        curriculum_decisions: int = 0,
        coastal_clearance_m: float = 200.0,
        progress_mode: str = "euclidean",
        route_curriculum: Optional[Dict[str, float]] = None,
        segmented_routes: bool = False,
        reward: Optional[Dict[str, float]] = None,
        seed: int = 0,
    ) -> None:
        super().__init__()
        self.map_name = map_name
        self.boat_type = boat_type
        if control_version is None:
            control_version = (
                SUBMARINE_V3_OBSERVATION_VERSION
                if boat_type == "submarine"
                else DESTROYER_V5_OBSERVATION_VERSION)
        self.control_version, observation_dim, action_nvecs = control_spec(
            boat_type, control_version)
        self.frame_skip = max(1, int(frame_skip))
        self.max_episode_seconds = float(max_episode_seconds)
        self.stuck_seconds = float(stuck_seconds)
        self.movement_anchor_m = float(movement_anchor_m)
        self.spawn_clearance_m = float(spawn_clearance_m)
        self.obstacle_min_m = float(obstacle_min_m)
        self.obstacle_max_m = float(obstacle_max_m)
        self.obstacle_probability_start = float(obstacle_probability_start)
        self.obstacle_probability_end = float(obstacle_probability_end)
        self.curriculum_decisions = max(0, int(curriculum_decisions))
        self.coastal_clearance_m = float(coastal_clearance_m)
        if progress_mode not in {"euclidean", "navigable_path"}:
            raise ValueError("mode de progression de mobilite invalide")
        self.progress_mode = progress_mode
        if type(segmented_routes) is not bool:
            raise ValueError("mode de routes segmentees invalide")
        self.segmented_routes = segmented_routes
        self.route_curriculum = None
        if route_curriculum is not None:
            if (not isinstance(route_curriculum, dict)
                    or set(route_curriculum) != set(ROUTE_CATEGORIES)):
                raise ValueError("curriculum de routes de mobilite invalide")
            weights = {key: float(route_curriculum[key]) for key in ROUTE_CATEGORIES}
            if (not all(math.isfinite(value) and value >= 0.0
                        for value in weights.values())
                    or not math.isclose(sum(weights.values()), 1.0,
                                        rel_tol=0.0, abs_tol=1e-9)):
                raise ValueError("poids du curriculum de routes invalides")
            self.route_curriculum = weights
        positive = (
            self.max_episode_seconds, self.stuck_seconds, self.movement_anchor_m,
            self.spawn_clearance_m, self.obstacle_min_m, self.obstacle_max_m,
            self.coastal_clearance_m,
        )
        if not all(math.isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("paramètres de mobilité non positifs")
        if self.obstacle_min_m > self.obstacle_max_m:
            raise ValueError("distances d'obstacle invalides")
        if not (0.0 <= self.obstacle_probability_start <= 1.0
                and 0.0 <= self.obstacle_probability_end <= 1.0):
            raise ValueError("probabilités d'obstacle invalides")
        self.reward_cfg = dict(DEFAULT_REWARD)
        if reward:
            unknown = set(reward) - set(DEFAULT_REWARD)
            if unknown:
                raise ValueError(f"récompenses de mobilité inconnues: {sorted(unknown)}")
            self.reward_cfg.update({key: float(value) for key, value in reward.items()})
        if not all(math.isfinite(value) for value in self.reward_cfg.values()):
            raise ValueError("récompenses de mobilité non finies")

        self.runner = HeadlessRunner(map_name=map_name, seed=seed)
        self._path_metric = (NavigablePathMetric(self.runner.world)
                             if self.progress_mode == "navigable_path" else None)
        self._route_planner = (NavigablePathMetric(
            self.runner.world, clearance_m=ROUTE_CLEARANCE_M,
            endpoint_clearance_m=DESTINATION_CLEARANCE_M,
            node_margin_m=ROUTE_NODE_MARGIN_M)
            if self.segmented_routes else None)
        self._waypoint_manager = RLWaypointManager(self.runner.random)
        self.base_seed = int(seed)
        self._episode_index = 0
        self._total_decisions = 0
        self.action_space = spaces.MultiDiscrete(action_nvecs)
        self.observation_space = spaces.Box(
            -1.0, 1.0, shape=(observation_dim,), dtype=np.float32)
        self.agent_sid: Optional[str] = None
        self._obstacle_episode = False
        self._route_category = "legacy"
        self._start_position = (0.0, 0.0)
        self._last_position = (0.0, 0.0)
        self._movement_anchor = (0.0, 0.0)
        self._last_movement_at = 0.0
        self._coastal_damage = 0.0
        self._path_length_m = 0.0
        self._forward_moved_m = 0.0
        self._reverse_moved_m = 0.0
        self._minimum_clearance_m = float("inf")
        self._speed_path_length_m = 0.0
        self._speed_elapsed_seconds = 0.0
        self._forward_path_length_m = 0.0
        self._completed_forward_displacement_m = 0.0
        self._forward_displacement_m = (0.0, 0.0)
        self._decisions = 0
        self._stationary_decisions = 0
        self._reverse_decisions = 0
        self._steering_decisions = 0
        self._near_coast_decisions = 0
        self._weapon_requests = 0
        self._lure_requests = 0
        self._sonar_requests = 0
        self._absolute_rudder = 0.0
        self._waypoints_reached = 0
        self._route_arrived = False
        self._previous_selected_rudder_ratio = 0.0
        self._max_speed_ms = 1.0

    def _agent(self) -> Dict[str, Any]:
        if self.agent_sid is None or self.agent_sid not in self.runner.legacy.bots:
            raise RuntimeError("agent de mobilité absent")
        return self.runner.legacy.bots[self.agent_sid]

    def _clearances_m(self, point: Tuple[float, float]) -> Tuple[float, float]:
        half_w = self.runner.world["ground"]["width"] / 2 - 4.0
        half_d = self.runner.world["ground"]["depth"] / 2 - 4.0
        boundary_u = min(half_w - abs(point[0]), half_d - abs(point[1]))
        island_u = geometry.min_distance_to_islands(*point, self.runner.world)
        island_m = island_u * simulation.UNIT_METERS_BOT
        return min(boundary_u * simulation.UNIT_METERS_BOT, island_m), island_m

    def _clearance_m(self, point: Tuple[float, float]) -> float:
        return self._clearances_m(point)[0]

    def _obstacle_probability(self) -> float:
        if self.curriculum_decisions <= 0:
            return self.obstacle_probability_end
        progress = min(1.0, self._total_decisions / self.curriculum_decisions)
        return self.obstacle_probability_start + progress * (
            self.obstacle_probability_end - self.obstacle_probability_start)

    def _record_open_water_motion(
            self, moved_m: float, forward_moved_m: float,
            forward_dx_m: float, forward_dz_m: float,
            elapsed_seconds: float, clearance_m: float) -> None:
        """Mesure séparément chaque tronçon hors de la zone de manœuvre côtière."""
        if clearance_m <= METRIC_EXEMPTION_M:
            self._completed_forward_displacement_m += math.hypot(
                *self._forward_displacement_m)
            self._forward_displacement_m = (0.0, 0.0)
            return
        self._speed_path_length_m += moved_m
        self._speed_elapsed_seconds += elapsed_seconds
        self._forward_path_length_m += forward_moved_m
        self._forward_displacement_m = (
            self._forward_displacement_m[0] + forward_dx_m,
            self._forward_displacement_m[1] + forward_dz_m,
        )

    def _sample_open_spawn(self) -> Tuple[Tuple[float, float], float]:
        half_w = self.runner.world["ground"]["width"] / 2 - 4.0
        half_d = self.runner.world["ground"]["depth"] / 2 - 4.0
        clearance = max(self.spawn_clearance_m, self.obstacle_max_m)
        for _ in range(5000):
            point = (self.runner.random.uniform(-half_w, half_w),
                     self.runner.random.uniform(-half_d, half_d))
            if (not geometry.point_on_any_island(*point, self.runner.world)
                    and self._clearance_m(point) >= clearance):
                return point, self.runner.random.uniform(0.0, math.tau)
        raise RuntimeError("aucun départ dégagé trouvé")

    def _sample_obstacle_spawn(self) -> Tuple[Tuple[float, float], float]:
        islands = [island for island in self.runner.world.get("islands", ())
                   if len(island.get("points") or ()) >= 2]
        if not islands:
            raise RuntimeError("aucune île pour le curriculum de mobilité")
        for _ in range(5000):
            points = self.runner.random.choice(islands)["points"]
            index = self.runner.random.randrange(len(points))
            first, second = points[index], points[(index + 1) % len(points)]
            midpoint = ((float(first["x"]) + float(second["x"])) / 2.0,
                        (float(first["z"]) + float(second["z"])) / 2.0)
            center = (sum(float(point["x"]) for point in points) / len(points),
                      sum(float(point["z"]) for point in points) / len(points))
            outward = (midpoint[0] - center[0], midpoint[1] - center[1])
            norm = math.hypot(*outward)
            if norm <= 1e-9:
                continue
            distance_u = self.runner.random.uniform(
                self.obstacle_min_m, self.obstacle_max_m) / simulation.UNIT_METERS_BOT
            start = (midpoint[0] + outward[0] / norm * distance_u,
                     midpoint[1] + outward[1] / norm * distance_u)
            if (geometry.point_on_any_island(*start, self.runner.world)
                    or self._clearance_m(start) < self.spawn_clearance_m):
                continue
            rotation = math.atan2(midpoint[1] - start[1], start[0] - midpoint[0])
            rotation += self.runner.random.uniform(-math.radians(15.0), math.radians(15.0))
            end = (start[0] - math.cos(rotation) * 100.0,
                   start[1] + math.sin(rotation) * 100.0)
            if geometry.first_island_intersection(*start, *end, self.runner.world) is not None:
                return start, rotation
        raise RuntimeError("aucune approche d'île trouvée")

    def _sample_safe_position(self) -> Tuple[float, float]:
        ground = self.runner.world["ground"]
        half_w = float(ground["width"]) / 2.0 - 4.0
        half_d = float(ground["depth"]) / 2.0 - 4.0
        for _ in range(ROUTE_SAMPLE_ATTEMPTS):
            point = (self.runner.random.uniform(-half_w, half_w),
                     self.runner.random.uniform(-half_d, half_d))
            if (not geometry.point_on_any_island(*point, self.runner.world)
                    and self._clearance_m(point) >= self.spawn_clearance_m):
                return point
        raise RuntimeError("aucun depart sur pour le curriculum de routes")

    def _sample_route_category(self) -> str:
        if self.route_curriculum is None:
            return "legacy"
        selected = self.runner.random.random()
        cumulative = 0.0
        for category in ROUTE_CATEGORIES:
            cumulative += self.route_curriculum[category]
            if selected < cumulative:
                return category
        return ROUTE_CATEGORIES[-1]

    @staticmethod
    def _route_matches(category: str, blockers: int, detour_ratio: float) -> bool:
        if category == "visible":
            return blockers == 0
        if category == "complex":
            return blockers >= 2
        if blockers != 1:
            return False
        if category == "small_obstruction":
            return detour_ratio <= SMALL_DETOUR_RATIO_MAX
        if category == "behind_island":
            return SMALL_DETOUR_RATIO_MAX < detour_ratio < LONG_DETOUR_RATIO_MIN
        return category == "long_detour" and detour_ratio >= LONG_DETOUR_RATIO_MIN

    def _sample_curriculum_waypoint(
            self, start: Tuple[float, float], category: str, *,
            attempts: int = ROUTE_SAMPLE_ATTEMPTS) -> Dict[str, float]:
        if self._path_metric is None:
            raise RuntimeError("metrique de chemin absente du curriculum")
        ground = self.runner.world["ground"]
        half_w = float(ground["width"]) / 2.0 - 4.0
        half_d = float(ground["depth"]) / 2.0 - 4.0
        minimum_u = WAYPOINT_MIN_DISTANCE_M / simulation.UNIT_METERS_BOT
        maximum_u = WAYPOINT_MAX_DISTANCE_M / simulation.UNIT_METERS_BOT
        clearance_u = WAYPOINT_ISLAND_CLEARANCE_M / simulation.UNIT_METERS_BOT
        for _ in range(attempts):
            angle = self.runner.random.uniform(0.0, math.tau)
            direct_u = self.runner.random.uniform(minimum_u, maximum_u)
            goal = (start[0] + math.cos(angle) * direct_u,
                    start[1] + math.sin(angle) * direct_u)
            if (abs(goal[0]) > half_w or abs(goal[1]) > half_d
                    or geometry.point_on_any_island(*goal, self.runner.world)
                    or geometry.min_distance_to_islands(*goal, self.runner.world) < clearance_u):
                continue
            blockers = blocking_island_count(start, goal, self.runner.world)
            if ((category == "visible" and blockers)
                    or (category == "complex" and blockers < 2)
                    or (category not in {"visible", "complex"} and blockers != 1)):
                continue
            self._path_metric.set_goal(goal)
            path_m = self._path_metric.distance_m(start)
            if (not math.isfinite(path_m)
                    or not self._route_matches(
                        category, blockers,
                        path_m / (direct_u * simulation.UNIT_METERS_BOT))):
                continue
            if self._route_planner is not None:
                try:
                    plan_segmented_route(
                        self.runner.world, start, goal, planner=self._route_planner)
                except (RuntimeError, ValueError):
                    continue
            return {"x": goal[0], "z": goal[1]}
        raise RuntimeError(f"aucun waypoint accessible pour la route {category}")

    def _ensure_waypoint(self, bot: Dict[str, Any]) -> bool:
        waypoint = bot.get("rl_waypoint")
        reached = bool(
            waypoint is not None
            and waypoint_reached(bot, waypoint))
        if self.segmented_routes and reached:
            remaining = bot.get("rl_route_waypoints")
            bot["rl_waypoint"] = (remaining.pop(0)
                                  if isinstance(remaining, list) and remaining
                                  else None)
            self._route_arrived = bot["rl_waypoint"] is None
            if self._path_metric is not None and not self._route_arrived:
                selected = bot["rl_waypoint"]
                self._path_metric.set_goal((selected["x"], selected["z"]))
            bot["rl_waypoints_reached"] = int(bot.get("rl_waypoints_reached", 0)) + 1
            return True
        if waypoint is None or reached:
            if self.route_curriculum is None:
                bot["rl_waypoint"] = self._waypoint_manager.sample(
                    bot, self.runner.world)
            else:
                start = (float(bot["position"]["x"]), float(bot["position"]["z"]))
                preferred = (self._sample_route_category() if reached
                             else self._route_category)
                categories = (preferred, *(
                    category for category in ROUTE_CATEGORIES
                    if category != preferred))
                for category in categories:
                    try:
                        bot["rl_waypoint"] = self._sample_curriculum_waypoint(
                            start, category, attempts=500)
                        self._route_category = category
                        break
                    except RuntimeError:
                        continue
                else:
                    raise RuntimeError("aucun waypoint de curriculum accessible")
            if self._path_metric is not None:
                selected = bot["rl_waypoint"]
                self._path_metric.set_goal((selected["x"], selected["z"]))
        if reached:
            bot["rl_waypoints_reached"] = int(bot.get("rl_waypoints_reached", 0)) + 1
        return reached

    def _progress_distance_m(self, bot: Dict[str, Any]) -> float:
        if bot.get("rl_waypoint") is None:
            return 0.0
        if self._path_metric is None:
            return waypoint_distance_m(bot, bot["rl_waypoint"])
        position = bot["position"]
        return self._path_metric.distance_m((
            float(position["x"]), float(position["z"])))

    def reset(self, *, seed: Optional[int] = None,
              options: Optional[Dict[str, Any]] = None):
        super().reset(seed=seed)
        if seed is None:
            seed = self.base_seed + self._episode_index
        self._episode_index += 1
        self.runner.reset(seed=seed)
        self._route_arrived = False
        if self.route_curriculum is not None:
            if options and "route_category" in options:
                self._route_category = str(options["route_category"])
                if self._route_category not in ROUTE_CATEGORIES:
                    raise ValueError("categorie de route de mobilite invalide")
            elif options and "obstacle" in options:
                self._route_category = (
                    "behind_island" if bool(options["obstacle"]) else "visible")
            else:
                self._route_category = self._sample_route_category()
            obstacle = self._route_category != "visible"
        else:
            self._route_category = "legacy"
            obstacle = (bool(options["obstacle"]) if options and "obstacle" in options
                        else self.runner.random.random() < self._obstacle_probability())
        prepared_waypoint = None
        if options and "position" in options and "rotation" in options:
            position = tuple(float(value) for value in options["position"])
            rotation = float(options["rotation"])
        elif self.route_curriculum is not None:
            for _ in range(40):
                position = self._sample_safe_position()
                try:
                    prepared_waypoint = self._sample_curriculum_waypoint(
                        position, self._route_category, attempts=250)
                    break
                except RuntimeError:
                    continue
            if prepared_waypoint is None:
                raise RuntimeError(
                    f"aucune route de mobilite pour {self._route_category}")
            rotation = self.runner.random.uniform(0.0, math.tau)
        elif obstacle:
            position, rotation = self._sample_obstacle_spawn()
        else:
            position, rotation = self._sample_open_spawn()
        self.agent_sid = self.runner.spawn_bot(
            self.boat_type, external_control=True, ai=None, position=position,
            rotation=rotation, team_id="mobility")
        bot = self._agent()
        bot["rl_control_version"] = self.control_version
        bot["rl_waypoint"] = None
        bot["rl_waypoints_reached"] = 0
        if options and "waypoint" in options:
            waypoint = options["waypoint"]
            bot["rl_waypoint"] = {
                "x": float(waypoint["x"]), "z": float(waypoint["z"])}
            if self._path_metric is not None and not self.segmented_routes:
                self._path_metric.set_goal((
                    bot["rl_waypoint"]["x"], bot["rl_waypoint"]["z"]))
        elif prepared_waypoint is not None:
            bot["rl_waypoint"] = prepared_waypoint
            if self._path_metric is not None and not self.segmented_routes:
                self._path_metric.set_goal((
                    prepared_waypoint["x"], prepared_waypoint["z"]))
        else:
            self._ensure_waypoint(bot)
        if self.segmented_routes:
            if self._route_planner is None or bot.get("rl_waypoint") is None:
                raise RuntimeError("route segmentee absente")
            destination = dict(bot["rl_waypoint"])
            start = (float(position[0]), float(position[1]))
            route = [
                {"x": point[0], "z": point[1]}
                for point in plan_segmented_route(
                    self.runner.world, start,
                    (destination["x"], destination["z"]),
                    planner=self._route_planner)
            ]
            if not route:
                raise RuntimeError("route segmentee vide")
            bot["rl_destination"] = destination
            bot["rl_route"] = [dict(point) for point in route]
            bot["rl_route_waypoints"] = [dict(point) for point in route[1:]]
            bot["rl_waypoint"] = dict(route[0])
            if self._path_metric is not None:
                self._path_metric.set_goal((route[0]["x"], route[0]["z"]))
        self._max_speed_ms = max(
            0.001, float(bot.get("max_speed_us", 0.0)) * simulation.UNIT_METERS_BOT)
        self._obstacle_episode = obstacle
        self._start_position = position
        self._last_position = position
        self._movement_anchor = position
        self._last_movement_at = self.runner.sim.now()
        self._coastal_damage = 0.0
        self._path_length_m = 0.0
        self._forward_moved_m = 0.0
        self._reverse_moved_m = 0.0
        self._minimum_clearance_m = self._clearance_m(position)
        self._speed_path_length_m = 0.0
        self._speed_elapsed_seconds = 0.0
        self._forward_path_length_m = 0.0
        self._completed_forward_displacement_m = 0.0
        self._forward_displacement_m = (0.0, 0.0)
        self._decisions = 0
        self._stationary_decisions = 0
        self._reverse_decisions = 0
        self._steering_decisions = 0
        self._near_coast_decisions = 0
        self._weapon_requests = 0
        self._lure_requests = 0
        self._sonar_requests = 0
        self._absolute_rudder = 0.0
        self._waypoints_reached = 0
        self._previous_selected_rudder_ratio = float(
            bot.get("control_target_rudder", 0.0))
        return build_observation(bot, self.runner.sim, self.runner.world), {
            "obstacle": obstacle,
            "position": list(position),
            "rotation": rotation,
            "control_version": self.control_version,
            "route_category": self._route_category,
            "progress_mode": self.progress_mode,
        }

    def step(self, action):
        values = np.asarray(action, dtype=np.int64).reshape(-1)
        if not self.action_space.contains(values):
            raise ValueError(f"action de mobilité invalide: {values.tolist()}")
        bot = self._agent()
        had_detected_torpedo = bool(bot.get("rl_torpedo_detected", False))
        hp_before = float(bot["integrity"])
        max_integrity = max(0.001, float(bot.get("maxIntegrity", hp_before)))
        depth_before = float(bot["position"].get("y", 0.0))
        position_before = (
            float(bot["position"]["x"]), float(bot["position"]["z"]))
        clearance_before_m, island_clearance_before_m = self._clearances_m(
            position_before)
        clearance_after_m = clearance_before_m
        island_clearance_after_m = island_clearance_before_m
        minimum_clearance_m = clearance_before_m
        selected_rudder_ratio = RUDDER_LEVELS[int(values[0])]
        rudder_change = abs(
            selected_rudder_ratio - self._previous_selected_rudder_ratio)
        self._previous_selected_rudder_ratio = selected_rudder_ratio
        result = apply_action(bot, self.runner.sim, values)
        self._weapon_requests += int(result["weapon_requested"])
        self._lure_requests += int(result["lure_requested"])
        self._sonar_requests += int(result["sonar_requested"])
        moved_m = 0.0
        forward_moved_m = 0.0
        reverse_moved_m = 0.0
        waypoint_progress_m = 0.0
        waypoints_reached = 0
        forward_dx_m = 0.0
        forward_dz_m = 0.0
        last_position = position_before
        progress_anchor_m = self._progress_distance_m(bot)
        for _ in range(self.frame_skip):
            before = (float(bot["position"]["x"]), float(bot["position"]["z"]))
            self.runner.step(PHYSICS_DT)
            self.runner.sim.drain_events()
            after = (float(bot["position"]["x"]), float(bot["position"]["z"]))
            last_position = after
            dx_m = (after[0] - before[0]) * simulation.UNIT_METERS_BOT
            dz_m = (after[1] - before[1]) * simulation.UNIT_METERS_BOT
            segment_m = math.hypot(dx_m, dz_m)
            moved_m += segment_m
            if float(bot.get("speed", 0.0)) > 0.0:
                forward_moved_m += segment_m
                forward_dx_m += dx_m
                forward_dz_m += dz_m
            elif float(bot.get("speed", 0.0)) < 0.0:
                reverse_moved_m += segment_m
            clearance_after_m, island_clearance_after_m = self._clearances_m(after)
            minimum_clearance_m = min(minimum_clearance_m, clearance_after_m)
            if self.agent_sid not in self.runner.legacy.bots:
                break
            bot = self._agent()
            if (bot.get("rl_waypoint") is not None
                    and waypoint_reached(bot, bot["rl_waypoint"])):
                waypoint_progress_m += progress_anchor_m - self._progress_distance_m(bot)
                self._ensure_waypoint(bot)
                waypoints_reached += 1
                if self._route_arrived:
                    break
                progress_anchor_m = self._progress_distance_m(bot)
        if not self._route_arrived:
            waypoint_progress_m += progress_anchor_m - self._progress_distance_m(bot)
        self._total_decisions += 1
        self._decisions += 1
        self._path_length_m += moved_m
        self._forward_moved_m += forward_moved_m
        self._reverse_moved_m += reverse_moved_m
        self._waypoints_reached += waypoints_reached
        self._minimum_clearance_m = min(
            self._minimum_clearance_m, minimum_clearance_m)

        alive = self.agent_sid in self.runner.legacy.bots
        if not alive:
            self._coastal_damage += hp_before
            self._last_position = last_position
            integrity_loss_ratio = hp_before / max_integrity
            reward = (integrity_loss_ratio * self.reward_cfg["coastal_damage"]
                      + self.reward_cfg["decision_cost"])
            return np.zeros(self.observation_space.shape, dtype=np.float32), reward, True, False, {
                **self._terminal_info("sunk"),
                "forward_moved_m_during_frame_skip": forward_moved_m,
                "reverse_moved_m_during_frame_skip": reverse_moved_m,
                "waypoint_progress_m_during_frame_skip": waypoint_progress_m,
                "waypoints_reached_during_frame_skip": waypoints_reached,
                "clearance_before_m": clearance_before_m,
                "clearance_after_m": clearance_after_m,
                "minimum_clearance_m_during_frame_skip": minimum_clearance_m,
                "integrity_loss_ratio": integrity_loss_ratio,
            }

        bot = self._agent()
        position = (float(bot["position"]["x"]), float(bot["position"]["z"]))
        if math.hypot(position[0] - self._movement_anchor[0],
                      position[1] - self._movement_anchor[1]) * simulation.UNIT_METERS_BOT >= (
                self.movement_anchor_m):
            self._movement_anchor = position
            self._last_movement_at = self.runner.sim.now()
        max_speed = max(0.001, float(bot.get("max_speed_us", 0.0)))
        speed_ratio = float(bot.get("speed", 0.0)) / max_speed
        forward_speed_ratio = max(0.0, min(1.0, speed_ratio))
        silent_speed_limit = max(0.0, min(
            1.0, float((bot.get("boat") or {}).get("speedNoiseLimit", 0.0))))
        silent_speed_ratio = min(forward_speed_ratio, silent_speed_limit)
        noisy_speed_ratio = max(0.0, forward_speed_ratio - silent_speed_limit)
        rudder_ratio = abs(float(bot.get("rudder", 0.0))) / max(
            0.001, float(bot.get("rudder_max", 0.36)))
        stationary = abs(speed_ratio) < 0.1
        reverse = speed_ratio < -0.05
        steering = rudder_ratio > 0.1
        self._stationary_decisions += int(stationary)
        self._reverse_decisions += int(reverse)
        self._steering_decisions += int(steering)
        self._absolute_rudder += rudder_ratio
        self._record_open_water_motion(
            moved_m, forward_moved_m, forward_dx_m, forward_dz_m,
            self.frame_skip * PHYSICS_DT, minimum_clearance_m)
        proximity = max(
            0.0, min(1.0, 1.0 - minimum_clearance_m / self.coastal_clearance_m)) ** 2
        self._near_coast_decisions += int(proximity > 0.0)
        hp_after = float(bot["integrity"])
        damage = max(0.0, hp_before - hp_after)
        integrity_loss_ratio = damage / max_integrity
        self._coastal_damage += damage
        depth_change_m = abs(float(bot["position"].get("y", 0.0)) - depth_before) * (
            simulation.UNIT_METERS_BOT)

        clearance_progress = 0.0
        if min(clearance_before_m, clearance_after_m) < self.coastal_clearance_m:
            clearance_progress = (
                max(0.0, min(1.0, clearance_after_m / self.coastal_clearance_m))
                - max(0.0, min(1.0, clearance_before_m / self.coastal_clearance_m)))
        reward = (waypoint_progress_m * self.reward_cfg["waypoint_progress_per_meter"]
                  + waypoints_reached * self.reward_cfg["waypoint_reached"]
                  + silent_speed_ratio * self.reward_cfg["silent_speed_ratio"]
                  + noisy_speed_ratio * self.reward_cfg["noisy_speed_ratio"]
                  + reverse_moved_m * self.reward_cfg["reverse_per_meter"]
                  + rudder_ratio * self.reward_cfg["rudder_use"]
                  + (rudder_ratio * self.reward_cfg["rudder_without_threat"]
                     if not had_detected_torpedo else 0.0)
                  + rudder_change * self.reward_cfg["rudder_change"]
                  + proximity * self.reward_cfg["coastal_proximity"]
                  + clearance_progress * self.reward_cfg["clearance_progress"]
                  + integrity_loss_ratio * self.reward_cfg["coastal_damage"]
                  + depth_change_m * self.reward_cfg["depth_change_per_meter"]
                  + (self.reward_cfg["weapon_request"] if result["weapon_requested"] else 0.0)
                  + (self.reward_cfg["weapon_without_acquisition"]
                     if result["weapon_without_acquisition"] else 0.0)
                  + (self.reward_cfg["lure_request"] if result["lure_requested"] else 0.0)
                  + (self.reward_cfg["lure_without_threat"]
                     if result["lure_without_threat"] else 0.0)
                  + (self.reward_cfg["sonar_request"] if result["sonar_requested"] else 0.0)
                  + self.reward_cfg["decision_cost"])
        stuck = self.runner.sim.now() - self._last_movement_at >= self.stuck_seconds
        timed_out = self.runner.sim.now() >= self.max_episode_seconds
        completed = self._route_arrived if self.segmented_routes else timed_out
        outcome = None
        if stuck:
            reward += self.reward_cfg["stuck"]
            outcome = "stuck"
        elif completed:
            reward += self.reward_cfg["completion"]
            outcome = "completed"
        elif timed_out:
            outcome = "timeout"
        terminated = stuck or (self.segmented_routes and completed)
        truncated = timed_out and not terminated
        self._last_position = position
        info = self._terminal_info(outcome) if outcome else {
            "coastal_damage": self._coastal_damage,
            "clearance_m": clearance_after_m,
            "island_clearance_m": island_clearance_after_m,
            "route_category": self._route_category,
            "progress_mode": self.progress_mode,
        }
        info.update({
            "forward_moved_m_during_frame_skip": forward_moved_m,
            "reverse_moved_m_during_frame_skip": reverse_moved_m,
            "waypoint_progress_m_during_frame_skip": waypoint_progress_m,
            "waypoints_reached_during_frame_skip": waypoints_reached,
            "clearance_before_m": clearance_before_m,
            "clearance_after_m": clearance_after_m,
            "minimum_clearance_m_during_frame_skip": minimum_clearance_m,
            "integrity_loss_ratio": integrity_loss_ratio,
            "rudder_change": rudder_change,
        })
        return (build_observation(bot, self.runner.sim, self.runner.world),
                float(reward), terminated, truncated, info)

    def _terminal_info(self, outcome: Optional[str]) -> Dict[str, Any]:
        position = self._last_position
        displacement_m = math.hypot(
            position[0] - self._start_position[0],
            position[1] - self._start_position[1]) * simulation.UNIT_METERS_BOT
        forward_displacement_m = (
            self._completed_forward_displacement_m
            + math.hypot(*self._forward_displacement_m))
        elapsed_seconds = self.runner.sim.now()
        return {
            "outcome": outcome,
            "success": outcome == "completed",
            "obstacle": self._obstacle_episode,
            "route_category": self._route_category,
            "progress_mode": self.progress_mode,
            "coastal_damage": self._coastal_damage,
            "decisions": self._decisions,
            "stationary_decisions": self._stationary_decisions,
            "reverse_decisions": self._reverse_decisions,
            "steering_decisions": self._steering_decisions,
            "near_coast_decisions": self._near_coast_decisions,
            "weapon_requests": self._weapon_requests,
            "lure_requests": self._lure_requests,
            "sonar_requests": self._sonar_requests,
            "mean_absolute_rudder": self._absolute_rudder / max(1, self._decisions),
            "path_length_m": self._path_length_m,
            "forward_moved_m": self._forward_moved_m,
            "reverse_moved_m": self._reverse_moved_m,
            "waypoints_reached": self._waypoints_reached,
            "route_arrived": self._route_arrived,
            "minimum_clearance_m": self._minimum_clearance_m,
            "speed_path_length_m": self._speed_path_length_m,
            "speed_elapsed_seconds": self._speed_elapsed_seconds,
            "displacement_m": displacement_m,
            "forward_path_length_m": self._forward_path_length_m,
            "forward_displacement_m": forward_displacement_m,
            "straightness": (min(
                1.0, forward_displacement_m / self._forward_path_length_m)
                if self._forward_path_length_m > 1e-9 else 0.0),
            "mean_speed_ratio": self._speed_path_length_m / max(
                0.001, self._speed_elapsed_seconds * self._max_speed_ms),
            "elapsed_seconds": elapsed_seconds,
        }

    def close(self) -> None:
        self.agent_sid = None
