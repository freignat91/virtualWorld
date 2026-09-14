"""Environnement Gymnasium de navigation pure entre les iles."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

import geometry
import simulation
from rl.headless import HeadlessRunner
from rl.rl_control import RAY_DIRECTIONS_DEG, RUDDER_LEVELS, THROTTLE_LEVELS


NAVIGATION_OBSERVATION_VERSION = "navigation_v1"
NAVIGATION_WAYPOINT_OBSERVATION_VERSION = "navigation_v2"
NAVIGATION_LOOKAHEAD_OBSERVATION_VERSION = "navigation_v3"
NAVIGATION_OBS_DIM = 13
NAVIGATION_ACTION_NVECS = np.array([5, 5], dtype=np.int64)
PHYSICS_DT = 0.05

DEFAULT_REWARD = {
    "progress_per_meter": 0.01,
    "arrival": 10.0,
    "coastal_damage_per_point": -1.0,
    "coastal_proximity": 0.0,
    "stuck": -5.0,
    "timeout": -1.0,
    "stationary": -0.002,
    "decision_cost": -0.001,
}


class NavigationEnv(gym.Env):
    """Conduit une coque seule vers un but dont la route directe est bloquee."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        map_name: str = "world",
        boat_type: str = "destroyer",
        frame_skip: int = 5,
        max_episode_seconds: float = 240.0,
        stuck_seconds: float = 20.0,
        goal_radius_m: float = 50.0,
        min_route_m: float = 800.0,
        max_route_m: float = 3000.0,
        route_mode: str = "blocked",
        max_detour_ratio: Optional[float] = None,
        coastal_clearance_m: float = 100.0,
        guidance_mode: str = "goal",
        guidance_clearance_m: float = 0.0,
        waypoint_lookahead_m: Optional[float] = None,
        progress_mode: str = "guidance",
        coastal_safety_clearance_m: float = 0.0,
        coastal_safety_horizon_s: float = 5.0,
        ray_max_m: float = 1000.0,
        reward: Optional[Dict[str, float]] = None,
        seed: int = 0,
    ) -> None:
        super().__init__()
        if boat_type not in {"destroyer", "submarine"}:
            raise ValueError(f"type de bateau inconnu: {boat_type}")
        self.map_name = map_name
        self.boat_type = boat_type
        self.frame_skip = max(1, int(frame_skip))
        self.max_episode_seconds = float(max_episode_seconds)
        self.stuck_seconds = float(stuck_seconds)
        self.goal_radius_m = float(goal_radius_m)
        self.min_route_m = float(min_route_m)
        self.max_route_m = float(max_route_m)
        if route_mode not in {"open", "single_island", "multi_island", "blocked"}:
            raise ValueError(f"mode de route inconnu: {route_mode}")
        self.route_mode = route_mode
        self.max_detour_ratio = (None if max_detour_ratio is None
                                 else float(max_detour_ratio))
        self.coastal_clearance_m = float(coastal_clearance_m)
        if guidance_mode not in {"goal", "safe_waypoint", "lookahead_waypoint"}:
            raise ValueError(f"mode de guidage inconnu: {guidance_mode}")
        self.guidance_mode = guidance_mode
        self.guidance_clearance_m = float(guidance_clearance_m)
        self.waypoint_lookahead_m = (self.goal_radius_m if waypoint_lookahead_m is None
                                     else float(waypoint_lookahead_m))
        if progress_mode not in {"geometric", "guidance"}:
            raise ValueError(f"mode de progression inconnu: {progress_mode}")
        self.progress_mode = progress_mode
        self.coastal_safety_clearance_m = float(coastal_safety_clearance_m)
        self.coastal_safety_horizon_s = float(coastal_safety_horizon_s)
        if guidance_mode == "lookahead_waypoint":
            self.observation_version = NAVIGATION_LOOKAHEAD_OBSERVATION_VERSION
        elif guidance_mode == "safe_waypoint":
            self.observation_version = NAVIGATION_WAYPOINT_OBSERVATION_VERSION
        else:
            self.observation_version = NAVIGATION_OBSERVATION_VERSION
        self.ray_max_m = float(ray_max_m)
        if not 0 < self.min_route_m <= self.max_route_m:
            raise ValueError("distances de route invalides")
        if min(self.max_episode_seconds, self.stuck_seconds, self.goal_radius_m,
               self.coastal_clearance_m, self.ray_max_m) <= 0:
            raise ValueError("parametres de navigation non positifs")
        if (self.max_detour_ratio is not None
                and (not math.isfinite(self.max_detour_ratio)
                     or self.max_detour_ratio < 1.0)):
            raise ValueError("rapport de detour invalide")
        if (not math.isfinite(self.guidance_clearance_m)
                or self.guidance_clearance_m < 0.0):
            raise ValueError("marge de guidage invalide")
        if (not math.isfinite(self.waypoint_lookahead_m)
                or self.waypoint_lookahead_m <= 0.0):
            raise ValueError("anticipation de waypoint invalide")
        if (not math.isfinite(self.coastal_safety_clearance_m)
                or self.coastal_safety_clearance_m < 0.0
                or not math.isfinite(self.coastal_safety_horizon_s)
                or self.coastal_safety_horizon_s <= 0.0):
            raise ValueError("bouclier cotier invalide")
        self.reward_cfg = dict(DEFAULT_REWARD)
        if reward:
            unknown = set(reward) - set(DEFAULT_REWARD)
            if unknown:
                raise ValueError(f"recompenses de navigation inconnues: {sorted(unknown)}")
            self.reward_cfg.update({key: float(value) for key, value in reward.items()})
        if not all(math.isfinite(value) for value in self.reward_cfg.values()):
            raise ValueError("recompenses de navigation non finies")

        self.runner = HeadlessRunner(map_name=map_name, seed=seed)
        self.base_seed = int(seed)
        self._episode_index = 0
        self.action_space = spaces.MultiDiscrete(NAVIGATION_ACTION_NVECS)
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(NAVIGATION_OBS_DIM,), dtype=np.float32)
        self.agent_sid: Optional[str] = None
        self.goal = (0.0, 0.0)
        self._node_distances = self._build_node_distances()
        self._goal_connections: Tuple[Tuple[int, float], ...] = ()
        self._guidance_goal_connections: Tuple[Tuple[int, float], ...] = ()
        self._initial_shortest_m = 0.0
        self._previous_shortest_m = 0.0
        self._path_length_m = 0.0
        self._coastal_damage = 0.0
        self._near_coast_decisions = 0
        self._stationary_decisions = 0
        self._safety_interventions = 0
        self._decisions = 0
        self._last_position = (0.0, 0.0)
        self._movement_anchor = (0.0, 0.0)
        self._last_movement_at = 0.0

    def _agent(self) -> Dict[str, Any]:
        if self.agent_sid is None or self.agent_sid not in self.runner.legacy.bots:
            raise RuntimeError("agent de navigation absent")
        return self.runner.legacy.bots[self.agent_sid]

    def _nav_nodes(self) -> Sequence[Dict[str, float]]:
        return (self.runner.world.get("nav_graph") or {}).get("nodes") or ()

    def _build_node_distances(self) -> Tuple[Tuple[float, ...], ...]:
        nodes = self._nav_nodes()
        count = len(nodes)
        distances = [[float("inf")] * count for _ in range(count)]
        for index in range(count):
            distances[index][index] = 0.0
        for left in range(count):
            for right in range(left + 1, count):
                a, b = nodes[left], nodes[right]
                if geometry.line_of_sight_clear(
                        a["x"], a["z"], b["x"], b["z"], self.runner.world):
                    distance = math.hypot(b["x"] - a["x"], b["z"] - a["z"])
                    distances[left][right] = distances[right][left] = distance
        for middle in range(count):
            for left in range(count):
                through = distances[left][middle]
                if not math.isfinite(through):
                    continue
                for right in range(count):
                    candidate = through + distances[middle][right]
                    if candidate < distances[left][right]:
                        distances[left][right] = candidate
        return tuple(tuple(row) for row in distances)

    def _visible_nodes(self, point: Tuple[float, float]) -> Tuple[Tuple[int, float], ...]:
        result = []
        for index, node in enumerate(self._nav_nodes()):
            if geometry.line_of_sight_clear(
                    point[0], point[1], node["x"], node["z"], self.runner.world):
                result.append((index, math.hypot(node["x"] - point[0], node["z"] - point[1])))
        return tuple(result)

    def _segment_has_guidance_clearance(self, start: Tuple[float, float],
                                        end: Tuple[float, float]) -> bool:
        if not geometry.line_of_sight_clear(*start, *end, self.runner.world):
            return False
        margin_u = self.guidance_clearance_m / simulation.UNIT_METERS_BOT
        if margin_u <= 0.0:
            return True
        half_w = self.runner.world["ground"]["width"] / 2 - 4.0
        half_d = self.runner.world["ground"]["depth"] / 2 - 4.0
        if min(half_w - abs(start[0]), half_w - abs(end[0]),
               half_d - abs(start[1]), half_d - abs(end[1])) < margin_u:
            return False
        for island in self.runner.world.get("islands", ()):
            points = island.get("points") or ()
            for index, point in enumerate(points):
                following = points[(index + 1) % len(points)]
                if min(
                    geometry.distance_point_segment(
                        start[0], start[1], point["x"], point["z"],
                        following["x"], following["z"]),
                    geometry.distance_point_segment(
                        end[0], end[1], point["x"], point["z"],
                        following["x"], following["z"]),
                    geometry.distance_point_segment(
                        point["x"], point["z"], *start, *end),
                ) < margin_u:
                    return False
        return True

    def _guidance_visible_nodes(
            self, point: Tuple[float, float]) -> Tuple[Tuple[int, float], ...]:
        if self.guidance_clearance_m <= 0.0:
            return self._visible_nodes(point)
        return tuple(
            (index, math.hypot(node["x"] - point[0], node["z"] - point[1]))
            for index, node in enumerate(self._nav_nodes())
            if self._segment_has_guidance_clearance(
                point, (float(node["x"]), float(node["z"]))))

    def _shortest_distance_u(self, start: Tuple[float, float],
                             goal: Tuple[float, float], *, guidance: bool = False) -> float:
        direct_clear = (self._segment_has_guidance_clearance(start, goal) if guidance
                        else geometry.line_of_sight_clear(
                            start[0], start[1], goal[0], goal[1], self.runner.world))
        if direct_clear:
            return math.hypot(goal[0] - start[0], goal[1] - start[1])
        best, _, _ = self._best_node_route_u(start, goal, guidance=guidance)
        return best

    def _best_node_route_u(
            self, start: Tuple[float, float], goal: Tuple[float, float],
            *, guidance: bool = False) -> Tuple[float, Optional[int], Optional[int]]:
        start_connections = self._visible_nodes(start)
        if guidance:
            goal_connections = (self._guidance_goal_connections if goal == self.goal
                                else self._guidance_visible_nodes(goal))
        else:
            goal_connections = (self._goal_connections if goal == self.goal
                                else self._visible_nodes(goal))
        best = float("inf")
        best_left = None
        best_right = None
        candidates = []
        for left, start_distance in start_connections:
            for right, goal_distance in goal_connections:
                candidate = start_distance + self._node_distances[left][right] + goal_distance
                if guidance and math.isfinite(candidate):
                    candidates.append((candidate, left, right))
                elif candidate < best:
                    best, best_left, best_right = candidate, left, right
        if guidance:
            nodes = self._nav_nodes()
            for candidate, left, right in sorted(candidates):
                node = nodes[left]
                if self._segment_has_guidance_clearance(
                        start, (float(node["x"]), float(node["z"]))):
                    return candidate, left, right
        return best, best_left, best_right

    def _guidance_target(self, position: Tuple[float, float]) -> Tuple[float, float]:
        if (self.guidance_mode == "goal"
                or self._segment_has_guidance_clearance(position, self.goal)):
            return self.goal
        _, left, right = self._best_node_route_u(position, self.goal, guidance=True)
        if left is None or right is None:
            return self.goal
        nodes = self._nav_nodes()
        left_point = (float(nodes[left]["x"]), float(nodes[left]["z"]))
        lookahead_u = self.waypoint_lookahead_m / simulation.UNIT_METERS_BOT
        if math.hypot(left_point[0] - position[0], left_point[1] - position[1]) > lookahead_u:
            return left_point
        if left == right:
            return self.goal
        best_next = None
        best_remaining = float("inf")
        for index, node in enumerate(nodes):
            if index == left or not self._segment_has_guidance_clearance(
                    left_point, (float(node["x"]), float(node["z"]))):
                continue
            edge_u = math.hypot(node["x"] - left_point[0], node["z"] - left_point[1])
            remaining = edge_u + self._node_distances[index][right]
            if remaining < best_remaining:
                best_remaining = remaining
                best_next = (float(node["x"]), float(node["z"]))
        return best_next if best_next is not None else left_point

    def _clearance_u(self, point: Tuple[float, float]) -> float:
        half_w = self.runner.world["ground"]["width"] / 2 - 4.0
        half_d = self.runner.world["ground"]["depth"] / 2 - 4.0
        boundary = min(half_w - abs(point[0]), half_d - abs(point[1]))
        return min(boundary, geometry.min_distance_to_islands(
            point[0], point[1], self.runner.world))

    def _random_safe_position(self) -> Tuple[float, float]:
        half_w = self.runner.world["ground"]["width"] / 2 - 12.0
        half_d = self.runner.world["ground"]["depth"] / 2 - 12.0
        for _ in range(1000):
            point = (self.runner.random.uniform(-half_w, half_w),
                     self.runner.random.uniform(-half_d, half_d))
            if (not geometry.point_on_any_island(*point, self.runner.world)
                    and self._clearance_u(point) >= 8.0):
                return point
        raise RuntimeError("aucune position de navigation sure trouvee")

    def _blocking_islands(self, start: Tuple[float, float],
                          goal: Tuple[float, float]) -> int:
        blocked = 0
        for island in self.runner.world.get("islands", ()):
            points = island.get("points") or ()
            if (geometry.point_in_polygon(*start, points)
                    or geometry.point_in_polygon(*goal, points)
                    or any(geometry.segments_intersect(
                        *start, *goal, edge["x"], edge["z"],
                        points[(index + 1) % len(points)]["x"],
                        points[(index + 1) % len(points)]["z"], include_boundary=True)
                        for index, edge in enumerate(points))):
                blocked += 1
        return blocked

    def _sample_route(self) -> Tuple[Tuple[float, float], Tuple[float, float], float, int]:
        attempts = 20000 if self.route_mode == "single_island" else 2000
        for _ in range(attempts):
            start = self._random_safe_position()
            distance_u = self.runner.random.uniform(
                self.min_route_m / simulation.UNIT_METERS_BOT,
                self.max_route_m / simulation.UNIT_METERS_BOT)
            angle = self.runner.random.uniform(0.0, math.tau)
            goal = (start[0] + math.cos(angle) * distance_u,
                    start[1] + math.sin(angle) * distance_u)
            if (geometry.point_on_any_island(*goal, self.runner.world)
                    or self._clearance_u(goal) < 8.0):
                continue
            blocking_islands = self._blocking_islands(start, goal)
            if self.route_mode == "open" and blocking_islands:
                continue
            if self.route_mode == "single_island" and blocking_islands != 1:
                continue
            if self.route_mode == "multi_island" and blocking_islands < 2:
                continue
            if self.route_mode == "blocked" and blocking_islands < 1:
                continue
            self.goal = goal
            self._goal_connections = self._visible_nodes(goal)
            shortest_u = self._shortest_distance_u(start, goal)
            if math.isfinite(shortest_u):
                if (self.max_detour_ratio is not None
                        and shortest_u / distance_u > self.max_detour_ratio):
                    continue
                self._guidance_goal_connections = self._guidance_visible_nodes(goal)
                if self.guidance_mode in {"safe_waypoint", "lookahead_waypoint"}:
                    guidance_shortest_u = self._shortest_distance_u(
                        start, goal, guidance=True)
                    if not math.isfinite(guidance_shortest_u):
                        continue
                    if self.progress_mode == "guidance":
                        shortest_u = guidance_shortest_u
                return (start, goal, shortest_u * simulation.UNIT_METERS_BOT,
                        blocking_islands)
        raise RuntimeError(f"aucune route accessible trouvee pour le mode {self.route_mode}")

    def _ray_distances(self, bot: Dict[str, Any]) -> Tuple[float, ...]:
        x = float(bot["position"]["x"])
        z = float(bot["position"]["z"])
        rotation = float(bot.get("rotation", 0.0))
        ray_max_u = self.ray_max_m / simulation.UNIT_METERS_BOT
        half_w = self.runner.world["ground"]["width"] / 2 - 4.0
        half_d = self.runner.world["ground"]["depth"] / 2 - 4.0
        distances = []
        for degrees in RAY_DIRECTIONS_DEG:
            angle = rotation + math.radians(degrees)
            dx, dz = -math.cos(angle), math.sin(angle)
            boundary_t = ray_max_u
            if dx > 1e-9:
                boundary_t = min(boundary_t, (half_w - x) / dx)
            elif dx < -1e-9:
                boundary_t = min(boundary_t, (-half_w - x) / dx)
            if dz > 1e-9:
                boundary_t = min(boundary_t, (half_d - z) / dz)
            elif dz < -1e-9:
                boundary_t = min(boundary_t, (-half_d - z) / dz)
            boundary_t = max(0.0, boundary_t)
            end_x, end_z = x + dx * boundary_t, z + dz * boundary_t
            hit = geometry.first_island_intersection(x, z, end_x, end_z, self.runner.world)
            distance = boundary_t * (hit if hit is not None else 1.0)
            distances.append(max(0.0, min(1.0, distance / ray_max_u)))
        return tuple(distances)

    def _predicted_action_clearance(
            self, bot: Dict[str, Any], rudder_ratio: float,
            speed_ratio: float, initial_clearance_m: float) -> Tuple[float, float]:
        """Projette une commande avec la meme cinematique que le controle externe."""
        x = float(bot["position"]["x"])
        z = float(bot["position"]["z"])
        rotation = float(bot.get("rotation", 0.0))
        speed = float(bot.get("speed", 0.0))
        rudder = float(bot.get("rudder", 0.0))
        rudder_max = float(bot.get("rudder_max", 0.36))
        max_speed = max(0.001, float(bot.get("max_speed_us", 0.0)))
        target_rudder = rudder_ratio * rudder_max
        target_speed = speed_ratio * max_speed
        rudder_step = float(bot.get("rudder_speed", 0.3)) * PHYSICS_DT
        throttle_step = float(bot.get("throttle_accel", 0.4)) * PHYSICS_DT
        minimum = initial_clearance_m
        clearance = initial_clearance_m
        steps = max(1, math.ceil(self.coastal_safety_horizon_s / PHYSICS_DT))
        for index in range(steps):
            rudder_delta = target_rudder - rudder
            rudder += (rudder_delta if abs(rudder_delta) <= rudder_step
                       else math.copysign(rudder_step, rudder_delta))
            speed_delta = target_speed - speed
            speed += (speed_delta if abs(speed_delta) <= throttle_step
                      else math.copysign(throttle_step, speed_delta))
            turn_ratio = max(min(1.0, abs(speed) / max_speed), 0.2)
            rotation += rudder * turn_ratio * (1 if speed >= 0 else -1) * PHYSICS_DT
            x -= math.cos(rotation) * speed * PHYSICS_DT
            z += math.sin(rotation) * speed * PHYSICS_DT
            if (index + 1) % self.frame_skip == 0 or index + 1 == steps:
                clearance = (0.0 if geometry.point_on_any_island(
                    x, z, self.runner.world) else
                    self._clearance_u((x, z)) * simulation.UNIT_METERS_BOT)
                minimum = min(minimum, clearance)
        return minimum, clearance

    def _safe_action(self, bot: Dict[str, Any], values: np.ndarray) -> Tuple[np.ndarray, bool]:
        if self.coastal_safety_clearance_m <= 0.0:
            return values, False
        current_clearance_m = self._clearance_u((
            float(bot["position"]["x"]), float(bot["position"]["z"])
        )) * simulation.UNIT_METERS_BOT
        reachable_m = (float(bot.get("max_speed_us", 0.0))
                       * simulation.UNIT_METERS_BOT * self.coastal_safety_horizon_s)
        if current_clearance_m >= self.coastal_safety_clearance_m + reachable_m:
            return values, False
        requested_rudder = RUDDER_LEVELS[int(values[0])]
        requested_throttle = THROTTLE_LEVELS[int(values[1])]
        requested = self._predicted_action_clearance(
            bot, requested_rudder, requested_throttle, current_clearance_m)
        if requested[0] >= self.coastal_safety_clearance_m:
            return values, False
        best_values = values
        best_score = (*requested, -abs(requested_throttle), 0.0)
        closest_safe_values = None
        closest_safe_score = None
        for rudder_index, rudder_ratio in enumerate(RUDDER_LEVELS):
            for throttle_index, throttle_ratio in enumerate(THROTTLE_LEVELS):
                clearance = self._predicted_action_clearance(
                    bot, rudder_ratio, throttle_ratio, current_clearance_m)
                score = (*clearance, -abs(throttle_ratio),
                         -abs(rudder_ratio - requested_rudder))
                if score > best_score:
                    best_score = score
                    best_values = np.asarray(
                        [rudder_index, throttle_index], dtype=np.int64)
                if clearance[0] >= self.coastal_safety_clearance_m:
                    deviation = (2.0 * abs(throttle_ratio - requested_throttle)
                                 + abs(rudder_ratio - requested_rudder))
                    safe_score = (-deviation, *clearance, -abs(throttle_ratio))
                    if closest_safe_score is None or safe_score > closest_safe_score:
                        closest_safe_score = safe_score
                        closest_safe_values = np.asarray(
                            [rudder_index, throttle_index], dtype=np.int64)
        selected = closest_safe_values if closest_safe_values is not None else best_values
        return selected, not np.array_equal(selected, values)

    def _observation(self) -> np.ndarray:
        bot = self._agent()
        position = bot["position"]
        target = self._guidance_target((float(position["x"]), float(position["z"])))
        dx, dz = target[0] - position["x"], target[1] - position["z"]
        rotation = float(bot.get("rotation", 0.0))
        forward = dx * -math.cos(rotation) + dz * math.sin(rotation)
        right = dx * math.sin(rotation) + dz * math.cos(rotation)
        scale_u = self.max_route_m / simulation.UNIT_METERS_BOT
        max_speed = max(0.001, float(bot["max_speed_us"]))
        rudder_max = max(0.001, float(bot["rudder_max"]))
        values = [
            max(-1.0, min(1.0, float(bot["speed"]) / max_speed)),
            max(-1.0, min(1.0, float(bot["rudder"]) / rudder_max)),
            max(-1.0, min(1.0, forward / scale_u)),
            max(-1.0, min(1.0, right / scale_u)),
            max(0.0, min(1.0, math.hypot(dx, dz) / scale_u)),
            *self._ray_distances(bot),
        ]
        return np.asarray(values, dtype=np.float32)

    def reset(self, *, seed: Optional[int] = None,
              options: Optional[Dict[str, Any]] = None):
        super().reset(seed=seed)
        if seed is None:
            seed = self.base_seed + self._episode_index
        self._episode_index += 1
        self.runner.reset(seed=seed)
        if options and "start" in options and "goal" in options:
            start = tuple(float(value) for value in options["start"])
            self.goal = tuple(float(value) for value in options["goal"])
            if len(start) != 2 or len(self.goal) != 2:
                raise ValueError("start et goal doivent contenir x,z")
            if min(self._clearance_u(start), self._clearance_u(self.goal)) < 0:
                raise ValueError("route hors de la zone navigable")
            self._goal_connections = self._visible_nodes(self.goal)
            self._guidance_goal_connections = self._guidance_visible_nodes(self.goal)
            shortest_u = self._shortest_distance_u(start, self.goal)
            if not math.isfinite(shortest_u):
                raise ValueError("route inaccessible")
            if self.guidance_mode in {"safe_waypoint", "lookahead_waypoint"}:
                guidance_shortest_u = self._shortest_distance_u(
                    start, self.goal, guidance=True)
                if not math.isfinite(guidance_shortest_u):
                    raise ValueError("route inaccessible avec la marge de guidage")
                if self.progress_mode == "guidance":
                    shortest_u = guidance_shortest_u
            shortest_m = shortest_u * simulation.UNIT_METERS_BOT
            blocking_islands = self._blocking_islands(start, self.goal)
        else:
            start, self.goal, shortest_m, blocking_islands = self._sample_route()
        rotation = (float(options["rotation"]) if options and "rotation" in options
                    else self.runner.random.uniform(0.0, math.tau))
        self.agent_sid = self.runner.spawn_bot(
            self.boat_type, external_control=True, ai=None, position=start,
            rotation=rotation, team_id="navigation")
        self._initial_shortest_m = shortest_m
        self._previous_shortest_m = shortest_m
        self._path_length_m = 0.0
        self._coastal_damage = 0.0
        self._near_coast_decisions = 0
        self._stationary_decisions = 0
        self._safety_interventions = 0
        self._decisions = 0
        self._last_position = start
        self._movement_anchor = start
        self._last_movement_at = self.runner.sim.now()
        return self._observation(), {
            "start": list(start), "goal": list(self.goal),
            "guidance_target": list(self._guidance_target(start)),
            "observation_version": self.observation_version,
            "shortest_path_m": shortest_m,
            "blocking_islands": blocking_islands,
            "direct_path_blocked": blocking_islands > 0,
        }

    def step(self, action):
        values = np.asarray(action, dtype=np.int64).reshape(-1)
        if values.size != 2 or np.any(values < 0) or np.any(values >= NAVIGATION_ACTION_NVECS):
            raise ValueError(f"action de navigation invalide: {values.tolist()}")
        bot = self._agent()
        values, intervened = self._safe_action(bot, values)
        self._safety_interventions += int(intervened)
        bot["control_target_rudder"] = RUDDER_LEVELS[int(values[0])]
        bot["control_target_speed_ratio"] = THROTTLE_LEVELS[int(values[1])]
        hp_before = float(bot["integrity"])
        for _ in range(self.frame_skip):
            before = (float(bot["position"]["x"]), float(bot["position"]["z"]))
            self.runner.step(PHYSICS_DT)
            if self.agent_sid not in self.runner.legacy.bots:
                break
            bot = self._agent()
            after = (float(bot["position"]["x"]), float(bot["position"]["z"]))
            self._path_length_m += math.hypot(
                after[0] - before[0], after[1] - before[1]) * simulation.UNIT_METERS_BOT

        self._decisions += 1
        if self.agent_sid not in self.runner.legacy.bots:
            self._coastal_damage += hp_before
            reward = (hp_before * self.reward_cfg["coastal_damage_per_point"]
                      + self.reward_cfg["decision_cost"])
            return np.zeros(NAVIGATION_OBS_DIM, dtype=np.float32), reward, True, False, {
                **self._terminal_info("sunk"), "coastal_damage": self._coastal_damage}

        bot = self._agent()
        current = (float(bot["position"]["x"]), float(bot["position"]["z"]))
        moved_u = math.hypot(current[0] - self._movement_anchor[0],
                             current[1] - self._movement_anchor[1])
        if moved_u * simulation.UNIT_METERS_BOT >= 20.0:
            self._movement_anchor = current
            self._last_movement_at = self.runner.sim.now()
        stationary = abs(float(bot["speed"])) < float(bot["max_speed_us"]) * 0.05
        if stationary:
            self._stationary_decisions += 1

        hp_after = float(bot["integrity"])
        damage = max(0.0, hp_before - hp_after)
        self._coastal_damage += damage
        clearance_m = self._clearance_u(current) * simulation.UNIT_METERS_BOT
        coastal_proximity = max(
            0.0, 1.0 - clearance_m / self.coastal_clearance_m)
        if coastal_proximity > 0.0:
            self._near_coast_decisions += 1
        shortest_u = self._shortest_distance_u(
            current, self.goal, guidance=self.progress_mode == "guidance")
        shortest_m = (shortest_u * simulation.UNIT_METERS_BOT
                      if math.isfinite(shortest_u) else self._previous_shortest_m)
        progress_m = self._previous_shortest_m - shortest_m
        self._previous_shortest_m = shortest_m
        goal_distance_m = math.hypot(
            self.goal[0] - current[0], self.goal[1] - current[1]) * simulation.UNIT_METERS_BOT

        reached = goal_distance_m <= self.goal_radius_m
        stuck = self.runner.sim.now() - self._last_movement_at >= self.stuck_seconds
        timeout = self.runner.sim.now() >= self.max_episode_seconds
        reward = (progress_m * self.reward_cfg["progress_per_meter"]
                  + damage * self.reward_cfg["coastal_damage_per_point"]
                  + coastal_proximity * self.reward_cfg["coastal_proximity"]
                  + self.reward_cfg["decision_cost"]
                  + (self.reward_cfg["stationary"] if stationary else 0.0))
        outcome = None
        if reached:
            reward += self.reward_cfg["arrival"]
            outcome = "arrived"
        elif stuck:
            reward += self.reward_cfg["stuck"]
            outcome = "stuck"
        elif timeout:
            reward += self.reward_cfg["timeout"]
            outcome = "timeout"
        terminated = reached or stuck
        truncated = timeout and not terminated
        info = self._terminal_info(outcome) if outcome else {
            "goal_distance_m": goal_distance_m,
            "coastal_damage": self._coastal_damage,
        }
        self._last_position = current
        return self._observation(), float(reward), terminated, truncated, info

    def _terminal_info(self, outcome: Optional[str]) -> Dict[str, Any]:
        path_efficiency = self._path_length_m / max(1.0, self._initial_shortest_m)
        return {
            "outcome": outcome,
            "success": outcome == "arrived",
            "coastal_damage": self._coastal_damage,
            "decisions": self._decisions,
            "stationary_decisions": self._stationary_decisions,
            "stationary_fraction": self._stationary_decisions / max(1, self._decisions),
            "near_coast_decisions": self._near_coast_decisions,
            "near_coast_fraction": self._near_coast_decisions / max(1, self._decisions),
            "safety_interventions": self._safety_interventions,
            "safety_intervention_fraction": self._safety_interventions / max(1, self._decisions),
            "path_length_m": self._path_length_m,
            "shortest_path_m": self._initial_shortest_m,
            "path_efficiency": path_efficiency,
            "elapsed_seconds": self.runner.sim.now(),
        }

    def close(self) -> None:
        self.agent_sid = None
