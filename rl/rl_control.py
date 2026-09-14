"""Interface stable entre une politique RL et la simulation autoritaire."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Sequence, Tuple

import numpy as np

import geometry
import simulation
from rl.waypoints import waypoint_observation


RAY_MAX_M = 1000.0
RAY_DIRECTIONS_DEG = (0, 45, 90, 135, 180, 225, 270, 315)
DIRECTIONAL_RAY_DIRECTIONS_DEG = (
    -150, -120, -90, -60, -45, -30, -15, 0,
    15, 30, 45, 60, 90, 120, 150, 180,
)
LONG_RANGE_RAY_DIRECTIONS_DEG = (-90, -60, -30, 0, 30, 60, 90)
LONG_RANGE_RAY_MAX_M = 2500.0
SUBMARINE_OBSERVATION_VERSION = "sub_duel_v1"
SUBMARINE_OBS_DIM = 32
SUBMARINE_ACTION_NVECS = np.array([5, 5, 5, 3, 2], dtype=np.int64)
SUBMARINE_V2_OBSERVATION_VERSION = "sub_duel_v2"
SUBMARINE_V3_OBSERVATION_VERSION = "sub_duel_v3"
SUBMARINE_V4_OBSERVATION_VERSION = "sub_duel_v4"
DESTROYER_V1_OBSERVATION_VERSION = "destroyer_duel_v1"
DESTROYER_V1_OBS_DIM = 36
DESTROYER_V1_ACTION_NVECS = np.array([5, 5, 5, 2, 2], dtype=np.int64)
DESTROYER_OBSERVATION_VERSION = "destroyer_duel_v2"
DESTROYER_OBS_DIM = 40
DESTROYER_ACTION_NVECS = np.array([5, 5, 5, 2, 2, 4], dtype=np.int64)
DESTROYER_V3_OBSERVATION_VERSION = "destroyer_duel_v3"
DESTROYER_V4_OBSERVATION_VERSION = "destroyer_duel_v4"
DESTROYER_V5_OBSERVATION_VERSION = "destroyer_duel_v5"
DESTROYER_V6_OBSERVATION_VERSION = "destroyer_duel_v6"
DESTROYER_V3_TORPEDO_SLOTS = 6
DESTROYER_V3_TORPEDO_SLOT_DIM = 7
DESTROYER_V3_LURE_SLOTS = 6
DESTROYER_V3_LURE_SLOT_DIM = 5
DESTROYER_V3_TORPEDO_START = 21
DESTROYER_V3_LURE_START = (
    DESTROYER_V3_TORPEDO_START + DESTROYER_V3_TORPEDO_SLOTS * DESTROYER_V3_TORPEDO_SLOT_DIM)
DESTROYER_V3_RAY_START = (
    DESTROYER_V3_LURE_START + DESTROYER_V3_LURE_SLOTS * DESTROYER_V3_LURE_SLOT_DIM)
DESTROYER_V3_OBS_DIM = DESTROYER_V3_RAY_START + 8
DESTROYER_V3_ACTION_NVECS = np.array([5, 5, 5, 2, 2], dtype=np.int64)
MOBILITY_TORPEDO_SLOTS = 6
MOBILITY_TORPEDO_SLOT_DIM = 10
MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM = 11
MOBILITY_LURE_SLOTS = 6
MOBILITY_LURE_SLOT_DIM = 5
MOBILITY_DIRECTIONAL_LURE_SLOT_DIM = 6
MOBILITY_GRENADE_SLOTS = 6
MOBILITY_GRENADE_SLOT_DIM = 9
MOBILITY_DIRECTIONAL_GRENADE_SLOT_DIM = 10
SUBMARINE_V2_TORPEDO_START = 17
SUBMARINE_V2_LURE_START = (
    SUBMARINE_V2_TORPEDO_START + MOBILITY_TORPEDO_SLOTS * MOBILITY_TORPEDO_SLOT_DIM)
SUBMARINE_V2_GRENADE_START = (
    SUBMARINE_V2_LURE_START + MOBILITY_LURE_SLOTS * MOBILITY_LURE_SLOT_DIM)
SUBMARINE_V2_RAY_START = (
    SUBMARINE_V2_GRENADE_START + MOBILITY_GRENADE_SLOTS * MOBILITY_GRENADE_SLOT_DIM)
SUBMARINE_V2_OBS_DIM = SUBMARINE_V2_RAY_START + len(RAY_DIRECTIONS_DEG)
SUBMARINE_V2_ACTION_NVECS = SUBMARINE_ACTION_NVECS.copy()
SUBMARINE_V3_CONTACT_START = 13
SUBMARINE_V3_TORPEDO_START = SUBMARINE_V2_TORPEDO_START + 3
SUBMARINE_V3_LURE_START = (
    SUBMARINE_V3_TORPEDO_START
    + MOBILITY_TORPEDO_SLOTS * MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM)
SUBMARINE_V3_GRENADE_START = (
    SUBMARINE_V3_LURE_START
    + MOBILITY_LURE_SLOTS * MOBILITY_DIRECTIONAL_LURE_SLOT_DIM)
SUBMARINE_V3_RAY_START = (
    SUBMARINE_V3_GRENADE_START
    + MOBILITY_GRENADE_SLOTS * MOBILITY_DIRECTIONAL_GRENADE_SLOT_DIM)
SUBMARINE_V3_WAYPOINT_START = (
    SUBMARINE_V3_RAY_START + len(DIRECTIONAL_RAY_DIRECTIONS_DEG))
SUBMARINE_V3_OBS_DIM = SUBMARINE_V3_WAYPOINT_START + 3
SUBMARINE_V3_ACTION_NVECS = SUBMARINE_V2_ACTION_NVECS.copy()
SUBMARINE_V4_LONG_RAY_START = SUBMARINE_V3_WAYPOINT_START
SUBMARINE_V4_WAYPOINT_START = (
    SUBMARINE_V4_LONG_RAY_START + len(LONG_RANGE_RAY_DIRECTIONS_DEG))
SUBMARINE_V4_OBS_DIM = SUBMARINE_V4_WAYPOINT_START + 3
SUBMARINE_V4_ACTION_NVECS = SUBMARINE_V3_ACTION_NVECS.copy()
DESTROYER_V4_TORPEDO_START = 21
DESTROYER_V4_LURE_START = (
    DESTROYER_V4_TORPEDO_START + MOBILITY_TORPEDO_SLOTS * MOBILITY_TORPEDO_SLOT_DIM)
DESTROYER_V4_GRENADE_START = (
    DESTROYER_V4_LURE_START + MOBILITY_LURE_SLOTS * MOBILITY_LURE_SLOT_DIM)
DESTROYER_V4_RAY_START = (
    DESTROYER_V4_GRENADE_START + MOBILITY_GRENADE_SLOTS * MOBILITY_GRENADE_SLOT_DIM)
DESTROYER_V4_OBS_DIM = DESTROYER_V4_RAY_START + len(RAY_DIRECTIONS_DEG)
DESTROYER_V4_ACTION_NVECS = DESTROYER_V3_ACTION_NVECS.copy()
DESTROYER_V5_CONTACT_START = 16
DESTROYER_V5_TORPEDO_START = DESTROYER_V4_TORPEDO_START + 2
DESTROYER_V5_LURE_START = (
    DESTROYER_V5_TORPEDO_START
    + MOBILITY_TORPEDO_SLOTS * MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM)
DESTROYER_V5_GRENADE_START = (
    DESTROYER_V5_LURE_START
    + MOBILITY_LURE_SLOTS * MOBILITY_DIRECTIONAL_LURE_SLOT_DIM)
DESTROYER_V5_RAY_START = (
    DESTROYER_V5_GRENADE_START
    + MOBILITY_GRENADE_SLOTS * MOBILITY_DIRECTIONAL_GRENADE_SLOT_DIM)
DESTROYER_V5_WAYPOINT_START = (
    DESTROYER_V5_RAY_START + len(DIRECTIONAL_RAY_DIRECTIONS_DEG))
DESTROYER_V5_OBS_DIM = DESTROYER_V5_WAYPOINT_START + 3
DESTROYER_V5_ACTION_NVECS = DESTROYER_V4_ACTION_NVECS.copy()
DESTROYER_V6_LONG_RAY_START = DESTROYER_V5_WAYPOINT_START
DESTROYER_V6_WAYPOINT_START = (
    DESTROYER_V6_LONG_RAY_START + len(LONG_RANGE_RAY_DIRECTIONS_DEG))
DESTROYER_V6_OBS_DIM = DESTROYER_V6_WAYPOINT_START + 3
DESTROYER_V6_ACTION_NVECS = DESTROYER_V5_ACTION_NVECS.copy()

# Alias conservés pour les checkpoints sous-marins existants.
OBSERVATION_VERSION = SUBMARINE_OBSERVATION_VERSION
OBS_DIM = SUBMARINE_OBS_DIM
ACTION_NVECS = SUBMARINE_ACTION_NVECS
CONTACT_MEMORY_S = 30.0
CONTACT_FIRE_MAX_AGE_S = 1.0
CONTACT_DEPTH_MAX_M = 450.0

RUDDER_LEVELS = (-1.0, -0.5, 0.0, 0.5, 1.0)
THROTTLE_LEVELS = (-0.35, 0.0, 0.35, 0.65, 1.0)
FULL_REVERSE_THROTTLE_LEVELS = (-1.0, 0.0, 0.35, 0.65, 1.0)
DEPTH_LEVELS = (0.01, 0.08, 0.25, 0.45, 0.70)


def control_spec(boat_type: str, version: str | None = None) -> Tuple[str, int, np.ndarray]:
    """Retourne la version et les espaces propres au type de bateau."""
    if boat_type == "submarine":
        if version == SUBMARINE_V4_OBSERVATION_VERSION:
            return version, SUBMARINE_V4_OBS_DIM, SUBMARINE_V4_ACTION_NVECS
        if version == SUBMARINE_V3_OBSERVATION_VERSION:
            return version, SUBMARINE_V3_OBS_DIM, SUBMARINE_V3_ACTION_NVECS
        if version == SUBMARINE_V2_OBSERVATION_VERSION:
            return version, SUBMARINE_V2_OBS_DIM, SUBMARINE_V2_ACTION_NVECS
        if version not in (None, SUBMARINE_OBSERVATION_VERSION):
            raise ValueError(f"version de contrôle incompatible avec {boat_type}: {version}")
        return SUBMARINE_OBSERVATION_VERSION, SUBMARINE_OBS_DIM, SUBMARINE_ACTION_NVECS
    if boat_type == "destroyer":
        if version in (None, DESTROYER_V1_OBSERVATION_VERSION):
            return DESTROYER_V1_OBSERVATION_VERSION, DESTROYER_V1_OBS_DIM, DESTROYER_V1_ACTION_NVECS
        if version == DESTROYER_OBSERVATION_VERSION:
            return DESTROYER_OBSERVATION_VERSION, DESTROYER_OBS_DIM, DESTROYER_ACTION_NVECS
        if version == DESTROYER_V3_OBSERVATION_VERSION:
            return DESTROYER_V3_OBSERVATION_VERSION, DESTROYER_V3_OBS_DIM, DESTROYER_V3_ACTION_NVECS
        if version == DESTROYER_V4_OBSERVATION_VERSION:
            return DESTROYER_V4_OBSERVATION_VERSION, DESTROYER_V4_OBS_DIM, DESTROYER_V4_ACTION_NVECS
        if version == DESTROYER_V5_OBSERVATION_VERSION:
            return DESTROYER_V5_OBSERVATION_VERSION, DESTROYER_V5_OBS_DIM, DESTROYER_V5_ACTION_NVECS
        if version == DESTROYER_V6_OBSERVATION_VERSION:
            return DESTROYER_V6_OBSERVATION_VERSION, DESTROYER_V6_OBS_DIM, DESTROYER_V6_ACTION_NVECS
        raise ValueError(f"version de contrôle incompatible avec {boat_type}: {version}")
    raise ValueError(f"type de bateau RL inconnu: {boat_type}")


def control_version_for_spaces(boat_type: str, observation_dim: int,
                               action_nvecs: Sequence[int],
                               declared_version: str | None = None) -> str:
    """Identifie une interface de contrôle à partir des espaces du modèle."""
    actual_nvecs = tuple(int(value) for value in action_nvecs)
    if declared_version is not None:
        version, expected_dim, expected_nvecs = control_spec(boat_type, declared_version)
        if (observation_dim != expected_dim
                or actual_nvecs != tuple(int(value) for value in expected_nvecs)):
            raise ValueError(f"espaces RL incompatibles avec {boat_type} {version}")
        return version
    versions = (
        SUBMARINE_OBSERVATION_VERSION, SUBMARINE_V2_OBSERVATION_VERSION,
        SUBMARINE_V3_OBSERVATION_VERSION,
        SUBMARINE_V4_OBSERVATION_VERSION) if boat_type == "submarine" else (
        DESTROYER_V1_OBSERVATION_VERSION, DESTROYER_OBSERVATION_VERSION,
        DESTROYER_V3_OBSERVATION_VERSION, DESTROYER_V4_OBSERVATION_VERSION,
        DESTROYER_V5_OBSERVATION_VERSION, DESTROYER_V6_OBSERVATION_VERSION)
    for version in versions:
        _, expected_dim, expected_nvecs = control_spec(boat_type, version)
        if observation_dim == expected_dim and actual_nvecs == tuple(expected_nvecs):
            return version
    raise ValueError(f"espaces RL incompatibles avec {boat_type}")


def contact_detected_index(boat_type: str, version: str | None = None) -> int:
    """Retourne l'indice du contact frais dans l'observation."""
    if boat_type == "submarine":
        return (SUBMARINE_V3_CONTACT_START
                if version in {SUBMARINE_V3_OBSERVATION_VERSION,
                               SUBMARINE_V4_OBSERVATION_VERSION} else 10)
    if version in {DESTROYER_V5_OBSERVATION_VERSION,
                   DESTROYER_V6_OBSERVATION_VERSION}:
        return DESTROYER_V5_CONTACT_START
    return 18 if version == DESTROYER_OBSERVATION_VERSION else 14


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _ratio(value: float) -> float:
    """Borne explicitement un ratio non signé, y compris pour une valeur non finie."""
    value = float(value)
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _throttle_target(bot: Dict[str, Any], index: int) -> float:
    """Utilise la marche arrière complète uniquement pour les nouveaux schémas."""
    levels = (FULL_REVERSE_THROTTLE_LEVELS
              if bot.get("rl_control_version") in {
                  SUBMARINE_V3_OBSERVATION_VERSION,
                  SUBMARINE_V4_OBSERVATION_VERSION,
                  DESTROYER_V5_OBSERVATION_VERSION,
                  DESTROYER_V6_OBSERVATION_VERSION,
              } else THROTTLE_LEVELS)
    return levels[index]


def _yaw_rate_ratio(bot: Dict[str, Any]) -> float:
    """Normalise la vitesse angulaire réellement appliquée par la simulation."""
    max_speed = max(0.001, float(bot.get("max_speed_us", 0.0)))
    rudder_max = max(0.001, float(bot.get("rudder_max", 0.36)))
    speed = float(bot.get("speed", 0.0))
    turn_ratio = max(min(1.0, abs(speed) / max_speed), 0.2)
    direction = 1.0 if speed >= 0.0 else -1.0
    return _clip(float(bot.get("rudder", 0.0)) * turn_ratio * direction / rudder_max)


def _relative_to_boat(bot: Dict[str, Any], x: float, z: float) -> Tuple[float, float]:
    """Projette un point en coordonnées avant/droite du bateau."""
    pos = bot["position"]
    dx = x - pos["x"]
    dz = z - pos["z"]
    rotation = float(bot.get("rotation", 0.0))
    forward_x = -math.cos(rotation)
    forward_z = math.sin(rotation)
    right_x = math.sin(rotation)
    right_z = math.cos(rotation)
    return dx * forward_x + dz * forward_z, dx * right_x + dz * right_z


def _ammo_ratio(current: int, maximum: int) -> float:
    return _ratio(current / max(1, maximum))


def _boat_at_surface(boat_state: Dict[str, Any]) -> bool:
    """Utilise le meme seuil de flottaison que les actions reservees a la surface."""
    boat = boat_state.get("boat") or {}
    flotation_m = float(boat.get("flotation", 2.0))
    surface_y = -flotation_m / simulation.UNIT_METERS_BOT
    return float((boat_state.get("position") or {}).get("y", 0.0)) >= surface_y - 0.05


def _visual_contacts(bot: Dict[str, Any], sim: simulation.Sim,
                     world: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Voit uniquement une coque adverse en surface par segment geometrique libre."""
    if not _boat_at_surface(bot):
        return []
    bx = float(bot["position"]["x"])
    bz = float(bot["position"]["z"])
    contacts = []
    for sid, player in sim.players.items():
        if (player.get("id") == bot.get("id") or simulation.same_team(bot, player)
                or player.get("sunk") or not _boat_at_surface(player)):
            continue
        position = player.get("position") or {}
        x = float(position.get("x", 0.0))
        z = float(position.get("z", 0.0))
        if not geometry.line_of_sight_clear(bx, bz, x, z, world):
            continue
        contacts.append({
            "id": player["id"], "sid": sid,
            "x": x, "y": float(position.get("y", 0.0)), "z": z,
            "dist_m": math.hypot(x - bx, z - bz) * simulation.UNIT_METERS_BOT,
            "noise_perceived": 0.0,
        })
    return contacts


