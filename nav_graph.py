"""Précalcul du graphe de navigation des bots.

Pour chaque île d'une carte, on calcule l'enveloppe convexe de ses points et on
la "gonfle" d'une marge de sécurité — ces sommets gonflés deviennent les nœuds
du graphe. Une arête relie deux nœuds si le segment entre eux ne traverse
aucune île de la carte.

Le graphe est stocké directement dans le JSON de la carte sous la clé
`nav_graph` :

    {
        "margin_m": 100,
        "nodes": [{"x": ..., "z": ...}, ...],
        "edges": [[i, j], ...],
        "island_nodes": [[node_idx, ...], ...]   # un sous-tableau par île
    }

Appelé par les handlers admin_save_map / admin_create_map / admin_copy_map du
serveur avant écriture du fichier. Aucun coût runtime côté bot.
"""

from typing import Dict, List, Any
import math

from geometry import line_of_sight_clear


def _convex_hull(points: List[Dict[str, float]]) -> List[Dict[str, float]]:
    """Andrew's monotone chain. Renvoie l'enveloppe convexe en ordre horaire,
    sans répéter le premier point."""
    pts = sorted({(p["x"], p["z"]) for p in points})
    if len(pts) < 3:
        return [{"x": x, "z": z} for x, z in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return [{"x": x, "z": z} for x, z in hull]


def _inflate_hull(hull: List[Dict[str, float]], margin: float) -> List[Dict[str, float]]:
    """Pousse chaque sommet de l'enveloppe vers l'extérieur, le long de la
    bissectrice des deux arêtes adjacentes. Le polygone reste convexe."""
    n = len(hull)
    if n == 0:
        return []
    if n == 1:
        x, z = hull[0]["x"], hull[0]["z"]
        return [
            {"x": x + margin, "z": z},
            {"x": x, "z": z + margin},
            {"x": x - margin, "z": z},
            {"x": x, "z": z - margin},
        ]
    out = []
    for i in range(n):
        prev_p = hull[(i - 1) % n]
        cur = hull[i]
        next_p = hull[(i + 1) % n]
        # Normales sortantes des deux arêtes adjacentes (à droite de la direction
        # de parcours horaire = vers l'extérieur du polygone convexe).
        e1x = cur["x"] - prev_p["x"]
        e1z = cur["z"] - prev_p["z"]
        e2x = next_p["x"] - cur["x"]
        e2z = next_p["z"] - cur["z"]
        # Normale extérieure d'une arête horaire (dx, dz) = (dz, -dx).
        n1x, n1z = e1z, -e1x
        n2x, n2z = e2z, -e2x
        m1 = math.hypot(n1x, n1z) or 1.0
        m2 = math.hypot(n2x, n2z) or 1.0
        n1x /= m1; n1z /= m1
        n2x /= m2; n2z /= m2
        bx = n1x + n2x
        bz = n1z + n2z
        bm = math.hypot(bx, bz)
        if bm < 1e-9:
            bx, bz = n1x, n1z
            bm = 1.0
        # Compense l'angle aigu pour rester à `margin` des deux arêtes.
        cos_half = max(0.1, (n1x * bx + n1z * bz) / bm)
        scale = margin / cos_half
        out.append({
            "x": cur["x"] + (bx / bm) * scale,
            "z": cur["z"] + (bz / bm) * scale,
        })
    return out


def build_nav_graph(world_data: Dict[str, Any], margin_m: float = 150.0,
                    unit_meters: float = 10.0) -> Dict[str, Any]:
    """Construit le graphe de navigation pour `world_data`. La marge est
    exprimée en mètres ; les coordonnées des îles sont en unités Babylon
    (1 u = unit_meters).
    Post-traitement : élimine les nœuds qui tombent sur une autre île et les
    arêtes dont le segment traverse une île."""
    from geometry import point_on_any_island, line_of_sight_clear

    margin_u = margin_m / unit_meters
    nodes: List[Dict[str, float]] = []
    island_nodes: List[List[int]] = []
    for island in world_data.get("islands", []):
        pts = island.get("points") or []
        if not pts:
            island_nodes.append([])
            continue
        hull = _convex_hull(pts)
        inflated = _inflate_hull(hull, margin_u)
        idx = []
        for p in inflated:
            if not point_on_any_island(p["x"], p["z"], world_data):
                idx.append(len(nodes))
                nodes.append(p)
        island_nodes.append(idx)

    # Arêtes : sommets adjacents du périmètre, mais uniquement si le segment
    # ne traverse aucune île (cas de deux îles très proches).
    edges: List[List[int]] = []
    for idxs in island_nodes:
        m = len(idxs)
        if m < 2:
            continue
        for k in range(m):
            a = idxs[k]
            b = idxs[(k + 1) % m]
            if line_of_sight_clear(nodes[a]["x"], nodes[a]["z"],
                                   nodes[b]["x"], nodes[b]["z"], world_data):
                edges.append([a, b])

    # Élaguer les culs-de-sac (nœuds à ≤ 1 arête) itérativement.
    # En retirant un cul-de-sac, son voisin peut en devenir un.
    for _ in range(50):
        degree: Dict[int, int] = {}
        for a, b in edges:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        dead_ends = {i for i in degree if degree[i] <= 1}
        if not dead_ends:
            break
        new_edges = [[a, b] for a, b in edges
                     if a not in dead_ends and b not in dead_ends]
        if len(new_edges) == len(edges):
            break
        edges = new_edges

    # Reconstruire island_nodes sans les nœuds élagués.
    surviving = set()
    for a, b in edges:
        surviving.add(a)
        surviving.add(b)
    island_nodes = [[ni for ni in idxs if ni in surviving] for idxs in island_nodes]

    return {
        "margin_m": margin_m,
        "nodes": nodes,
        "edges": edges,
        "island_nodes": island_nodes,
    }


def adjacency(nav_graph: Dict[str, Any]) -> Dict[int, List[int]]:
    """Renvoie un dict {node_idx: [voisins]} à partir du graphe stocké."""
    adj: Dict[int, List[int]] = {i: [] for i in range(len(nav_graph.get("nodes") or []))}
    for a, b in nav_graph.get("edges") or []:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj
