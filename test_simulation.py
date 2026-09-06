import math
import unittest
from types import SimpleNamespace

from events import LureDestroyed
from simulation import Sim


class AcousticTorpedoConeTest(unittest.TestCase):
    def setUp(self):
        self.sim = Sim({})
        self.sim._legacy = SimpleNamespace(
            line_of_sight_clear=lambda *args: True,
            count_thermoclines_crossed=lambda *args: 0,
            point_in_polygon=lambda *args: False,
            _ensure_island_bounds=lambda *args: [],
            closest_approach_on_segment=lambda *args: None,
            segments_intersect=lambda *args: False,
            distance_point_segment=lambda *args: float("inf"),
        )
        self.torpedo = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "dirX": 1.0,
            "dirZ": 0.0,
            "minNoise": 2.7,
            "radarHalfAngle": math.radians(60.0 * 0.5),
        }

    @staticmethod
    def player(player_id, angle_deg, noise=10.0):
        angle = math.radians(angle_deg)
        return {
            "id": player_id,
            "boat": {"noise": noise, "minNoise": 1.0, "speedNoiseLimit": 0.2},
            "speedRatio": 1.0,
            "position": {
                "x": math.cos(angle) * 100.0,
                "y": 0.0,
                "z": math.sin(angle) * 100.0,
            },
        }

    def test_selects_boat_inside_cone_over_louder_boat_outside(self):
        self.sim.players = {
            "inside": self.player("inside", 29.0),
            "outside": self.player("outside", 31.0, noise=100.0),
        }

        pick = self.sim._pick_acoustic(self.torpedo)

        self.assertEqual("boat:inside", pick["key"])

    def test_does_not_select_boat_behind_torpedo(self):
        self.sim.players = {"behind": self.player("behind", 180.0, noise=100.0)}

        pick = self.sim._pick_acoustic(self.torpedo)

        self.assertIsNone(pick["key"])

    def test_does_not_select_lure_outside_cone(self):
        angle = math.radians(31.0)
        self.sim.lures = {
            ("owner", 1): {
                "ownerId": "owner",
                "lid": 1,
                "x": math.cos(angle) * 100.0,
                "y": 0.0,
                "z": math.sin(angle) * 100.0,
                "noise": 100.0,
                "expiresAt": self.sim.t + 10.0,
            }
        }

        pick = self.sim._pick_acoustic(self.torpedo)

        self.assertIsNone(pick["key"])

    def test_expired_lure_is_purged_without_active_torpedo(self):
        self.sim.lures = {
            ("owner", 1): {
                "ownerId": "owner",
                "lid": 1,
                "expiresAt": self.sim.now() - 1.0,
            }
        }

        self.sim.update_server_torpedoes(0.05, {})

        self.assertEqual({}, self.sim.lures)
        events = self.sim.drain_events()
        self.assertEqual(1, len(events))
        self.assertIsInstance(events[0], LureDestroyed)


if __name__ == "__main__":
    unittest.main()
