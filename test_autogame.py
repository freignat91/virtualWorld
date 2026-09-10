"""Scenario reel prepare sans serveur ; fonctions serveur executees avec I/O factices."""

import ast
import copy
import io
import json
import logging
import math
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import autogame
import bot_ai
import simulation
import events
from rl.headless import HeadlessRunner, load_boat
from rl.rl_runtime import RuntimeController
from test_integrity import server_functions


class AutogameTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = HeadlessRunner(seed=11)
        self.world = self.runner.world
        self.world.update(islands=[], thermoclines=[])
        self.entry = dict(boatType="destroyer", ai="autodest", teamId="red",
                          position=dict(x=-100, y=-0.2, z=0), rotation=math.pi / 2)
        self.specs = {kind: load_boat(kind) for kind in ("destroyer", "submarine")}

    def load_boat(self, kind: str) -> dict:
        return copy.deepcopy(self.specs[kind])

    def prepare(self, data: object) -> list:
        with patch.object(Path, "open", return_value=io.StringIO(json.dumps(data))):
            return autogame.prepare_autogame(Path("autogame.json"), "world",
                                            self.world, self.load_boat).boats

    def namespace(self) -> dict:
        legacy = self.runner.legacy
        ns = dict(vars(legacy), simulation=simulation, bot_ai=bot_ai,
                  load_world=lambda: self.world, load_boat=self.load_boat,
                  next_bot_id=1, UNIT_METERS_BOT=10, random=random, json=json,
                  time=SimpleNamespace(time=self.runner.sim.now, monotonic=self.runner.sim.now), logging=logging,
                  autogame_end=None,
                  socketio=Mock(), game_trace=SimpleNamespace(enabled=False),
                  _random_spawn_on_nav_graph=Mock(side_effect=AssertionError("random spawn")))
        for weapon in ("torpedo", "drone", "grenade", "cannon", "beacon", "lure", "mine"):
            name = f"init_{weapon}_ammo_for_sid"
            ns[name] = getattr(legacy, name)
        return server_functions({"spawn_bot", "initialize_autogame", "start_autogame_if_ready"}, ns)

    def test_empty_missing_and_invalid_file(self) -> None:
        self.assertEqual([], self.prepare({"boats": []}))
        with self.assertRaises(FileNotFoundError):
            autogame.prepare_autogame(Path("missing-autogame.json"), "world", self.world, load_boat)
        with patch.object(Path, "open", return_value=io.StringIO("{")):
            with self.assertRaises(ValueError):
                autogame.prepare_autogame(Path("unused"), "world", self.world, load_boat)

    def test_validation(self) -> None:
        bad_entries = [dict(self.entry, boatType="unknown"), dict(self.entry, ai="../autodest"),
                       dict(self.entry, ai="missing-tree"), dict(self.entry, teamId=""),
                       dict(self.entry, rotation=True), dict(self.entry, extra=1)]
        for key, value in (("x", math.inf), ("y", -1), ("z", 100000), ("x", "1")):
            entry = copy.deepcopy(self.entry)
            entry["position"][key] = value
            bad_entries.append(entry)
        for bad in bad_entries:
            with self.subTest(entry=bad), self.assertRaises(ValueError):
                self.prepare({"boats": [self.entry, bad]})
        for data in ([], {}, {"boats": {}}, {"boats": [], "extra": 1},
                     {"boats": [], "map": "other"}, {"boats": [self.entry] * 33}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.prepare(data)
        with patch("geometry.point_on_any_island", return_value=True):
            with self.assertRaises(ValueError):
                self.prepare({"boats": [self.entry]})
        with patch("bot_ai.load_ai", return_value=bot_ai.Action("missing-action", {})):
            with self.assertRaises(ValueError):
                self.prepare({"boats": [self.entry]})
        self.assertFalse(self.runner.sim.bots)

    def test_end_validation(self) -> None:
        invalid = [None, {}, [], {"type": []}, {"type": "unknown"},
                   {"type": "anyBoatSunk", "extra": 1},
                   {"type": "anyTeamEliminated", "teamId": "red"},
                   {"type": "teamEliminated"},
                   {"type": "teamEliminated", "teamId": "missing"},
                   {"type": "teamEliminated", "teamId": []}]
        invalid.extend({"type": kind, **({"teamId": "red"} if kind == "teamEliminated" else {}),
                        "waitForTorpedoes": value}
                       for kind in ("anyBoatSunk", "anyTeamEliminated", "teamEliminated")
                       for value in (None, 0, 1, "true", [], {}))
        for condition in invalid:
            with self.subTest(condition=condition), self.assertRaises(ValueError):
                self.prepare(dict(boats=[self.entry], endCondition=condition))
        for duration in (None, True, False, 0, -1, math.inf, math.nan, "10", []):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                self.prepare(dict(boats=[self.entry], maxDurationSeconds=duration))
        for options in ({"endCondition": {"type": "anyBoatSunk"}}, {"maxDurationSeconds": 1}):
            with self.assertRaises(ValueError):
                self.prepare(dict(boats=[], **options))
        for kind in ("anyBoatSunk", "anyTeamEliminated", "teamEliminated"):
            condition = {"type": kind}
            if kind == "teamEliminated":
                condition["teamId"] = "red"
            self.assertEqual(1, len(self.prepare(dict(boats=[self.entry],
                                                     endCondition=condition, maxDurationSeconds=0.1))))
            for flag in (False, True):
                condition["waitForTorpedoes"] = flag
                self.assertEqual(1, len(self.prepare(dict(boats=[self.entry],
                                                         endCondition=condition))))

    def test_start_delay_validation(self) -> None:
        for delay in (None, True, False, -1, math.inf, -math.inf, math.nan, "30", []):
            with self.subTest(delay=delay), self.assertRaises(ValueError):
                self.prepare(dict(boats=[self.entry], startDelaySeconds=delay))
        with self.assertRaises(ValueError):
            self.prepare(dict(boats=[], startDelaySeconds=30))
        for delay in (0, 0.5, 30):
            self.assertEqual(1, len(self.prepare(dict(boats=[self.entry], startDelaySeconds=delay))))
        self.assertEqual([], self.prepare(dict(boats=[], startDelaySeconds=0)))

    def test_real_spawn_exact_initial_state_and_teams(self) -> None:
        sub = dict(self.entry, boatType="submarine", ai="autosub", teamId="blue",
                   position=dict(x=100, y=-30, z=0), rotation=-math.pi / 2)
        prepared = self.prepare({"map": "world", "boats": [self.entry, sub]})
        ns = self.namespace()
        for expected, entry in zip((self.entry, sub), prepared):
            pid = ns["spawn_bot"](**entry)
            sid = "__bot__" + pid
            bot, mirror = ns["bots"][sid], ns["players"][sid]
            self.assertIsNot(bot, mirror)
            for entity in (bot, mirror):
                self.assertEqual(expected["position"], entity["position"])
                self.assertEqual(expected["rotation"], entity["rotation"])
                self.assertEqual(expected["teamId"], entity["team_id"])
            self.assertEqual(expected["position"]["y"], bot["depth_target_y"])
            self.assertEqual(bot["depth_target_y"], bot["spawn_y"])
            self.assertEqual(0, bot["speed"])
            self.assertEqual(200 if expected["boatType"] == "destroyer" else 100,
                             bot["maxIntegrity"])
            self.assertIn(sid, self.runner.legacy.torpedo_ammo)
        self.assertEqual(2, ns["socketio"].emit.call_count)

    def test_documented_world_positions(self) -> None:
        self.world = json.loads(Path("maps/world.json").read_text())
        entries = [dict(self.entry, position=dict(x=x, y=-0.2, z=600), rotation=rotation)
                   for x, rotation in ((-100, math.pi), (100, 0))]
        self.assertEqual(2, len(self.prepare({"map": "world", "boats": entries})))
        self.assertGreater(-math.cos(entries[0]["rotation"]), 0)
        self.assertLess(-math.cos(entries[1]["rotation"]), 0)

    def test_initialized_tracking_uses_real_native_sinks(self) -> None:
        ns = self.startup(["--autogame"])
        data = dict(boats=[self.entry, dict(self.entry, teamId="blue")],
                    endCondition={"type": "anyTeamEliminated"}, maxDurationSeconds=10)
        with patch.object(Path, "open", return_value=io.StringIO(json.dumps(data))):
            ns["initialize_autogame"]()
        end = ns["autogame_end"]
        self.assertIsNone(end.started)
        self.assertTrue(ns["start_autogame_if_ready"]())
        self.assertEqual({"red", "blue"}, set(end.members.values()))
        self.assertEqual(10, end.max_duration)
        self.assertIsNone(end.evaluate())
        for sid, bot in list(ns["sim"].bots.items()):
            ns["sim"].sink_bot(sid, bot, attacker_id=None)
        pending = ns["sim"].drain_events()
        self.assertEqual(2, sum(isinstance(e, events.BoatSunk) for e in pending))
        end.record(pending)
        self.assertTrue(end.evaluate()["draw"])

    def test_native_torpedo_survives_owner_then_range_or_posthumous_hit(self) -> None:
        for hit in (False, True):
            runner = HeadlessRunner(seed=11)
            runner.world.update(islands=[], thermoclines=[])
            sim = runner.sim
            owner_sid = runner.spawn_bot("destroyer", external_control=True,
                                         position=(0, 0), team_id="red")
            target_sid = runner.spawn_bot("destroyer", external_control=True,
                                          position=(100, 0), team_id="blue")
            owner, target = sim.bots[owner_sid], sim.bots[target_sid]
            end = autogame.AutogameEnd({owner["id"]: "red", target["id"]: "blue"},
                                      {"type": "anyBoatSunk", "waitForTorpedoes": True},
                                      600, sim.now)
            self.assertTrue(sim.spawn_bot_torpedo(owner, target))
            torpedo = next(iter(sim.torpedoes.values()))
            sim.sink_bot(owner_sid, owner, attacker_id=target["id"])
            end.record(sim.drain_events())
            self.assertIs(sim.torpedoes, runner.legacy.torpedoes_server)
            self.assertIsNone(end.evaluate(sim.torpedoes.values()))
            if hit:
                torpedo.update(x=99.9, y=target["position"]["y"], z=0,
                               dirX=1, dirZ=0, activation=0, damage=1000)
            else:
                torpedo.update(maxRange=0.001, activation=100000)
            sim.update_server_torpedoes(0.05, runner.world)
            pending = sim.drain_events()
            self.assertTrue(any(isinstance(e, events.TorpedoDead) for e in pending))
            self.assertEqual({}, sim.torpedoes)
            end.record(pending)
            result = end.evaluate(sim.torpedoes.values())
            self.assertEqual(hit, result["draw"])
            self.assertEqual([] if hit else ["blue"], result["winningTeamIds"])

    def test_rl_preflight_strict_and_controller_not_reset(self) -> None:
        entry = dict(self.entry, ai="rl_missing_run")
        with self.assertRaises(FileNotFoundError):
            self.prepare({"boats": [entry]})
        entry["ai"] = "rl_../../escape"
        with self.assertRaises(ValueError):
            self.prepare({"boats": [entry]})
        model = SimpleNamespace(observation_space=SimpleNamespace(shape=(32,)),
                                action_space=SimpleNamespace(nvec=(5, 3, 4, 2, 3)))
        with patch("rl.rl_runtime.load_model", return_value=model):
            with self.assertRaises(ValueError):
                self.prepare({"boats": [dict(self.entry, ai="rl_incompatible")]})
        from rl.rl_control import control_spec
        _, dim, nvec = control_spec("destroyer")
        model.observation_space.shape = (dim,)
        model.action_space.nvec = nvec
        with patch("rl.rl_runtime.load_model", return_value=model) as loader:
            prepared = self.prepare({"boats": [dict(self.entry, ai="rl_valid")]})
            controller = prepared[0]["prepared_ai"]["rl_controller"]
            self.assertIsInstance(controller, RuntimeController)
            ns = self.namespace()
            ns["spawn_bot"](**prepared[0])
            bot = next(iter(ns["bots"].values()))
            self.assertIs(controller, bot["rl_controller"])
            self.assertEqual(-0.2, bot["control_target_depth_y"])
            self.assertEqual(1, loader.call_count)

    def test_startup_hook_without_client_and_failure_before_spawn(self) -> None:
        ns = self.namespace()
        ns.update(__file__=str(Path("server.py").resolve()), __name__="test_autogame",
                  sys=SimpleNamespace(modules={"test_autogame": self.runner.legacy}),
                  current_map_name="world", MAX_BOTS=32)
        with patch.object(Path, "open", return_value=io.StringIO(json.dumps({"boats": [self.entry]}))):
            ns["initialize_autogame"]()
        self.assertIsInstance(ns["sim"], simulation.Sim)
        self.assertEqual(1, len(ns["sim"].bots))
        ns["spawn_bot"] = Mock()
        with patch.object(Path, "open", return_value=io.StringIO(json.dumps(
                {"boats": [self.entry, dict(self.entry, ai="rl_missing_run")]}))):
            with self.assertRaises(FileNotFoundError):
                ns["initialize_autogame"]()
        ns["spawn_bot"].assert_not_called()
        tree = ast.parse(Path("server.py").read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        starts = [n.lineno for n in calls if isinstance(n.func, ast.Name)
                  and n.func.id == "initialize_autogame"]
        self.assertEqual(1, len(starts))
        main = tree.body[-1]
        for call in (n for n in ast.walk(main) if isinstance(n, ast.Call)):
            if isinstance(call.func, ast.Attribute) and call.func.attr in ("start_background_task", "run"):
                self.assertLess(starts[0], call.lineno)

    def startup(self, argv: list) -> dict:
        """Execute le parseur et la fin du demarrage reels, sans reseau ni taches."""
        main = ast.parse(Path("server.py").read_text()).body[-1]
        parser_end = next(i for i, node in enumerate(main.body)
                          if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "args"
                                  for t in node.targets))
        gate_start = next(i for i, node in enumerate(main.body)
                          if isinstance(node, ast.If)
                          and isinstance(node.test, ast.Attribute)
                          and node.test.attr == "autogame")
        ns = self.namespace()
        ns.update(__file__=str(Path("server.py").resolve()), __name__="test_autogame",
                  sys=SimpleNamespace(modules={"test_autogame": self.runner.legacy}),
                  current_map_name="world", DEFAULT_MAP="world", MAX_BOTS=32,
                  config={"server": {"port": 7000}}, port=7000, MAX_HUMAN_PLAYERS=10,
                  app=Mock(), print=Mock(), sonar_beacon_ticker=Mock(),
                  passive_sonar_beacon_ticker=Mock(), bot_ticker=Mock())
        with patch("sys.argv", ["server.py", *argv]):
            exec(compile(ast.Module(body=main.body[:parser_end + 1], type_ignores=[]),
                         "server.py", "exec"), ns)
        ns["startup_tail"] = compile(ast.Module(body=main.body[gate_start:], type_ignores=[]),
                                     "server.py", "exec")
        return ns

    def test_cli_autogame_opt_in(self) -> None:
        self.assertIs(self.startup([])["args"].autogame, False)
        args = self.startup(["--trace", "--autogame", "--map", "world"])["args"]
        self.assertIs(args.autogame, True)
        self.assertIs(args.trace, True)
        self.assertEqual("world", args.map)

    def test_disabled_skips_file_validation_preload_spawn_and_trace(self) -> None:
        for argv in ([], ["--trace"]):
            for error in (FileNotFoundError("autogame.json"), ValueError("invalid JSON")):
                with self.subTest(argv=argv, error=error):
                    ns = self.startup(argv)
                    ns["game_trace"] = Mock(enabled=ns["args"].trace)
                    ns["spawn_bot"] = Mock()
                    with patch.object(Path, "open", side_effect=error) as opened, \
                            patch("autogame.prepare_autogame", side_effect=error) as prepare:
                        exec(ns["startup_tail"], ns)
                    opened.assert_not_called()
                    prepare.assert_not_called()
                    ns["spawn_bot"].assert_not_called()
                    ns["game_trace"]._write.assert_not_called()
                    self.assertFalse(ns["bots"])
                    ns["socketio"].run.assert_called_once()

    def test_enabled_prepares_spawns_and_traces_once_before_tasks(self) -> None:
        ns = self.startup(["--trace", "--autogame"])
        ns["game_trace"] = Mock(enabled=True)
        calls = Mock()
        calls.attach_mock(ns["socketio"], "socketio")
        with patch("autogame.prepare_autogame", wraps=autogame.prepare_autogame) as prepare, \
                patch.dict(ns, spawn_bot=Mock(wraps=ns["spawn_bot"])), \
                patch.object(Path, "open", return_value=io.StringIO(
                    json.dumps({"boats": [self.entry]}))) as opened:
            calls.attach_mock(prepare, "prepare")
            calls.attach_mock(ns["spawn_bot"], "spawn")
            exec(ns["startup_tail"], ns)
            prepare.assert_called_once()
            opened.assert_called_once()
            ns["spawn_bot"].assert_called_once()
        self.assertEqual(1, len(ns["sim"].bots))
        self.assertEqual(["autogame", "autogame_ready"],
                         [c.args[0] for c in ns["game_trace"]._write.call_args_list])
        names = [call[0] for call in calls.mock_calls]
        self.assertLess(names.index("prepare"), names.index("spawn"))
        self.assertLess(names.index("spawn"), names.index("socketio.start_background_task"))
        self.assertLess(names.index("socketio.start_background_task"), names.index("socketio.run"))

    def test_enabled_invalid_file_stops_before_tasks_and_trace(self) -> None:
        for error in (FileNotFoundError("autogame.json"), ValueError("invalid JSON")):
            with self.subTest(error=error):
                ns = self.startup(["--trace", "--autogame"])
                ns["game_trace"] = Mock(enabled=True)
                ns["spawn_bot"] = Mock()
                with patch.object(Path, "open", side_effect=error) as opened, \
                        self.assertLogs(level="ERROR"), self.assertRaises(SystemExit):
                    exec(ns["startup_tail"], ns)
                opened.assert_called_once()
                ns["spawn_bot"].assert_not_called()
                ns["game_trace"]._write.assert_not_called()
                ns["socketio"].start_background_task.assert_not_called()
                ns["socketio"].run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