def _update_contact(bot: Dict[str, Any], sim: simulation.Sim,
                    world: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, bool]:
    now = sim.now()
    detected = sim.detect_enemies_passive(bot, world)
    detected = detected + sim.active_sonar_contacts(bot)
    if bot.get("rl_control_version") in {
            SUBMARINE_V2_OBSERVATION_VERSION, SUBMARINE_V3_OBSERVATION_VERSION,
            DESTROYER_V4_OBSERVATION_VERSION, DESTROYER_V5_OBSERVATION_VERSION}:
        detected += _visual_contacts(bot, sim, world)
    detected = [contact for contact in detected
                if contact.get("tracked", True) and sim.bot_target_los(bot, contact)]
    if detected:
        nearest = min(detected, key=lambda item: float(item.get("dist_m", float("inf"))))
        contact = {
            "id": nearest["id"], "sid": nearest["sid"],
            "x": float(nearest["x"]), "y": float(nearest.get("y", 0.0)),
            "z": float(nearest["z"]), "at": now,
            "noise": float(nearest.get("noise_perceived", 0.0)),
            "boat": {"flotation": (sim.players[nearest["sid"]].get("boat") or {}).get("flotation", 2)},
        }
        if "active_detected_until" in nearest:
            contact["active_detected_until"] = nearest["active_detected_until"]
        bot["rl_contact"] = contact
        bot["rl_contact_tracked"] = True
        return contact, True
    bot["rl_contact_tracked"] = False
    contact = bot.get("rl_contact")
    if contact is None or now - float(contact.get("at", 0.0)) > CONTACT_MEMORY_S:
        bot.pop("rl_contact", None)
        return None, False
    return contact, False


