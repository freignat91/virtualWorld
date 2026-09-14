"""Entraine et selectionne une politique sur la navigation seule."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Dict

import numpy as np
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor

from rl.navigation_env import NavigationEnv
from rl.train_ai import configure_loaded_model, file_sha256


BASE_DIR = Path(__file__).resolve().parent
NAVIGATION_GATES = {
    "min_success_rate": ("success_rate", "min"),
    "max_coastal_damage_episode_fraction": ("coastal_damage_episode_fraction", "max"),
    "max_stuck_rate": ("stuck_rate", "max"),
    "max_stationary_fraction": ("stationary_fraction", "max"),
    "max_mean_success_path_efficiency": ("mean_success_path_efficiency", "max"),
}


def validate_navigation_gates(config: Dict[str, Any]) -> Dict[str, float]:
    """Valide les seuils qui autorisent la promotion d'un navigateur."""
    gates = config.get("evaluation", {}).get("behavior_gates") or {}
    if not isinstance(gates, dict) or set(gates) - set(NAVIGATION_GATES):
        raise ValueError("behavior_gates de navigation invalides")
    normalized = {}
    for key, raw in gates.items():
        if isinstance(raw, bool):
            raise ValueError(f"gate de navigation invalide: {key}")
        value = float(raw)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"gate de navigation invalide: {key}")
        if key != "max_mean_success_path_efficiency" and value > 1.0:
            raise ValueError(f"gate de navigation hors proportion: {key}")
        normalized[key] = value
    return normalized


def navigation_gate_report(config: Dict[str, Any], metrics: Dict[str, float]) -> Dict[str, Any]:
    """Compare les mesures de navigation aux seuils sans utiliser de victoire."""
    gates = validate_navigation_gates(config)
    failures = []
    for key, threshold in gates.items():
        metric, direction = NAVIGATION_GATES[key]
        value = float(metrics[metric])
        if ((direction == "min" and value < threshold)
                or (direction == "max" and value > threshold)):
            failures.append(key)
    return {"passed": not failures, "gates": gates, "metrics": metrics,
            "failures": failures}


def env_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    """Traduit la config JSON vers l'environnement de navigation."""
    env = config["env"]
    return {
        "map_name": env["map_name"],
        "boat_type": env["boat_type"],
        "frame_skip": int(env["frame_skip"]),
        "max_episode_seconds": float(env["max_episode_seconds"]),
        "stuck_seconds": float(env["stuck_seconds"]),
        "goal_radius_m": float(env["goal_radius_m"]),
        "min_route_m": float(env["min_route_m"]),
        "max_route_m": float(env["max_route_m"]),
        "route_mode": env.get("route_mode", "blocked"),
        "max_detour_ratio": env.get("max_detour_ratio"),
        "coastal_clearance_m": float(env.get("coastal_clearance_m", 100.0)),
        "guidance_mode": env.get("guidance_mode", "goal"),
        "guidance_clearance_m": float(env.get("guidance_clearance_m", 0.0)),
        "waypoint_lookahead_m": env.get("waypoint_lookahead_m"),
        "progress_mode": env.get("progress_mode", "guidance"),
        "coastal_safety_clearance_m": float(env.get("coastal_safety_clearance_m", 0.0)),
        "coastal_safety_horizon_s": float(env.get("coastal_safety_horizon_s", 5.0)),
        "ray_max_m": float(env["ray_max_m"]),
        "reward": config["reward"],
    }


