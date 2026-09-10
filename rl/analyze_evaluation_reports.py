"""Valide les rapports independants et compare les scores par graines appariees."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, variance
from typing import Any


SCORES = {"win": 1.0, "loss": 0.0, "draw": 0.5}


def validate_report(report: dict[str, Any], episodes: int) -> None:
    """Refuse les identites alterees, graines manquantes et agregats incoherents."""
    if report["report_version"] != 1 or report["deterministic"] is not True:
        raise ValueError("rapport non deterministe ou version inconnue")
    artifacts = [report["model"], report["config"]]
    seen = set()
    for result in report["results"]:
        artifacts.extend(result["opponent_manifest"])
        if len(result["opponent_manifest"]) != 1:
            raise ValueError("un seul adversaire fige par strate est requis")
        opponent = result["opponent_manifest"][0]
        key = (result["map"], opponent["sha256"], result["seed"])
        if key in seen:
            raise ValueError("strate dupliquee")
        seen.add(key)
        rows = result["episode_results"]
        if (result["episodes"] != episodes or len(rows) != episodes
                or result["seed"] != report["seed"]
                or [row["seed"] for row in rows] != list(range(report["seed"], report["seed"] + episodes))):
            raise ValueError("nombre ou serie de graines invalide")
        expected_opponent = (
            f"policy:{result['opponent_boat_type']}/{Path(opponent['path']).name}"
            if result["opponent_kind"] == "policy" else
            f"bt:{result['opponent_boat_type']}/{result['opponent_ai']}")
        for row in rows:
            if (row["outcome"] not in SCORES or row["opponent"] != expected_opponent
                    or not (row["terminated"] or row["truncated"])
                    or not 0 < row["physics_steps"] <= result["env"]["max_physics_steps"]
                    or row["length"] <= 0 or not math.isfinite(row["reward"])):
                raise ValueError("episode invalide ou adversaire inattendu")
        counts = Counter(row["outcome"] for row in rows)
        if any(result[field] != counts[outcome] for field, outcome in
               (("wins", "win"), ("losses", "loss"), ("draws", "draw"))):
            raise ValueError("WLD incoherent")
        if not math.isclose(result["mean_reward"], mean(row["reward"] for row in rows), abs_tol=1e-9):
            raise ValueError("reward moyenne incoherente")
    if not seen:
        raise ValueError("rapport vide")
    for artifact in artifacts:
        with Path(artifact["path"]).open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != artifact["sha256"]:
            raise ValueError(f"empreinte modifiee: {artifact['path']}")


def paired_difference(strata: list[list[float]]) -> dict[str, Any]:
    """Poids fixes egaux; variance estimee separement dans chaque strate."""
    if not strata or any(len(values) < 2 for values in strata):
        raise ValueError("au moins deux paires par strate sont requises")
    delta = mean(mean(values) for values in strata)
    se = math.sqrt(sum(variance(values) / len(values) for values in strata)) / len(strata)
    return {"pairs": sum(map(len, strata)), "difference_pp": 100 * delta,
            "ci95_pp": [100 * (delta - 1.96 * se), 100 * (delta + 1.96 * se)]}


def analyze(reports: list[dict[str, Any]], baseline: str, episodes: int) -> dict[str, Any]:
    groups: dict[str, dict[tuple, dict]] = {}
    paths = {}
    config_hashes = set()
    for report in reports:
        validate_report(report, episodes)
        model = report["model"]["sha256"]
        paths[model] = report["model"]["path"]
        config_hashes.add(report["config"]["sha256"])
        group = groups.setdefault(model, {})
        for result in report["results"]:
            key = (result["map"], result["opponent_manifest"][0]["sha256"], result["seed"])
            if key in group:
                raise ValueError("rapport duplique")
            group[key] = result
    if len(config_hashes) != 1 or baseline not in groups:
        raise ValueError("configurations incompatibles ou reference absente")
    reference = groups[baseline]
    output = {"method": "equal fixed series/opponent weights; paired seed-clustered SE across opponents; normal 95% CI",
              "baseline_sha256": baseline, "models": []}
    for model, group in groups.items():
        if group.keys() != reference.keys():
            raise ValueError("strates non appariees")
        rows = []
        differences = []
        clusters: dict[int, dict[tuple, list[float]]] = {}
        by_opponent: dict[str, list] = {}
        for key in sorted(group):
            result, ref = group[key], reference[key]
            if result["env"] != ref["env"]:
                raise ValueError("environnements non comparables")
            values = [SCORES[row["outcome"]] - SCORES[base["outcome"]]
                      for row, base in zip(result["episode_results"], ref["episode_results"], strict=True)]
            differences.append(values)
            clusters.setdefault(key[2], {})[key[:2]] = values
            opponent = result["episode_results"][0]["opponent"]
            by_opponent.setdefault(opponent, []).append(values)
            rows.append({"opponent": opponent, "seed": key[2], "episodes": episodes,
                         "wins": result["wins"], "losses": result["losses"], "draws": result["draws"],
                         "score_pct": 100 * (result["wins"] + 0.5 * result["draws"]) / episodes,
                         "relative_to_baseline": paired_difference([values])})
        clustered = seed_clustered_difference(clusters)
        output["models"].append({"path": paths[model], "sha256": model, "strata": rows,
                                 "score_pct": mean(row["score_pct"] for row in rows),
                                 "relative_to_baseline": clustered,
                                 "independent_strata_diagnostic": paired_difference(differences),
                                 "opponent_differences": {key: paired_difference(values)
                                                          for key, values in by_opponent.items()}})
    return output


def seed_clustered_difference(series: dict[int, dict[tuple, list[float]]]) -> dict[str, Any]:
    """Conserve la covariance entre adversaires partageant une meme graine."""
    if not series:
        raise ValueError("series absentes")
    opponents = next(iter(series.values())).keys()
    seen = set()
    strata = []
    for start, group in sorted(series.items()):
        if not opponents or group.keys() != opponents:
            raise ValueError("adversaires non apparies entre series")
        sizes = {len(values) for values in group.values()}
        if len(sizes) != 1 or min(sizes) < 2:
            raise ValueError("graines non appariees")
        seeds = set(range(start, start + next(iter(sizes))))
        if seeds & seen:
            raise ValueError("series de graines chevauchantes")
        seen.update(seeds)
        strata.append([mean(values) for values in zip(*group.values(), strict=True)])
    result = paired_difference(strata)
    result["seed_clusters"] = result.pop("pairs")
    result["match_pairs"] = result["seed_clusters"] * len(opponents)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--baseline", required=True, help="SHA-256 du modele de reference")
    parser.add_argument("--episodes", type=int, default=100)
    args = parser.parse_args()
    try:
        reports = [json.loads(path.read_text()) for path in args.reports]
        print(json.dumps(analyze(reports, args.baseline, args.episodes), indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
