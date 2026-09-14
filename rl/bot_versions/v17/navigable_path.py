"""Distances de plus court chemin sur le graphe de visibilite des iles."""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Sequence, Tuple

import simulation

from . import geometry, nav_graph


Point = Tuple[float, float]

DESTINATION_CLEARANCE_M = 100.0
ROUTE_CLEARANCE_M = 500.0
ROUTE_NODE_MARGIN_M = 600.0
ROUTE_LONG_SEGMENT_M = 7500.0
ROUTE_NEAR_AXIS_SEARCH_RADIUS_M = 3000.0
ROUTE_NEAR_AXIS_SEARCH_STEP_M = 100.0
ROUTE_NEAR_AXIS_SEARCH_DIRECTIONS = 36
ROUTE_NEAR_AXIS_CANDIDATES_PER_LAYER = 96
ROUTE_NEAR_AXIS_EXTRA_SEGMENTS = 3


def blocking_island_count(start: Point, goal: Point,
                          world: Dict[str, Any]) -> int:
    """Compte les iles coupees par le segment direct ferme."""
    blocked = 0
    for island in world.get("islands", ()):
        points = island.get("points") or ()
        if not points:
            continue
        if (geometry.point_in_polygon(*start, points)
                or geometry.point_in_polygon(*goal, points)
                or any(geometry.segments_intersect(
                    *start, *goal, edge["x"], edge["z"],
                    points[(index + 1) % len(points)]["x"],
                    points[(index + 1) % len(points)]["z"],
                    include_boundary=True)
                    for index, edge in enumerate(points))):
            blocked += 1
    return blocked


