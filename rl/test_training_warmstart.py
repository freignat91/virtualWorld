"""Verifie une nouvelle phase recurrente sans toucher aux modeles publies."""

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import gymnasium as gym
import numpy as np
from sb3_contrib import RecurrentPPO
import torch

from rl import train_ai


class SeedEnv(gym.Env):
    """Petit environnement qui expose la graine effectivement recue au reset."""

    observation_space = gym.spaces.Box(-1.0, 1.0, (4,), dtype=np.float32)
    action_space = gym.spaces.Discrete(2)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.reset_seed = seed
        return self.np_random.uniform(-1, 1, 4).astype(np.float32), {}

    def step(self, action):
        return self.np_random.uniform(-1, 1, 4).astype(np.float32), 0.0, False, False, {}


class TrainingWarmStartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = train_ai.load_config(str(train_ai.BASE_DIR / "configs/aidest_v5.json"))
        self.config["model"] = {
            "net_arch": [8], "lstm_hidden_size": 8, "n_lstm_layers": 1}
        self.config["training"].update(
            total_steps=32, n_envs=8, n_steps=4, batch_size=4, n_epochs=1)
        self.source = self.root / "source.zip"
        self.output = self.root / "models_rl" / "new_phase"

    def run_main(self) -> None:
        with patch.object(train_ai, "BASE_DIR", self.root), \
                patch.object(train_ai, "load_config", return_value=self.config), \
                patch.object(train_ai, "make_env", return_value=SeedEnv), \
                patch("sys.argv", ["train_ai", "--run-name", "new_phase",
                                   "--resume", str(self.source), "--device", "cpu"]):
            train_ai.main()

    def save_source(self) -> RecurrentPPO:
        env = SeedEnv()
        self.addCleanup(env.close)
        model = RecurrentPPO(
            "MlpLstmPolicy", env, n_steps=4, batch_size=4, n_epochs=1,
            policy_kwargs=self.config["model"], seed=42, device="cpu", verbose=0)
        model.learn(4)
        model.save(self.source)
        return model

    def test_real_load_seed_weights_workers_and_provenance(self) -> None:
        source_model = self.save_source()
        self.output.mkdir(parents=True)
        digest = train_ai.file_sha256(self.source)
        original_learn = RecurrentPPO.learn
        observed = []

        def learn(model, *args, **kwargs):
            self.assertEqual(model.seed, 1542)
            self.assertEqual(model.policy_kwargs, self.config["model"])
            for key, value in source_model.policy.state_dict().items():
                self.assertTrue(torch.equal(value, model.policy.state_dict()[key]), key)
            self.assertEqual(model.rollout_buffer.gamma, self.config["training"]["gamma"])
            self.assertEqual(model.rollout_buffer.gae_lambda,
                             self.config["training"]["gae_lambda"])
            result = original_learn(model, *args, **kwargs)
            observed.extend(model.get_env().get_attr("reset_seed"))
            self.assertEqual(model.num_timesteps, 32)
            return result

        with patch.object(RecurrentPPO, "learn", learn):
            self.run_main()
        self.assertEqual(observed, list(range(1542, 1550)))
        self.assertEqual(train_ai.file_sha256(self.source), digest)
        provenance = json.loads((self.output / "provenance.json").read_text())
        self.assertEqual(provenance["checkpoint_sha256"], digest)
        self.assertEqual(provenance["checkpoint_source"], str(self.source.resolve()))
        self.assertEqual(provenance["checkpoint_timesteps"], 4)
        self.assertEqual(provenance["seed"], 1542)
        self.assertEqual(provenance["architecture"], self.config["model"])
        self.assertEqual(provenance["policy_kwargs"], self.config["model"])
        self.assertEqual(provenance["phase"], "warm_start")
        self.assertIn("stable-baselines3", provenance["dependencies"])
        effective = json.loads((self.output / "effective_config.json").read_text())
        self.assertEqual(effective["training"], self.config["training"])

    def test_architecture_mismatches_rejected_before_learning(self) -> None:
        self.save_source()
        original = copy.deepcopy(self.config["model"])
        self.config["training"]["n_envs"] = 1
        for key, value in (("net_arch", [16]), ("lstm_hidden_size", 16),
                           ("n_lstm_layers", 2)):
            with self.subTest(key=key):
                self.config["model"] = dict(original, **{key: value})
                with patch.object(train_ai, "BASE_DIR", self.root / key), \
                        patch.object(train_ai, "load_config", return_value=self.config), \
                        patch.object(train_ai, "make_env", return_value=SeedEnv), \
                        patch.object(RecurrentPPO, "learn") as learn, \
                        patch("sys.argv", ["train_ai", "--run-name", "new_phase",
                                           "--resume", str(self.source), "--device", "cpu"]):
                    with self.assertRaisesRegex(ValueError, "policy kwargs"):
                        train_ai.main()
                    learn.assert_not_called()
                self.assertFalse((self.root / key / "models_rl/new_phase/effective_config.json").exists())

    def test_nonempty_output_rejected_without_writes(self) -> None:
        self.output.mkdir(parents=True)
        sentinel = self.output / "effective_config.json"
        sentinel.write_text("existing configuration")
        with patch.object(RecurrentPPO, "load") as load:
            with self.assertRaisesRegex(ValueError, "sortie non vide"):
                self.run_main()
            load.assert_not_called()
        self.assertEqual(sentinel.read_text(), "existing configuration")
        self.assertEqual(list(self.output.iterdir()), [sentinel])

    def test_v5_only_changes_phase_identity_and_seed(self) -> None:
        v4 = train_ai.load_config(str(train_ai.BASE_DIR / "configs/aidest_v4.json"))
        v5 = train_ai.load_config(str(train_ai.BASE_DIR / "configs/aidest_v5.json"))
        self.assertEqual(v5["name"], "aidest_v5")
        self.assertEqual(v5["training"]["seed"], 1542)
        for key in ("name", "description"):
            v5[key] = v4[key]
        v5["training"]["seed"] = v4["training"]["seed"]
        self.assertEqual(v4, v5)


if __name__ == "__main__":
    unittest.main()