def _ray_distances(bot: Dict[str, Any], world: Dict[str, Any], *,
                   directions: Sequence[int] = RAY_DIRECTIONS_DEG,
                   proximity: bool = False,
                   ray_max_m: float = RAY_MAX_M) -> Iterable[float]:
    ray_max_u = ray_max_m / simulation.UNIT_METERS_BOT
    step_u = 5.0
    x = float(bot["position"]["x"])
    z = float(bot["position"]["z"])
    rotation = float(bot.get("rotation", 0.0))
    half_w = world["ground"]["width"] / 2 - 4.0
    half_d = world["ground"]["depth"] / 2 - 4.0
    for degrees in directions:
        angle = rotation + math.radians(degrees)
        direction_x = -math.cos(angle)
        direction_z = math.sin(angle)
        distance = step_u
        while distance < ray_max_u:
            px = x + direction_x * distance
            pz = z + direction_z * distance
            if (px < -half_w or px > half_w or pz < -half_d or pz > half_d
                    or geometry.point_on_any_island(px, pz, world)):
                break
            distance += step_u
        distance_ratio = _ratio(distance / ray_max_u)
        yield _ratio(1.0 - distance_ratio) if proximity else distance_ratio


def _ray_proximities(bot: Dict[str, Any], world: Dict[str, Any]) -> Iterable[float]:
    """Mesure seize proximités, avec une résolution angulaire renforcée devant."""
    return _ray_distances(
        bot, world, directions=DIRECTIONAL_RAY_DIRECTIONS_DEG, proximity=True)


def _long_range_ray_proximities(
        bot: Dict[str, Any], world: Dict[str, Any]) -> Iterable[float]:
    """Mesure sept ouvertures laterales et frontales a longue portee."""
    return _ray_distances(
        bot, world, directions=LONG_RANGE_RAY_DIRECTIONS_DEG,
        proximity=True, ray_max_m=LONG_RANGE_RAY_MAX_M)


def _torpedo_observation(bot: Dict[str, Any], sim: simulation.Sim,
                         world: Dict[str, Any]) -> Tuple[float, ...]:
    """Radar local strict ; CPA/ETA cinematiques, sans verrou ni type prive."""
    result = (0.0,) * 7
    best_rank = (True, float("inf"))
    bot["rl_torpedo_detected"] = False
    tracing = sim.trace_rl_decisions
    if tracing:
        bot["rl_visible_threat"] = None
    for torpedo in sim.torpedoes.values():
        threat = simulation.torpedo_radar_threat(bot, torpedo, world)
        if threat is None:
            continue
        distance_m, _, eta = threat
        # ETA > 0 equivaut a une projection brute positive ; ne pas supprimer
        # les CPA passes a <= 200 m, encore dangereux par proximite/explosion.
        rank = (eta <= 0.0, eta)
        if rank >= best_rank:
            continue
        best_rank = rank
        bot["rl_torpedo_detected"] = True
        if tracing:
            bot["rl_visible_threat"] = {
                "owner_id": torpedo.get("ownerPlayerId"), "tid": torpedo.get("tid")}
        forward, right = _relative_to_boat(bot, torpedo["x"], torpedo["z"])
        # Slots historiques conserves : verrou exact et type restent inconnus,
        # meme pour les torpilles alliees (aucune classification necessaire).
        result = (1.0, _clip(forward / 200.0), _clip(right / 200.0),
                  eta / 10.0, 0.0, 0.0,
                  _ratio(distance_m / 2000.0))
    return result


def _relative_vector_to_boat(bot: Dict[str, Any], x: float, z: float) -> Tuple[float, float]:
    """Projette un vecteur monde en composantes avant/droite du bateau."""
    rotation = float(bot.get("rotation", 0.0))
    return (-x * math.cos(rotation) + z * math.sin(rotation),
            x * math.sin(rotation) + z * math.cos(rotation))