def evaluate_navigation(model: RecurrentPPO, config: Dict[str, Any],
                        episodes: int, seed: int) -> Dict[str, float]:
    """Evalue des routes fixes et agrege uniquement les comportements utiles."""
    if episodes <= 0:
        raise ValueError("episodes d'evaluation non positifs")
    env = NavigationEnv(**env_kwargs(config), seed=seed)
    totals = {
        "successes": 0, "coastal_damage_episodes": 0, "stuck": 0, "timeout": 0,
        "stationary_decisions": 0, "decisions": 0, "coastal_damage": 0.0,
        "near_coast_decisions": 0, "safety_interventions": 0,
        "success_path_efficiency": 0.0,
    }
    try:
        for episode in range(episodes):
            observation, _ = env.reset(seed=seed + episode)
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
            success = bool(info["success"])
            totals["successes"] += int(success)
            totals["coastal_damage_episodes"] += int(info["coastal_damage"] > 0.0)
            totals["stuck"] += int(info["outcome"] == "stuck")
            totals["timeout"] += int(info["outcome"] == "timeout")
            totals["stationary_decisions"] += int(info["stationary_decisions"])
            totals["near_coast_decisions"] += int(info["near_coast_decisions"])
            totals["safety_interventions"] += int(info["safety_interventions"])
            totals["decisions"] += int(info["decisions"])
            totals["coastal_damage"] += float(info["coastal_damage"])
            if success:
                totals["success_path_efficiency"] += float(info["path_efficiency"])
    finally:
        env.close()
    successes = totals["successes"]
    return {
        "episodes": float(episodes),
        "success_rate": successes / episodes,
        "coastal_damage_episode_fraction": totals["coastal_damage_episodes"] / episodes,
        "mean_coastal_damage": totals["coastal_damage"] / episodes,
        "stuck_rate": totals["stuck"] / episodes,
        "timeout_rate": totals["timeout"] / episodes,
        "stationary_fraction": totals["stationary_decisions"] / max(1, totals["decisions"]),
        "near_coast_fraction": totals["near_coast_decisions"] / max(1, totals["decisions"]),
        "safety_intervention_fraction": (
            totals["safety_interventions"] / max(1, totals["decisions"])),
        "mean_success_path_efficiency": (
            totals["success_path_efficiency"] / successes if successes else 1_000_000.0),
    }


def navigation_quality(metrics: Dict[str, float]) -> float:
    """Ordonne les checkpoints admissibles avec des mesures de navigation."""
    return (metrics["success_rate"]
            - metrics["coastal_damage_episode_fraction"]
            - metrics["stuck_rate"] - metrics["timeout_rate"]
            - 0.1 * metrics["stationary_fraction"]
            - 0.1 * max(0.0, metrics["mean_success_path_efficiency"] - 1.0))


