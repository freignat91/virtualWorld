"""Chargement paresseux et exécution des politiques RL dans le serveur live."""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Any, Dict

import numpy as np

import events

from rl.rl_control import apply_action, build_observation, control_spec, control_version_for_spaces
from rl.model_config import parse_model_spec


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = (BASE_DIR / "models_rl").resolve()
_MODEL_CACHE: Dict[Path, Any] = {}


def resolve_model_path(ai_name: str) -> Path:
    """Résout ``rl_<run>`` ou ``rl_<run>:<checkpoint>`` sans path traversal."""
    if not isinstance(ai_name, str) or not ai_name.startswith("rl_"):
        raise ValueError("le nom d'une politique doit commencer par rl_")
    run_name, checkpoint = parse_model_spec(ai_name[3:])
    run_dir = (MODELS_DIR / run_name).resolve()
    if run_dir != MODELS_DIR and MODELS_DIR not in run_dir.parents:
        raise ValueError("run RL hors de models_rl")
    if checkpoint:
        filename = checkpoint if checkpoint.endswith(".zip") else f"{checkpoint}.zip"
        candidates = (run_dir / filename, run_dir / "checkpoints" / filename)
    else:
        candidates = (run_dir / "best" / "best_model.zip", run_dir / "policy_final.zip")
    for candidate in candidates:
        candidate = candidate.resolve()
        if MODELS_DIR not in candidate.parents:
            raise ValueError("modele RL hors de models_rl")
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"aucun modèle trouvé pour {ai_name}: {candidates}")


def load_model(ai_name: str, boat_type: str = "submarine", trace_enabled: bool = False):
    path = resolve_model_path(ai_name)
    model = _MODEL_CACHE.get(path)
    if model is None:
        from sb3_contrib import RecurrentPPO

        contents = None
        if trace_enabled:
            try:
                contents = path.read_bytes()
            except Exception:
                logging.warning("[rl] model trace capture failed")
        model = RecurrentPPO.load(io.BytesIO(contents) if contents is not None else path,
                                  device="cpu")
        model._trace_model_id = path.relative_to(MODELS_DIR).as_posix()
        model._trace_model_sha256 = None
        if contents is not None:
            try:
                model._trace_model_sha256 = hashlib.sha256(contents).hexdigest()
            except Exception:
                logging.warning("[rl] model trace fingerprint failed")
    observation_dim = int((model.observation_space.shape or (0,))[0])
    model_nvec = tuple(int(value) for value in getattr(model.action_space, "nvec", ()))
    control_version_for_spaces(boat_type, observation_dim, model_nvec)
    _MODEL_CACHE[path] = model
    logging.info("[rl] modèle chargé: %s", path)
    return model


class RuntimeController:
    """Évalue la politique à 4 Hz pendant que la physique reste à 20 Hz."""

    def __init__(self, model, decision_interval_s: float = 0.25) -> None:
        self.model = model
        self.decision_interval_s = decision_interval_s
        self.next_decision_at = 0.0
        self.state = None
        self.episode_start = True

    def tick(self, bot: Dict[str, Any], sim, world: Dict[str, Any], dt: float) -> None:
        now = sim.now()
        if now < self.next_decision_at:
            return
        observation = build_observation(bot, sim, world)
        captured = None
        if sim.trace_rl_decisions:
            try:
                threat = bot.get("rl_visible_threat")
                captured = (observation.tolist(), None if threat is None else dict(threat),
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
                    control_version=control_spec(bot["boatType"], bot.get("rl_control_version"))[0],
                    decision_at=now, physics_dt=dt, simulation_step=sim.trace_step,
                    decision_interval_s=self.decision_interval_s, episode_start=captured[2],
                    observation=captured[0], action=np.asarray(action).reshape(-1).tolist(),
                    result=dict(result), visible_threat=captured[1],
                    model_id=getattr(self.model, "_trace_model_id", None),
                    model_sha256=getattr(self.model, "_trace_model_sha256", None)))
            except Exception:
                logging.warning("[rl] decision trace capture failed")


def attach_controller(bot: Dict[str, Any], ai_name: str, trace_enabled: bool = False) -> None:
    bot["ai_tree"] = None
    bot["external_control"] = True
    boat_type = bot.get("boatType", "submarine")
    model = load_model(ai_name, boat_type, trace_enabled=trace_enabled)
    observation_dim = int((model.observation_space.shape or (0,))[0])
    model_nvec = tuple(int(value) for value in getattr(model.action_space, "nvec", ()))
    bot["rl_control_version"] = control_version_for_spaces(
        boat_type, observation_dim, model_nvec)
    bot["rl_controller"] = RuntimeController(model)
    bot["control_target_rudder"] = 0.0
    bot["control_target_speed_ratio"] = 0.0
    bot["control_target_depth_y"] = bot["position"].get("y", 0.0)