def _multi_torpedo_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                world: Dict[str, Any], *, include_kind: bool,
                                directional: bool = False) -> Tuple[float, ...]:
    """Expose six trajectoires radar, sans verrou ni cible privee."""
    candidates = []
    bx = float(bot["position"]["x"])
    bz = float(bot["position"]["z"])
    rotation = float(bot.get("rotation", 0.0))
    boat_speed = float(bot.get("speed", 0.0))
    boat_vx = -math.cos(rotation) * boat_speed
    boat_vz = math.sin(rotation) * boat_speed
    for torpedo in sim.torpedoes.values():
        if torpedo.get("ownerPlayerId") == bot.get("id"):
            continue
        if not simulation.torpedo_radar_visible(bot, torpedo, world):
            continue
        speed = float(torpedo.get("speed", 0.0))
        if speed <= 0.001:
            continue
        tx = float(torpedo["x"])
        tz = float(torpedo["z"])
        t_raw, cpa_u = geometry.closest_approach_on_segment(
            bx, bz, tx, tz,
            tx + float(torpedo.get("dirX", 0.0)) * speed * 10.0,
            tz + float(torpedo.get("dirZ", 0.0)) * speed * 10.0)
        distance_u = math.hypot(tx - bx, tz - bz)
        cpa_m = cpa_u * simulation.UNIT_METERS_BOT
        group = 0 if t_raw > 0.0 and cpa_m <= 200.0 else 1 if t_raw > 0.0 else 2
        rank = (group, max(0.0, t_raw) if group == 0 else distance_u,
                cpa_m, tx, tz, float(torpedo.get("dirX", 0.0)),
                float(torpedo.get("dirZ", 0.0)), speed)
        forward, right = _relative_to_boat(bot, tx, tz)
        relative_vx = float(torpedo.get("dirX", 0.0)) * speed - boat_vx
        relative_vz = float(torpedo.get("dirZ", 0.0)) * speed - boat_vz
        velocity_forward, velocity_right = _relative_vector_to_boat(
            bot, relative_vx, relative_vz)
        if directional:
            bearing_sin = right / distance_u if distance_u > 1e-9 else 0.0
            bearing_cos = forward / distance_u if distance_u > 1e-9 else 0.0
            values = (
                1.0, _clip(bearing_sin), _clip(bearing_cos),
                _ratio(distance_u * simulation.UNIT_METERS_BOT / 10000.0),
                _clip(velocity_forward / 10.0), _clip(velocity_right / 10.0),
                _ratio(cpa_m / 2000.0), _ratio(t_raw),
            )
        else:
            values = (1.0, _clip(forward / 1000.0), _clip(right / 1000.0),
                      _clip(velocity_forward / 10.0), _clip(velocity_right / 10.0),
                      _ratio(cpa_m / 2000.0), _ratio(t_raw))
        if include_kind:
            kind = torpedo.get("kind")
            values += (1.0 if kind == "acoustic" else 0.0,
                       1.0 if kind == "autonomous" else 0.0,
                       1.0 if kind == "wireGuided" else 0.0)
        candidates.append((rank, torpedo, values))
    candidates.sort(key=lambda item: item[0])
    selected = candidates[:DESTROYER_V3_TORPEDO_SLOTS]
    bot["rl_torpedo_detected"] = bool(selected)
    if sim.trace_rl_decisions:
        bot["rl_visible_threat"] = (None if not selected else {
            "owner_id": selected[0][1].get("ownerPlayerId"),
            "tid": selected[0][1].get("tid"),
        })
    slot_dim = (MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM if directional else
                MOBILITY_TORPEDO_SLOT_DIM if include_kind else
                DESTROYER_V3_TORPEDO_SLOT_DIM)
    values = [0.0] * (MOBILITY_TORPEDO_SLOTS * slot_dim)
    for index, (_, _, slot) in enumerate(selected):
        start = index * slot_dim
        values[start:start + slot_dim] = slot
    return tuple(values)


def _destroyer_v3_torpedo_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                       world: Dict[str, Any]) -> Tuple[float, ...]:
    """Conserve les slots historiques sans type de torpille."""
    return _multi_torpedo_observation(bot, sim, world, include_kind=False)


def _typed_torpedo_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                world: Dict[str, Any]) -> Tuple[float, ...]:
    """Ajoute le type public aux trajectoires visibles des nouveaux modeles."""
    return _multi_torpedo_observation(bot, sim, world, include_kind=True)


def _directional_typed_torpedo_observation(
        bot: Dict[str, Any], sim: simulation.Sim,
        world: Dict[str, Any]) -> Tuple[float, ...]:
    """Encode relèvement, distance, cinématique et type de six torpilles."""
    return _multi_torpedo_observation(
        bot, sim, world, include_kind=True, directional=True)


def _destroyer_v3_lure_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                   world: Dict[str, Any], *,
                                   directional: bool = False) -> Tuple[float, ...]:
    """Expose les six leurres actifs les plus proches, sans identite adverse."""
    candidates = []
    now = sim.now()
    for lure in sim.lures.values():
        remaining = float(lure.get("expiresAt", 0.0)) - now
        if remaining <= 0.0:
            continue
        own = lure.get("ownerId") == bot.get("id")
        if not own and not simulation.radar_position_visible(
                bot, lure["x"], lure.get("y", 0.0), lure["z"], world):
            continue
        forward, right = _relative_to_boat(bot, lure["x"], lure["z"])
        distance_u = math.hypot(forward, right)
        if directional:
            bearing_sin = right / distance_u if distance_u > 1e-9 else 0.0
            bearing_cos = forward / distance_u if distance_u > 1e-9 else 0.0
            slot = (
                1.0, _clip(bearing_sin), _clip(bearing_cos),
                _ratio(distance_u * simulation.UNIT_METERS_BOT / 10000.0),
                _ratio(remaining / 120.0), 1.0 if own else -1.0,
            )
        else:
            slot = (1.0, _clip(forward / 1000.0), _clip(right / 1000.0),
                    _ratio(remaining / 120.0), 1.0 if own else -1.0)
        candidates.append(((distance_u, slot), slot))
    candidates.sort(key=lambda item: item[0])
    slot_dim = (MOBILITY_DIRECTIONAL_LURE_SLOT_DIM if directional else
                DESTROYER_V3_LURE_SLOT_DIM)
    values = [0.0] * (DESTROYER_V3_LURE_SLOTS * slot_dim)
    for index, (_, slot) in enumerate(candidates[:DESTROYER_V3_LURE_SLOTS]):
        start = index * slot_dim
        values[start:start + slot_dim] = slot
    return tuple(values)


def _directional_lure_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                  world: Dict[str, Any]) -> Tuple[float, ...]:
    """Encode relèvement, distance, durée et propriété de six leurres."""
    return _destroyer_v3_lure_observation(bot, sim, world, directional=True)


def _grenade_observation(bot: Dict[str, Any], sim: simulation.Sim, *,
                         directional: bool = False) -> Tuple[float, ...]:
    """Expose les trajectoires publiques de six grenades, sans cible privee."""
    candidates = []
    max_depth_u = max(1.0, float(bot.get("max_depth_m", 200.0))) / simulation.UNIT_METERS_BOT
    for grenade in sim.grenades.values():
        x = float(grenade.get("x", 0.0))
        y = float(grenade.get("y", 0.0))
        z = float(grenade.get("z", 0.0))
        forward, right = _relative_to_boat(bot, x, z)
        planar_distance_u = math.hypot(forward, right)
        velocity_forward, velocity_right = _relative_vector_to_boat(
            bot, float(grenade.get("vx", 0.0)), float(grenade.get("vz", 0.0)))
        target_depth_u = max(0.0, float(grenade.get("targetDepthU", 0.0)))
        sink_speed_u = max(0.001, float(grenade.get("sinkSpeedU", 0.0)))
        if grenade.get("phase") == "water":
            time_to_explosion = max(0.0, (target_depth_u + y) / sink_speed_u)
        else:
            velocity_y = float(grenade.get("vy", 0.0))
            discriminant = max(0.0, velocity_y * velocity_y + 2.0 * simulation.GRENADE_GRAVITY * y)
            time_to_water = (velocity_y + math.sqrt(discriminant)) / simulation.GRENADE_GRAVITY
            time_to_explosion = max(0.0, time_to_water) + target_depth_u / sink_speed_u
        explosion_y = -target_depth_u
        bot_y = float(bot["position"].get("y", 0.0))
        distance_u = math.hypot(planar_distance_u, explosion_y - bot_y)
        own = grenade.get("ownerPlayerId") == bot.get("id")
        radius_m = max(0.0, float(grenade.get("effectRadiusU", 0.0))) * simulation.UNIT_METERS_BOT
        if directional:
            bearing_sin = right / planar_distance_u if planar_distance_u > 1e-9 else 0.0
            bearing_cos = forward / planar_distance_u if planar_distance_u > 1e-9 else 0.0
            slot = (
                1.0, _clip(bearing_sin), _clip(bearing_cos),
                _ratio(planar_distance_u * simulation.UNIT_METERS_BOT / 10000.0),
                _clip(velocity_forward / 2000.0),
                _clip(velocity_right / 2000.0),
                _clip((explosion_y - bot_y) / max_depth_u),
                _ratio(time_to_explosion / 120.0),
                _ratio(radius_m / 500.0),
                1.0 if own else -1.0,
            )
        else:
            slot = (
                1.0,
                _clip(forward / 1000.0),
                _clip(right / 1000.0),
                _clip((explosion_y - bot_y) / max_depth_u),
                _clip(velocity_forward / 2000.0),
                _clip(velocity_right / 2000.0),
                _ratio(time_to_explosion / 120.0),
                _ratio(radius_m / 500.0),
                1.0 if own else -1.0,
            )
        candidates.append(((time_to_explosion, distance_u, x, z), slot))
    candidates.sort(key=lambda item: item[0])
    slot_dim = (MOBILITY_DIRECTIONAL_GRENADE_SLOT_DIM if directional else
                MOBILITY_GRENADE_SLOT_DIM)
    values = [0.0] * (MOBILITY_GRENADE_SLOTS * slot_dim)
    for index, (_, slot) in enumerate(candidates[:MOBILITY_GRENADE_SLOTS]):
        start = index * slot_dim
        values[start:start + slot_dim] = slot
    return tuple(values)


