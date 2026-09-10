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
            self.assertFalse(result['weapon_invalid'])
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
                sim.spawn_bot_torpedo(bot)
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
