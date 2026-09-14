"""Regressions du diagnostic, sans apprentissage ni port reseau."""

import unittest
from unittest.mock import patch

import numpy as np

from rl.diagnose_duels import duel, launch_context, outcome, pending_torpedoes
from rl.rl_control import apply_action
from rl.rl_env import SubmarineDuelEnv


class IdlePolicy:
    def __init__(self):
        self.calls = 0

    def predict(self, observation, **kwargs):
        self.calls += 1
        return np.array([2, 0, 0, 0, 0, 0]), None


class DiagnosticTests(unittest.TestCase):
    def test_action_seed_varies_policy_not_initial_conditions(self):
        import torch

        class Policy:
            def predict(self, observation, **kwargs):
                return np.array([torch.randint(5, ()).item(), 1, 0, 0, 0, 0]), None

        env = SubmarineDuelEnv(agent_boat_type='destroyer',
                               control_version='destroyer_duel_v2', max_physics_steps=50)
        try:
            samples = []
            for action_seed in (160000, 1160000, 160000):
                rows = []
                result = duel(env, Policy(), 160000, rows.append,
                              deterministic=False, action_seed=action_seed)
                self.assertEqual(action_seed, result['action_seed'])
                samples.append((result['initial'], [r['action'] for r in rows
                                                    if r['type'] == 'RLDecision']))
            self.assertEqual(samples[0], samples[2])
            self.assertEqual(samples[0][0], samples[1][0])
            self.assertNotEqual(samples[0][1], samples[1][1])
            for seed in (-1, 2**63, True):
                with self.assertRaises(ValueError):
                    duel(env, Policy(), 160000, lambda row: None,
                         deterministic=False, action_seed=seed)
            with self.assertRaises(ValueError):
                duel(env, Policy(), 160000, lambda row: None, action_seed=160000)
        finally:
            env.close()

    def test_mine_ablation_changes_only_applied_agent_component(self):
        class MinePolicy:
            action = np.array([2, 1, 0, 0, 0, 1])

            def predict(self, observation, **kwargs):
                return self.action, None

        env = SubmarineDuelEnv(agent_boat_type='destroyer',
                               control_version='destroyer_duel_v2', max_physics_steps=10)
        policy = MinePolicy()
        try:
            for disabled in (False, True):
                rows = []
                result = duel(env, policy, 150000, rows.append,
                              disable_agent_mines=disabled)
                decisions = [r for r in rows if r['type'] == 'RLDecision'
                             and r['player_id'] == 'bot001']
                self.assertTrue(decisions)
                for row in decisions:
                    self.assertEqual(row['proposed_action'], [2, 1, 0, 0, 0, 1])
                    self.assertEqual(row['action'][:5], row['proposed_action'][:5])
                    self.assertEqual(row['action'][5], 0 if disabled else 1)
                self.assertEqual(policy.action.tolist(), [2, 1, 0, 0, 0, 1])
                initial = result['initial_ammo']['bot001']['mine_ammo']['surface']
                final = result['first']['ammo']['bot001']['mine_ammo']['surface']
                self.assertEqual(initial - final, 0 if disabled else 1)
        finally:
            env.close()

    def test_mine_ablation_rejects_wrong_action_schema(self):
        env = SubmarineDuelEnv()
        try:
            with self.assertRaises(ValueError):
                duel(env, IdlePolicy(), 150000, lambda row: None,
                     disable_agent_mines=True)
        finally:
            env.close()

    def test_sampled_actions_are_seeded_and_rng_restored(self):
        import torch

        class SampledPolicy:
            def __init__(self):
                self.modes = []

            def predict(self, observation, **kwargs):
                self.modes.append(kwargs['deterministic'])
                return np.array([torch.randint(5, ()).item(), 1, 0, 0, 0, 0]), None

        env = SubmarineDuelEnv(agent_boat_type='destroyer',
                               control_version='destroyer_duel_v2', max_physics_steps=15)
        policy = SampledPolicy()
        before = torch.get_rng_state().clone()
        try:
            histories = []
            for _ in range(2):
                rows = []
                result = duel(env, policy, 140000, rows.append, deterministic=False)
                self.assertFalse(result['deterministic'])
                histories.append([r['action'] for r in rows if r['type'] == 'RLDecision'])
                self.assertTrue(torch.equal(before, torch.get_rng_state()))
            self.assertEqual(histories[0], histories[1])
            self.assertTrue(policy.modes)
            self.assertFalse(any(policy.modes))
        finally:
            env.close()

    def test_outcomes(self):
        self.assertEqual([outcome(x) for x in ([True, False], [False, True],
                         [False, False], [True, True])], ['win', 'loss', 'draw', 'draw'])

    def test_cooldown_keeps_penalty_flags(self):
        env = SubmarineDuelEnv(agent_boat_type='destroyer', control_version='destroyer_duel_v2')
        try:
            env.reset(seed=12)
            bot = env._agent()
            bot['next_torpedo_at'] = 10
            action = [2, 0, 1, 0, 0, 0]
            self.assertEqual(launch_context(bot, env.runner.sim, action)['rejection_reason'], 'cooldown')
            result = apply_action(bot, env.runner.sim, action)
            self.assertTrue(result['weapon_invalid'])
            self.assertFalse(result['weapon_fired'])
        finally:
            env.close()

    def test_continuation_no_ghost_inference_and_damage_count(self):
        env = SubmarineDuelEnv(agent_boat_type='destroyer', control_version='destroyer_duel_v2')
        policy = IdlePolicy()
        native_step = env.runner.step
        rows = []

        def step(dt):
            sim = env.runner.sim
            native_step(dt)
            if env.runner._time < .06:
                bot = env._agent()
                sim.spawn_bot_torpedo(bot, env._opponent())
                sim._explode_torpedo({'ownerPlayerId': env._opponent()['id'], 'tid': 99,
                    'x': bot['position']['x'], 'y': bot['position']['y'], 'z': bot['position']['z']},
                    direct_hit_id=bot['id'], damage=200, hit_target_id=bot['id'])
            elif env.runner._time >= .3:
                bot = env._opponent()
                sim._explode_torpedo({'ownerPlayerId': 'bot001', 'tid': 98,
                    'x': bot['position']['x'], 'y': bot['position']['y'], 'z': bot['position']['z']},
                    direct_hit_id=bot['id'], damage=100, hit_target_id=bot['id'])
                sim.torpedoes.clear()

        try:
            with patch.object(env.runner, 'step', step):
                result = duel(env, policy, 12, rows.append)
            self.assertEqual(result['first']['outcome'], 'loss')
            self.assertEqual(result['settled']['outcome'], 'draw')
            self.assertEqual(policy.calls, 1)
            self.assertEqual(sum(result['damage'].values()), 300)
            self.assertFalse(result['settled']['pending'])
            self.assertIsNotNone(result['settled']['ammo']['bot001']['torpedo_ammo'])
        finally:
            env.close()

    def test_timeout_no_extra_decision(self):
        env = SubmarineDuelEnv(agent_boat_type='destroyer', control_version='destroyer_duel_v2',
                               max_physics_steps=5)
        policy = IdlePolicy()
        try:
            result = duel(env, policy, 12, lambda row: None)
            self.assertEqual(result['first']['tick'], 5)
            self.assertEqual(result['settled']['tick'], 5)
            self.assertEqual(policy.calls, 1)
            self.assertEqual(pending_torpedoes(env.runner.sim, {'not_an_owner'}), [])
        finally:
            env.close()


if __name__ == '__main__':
    unittest.main()
