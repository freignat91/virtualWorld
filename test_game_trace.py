"""Regressions de trace hors serveur, sans socket ni lancement de partie."""

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import events
from game_trace import GameTrace
from simulation import Sim


class GameTraceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "logs" / "game_trace.jsonl"
        self.sim = Sim({}, clock=lambda: 123.0)
        self.server = SimpleNamespace(passive_sonar_beacons={}, sim_tick_multiplier=1,
                                      bots_passive=False, torpedo_ammo={"secret-sid": {"acoustic": 4}})

    def trace(self, **kwargs) -> GameTrace:
        trace = GameTrace(path=self.path, **kwargs)
        self.addCleanup(trace.close)
        return trace

    def rows(self) -> list:
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def test_off_has_no_files_or_calls(self) -> None:
        trace = self.trace()
        trace.metadata(Mock(), "world", {})
        trace.observe(Mock(), Mock(), 0.05)
        trace.event(events.PlayerLeft("p"), {})
        trace.network("cannon_hit", {"damage": 3})
        self.assertFalse(self.path.parent.exists())

    def test_all_objects_lifecycle_controls_ammo_and_privacy(self) -> None:
        trace = self.trace(enabled=True)
        self.sim.players["secret-sid"] = dict(id="public", position=dict(x=1, y=-3, z=2),
                                              sid="secret-sid", name="private-name", ip="private-ip")
        self.sim.bots["secret-sid"] = dict(self.sim.players["secret-sid"],
            control_target_speed_ratio=0.5, depth_target_y=-4, speed=2,
            bb={"chat": "secret-chat"})
        for name in ("torpedoes", "drones", "grenades", "mines", "lures"):
            getattr(self.sim, name)[("public", 1)] = dict(ownerPlayerId="public", tid=1,
                x=1, y=-3, z=2, ownerSid="secret-sid", initialTarget=(1, -4, 3))
        self.sim.beacons[1] = dict(bid=1, x=2, ownerSid="secret-sid")
        self.server.passive_sonar_beacons[1] = dict(bid=1, x=3)
        with patch("game_trace.time.monotonic", return_value=10):
            trace.observe(self.sim, self.server, 0.05)
            trace.observe(self.sim, self.server, 0.05)
        snapshots = [r for r in self.rows() if r["type"] == "snapshot"]
        self.assertEqual(len(snapshots), 8)
        boat = next(r["data"]["fields"] for r in snapshots if r["data"]["object"][0] == "boat")
        self.assertEqual(boat["ammo"]["torpedo"]["acoustic"], 4)
        self.assertEqual(boat["control_target_speed_ratio"], 0.5)
        self.assertEqual(boat["position"]["y"], -3)
        self.assertTrue(trace.enabled)
        self.sim.reset()
        self.server.passive_sonar_beacons.clear()
        with patch("game_trace.time.monotonic", return_value=11):
            trace.observe(self.sim, self.server)
        self.assertEqual(len([r for r in self.rows() if r["type"] == "despawn"]), 8)
        for secret in ("secret-sid", "private-name", "private-ip", "secret-chat"):
            self.assertNotIn(secret, self.path.read_text())

    def test_events_short_projectiles_sanitization_and_native_transitions(self) -> None:
        trace = self.trace(enabled=True)
        state = events.TorpedoState("p", 1, "acoustic", 1, -2, 3, 1, 0, None, None, None)
        trace.event(state, {})
        trace.event(state, {})
        trace.event(events.TorpedoDead("p", 1), {})
        trace.event(events.GrenadeLaunched("p", 2, 1, 2, 3, 1, 2, 3, -10, 4), {})
        trace.event(events.GrenadeExploded("p", 2, 1, -10, 3, 50, 12), {})
        trace.event(events.IntegrityChanged(None, 77, target_sid="secret-sid"),
                    {"secret-sid": {"id": "p"}})
        trace.event(events.PlayerJoined({"id": "p", "position": {"x": 1, "token": "SECRET"},
                                        "chat": "SECRET"}, target_sid="SECRET"), {})
        trace.event(events.AdminError("SECRET"), {})
        trace.network("chat", {"id": "SECRET"})
        trace.network("cannon_hit", {"shooterId": "p", "targetId": "q", "damage": 4,
                                     "sid": "SECRET", "credentials": "SECRET"})
        self.sim.torpedoes[("p", 1)] = dict(ownerPlayerId="p", tid=1, lockedKey="radar:q")
        self.sim._sonar_reveals[("SECRET", "q")] = dict(bot={"id": "p"}, target={"id": "q"})
        with patch("game_trace.time.monotonic", return_value=10):
            trace.observe(self.sim, self.server, 0.05)
            self.sim.torpedoes[("p", 1)]["lockedKey"] = None
            self.sim._sonar_reveals.clear()
            trace.observe(self.sim, self.server, 0.05)
        rows = self.rows()
        self.assertEqual(sum(r["data"].get("name") == "TorpedoState" for r in rows), 1)
        self.assertEqual(sum(r["type"] == "lock" for r in rows), 2)
        self.assertEqual(sum(r["type"] == "sonar_contact" for r in rows), 2)
        self.assertNotIn("SECRET", self.path.read_text())
        integrity = next(r for r in rows if r["data"].get("name") == "IntegrityChanged")
        self.assertEqual(integrity["data"]["fields"], {"value": 77, "max_integrity": 100.0, "player_id": "p"})
        self.assertEqual([r["seq"] for r in rows], list(range(1, len(rows) + 1)))

    def test_integrity_maxima_and_nonlethal_lure_event(self) -> None:
        trace = self.trace(enabled=True)
        self.sim.players["secret-sid"] = dict(id="p", integrity=120, maxIntegrity=200)
        self.sim.lures[("p", 1)] = dict(ownerId="p", lid=1, x=0, y=-2, z=0,
                                               expiresAt=200, integrity=10, maxIntegrity=10)
        self.sim.lure_splash_damage(0, -2, 0, 5, 20)
        for event in self.sim.drain_events():
            trace.event(event, self.sim.players)
        trace.observe(self.sim, self.server, 0.05)
        rows = self.rows()
        changed = next(r["data"]["fields"] for r in rows
                       if r["data"].get("name") == "LureIntegrityChanged")
        self.assertEqual(dict(owner_id="p", lid=1, integrity=5, max_integrity=10), changed)
        snapshots = [r["data"] for r in rows if r["type"] == "snapshot"]
        boat = next(r["fields"] for r in snapshots if r["object"][0] == "boat")
        lure = next(r["fields"] for r in snapshots if r["object"][0] == "lure")
        self.assertEqual((120, 200), (boat["integrity"], boat["maxIntegrity"]))
        self.assertEqual((5, 10), (lure["integrity"], lure["maxIntegrity"]))
        self.assertNotIn("secret-sid", self.path.read_text())

    def test_rotation_and_cross_session_ids(self) -> None:
        first = self.trace(enabled=True, max_bytes=1024, backups=2)
        for _ in range(40):
            first.network("cannon_hit", {"damage": 4})
        first.close()
        files = list(self.path.parent.iterdir())
        self.assertEqual(len(files), 3)
        for file in files:
            self.assertLessEqual(file.stat().st_size, 1024)
            for line in file.read_text().splitlines():
                json.loads(line)
        second = self.trace(enabled=True, max_bytes=1024, backups=2)
        second.network("player_joined", {"id": "reused-id"})
        self.assertNotEqual(first.session, second.session)
        self.assertEqual(self.rows()[-1]["session"], second.session)
        self.assertEqual(self.rows()[-1]["seq"], 2)
        self.assertEqual(len(second.logger.handlers), 1)
        self.assertFalse(second.logger.propagate)

    def test_restart_after_partial_line_and_snapshot_failure(self) -> None:
        first = self.trace(enabled=True)
        first.close()
        # Simule une interruption au milieu d'une ligne, sans toucher au serveur.
        with self.path.open("a") as stream:
            stream.write('{"incomplete":')
        second = self.trace(enabled=True)
        self.assertEqual(self.rows()[0]["type"], "session")
        self.assertTrue(Path(str(self.path) + ".1").read_text().endswith('{"incomplete":'))
        self.sim.players["SECRET"] = {"id": "p", "position": {"x": object()}}
        with self.assertLogs("game_trace", level="WARNING"):
            second.observe(self.sim, self.server, 0.05)
        self.assertFalse(second.enabled)
        self.assertNotIn("SECRET", self.path.read_text())

    def test_fail_safe_serialization_disk_and_open(self) -> None:
        trace = self.trace(enabled=True)
        with self.assertLogs("game_trace", level="WARNING"):
            trace.network("cannon_hit", {"damage": float("nan")})
        self.assertFalse(trace.enabled)
        self.assertIsNone(trace.handler)
        trace.network("cannon_hit", {"damage": 4})
        trace = self.trace(enabled=True)
        with patch.object(trace.handler, "shouldRollover", side_effect=OSError("SECRET")):
            with self.assertLogs("game_trace", level="WARNING") as logs:
                trace.network("cannon_hit", {"damage": 4})
        self.assertFalse(trace.enabled)
        self.assertNotIn("SECRET", str(logs.output))
        with patch("game_trace.StrictRotatingHandler", side_effect=OSError("SECRET")):
            with self.assertLogs("game_trace", level="WARNING"):
                failed = self.trace(enabled=True)
        self.assertFalse(failed.enabled)

    def test_metadata_world_epoch_and_oversized_record(self) -> None:
        trace = self.trace(enabled=True)
        root = Path(__file__).parent
        with patch("game_trace.subprocess.run", return_value=SimpleNamespace(stdout="abc\n")) as git:
            trace.metadata(root, "world", {"size": 100})
            self.assertEqual(git.call_count, 2)
            trace.world("other", {"size": 200})
            trace.observe(self.sim, self.server, 0.05)
            self.assertEqual(git.call_count, 2)
        meta = next(r["data"] for r in self.rows() if r["type"] == "metadata")
        self.assertIn("boats/submarine.json", meta["sha256"])
        self.assertTrue(meta["git_dirty"])
        self.assertEqual(trace.epoch, 2)
        with self.assertLogs("game_trace", level="WARNING"):
            trace.network("player_joined", {"id": "x" * trace.max_bytes})
        self.assertFalse(trace.enabled)

    def test_server_hooks_preserve_transport_and_no_duplicate_dispatch(self) -> None:
        tree = ast.parse(Path("server.py").read_text())
        names = {"_traced_socket_emit", "_emit_one", "dispatch_events"}
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        trace = self.trace(enabled=True)
        transport = Mock(return_value="sent")
        namespace = dict(game_trace=trace, _socket_emit=transport, players={}, autogame_end=None,
                         EVENT_DISPATCH={events.PlayerLeft: lambda e: namespace["_emit_one"](
                             "player_left", {"id": e.player_id})})
        exec(compile(ast.Module(body=functions, type_ignores=[]), "server.py", "exec"), namespace)
        result = namespace["_traced_socket_emit"]("cannon_hit", {"damage": 4}, to="SECRET")
        self.assertEqual(result, "sent")
        transport.assert_called_once_with("cannon_hit", {"damage": 4}, to="SECRET")
        namespace["dispatch_events"]([events.PlayerLeft("p")])
        self.assertEqual(len(self.rows()), 3)
        self.assertNotIn("SECRET", self.path.read_text())

    def test_flask_emit_delegates_once_without_live_server(self) -> None:
        from flask import Flask, request
        from flask_socketio import emit

        app = Flask(__name__)
        trace = self.trace(enabled=True)
        transport = Mock()

        def send(name, payload, **kwargs):
            trace.network(name, payload, {"SECRET": {"id": "public"}}, kwargs.get("to"))
            transport(name, payload, **kwargs)

        app.extensions["socketio"] = SimpleNamespace(emit=send)
        with app.test_request_context("/"):
            request.sid = "SECRET"
            request.namespace = "/"
            emit("grenade_count", {"count": 3})
        transport.assert_called_once()
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["data"]["fields"], {"count": 3, "player_id": "public"})
        self.assertNotIn("SECRET", self.path.read_text())


if __name__ == "__main__":
    unittest.main()
