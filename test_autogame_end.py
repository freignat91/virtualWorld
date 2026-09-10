"""Conditions et cycle de vie reels, sans ecoute reseau ni import du serveur."""

import ast
import json
import logging
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from autogame import AutogameEnd
from events import BoatSunk, PlayerLeft


def functions(names: set, namespace: dict) -> dict:
    tree = ast.parse(Path("server.py").read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "server.py", "exec"), namespace)
    return namespace


class AutogameEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Mock(return_value=100.0)
        self.members = {"a": "red", "b": "red", "c": "blue"}

    def end(self, kind: str = "anyBoatSunk", duration: float = None) -> AutogameEnd:
        condition = {"type": kind} if kind else None
        if kind == "teamEliminated":
            condition["teamId"] = "red"
        return AutogameEnd(self.members, condition, duration, self.clock)

    def sink(self, end: AutogameEnd, *ids: str) -> None:
        end.record([BoatSunk(victim_id=pid, attacker_id=None) for pid in ids])

    def test_absent_and_non_scenario_events(self) -> None:
        end = self.end(None)
        self.sink(end, "a", "b", "c")
        self.clock.return_value = 100000
        self.assertIsNone(end.evaluate())
        end = self.end()
        self.sink(end, "human", "manual-bot")
        end.record([PlayerLeft(player_id="a")])
        self.assertIsNone(end.evaluate())

    def test_any_boat_allied_or_enemy_and_once(self) -> None:
        for pid in self.members:
            end = self.end()
            self.assertIsNone(end.evaluate())
            self.sink(end, pid)
            result = end.evaluate()
            self.assertEqual("anyBoatSunk", result["reason"])
            self.assertEqual([pid], result["triggeringBoatIds"])
            self.sink(end, "b")
            self.assertIsNone(end.evaluate())

    def test_team_modes_and_accumulated_sinks(self) -> None:
        for kind in ("teamEliminated", "anyTeamEliminated"):
            end = self.end(kind)
            self.sink(end, "a")
            self.assertIsNone(end.evaluate())
            self.sink(end, "b")
            result = end.evaluate()
            self.assertEqual(["red"], result["eliminatedTeamIds"])
            self.assertEqual(["blue"], result["winningTeamIds"])
            self.assertEqual(["b"], result["triggeringBoatIds"])
        end = self.end("teamEliminated")
        self.sink(end, "c")
        self.assertIsNone(end.evaluate())
        end = self.end("anyTeamEliminated")
        self.sink(end, "c")
        self.assertEqual(["red"], end.evaluate()["winningTeamIds"])

    def test_simultaneous_draw_independent_of_event_order(self) -> None:
        for kind in ("anyBoatSunk", "anyTeamEliminated", "teamEliminated"):
            for ids in (("a", "b", "c"), ("c", "b", "a")):
                end = self.end(kind)
                self.sink(end, *ids)
                result = end.evaluate()
                self.assertTrue(result["draw"])
                self.assertEqual([], result["winningTeamIds"])
                self.assertEqual(["blue", "red"], result["eliminatedTeamIds"])

    def test_monotonic_timeout_and_condition_priority(self) -> None:
        for kind in (None, "anyBoatSunk"):
            end = self.end(kind, 10)
            self.clock.return_value = end.started + 9.99
            self.assertIsNone(end.evaluate())
            self.clock.return_value = end.started + 10
            result = end.evaluate()
            self.assertEqual("timeout", result["reason"])
            self.assertEqual(10, result["elapsedSeconds"])
            self.assertFalse(result["draw"])
            self.assertEqual([], result["winningTeamIds"])
        end = self.end(duration=10)
        self.clock.return_value += 10
        self.sink(end, "a")
        self.assertEqual("anyBoatSunk", end.evaluate()["reason"])

    def test_dispatch_trace_close_shutdown_order_and_failure(self) -> None:
        for trace_failure in (False, True):
            calls = Mock()
            end = self.end()
            ns = functions({"dispatch_events", "finish_autogame"}, dict(
                autogame_end=end, game_trace=calls.trace, players={}, torpedoes_server={},
                EVENT_DISPATCH={BoatSunk: calls.dispatch}, logging=calls.log,
                print=calls.stdout, json=json, current_map_name="world",
                autogame_boats=[dict(id="a", ai_name="autodest", team_id="red")],
                sim=Mock(), sys=sys, __name__=__name__, autogame_shutdown=calls.shutdown))
            calls.log.getLogger.return_value.handlers = [calls.handler]
            if trace_failure:
                calls.trace._write.side_effect = OSError("disk full")
            ns["dispatch_events"]([BoatSunk(victim_id="a", attacker_id=None)])
            self.assertTrue(ns["finish_autogame"]())
            self.assertFalse(ns["finish_autogame"]())
            names = [c[0] for c in calls.mock_calls]
            ordered = ["trace.event", "dispatch", "log.info", "stdout", "trace.observe",
                       "trace._write", "trace.close", "handler.flush", "shutdown.send"]
            self.assertEqual(sorted(names.index(n) for n in ordered), [names.index(n) for n in ordered])
            calls.shutdown.send.assert_called_once()
            if trace_failure:
                calls.trace._disable.assert_called_once()

    def test_wait_default_false_and_surviving_owners_do_not_block(self) -> None:
        for flag in (None, False, True):
            end = self.end()
            if flag is not None:
                end.condition["waitForTorpedoes"] = flag
            self.sink(end, "a")
            torpedoes = [dict(ownerPlayerId="c", tid=1), dict(ownerPlayerId="human", tid=1)]
            if flag is not True:
                torpedoes.append(dict(ownerPlayerId="a", tid=1))
            self.assertIsNotNone(end.evaluate(torpedoes))
            self.assertIsNone(end.settling)

    def test_settling_all_sunk_owners_duplicate_tids_and_posthumous_draw(self) -> None:
        for kind in ("anyBoatSunk", "anyTeamEliminated", "teamEliminated"):
            end = self.end(kind)
            end.condition["waitForTorpedoes"] = True
            torpedoes = {(pid, 1): dict(ownerPlayerId=pid, tid=1) for pid in self.members}
            self.sink(end, "a", "b")
            self.assertIsNone(end.evaluate(torpedoes.values()))
            self.assertFalse(end.finished)
            first = end.settling
            self.assertEqual(2, first["outstandingTorpedoCount"])
            self.assertEqual(2, first["outstandingOwnerCount"])
            del torpedoes[("a", 1)]
            self.assertIsNone(end.evaluate(torpedoes.values()))
            self.sink(end, "c")
            del torpedoes[("b", 1)]
            self.assertIsNone(end.evaluate(torpedoes.values()))
            self.assertIs(first, end.settling)
            del torpedoes[("c", 1)]
            result = end.evaluate(torpedoes.values())
            self.assertTrue(result["draw"])
            self.assertEqual([], result["winningTeamIds"])
            self.assertEqual(sorted(self.members), result["sunkBoatIds"])

    def test_wait_requires_condition_and_timeout_bounds_settling(self) -> None:
        for kind in ("anyBoatSunk", "anyTeamEliminated", "teamEliminated"):
            for trigger in (False, True):
                end = self.end(kind, 10)
                end.condition["waitForTorpedoes"] = True
                torpedoes = [dict(ownerPlayerId="a", tid=1)]
                if trigger:
                    self.sink(end, "a", "b")
                elif kind != "anyBoatSunk":
                    self.sink(end, "a")
                self.assertIsNone(end.evaluate(torpedoes))
                self.assertEqual(trigger, end.settling is not None)
                self.clock.return_value = end.started + 10
                result = end.evaluate(torpedoes)
                self.assertEqual("timeout", result["reason"])
                self.assertEqual([], result["winningTeamIds"])
                self.assertFalse(result["draw"])

    def test_settling_trace_once_before_final_dispatch_snapshot_and_shutdown(self) -> None:
        for trace_failure in (False, True):
            end = self.end()
            end.condition["waitForTorpedoes"] = True
            calls = Mock()
            torpedoes = {("c", 1): dict(ownerPlayerId="c", tid=1)}
            ns = functions({"dispatch_events", "finish_autogame"}, dict(
                autogame_end=end, game_trace=calls.trace, players={}, torpedoes_server=torpedoes,
                EVENT_DISPATCH={BoatSunk: calls.dispatch}, logging=calls.log,
                print=calls.stdout, json=json, current_map_name="world", autogame_boats=[],
                sim=Mock(), sys=sys, __name__=__name__, autogame_shutdown=calls.shutdown))
            calls.log.getLogger.return_value.handlers = []
            if trace_failure:
                calls.trace._write.side_effect = OSError("disk full")
            ns["dispatch_events"]([BoatSunk(victim_id="c", attacker_id="a")])
            self.assertFalse(ns["finish_autogame"]())
            self.assertFalse(ns["finish_autogame"]())
            calls.trace._write.assert_called_once()
            self.assertEqual("autogame_settling", calls.trace._write.call_args.args[0])
            calls.trace.close.assert_not_called()
            calls.stdout.assert_not_called()
            calls.shutdown.send.assert_not_called()
            if trace_failure:
                calls.trace._disable.assert_called_once()
            ns["dispatch_events"]([BoatSunk(victim_id=pid, attacker_id="c") for pid in ("a", "b")])
            torpedoes.clear()
            self.assertTrue(ns["finish_autogame"]())
            self.assertTrue(calls.trace._write.call_args.args[1]["draw"])
            names = [c[0] for c in calls.mock_calls]
            self.assertLess(max(i for i, n in enumerate(names) if n == "dispatch"), names.index("trace.observe"))
            self.assertLess(names.index("trace.close"), names.index("shutdown.send"))

    def test_preparation_clock_timeout_and_started_trace_once(self) -> None:
        for delay in (0, 30):
            self.clock.return_value = 100
            end = self.end(duration=10)
            end.condition["waitForTorpedoes"] = True
            end.started = None
            trace = Mock(enabled=True)
            ns = functions({"start_autogame_if_ready"}, dict(
                autogame_preparation=dict(startDelaySeconds=delay, readyMonotonic=100,
                                          plannedStartMonotonic=100 + delay),
                autogame_end=end, time=SimpleNamespace(monotonic=self.clock, time=self.clock),
                bots={"a": {"next_depth_change_at": 150}},
                game_trace=trace, logging=logging, json=json, sim=Mock(), sys=sys, __name__=__name__))
            if delay:
                self.clock.return_value = 129.99
                self.assertFalse(ns["start_autogame_if_ready"]())
                self.sink(end, "a")
                self.assertIsNone(end.evaluate())
                trace._write.assert_not_called()
            self.clock.return_value = 100 + delay
            self.assertTrue(ns["start_autogame_if_ready"]())
            self.assertEqual(100 + delay, end.started)
            self.assertEqual(150 + delay, ns["bots"]["a"]["next_depth_change_at"])
            self.assertIsNone(end.evaluate())
            self.assertTrue(ns["start_autogame_if_ready"]())
            trace._write.assert_called_once()
            self.assertEqual("autogame_started", trace._write.call_args.args[0])
            self.assertEqual(100 + delay, trace._write.call_args.args[1]["startedMonotonic"])
            trace.observe.assert_called_once()
            self.clock.return_value += 9.99
            self.assertIsNone(end.evaluate())
            self.clock.return_value = 110 + delay
            self.assertEqual(10, end.evaluate()["elapsedSeconds"])

    def test_ticker_waits_without_steps_decisions_dispatch_or_finish(self) -> None:
        for delay in (0, 30):
            clock = Mock(return_value=100.0)
            calls = Mock()
            calls.trace.enabled = False
            calls.sim.drain_events.return_value = []
            ns = functions({"bot_ticker", "start_autogame_if_ready"}, dict(
                autogame_preparation=dict(readyMonotonic=100, plannedStartMonotonic=100 + delay), autogame_end=None,
                time=SimpleNamespace(time=clock, monotonic=clock), game_trace=calls.trace,
                logging=logging, json=json, sim=calls.sim, sys=sys, __name__=__name__,
                socketio=calls.socketio, BOT_TICK_INTERVAL=0.05, BOT_DT_MAX=0.1,
                bots={"a": {}}, players={}, load_world=lambda: {}, current_map_name="world",
                sim_tick_multiplier=2, dispatch_events=calls.dispatch,
                finish_autogame=Mock(return_value=True),
                _ws_diag=dict(tick_count=0, gap_sum=0, gap_max=0)))
            times = iter((100.05, 129.95, 130.0) if delay else (100.05,))

            def sleep(interval: float) -> None:
                calls.sim.step.assert_not_called()
                calls.sim.drain_events.assert_not_called()
                ns["finish_autogame"].assert_not_called()
                clock.return_value = next(times)

            calls.socketio.sleep.side_effect = sleep
            ns["bot_ticker"]()
            self.assertEqual(2, calls.sim.step.call_count)
            for call in calls.sim.step.call_args_list:
                self.assertAlmostEqual(0.05, call.args[0])
            calls.sim.drain_events.assert_called_once()
            ns["finish_autogame"].assert_called_once()
            calls.dispatch.assert_not_called()

    def test_both_beacon_tickers_wait_without_detection(self) -> None:
        for name in ("sonar_beacon_ticker", "passive_sonar_beacon_ticker"):
            socketio = Mock()
            socketio.sleep.side_effect = [None, RuntimeError("end test")]
            world = Mock()
            ns = functions({name}, dict(socketio=socketio, autogame_preparation={},
                                        SONAR_BEACON_PING_INTERVAL=1, PASSIVE_BEACON_TICK_INTERVAL=1,
                                        load_world=world))
            with self.assertRaisesRegex(RuntimeError, "end test"):
                ns[name]()
            world.assert_not_called()
            socketio.emit.assert_not_called()

    def test_non_listening_process_lifecycle(self) -> None:
        for mode, code in (("finish", 0), ("delay", 0), ("settling", 0), ("failure", 1), ("return", 0)):
            result = subprocess.run([sys.executable, __file__, "--lifecycle", mode],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(code, result.returncode, result.stderr)
            if mode in ("finish", "delay", "settling"):
                self.assertIn("autogame_end", result.stdout)
                self.assertIn("main returned", result.stdout)
            if mode == "failure":
                self.assertIn("fake listen failure", result.stderr)

    def test_ticker_drains_final_batch_even_when_empty(self) -> None:
        for idle in (False, True):
            calls = Mock()
            calls.trace.tick = 0
            end = self.end("anyTeamEliminated")
            pending = [BoatSunk(victim_id=pid, attacker_id=None) for pid in self.members]
            sim = calls.sim
            sim.drain_events.return_value = pending
            ns = functions({"bot_ticker", "dispatch_events", "finish_autogame"}, dict(
                autogame_end=end, autogame_shutdown=calls.shutdown, autogame_boats=[],
                game_trace=calls.trace, players={}, bots={} if idle else {"a": {}},
                torpedoes_server={}, drones_server={}, grenades_server={},
                EVENT_DISPATCH={BoatSunk: calls.dispatch}, logging=calls.log,
                print=calls.stdout, json=json, current_map_name="world",
                sim=sim, sys=sys, __name__=__name__, socketio=calls.socketio,
                start_autogame_if_ready=lambda: True,
                time=SimpleNamespace(time=lambda: 0), BOT_TICK_INTERVAL=0.05,
                BOT_DT_MAX=0.1, load_world=lambda: {}, sim_tick_multiplier=2,
                _ws_diag=dict(tick_count=0, gap_sum=0, gap_max=0, events_sum=0,
                              dispatch_time_sum=0, dispatch_time_max=0)))
            calls.log.getLogger.return_value.handlers = []
            ns["bot_ticker"]()
            self.assertEqual(0 if idle else 2, sim.step.call_count)
            self.assertEqual(3, calls.dispatch.call_count)
            calls.shutdown.send.assert_called_once()
            self.assertTrue(calls.trace._write.call_args.args[1]["draw"])


def lifecycle(mode: str) -> None:
    import eventlet
    clock = Mock(return_value=0)
    ns = functions({"run_server", "finish_autogame", "start_autogame_if_ready"}, dict(
        eventlet=eventlet, sys=sys, logging=logging, json=json, app=None, port=0,
        game_trace=Mock(enabled=False), current_map_name="world", autogame_boats=[],
        bots={}, torpedoes_server={}, time=SimpleNamespace(monotonic=clock, time=clock),
        autogame_preparation=dict(readyMonotonic=0, plannedStartMonotonic=30),
        autogame_end=AutogameEnd({"a": "red"}, None, 1, clock)))

    def serve(*args: object, **kwargs: object) -> None:
        if mode == "failure":
            raise RuntimeError("fake listen failure")
        if mode == "settling":
            end = ns["autogame_end"]
            end.condition = {"type": "anyBoatSunk", "waitForTorpedoes": True}
            ns["torpedoes_server"][("a", 1)] = dict(ownerPlayerId="a", tid=1)
            end.record([BoatSunk(victim_id="a", attacker_id=None)])
            assert not ns["finish_autogame"]()
            eventlet.sleep(0)
            ns["torpedoes_server"].clear()
        if mode == "delay":
            ns["autogame_end"].started = None
            clock.return_value = 29
            assert not ns["start_autogame_if_ready"]()
            assert not ns["finish_autogame"]()
            eventlet.sleep(0)
            clock.return_value = 30
            assert ns["start_autogame_if_ready"]()
            assert not ns["finish_autogame"]()
            clock.return_value = 31
        else:
            clock.return_value = 1
        if mode in ("finish", "delay", "settling"):
            ns["finish_autogame"]()
            # Le serveur factice reste actif : seul le greenlet principal termine.
            while True:
                eventlet.sleep(1)

    ns["socketio"] = SimpleNamespace(run=serve)
    ns["run_server"]()
    print("main returned", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--lifecycle":
        lifecycle(sys.argv[2])
    else:
        unittest.main()
