"""Gestion déterministe des objectifs de navigation des politiques RL."""

from __future__ import annotations

import math
import random
from typing import Any, Dict, Tuple

import simulation

from . import geometry


WAYPOINT_MIN_DISTANCE_M = 4000.0
WAYPOINT_MAX_DISTANCE_M = 5000.0
WAYPOINT_ISLAND_CLEARANCE_M = 150.0
WAYPOINT_FINAL_REACHED_RADIUS_M = 200.0
WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M = 500.0
WAYPOINT_SAMPLE_ATTEMPTS = 5000
WAYPOINT_CONTROL_VERSIONS = frozenset({
    "sub_duel_v3", "sub_duel_v4", "destroyer_duel_v5", "destroyer_duel_v6",
})


def waypoint_distance_m(bot: Dict[str, Any], waypoint: Dict[str, float]) -> float:
    """Retourne la distance horizontale entre une coque et son objectif."""
    position = bot["position"]
    return math.hypot(
        float(waypoint["x"]) - float(position["x"]),
        float(waypoint["z"]) - float(position["z"]),
    ) * simulation.UNIT_METERS_BOT


def waypoint_reached(bot: Dict[str, Any], waypoint: Dict[str, float]) -> bool:
    """Applique le rayon large uniquement aux points intermediaires."""
    remaining = bot.get("rl_route_waypoints")
    radius_m = (WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M
                if isinstance(remaining, list) and remaining
                else WAYPOINT_FINAL_REACHED_RADIUS_M)
    return waypoint_distance_m(bot, waypoint) <= radius_m


class RLWaypointManager:
    """Choisit les objectifs sans laisser cette décision à la politique."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def sample(self, bot: Dict[str, Any], world: Dict[str, Any]) -> Dict[str, float]:
        """Échantillonne un point lointain, dégagé et directement visible."""
        position = bot["position"]
        start = (float(position["x"]), float(position["z"]))
        ground = world.get("ground") or {}
        half_width = float(ground.get("width", 0.0)) / 2.0 - 4.0
        half_depth = float(ground.get("depth", 0.0)) / 2.0 - 4.0
        min_distance_u = WAYPOINT_MIN_DISTANCE_M / simulation.UNIT_METERS_BOT
        max_distance_u = WAYPOINT_MAX_DISTANCE_M / simulation.UNIT_METERS_BOT
        island_clearance_u = WAYPOINT_ISLAND_CLEARANCE_M / simulation.UNIT_METERS_BOT
        for _ in range(WAYPOINT_SAMPLE_ATTEMPTS):
            angle = self.rng.uniform(0.0, math.tau)
            distance_u = self.rng.uniform(min_distance_u, max_distance_u)
            candidate = (
                start[0] + math.cos(angle) * distance_u,
                start[1] + math.sin(angle) * distance_u,
            )
            if abs(candidate[0]) > half_width or abs(candidate[1]) > half_depth:
                continue
            if geometry.point_on_any_island(*candidate, world):
                continue
            if geometry.min_distance_to_islands(*candidate, world) < island_clearance_u:
                continue
            if not geometry.line_of_sight_clear(*start, *candidate, world):
                continue
            return {"x": candidate[0], "z": candidate[1]}
        raise RuntimeError("aucun objectif RL lointain et visible trouvé")

    def ensure(self, bot: Dict[str, Any], world: Dict[str, Any]) -> bool:
        """Remplace un objectif atteint ou initialise l'objectif manquant."""
        waypoint = bot.get("rl_waypoint")
        reached = bool(
            waypoint is not None
            and waypoint_reached(bot, waypoint))
        if waypoint is None or reached:
            bot["rl_waypoint"] = self.sample(bot, world)
        if reached:
            bot["rl_waypoints_reached"] = int(bot.get("rl_waypoints_reached", 0)) + 1
        return reached


def waypoint_observation(bot: Dict[str, Any]) -> Tuple[float, float, float]:
    """Encode relèvement relatif et distance bornée de l'objectif courant."""
    waypoint = bot.get("rl_waypoint")
    if waypoint is None:
        return 0.0, 0.0, 0.0
    position = bot["position"]
    dx = float(waypoint["x"]) - float(position["x"])
    dz = float(waypoint["z"]) - float(position["z"])
    distance_u = math.hypot(dx, dz)
    if distance_u <= 1e-9:
        return 0.0, 0.0, 0.0
    rotation = float(bot.get("rotation", 0.0))
    forward = dx * -math.cos(rotation) + dz * math.sin(rotation)
    right = dx * math.sin(rotation) + dz * math.cos(rotation)
    distance_m = distance_u * simulation.UNIT_METERS_BOT
    return (
        max(-1.0, min(1.0, right / distance_u)),
        max(-1.0, min(1.0, forward / distance_u)),
        max(0.0, min(1.0, distance_m / WAYPOINT_MAX_DISTANCE_M)),
    )
