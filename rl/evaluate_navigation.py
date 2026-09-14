"""Evalue un navigateur sur des routes tenues hors entrainement."""

import argparse
import json
from pathlib import Path

from sb3_contrib import RecurrentPPO

from rl.navigation_env import NAVIGATION_ACTION_NVECS, NAVIGATION_OBS_DIM
from rl.train_navigation import (
    evaluate_navigation,
    load_config,
    navigation_gate_report,
    navigation_quality,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=500)
    parser.add_argument("--seed", type=int, default=311542)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    config = load_config(args.config)
    model = RecurrentPPO.load(args.model, device=args.device)
    if model.observation_space.shape != (NAVIGATION_OBS_DIM,):
        parser.error("observation incompatible avec la navigation")
    if tuple(int(value) for value in model.action_space.nvec) != tuple(NAVIGATION_ACTION_NVECS):
        parser.error("actions incompatibles avec la navigation")
    metrics = evaluate_navigation(model, config, args.episodes, args.seed)
    print(json.dumps({
        "model": str(args.model), "seed": args.seed,
        "quality": navigation_quality(metrics),
        "behavior": navigation_gate_report(config, metrics),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
