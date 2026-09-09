"""Mesure locale CPU de predict recurrent, hors simulation et reseau."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import random
import socket
import sys
from time import perf_counter_ns
from typing import Any, Sequence

import numpy as np

from rl.rl_runtime import RuntimeController, load_model, resolve_model_path


ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", help="Noms runtime rl_<run>[:checkpoint]")
    parser.add_argument("--boat-type", choices=("destroyer", "submarine"), default="destroyer")
    parser.add_argument("--map", default="testCombats")
    parser.add_argument("--seed", type=int, default=95000)
    parser.add_argument("--trajectory-steps", type=int, default=64)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--threads", type=int, help="Threads intra-op ; absent = defaut natif")
    parser.add_argument("--interop-threads", type=int, help="Absent = defaut natif")
    parser.add_argument("--output", type=Path, required=True, help="Nouveau JSON, jamais ecrase")
    args = parser.parse_args(argv)
    for name in ("trajectory_steps", "warmup", "samples", "threads", "interop_threads"):
        value = getattr(args, name)
        if value is not None and value < 1:
            parser.error(f"--{name.replace('_', '-')} doit etre positif")
    if not 0 <= args.seed < 2**32:
        parser.error("--seed doit etre dans [0, 2**32)")
    if not args.map or Path(args.map).name != args.map or args.map in {".", ".."}:
        parser.error("nom de carte invalide")
    map_file = "world.json" if args.map == "world" else f"world_{args.map}.json"
    if not (ROOT / "maps" / map_file).is_file():
        parser.error(f"carte absente: {args.map}")
    if args.output.exists():
        parser.error(f"sortie deja existante: {args.output}")
    try:
        for name in args.models:
            resolve_model_path(name)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    return args


def prepare_observations(model: Any, args: argparse.Namespace) -> tuple[list[np.ndarray], list[bool], str]:
    """Joue une courte trajectoire reelle avant toute mesure de latence."""
    from rl.rl_control import control_version_for_spaces
    from rl.rl_env import SubmarineDuelEnv

    control_version = control_version_for_spaces(
        args.boat_type, model.observation_space.shape[0], tuple(model.action_space.nvec))
    env = SubmarineDuelEnv(
        map_name=args.map, agent_boat_type=args.boat_type, control_version=control_version,
        opponent_ai="autosub", seed=args.seed)
    observations, starts = [], []
    controller = RuntimeController(model)
    try:
        observation, _ = env.reset(seed=args.seed)
        for _ in range(args.trajectory_steps):
            if not env.observation_space.contains(observation) or not np.isfinite(observation).all():
                raise ValueError("observation headless invalide")
            observations.append(observation.copy())
            starts.append(controller.episode_start)
            action, controller.state = controller.model.predict(
                observation, state=controller.state,
                episode_start=np.array([controller.episode_start], dtype=bool), deterministic=True)
            controller.episode_start = False
            observation, _, terminated, truncated, _ = env.step(action)
            if terminated or truncated:
                observation, _ = env.reset()
                controller = RuntimeController(model)
    finally:
        env.close()
    return observations, starts, control_version


def measure_predictions(model: Any, observations: Sequence[np.ndarray], starts: Sequence[bool],
                        count: int) -> list[float]:
    """Rejoue le corpus, avec un nouveau controleur a chaque debut d'episode."""
    if count < 1 or not observations or len(observations) != len(starts) or not starts[0]:
        raise ValueError("nombre de mesures ou corpus invalide")
    latencies = []
    controller = RuntimeController(model)
    for index in range(count):
        slot = index % len(observations)
        if starts[slot]:
            controller = RuntimeController(model)
        observation = observations[slot]
        start = perf_counter_ns()
        _, controller.state = controller.model.predict(
            observation, state=controller.state,
            episode_start=np.array([controller.episode_start], dtype=bool), deterministic=True)
        elapsed = perf_counter_ns() - start
        controller.episode_start = False
        latencies.append(elapsed / 1_000_000)
    return latencies


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    import torch

    native_threads = {"intra_op": torch.get_num_threads(), "inter_op": torch.get_num_interop_threads()}
    if args.threads is not None:
        torch.set_num_threads(args.threads)
    if args.interop_threads is not None:
        torch.set_num_interop_threads(args.interop_threads)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True)
    cpu_info = Path("/proc/cpuinfo")
    cpu = next((line.split(":", 1)[1].strip() for line in cpu_info.read_text().splitlines()
                if line.startswith("model name")), platform.processor()) if cpu_info.exists() else platform.processor()
    source_paths = set(ROOT.glob("*.py")) | set((ROOT / "rl").glob("*.py"))
    for pattern in ("maps/*.json", "boats/*.json", "bots/ai/*.json", "config/*.json"):
        source_paths.update(ROOT.glob(pattern))
    inputs = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(source_paths)}
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "local CPU predict only; not established representative of production",
        "excluded": ["model loading", "headless reset/trajectory", "observation building",
                     "action application", "simulation", "network", "multi-bot load", "human inspection"],
        "hostname": socket.gethostname(), "cpu": cpu, "logical_cpus": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "platform": platform.platform(), "python": sys.version, "executable": sys.executable,
        "packages": {name: version(name) for name in
                     ("torch", "numpy", "gymnasium", "stable-baselines3", "sb3-contrib")},
        "threads": {"native": native_threads, "intra_op": torch.get_num_threads(),
                    "inter_op": torch.get_num_interop_threads(),
                    "environment": {name: os.environ.get(name) for name in
                                    ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                     "NUMEXPR_NUM_THREADS", "PYTHONHASHSEED")}},
        "device": "cpu", "deterministic_predict": True,
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "arguments": {**vars(args), "output": str(args.output)},
        "environment": {"map": args.map, "seed": args.seed, "opponent": "autosub",
                        "opponent_boat_type": "submarine", "frame_skip": 5,
                        "physics_dt_s": 0.05, "spawn_m": [600, 2000], "max_physics_steps": 6000},
        "source_input_sha256": inputs,
        "protocol": "Separate warmup and measured replay from fresh RuntimeController; carry returned "
                    "LSTM state within each episode, reset state=None/episode_start=True at episode "
                    "and corpus boundaries. Only predict call/episode array/state assignment timed. "
                    "Throughput = samples / sum(predict seconds), not game throughput.",
        "results": [],
    }
    for name in args.models:
        path = resolve_model_path(name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        model = load_model(name, args.boat_type)
        observations, starts, control_version = prepare_observations(model, args)
        measure_predictions(model, observations, starts, args.warmup)
        latencies = measure_predictions(model, observations, starts, args.samples)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"modele modifie pendant le benchmark: {path}")
        report["results"].append({
            "model": name, "path": str(path.relative_to(ROOT)), "sha256": digest,
            "control_version": control_version, "observation_shape": list(observations[0].shape),
            "observation_sha256": hashlib.sha256(np.stack(observations).tobytes()).hexdigest(),
            "episode_starts": starts, "warmup": args.warmup, "samples": args.samples,
            "latency_ms": {"p50": float(np.percentile(latencies, 50)),
                           "p95": float(np.percentile(latencies, 95)),
                           "p99": float(np.percentile(latencies, 99)),
                           "max": max(latencies), "mean": float(np.mean(latencies))},
            "throughput_predictions_s": 1000 / float(np.mean(latencies)),
            "raw_latency_ms": latencies,
        })
    if any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
           for name, digest in inputs.items()):
        raise RuntimeError("entrees modifiees pendant le benchmark")
    report["source_inputs_unchanged"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    for result in report["results"]:
        print(json.dumps({key: result[key] for key in
                          ("model", "sha256", "latency_ms", "throughput_predictions_s")}))
    print(f"Archive: {args.output}")


if __name__ == "__main__":
    main()
