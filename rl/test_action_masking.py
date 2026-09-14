"""Regressions du masquage situationnel des actions recurrentes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch as th
from gymnasium import spaces
from sb3_contrib import RecurrentPPO

from rl.headless import HeadlessRunner
from rl.masked_recurrent_policy import (
    SituationMaskedMlpLstmPolicy,
    situation_action_masks,
)
from rl.rl_control import (
    SUBMARINE_V3_ACTION_NVECS,
    SUBMARINE_V3_OBS_DIM,
    SUBMARINE_V3_OBSERVATION_VERSION,
    SUBMARINE_V3_TORPEDO_START,
    SUBMARINE_V4_OBS_DIM,
    SUBMARINE_V4_OBSERVATION_VERSION,
    DESTROYER_V5_OBS_DIM,
    DESTROYER_V5_OBSERVATION_VERSION,
    DESTROYER_V5_TORPEDO_START,
    DESTROYER_V6_OBS_DIM,
    DESTROYER_V6_OBSERVATION_VERSION,
    MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM,
    build_observation,
)


class UnavailableResourcesEnv(gym.Env):
    """Expose uniquement des actions de ressources masquees."""

    def __init__(self) -> None:
        self.action_space = spaces.MultiDiscrete(SUBMARINE_V3_ACTION_NVECS)
        self.observation_space = spaces.Box(
            -1.0, 1.0, shape=(SUBMARINE_V3_OBS_DIM,), dtype=np.float32)
        self.steps = 0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.steps = 0
        return np.zeros(SUBMARINE_V3_OBS_DIM, dtype=np.float32), {}

    def step(self, action):
        if int(action[3]) != 0 or int(action[4]) != 0:
            raise AssertionError(f"action masquee selectionnee: {action}")
        self.steps += 1
        return (np.zeros(SUBMARINE_V3_OBS_DIM, dtype=np.float32), 0.0,
                False, self.steps >= 2, {})


class SituationActionMaskTest(unittest.TestCase):
    def test_observation_masks_match_authoritative_empty_stores(self) -> None:
        runner = HeadlessRunner(seed=61542)
        for boat_type, version, masked_indices in (
            ("submarine", SUBMARINE_V3_OBSERVATION_VERSION, (16, 17, 19)),
            ("destroyer", DESTROYER_V5_OBSERVATION_VERSION,
             (11, 12, 13, 14, 16, 18)),
            ("submarine", SUBMARINE_V4_OBSERVATION_VERSION, (16, 17, 19)),
            ("destroyer", DESTROYER_V6_OBSERVATION_VERSION,
             (11, 12, 13, 14, 16, 18)),
        ):
            with self.subTest(boat_type=boat_type):
                runner.reset(seed=61542)
                sid = runner.spawn_bot(
                    boat_type, external_control=True, ai=None,
                    position=(0.0, 0.0), rotation=0.0, team_id="agent")
                bot = runner.legacy.bots[sid]
                bot["rl_control_version"] = version
                runner.legacy.torpedo_ammo[sid] = {
                    "acoustic": 0, "autonomous": 0, "wireGuided": 0}
                runner.legacy.cannon_ammo[sid] = {"cannon": 0}
                runner.legacy.grenade_ammo[sid] = 0
                runner.legacy.lure_ammo[sid] = 0
                bot["next_torpedo_at"] = runner.sim.now() + 10.0
                bot["next_cannon_at"] = runner.sim.now() + 10.0
                bot["next_grenade_at"] = runner.sim.now() + 10.0
                bot["next_lure_at"] = runner.sim.now() + 10.0
                bot.setdefault("bb", {})["next_sonar_ping_at"] = runner.sim.now() + 10.0
                observation = build_observation(bot, runner.sim, runner.world)
                mask = situation_action_masks(
                    th.as_tensor(observation).unsqueeze(0), version)[0]
                for index in masked_indices:
                    self.assertFalse(bool(mask[index]))

    def test_submarine_masks_ammo_and_cooldowns(self) -> None:
        observation = th.zeros((1, SUBMARINE_V3_OBS_DIM))
        mask = situation_action_masks(
            observation, SUBMARINE_V3_OBSERVATION_VERSION)[0]
        self.assertTrue(bool(th.all(mask[:16])))
        self.assertFalse(bool(mask[16]))
        self.assertFalse(bool(mask[17]))
        self.assertTrue(bool(mask[18]))
        self.assertFalse(bool(mask[19]))

        observation[0, [7, 8, 9, 10, 11]] = 1.0
        observation[0, SUBMARINE_V3_TORPEDO_START] = 1.0
        mask = situation_action_masks(
            observation, SUBMARINE_V3_OBSERVATION_VERSION)[0]
        self.assertTrue(bool(th.all(mask)))
        observation[0, 10] = 0.0
        mask = situation_action_masks(
            observation, SUBMARINE_V3_OBSERVATION_VERSION)[0]
        self.assertFalse(bool(mask[16]))
        self.assertFalse(bool(mask[17]))
        self.assertTrue(bool(mask[19]))

    def test_destroyer_masks_each_resource_and_cooldown(self) -> None:
        observation = th.zeros((1, DESTROYER_V5_OBS_DIM))
        mask = situation_action_masks(
            observation, DESTROYER_V5_OBSERVATION_VERSION)[0]
        self.assertTrue(bool(th.all(mask[:11])))
        self.assertFalse(bool(th.any(mask[11:15])))
        self.assertTrue(bool(mask[15]))
        self.assertFalse(bool(mask[16]))
        self.assertTrue(bool(mask[17]))
        self.assertFalse(bool(mask[18]))

        observation[0, 6:16] = 1.0
        observation[0, DESTROYER_V5_TORPEDO_START] = 1.0
        mask = situation_action_masks(
            observation, DESTROYER_V5_OBSERVATION_VERSION)[0]
        self.assertTrue(bool(th.all(mask)))
        conditions = {
            6: (11,), 7: (12,), 8: (13,), 9: (14,), 10: (16,),
            11: (11, 12), 12: (13,), 13: (14,), 14: (16,), 15: (18,),
        }
        for observation_index, action_indices in conditions.items():
            with self.subTest(observation_index=observation_index):
                observation[0, observation_index] = 0.0
                mask = situation_action_masks(
                    observation, DESTROYER_V5_OBSERVATION_VERSION)[0]
                for action_index in action_indices:
                    self.assertFalse(bool(mask[action_index]))
                observation[0, observation_index] = 1.0

    def test_lure_requires_a_visible_torpedo(self) -> None:
        for version, dimension, ammo_index, ready_index, torpedo_start, lure_index in (
            (SUBMARINE_V3_OBSERVATION_VERSION, SUBMARINE_V3_OBS_DIM,
             9, 11, SUBMARINE_V3_TORPEDO_START, 19),
            (DESTROYER_V5_OBSERVATION_VERSION, DESTROYER_V5_OBS_DIM,
             10, 14, DESTROYER_V5_TORPEDO_START, 16),
            (SUBMARINE_V4_OBSERVATION_VERSION, SUBMARINE_V4_OBS_DIM,
             9, 11, SUBMARINE_V3_TORPEDO_START, 19),
            (DESTROYER_V6_OBSERVATION_VERSION, DESTROYER_V6_OBS_DIM,
             10, 14, DESTROYER_V5_TORPEDO_START, 16),
        ):
            with self.subTest(version=version):
                observation = th.zeros((1, dimension))
                observation[0, [ammo_index, ready_index]] = 1.0
                observation[0, torpedo_start + 1] = 1.0
                mask = situation_action_masks(observation, version)[0]
                self.assertFalse(bool(mask[lure_index]))

                observation[0, torpedo_start
                            + 5 * MOBILITY_DIRECTIONAL_TORPEDO_SLOT_DIM] = 1.0
                mask = situation_action_masks(observation, version)[0]
                self.assertTrue(bool(mask[lure_index]))

    def test_mobility_curriculum_forces_tactical_actions_to_none(self) -> None:
        for version, dimension, masked_indices in (
            (SUBMARINE_V3_OBSERVATION_VERSION, SUBMARINE_V3_OBS_DIM,
             (16, 17, 19)),
            (DESTROYER_V5_OBSERVATION_VERSION, DESTROYER_V5_OBS_DIM,
             (11, 12, 13, 14, 16, 18)),
            (SUBMARINE_V4_OBSERVATION_VERSION, SUBMARINE_V4_OBS_DIM,
             (16, 17, 19)),
            (DESTROYER_V6_OBSERVATION_VERSION, DESTROYER_V6_OBS_DIM,
             (11, 12, 13, 14, 16, 18)),
        ):
            with self.subTest(version=version):
                observation = th.ones((1, dimension))
                mask = situation_action_masks(
                    observation, version, mobility_curriculum=True)[0]
                for index in masked_indices:
                    self.assertFalse(bool(mask[index]))

    def test_recurrent_policy_masks_collection_training_and_reload(self) -> None:
        env = UnavailableResourcesEnv()
        model = RecurrentPPO(
            SituationMaskedMlpLstmPolicy,
            env,
            n_steps=4,
            batch_size=4,
            n_epochs=1,
            policy_kwargs={
                "control_version": SUBMARINE_V3_OBSERVATION_VERSION,
                "net_arch": [8],
                "lstm_hidden_size": 8,
            },
            seed=61542,
        )
        model.rl_control_version = SUBMARINE_V3_OBSERVATION_VERSION
        model.learn(8)
        observation, _ = env.reset()
        action, _ = model.predict(observation, deterministic=True)
        self.assertEqual(0, int(action[3]))
        self.assertEqual(0, int(action[4]))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "masked.zip"
            model.save(path)
            loaded = RecurrentPPO.load(path)
            self.assertIsInstance(loaded.policy, SituationMaskedMlpLstmPolicy)
            action, _ = loaded.predict(observation, deterministic=True)
            self.assertEqual(0, int(action[3]))
            self.assertEqual(0, int(action[4]))


if __name__ == "__main__":
    unittest.main()