def _directional_grenade_observation(bot: Dict[str, Any],
                                     sim: simulation.Sim) -> Tuple[float, ...]:
    """Encode relèvement, distance, trajectoire et effet de six grenades."""
    return _grenade_observation(bot, sim, directional=True)


def _build_submarine_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                 world: Dict[str, Any]) -> np.ndarray:
    """Construit une observation sans lire l'état réel d'un ennemi non détecté."""
    obs = np.zeros(OBS_DIM, dtype=np.float32)
    boat = bot.get("boat") or {}
    sid = bot["sid"]
    max_speed = max(0.001, float(bot.get("max_speed_us", 0.0)))
    max_depth_m = max(1.0, float(bot.get("max_depth_m", 200.0)))
    max_depth_u = max_depth_m / simulation.UNIT_METERS_BOT
    rudder_max = max(0.001, float(bot.get("rudder_max", 0.36)))
    ammo = sim._legacy.torpedo_ammo.get(sid) or {}
    specs = simulation.boat_torpedo_specs(boat)
    max_acoustic = int((specs.get("acoustic") or {}).get("count", 0))
    max_acoustic += int((specs.get("wireGuided") or {}).get("count", 0))
    max_autonomous = int((specs.get("autonomous") or {}).get("count", 0))
    max_lures = int((boat.get("acousticLures") or {}).get("number", 0))
    speed_ratio = float(bot.get("speed", 0.0)) / max_speed
    rudder_ratio = abs(float(bot.get("rudder", 0.0))) / rudder_max
    emitted_noise = simulation.compute_emitted_noise(
        boat, abs(speed_ratio), speed_ratio < 0, rudder_ratio)

    obs[0] = _clip(speed_ratio)
    obs[1] = _ratio(-float(bot["position"].get("y", 0.0)) / max_depth_u)
    obs[2] = _clip(float(bot.get("rudder", 0.0)) / rudder_max)
    obs[3] = _ratio(float(bot.get("integrity", 100.0)) / bot.get("maxIntegrity", 100.0))
    obs[4] = _ammo_ratio(int(ammo.get("acoustic", 0)), max_acoustic)
    obs[5] = _ammo_ratio(int(ammo.get("autonomous", 0)), max_autonomous)
    obs[6] = _ammo_ratio(int(sim._legacy.lure_ammo.get(sid, 0)), max_lures)
    obs[7] = 1.0 if sim.now() >= float(bot.get("next_torpedo_at", 0.0)) else 0.0
    obs[8] = 1.0 if sim.now() >= float(bot.get("next_lure_at", 0.0)) else 0.0
    obs[9] = _ratio(emitted_noise / max(1.0, float(boat.get("noise", 100.0))))

    contact, detected_now = _update_contact(bot, sim, world)
    if contact is not None:
        forward, right = _relative_to_boat(bot, contact["x"], contact["z"])
        distance_m = math.hypot(forward, right) * simulation.UNIT_METERS_BOT
        age = max(0.0, sim.now() - float(contact["at"]))
        obs[10] = 1.0 if detected_now else 0.0
        obs[11] = _clip(forward / 300.0)
        obs[12] = _clip(right / 300.0)
        obs[13] = _ratio(distance_m / 5000.0)
        obs[14] = _ratio(age / CONTACT_MEMORY_S)
        obs[15] = _ratio(-float(contact.get("y", 0.0)) / max_depth_u)
        obs[16] = _ratio(float(contact.get("noise", 0.0)) / 20.0)

    obs[17:24] = _torpedo_observation(bot, sim, world)

    obs[24:32] = tuple(_ray_distances(bot, world))
    return obs


def _build_submarine_v2_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Etend le sous-marin avec six menaces typees, leurres et grenades."""
    base = _build_submarine_observation(bot, sim, world)
    obs = np.zeros(SUBMARINE_V2_OBS_DIM, dtype=np.float32)
    obs[:SUBMARINE_V2_TORPEDO_START] = base[:SUBMARINE_V2_TORPEDO_START]
    obs[SUBMARINE_V2_TORPEDO_START:SUBMARINE_V2_LURE_START] = (
        _typed_torpedo_observation(bot, sim, world))
    obs[SUBMARINE_V2_LURE_START:SUBMARINE_V2_GRENADE_START] = (
        _destroyer_v3_lure_observation(bot, sim, world))
    obs[SUBMARINE_V2_GRENADE_START:SUBMARINE_V2_RAY_START] = (
        _grenade_observation(bot, sim))
    obs[SUBMARINE_V2_RAY_START:] = base[24:32]
    return obs


def _replace_contact_with_bearing(obs: np.ndarray, start: int,
                                  bot: Dict[str, Any]) -> None:
    """Remplace les coordonnées du contact par son relèvement relatif unitaire."""
    contact = bot.get("rl_contact")
    if contact is None:
        return
    forward, right = _relative_to_boat(bot, contact["x"], contact["z"])
    distance_u = math.hypot(forward, right)
    obs[start] = 1.0
    if distance_u > 1e-9:
        obs[start + 1] = _clip(right / distance_u)
        obs[start + 2] = _clip(forward / distance_u)
    contact_depth_m = -float(contact.get("y", 0.0)) * simulation.UNIT_METERS_BOT
    obs[start + 5] = _ratio(contact_depth_m / CONTACT_DEPTH_MAX_M)


def _build_submarine_v3_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Encode les relèvements du contact et des six torpilles typées."""
    base = _build_submarine_observation(bot, sim, world)
    obs = np.zeros(SUBMARINE_V3_OBS_DIM, dtype=np.float32)
    obs[0] = base[0]
    throttle_ratio = float(bot.get("control_target_speed_ratio", 0.0))
    obs[1] = _clip(throttle_ratio) if math.isfinite(throttle_ratio) else 0.0
    obs[2] = _yaw_rate_ratio(bot)
    obs[3] = _clip(float(bot.get("vertical_speed_us", 0.0))
                   / simulation.SUBMARINE_VERTICAL_SPEED_US)
    obs[4:SUBMARINE_V3_TORPEDO_START] = base[1:SUBMARINE_V2_TORPEDO_START]
    _replace_contact_with_bearing(obs, SUBMARINE_V3_CONTACT_START, bot)
    obs[SUBMARINE_V3_TORPEDO_START:SUBMARINE_V3_LURE_START] = (
        _directional_typed_torpedo_observation(bot, sim, world))
    obs[SUBMARINE_V3_LURE_START:SUBMARINE_V3_GRENADE_START] = (
        _directional_lure_observation(bot, sim, world))
    obs[SUBMARINE_V3_GRENADE_START:SUBMARINE_V3_RAY_START] = (
        _directional_grenade_observation(bot, sim))
    obs[SUBMARINE_V3_RAY_START:SUBMARINE_V3_WAYPOINT_START] = tuple(
        _ray_proximities(bot, world))
    obs[SUBMARINE_V3_WAYPOINT_START:] = waypoint_observation(bot)
    return obs


