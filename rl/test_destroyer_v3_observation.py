"""Regressions du schema defensif destroyer_duel_v3."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from rl.headless import HeadlessRunner
from rl.rl_control import (
    DESTROYER_OBSERVATION_VERSION,
    DESTROYER_V3_ACTION_NVECS,
    DESTROYER_V3_LURE_SLOT_DIM,
    DESTROYER_V3_LURE_SLOTS,
    DESTROYER_V3_LURE_START,
    DESTROYER_V3_OBS_DIM,
    DESTROYER_V3_OBSERVATION_VERSION,
    DESTROYER_V3_RAY_START,
    DESTROYER_V3_TORPEDO_SLOT_DIM,
    DESTROYER_V3_TORPEDO_SLOTS,
    DESTROYER_V3_TORPEDO_START,
    apply_action,
    build_observation,
    control_spec,
    control_version_for_spaces,
)


class DestroyerV3ObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = HeadlessRunner(seed=4542)
        self.runner.reset(seed=4542)
        self.runner.world["islands"] = []
        self.runner.world["thermoclines"] = []
        self.sid = self.runner.spawn_bot(
            boat_type="destroyer", external_control=True, ai=None,
            position=(0.0, 0.0), rotation=0.0, team_id="agent")
        self.bot = self.runner.legacy.bots[self.sid]
        self.bot["rl_control_version"] = DESTROYER_V3_OBSERVATION_VERSION

    def _torpedo(self, index: int, x: float) -> dict:
        return {
            "ownerPlayerId": f"enemy-{index}", "tid": index,
            "x": x, "y": self.bot["position"].get("y", 0.0), "z": 0.0,
            "dirX": 1.0, "dirZ": 0.0, "speed": 1.0,
            "kind": "acoustic", "acquiredBoatId": self.bot["id"],
        }

    def test_spaces_are_distinct_and_mines_are_not_actionable(self) -> None:
        from rl.rl_env import SubmarineDuelEnv

        version, dimension, nvec = control_spec(
            "destroyer", DESTROYER_V3_OBSERVATION_VERSION)
        self.assertEqual(DESTROYER_V3_OBSERVATION_VERSION, version)
        self.assertEqual(101, dimension)
        self.assertEqual(tuple(DESTROYER_V3_ACTION_NVECS), tuple(nvec))
        self.assertEqual(version, control_version_for_spaces("destroyer", dimension, nvec))

        mine_ammo = dict(self.runner.legacy.mine_ammo[self.sid])
        result = apply_action(self.bot, self.runner.sim, [2, 1, 0, 0, 0])
        self.assertFalse(result["mine_requested"])
        self.assertFalse(result["mine_placed"])
        self.assertEqual(mine_ammo, self.runner.legacy.mine_ammo[self.sid])
        self.assertEqual({}, self.runner.legacy.mines_server)
        with self.assertRaises(ValueError):
            apply_action(self.bot, self.runner.sim, [2, 1, 0, 0, 0, 1])

        env = SubmarineDuelEnv(
            agent_boat_type="destroyer", control_version=version,
            opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
            seed=4542, frame_skip=2, max_physics_steps=10,
            spawn_min_m=400.0, spawn_max_m=700.0)
        try:
            observation, _ = env.reset(seed=4542)
            self.assertEqual((dimension,), observation.shape)
            self.assertEqual(tuple(nvec), tuple(env.action_space.nvec))
            self.assertTrue(env.action_space.contains(np.array([2, 1, 0, 0, 0])))
        finally:
            env.close()

    def test_v7_config_and_recurrent_ppo_smoke_training(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv

        config = json.loads((Path(__file__).parent / "configs/aidest_v7_defense.json").read_text())
        self.assertEqual(DESTROYER_V3_OBSERVATION_VERSION, config["env"]["control_version"])
        self.assertEqual(-1.0, config["reward"]["mine_placed"])
        self.assertEqual([0, 1_000_000, 2_000_000],
                         config["evaluation"]["sampled_action_seed_offsets"])
        env = SubmarineDuelEnv(
            agent_boat_type="destroyer",
            control_version=DESTROYER_V3_OBSERVATION_VERSION,
            opponents=[{"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
            seed=4542, frame_skip=2, max_physics_steps=10,
            spawn_min_m=400.0, spawn_max_m=700.0)
        try:
            model = RecurrentPPO(
                "MlpLstmPolicy", env, n_steps=4, batch_size=4, n_epochs=1,
                policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                device="cpu", seed=4542, verbose=0)
            model.learn(total_timesteps=8)
        finally:
            env.close()

    def test_v2_checkpoint_cannot_warm_start_v3(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv

        options = {
            "agent_boat_type": "destroyer",
            "opponents": [{"boat_type": "submarine", "ai": "autosub", "weight": 1.0}],
            "seed": 4542, "frame_skip": 2, "max_physics_steps": 10,
            "spawn_min_m": 400.0, "spawn_max_m": 700.0,
        }
        old_env = SubmarineDuelEnv(
            control_version=DESTROYER_OBSERVATION_VERSION, **options)
        try:
            old_model = RecurrentPPO(
                "MlpLstmPolicy", old_env, n_steps=4, batch_size=4, n_epochs=1,
                policy_kwargs={"net_arch": [16], "lstm_hidden_size": 16},
                device="cpu", seed=4542, verbose=0)
            with TemporaryDirectory() as directory:
                path = Path(directory) / "v2.zip"
                old_model.save(path)
                new_env = SubmarineDuelEnv(
                    control_version=DESTROYER_V3_OBSERVATION_VERSION, **options)
                try:
                    with self.assertRaises(ValueError):
                        RecurrentPPO.load(path, env=new_env, device="cpu")
                finally:
                    new_env.close()
        finally:
            old_env.close()

    def test_six_visible_torpedo_trajectories_are_ranked_and_bounded(self) -> None:
        for index, x in enumerate(range(-5, -40, -5), start=1):
            torpedo = self._torpedo(index, float(x))
            self.runner.sim.torpedoes[(torpedo["ownerPlayerId"], index)] = torpedo
        observation = build_observation(self.bot, self.runner.sim, self.runner.world)
        self.assertEqual((DESTROYER_V3_OBS_DIM,), observation.shape)
        self.assertEqual(np.float32, observation.dtype)
        self.assertTrue(np.all(observation >= -1.0))
        self.assertTrue(np.all(observation <= 1.0))
        for index in range(DESTROYER_V3_TORPEDO_SLOTS):
            start = DESTROYER_V3_TORPEDO_START + index * DESTROYER_V3_TORPEDO_SLOT_DIM
            self.assertEqual(1.0, observation[start])
        first = observation[
            DESTROYER_V3_TORPEDO_START:
            DESTROYER_V3_TORPEDO_START + DESTROYER_V3_TORPEDO_SLOT_DIM]
        self.assertAlmostEqual(0.005, first[1], places=6)
        self.assertAlmostEqual(0.0, first[2], places=6)
        self.assertAlmostEqual(-0.1, first[3], places=6)
        self.assertAlmostEqual(0.0, first[4], places=6)
        self.assertAlmostEqual(0.0, first[5], places=6)
        self.assertAlmostEqual(0.5, first[6], places=6)

        baseline = observation.copy()
        omitted = self.runner.sim.torpedoes[("enemy-7", 7)]
        omitted.update(kind="autonomous", acquiredBoatId=None, targetId="private")
        np.testing.assert_array_equal(
            baseline, build_observation(self.bot, self.runner.sim, self.runner.world))
        selected = self.runner.sim.torpedoes[("enemy-1", 1)]
        selected.update(kind="wireGuided", acquiredBoatId=None, targetId="private")
        np.testing.assert_array_equal(
            baseline, build_observation(self.bot, self.runner.sim, self.runner.world))

    def test_hidden_torpedo_is_excluded_before_slot_selection(self) -> None:
        baseline = build_observation(self.bot, self.runner.sim, self.runner.world)
        hidden = self._torpedo(1, -10.0)
        self.runner.sim.torpedoes[(hidden["ownerPlayerId"], 1)] = hidden
        self.runner.world["islands"] = [{"points": [
            {"x": -6.0, "z": -2.0}, {"x": -4.0, "z": -2.0},
            {"x": -4.0, "z": 2.0}, {"x": -6.0, "z": 2.0},
        ]}]
        observation = build_observation(self.bot, self.runner.sim, self.runner.world)
        np.testing.assert_array_equal(
            baseline[DESTROYER_V3_TORPEDO_START:DESTROYER_V3_LURE_START],
            observation[DESTROYER_V3_TORPEDO_START:DESTROYER_V3_LURE_START])

    def test_lure_slots_include_owner_lifetime_and_visibility(self) -> None:
        now = self.runner.sim.now()
        for index in range(1, 8):
            owner = self.bot["id"] if index % 2 else f"enemy-{index}"
            self.runner.sim.lures[(owner, index)] = {
                "ownerId": owner, "lid": index,
                "x": -float(index), "y": 0.0, "z": 0.0,
                "expiresAt": now + 120.0 - index,
            }
        observation = build_observation(self.bot, self.runner.sim, self.runner.world)
        for index in range(DESTROYER_V3_LURE_SLOTS):
            start = DESTROYER_V3_LURE_START + index * DESTROYER_V3_LURE_SLOT_DIM
            self.assertEqual(1.0, observation[start])
        first = observation[
            DESTROYER_V3_LURE_START:
            DESTROYER_V3_LURE_START + DESTROYER_V3_LURE_SLOT_DIM]
        second = observation[
            DESTROYER_V3_LURE_START + DESTROYER_V3_LURE_SLOT_DIM:
            DESTROYER_V3_LURE_START + 2 * DESTROYER_V3_LURE_SLOT_DIM]
        self.assertAlmostEqual(0.001, first[1], places=6)
        self.assertAlmostEqual(119.0 / 120.0, first[3], places=6)
        self.assertEqual(1.0, first[4])
        self.assertEqual(-1.0, second[4])
        self.assertEqual(DESTROYER_V3_OBS_DIM - 8, DESTROYER_V3_RAY_START)

        baseline = observation.copy()
        self.runner.sim.lures[(self.bot["id"], 7)]["expiresAt"] = now - 1.0
        np.testing.assert_array_equal(
            baseline, build_observation(self.bot, self.runner.sim, self.runner.world))

    def test_hidden_enemy_lure_is_excluded_but_own_lure_remains_known(self) -> None:
        now = self.runner.sim.now()
        self.runner.world["islands"] = [{"points": [
            {"x": -6.0, "z": -2.0}, {"x": -4.0, "z": -2.0},
            {"x": -4.0, "z": 2.0}, {"x": -6.0, "z": 2.0},
        ]}]
        hidden = {"ownerId": "enemy", "lid": 1, "x": -10.0, "y": 0.0,
                  "z": 0.0, "expiresAt": now + 60.0}
        self.runner.sim.lures[("enemy", 1)] = hidden
        observation = build_observation(self.bot, self.runner.sim, self.runner.world)
        self.assertEqual(0.0, observation[DESTROYER_V3_LURE_START])
        hidden["ownerId"] = self.bot["id"]
        observation = build_observation(self.bot, self.runner.sim, self.runner.world)
        self.assertEqual(1.0, observation[DESTROYER_V3_LURE_START])
        self.assertEqual(1.0, observation[DESTROYER_V3_LURE_START + 4])


if __name__ == "__main__":
    unittest.main()
