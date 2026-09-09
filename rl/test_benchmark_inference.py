"""Validation du benchmark et du transport d'etat recurrent, sans checkpoint."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from rl.benchmark_inference import measure_predictions, parse_args


class BenchmarkInferenceTests(unittest.TestCase):
    def test_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
                "rl.benchmark_inference.resolve_model_path", return_value=Path("model.zip")):
            base = ["rl_example", "--output", str(Path(directory) / "new.json")]
            args = parse_args(base)
            self.assertGreaterEqual(args.warmup, 100)
            self.assertGreaterEqual(args.samples, 1000)
            self.assertIsNone(args.threads)
            self.assertIsNone(args.interop_threads)
            for option, value in (("--warmup", "0"), ("--samples", "-1"),
                                  ("--threads", "0"), ("--interop-threads", "-2"),
                                  ("--trajectory-steps", "0"), ("--seed", "-1"),
                                  ("--seed", str(2**32)), ("--map", "../testCombats"),
                                  ("--map", "missing_map"), ("--samples", "1.5")):
                with self.subTest(option=option, value=value), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parse_args(base + [option, value])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["rl_example", "--output", directory])
            self.assertEqual(parse_args(base + ["--warmup", "1", "--samples", "2"]).samples, 2)

    def test_missing_model(self) -> None:
        with patch("rl.benchmark_inference.resolve_model_path", side_effect=FileNotFoundError("missing")):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["rl_missing", "--output", "/tmp/benchmark_missing_model_test.json"])

    def test_recurrent_state_and_timing(self) -> None:
        calls = []

        class Model:
            def predict(self, observation, *, state, episode_start, deterministic):
                calls.append((int(observation[0]), state, episode_start.tolist(), deterministic))
                return np.array([0]), (state or 0) + 1

        observations = [np.array([value], dtype=np.float32) for value in range(3)]
        with patch("rl.benchmark_inference.perf_counter_ns", side_effect=range(0, 14_000_000, 1_000_000)):
            result = measure_predictions(Model(), observations, [True, False, True], 7)
        self.assertEqual(result, [1.0] * 7)
        self.assertEqual(calls, [(0, None, [True], True), (1, 1, [False], True),
                                 (2, None, [True], True), (0, None, [True], True),
                                 (1, 1, [False], True), (2, None, [True], True),
                                 (0, None, [True], True)])
        for obs, starts, count in (([], [], 1), (observations, [True], 1),
                                    (observations, [False] * 3, 1),
                                    (observations, [True] * 3, 0)):
            with self.assertRaises(ValueError):
                measure_predictions(Model(), obs, starts, count)


if __name__ == "__main__":
    unittest.main()
