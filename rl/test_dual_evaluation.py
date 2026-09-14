"""Selection des deux modes sans modifier les politiques de production."""

import copy
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import torch
from sb3_contrib import RecurrentPPO

from rl.evaluate_ai import evaluate
from rl.rl_env import SubmarineDuelEnv
from rl.train_ai import MatchScoreEvalCallback, load_config, sampled_seed_offsets

CONFIG = Path(__file__).resolve().parent / 'configs' / 'aidest_v6_dual_eval.json'


class DualEvaluationTests(unittest.TestCase):
    def test_cli_wires_both_callbacks_in_new_run(self):
        from rl.train_ai import main

        config = self.config()
        config['env'].pop('fixed_opponent_policy')
        config['training'].update(total_steps=8, n_envs=1, n_steps=8,
                                  batch_size=8, n_epochs=1, seed=42)
        config['model'].update(net_arch=[16], lstm_hidden_size=16)
        config['evaluation'].update(every_steps=8, episodes=1)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'config.json'
            path.write_text(json.dumps(config))
            with patch('rl.train_ai.BASE_DIR', root), patch('sys.argv', [
                    'train_ai', '--config', str(path), '--run-name', 'smoke', '--device', 'cpu']):
                main()
            output = root / 'models_rl/smoke'
            self.assertTrue((output/'best/best_model.zip').is_file())
            self.assertTrue((output/'sampled/best/best_model.zip').is_file())
            self.assertTrue((output/'policy_final.zip').is_file())
            self.assertEqual(2, len(json.loads((output/'sampled/evaluation/match_scores.jsonl').read_text())['opponents']))

    def config(self):
        config = load_config(str(CONFIG))
        config['env']['max_physics_steps'] = 5
        config['evaluation'].pop('fixed_opponent_policy')
        config['evaluation']['sampled_action_seed_offsets'] = [0, 1000000]
        return config

    def test_protocol_preserves_training_and_validates_repetitions(self):
        original = load_config(str(CONFIG.with_name('aidest_v6.json')))
        dual = load_config(str(CONFIG))
        for key in ('training', 'model', 'env', 'reward', 'league'):
            self.assertEqual(original[key], dual[key])
        self.assertEqual((), sampled_seed_offsets(original))
        self.assertEqual((0, 1000000, 2000000), sampled_seed_offsets(dual))
        for invalid in (None, [], [0], [0, 0], [0, True], [0, -1], [0, 1.5], '0,1'):
            dual['evaluation']['sampled_action_seed_offsets'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                sampled_seed_offsets(dual)
        dual['evaluation']['sampled_action_seed_offsets'] = [0, 2**63]
        with self.assertRaises(ValueError):
            MatchScoreEvalCallback(dual, Path('/unused'), 8, 1, 42)

    def test_repeated_scores_keep_opponent_weights(self):
        config = load_config(str(CONFIG))
        config['evaluation']['sampled_action_seed_offsets'] = [0, 1, 2]
        config['evaluation']['opponents'] = [
            {'boat_type': 'submarine', 'ai': 'low', 'weight': 1},
            {'boat_type': 'submarine', 'ai': 'high', 'weight': 3},
        ]
        calls = []

        def evaluated(model, map_name, boat, ai, episodes, seed, *args, **kwargs):
            calls.append((ai, seed, kwargs.copy()))
            wins = (4 if args else {'low': 2, 'high': 6}[ai]) + kwargs['action_seed_offset']
            return {'episodes': 10, 'wins': wins, 'losses': 10-wins, 'draws': 0,
                    'action_seed_offset': kwargs['action_seed_offset']}

        callback = MatchScoreEvalCallback(config, Path('/unused'), 8, 10, 42, sampled=True)
        callback.model = object()
        with patch('rl.train_ai.evaluate_policy', side_effect=evaluated):
            score, details = callback._evaluate()
        self.assertAlmostEqual(.55, score)
        self.assertAlmostEqual(1, sum(d['selection_weight'] for d in details))
        self.assertEqual(9, len(calls))
        self.assertEqual({42}, {seed for _, seed, _ in calls})
        self.assertTrue(all(not k['deterministic'] and k['include_episodes'] for _, _, k in calls))
        self.assertEqual([0]*3 + [1]*3 + [2]*3, [k['action_seed_offset'] for _, _, k in calls])

    def test_real_training_saves_both_modes_then_retains_best_independently(self):
        config = self.config()
        env = SubmarineDuelEnv(max_physics_steps=5, agent_boat_type='destroyer',
                               control_version='destroyer_duel_v2', seed=42)
        try:
            model = RecurrentPPO('MlpLstmPolicy', env, n_steps=8, batch_size=8,
                n_epochs=1, policy_kwargs={'net_arch': [16], 'lstm_hidden_size': 16},
                device='cpu', seed=42, verbose=0)
            with TemporaryDirectory() as directory:
                root = Path(directory)
                det = MatchScoreEvalCallback(config, root, 8, 1, 900000)
                sampled = MatchScoreEvalCallback(config, root, 8, 1, 900000, sampled=True)
                model.learn(total_timesteps=8, callback=[det, sampled])
                det_zip, sampled_zip = root/'best/best_model.zip', root/'sampled/best/best_model.zip'
                self.assertTrue(det_zip.is_file() and sampled_zip.is_file())
                for callback, path, mode in ((det, root, 'deterministic'),
                                             (sampled, root/'sampled', 'sampled')):
                    metadata = json.loads((path/'best/selection.json').read_text())
                    self.assertEqual(mode, metadata['inference_mode'])
                    self.assertEqual(8, metadata['timesteps'])
                    self.assertEqual(.5, metadata['match_score'])
                    self.assertIn('episode_results', metadata['opponents'][0])
                    restored = MatchScoreEvalCallback(config, root, 8, 1, 900000,
                                                      sampled=callback.sampled)
                    restored.init_callback(model)
                    self.assertEqual(.5, restored.best_score)
                old_det, old_sampled = det_zip.read_bytes(), sampled_zip.read_bytes()
                det.num_timesteps = sampled.num_timesteps = 16
                with patch.object(det, '_evaluate', return_value=(.4, [])), \
                        patch.object(sampled, '_evaluate', return_value=(.7, [])):
                    det._on_step()
                    sampled._on_step()
                self.assertEqual(old_det, det_zip.read_bytes())
                self.assertEqual(.7, sampled.best_score)
                self.assertEqual(.5, det.best_score)
                self.assertEqual(16, json.loads((root/'sampled/best/selection.json').read_text())['timesteps'])
                det.num_timesteps = sampled.num_timesteps = 24
                with patch.object(det, '_evaluate', return_value=(.8, [])), \
                        patch.object(sampled, '_evaluate', return_value=(.7, [])):
                    before = sampled_zip.read_bytes()
                    det._on_step()
                    sampled._on_step()
                    self.assertEqual(before, sampled_zip.read_bytes())
                self.assertNotEqual(old_det, det_zip.read_bytes())
                config2 = copy.deepcopy(config)
                config2['evaluation']['sampled_action_seed_offsets'] = [0, 2000000]
                with self.assertRaises(RuntimeError):
                    MatchScoreEvalCallback(config2, root, 8, 1, 900000, sampled=True).init_callback(model)
        finally:
            env.close()

    def test_sampled_evaluation_repeats_and_preserves_rng_and_weights(self):
        env = SubmarineDuelEnv(max_physics_steps=5)
        try:
            model = RecurrentPPO('MlpLstmPolicy', env, n_steps=8, batch_size=8,
                policy_kwargs={'net_arch': [16], 'lstm_hidden_size': 16},
                device='cpu', seed=42, verbose=0)
            weights = {k: v.clone() for k, v in model.policy.state_dict().items()}
            rng = torch.get_rng_state().clone()
            py_rng, np_rng = random.getstate(), np.random.get_state()
            calls = []
            predict = model.predict

            def recorded(*args, **kwargs):
                action, state = predict(*args, **kwargs)
                calls.append((kwargs['deterministic'], action.tolist()))
                return action, state

            with patch.object(model, 'predict', side_effect=recorded):
                histories = []
                for _ in range(2):
                    calls.clear()
                    result = evaluate(model, 'testCombats', 'submarine', 'autosub', 3, 42,
                                      env_options={'max_physics_steps': 5}, include_episodes=True,
                                      deterministic=False, action_seed_offset=1000000)
                    histories.append(copy.deepcopy(calls))
                    self.assertEqual([1000042, 1000043, 1000044],
                                     [r['action_seed'] for r in result['episode_results']])
                self.assertEqual(histories[0], histories[1])
                self.assertTrue(all(not mode for mode, _ in calls))
            self.assertTrue(torch.equal(rng, torch.get_rng_state()))
            self.assertEqual(py_rng, random.getstate())
            self.assertTrue(np.array_equal(np_rng[1], np.random.get_state()[1]))
            for k, value in weights.items():
                self.assertTrue(torch.equal(value, model.policy.state_dict()[k]))
        finally:
            env.close()


if __name__ == '__main__':
    unittest.main()
