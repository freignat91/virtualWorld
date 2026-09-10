"""Integrite absolue partagee: coques, leurres, reseau et observations RL."""

import ast
import json
import logging
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

import events
import simulation
from rl.headless import HeadlessRunner, load_boat
from rl.rl_control import build_observation
from rl.rl_env import SubmarineDuelEnv


def server_functions(names: set, namespace: dict) -> dict:
    """Execute les vraies fonctions sans importer/demarrer le serveur."""
    tree = ast.parse(Path("server.py").read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "server.py", "exec"), namespace)
    return namespace


class IntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = HeadlessRunner(seed=73)
        self.sim = self.runner.sim
        self.runner.world.update(islands=[], thermoclines=[])

    def human(self, kind: str = "destroyer", sid: str = "human") -> dict:
        player = dict(id=sid, boatType=kind, boat=load_boat(kind),
                      position=dict(x=0.0, y=-2.0, z=0.0))
        self.sim.players[sid] = player
        self.sim.init_player_integrity(sid)
        return player

    def lure(self, lid: int, x: float = 0, y: float = -2) -> dict:
        lure = dict(ownerId="owner", lid=lid, x=x, y=y, z=0, noise=800,
                    expiresAt=self.sim.now() + 120, integrity=10.0, maxIntegrity=10.0)
        self.sim.lures[("owner", lid)] = lure
        return lure

    def test_validation_and_legacy_specs(self) -> None:
        self.assertEqual(100, simulation.integrity_capacity({}))
        self.assertEqual(10, simulation.integrity_capacity({}, 10))
        for bad in (0, -1, math.nan, math.inf, -math.inf, True, "200", None):
            for lure in (False, True):
                with self.subTest(bad=bad, lure=lure):
                    boat = {"acousticLures": {"integrity": bad}} if lure else {"integrity": bad}
                    with self.assertRaises(ValueError):
                        simulation.init_hull_integrity({"boat": boat})
                    with patch("rl.headless.load_boat", return_value=boat):
                        with self.assertRaises(ValueError):
                            self.runner.spawn_bot("destroyer", external_control=True, position=(0, 0))

    def test_human_and_headless_damage_observations_and_immutable_capacity(self) -> None:
        for kind, maximum, left, index in (("destroyer", 200, 120, 2), ("submarine", 100, 20, 3)):
            for external in (True, False):
                with self.subTest(kind=kind, external=external):
                    sid = self.runner.spawn_bot(kind, ai="default", external_control=external, position=(100, 80))
                    bot = self.sim.bots[sid]
                    self.assertEqual((maximum, maximum), (bot["integrity"], bot["maxIntegrity"]))
                    self.assertEqual(1, build_observation(bot, self.sim, self.runner.world)[index])
                    self.sim.bot_apply_damage(sid, bot, 80, None)
                    self.assertEqual(left, bot["integrity"])
                    self.assertEqual(left, self.sim.players[sid]["integrity"])
                    self.assertAlmostEqual(left / maximum, build_observation(bot, self.sim, self.runner.world)[index])
            player = self.human(kind)
            self.sim.apply_player_damage("human", player, 80, None)
            self.assertEqual(left, player["integrity"])
            player["boat"]["integrity"] = 999
            self.assertEqual(maximum, player["maxIntegrity"])
            event = [e for e in self.sim.drain_events() if isinstance(e, events.IntegrityChanged)][-1]
            self.assertEqual((left, maximum), (event.value, event.max_integrity))

    def test_regen_and_secondary_resupply(self) -> None:
        player = self.human(sid="secondary")
        self.runner.legacy.human_owner_sid["secondary"] = "human"
        player["integrity"] = 199.9
        self.runner._time = 10
        self.sim.update_player_integrity(60, self.runner.world)
        self.assertEqual(200, player["integrity"])
        event = self.sim.drain_events()[-1]
        self.assertEqual((200, 200, "human", "secondary"),
                         (event.value, event.max_integrity, event.target_sid, event.bsid))
        player["boat"] = load_boat("submarine")
        self.sim.init_player_integrity("secondary")
        self.assertEqual((100, 100), (player["integrity"], player["maxIntegrity"]))

    def test_reset_has_no_phantom_reward_and_damage_remains_absolute(self) -> None:
        env = SubmarineDuelEnv(agent_boat_type="destroyer", control_version="destroyer_duel_v2",
            opponents=[dict(boat_type="destroyer", ai="default")],
            reward={"decision_cost": 0, "new_contact": 0})
        self.addCleanup(env.close)
        obs, _ = env.reset(seed=17)
        self.assertEqual(1, obs[2])
        self.assertEqual((200, 200), (env._previous_agent_hp, env._previous_opponent_hp))
        action = np.array([2, 1, 0, 0, 0, 0])
        env.runner.world.update(islands=[], thermoclines=[])
        target = env._opponent()
        target["external_control"] = True
        self.assertEqual(0, env.step(action)[1])
        env.runner.sim.bot_apply_damage(env.opponent_sid, target, 80, None)
        self.assertAlmostEqual(80 * env.reward_cfg["damage_dealt"], env.step(action)[1])

    def test_torpedo_splash_persistent_hp_depth_and_single_destruction(self) -> None:
        near = self.lure(1)
        far = self.lure(2, x=19)
        deep = self.lure(3, y=-21)
        outside = self.lure(4, x=21)
        torpedo = dict(ownerPlayerId="shooter", tid=1, x=0, y=-2, z=0)
        for hit in range(3):
            self.sim._explode_torpedo(torpedo, direct_hit_id=None, damage=80, hit_target_id=None)
            if hit == 0:
                self.assertEqual(0, near["integrity"])
                self.assertAlmostEqual(6, far["integrity"])
                self.assertAlmostEqual(6, deep["integrity"])
                self.assertEqual(10, outside["integrity"])
        emitted = self.sim.drain_events()
        destroyed = [e.lid for e in emitted if isinstance(e, events.LureDestroyed)]
        self.assertEqual([1, 2, 3], destroyed)
        self.assertEqual(4, sum(isinstance(e, events.LureIntegrityChanged) for e in emitted))
        self.assertEqual({("owner", 4)}, set(self.sim.lures))

    def test_grenade_and_mine_formulas_and_expiry(self) -> None:
        far = self.lure(1, x=19)
        deep = self.lure(2, y=-23)
        self.sim.explode_server_grenade(dict(x=0, z=0, targetDepthU=2, damage=60,
                                            ownerPlayerId="shooter", gid=1, effectRadiusU=20))
        self.assertAlmostEqual(7, far["integrity"])
        self.assertEqual(10, deep["integrity"])
        event = next(e for e in self.sim.drain_events() if isinstance(e, events.GrenadeExploded))
        self.assertEqual(3, event.dealt)
        mine = dict(ownerId="shooter", mid=1, kind="bottom", x=0, y=-2, z=0, range=200, damage=10)
        self.sim.mines[("shooter", 1)] = mine
        self.sim.explode_server_mine(mine)
        self.assertAlmostEqual(1.75, far["integrity"])
        self.sim.explode_server_mine(mine)
        self.assertAlmostEqual(1.75, far["integrity"])
        self.runner._time = far["expiresAt"]
        self.sim.update_server_torpedoes(0.05, self.runner.world)
        self.sim.update_server_torpedoes(0.05, self.runner.world)
        self.assertEqual(2, sum(isinstance(e, events.LureDestroyed) for e in self.sim.drain_events()))

    def test_grenade_self_damage_human_bt_rl_and_collateral(self) -> None:
        for owner_kind in ("human", "bt", "rl"):
            for distance in (0, 10, 20, 21):
                with self.subTest(owner=owner_kind, distance=distance):
                    self.setUp()
                    human = self.human()
                    sid = self.runner.spawn_bot("destroyer", ai="default",
                        external_control=owner_kind == "rl", position=(0, 0))
                    bot = self.sim.bots[sid]
                    for entity in (human, bot):
                        entity.update(team_id="same-team")
                        entity["position"] = dict(x=distance, y=-2, z=0)
                    self.sim.players[sid]["position"] = dict(bot["position"])
                    owner = human if owner_kind == "human" else bot
                    self.sim.explode_server_grenade(dict(x=0, z=0, targetDepthU=2,
                        damage=60, ownerPlayerId=owner["id"], gid=1, effectRadiusU=20))
                    damage = 60 * max(0, 1 - distance / 20)
                    self.assertEqual(200 - damage, human["integrity"])
                    self.assertEqual(human["integrity"], bot["integrity"])
                    self.assertEqual(bot["integrity"], self.sim.players[sid]["integrity"])
                    event = next(e for e in self.sim.drain_events()
                                 if isinstance(e, events.GrenadeExploded))
                    self.assertEqual(damage, event.dealt)

    def test_human_and_bot_lure_initialization_and_nonlethal_dispatch(self) -> None:
        player = self.human()
        self.runner.legacy.lure_ammo["human"] = 2
        io = Mock()
        ns = server_functions({"handle_lure_drop", "_dispatch_lure_integrity_changed"}, {
            "sim": self.sim, "simulation": simulation, "players": self.sim.players,
            "request": SimpleNamespace(sid="human"), "resolve_acting_sid": lambda sid, data: sid,
            "lure_ammo": self.runner.legacy.lure_ammo, "next_lure_lid": {},
            "server_lures": self.sim.lures, "emit_lure_count": Mock(), "socketio": io,
            "time": SimpleNamespace(time=self.sim.now), "_emit_one": io.emit})
        ns["handle_lure_drop"]({})
        human_lure = self.sim.lures[("human", 1)]
        self.assertEqual((10, 10), (human_lure["integrity"], human_lure["maxIntegrity"]))
        self.assertEqual(1, self.runner.legacy.lure_ammo["human"])
        self.assertEqual(10, io.emit.call_args.args[1]["maxIntegrity"])
        sid = self.runner.spawn_bot("submarine", external_control=True, position=(100, 0))
        self.assertTrue(self.sim.bot_drop_lure(self.sim.bots[sid]))
        bot_lure = self.sim.lures[(self.sim.bots[sid]["id"], 1)]
        self.assertEqual((10, 10), (bot_lure["integrity"], bot_lure["maxIntegrity"]))
        self.sim.lure_splash_damage(human_lure["x"], human_lure["y"], human_lure["z"], 5, 20)
        changed = next(e for e in self.sim.drain_events() if isinstance(e, events.LureIntegrityChanged))
        ns["_dispatch_lure_integrity_changed"](changed)
        self.assertEqual(("lure_integrity", {"ownerId": "human", "lid": 1,
                          "integrity": 5, "maxIntegrity": 10}), io.emit.call_args.args)
        self.assertEqual(1, self.runner.legacy.lure_ammo["human"])

    def test_direct_lure_collision_uses_nominal_damage_and_depth(self) -> None:
        sid = self.runner.spawn_bot("destroyer", external_control=True, position=(100, 100))
        target = dict(id="target", position=dict(x=200, y=-2, z=100))
        self.assertTrue(self.sim.spawn_bot_torpedo(self.sim.bots[sid], target))
        torpedo = next(iter(self.sim.torpedoes.values()))
        torpedo.update(x=0, y=-2, z=0, dirX=1, dirZ=0, pitch=0,
                       speed=2, activation=0, minNoise=1e9)
        deep = self.lure(1, x=0.1, y=-40)
        self.sim.update_server_torpedoes(0.05, self.runner.world)
        self.assertTrue(self.sim.torpedoes)
        impact = self.lure(2, x=0.2)
        self.sim.drain_events()
        self.sim.update_server_torpedoes(0.05, self.runner.world)
        self.assertFalse(self.sim.torpedoes)
        self.assertEqual(0, impact["integrity"])
        self.assertEqual(10, deep["integrity"])
        emitted = self.sim.drain_events()
        explosion = next(e for e in emitted if isinstance(e, events.TorpedoExploded))
        self.assertEqual(80, explosion.damage)
        self.assertTrue(explosion.hit_lure)
        self.assertEqual(1, sum(isinstance(e, events.LureDestroyed) for e in emitted))

    def test_server_selection_and_bt_spawn_use_real_json(self) -> None:
        io = Mock()
        legacy = self.runner.legacy
        ns = dict(sim=self.sim, simulation=simulation, json=json, logging=logging,
            players=self.sim.players, bots=self.sim.bots, request=SimpleNamespace(sid="human"),
            MAX_HUMAN_PLAYERS=20, BOAT_TYPES={"destroyer", "submarine"},
            uuid=SimpleNamespace(uuid4=lambda: "human-id"),
            time=SimpleNamespace(time=self.sim.now), random=self.runner.random,
            load_world=lambda: self.runner.world, _random_spawn_on_nav_graph=lambda *args: (0, 0),
            config={}, BOT_RL_MODELS={}, day_cycle_snapshot=lambda: {},
            sonar_beacons={}, passive_sonar_beacons={}, mines_server={},
            player_boats_sids={}, emit=io.emit, socketio=io,
            init_player_integrity=self.sim.init_player_integrity,
            emit_integrity=self.sim._emit_integrity, resolve_acting_sid=lambda sid, data: sid,
            game_trace=SimpleNamespace(enabled=False),
            next_bot_id=1, UNIT_METERS_BOT=10, bot_ai=SimpleNamespace(load_ai=lambda name: {}))
        for kind in ("torpedo", "drone", "grenade", "cannon", "beacon", "lure", "mine"):
            ns[kind + "_ammo"] = getattr(legacy, kind + "_ammo")
            ns["init_" + kind + "_ammo_for_sid"] = getattr(legacy, "init_" + kind + "_ammo_for_sid")
        ns.update(passive_beacon_ammo={}, init_passive_beacon_ammo_for_sid=Mock())
        server_functions({"handle_select_boat", "load_boat", "spawn_bot", "handle_cheat_resupply"}, ns)
        ns["handle_select_boat"]({"boatType": "destroyer"})
        player = self.sim.players["human"]
        self.assertEqual((200, 200), (player["integrity"], player["maxIntegrity"]))
        payload = next(c.args[1] for c in io.emit.call_args_list if c.args[0] == "init")
        self.assertEqual((200, 200), (payload["integrity"], payload["maxIntegrity"]))
        self.sim.apply_player_damage("human", player, 80, None)
        self.sim.drain_events()
        ns["handle_cheat_resupply"]({})
        self.assertEqual(200, player["integrity"])
        event = self.sim.drain_events()[-1]
        self.assertEqual((200, 200), (event.value, event.max_integrity))
        ns["spawn_bot"]("destroyer")
        bot = next(iter(self.sim.bots.values()))
        self.assertEqual((200, 200), (bot["integrity"], bot["maxIntegrity"]))
        self.assertEqual(200, self.sim.players[bot["sid"]]["maxIntegrity"])
        with patch("rl.rl_runtime.attach_controller") as attach:
            ns["spawn_bot"]("destroyer", ai_name="rl_test")
        runtime_bot = attach.call_args.args[0]
        self.assertTrue(runtime_bot["external_control"])
        self.assertEqual((200, 200), (runtime_bot["integrity"], runtime_bot["maxIntegrity"]))


if __name__ == "__main__":
    unittest.main()