class NavigablePathMetric:
    """Calcule une distance navigable sans exposer le chemin a la politique."""

    def __init__(self, world: Dict[str, Any], clearance_m: float = 0.0, *,
                 endpoint_clearance_m: float | None = None,
                 node_margin_m: float | None = None) -> None:
        if endpoint_clearance_m is None:
            endpoint_clearance_m = clearance_m
        values = (clearance_m, endpoint_clearance_m)
        if node_margin_m is not None:
            values += (node_margin_m,)
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("marge de navigation invalide")
        self.world = world
        self.clearance_u = clearance_m / simulation.UNIT_METERS_BOT
        self.endpoint_clearance_u = endpoint_clearance_m / simulation.UNIT_METERS_BOT
        self._point_clear_cache: Dict[Tuple[float, float, float], bool] = {}
        graph = (nav_graph.build_nav_graph(
            world, margin_m=node_margin_m, unit_meters=simulation.UNIT_METERS_BOT)
            if node_margin_m is not None else world.get("nav_graph") or {})
        source_nodes = graph.get("nodes") or ()
        self.nodes: Sequence[Dict[str, float]] = tuple(
            node for node in source_nodes
            if self._point_is_clear((float(node["x"]), float(node["z"]))))
        self.adjacency = [[] for _ in self.nodes]
        for left, first in enumerate(self.nodes):
            for right in range(left + 1, len(self.nodes)):
                second = self.nodes[right]
                if not self._segment_is_clear(
                        (first["x"], first["z"]), (second["x"], second["z"])):
                    continue
                distance = math.hypot(
                    second["x"] - first["x"], second["z"] - first["z"])
                self.adjacency[left].append((right, distance))
                self.adjacency[right].append((left, distance))
        self.goal: Point | None = None
        self._node_to_goal_u: Tuple[float, ...] = ()
        self._next_node_to_goal: Tuple[int | None, ...] = ()

    def _point_is_clear(self, point: Point, clearance_u: float | None = None) -> bool:
        clearance_u = self.clearance_u if clearance_u is None else clearance_u
        if clearance_u <= 0.0:
            return True
        cache_key = (point[0], point[1], clearance_u)
        if cache_key in self._point_clear_cache:
            return self._point_clear_cache[cache_key]
        ground = self.world.get("ground") or {}
        half_width = float(ground.get("width", 0.0)) / 2.0
        half_depth = float(ground.get("depth", 0.0)) / 2.0
        boundary_clearance = min(
            half_width - abs(point[0]), half_depth - abs(point[1]))
        clear = bool(
            boundary_clearance > clearance_u
            and not geometry.point_on_any_island(*point, self.world)
            and geometry.min_distance_to_islands(*point, self.world) > clearance_u)
        self._point_clear_cache[cache_key] = clear
        return clear

    def _segment_is_clear(self, start: Point, goal: Point,
                          clearance_u: float | None = None) -> bool:
        clearance_u = self.clearance_u if clearance_u is None else clearance_u
        if clearance_u <= 0.0:
            return geometry.line_of_sight_clear(*start, *goal, self.world)
        if (not self._point_is_clear(start, clearance_u)
                or not self._point_is_clear(goal, clearance_u)):
            return False
        min_x = min(start[0], goal[0]) - clearance_u
        max_x = max(start[0], goal[0]) + clearance_u
        min_z = min(start[1], goal[1]) - clearance_u
        max_z = max(start[1], goal[1]) + clearance_u
        for bounds in geometry.ensure_island_bounds(self.world):
            if (bounds["maxX"] < min_x or bounds["minX"] > max_x
                    or bounds["maxZ"] < min_z or bounds["minZ"] > max_z):
                continue
            points = bounds["points"]
            for index, first in enumerate(points):
                second = points[(index + 1) % len(points)]
                if geometry.segments_intersect(
                        *start, *goal, first["x"], first["z"],
                        second["x"], second["z"], include_boundary=True):
                    return False
                distances = (
                    geometry.distance_point_segment(
                        start[0], start[1], first["x"], first["z"],
                        second["x"], second["z"]),
                    geometry.distance_point_segment(
                        goal[0], goal[1], first["x"], first["z"],
                        second["x"], second["z"]),
                    geometry.distance_point_segment(
                        first["x"], first["z"], *start, *goal),
                    geometry.distance_point_segment(
                        second["x"], second["z"], *start, *goal),
                )
                if min(distances) <= clearance_u:
                    return False
        return True

    def _visible_connections(self, point: Point,
                             clearance_u: float | None = None) -> Tuple[Tuple[int, float], ...]:
        return tuple(
            (index, math.hypot(node["x"] - point[0], node["z"] - point[1]))
            for index, node in enumerate(self.nodes)
            if self._segment_is_clear(
                point, (float(node["x"]), float(node["z"])), clearance_u))

    def set_goal(self, goal: Point) -> None:
        """Precalcule par Dijkstra la distance de chaque noeud au but."""
        self.goal = (float(goal[0]), float(goal[1]))
        if not self._point_is_clear(self.goal, self.endpoint_clearance_u):
            raise ValueError("objectif hors de la zone navigable")
        distances = [float("inf")] * len(self.nodes)
        next_nodes: List[int | None] = [None] * len(self.nodes)
        queue = []
        for index, distance in self._visible_connections(
                self.goal, self.endpoint_clearance_u):
            if distance < distances[index]:
                distances[index] = distance
                heapq.heappush(queue, (distance, index))
        while queue:
            distance, index = heapq.heappop(queue)
            if distance != distances[index]:
                continue
            for neighbor, edge_distance in self.adjacency[index]:
                candidate = distance + edge_distance
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    next_nodes[neighbor] = index
                    heapq.heappush(queue, (candidate, neighbor))
        self._node_to_goal_u = tuple(distances)
        self._next_node_to_goal = tuple(next_nodes)

    def shortest_path(self, start: Point) -> Tuple[Point, ...]:
        """Reconstruit le plus court chemin courant, depart et but inclus."""
        if self.goal is None:
            raise RuntimeError("objectif de chemin navigable absent")
        start = (float(start[0]), float(start[1]))
        if not self._point_is_clear(start, self.endpoint_clearance_u):
            raise RuntimeError("depart hors de la zone navigable")
        if self._segment_is_clear(start, self.goal, self.endpoint_clearance_u):
            return start, self.goal
        candidates = (
            (start_distance + self._node_to_goal_u[index], index)
            for index, start_distance in self._visible_connections(
                start, self.endpoint_clearance_u)
            if math.isfinite(self._node_to_goal_u[index]))
        _, index = min(candidates, default=(float("inf"), -1))
        if index < 0:
            raise RuntimeError("aucun chemin navigable vers l'objectif")
        path = [start]
        for _ in range(len(self.nodes) + 1):
            node = self.nodes[index]
            point = (float(node["x"]), float(node["z"]))
            if point != path[-1]:
                path.append(point)
            next_index = self._next_node_to_goal[index]
            if next_index is None:
                break
            index = next_index
        else:
            raise RuntimeError("cycle dans le chemin navigable")
        if self.goal != path[-1]:
            path.append(self.goal)
        return tuple(path)

    def distance_m(self, start: Point) -> float:
        """Retourne le plus court chemin courant, en metres."""
        if self.goal is None:
            raise RuntimeError("objectif de chemin navigable absent")
        if self._segment_is_clear(start, self.goal, self.endpoint_clearance_u):
            distance_u = math.hypot(
                self.goal[0] - start[0], self.goal[1] - start[1])
        else:
            distance_u = min((
                start_distance + self._node_to_goal_u[index]
                for index, start_distance in self._visible_connections(
                    start, self.endpoint_clearance_u)
            ), default=float("inf"))
        return distance_u * simulation.UNIT_METERS_BOT


