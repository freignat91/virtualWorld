"""Le diagnostic conserve la trajectoire standard avant sa terminaison."""

import unittest

import numpy as np

from rl.diagnose_duels import duel
from rl.rl_env import SubmarineDuelEnv


class ParityTests(unittest.TestCase):
    def test_observations_actions_events_and_ammo_match_standard(self):
        options = dict(agent_boat_type='destroyer', control_version='destroyer_duel_v2',
                       max_physics_steps=100)
        action = np.array([2, 2, 1, 0, 1, 0])
        env = SubmarineDuelEnv(**options)
        expected = []
        try:
            obs, _ = env.reset(seed=731)
            while True:
                expected.append(obs.copy())
                obs, _, terminated, truncated, info = env.step(action)
                if terminated or truncated:
                    break
            stock = dict(env.runner.legacy.torpedo_ammo[env.agent_sid])
        finally:
            env.close()

        class Policy:
            def __init__(self):
                self.calls = 0

            def predict(self, obs, **kwargs):
                np.testing.assert_array_equal(obs, expected[self.calls])
                self.calls += 1
                return action, None

        policy = Policy()
        diagnostic = SubmarineDuelEnv(**options)
        try:
            result = duel(diagnostic, policy, 731, lambda row: None)
            self.assertEqual(policy.calls, len(expected))
            self.assertEqual(result['first']['outcome'], info['outcome'])
            self.assertEqual(result['first']['tick'], info['physics_steps'])
            self.assertEqual(result['first']['ammo']['bot001']['torpedo_ammo'], stock)
            self.assertEqual(result['first']['counts']['first:bot001:weapon_fired'], info['weapons'])
        finally:
            diagnostic.close()


if __name__ == '__main__':
    unittest.main()
