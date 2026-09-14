"""Chargement paresseux et exécution des politiques RL dans le serveur live."""

from __future__ import annotations

import hashlib
import io
import logging
import random
import zlib
from pathlib import Path
from typing import Any, Dict

import numpy as np

import events

from rl.rl_control import apply_action, build_observation, control_spec, control_version_for_spaces
from rl.model_config import parse_model_spec
from rl.waypoints import (
    RLWaypointManager,
    WAYPOINT_CONTROL_VERSIONS,
    waypoint_reached,
)


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = (BASE_DIR / "models_rl").resolve()
_MODEL_CACHE: Dict[Path, Any] = {}
_V15_MODELS = frozenset({
    "aisub_mobility_runtime_v15",
    "aidest_mobility_runtime_v15",
})
_V16_MODELS = frozenset({
    "aisub_mobility_runtime_v16",
    "aidest_mobility_runtime_v16",
})
_V17_MODELS = frozenset({
    "aisub_mobility_runtime_v17",
    "aidest_mobility_runtime_v17",
})


def _runtime_for_ai(ai_name: str):
    """Selectionne uniquement le runtime fige associe a un alias promu."""
    run_name, _ = parse_model_spec(ai_name[3:])
    if run_name in _V15_MODELS:
        from rl.bot_versions.v15 import runtime

        return runtime
    if run_name in _V16_MODELS:
        from rl.bot_versions.v16 import runtime

        return runtime
    if run_name in _V17_MODELS:
        from rl.bot_versions.v17 import runtime

        return runtime
    return None


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
    runtime = _runtime_for_ai(ai_name)
    model = _MODEL_CACHE.get(path)
    if model is None:
        from sb3_contrib import RecurrentPPO

        contents = None
        if trace_enabled:
            try:
                contents = path.read_bytes()
            except Exception:
                logging.warning("[rl] model trace capture failed")
        model = RecurrentPPO.load(
            io.BytesIO(contents) if contents is not None else path,
            device="cpu",
            custom_objects=(runtime.model_custom_objects() if runtime else None),
        )
        model._trace_model_id = path.relative_to(MODELS_DIR).as_posix()
        model._trace_model_sha256 = None
        if contents is not None:
            try:
                model._trace_model_sha256 = hashlib.sha256(contents).hexdigest()
            except Exception:
                logging.warning("[rl] model trace fingerprint failed")
    if runtime:
        runtime.configure_model(model, boat_type)
    else:
        observation_dim = int((model.observation_space.shape or (0,))[0])
        model_nvec = tuple(int(value) for value in getattr(model.action_space, "nvec", ()))
        declared_version = getattr(model, "rl_control_version", None)
        model.rl_control_version = control_version_for_spaces(
            boat_type, observation_dim, model_nvec, declared_version)
        if model.rl_control_version in {
                "sub_duel_v3", "sub_duel_v4", "destroyer_duel_v5", "destroyer_duel_v6"}:
            from rl.masked_recurrent_policy import SituationMaskedMlpLstmPolicy

            if not isinstance(model.policy, SituationMaskedMlpLstmPolicy):
                raise ValueError(
                    f"politique sans masque pour {model.rl_control_version}")
    _MODEL_CACHE[path] = model
    logging.info("[rl] modèle chargé: %s", path)
    return model