def segment_route(path: Sequence[Point],
                  metric: NavigablePathMetric | None = None) -> Tuple[Point, ...]:
    """Decoupe chaque arete du chemin pour garantir la portee locale maximale."""
    points = tuple((float(point[0]), float(point[1])) for point in path)
    if len(points) < 2:
        return ()
    long_u = ROUTE_LONG_SEGMENT_M / simulation.UNIT_METERS_BOT
    waypoints: List[Point] = []
    for edge_index, (start, goal) in enumerate(zip(points, points[1:])):
        distance_u = math.hypot(goal[0] - start[0], goal[1] - start[1])
        parts = max(1, math.ceil(distance_u / long_u))
        for part in range(1, parts):
            ratio = part / parts
            candidate = (
                start[0] + (goal[0] - start[0]) * ratio,
                start[1] + (goal[1] - start[1]) * ratio,
            )
            if metric is not None and not metric._point_is_clear(candidate):
                return ()
            waypoints.append(candidate)
        if edge_index < len(points) - 2:
            waypoints.append(goal)
    waypoints.append(points[-1])
    return tuple(waypoints)


def _aligned_segment_route(metric: NavigablePathMetric, start: Point,
                           goal: Point) -> Tuple[Point, ...] | None:
    """Decoupe l'axe direct avec des objectifs intermediaires degages."""
    dx = goal[0] - start[0]
    dz = goal[1] - start[1]
    distance_u = math.hypot(dx, dz)
    long_u = ROUTE_LONG_SEGMENT_M / simulation.UNIT_METERS_BOT
    segment_count = math.ceil(distance_u / long_u)
    if segment_count <= 1:
        return (goal,)

    waypoints: List[Point] = []
    previous_u = 0.0
    search_step_u = 1.0
    for index in range(1, segment_count):
        remaining_segments = segment_count - index
        minimum_u = max(
            previous_u + search_step_u,
            distance_u - remaining_segments * long_u)
        maximum_u = min(previous_u + long_u, distance_u - search_step_u)
        if minimum_u > maximum_u:
            return None
        ideal_u = min(max(distance_u * index / segment_count, minimum_u), maximum_u)
        max_offset = math.ceil(max(ideal_u - minimum_u, maximum_u - ideal_u))
        candidate_u = None
        for offset in range(max_offset + 1):
            distances = (ideal_u,) if offset == 0 else (
                ideal_u - offset * search_step_u,
                ideal_u + offset * search_step_u)
            for along_u in distances:
                if along_u < minimum_u or along_u > maximum_u:
                    continue
                ratio = along_u / distance_u
                point = (start[0] + dx * ratio, start[1] + dz * ratio)
                if metric._point_is_clear(point):
                    candidate_u = along_u
                    waypoints.append(point)
                    break
            if candidate_u is not None:
                break
        if candidate_u is None:
            return None
        previous_u = candidate_u
    waypoints.append(goal)
    return tuple(waypoints)


