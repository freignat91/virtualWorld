"""Decisions du RuntimeController reel, sans serveur ni entrainement."""

import ast
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

import events
import simulation
from game_trace import GameTrace
from rl.headless import HeadlessRunner
from rl.rl_control import apply_action, build_observation, control_spec
from rl.rl_runtime import RuntimeController, attach_controller


class DecisionTraceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "trace.jsonl"
        self.runner = HeadlessRunner(seed=4)
        self.runner.world.update(islands=[], thermoclines=[])

    def scene(self, boat_type="submarine", version=None):
        self.runner.reset(seed=4)
        sid = self.runner.spawn_bot(boat_type, external_control=True,
                                   position=(0, 0), rotation=0)
        self.bot = self.runner.sim.bots[sid]
        self.bot["rl_control_version"] = control_spec(boat_type, version)[0]
        self.bot.update(name="SECRET", bb={"token": "SECRET"})
        self.runner.sim.drain_events()
        return self.runner.sim

    def trace(self, enabled=True):
        trace = GameTrace(enabled=enabled, path=self.path)
        self.addCleanup(trace.close)
        return trace

    def test_exact_vectors_results_cadence_and_visible_identity_all_schemas(self) -> None:
        for boat_type, version, action in (
            ("submarine", None, [2, 3, 3, 1, 1]),
            ("destroyer", None, [2, 3, 1, 1, 1]),
            ("destroyer", "destroyer_duel_v2", [2, 3, 1, 1, 1, 0]),
        ):
            with self.subTest(boat_type=boat_type, version=version):
                sim = self.scene(boat_type, version)
                sim.trace_rl_decisions = True
                sim.trace_step = 7
                base = dict(ownerPlayerId="public-owner", tid=1, y=self.bot["position"]["y"],
                            z=0, dirX=1, dirZ=0, speed=2, ownerSid="SECRET",
                            lockedKey="SECRET", acquiredBoatId="SECRET")
                sim.torpedoes.update(passed=dict(base, x=1), incoming=dict(base, x=-10, tid=2))
                model = SimpleNamespace(predict=Mock(return_value=(np.array(action), "SECRET")))
                controller = RuntimeController(model)
                trace = self.trace()
                results = []

                def apply(bot, current_sim, chosen):
                    result = apply_action(bot, current_sim, chosen)
                    results.append(dict(result))
                    return result

                with patch("rl.rl_runtime.build_observation", wraps=build_observation) as builder, \
                        patch.object(sim, "detect_enemies_passive", wraps=sim.detect_enemies_passive) as sonar, \
                        patch("simulation.torpedo_radar_threat", wraps=simulation.torpedo_radar_threat) as radar, \
                        patch("rl.rl_runtime.apply_action", side_effect=apply):
                    controller.tick(self.bot, sim, self.runner.world, 0.05)
                    controller.tick(self.bot, sim, self.runner.world, 0.05)
                    self.assertEqual(builder.call_count, 1)
                    self.assertEqual(sonar.call_count, 1)
                    self.assertEqual(radar.call_count, 2)
                    decision = next(e for e in sim.drain_events() if isinstance(e, events.RLDecision))
                    self.assertEqual(decision.observation, model.predict.call_args.args[0].tolist())
                    self.assertEqual(len(decision.observation), control_spec(boat_type, version)[1])
                    self.assertEqual(decision.action, action)
                    self.assertEqual(decision.result, results[0])
                    self.assertFalse(decision.result["weapon_invalid"])
                    self.assertTrue(decision.result["weapon_fired"])
                    self.assertTrue(decision.result["lure_dropped"])
                    self.assertEqual(decision.visible_threat, {"owner_id": "public-owner", "tid": 2})
                    self.assertEqual((decision.decision_at, decision.physics_dt, decision.simulation_step),
                                     (sim.now(), 0.05, 7))
                    self.assertTrue(decision.episode_start)
                    decision.result["token"] = "SECRET"
                    decision.visible_threat["lockedKey"] = "SECRET"
                    trace.event(decision, sim.players)
                    sim.torpedoes.clear()
                    self.runner._time += 0.25
                    sim.trace_step = 12
                    controller.tick(self.bot, sim, self.runner.world, 0.05)
                    second = next(e for e in sim.drain_events() if isinstance(e, events.RLDecision))
                    self.assertIsNone(second.visible_threat)
                    self.assertFalse(second.episode_start)
                    self.assertEqual(second.simulation_step, 12)
                    self.assertEqual(builder.call_count, 2)
                    self.assertEqual(sonar.call_count, 2)
                    self.assertEqual(radar.call_count, 2)
                    trace.event(second, sim.players)
                rows = [json.loads(line) for line in self.path.read_text().splitlines()]
                self.assertEqual(sum(r["type"] == "rl_model" for r in rows), 1)
                saved = [r["data"]["fields"] for r in rows if r["type"] == "event"]
                self.assertEqual(saved[0]["observation"], decision.observation)
                self.assertEqual(saved[0]["result"], results[0])
                self.assertNotIn("SECRET", self.path.read_text())
                trace.close()

    def test_off_has_no_event_copy_hash_metadata_or_file(self) -> None:
        sim = self.scene()
        controller = RuntimeController(Mock(predict=Mock(return_value=(np.array([2, 1, 0, 0, 0]), None))))
        trace = self.trace(enabled=False)
        with patch("rl.rl_runtime.events.RLDecision", side_effect=AssertionError), \
                patch("rl.rl_runtime.hashlib.sha256", side_effect=AssertionError):
            controller.tick(self.bot, sim, self.runner.world, 0.05)
        self.assertNotIn("rl_visible_threat", self.bot)
        self.assertEqual(sim.drain_events(), [])
        trace.event(Mock(), {})
        self.assertFalse(self.path.exists())

    def test_capture_and_write_failures_do_not_repeat_action_or_leak(self) -> None:
        sim = self.scene()
        sim.trace_rl_decisions = True
        model = Mock(predict=Mock(return_value=(np.array([2, 3, 0, 0, 0]), None)))
        controller = RuntimeController(model)
        with patch.object(sim, "emit", side_effect=OSError("SECRET")), \
                self.assertLogs(level="WARNING") as logs:
            controller.tick(self.bot, sim, self.runner.world, 0.05)
        self.assertEqual(self.bot["control_target_speed_ratio"], 0.65)
        controller.tick(self.bot, sim, self.runner.world, 0.05)
        self.assertEqual(model.predict.call_count, 1)
        self.assertNotIn("SECRET", str(logs.output))
        controller.next_decision_at = 0
        controller.tick(self.bot, sim, self.runner.world, 0.05)
        decision = sim.drain_events()[-1]
        trace = self.trace()
        with patch.object(trace.handler, "shouldRollover", side_effect=OSError("SECRET")), \
                self.assertLogs("game_trace", level="WARNING"):
            trace.event(decision, {})
        self.assertFalse(trace.enabled)

    def test_trace_vectors_reject_non_numeric_and_nonfinite_values(self) -> None:
        sim = self.scene()
        sim.trace_rl_decisions = True
        controller = RuntimeController(SimpleNamespace(
            predict=lambda *args, **kwargs: (np.array([2, 1, 0, 0, 0]), None)))
        controller.tick(self.bot, sim, self.runner.world, 0.05)
        decision = sim.drain_events()[-1]
        for invalid in ("SECRET", float("nan")):
            with self.subTest(invalid=invalid):
                trace = self.trace()
                decision.observation[0] = invalid
                with self.assertLogs("game_trace", level="WARNING"):
                    trace.event(decision, {})
                self.assertFalse(trace.enabled)
                self.assertNotIn("SECRET", self.path.read_text())

    def test_real_tiny_model_loaded_bytes_hash_once_and_runtime(self) -> None:
        from sb3_contrib import RecurrentPPO
        from rl.rl_env import SubmarineDuelEnv

        env = SubmarineDuelEnv()
        self.addCleanup(env.close)
        model = RecurrentPPO("MlpLstmPolicy", env, n_steps=8, batch_size=8,
                             policy_kwargs=dict(lstm_hidden_size=8, net_arch=[8]),
                             device="cpu", seed=4)
        root = Path(self.tmp.name)
        run = root / "tiny"
        run.mkdir()
        path = run / "policy_final.zip"
        model.save(path)
        expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        sim = self.scene()
        sim.trace_rl_decisions = True
        with patch("rl.rl_runtime.MODELS_DIR", root), patch("rl.rl_runtime._MODEL_CACHE", {}), \
                patch("rl.rl_runtime.hashlib.sha256", wraps=hashlib.sha256) as hashing:
            attach_controller(self.bot, "rl_tiny", trace_enabled=True)
            attach_controller(self.bot, "rl_tiny", trace_enabled=True)
            controller = self.bot["rl_controller"]
            for _ in range(2):
                controller.tick(self.bot, sim, self.runner.world, 0.05)
                self.runner._time += 0.25
            self.assertEqual(hashing.call_count, 1)
        decisions = [e for e in sim.drain_events() if isinstance(e, events.RLDecision)]
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0].model_id, "tiny/policy_final.zip")
        self.assertEqual(decisions[0].model_sha256, expected_hash)
        self.assertEqual(len(decisions[0].observation), 32)
        self.assertIsNotNone(controller.state)

    def test_server_dispatch_is_explicitly_trace_only(self) -> None:
        tree = ast.parse(Path("server.py").read_text())
        dispatch = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "EVENT_DISPATCH" for t in n.targets))
        handler = next(value for key, value in zip(dispatch.keys, dispatch.values)
                       if isinstance(key, ast.Attribute) and key.attr == "RLDecision")
        self.assertIsInstance(handler, ast.Lambda)
        self.assertIsNone(handler.body.value)


if __name__ == "__main__":
    unittest.main()
