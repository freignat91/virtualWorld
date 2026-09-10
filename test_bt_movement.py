"""Collisions BT sur le mouvement commande, sans navigation de secours ajoutee."""

import copy
import math
import unittest

import bot_ai
import geometry


class BtMovementTest(unittest.TestCase):
    def setUp(self) -> None:
        self.world = {"ground": {"width": 100, "depth": 100}, "islands": []}
        self.bot = {"id": "bt", "boatType": "destroyer", "boat": {},
                    "position": {"x": 0.0, "y": -0.2, "z": 0.0},
                    "rotation": 0.0, "speed": 2.0, "max_speed_us": 2.0,
                    "rudder": 0.0, "rudder_max": 0.36, "rudder_speed": 0.3,
                    "throttle_accel": 0.4}
        self.ctx = {"world": self.world, "dt": 1.0, "now": 1.0,
                    "deps": {"UNIT_METERS_BOT": 10,
                             "point_on_any_island": geometry.point_on_any_island}}

    def drive(self, x: float = -40, z: float = 0) -> None:
        self.assertEqual(bot_ai.Status.SUCCESS, bot_ai._drive_to_waypoint(
            self.bot, self.ctx, {"x": x, "z": z}, {"full_speed": True}))

    def test_free_motion_keeps_throttle_rudder_rotation_and_dt(self) -> None:
        self.bot["speed"] = 1.0
        self.ctx["dt"] = 0.25
        self.drive(0, 40)
        self.assertAlmostEqual(0.075, self.bot["rudder"])
        self.assertAlmostEqual(0.9, self.bot["speed"])
        rotation = 0.075 * 0.9 * 0.25
        self.assertAlmostEqual(rotation, self.bot["rotation"])
        self.assertAlmostEqual(-math.cos(rotation) * 0.9 * 0.25, self.bot["position"]["x"])
        self.assertAlmostEqual(math.sin(rotation) * 0.9 * 0.25, self.bot["position"]["z"])
        self.assertEqual(-0.2, self.bot["position"]["y"])

    def test_thin_crossing_inside_endpoint_and_edge_stop_without_teleport(self) -> None:
        for left, right, low in ((-1.01, -1, -1), (-3, -1, -1), (-3, -2, -1),
                                 (-1.01, -1, 0)):
            with self.subTest(island=(left, right, low)):
                self.setUp()
                self.world["islands"] = [{"points": [{"x": x, "z": z} for x, z in
                    ((left, low), (right, low), (right, 1), (left, 1))]}]
                before = copy.deepcopy(self.bot["position"])
                self.drive()
                self.assertEqual(before, self.bot["position"])
                self.assertEqual(0.0, self.bot["speed"])
                self.assertEqual(2, self.bot["bb"]["_stuck_ticks"])

    def test_world_edges_allow_equality_but_block_crossing(self) -> None:
        for rotation in (0, math.pi / 2, math.pi, -math.pi / 2):
            for start, blocked in ((44, False), (44.01, True)):
                with self.subTest(rotation=rotation, start=start):
                    self.setUp()
                    dx, dz = -math.cos(rotation), math.sin(rotation)
                    self.bot["rotation"] = rotation
                    self.bot["position"].update(x=dx * start, z=dz * start)
                    before = copy.deepcopy(self.bot["position"])
                    self.drive(dx * 100, dz * 100)
                    if blocked:
                        self.assertEqual(before, self.bot["position"])
                        self.assertEqual(0, self.bot["speed"])
                    else:
                        self.assertAlmostEqual(dx * 46, self.bot["position"]["x"])
                        self.assertAlmostEqual(dz * 46, self.bot["position"]["z"])

    def test_zero_dt_does_not_move_or_teleport_to_waypoint(self) -> None:
        self.ctx["dt"] = 0
        before = copy.deepcopy(self.bot)
        self.drive(20, 30)
        for key in ("position", "rotation", "speed", "rudder"):
            self.assertEqual(before[key], self.bot[key])

    def test_existing_stuck_waypoint_recovery_is_preserved(self) -> None:
        self.bot["position"]["x"] = -45
        self.bot["bb"] = {"_stuck_ticks": 100, "nav_node": 3}
        self.drive()
        self.assertEqual(-45, self.bot["position"]["x"])
        self.assertIsNone(self.bot["waypoint"])
        self.assertIn(3, self.bot["bb"]["nav_banned_nodes"])

    def test_existing_island_redirect_selects_waypoint_but_cannot_escape_by_crossing(self) -> None:
        self.world["islands"] = [{"points": [{"x": x, "z": z} for x, z in
            ((-1, -1), (1, -1), (1, 1), (-1, 1))]}]
        self.world["nav_graph"] = {"nodes": [{"x": -5, "z": 0}]}
        before = copy.deepcopy(self.bot["position"])
        self.drive(40, 0)
        self.assertEqual(0, self.bot["bb"]["nav_node"])
        self.assertEqual({"x": -5, "z": 0, "_node_idx": 0}, self.bot["waypoint"])
        self.assertEqual(before, self.bot["position"])
        self.assertEqual(0, self.bot["speed"])


if __name__ == "__main__":
    unittest.main()