def _near_axis_candidates(metric: NavigablePathMetric, ideal: Point,
                          start: Point, goal: Point) -> Tuple[Tuple[float, Point], ...]:
    """Echantillonne les points degages les plus proches d'une position ideale."""
    step_u = ROUTE_NEAR_AXIS_SEARCH_STEP_M / simulation.UNIT_METERS_BOT
    radius_u = ROUTE_NEAR_AXIS_SEARCH_RADIUS_M / simulation.UNIT_METERS_BOT
    route_dx = goal[0] - start[0]
    route_dz = goal[1] - start[1]
    route_length_sq = route_dx * route_dx + route_dz * route_dz
    candidates: Dict[Tuple[float, float], Tuple[float, Point]] = {}
    ring_count = math.ceil(radius_u / step_u)
    for ring in range(ring_count + 1):
        radius = ring * step_u
        angles = (0.0,) if ring == 0 else tuple(
            math.tau * index / ROUTE_NEAR_AXIS_SEARCH_DIRECTIONS
            for index in range(ROUTE_NEAR_AXIS_SEARCH_DIRECTIONS))
        for angle in angles:
            point = (ideal[0] + math.cos(angle) * radius,
                     ideal[1] + math.sin(angle) * radius)
            progress = ((point[0] - start[0]) * route_dx
                        + (point[1] - start[1]) * route_dz) / route_length_sq
            if not 0.0 < progress < 1.0 or not metric._point_is_clear(point):
                continue
            displacement = math.hypot(point[0] - ideal[0], point[1] - ideal[1])
            key = (round(point[0], 9), round(point[1], 9))
            candidates[key] = (displacement, point)
    return tuple(sorted(
        candidates.values(), key=lambda item: (item[0], item[1][0], item[1][1])
    )[:ROUTE_NEAR_AXIS_CANDIDATES_PER_LAYER])


def _near_aligned_segment_route(metric: NavigablePathMetric, start: Point,
                                goal: Point) -> Tuple[Point, ...] | None:
    """Minimise la route parmi des couches de points proches de l'axe direct."""
    dx = goal[0] - start[0]
    dz = goal[1] - start[1]
    distance_u = math.hypot(dx, dz)
    long_u = ROUTE_LONG_SEGMENT_M / simulation.UNIT_METERS_BOT
    minimum_segments = math.ceil(distance_u / long_u)
    epsilon = 1e-9
    for segment_count in range(
            minimum_segments, minimum_segments + ROUTE_NEAR_AXIS_EXTRA_SEGMENTS + 1):
        states = [(0.0, 0.0, start, ())]
        viable = True
        for index in range(1, segment_count):
            ratio = index / segment_count
            ideal = (start[0] + dx * ratio, start[1] + dz * ratio)
            next_states = []
            for displacement, candidate in _near_axis_candidates(
                    metric, ideal, start, goal):
                predecessors = (
                    (cost + math.hypot(
                        candidate[0] - previous[0], candidate[1] - previous[1]),
                     offset + displacement, path)
                    for cost, offset, previous, path in states
                    if math.hypot(
                        candidate[0] - previous[0], candidate[1] - previous[1]
                    ) <= long_u + epsilon)
                best = min(predecessors, default=None,
                           key=lambda item: (item[0], item[1], item[2]))
                if best is not None:
                    next_states.append((
                        best[0], best[1], candidate, (*best[2], candidate)))
            if not next_states:
                viable = False
                break
            states = next_states
        if not viable:
            continue
        complete = (
            (cost + math.hypot(goal[0] - point[0], goal[1] - point[1]),
             offset, path)
            for cost, offset, point, path in states
            if math.hypot(goal[0] - point[0], goal[1] - point[1]) <= long_u + epsilon)
        best = min(complete, default=None, key=lambda item: (item[0], item[1], item[2]))
        if best is not None:
            return (*best[2], goal)
    return None


def plan_segmented_route(world: Dict[str, Any], start: Point,
                          goal: Point,
                          planner: NavigablePathMetric | None = None) -> Tuple[Point, ...]:
    """Planifie une route sure; le depart est exclu des sous-objectifs retournes."""
    metric = planner or NavigablePathMetric(
        world, clearance_m=ROUTE_CLEARANCE_M,
        endpoint_clearance_m=DESTINATION_CLEARANCE_M,
        node_margin_m=ROUTE_NODE_MARGIN_M)
    metric.set_goal(goal)
    if math.hypot(goal[0] - start[0], goal[1] - start[1]) * (
            simulation.UNIT_METERS_BOT) <= ROUTE_LONG_SEGMENT_M:
        return ((float(goal[0]), float(goal[1])),)
    aligned_route = _aligned_segment_route(metric, start, goal)
    if aligned_route is not None:
        return aligned_route
    near_aligned_route = _near_aligned_segment_route(metric, start, goal)
    if near_aligned_route is not None:
        return near_aligned_route
    try:
        graph_route = segment_route(metric.shortest_path(start), metric=metric)
    except RuntimeError:
        graph_route = ()
    if graph_route:
        return graph_route
    raise RuntimeError("aucune route segmentee sure vers l'objectif")
