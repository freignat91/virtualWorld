"""Entraîne une politique récurrente contre les BT puis en self-play."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple

from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.utils import get_schedule_fn
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor

from rl.evaluate_ai import evaluate as evaluate_policy
from rl.rl_control import control_spec
from rl.rl_env import SubmarineDuelEnv


BASE_DIR = Path(__file__).resolve().parent


class EntropyScheduleCallback(BaseCallback):
    """Réduit linéairement l'entropie pendant cette phase d'entraînement."""

    def __init__(self, start: float, end: float, total_steps: int) -> None:
        super().__init__()
        self.start = start
        self.end = end
        self.total_steps = max(1, total_steps)

    def _on_step(self) -> bool:
        progress = min(1.0, self.num_timesteps / self.total_steps)
        self.model.ent_coef = self.start + progress * (self.end - self.start)
        return True


class LeagueSnapshotCallback(BaseCallback):
    """Publie atomiquement des adversaires historiques pour les workers."""

    def __init__(self, directory: Path, every_steps: int, keep_last: int) -> None:
        super().__init__()
        self.directory = directory
        self.every_steps = max(1, every_steps)
        self.keep_last = max(2, keep_last)
        self.next_step = self.every_steps

    def _on_step(self) -> bool:
        if self.num_timesteps < self.next_step:
            return True
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"policy_{self.num_timesteps:09d}.zip"
        temporary = self.directory / f".policy_{self.num_timesteps:09d}.tmp.zip"
        self.model.save(temporary)
        os.replace(temporary, target)
        snapshots = sorted(self.directory.glob("policy_*.zip"))
        for old_path in snapshots[:-self.keep_last]:
            old_path.unlink(missing_ok=True)
        while self.next_step <= self.num_timesteps:
            self.next_step += self.every_steps
        return True


def match_score(result: Dict[str, Any]) -> float:
    """Calcule victoire + 0,5 nul sur une série d'évaluation."""
    episodes = int(result.get("episodes", 0))
    if episodes <= 0:
        raise ValueError("une évaluation doit contenir au moins un épisode")
    wins = int(result.get("wins", 0))
    losses = int(result.get("losses", 0))
    draws = int(result.get("draws", 0))
    if min(wins, losses, draws) < 0 or wins + losses + draws != episodes:
        raise ValueError("comptes victoire/défaite/nul incohérents")
    return (wins + 0.5 * draws) / episodes


def weighted_match_score(results: Sequence[Tuple[Dict[str, Any], float]]) -> float:
    """Agrège les adversaires selon leur probabilité dans la configuration."""
    if any(not math.isfinite(weight) or weight < 0.0 for _, weight in results):
        raise ValueError("poids d'évaluation invalide")
    total_weight = sum(weight for _, weight in results)
    if total_weight <= 0.0:
        raise ValueError("poids d'évaluation total nul")
    return sum(match_score(result) * weight for result, weight in results) / total_weight


