"""Entraîne une politique récurrente contre les BT puis en self-play."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import zipfile
from importlib.metadata import version
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple

from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.utils import get_schedule_fn
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecMonitor

from rl.evaluate_ai import evaluate as evaluate_policy
from rl.masked_recurrent_policy import (
    MASKED_CONTROL_VERSIONS,
    SituationMaskedMlpLstmPolicy,
)
from rl.rl_control import (
    DESTROYER_V5_OBSERVATION_VERSION,
    SUBMARINE_V3_OBSERVATION_VERSION,
    control_spec,
)
from rl.rl_env import SubmarineDuelEnv


BASE_DIR = Path(__file__).resolve().parent


def sampled_seed_offsets(config: Dict[str, Any]) -> Tuple[int, ...]:
    """Valide le protocole optionnel sans modifier les configurations historiques."""
    offsets = config['evaluation'].get('sampled_action_seed_offsets')
    if 'sampled_action_seed_offsets' not in config['evaluation']:
        return ()
    if (not isinstance(offsets, list) or len(offsets) < 2
            or any(type(x) is not int or x < 0 for x in offsets)
            or len(set(offsets)) != len(offsets)):
        raise ValueError('sampled_action_seed_offsets exige au moins deux entiers positifs ou nuls distincts')
    seed = config.get('training', {}).get('seed')
    episodes = config['evaluation'].get('episodes')
    if (type(seed) is not int or type(episodes) is not int or episodes <= 0
            or not 0 <= seed + 100_000 <= 2**63 - episodes - max(offsets)):
        raise ValueError('plage de graines du protocole echantillonne invalide')
    return tuple(offsets)


class EntropyScheduleCallback(BaseCallback):
    """Réduit linéairement l'entropie après une exploration initiale optionnelle."""

    def __init__(self, start: float, end: float, total_steps: int,
                 start_after_steps: int = 0) -> None:
        super().__init__()
        self.start = start
        self.end = end
        self.total_steps = max(1, total_steps)
        self.start_after_steps = max(0, start_after_steps)

    def _on_step(self) -> bool:
        decay_steps = max(1, self.total_steps - self.start_after_steps)
        progress = min(1.0, max(
            0.0, (self.num_timesteps - self.start_after_steps) / decay_steps))
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


BEHAVIOR_GATES = {
    "max_unacquired_weapon_fraction": ("unacquired_weapon_fraction", "max"),
    "max_invalid_weapon_request_fraction": ("invalid_weapon_request_fraction", "max"),
    "max_misaligned_weapon_fraction": ("misaligned_weapon_fraction", "max"),
    "max_stationary_unengaged_fraction": ("stationary_unengaged_fraction", "max"),
    "max_zero_weapon_episode_fraction": ("zero_weapon_episode_fraction", "max"),
    "min_mean_acquired_weapons": ("mean_acquired_weapons", "min"),
    "min_sonar_request_efficiency": ("sonar_request_efficiency", "min"),
}


def validate_behavior_gates(config: Dict[str, Any]) -> Dict[str, float]:
    """Valide les seuils optionnels qui conditionnent la selection d'un modele."""
    gates = config.get("evaluation", {}).get("behavior_gates") or {}
    if not isinstance(gates, dict) or set(gates) - set(BEHAVIOR_GATES):
        raise ValueError("evaluation.behavior_gates contient des criteres inconnus")
    validated = {}
    for key, value in gates.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0.0:
            raise ValueError(f"seuil comportemental invalide: {key}")
        if key != "min_mean_acquired_weapons" and value > 1.0:
            raise ValueError(f"fraction comportementale hors limites: {key}")
        validated[key] = float(value)
    return validated


