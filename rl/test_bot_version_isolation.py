"""Garanties d'etancheite des runtimes de bots promus."""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
import unittest

from rl import rl_runtime


ROOT = Path(__file__).resolve().parent
VERSIONS = {
    "v15": ROOT / "bot_versions/v15",
    "v16": ROOT / "bot_versions/v16",
    "v17": ROOT / "bot_versions/v17",
}


class BotVersionIsolationTest(unittest.TestCase):
    def test_runtime_files_match_their_immutable_manifests(self) -> None:
        for version, directory in VERSIONS.items():
            manifest = json.loads(
                (directory / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(version, manifest["runtimeVersion"])
            self.assertIs(True, manifest["immutable"])
            for filename, expected in manifest["files"].items():
                with self.subTest(version=version, filename=filename):
                    digest = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
                    self.assertEqual(expected, digest)

    def test_versions_never_import_mutable_bot_runtime_modules(self) -> None:
        forbidden = {
            "geometry", "nav_graph", "rl.masked_recurrent_policy",
            "rl.navigable_path", "rl.rl_control", "rl.rl_runtime", "rl.waypoints",
        }
        for version, directory in VERSIONS.items():
            for path in directory.glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imports = {
                    node.module for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.level == 0
                }
                imports.update(
                    alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names)
                self.assertFalse(
                    imports & forbidden,
                    f"imports partages dans {version}/{path.name}")

    def test_aliases_dispatch_only_to_their_runtime(self) -> None:
        from rl.bot_versions.v15 import runtime as runtime_v15
        from rl.bot_versions.v16 import runtime as runtime_v16
        from rl.bot_versions.v17 import runtime as runtime_v17

        cases = {
            "rl_aisub_mobility_runtime_v15": runtime_v15,
            "rl_aidest_mobility_runtime_v15": runtime_v15,
            "rl_aisub_mobility_runtime_v16": runtime_v16,
            "rl_aidest_mobility_runtime_v16": runtime_v16,
            "rl_aisub_mobility_runtime_v16:source_v15": runtime_v16,
            "rl_aidest_mobility_runtime_v16:source_v15": runtime_v16,
            "rl_aisub_mobility_runtime_v17:source_v16": runtime_v17,
            "rl_aidest_mobility_runtime_v17:source_v16": runtime_v17,
            "rl_aisub_mobility_runtime_v17": runtime_v17,
            "rl_aidest_mobility_runtime_v17": runtime_v17,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertIs(expected, rl_runtime._runtime_for_ai(name))
        self.assertIsNone(rl_runtime._runtime_for_ai(
            "rl_aisub_mobility_runtime_v14_seed89542"))

    def test_v16_keeps_an_independent_radius_and_trace_profile(self) -> None:
        from rl.bot_versions.v15 import runtime as runtime_v15
        from rl.bot_versions.v15 import waypoints as v15
        from rl.bot_versions.v16 import runtime as runtime_v16
        from rl.bot_versions.v16 import waypoints as v16

        self.assertEqual(200.0, v15.WAYPOINT_FINAL_REACHED_RADIUS_M)
        self.assertEqual(500.0, v16.WAYPOINT_FINAL_REACHED_RADIUS_M)
        self.assertEqual(
            v15.WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M,
            v16.WAYPOINT_INTERMEDIATE_REACHED_RADIUS_M)
        self.assertFalse(hasattr(runtime_v15.RuntimeController, "route_trace"))
        self.assertTrue(hasattr(runtime_v16.RuntimeController, "route_trace"))

    def test_v16_long_route_prefers_a_safe_aligned_waypoint(self) -> None:
        from rl.bot_versions.v15 import navigable_path as v15
        from rl.bot_versions.v16 import geometry as v16_geometry
        from rl.bot_versions.v16 import navigable_path as v16

        world = json.loads(
            (ROOT.parent / "maps/world.json").read_text(encoding="utf-8"))
        start = (-91.70283505719969, 595.7436711726803)
        goal = (872.2466960352422, 231.44104803493443)
        route = v16.plan_segmented_route(world, start, goal)

        self.assertEqual(2, len(route))
        waypoint = route[0]
        cross_product = ((waypoint[0] - start[0]) * (goal[1] - start[1])
                         - (waypoint[1] - start[1]) * (goal[0] - start[0]))
        self.assertAlmostEqual(0.0, cross_product, places=7)
        self.assertFalse(v16_geometry.point_on_any_island(*waypoint, world))
        self.assertGreater(
            v16_geometry.min_distance_to_islands(*waypoint, world) * 10.0,
            v16.ROUTE_CLEARANCE_M)
        self.assertLessEqual(
            math.hypot(waypoint[0] - start[0], waypoint[1] - start[1]) * 10.0,
            v16.ROUTE_LONG_SEGMENT_M)
        self.assertLessEqual(
            math.hypot(goal[0] - waypoint[0], goal[1] - waypoint[1]) * 10.0,
            v16.ROUTE_LONG_SEGMENT_M)
        self.assertNotEqual(route, v15.plan_segmented_route(world, start, goal))

    def test_v17_near_axis_route_is_short_and_bounds_every_segment(self) -> None:
        from rl.bot_versions.v16 import navigable_path as v16
        from rl.bot_versions.v17 import geometry as v17_geometry
        from rl.bot_versions.v17 import navigable_path as v17

        world = json.loads(
            (ROOT.parent / "maps/world.json").read_text(encoding="utf-8"))
        start = (-1285.3958972943403, 207.53590070694236)
        goal = (255.50660792951527, 877.7292576419212)
        v16_route = v16.plan_segmented_route(world, start, goal)
        route = v17.plan_segmented_route(world, start, goal)

        def legs(points):
            return [math.hypot(second[0] - first[0], second[1] - first[1]) * 10.0
                    for first, second in zip(points, points[1:])]

        v16_legs = legs((start, *v16_route))
        route_legs = legs((start, *route))
        direct_m = math.hypot(goal[0] - start[0], goal[1] - start[1]) * 10.0
        self.assertGreater(max(v16_legs), v16.ROUTE_LONG_SEGMENT_M)
        self.assertLessEqual(max(route_legs), v17.ROUTE_LONG_SEGMENT_M)
        self.assertLess(sum(route_legs), sum(v16_legs))
        self.assertLess(sum(route_legs), direct_m + 100.0)
        for waypoint in route[:-1]:
            self.assertFalse(v17_geometry.point_on_any_island(*waypoint, world))
            self.assertGreater(
                v17_geometry.min_distance_to_islands(*waypoint, world) * 10.0,
                v17.ROUTE_CLEARANCE_M)


if __name__ == "__main__":
    unittest.main()
