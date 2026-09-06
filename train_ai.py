"""Entraîne une politique récurrente contre les BT puis en self-play."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict

from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback, EvalCallback
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.utils import get_schedule_fn
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor

from rl_control import OBSERVATION_VERSION
from rl_env import SubmarineDuelEnv


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
        return SubmarineDuelEnv(
            map_name=eval_cfg["map_name"] if evaluation else env_cfg["map_name"],
            opponents=opponent_cfg.get("opponents"),
            opponent_ais=opponent_cfg.get("opponent_ais"),
            opponent_pool_dir=None if evaluation or stage == "scripted" else str(league_dir),
            self_play_probability=0.0 if evaluation or stage == "scripted" else float(
                config["league"]["self_play_probability"]),
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
    parser.add_argument("--config", default="configs/aisub_v14.json")
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
    effective["observation_version"] = OBSERVATION_VERSION
    effective["curriculum_decisions_per_env"] = curriculum_decisions
    with (output_dir / "effective_config.json").open("w", encoding="utf-8") as handle:
        json.dump(effective, handle, indent=2, ensure_ascii=True)

    smoke_env = make_env(
        config, seed=int(training["seed"]), stage=args.stage,
        curriculum_decisions=curriculum_decisions, league_dir=league_dir)()
    check_env(smoke_env, warn=True)
    smoke_env.close()

    env_factories = [
        make_env(
            config, seed=int(training["seed"]) + index, stage=args.stage,
            curriculum_decisions=curriculum_decisions, league_dir=league_dir)
        for index in range(n_envs)
    ]
    vec_env = DummyVecEnv(env_factories) if n_envs == 1 else SubprocVecEnv(
        env_factories, start_method="forkserver")
    vec_env = VecMonitor(vec_env, filename=str(output_dir / "monitor.csv"))
    eval_env = DummyVecEnv([
        make_env(
            config, seed=int(training["seed"]) + 100_000,
            stage="scripted", curriculum_decisions=0,
            league_dir=league_dir, evaluation=True)
    ])
    eval_env = VecMonitor(eval_env)

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
        EvalCallback(
            eval_env,
            best_model_save_path=str(output_dir / "best"),
            log_path=str(output_dir / "evaluation"),
            eval_freq=max(1, int(config["evaluation"]["every_steps"]) // n_envs),
            n_eval_episodes=int(config["evaluation"]["episodes"]),
            deterministic=True,
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
        eval_env.close()


if __name__ == "__main__":
    main()