def behavior_gate_report(config: Dict[str, Any], details: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Agrege les comportements selon les memes poids que le score de match."""
    gates = validate_behavior_gates(config)
    if not gates:
        return {"passed": True, "gates": {}, "metrics": {}, "failures": []}
    total_weight = sum(float(detail["selection_weight"]) for detail in details)
    if total_weight <= 0.0:
        raise ValueError("poids comportemental total nul")
    metric_names = {BEHAVIOR_GATES[key][0] for key in gates}
    metrics = {}
    for metric in metric_names:
        if any(metric not in detail for detail in details):
            raise ValueError(f"metrique comportementale absente: {metric}")
        metrics[metric] = sum(
            float(detail[metric]) * float(detail["selection_weight"])
            for detail in details) / total_weight
    failures = []
    for key, limit in gates.items():
        metric, direction = BEHAVIOR_GATES[key]
        value = metrics[metric]
        if direction == "max" and value > limit or direction == "min" and value < limit:
            failures.append(key)
    return {"passed": not failures, "gates": gates, "metrics": metrics,
            "failures": failures}


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
                 every_steps: int, episodes: int, seed: int, *, sampled: bool = False) -> None:
        super().__init__()
        self.config = config
        self.sampled = sampled
        self.action_seed_offsets = sampled_seed_offsets(config)
        if sampled and not self.action_seed_offsets:
            raise ValueError('evaluation echantillonnee sans graines configurees')
        self.output_dir = output_dir / 'sampled' if sampled else output_dir
        self.metric_prefix = 'eval_sampled' if sampled else 'eval'
        self.every_steps = int(every_steps)
        self.episodes = int(episodes)
        if self.every_steps <= 0:
            raise ValueError("evaluation.every_steps doit être positif")
        if self.episodes <= 0:
            raise ValueError("evaluation.episodes doit être positif")
        self.seed = int(seed)
        if self.action_seed_offsets and not 0 <= self.seed <= 2**63 - self.episodes - max(self.action_seed_offsets):
            raise ValueError('plage de graines des actions invalide')
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
        if self.sampled:
            selection_config['inference_mode'] = 'sampled'
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
        if not math.isfinite(self.best_score) or not 0 <= self.best_score <= 1:
            raise RuntimeError('score sauvegarde invalide')

    def _evaluate(self) -> Tuple[float, list[Dict[str, Any]]]:
        if not self.sampled:
            return self._evaluate_once()
        details = []
        for offset in self.action_seed_offsets:
            _, repeated = self._evaluate_once(offset)
            for result in repeated:
                result['selection_weight'] /= len(self.action_seed_offsets)
                details.append(result)
        return weighted_match_score([(r, r['selection_weight']) for r in details]), details

    def _evaluate_once(self, action_seed_offset: int = 0) -> Tuple[float, list[Dict[str, Any]]]:
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
        evaluation_options = {
            'deterministic': not self.sampled,
            'action_seed_offset': action_seed_offset,
            'include_episodes': bool(self.action_seed_offsets),
        }

        for opponent in opponents:
            weight = ((1.0 - fixed_probability) * float(opponent.get("weight", 1.0))
                      / bt_weight) if bt_weight > 0.0 else 0.0
            result = evaluate_policy(
                self.model, eval_cfg["map_name"], opponent["boat_type"], opponent["ai"],
                self.episodes, self.seed, agent_boat_type=agent_boat_type,
                agent_control_version=control_version, env_options=env_options,
                **evaluation_options)
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
                fixed_boat_type, control_version, env_options, **evaluation_options)
            result["selection_weight"] = fixed_probability
            result["match_score"] = match_score(result)
            weighted_results.append((result, fixed_probability))
            details.append(result)

        score = weighted_match_score(weighted_results)
        return score, details

    def _save_best(self, score: float, details: list[Dict[str, Any]],
                   behavior: Dict[str, Any]) -> None:
        best_dir = self.output_dir / "best"
        best_dir.mkdir(parents=True, exist_ok=True)
        temporary_model = best_dir / ".best_model.tmp.zip"
        self.model.save(temporary_model)
        model_digest = file_sha256(temporary_model)
        metadata = {
            "timesteps": self.num_timesteps,
            "inference_mode": "sampled" if self.sampled else "deterministic",
            "action_seed_offsets": list(self.action_seed_offsets) if self.sampled else [],
            "match_score": score,
            "selection_signature": self._selection_signature(),
            "model_sha256": model_digest,
            "opponents": details,
            "behavior": behavior,
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
        behavior = behavior_gate_report(self.config, details)
        history_dir = self.output_dir / "evaluation"
        history_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timesteps": self.num_timesteps,
            "inference_mode": "sampled" if self.sampled else "deterministic",
            "action_seed_offsets": list(self.action_seed_offsets) if self.sampled else [],
            "match_score": score,
            "opponents": details,
            "behavior": behavior,
        }
        with (history_dir / "match_scores.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.logger.record(f"{self.metric_prefix}/match_score", score)
        for index, detail in enumerate(details):
            self.logger.record(f"{self.metric_prefix}/opponent_{index}_match_score", detail["match_score"])
        for metric, value in behavior["metrics"].items():
            self.logger.record(f"{self.metric_prefix}/behavior_{metric}", value)
        print(f"{self.metric_prefix} match score at {self.num_timesteps} steps: {score:.2%}")
        if behavior["failures"]:
            print(f"Behavior gates failed: {', '.join(behavior['failures'])}")
        if behavior["passed"] and score > self.best_score:
            self._save_best(score, details, behavior)
            self.best_score = score
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
    sampled_seed_offsets(config)
    validate_behavior_gates(config)
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
    # Le buffer construit au chargement conserve ses propres paramètres GAE.
    model.rollout_buffer.gamma = model.gamma
    model.rollout_buffer.gae_lambda = model.gae_lambda
    model.clip_range = get_schedule_fn(float(training["clip_range"]))
    model.ent_coef = float(training["ent_coef"])
    model.vf_coef = float(training["vf_coef"])
    model.max_grad_norm = float(training["max_grad_norm"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(BASE_DIR / "configs" / "aisub_v14.json"))
    parser.add_argument("--stage", choices=("scripted", "selfplay"), default="scripted")
    parser.add_argument("--run-name")
    parser.add_argument("--resume", help="checkpoint source d'une nouvelle phase, pas une continuation exacte")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--stop-after-steps", type=int,
                        help="Limite cette execution avant bilan, sans raccourcir les calendriers configures")
    args = parser.parse_args()

    config = load_config(args.config)
    training = config["training"]
    model_cfg = config["model"]
    total_steps = int(training["total_steps"])
    if args.stop_after_steps is not None and not 0 < args.stop_after_steps <= total_steps:
        parser.error('--stop-after-steps doit etre positif et ne pas depasser training.total_steps')
    invocation_steps = args.stop_after_steps if args.stop_after_steps is not None else total_steps
    n_envs = int(training["n_envs"])
    if n_envs < 1:
        raise ValueError("n_envs doit être positif")
    run_name = args.run_name or f"{config['name']}_{args.stage}"
    output_dir = BASE_DIR / "models_rl" / run_name
    league_dir = output_dir / "league"
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError(f"repertoire de sortie non vide: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    league_dir.mkdir()
    source_path = Path(args.resume).resolve(strict=True) if args.resume else None
    source_sha256 = file_sha256(source_path) if source_path else None
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
    effective["requested_steps_this_invocation"] = invocation_steps
    effective["observation_version"] = control_spec(
        config["env"].get("agent_boat_type", "submarine"),
        config["env"].get("control_version"))[0]
    effective["curriculum_decisions_per_env"] = curriculum_decisions
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
    control_version = effective["observation_version"]
    policy = "MlpLstmPolicy"
    if control_version in MASKED_CONTROL_VERSIONS:
        policy = SituationMaskedMlpLstmPolicy
        policy_kwargs["control_version"] = control_version
    if args.resume:
        try:
            model = RecurrentPPO.load(
                source_path, env=vec_env, device=args.device,
                seed=int(training["seed"]), policy_kwargs=policy_kwargs,
                tensorboard_log=str(output_dir / "tensorboard"))
            configure_loaded_model(model, config)
            if file_sha256(source_path) != source_sha256:
                raise RuntimeError("checkpoint source modifie pendant le chargement")
        except BaseException:
            vec_env.close()
            raise
    else:
        model = RecurrentPPO(
            policy, vec_env,
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
    expected_control_version = effective["observation_version"]
    loaded_control_version = getattr(model, "rl_control_version", None)
    if (args.resume and expected_control_version in {
            SUBMARINE_V3_OBSERVATION_VERSION, DESTROYER_V5_OBSERVATION_VERSION}
            and loaded_control_version != expected_control_version):
        vec_env.close()
        raise ValueError(
            f"checkpoint incompatible avec {expected_control_version}: "
            f"{loaded_control_version or 'schema non declare'}")
    model.rl_control_version = expected_control_version

    provenance = {
        "phase": "warm_start" if source_path else "new_model",
        "checkpoint_source": str(source_path) if source_path else None,
        "checkpoint_sha256": source_sha256,
        "checkpoint_timesteps": model.num_timesteps,
        "planned_phase_steps": total_steps,
        "requested_steps_this_invocation": invocation_steps,
        "seed": model.seed,
        "policy_class": f"{type(model.policy).__module__}.{type(model.policy).__name__}",
        "policy_kwargs": model.policy_kwargs,
        "architecture": {
            "net_arch": model.policy.net_arch,
            "lstm_hidden_size": model.policy.lstm_actor.hidden_size,
            "n_lstm_layers": model.policy.lstm_actor.num_layers,
        },
        "device": str(model.device),
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in (
            "torch", "stable-baselines3", "sb3-contrib", "gymnasium", "numpy")},
    }
    try:
        for filename, content in (("effective_config.json", effective),
                                  ("provenance.json", provenance)):
            with (output_dir / filename).open("x", encoding="utf-8") as handle:
                json.dump(content, handle, indent=2, ensure_ascii=True)
    except BaseException:
        vec_env.close()
        raise

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
    if sampled_seed_offsets(config):
        callbacks.append(MatchScoreEvalCallback(
            config, output_dir,
            every_steps=int(config['evaluation']['every_steps']),
            episodes=int(config['evaluation']['episodes']),
            seed=int(training['seed']) + 100_000, sampled=True))
    if args.stage == "selfplay":
        callbacks.append(LeagueSnapshotCallback(
            league_dir,
            every_steps=int(config["league"]["snapshot_every_steps"]),
            keep_last=int(config["league"]["keep_last"]),
        ))
    try:
        model.learn(
            total_timesteps=invocation_steps, callback=callbacks,
            reset_num_timesteps=True, tb_log_name=run_name,
            progress_bar=True)
    finally:
        model.save(output_dir / "policy_final")
        vec_env.close()


if __name__ == "__main__":
    main()
