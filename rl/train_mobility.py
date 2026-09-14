"""Entraine depuis zero une politique runtime sur la mobilite seule."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Dict

import numpy as np
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor

import simulation
from rl.mobility_env import ROUTE_CATEGORIES, MobilityEnv
from rl.masked_recurrent_policy import (
    MASKED_CONTROL_VERSIONS,
    SituationMaskedMlpLstmPolicy,
)
from rl.rl_control import (
    DESTROYER_V5_OBSERVATION_VERSION,
    DESTROYER_V6_OBSERVATION_VERSION,
    SUBMARINE_V3_OBSERVATION_VERSION,
    SUBMARINE_V4_OBSERVATION_VERSION,
    control_spec,
)
from rl.train_ai import EntropyScheduleCallback, file_sha256


BASE_DIR = Path(__file__).resolve().parent
MOBILITY_GATES = {
    "min_completion_rate": ("completion_rate", "min"),
    "min_open_completion_rate": ("open_completion_rate", "min"),
    "min_obstacle_completion_rate": ("obstacle_completion_rate", "min"),
    "min_waypoint_arrival_rate": ("waypoint_arrival_rate", "min"),
    "min_mean_speed_ratio": ("mean_speed_ratio", "min"),
    "min_mean_straightness": ("mean_straightness", "min"),
    "max_coastal_damage_episode_fraction": ("coastal_damage_episode_fraction", "max"),
    "max_sunk_count": ("sunk_count", "max"),
    "max_stuck_count": ("stuck_count", "max"),
    "max_stuck_rate": ("stuck_rate", "max"),
    "max_stationary_fraction": ("stationary_fraction", "max"),
    "max_reverse_fraction": ("reverse_fraction", "max"),
    "max_weapon_request_fraction": ("weapon_request_fraction", "max"),
    "max_lure_request_fraction": ("lure_request_fraction", "max"),
    "max_sonar_request_fraction": ("sonar_request_fraction", "max"),
}


def validate_mobility_gates(config: Dict[str, Any]) -> Dict[str, float]:
    """Valide les seuils comportementaux de la premiere phase."""
    gates = config.get("evaluation", {}).get("behavior_gates") or {}
    if not isinstance(gates, dict) or set(gates) - set(MOBILITY_GATES):
        raise ValueError("evaluation.behavior_gates de mobilite invalides")
    normalized = {}
    for key, raw in gates.items():
        if type(raw) not in (int, float):
            raise ValueError(f"gate de mobilite invalide: {key}")
        value = float(raw)
        is_count = key.endswith("_count")
        if (not math.isfinite(value) or value < 0.0
                or (is_count and not value.is_integer())
                or (not is_count and value > 1.0)):
            raise ValueError(f"gate de mobilite hors limites: {key}")
        normalized[key] = value
    return normalized


def mobility_gate_report(config: Dict[str, Any], metrics: Dict[str, float]) -> Dict[str, Any]:
    """Compare une evaluation aux seuils sans score de combat."""
    gates = validate_mobility_gates(config)
    failures = []
    for key, threshold in gates.items():
        metric, direction = MOBILITY_GATES[key]
        value = float(metrics[metric])
        if ((direction == "min" and value < threshold)
                or (direction == "max" and value > threshold)):
            failures.append(key)
    return {"passed": not failures, "gates": gates, "metrics": metrics,
            "failures": failures}


def env_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    """Traduit la configuration vers l'environnement de mobilite."""
    env = config["env"]
    return {
        "map_name": env["map_name"],
        "boat_type": env["boat_type"],
        "control_version": env["control_version"],
        "frame_skip": int(env["frame_skip"]),
        "max_episode_seconds": float(env["max_episode_seconds"]),
        "stuck_seconds": float(env["stuck_seconds"]),
        "movement_anchor_m": float(env["movement_anchor_m"]),
        "spawn_clearance_m": float(env["spawn_clearance_m"]),
        "obstacle_min_m": float(env["obstacle_min_m"]),
        "obstacle_max_m": float(env["obstacle_max_m"]),
        "obstacle_probability_start": float(env["obstacle_probability_start"]),
        "obstacle_probability_end": float(env["obstacle_probability_end"]),
        "curriculum_decisions": int(env["curriculum_decisions"]),
        "coastal_clearance_m": float(env["coastal_clearance_m"]),
        "progress_mode": env.get("progress_mode", "euclidean"),
        "route_curriculum": env.get("route_curriculum"),
        "reward": config["reward"],
    }


