"""Canon physique partage : vraie Sim, handlers extraits sans port reseau."""

import copy
import json
import math
import random
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import events
import game_trace
import geometry
from rl.headless import HeadlessRunner
import test_server_fire_los


class CannonBallisticsTest(unittest.TestCase):
    def setUp(self) -> None:
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        self.runner = HeadlessRunner(seed=73)
        self.runner.world.update(islands=[], thermoclines=[])
        self.runner.reset(seed=73)
        self.sim = self.runner.sim
        self.sid = self.runner.spawn_bot("destroyer", external_control=True,
                                         position=(0, 0), team_id="a")
        self.tid = self.runner.spawn_bot("submarine", external_control=True,
                                         position=(80, 0), team_id="b")
        self.shooter = self.sim.bots[self.sid]
        self.target = self.sim.bots[self.tid]
        self.move(self.tid, 80, -0.2, 0)
        self.sim.drain_events()

    def move(self, sid: str, x: float, y: float, z: float) -> None:
        for p in (self.sim.players[sid], self.sim.bots[sid]):
            p["position"] = dict(x=x, y=y, z=z)

    def advance(self, seconds: float) -> list:
        self.runner._time += seconds
        self.sim.update_cannon_shells()
        return self.sim.drain_events()

    def fire(self) -> dict:
        self.assertTrue(self.sim.bot_fire_cannon(self.shooter, self.sim.players[self.tid]))
        return copy.deepcopy(self.sim.cannon_shells[-1])

    def island(self, x: float = 40, z: float = 0) -> None:
        self.runner.world["islands"] = [{"points": [dict(x=x + dx, z=z + dz)
            for dx, dz in ((0, -1), (0.001, -1), (0.001, 1), (0, 1))]}]

    def test_stationary_hit_only_at_physical_arrival_once(self) -> None:
        self.fire()
        self.assertFalse(any(isinstance(e, events.CannonHit) for e in self.advance(1.4)))
        result = self.advance(0.2)
        hits = [e for e in result if isinstance(e, events.CannonHit)]
        self.assertEqual([(self.target["id"], 30)], [(e.target_id, e.damage) for e in hits])
        self.assertEqual(70, self.target["integrity"])
        self.assertEqual([], self.sim.cannon_shells)
        self.assertEqual([], self.advance(10))

    def test_lateral_and_diving_targets_evade(self) -> None:
        for y, z in ((-0.2, 8), (-0.251, 0), (-10, 0)):
            with self.subTest(y=y, z=z):
                self.setUp()
                shell = self.fire()
                self.move(self.tid, 80, y, z)
                self.assertEqual(shell, self.sim.cannon_shells[0])
                result = self.advance(2)
                self.assertFalse(any(isinstance(e, events.CannonHit) for e in result))
                self.assertEqual(100, self.target["integrity"])

    def test_narrow_island_blocks_at_first_contact_not_endpoint(self) -> None:
        self.island()
        self.fire()
        result = self.advance(1)
        impact = next(e for e in result if isinstance(e, events.CannonImpact))
        self.assertEqual("island", impact.reason)
        self.assertAlmostEqual(40, impact.x)
        self.assertEqual(100, self.target["integrity"])
        self.assertFalse(self.sim.cannon_shells)

    def test_nearest_island_independent_of_order_and_boat_before_island(self) -> None:
        self.island(70)
        far = self.runner.world["islands"][0]
        self.island(40)
        self.runner.world["islands"].insert(0, far)
        self.fire()
        self.assertAlmostEqual(40, next(e.x for e in self.advance(2) if isinstance(e, events.CannonImpact)))
        self.setUp()
        self.island(79.99)
        self.fire()
        result = self.advance(2)
        self.assertEqual("boat", next(e.reason for e in result if isinstance(e, events.CannonImpact)))
        self.assertEqual(70, self.target["integrity"])

    def test_target_moves_behind_island_no_guidance_or_damage(self) -> None:
        self.island(z=10)
        shell = self.fire()
        self.move(self.tid, 80, -0.2, 10)
        self.assertEqual(shell, self.sim.cannon_shells[0])
        result = self.advance(2)
        self.assertFalse(any(isinstance(e, events.CannonHit) for e in result))

    def test_dynamic_nearer_boat_and_friendly_fire(self) -> None:
        self.fire()
        sid = self.runner.spawn_bot("destroyer", external_control=True,
                                    position=(76, 20), team_id="a")
        self.move(sid, 76, 0.0, 0)
        result = self.advance(2)
        hit = next(e for e in result if isinstance(e, events.CannonHit))
        self.assertEqual(self.sim.players[sid]["id"], hit.target_id)
        self.assertEqual(100, self.target["integrity"])

    def test_shell_flies_over_nearer_hull_when_arc_is_high(self) -> None:
        sid = self.runner.spawn_bot("destroyer", external_control=True,
                                    position=(40, 0), team_id="a")
        self.fire()
        result = self.advance(2)
        self.assertEqual(self.target["id"], next(e.target_id for e in result if isinstance(e, events.CannonHit)))
        self.assertEqual(200, self.sim.bots[sid]["integrity"])

    def test_shell_survives_shooter_sinking(self) -> None:
        self.fire()
        attacker = self.shooter["id"]
        self.sim.bot_apply_damage(self.sid, self.shooter, 200, self.target["id"])
        self.assertNotIn(self.sid, self.sim.bots)
        result = self.advance(2)
        self.assertEqual(attacker, next(e.shooter_id for e in result if isinstance(e, events.CannonHit)))

    def test_snapshot_is_invariant_even_if_target_removed(self) -> None:
        point = copy.deepcopy(self.sim.players[self.tid])
        point["tracked"] = False
        self.sim.players.pop(self.tid)
        self.sim.bots.pop(self.tid)
        self.assertTrue(self.sim.bot_fire_cannon(self.shooter, point))
        shell = copy.deepcopy(self.sim.cannon_shells[0])
        point["position"].update(x=0, z=200)
        self.assertEqual(shell, self.sim.cannon_shells[0])
        self.assertNotIn("target_id", shell)
        self.advance(2)
        self.assertFalse(self.sim.cannon_shells)

    def test_invalid_points_range_ammo_and_cooldown_have_no_effect(self) -> None:
        ammo = copy.deepcopy(self.runner.legacy.cannon_ammo)
        for point in (None, {}, {"x": 0, "z": 0}, {"x": 201, "z": 0},
                      {"x": True, "z": 0}, {"x": math.nan, "z": 0},
                      {"x": 80, "z": math.inf}, {"x": "80", "z": 0}):
            self.assertFalse(self.sim.fire_cannon(self.sid, self.shooter, point))
        self.shooter["next_cannon_at"] = 3
        self.assertFalse(self.sim.bot_fire_cannon(self.shooter, self.target))
        self.shooter["next_cannon_at"] = 0
        self.shooter["boatType"] = "submarine"
        self.shooter["position"]["y"] = -1
        self.assertFalse(self.sim.bot_fire_cannon(self.shooter, self.target))
        self.assertEqual(ammo, self.runner.legacy.cannon_ammo)
        self.assertEqual([], self.sim.drain_events())
        self.shooter["boatType"] = "destroyer"
        self.runner.legacy.cannon_ammo[self.sid]["cannon"] = 0
        self.assertFalse(self.sim.bot_fire_cannon(self.shooter, self.target))
        self.assertFalse(self.sim.cannon_shells)

    def test_dispersion_is_geometry_not_a_guaranteed_miss_and_range_is_bounded(self) -> None:
        self.move(self.tid, 200, -0.2, 0)
        with patch("simulation.random.random", return_value=1), patch("simulation.random.uniform", return_value=0):
            shell = self.fire()
        self.assertEqual(200, shell["end_x"])
        self.assertEqual(4, shell["duration"])
        self.advance(5)
        self.assertEqual(70, self.target["integrity"])
        self.assertFalse(self.sim.cannon_shells)

    def test_numerical_points_do_not_poison_sim_or_human_ticks(self) -> None:
        test_server_fire_los.ServerFireLosTest.setUpClass()
        for human in (False, True):
            for x in (1e-200, math.ulp(0.0), 1e308, math.nan, math.inf):
                with self.subTest(human=human, x=x):
                    self.setUp()
                    shooter = self.shooter
                    if human:
                        self.sim.bots.pop(self.sid)
                        shooter = self.sim.players[self.sid]
                        shooter["is_bot"] = False
                    io = Mock()
                    ns = dict(vars(self.runner.legacy), sim=self.sim, socketio=io,
                              request=type("Request", (), {"sid": self.sid})(),
                              resolve_acting_sid=lambda sid, data: sid)
                    exec(test_server_fire_los.ServerFireLosTest.code, ns)
                    ammo = copy.deepcopy(self.runner.legacy.cannon_ammo)
                    cooldown = shooter.get("next_cannon_at")
                    point = {"x": x, "z": 0}
                    if human:
                        ns["handle_cannon_fire"]({"kind": "cannon", "targetType": "point",
                                                  "fixedTarget": point})
                    else:
                        self.sim.fire_cannon(self.sid, shooter, point)
                    # Les vrais ticks doivent rester utilisables meme apres le tir invalide.
                    for _ in range(3):
                        self.runner._time += 0.1
                        self.sim.step(0, self.runner.world)
                    self.assertEqual(ammo, self.runner.legacy.cannon_ammo)
                    self.assertEqual(cooldown, shooter.get("next_cannon_at"))
                    self.assertFalse(self.sim.cannon_shells)
                    self.assertFalse(any(isinstance(e, (events.CannonFire, events.CannonImpact))
                                         for e in self.sim.drain_events()))
                    self.assertEqual(100, self.target["integrity"])
                    self.move(self.tid, 0.01, -0.2, 0)
                    if human:
                        ns["handle_cannon_fire"]({"kind": "cannon", "targetType": "point",
                                                  "fixedTarget": {"x": 0.01, "z": 0}})
                    else:
                        self.assertTrue(self.sim.fire_cannon(self.sid, shooter, {"x": 0.01, "z": 0}))
                    self.advance(0.1)
                    self.assertEqual(70, self.target["integrity"])
                    self.assertFalse(self.sim.cannon_shells)
                    io.start_background_task.assert_not_called()

    def test_finite_coordinates_with_overflowed_length_reject_before_ammo(self) -> None:
        self.shooter["boat"]["cannon"]["range"] = math.inf
        ammo = copy.deepcopy(self.runner.legacy.cannon_ammo)
        self.assertFalse(self.sim.fire_cannon(self.sid, self.shooter, {"x": 1e308, "z": 0}))
        self.assertEqual(ammo, self.runner.legacy.cannon_ammo)
        self.assertFalse(self.sim.cannon_shells)

    def test_finite_extreme_height_and_short_resolvable_displacement(self) -> None:
        for x, y in ((1e-150, 0), (80, 1e308), (80, -1e308)):
            with self.subTest(x=x, y=y):
                self.setUp()
                self.assertTrue(self.sim.fire_cannon(self.sid, self.shooter, {"x": x, "y": y, "z": 0}))
                for _ in range(3):
                    self.advance(1)
                self.assertFalse(self.sim.cannon_shells)
                self.assertEqual(100, self.target["integrity"])

    def test_unresolvable_collision_coefficients_do_not_poison_shells(self) -> None:
        for x in (1e-200, 1e308):
            with self.subTest(x=x):
                self.setUp()
                self.fire()
                self.sim.cannon_shells[0]["end_x"] = x
                for _ in range(3):
                    self.advance(1)
                self.assertFalse(self.sim.cannon_shells)
                self.assertEqual(100, self.target["integrity"])

    def test_active_passive_beacon_and_surface_mine_use_flight(self) -> None:
        for kind in ("beacon", "passive_beacon", "mine"):
            with self.subTest(kind=kind):
                self.setUp()
                self.move(self.tid, 100, -0.2, 20)
                point = dict(x=80, y=0, z=0)
                if kind == "mine":
                    # La mine utilise son explosion native, sans nouveau capital HP.
                    owner = self.sim.players[self.tid]
                    owner["position"] = dict(point)
                    self.assertTrue(self.sim.place_mine(self.tid, owner, "surface", 0))
                    self.move(self.tid, 100, -0.2, 20)
                    store = self.sim.mines
                else:
                    store = self.sim.beacons if kind == "beacon" else self.runner.legacy.passive_sonar_beacons
                    store[1] = dict(point)
                self.assertTrue(self.sim.fire_cannon(self.sid, self.shooter, point, kind))
                self.advance(1)
                self.assertTrue(store)
                result = self.advance(1)
                self.assertFalse(store)
                expected = {"beacon": events.SonarBeaconDestroyed,
                            "passive_beacon": events.PassiveSonarBeaconDestroyed,
                            "mine": events.MineExploded}[kind]
                self.assertTrue(any(isinstance(e, expected) for e in result))

    def test_human_handler_and_bot_share_endpoint_and_impact(self) -> None:
        test_server_fire_los.ServerFireLosTest.setUpClass()
        bot_shell = self.fire()
        bot_events = self.advance(2)
        self.setUp()
        self.sim.bots.pop(self.sid)
        human = self.sim.players[self.sid]
        human["is_bot"] = False
        io = Mock()
        ns = dict(vars(self.runner.legacy), sim=self.sim, socketio=io, UNIT_METERS_BOT=10,
                  request=type("Request", (), {"sid": self.sid})(),
                  resolve_acting_sid=lambda sid, data: sid)
        exec(test_server_fire_los.ServerFireLosTest.code, ns)
        ns["handle_cannon_fire"]({"kind": "cannon", "targetType": "boat", "targetId": self.target["id"]})
        self.assertEqual(bot_shell, self.sim.cannon_shells[0])
        result = self.advance(2)
        self.assertEqual([e for e in bot_events if isinstance(e, (events.CannonFire, events.CannonHit, events.CannonImpact))],
                         [e for e in result if isinstance(e, (events.CannonFire, events.CannonHit, events.CannonImpact))])
        io.start_background_task.assert_not_called()

        self.sim.cannon_shells.clear()
        point = {"x": 80, "y": -0.2, "z": 0}
        self.move(self.tid, 80, -10, 20)
        self.island()
        ns["handle_cannon_fire"]({"kind": "cannon", "targetType": "point", "fixedTarget": point})
        self.assertEqual(80, self.sim.cannon_shells[0]["end_x"])
        self.assertEqual(-0.2, self.sim.cannon_shells[0]["end_y"])
        point["x"] = 0
        self.assertEqual(80, self.sim.cannon_shells[0]["end_x"])
        result = self.advance(2)
        self.assertEqual("island", next(e.reason for e in result if isinstance(e, events.CannonImpact)))
        before = copy.deepcopy(self.runner.legacy.cannon_ammo)
        ns["handle_cannon_fire"]({"kind": "cannon", "targetType": "point", "fixedTarget": {"x": math.nan, "z": 0}})
        self.assertEqual(before, self.runner.legacy.cannon_ammo)
        self.assertFalse(self.sim.cannon_shells)

    def test_sim_step_and_trace_include_full_shell_and_native_impact(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            trace = game_trace.GameTrace(True, path=path)
            self.addCleanup(trace.close)
            shell = self.fire()
            for event in self.sim.drain_events():
                trace.event(event, self.sim.players)
            self.runner.legacy.sim_tick_multiplier = 1
            trace.observe(self.sim, self.runner.legacy)
            self.runner._time = 2
            self.sim.step(0, self.runner.world)
            for event in self.sim.drain_events():
                trace.event(event, self.sim.players)
            trace.close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            text = path.read_text()
            self.assertIn('CannonFire', text)
            self.assertIn('CannonImpact', text)
            self.assertIn('CannonHit', text)
            self.assertTrue(any(row.get("type") == "cannon_shell" for row in rows))
            self.assertEqual(shell, game_trace.select(shell))

    def test_closed_island_geometry_tangent_collinear_and_order(self) -> None:
        self.island()
        for z in (-1, 0, 1):
            self.assertAlmostEqual(0.5, geometry.first_island_intersection(0, z, 80, z, self.runner.world))
        self.assertEqual(0, geometry.first_island_intersection(40, 1, 40, 1, self.runner.world))
        self.assertIsNone(geometry.first_island_intersection(0, 2, 80, 2, self.runner.world))


if __name__ == "__main__":
    unittest.main()
