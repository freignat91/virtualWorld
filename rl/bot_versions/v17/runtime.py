"""Runtime autonome des politiques de mobilite experimentees en v17."""

from __future__ import annotations

import logging
import math
import random
import zlib
from typing import Any, Dict

import numpy as np

import events
import simulation

from .masked_recurrent_policy import SituationMaskedMlpLstmPolicy
from .navigable_path import (
    DESTINATION_CLEARANCE_M,
    NavigablePathMetric,
    ROUTE_CLEARANCE_M,
    ROUTE_LONG_SEGMENT_M,
    ROUTE_NEAR_AXIS_SEARCH_RADIUS_M,
    ROUTE_NODE_MARGIN_M,
    plan_segmented_route,
)
from .rl_control import (
    apply_action,
    build_observation,
    control_spec,
    control_version_for_spaces,
)
from .waypoints import (
    RLWaypointManager,
    WAYPOINT_CONTROL_VERSIONS,
    WAYPOINT_FINAL_REACHED_RADIUS_M,
    WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M,
    waypoint_reached,
)


RUNTIME_VERSION = "v17"


def model_custom_objects() -> Dict[str, Any]:
    """Force la classe de politique autonome au chargement du ZIP v17."""
    return {"policy_class": SituationMaskedMlpLstmPolicy}


def configure_model(model, boat_type: str) -> None:
    """Valide le modele exclusivement contre l'interface v17."""
    observation_dim = int((model.observation_space.shape or (0,))[0])
    model_nvec = tuple(int(value) for value in getattr(model.action_space, "nvec", ()))
    model.rl_control_version = control_version_for_spaces(
        boat_type, observation_dim, model_nvec,
        getattr(model, "rl_control_version", None))
    if not isinstance(model.policy, SituationMaskedMlpLstmPolicy):
        raise ValueError(f"politique sans runtime {RUNTIME_VERSION}")


