"""Évalue un modèle récurrent sur plusieurs cartes et adversaires BT."""

from __future__ import annotations

import argparse
import json
from collections import Counter

import numpy as np
from sb3_contrib import RecurrentPPO

from rl_env import SubmarineDuelEnv


def evaluate(model: RecurrentPPO, map_name: str, opponent: str,
             episodes: int, seed: int) -> dict:
    env = SubmarineDuelEnv(map_name=map_name, opponent_ai=opponent, seed=seed)
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
        "opponent": opponent,
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
    parser.add_argument("--opponents", default="autosub,default")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=10000)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    model = RecurrentPPO.load(args.model, device=args.device)
    results = []
    for map_name in filter(None, (value.strip() for value in args.maps.split(","))):
        for opponent in filter(None, (value.strip() for value in args.opponents.split(","))):
            results.append(evaluate(model, map_name, opponent, args.episodes, args.seed))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
