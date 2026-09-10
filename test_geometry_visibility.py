"""Occlusion fermee Python/JS : fixtures communes et regressions sans reseau."""

import itertools
import json
from pathlib import Path
import shutil
import subprocess
import unittest

import geometry
import simulation


ROOT = Path(__file__).resolve().parent
FIXTURES = json.loads((ROOT / "tests/geometry_visibility.json").read_text())


class GeometryVisibilityTest(unittest.TestCase):
    def test_shared_visibility_and_torpedo_cases(self) -> None:
        for case in FIXTURES["cases"]:
            for reverse, winding, closed in itertools.product((False, True), repeat=3):
                with self.subTest(case=case["name"], reverse=reverse, winding=winding, closed=closed):
                    islands = []
                    for name in case["islands"]:
                        points = [{"x": x, "z": z} for x, z in FIXTURES["polygons"][name]]
                        if winding:
                            points.reverse()
                        if closed and points:
                            points.append(dict(points[0]))
                        islands.append({"points": points})
                    world = {"islands": islands}
                    segment = case["segment"]
                    if reverse:
                        segment = segment[2:] + segment[:2]
                    self.assertEqual(case["clear"], geometry.line_of_sight_clear(*segment, world))
                    self.assertEqual(not case["clear"], simulation.torpedo_segment_blocked(
                        *segment, world, point_in_polygon=geometry.point_in_polygon,
                        ensure_island_bounds=geometry.ensure_island_bounds))

    def test_closed_segments_and_unchanged_hit_contract(self) -> None:
        cases = [
            ((0, 0, 2, 2, 0, 2, 2, 0), True),
            ((0, 0, 2, 0, 1, 0, 3, 0), True),
            ((0, 0, 2, 0, 3, 0, 4, 0), False),
            ((0, 0, 2, 0, 2, 0, 2, 2), True),
            ((1, 0, 1, 0, 0, 0, 2, 0), True),
            ((1, 1, 1, 1, 0, 0, 2, 0), False),
            ((1, 1, 1, 1, 1, 1, 1, 1), True),
            ((1, 1, 1, 1, 2, 2, 2, 2), False),
        ]
        for coords, expected in cases:
            a, b, c, d = [coords[i:i + 2] for i in range(0, 8, 2)]
            for p, q in ((a, b), (b, a)):
                for r, s in ((c, d), (d, c)):
                    for values in (p + q + r + s, r + s + p + q):
                        with self.subTest(values=values):
                            self.assertEqual(expected, geometry.segments_intersect(
                                *values, include_boundary=True))
        self.assertFalse(geometry.segments_intersect(0, 0, 2, 0, 1, 0, 3, 0))
        self.assertTrue(geometry.segments_intersect(0, 0, 2, 2, 0, 2, 2, 0))

    def test_torpedo_avoidance_uses_exact_occlusion(self) -> None:
        world = {"islands": [{"points": [
            {"x": x, "z": z} for x, z in FIXTURES["polygons"]["thin"]]}]}
        torpedo = {"x": 0.0, "z": 0.0, "dirX": 1.0, "dirZ": 0.0}
        direction = simulation.torpedo_avoid_island(
            torpedo, 1.0, 0.0, 10.0, world,
            point_in_polygon=geometry.point_in_polygon,
            ensure_island_bounds=geometry.ensure_island_bounds)
        self.assertNotEqual((1.0, 0.0), direction)
        self.assertTrue(geometry.line_of_sight_clear(
            0.0, 0.0, direction[0] * 10.0, direction[1] * 10.0, world))

    @unittest.skipUnless(shutil.which("node"), "Node.js indisponible")
    def test_javascript_shared_fixtures(self) -> None:
        result = subprocess.run(
            [shutil.which("node"), str(ROOT / "tests/test_geometry_visibility.js")],
            capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
