"""Placement reel Sim et handler serveur extrait sans demarrer Flask."""

import ast
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import events
from game_trace import GameTrace
from simulation import Sim


class TeleBotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tree = ast.parse(Path(__file__).with_name("server.py").read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {"handle_cheat_move_bot", "dispatch_events"}]
        for node in nodes:
            node.decorator_list = []
        cls.code = compile(ast.Module(body=nodes, type_ignores=[]), "server.py", "exec")

    def setUp(self) -> None:
        self.sim = Sim({"ground": {"width": 1000, "depth": 800}, "islands": [
            {"points": [{"x": x, "z": z} for x, z in ((20, 20), (30, 20), (30, 30), (20, 30))]}]})
        self.bot = {"id": "public-bot", "boatType": "submarine", "team_id": "ally",
                    "position": {"x": -50, "y": -12, "z": -60}, "rotation": 1.2,
                    "speed": 3, "rudder": 0.4, "integrity": 80, "depth_target_y": -15,
                    "waypoint": {"x": 9, "z": 9}, "last_detected_ids": ["enemy"],
                    "bb": {"last_enemy_pos": {"x": 7, "z": 8}, "nav_node": 5,
                           "nav_seen_nodes": [1, 2], "_evade": {"wp": {"x": 1, "z": 1}},
                           "_stuck_ticks": 90, "_ref_wp_dist": 2, "_yvan_until": 100}}
        self.sim.bots["secret-bot-sid"] = self.bot
        self.sim.players.update({"secret-human-sid": {"id": "public-actor", "team_id": "ally"},
                                 "secret-bot-sid": dict(copy.deepcopy(self.bot), is_bot=True)})
        self.sent = Mock()
        self.ns = {"sim": self.sim, "players": self.sim.players, "emit": self.sent, "autogame_end": None,
                   "request": SimpleNamespace(sid="secret-human-sid")}
        exec(self.code, self.ns)

    def send(self, data: object) -> dict:
        self.ns["handle_cheat_move_bot"](data)
        self.assertEqual(self.sent.call_args.args[0], "cheat_move_bot_result")
        return self.sent.call_args.args[1]

    def test_cheat_name_in_errors(self) -> None:
        self.assertEqual(self.send(None)["message"], "Requete telebot invalide")
        self.ns["request"].sid = "unknown"
        self.assertEqual(self.send(None)["message"], "Rejoignez le jeu avant telebot")

    def test_allied_and_enemy_teleport_sync_and_preserve_memory(self) -> None:
        for team in ("ally", "enemy"):
            with self.subTest(team=team):
                self.setUp()
                self.bot["team_id"] = team
                actor = copy.deepcopy(self.sim.players["secret-human-sid"])
                old = dict(self.bot["position"])
                self.assertTrue(self.send({"id": "public-bot", "x": 100, "z": 150, "y": 0})["ok"])
                self.assertEqual(self.bot["position"], {"x": 100, "y": -12, "z": 150})
                self.assertEqual(self.bot["position"], self.sim.players["secret-bot-sid"]["position"])
                self.assertEqual(actor, self.sim.players["secret-human-sid"])
                self.assertEqual((self.bot["speed"], self.bot["rudder"], self.bot["waypoint"]), (0, 0, None))
                self.assertEqual((self.bot["rotation"], self.bot["integrity"], self.bot["depth_target_y"]), (1.2, 80, -15))
                self.assertEqual(self.bot["bb"], {"last_enemy_pos": {"x": 7, "z": 8}, "nav_seen_nodes": [1, 2]})
                self.assertEqual(self.bot["last_detected_ids"], ["enemy"])
                emitted = self.sim.drain_events()
                self.assertEqual([type(e) for e in emitted], [events.BotTeleported, events.PlayerMoved])
                self.assertEqual(emitted[0].old_position, old)
                self.assertEqual(emitted[0].actor_id, "public-actor")

    def test_rejections_leave_state_and_events_untouched(self) -> None:
        valid = {"id": "public-bot", "x": 100, "z": 150}
        invalid = [None, [], "bad", {}, valid | {"id": "public-actor"},
                   valid | {"id": "secret-bot-sid"}, valid | {"id": "stale"}, valid | {"id": []}]
        invalid += [valid | {axis: v} for axis in ("x", "z")
                    for v in (None, "100", True, [], {}, float("nan"), float("inf"), -float("inf"), 10**400, 900, -900)]
        invalid += [valid | {"x": x, "z": z} for x, z in ((25, 25), (20, 25), (30, 30))]
        for data in invalid:
            with self.subTest(data=str(data)[:100]):
                before = copy.deepcopy((self.sim.bots, self.sim.players))
                self.assertFalse(self.send(data)["ok"])
                self.assertEqual(before, (self.sim.bots, self.sim.players))
                self.assertEqual(self.sim.drain_events(), [])

    def test_unjoined_dead_nonbot_and_missing_player(self) -> None:
        for case in ("unjoined", "bot_actor", "sunk", "dead", "player_dead", "human", "missing"):
            with self.subTest(case=case):
                self.setUp()
                if case == "unjoined":
                    self.ns["request"].sid = "unknown"
                elif case == "bot_actor":
                    self.ns["request"].sid = "secret-bot-sid"
                elif case == "sunk":
                    self.bot["sunk"] = True
                elif case == "dead":
                    self.bot["integrity"] = 0
                elif case == "player_dead":
                    self.sim.players["secret-bot-sid"]["integrity"] = 0
                elif case == "human":
                    self.sim.players["secret-bot-sid"]["is_bot"] = False
                else:
                    del self.sim.players["secret-bot-sid"]
                before = copy.deepcopy((self.sim.bots, self.sim.players))
                self.assertFalse(self.send({"id": "public-bot", "x": 100, "z": 150})["ok"])
                self.assertEqual(before, (self.sim.bots, self.sim.players))
                self.assertEqual([], self.sim.drain_events())

    def test_trace_dispatch_has_public_ids_old_and_new_position(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            trace = GameTrace(True, path)
            self.addCleanup(trace.close)
            self.ns.update(game_trace=trace, ev_mod=events,
                           EVENT_DISPATCH={events.PlayerMoved: Mock(), events.BotTeleported: lambda e: None},
                           logging=Mock())
            self.send({"id": "public-bot", "x": 100, "z": 150})
            self.ns["dispatch_events"](self.sim.drain_events())
            trace.close()
            raw = path.read_text()
            self.assertNotIn("secret-", raw)
            row = json.loads(raw.splitlines()[-1])
            self.assertEqual(row["data"], {"name": "BotTeleported", "fields": {
                "actor_id": "public-actor", "player_id": "public-bot",
                "old_position": {"x": -50, "y": -12, "z": -60},
                "position": {"x": 100, "y": -12, "z": 150}}})
            self.ns["EVENT_DISPATCH"][events.PlayerMoved].assert_called_once()
            self.ns["logging"].warning.assert_not_called()

    def test_real_headless_bots_resume_after_teleport(self) -> None:
        from rl.headless import HeadlessRunner

        for boat_type, ai, external in (("submarine", "autosub", False),
                                        ("destroyer", "autodest", False),
                                        ("submarine", None, True)):
            with self.subTest(boat=boat_type, external=external):
                runner = HeadlessRunner(seed=12)
                sid = runner.spawn_bot(boat_type, ai=ai, external_control=external)
                bot = runner.sim.bots[sid]
                runner.step(0.05)
                x, z = runner.random_ocean_position()
                y = bot["position"]["y"]
                self.assertIsNone(runner.sim.teleport_bot("actor", bot["id"], x, z))
                self.assertEqual(bot["position"], {"x": x, "y": y, "z": z})
                self.assertEqual(bot["position"], runner.sim.players[sid]["position"])
                runner.step(0.05)
                # Le BT synchronise via son action sync_player, pas a chaque mouvement.
                self.assertLess(abs(runner.sim.players[sid]["position"]["x"] - x), 1)
                self.assertLess(abs(bot["position"]["x"] - x), 1)
                self.assertLess(abs(bot["position"]["z"] - z), 1)


if __name__ == "__main__":
    unittest.main()