def _build_submarine_v4_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Ajoute sept rayons longue portee sans exposer le chemin de reward."""
    base = _build_submarine_v3_observation(bot, sim, world)
    obs = np.zeros(SUBMARINE_V4_OBS_DIM, dtype=np.float32)
    obs[:SUBMARINE_V4_LONG_RAY_START] = base[:SUBMARINE_V3_WAYPOINT_START]
    obs[SUBMARINE_V4_LONG_RAY_START:SUBMARINE_V4_WAYPOINT_START] = tuple(
        _long_range_ray_proximities(bot, world))
    obs[SUBMARINE_V4_WAYPOINT_START:] = base[SUBMARINE_V3_WAYPOINT_START:]
    return obs


def _build_destroyer_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                 world: Dict[str, Any]) -> np.ndarray:
    """Construit l'observation surface, armement et sonar du destroyer."""
    obs = np.zeros(DESTROYER_V1_OBS_DIM, dtype=np.float32)
    boat = bot.get("boat") or {}
    sid = bot["sid"]
    max_speed = max(0.001, float(bot.get("max_speed_us", 0.0)))
    rudder_max = max(0.001, float(bot.get("rudder_max", 0.36)))
    torpedo_ammo = sim._legacy.torpedo_ammo.get(sid) or {}
    torpedo_specs = simulation.boat_torpedo_specs(boat)
    cannon_ammo = sim._legacy.cannon_ammo.get(sid) or {}
    speed_ratio = float(bot.get("speed", 0.0)) / max_speed
    rudder_ratio = abs(float(bot.get("rudder", 0.0))) / rudder_max
    emitted_noise = simulation.compute_emitted_noise(
        boat, abs(speed_ratio), speed_ratio < 0, rudder_ratio)
    now = sim.now()

    obs[0] = _clip(speed_ratio)
    obs[1] = _clip(float(bot.get("rudder", 0.0)) / rudder_max)
    obs[2] = _ratio(float(bot.get("integrity", 100.0)) / bot.get("maxIntegrity", 100.0))
    obs[3] = _ratio(emitted_noise / max(1.0, float(boat.get("noise", 100.0))))
    obs[4] = _ammo_ratio(
        int(torpedo_ammo.get("acoustic", 0)),
        int((torpedo_specs.get("acoustic") or {}).get("count", 0)))
    obs[5] = _ammo_ratio(
        int(torpedo_ammo.get("autonomous", 0)),
        int((torpedo_specs.get("autonomous") or {}).get("count", 0)))
    obs[6] = _ammo_ratio(
        int(cannon_ammo.get("cannon", 0)),
        int((boat.get("cannon") or {}).get("ammunition", 0)))
    obs[7] = _ammo_ratio(
        int(sim._legacy.grenade_ammo.get(sid, 0)),
        int((boat.get("grenade") or {}).get("number", 0)))
    obs[8] = _ammo_ratio(
        int(sim._legacy.lure_ammo.get(sid, 0)),
        int((boat.get("acousticLures") or {}).get("number", 0)))
    obs[9] = 1.0 if now >= float(bot.get("next_torpedo_at", 0.0)) else 0.0
    obs[10] = 1.0 if now >= float(bot.get("next_cannon_at", 0.0)) else 0.0
    obs[11] = 1.0 if now >= float(bot.get("next_grenade_at", 0.0)) else 0.0
    obs[12] = 1.0 if now >= float(bot.get("next_lure_at", 0.0)) else 0.0
    obs[13] = 1.0 if now >= float(bot.get("bb", {}).get("next_sonar_ping_at", 0.0)) else 0.0

    contact, detected_now = _update_contact(bot, sim, world)
    if contact is not None:
        forward, right = _relative_to_boat(bot, contact["x"], contact["z"])
        distance_m = math.hypot(forward, right) * simulation.UNIT_METERS_BOT
        age = max(0.0, now - float(contact["at"]))
        obs[14] = 1.0 if detected_now else 0.0
        obs[15] = _clip(forward / 300.0)
        obs[16] = _clip(right / 300.0)
        obs[17] = _ratio(distance_m / 5000.0)
        obs[18] = _ratio(age / CONTACT_MEMORY_S)
        obs[19] = _ratio(-float(contact.get("y", 0.0)) / 50.0)
        obs[20] = _ratio(float(contact.get("noise", 0.0)) / 20.0)

    obs[21:28] = _torpedo_observation(bot, sim, world)

    obs[28:36] = tuple(_ray_distances(bot, world))
    return obs


def _build_destroyer_v2_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Ajoute les stocks et le cooldown des mines à l'observation v1."""
    base = _build_destroyer_observation(bot, sim, world)
    obs = np.zeros(DESTROYER_OBS_DIM, dtype=np.float32)
    obs[:14] = base[:14]
    ammo = sim._legacy.mine_ammo.get(bot["sid"]) or {}
    boat = bot.get("boat") or {}
    obs[14] = _ammo_ratio(
        int(ammo.get("surface", 0)), int((boat.get("mineSurf") or {}).get("number", 0)))
    obs[15] = _ammo_ratio(
        int(ammo.get("bottom", 0)), int((boat.get("mineBottom") or {}).get("number", 0)))
    obs[16] = _ammo_ratio(
        int(ammo.get("suspended", 0)),
        int((boat.get("mineSuspended") or {}).get("number", 0)))
    obs[17] = 1.0 if sim.now() >= float(bot.get("next_mine_at", 0.0)) else 0.0
    obs[18:25] = base[14:21]
    obs[25:32] = base[21:28]
    obs[32:40] = base[28:36]
    return obs


def _build_destroyer_v3_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Ajoute plusieurs torpilles et leurres ; les mines ne sont plus controlables."""
    base = _build_destroyer_observation(bot, sim, world)
    obs = np.zeros(DESTROYER_V3_OBS_DIM, dtype=np.float32)
    obs[:DESTROYER_V3_TORPEDO_START] = base[:21]
    obs[DESTROYER_V3_TORPEDO_START:DESTROYER_V3_LURE_START] = (
        _destroyer_v3_torpedo_observation(bot, sim, world))
    obs[DESTROYER_V3_LURE_START:DESTROYER_V3_RAY_START] = (
        _destroyer_v3_lure_observation(bot, sim, world))
    obs[DESTROYER_V3_RAY_START:] = base[28:36]
    return obs


def _build_destroyer_v4_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Fige l'interface complete avec torpilles typees et grenades publiques."""
    base = _build_destroyer_observation(bot, sim, world)
    obs = np.zeros(DESTROYER_V4_OBS_DIM, dtype=np.float32)
    obs[:DESTROYER_V4_TORPEDO_START] = base[:DESTROYER_V4_TORPEDO_START]
    obs[DESTROYER_V4_TORPEDO_START:DESTROYER_V4_LURE_START] = (
        _typed_torpedo_observation(bot, sim, world))
    obs[DESTROYER_V4_LURE_START:DESTROYER_V4_GRENADE_START] = (
        _destroyer_v3_lure_observation(bot, sim, world))
    obs[DESTROYER_V4_GRENADE_START:DESTROYER_V4_RAY_START] = (
        _grenade_observation(bot, sim))
    obs[DESTROYER_V4_RAY_START:] = base[28:36]
    return obs