class RuntimeController:
    """Évalue la politique à 4 Hz pendant que la physique reste à 20 Hz."""

    def __init__(self, model, decision_interval_s: float = 0.25,
                 waypoint_seed: int = 0) -> None:
        self.model = model
        self.decision_interval_s = decision_interval_s
        self.next_decision_at = 0.0
        self.state = None
        self.episode_start = True
        self.waypoints = RLWaypointManager(random.Random(waypoint_seed))
        self.uses_waypoints = (
            getattr(model, "rl_control_version", None) in WAYPOINT_CONTROL_VERSIONS)

    @property
    def destination_clearance_m(self) -> float:
        from rl.navigable_path import DESTINATION_CLEARANCE_M

        return DESTINATION_CLEARANCE_M

    @property
    def final_waypoint_radius_m(self) -> float:
        from rl.waypoints import WAYPOINT_FINAL_REACHED_RADIUS_M

        return WAYPOINT_FINAL_REACHED_RADIUS_M

    @property
    def intermediate_waypoint_radius_m(self) -> float:
        from rl.waypoints import WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M

        return WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M

    @staticmethod
    def create_route_planner(world: Dict[str, Any]):
        from rl.navigable_path import (
            DESTINATION_CLEARANCE_M,
            NavigablePathMetric,
            ROUTE_CLEARANCE_M,
            ROUTE_NODE_MARGIN_M,
        )

        return NavigablePathMetric(
            world, clearance_m=ROUTE_CLEARANCE_M,
            endpoint_clearance_m=DESTINATION_CLEARANCE_M,
            node_margin_m=ROUTE_NODE_MARGIN_M)

    @staticmethod
    def plan_route(world: Dict[str, Any], start, goal, planner=None):
        from rl.navigable_path import plan_segmented_route

        return plan_segmented_route(world, start, goal, planner=planner)

    def ensure_waypoint(self, bot: Dict[str, Any], world: Dict[str, Any]) -> bool:
        return self.waypoints.ensure(bot, world)

    @staticmethod
    def _pause_for_checkpoint(bot: Dict[str, Any]) -> None:
        """Immobilise une politique sans checkpoint manuel actif."""
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
        if bot.get("rl_control_version") in WAYPOINT_CONTROL_VERSIONS:
            if bot.get("rl_manual_checkpoint"):
                waypoint = bot.get("rl_waypoint")
                if (waypoint is not None
                        and waypoint_reached(bot, waypoint)):
                    bot["rl_waypoints_reached"] = int(bot.get("rl_waypoints_reached", 0)) + 1
                    remaining = bot.get("rl_route_waypoints")
                    bot["rl_waypoint"] = (remaining.pop(0)
                                          if isinstance(remaining, list) and remaining
                                          else None)
                    bot.pop("_last_emit_state", None)
                if bot.get("rl_waypoint") is None:
                    self._pause_for_checkpoint(bot)
                    self.next_decision_at = now + self.decision_interval_s
                    return
            else:
                self.waypoints.ensure(bot, world)
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
    runtime = _runtime_for_ai(ai_name)
    if runtime:
        model = load_model(
            ai_name, bot.get("boatType", "submarine"), trace_enabled=trace_enabled)
        runtime.attach_controller(bot, ai_name, model)
        return
    bot["ai_tree"] = None
    bot["external_control"] = True
    boat_type = bot.get("boatType", "submarine")
    model = load_model(ai_name, boat_type, trace_enabled=trace_enabled)
    observation_dim = int((model.observation_space.shape or (0,))[0])
    model_nvec = tuple(int(value) for value in getattr(model.action_space, "nvec", ()))
    bot["rl_control_version"] = control_version_for_spaces(
        boat_type, observation_dim, model_nvec,
        getattr(model, "rl_control_version", None))
    seed_material = f"{ai_name}:{boat_type}".encode("utf-8")
    waypoint_seed = zlib.crc32(seed_material)
    bot["rl_waypoint"] = None
    bot["rl_waypoints_reached"] = 0
    bot["rl_destination"] = None
    bot["rl_route_start"] = None
    bot["rl_route"] = []
    bot["rl_route_waypoints"] = []
    controller = RuntimeController(model, waypoint_seed=waypoint_seed)
    controller.uses_waypoints = bot["rl_control_version"] in WAYPOINT_CONTROL_VERSIONS
    bot["rl_controller"] = controller
    bot["control_target_rudder"] = 0.0
    bot["control_target_speed_ratio"] = 0.0
    bot["control_target_depth_y"] = bot["position"].get("y", 0.0)
