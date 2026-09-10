"""Diagnostics locaux de la premiere trace ; ni politique ni replay reseau."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any
import unittest

import geometry
import simulation
from rl.headless import BASE_DIR, HeadlessRunner, load_world
from rl.rl_control import _torpedo_observation, apply_action


# Snapshot conserve meme si le journal tourne ; commandes d'armes non enregistrees.
SESSION = "e4f954245d2f4286885ecbc4a2b60bcc"
POSITION = (-276.1323294357245, -586.9339318198893)
SNAPSHOT = {
    "rotation": 2.1367188922448874,
    "speed": 0.0,
    "rudder": -0.08395879268646246,
    "control_target_rudder": 0.0,
    "control_target_speed_ratio": 0.65,
    "control_target_depth_y": -20.25,
}


def movement_experiment(phases: list[tuple[float, list[int]]]) -> dict[str, Any]:
    """Isole la locomotion du snapshot epoch=2/seq=19638, sans autres acteurs."""
    runner = HeadlessRunner("world", seed=0)
    sid = runner.spawn_bot(external_control=True, position=POSITION,
                           rotation=SNAPSHOT["rotation"])
    bot = runner.sim.bots[sid]
    bot.update(SNAPSHOT)
    bot["position"]["y"] = -20.25
    runner.sim.players[sid].update({
        "position": dict(bot["position"]), "rotation": bot["rotation"],
        "speed": bot["speed"], "rudder": bot["rudder"],
    })
    results = []
    for seconds, action in phases:
        ticks = round(seconds / 0.05)
        if ticks <= 0 or not math.isclose(ticks * 0.05, seconds):
            raise ValueError("duree positive multiple de 0.05 s requise")
        start = dict(bot["position"])
        blocked_ticks = 0
        for tick in range(ticks):
            if tick % 5 == 0:
                apply_action(bot, runner.sim, action)
            previous = dict(bot["position"])
            runner.step(0.05)
            pos = bot["position"]
            if (geometry.point_on_any_island(pos["x"], pos["z"], runner.world)
                    or not geometry.line_of_sight_clear(
                        previous["x"], previous["z"], pos["x"], pos["z"], runner.world)):
                raise AssertionError("trajet sur une ile ou a travers une ile")
            half_w = runner.world["ground"]["width"] / 2 - 4
            half_d = runner.world["ground"]["depth"] / 2 - 4
            if not (-half_w <= pos["x"] <= half_w and -half_d <= pos["z"] <= half_d):
                raise AssertionError("trajet hors carte")
            blocked_ticks += bot["speed"] == 0 and action[1] != 1
        results.append({
            "seconds": seconds, "action": action, "position": dict(bot["position"]),
            "rotation": bot["rotation"], "speed": bot["speed"],
            "displacement_m": math.hypot(bot["position"]["x"] - start["x"],
                                         bot["position"]["z"] - start["z"]) * 10,
            "blocked_ticks": blocked_ticks,
        })
    return {"phases": results, "all_segments_ocean": True}


def threat_experiment() -> dict[str, Any]:
    """Fixture synthetique : cible immobile, torpilles visibles sans verrou prive."""
    runner = HeadlessRunner("world", seed=0)
    runner.world["islands"] = []
    runner.world["thermoclines"] = []
    sid = runner.spawn_bot(external_control=True, position=(0.0, 0.0), rotation=0.0)
    bot = runner.sim.bots[sid]
    bot["position"]["y"] = -3.0
    receding = {"ownerPlayerId": "other", "x": 10.0, "z": 0.0, "y": -3.0,
                "dirX": 1.0, "dirZ": 0.0, "speed": 2.0}
    incoming = {**receding, "x": -10.0}
    runner.sim.torpedoes.update({"receding": receding, "incoming": incoming})
    metrics = {key: simulation.torpedo_radar_threat(bot, value, runner.world)
               for key, value in runner.sim.torpedoes.items()}
    observation = _torpedo_observation(bot, runner.sim, runner.world)
    runner.sim.torpedoes.pop("receding")
    desired = _torpedo_observation(bot, runner.sim, runner.world)
    return {"metrics_distance_cpa_eta": metrics, "actual_observation": observation,
            "desired_incoming_observation": desired}


class LiveTraceDiagnosticsTest(unittest.TestCase):
    def test_recorded_forward_stays_blocked_in_ocean(self) -> None:
        result = movement_experiment([(30.0, [2, 3, 3, 0, 0])])
        phase = result["phases"][0]
        self.assertEqual(phase["blocked_ticks"], 600)
        self.assertEqual(phase["displacement_m"], 0.0)

    def test_bounded_reverse_turn_then_forward_clears_recorded_stall(self) -> None:
        for rudder in (0, 4):
            with self.subTest(rudder=rudder):
                result = movement_experiment([
                    (15.0, [rudder, 0, 3, 0, 0]), (30.0, [2, 3, 3, 0, 0])])
                reverse, forward = result["phases"]
                self.assertEqual(reverse["blocked_ticks"], 0)
                self.assertLess(reverse["speed"], 0.0)
                self.assertEqual(forward["blocked_ticks"], 0)
                self.assertAlmostEqual(forward["speed"], 0.65 * 1.28611)
                self.assertGreater(forward["displacement_m"], 200.0)

    def test_synthetic_threat_candidates_are_visible(self) -> None:
        result = threat_experiment()
        for metrics in result["metrics_distance_cpa_eta"].values():
            self.assertIsNotNone(metrics)
        self.assertEqual(result["desired_incoming_observation"],
                         (1.0, 0.05, 0.0, 0.5, 0.0, 0.0, 0.05))

    def test_incoming_outranks_receding(self) -> None:
        result = threat_experiment()
        self.assertEqual(result["actual_observation"], result["desired_incoming_observation"])

    def test_multiple_passed_candidates_and_near_incoming(self) -> None:
        runner = HeadlessRunner("world", seed=0)
        runner.world.update(islands=[], thermoclines=[])
        sid = runner.spawn_bot(external_control=True, position=(0, 0), rotation=0)
        bot = runner.sim.bots[sid]
        base = dict(ownerPlayerId="other", y=bot["position"]["y"], z=0,
                    dirX=1, dirZ=0, speed=2)
        for tid, x in enumerate((1, 5, 20, -10, -0.2)):
            runner.sim.torpedoes[tid] = dict(base, tid=tid, x=x)
        threats = runner.sim.bot_torpedoes_threat(bot)
        self.assertEqual([t["tid"] for t in threats], [4, 3, 0, 1, 2])
        self.assertAlmostEqual(_torpedo_observation(bot, runner.sim, runner.world)[3], 0.01)
        # Sans arrivante, ne pas effacer les risques de proximite (dont les leurres).
        del runner.sim.torpedoes[4]
        del runner.sim.torpedoes[3]
        self.assertEqual([t["tid"] for t in runner.sim.bot_torpedoes_threat(bot)], [0, 1, 2])
        obs = _torpedo_observation(bot, runner.sim, runner.world)
        self.assertEqual((obs[0], obs[3], obs[6]), (1, 0, 0.005))
        runner.sim.torpedoes.clear()
        self.assertEqual(_torpedo_observation(bot, runner.sim, runner.world), (0,) * 7)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, help="journal optionnel, session epinglee uniquement")
    args = parser.parse_args()
    if args.trace:
        matches = []
        with args.trace.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                fields = record.get("data", {}).get("fields", {})
                position = fields.get("position", {})
                if (record.get("session") == SESSION and record.get("epoch") == 2
                        and fields.get("id") == "bot002"
                        and position.get("x") == POSITION[0] and position.get("z") == POSITION[1]):
                    matches.append(record)
        if not matches:
            raise SystemExit("snapshot absent de la session epinglee ; aucune substitution")
        pinned = next((row for row in matches if row["seq"] == 19638), None)
        if (pinned is None or any(pinned["data"]["fields"].get(key) != value
                                  for key, value in SNAPSHOT.items())
                or pinned["data"]["fields"]["position"]["y"] != -20.25):
            raise SystemExit("snapshot epingle absent ou different de la fixture")
        print(json.dumps({"trace_count": len(matches), "first": matches[0], "last": matches[-1]}))
    print(json.dumps({"world_canonical_sha256": hashlib.sha256(json.dumps(
                          load_world("world"), sort_keys=True, allow_nan=False).encode()).hexdigest(),
                      "map_sha256": hashlib.sha256((BASE_DIR / "maps/world.json").read_bytes()).hexdigest(),
                      "boat_sha256": hashlib.sha256((BASE_DIR / "boats/submarine.json").read_bytes()).hexdigest()}))
    print(json.dumps({"forward": movement_experiment([(30.0, [2, 3, 3, 0, 0])])}))
    for rudder in (0, 4):
        for seconds in (2.0, 5.0, 10.0, 15.0, 20.0):
            print(json.dumps({"reverse_turn": movement_experiment([
                (seconds, [rudder, 0, 3, 0, 0]), (30.0, [2, 3, 3, 0, 0])])}))
    print(json.dumps({"synthetic_threat": threat_experiment()}))
