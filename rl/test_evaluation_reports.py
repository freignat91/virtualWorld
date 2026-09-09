"""Regression des rapports opt-in sans modification de la simulation."""

import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from sb3_contrib import RecurrentPPO

from rl.evaluate_ai import artifact_manifest, evaluate, main
from rl.rl_env import DEFAULT_REWARD, SubmarineDuelEnv


class EvaluationReportsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.model = SimpleNamespace(
            observation_space=SimpleNamespace(shape=(32,)),
            action_space=SimpleNamespace(nvec=[5, 5, 5, 3, 2]),
            predict=Mock(return_value=(np.array([2, 1, 0, 0, 0]), None)))
        self.options = {"max_physics_steps": 6, "frame_skip": 2,
                        "spawn_min_m": 700, "spawn_max_m": 800,
                        "reward": {"decision_cost": -0.125}}

    def run_cli(self, *args: str) -> object:
        output = io.StringIO()
        with patch("sys.argv", ["evaluate_ai", *args]), \
                patch("rl.evaluate_ai.RecurrentPPO.load", return_value=self.model), \
                redirect_stdout(output):
            main()
        return json.loads(output.getvalue())

    def test_real_episodes_preserve_aggregates_and_repeat(self) -> None:
        args = (self.model, "testCombats", "submarine", "autosub", 2, 123)
        plain = evaluate(*args, env_options=self.options)
        report = evaluate(*args, env_options=self.options, include_episodes=True)
        self.assertEqual(plain, {key: report[key] for key in plain})
        self.assertNotIn("episode_results", plain)
        self.assertNotIn("env", plain)
        self.assertNotIn("seed", plain)
        self.assertEqual(report, evaluate(
            *args, env_options=self.options, include_episodes=True))
        self.assertEqual(report["seed"], 123)
        self.assertEqual(report["env"]["reward"],
                         {**DEFAULT_REWARD, "decision_cost": -0.125})
        for key in ("max_physics_steps", "frame_skip", "spawn_min_m", "spawn_max_m"):
            self.assertEqual(report["env"][key], self.options[key])
        self.assertEqual(report["env"]["control_version"], "sub_duel_v1")
        for index, episode in enumerate(report["episode_results"]):
            self.assertEqual(episode["seed"], 123 + index)
            self.assertEqual(episode["length"], 3)
            self.assertEqual(episode["physics_steps"], 6)
            self.assertEqual(episode["outcome"], "draw")
            self.assertTrue(episode["truncated"])
            self.assertFalse(episode["terminated"])
            self.assertIn("agent_hp", episode)
            self.assertIn("opponent_hp", episode)
            self.assertIn("invalid_weapons", episode)
            self.assertEqual(episode["opponent"], "bt:submarine/autosub")
        manifest = report["opponent_manifest"][0]
        self.assertEqual(manifest, artifact_manifest(Path("bots/ai/autosub.json")))
        json.dumps(report, allow_nan=False)

    def test_terminal_outcomes_and_recurrent_reset(self) -> None:
        endings = []
        for outcome, hp in (("win", (50, 0)), ("loss", (0, 70)), ("draw", (0, 0))):
            endings.append((np.zeros(32), 2.5, True, False, {
                "outcome": outcome, "agent_hp": hp[0], "opponent_hp": hp[1],
                "physics_steps": 1, "weapons": 2}))
        with patch.object(SubmarineDuelEnv, "step", side_effect=endings), \
                patch.object(SubmarineDuelEnv, "close") as close:
            report = evaluate(self.model, "testCombats", "submarine", "autosub",
                              3, 10, include_episodes=True)
        close.assert_called_once()
        self.assertEqual([row["outcome"] for row in report["episode_results"]],
                         ["win", "loss", "draw"])
        self.assertEqual((report["wins"], report["losses"], report["draws"]), (1, 1, 1))
        self.assertEqual(report["mean_reward"], 2.5)
        self.assertEqual(report["mean_weapons"], 2)
        for call in self.model.predict.call_args_list:
            self.assertIsNone(call.kwargs["state"])
            self.assertTrue(call.kwargs["deterministic"])

    def test_report_failure_closes_environment(self) -> None:
        with patch("rl.evaluate_ai.artifact_manifest", side_effect=OSError("missing")), \
                patch.object(SubmarineDuelEnv, "close") as close:
            with self.assertRaises(OSError):
                evaluate(self.model, "testCombats", "submarine", "autosub",
                         1, 10, include_episodes=True)
        close.assert_called_once()

    def test_pool_manifest_matches_selectable_checkpoints(self) -> None:
        with TemporaryDirectory() as directory:
            pool = Path(directory)
            for name in ("b.zip", "a.zip", ".partial.zip", "ignored.txt"):
                (pool / name).write_bytes(name.encode())
            report = evaluate(self.model, "testCombats", "submarine", "autosub",
                              0, 10, directory, include_episodes=True)
            self.assertEqual(report["opponent_manifest"],
                             [artifact_manifest(pool / name) for name in ("a.zip", "b.zip")])
            self.assertEqual(report["episode_results"], [])

    def test_cli_default_interface(self) -> None:
        result = self.run_cli("unused.zip", "--episodes", "0")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 4)
        self.assertTrue(all("episode_results" not in row for row in result))

    def test_real_checkpoint_opponent_is_identified(self) -> None:
        env = SubmarineDuelEnv(max_physics_steps=2)
        self.addCleanup(env.close)
        model = RecurrentPPO(
            "MlpLstmPolicy", env, n_steps=8, batch_size=8, device="cpu", seed=13,
            policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16})
        with TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "opponent.zip"
            model.save(checkpoint)
            report = evaluate(model, "testCombats", "submarine", "autosub",
                              1, 123, directory, env_options=self.options,
                              include_episodes=True)
            self.assertEqual(report["opponent_manifest"], [artifact_manifest(checkpoint)])
            self.assertEqual(report["episode_results"][0]["opponent"],
                             "policy:submarine/opponent.zip")
            self.assertEqual(report, evaluate(
                model, "testCombats", "submarine", "autosub", 1, 123, directory,
                env_options=self.options, include_episodes=True))

    def test_cli_report_config_and_model_suffix(self) -> None:
        with TemporaryDirectory() as directory:
            model = Path(directory) / "model.zip"
            model.write_bytes(b"model bytes")
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"env": {
                **{key: value for key, value in self.options.items() if key != "reward"},
                "agent_boat_type": "submarine", "control_version": "sub_duel_v1"},
                "reward": self.options["reward"]}), encoding="utf-8")
            report = self.run_cli(str(model.with_suffix("")), "--report", "--config",
                                  str(config), "--maps", "testCombats", "--opponents",
                                  "submarine/autosub", "--episodes", "1", "--seed", "42")
            self.assertEqual(report["model"]["sha256"], hashlib.sha256(b"model bytes").hexdigest())
            self.assertEqual(report["config"], artifact_manifest(config))
            self.assertEqual(report["seed"], 42)
            self.assertEqual(report["results"][0]["episode_results"][0]["length"], 3)
            self.assertEqual(report["results"][0]["env"]["curriculum_decisions"], 0)

    def test_cli_rejects_agent_and_control_mismatches(self) -> None:
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            for agent, control, extra in (
                    ("submarine", "sub_duel_v1", ["--agent-boat-type", "destroyer"]),
                    ("destroyer", "destroyer_duel_v2", []),
                    ("submarine", "destroyer_duel_v2", []),
                    (None, "sub_duel_v1", [])):
                config.write_text(json.dumps({"env": {**self.options,
                    "agent_boat_type": agent, "control_version": control}, "reward": {}}))
                with self.subTest(agent=agent, control=control, extra=extra), \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    self.run_cli("unused.zip", "--config", str(config), *extra)
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
