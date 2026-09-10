"""Regressions canon/radar strict et sonar actif temporise.

Le navigateur et le handler humain ne sont pas executes : leurs regles servent de comparaison
documentee, pas de preuve de parite reseau complete.
"""

import math
import random
import unittest

import numpy as np

import geometry
from rl.headless import HeadlessRunner
from rl.rl_control import (
    DESTROYER_OBSERVATION_VERSION,
    DESTROYER_V1_OBSERVATION_VERSION,
    SUBMARINE_OBSERVATION_VERSION,
    apply_action,
    build_observation,
)
from simulation import UNIT_METERS_BOT


class FairnessDiagnosticsTest(unittest.TestCase):
    """Fixtures reelles et minimales, sans simulation des regles par des mocks."""

    def setUp(self) -> None:
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        random.seed(73)
        self.runner = HeadlessRunner(seed=73)
        self.runner.world["islands"] = []
        self.runner.world["thermoclines"] = []

    def _spawn_torpedo_scene(self, boat_type: str, version: str) -> tuple[dict, dict]:
        """Construit un observateur et une vraie torpille Sim, sans obstacle."""
        runner = self.runner
        runner.reset(seed=73)
        runner.world["islands"] = []
        runner.world["thermoclines"] = []
        observer_sid = runner.spawn_bot(
            boat_type=boat_type,
            external_control=True, position=(100.0, 100.0), rotation=0.0,
            team_id="observer")
        shooter_sid = runner.spawn_bot(
            external_control=True, position=(120.0, 100.0), rotation=0.0,
            team_id="enemy")
        observer = runner.legacy.bots[observer_sid]
        observer["rl_control_version"] = version
        shooter = runner.legacy.bots[shooter_sid]
        self.assertTrue(runner.sim.spawn_bot_torpedo(
            shooter, runner.legacy.players[observer_sid]))
        torpedo = next(iter(runner.sim.torpedoes.values()))
        torpedo["y"] = observer["position"]["y"]
        return observer, torpedo

    def test_hidden_torpedo_cannot_influence_observation(self) -> None:
        """Filtrage avant selection, meme si la torpille cachee est verrouillee."""
        runner = self.runner
        polygon = [{"x": x, "z": z} for x, z in (
            (105.0, 90.0), (115.0, 90.0), (115.0, 110.0), (105.0, 110.0))]
        for boat_type, version, start in (
            ("submarine", SUBMARINE_OBSERVATION_VERSION, 17),
            ("destroyer", DESTROYER_V1_OBSERVATION_VERSION, 21),
            ("destroyer", DESTROYER_OBSERVATION_VERSION, 25),
        ):
            for barrier in ("island", "thermocline", "range", "ceil_island", "thin_island"):
                with self.subTest(version=version, barrier=barrier):
                    observer, hidden = self._spawn_torpedo_scene(boat_type, version)
                    self.assertEqual(1.0, build_observation(observer, runner.sim, runner.world)[start])
                    if barrier == "island":
                        runner.world["islands"] = [{"points": polygon}]
                    elif barrier in ("ceil_island", "thin_island"):
                        # Ancien ecart floor/ceil et ile manquee par les deux grilles.
                        left = 104.8 if barrier == "ceil_island" else 101.01
                        right = 105.0 if barrier == "ceil_island" else left + 0.01
                        runner.world["islands"] = [{"points": [
                            {"x": x, "z": z} for x, z in (
                                (left, 99.0), (right, 99.0),
                                (right, 101.0), (left, 101.0))]}]
                        self.assertFalse(geometry.line_of_sight_clear(
                            100.0, 100.0, hidden["x"], hidden["z"], runner.world))
                    elif barrier == "thermocline":
                        runner.world["thermoclines"] = [{"depthMeters": 40.0, "points": polygon}]
                        hidden["y"] = -8.0 - observer["position"]["y"]
                    else:
                        observer["boat"]["radarRangeMeters"] = 500.0
                        hidden["x"] = 160.0
                    hidden_key = (hidden["ownerPlayerId"], hidden["tid"])
                    del runner.sim.torpedoes[hidden_key]
                    baseline = build_observation(observer, runner.sim, runner.world)
                    np.testing.assert_array_equal(np.zeros(7), baseline[start:start + 7])
                    for with_visible in (False, True):
                        if with_visible:
                            # Menace entrante : le tube suit maintenant le cap du tireur.
                            shooter_sid = runner.spawn_bot(
                                external_control=True, position=(100.0, 140.0),
                                rotation=-math.pi / 2, team_id="enemy")
                            self.assertTrue(runner.sim.spawn_bot_torpedo(
                                runner.legacy.bots[shooter_sid],
                                runner.legacy.players[observer["sid"]]))
                            visible = next(iter(runner.sim.torpedoes.values()))
                            visible["y"] = observer["position"]["y"]
                            baseline = build_observation(observer, runner.sim, runner.world)
                            self.assertEqual(1.0, baseline[start])
                            self.assertAlmostEqual(39.6 / 200.0, baseline[start + 2])
                        for locked, speed, kind in (
                            (False, 2.57222, "acoustic"),
                            (True, 100.0, "autonomous"),
                            (True, 0.0, "wireGuided"),
                        ):
                            hidden.update(acquiredBoatId=observer["id"] if locked else None,
                                          speed=speed, kind=kind)
                            # La torpille cachee precede aussi la visible dans le dictionnaire.
                            visible_items = dict(runner.sim.torpedoes)
                            runner.sim.torpedoes.clear()
                            runner.sim.torpedoes[hidden_key] = hidden
                            runner.sim.torpedoes.update(visible_items)
                            np.testing.assert_array_equal(
                                baseline, build_observation(observer, runner.sim, runner.world))
                            del runner.sim.torpedoes[hidden_key]

    def test_torpedo_tick_cannot_cross_thin_island_before_activation(self) -> None:
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                _, torpedo = self._spawn_torpedo_scene("submarine", SUBMARINE_OBSERVATION_VERSION)
                torpedo.update(x=100.0, z=100.0, dirX=1.0, dirZ=0.0, pitch=0.0,
                               speed=2.0, activation=1000.0, traveled=0.0, initialTarget=None)
                self.runner.world["islands"] = [{"points": [
                    {"x": x, "z": z} for x, z in (
                        (100.05, 99.0), (100.06, 99.0),
                        (100.06, 101.0), (100.05, 101.0))]}] if blocked else []
                self.runner.sim.update_server_torpedoes(0.05, self.runner.world)
                key = (torpedo["ownerPlayerId"], torpedo["tid"])
                self.assertEqual(not blocked, key in self.runner.sim.torpedoes)
                if not blocked:
                    self.assertAlmostEqual(100.1, torpedo["x"])

    def test_torpedo_lock_and_kind_are_neutral_with_duplicate_tids(self) -> None:
        """Verrous propres/etrangers et types ne changent aucun slot d'observation."""
        runner = self.runner
        for boat_type, version, start, dimension in (
            ("submarine", SUBMARINE_OBSERVATION_VERSION, 17, 32),
            ("destroyer", DESTROYER_V1_OBSERVATION_VERSION, 21, 36),
            ("destroyer", DESTROYER_OBSERVATION_VERSION, 25, 40),
        ):
            for barrier in (None, "island", "thermocline"):
                with self.subTest(version=version, barrier=barrier):
                    runner.reset(seed=73)
                    runner.world["islands"] = []
                    runner.world["thermoclines"] = []
                    sid = runner.spawn_bot(
                        boat_type=boat_type, external_control=True,
                        position=(100.0, 100.0), rotation=0.0, team_id="observer")
                    bot = runner.legacy.bots[sid]
                    bot["rl_control_version"] = version
                    torpedoes = []
                    for x in (101.0, 120.0):
                        shooter_sid = runner.spawn_bot(
                            external_control=True, position=(x, 100.0),
                            rotation=0.0, team_id="enemy")
                        shooter = runner.legacy.bots[shooter_sid]
                        self.assertTrue(runner.sim.spawn_bot_torpedo(
                            shooter, runner.legacy.players[sid]))
                        torpedoes.append(runner.sim.torpedoes[(shooter["id"], 1)])
                    selected, other = torpedoes
                    self.assertEqual(selected["tid"], other["tid"])
                    self.assertNotEqual(selected["ownerPlayerId"], other["ownerPlayerId"])
                    # CPA proche mais cap sortant : conserver ETA 0, apres
                    # l'arrivante seulement si celle-ci est visible.
                    selected["dirX"] = 1.0
                    selected["dirZ"] = 0.0
                    selected["y"] = bot["position"]["y"]
                    polygon = [{"x": x, "z": z} for x, z in (
                        (105.0, 90.0), (115.0, 90.0),
                        (115.0, 110.0), (105.0, 110.0))]
                    if barrier == "island":
                        runner.world["islands"] = [{"points": polygon}]
                    elif barrier == "thermocline":
                        runner.world["thermoclines"] = [
                            {"depthMeters": 40.0, "points": polygon}]
                        other["y"] = -8.0 - bot["position"]["y"]
                    pos = bot["position"]
                    for torpedo, visible in ((selected, True), (other, barrier is None)):
                        clear = geometry.line_of_sight_clear(
                            pos["x"], pos["z"], torpedo["x"], torpedo["z"], runner.world)
                        crossed = geometry.count_thermoclines_crossed(
                            pos["x"], pos["y"], pos["z"], torpedo["x"],
                            torpedo["y"], torpedo["z"], runner.world)
                        self.assertEqual(visible, clear and crossed == 0)
                    baseline = build_observation(bot, runner.sim, runner.world)
                    self.assertEqual((dimension,), baseline.shape)
                    self.assertEqual(np.float32, baseline.dtype)
                    self.assertEqual(1.0, baseline[start])
                    self.assertEqual(0.0, baseline[start + 4])
                    self.assertEqual(0.0, baseline[start + 5])
                    other["acquiredBoatId"] = bot["id"]
                    threats = runner.sim.bot_torpedoes_threat(bot)
                    self.assertEqual(2 if barrier is None else 1, len(threats))
                    expected = other if barrier is None else selected
                    self.assertEqual(expected["ownerPlayerId"], threats[0]["ownerId"])
                    self.assertTrue(all(t["kind"] is None for t in threats))
                    if barrier is None:
                        self.assertGreater(threats[0]["eta_s"], 0.0)
                    self.assertEqual(0.0, threats[-1]["eta_s"])
                    np.testing.assert_array_equal(
                        baseline, build_observation(bot, runner.sim, runner.world))
                    selected["acquiredBoatId"] = bot["id"]
                    selected["kind"] = "autonomous"
                    np.testing.assert_array_equal(
                        baseline, build_observation(bot, runner.sim, runner.world))
                    selected["acquiredBoatId"] = other["ownerPlayerId"]
                    selected["kind"] = "wireGuided"
                    np.testing.assert_array_equal(
                        baseline, build_observation(bot, runner.sim, runner.world))

    def test_visible_threat_uses_geometric_eta_not_lock_priority(self) -> None:
        """Le verrou ne change ni inclusion, ni ordre, ni ETA des menaces visibles."""
        runner = self.runner
        bot, farther = self._spawn_torpedo_scene("submarine", SUBMARINE_OBSERVATION_VERSION)
        farther["x"] = 120.0
        farther["speed"] = 5.0
        shooter_sid = runner.spawn_bot(
            external_control=True, position=(110.0, 100.0), rotation=0.0, team_id="enemy")
        self.assertTrue(runner.sim.spawn_bot_torpedo(
            runner.legacy.bots[shooter_sid], runner.legacy.players[bot["sid"]]))
        nearer = runner.sim.torpedoes[(runner.legacy.bots[shooter_sid]["id"], 1)]
        nearer["speed"] = 0.2
        nearer["y"] = bot["position"]["y"]
        baseline = build_observation(bot, runner.sim, runner.world)
        self.assertAlmostEqual(-20.0 / 200.0, baseline[18])
        self.assertAlmostEqual(20.0 / 5.0 / 10.0, baseline[20])
        for torpedo in (nearer, farther):
            torpedo["acquiredBoatId"] = bot["id"]
            np.testing.assert_array_equal(baseline, build_observation(bot, runner.sim, runner.world))
        # Egalite d'ETA : conserver l'ordre stable, sans departager par tid/type.
        nearer["speed"] = 2.5
        nearer["x"] = 110.0
        np.testing.assert_array_equal(baseline, build_observation(bot, runner.sim, runner.world))
        nearer["speed"] = 10.0
        observation = build_observation(bot, runner.sim, runner.world)
        self.assertAlmostEqual(-10.0 / 200.0, observation[18])
        self.assertAlmostEqual(0.1, observation[20])
        runner.sim.torpedoes.pop((nearer["ownerPlayerId"], nearer["tid"]))
        for speed, x, dir_x in ((0.0, 119.6, -1.0), (5.0, 200.0, 1.0)):
            farther.update(speed=speed, x=x, dirX=dir_x)
            np.testing.assert_array_equal(
                np.zeros(7), build_observation(bot, runner.sim, runner.world)[17:24])

    def test_torpedo_radar_range_defaults_and_boundary(self) -> None:
        """Portee horizontale de la coque, 30000 m par defaut, egalite incluse."""
        runner = self.runner
        for boat_type, version, start in (
            ("submarine", SUBMARINE_OBSERVATION_VERSION, 17),
            ("destroyer", DESTROYER_V1_OBSERVATION_VERSION, 21),
            ("destroyer", DESTROYER_OBSERVATION_VERSION, 25),
        ):
            for range_m in (None, 200.0):
                with self.subTest(version=version, range_m=range_m):
                    bot, torpedo = self._spawn_torpedo_scene(boat_type, version)
                    if range_m is None:
                        bot["boat"].pop("radarRangeMeters", None)
                    else:
                        bot["boat"]["radarRangeMeters"] = range_m
                    boundary_x = 100.0 + (30000.0 if range_m is None else range_m) / UNIT_METERS_BOT
                    # Vitesse de fixture pour garder une CPA menacante a la
                    # limite radar : la portee seule doit decider l'eligibilite.
                    torpedo["speed"] = (boundary_x - 100.0) / 5.0
                    torpedo["acquiredBoatId"] = bot["id"]
                    for x, visible in ((math.nextafter(boundary_x, -math.inf), True),
                                       (boundary_x, True),
                                       (math.nextafter(boundary_x, math.inf), False)):
                        torpedo["x"] = x
                        obs = build_observation(bot, runner.sim, runner.world)
                        self.assertEqual(float(visible), obs[start])
                        self.assertEqual(0.0, obs[start + 4])
                        self.assertEqual(0.0, obs[start + 5])
                        if not visible:
                            np.testing.assert_array_equal(np.zeros(7), obs[start:start + 7])

    def test_cannon_target_depth_matches_human_threshold(self) -> None:
        """Verifie le seuil humain avec le vrai contact passif et les impacts Sim.

        Comparaison au predicat de server.py::fire_cannon_intent, sans importer
        le serveur web ; la limite exacte est autorisee, juste dessous refusee.
        """
        runner = self.runner
        for flotation in (2, 3, None):
            surface_y = -(2 if flotation is None else flotation) / UNIT_METERS_BOT
            cutoff_y = surface_y - 0.05
            cases = (
                ("surface", surface_y, True),
                ("just_above", math.nextafter(cutoff_y, math.inf), True),
                ("boundary", cutoff_y, True),
                ("just_below", math.nextafter(cutoff_y, -math.inf), False),
                ("formerly_accepted", -4.5 / UNIT_METERS_BOT, False),
                ("deep", -30.0 / UNIT_METERS_BOT, False),
            )
            for label, target_y, accepted in cases:
                with self.subTest(flotation=flotation, depth=label):
                    runner.reset(seed=73)
                    sid = runner.spawn_bot(
                        boat_type="destroyer", external_control=True,
                        position=(100.0, 100.0), rotation=math.pi, team_id="destroyer")
                    target_sid = runner.spawn_bot(
                        external_control=True, position=(105.0, 100.0), rotation=0.0,
                        team_id="submarine")
                    bot = runner.legacy.bots[sid]
                    bot["rl_control_version"] = DESTROYER_OBSERVATION_VERSION
                    target = runner.legacy.bots[target_sid]
                    for entity in (target, runner.legacy.players[target_sid]):
                        if flotation is None:
                            entity["boat"].pop("flotation", None)
                        else:
                            entity["boat"]["flotation"] = flotation
                        entity["position"]["y"] = target_y
                        entity["speed"] = target["max_speed_us"]
                    self.assertEqual(1.0, build_observation(bot, runner.sim, runner.world)[18])
                    ammo_before = runner.legacy.cannon_ammo[sid]["cannon"]
                    integrity_before = target["integrity"]
                    cooldown_before = bot["next_cannon_at"]
                    result = apply_action(bot, runner.sim, [2, 1, 3, 0, 0, 0])
                    self.assertEqual(accepted, result["weapon_fired"])
                    self.assertEqual(not accepted, result["weapon_invalid"])
                    self.assertEqual("cannon" if accepted else None, result["weapon_kind"])
                    self.assertEqual(ammo_before - int(accepted),
                                     runner.legacy.cannon_ammo[sid]["cannon"])
                    self.assertEqual(int(accepted), len(runner.sim.cannon_shells))
                    if accepted:
                        self.assertEqual(target_y, runner.sim.cannon_shells[0]["end_y"])
                    else:
                        self.assertEqual(cooldown_before, bot["next_cannon_at"])
                    runner.step(0.25)
                    self.assertEqual([], runner.sim.cannon_shells)
                    if accepted:
                        self.assertLess(target["integrity"], integrity_before)
                    else:
                        self.assertEqual(integrity_before, target["integrity"])
                        self.assertEqual(integrity_before,
                                         runner.legacy.players[target_sid]["integrity"])
                        self.assertEqual(ammo_before, runner.legacy.cannon_ammo[sid]["cannon"])

    def test_ping_cannot_supply_contact_to_same_action_fire(self) -> None:
        """Le ping seul ne permet aucun tir avant le premier tick de propagation."""
        runner = self.runner
        sid = runner.spawn_bot(
            boat_type="destroyer", external_control=True,
            position=(100.0, 100.0), rotation=math.pi, team_id="destroyer")
        target_sid = runner.spawn_bot(
            external_control=True, position=(105.0, 100.0), rotation=0.0,
            team_id="submarine")
        bot = runner.legacy.bots[sid]
        bot["rl_control_version"] = DESTROYER_OBSERVATION_VERSION
        for entity in (runner.legacy.bots[target_sid], runner.legacy.players[target_sid]):
            entity["position"]["y"] = -2.0 / UNIT_METERS_BOT
        self.assertEqual(0.0, build_observation(bot, runner.sim, runner.world)[18])
        self.assertNotIn("rl_contact", bot)
        ammo_before = runner.legacy.cannon_ammo[sid]["cannon"]
        without_ping = apply_action(bot, runner.sim, [2, 1, 3, 0, 0, 0])
        self.assertFalse(without_ping["weapon_fired"])
        self.assertTrue(without_ping["weapon_invalid"])
        self.assertEqual(ammo_before, runner.legacy.cannon_ammo[sid]["cannon"])
        now = runner.sim.now()
        with_ping = apply_action(bot, runner.sim, [2, 1, 3, 0, 1, 0])
        self.assertTrue(with_ping["sonar_pinged"])
        self.assertFalse(with_ping["weapon_fired"])
        self.assertTrue(with_ping["weapon_invalid"])
        self.assertEqual(ammo_before, runner.legacy.cannon_ammo[sid]["cannon"])
        self.assertNotIn("rl_contact", bot)
        self.assertEqual(now, runner.sim.now())
        runner.step(0.05)
        self.assertEqual(1.0, build_observation(bot, runner.sim, runner.world)[18])
        self.assertTrue(apply_action(bot, runner.sim, [2, 1, 3, 0, 0, 0])["weapon_fired"])


if __name__ == "__main__":
    unittest.main()
