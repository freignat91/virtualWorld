"""Interface stable entre une politique RL et la simulation autoritaire."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Sequence, Tuple

import numpy as np

import geometry
import simulation


SUBMARINE_OBSERVATION_VERSION = "sub_duel_v1"
SUBMARINE_OBS_DIM = 32
SUBMARINE_ACTION_NVECS = np.array([5, 5, 5, 3, 2], dtype=np.int64)
DESTROYER_V1_OBSERVATION_VERSION = "destroyer_duel_v1"
DESTROYER_V1_OBS_DIM = 36
DESTROYER_V1_ACTION_NVECS = np.array([5, 5, 5, 2, 2], dtype=np.int64)
DESTROYER_OBSERVATION_VERSION = "destroyer_duel_v2"
DESTROYER_OBS_DIM = 40
DESTROYER_ACTION_NVECS = np.array([5, 5, 5, 2, 2, 4], dtype=np.int64)

# Alias conservés pour les checkpoints sous-marins existants.
OBSERVATION_VERSION = SUBMARINE_OBSERVATION_VERSION
OBS_DIM = SUBMARINE_OBS_DIM
ACTION_NVECS = SUBMARINE_ACTION_NVECS
CONTACT_MEMORY_S = 30.0
CONTACT_FIRE_MAX_AGE_S = 1.0
RAY_MAX_M = 1000.0
RAY_DIRECTIONS_DEG = (0, 45, 90, 135, 180, 225, 270, 315)

RUDDER_LEVELS = (-1.0, -0.5, 0.0, 0.5, 1.0)
THROTTLE_LEVELS = (-0.35, 0.0, 0.35, 0.65, 1.0)
DEPTH_LEVELS = (0.01, 0.08, 0.25, 0.45, 0.70)


def control_spec(boat_type: str, version: str | None = None) -> Tuple[str, int, np.ndarray]:
    """Retourne la version et les espaces propres au type de bateau."""
    if boat_type == "submarine":
        if version not in (None, SUBMARINE_OBSERVATION_VERSION):
            raise ValueError(f"version de contrôle incompatible avec {boat_type}: {version}")
        return SUBMARINE_OBSERVATION_VERSION, SUBMARINE_OBS_DIM, SUBMARINE_ACTION_NVECS
    if boat_type == "destroyer":
        if version in (None, DESTROYER_V1_OBSERVATION_VERSION):
            return DESTROYER_V1_OBSERVATION_VERSION, DESTROYER_V1_OBS_DIM, DESTROYER_V1_ACTION_NVECS
        if version == DESTROYER_OBSERVATION_VERSION:
            return DESTROYER_OBSERVATION_VERSION, DESTROYER_OBS_DIM, DESTROYER_ACTION_NVECS
        raise ValueError(f"version de contrôle incompatible avec {boat_type}: {version}")
    raise ValueError(f"type de bateau RL inconnu: {boat_type}")


def control_version_for_spaces(boat_type: str, observation_dim: int,
                               action_nvecs: Sequence[int]) -> str:
    """Identifie une interface de contrôle à partir des espaces du modèle."""
    versions = (SUBMARINE_OBSERVATION_VERSION,) if boat_type == "submarine" else (
        DESTROYER_V1_OBSERVATION_VERSION, DESTROYER_OBSERVATION_VERSION)
    actual_nvecs = tuple(int(value) for value in action_nvecs)
    for version in versions:
        _, expected_dim, expected_nvecs = control_spec(boat_type, version)
        if observation_dim == expected_dim and actual_nvecs == tuple(expected_nvecs):
            return version
    raise ValueError(f"espaces RL incompatibles avec {boat_type}")


def contact_detected_index(boat_type: str, version: str | None = None) -> int:
    """Retourne l'indice du contact frais dans l'observation."""
    if boat_type == "submarine":
        return 10
    return 18 if version == DESTROYER_OBSERVATION_VERSION else 14


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
    active_until = contact.get("active_detected_until")
    return contact, active_until is not None and now <= float(active_until)


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
    obs[2] = _clip(float(bot.get("integrity", 100.0)) / 100.0, 0.0, 1.0)
    obs[3] = _clip(emitted_noise / max(1.0, float(boat.get("noise", 100.0))), 0.0, 1.0)
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
        obs[17] = _clip(distance_m / 5000.0, 0.0, 1.0)
        obs[18] = _clip(age / CONTACT_MEMORY_S, 0.0, 1.0)
        obs[19] = _clip(-float(contact.get("y", 0.0)) / 50.0, 0.0, 1.0)
        obs[20] = _clip(float(contact.get("noise", 0.0)) / 20.0, 0.0, 1.0)

    threats = sim.bot_torpedoes_threat(bot)
    if threats:
        threat = threats[0]
        forward, right = _relative_to_boat(bot, float(threat["x"]), float(threat["z"]))
        obs[21] = 1.0
        obs[22] = _clip(forward / 200.0)
        obs[23] = _clip(right / 200.0)
        obs[24] = _clip(float(threat.get("eta_s", 10.0)) / 10.0, 0.0, 1.0)
        obs[25] = 1.0 if any(
            item.get("tid") == threat.get("tid") and item.get("acquiredBoatId") == bot.get("id")
            for item in sim.torpedoes.values()) else 0.0
        obs[26] = 1.0 if threat.get("kind") == "acoustic" else -1.0
        obs[27] = _clip(float(threat.get("dist_m", 2000.0)) / 2000.0, 0.0, 1.0)

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


def build_observation(bot: Dict[str, Any], sim: simulation.Sim,
                      world: Dict[str, Any]) -> np.ndarray:
    """Construit l'observation correspondant à la coque contrôlée."""
    if bot.get("boatType") == "submarine":
        return _build_submarine_observation(bot, sim, world)
    if bot.get("boatType") == "destroyer":
        if bot.get("rl_control_version") == DESTROYER_OBSERVATION_VERSION:
            return _build_destroyer_v2_observation(bot, sim, world)
        return _build_destroyer_observation(bot, sim, world)
    raise ValueError(f"type de bateau RL inconnu: {bot.get('boatType')}")


