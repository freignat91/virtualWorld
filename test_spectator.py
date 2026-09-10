"""Transport SocketIO en memoire et vrais handlers AST, sans ecoute serveur."""

import ast
import copy
from functools import wraps
import logging
from pathlib import Path
import time
import unittest

from flask import Flask, request
from flask_socketio import SocketIO, emit


class SpectatorTest(unittest.TestCase):
    def setUp(self) -> None:
        tree = ast.parse(Path(__file__).with_name("server.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GameSocketIO")
        self.ns = {"SocketIO": SocketIO, "wraps": wraps, "request": request,
                   "emit": emit, "spectator_sids": set(), "logging": logging, "time": time,
                   "autogame_preparation": None}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "server.py", "exec"), self.ns)
        app = Flask(__name__)
        self.app = app
        app.config["SECRET_KEY"] = "test-only"
        self.io = self.ns["GameSocketIO"](app, async_mode="threading")
        self.ns.update(socketio=self.io, _socket_emit=self.io.emit, MAX_HUMAN_PLAYERS=0,
                       players={"bot-sid": {"id": "bot", "is_bot": True, "team_id": "red"}},
                       bots={"bot": {"state": "unchanged"}}, torpedo_ammo={}, grenade_ammo={},
                       player_boats_sids={}, human_owner_sid={}, autopiloted_sids=set(),
                       torpedoes_server={}, drones_server={}, grenades_server={}, server_lures={},
                       sonar_beacons={}, passive_sonar_beacons={}, mines_server={},
                       load_world=lambda: {"ground": {"width": 100, "depth": 100}, "islands": []},
                       day_cycle_snapshot=lambda: {"state": "off"}, _mine_payload=lambda m: dict(m))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and (
            n.name in ("_list_active_teams", "_emit_one") or any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and isinstance(d.func.value, ast.Name) and d.func.value.id == "socketio"
                for d in n.decorator_list))]
        self.handlers = {n.decorator_list[0].args[0].value: n for n in nodes if n.decorator_list}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "server.py", "exec"), self.ns)
        self.client = self.io.test_client(app)
        self.addCleanup(lambda: self.client.disconnect() if self.client.is_connected() else None)

    def state(self) -> dict:
        return copy.deepcopy({k: v for k, v in self.ns.items() if isinstance(v, (dict, set))
                              and k not in ("__builtins__", "spectator_sids")})

    def test_join_has_no_unit_slot_ammo_team_or_sim_effect(self) -> None:
        before = self.state()
        self.assertEqual(self.client.emit("spectate", callback=True), {"spectator": True})
        received = self.client.get_received()
        self.assertEqual([p["name"] for p in received], ["init"])
        payload = received[0]["args"][0]
        self.assertTrue(payload["spectator"])
        self.assertNotIn("boat", payload)
        self.assertNotIn("playerId", payload)
        self.assertEqual(payload["players"], self.ns["players"])
        self.assertEqual(before, self.state())
        self.assertEqual(len(self.ns["spectator_sids"]), 1)
        self.client.emit("spectate")
        self.assertEqual(self.client.get_received(), [])
        self.client.disconnect()
        self.assertFalse(self.ns["spectator_sids"])
        self.assertEqual(before, self.state())

    def test_preparation_allows_observer_init_but_no_gameplay(self) -> None:
        self.ns["autogame_preparation"] = {"startDelaySeconds": 30}
        self.ns["players"]["bot-sid"]["position"] = dict(x=-100, y=-0.2, z=600)
        before = self.state()
        allowed = {"connect", "disconnect", "spectate", "list_teams", "ws_ping", "ws_rtt_report"}
        for event, node in self.handlers.items():
            if event in allowed:
                continue
            args = [{}] if node.args.args else []
            with self.subTest(event=event):
                self.assertEqual(self.client.emit(event, *args, callback=True),
                                 {"error": "autogame_preparing"})
        self.assertEqual(self.client.emit("spectate", callback=True), {"spectator": True})
        payload = self.client.get_received()[0]["args"][0]
        self.assertEqual(before, self.state())
        self.assertEqual(payload["players"], self.ns["players"])

    def test_every_registered_mutating_event_denied_before_handler(self) -> None:
        self.client.emit("spectate")
        self.client.get_received()
        before = self.state()
        allowed = {"connect", "disconnect", "spectate", "list_teams", "ws_ping"}
        for event, node in self.handlers.items():
            if event in allowed:
                continue
            with self.subTest(event=event):
                args = [{"bsid": "bot-sid", "id": "bot", "multiplier": 8}] if node.args.args else []
                self.assertEqual(self.client.emit(event, *args, callback=True),
                                 {"error": "spectator_read_only"})
                self.assertEqual(self.client.get_received(), [])
                self.assertEqual(before, self.state())
        self.client.emit("ws_ping", {"ts": 10})
        self.assertEqual(self.client.get_received()[0]["name"], "ws_pong")
        self.client.emit("list_teams")
        self.assertEqual(self.client.get_received()[0]["args"][0]["teams"][0]["members"], 1)
        self.assertEqual(self.client.emit("disconnect", callback=True), {"error": "spectator_read_only"})
        self.assertTrue(self.ns["spectator_sids"])
        self.assertEqual(self.client.emit("select_boat", {}, callback=True), {"error": "spectator_read_only"})

    def test_initial_projectiles_are_current_unicast_state(self) -> None:
        self.ns["torpedoes_server"][1] = dict(ownerPlayerId="bot", tid=1, kind="acoustic",
                                            x=3, y=-5, z=7, dirX=1, dirZ=0)
        self.ns["drones_server"][1] = dict(ownerPlayerId="bot", did=1, kind="automatic",
                                          x=5, y=8, z=7, dirX=1, dirZ=0, range_m=3000)
        self.ns["grenades_server"][1] = dict(ownerPlayerId="bot", gid=1, phase="water",
                                            x=3, y=-4, z=5, vx=0, vy=0, vz=0,
                                            impactX=3, impactZ=5, targetDepthU=10, sinkSpeedU=0.4)
        self.ns["server_lures"][1] = dict(ownerId="bot", lid=1, x=1, y=-2, z=3,
                                         expiresAt=time.time() + 10, integrity=6, maxIntegrity=10)
        self.ns["sonar_beacons"][1] = dict(bid=1, ownerSid="private", revealedTeams={"red"})
        self.ns["passive_sonar_beacons"][1] = dict(bid=2, x=1, y=0, z=2)
        self.ns["mines_server"][1] = dict(ownerId="bot", mid=1, kind="surface", x=1, y=0, z=2)
        before = self.state()
        other = self.io.test_client(self.app)
        traced = []
        raw_emit = self.io.emit

        def trace_emit(name, *args, **kwargs):
            traced.append(name)
            return raw_emit(name, *args, **kwargs)

        self.io.emit = trace_emit
        try:
            self.client.emit("spectate")
            messages = {p["name"]: p["args"][0] for p in self.client.get_received()}
            self.assertEqual(other.get_received(), [])
            self.assertEqual(messages["init"]["grenades"][0]["phase"], "water")
            self.assertEqual(messages["init"]["grenades"][0]["y"], -4)
            self.assertEqual(messages["init"]["sonarBeacons"], [{"bid": 1}])
            self.assertEqual(len(messages["init"]["mines"]), 1)
            self.assertEqual(len(messages["init"]["passiveSonarBeacons"]), 1)
            self.assertEqual(messages["torpedo_state"]["x"], 3)
            self.assertEqual(messages["drone_state"]["y"], 8)
            self.assertEqual(messages["drone_state"]["rangeMeters"], 3000)
            self.assertEqual(messages["lure_dropped"]["integrity"], 6)
            self.assertTrue(0 < messages["lure_dropped"]["durationMs"] <= 10000)
            self.assertEqual(before, self.state())
            self.assertEqual(traced, ["init"])
        finally:
            other.disconnect()

    def test_full_human_lobby_and_no_mode_switch_for_player(self) -> None:
        self.client.emit("select_boat", {})
        self.assertEqual(self.client.get_received()[0]["name"], "server_full")
        self.client.emit("spectate")
        self.assertEqual(self.client.get_received()[0]["name"], "init")
        sid = next(iter(self.ns["spectator_sids"]))
        self.ns["spectator_sids"].clear()
        self.ns["players"][sid] = {"id": "human"}
        self.assertEqual(self.client.emit("spectate", callback=True), {"error": "already_playing"})
        self.assertFalse(self.ns["spectator_sids"])
        del self.ns["players"][sid]


if __name__ == "__main__":
    unittest.main()