def evaluate_mobility(model: RecurrentPPO, config: Dict[str, Any],
                      episodes: int, seed: int, *,
                      segmented_routes: bool = False,
                      episode_records: list[Dict[str, Any]] | None = None,
                      episode_progress: Callable[
                          [int, int, Dict[str, Any]], None] | None = None,
                      ) -> Dict[str, float]:
    """Evalue alternativement en eau libre et face a une ile."""
    if episodes < 2:
        raise ValueError("evaluation de mobilite exige au moins deux episodes")
    env = MobilityEnv(
        **env_kwargs(config), seed=seed, segmented_routes=segmented_routes)
    totals = {
        "completions": 0, "open_episodes": 0, "open_completions": 0,
        "obstacle_episodes": 0, "obstacle_completions": 0,
        "coastal_damage_episodes": 0, "sunk": 0, "stuck": 0,
        "stationary_decisions": 0, "reverse_decisions": 0,
        "weapon_requests": 0, "lure_requests": 0, "sonar_requests": 0,
        "decisions": 0, "coastal_damage": 0.0,
        "near_coast_decisions": 0, "straightness": 0.0, "speed_ratio": 0.0,
        "forward_moved_m": 0.0, "reverse_moved_m": 0.0,
        "waypoints_reached": 0, "arrivals": 0,
        "minimum_clearance_m": float("inf"),
    }
    route_totals = {
        category: {
            "episodes": 0, "completions": 0, "arrivals": 0,
            "coastal": 0, "stuck": 0,
        }
        for category in ROUTE_CATEGORIES
    }
    route_curriculum = config["env"].get("route_curriculum")
    masked_policy = getattr(model.policy, "mobility_curriculum", None)
    if masked_policy is not None:
        model.policy.mobility_curriculum = True
    try:
        for episode in range(episodes):
            if route_curriculum:
                target = (episode + 0.5) / episodes
                cumulative = 0.0
                category = ROUTE_CATEGORIES[-1]
                for candidate in ROUTE_CATEGORIES:
                    cumulative += float(route_curriculum[candidate])
                    if target < cumulative:
                        category = candidate
                        break
                obstacle = category != "visible"
                reset_options = {"route_category": category}
            else:
                obstacle = bool(episode % 2)
                reset_options = {"obstacle": obstacle}
            observation, reset_info = env.reset(
                seed=seed + episode, options=reset_options)
            initial_bot = env._agent()
            destination = dict(
                initial_bot.get("rl_destination") or initial_bot["rl_waypoint"])
            planned_waypoints = [
                dict(point) for point in initial_bot.get(
                    "rl_route", [initial_bot["rl_waypoint"]])]
            state = None
            episode_start = np.array([True], dtype=bool)
            while True:
                action, state = model.predict(
                    observation, state=state, episode_start=episode_start,
                    deterministic=True)
                episode_start[:] = False
                observation, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    break
            completed = info["outcome"] == "completed"
            arrived = int(info.get("route_arrived", info["waypoints_reached"] > 0))
            totals["completions"] += int(completed)
            totals["arrivals"] += arrived
            group = "obstacle" if obstacle else "open"
            totals[f"{group}_episodes"] += 1
            totals[f"{group}_completions"] += int(completed)
            totals["coastal_damage_episodes"] += int(info["coastal_damage"] > 0.0)
            totals["sunk"] += int(info["outcome"] == "sunk")
            totals["stuck"] += int(info["outcome"] == "stuck")
            if route_curriculum:
                category_total = route_totals[category]
                category_total["episodes"] += 1
                category_total["completions"] += int(completed)
                category_total["arrivals"] += arrived
                category_total["coastal"] += int(info["coastal_damage"] > 0.0)
                category_total["stuck"] += int(info["outcome"] == "stuck")
            for key in (
                    "stationary_decisions", "reverse_decisions", "weapon_requests",
                    "lure_requests", "sonar_requests", "decisions", "near_coast_decisions"):
                totals[key] += int(info[key])
            totals["coastal_damage"] += float(info["coastal_damage"])
            totals["straightness"] += float(info["straightness"])
            totals["speed_ratio"] += float(info["mean_speed_ratio"])
            totals["forward_moved_m"] += float(info["forward_moved_m"])
            totals["reverse_moved_m"] += float(info["reverse_moved_m"])
            totals["waypoints_reached"] += int(info["waypoints_reached"])
            totals["minimum_clearance_m"] = min(
                totals["minimum_clearance_m"], float(info["minimum_clearance_m"]))
            if episode_records is not None:
                final_position = env._last_position
                episode_records.append({
                    "episode": episode,
                    "seed": seed + episode,
                    "category": category if route_curriculum else group,
                    "start": reset_info["position"],
                    "rotation": reset_info["rotation"],
                    "destination": destination,
                    "plannedWaypoints": planned_waypoints,
                    "outcome": info["outcome"],
                    "arrived": bool(arrived),
                    "elapsedSeconds": float(info["elapsed_seconds"]),
                    "finalPosition": {
                        "x": float(final_position[0]), "z": float(final_position[1])},
                    "finalDistanceMeters": math.hypot(
                        destination["x"] - final_position[0],
                        destination["z"] - final_position[1]) * simulation.UNIT_METERS_BOT,
                    "segmentsReached": int(info["waypoints_reached"]),
                    "coastalDamage": float(info["coastal_damage"]),
                    "minimumClearanceMeters": float(info["minimum_clearance_m"]),
                    "meanSpeedRatio": float(info["mean_speed_ratio"]),
                    "straightness": float(info["straightness"]),
                })
            if episode_progress is not None:
                episode_progress(episode + 1, episodes, info)
    finally:
        env.close()
        if masked_policy is not None:
            model.policy.mobility_curriculum = masked_policy
    decisions = max(1, totals["decisions"])
    result = {
        "episodes": float(episodes),
        "completion_rate": totals["completions"] / episodes,
        "waypoint_arrival_rate": totals["arrivals"] / episodes,
        "open_completion_rate": totals["open_completions"] / totals["open_episodes"],
        "obstacle_completion_rate": (
            totals["obstacle_completions"] / totals["obstacle_episodes"]),
        "coastal_damage_episode_fraction": totals["coastal_damage_episodes"] / episodes,
        "mean_coastal_damage": totals["coastal_damage"] / episodes,
        "sunk_count": float(totals["sunk"]),
        "stuck_count": float(totals["stuck"]),
        "stuck_rate": totals["stuck"] / episodes,
        "stationary_fraction": totals["stationary_decisions"] / decisions,
        "reverse_fraction": totals["reverse_decisions"] / decisions,
        "near_coast_fraction": totals["near_coast_decisions"] / decisions,
        "weapon_request_fraction": totals["weapon_requests"] / decisions,
        "lure_request_fraction": totals["lure_requests"] / decisions,
        "sonar_request_fraction": totals["sonar_requests"] / decisions,
        "mean_straightness": totals["straightness"] / episodes,
        "mean_speed_ratio": totals["speed_ratio"] / episodes,
        "mean_forward_moved_m": totals["forward_moved_m"] / episodes,
        "mean_reverse_moved_m": totals["reverse_moved_m"] / episodes,
        "waypoints_reached_per_episode": totals["waypoints_reached"] / episodes,
        "minimum_clearance_m": totals["minimum_clearance_m"],
    }
    if route_curriculum:
        for category, category_total in route_totals.items():
            count = max(1, category_total["episodes"])
            result[f"route_{category}_episodes"] = float(category_total["episodes"])
            result[f"route_{category}_completion_rate"] = (
                category_total["completions"] / count)
            result[f"route_{category}_arrival_rate"] = (
                category_total["arrivals"] / count)
            result[f"route_{category}_coastal_damage_episode_fraction"] = (
                category_total["coastal"] / count)
            result[f"route_{category}_stuck_rate"] = category_total["stuck"] / count
    return result