def _contact_target(bot: Dict[str, Any], sim: simulation.Sim) -> Dict[str, Any] | None:
    contact = bot.get("rl_contact")
    if contact is None or sim.now() - float(contact.get("at", 0.0)) > CONTACT_FIRE_MAX_AGE_S:
        return None
    target_id = contact.get("id")
    for player in sim.players.values():
        if player.get("id") == target_id and not player.get("sunk"):
            return player
    return None


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
    bot["control_target_speed_ratio"] = THROTTLE_LEVELS[throttle_i]
    max_depth_m = float(bot.get("max_depth_m", 200.0))
    bot["control_target_depth_y"] = -(DEPTH_LEVELS[depth_i] * max_depth_m) / simulation.UNIT_METERS_BOT

    result = {
        "weapon_requested": weapon_i != 0,
        "weapon_fired": False,
        "weapon_invalid": False,
        "weapon_kind": None,
        "lure_requested": lure_i == 1,
        "lure_dropped": False,
        "lure_invalid": False,
        "sonar_requested": False,
        "sonar_pinged": False,
        "sonar_invalid": False,
        "mine_requested": False,
        "mine_placed": False,
        "mine_invalid": False,
        "mine_kind": None,
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
            result["weapon_kind"] = "acoustic" if weapon_i == 1 else "autonomous"
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


def _remember_active_contact(bot: Dict[str, Any], sim: simulation.Sim,
                             detected: Sequence[Dict[str, Any]]) -> None:
    """Mémorise le contact actif le plus proche sans exposer les autres cibles."""
    if not detected:
        return
    nearest = min(detected, key=lambda item: float(item.get("dist_m", float("inf"))))
    target = next(
        (player for player in sim.players.values() if player.get("id") == nearest.get("id")),
        None,
    )
    position = (target or {}).get("position") or nearest
    now = sim.now()
    bot["rl_contact"] = {
        "id": nearest["id"],
        "sid": (target or {}).get("sid"),
        "x": float(nearest["x"]),
        "y": float(position.get("y", 0.0)),
        "z": float(nearest["z"]),
        "at": now,
        "noise": 0.0,
        "active_detected_until": now + 0.25,
    }


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
    bot["control_target_speed_ratio"] = THROTTLE_LEVELS[throttle_i]
    result = {
        "weapon_requested": weapon_i != 0,
        "weapon_fired": False,
        "weapon_invalid": False,
        "weapon_kind": None,
        "lure_requested": lure_i == 1,
        "lure_dropped": False,
        "lure_invalid": False,
        "sonar_requested": sonar_i == 1,
        "sonar_pinged": False,
        "sonar_invalid": False,
        "mine_requested": False,
        "mine_placed": False,
        "mine_invalid": False,
        "mine_kind": None,
    }
    now = sim.now()

    if sonar_i:
        bb = bot.setdefault("bb", {})
        if now >= float(bb.get("next_sonar_ping_at", 0.0)):
            bb["next_sonar_ping_at"] = now + 30.0
            _remember_active_contact(bot, sim, sim.bot_sonar_ping(bot, sim.world_data))
            result["sonar_pinged"] = True

    if weapon_i in (1, 2):
        if now >= float(bot.get("next_torpedo_at", 0.0)):
            target = _contact_target(bot, sim)
            if target is None:
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
                result["weapon_kind"] = "acoustic" if weapon_i == 1 else "autonomous"
                bot["next_torpedo_at"] = now + 4.0
            else:
                result["weapon_invalid"] = True
    elif weapon_i == 3:
        if now >= float(bot.get("next_cannon_at", 0.0)):
            target = _contact_target(bot, sim)
            target_y = float((target or {}).get("position", {}).get("y", 0.0))
            if target is None or target_y < -0.6:
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
            target = _contact_target(bot, sim)
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
