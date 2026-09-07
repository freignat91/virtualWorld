"""Évalue un modèle récurrent sur plusieurs cartes et adversaires."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sb3_contrib import RecurrentPPO

from rl_env import SubmarineDuelEnv


def evaluate(model: RecurrentPPO, map_name: str, boat_type: str, opponent_ai: str,
             episodes: int, seed: int, opponent_pool_dir: str | None = None) -> dict:
    env = SubmarineDuelEnv(
        map_name=map_name,
        opponents=[{"boat_type": boat_type, "ai": opponent_ai, "weight": 1.0}],
        opponent_pool_dir=opponent_pool_dir,
        self_play_probability=1.0 if opponent_pool_dir else 0.0,
        seed=seed,
    )
    outcomes: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    rewards = []
    try:
        for episode in range(episodes):
            observation, _ = env.reset(seed=seed + episode)
            state = None
            episode_start = np.ones((1,), dtype=bool)
            episode_reward = 0.0
            while True:
                action, state = model.predict(
                    observation, state=state,
                    episode_start=episode_start, deterministic=True)
                observation, reward, terminated, truncated, info = env.step(action)
                episode_reward += reward
                episode_start[:] = terminated or truncated
                if terminated or truncated:
                    outcomes[info.get("outcome", "unknown")] += 1
                    for key in ("weapons", "invalid_weapons", "lures", "contacts", "physics_steps"):
                        totals[key] += info.get(key, 0)
                    rewards.append(episode_reward)
                    break
    finally:
        env.close()
    return {
        "map": map_name,
        "opponent_kind": "policy" if opponent_pool_dir else "bt",
        "opponent_boat_type": "submarine" if opponent_pool_dir else boat_type,
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
        "mean_contacts": totals["contacts"] / max(1, episodes),
        "mean_physics_steps": totals["physics_steps"] / max(1, episodes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("--maps", default="combats,testCombats")
    parser.add_argument(
        "--opponents", default="submarine/autosub,destroyer/autodest",
        help="paires boat_type/ai séparées par des virgules")
    parser.add_argument(
        "--opponent-pools", default="",
        help="répertoires de checkpoints adversaires séparés par des virgules")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=10000)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    model = RecurrentPPO.load(args.model, device=args.device)
    results = []
    for map_name in filter(None, (value.strip() for value in args.maps.split(","))):
        for opponent in filter(None, (value.strip() for value in args.opponents.split(","))):
            if "/" in opponent:
                boat_type, opponent_ai = opponent.split("/", 1)
            else:
                boat_type, opponent_ai = "submarine", opponent
            results.append(evaluate(
                model, map_name, boat_type, opponent_ai, args.episodes, args.seed))
        for pool in filter(None, (value.strip() for value in args.opponent_pools.split(","))):
            pool_path = Path(pool)
            if not pool_path.is_dir() or not any(pool_path.glob("*.zip")):
                parser.error(f"pool de modèles adversaires invalide: {pool}")
            results.append(evaluate(
                model, map_name, "submarine", "autosub", args.episodes, args.seed, pool))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
