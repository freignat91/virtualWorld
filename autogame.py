"""Validation du scenario de demarrage, sans creation d'entites ni I/O reseau."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Iterable

from events import BoatSunk

import bot_ai
import geometry
import simulation


@dataclass
class PreparedAutogame:
    boats: List[Dict[str, Any]]
    end_condition: Optional[Dict[str, Any]]
    max_duration: Optional[float]
    start_delay: float = 0.0


class AutogameEnd:
    """Suit uniquement les naufrages natifs des identifiants publics initiaux."""

    def __init__(self, members: Dict[str, str], condition: Optional[Dict[str, Any]],
                 max_duration: Optional[float], clock: Callable[[], float]) -> None:
        self.members = dict(members)
        self.condition = condition
        self.max_duration = max_duration
        self.clock = clock
        self.started: Optional[float] = clock()
        self.sunk: set[str] = set()
        self.pending: set[str] = set()
        self.finished = False
        self.settling: Optional[Dict[str, Any]] = None

    def record(self, events: Iterable[Any]) -> None:
        if self.started is None:
            return
        for event in events:
            if isinstance(event, BoatSunk) and event.victim_id in self.members:
                self.pending.add(event.victim_id)

    def evaluate(self, torpedoes: Iterable[Dict[str, Any]] = ()) -> Optional[Dict[str, Any]]:
        if self.finished or self.started is None:
            return None
        elapsed = max(0.0, self.clock() - self.started)
        triggering = self.pending - self.sunk
        self.sunk.update(self.pending)
        self.pending.clear()
        teams = set(self.members.values())
        surviving = {team for pid, team in self.members.items() if pid not in self.sunk}
        eliminated = teams - surviving
        kind = self.condition["type"] if self.condition else None
        reached = (kind == "anyBoatSunk" and bool(self.sunk)
                   or kind == "anyTeamEliminated" and bool(eliminated)
                   or kind == "teamEliminated" and self.condition["teamId"] in eliminated)
        timeout = self.max_duration is not None and elapsed >= self.max_duration
        if not reached and not timeout:
            return None
        outstanding = []
        if reached and self.condition.get("waitForTorpedoes", False):
            outstanding = [dict(ownerPlayerId=t["ownerPlayerId"], tid=t["tid"])
                           for t in torpedoes if t["ownerPlayerId"] in self.sunk]
        if outstanding:
            if not timeout:
                if self.settling is None:
                    self.settling = dict(reason=kind, elapsedSeconds=elapsed,
                                         triggeringBoatIds=sorted(triggering),
                                         sunkBoatIds=sorted(self.sunk),
                                         outstandingTorpedoes=outstanding,
                                         outstandingTorpedoCount=len(outstanding),
                                         outstandingOwnerCount=len({t["ownerPlayerId"] for t in outstanding}))
                return None
            # La limite reste une borne, meme si la condition attend des torpilles.
            reached = False
        self.finished = True
        # Un timeout ou plusieurs equipes survivantes ne designe aucun vainqueur.
        winners = sorted(surviving) if reached and eliminated and len(surviving) == 1 else []
        return dict(reason=kind if reached else "timeout", elapsedSeconds=elapsed,
                    triggeringBoatIds=sorted(triggering), sunkBoatIds=sorted(self.sunk),
                    eliminatedTeamIds=sorted(eliminated), survivingTeamIds=sorted(surviving),
                    winningTeamIds=winners, draw=bool(reached and not surviving))


def prepare_autogame(path: Path, map_name: str, world: Dict[str, Any],
                     load_boat: Callable, max_bots: int = 32,
                     trace_enabled: bool = False) -> PreparedAutogame:
    """Valide tout avant spawn ; fichier absent ou IA invalide = erreur fatale."""
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or set(data) - {"map", "boats", "endCondition", "maxDurationSeconds", "startDelaySeconds"}:
        raise ValueError("autogame: objet attendu, champs inconnus interdits")
    if "map" in data and data["map"] != map_name:
        raise ValueError("autogame: map doit correspondre a --map")
    entries = data.get("boats")
    if not isinstance(entries, list) or len(entries) > max_bots:
        raise ValueError(f"autogame: boats doit etre une liste de 0 a {max_bots} bateaux")
    condition = data.get("endCondition")
    if "endCondition" in data:
        if not isinstance(condition, dict) or not isinstance(condition.get("type"), str):
            raise ValueError("autogame: endCondition exige un type")
        kind = condition["type"]
        keys = {"type", "teamId"} if kind == "teamEliminated" else {"type"}
        if (kind not in {"anyBoatSunk", "anyTeamEliminated", "teamEliminated"}
                or set(condition) - {"waitForTorpedoes"} != keys):
            raise ValueError("autogame: endCondition type/champs invalides")
        if "waitForTorpedoes" in condition and type(condition["waitForTorpedoes"]) is not bool:
            raise ValueError("autogame: waitForTorpedoes doit etre un booleen")
        if kind == "teamEliminated" and (not isinstance(condition["teamId"], str)
                or not any(isinstance(e, dict) and e.get("teamId") == condition["teamId"] for e in entries)):
            raise ValueError("autogame: equipe cible absente du scenario")
    duration = data.get("maxDurationSeconds")
    if "maxDurationSeconds" in data and (type(duration) not in (int, float)
            or not math.isfinite(duration) or duration <= 0):
        raise ValueError("autogame: maxDurationSeconds doit etre fini et strictement positif")
    if not entries and (condition is not None or duration is not None):
        raise ValueError("autogame: une fin automatique exige des bateaux")
    delay = data.get("startDelaySeconds", 0)
    if type(delay) not in (int, float) or not math.isfinite(delay) or delay < 0:
        raise ValueError("autogame: startDelaySeconds doit etre fini et positif ou nul")
    if delay > 0 and not entries:
        raise ValueError("autogame: un delai de preparation exige des bateaux")
    prepared = []
    for index, entry in enumerate(entries):
        label = f"autogame boats[{index}]"
        required = {"boatType", "ai", "position", "teamId"}
        if (not isinstance(entry, dict) or not required <= set(entry)
                or set(entry) - required - {"rotation", "teamName"}):
            raise ValueError(f"{label}: champs requis/inconnus invalides")
        kind = entry["boatType"]
        if kind not in ("destroyer", "submarine"):
            raise ValueError(f"{label}: boatType invalide")
        ai = entry["ai"]
        if not isinstance(ai, str) or not ai:
            raise ValueError(f"{label}: ai requis")
        for key in ("teamId", "teamName"):
            if key in entry and (not isinstance(entry[key], str)
                                 or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", entry[key])):
                raise ValueError(f"{label}: {key} invalide (1-64 lettres/chiffres/_/-)")
        pos = entry["position"]
        rotation = entry.get("rotation", 0.0)
        if not isinstance(pos, dict) or set(pos) != {"x", "y", "z"}:
            raise ValueError(f"{label}: position doit contenir x, y, z")
        for value in (*pos.values(), rotation):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{label}: coordonnees/rotation doivent etre finies")
        ground = world.get("ground") or {}
        if (abs(pos["x"]) > ground.get("width", 400) / 2 - 2
                or abs(pos["z"]) > ground.get("depth", 200) / 2 - 2
                or geometry.point_on_any_island(pos["x"], pos["z"], world)):
            raise ValueError(f"{label}: position hors carte ou sur une ile")
        boat = load_boat(kind)
        simulation.init_hull_integrity({"boat": boat})
        surface = -boat.get("flotation", 2) / simulation.UNIT_METERS_BOT
        bottom = -boat.get("maxDepthMeters", 200) / simulation.UNIT_METERS_BOT
        if (kind == "destroyer" and pos["y"] != surface
                or kind == "submarine" and not bottom <= pos["y"] <= surface):
            raise ValueError(f"{label}: profondeur incompatible avec le bateau")
        state = {"boatType": kind, "position": dict(pos)}
        if ai.startswith("rl_"):
            from rl.rl_runtime import attach_controller
            attach_controller(state, ai, trace_enabled=trace_enabled)
        else:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", ai):
                raise ValueError(f"{label}: nom BT invalide")
            tree = bot_ai.load_ai(ai)
            if tree is None:
                raise ValueError(f"{label}: arbre BT absent ou invalide: {ai}")
            pending = [tree]
            while pending:
                node = pending.pop()
                registry = (bot_ai.ACTIONS if isinstance(node, bot_ai.Action)
                            else bot_ai.CONDITIONS if isinstance(node, bot_ai.Condition) else None)
                if registry is not None and node.fn_name not in registry:
                    raise ValueError(f"{label}: fonction BT inconnue: {node.fn_name}")
                pending.extend(getattr(node, "children", []))
                if hasattr(node, "child"):
                    pending.append(node.child)
            state.update(ai_tree=tree, external_control=False)
        del state["boatType"], state["position"]
        prepared.append(dict(boat_type=kind, ai_name=ai, position=dict(pos),
                             rotation=rotation, team_id=entry["teamId"],
                             team_name=entry.get("teamName", entry["teamId"]),
                             prepared_ai=state))
    return PreparedAutogame(prepared, condition, duration, delay)