def _build_destroyer_v5_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Encode les relèvements du contact et des six torpilles typées."""
    base = _build_destroyer_observation(bot, sim, world)
    obs = np.zeros(DESTROYER_V5_OBS_DIM, dtype=np.float32)
    obs[0] = base[0]
    throttle_ratio = float(bot.get("control_target_speed_ratio", 0.0))
    obs[1] = _clip(throttle_ratio) if math.isfinite(throttle_ratio) else 0.0
    obs[2] = _yaw_rate_ratio(bot)
    obs[3:DESTROYER_V5_TORPEDO_START] = base[1:DESTROYER_V4_TORPEDO_START]
    _replace_contact_with_bearing(obs, DESTROYER_V5_CONTACT_START, bot)
    obs[DESTROYER_V5_TORPEDO_START:DESTROYER_V5_LURE_START] = (
        _directional_typed_torpedo_observation(bot, sim, world))
    obs[DESTROYER_V5_LURE_START:DESTROYER_V5_GRENADE_START] = (
        _directional_lure_observation(bot, sim, world))
    obs[DESTROYER_V5_GRENADE_START:DESTROYER_V5_RAY_START] = (
        _directional_grenade_observation(bot, sim))
    obs[DESTROYER_V5_RAY_START:DESTROYER_V5_WAYPOINT_START] = tuple(
        _ray_proximities(bot, world))
    obs[DESTROYER_V5_WAYPOINT_START:] = waypoint_observation(bot)
    return obs


def _build_destroyer_v6_observation(bot: Dict[str, Any], sim: simulation.Sim,
                                    world: Dict[str, Any]) -> np.ndarray:
    """Ajoute sept rayons longue portee sans exposer le chemin de reward."""
    base = _build_destroyer_v5_observation(bot, sim, world)
    obs = np.zeros(DESTROYER_V6_OBS_DIM, dtype=np.float32)
    obs[:DESTROYER_V6_LONG_RAY_START] = base[:DESTROYER_V5_WAYPOINT_START]
    obs[DESTROYER_V6_LONG_RAY_START:DESTROYER_V6_WAYPOINT_START] = tuple(
        _long_range_ray_proximities(bot, world))
    obs[DESTROYER_V6_WAYPOINT_START:] = base[DESTROYER_V5_WAYPOINT_START:]
    return obs


def build_observation(bot: Dict[str, Any], sim: simulation.Sim,
                      world: Dict[str, Any]) -> np.ndarray:
    """Construit l'observation correspondant à la coque contrôlée."""
    if bot.get("boatType") == "submarine":
        if bot.get("rl_control_version") == SUBMARINE_V4_OBSERVATION_VERSION:
            return _build_submarine_v4_observation(bot, sim, world)
        if bot.get("rl_control_version") == SUBMARINE_V3_OBSERVATION_VERSION:
            return _build_submarine_v3_observation(bot, sim, world)
        if bot.get("rl_control_version") == SUBMARINE_V2_OBSERVATION_VERSION:
            return _build_submarine_v2_observation(bot, sim, world)
        return _build_submarine_observation(bot, sim, world)
    if bot.get("boatType") == "destroyer":
        if bot.get("rl_control_version") == DESTROYER_V6_OBSERVATION_VERSION:
            return _build_destroyer_v6_observation(bot, sim, world)
        if bot.get("rl_control_version") == DESTROYER_V5_OBSERVATION_VERSION:
            return _build_destroyer_v5_observation(bot, sim, world)
        if bot.get("rl_control_version") == DESTROYER_V4_OBSERVATION_VERSION:
            return _build_destroyer_v4_observation(bot, sim, world)
        if bot.get("rl_control_version") == DESTROYER_V3_OBSERVATION_VERSION:
            return _build_destroyer_v3_observation(bot, sim, world)
        if bot.get("rl_control_version") == DESTROYER_OBSERVATION_VERSION:
            return _build_destroyer_v2_observation(bot, sim, world)
        return _build_destroyer_observation(bot, sim, world)
    raise ValueError(f"type de bateau RL inconnu: {bot.get('boatType')}")


def _contact_target(bot: Dict[str, Any], sim: simulation.Sim) -> Dict[str, Any] | None:
    contact = bot.get("rl_contact")
    if contact is None or sim.now() - float(contact.get("at", 0.0)) > CONTACT_FIRE_MAX_AGE_S:
        return None
    if sim.now() >= float(contact.get("active_detected_until", float("inf"))):
        return None
    return {"id": contact["id"], "sid": contact["sid"],
            "position": {axis: contact[axis] for axis in ("x", "y", "z")},
            "boat": dict(contact.get("boat") or {}), "observed_at": contact["at"],
            "tracked": bot.get("rl_contact_tracked", False)}


def _record_weapon_context(result: Dict[str, Any], bot: Dict[str, Any],
                           sim: simulation.Sim, target: Dict[str, Any] | None) -> None:
    """Decrit la solution de tir connue sans consulter un nouveau capteur."""
    result["weapon_had_acquisition"] = target is not None
    if target is None:
        return
    position = target["position"]
    forward, right = _relative_to_boat(bot, position["x"], position["z"])
    result["weapon_contact_age_s"] = max(0.0, sim.now() - float(target["observed_at"]))
    result["weapon_bearing_error_deg"] = abs(math.degrees(math.atan2(right, forward)))


def _apply_submarine_action(bot: Dict[str, Any], sim: simulation.Sim,
                            action: Sequence[int]) -> Dict[str, Any]:
    """Applique une macro-action discrète ; la physique reste gérée par ``Sim``."""
    values = np.asarray(action, dtype=np.int64).reshape(-1)
    if values.size != len(ACTION_NVECS):
        raise ValueError(f"action attendue: {len(ACTION_NVECS)} valeurs")
    if np.any(values < 0) or np.any(values >= ACTION_NVECS):
        raise ValueError(f"action hors limites: {values.tolist()}")

    rudder_i, throttle_i, depth_i, weapon_i, lure_i = (int(value) for value in values)
    bot["control_target_rudder"] = RUDDER_LEVELS[rudder_i]
    bot["control_target_speed_ratio"] = _throttle_target(bot, throttle_i)
    max_depth_m = float(bot.get("max_depth_m", 200.0))
    bot["control_target_depth_y"] = -(DEPTH_LEVELS[depth_i] * max_depth_m) / simulation.UNIT_METERS_BOT

    result = {
        "weapon_requested": weapon_i != 0,
        "weapon_fired": False,
        "weapon_invalid": False,
        "weapon_kind": None,
        "weapon_had_acquisition": None,
        "weapon_without_acquisition": False,
        "weapon_misaligned": False,
        "weapon_contact_age_s": None,
        "weapon_bearing_error_deg": None,
        "lure_requested": lure_i == 1,
        "lure_dropped": False,
        "lure_invalid": False,
        "lure_without_threat": False,
        "sonar_requested": False,
        "sonar_pinged": False,
        "sonar_invalid": False,
        "mine_requested": False,
        "mine_placed": False,
        "mine_invalid": False,
        "mine_kind": None,
    }
    now = sim.now()
    target = _contact_target(bot, sim) if weapon_i else None
    if weapon_i:
        _record_weapon_context(result, bot, sim, target)
    if weapon_i:
        if target is None or now < float(bot.get("next_torpedo_at", 0.0)):
            result["weapon_invalid"] = True
            result["weapon_without_acquisition"] = target is None
        elif weapon_i == 1:
            result["weapon_fired"] = sim.spawn_bot_torpedo(bot, target)
        else:
            distance_m = math.hypot(
                target["position"]["x"] - bot["position"]["x"],
                target["position"]["z"] - bot["position"]["z"],
            ) * simulation.UNIT_METERS_BOT
            activation_m = 500.0 if distance_m >= 1000.0 else 200.0
            result["weapon_fired"] = sim.spawn_bot_torpedo_autonomous(
                bot, target, activation_m=activation_m)
        if result["weapon_fired"]:
            result["weapon_kind"] = "acoustic" if weapon_i == 1 else "autonomous"
            result["weapon_without_acquisition"] = False
            spec = simulation.boat_torpedo_specs(bot.get("boat") or {}).get(
                result["weapon_kind"]) or {}
            result["weapon_misaligned"] = result["weapon_bearing_error_deg"] > (
                float(spec.get("radarConeDeg", 0.0)) / 2.0)
            bot["next_torpedo_at"] = now + 4.0
        else:
            result["weapon_invalid"] = True

    if lure_i:
        result["lure_without_threat"] = not bool(
            bot.get("rl_torpedo_detected", False))
        if now < float(bot.get("next_lure_at", 0.0)):
            result["lure_invalid"] = True
        else:
            result["lure_dropped"] = sim.bot_drop_lure(bot)
            if result["lure_dropped"]:
                bot["next_lure_at"] = now + 3.0
            else:
                result["lure_invalid"] = True
    bot["rl_last_action_result"] = result
    return result


