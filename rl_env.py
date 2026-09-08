"""Environnement Gymnasium pour les duels de bateaux RL."""

from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

import geometry
from headless import HeadlessRunner
from rl_control import (
    apply_action,
    build_observation,
    contact_detected_index,
    control_spec,
    control_version_for_spaces,
)


PHYSICS_DT = 0.05

DEFAULT_REWARD = {
    "win": 10.0,
    "loss": -10.0,
    "damage_dealt": 0.02,
    "damage_taken": -0.02,
    "decision_cost": -0.001,
    "weapon_fired": -0.02,
    "weapon_invalid": -0.005,
    "lure_dropped": -0.01,
    "lure_invalid": -0.002,
    "sonar_pinged": -0.01,
    "sonar_invalid": -0.002,
    "mine_placed": -0.05,
    "mine_invalid": -0.005,
    "new_contact": 0.01,
}


class SubmarineDuelEnv(gym.Env):
    """Duel 1v1 : un agent externe affronte un BT ou une politique gelée."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        map_name: str = "combats",
        agent_boat_type: str = "submarine",
        control_version: Optional[str] = None,
        opponent_ai: str = "autosub",
        opponent_ais: Optional[Sequence[str]] = None,
        opponents: Optional[Sequence[Dict[str, Any]]] = None,
        opponent_pool_dir: Optional[str] = None,
        self_play_probability: float = 0.0,
        fixed_opponent_pool_dir: Optional[str] = None,
        fixed_opponent_boat_type: str = "submarine",
        fixed_policy_probability: float = 0.0,
        max_physics_steps: int = 6000,
        frame_skip: int = 5,
        spawn_min_m: float = 600.0,
        spawn_max_m: float = 2000.0,
        curriculum_start_min_m: Optional[float] = None,
        curriculum_start_max_m: Optional[float] = None,
        curriculum_decisions: int = 0,
        reward: Optional[Dict[str, float]] = None,
        seed: int = 0,
    ) -> None:
        super().__init__()
        self.map_name = map_name
        self.agent_boat_type = agent_boat_type
        self.control_version, observation_dim, action_nvecs = control_spec(
            agent_boat_type, control_version)
        if opponents is None:
            names = tuple(opponent_ais or (opponent_ai,))
            opponents = tuple(
                {"boat_type": "submarine", "ai": name, "weight": 1.0}
                for name in names)
        normalized_opponents = []
        for opponent in opponents:
            if not isinstance(opponent, dict):
                raise ValueError("chaque adversaire doit être un objet")
            boat_type = opponent.get("boat_type")
            ai = opponent.get("ai")
            weight = float(opponent.get("weight", 1.0))
            if boat_type not in {"submarine", "destroyer"}:
                raise ValueError(f"type d'adversaire inconnu: {boat_type}")
            if not isinstance(ai, str) or not ai:
                raise ValueError("Behavior Tree adversaire absent")
            if not math.isfinite(weight) or weight <= 0.0:
                raise ValueError(f"poids adversaire invalide: {weight}")
            normalized_opponents.append({"boat_type": boat_type, "ai": ai, "weight": weight})
        if not normalized_opponents:
            raise ValueError("au moins un adversaire BT est requis")
        self.opponents = tuple(normalized_opponents)
        self._opponent_weights = tuple(item["weight"] for item in self.opponents)
        self.opponent_pool_dir = Path(opponent_pool_dir) if opponent_pool_dir else None
        self.self_play_probability = max(0.0, min(1.0, self_play_probability))
        self.fixed_opponent_pool_dir = (
            Path(fixed_opponent_pool_dir) if fixed_opponent_pool_dir else None)
        self.fixed_opponent_boat_type = fixed_opponent_boat_type
        control_spec(fixed_opponent_boat_type)
        self.fixed_policy_probability = max(0.0, min(1.0, fixed_policy_probability))
        if self.fixed_opponent_pool_dir is not None and not any(
                self.fixed_opponent_pool_dir.glob("*.zip")):
            raise ValueError(f"pool de politiques vide: {self.fixed_opponent_pool_dir}")
        self.max_physics_steps = max(1, int(max_physics_steps))
        self.frame_skip = max(1, int(frame_skip))
        self.spawn_min_m = float(spawn_min_m)
        self.spawn_max_m = float(spawn_max_m)
        self.curriculum_start_min_m = float(
            curriculum_start_min_m if curriculum_start_min_m is not None else spawn_min_m)
        self.curriculum_start_max_m = float(
            curriculum_start_max_m if curriculum_start_max_m is not None else spawn_max_m)
        self.curriculum_decisions = max(0, int(curriculum_decisions))
        self.reward_cfg = dict(DEFAULT_REWARD)
        if reward:
            unknown = set(reward) - set(DEFAULT_REWARD)
            if unknown:
                raise ValueError(f"récompenses inconnues: {sorted(unknown)}")
            self.reward_cfg.update({key: float(value) for key, value in reward.items()})
        self.base_seed = int(seed)
        self.action_space = spaces.MultiDiscrete(action_nvecs)
        self.observation_space = spaces.Box(
            -1.0, 1.0, shape=(observation_dim,), dtype=np.float32)
        self.runner = HeadlessRunner(map_name=map_name, seed=seed)
        self.agent_sid: Optional[str] = None
        self.opponent_sid: Optional[str] = None
        self._opponent_model = None
        self._opponent_control_version: Optional[str] = None
        self._opponent_state = None
        self._opponent_episode_start = True
        self._model_cache: OrderedDict[Path, Any] = OrderedDict()
        self._episode_index = 0
        self._physics_steps = 0
        self._total_decisions = 0
        self._previous_agent_hp = 100.0
        self._previous_opponent_hp = 100.0
        self._had_contact = False
        self._stats: Dict[str, int] = {}
        self._opponent_info: Dict[str, Any] = {}

    def _spawn_range(self) -> Tuple[float, float]:
        if self.curriculum_decisions <= 0:
            return self.spawn_min_m, self.spawn_max_m
        progress = min(1.0, self._total_decisions / self.curriculum_decisions)
        minimum = self.curriculum_start_min_m + progress * (
            self.spawn_min_m - self.curriculum_start_min_m)
        maximum = self.curriculum_start_max_m + progress * (
            self.spawn_max_m - self.curriculum_start_max_m)
        return minimum, maximum

    def _spawn_pair(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        minimum_m, maximum_m = self._spawn_range()
        world = self.runner.world
        half_w = world["ground"]["width"] / 2 - 5.0
        half_d = world["ground"]["depth"] / 2 - 5.0
        for _ in range(500):
            ax = self.runner.random.uniform(-half_w, half_w)
            az = self.runner.random.uniform(-half_d, half_d)
            if geometry.point_on_any_island(ax, az, world):
                continue
            angle = self.runner.random.uniform(0.0, math.tau)
            distance_u = self.runner.random.uniform(minimum_m, maximum_m) / 10.0
            ox = ax + math.cos(angle) * distance_u
            oz = az + math.sin(angle) * distance_u
            if abs(ox) > half_w or abs(oz) > half_d:
                continue
            if geometry.point_on_any_island(ox, oz, world):
                continue
            return (ax, az), (ox, oz)
        raise RuntimeError("impossible de trouver deux positions de duel valides")

    @staticmethod
    def _pool_paths(directory: Optional[Path]) -> Sequence[Path]:
        if directory is None or not directory.exists():
            return ()
        return tuple(
            path for path in sorted(directory.glob("*.zip"))
            if not path.name.startswith(".")
        )

    def _load_opponent(self, path: Path, boat_type: str):
        cached = self._model_cache.get(path)
        if cached is None:
            from sb3_contrib import RecurrentPPO

            cached = RecurrentPPO.load(path, device="cpu")
            self._model_cache[path] = cached
            while len(self._model_cache) > 3:
                self._model_cache.popitem(last=False)
        else:
            self._model_cache.move_to_end(path)
        observation_dim = int((cached.observation_space.shape or (0,))[0])
        nvec = tuple(int(value) for value in getattr(cached.action_space, "nvec", ()))
        version = control_version_for_spaces(boat_type, observation_dim, nvec)
        return cached, version

    def reset(self, *, seed: Optional[int] = None,
              options: Optional[Dict[str, Any]] = None):
        super().reset(seed=seed)
        if seed is None:
            seed = self.base_seed + self._episode_index
        self._episode_index += 1
        self.runner.reset(seed=seed)
        self._physics_steps = 0
        self._opponent_model = None
        self._opponent_control_version = None
        self._opponent_state = None
        self._opponent_episode_start = True
        self._stats = {
            "weapons": 0, "invalid_weapons": 0,
            "lures": 0, "sonars": 0, "invalid_sonars": 0, "contacts": 0,
            "acoustic_torpedoes": 0, "autonomous_torpedoes": 0,
            "cannon_shots": 0, "grenades": 0,
            "mines": 0, "invalid_mines": 0,
            "surface_mines": 0, "bottom_mines": 0, "suspended_mines": 0,
        }
        agent_pos, opponent_pos = self._spawn_pair()

        pool = self._pool_paths(self.opponent_pool_dir)
        fixed_pool = self._pool_paths(self.fixed_opponent_pool_dir)
        use_self_play = bool(pool) and self.runner.random.random() < self.self_play_probability
        if use_self_play:
            path = self.runner.random.choice(pool)
            opponent_boat_type = self.agent_boat_type
            self._opponent_model, self._opponent_control_version = self._load_opponent(
                path, opponent_boat_type)
            opponent_external = True
            opponent_ai = None
            self._opponent_info = {
                "opponent": f"policy:{opponent_boat_type}/{path.name}",
                "opponent_kind": "policy",
                "opponent_boat_type": opponent_boat_type,
                "opponent_ai": None,
            }
        elif (fixed_pool
              and self.runner.random.random() < self.fixed_policy_probability):
            path = self.runner.random.choice(fixed_pool)
            opponent_boat_type = self.fixed_opponent_boat_type
            self._opponent_model, self._opponent_control_version = self._load_opponent(
                path, opponent_boat_type)
            opponent_external = True
            opponent_ai = None
            self._opponent_info = {
                "opponent": f"policy:{opponent_boat_type}/{path.name}",
                "opponent_kind": "policy",
                "opponent_boat_type": opponent_boat_type,
                "opponent_ai": None,
            }
        else:
            opponent_external = False
            opponent = self.runner.random.choices(
                self.opponents, weights=self._opponent_weights, k=1)[0]
            opponent_boat_type = opponent["boat_type"]
            opponent_ai = opponent["ai"]
            self._opponent_info = {
                "opponent": f"bt:{opponent_boat_type}/{opponent_ai}",
                "opponent_kind": "bt",
                "opponent_boat_type": opponent_boat_type,
                "opponent_ai": opponent_ai,
            }

        self.agent_sid = self.runner.spawn_bot(
            boat_type=self.agent_boat_type, external_control=True, ai=None, position=agent_pos,
            rotation=self.runner.random.uniform(0.0, math.tau), team_id="agent")
        self.opponent_sid = self.runner.spawn_bot(
            boat_type=opponent_boat_type, external_control=opponent_external,
            ai=opponent_ai, position=opponent_pos,
            rotation=self.runner.random.uniform(0.0, math.tau), team_id="opponent")
        self._agent()["rl_control_version"] = self.control_version
        if self._opponent_control_version is not None:
            self._opponent()["rl_control_version"] = self._opponent_control_version
        self._previous_agent_hp = 100.0
        self._previous_opponent_hp = 100.0
        observation = build_observation(self._agent(), self.runner.sim, self.runner.world)
        self._had_contact = bool(observation[
            contact_detected_index(self.agent_boat_type, self.control_version)] > 0.5)
        return observation, dict(self._opponent_info)

    def _agent(self) -> Dict[str, Any]:
        if self.agent_sid is None or self.agent_sid not in self.runner.legacy.bots:
            raise RuntimeError("agent absent")
        return self.runner.legacy.bots[self.agent_sid]

    def _opponent(self) -> Dict[str, Any]:
        if self.opponent_sid is None or self.opponent_sid not in self.runner.legacy.bots:
            raise RuntimeError("adversaire absent")
        return self.runner.legacy.bots[self.opponent_sid]

    def _predict_opponent(self) -> None:
        if self._opponent_model is None:
            return
        opponent = self._opponent()
        observation = build_observation(opponent, self.runner.sim, self.runner.world)
        action, self._opponent_state = self._opponent_model.predict(
            observation,
            state=self._opponent_state,
            episode_start=np.array([self._opponent_episode_start], dtype=bool),
            deterministic=True,
        )
        self._opponent_episode_start = False
        apply_action(opponent, self.runner.sim, action)

    def step(self, action):
        agent = self._agent()
        result = apply_action(agent, self.runner.sim, action)
        self._predict_opponent()
        if result["weapon_fired"]:
            self._stats["weapons"] += 1
            weapon_kind = result.get("weapon_kind")
            weapon_stat = {
                "acoustic": "acoustic_torpedoes",
                "autonomous": "autonomous_torpedoes",
                "cannon": "cannon_shots",
                "grenade": "grenades",
            }.get(weapon_kind)
            if weapon_stat:
                self._stats[weapon_stat] += 1
        if result["weapon_invalid"]:
            self._stats["invalid_weapons"] += 1
        if result["lure_dropped"]:
            self._stats["lures"] += 1
        if result["sonar_pinged"]:
            self._stats["sonars"] += 1
        if result["sonar_invalid"]:
            self._stats["invalid_sonars"] += 1
        if result["mine_placed"]:
            self._stats["mines"] += 1
            self._stats[f"{result['mine_kind']}_mines"] += 1
        if result["mine_invalid"]:
            self._stats["invalid_mines"] += 1

        for _ in range(self.frame_skip):
            self.runner.step(PHYSICS_DT)
            self._physics_steps += 1
            self.runner.sim.drain_events()
            if self.agent_sid not in self.runner.legacy.bots or self.opponent_sid not in self.runner.legacy.bots:
                break
        self._total_decisions += 1

        agent_alive = self.agent_sid in self.runner.legacy.bots
        opponent_alive = self.opponent_sid in self.runner.legacy.bots
        agent_hp = float(self.runner.legacy.bots[self.agent_sid]["integrity"]) if agent_alive else 0.0
        opponent_hp = float(self.runner.legacy.bots[self.opponent_sid]["integrity"]) if opponent_alive else 0.0
        reward = self.reward_cfg["decision_cost"]
        reward += max(0.0, self._previous_opponent_hp - opponent_hp) * self.reward_cfg["damage_dealt"]
        reward += max(0.0, self._previous_agent_hp - agent_hp) * self.reward_cfg["damage_taken"]
        reward += self.reward_cfg["weapon_fired"] if result["weapon_fired"] else 0.0
        reward += self.reward_cfg["weapon_invalid"] if result["weapon_invalid"] else 0.0
        reward += self.reward_cfg["lure_dropped"] if result["lure_dropped"] else 0.0
        reward += self.reward_cfg["lure_invalid"] if result["lure_invalid"] else 0.0
        reward += self.reward_cfg["sonar_pinged"] if result["sonar_pinged"] else 0.0
        reward += self.reward_cfg["sonar_invalid"] if result["sonar_invalid"] else 0.0
        reward += self.reward_cfg["mine_placed"] if result["mine_placed"] else 0.0
        reward += self.reward_cfg["mine_invalid"] if result["mine_invalid"] else 0.0
        self._previous_agent_hp = agent_hp
        self._previous_opponent_hp = opponent_hp

        terminated = not agent_alive or not opponent_alive
        truncated = not terminated and self._physics_steps >= self.max_physics_steps
        if agent_alive:
            observation = build_observation(self.runner.legacy.bots[self.agent_sid], self.runner.sim, self.runner.world)
        else:
            observation = np.zeros(self.observation_space.shape, dtype=np.float32)
        has_contact = bool(observation[
            contact_detected_index(self.agent_boat_type, self.control_version)] > 0.5)
        if has_contact and not self._had_contact:
            reward += self.reward_cfg["new_contact"]
            self._stats["contacts"] += 1
        self._had_contact = has_contact

        info: Dict[str, Any] = dict(self._opponent_info)
        if terminated:
            if agent_alive and not opponent_alive:
                reward += self.reward_cfg["win"]
                info["outcome"] = "win"
                info["is_success"] = True
            elif opponent_alive and not agent_alive:
                reward += self.reward_cfg["loss"]
                info["outcome"] = "loss"
                info["is_success"] = False
            else:
                info["outcome"] = "draw"
                info["is_success"] = False
        elif truncated:
            info["outcome"] = "draw"
            info["is_success"] = False
        if terminated or truncated:
            info.update(self._stats)
            info["agent_hp"] = agent_hp
            info["opponent_hp"] = opponent_hp
            info["physics_steps"] = self._physics_steps
        return observation, float(reward), terminated, truncated, info

    def close(self) -> None:
        self._model_cache.clear()
