"""Interface stable entre une politique RL et la simulation autoritaire."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Sequence, Tuple

import numpy as np

import geometry
import simulation


OBSERVATION_VERSION = "sub_duel_v1"
OBS_DIM = 32
ACTION_NVECS = np.array([5, 5, 5, 3, 2], dtype=np.int64)
CONTACT_MEMORY_S = 30.0
CONTACT_FIRE_MAX_AGE_S = 1.0
RAY_MAX_M = 1000.0
RAY_DIRECTIONS_DEG = (0, 45, 90, 135, 180, 225, 270, 315)

RUDDER_LEVELS = (-1.0, -0.5, 0.0, 0.5, 1.0)
THROTTLE_LEVELS = (-0.35, 0.0, 0.35, 0.65, 1.0)
DEPTH_LEVELS = (0.01, 0.08, 0.25, 0.45, 0.70)


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


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
    return _clip(current / max(1, maximum), 0.0, 1.0)


def _update_contact(bot: Dict[str, Any], sim: simulation.Sim,
                    world: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, bool]:
    now = sim.now()
    detected = sim.detect_enemies_passive(bot, world)
    if detected:
        nearest = min(detected, key=lambda item: float(item.get("dist_m", float("inf"))))
        contact = {
            "id": nearest["id"], "sid": nearest["sid"],
            "x": float(nearest["x"]), "y": float(nearest.get("y", 0.0)),
            "z": float(nearest["z"]), "at": now,
            "noise": float(nearest.get("noise_perceived", 0.0)),
        }
        bot["rl_contact"] = contact
        return contact, True
    contact = bot.get("rl_contact")
    if contact is None or now - float(contact.get("at", 0.0)) > CONTACT_MEMORY_S:
        bot.pop("rl_contact", None)
        return None, False
    return contact, False


def _ray_distances(bot: Dict[str, Any], world: Dict[str, Any]) -> Iterable[float]:
    ray_max_u = RAY_MAX_M / simulation.UNIT_METERS_BOT
    step_u = 5.0
    x = float(bot["position"]["x"])
    z = float(bot["position"]["z"])
    rotation = float(bot.get("rotation", 0.0))
    half_w = world["ground"]["width"] / 2 - 4.0
    half_d = world["ground"]["depth"] / 2 - 4.0
    for degrees in RAY_DIRECTIONS_DEG:
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
        yield _clip(distance / ray_max_u, 0.0, 1.0)


def build_observation(bot: Dict[str, Any], sim: simulation.Sim,
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
    obs[1] = _clip(-float(bot["position"].get("y", 0.0)) / max_depth_u, 0.0, 1.0)
    obs[2] = _clip(float(bot.get("rudder", 0.0)) / rudder_max)
    obs[3] = _clip(float(bot.get("integrity", 100.0)) / 100.0, 0.0, 1.0)
    obs[4] = _ammo_ratio(int(ammo.get("acoustic", 0)), max_acoustic)
    obs[5] = _ammo_ratio(int(ammo.get("autonomous", 0)), max_autonomous)
    obs[6] = _ammo_ratio(int(sim._legacy.lure_ammo.get(sid, 0)), max_lures)
    obs[7] = 1.0 if sim.now() >= float(bot.get("next_torpedo_at", 0.0)) else 0.0
    obs[8] = 1.0 if sim.now() >= float(bot.get("next_lure_at", 0.0)) else 0.0
    obs[9] = _clip(emitted_noise / max(1.0, float(boat.get("noise", 100.0))), 0.0, 1.0)

    contact, detected_now = _update_contact(bot, sim, world)
    if contact is not None:
        forward, right = _relative_to_boat(bot, contact["x"], contact["z"])
        distance_m = math.hypot(forward, right) * simulation.UNIT_METERS_BOT
        age = max(0.0, sim.now() - float(contact["at"]))
        obs[10] = 1.0 if detected_now else 0.0
        obs[11] = _clip(forward / 300.0)
        obs[12] = _clip(right / 300.0)
        obs[13] = _clip(distance_m / 5000.0, 0.0, 1.0)
        obs[14] = _clip(age / CONTACT_MEMORY_S, 0.0, 1.0)
        obs[15] = _clip(-float(contact.get("y", 0.0)) / max_depth_u, 0.0, 1.0)
        obs[16] = _clip(float(contact.get("noise", 0.0)) / 20.0, 0.0, 1.0)

    threats = sim.bot_torpedoes_threat(bot)
    if threats:
        threat = threats[0]
        forward, right = _relative_to_boat(bot, float(threat["x"]), float(threat["z"]))
        obs[17] = 1.0
        obs[18] = _clip(forward / 200.0)
        obs[19] = _clip(right / 200.0)
        obs[20] = _clip(float(threat.get("eta_s", 10.0)) / 10.0, 0.0, 1.0)
        obs[21] = 1.0 if any(
            t.get("tid") == threat.get("tid") and t.get("acquiredBoatId") == bot.get("id")
            for t in sim.torpedoes.values()) else 0.0
        obs[22] = 1.0 if threat.get("kind") == "acoustic" else -1.0
        obs[23] = _clip(float(threat.get("dist_m", 2000.0)) / 2000.0, 0.0, 1.0)

    obs[24:32] = tuple(_ray_distances(bot, world))
    return obs


def _contact_target(bot: Dict[str, Any], sim: simulation.Sim) -> Dict[str, Any] | None:
    contact = bot.get("rl_contact")
    if contact is None or sim.now() - float(contact.get("at", 0.0)) > CONTACT_FIRE_MAX_AGE_S:
        return None
    target_id = contact.get("id")
    for player in sim.players.values():
        if player.get("id") == target_id and not player.get("sunk"):
            return player
    return None


def apply_action(bot: Dict[str, Any], sim: simulation.Sim,
                 action: Sequence[int]) -> Dict[str, Any]:
    """Applique une macro-action discrète ; la physique reste gérée par ``Sim``."""
    values = np.asarray(action, dtype=np.int64).reshape(-1)
    if values.size != len(ACTION_NVECS):
        raise ValueError(f"action attendue: {len(ACTION_NVECS)} valeurs")
    if np.any(values < 0) or np.any(values >= ACTION_NVECS):
        raise ValueError(f"action hors limites: {values.tolist()}")

    rudder_i, throttle_i, depth_i, weapon_i, lure_i = (int(value) for value in values)
    bot["control_target_rudder"] = RUDDER_LEVELS[rudder_i]
    bot["control_target_speed_ratio"] = THROTTLE_LEVELS[throttle_i]
    max_depth_m = float(bot.get("max_depth_m", 200.0))
    bot["control_target_depth_y"] = -(DEPTH_LEVELS[depth_i] * max_depth_m) / simulation.UNIT_METERS_BOT

    result = {
        "weapon_requested": weapon_i != 0,
        "weapon_fired": False,
        "weapon_invalid": False,
        "lure_requested": lure_i == 1,
        "lure_dropped": False,
        "lure_invalid": False,
    }
    now = sim.now()
    if weapon_i:
        target = _contact_target(bot, sim)
        if target is None or now < float(bot.get("next_torpedo_at", 0.0)):
            result["weapon_invalid"] = True
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
            bot["next_torpedo_at"] = now + 4.0
        else:
            result["weapon_invalid"] = True

    if lure_i:
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
