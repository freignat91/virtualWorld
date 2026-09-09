"""Tests d'isolation des RNG pendant l'evaluation et le chargement adverse."""

import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import torch
from sb3_contrib import RecurrentPPO

from rl.evaluate_ai import evaluate
from rl.rl_env import SubmarineDuelEnv
from rl.rng import preserve_rng_state


def rng_samples() -> tuple:
    return (random.random(), np.random.random(4).tolist(), torch.rand(4).tolist())


def disturb_rng() -> None:
    random.seed(987)
    np.random.seed(987)
    torch.manual_seed(987)
    rng_samples()


class RNGIsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(preserve_rng_state())
        random.seed(123)
        np.random.seed(123)
        torch.manual_seed(123)

    def test_restoration_and_nesting(self) -> None:
        with preserve_rng_state():
            expected = rng_samples()
        with preserve_rng_state():
            disturb_rng()
            with preserve_rng_state():
                nested_expected = rng_samples()
            with preserve_rng_state():
                disturb_rng()
            self.assertEqual(nested_expected, rng_samples())
        self.assertEqual(expected, rng_samples())

    def test_exception_restoration(self) -> None:
        with preserve_rng_state():
            expected = rng_samples()
        with self.assertRaisesRegex(RuntimeError, "rng failure"):
            with preserve_rng_state():
                disturb_rng()
                raise RuntimeError("rng failure")
        self.assertEqual(expected, rng_samples())

    def test_uninitialized_cuda_is_not_touched(self) -> None:
        with patch.object(torch.cuda, "is_initialized", return_value=False), \
                patch.object(torch.cuda, "get_rng_state_all") as get_states, \
                patch.object(torch.cuda, "set_rng_state_all") as set_states:
            with preserve_rng_state():
                rng_samples()
            get_states.assert_not_called()
            set_states.assert_not_called()

    def test_initialized_cuda_restored_on_exception(self) -> None:
        states = [torch.tensor([1, 2], dtype=torch.uint8)]
        with patch.object(torch.cuda, "is_initialized", return_value=True), \
                patch.object(torch.cuda, "get_rng_state_all", return_value=states), \
                patch.object(torch.cuda, "set_rng_state_all") as set_states:
            with self.assertRaises(RuntimeError):
                with preserve_rng_state():
                    raise RuntimeError("rng failure")
            set_states.assert_called_once_with(states)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA unavailable")
    def test_real_cuda_restoration(self) -> None:
        torch.cuda.init()
        with preserve_rng_state():
            expected = [torch.rand(4, device=f"cuda:{i}").cpu().tolist()
                        for i in range(torch.cuda.device_count())]
        with self.assertRaises(RuntimeError):
            with preserve_rng_state():
                disturb_rng()
                for i in range(torch.cuda.device_count()):
                    torch.rand(4, device=f"cuda:{i}")
                raise RuntimeError("rng failure")
        actual = [torch.rand(4, device=f"cuda:{i}").cpu().tolist()
                  for i in range(torch.cuda.device_count())]
        self.assertEqual(expected, actual)

    def test_evaluation_restores_rng_on_success_and_failure(self) -> None:
        env = SubmarineDuelEnv(max_physics_steps=10)
        self.addCleanup(env.close)
        model = RecurrentPPO(
            "MlpLstmPolicy", env, n_steps=8, batch_size=8,
            policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
            device="cpu", seed=13)
        for fail in (False, True):
            with self.subTest(fail=fail):
                with preserve_rng_state():
                    expected = rng_samples()
                predict = model.predict

                def predict_with_rng(*args, **kwargs):
                    disturb_rng()
                    if fail:
                        raise RuntimeError("prediction failure")
                    return predict(*args, **kwargs)

                with patch.object(model, "predict", side_effect=predict_with_rng):
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, "prediction failure"):
                            evaluate(model, "combats", "submarine", "autosub", 2, 51,
                                     env_options={"max_physics_steps": 10})
                    else:
                        result = evaluate(
                            model, "combats", "submarine", "autosub", 2, 51,
                            env_options={"max_physics_steps": 10})
                        self.assertEqual(2, result["episodes"])
                self.assertEqual(expected, rng_samples())

    def test_failed_opponent_load_restores_rng(self) -> None:
        env = SubmarineDuelEnv(max_physics_steps=10)
        self.addCleanup(env.close)
        with preserve_rng_state():
            expected = rng_samples()

        def fail_load(*args, **kwargs):
            disturb_rng()
            raise RuntimeError("load failure")

        with patch.object(RecurrentPPO, "load", side_effect=fail_load):
            with self.assertRaisesRegex(RuntimeError, "load failure"):
                env._load_opponent(Path("failed.zip"), "submarine")
        self.assertEqual(expected, rng_samples())
        self.assertFalse(env._model_cache)

    def test_cold_warm_checkpoint_loads_and_rollouts_match(self) -> None:
        env = SubmarineDuelEnv(max_physics_steps=10)
        self.addCleanup(env.close)
        model = RecurrentPPO(
            "MlpLstmPolicy", env, n_steps=8, batch_size=8,
            policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
            device="cpu", seed=13)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "opponent.zip"
            model.save(path)
            with preserve_rng_state():
                expected = rng_samples()
            with patch.object(RecurrentPPO, "load", wraps=RecurrentPPO.load) as load:
                cold, version = env._load_opponent(path, "submarine")
                warm, warm_version = env._load_opponent(path, "submarine")
                self.assertIs(cold, warm)
                self.assertEqual(version, warm_version)
                load.assert_called_once()
            self.assertEqual(expected, rng_samples())

            env.fixed_opponent_pool_dir = Path(directory)
            env.fixed_policy_probability = 1.0
            env._model_cache.clear()
            trajectories = []
            for _ in range(2):
                observation, info = env.reset(seed=51)
                trajectory = [(observation.tolist(), info)]
                for _ in range(2):
                    observation, reward, terminated, truncated, info = env.step(
                        np.array([2, 1, 2, 0, 0]))
                    trajectory.append((observation.tolist(), reward, terminated, truncated, info))
                trajectories.append((trajectory, random.random()))
            self.assertEqual(trajectories[0], trajectories[1])


if __name__ == "__main__":
    unittest.main()