class RuntimeController:
    """Controleur complet et autonome des bots v17."""

    runtime_version = RUNTIME_VERSION
    destination_clearance_m = DESTINATION_CLEARANCE_M
    final_waypoint_radius_m = WAYPOINT_FINAL_REACHED_RADIUS_M
    intermediate_waypoint_radius_m = WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M

    def __init__(self, model, decision_interval_s: float = 0.25,
                 waypoint_seed: int = 0) -> None:
        self.model = model
        self.decision_interval_s = decision_interval_s
        self.next_decision_at = 0.0
        self.state = None
        self.episode_start = True
        self.waypoints = RLWaypointManager(random.Random(waypoint_seed))
        self.uses_waypoints = model.rl_control_version in WAYPOINT_CONTROL_VERSIONS

    @staticmethod
    def create_route_planner(world: Dict[str, Any]) -> NavigablePathMetric:
        return NavigablePathMetric(
            world, clearance_m=ROUTE_CLEARANCE_M,
            endpoint_clearance_m=DESTINATION_CLEARANCE_M,
            node_margin_m=ROUTE_NODE_MARGIN_M)

    @staticmethod
    def plan_route(world: Dict[str, Any], start, goal, planner=None):
        return plan_segmented_route(world, start, goal, planner=planner)

    def route_trace(self, player_id: str, start, destination, route, planner):
        """Decrit la route exposee et le chemin Dijkstra interne pour diagnostic."""
        start = (float(start[0]), float(start[1]))
        destination = (float(destination["x"]), float(destination["z"]))
        planned = tuple((float(point["x"]), float(point["z"])) for point in route)
        try:
            graph_path = tuple(planner.shortest_path(start))
        except RuntimeError:
            graph_path = ()

        def distance_m(points) -> float:
            return sum(
                math.hypot(second[0] - first[0], second[1] - first[1])
                for first, second in zip(points, points[1:])) * simulation.UNIT_METERS_BOT

        direct_distance_m = math.hypot(
            destination[0] - start[0], destination[1] - start[1]
        ) * simulation.UNIT_METERS_BOT
        planned_distance_m = distance_m((start, *planned))
        segment_distances_m = [
            distance_m((first, second))
            for first, second in zip((start, *planned), planned)
        ]
        graph_distance_m = distance_m(graph_path) if graph_path else None
        return {
            "player_id": player_id,
            "runtime_version": RUNTIME_VERSION,
            "model_id": getattr(self.model, "_trace_model_id", None),
            "model_sha256": getattr(self.model, "_trace_model_sha256", None),
            "unit_meters": simulation.UNIT_METERS_BOT,
            "start": {"x": start[0], "z": start[1]},
            "destination": {"x": destination[0], "z": destination[1]},
            "waypoints": [
                {
                    "index": index,
                    "kind": "final" if index == len(planned) - 1 else "intermediate",
                    "x": point[0],
                    "z": point[1],
                    "arrival_radius_m": (
                        self.final_waypoint_radius_m
                        if index == len(planned) - 1
                        else self.intermediate_waypoint_radius_m),
                }
                for index, point in enumerate(planned)
            ],
            "graph_path": [{"x": point[0], "z": point[1]} for point in graph_path],
            "direct_distance_m": direct_distance_m,
            "planned_distance_m": planned_distance_m,
            "planned_segment_distances_m": segment_distances_m,
            "max_planned_segment_m": max(segment_distances_m, default=0.0),
            "graph_distance_m": graph_distance_m,
            "planned_to_graph_ratio": (
                planned_distance_m / graph_distance_m
                if graph_distance_m and graph_distance_m > 0.0 else None),
            "graph_detour_ratio": (
                graph_distance_m / direct_distance_m
                if graph_distance_m is not None and direct_distance_m > 0.0 else None),
            "destination_clearance_m": DESTINATION_CLEARANCE_M,
            "intermediate_clearance_m": ROUTE_CLEARANCE_M,
            "route_node_margin_m": ROUTE_NODE_MARGIN_M,
            "direct_goal_distance_m": ROUTE_LONG_SEGMENT_M,
            "near_axis_search_radius_m": ROUTE_NEAR_AXIS_SEARCH_RADIUS_M,
        }

    def ensure_waypoint(self, bot: Dict[str, Any], world: Dict[str, Any]) -> bool:
        return self.waypoints.ensure(bot, world)

    @staticmethod
    def _pause_for_checkpoint(bot: Dict[str, Any]) -> None:
        bot["control_target_speed_ratio"] = 0.0
        bot["control_target_rudder"] = 0.0
        bot["speed"] = 0.0
        bot["rudder"] = 0.0
        if bot.get("boatType") == "submarine":
            bot["control_target_depth_y"] = bot["position"].get("y", 0.0)
            bot["vertical_speed_us"] = 0.0

    def tick(self, bot: Dict[str, Any], sim, world: Dict[str, Any], dt: float) -> None:
        now = sim.now()
        if now < self.next_decision_at:
            return
        if self.uses_waypoints:
            if bot.get("rl_manual_checkpoint"):
                waypoint = bot.get("rl_waypoint")
                if waypoint is not None and waypoint_reached(bot, waypoint):
                    bot["rl_waypoints_reached"] = int(
                        bot.get("rl_waypoints_reached", 0)) + 1
                    remaining = bot.get("rl_route_waypoints")
                    bot["rl_waypoint"] = (
                        remaining.pop(0)
                        if isinstance(remaining, list) and remaining else None)
                    bot.pop("_last_emit_state", None)
                if bot.get("rl_waypoint") is None:
                    self._pause_for_checkpoint(bot)
                    self.next_decision_at = now + self.decision_interval_s
                    return
            else:
                self.ensure_waypoint(bot, world)
        observation = build_observation(bot, sim, world)
        captured = None
        if sim.trace_rl_decisions:
            try:
                threat = bot.get("rl_visible_threat")
                captured = (
                    observation.tolist(), None if threat is None else dict(threat),
                    self.episode_start)
            except Exception:
                logging.warning("[rl] decision trace capture failed")
        action, self.state = self.model.predict(
            observation,
            state=self.state,
            episode_start=np.array([self.episode_start], dtype=bool),
            deterministic=True,
        )
        self.episode_start = False
        result = apply_action(bot, sim, action)
        self.next_decision_at = now + self.decision_interval_s
        if captured is not None:
            try:
                sim.emit(events.RLDecision(
                    player_id=bot["id"],
                    control_version=control_spec(
                        bot["boatType"], bot.get("rl_control_version"))[0],
                    decision_at=now, physics_dt=dt, simulation_step=sim.trace_step,
                    decision_interval_s=self.decision_interval_s,
                    episode_start=captured[2], observation=captured[0],
                    action=np.asarray(action).reshape(-1).tolist(),
                    result=dict(result), visible_threat=captured[1],
                    model_id=getattr(self.model, "_trace_model_id", None),
                    model_sha256=getattr(self.model, "_trace_model_sha256", None)))
            except Exception:
                logging.warning("[rl] decision trace capture failed")


def attach_controller(bot: Dict[str, Any], ai_name: str, model) -> None:
    """Initialise tout l'etat runtime propre au bot v17."""
    bot["ai_tree"] = None
    bot["external_control"] = True
    boat_type = bot.get("boatType", "submarine")
    observation_dim = int((model.observation_space.shape or (0,))[0])
    model_nvec = tuple(int(value) for value in getattr(model.action_space, "nvec", ()))
    bot["rl_control_version"] = control_version_for_spaces(
        boat_type, observation_dim, model_nvec,
        getattr(model, "rl_control_version", None))
    waypoint_seed = zlib.crc32(f"{ai_name}:{boat_type}".encode("utf-8"))
    bot["rl_waypoint"] = None
    bot["rl_waypoints_reached"] = 0
    bot["rl_destination"] = None
    bot["rl_route_start"] = None
    bot["rl_route"] = []
    bot["rl_route_waypoints"] = []
    bot["rl_controller"] = RuntimeController(model, waypoint_seed=waypoint_seed)
    bot["control_target_rudder"] = 0.0
    bot["control_target_speed_ratio"] = 0.0
    bot["control_target_depth_y"] = bot["position"].get("y", 0.0)