def file_sha256(path: Path) -> str:
    """Calcule l'empreinte d'un artefact sans le charger entièrement en mémoire."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MatchScoreEvalCallback(BaseCallback):
    """Évalue chaque adversaire et conserve le meilleur score de match."""

    def __init__(self, config: Dict[str, Any], output_dir: Path,
                 every_steps: int, episodes: int, seed: int) -> None:
        super().__init__()
        self.config = config
        self.output_dir = output_dir
        self.every_steps = int(every_steps)
        self.episodes = int(episodes)
        if self.every_steps <= 0:
            raise ValueError("evaluation.every_steps doit être positif")
        if self.episodes <= 0:
            raise ValueError("evaluation.episodes doit être positif")
        self.seed = int(seed)
        self.next_step = self.every_steps
        self.best_score = float("-inf")

    def _selection_signature(self) -> str:
        env_cfg = self.config["env"]
        selection_config = {
            "agent_boat_type": env_cfg.get("agent_boat_type", "submarine"),
            "control_version": env_cfg.get("control_version"),
            "frame_skip": env_cfg["frame_skip"],
            "max_physics_steps": env_cfg["max_physics_steps"],
            "spawn_min_m": env_cfg["spawn_min_m"],
            "spawn_max_m": env_cfg["spawn_max_m"],
            "reward": self.config["reward"],
            "evaluation": self.config["evaluation"],
            "episodes": self.episodes,
            "seed": self.seed,
        }
        encoded = json.dumps(
            selection_config, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _init_callback(self) -> None:
        selection_path = self.output_dir / "best" / "selection.json"
        if not selection_path.is_file():
            return
        with selection_path.open(encoding="utf-8") as handle:
            previous = json.load(handle)
        best_model_path = self.output_dir / "best" / "best_model.zip"
        if previous.get("selection_signature") != self._selection_signature():
            raise RuntimeError("configuration d'évaluation différente du meilleur modèle existant")
        if not best_model_path.is_file() or not zipfile.is_zipfile(best_model_path):
            raise RuntimeError("meilleur modèle existant absent ou invalide")
        if previous.get("model_sha256") != file_sha256(best_model_path):
            raise RuntimeError("le meilleur modèle ne correspond pas à selection.json")
        self.best_score = float(previous["match_score"])

    def _evaluate(self) -> Tuple[float, list[Dict[str, Any]]]:
        env_cfg = self.config["env"]
        eval_cfg = self.config["evaluation"]
        agent_boat_type = env_cfg.get("agent_boat_type", "submarine")
        control_version = control_spec(
            agent_boat_type, env_cfg.get("control_version"))[0]
        env_options = {
            "max_physics_steps": int(env_cfg["max_physics_steps"]),
            "frame_skip": int(env_cfg["frame_skip"]),
            "spawn_min_m": float(env_cfg["spawn_min_m"]),
            "spawn_max_m": float(env_cfg["spawn_max_m"]),
            "reward": self.config["reward"],
        }
        fixed_policy = eval_cfg.get("fixed_opponent_policy") or {}
        fixed_probability = max(0.0, min(1.0, float(fixed_policy.get("probability", 0.0))))
        opponents = tuple(eval_cfg.get("opponents") or ())
        bt_weight = sum(float(opponent.get("weight", 1.0)) for opponent in opponents)
        weighted_results: list[Tuple[Dict[str, Any], float]] = []
        details: list[Dict[str, Any]] = []

        for opponent in opponents:
            weight = ((1.0 - fixed_probability) * float(opponent.get("weight", 1.0))
                      / bt_weight) if bt_weight > 0.0 else 0.0
            result = evaluate_policy(
                self.model, eval_cfg["map_name"], opponent["boat_type"], opponent["ai"],
                self.episodes, self.seed, agent_boat_type=agent_boat_type,
                agent_control_version=control_version, env_options=env_options)
            result["selection_weight"] = weight
            result["match_score"] = match_score(result)
            weighted_results.append((result, weight))
            details.append(result)

        fixed_pool = fixed_policy.get("pool_dir")
        if fixed_pool and fixed_probability > 0.0:
            pool_path = Path(fixed_pool)
            if not pool_path.is_absolute():
                pool_path = BASE_DIR / pool_path
            fixed_boat_type = fixed_policy.get("boat_type", "submarine")
            result = evaluate_policy(
                self.model, eval_cfg["map_name"], fixed_boat_type, "autosub",
                self.episodes, self.seed, str(pool_path), agent_boat_type,
                fixed_boat_type, control_version, env_options)
            result["selection_weight"] = fixed_probability
            result["match_score"] = match_score(result)
            weighted_results.append((result, fixed_probability))
            details.append(result)

        score = weighted_match_score(weighted_results)
        return score, details

    def _save_best(self, score: float, details: list[Dict[str, Any]]) -> None:
        best_dir = self.output_dir / "best"
        best_dir.mkdir(parents=True, exist_ok=True)
        temporary_model = best_dir / ".best_model.tmp.zip"
        self.model.save(temporary_model)
        model_digest = file_sha256(temporary_model)
        metadata = {
            "timesteps": self.num_timesteps,
            "match_score": score,
            "selection_signature": self._selection_signature(),
            "model_sha256": model_digest,
            "opponents": details,
        }
        temporary_metadata = best_dir / ".selection.tmp.json"
        with temporary_metadata.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, ensure_ascii=False)
        os.replace(temporary_model, best_dir / "best_model.zip")
        os.replace(temporary_metadata, best_dir / "selection.json")

    def _on_step(self) -> bool:
        if self.num_timesteps < self.next_step:
            return True
        score, details = self._evaluate()
        history_dir = self.output_dir / "evaluation"
        history_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timesteps": self.num_timesteps,
            "match_score": score,
            "opponents": details,
        }
        with (history_dir / "match_scores.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.logger.record("eval/match_score", score)
        for index, detail in enumerate(details):
            self.logger.record(f"eval/opponent_{index}_match_score", detail["match_score"])
        print(f"Match score at {self.num_timesteps} steps: {score:.2%}")
        if score > self.best_score:
            self.best_score = score
            self._save_best(score, details)
            print("New best match score!")
        while self.next_step <= self.num_timesteps:
            self.next_step += self.every_steps
        return True


def load_config(path: str) -> Dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    for section in ("model", "training", "env", "reward", "evaluation", "league"):
        if section not in config:
            raise ValueError(f"section absente dans la config: {section}")
    return config


def make_env(config: Dict[str, Any], *, seed: int, stage: str,
             curriculum_decisions: int, league_dir: Path,
             evaluation: bool = False):
    env_cfg = config["env"]
    eval_cfg = config["evaluation"]

    def factory() -> SubmarineDuelEnv:
        opponent_cfg = eval_cfg if evaluation else env_cfg
        fixed_policy = opponent_cfg.get("fixed_opponent_policy") or {}
        fixed_pool = fixed_policy.get("pool_dir")
        if fixed_pool:
            fixed_pool_path = Path(fixed_pool)
            if not fixed_pool_path.is_absolute():
                fixed_pool_path = BASE_DIR / fixed_pool_path
            fixed_pool = str(fixed_pool_path)
        return SubmarineDuelEnv(
            map_name=eval_cfg["map_name"] if evaluation else env_cfg["map_name"],
            agent_boat_type=env_cfg.get("agent_boat_type", "submarine"),
            control_version=env_cfg.get("control_version"),
            opponents=opponent_cfg.get("opponents"),
            opponent_ais=opponent_cfg.get("opponent_ais"),
            opponent_pool_dir=None if evaluation or stage == "scripted" else str(league_dir),
            self_play_probability=0.0 if evaluation or stage == "scripted" else float(
                config["league"]["self_play_probability"]),
            fixed_opponent_pool_dir=fixed_pool,
            fixed_opponent_boat_type=fixed_policy.get("boat_type", "submarine"),
            fixed_policy_probability=float(fixed_policy.get("probability", 0.0)),
            max_physics_steps=int(env_cfg["max_physics_steps"]),
            frame_skip=int(env_cfg["frame_skip"]),
            spawn_min_m=float(env_cfg["spawn_min_m"]),
            spawn_max_m=float(env_cfg["spawn_max_m"]),
            curriculum_start_min_m=None if evaluation else float(env_cfg["curriculum_start_min_m"]),
            curriculum_start_max_m=None if evaluation else float(env_cfg["curriculum_start_max_m"]),
            curriculum_decisions=0 if evaluation else curriculum_decisions,
            reward=config["reward"],
            seed=seed,
        )

    return factory


def configure_loaded_model(model: RecurrentPPO, config: Dict[str, Any]) -> None:
    """Réapplique explicitement les paramètres scalaires après un chargement."""
    training = config["training"]
    if model.n_steps != int(training["n_steps"]):
        raise ValueError("n_steps du checkpoint incompatible avec la config")
    if model.batch_size != int(training["batch_size"]):
        raise ValueError("batch_size du checkpoint incompatible avec la config")
    learning_rate = float(training["learning_rate"])
    model.learning_rate = learning_rate
    model.lr_schedule = get_schedule_fn(learning_rate)
    model.n_epochs = int(training["n_epochs"])
    model.gamma = float(training["gamma"])
    model.gae_lambda = float(training["gae_lambda"])
    model.clip_range = get_schedule_fn(float(training["clip_range"]))
    model.ent_coef = float(training["ent_coef"])
    model.vf_coef = float(training["vf_coef"])
    model.max_grad_norm = float(training["max_grad_norm"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(BASE_DIR / "configs" / "aisub_v14.json"))
    parser.add_argument("--stage", choices=("scripted", "selfplay"), default="scripted")
    parser.add_argument("--run-name")
    parser.add_argument("--resume", help="checkpoint servant de point de départ")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    config = load_config(args.config)
    training = config["training"]
    model_cfg = config["model"]
    total_steps = int(training["total_steps"])
    n_envs = int(training["n_envs"])
    if n_envs < 1:
        raise ValueError("n_envs doit être positif")
    run_name = args.run_name or f"{config['name']}_{args.stage}"
    output_dir = BASE_DIR / "models_rl" / run_name
    league_dir = output_dir / "league"
    output_dir.mkdir(parents=True, exist_ok=True)
    league_dir.mkdir(parents=True, exist_ok=True)
    if args.stage == "selfplay" and args.resume:
        bootstrap = league_dir / "policy_bootstrap.zip"
        if not bootstrap.exists():
            shutil.copy2(args.resume, bootstrap)

    per_env_decisions = max(1, total_steps // n_envs)
    curriculum_decisions = int(
        per_env_decisions * float(config["env"].get("curriculum_fraction", 0.0)))
    effective = dict(config)
    effective["stage"] = args.stage
    effective["resume"] = args.resume
    effective["observation_version"] = control_spec(
        config["env"].get("agent_boat_type", "submarine"),
        config["env"].get("control_version"))[0]
    effective["curriculum_decisions_per_env"] = curriculum_decisions
    with (output_dir / "effective_config.json").open("w", encoding="utf-8") as handle:
        json.dump(effective, handle, indent=2, ensure_ascii=True)

    smoke_env = make_env(
        config, seed=int(training["seed"]), stage=args.stage,
        curriculum_decisions=curriculum_decisions, league_dir=league_dir)()
    check_env(smoke_env, warn=True)
    smoke_env.close()
    smoke_eval_env = make_env(
        config, seed=int(training["seed"]) + 100_000,
        stage="scripted", curriculum_decisions=0,
        league_dir=league_dir, evaluation=True)()
    smoke_eval_env.close()

    env_factories = [
        make_env(
            config, seed=int(training["seed"]) + index, stage=args.stage,
            curriculum_decisions=curriculum_decisions, league_dir=league_dir)
        for index in range(n_envs)
    ]
    vec_env = DummyVecEnv(env_factories) if n_envs == 1 else SubprocVecEnv(
        env_factories, start_method="forkserver")
    vec_env = VecMonitor(vec_env, filename=str(output_dir / "monitor.csv"))
    policy_kwargs = {
        "net_arch": list(model_cfg["net_arch"]),
        "lstm_hidden_size": int(model_cfg["lstm_hidden_size"]),
        "n_lstm_layers": int(model_cfg["n_lstm_layers"]),
    }
    if args.resume:
        model = RecurrentPPO.load(
            args.resume, env=vec_env, device=args.device,
            tensorboard_log=str(output_dir / "tensorboard"))
        configure_loaded_model(model, config)
    else:
        model = RecurrentPPO(
            "MlpLstmPolicy", vec_env,
            learning_rate=float(training["learning_rate"]),
            n_steps=int(training["n_steps"]),
            batch_size=int(training["batch_size"]),
            n_epochs=int(training["n_epochs"]),
            gamma=float(training["gamma"]),
            gae_lambda=float(training["gae_lambda"]),
            clip_range=float(training["clip_range"]),
            ent_coef=float(training["ent_coef"]),
            vf_coef=float(training["vf_coef"]),
            max_grad_norm=float(training["max_grad_norm"]),
            policy_kwargs=policy_kwargs,
            tensorboard_log=str(output_dir / "tensorboard"),
            seed=int(training["seed"]), device=args.device, verbose=1,
        )

    callbacks = [
        EntropyScheduleCallback(
            float(training["ent_coef"]), float(training["ent_coef_end"]), total_steps),
        CheckpointCallback(
            save_freq=max(1, int(training["checkpoint_every_steps"]) // n_envs),
            save_path=str(output_dir / "checkpoints"), name_prefix="policy"),
        MatchScoreEvalCallback(
            config, output_dir,
            every_steps=int(config["evaluation"]["every_steps"]),
            episodes=int(config["evaluation"]["episodes"]),
            seed=int(training["seed"]) + 100_000,
        ),
    ]
    if args.stage == "selfplay":
        callbacks.append(LeagueSnapshotCallback(
            league_dir,
            every_steps=int(config["league"]["snapshot_every_steps"]),
            keep_last=int(config["league"]["keep_last"]),
        ))
    try:
        model.learn(
            total_timesteps=total_steps, callback=callbacks,
            reset_num_timesteps=True, tb_log_name=run_name,
            progress_bar=True)
    finally:
        model.save(output_dir / "policy_final")
        vec_env.close()


if __name__ == "__main__":
    main()
