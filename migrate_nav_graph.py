"""Script one-shot : recalcule le graphe de navigation pour toutes les cartes
de maps/ et le sauvegarde dans le JSON. À lancer après l'introduction du
système nav_graph.

Usage (après `source .venv/bin/activate`) :
    python migrate_nav_graph.py
"""

import argparse
import json
import os
import sys

import nav_graph

MAPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps")
UNIT_METERS = 10.0


def main():
    argparse.ArgumentParser(
        description="Recalcule le nav_graph pour toutes les cartes maps/*.json "
                    "et sauvegarde in-place. À lancer après modification du "
                    "système nav_graph ou ajout/retrait d'îles.",
        epilog="Usage : python migrate_nav_graph.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    ).parse_args()
    if not os.path.isdir(MAPS_DIR):
        print(f"Pas de dossier {MAPS_DIR}")
        return 1
    for fname in sorted(os.listdir(MAPS_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(MAPS_DIR, fname)
        with open(path) as f:
            world = json.load(f)
        n_islands = len(world.get("islands") or [])
        ng = nav_graph.build_nav_graph(world, unit_meters=UNIT_METERS)
        world["nav_graph"] = ng
        with open(path, "w") as f:
            json.dump(world, f, indent=2)
        print(f"  {fname}: {n_islands} îles → {len(ng['nodes'])} nœuds, {len(ng['edges'])} arêtes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
