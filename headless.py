"""Adaptateur sans réseau pour exécuter la simulation lors des entraînements."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import bot_ai
import geometry
import simulation


BASE_DIR = Path(__file__).resolve().parent


class _NoopSocketIO:
    """Remplace les appels Socket.IO qui n'ont pas d'effet en headless."""

    def emit(self, *args, **kwargs) -> None:
        return None

    def sleep(self, seconds: float) -> None:
        return None

    def start_background_task(self, target, *args, **kwargs):
        return None


class HeadlessLegacy:
    """Expose à ``Sim`` les derniers hooks qui vivent encore dans le serveur."""

    point_in_polygon = staticmethod(geometry.point_in_polygon)
    point_on_any_island = staticmethod(geometry.point_on_any_island)
    line_of_sight_clear = staticmethod(geometry.line_of_sight_clear)
    count_thermoclines_crossed = staticmethod(geometry.count_thermoclines_crossed)
    distance_point_segment = staticmethod(geometry.distance_point_segment)
    closest_approach_on_segment = staticmethod(geometry.closest_approach_on_segment)
    segments_intersect = staticmethod(geometry.segments_intersect)
    min_distance_to_islands = staticmethod(geometry.min_distance_to_islands)
    _ensure_island_bounds = staticmethod(geometry.ensure_island_bounds)

    def __init__(self) -> None:
        self.players: Dict[str, Dict[str, Any]] = {}
        self.bots: Dict[str, Dict[str, Any]] = {}
        self.torpedoes_server: Dict[Any, Dict[str, Any]] = {}
        self.drones_server: Dict[Any, Dict[str, Any]] = {}
        self.grenades_server: Dict[Any, Dict[str, Any]] = {}
        self.mines_server: Dict[Any, Dict[str, Any]] = {}
        self.sonar_beacons: Dict[Any, Dict[str, Any]] = {}
        self.passive_sonar_beacons: Dict[Any, Dict[str, Any]] = {}
        self.server_lures: Dict[Any, Dict[str, Any]] = {}
        self.active_wire_torpedoes: Dict[Any, Dict[str, Any]] = {}
        self.human_owner_sid: Dict[str, str] = {}
        self.player_boats_sids: Dict[str, list[str]] = {}
        self.autopiloted_sids: set[str] = set()
        self.torpedo_ammo: Dict[str, Dict[str, int]] = {}
        self.drone_ammo: Dict[str, Dict[str, int]] = {}
        self.grenade_ammo: Dict[str, int] = {}
        self.cannon_ammo: Dict[str, Dict[str, int]] = {}
        self.beacon_ammo: Dict[str, int] = {}
        self.passive_beacon_ammo: Dict[str, int] = {}
        self.lure_ammo: Dict[str, int] = {}
        self.mine_ammo: Dict[str, Dict[str, int]] = {}
        self.next_torpedo_tid: Dict[str, int] = {}
        self.next_drone_did: Dict[str, int] = {}
        self.next_grenade_gid: Dict[str, int] = {}
        self.next_lure_lid: Dict[str, int] = {}
        self.next_mine_id: Dict[str, int] = {}
        self.bots_passive = False
        self.socketio = _NoopSocketIO()
        self.sim: Optional[simulation.Sim] = None

    def init_torpedo_ammo_for_sid(self, sid: str) -> None:
        player = self.players.get(sid)
        if player is None:
            return
        specs = simulation.boat_torpedo_specs(player.get("boat") or {})
        ammo = {kind: int(spec.get("count", 0)) for kind, spec in specs.items()}
        if player.get("boatType") == "submarine":
            ammo["acoustic"] = ammo.get("acoustic", 0) + ammo.get("wireGuided", 0)
            ammo["wireGuided"] = 0
        self.torpedo_ammo[sid] = ammo

    def init_drone_ammo_for_sid(self, sid: str) -> None:
        player = self.players.get(sid) or {}
        specs = simulation.boat_drone_specs(player.get("boat") or {})
        self.drone_ammo[sid] = {kind: int(spec.get("number", 0)) for kind, spec in specs.items()}

    def init_grenade_ammo_for_sid(self, sid: str) -> None:
        player = self.players.get(sid) or {}
        spec = simulation.boat_grenade_spec(player.get("boat") or {})
        self.grenade_ammo[sid] = int((spec or {}).get("number", 0))

    def init_cannon_ammo_for_sid(self, sid: str) -> None:
        boat = (self.players.get(sid) or {}).get("boat") or {}
        self.cannon_ammo[sid] = {
            "cannon": int((boat.get("cannon") or {}).get("ammunition", 0)),
            "aa": int((boat.get("antiAircraft") or {}).get("ammunition", 0)),
        }

    def init_beacon_ammo_for_sid(self, sid: str) -> None:
        boat = (self.players.get(sid) or {}).get("boat") or {}
        self.beacon_ammo[sid] = int((boat.get("sonarBeacons") or {}).get("number", 0))
        self.passive_beacon_ammo[sid] = int((boat.get("passiveSonarBeacons") or {}).get("number", 0))

    def init_lure_ammo_for_sid(self, sid: str) -> None:
        boat = (self.players.get(sid) or {}).get("boat") or {}
        self.lure_ammo[sid] = int((boat.get("acousticLures") or {}).get("number", 0))

    def init_mine_ammo_for_sid(self, sid: str) -> None:
        boat = (self.players.get(sid) or {}).get("boat") or {}
        self.mine_ammo[sid] = {
            "surface": int((boat.get("mineSurf") or {}).get("number", 0)),
            "bottom": int((boat.get("mineBottom") or {}).get("number", 0)),
            "suspended": int((boat.get("mineSuspended") or {}).get("number", 0)),
        }

    def emit_drone_counts(self, sid: str) -> None:
        return None

    def emit_grenade_count(self, sid: str) -> None:
        return None

    def emit_torpedo_counts(self, sid: str) -> None:
        return None

    def emit_cannon_counts(self, sid: str) -> None:
        return None

    def emit_beacon_count(self, sid: str) -> None:
        return None

    def emit_lure_count(self, sid: str) -> None:
        return None

    def emit_mine_counts(self, sid: str) -> None:
        return None

    def _cleanup_player_entities(self, sid: str, player_id: str) -> None:
        return None

    def _get_bt_deps(self) -> Dict[str, Any]:
        assert self.sim is not None
        return {
            "UNIT_METERS_BOT": simulation.UNIT_METERS_BOT,
            "players": self.players,
            "drones_server": self.drones_server,
            "torpedoes_server": self.torpedoes_server,
            "torpedo_ammo": self.torpedo_ammo,
            "server_lures": self.server_lures,
            "pick_bot_waypoint": self.sim.pick_bot_waypoint,
            "point_on_any_island": geometry.point_on_any_island,
            "detect_enemies_passive": self.sim.detect_enemies_passive,
            "spawn_bot_torpedo": self.sim.spawn_bot_torpedo,
            "spawn_bot_torpedo_autonomous": self.sim.spawn_bot_torpedo_autonomous,
            "bot_torpedoes_status": lambda owner_id: [
                torpedo for torpedo in self.torpedoes_server.values()
                if torpedo.get("ownerPlayerId") == owner_id
            ],
            "bot_fire_cannon": self.sim.bot_fire_cannon,
            "bot_fire_aa": self.sim.bot_fire_aa,
            "bot_torpedoes_threat": self.sim.bot_torpedoes_threat,
            "bot_drop_lure": self.sim.bot_drop_lure,
            "bot_sonar_ping": self.sim.bot_sonar_ping,
            "same_team": simulation.same_team,
            "bots_passive_get": lambda: self.bots_passive,
            "spawn_drone": self.sim.spawn_drone,
            "drone_ammo": self.drone_ammo,
            "ensure_island_bounds": geometry.ensure_island_bounds,
            "line_of_sight_clear": geometry.line_of_sight_clear,
        }


def load_world(map_name: str) -> Dict[str, Any]:
    filename = "world.json" if map_name == "world" else f"world_{map_name}.json"
    with (BASE_DIR / "maps" / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_boat(boat_type: str) -> Dict[str, Any]:
    if boat_type not in {"submarine", "destroyer"}:
        raise ValueError(f"type de bateau inconnu: {boat_type}")
    with (BASE_DIR / "boats" / f"{boat_type}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


class HeadlessRunner:
    """Possède une simulation et une horloge déterministe sans serveur web."""

    def __init__(self, map_name: str = "combats", seed: int = 0) -> None:
        self.map_name = map_name
        self.world = load_world(map_name)
        self.random = random.Random(seed)
        self._time = 0.0
        self.legacy = HeadlessLegacy()
        self.sim = simulation.Sim(self.world, clock=lambda: self._time)
        self.legacy.sim = self.sim
        self.sim.set_legacy_hooks(self.legacy)
        self._bot_counter = 0

    def reset(self, seed: Optional[int] = None) -> None:
        if seed is not None:
            self.random.seed(seed)
            random.seed(seed)
        self._time = 0.0
        self.sim.reset()
        for value in vars(self.legacy).values():
            if isinstance(value, (dict, set)):
                value.clear()
        self.legacy.sim = self.sim
        self._bot_counter = 0

    def step(self, dt: float) -> None:
        self._time += dt
        self.sim.step(dt, self.world)

    def random_ocean_position(self, margin: float = 5.0) -> Tuple[float, float]:
        half_w = self.world["ground"]["width"] / 2 - margin
        half_d = self.world["ground"]["depth"] / 2 - margin
        for _ in range(500):
            x = self.random.uniform(-half_w, half_w)
            z = self.random.uniform(-half_d, half_d)
            if not geometry.point_on_any_island(x, z, self.world):
                return x, z
        raise RuntimeError("aucune position océanique trouvée")

    def spawn_bot(self, boat_type: str = "submarine", *, ai: Optional[str] = "autosub",
                  external_control: bool = False, position: Optional[Tuple[float, float]] = None,
                  rotation: Optional[float] = None, team_id: str = "team_bot") -> str:
        self._bot_counter += 1
        sid = f"__bot__{self._bot_counter}"
        player_id = f"bot{self._bot_counter:03d}"
        boat = load_boat(boat_type)
        x, z = position if position is not None else self.random_ocean_position()
        if geometry.point_on_any_island(x, z, self.world):
            raise ValueError("position de spawn située sur une île")
        max_speed_us = float(boat.get("speed", 25)) * 0.514444 / simulation.UNIT_METERS_BOT
        max_depth_m = float(boat.get("maxDepthMeters", 0)) if boat_type == "submarine" else 0.0
        depth_m = min(30.0, max_depth_m) if boat_type == "submarine" else float(boat.get("flotation", 2))
        spawn_y = -depth_m / simulation.UNIT_METERS_BOT
        selected_ai = None if external_control else (ai or boat.get("ai") or "default")
        bot = {
            "sid": sid, "id": player_id, "is_bot": True,
            "boatType": boat_type, "boat": boat, "team_id": team_id,
            "position": {"x": x, "y": spawn_y, "z": z},
            "rotation": rotation if rotation is not None else self.random.uniform(0, math.tau),
            "speed": 0.0, "rudder": 0.0,
            "rudder_max": 0.36, "rudder_speed": 0.3,
            "max_speed_us": max_speed_us, "cruise_us": max_speed_us * 0.6,
            "base_max_speed_us": max_speed_us, "base_cruise_us": max_speed_us * 0.6,
            "throttle_accel": 0.4, "max_depth_m": max_depth_m,
            "depth_target_y": spawn_y, "next_depth_change_at": 20.0,
            "next_detect_at": 0.0, "next_torpedo_at": 0.0,
            "next_cannon_at": 0.0, "next_aa_at": 0.0,
            "last_detected_ids": set(), "last_emit": 0.0,
            "waypoint": None, "integrity": 100.0,
            "ai_name": selected_ai, "ai_tree": bot_ai.load_ai(selected_ai),
            "external_control": external_control,
            "control_target_rudder": 0.0,
            "control_target_speed_ratio": 0.0,
            "control_target_depth_y": spawn_y,
        }
        self.legacy.bots[sid] = bot
        self.legacy.players[sid] = {
            "sid": sid, "id": player_id, "is_bot": True,
            "boatType": boat_type, "boat": boat, "team_id": team_id,
            "position": dict(bot["position"]), "rotation": bot["rotation"],
            "speed": 0.0, "speedRatio": 0.0, "reverse": False,
            "rudder": 0.0, "rudder_max": bot["rudder_max"], "max_speed_us": max_speed_us,
            "integrity": 100.0,
        }
        self.legacy.init_torpedo_ammo_for_sid(sid)
        self.legacy.init_drone_ammo_for_sid(sid)
        self.legacy.init_grenade_ammo_for_sid(sid)
        self.legacy.init_cannon_ammo_for_sid(sid)
        self.legacy.init_beacon_ammo_for_sid(sid)
        self.legacy.init_lure_ammo_for_sid(sid)
        self.legacy.init_mine_ammo_for_sid(sid)
        return sid
