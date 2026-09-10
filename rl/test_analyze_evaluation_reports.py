"""Regressions de validation et de variance stratifiee appariee."""

import copy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rl.analyze_evaluation_reports import analyze, paired_difference, seed_clustered_difference, validate_report


class AnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "model.zip"
        path.write_bytes(b"fixture")
        artifact = {"path": str(path), "sha256": hashlib.sha256(b"fixture").hexdigest()}
        self.report = {"report_version": 1, "deterministic": True, "seed": 10,
                       "model": artifact, "config": artifact, "results": [{
                           "map": "testCombats", "opponent_manifest": [artifact], "seed": 10,
                           "episodes": 2, "opponent_kind": "policy", "opponent_boat_type": "submarine",
                           "wins": 1, "losses": 0, "draws": 1, "mean_reward": 0,
                           "env": {"max_physics_steps": 6000}, "episode_results": [
                               {"seed": seed, "outcome": outcome, "reward": 0, "length": 1,
                                "physics_steps": 5, "terminated": True, "truncated": False,
                                "opponent": "policy:submarine/model.zip"}
                               for seed, outcome in ((10, "win"), (11, "draw"))]}]}

    def test_valid_and_self_comparison(self) -> None:
        validate_report(self.report, 2)
        result = analyze([self.report], self.report["model"]["sha256"], 2)
        self.assertEqual(result["models"][0]["score_pct"], 75)
        self.assertEqual(result["models"][0]["relative_to_baseline"]["ci95_pp"], [0, 0])

    def test_reject_invalid_reports(self) -> None:
        for field, value in (("seed", 11), ("outcome", "unknown"), ("opponent", "wrong"),
                             ("reward", float("nan")), ("physics_steps", 6001)):
            report = copy.deepcopy(self.report)
            report["results"][0]["episode_results"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_report(report, 2)
        for field, value in (("episodes", 100), ("wins", 0), ("episode_results", [])):
            report = copy.deepcopy(self.report)
            report["results"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_report(report, 2)
        with self.assertRaises(ValueError):
            analyze([self.report, self.report], self.report["model"]["sha256"], 2)
        Path(self.report["model"]["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            validate_report(self.report, 2)

    def test_fixed_stratum_variance(self) -> None:
        result = paired_difference([[1, 1], [-1, -1]])
        self.assertEqual(result["ci95_pp"], [0, 0])
        result = paired_difference([[0, 1], [0, 1]])
        self.assertEqual(result["difference_pp"], 50)
        self.assertAlmostEqual(result["ci95_pp"][1], 50 + 196 * (0.125 ** 0.5))
        with self.assertRaises(ValueError):
            paired_difference([[1]])

    def test_seed_clusters_preserve_covariance(self) -> None:
        result = seed_clustered_difference({10: {("a",): [0, 1], ("b",): [0, 1]}})
        self.assertEqual(result["seed_clusters"], 2)
        self.assertEqual(result["match_pairs"], 4)
        self.assertEqual(result["ci95_pp"], [-48, 148])
        result = seed_clustered_difference({10: {("a",): [0, 1], ("b",): [1, 0]}})
        self.assertEqual(result["ci95_pp"], [50, 50])
        result = seed_clustered_difference({10: {("a",): [1, 1]}, 20: {("a",): [-1, -1]}})
        self.assertEqual(result["ci95_pp"], [0, 0])

    def test_reject_invalid_seed_clusters(self) -> None:
        for series in ({}, {10: {}}, {10: {("a",): [1]}},
                       {10: {("a",): [0, 1], ("b",): [0]}},
                       {10: {("a",): [0, 1]}, 11: {("a",): [0, 1]}},
                       {10: {("a",): [0, 1]}, 20: {("b",): [0, 1]}}):
            with self.subTest(series=series), self.assertRaises(ValueError):
                seed_clustered_difference(series)


if __name__ == "__main__":
    unittest.main()
