"""Évalue un modèle récurrent sur plusieurs cartes et adversaires."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sb3_contrib import RecurrentPPO

from rl.rl_control import control_version_for_spaces
from rl.rl_env import PHYSICS_DT, SubmarineDuelEnv
from rl.rng import preserve_rng_state


def artifact_manifest(path: Path) -> dict:
    """Identifie les octets d'un artefact avant l'evaluation."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "sha256": digest.hexdigest()}


@preserve_rng_state()
def evaluate(model: RecurrentPPO, map_name: str, boat_type: str, opponent_ai: str,
             episodes: int, seed: int, opponent_pool_dir: str | None = None,
             agent_boat_type: str = "submarine",
             opponent_pool_boat_type: str = "submarine",
             agent_control_version: str | None = None,
             env_options: dict | None = None,
             include_episodes: bool = False) -> dict:
    options = dict(env_options or {})
    env = SubmarineDuelEnv(
        map_name=map_name,
        agent_boat_type=agent_boat_type,
        control_version=agent_control_version,
        opponents=[{"boat_type": boat_type, "ai": opponent_ai, "weight": 1.0}],
        fixed_opponent_pool_dir=opponent_pool_dir,
        fixed_opponent_boat_type=opponent_pool_boat_type,
        fixed_policy_probability=1.0 if opponent_pool_dir else 0.0,
        seed=seed,
        **options,
    )
    outcomes: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    rewards = []
    episode_results = []
    try:
        if include_episodes:
            effective_env = {key: getattr(env, key) for key in (
                "map_name", "agent_boat_type", "control_version", "opponents",
                "self_play_probability", "fixed_opponent_boat_type",
                "fixed_policy_probability", "max_physics_steps", "frame_skip",
                "spawn_min_m", "spawn_max_m", "curriculum_start_min_m",
                "curriculum_start_max_m", "curriculum_decisions")}
            effective_env.update(reward=dict(env.reward_cfg), physics_dt=PHYSICS_DT)
            for key in ("opponent_pool_dir", "fixed_opponent_pool_dir"):
                directory = getattr(env, key)
                effective_env[key] = str(directory.resolve()) if directory else None
            opponent_paths = (
                env._pool_paths(Path(opponent_pool_dir)) if opponent_pool_dir else
                (Path(__file__).resolve().parent.parent / "bots" / "ai" / f"{opponent_ai}.json",))
            opponent_manifest = [artifact_manifest(path) for path in opponent_paths]
        for episode in range(episodes):
            observation, _ = env.reset(seed=seed + episode)
            state = None
            episode_start = np.ones((1,), dtype=bool)
            episode_reward = 0.0
            decisions = 0
            while True:
                action, state = model.predict(
                    observation, state=state,
                    episode_start=episode_start, deterministic=True)
                observation, reward, terminated, truncated, info = env.step(action)
                episode_reward += reward
                decisions += 1
                episode_start[:] = terminated or truncated
                if terminated or truncated:
                    outcomes[info.get("outcome", "unknown")] += 1
                    for key in (
                            "weapons", "invalid_weapons", "lures", "sonars",
                            "invalid_sonars", "contacts", "physics_steps",
                            "acoustic_torpedoes", "autonomous_torpedoes",
                            "cannon_shots", "grenades", "mines", "invalid_mines",
                            "surface_mines", "bottom_mines", "suspended_mines"):
                        totals[key] += info.get(key, 0)
                    rewards.append(episode_reward)
                    if include_episodes:
                        episode_results.append({
                            **info, "seed": seed + episode,
                            "length": decisions, "reward": float(episode_reward),
                            "terminated": bool(terminated), "truncated": bool(truncated),
                        })
                    break
    finally:
        env.close()
    result = {
        "map": map_name,
        "agent_boat_type": agent_boat_type,
        "control_version": agent_control_version,
        "opponent_kind": "policy" if opponent_pool_dir else "bt",
        "opponent_boat_type": opponent_pool_boat_type if opponent_pool_dir else boat_type,
        "opponent_ai": None if opponent_pool_dir else opponent_ai,
        "opponent_pool": opponent_pool_dir,
        "episodes": episodes,
        "wins": outcomes["win"],
        "losses": outcomes["loss"],
        "draws": outcomes["draw"],
        "win_rate": outcomes["win"] / max(1, episodes),
        "mean_reward": float(np.mean(rewards)) if rewards else 0.0,
        "mean_weapons": totals["weapons"] / max(1, episodes),
        "mean_invalid_weapons": totals["invalid_weapons"] / max(1, episodes),
        "mean_lures": totals["lures"] / max(1, episodes),
        "mean_sonars": totals["sonars"] / max(1, episodes),
        "mean_invalid_sonars": totals["invalid_sonars"] / max(1, episodes),
        "mean_acoustic_torpedoes": totals["acoustic_torpedoes"] / max(1, episodes),
        "mean_autonomous_torpedoes": totals["autonomous_torpedoes"] / max(1, episodes),
        "mean_cannon_shots": totals["cannon_shots"] / max(1, episodes),
        "mean_grenades": totals["grenades"] / max(1, episodes),
        "mean_mines": totals["mines"] / max(1, episodes),
        "mean_invalid_mines": totals["invalid_mines"] / max(1, episodes),
        "mean_surface_mines": totals["surface_mines"] / max(1, episodes),
        "mean_bottom_mines": totals["bottom_mines"] / max(1, episodes),
        "mean_suspended_mines": totals["suspended_mines"] / max(1, episodes),
        "mean_contacts": totals["contacts"] / max(1, episodes),
        "mean_physics_steps": totals["physics_steps"] / max(1, episodes),
    }
    if include_episodes:
        result.update(seed=seed, env=effective_env,
                      opponent_manifest=opponent_manifest,
                      episode_results=episode_results)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument(
        "--agent-boat-type", choices=("submarine", "destroyer"))
    parser.add_argument("--config", type=Path,
                        help="config d'entrainement: agent, controle, reward, timing et spawn final; cartes/adversaires via CLI")
    parser.add_argument("--report", action="store_true",
                        help="rapport JSON detaille sur stdout (sinon agregats historiques)")
    parser.add_argument("--maps", default="combats,testCombats")
    parser.add_argument(
        "--opponents", default="submarine/autosub,destroyer/autodest",
        help="paires boat_type/ai séparées par des virgules")
    parser.add_argument(
        "--opponent-pools", default="",
        help="répertoires de checkpoints adversaires séparés par des virgules")
    parser.add_argument(
        "--opponent-pool-boat-type", choices=("submarine", "destroyer"),
        default="submarine")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=10000)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    env_options = {}
    configured_control = None
    config_manifest = None
    if args.config:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
            env_cfg = config["env"]
            if not isinstance(env_cfg, dict) or not isinstance(config["reward"], dict):
                raise ValueError("env et reward doivent etre des objets")
            configured_agent = env_cfg.get("agent_boat_type", "submarine")
            if configured_agent not in ("submarine", "destroyer"):
                raise ValueError(f"type de bateau RL inconnu: {configured_agent}")
            if args.agent_boat_type and args.agent_boat_type != configured_agent:
                raise ValueError("agent CLI incompatible avec la config")
            args.agent_boat_type = configured_agent
            configured_control = env_cfg.get("control_version")
            env_options = {key: env_cfg[key] for key in (
                "frame_skip", "max_physics_steps", "spawn_min_m", "spawn_max_m")}
            env_options["reward"] = config["reward"]
            if args.report:
                config_manifest = artifact_manifest(args.config)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f"config invalide: {exc}")
    args.agent_boat_type = args.agent_boat_type or "submarine"
    model_manifest = None
    if args.report:
        model_path = Path(args.model)
        if not model_path.exists():
            model_path = Path(str(model_path) + ".zip")
        model_manifest = artifact_manifest(model_path)
    model = RecurrentPPO.load(args.model, device=args.device)
    observation_dim = int((model.observation_space.shape or (0,))[0])
    model_nvec = tuple(int(value) for value in getattr(model.action_space, "nvec", ()))
    try:
        control_version = control_version_for_spaces(
            args.agent_boat_type, observation_dim, model_nvec)
        if configured_control is not None and configured_control != control_version:
            raise ValueError("controle du modele incompatible avec la config")
    except ValueError as exc:
        parser.error(str(exc))
    results = []
    for map_name in filter(None, (value.strip() for value in args.maps.split(","))):
        for opponent in filter(None, (value.strip() for value in args.opponents.split(","))):
            if "/" in opponent:
                boat_type, opponent_ai = opponent.split("/", 1)
            else:
                boat_type, opponent_ai = "submarine", opponent
            results.append(evaluate(
                model, map_name, boat_type, opponent_ai, args.episodes, args.seed,
                agent_boat_type=args.agent_boat_type,
                agent_control_version=control_version,
                env_options=env_options, include_episodes=args.report))
        for pool in filter(None, (value.strip() for value in args.opponent_pools.split(","))):
            pool_path = Path(pool)
            if not pool_path.is_dir() or not any(pool_path.glob("*.zip")):
                parser.error(f"pool de modèles adversaires invalide: {pool}")
            results.append(evaluate(
                model, map_name, "submarine", "autosub", args.episodes, args.seed, pool,
                args.agent_boat_type, args.opponent_pool_boat_type, control_version,
                env_options=env_options, include_episodes=args.report))
    output = ({"report_version": 1, "seed": args.seed, "deterministic": True,
               "model": model_manifest, "config": config_manifest, "results": results}
              if args.report else results)
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
