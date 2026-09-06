"""Helpers géométriques purs (sans dépendance Flask/socketio).

Réutilisable par server.py (binding via legacy hooks).
"""

from typing import Any, Dict, List, Optional, Tuple


# Cache module-level invalidé par id(world_data).
_island_bounds_cache: Dict[str, Any] = {"world_id": None, "bounds": []}


def point_in_polygon(x: float, z: float, points: List[Dict[str, float]]) -> bool:
    n = len(points)
    inside = False
    j = n - 1
    for i in range(n):
        xi, zi = points[i]["x"], points[i]["z"]
        xj, zj = points[j]["x"], points[j]["z"]
        if ((zi > z) != (zj > z)) and (x < (xj - xi) * (z - zi) / (zj - zi) + xi):
            inside = not inside
        j = i
    return inside


def ensure_island_bounds(world_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if _island_bounds_cache["world_id"] is id(world_data) and _island_bounds_cache["bounds"]:
        return _island_bounds_cache["bounds"]
    bounds = []
    for island in world_data.get("islands", []):
        pts = island["points"]
        if not pts:
            continue
        xs = [p["x"] for p in pts]
        zs = [p["z"] for p in pts]
        bounds.append({
            "minX": min(xs), "maxX": max(xs),
            "minZ": min(zs), "maxZ": max(zs),
            "points": pts,
        })
    _island_bounds_cache["world_id"] = id(world_data)
    _island_bounds_cache["bounds"] = bounds
    return bounds


def point_on_any_island(x: float, z: float, world_data: Dict[str, Any]) -> bool:
    for b in ensure_island_bounds(world_data):
        if x < b["minX"] or x > b["maxX"] or z < b["minZ"] or z > b["maxZ"]:
            continue
        if point_in_polygon(x, z, b["points"]):
            return True
    return False


def line_of_sight_clear(x1: float, z1: float, x2: float, z2: float,
                        world_data: Dict[str, Any]) -> bool:
    """Vrai si le segment ne traverse aucune île. Échantillonnage 5 u (50 m)."""
    bounds_list = ensure_island_bounds(world_data)
    if not bounds_list:
        return True
    dx = x2 - x1
    dz = z2 - z1
    seg_min_x = x1 if dx >= 0 else x2
    seg_max_x = x2 if dx >= 0 else x1
    seg_min_z = z1 if dz >= 0 else z2
    seg_max_z = z2 if dz >= 0 else z1
    candidates = []
    for b in bounds_list:
        if b["maxX"] < seg_min_x or b["minX"] > seg_max_x:
            continue
        if b["maxZ"] < seg_min_z or b["minZ"] > seg_max_z:
            continue
        candidates.append(b)
    if not candidates:
        return True
    length = (dx * dx + dz * dz) ** 0.5
    steps = max(2, int(length / 5))
    for i in range(1, steps):
        t = i / steps
        x = x1 + dx * t
        z = z1 + dz * t
        for b in candidates:
            if x < b["minX"] or x > b["maxX"] or z < b["minZ"] or z > b["maxZ"]:
                continue
            if point_in_polygon(x, z, b["points"]):
                return False
    return True


def count_thermoclines_crossed(x1: float, y1: float, z1: float,
                               x2: float, y2: float, z2: float,
                               world_data: Dict[str, Any],
                               unit_meters: float = 10.0) -> int:
    """Nombre de thermoclines traversées par le segment 3D (émetteur→récepteur).

    Une thermocline est un plan horizontal à la profondeur y_thermo = -depthMeters
    / unit_meters, délimité par un polygone XZ. Le segment la traverse si y1 et y2
    encadrent y_thermo ET que le point d'intersection (à y_thermo) tombe dans le
    polygone. Sert à atténuer/bloquer le son qui franchit la couche."""
    thermos = world_data.get("thermoclines") or []
    if not thermos:
        return 0
    crossed = 0
    dy = y2 - y1
    for tc in thermos:
        pts = tc.get("points")
        if not pts or len(pts) < 3:
            continue
        y_t = -float(tc.get("depthMeters", 50)) / unit_meters
        # Les deux extrémités doivent encadrer la profondeur de la thermocline.
        if (y1 - y_t) * (y2 - y_t) > 0:
            continue  # même côté → pas de croisement
        if abs(dy) < 1e-9:
            # Segment horizontal pile sur la couche : on considère traversé si dans le polygone.
            mx, mz = (x1 + x2) * 0.5, (z1 + z2) * 0.5
            if point_in_polygon(mx, mz, pts):
                crossed += 1
            continue
        t = (y_t - y1) / dy           # paramètre du point de croisement
        if t < 0.0 or t > 1.0:
            continue
        ix = x1 + (x2 - x1) * t
        iz = z1 + (z2 - z1) * t
        if point_in_polygon(ix, iz, pts):
            crossed += 1
    return crossed


def distance_point_segment(px, pz, ax, az, bx, bz) -> float:
    dx = bx - ax
    dz = bz - az
    len_sq = dx * dx + dz * dz
    if len_sq <= 0:
        return ((px - ax) ** 2 + (pz - az) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / len_sq))
    cx = ax + t * dx
    cz = az + t * dz
    return ((px - cx) ** 2 + (pz - cz) ** 2) ** 0.5


def closest_approach_on_segment(px, pz, ax, az, bx, bz) -> Tuple[float, float]:
    """(t_raw, dist_min). t_raw non-clampé ; dist clampée au segment."""
    dx = bx - ax
    dz = bz - az
    len_sq = dx * dx + dz * dz
    if len_sq <= 0:
        return 0.0, ((px - ax) ** 2 + (pz - az) ** 2) ** 0.5
    t_raw = ((px - ax) * dx + (pz - az) * dz) / len_sq
    t = max(0.0, min(1.0, t_raw))
    cx = ax + t * dx
    cz = az + t * dz
    return t_raw, ((px - cx) ** 2 + (pz - cz) ** 2) ** 0.5


def segments_intersect(ax, az, bx, bz, cx, cz, dx, dz) -> bool:
    def orient(x1, z1, x2, z2, x3, z3):
        return (x2 - x1) * (z3 - z1) - (z2 - z1) * (x3 - x1)
    o1 = orient(ax, az, bx, bz, cx, cz)
    o2 = orient(ax, az, bx, bz, dx, dz)
    o3 = orient(cx, cz, dx, dz, ax, az)
    o4 = orient(cx, cz, dx, dz, bx, bz)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def min_distance_to_islands(x: float, z: float, world_data: Dict[str, Any],
                            cap: Optional[float] = None) -> float:
    """Distance min point→arête d'île. `cap` : early-out si on trouve plus proche."""
    best = float("inf")
    for b in ensure_island_bounds(world_data):
        bx = max(b["minX"] - x, 0, x - b["maxX"])
        bz = max(b["minZ"] - z, 0, z - b["maxZ"])
        aabb_dist = (bx * bx + bz * bz) ** 0.5
        if aabb_dist >= best:
            continue
        pts = b["points"]
        n = len(pts)
        for i in range(n):
            ax = pts[i]["x"]
            az = pts[i]["z"]
            bx2 = pts[(i + 1) % n]["x"]
            bz2 = pts[(i + 1) % n]["z"]
            d = distance_point_segment(x, z, ax, az, bx2, bz2)
            if d < best:
                best = d
                if cap is not None and best < cap:
                    return best
    return best