def mobility_quality(metrics: Dict[str, float]) -> float:
    """Ordonne les candidats sans masquer un echec aux gates."""
    return (metrics["completion_rate"]
            + metrics["waypoints_reached_per_episode"]
            + 0.2 * metrics["mean_speed_ratio"]
            + 0.1 * metrics["mean_straightness"]
            - metrics["coastal_damage_episode_fraction"]
            - metrics["stuck_rate"]
            - 0.1 * metrics["stationary_fraction"]
            - 0.05 * metrics["reverse_fraction"]
            - 0.02 * (metrics["weapon_request_fraction"]
                      + metrics["lure_request_fraction"]
                      + metrics["sonar_request_fraction"]))


class MobilityEvalCallback(BaseCallback):
    """Sauvegarde le meilleur candidat et, separement, le meilleur admissible."""

    def __init__(self, config: Dict[str, Any], output_dir: Path) -> None:
        super().__init__()
        evaluation = config["evaluation"]
        self.config = config
        self.output_dir = output_dir
        self.every_steps = int(evaluation["every_steps"])
        self.episodes = int(evaluation["episodes"])
        self.seed = int(evaluation["seed"])
        if self.every_steps <= 0 or self.episodes < 2:
            raise ValueError("frequence ou nombre d'episodes d'evaluation invalide")
        self.next_step = self.every_steps
        self.best_quality = -float("inf")
        self.best_candidate_quality = -float("inf")

    def _save(self, directory_name: str, model_name: str,
              metadata: Dict[str, Any]) -> None:
        directory = self.output_dir / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        temporary_model = directory / f".{model_name}.tmp.zip"
        self.model.save(temporary_model)
        metadata = {**metadata, "model_sha256": file_sha256(temporary_model)}
        temporary_metadata = directory / ".selection.tmp.json"
        temporary_metadata.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary_model, directory / f"{model_name}.zip")
        os.replace(temporary_metadata, directory / "selection.json")

    def _on_step(self) -> bool:
        if self.num_timesteps < self.next_step:
            return True
        metrics = evaluate_mobility(self.model, self.config, self.episodes, self.seed)
        behavior = mobility_gate_report(self.config, metrics)
        quality = mobility_quality(metrics)
        evaluation_dir = self.output_dir / "evaluation"
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        record = {"timesteps": self.num_timesteps, "quality": quality,
                  "behavior": behavior}
        with (evaluation_dir / "mobility.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        for key, value in metrics.items():
            self.logger.record(f"mobility/{key}", value)
        print(f"mobility eval at {self.num_timesteps}: completion={metrics['completion_rate']:.1%}")
        metadata = {"timesteps": self.num_timesteps, "quality": quality,
                    "behavior": behavior}
        if quality > self.best_candidate_quality:
            self._save("candidate", "candidate_model", metadata)
            self.best_candidate_quality = quality
        if behavior["passed"] and quality > self.best_quality:
            self._save("best", "best_model", metadata)
            self.best_quality = quality
        while self.next_step <= self.num_timesteps:
            self.next_step += self.every_steps
        return True


def load_config(path: Path) -> Dict[str, Any]:
    """Charge une configuration fraiche et interdit une interface historique."""
    config = json.loads(path.read_text(encoding="utf-8"))
    for section in ("model", "training", "env", "reward", "evaluation"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"section de mobilite absente: {section}")
    env = config["env"]
    allowed = {
        "submarine": {
            SUBMARINE_V3_OBSERVATION_VERSION, SUBMARINE_V4_OBSERVATION_VERSION},
        "destroyer": {
            DESTROYER_V5_OBSERVATION_VERSION, DESTROYER_V6_OBSERVATION_VERSION},
    }.get(env.get("boat_type"))
    version = env.get("control_version")
    if allowed is None or version not in allowed:
        raise ValueError("la mobilite exige l'interface runtime definitive de la coque")
    control_spec(env["boat_type"], version)
    validate_mobility_gates(config)
    training = config["training"]
    entropy_values = (
        training.get("ent_coef"),
        training.get("ent_coef_end", training.get("ent_coef")),
    )
    if any(type(value) not in (int, float) or not math.isfinite(float(value))
           or float(value) < 0.0 for value in entropy_values):
        raise ValueError("coefficients d'entropie de mobilite invalides")
    decay_start = training.get("ent_coef_decay_start_steps", 0)
    total_steps = training.get("total_steps")
    if (type(total_steps) is not int or total_steps <= 0
            or type(decay_start) is not int
            or not 0 <= decay_start < total_steps):
        raise ValueError("plage de decroissance d'entropie de mobilite invalide")
    return config


def make_env(config: Dict[str, Any], seed: int):
    """Fabrique une closure serialisable pour les environnements vectorises."""
    def factory() -> MobilityEnv:
        return MobilityEnv(**env_kwargs(config), seed=seed)
    return factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-name")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--stop-after-steps", type=int)
    args = parser.parse_args()
    config = load_config(args.config)
    training = config["training"]
    total_steps = int(training["total_steps"])
    invocation_steps = args.stop_after_steps or total_steps
    if not 0 < invocation_steps <= total_steps:
        parser.error("--stop-after-steps doit etre positif et limite au plan")
    n_envs = int(training["n_envs"])
    if n_envs < 1:
        raise ValueError("training.n_envs doit etre positif")
    run_name = args.run_name or config["name"]
    output_dir = BASE_DIR / "models_rl" / run_name
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError(f"repertoire de sortie non vide: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    smoke = make_env(config, int(training["seed"]))()
    check_env(smoke, warn=True)
    smoke.close()
    factories = [make_env(config, int(training["seed"]) + index) for index in range(n_envs)]
    vec_env = (DummyVecEnv(factories) if n_envs == 1 else
               SubprocVecEnv(factories, start_method="forkserver"))
    vec_env = VecMonitor(vec_env, filename=str(output_dir / "monitor.csv"))
    model_cfg = config["model"]
    control_version = config["env"]["control_version"]
    policy_kwargs = {
        "net_arch": list(model_cfg["net_arch"]),
        "lstm_hidden_size": int(model_cfg["lstm_hidden_size"]),
        "n_lstm_layers": int(model_cfg["n_lstm_layers"]),
    }
    policy = "MlpLstmPolicy"
    if control_version in MASKED_CONTROL_VERSIONS:
        policy = SituationMaskedMlpLstmPolicy
        policy_kwargs["control_version"] = control_version
    model = RecurrentPPO(
        policy, vec_env,
        learning_rate=float(training["learning_rate"]),
        n_steps=int(training["n_steps"]), batch_size=int(training["batch_size"]),
        n_epochs=int(training["n_epochs"]), gamma=float(training["gamma"]),
        gae_lambda=float(training["gae_lambda"]), clip_range=float(training["clip_range"]),
        ent_coef=float(training["ent_coef"]), vf_coef=float(training["vf_coef"]),
        max_grad_norm=float(training["max_grad_norm"]),
        policy_kwargs=policy_kwargs,
        tensorboard_log=str(output_dir / "tensorboard"), seed=int(training["seed"]),
        device=args.device, verbose=1)
    model.rl_control_version = config["env"]["control_version"]
    if isinstance(model.policy, SituationMaskedMlpLstmPolicy):
        model.policy.mobility_curriculum = True
    (output_dir / "effective_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "provenance.json").write_text(json.dumps({
        "phase": "mobility_from_scratch",
        "checkpoint_source": None,
        "seed": int(training["seed"]),
        "planned_steps": total_steps,
        "requested_steps": invocation_steps,
        "boat_type": config["env"]["boat_type"],
        "control_version": config["env"]["control_version"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    callbacks = [
        EntropyScheduleCallback(
            float(training["ent_coef"]),
            float(training.get("ent_coef_end", training["ent_coef"])),
            total_steps,
            int(training.get("ent_coef_decay_start_steps", 0))),
        CheckpointCallback(
            save_freq=max(1, int(training["checkpoint_every_steps"]) // n_envs),
            save_path=str(output_dir / "checkpoints"), name_prefix="policy"),
        MobilityEvalCallback(config, output_dir),
    ]
    try:
        model.learn(total_timesteps=invocation_steps, callback=callbacks,
                    reset_num_timesteps=True, tb_log_name=run_name, progress_bar=True)
    finally:
        model.save(output_dir / "policy_final")
        vec_env.close()


if __name__ == "__main__":
    main()