class NavigationEvalCallback(BaseCallback):
    """Evalue et sauvegarde seulement les navigateurs qui passent tous les gates."""

    def __init__(self, config: Dict[str, Any], output_dir: Path) -> None:
        super().__init__()
        evaluation = config["evaluation"]
        self.config = config
        self.output_dir = output_dir
        self.every_steps = int(evaluation["every_steps"])
        self.episodes = int(evaluation["episodes"])
        self.seed = int(evaluation["seed"])
        self.next_step = self.every_steps
        self.best_quality = -float("inf")
        self.best_candidate_quality = -float("inf")

    def _save_selection(self, directory_name: str, model_name: str,
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
        metrics = evaluate_navigation(self.model, self.config, self.episodes, self.seed)
        gates = navigation_gate_report(self.config, metrics)
        quality = navigation_quality(metrics)
        evaluation_dir = self.output_dir / "evaluation"
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        record = {"timesteps": self.num_timesteps, "quality": quality, "behavior": gates}
        with (evaluation_dir / "navigation.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        for key, value in metrics.items():
            self.logger.record(f"navigation/{key}", value)
        print(f"navigation eval at {self.num_timesteps}: success={metrics['success_rate']:.1%}")
        if gates["failures"]:
            print(f"Navigation gates failed: {', '.join(gates['failures'])}")
        metadata = {
            "timesteps": self.num_timesteps,
            "quality": quality,
            "behavior": gates,
        }
        if quality > self.best_candidate_quality:
            self._save_selection("candidate", "candidate_model", metadata)
            self.best_candidate_quality = quality
            print("New best navigation candidate!")
        if gates["passed"] and quality > self.best_quality:
            self._save_selection("best", "best_model", metadata)
            self.best_quality = quality
            print("New best navigation behavior!")
        while self.next_step <= self.num_timesteps:
            self.next_step += self.every_steps
        return True


def load_config(path: Path) -> Dict[str, Any]:
    """Charge une config de navigation et valide ses sections structurantes."""
    config = json.loads(path.read_text(encoding="utf-8"))
    for section in ("model", "training", "env", "reward", "evaluation"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"section de navigation absente: {section}")
    validate_navigation_gates(config)
    return config


def make_env(config: Dict[str, Any], seed: int):
    """Fabrique une closure sérialisable pour les environnements vectorisés."""
    def factory() -> NavigationEnv:
        return NavigationEnv(**env_kwargs(config), seed=seed)
    return factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=BASE_DIR / "configs" / "aidest_navigation_v1.json")
    parser.add_argument("--run-name")
    parser.add_argument("--resume", type=Path,
                        help="checkpoint source d'une nouvelle phase de navigation")
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
        raise ValueError("n_envs doit etre positif")
    run_name = args.run_name or config["name"]
    output_dir = BASE_DIR / "models_rl" / run_name
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError(f"repertoire de sortie non vide: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = args.resume.resolve(strict=True) if args.resume else None
    source_sha256 = file_sha256(source_path) if source_path else None
    smoke = make_env(config, int(training["seed"]))()
    check_env(smoke, warn=True)
    smoke.close()
    factories = [make_env(config, int(training["seed"]) + index) for index in range(n_envs)]
    vec_env = (DummyVecEnv(factories) if n_envs == 1 else
               SubprocVecEnv(factories, start_method="forkserver"))
    vec_env = VecMonitor(vec_env, filename=str(output_dir / "monitor.csv"))
    model_cfg = config["model"]
    policy_kwargs = {"net_arch": list(model_cfg["net_arch"]),
                     "lstm_hidden_size": int(model_cfg["lstm_hidden_size"]),
                     "n_lstm_layers": int(model_cfg["n_lstm_layers"])}
    if source_path:
        try:
            model = RecurrentPPO.load(
                source_path, env=vec_env, device=args.device,
                seed=int(training["seed"]), policy_kwargs=policy_kwargs,
                tensorboard_log=str(output_dir / "tensorboard"))
            configure_loaded_model(model, config)
            if file_sha256(source_path) != source_sha256:
                raise RuntimeError("checkpoint de navigation modifie pendant le chargement")
        except BaseException:
            vec_env.close()
            raise
    else:
        model = RecurrentPPO(
            "MlpLstmPolicy", vec_env,
            learning_rate=float(training["learning_rate"]),
            n_steps=int(training["n_steps"]), batch_size=int(training["batch_size"]),
            n_epochs=int(training["n_epochs"]), gamma=float(training["gamma"]),
            gae_lambda=float(training["gae_lambda"]), clip_range=float(training["clip_range"]),
            ent_coef=float(training["ent_coef"]), vf_coef=float(training["vf_coef"]),
            max_grad_norm=float(training["max_grad_norm"]), policy_kwargs=policy_kwargs,
            tensorboard_log=str(output_dir / "tensorboard"), seed=int(training["seed"]),
            device=args.device, verbose=1)
    (output_dir / "effective_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "provenance.json").write_text(json.dumps({
        "phase": "navigation_warm_start" if source_path else "navigation_from_scratch",
        "checkpoint_source": str(source_path) if source_path else None,
        "checkpoint_sha256": source_sha256,
        "checkpoint_timesteps": model.num_timesteps,
        "seed": int(training["seed"]),
        "planned_steps": total_steps, "requested_steps": invocation_steps,
        "observation_version": {
            "goal": "navigation_v1",
            "safe_waypoint": "navigation_v2",
            "lookahead_waypoint": "navigation_v3",
        }.get(config["env"].get("guidance_mode", "goal"), "navigation_v1"),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    callbacks = [
        CheckpointCallback(
            save_freq=max(1, int(training["checkpoint_every_steps"]) // n_envs),
            save_path=str(output_dir / "checkpoints"), name_prefix="policy"),
        NavigationEvalCallback(config, output_dir),
    ]
    try:
        model.learn(total_timesteps=invocation_steps, callback=callbacks,
                    reset_num_timesteps=True,
                    tb_log_name=run_name, progress_bar=True)
    finally:
        model.save(output_dir / "policy_final")
        vec_env.close()


if __name__ == "__main__":
    main()