def _apply_destroyer_action(bot: Dict[str, Any], sim: simulation.Sim,
                            action: Sequence[int]) -> Dict[str, Any]:
    """Applique les commandes, armes de surface et sonar du destroyer."""
    values = np.asarray(action, dtype=np.int64).reshape(-1)
    if values.size != len(DESTROYER_V1_ACTION_NVECS):
        raise ValueError(f"action attendue: {len(DESTROYER_V1_ACTION_NVECS)} valeurs")
    if np.any(values < 0) or np.any(values >= DESTROYER_V1_ACTION_NVECS):
        raise ValueError(f"action hors limites: {values.tolist()}")

    rudder_i, throttle_i, weapon_i, lure_i, sonar_i = (int(value) for value in values)
    bot["control_target_rudder"] = RUDDER_LEVELS[rudder_i]
    bot["control_target_speed_ratio"] = _throttle_target(bot, throttle_i)
    result = {
        "weapon_requested": weapon_i != 0,
        "weapon_fired": False,
        "weapon_invalid": False,
        "weapon_kind": None,
        "weapon_had_acquisition": None,
        "weapon_without_acquisition": False,
        "weapon_misaligned": False,
        "weapon_contact_age_s": None,
        "weapon_bearing_error_deg": None,
        "lure_requested": lure_i == 1,
        "lure_dropped": False,
        "lure_invalid": False,
        "lure_without_threat": False,
        "sonar_requested": sonar_i == 1,
        "sonar_pinged": False,
        "sonar_invalid": False,
        "mine_requested": False,
        "mine_placed": False,
        "mine_invalid": False,
        "mine_kind": None,
    }
    now = sim.now()
    target = _contact_target(bot, sim) if weapon_i else None
    if weapon_i:
        _record_weapon_context(result, bot, sim, target)

    if sonar_i:
        bb = bot.setdefault("bb", {})
        if now >= float(bb.get("next_sonar_ping_at", 0.0)):
            bb["next_sonar_ping_at"] = now + 30.0
            sim.bot_sonar_ping(bot, sim.world_data)
            result["sonar_pinged"] = True

    if weapon_i in (1, 2):
        if target is None:
            result["weapon_invalid"] = True
            result["weapon_without_acquisition"] = True
        elif now >= float(bot.get("next_torpedo_at", 0.0)):
            if weapon_i == 1:
                result["weapon_fired"] = sim.spawn_bot_torpedo(bot, target)
            else:
                distance_m = math.hypot(
                    target["position"]["x"] - bot["position"]["x"],
                    target["position"]["z"] - bot["position"]["z"],
                ) * simulation.UNIT_METERS_BOT
                activation_m = 500.0 if distance_m >= 1000.0 else 200.0
                result["weapon_fired"] = sim.spawn_bot_torpedo_autonomous(
                    bot, target, activation_m=activation_m)
            if result["weapon_fired"]:
                result["weapon_kind"] = "acoustic" if weapon_i == 1 else "autonomous"
                result["weapon_without_acquisition"] = False
                spec = simulation.boat_torpedo_specs(bot.get("boat") or {}).get(
                    result["weapon_kind"]) or {}
                result["weapon_misaligned"] = result["weapon_bearing_error_deg"] > (
                    float(spec.get("radarConeDeg", 0.0)) / 2.0)
                bot["next_torpedo_at"] = now + 4.0
            else:
                result["weapon_invalid"] = True
    elif weapon_i == 3:
        if now >= float(bot.get("next_cannon_at", 0.0)):
            target_y = float((target or {}).get("position", {}).get("y", 0.0))
            target_boat = (target or {}).get("boat") or {}
            target_surface_y = -target_boat.get("flotation", 2) / simulation.UNIT_METERS_BOT
            # Meme seuil que server.fire_cannon_intent, limite exacte incluse.
            if target is None or target_y < target_surface_y - 0.05:
                result["weapon_invalid"] = True
            else:
                result["weapon_fired"] = sim.bot_fire_cannon(bot, target)
                if result["weapon_fired"]:
                    result["weapon_kind"] = "cannon"
                    bot["next_cannon_at"] = now + 3.0
                else:
                    result["weapon_invalid"] = True
    elif weapon_i == 4:
        if now >= float(bot.get("next_grenade_at", 0.0)):
            if target is None:
                result["weapon_invalid"] = True
            else:
                ammo_before = int(sim._legacy.grenade_ammo.get(bot["sid"], 0))
                position = target.get("position") or {}
                sim.spawn_grenade(bot["sid"], sim.players[bot["sid"]], {
                    "targetX": position.get("x", bot["position"]["x"]),
                    "targetZ": position.get("z", bot["position"]["z"]),
                    "depthMeters": max(5.0, -float(position.get("y", 0.0)) * simulation.UNIT_METERS_BOT),
                })
                result["weapon_fired"] = int(
                    sim._legacy.grenade_ammo.get(bot["sid"], 0)) < ammo_before
                if result["weapon_fired"]:
                    result["weapon_kind"] = "grenade"
                    bot["next_grenade_at"] = now + 4.0
                else:
                    result["weapon_invalid"] = True

    if lure_i:
        result["lure_without_threat"] = not bool(
            bot.get("rl_torpedo_detected", False))
        if now < float(bot.get("next_lure_at", 0.0)):
            result["lure_invalid"] = True
        else:
            result["lure_dropped"] = sim.bot_drop_lure(bot)
            if result["lure_dropped"]:
                bot["next_lure_at"] = now + 3.0
            else:
                result["lure_invalid"] = True
    bot["rl_last_action_result"] = result
    return result


def _apply_destroyer_v2_action(bot: Dict[str, Any], sim: simulation.Sim,
                               action: Sequence[int]) -> Dict[str, Any]:
    """Ajoute la pose de mines secondaire aux commandes destroyer v1."""
    values = np.asarray(action, dtype=np.int64).reshape(-1)
    if values.size != len(DESTROYER_ACTION_NVECS):
        raise ValueError(f"action attendue: {len(DESTROYER_ACTION_NVECS)} valeurs")
    if np.any(values < 0) or np.any(values >= DESTROYER_ACTION_NVECS):
        raise ValueError(f"action hors limites: {values.tolist()}")
    result = _apply_destroyer_action(bot, sim, values[:5])
    mine_i = int(values[5])
    result["mine_requested"] = mine_i != 0
    if mine_i == 0 or int(values[2]) == 4:
        return result
    now = sim.now()
    if now < float(bot.get("next_mine_at", 0.0)):
        return result
    kind = ("surface", "bottom", "suspended")[mine_i - 1]
    contact = bot.get("rl_contact") or {}
    depth_m = max(
        5.0,
        -float(contact.get("y", -5.0)) * simulation.UNIT_METERS_BOT,
    )
    result["mine_kind"] = kind
    result["mine_placed"] = sim.place_mine(
        bot["sid"], sim.players[bot["sid"]], kind, depth_m)
    if result["mine_placed"]:
        bot["next_mine_at"] = now + 15.0
    else:
        result["mine_invalid"] = True
    bot["rl_last_action_result"] = result
    return result


def apply_action(bot: Dict[str, Any], sim: simulation.Sim,
                 action: Sequence[int]) -> Dict[str, Any]:
    """Applique une action adaptée au type de bateau contrôlé."""
    if bot.get("boatType") == "submarine":
        return _apply_submarine_action(bot, sim, action)
    if bot.get("boatType") == "destroyer":
        if bot.get("rl_control_version") == DESTROYER_OBSERVATION_VERSION:
            return _apply_destroyer_v2_action(bot, sim, action)
        return _apply_destroyer_action(bot, sim, action)
    raise ValueError(f"type de bateau RL inconnu: {bot.get('boatType')}")
