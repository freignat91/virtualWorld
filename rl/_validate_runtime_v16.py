"""Evalue deterministement un modele de mobilite avec le runtime isole v16."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from sb3_contrib import RecurrentPPO

from rl import mobility_env
from rl.bot_versions.v16 import geometry, navigable_path, rl_control, runtime, waypoints
from rl.train_mobility import (
    evaluate_mobility,
    load_config,
    mobility_gate_report,
    mobility_quality,
)


ROOT = Path(__file__).resolve().parent.parent
CASES = {
    "destroyer": {
        "config": ROOT / "rl/configs/aidest_mobility_runtime_v14.json",
        "model": ROOT / "rl/models_rl/aidest_mobility_runtime_v16/checkpoints/source_v15.zip",
        "seed": 533542,
        "alias": "rl_aidest_mobility_runtime_v16:source_v15",
        "report": ROOT / "rl/models_rl/aidest_mobility_runtime_v16/evaluation/segmented_runtime_v16_aligned_final500_seed533542.json",
    },
    "submarine": {
        "config": ROOT / "rl/configs/aisub_mobility_runtime_v14.json",
        "model": ROOT / "rl/models_rl/aisub_mobility_runtime_v16/checkpoints/source_v15.zip",
        "seed": 523542,
        "alias": "rl_aisub_mobility_runtime_v16:source_v15",
        "report": ROOT / "rl/models_rl/aisub_mobility_runtime_v16/evaluation/segmented_runtime_v16_aligned_final500_seed523542.json",
    },
}


def file_sha256(path: Path) -> str:
    """Calcule une empreinte de provenance sans modifier l'artefact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_v16_environment() -> None:
    """Force l'evaluateur partage a utiliser exclusivement le runtime v16."""
    mobility_env.geometry = geometry
    mobility_env.NavigablePathMetric = navigable_path.NavigablePathMetric
    mobility_env.DESTINATION_CLEARANCE_M = navigable_path.DESTINATION_CLEARANCE_M
    mobility_env.ROUTE_CLEARANCE_M = navigable_path.ROUTE_CLEARANCE_M
    mobility_env.ROUTE_NODE_MARGIN_M = navigable_path.ROUTE_NODE_MARGIN_M
    mobility_env.blocking_island_count = navigable_path.blocking_island_count
    mobility_env.plan_segmented_route = navigable_path.plan_segmented_route
    mobility_env.RLWaypointManager = waypoints.RLWaypointManager
    mobility_env.WAYPOINT_ISLAND_CLEARANCE_M = waypoints.WAYPOINT_ISLAND_CLEARANCE_M
    mobility_env.WAYPOINT_MAX_DISTANCE_M = waypoints.WAYPOINT_MAX_DISTANCE_M
    mobility_env.WAYPOINT_MIN_DISTANCE_M = waypoints.WAYPOINT_MIN_DISTANCE_M
    mobility_env.waypoint_distance_m = waypoints.waypoint_distance_m
    mobility_env.waypoint_reached = waypoints.waypoint_reached
    mobility_env.apply_action = rl_control.apply_action
    mobility_env.build_observation = rl_control.build_observation
    mobility_env.control_spec = rl_control.control_spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boat_type", choices=tuple(CASES))
    args = parser.parse_args()
    case = CASES[args.boat_type]
    report_path = case["report"]
    if report_path.exists():
        parser.error(f"rapport deja present: {report_path}")

    install_v16_environment()
    config = load_config(case["config"])
    episodes = int(config["evaluation"]["episodes"])
    model = RecurrentPPO.load(
        case["model"], device="cpu", custom_objects=runtime.model_custom_objects())
    runtime.configure_model(model, args.boat_type)
    episode_records = []
    progress_path = report_path.with_name(f"{report_path.stem}.progress.json")
    started_at = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()

    def record_progress(completed: int, total: int, info: dict) -> None:
        elapsed_seconds = time.monotonic() - started_monotonic
        mean_seconds = elapsed_seconds / completed
        remaining_seconds = mean_seconds * (total - completed)
        progress = {
            "status": "episodes_complete" if completed == total else "running",
            "boatType": args.boat_type,
            "startedUtc": started_at.isoformat(),
            "updatedUtc": datetime.now(timezone.utc).isoformat(),
            "completedEpisodes": completed,
            "totalEpisodes": total,
            "elapsedSeconds": elapsed_seconds,
            "meanSecondsPerEpisode": mean_seconds,
            "estimatedRemainingSeconds": remaining_seconds,
            "estimatedCompletionUtc": (
                datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)
            ).isoformat(),
            "lastOutcome": info.get("outcome"),
        }
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(progress, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        os.replace(temporary, progress_path)
        print(
            f"[{args.boat_type}] {completed}/{total} episodes; "
            f"ETA {progress['estimatedCompletionUtc']}", flush=True)

    metrics = evaluate_mobility(
        model, config, episodes, case["seed"], segmented_routes=True,
        episode_records=episode_records, episode_progress=record_progress)
    behavior = mobility_gate_report(config, metrics)
    report = {
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "scope": "deterministic CPU control only; no training, selection or promotion",
        "boatType": args.boat_type,
        "runtimeVersion": runtime.RUNTIME_VERSION,
        "model": case["alias"],
        "modelPath": str(case["model"].relative_to(ROOT)),
        "modelSha256": file_sha256(case["model"]),
        "configPath": str(case["config"].relative_to(ROOT)),
        "configSha256": file_sha256(case["config"]),
        "runtimeManifestSha256": file_sha256(
            ROOT / "rl/bot_versions/v16/manifest.json"),
        "protocol": {
            "episodes": episodes,
            "seed": case["seed"],
            "deterministic": True,
            "segmentedRoutes": True,
            "maxEpisodeSeconds": config["env"]["max_episode_seconds"],
            "finalWaypointRadiusMeters": waypoints.WAYPOINT_FINAL_REACHED_RADIUS_M,
            "intermediateWaypointRadiusMeters": (
                waypoints.WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M),
            "destinationClearanceMeters": navigable_path.DESTINATION_CLEARANCE_M,
            "intermediateClearanceMeters": navigable_path.ROUTE_CLEARANCE_M,
            "routeNodeMarginMeters": navigable_path.ROUTE_NODE_MARGIN_M,
            "directGoalDistanceMeters": navigable_path.ROUTE_LONG_SEGMENT_M,
            "routeStrategy": "safe_aligned_then_dijkstra_fallback",
            "routeCurriculum": config["env"]["route_curriculum"],
        },
        "qualityDiagnosticOnly": mobility_quality(metrics),
        "behavior": behavior,
        "episodeRecords": episode_records,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "boatType": args.boat_type,
        "report": str(report_path.relative_to(ROOT)),
        "passed": behavior["passed"],
        "failures": behavior["failures"],
        "metrics": metrics,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
