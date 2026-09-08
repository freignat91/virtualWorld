import eventlet
eventlet.monkey_patch()

import gzip
import json
import math
import os
import re
import secrets
import time
import uuid
import random
import logging
from logging.handlers import RotatingFileHandler

# Logs rotatifs dans logs/ : 3 fichiers de 10 MB max (server.log + .1 + .2).
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_root = logging.getLogger()
_root.setLevel(logging.INFO)
# Ne pas dupliquer si reload (rare en eventlet, mais safe).
if not any(isinstance(h, RotatingFileHandler) for h in _root.handlers):
    _fh = RotatingFileHandler(
        os.path.join(_LOG_DIR, "server.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=2,
    )
    _fh.setFormatter(_log_fmt)
    _root.addHandler(_fh)
if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in _root.handlers):
    _sh = logging.StreamHandler()
    _sh.setFormatter(_log_fmt)
    _root.addHandler(_sh)

from flask import Flask, render_template, send_from_directory, request, Response, abort
from flask_socketio import SocketIO, emit
import mimetypes

import bot_ai
import events as ev_mod
import geometry
import nav_graph
import simulation
import sys

# Instance unique de la simu. Initialisée à la première utilisation
# (bot_ticker) pour que tous les globals de server.py soient déjà déclarés.
sim = None

app = Flask(__name__, static_folder="static", template_folder="templates")
_flask_secret_key = os.environ.get("VIRTUALWORLD_SECRET_KEY")
if _flask_secret_key and len(_flask_secret_key) < 32:
    raise RuntimeError("VIRTUALWORLD_SECRET_KEY doit contenir au moins 32 caractères")
if not _flask_secret_key:
    _flask_secret_key = secrets.token_urlsafe(48)
    logging.warning(
        "[security] VIRTUALWORLD_SECRET_KEY absente, utilisation d'une clé temporaire")
app.config["SECRET_KEY"] = _flask_secret_key
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
# ping_timeout élevé (120 s) : tolère qu'un joueur laisse l'onglet en arrière-plan
# plusieurs minutes (le navigateur throttle le pong) sans être déconnecté. Son
# bateau continue en autopilote pendant ce temps. ping_interval modéré pour ne
# pas spammer.
socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False,
                    ping_timeout=120, ping_interval=25,
                    compression_threshold=0)


# ============================================================================
# Event dispatcher : Sim emit Events → socketio.emit (Phase A du refactor).
#
# La simulation (simulation.Sim) ne connaît pas le réseau ; elle pousse des
# Events typés (events.py) dans un buffer. Le serveur draine ce buffer à
# chaque tick et publie sur socketio en routant selon le type.
#
# Conventions :
#   - target_sid/exclude_sid sont des champs hérités de la classe Event de base.
#   - Si target_sid est défini, on envoie en unicast (`to=sid`).
#   - Sinon broadcast à tous (avec exclude_sid optionnel via socketio rooms).
#
# Phase A : la table EVENT_DISPATCH est en place mais INACTIVE — la simu
# n'émet rien (le legacy server.py continue d'appeler socketio.emit
# directement). Phases B+ retireront ces appels directs au profit d'events.
# ============================================================================

def _r(v, n=2):
    """Arrondit un float à n décimales pour alléger les payloads JSON haute
    fréquence. Laisse les non-floats (None, bool, str, int) intacts."""
    if isinstance(v, float):
        return round(v, n)
    return v


def _round_pos(pos, n=2):
    """Reconstruit un dict position arrondi SANS muter l'original (l'état vivant
    de la simu y pointe — le muter corromprait la physique)."""
    if not pos:
        return pos
    return {
        "x": _r(pos.get("x", 0), n),
        "y": _r(pos.get("y", 0), n),
        "z": _r(pos.get("z", 0), n),
    }


def _emit_one(name, payload, target_sid=None):
    if target_sid:
        socketio.emit(name, payload, to=target_sid)
    else:
        socketio.emit(name, payload)


def _dispatch_player_joined(e):
    _emit_one("player_joined", e.player_data)


def _dispatch_player_left(e):
    _emit_one("player_left", {"id": e.player_id})


def _dispatch_player_moved(e):
    _emit_one("player_moved", {
        "id": e.player_id,
        "position": _round_pos(e.position),
        "rotation": _r(e.rotation, 3),
        "rudder": _r(e.rudder, 3),
        "reverse": e.reverse,
        "speedRatio": _r(e.speed_ratio, 3),
        "integrity": _r(e.integrity, 1),
        "submerged": e.submerged,
    })


def _dispatch_position_correct(e):
    _emit_one("position_correct", {
        "x": e.position.get("x", 0),
        "y": e.position.get("y", 0),
        "z": e.position.get("z", 0),
        "rotation": e.rotation,
        "reason": e.reason,
    }, target_sid=e.target_sid)


def _dispatch_boat_sunk(e):
    _emit_one("boat_sunk", {"victimId": e.victim_id, "attackerId": e.attacker_id})


def _dispatch_own_boat_sunk(e):
    _emit_one("own_boat_sunk", {"bsid": e.bsid, "playerId": e.player_id}, target_sid=e.target_sid)


def _dispatch_own_boat_added(e):
    _emit_one("own_boat_added", {
        "ghostSid": e.ghost_sid,
        "playerId": e.player_id,
        "boatType": e.boat_type,
        "boat": e.boat,
        "position": e.position,
        "rotation": e.rotation,
        "torpedoCounts": e.torpedo_counts,
        "droneCounts": e.drone_counts,
        "grenadeCount": e.grenade_count,
        "cannonCounts": e.cannon_counts,
        "beaconCount": e.beacon_count,
        "lureCount": e.lure_count,
        "mineCounts": e.mine_counts,
    }, target_sid=e.target_sid)


def _dispatch_integrity_changed(e):
    _emit_one("integrity", {"value": e.value, "bsid": e.bsid}, target_sid=e.target_sid)


def _dispatch_boat_changed(e):
    _emit_one("boat_changed", {
        "boatType": e.boat_type,
        "boat": e.boat,
        "torpedoCounts": e.torpedo_counts,
        "droneCounts": e.drone_counts,
        "grenadeCount": e.grenade_count,
        "cannonCounts": e.cannon_counts,
        "beaconCount": e.beacon_count,
        "lureCount": e.lure_count,
    }, target_sid=e.target_sid)


def _dispatch_other_boat_changed(e):
    _emit_one("other_boat_changed", {"id": e.player_id, "boat": e.boat})


def _dispatch_torpedo_counts(e):
    payload = dict(e.counts); payload["bsid"] = e.bsid
    _emit_one("torpedo_counts", payload, target_sid=e.target_sid)


def _dispatch_drone_counts(e):
    payload = dict(e.counts); payload["bsid"] = e.bsid
    _emit_one("drone_counts", payload, target_sid=e.target_sid)


def _dispatch_grenade_count(e):
    _emit_one("grenade_count", {"count": e.count, "bsid": e.bsid}, target_sid=e.target_sid)


def _dispatch_cannon_counts(e):
    payload = dict(e.counts); payload["bsid"] = e.bsid
    _emit_one("cannon_counts", payload, target_sid=e.target_sid)


def _dispatch_beacon_count(e):
    _emit_one("beacon_count", {"count": e.count, "bsid": e.bsid}, target_sid=e.target_sid)


def _dispatch_lure_count(e):
    _emit_one("lure_count", {"count": e.count, "bsid": e.bsid}, target_sid=e.target_sid)


def _dispatch_mine_counts(e):
    payload = dict(e.counts); payload["bsid"] = e.bsid
    _emit_one("mine_counts", payload, target_sid=e.target_sid)


def _dispatch_torpedo_state(e):
    _emit_one("torpedo_state", {
        "ownerId": e.owner_id, "tid": e.tid, "kind": e.kind,
        "x": _r(e.x), "y": _r(e.y), "z": _r(e.z),
        "dirX": _r(e.dir_x, 3), "dirZ": _r(e.dir_z, 3),
        "tx": _r(e.target_x), "ty": _r(e.target_y), "tz": _r(e.target_z),
    })


def _dispatch_torpedo_alert(e):
    pass


def _dispatch_torpedo_acquisition(e):
    pass


def _dispatch_torpedo_exploded(e):
    _emit_one("torpedo_exploded", {
        "ownerId": e.owner_id, "x": e.x, "y": e.y, "z": e.z,
        "damage": e.damage, "directHitId": e.direct_hit_id,
    })


def _dispatch_torpedo_dead(e):
    _emit_one("torpedo_dead", {"ownerId": e.owner_id, "tid": e.tid})


def _dispatch_drone_state(e):
    _emit_one("drone_state", {
        "ownerId": e.owner_id, "did": e.did, "kind": e.kind,
        "x": _r(e.x), "y": _r(e.y), "z": _r(e.z),
        "dirX": _r(e.dir_x, 3), "dirZ": _r(e.dir_z, 3),
        "returning": e.returning, "speed": _r(e.speed, 3),
        "autonomy": _r(e.autonomy, 1), "traveled": _r(e.traveled, 1),
        "rangeMeters": e.range_m,
    })


def _dispatch_drone_dead(e):
    _emit_one("drone_dead", {"ownerId": e.owner_id, "did": e.did, "reason": e.reason})


def _dispatch_grenade_launched(e):
    _emit_one("grenade_launched", {
        "shooterId": e.shooter_id, "gid": e.gid,
        "x": e.x, "y": e.y, "z": e.z,
        "vx": e.vx, "vy": e.vy, "vz": e.vz,
        "targetDepth": e.target_depth, "sinkSpeed": e.sink_speed,
    })


def _dispatch_grenade_exploded(e):
    _emit_one("grenade_exploded", {
        "id": e.shooter_id, "gid": e.gid,
        "x": e.x, "y": e.y, "z": e.z, "damage": e.damage, "dealt": e.dealt,
    })


def _dispatch_mine_placed(e):
    _emit_one("mine_placed", e.payload)


def _dispatch_mine_armed(e):
    _emit_one("mine_armed", {"ownerId": e.owner_id, "mid": e.mid})


def _dispatch_mine_exploded(e):
    _emit_one("mine_exploded", {
        "ownerId": e.owner_id, "mid": e.mid, "kind": e.kind,
        "x": e.x, "y": e.y, "z": e.z, "range": e.range,
    })


def _dispatch_mine_dead(e):
    _emit_one("mine_dead", {"ownerId": e.owner_id, "mid": e.mid})


def _dispatch_mine_revealed(e):
    payload = {"ownerId": e.owner_id, "mid": e.mid}
    for sid_p, p_p in players.items():
        if p_p.get("team_id") == e.target_team:
            socketio.emit("mine_revealed", payload, to=sid_p)


def _dispatch_sonar_beacon_placed(e):
    _emit_one("sonar_beacon_placed", e.payload)


def _dispatch_sonar_beacon_destroyed(e):
    _emit_one("sonar_beacon_destroyed", {"bid": e.bid})


def _dispatch_sonar_beacon_ping(e):
    _emit_one("sonar_beacon_ping", {"bid": e.bid, "x": e.x, "z": e.z, "at": e.at})


def _dispatch_sonar_pinged(e):
    _emit_one("sonar_pinged", {
        "id": e.player_id, "x": e.x, "z": e.z,
        "coneDeg": e.cone_deg, "rotation": e.rotation,
        "range": e.range_m, "reveal": e.reveal_m,
    })


def _dispatch_lure_dropped(e):
    _emit_one("lure_dropped", {
        "ownerId": e.owner_id, "lid": e.lid,
        "x": e.x, "y": e.y, "z": e.z,
        "noise": e.noise, "durationMs": e.duration_ms,
    })


def _dispatch_lure_destroyed(e):
    _emit_one("lure_destroyed", {"ownerId": e.owner_id, "lid": e.lid})


def _dispatch_cannon_fire(e):
    _emit_one("cannon_fire", {
        "shooterId": e.shooter_id, "kind": e.kind,
        "startX": e.start_x, "startY": e.start_y, "startZ": e.start_z,
        "endX": e.end_x, "endY": e.end_y, "endZ": e.end_z,
        "arcHeight": e.arc_height, "duration": e.duration, "impact": e.impact,
    })


def _dispatch_cannon_hit(e):
    _emit_one("cannon_hit", {
        "shooterId": e.shooter_id, "targetId": e.target_id, "damage": e.damage,
    })


def _dispatch_wake_spawned(e):
    _emit_one("wake_spawned", {
        "id": e.player_id, "x": e.x, "z": e.z,
        "submerged": e.submerged, "y": e.y,
    })


def _dispatch_day_cycle_state(e):
    _emit_one("day_cycle_state", e.snapshot)


def _dispatch_cheat_view_bot(e):
    _emit_one("cheat_view_bot", e.payload, target_sid=e.target_sid)


def _dispatch_cheat_view_self(e):
    _emit_one("cheat_view_self", {}, target_sid=e.target_sid)


def _dispatch_cheat_bots_calmdown_state(e):
    _emit_one("cheat_bots_calmdown_state", {"passive": e.passive}, target_sid=e.target_sid)


def _dispatch_cheat_reload_ai_done(e):
    _emit_one("cheat_reload_ai_done", {"count": e.count}, target_sid=e.target_sid)


def _dispatch_bot_spawned(e):
    _emit_one("bot_spawned", {"id": e.bot_id, "boatType": e.boat_type, "ai": e.ai}, target_sid=e.target_sid)


def _dispatch_admin_world_loaded(e):
    _emit_one("admin_world_loaded", {"world": e.world, "name": e.name}, target_sid=e.target_sid)


def _dispatch_admin_save_ok(e):
    _emit_one("admin_save_ok", {"name": e.name}, target_sid=e.target_sid)


def _dispatch_admin_error(e):
    _emit_one("admin_error", {"message": e.message}, target_sid=e.target_sid)


# Table type → dispatcher.
EVENT_DISPATCH = {
    ev_mod.PlayerJoined: _dispatch_player_joined,
    ev_mod.PlayerLeft: _dispatch_player_left,
    ev_mod.PlayerMoved: _dispatch_player_moved,
    ev_mod.PositionCorrect: _dispatch_position_correct,
    ev_mod.BoatSunk: _dispatch_boat_sunk,
    ev_mod.OwnBoatSunk: _dispatch_own_boat_sunk,
    ev_mod.OwnBoatAdded: _dispatch_own_boat_added,
    ev_mod.IntegrityChanged: _dispatch_integrity_changed,
    ev_mod.BoatChanged: _dispatch_boat_changed,
    ev_mod.OtherBoatChanged: _dispatch_other_boat_changed,
    ev_mod.TorpedoCounts: _dispatch_torpedo_counts,
    ev_mod.DroneCounts: _dispatch_drone_counts,
    ev_mod.GrenadeCount: _dispatch_grenade_count,
    ev_mod.CannonCounts: _dispatch_cannon_counts,
    ev_mod.BeaconCount: _dispatch_beacon_count,
    ev_mod.LureCount: _dispatch_lure_count,
    ev_mod.MineCounts: _dispatch_mine_counts,
    ev_mod.TorpedoState: _dispatch_torpedo_state,
    ev_mod.TorpedoAlert: _dispatch_torpedo_alert,
    ev_mod.TorpedoAcquisition: _dispatch_torpedo_acquisition,
    ev_mod.TorpedoExploded: _dispatch_torpedo_exploded,
    ev_mod.TorpedoDead: _dispatch_torpedo_dead,
    ev_mod.DroneState: _dispatch_drone_state,
    ev_mod.DroneDead: _dispatch_drone_dead,
    ev_mod.GrenadeLaunched: _dispatch_grenade_launched,
    ev_mod.GrenadeExploded: _dispatch_grenade_exploded,
    ev_mod.MinePlaced: _dispatch_mine_placed,
    ev_mod.MineArmed: _dispatch_mine_armed,
    ev_mod.MineExploded: _dispatch_mine_exploded,
    ev_mod.MineDead: _dispatch_mine_dead,
    ev_mod.MineRevealed: _dispatch_mine_revealed,
    ev_mod.SonarBeaconPlaced: _dispatch_sonar_beacon_placed,
    ev_mod.SonarBeaconDestroyed: _dispatch_sonar_beacon_destroyed,
    ev_mod.SonarBeaconPing: _dispatch_sonar_beacon_ping,
    ev_mod.SonarPinged: _dispatch_sonar_pinged,
    ev_mod.LureDropped: _dispatch_lure_dropped,
    ev_mod.LureDestroyed: _dispatch_lure_destroyed,
    ev_mod.CannonFire: _dispatch_cannon_fire,
    ev_mod.CannonHit: _dispatch_cannon_hit,
    ev_mod.WakeSpawned: _dispatch_wake_spawned,
    ev_mod.DayCycleState: _dispatch_day_cycle_state,
    ev_mod.CheatViewBot: _dispatch_cheat_view_bot,
    ev_mod.CheatViewSelf: _dispatch_cheat_view_self,
    ev_mod.CheatBotsCalmdownState: _dispatch_cheat_bots_calmdown_state,
    ev_mod.CheatReloadAiDone: _dispatch_cheat_reload_ai_done,
    ev_mod.BotSpawned: _dispatch_bot_spawned,
    ev_mod.AdminWorldLoaded: _dispatch_admin_world_loaded,
    ev_mod.AdminSaveOk: _dispatch_admin_save_ok,
    ev_mod.AdminError: _dispatch_admin_error,
}


def dispatch_events(events_list):
    """Drain le buffer Sim et publie sur socketio. Inconnu = warning."""
    for e in events_list:
        fn = EVENT_DISPATCH.get(type(e))
        if fn is None:
            logging.warning(f"[event-dispatch] No handler for {type(e).__name__}")
            continue
        try:
            fn(e)
        except Exception as ex:
            logging.exception(f"[event-dispatch] {type(e).__name__}: {ex}")


with open("config/conffile.json", "r") as f:
    config = json.load(f)

BOAT_TYPES = ["destroyer", "submarine"]

MAPS_DIR = "maps"
DEFAULT_MAP = "world"
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
CURRENT_MAP_FILE = os.path.join(MAPS_DIR, ".current_map")


def map_path(name):
    if not SAFE_NAME_RE.match(name):
        raise ValueError("Nom invalide")
    if name == DEFAULT_MAP:
        return os.path.join(MAPS_DIR, "world.json")
    return os.path.join(MAPS_DIR, f"world_{name}.json")


def read_current_map_name():
    try:
        with open(CURRENT_MAP_FILE, "r") as f:
            name = f.read().strip()
        if name and SAFE_NAME_RE.match(name) and os.path.exists(map_path(name)):
            return name
    except Exception:
        pass
    return DEFAULT_MAP


def write_current_map_name(name):
    try:
        os.makedirs(MAPS_DIR, exist_ok=True)
        with open(CURRENT_MAP_FILE, "w") as f:
            f.write(name)
    except Exception as e:
        logging.warning(f"Impossible de sauvegarder la carte courante: {e}")


current_map_name = read_current_map_name()
MAX_HUMAN_PLAYERS = 10  # peut être surchargé via --maxPlayer en CLI
MAX_BOTS = 32
MAX_PLAYER_BOATS = 8
MAX_WORLD_SONAR_BEACONS = 256
MAX_WORLD_PASSIVE_BEACONS = 256


def load_world():
    with open(map_path(current_map_name), "r") as f:
        return json.load(f)


def load_boat(boat_type):
    filename = "boats/destroyer.json" if boat_type == "destroyer" else "boats/submarine.json"
    with open(filename, "r") as f:
        return json.load(f)


# Phase G : helpers géométriques migrés dans geometry.py (purs, sans Flask).
point_in_polygon = geometry.point_in_polygon
_ensure_island_bounds = geometry.ensure_island_bounds
point_on_any_island = geometry.point_on_any_island
line_of_sight_clear = geometry.line_of_sight_clear
count_thermoclines_crossed = geometry.count_thermoclines_crossed
distance_point_segment = geometry.distance_point_segment
closest_approach_on_segment = geometry.closest_approach_on_segment
segments_intersect = geometry.segments_intersect


min_distance_to_islands = geometry.min_distance_to_islands


def random_ocean_position(world_data, players_dict=None, unit_meters=10):
    half_w = world_data["ground"]["width"] / 2
    half_d = world_data["ground"]["depth"] / 2
    min_island_dist = 20.0 / unit_meters
    target_min_dist_from_other = 12000.0 / unit_meters
    target_max_dist_from_other = 15000.0 / unit_meters
    others = []
    if players_dict:
        for p in players_dict.values():
            pos = p.get("position")
            if pos:
                others.append((pos.get("x", 0), pos.get("z", 0)))
    have_anchor = len(others) > 0
    import math
    for attempt in range(200):
        if have_anchor and attempt < 150:
            ax, az = random.choice(others)
            r = random.uniform(target_min_dist_from_other, target_max_dist_from_other)
            theta = random.uniform(0, 6.2832)
            x = ax + r * math.cos(theta)
            z = az + r * math.sin(theta)
            if x < -half_w or x > half_w or z < -half_d or z > half_d:
                continue
            too_close = False
            for ox, oz in others:
                dx = x - ox
                dz = z - oz
                if dx * dx + dz * dz < target_min_dist_from_other * target_min_dist_from_other:
                    too_close = True
                    break
            if too_close:
                continue
        else:
            x = random.uniform(-half_w, half_w)
            z = random.uniform(-half_d, half_d)
        if point_on_any_island(x, z, world_data):
            continue
        if min_distance_to_islands(x, z, world_data) < min_island_dist:
            continue
        return x, z
    for _ in range(100):
        x = random.uniform(-half_w, half_w)
        z = random.uniform(-half_d, half_d)
        if not point_on_any_island(x, z, world_data):
            return x, z
    return 0, 0


players = {}
bots = {}
next_bot_id = 1
# Multi-bateaux par joueur humain. Chaque bateau secondaire est ajouté à
# `players` avec un sid synthétique f"__own__<sid>__<n>" et un nouveau playerId
# (UUID). Les autres joueurs le voient comme un participant indépendant.
human_owner_sid = {}     # sid_secondaire -> sid_humain_propriétaire
player_boats_sids = {}   # sid_humain -> [sids_de_ses_bateaux] (1er = bateau primaire)
autopiloted_sids = set() # sids actuellement en autopilote (= non actif côté joueur)
sonar_beacons = {}
next_beacon_id = 1
# Balises sonar passives (ne pingent pas, détectent par bruit perçu).
passive_sonar_beacons = {}      # bid -> dict beacon
next_passive_beacon_id = 1
passive_beacon_ammo = {}        # sid -> count restant
PASSIVE_BEACON_TICK_INTERVAL = 3.0  # tick détection toutes les 3s
# Mines posées (3 types : surface, bottom, suspended). Clé (ownerId, mid).
mines_server = {}
next_mine_id = {}        # ownerId -> prochain mid
mine_ammo = {}           # sid -> { surface: n, bottom: n, suspended: n }
MINE_TICK_INTERVAL = 0.05  # même que bot_ticker
# Tous les drones (joueurs + bots), simulés côté serveur authoritaire.
# Clé : (ownerPlayerId, did). did est unique par tireur, alloué côté serveur.
drones_server = {}
next_drone_did = {}  # ownerPlayerId -> prochain did
drone_ammo = {}      # sid -> { automatic: n, manual: n }
DRONE_DISCOVER_RADIUS_M = 3000.0
DRONE_RECOVERY_DISTANCE_U = 0.5  # ~5 m
# Toggle global : si True, les bots n'attaquent plus (ni DCA, ni futurs tirs torpilles/canon).
bots_passive = False
# Multiplicateur de vitesse de simulation (cheats time1/time2/time4/time8).
# 1 = normal. 2 = 2 sim.step par tick réel. Idem ×4, ×8.
sim_tick_multiplier = 1
# Toutes les torpilles (joueurs + bots), simulées côté serveur authoritaire.
# Clé : (ownerPlayerId, tid). Le tid est unique par tireur et alloué par le serveur.
torpedoes_server = {}
next_torpedo_tid = {}  # ownerId -> prochain tid à allouer
# Compteurs munitions par sid (joueurs et bots) : { sid: { acoustic: n, wireGuided: n, autonomous: n } }
torpedo_ammo = {}
# Leurres acoustiques actifs côté serveur, indexés par (ownerId, lid). Servent à
# l'acquisition acoustique des torpilles serveur.
server_lures = {}
# Torpilles filoguidée actives par tireur. Sert à empêcher d'en lancer une 2e
# tant que la première est en l'air, et à appliquer le steering reçu.
active_wire_torpedoes = {}  # ownerPlayerId -> (ownerId, tid)
TORPEDO_TICK_INTERVAL = 0.05  # 20 Hz, aligné sur bot_ticker / MOVE_EMIT_INTERVAL
TORPEDO_CEILING_Y = -2.0 / 10.0  # plafond -2 m en unités
SONAR_BEACON_PING_INTERVAL = 30.0
BOT_TICK_INTERVAL = 0.05
BOT_DT_MAX = 0.15
UNIT_METERS_BOT = 10.0

# Diagnostics WebSocket — compteurs internes, raz toutes les 10 s
_ws_diag = {
    "tick_count": 0,
    "gap_sum": 0.0,
    "gap_max": 0.0,
    "events_sum": 0,
    "dispatch_time_sum": 0.0,
    "dispatch_time_max": 0.0,
    "last_report": 0.0,
}
WS_DIAG_INTERVAL = 10.0  # secondes entre deux rapports

DAY_DURATION = float(config.get("world", {}).get("dayDurationSeconds", 1800))
ENDING_TRANSITION_SECONDS = 15.0
day_cycle = {"state": "off", "startedAt": 0.0, "startTimeOfDay": 0.0, "speed": 1.0, "endsAt": 0.0}


def day_cycle_snapshot():
    return {
        "state": day_cycle["state"],
        "startedAt": day_cycle["startedAt"],
        "startTimeOfDay": day_cycle["startTimeOfDay"],
        "speed": day_cycle["speed"],
        "endsAt": day_cycle["endsAt"],
        "now": time.time(),
        "dayDuration": DAY_DURATION,
    }


def current_time_of_day(now):
    elapsed = max(0.0, now - day_cycle["startedAt"])
    return (day_cycle["startTimeOfDay"] + day_cycle["speed"] * elapsed / DAY_DURATION) % 1


def shortest_signed_distance(current, target=0.5):
    diff = (target - current) % 1.0
    if diff > 0.5:
        diff -= 1.0
    return diff


@app.route("/")
def index():
    resp = Response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/aide")
def aide():
    return render_template("aide.html")


# Pré-chargement des assets en RAM : sert à éviter qu'un I/O disque synchrone
# (notamment les grosses textures de modèles) ne bloque eventlet et fasse
# accumuler les emits du bot_ticker (saccades sur les bots).
_asset_cache = {}


_GZIP_EXTENSIONS = {".gltf", ".bin", ".json", ".js", ".css", ".html", ".txt", ".svg"}

def _preload_asset_dir(label, root):
    if not os.path.isdir(root):
        return
    count = 0
    total = 0
    gz_count = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            ctype = mimetypes.guess_type(fn)[0] or "application/octet-stream"
            _asset_cache[(label, rel)] = (data, ctype)
            ext = os.path.splitext(fn)[1].lower()
            if ext in _GZIP_EXTENSIONS and len(data) > 1024:
                data_gz = gzip.compress(data, compresslevel=6)
                if len(data_gz) < len(data) * 0.9:
                    _asset_cache[(label + "_gz", rel)] = (data_gz, ctype)
                    gz_count += 1
            count += 1
            total += len(data)
    logging.info(f"[preload] {label}: {count} fichiers, {total/1024/1024:.1f} MB en RAM ({gz_count} gzippés)")


_preload_asset_dir("images", "images")
_preload_asset_dir("models", "models")

# Précharge les gros JS tiers en RAM : évite que la lecture disque de babylon.js
# (4.9 MB) ne bloque la boucle eventlet pendant le transfert et force les autres
# requêtes statiques à s'exécuter en série.
_STATIC_JS_PRELOAD = ["babylon.js", "babylon.glTFFileLoader.js", "earcut.min.js", "socket.io.min.js"]
for _fn in _STATIC_JS_PRELOAD:
    _fp = os.path.join("static", _fn)
    if os.path.exists(_fp):
        with open(_fp, "rb") as _f:
            _data = _f.read()
        _data_gz = gzip.compress(_data, compresslevel=6)
        _asset_cache[("static_js", _fn)] = (_data, "application/javascript")
        _asset_cache[("static_js_gz", _fn)] = (_data_gz, "application/javascript")
        logging.info(f"[preload] static_js/{_fn}: {len(_data)//1024}KB -> {len(_data_gz)//1024}KB gz")


def _serve_cached(label, filename, fallback_dir):
    from flask import request as _req
    entry = _asset_cache.get((label, filename))
    if entry is None:
        return send_from_directory(fallback_dir, filename)
    data, ctype = entry
    accept_gz = "gzip" in _req.headers.get("Accept-Encoding", "")
    gz_entry = _asset_cache.get((label + "_gz", filename)) if accept_gz else None
    if gz_entry is not None:
        data, ctype = gz_entry
        resp = Response(data, mimetype=ctype)
        resp.headers["Content-Encoding"] = "gzip"
    else:
        resp = Response(data, mimetype=ctype)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.route("/images/<path:filename>")
def images(filename):
    return _serve_cached("images", filename, "images")


@app.route("/models/<path:filename>")
def models(filename):
    return _serve_cached("models", filename, "models")


def _static_files_handler(filename):
    """Remplace le handler Flask intégré /static/ : sert les gros JS depuis la RAM avec gzip."""
    from flask import request as _req
    _t0 = time.time()
    accept_gz = "gzip" in _req.headers.get("Accept-Encoding", "")
    gz_entry = _asset_cache.get(("static_js_gz", filename)) if accept_gz else None
    raw_entry = _asset_cache.get(("static_js", filename))
    if gz_entry is not None:
        data, ctype = gz_entry
        resp = Response(data, mimetype=ctype)
        resp.headers["Content-Encoding"] = "gzip"
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        raw_kb = len(raw_entry[0]) // 1024 if raw_entry else 0
        logging.info(f"[startup] /static/{filename} RAM+gz {raw_kb}KB->{len(data)//1024}KB {(time.time()-_t0)*1000:.1f}ms")
        return resp
    if raw_entry is not None:
        data, ctype = raw_entry
        resp = Response(data, mimetype=ctype)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        logging.info(f"[startup] /static/{filename} RAM {len(data)//1024}KB {(time.time()-_t0)*1000:.1f}ms")
        return resp
    resp = send_from_directory("static", filename)
    logging.info(f"[startup] /static/{filename} disque {(time.time()-_t0)*1000:.1f}ms")
    return resp

# Surcharge le handler Flask intégré pour /static/ (endpoint "static").
app.view_functions["static"] = _static_files_handler


@app.route("/api/world")
def api_world():
    return load_world()


@socketio.on("connect")
def handle_connect():
    transport = request.environ.get("HTTP_UPGRADE", "polling")
    logging.info(f"[startup] connect sid={request.sid} transport={transport}")


def _list_active_teams():
    """Liste des équipes actuellement en jeu, dédupliquée par team_id."""
    seen = {}
    for p in players.values():
        tid = p.get("team_id")
        if not tid:
            continue
        if tid not in seen:
            seen[tid] = {
                "team_id": tid,
                "team_name": p.get("team_name") or tid,
                "is_bots": bool(p.get("is_bot")),
                "members": 0,
            }
        seen[tid]["members"] += 1
    return list(seen.values())


@socketio.on("list_teams")
def handle_list_teams():
    emit("teams_list", {"teams": _list_active_teams()})


@socketio.on("select_boat")
def handle_select_boat(data):
    _t_select = time.time()
    logging.info(f"[startup] select_boat reçu sid={request.sid[:8]}")
    if request.sid in players:
        logging.warning(f"[startup] select_boat ignoré pour sid déjà initialisé={request.sid[:8]}")
        return
    humans = sum(1 for p in players.values() if not p.get("is_bot"))
    if humans >= MAX_HUMAN_PLAYERS:
        emit("server_full", {"max": MAX_HUMAN_PLAYERS})
        return
    player_id = str(uuid.uuid4())[:8]
    boat_type = data.get("boatType", "destroyer")
    if boat_type not in BOAT_TYPES:
        boat_type = "destroyer"
    _t0 = time.time()
    boat_data = load_boat(boat_type)
    logging.info(f"[startup] load_boat={((time.time()-_t0)*1000):.0f}ms")
    _t0 = time.time()
    world_data = load_world()
    logging.info(f"[startup] load_world={((time.time()-_t0)*1000):.0f}ms")
    _t0 = time.time()
    spawn_x, spawn_z = _random_spawn_on_nav_graph(world_data, players)
    logging.info(f"[startup] spawn_nav={((time.time()-_t0)*1000):.0f}ms")
    # Équipe : prend ce que le client envoie (team_id/team_name) ou fallback "equipe1".
    raw_tid = data.get("team_id")
    raw_tname = data.get("team_name")
    if raw_tid and isinstance(raw_tid, str):
        team_id = raw_tid.strip()[:32] or None
    else:
        team_id = None
    if raw_tname and isinstance(raw_tname, str):
        team_name = raw_tname.strip()[:64] or None
    else:
        team_name = None
    if not team_id:
        # Fallback : nouvelle équipe "equipeN" où N = nb équipes humaines actives + 1.
        existing_human_teams = {p.get("team_id") for p in players.values()
                                if not p.get("is_bot") and p.get("team_id")}
        n = len(existing_human_teams) + 1
        team_id = f"equipe{n}"
        team_name = team_name or f"Équipe {n}"
    if not team_name:
        team_name = team_id
    players[request.sid] = {
        "id": player_id,
        "boatType": boat_type,
        "boat": boat_data,
        "position": {"x": spawn_x, "y": 0, "z": spawn_z},
        "rotation": random.uniform(0, 6.28),
        "team_id": team_id,
        "team_name": team_name,
    }
    init_torpedo_ammo_for_sid(request.sid)
    init_drone_ammo_for_sid(request.sid)
    init_grenade_ammo_for_sid(request.sid)
    init_cannon_ammo_for_sid(request.sid)
    init_beacon_ammo_for_sid(request.sid)
    init_passive_beacon_ammo_for_sid(request.sid)
    init_lure_ammo_for_sid(request.sid)
    init_mine_ammo_for_sid(request.sid)
    init_player_integrity(request.sid)
    _t0 = time.time()
    _world_for_init = load_world()
    logging.info(f"[startup] load_world (init payload)={((time.time()-_t0)*1000):.0f}ms")
    _t0 = time.time()
    _init_payload = {
        "world": _world_for_init,
        "playerId": player_id,
        "boatType": boat_type,
        "boat": boat_data,
        "team_id": team_id,
        "team_name": team_name,
        "players": {sid: p for sid, p in players.items() if sid != request.sid},
        "position": players[request.sid]["position"],
        "rotation": players[request.sid]["rotation"],
        "dayCycle": day_cycle_snapshot(),
        "weapons": config.get("weapons", {}),
        "sonarBeacons": [
            {**{k: v for k, v in b.items() if k not in ("ownerSid", "revealedTeams")},
             "revealedByMyTeam": team_id in b.get("revealedTeams", set())}
            for b in sonar_beacons.values()
        ],
        "passiveSonarBeacons": list(passive_sonar_beacons.values()),
        "mines": [
            {**_mine_payload(m), "teamId": m.get("teamId"),
             "revealedByMyTeam": team_id in m.get("revealedTeams", set())}
            for m in mines_server.values()
        ],
        "torpedoCounts": dict(torpedo_ammo.get(request.sid) or {}),
        "droneCounts": dict(drone_ammo.get(request.sid) or {}),
        "grenadeCount": grenade_ammo.get(request.sid, 0),
        "cannonCounts": dict(cannon_ammo.get(request.sid) or {}),
        "beaconCount": beacon_ammo.get(request.sid, 0),
        "passiveBeaconCount": passive_beacon_ammo.get(request.sid, 0),
        "lureCount": lure_ammo.get(request.sid, 0),
        "mineCounts": dict(mine_ammo.get(request.sid) or {}),
    }
    import sys as _sys
    _payload_kb = _sys.getsizeof(str(_init_payload)) / 1024
    logging.info(f"[startup] init payload built={((time.time()-_t0)*1000):.0f}ms size~{_payload_kb:.0f}KB players={len(players)-1}")
    _t0 = time.time()
    emit("init", _init_payload)
    logging.info(f"[startup] emit(init) done={((time.time()-_t0)*1000):.0f}ms total={((time.time()-_t_select)*1000):.0f}ms")
    emit("player_joined", players[request.sid], broadcast=True, include_self=False)
    # Multi-bateaux : initialise la liste avec le bateau primaire.
    player_boats_sids[request.sid] = [request.sid]


def _cleanup_player_entities(sid, pid):
    """Retire torpilles, drones, grenades, leurres, balises passives et compteurs
    de munitions d'un bateau (primaire ou secondaire). Les mines posées restent
    en jeu (comme les balises sonar)."""
    for k in list(torpedoes_server.keys()):
        if torpedoes_server[k]["ownerPlayerId"] == pid:
            torpedoes_server.pop(k, None)
    active_wire_torpedoes.pop(pid, None)
    next_torpedo_tid.pop(pid, None)
    torpedo_ammo.pop(sid, None)
    for k in list(drones_server.keys()):
        if drones_server[k]["ownerPlayerId"] == pid:
            kill_server_drone(drones_server[k], reason="lost", refund=False)
            drones_server.pop(k, None)
    next_drone_did.pop(pid, None)
    drone_ammo.pop(sid, None)
    for k in list(grenades_server.keys()):
        if grenades_server[k]["ownerPlayerId"] == pid:
            grenades_server.pop(k, None)
    next_grenade_gid.pop(pid, None)
    grenade_ammo.pop(sid, None)
    cannon_ammo.pop(sid, None)
    beacon_ammo.pop(sid, None)
    passive_beacon_ammo.pop(sid, None)
    for bid in list(passive_sonar_beacons.keys()):
        if passive_sonar_beacons[bid].get("ownerSid") == sid:
            del passive_sonar_beacons[bid]
            socketio.emit("passive_sonar_beacon_destroyed", {"bid": bid})
    for k in list(server_lures.keys()):
        if k[0] == pid:
            lure = server_lures.pop(k, None)
            if lure:
                socketio.emit("lure_destroyed", {"ownerId": lure["ownerId"], "lid": lure["lid"]})
    next_lure_lid.pop(pid, None)
    lure_ammo.pop(sid, None)
    next_mine_id.pop(pid, None)
    mine_ammo.pop(sid, None)


@socketio.on("disconnect")
def handle_disconnect():
    if request.sid not in players:
        return
    pid = players[request.sid]["id"]
    _cleanup_player_entities(request.sid, pid)
    # Multi-bateaux : nettoyer tous les bateaux secondaires du joueur.
    for ghost_sid in list(player_boats_sids.get(request.sid, [])):
        if ghost_sid == request.sid:
            continue
        ghost = players.get(ghost_sid)
        if ghost is None:
            continue
        _cleanup_player_entities(ghost_sid, ghost["id"])
        human_owner_sid.pop(ghost_sid, None)
        autopiloted_sids.discard(ghost_sid)
        emit("player_left", {"id": ghost["id"]}, broadcast=True)
        del players[ghost_sid]
    player_boats_sids.pop(request.sid, None)
    autopiloted_sids.discard(request.sid)
    emit("player_left", {"id": pid}, broadcast=True)
    del players[request.sid]


@socketio.on("cheat_swap_to_bot")
def handle_cheat_swap_to_bot(data):
    if request.sid not in players:
        return
    p = players[request.sid]
    pos = p.get("position") or {"x": 0, "y": 0, "z": 0}
    px, pz = pos.get("x", 0), pos.get("z", 0)
    sorted_bots = sorted(
        bots.values(),
        key=lambda b: (b["position"]["x"] - px) ** 2 + (b["position"]["z"] - pz) ** 2,
    )
    if not sorted_bots:
        emit("admin_error", {"message": "Aucun bot disponible"})
        return
    idx = int(data.get("index", 0)) % len(sorted_bots)
    target = sorted_bots[idx]
    autopiloted_sids.add(request.sid)
    emit("cheat_view_bot", {
        "botId": target["id"],
        "boatType": target["boatType"],
        "boat": target["boat"],
    })


@socketio.on("cheat_swap_to_self")
def handle_cheat_swap_to_self():
    if request.sid not in players:
        return
    autopiloted_sids.discard(request.sid)
    emit("cheat_view_self", {})


@socketio.on("cheat_bot_speed_mult")
def handle_cheat_bot_speed_mult(data):
    """Cycle la vitesse max d'un bot : ×1 → ×2 → ×4 → ×8 → ×1."""
    if request.sid not in players:
        return
    bot_id = (data or {}).get("id")
    if not bot_id:
        return
    try:
        mult = int((data or {}).get("multiplier", 2))
    except (TypeError, ValueError):
        mult = 2
    if mult not in (1, 2, 4, 8):
        mult = 1
    for bot in bots.values():
        if bot.get("id") == bot_id:
            base = bot.get("base_max_speed_us")
            if base is None:
                base = bot.get("max_speed_us", 0)
                bot["base_max_speed_us"] = base
            base_cruise = bot.get("base_cruise_us")
            if base_cruise is None:
                base_cruise = bot.get("cruise_us", 0)
                bot["base_cruise_us"] = base_cruise
            old_mult = bot.get("speed_mult", 1)
            bot["max_speed_us"] = base * mult
            bot["cruise_us"] = base_cruise * mult
            # Applique immédiatement le multiplicateur à la vitesse courante du
            # bot (sinon l'accélération progressive masque l'effet).
            bot["speed"] = bot.get("speed", 0) * (mult / old_mult)
            bot["speed_mult"] = mult
            logging.info(f"[cheat] {bot_id} max_speed_us = ×{mult} ({bot['max_speed_us']:.3f} u/s)")
            return


@socketio.on("cheat_speed_mult")
def handle_cheat_speed_mult(data):
    """Multiplie la vitesse max validée côté serveur pour le bateau ACTIF du
    joueur (équivalent serveur du cheat client `speed2`). Appliqué via
    p['speed_mult'], lu dans validate_player_move."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data or {})
    p = players.get(acting_sid)
    if not p:
        return
    try:
        mult = int((data or {}).get("multiplier", 2))
    except (TypeError, ValueError):
        mult = 2
    if mult not in (1, 2, 4, 8):
        mult = 1
    p["speed_mult"] = float(mult)
    logging.info(f"[cheat] {p.get('id')} speed_mult = ×{mult}")


@socketio.on("cheat_godmode")
def handle_cheat_godmode(data):
    """Toggle invincibilité sur TOUS les bateaux du joueur (cheat iddqd)."""
    if request.sid not in players:
        return
    p = players[request.sid]
    new_state = not p.get("godmode", False)
    owned_sids = player_boats_sids.get(request.sid, [request.sid])
    for sid in owned_sids:
        pp = players.get(sid)
        if pp:
            pp["godmode"] = new_state
    logging.info(f"[cheat] {p.get('id')} godmode={new_state} sids={owned_sids}")
    emit("cheat_godmode_state", {"active": new_state})


@socketio.on("cheat_resupply")
def handle_cheat_resupply(data):
    """Recharge toutes les munitions au max pour le bateau actif (cheat idkfa)."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data or {})
    p = players.get(acting_sid)
    if not p:
        return
    init_torpedo_ammo_for_sid(acting_sid)
    init_drone_ammo_for_sid(acting_sid)
    init_grenade_ammo_for_sid(acting_sid)
    init_cannon_ammo_for_sid(acting_sid)
    init_beacon_ammo_for_sid(acting_sid)
    init_passive_beacon_ammo_for_sid(acting_sid)
    init_lure_ammo_for_sid(acting_sid)
    init_mine_ammo_for_sid(acting_sid)
    init_player_integrity(acting_sid)
    bsid = acting_sid if acting_sid != request.sid else None
    # Format plat attendu côté client : { bsid, ...counts }.
    torp_payload = dict(torpedo_ammo.get(acting_sid) or {}); torp_payload["bsid"] = bsid
    emit("torpedo_counts", torp_payload)
    drone_payload = dict(drone_ammo.get(acting_sid) or {}); drone_payload["bsid"] = bsid
    emit("drone_counts", drone_payload)
    cannon_payload = dict(cannon_ammo.get(acting_sid) or {}); cannon_payload["bsid"] = bsid
    emit("cannon_counts", cannon_payload)
    mine_payload = dict(mine_ammo.get(acting_sid) or {}); mine_payload["bsid"] = bsid
    emit("mine_counts", mine_payload)
    emit("grenade_count", {"bsid": bsid, "count": grenade_ammo.get(acting_sid, 0)})
    emit("beacon_count", {"bsid": bsid, "count": beacon_ammo.get(acting_sid, 0)})
    emit("passive_beacon_count", {"bsid": bsid, "count": passive_beacon_ammo.get(acting_sid, 0)})
    emit("lure_count", {"bsid": bsid, "count": lure_ammo.get(acting_sid, 0)})
    logging.info(f"[cheat] {p.get('id')} resupply (idkfa)")


@socketio.on("cheat_reload_ai")
def handle_cheat_reload_ai():
    """Vide le cache des arbres BT et recharge l'arbre de chaque bot vivant.
    Permet d'itérer sur les JSON sans redémarrer Flask."""
    bot_ai.reload_ai()
    for sid, bot in bots.items():
        if bot.get("external_control"):
            continue
        name = bot.get("ai_name") or "default"
        bot["ai_tree"] = bot_ai.load_ai(name)
    logging.info(f"[bt] Reloaded AI for {len(bots)} bots")
    emit("cheat_reload_ai_done", {"count": len(bots)})


@socketio.on("cheat_bots_calmdown")
def handle_cheat_bots_calmdown():
    global bots_passive
    bots_passive = not bots_passive
    logging.info(f"[calmdown] bots_passive={bots_passive}")
    emit("cheat_bots_calmdown_state", {"passive": bots_passive})


@socketio.on("cheat_debug_toggle")
def handle_cheat_debug_toggle(data):
    """Toggle une catégorie de debug log (grenades, torpilles, deplacement...)."""
    from debug_log import toggle_category, enabled_categories
    cat = (data or {}).get("category", "").strip()
    if not cat:
        return
    now_on = toggle_category(cat)
    logging.info(f"[debug] catégorie '{cat}' → {'ON' if now_on else 'OFF'} (actives: {enabled_categories()})")
    emit("cheat_debug_state", {"category": cat, "enabled": now_on, "all": enabled_categories()})


@socketio.on("cheat_debug_query")
def handle_cheat_debug_query():
    """Renvoie la liste des catégories actives."""
    from debug_log import enabled_categories
    emit("cheat_debug_state", {"all": enabled_categories()})


@socketio.on("cheat_debug_test")
def handle_cheat_debug_test(data):
    """Marque le début ou la fin d'un test dans les logs."""
    action = (data or {}).get("action", "")
    name = (data or {}).get("name", "").strip()
    if not name:
        return
    if action == "start":
        logging.info(f"{'='*60}")
        logging.info(f"[TEST] ===== DEBUT DE TEST : {name} =====")
        logging.info(f"{'='*60}")
    elif action == "end":
        logging.info(f"{'='*60}")
        logging.info(f"[TEST] ===== FIN DE TEST : {name} =====")
        logging.info(f"{'='*60}")


@socketio.on("cheat_kill_bot")
def handle_cheat_kill_bot():
    """Supprime le bot le plus proche du joueur."""
    sid = request.sid
    p = players.get(sid)
    if not p:
        return
    pos = p.get("position") or {}
    px = pos.get("x", 0)
    pz = pos.get("z", 0)
    best_sid = None
    best_dist = float("inf")
    for bsid, bot in bots.items():
        bp = bot.get("position") or {}
        dx = bp.get("x", 0) - px
        dz = bp.get("z", 0) - pz
        d = dx * dx + dz * dz
        if d < best_dist:
            best_dist = d
            best_sid = bsid
    if best_sid:
        bot = bots.get(best_sid)
        pid = bot["id"] if bot else best_sid
        logging.info(f"[cheat_kill_bot] removing bot {pid} (sid={best_sid})")
        if bot:
            sim.sink_bot(best_sid, bot, attacker_id=p.get("id"))


@socketio.on("change_boat")
def handle_change_boat():
    if request.sid in players:
        current_type = players[request.sid]["boatType"]
        new_type = "submarine" if current_type == "destroyer" else "destroyer"
        new_boat = load_boat(new_type)
        players[request.sid]["boatType"] = new_type
        players[request.sid]["boat"] = new_boat
        # Nettoyer les drones du joueur (changement de bateau = nouvelles munitions).
        pid = players[request.sid]["id"]
        for k in list(drones_server.keys()):
            if drones_server[k]["ownerPlayerId"] == pid:
                kill_server_drone(drones_server[k], reason="lost", refund=False)
                drones_server.pop(k, None)
        init_torpedo_ammo_for_sid(request.sid)
        init_drone_ammo_for_sid(request.sid)
        init_grenade_ammo_for_sid(request.sid)
        init_cannon_ammo_for_sid(request.sid)
        init_beacon_ammo_for_sid(request.sid)
        init_passive_beacon_ammo_for_sid(request.sid)
        init_lure_ammo_for_sid(request.sid)
        init_mine_ammo_for_sid(request.sid)
        init_player_integrity(request.sid)
        emit("boat_changed", {
            "boatType": new_type,
            "boat": new_boat,
            "torpedoCounts": dict(torpedo_ammo.get(request.sid) or {}),
            "droneCounts": dict(drone_ammo.get(request.sid) or {}),
            "grenadeCount": grenade_ammo.get(request.sid, 0),
            "cannonCounts": dict(cannon_ammo.get(request.sid) or {}),
            "beaconCount": beacon_ammo.get(request.sid, 0),
            "passiveBeaconCount": passive_beacon_ammo.get(request.sid, 0),
            "lureCount": lure_ammo.get(request.sid, 0),
            "mineCounts": dict(mine_ammo.get(request.sid) or {}),
        })
        emit("other_boat_changed", {
            "id": players[request.sid]["id"],
            "boat": new_boat,
        }, broadcast=True, include_self=False)


SEABED_FLOOR_Y = -(500 - 10) / UNIT_METERS_BOT  # -49 u, aligné sur le client.
DANGER_ZONE_OFFSET = 3.0  # u, anneau autour de chaque île (aligné sur game.js).
REGEN_DELAY_S = 5.0
REGEN_RATE_PER_S = 10.0 / (10.0 * 60.0)  # 10 pts en 10 minutes
REGEN_MAX_BUDGET = 10.0
REGEN_TOTAL_INITIAL = 20.0


def init_player_integrity(sid):
    """Phase D : délégué à Sim.init_player_integrity."""
    sim.init_player_integrity(sid)


def emit_integrity(sid, p):
    """Phase D : délégué à Sim._emit_integrity."""
    sim._emit_integrity(sid, p)


def apply_player_damage(sid, p, damage, attacker_id):
    """Phase D : délégué à Sim.apply_player_damage."""
    sim.apply_player_damage(sid, p, damage, attacker_id)


def sink_player(sid, p, attacker_id):
    """Phase D : délégué à Sim.sink_player."""
    sim.sink_player(sid, p, attacker_id)


def player_splash_damage(ex, ey, ez, base_damage, attacker_id, effect_radius_u):
    """Phase D : délégué à Sim.player_splash_damage."""
    sim.player_splash_damage(ex, ey, ez, base_damage, attacker_id, effect_radius_u)


def is_in_danger_zone(x, z, world_data):
    """Phase D : délégué à Sim.is_in_danger_zone."""
    return sim.is_in_danger_zone(x, z, world_data)


def update_player_integrity(dt, world_data):
    """Phase D : délégué à Sim.update_player_integrity."""
    sim.update_player_integrity(dt, world_data)



MOVE_VALIDATION_MARGIN = 3.0  # facteur de tolérance horizontale (* vmax * dt).
MOVE_VALIDATION_MIN_DT = 0.05
MOVE_VALIDATION_MAX_DT = 0.5
ADMIN_TELEPORT_THRESHOLD_U = 200.0  # cheat "move" = saut massif accepté.


def emit_position_correct(sid, p, reason):
    """Renvoie au client la dernière position serveur (anti-cheat / téléport)."""
    pos = p.get("position") or {"x": 0, "y": 0, "z": 0}
    logging.info(f"[position_correct] sid={sid} reason={reason} pos=({pos.get('x',0):.1f},{pos.get('z',0):.1f})")
    socketio.emit("position_correct", {
        "x": pos.get("x", 0),
        "y": pos.get("y", 0),
        "z": pos.get("z", 0),
        "rotation": float(p.get("rotation") or 0),
        "reason": reason,
    }, to=sid)


def validate_player_move(p, new_pos, world_data, now):
    """Retourne (ok, reason). Vérifie distance plausible, pas sur île, dans le
    monde, profondeur permise. La rotation et le speedRatio sont acceptés tels quels."""
    import math
    boat = p.get("boat") or {}
    boat_type = p.get("boatType") or ""
    # Marge de 40 m (4 u) avant le bord du monde : on n'accepte pas de mouvement
    # plus loin que cette limite (le bateau peut reculer pour en sortir).
    EDGE_MARGIN_U = 4.0
    half_w = world_data["ground"]["width"] / 2 - EDGE_MARGIN_U
    half_d = world_data["ground"]["depth"] / 2 - EDGE_MARGIN_U
    nx = float(new_pos.get("x", 0))
    nz = float(new_pos.get("z", 0))
    ny = float(new_pos.get("y", 0))
    last_pos = p.get("position") or {}
    cur_x = float(last_pos.get("x", 0))
    cur_z = float(last_pos.get("z", 0))
    # Test bord par axe : si le bateau est déjà au-delà sur un axe, on accepte
    # à condition qu'il se rapproche du centre (recul depuis hors-zone).
    def _axis_ok(n, c, half):
        if n < -half or n > half:
            return abs(n) < abs(c)  # se rapproche du centre = on tolère
        return True
    if not _axis_ok(nx, cur_x, half_w) or not _axis_ok(nz, cur_z, half_d):
        return False, "out_of_bounds"
    if point_on_any_island(nx, nz, world_data):
        return False, "on_island"
    # Profondeur autorisée pour sub.
    if boat_type == "submarine":
        max_depth_m = boat.get("maxDepthMeters", 200)
        flotation_m = boat.get("flotation", 2)
        # Le client autorise jusqu'à seabed (avec damage si dépassement) ; on
        # accepte la fenêtre [SEABED_FLOOR_Y - 0.5, surface + 0.1].
        surface_y = -flotation_m / UNIT_METERS_BOT
        if ny > surface_y + 0.1:
            return False, "above_surface"
        if ny < SEABED_FLOOR_Y - 0.5:
            return False, "below_seabed"
    else:
        # Destroyer flotte ; la position client est lue à boatFlotationY (légèrement
        # négative). Tolérance large.
        flotation_m = boat.get("flotation", 2)
        flotation_y = -flotation_m / UNIT_METERS_BOT
        if ny > flotation_y + 0.5 or ny < flotation_y - 0.5:
            return False, "destroyer_y"
    # Vitesse plausible.
    last_pos = p.get("position") or {}
    last_at = p.get("last_move_at")
    if last_pos and last_at is not None:
        dt = now - last_at
        if dt < MOVE_VALIDATION_MIN_DT:
            dt = MOVE_VALIDATION_MIN_DT
        if dt > MOVE_VALIDATION_MAX_DT:
            dt = MOVE_VALIDATION_MAX_DT
        max_speed_us = (boat.get("speed", 30) * 0.514444) / UNIT_METERS_BOT
        max_speed_us *= p.get("speed_mult", 1.0)
        # Multiplicateur global de vitesse simu (cheats time2/time4/time8) :
        # le client avance N× plus vite, on accepte des sauts proportionnels.
        max_horiz = max_speed_us * dt * MOVE_VALIDATION_MARGIN * sim_tick_multiplier
        dx = nx - last_pos.get("x", 0)
        dz = nz - last_pos.get("z", 0)
        if dx * dx + dz * dz > max_horiz * max_horiz:
            # Tolérer un téléport admin (cheat "move") : pas une triche typique
            # mais un saut massif (>200 u). On laisse passer.
            if dx * dx + dz * dz < ADMIN_TELEPORT_THRESHOLD_U * ADMIN_TELEPORT_THRESHOLD_U:
                return False, "speed"
    return True, None


# Cache du monde pour validate_player_move (évite de relire le JSON à chaque move).
_validate_world_cache = {"name": None, "world": None}


def _world_for_validation():
    if _validate_world_cache["name"] != current_map_name or _validate_world_cache["world"] is None:
        try:
            _validate_world_cache["world"] = load_world()
            _validate_world_cache["name"] = current_map_name
        except Exception as e:
            logging.warning(f"[validate] impossible de charger le monde: {e}")
            return None
    return _validate_world_cache["world"]


@socketio.on("ws_ping")
def handle_ws_ping(data):
    d = dict(data) if data else {}
    d["sts"] = time.time()  # server timestamp pour mesurer délai réseau aller
    emit("ws_pong", d)


@socketio.on("ws_rtt_report")
def handle_ws_rtt_report(data):
    d = data or {}
    _ws_diag["rtt_avg"]         = float(d.get("avg", 0))
    _ws_diag["rtt_p95"]         = d.get("p95", "?")
    _ws_diag["rtt_max"]         = float(d.get("max", 0))
    _ws_diag["rtt_n"]           = int(d.get("n", 0))
    _ws_diag["rtt_to_server"]   = d.get("toServer")
    _ws_diag["rtt_from_server"] = d.get("fromServer")


@socketio.on("move")
def handle_move(data):
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    p = players[acting_sid]
    new_pos = data.get("position") or {}
    world_data = _world_for_validation()
    now = time.time()
    if world_data is not None:
        ok, reason = validate_player_move(p, new_pos, world_data, now)
        if not ok:
            # On ne met pas à jour p["position"] : on renvoie la dernière connue.
            # La correction part au sid principal (le client n'a qu'un seul socket).
            emit_position_correct(request.sid, p, reason)
            return
    p["position"] = new_pos
    rotation = data.get("rotation", p.get("rotation", 0.0))
    p["rotation"] = rotation
    new_sr = data.get("speedRatio", 0.0)
    # Trace les transitions speedRatio importantes pour debug visibilitychange.
    old_sr = p.get("speedRatio", 0.0)
    if abs(new_sr - old_sr) > 0.3:
        logging.info(f"[move] sid={acting_sid} speedRatio {old_sr:.2f}→{new_sr:.2f} reverse={data.get('reverse')}")
    p["speedRatio"] = new_sr
    p["reverse"] = data.get("reverse", False)
    p["rudder"] = data.get("rudder", 0)
    p["last_move_at"] = now
    # Diag latence réseau : le client peut inclure _ts (time.time() JS / 1000)
    _client_ts = data.get("_ts")
    if _client_ts is not None:
        _latency_ms = (now - _client_ts) * 1000.0
        _ws_diag.setdefault("move_latency_sum", 0.0)
        _ws_diag.setdefault("move_latency_max", 0.0)
        _ws_diag.setdefault("move_latency_count", 0)
        _ws_diag["move_latency_sum"] += _latency_ms
        _ws_diag["move_latency_count"] += 1
        if _latency_ms > _ws_diag["move_latency_max"]:
            _ws_diag["move_latency_max"] = _latency_ms
    _sr = data.get("speedRatio", None)
    emit("player_moved", {
        "id": p["id"],
        "position": _round_pos(new_pos),
        "rotation": _r(rotation, 3),
        "rudder": _r(data.get("rudder", 0), 3),
        "reverse": data.get("reverse", False),
        "speedRatio": _r(_sr, 3) if _sr is not None else None,
        "integrity": _r(float(p.get("integrity", 100.0)), 1),
        "submerged": new_pos.get("y", 0) <= -5.0 / UNIT_METERS_BOT,
    }, broadcast=True, include_self=False)


@socketio.on("wake")
def handle_wake(data):
    if request.sid not in players:
        return
    data = data or {}
    x = data.get("x")
    z = data.get("z")
    if x is None or z is None:
        return
    emit("wake_spawned", {
        "id": players[request.sid]["id"],
        "x": x,
        "z": z,
        "submerged": data.get("submerged", False),
        "y": data.get("y"),
    }, broadcast=True, include_self=False)


@socketio.on("toggle_day_cycle")
def handle_toggle_day_cycle():
    state = day_cycle["state"]
    now = time.time()
    if state == "off":
        day_cycle["state"] = "running"
        day_cycle["startedAt"] = now
        day_cycle["startTimeOfDay"] = 0.5
        day_cycle["speed"] = 1.0
        day_cycle["endsAt"] = 0.0
    elif state == "running":
        current = current_time_of_day(now)
        signed = shortest_signed_distance(current, 0.5)
        speed = signed * DAY_DURATION / ENDING_TRANSITION_SECONDS
        day_cycle["state"] = "ending"
        day_cycle["startedAt"] = now
        day_cycle["startTimeOfDay"] = current
        day_cycle["speed"] = speed
        day_cycle["endsAt"] = now + ENDING_TRANSITION_SECONDS
    elif state == "ending":
        current = current_time_of_day(now)
        day_cycle["state"] = "running"
        day_cycle["startedAt"] = now
        day_cycle["startTimeOfDay"] = current
        day_cycle["speed"] = 1.0
        day_cycle["endsAt"] = 0.0
    emit("day_cycle_state", day_cycle_snapshot(), broadcast=True, include_self=True)


@socketio.on("day_cycle_done")
def handle_day_cycle_done():
    if day_cycle["state"] == "ending":
        day_cycle["state"] = "off"
        day_cycle["startedAt"] = 0.0
        day_cycle["startTimeOfDay"] = 0.0
        day_cycle["speed"] = 1.0
        day_cycle["endsAt"] = 0.0
        emit("day_cycle_state", day_cycle_snapshot(), broadcast=True, include_self=True)


@socketio.on("grenade_fire")
def handle_grenade_fire(data):
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    spawn_grenade(acting_sid, players[acting_sid], data or {})


@socketio.on("torpedo_fire")
def handle_torpedo_fire(data):
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    spawn_torpedo(acting_sid, players[acting_sid], data or {})


@socketio.on("torpedo_steer")
def handle_torpedo_steer(data):
    """Steering filoguidée : `yaw` (-1/0/+1) et `pitch` (-1/0/+1).
    Le client n'émet que sur changement (change-only)."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    pid = players[acting_sid]["id"]
    key = active_wire_torpedoes.get(pid)
    if not key:
        return
    t = torpedoes_server.get(key)
    if not t:
        return
    d = data or {}
    t["wireYaw"] = max(-1, min(1, int(d.get("yaw", 0) or 0)))
    t["wirePitch"] = max(-1, min(1, int(d.get("pitch", 0) or 0)))


@socketio.on("torpedo_self_destruct")
def handle_torpedo_self_destruct(data):
    """Bouton "détruire" : explose une torpille appartenant au tireur."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    pid = players[acting_sid]["id"]
    d = data or {}
    kind = d.get("kind")
    tid = d.get("tid")
    keys = []
    if tid is not None:
        keys.append((pid, tid))
    else:
        for k, t in torpedoes_server.items():
            if t["ownerPlayerId"] == pid and (kind is None or t["kind"] == kind):
                keys.append(k)
    for k in keys:
        t = torpedoes_server.get(k)
        if t:
            explode_server_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None)
            torpedoes_server.pop(k, None)


@socketio.on("lure_drop")
def handle_lure_drop(data):
    """Intent de largage de leurre acoustique. Le serveur valide ammo, calcule
    position derrière le bateau, alloue lid, broadcast."""
    import math
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    p = players[acting_sid]
    boat = p.get("boat") or {}
    spec = boat.get("acousticLures") or None
    if not spec:
        return
    if lure_ammo.get(acting_sid, 0) <= 0:
        return
    pos = p.get("position") or {}
    rotation = float(p.get("rotation") or 0)
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    # Stern offset ~1.5 u (≈ boatHalfLength + 1) — alignement avec le client.
    stern = 1.5
    x = pos.get("x", 0) + cos_r * stern
    z = pos.get("z", 0) - sin_r * stern
    boat_type = p.get("boatType") or ""
    y = pos.get("y", 0) if boat_type == "submarine" else 0.0
    noise = float(spec.get("noise", 0))
    duration_ms = float(spec.get("time", 0)) * 60.0 * 1000.0
    pid = p["id"]
    lid = next_lure_lid.get(pid, 1)
    next_lure_lid[pid] = lid + 1
    expires_at = time.time() + duration_ms / 1000.0
    server_lures[(pid, lid)] = {
        "ownerId": pid, "lid": lid,
        "x": x, "y": y, "z": z, "noise": noise,
        "expiresAt": expires_at,
    }
    lure_ammo[acting_sid] = max(0, lure_ammo.get(acting_sid, 0) - 1)
    emit_lure_count(acting_sid)
    socketio.emit("lure_dropped", {
        "ownerId": pid, "lid": lid,
        "x": x, "y": y, "z": z, "noise": noise,
        "durationMs": duration_ms,
    })


def _emit_mine_revealed(mine, target_team):
    """Notifie target_team que la mine devient visible sur leur radar."""
    payload = {"ownerId": mine["ownerId"], "mid": mine["mid"]}
    for sid_p, p_p in players.items():
        if p_p.get("team_id") == target_team:
            socketio.emit("mine_revealed", payload, to=sid_p)


def _emit_beacon_revealed(beacon, target_team):
    payload = {"bid": beacon["bid"]}
    for sid_p, p_p in players.items():
        if p_p.get("team_id") == target_team:
            socketio.emit("sonar_beacon_revealed", payload, to=sid_p)


def reveal_mines_and_beacons_by_ping(pinger_team, px, pz, range_u,
                                     cone_deg, rotation, world_data):
    """Pour chaque ping (bateau ou balise active), révèle aux ennemis :
    - les mines ennemies dans le rayon (LOS clear, cône). Bottom : ≥ 2× range mine.
    - les balises actives ennemies dans le rayon (LOS clear, cône)."""
    if not pinger_team:
        return
    range_u_sq = range_u * range_u
    half_cos = math.cos(math.radians(cone_deg) / 2.0) if cone_deg < 360 else -2.0
    fwd_x = -math.cos(rotation) if cone_deg < 360 else 0.0
    fwd_z = math.sin(rotation) if cone_deg < 360 else 0.0
    active_teams = {p.get("team_id") for p in players.values() if p.get("team_id")}
    for m in mines_server.values():
        m.setdefault("revealedTeams", set()).intersection_update(active_teams)
        m_team = m.get("teamId")
        if not m_team or m_team == pinger_team:
            continue
        if pinger_team in m.get("revealedTeams", set()):
            continue
        dx = m["x"] - px
        dz = m["z"] - pz
        d2 = dx * dx + dz * dz
        if d2 > range_u_sq:
            continue
        if cone_deg < 360 and d2 > 0:
            ln = math.sqrt(d2)
            dot = (dx * fwd_x + dz * fwd_z) / ln
            if dot < half_cos:
                continue
        # Mines de fond : require dist ≥ 2× mine.range (mines profondes plus furtives).
        if m.get("kind") == "bottom":
            mine_range_u = float(m.get("range", 60)) / UNIT_METERS_BOT
            if d2 < (2 * mine_range_u) * (2 * mine_range_u):
                continue
        if world_data and not line_of_sight_clear(px, pz, m["x"], m["z"], world_data):
            continue
        m.setdefault("revealedTeams", set()).add(pinger_team)
        _emit_mine_revealed(m, pinger_team)
    for b in sonar_beacons.values():
        b.setdefault("revealedTeams", set()).intersection_update(active_teams)
        b_team = b.get("teamId")
        if not b_team or b_team == pinger_team:
            continue
        if pinger_team in b.get("revealedTeams", set()):
            continue
        dx = b["x"] - px
        dz = b["z"] - pz
        d2 = dx * dx + dz * dz
        if d2 > range_u_sq:
            continue
        if cone_deg < 360 and d2 > 0:
            ln = math.sqrt(d2)
            dot = (dx * fwd_x + dz * fwd_z) / ln
            if dot < half_cos:
                continue
        if world_data and not line_of_sight_clear(px, pz, b["x"], b["z"], world_data):
            continue
        b["revealedTeams"].add(pinger_team)
        _emit_beacon_revealed(b, pinger_team)


@socketio.on("sonar_ping")
def handle_sonar_ping(data):
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    p = players[acting_sid]
    boat = p.get("boat") or {}
    active_sonar = boat.get("activeSonar") or {}
    short_angle = float(active_sonar.get("shortAngle", 30))
    large_angle = float(active_sonar.get("largeAngle", 120))
    short_range = float(active_sonar.get("shortAngleRange", 5000))
    large_range = float(active_sonar.get("largeAngleRange", 2500))
    reveal_m = float(active_sonar.get("reveal", 15000))
    cone_deg = float(data.get("coneDeg") or 360)
    rotation = float(data.get("rotation") or 0)
    # Détermine la portée selon l'angle du ping (tolérance ±0.5°).
    if abs(cone_deg - short_angle) < 0.5:
        range_m = short_range
    elif abs(cone_deg - large_angle) < 0.5:
        range_m = large_range
    else:
        # Override explicite ou valeur inattendue : utilise rangeMeters envoyé sinon court.
        range_m = float(data.get("rangeMeters") or short_range)
    emit("sonar_pinged", {
        "id": p["id"],
        "x": float(data.get("x", 0)),
        "z": float(data.get("z", 0)),
        "y": float((p.get("position") or {}).get("y", 0)),
        "coneDeg": cone_deg,
        "rotation": rotation,
        "range": range_m,
        "reveal": reveal_m,
    }, broadcast=True, include_self=False)
    # Notifier les bots dans le cône de révélation qu'ils ont été pingés.
    reveal_u = reveal_m / UNIT_METERS_BOT
    px, pz = float(data.get("x", 0)), float(data.get("z", 0))
    py = float((p.get("position") or {}).get("y", 0))
    half_cos = math.cos(math.radians(cone_deg) / 2.0) if cone_deg < 360 else -2.0
    fwd_x = -math.cos(rotation)
    fwd_z = math.sin(rotation)
    now = time.time()
    world_data = _world_for_validation()
    for bot in bots.values():
        bpos = bot.get("position") or {}
        bx, bz = bpos.get("x", 0), bpos.get("z", 0)
        dx, dz = bx - px, bz - pz
        d2 = dx * dx + dz * dz
        if d2 > reveal_u * reveal_u:
            continue
        if cone_deg < 360 and d2 > 0:
            ln = math.sqrt(d2)
            dot = (dx * fwd_x + dz * fwd_z) / ln
            if dot < half_cos:
                continue
        if world_data and not line_of_sight_clear(px, pz, bx, bz, world_data):
            continue
        # Le sonar actif ne franchit PAS une thermocline (sauf pénétration aléatoire).
        if world_data and count_thermoclines_crossed(px, py, pz, bx, bpos.get("y", 0), bz,
                                                      world_data, UNIT_METERS_BOT) > 0:
            tc_pen = float(active_sonar.get("thermoclinePenetration", 0))
            if tc_pen <= 0 or random.random() >= tc_pen:
                continue
        bb = bot.setdefault("bb", {})
        bb["pinged_at"] = now
        bb["pinged_by_pos"] = {"x": px, "z": pz, "id": p["id"]}
    # Révélation des mines/balises ennemies vues par le ping (rayon = range_m du ping).
    pinger_team = p.get("team_id")
    reveal_mines_and_beacons_by_ping(pinger_team, px, pz, range_m / UNIT_METERS_BOT,
                                     cone_deg, rotation, world_data)


@socketio.on("drone_launch")
def handle_drone_launch(data):
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    spawn_drone(acting_sid, players[acting_sid], data or {})


@socketio.on("drone_steer")
def handle_drone_steer(data):
    """Steering du drone manuel : yaw, throttle, climb (-1/0/+1) change-only."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    pid = players[acting_sid]["id"]
    d = data or {}
    did = d.get("did")
    if did is None:
        # Cherche le drone manuel actif du tireur.
        for (op, dd), drone in drones_server.items():
            if op == pid and drone["kind"] == "manual" and not drone.get("returning"):
                did = dd
                break
    if did is None:
        return
    drone = drones_server.get((pid, did))
    if not drone or drone["kind"] != "manual":
        return
    drone["steerYaw"] = max(-1, min(1, int(d.get("yaw", 0) or 0)))
    drone["steerThrottle"] = max(-1, min(1, int(d.get("throttle", 0) or 0)))
    drone["steerClimb"] = max(-1, min(1, int(d.get("climb", 0) or 0)))


@socketio.on("drone_recall")
def handle_drone_recall(data):
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    pid = players[acting_sid]["id"]
    kind = (data or {}).get("kind")
    for (op, did), drone in drones_server.items():
        if op == pid and (kind is None or drone["kind"] == kind):
            drone["returning"] = True


@socketio.on("drone_self_destruct")
def handle_drone_self_destruct(data):
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    pid = players[acting_sid]["id"]
    d = data or {}
    did = d.get("did")
    keys = []
    if did is not None:
        keys.append((pid, did))
    else:
        for k, drone in drones_server.items():
            if k[0] == pid:
                keys.append(k)
    for k in keys:
        drone = drones_server.get(k)
        if drone:
            kill_server_drone(drone, reason="lost", refund=False)
            drones_server.pop(k, None)


@socketio.on("cannon_fire")
def handle_cannon_fire(data):
    """Intent de tir canon ou DCA d'un joueur humain. Le serveur valide la cible,
    calcule hit/miss, broadcast le tracer et planifie l'application des dégâts."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    fire_cannon_intent(acting_sid, players[acting_sid], data or {})


# Garde-fous contre des cartes aberrantes envoyées par le client (tailles non
# bornées → gros nav_graph / gros fichiers / rendu démesuré côté client).
MAX_MAP_KM = 200.0     # dimension max de la carte en kilomètres
MAX_ISLANDS = 500      # nombre max d'îles par carte


def _validate_world_size(world):
    """Lève ValueError si la carte dépasse les bornes acceptées."""
    ground = world.get("ground") or {}
    w = float(ground.get("width", 0))
    d = float(ground.get("depth", 0))
    max_u = MAX_MAP_KM * 100  # 1 km = 100 unités Babylon
    if not (0 < w <= max_u and 0 < d <= max_u):
        raise ValueError(f"Dimensions de carte invalides ({w}x{d})")
    if len(world.get("islands") or []) > MAX_ISLANDS:
        raise ValueError(f"Trop d'îles ({len(world['islands'])} > {MAX_ISLANDS})")


@socketio.on("admin_load_map")
def handle_admin_load_map(data):
    global current_map_name
    name = (data or {}).get("name", "").strip()
    try:
        path = map_path(name)
        with open(path, "r") as f:
            world = json.load(f)
    except Exception as e:
        emit("admin_error", {"message": f"Erreur chargement: {e}"})
        return
    current_map_name = name
    write_current_map_name(name)
    emit("admin_world_loaded", {"world": world, "name": name})


@socketio.on("admin_create_map")
def handle_admin_create_map(data):
    global current_map_name
    data = data or {}
    name = data.get("name", "").strip()
    try:
        width_km = max(0.5, min(MAX_MAP_KM, float(data.get("widthKm", 4))))
        depth_km = max(0.5, min(MAX_MAP_KM, float(data.get("depthKm", 2))))
        path = map_path(name)
        if os.path.exists(path):
            emit("admin_error", {"message": "Carte existe déjà"})
            return
        world = {
            "ground": {
                "width": int(width_km * 100),
                "depth": int(depth_km * 100),
                "color": "#4fb5cc",
            },
            "islands": [],
        }
        world["nav_graph"] = nav_graph.build_nav_graph(world, unit_meters=UNIT_METERS_BOT)
        os.makedirs(MAPS_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(world, f, indent=2)
        current_map_name = name
        write_current_map_name(name)
        emit("admin_world_loaded", {"world": world, "name": name})
    except Exception as e:
        emit("admin_error", {"message": str(e)})


@socketio.on("admin_copy_map")
def handle_admin_copy_map(data):
    global current_map_name
    data = data or {}
    name = (data.get("name") or "").strip()
    world = data.get("world")
    try:
        path = map_path(name)
        if os.path.exists(path):
            emit("admin_error", {"message": "Carte existe déjà"})
            return
        if not isinstance(world, dict) or "ground" not in world or "islands" not in world:
            raise ValueError("Données carte invalides")
        _validate_world_size(world)
        world["nav_graph"] = nav_graph.build_nav_graph(world, unit_meters=UNIT_METERS_BOT)
        os.makedirs(MAPS_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(world, f, indent=2)
        current_map_name = name
        write_current_map_name(name)
        emit("admin_world_loaded", {"world": world, "name": name})
    except Exception as e:
        emit("admin_error", {"message": str(e)})


@socketio.on("admin_list_textures")
def handle_admin_list_textures():
    """Liste toutes les images jpg/png/gif disponibles dans images/ pour
    habiller le plateau des îles."""
    import os
    ALLOWED_EXTS = (".jpg", ".jpeg", ".png", ".gif")
    textures = []
    images_dir = os.path.join(os.path.dirname(__file__), "images")
    try:
        for fname in sorted(os.listdir(images_dir)):
            if not fname.lower().endswith(ALLOWED_EXTS):
                continue
            name = os.path.splitext(fname)[0]
            textures.append({"name": name, "url": f"/images/{fname}"})
    except FileNotFoundError:
        pass
    emit("admin_textures_list", {"textures": textures})


@socketio.on("admin_save_map")
def handle_admin_save_map(data):
    data = data or {}
    name = (data.get("name") or "").strip()
    world = data.get("world")
    try:
        path = map_path(name)
        if not isinstance(world, dict) or "ground" not in world or "islands" not in world:
            raise ValueError("Données carte invalides")
        _validate_world_size(world)
        world["nav_graph"] = nav_graph.build_nav_graph(world, unit_meters=UNIT_METERS_BOT)
        with open(path, "w") as f:
            json.dump(world, f, indent=2)
        emit("admin_save_ok", {"name": name})
    except Exception as e:
        emit("admin_error", {"message": str(e)})


@socketio.on("spawn_bot")
def handle_spawn_bot(data):
    if len(bots) >= MAX_BOTS:
        logging.warning(f"[spawn_bot] limite atteinte ({MAX_BOTS})")
        return
    data = data or {}
    boat_type = data.get("boatType", "submarine")
    if boat_type not in BOAT_TYPES:
        boat_type = "submarine"
    ai_name = data.get("ai")  # facultatif : override de l'IA par défaut
    team_id = data.get("team_id")
    team_name = data.get("team_name")
    bot_id = spawn_bot(boat_type, ai_name=ai_name, team_id=team_id, team_name=team_name)
    emit("bot_spawned", {"id": bot_id, "boatType": boat_type, "ai": ai_name or "default"})


def _owner_socket_sid(sid):
    """Pour un sid réel humain, renvoie sid. Pour un sid secondaire __own__,
    renvoie le sid du propriétaire humain (= la vraie socket). Pour un bot,
    renvoie None (pas de UI à informer)."""
    if not sid:
        return None
    if sid.startswith("__bot__"):
        return None
    return human_owner_sid.get(sid, sid)


def _bsid_for(sid):
    """Champ `bsid` à inclure dans les emits ammo : None si bateau primaire,
    sinon le sid synthétique. Le client utilise cette clé pour dispatcher
    dans son tableau de bateaux."""
    return sid if sid in human_owner_sid else None


def resolve_acting_sid(request_sid, data):
    """Multi-bateaux : le client peut envoyer un champ `bsid` pour cibler un
    de ses bateaux secondaires. Renvoie le sid à utiliser pour les handlers
    d'intent (ammo, position, etc.). Sans `bsid` ou si le bateau n'appartient
    pas au demandeur, on retombe sur request_sid (bateau primaire)."""
    bsid = (data or {}).get("bsid")
    if bsid and human_owner_sid.get(bsid) == request_sid and bsid in players:
        return bsid
    return request_sid


@socketio.on("set_sim_speed")
def handle_set_sim_speed(data):
    """Cheats time1/time2/time4/time8 : multiplicateur global de vitesse de simu."""
    global sim_tick_multiplier
    n = (data or {}).get("multiplier", 1)
    try:
        n = int(n)
    except Exception:
        n = 1
    if n not in (1, 2, 4, 8):
        return
    sim_tick_multiplier = n
    logging.info(f"[cheat] sim_tick_multiplier = ×{n}")
    socketio.emit("sim_speed_changed", {"multiplier": n})


@socketio.on("pause_active_boat")
def handle_pause_active_boat(data):
    """Le client a perdu le focus (visibilitychange) : son bateau actif passe
    en autopilote serveur pour continuer à avancer. Tous les bateaux du joueur
    sont alors autopilotés. Le flag `_paused_by_visibility` désactive l'arrêt
    défensif (ahead_in_danger) — le bateau garde sa vitesse."""
    if request.sid not in players:
        return
    owned = player_boats_sids.get(request.sid, [request.sid])
    for s in owned:
        autopiloted_sids.add(s)
        if s in players:
            players[s].pop("_autopilot_state", None)
            players[s]["_paused_by_visibility"] = True
            sr = players[s].get("speedRatio", 0)
            logging.info(f"[pause] {s} → autopilot, speedRatio={sr:.2f} reverse={players[s].get('reverse')}")


@socketio.on("resume_active_boat")
def handle_resume_active_boat(data):
    """Le focus est revenu : le client reprend le contrôle du bateau actif
    indiqué par bsid (ou primaire si absent)."""
    if request.sid not in players:
        return
    bsid = (data or {}).get("bsid")
    target_sid = bsid if bsid else request.sid
    if target_sid != request.sid and human_owner_sid.get(target_sid) != request.sid:
        return
    if target_sid in players:
        autopiloted_sids.discard(target_sid)
        players[target_sid].pop("_autopilot_state", None)
        players[target_sid].pop("_paused_by_visibility", None)
        # Téléporte le client à la position serveur courante : pendant la pause
        # le bateau a continué à avancer en autopilote, le client ne sait pas
        # où il est rendu.
        emit_position_correct(request.sid, players[target_sid], "resume")


@socketio.on("set_active_boat")
def handle_set_active_boat(data):
    """Le client signale quel bateau est désormais piloté manuellement. Tous
    les autres bateaux du joueur passent en autopilote serveur."""
    if request.sid not in players:
        return
    bsid = (data or {}).get("bsid")
    # bsid None → bateau primaire actif.
    target_sid = bsid if bsid else request.sid
    if target_sid != request.sid and human_owner_sid.get(target_sid) != request.sid:
        return
    if target_sid not in players:
        return
    owned = player_boats_sids.get(request.sid, [request.sid])
    for s in owned:
        if s == target_sid:
            autopiloted_sids.discard(s)
            # Reset état machine pour qu'au prochain Tab vers ce bateau,
            # l'autopilote reparte en "cruise" et pas en "stopped".
            if s in players:
                players[s].pop("_autopilot_state", None)
        else:
            autopiloted_sids.add(s)
            if s in players:
                players[s].pop("_autopilot_state", None)


@socketio.on("add_player_boat")
def handle_add_player_boat(data):
    """Cheat addsub/adddest : ajoute un bateau secondaire que le joueur pilote.
    Le bateau apparaît à 300 m à tribord, est broadcast comme un participant
    indépendant. Sid synthétique f"__own__<sid>__<n>"."""
    import math
    if request.sid not in players:
        return
    if len(player_boats_sids.get(request.sid, [request.sid])) >= MAX_PLAYER_BOATS:
        logging.warning(f"[add_player_boat] limite atteinte pour sid={request.sid[:8]}")
        return
    boat_type = (data or {}).get("boatType")
    if boat_type not in BOAT_TYPES:
        return
    primary = players[request.sid]
    pos = primary.get("position") or {}
    rot = float(primary.get("rotation") or 0)
    world = load_world()
    # Convention serveur : avant = (-cos, sin). Tribord = (sin, cos).
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    # Marge minimale aux îles : 30 m pour que le bateau ne soit pas coincé
    # contre une paroi (longueur destroyer ~100m, on lui laisse au moins 3u).
    MIN_ISLAND_DIST_U = 3.0  # 30 m
    sx = sz = None
    # On cherche un côté libre (tribord, bâbord, arrière, avant) à 100m.
    candidates = [
        (sin_r, cos_r),     # tribord
        (-sin_r, -cos_r),   # bâbord
        (cos_r, -sin_r),    # arrière
        (-cos_r, sin_r),    # avant
    ]
    offset_u = 100.0 / UNIT_METERS_BOT
    for dx, dz in candidates:
        cx = pos.get("x", 0) + dx * offset_u
        cz = pos.get("z", 0) + dz * offset_u
        if point_on_any_island(cx, cz, world):
            continue
        if geometry.min_distance_to_islands(cx, cz, world, cap=MIN_ISLAND_DIST_U) < MIN_ISLAND_DIST_U:
            continue
        sx, sz = cx, cz
        break
    if sx is None:
        # Aucun côté libre près du primaire : fallback ocean random valide.
        sx, sz = _random_spawn_on_nav_graph(world, players)
    n = len(player_boats_sids.get(request.sid, [request.sid]))
    ghost_sid = f"__own__{request.sid}__{n}"
    new_pid = str(uuid.uuid4())[:8]
    boat_data = load_boat(boat_type)
    flotation_m = boat_data.get("flotation", 2)
    flotation_y = -flotation_m / UNIT_METERS_BOT
    spawn_y = flotation_y if boat_type == "destroyer" else flotation_y - 0.05
    players[ghost_sid] = {
        "id": new_pid,
        "boatType": boat_type,
        "boat": boat_data,
        "position": {"x": sx, "y": spawn_y, "z": sz},
        "rotation": rot,
        "owner_sid": request.sid,
        "team_id": primary.get("team_id"),
        "team_name": primary.get("team_name"),
    }
    init_torpedo_ammo_for_sid(ghost_sid)
    init_drone_ammo_for_sid(ghost_sid)
    init_grenade_ammo_for_sid(ghost_sid)
    init_cannon_ammo_for_sid(ghost_sid)
    init_beacon_ammo_for_sid(ghost_sid)
    init_passive_beacon_ammo_for_sid(ghost_sid)
    init_lure_ammo_for_sid(ghost_sid)
    init_mine_ammo_for_sid(ghost_sid)
    init_player_integrity(ghost_sid)
    human_owner_sid[ghost_sid] = request.sid
    player_boats_sids.setdefault(request.sid, [request.sid]).append(ghost_sid)
    # Le bateau secondaire démarre en autopilote (le joueur reste sur son
    # bateau actif jusqu'à ce qu'il fasse Tab).
    autopiloted_sids.add(ghost_sid)
    # Broadcast comme un participant indépendant (autres joueurs verront un
    # nouveau bateau exactement comme un humain ou bot).
    socketio.emit("player_joined", players[ghost_sid])
    emit("own_boat_added", {
        "ghostSid": ghost_sid,
        "playerId": new_pid,
        "boatType": boat_type,
        "boat": boat_data,
        "position": players[ghost_sid]["position"],
        "rotation": rot,
        "torpedoCounts": dict(torpedo_ammo.get(ghost_sid) or {}),
        "droneCounts": dict(drone_ammo.get(ghost_sid) or {}),
        "grenadeCount": grenade_ammo.get(ghost_sid, 0),
        "cannonCounts": dict(cannon_ammo.get(ghost_sid) or {}),
        "beaconCount": beacon_ammo.get(ghost_sid, 0),
        "lureCount": lure_ammo.get(ghost_sid, 0),
        "mineCounts": dict(mine_ammo.get(ghost_sid) or {}),
    })


@socketio.on("sonar_beacon_place")
def handle_sonar_beacon_place(data):
    global next_beacon_id
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    if len(sonar_beacons) >= MAX_WORLD_SONAR_BEACONS:
        logging.warning(f"[sonar_beacon_place] limite globale atteinte ({MAX_WORLD_SONAR_BEACONS})")
        return
    p = players[acting_sid]
    boat = p.get("boat") or {}
    spec = boat.get("sonarBeacons") or None
    if not spec:
        return
    if beacon_ammo.get(acting_sid, 0) <= 0:
        return
    # Sub immergé ne peut pas larguer une balise.
    pos = p.get("position") or {}
    boat_type = p.get("boatType") or ""
    if boat_type == "submarine":
        flotation_m = boat.get("flotation", 2)
        surface_y = -flotation_m / UNIT_METERS_BOT
        if pos.get("y", 0) < surface_y - 0.05:
            return
    # Position : on prend celle du joueur côté serveur (plus sûr que data).
    bid = next_beacon_id
    next_beacon_id += 1
    beacon = {
        "bid": bid,
        "ownerId": p["id"],
        "ownerSid": acting_sid,                 # interne (pas envoyé client)
        "teamId": p.get("team_id"),
        "rangeMeters": float(spec.get("rangeMeters", 1000)),
        "thermoclinePenetration": float(spec.get("thermoclinePenetration", 0)),
        "x": pos.get("x", 0),
        "z": pos.get("z", 0),
        "placedAt": time.time(),
        "revealedTeams": set(),                 # teams qui l'ont découverte (interne)
    }
    sonar_beacons[bid] = beacon
    beacon_ammo[acting_sid] = max(0, beacon_ammo.get(acting_sid, 0) - 1)
    emit_beacon_count(acting_sid)
    pub = {k: v for k, v in beacon.items() if k not in ("ownerSid", "revealedTeams")}
    # Broadcast à tous (le client masque sur radar selon teamId/revealedByMyTeam).
    socketio.emit("sonar_beacon_placed", pub)


@socketio.on("passive_sonar_beacon_place")
def handle_passive_sonar_beacon_place(data):
    """Pose une balise sonar passive : ne ping pas, détecte en continu les
    bateaux audibles en LOS, ne révèle l'info qu'à l'équipe du propriétaire."""
    global next_passive_beacon_id
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    if len(passive_sonar_beacons) >= MAX_WORLD_PASSIVE_BEACONS:
        logging.warning(f"[passive_sonar_beacon_place] limite globale atteinte ({MAX_WORLD_PASSIVE_BEACONS})")
        return
    p = players[acting_sid]
    boat = p.get("boat") or {}
    spec = boat.get("passiveSonarBeacons") or None
    if not spec:
        return
    if passive_beacon_ammo.get(acting_sid, 0) <= 0:
        return
    pos = p.get("position") or {}
    bid = next_passive_beacon_id
    next_passive_beacon_id += 1
    beacon = {
        "bid": bid,
        "ownerId": p["id"],
        "ownerSid": acting_sid,           # interne (pour cleanup, pas envoyé client)
        "teamId": p.get("team_id"),       # filtre côté client pour révélation
        "minNoise": float(spec.get("minNoise", 20)),
        "x": pos.get("x", 0),
        "z": pos.get("z", 0),
        "y": pos.get("y", 0),
        "placedAt": time.time(),
    }
    passive_sonar_beacons[bid] = beacon
    passive_beacon_ammo[acting_sid] = max(0, passive_beacon_ammo.get(acting_sid, 0) - 1)
    emit_passive_beacon_count(acting_sid)
    # Payload diffusé : on retire le champ interne ownerSid.
    pub = {k: v for k, v in beacon.items() if k != "ownerSid"}
    emit("passive_sonar_beacon_placed", pub, broadcast=True, include_self=True)


@socketio.on("mine_place")
def handle_mine_place(data):
    """Pose une mine (kind: surface | bottom | suspended) à la position du
    bateau. cableMeters utilisé uniquement pour suspended (longueur du câble
    depuis le fond)."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    kind = (data or {}).get("kind") or ""
    try:
        depth_m = float((data or {}).get("depthMeters", 20.0))
    except (TypeError, ValueError):
        depth_m = 20.0
    if not sim.place_mine(acting_sid, players[acting_sid], kind, depth_m):
        logging.debug("[mine_place] pose refusée pour %s (%s)", acting_sid, kind)


_mine_payload = simulation.mine_payload


@socketio.on("mine_spotted")
def handle_mine_spotted(data):
    """Le joueur a aperçu visuellement une mine (clic 3D). On la marque comme
    découverte pour sa team, qui la verra désormais sur le radar."""
    if request.sid not in players:
        return
    p = players[request.sid]
    team = p.get("team_id")
    if not team:
        return
    try:
        owner_id = data.get("ownerId")
        mid = int(data.get("mid"))
    except (TypeError, ValueError, AttributeError):
        return
    mine = mines_server.get((owner_id, mid))
    if mine is None:
        return
    if mine.get("teamId") == team:
        return  # déjà visible (notre mine)
    revealed_teams = mine.setdefault("revealedTeams", set())
    active_teams = {player.get("team_id") for player in players.values() if player.get("team_id")}
    revealed_teams.intersection_update(active_teams)
    if team in revealed_teams:
        return
    revealed_teams.add(team)
    _emit_mine_revealed(mine, team)


@socketio.on("mine_disarm")
def handle_mine_disarm(data):
    """Désamorce une mine que le joueur a posée. Conditions : être le poseur,
    être à ≤ 200 m de la mine. La mine est retirée et la munition restituée."""
    if request.sid not in players:
        return
    acting_sid = resolve_acting_sid(request.sid, data)
    if acting_sid not in players:
        return
    p = players[acting_sid]
    pid = p["id"]
    try:
        owner_id = data.get("ownerId")
        mid = int(data.get("mid"))
    except (TypeError, ValueError):
        return
    if owner_id != pid:
        return  # seul le poseur peut désamorcer
    mine = mines_server.get((owner_id, mid))
    if mine is None:
        return
    pos = p.get("position") or {}
    dx = (pos.get("x", 0) - mine["x"]) * UNIT_METERS_BOT
    dz = (pos.get("z", 0) - mine["z"]) * UNIT_METERS_BOT
    if (dx * dx + dz * dz) ** 0.5 > 200.0:
        return  # trop loin
    # Restitue la munition + retire la mine.
    kind = mine["kind"]
    ammo = mine_ammo.get(acting_sid)
    if ammo is None:
        init_mine_ammo_for_sid(acting_sid)
        ammo = mine_ammo.get(acting_sid) or {}
    ammo[kind] = ammo.get(kind, 0) + 1
    mines_server.pop((owner_id, mid), None)
    emit_mine_counts(acting_sid)
    socketio.emit("mine_dead", {"ownerId": owner_id, "mid": mid})


@socketio.on("sonar_beacon_destroy")
def handle_sonar_beacon_destroy(data):
    bid = int(data.get("bid", -1))
    if bid in sonar_beacons:
        del sonar_beacons[bid]
        emit("sonar_beacon_destroyed", {"bid": bid}, broadcast=True, include_self=True)


def segment_min_island_distance(x1, z1, x2, z2, world_data, cap=None):
    """Phase E : délégué à Sim.segment_min_island_distance."""
    return sim.segment_min_island_distance(x1, z1, x2, z2, world_data, cap=cap)


def pick_bot_waypoint(bot, world_data):
    """Phase E : délégué à Sim.pick_bot_waypoint."""
    return sim.pick_bot_waypoint(bot, world_data)


def _random_spawn_on_nav_graph(world_data, players_dict):
    """Spawn près d'un nœud du graphe de navigation (= sur la route que les bots
    empruntent). Utilisé pour bots ET humains pour que tout le monde ait les
    mêmes chances. Respecte la distance min des autres bateaux, fallback sur
    random_ocean_position si rien ne convient."""
    ng = world_data.get("nav_graph") or {}
    nodes = ng.get("nodes") or []
    if not nodes:
        return random_ocean_position(world_data, players_dict)
    others = []
    for p in (players_dict or {}).values():
        pos = p.get("position")
        if pos:
            others.append((pos.get("x", 0), pos.get("z", 0)))
    ground = world_data.get("ground") or {}
    map_w = ground.get("width", 400)
    map_d = ground.get("depth", 200)
    map_diag_u = (map_w ** 2 + map_d ** 2) ** 0.5
    min_dist_u = map_diag_u * 0.25
    half_w = map_w / 2 - 2.0
    half_d = map_d / 2 - 2.0
    edges = ng.get("edges") or []
    connected = set()
    for a, b in edges:
        connected.add(a)
        connected.add(b)
    # Ne garder que les nœuds avec au moins 2 voisins (pas les culs-de-sac).
    adj_count = {}
    for a, b in edges:
        adj_count[a] = adj_count.get(a, 0) + 1
        adj_count[b] = adj_count.get(b, 0) + 1
    candidates = [ni for ni in range(len(nodes))
                  if adj_count.get(ni, 0) >= 2
                  and abs(nodes[ni]["x"]) <= half_w
                  and abs(nodes[ni]["z"]) <= half_d]
    if not candidates:
        candidates = [ni for ni in range(len(nodes))
                      if ni in connected
                      and abs(nodes[ni]["x"]) <= half_w
                      and abs(nodes[ni]["z"]) <= half_d]
    random.shuffle(candidates)
    for ni in candidates:
        x = nodes[ni]["x"]
        z = nodes[ni]["z"]
        if point_on_any_island(x, z, world_data):
            continue
        too_close = False
        for ox, oz in others:
            if (x - ox) ** 2 + (z - oz) ** 2 < min_dist_u * min_dist_u:
                too_close = True
                break
        if too_close:
            continue
        if others:
            min_d_m = min(((x - ox) ** 2 + (z - oz) ** 2) ** 0.5 for ox, oz in others) * UNIT_METERS_BOT
            logging.info(f"[spawn] nœud #{ni} à ({x:.0f},{z:.0f}), distance min aux autres: {min_d_m:.0f} m (seuil {min_dist_u*UNIT_METERS_BOT:.0f} m)")
        return x, z
    # Aucun nœud ne respecte la distance min : prendre le nœud LE PLUS LOIN
    # des autres bateaux (et hors île).
    logging.warning(f"[spawn] FALLBACK : aucun nœud à ≥ {min_dist_u*UNIT_METERS_BOT:.0f} m de {len(others)} autres bateaux")
    best_ni = None
    best_min_d2 = -1.0
    for ni in candidates:
        x = nodes[ni]["x"]
        z = nodes[ni]["z"]
        if point_on_any_island(x, z, world_data):
            continue
        if not others:
            best_ni = ni
            break
        d2_min = min((x - ox) ** 2 + (z - oz) ** 2 for ox, oz in others)
        if d2_min > best_min_d2:
            best_min_d2 = d2_min
            best_ni = ni
    if best_ni is not None:
        x = nodes[best_ni]["x"]
        z = nodes[best_ni]["z"]
        min_d_m = best_min_d2 ** 0.5 * UNIT_METERS_BOT if others else 0
        logging.warning(f"[spawn] fallback nœud #{best_ni}, distance min: {min_d_m:.0f} m")
        return x, z
    return random_ocean_position(world_data, players_dict)


def spawn_bot(boat_type, ai_name=None, team_id=None, team_name=None):
    global next_bot_id
    boat_data = load_boat(boat_type)
    world_data = load_world()
    spawn_x, spawn_z = _random_spawn_on_nav_graph(world_data, players)
    bot_pid = f"bot{next_bot_id:03d}"
    next_bot_id += 1
    sid = f"__bot__{bot_pid}"
    flotation = boat_data.get("flotation", 2)
    surface_y = -flotation / UNIT_METERS_BOT
    rotation = random.uniform(0, 6.2832)
    max_speed_kn = boat_data.get("speed", 25)
    max_speed_us = max_speed_kn * 0.514444 / UNIT_METERS_BOT
    max_depth_m = boat_data.get("maxDepthMeters", 200) if boat_type == "submarine" else 0
    # Les bots sous-marins ne sortent jamais en surface : ils spawnent à profondeur
    # de plongée aléatoire (entre 30 m et 70 % de leur profondeur max).
    if boat_type == "submarine":
        min_depth_m = 30
        depth_m = random.uniform(min_depth_m, max(min_depth_m + 1, max_depth_m * 0.7))
        spawn_y = -depth_m / UNIT_METERS_BOT
    else:
        spawn_y = surface_y
    bot = {
        "sid": sid,
        "id": bot_pid,
        "boatType": boat_type,
        "boat": boat_data,
        "position": {"x": spawn_x, "y": spawn_y, "z": spawn_z},
        "rotation": rotation,
        "rudder": 0.0,
        "speed": 0.0,
        "max_speed_us": max_speed_us,
        "cruise_us": max_speed_us * 0.6,
        "base_max_speed_us": max_speed_us,
        "base_cruise_us": max_speed_us * 0.6,
        "rudder_max": 0.36,
        "rudder_speed": 0.3,
        "throttle_accel": 0.4,
        "depth_target_y": spawn_y,
        "next_depth_change_at": time.time() + random.uniform(20, 60),
        "max_depth_m": max_depth_m,
        "spawn_y": spawn_y,
        "waypoint": None,
        "last_emit": 0.0,
        "integrity": 100.0,
    }
    # IA : BT classique ou politique RL chargée après l'initialisation des munitions.
    selected_ai = ai_name or boat_data.get("ai") or "default"
    rl_requested = isinstance(selected_ai, str) and selected_ai.startswith("rl_")
    bot["ai_name"] = selected_ai
    bot["ai_tree"] = None if rl_requested else bot_ai.load_ai(selected_ai)
    bot["external_control"] = rl_requested
    final_team_id = team_id or "bots"
    final_team_name = team_name or ("Bots" if final_team_id == "bots" else final_team_id)
    bot["team_id"] = final_team_id
    bot["team_name"] = final_team_name
    bots[sid] = bot
    players[sid] = {
        "id": bot_pid,
        "boatType": boat_type,
        "boat": boat_data,
        "position": dict(bot["position"]),
        "rotation": rotation,
        "is_bot": True,
        "team_id": final_team_id,
        "team_name": final_team_name,
    }
    init_torpedo_ammo_for_sid(sid)
    init_drone_ammo_for_sid(sid)
    init_grenade_ammo_for_sid(sid)
    init_cannon_ammo_for_sid(sid)
    init_beacon_ammo_for_sid(sid)
    init_lure_ammo_for_sid(sid)
    init_mine_ammo_for_sid(sid)
    if rl_requested:
        try:
            from rl_runtime import attach_controller
            attach_controller(bot, selected_ai)
        except Exception:
            fallback_ai = "autodest" if boat_type == "destroyer" else "autosub"
            logging.exception("[rl] impossible de charger %s, repli sur %s", selected_ai, fallback_ai)
            bot["ai_name"] = fallback_ai
            bot["ai_tree"] = bot_ai.load_ai(fallback_ai)
            bot["external_control"] = False
            bot.pop("rl_controller", None)
    socketio.emit("player_joined", players[sid])
    return bot_pid


# Phase B : `boat_torpedo_specs` est désormais dans simulation.py.
# Wrapper pour rétrocompat (les autres fonctions du module l'appellent).
boat_torpedo_specs = simulation.boat_torpedo_specs


def init_torpedo_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    specs = boat_torpedo_specs(p.get("boat"))
    ammo = {kind: int(spec.get("count", 0)) for kind, spec in specs.items()}
    # Bots sub : pas de filoguidée (ne savent pas piloter), redistribuer en acoustique.
    if p.get("is_bot") and p.get("boatType") == "submarine":
        wg = ammo.get("wireGuided", 0)
        if wg > 0:
            ammo["acoustic"] = ammo.get("acoustic", 0) + wg
            ammo["wireGuided"] = 0
    torpedo_ammo[sid] = ammo


def emit_torpedo_counts(sid):
    """Envoie les compteurs munitions au socket du propriétaire (humain). Inclut
    `bsid` pour multi-bateaux (None pour le bateau primaire)."""
    target = _owner_socket_sid(sid)
    if not target:
        return
    payload = dict(torpedo_ammo.get(sid) or {})
    payload["bsid"] = _bsid_for(sid)
    socketio.emit("torpedo_counts", payload, to=target)


# Phase B : torpedo_segment_blocked et torpedo_avoid_island sont dans
# simulation.py. Wrappers pour les usages internes (spawn_torpedo, bot_*).
def torpedo_segment_blocked(x1, z1, x2, z2, world_data):
    return simulation.torpedo_segment_blocked(
        x1, z1, x2, z2, world_data,
        point_in_polygon=point_in_polygon,
        ensure_island_bounds=_ensure_island_bounds,
    )


def torpedo_avoid_island(t, des_x, des_z, horizon, world_data):
    return simulation.torpedo_avoid_island(
        t, des_x, des_z, horizon, world_data,
        point_in_polygon=point_in_polygon,
        ensure_island_bounds=_ensure_island_bounds,
    )


# Phase B : ces fonctions sont méthodes de Sim. Wrappers exposés pour
# rétrocompat (utilisés par bot_torpedoes_threat, etc.).
def torpedo_pick_acoustic(t):
    return sim._pick_acoustic(t)


def torpedo_pick_radar(t, world_data):
    return sim._pick_radar(t, world_data)


# Phase B : ces fonctions sont méthodes de Sim. Wrappers pour rétrocompat.
def emit_torpedo_state_broadcast(t):
    sim._emit_torpedo_state(t)


def notify_shooter_torpedo_status(t, *, acquired=None, destroyed=False, reason=None, launched=False):
    sim._notify_shooter_status(t, acquired=acquired, destroyed=destroyed, reason=reason, launched=launched)


def notify_torpedo_acquisition(t, target_id, acquired, destroyed=False, reason=None):
    sim._notify_torpedo_acquisition(t, target_id, acquired=acquired, destroyed=destroyed, reason=reason)


def explode_server_torpedo(t, direct_hit_id, damage, hit_target_id, hit_lure=False, silent=False):
    sim._explode_torpedo(t, direct_hit_id=direct_hit_id, damage=damage,
                         hit_target_id=hit_target_id, hit_lure=hit_lure, silent=silent)


def spawn_torpedo(sid, player_dict, data):
    """Crée une torpille serveur sur intention de tir d'un joueur humain.
    `data` : { kind, targetId|null, fixedTarget|null:{x,z,beaconBid?} }."""
    import math
    kind = data.get("kind")
    if kind not in ("acoustic", "wireGuided", "autonomous"):
        return
    boat = player_dict.get("boat") or {}
    specs = boat_torpedo_specs(boat)
    spec = specs.get(kind)
    if not spec:
        return
    pid = player_dict["id"]
    ammo = torpedo_ammo.get(sid)
    if ammo is None:
        init_torpedo_ammo_for_sid(sid)
        ammo = torpedo_ammo.get(sid) or {}
    if ammo.get(kind, 0) <= 0:
        logging.info(f"[torpedo-fire-REFUS] {pid} kind={kind} ammo={ammo.get(kind)} (munitions épuisées côté serveur)")
        return
    # Filoguidée : une seule à la fois.
    if kind == "wireGuided" and active_wire_torpedoes.get(pid):
        logging.info(f"[torpedo-fire-REFUS] {pid} kind=wireGuided : une filoguidée déjà en vol")
        return
    pos = player_dict.get("position") or {}
    bx = pos.get("x", 0)
    bz = pos.get("z", 0)
    by = pos.get("y", 0)
    rotation = float(player_dict.get("rotation") or 0)
    # Cible : joueur ou point fixe.
    target_id = data.get("targetId")
    fixed = data.get("fixedTarget") or None
    aim_x = aim_z = None
    aim_y = 0.0
    if target_id:
        for sid2, other in players.items():
            if other.get("id") == target_id:
                opos = other.get("position") or {}
                aim_x = opos.get("x", 0)
                aim_z = opos.get("z", 0)
                aim_y = opos.get("y", 0)
                # Diag : si la cible est un bot, comparons avec bot["position"]
                # qui est la source de vérité diffusée via player_moved.
                if other.get("is_bot"):
                    bot_obj = bots.get(sid2)
                    if bot_obj is not None:
                        bp = bot_obj.get("position") or {}
                        if abs(bp.get("x", 0) - aim_x) > 0.5 or abs(bp.get("z", 0) - aim_z) > 0.5:
                            logging.warning(
                                f"[torpedo-fire-DESYNC] target {target_id} "
                                f"players[]={aim_x:.1f},{aim_z:.1f} "
                                f"bot[]={bp.get('x', 0):.1f},{bp.get('z', 0):.1f}"
                            )
                break
    if aim_x is None and fixed:
        aim_x = float(fixed.get("x", 0))
        aim_z = float(fixed.get("z", 0))
    if aim_x is None:
        return
    # Validation portée.
    max_range_m = spec.get("maxRangeMeters", 10000)
    dist_m = math.hypot(aim_x - bx, aim_z - bz) * UNIT_METERS_BOT
    # Log diagnostic tir humain : on vérifie que la cible serveur est bien là
    # où le client visait. Si targetId, on log la position serveur courante du
    # bateau cible (= position où la torpille va se diriger en phase course).
    logging.info(
        f"[torpedo-fire] kind={kind} shooter={pid} pos=({bx:.1f},{bz:.1f}) "
        f"targetId={target_id} fixed={fixed} aim=({aim_x:.1f},{aim_z:.1f}) "
        f"dist={dist_m:.0f} m"
    )
    if dist_m > max_range_m:
        logging.info(f"[torpedo-fire-REFUS] {pid} kind={kind} dist={dist_m:.0f}m > portée max {max_range_m}m (cible hors de portée)")
        return
    # Activation : valeur saisie côté client (mètres), clampée [0, maxRange-1].
    # Fallback sur la valeur du JSON si non fournie.
    raw_activation = (data or {}).get("activationMeters")
    try:
        activation_m_human = float(raw_activation) if raw_activation is not None else float(spec.get("activation", 0))
    except (TypeError, ValueError):
        activation_m_human = float(spec.get("activation", 0))
    activation_m_human = max(0.0, min(max_range_m - 1.0, activation_m_human))
    # Spawn 1.5 u devant le bateau (alignement avec le client : boatHalfLength + 1.5).
    # Le serveur n'a pas de boatHalfLength précis, on prend 1.5 u (~15 m) d'avance simple.
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    ahead = 1.5
    spawn_x = bx - cos_r * ahead
    spawn_z = bz + sin_r * ahead
    dir_x = -cos_r
    dir_z = sin_r
    # Profondeur initiale : destroyer en surface tire à -0.3 ; sub à sa propre profondeur.
    boat_type = player_dict.get("boatType") or ""
    spawn_y = -0.3 if boat_type == "destroyer" else by
    # Allocation tid par tireur (compteur incrémental).
    tid = next_torpedo_tid.get(pid, 1)
    next_torpedo_tid[pid] = tid + 1
    speed_us = spec.get("speed", 50) * 0.514444 / UNIT_METERS_BOT
    radar_range_m = spec.get("radarRangeMeters", 0) or 0
    t = {
        "ownerSid": sid,
        "ownerPlayerId": pid,
        "tid": tid,
        "kind": kind,
        "x": spawn_x, "y": spawn_y, "z": spawn_z,
        "dirX": dir_x, "dirZ": dir_z,
        "pitch": 0.0,
        "speed": speed_us,
        "minTurnRadius": spec.get("minTurnRadius", 400) / UNIT_METERS_BOT,
        "maxRange": max_range_m / UNIT_METERS_BOT,
        "activation": activation_m_human / UNIT_METERS_BOT,
        "damage": spec.get("damage", 60),
        "minNoise": float(spec.get("minNoise", 4)),
        "radarRange": radar_range_m / UNIT_METERS_BOT,
        "radarHalfAngle": (spec.get("radarConeDeg", 30) * 0.5) * math.pi / 180,
        "thermoclinePenetration": float((boat.get("activeSonar") or {}).get("thermoclinePenetration", 0)),
        "traveled": 0.0,
        "lockedKey": None,
        "acquired": False,
        "lastAcquiredPos": None,
        "initialTargetTracked": False,
        "acquiredBoatId": None,
        "inAcquisition": False,
        "lastIntensity": 0.0,
        "initialTarget": (aim_x, aim_y, aim_z),
        "targetId": target_id,
        "wireYaw": 0,
        "wirePitch": 0,
        "notifiedTargets": set(),
        "bornAt": time.time(),
        "antiTorpedo": bool(data.get("antiTorpedo")),
    }
    torpedoes_server[(pid, tid)] = t
    if kind == "wireGuided":
        active_wire_torpedoes[pid] = (pid, tid)
    # Décrément munition + resync au tireur.
    ammo[kind] = max(0, ammo.get(kind, 0) - 1)
    emit_torpedo_counts(sid)
    # Premier état + alert "lancée" si la torpille vise un joueur humain.
    emit_torpedo_state_broadcast(t)
    if target_id:
        for sid2, other in players.items():
            if other.get("id") == target_id and not other.get("is_bot"):
                socketio.emit("torpedo_alert", {
                    "shooterId": pid,
                    "tid": tid,
                    "kind": kind,
                }, to=sid2)
                break
        t["notifiedTargets"].add(target_id)
    # Miroir tireur (vert) : "lancée".
    notify_shooter_torpedo_status(t, launched=True)
    # Filoguidée : pas d'acquisition automatique, mais le tireur la guide
    # explicitement vers la cible désignée → on présente le même flux à la cible
    # qu'une torpille normale (lancée → en acquisition).
    if kind == "wireGuided" and target_id:
        t["inAcquisition"] = True
        notify_torpedo_acquisition(t, target_id, acquired=True)
        notify_shooter_torpedo_status(t, acquired=True)


def spawn_bot_torpedo(bot, target_player):
    """Phase E : délégué à Sim.spawn_bot_torpedo."""
    return sim.spawn_bot_torpedo(bot, target_player)


def spawn_bot_torpedo_autonomous(bot, target_player, activation_m=None):
    """Tire une torpille autonome avec activation personnalisée."""
    return sim.spawn_bot_torpedo_autonomous(bot, target_player, activation_m)


def bot_torpedoes_status(owner_player_id):
    """Retourne la liste des torpilles en vol appartenant à ce bot."""
    return [t for t in sim.torpedoes.values()
            if t.get("ownerPlayerId") == owner_player_id]


def update_server_torpedoes(dt, world_data):
    """Phase B : délégué à Sim.update_server_torpedoes (cf. simulation.py)."""
    sim.update_server_torpedoes(dt, world_data)


# ===================== DRONES (serveur authoritaire) =====================

boat_drone_specs = simulation.boat_drone_specs


def init_drone_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    specs = boat_drone_specs(p.get("boat"))
    drone_ammo[sid] = {kind: int(spec.get("number", 0)) for kind, spec in specs.items()}


def emit_drone_counts(sid):
    target = _owner_socket_sid(sid)
    if not target:
        return
    payload = dict(drone_ammo.get(sid) or {})
    payload["bsid"] = _bsid_for(sid)
    socketio.emit("drone_counts", payload, to=target)


def emit_drone_state_broadcast(d):
    """Phase C : délégué à Sim._emit_drone_state."""
    sim._emit_drone_state(d)


def kill_server_drone(d, reason, refund):
    """Phase C : délégué à Sim.kill_server_drone."""
    sim.kill_server_drone(d, reason, refund)


def spawn_drone(sid, player_dict, data):
    """Phase C : délégué à Sim.spawn_drone."""
    sim.spawn_drone(sid, player_dict, data)


def update_server_drones(dt, world_data):
    """Phase C : délégué à Sim.update_server_drones."""
    sim.update_server_drones(dt, world_data)


# ===================== GRENADES (serveur authoritaire) =====================

grenades_server = {}
next_grenade_gid = {}     # ownerPlayerId -> prochain gid
grenade_ammo = {}         # sid -> int (nombre de grenades restantes)
GRENADE_GRAVITY = 18.0
GRENADE_LATERAL_SPEED = 6.0
GRENADE_INITIAL_VY = 5.0
GRENADE_EXPLOSION_DURATION = 0.9


boat_grenade_spec = simulation.boat_grenade_spec


def init_grenade_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    spec = boat_grenade_spec(p.get("boat"))
    grenade_ammo[sid] = int(spec.get("number", 0)) if spec else 0


def emit_grenade_count(sid):
    target = _owner_socket_sid(sid)
    if not target:
        return
    socketio.emit("grenade_count", {
        "count": grenade_ammo.get(sid, 0),
        "bsid": _bsid_for(sid),
    }, to=target)


def spawn_grenade(sid, player_dict, data):
    """Phase C : délégué à Sim.spawn_grenade."""
    sim.spawn_grenade(sid, player_dict, data)


def explode_server_grenade(g):
    """Phase C : délégué à Sim.explode_server_grenade."""
    sim.explode_server_grenade(g)


def update_server_grenades(dt, world_data):
    """Phase C : délégué à Sim.update_server_grenades."""
    sim.update_server_grenades(dt, world_data)


# ===================== MINES (simu serveur) =====================

def explode_server_mine(mine, trigger_id=None, _chain_visited=None):
    """Phase C : délégué à Sim.explode_server_mine."""
    sim.explode_server_mine(mine, trigger_id=trigger_id, _chain_visited=_chain_visited)


def update_server_mines(dt, world_data):
    """Phase C : délégué à Sim.update_server_mines."""
    sim.update_server_mines(dt, world_data)


# ===================== BALISES SONAR (compteurs munitions) =====================

beacon_ammo = {}  # sid -> int (nombre de balises restantes)


def init_beacon_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    spec = (p.get("boat") or {}).get("sonarBeacons") or None
    beacon_ammo[sid] = int(spec.get("number", 0)) if spec else 0


def init_passive_beacon_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    spec = (p.get("boat") or {}).get("passiveSonarBeacons") or None
    passive_beacon_ammo[sid] = int(spec.get("number", 0)) if spec else 0


def emit_passive_beacon_count(sid):
    target = _owner_socket_sid(sid)
    if not target:
        return
    socketio.emit("passive_beacon_count", {
        "bsid": _bsid_for(sid),
        "count": passive_beacon_ammo.get(sid, 0),
    }, to=target)


def emit_beacon_count(sid):
    target = _owner_socket_sid(sid)
    if not target:
        return
    socketio.emit("beacon_count", {
        "count": beacon_ammo.get(sid, 0),
        "bsid": _bsid_for(sid),
    }, to=target)


# ===================== LEURRES ACOUSTIQUES (compteurs munitions) =====================

lure_ammo = {}      # sid -> int
next_lure_lid = {}  # ownerPlayerId -> prochain lid


def init_lure_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    spec = (p.get("boat") or {}).get("acousticLures") or None
    lure_ammo[sid] = int(spec.get("number", 0)) if spec else 0


def emit_lure_count(sid):
    target = _owner_socket_sid(sid)
    if not target:
        return
    socketio.emit("lure_count", {
        "count": lure_ammo.get(sid, 0),
        "bsid": _bsid_for(sid),
    }, to=target)


def init_mine_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    boat = p.get("boat") or {}
    mine_ammo[sid] = {
        "surface":   int((boat.get("mineSurf") or {}).get("number", 0)),
        "bottom":    int((boat.get("mineBottom") or {}).get("number", 0)),
        "suspended": int((boat.get("mineSuspended") or {}).get("number", 0)),
    }


def emit_mine_counts(sid):
    target = _owner_socket_sid(sid)
    if not target:
        return
    payload = dict(mine_ammo.get(sid) or {})
    payload["bsid"] = _bsid_for(sid)
    socketio.emit("mine_counts", payload, to=target)


# ===================== CANNON / DCA (serveur authoritaire) =====================

cannon_ammo = {}  # sid -> { cannon: n, antiAircraft: n }
CANNON_SHELL_SPEED_MS = 500.0
AA_BULLET_SPEED_MS = 1000.0


def boat_cannon_specs(boat):
    out = {}
    c = (boat or {}).get("cannon") or None
    if c:
        out["cannon"] = {
            "ammunition": c.get("ammunition", 0),
            "range": c.get("range", 8000),
            "damage": c.get("damage", 30),
        }
    a = (boat or {}).get("antiAircraft") or None
    if a:
        out["antiAircraft"] = {
            "ammunition": a.get("ammunition", 0),
            "range": a.get("range", 5000),
            "damage": a.get("damage", 1),
        }
    return out


def init_cannon_ammo_for_sid(sid):
    p = players.get(sid)
    if not p:
        return
    specs = boat_cannon_specs(p.get("boat"))
    cannon_ammo[sid] = {kind: int(spec.get("ammunition", 0)) for kind, spec in specs.items()}


def emit_cannon_counts(sid):
    target = _owner_socket_sid(sid)
    if not target:
        return
    payload = dict(cannon_ammo.get(sid) or {})
    payload["bsid"] = _bsid_for(sid)
    socketio.emit("cannon_counts", payload, to=target)


def hit_probability(kind, target_type, dist_m, range_m):
    """Aligné sur le client (game.js fireCannon).
    cannon vs bateau : 1 → 0.3 dégressif au-delà de demi-portée.
    DCA vs bateau : toujours 1 (mais peu de dégâts).
    DCA vs drone : 0.9 → 0.3 dégressif.
    cannon vs drone : 0 (refusé)."""
    if target_type == "drone":
        if kind != "antiAircraft":
            return 0.0
        max_p, min_p = 0.9, 0.3
    elif target_type == "boat":
        if kind == "antiAircraft":
            return 1.0
        max_p, min_p = 1.0, 0.3
    else:
        # beacon : tir au canon réussit toujours dans la portée.
        return 1.0
    half = range_m / 2
    if dist_m <= half:
        return max_p
    return max_p - (max_p - min_p) * ((dist_m - half) / max(1.0, range_m - half))


def fire_cannon_intent(sid, shooter, data):
    """Pipe complet pour un tir cannon/DCA d'un joueur humain.
    `data` : { kind, targetType, targetId|key|bid }."""
    import math
    kind = data.get("kind")
    if kind not in ("cannon", "antiAircraft"):
        return
    boat = shooter.get("boat") or {}
    specs = boat_cannon_specs(boat)
    spec = specs.get(kind)
    if not spec:
        return
    # Sub immergé ne tire pas.
    boat_type = shooter.get("boatType") or ""
    pos = shooter.get("position") or {}
    if boat_type == "submarine":
        flotation_m = boat.get("flotation", 2)
        surface_y = -flotation_m / UNIT_METERS_BOT
        if pos.get("y", 0) < surface_y - 0.05:
            return
    ammo = cannon_ammo.get(sid)
    if ammo is None:
        init_cannon_ammo_for_sid(sid)
        ammo = cannon_ammo.get(sid) or {}
    if ammo.get(kind, 0) <= 0:
        return
    # Résolution de la cible.
    target_type = data.get("targetType")
    tx = ty = tz = None
    target_boat_id = None
    target_drone_owner = target_drone_did = None
    target_beacon_bid = None
    target_passive_beacon_bid = None
    if target_type == "boat":
        target_boat_id = data.get("targetId")
        for sid2, p in players.items():
            if p.get("id") == target_boat_id:
                p2 = p.get("position") or {}
                tx, ty, tz = p2.get("x", 0), p2.get("y", 0), p2.get("z", 0)
                # Sub immergé : pas ciblable au canon/DCA
                t_boat = p.get("boat") or {}
                t_flotation = t_boat.get("flotation", 2)
                t_surface_y = -t_flotation / UNIT_METERS_BOT
                if p2.get("y", 0) < t_surface_y - 0.05:
                    return
                break
        if tx is None:
            return
    elif target_type == "drone":
        if kind != "antiAircraft":
            return
        target_drone_owner = data.get("ownerId")
        target_drone_did = data.get("did")
        drone = drones_server.get((target_drone_owner, target_drone_did))
        if not drone:
            return
        tx, ty, tz = drone["x"], drone["y"], drone["z"]
    elif target_type == "beacon":
        if kind not in ("cannon", "antiAircraft"):
            return
        target_beacon_bid = data.get("bid")
        beacon = sonar_beacons.get(target_beacon_bid)
        if not beacon:
            return
        tx, ty, tz = beacon["x"], 0.0, beacon["z"]
    elif target_type == "passive_beacon":
        if kind not in ("cannon", "antiAircraft"):
            return
        target_passive_beacon_bid = data.get("bid")
        pbeacon = passive_sonar_beacons.get(target_passive_beacon_bid)
        if not pbeacon:
            return
        tx, ty, tz = pbeacon["x"], 0.0, pbeacon["z"]
    elif target_type == "mine":
        # Canon ou DCA peuvent tirer sur une mine de surface uniquement.
        target_mine_owner = data.get("ownerId")
        target_mine_mid = data.get("mid")
        mine = mines_server.get((target_mine_owner, target_mine_mid))
        if not mine or mine.get("kind") != "surface":
            return
        tx, ty, tz = mine["x"], 0.0, mine["z"]
    else:
        return
    bx = pos.get("x", 0)
    bz = pos.get("z", 0)
    dx_m = (tx - bx) * UNIT_METERS_BOT
    dz_m = (tz - bz) * UNIT_METERS_BOT
    dy_m = ((ty or 0) - (pos.get("y", 0))) * UNIT_METERS_BOT if target_type == "drone" else 0.0
    dist_m = (dx_m * dx_m + dy_m * dy_m + dz_m * dz_m) ** 0.5
    range_m = spec.get("range", 8000)
    if dist_m > range_m:
        return
    ammo[kind] = max(0, ammo.get(kind, 0) - 1)
    emit_cannon_counts(sid)
    hit_prob = hit_probability(kind, target_type, dist_m, range_m)
    hit = random.random() < hit_prob
    end_x, end_y, end_z = tx, (ty or 0), tz
    if not hit:
        miss_r = (5.0 if kind == "antiAircraft" else 8.0) / UNIT_METERS_BOT
        ang = random.uniform(0, math.tau)
        end_x += math.cos(ang) * miss_r
        end_z += math.sin(ang) * miss_r
    speed_ms = AA_BULLET_SPEED_MS if kind == "antiAircraft" else CANNON_SHELL_SPEED_MS
    flight_s = dist_m / speed_ms
    duration_ms = flight_s * 1000.0
    if kind == "antiAircraft":
        arc_height = 0.0
    else:
        dist_u = (((end_x - bx) ** 2 + (end_z - bz) ** 2) ** 0.5)
        range_u = range_m / UNIT_METERS_BOT
        arc_height = dist_u * 0.25 * min(1.0, dist_u / max(1.0, range_u))
    start_y = 0.5 if boat_type == "destroyer" else 0.0
    socketio.emit("cannon_fire", {
        "shooterId": shooter["id"],
        "kind": kind,
        "startX": bx, "startY": start_y, "startZ": bz,
        "endX": end_x, "endY": end_y, "endZ": end_z,
        "arcHeight": arc_height,
        "duration": duration_ms,
        "impact": kind == "cannon",
    })
    if not hit:
        return
    damage = spec.get("damage", 1)
    attacker_id = shooter["id"]
    # Application différée à l'arrivée du projectile.
    if target_type == "boat":
        target_id = target_boat_id
        def _delayed_boat():
            socketio.sleep(flight_s)
            socketio.emit("cannon_hit", {
                "shooterId": attacker_id,
                "targetId": target_id,
                "damage": damage,
            })
            bsid, bot = find_bot_by_player_id(target_id)
            if bot is not None:
                bot_apply_damage(bsid, bot, damage, attacker_id)
            else:
                for sid_h, p_h in players.items():
                    if p_h.get("id") == target_id and not p_h.get("is_bot"):
                        apply_player_damage(sid_h, p_h, damage, attacker_id)
                        break
        socketio.start_background_task(_delayed_boat)
    elif target_type == "drone":
        owner_id = target_drone_owner
        did = target_drone_did
        def _delayed_drone():
            socketio.sleep(flight_s)
            d = drones_server.get((owner_id, did))
            if d:
                kill_server_drone(d, reason="shot", refund=False)
                drones_server.pop((owner_id, did), None)
        socketio.start_background_task(_delayed_drone)
    elif target_type == "beacon":
        bid = target_beacon_bid
        def _delayed_beacon():
            socketio.sleep(flight_s)
            if bid in sonar_beacons:
                sonar_beacons.pop(bid, None)
                socketio.emit("sonar_beacon_destroyed", {"bid": bid})
        socketio.start_background_task(_delayed_beacon)
    elif target_type == "passive_beacon":
        pbid = target_passive_beacon_bid
        def _delayed_passive_beacon():
            socketio.sleep(flight_s)
            if pbid in passive_sonar_beacons:
                passive_sonar_beacons.pop(pbid, None)
                socketio.emit("passive_sonar_beacon_destroyed", {"bid": pbid})
        socketio.start_background_task(_delayed_passive_beacon)
    elif target_type == "mine":
        m_owner = target_mine_owner
        m_mid = target_mine_mid
        def _delayed_mine():
            socketio.sleep(flight_s)
            mine = mines_server.get((m_owner, m_mid))
            if mine is not None:
                # Cannon / DCA déclenche l'explosion complète de la mine.
                explode_server_mine(mine, trigger_id=attacker_id)
        socketio.start_background_task(_delayed_mine)


def bot_fire_cannon(bot, target_player):
    """Phase E : délégué à Sim.bot_fire_cannon."""
    return sim.bot_fire_cannon(bot, target_player)


def bot_fire_aa(bot, drone):
    """Phase E : délégué à Sim.bot_fire_aa."""
    return sim.bot_fire_aa(bot, drone)


def bot_torpedoes_threat(bot):
    """Phase E : délégué à Sim.bot_torpedoes_threat."""
    return sim.bot_torpedoes_threat(bot)


def bot_drop_lure(bot):
    """Phase E : délégué à Sim.bot_drop_lure."""
    return sim.bot_drop_lure(bot)


def detect_enemies_passive(bot, world_data):
    """Phase E : délégué à Sim.detect_enemies_passive."""
    return sim.detect_enemies_passive(bot, world_data)


def bot_sonar_ping(bot, world_data):
    """Phase E : délégué à Sim.bot_sonar_ping."""
    return sim.bot_sonar_ping(bot, world_data)


def update_human_autopilot(p, dt, world_data):
    """Phase E : délégué à Sim.update_human_autopilot."""
    sim.update_human_autopilot(p, dt, world_data)


def _bots_passive_get():
    """Helper pour bot_ai (évite l'import circulaire et capture la vraie
    valeur du global, pas un snapshot)."""
    return bots_passive


# Dépendances injectées dans le ctx du BT (bot_ai). Toutes les fonctions
# nécessaires aux conditions/actions sont passées par référence.
_BT_DEPS = None


def _get_bt_deps():
    global _BT_DEPS
    if _BT_DEPS is None:
        _BT_DEPS = {
            "UNIT_METERS_BOT": UNIT_METERS_BOT,
            "players": players,
            "drones_server": drones_server,
            "torpedoes_server": torpedoes_server,
            "torpedo_ammo": torpedo_ammo,
            "server_lures": server_lures,
            "pick_bot_waypoint": pick_bot_waypoint,
            "point_on_any_island": point_on_any_island,
            "detect_enemies_passive": detect_enemies_passive,
            "spawn_bot_torpedo": spawn_bot_torpedo,
            "spawn_bot_torpedo_autonomous": spawn_bot_torpedo_autonomous,
            "bot_torpedoes_status": bot_torpedoes_status,
            "bot_fire_cannon": bot_fire_cannon,
            "bot_fire_aa": bot_fire_aa,
            "bot_torpedoes_threat": bot_torpedoes_threat,
            "bot_drop_lure": bot_drop_lure,
            "bot_sonar_ping": bot_sonar_ping,
            "same_team": simulation.same_team,
            "bots_passive_get": _bots_passive_get,
            "spawn_drone": spawn_drone,
            "drone_ammo": drone_ammo,
            "ensure_island_bounds": _ensure_island_bounds,
            "line_of_sight_clear": line_of_sight_clear,
        }
    return _BT_DEPS


def update_bot(bot, dt, world_data):
    """Phase F : délégué à Sim.update_bot."""
    sim.update_bot(bot, dt, world_data)


def update_bot_legacy(bot, dt, world_data):
    """Phase F : délégué à Sim.update_bot_legacy."""
    sim.update_bot_legacy(bot, dt, world_data)


BOT_SPLASH_RADIUS_M = 200.0


def find_bot_by_player_id(pid):
    """Phase D : délégué à Sim.find_bot_by_player_id."""
    return sim.find_bot_by_player_id(pid)


def bot_apply_damage(sid, bot, damage, attacker_id):
    """Phase D : délégué à Sim.bot_apply_damage."""
    sim.bot_apply_damage(sid, bot, damage, attacker_id)


def sink_bot(sid, bot, attacker_id):
    """Phase D : délégué à Sim.sink_bot."""
    sim.sink_bot(sid, bot, attacker_id)


def bot_splash_damage(ex, ey, ez, base_damage, attacker_id, depth_check=True):
    """Phase D : délégué à Sim.bot_splash_damage."""
    sim.bot_splash_damage(ex, ey, ez, base_damage, attacker_id, depth_check=depth_check)


def bot_ticker():
    """Phase F : la simu tourne dans Sim.step(). Le ticker se contente de cadencer,
    drainer les events et dispatcher vers socketio."""
    global sim
    last = time.time()
    cached = {"name": None, "world": None}
    if sim is None:
        try:
            world_for_sim = load_world()
        except Exception as e:
            logging.exception(f"[sim] impossible de charger le monde: {e}")
            world_for_sim = {}
        sim = simulation.Sim(world_for_sim)
        sim.set_legacy_hooks(sys.modules[__name__])
        logging.info("[sim] Initialized (Phase F: Sim.step orchestrated)")
    while True:
        socketio.sleep(BOT_TICK_INTERVAL)
        now = time.time()
        dt = min(BOT_DT_MAX, now - last)
        gap = now - last
        if gap > 0.15:
            logging.warning(f"[bot_ticker] long gap: {gap*1000:.0f} ms (target {BOT_TICK_INTERVAL*1000:.0f}, bots={len(bots)}, players={len(players)})")
        # Diag WS — accumulation
        _ws_diag["tick_count"] += 1
        _ws_diag["gap_sum"] += gap
        if gap > _ws_diag["gap_max"]:
            _ws_diag["gap_max"] = gap
        last = now
        any_human = any(not p.get("is_bot") for p in players.values())
        if not bots and not any_human and not torpedoes_server and not drones_server and not grenades_server:
            continue
        if cached["name"] != current_map_name or cached["world"] is None:
            try:
                cached["world"] = load_world()
                cached["name"] = current_map_name
                sim.world_data = cached["world"]
            except Exception as e:
                logging.warning(f"[bot_ticker] impossible de charger le monde: {e}")
                continue
        world_data = cached["world"]
        # Multiplicateur de vitesse : on fait N ticks de sim par tick réel.
        # Coût CPU ×N mais cohérence physique parfaite.
        n_steps = max(1, int(sim_tick_multiplier))
        for _ in range(n_steps):
            try:
                sim.step(dt, world_data)
            except Exception as e:
                logging.exception(f"sim step error: {e}")
                break
        try:
            pending = sim.drain_events()
            if pending:
                _t0_dispatch = time.time()
                dispatch_events(pending)
                _dispatch_ms = (time.time() - _t0_dispatch) * 1000.0
                _ws_diag["events_sum"] += len(pending)
                _ws_diag["dispatch_time_sum"] += _dispatch_ms
                if _dispatch_ms > _ws_diag["dispatch_time_max"]:
                    _ws_diag["dispatch_time_max"] = _dispatch_ms
        except Exception as e:
            logging.exception(f"[sim] event drain error: {e}")
        # Rapport diag WS toutes les WS_DIAG_INTERVAL secondes (seulement si catégorie active)
        if now - _ws_diag["last_report"] >= WS_DIAG_INTERVAL and _ws_diag["tick_count"] > 0:
            from debug_log import dlog
            _n = _ws_diag["tick_count"]
            _avg_gap = _ws_diag["gap_sum"] / _n * 1000.0
            _avg_ev = _ws_diag["events_sum"] / _n
            _avg_disp = _ws_diag["dispatch_time_sum"] / max(1, _ws_diag["events_sum"]) if _ws_diag["events_sum"] else 0.0
            _lat_n = _ws_diag.get("move_latency_count", 0)
            _lat_str = ""
            if _lat_n > 0:
                _lat_avg = _ws_diag["move_latency_sum"] / _lat_n
                _lat_max = _ws_diag["move_latency_max"]
                _lat_str = f" | move(biaisé) avg={_lat_avg:.1f}ms max={_lat_max:.1f}ms n={_lat_n}"
            _rtt_n = _ws_diag.get("rtt_n", 0)
            _rtt_str = ""
            if _rtt_n > 0:
                _to = _ws_diag.get("rtt_to_server")
                _fr = _ws_diag.get("rtt_from_server")
                _dir = f" (→{_to}ms ←{_fr}ms)" if _to is not None else ""
                _p95 = _ws_diag.get("rtt_p95", "?")
                _rtt_str = f" | RTT médiane={_ws_diag['rtt_avg']:.0f}ms p95={_p95}ms max={_ws_diag['rtt_max']:.0f}ms n={_rtt_n}{_dir}"
            dlog("webSocket",
                f"ticks={_n} | gap avg={_avg_gap:.1f}ms max={_ws_diag['gap_max']*1000:.1f}ms"
                f" | events/tick={_avg_ev:.1f} total={_ws_diag['events_sum']}"
                f" | dispatch avg/ev={_avg_disp:.3f}ms max={_ws_diag['dispatch_time_max']:.1f}ms"
                f" | bots={len(bots)} players={len(players)}{_rtt_str}{_lat_str}"
            )
            _ws_diag.update({"tick_count": 0, "gap_sum": 0.0, "gap_max": 0.0,
                             "events_sum": 0, "dispatch_time_sum": 0.0, "dispatch_time_max": 0.0,
                             "move_latency_sum": 0.0, "move_latency_max": 0.0, "move_latency_count": 0,
                             "rtt_avg": 0.0, "rtt_max": 0.0, "rtt_n": 0,
                             "last_report": now})
        # Yield eventlet entre ticks pour ne pas monopoliser la boucle.
        socketio.sleep(0)


def sonar_beacon_ticker():
    while True:
        socketio.sleep(SONAR_BEACON_PING_INTERVAL)
        now = time.time()
        try:
            world_data = load_world()
        except Exception as e:
            logging.warning(f"[sonar_beacon] impossible de charger le monde: {e}")
            world_data = None
        active_teams = {p.get("team_id") for p in players.values() if p.get("team_id")}
        for b in list(sonar_beacons.values()):
            b.setdefault("revealedTeams", set()).intersection_update(active_teams)
            owner_team = b.get("teamId")
            range_m = float(b.get("rangeMeters", 1000))
            range_u = range_m / UNIT_METERS_BOT
            range_u_sq = range_u * range_u
            # Détecte chaque bateau ennemi en LOS dans le rayon → révèle la balise
            # à sa team de façon permanente.
            new_teams = []
            if world_data is not None:
                tc_pen = float(b.get("thermoclinePenetration", 0))
                by = 0.0  # balise en surface
                # Humains.
                for sid_e, p_e in players.items():
                    e_team = p_e.get("team_id")
                    if not e_team or e_team == owner_team:
                        continue
                    if e_team in b["revealedTeams"]:
                        continue
                    if p_e.get("sunk"):
                        continue
                    pos = p_e.get("position") or {}
                    dx = pos.get("x", 0) - b["x"]
                    dz = pos.get("z", 0) - b["z"]
                    if dx * dx + dz * dz > range_u_sq:
                        continue
                    if not line_of_sight_clear(b["x"], b["z"],
                                               pos.get("x", 0), pos.get("z", 0),
                                               world_data):
                        continue
                    if count_thermoclines_crossed(b["x"], by, b["z"],
                                                  pos.get("x", 0), pos.get("y", 0), pos.get("z", 0),
                                                  world_data, UNIT_METERS_BOT) > 0:
                        if tc_pen <= 0 or random.random() >= tc_pen:
                            continue
                    b["revealedTeams"].add(e_team)
                    new_teams.append(e_team)
                # Bots : ping touche un bot → marque pinged_at + ajoute threat
                # path pour la team du bot.
                for sid_b, bot in bots.items():
                    bt = bot.get("team_id")
                    if not bt or bt == owner_team:
                        continue
                    bpos = bot.get("position") or {}
                    bx = bpos.get("x", 0); bz = bpos.get("z", 0)
                    dx = bx - b["x"]; dz = bz - b["z"]
                    if dx * dx + dz * dz > range_u_sq:
                        continue
                    if not line_of_sight_clear(b["x"], b["z"], bx, bz, world_data):
                        continue
                    if count_thermoclines_crossed(b["x"], by, b["z"],
                                                  bx, bpos.get("y", 0), bz,
                                                  world_data, UNIT_METERS_BOT) > 0:
                        if tc_pen <= 0 or random.random() >= tc_pen:
                            continue
                    if bt not in b["revealedTeams"]:
                        b["revealedTeams"].add(bt)
                        new_teams.append(bt)
                    bbb = bot.setdefault("bb", {})
                    bbb["pinged_at"] = now
                    bbb["pinged_by_pos"] = {"x": b["x"], "z": b["z"], "id": "beacon:" + str(b["bid"])}
                    bbb["_flee_from"] = (b["x"], b["z"])
                    bbb["_flee_at"] = now
            # Notifier les joueurs ennemis immergés dans le rayon qu'ils ont été pingés.
            if world_data is not None:
                notified_sids = set()
                for sid_e, p_e in players.items():
                    e_team = p_e.get("team_id")
                    if not e_team or e_team == owner_team:
                        continue
                    if p_e.get("sunk") or p_e.get("is_bot"):
                        continue
                    pos = p_e.get("position") or {}
                    if pos.get("y", 0) >= 0:
                        continue
                    dx = pos.get("x", 0) - b["x"]
                    dz = pos.get("z", 0) - b["z"]
                    if dx * dx + dz * dz > range_u_sq:
                        continue
                    if not line_of_sight_clear(b["x"], b["z"],
                                               pos.get("x", 0), pos.get("z", 0),
                                               world_data):
                        continue
                    if count_thermoclines_crossed(b["x"], by, b["z"],
                                                  pos.get("x", 0), pos.get("y", 0), pos.get("z", 0),
                                                  world_data, UNIT_METERS_BOT) > 0:
                        if tc_pen <= 0 or random.random() >= tc_pen:
                            continue
                    real_sid = _owner_socket_sid(sid_e)
                    if not real_sid or real_sid in notified_sids:
                        continue
                    notified_sids.add(real_sid)
                    socketio.emit("sonar_pinged", {
                        "id": "beacon:" + str(b["bid"]),
                        "x": b["x"], "z": b["z"], "y": by,
                        "coneDeg": 360, "rotation": 0,
                        "range": range_m, "reveal": range_m,
                    }, to=real_sid)
            # Le ping de balise active révèle aussi les mines ennemies dans le rayon
            # à la team du poseur (chaque mine ennemie en LOS clear).
            if world_data is not None and owner_team:
                reveal_mines_and_beacons_by_ping(owner_team, b["x"], b["z"],
                                                 range_u, 360, 0.0, world_data)
            # Notifie les nouvelles teams que la balise leur est révélée.
            for t in new_teams:
                _emit_beacon_revealed(b, t)
            # Le ping est diffusé uniquement aux teams qui voient la balise
            # (poseur + teams révélées). Sinon les ennemis verraient le cercle
            # grandir alors que la balise est censée être discrète.
            visible_teams = {owner_team} | b["revealedTeams"]
            ping_payload = {
                "bid": b["bid"],
                "x": b["x"],
                "z": b["z"],
                "at": now,
            }
            pinged_sids = set()
            for sid_p, p_p in players.items():
                if p_p.get("team_id") in visible_teams:
                    real = _owner_socket_sid(sid_p)
                    if real and real not in pinged_sids:
                        pinged_sids.add(real)
                        socketio.emit("sonar_beacon_ping", ping_payload, to=real)


def passive_sonar_beacon_ticker():
    """Tick 1 Hz : pour chaque balise passive, calcule les bateaux audibles
    en LOS, et broadcast une révélation à tous (le client filtre par team
    pour décider si afficher)."""
    from simulation import compute_emitted_noise, perceived_noise
    while True:
        socketio.sleep(PASSIVE_BEACON_TICK_INTERVAL)
        if not passive_sonar_beacons:
            continue
        try:
            world_data = load_world()
        except Exception as e:
            logging.warning(f"[passive_beacon] impossible de charger le monde: {e}")
            continue
        now = time.time()
        for b in list(passive_sonar_beacons.values()):
            bx = b["x"]; bz = b["z"]; by = b.get("y", 0)
            owner_id = b.get("ownerId")
            team_id = b.get("teamId")
            min_noise = b.get("minNoise", 20.0)
            for sid_p, p in players.items():
                if p.get("id") == owner_id:
                    continue
                # Pas de filtre team ici : la balise détecte tout (ami ou ennemi
                # potentiel). Le client filtrera côté affichage. Mais on évite
                # de tracker ses propres coéquipiers (bruit utile mais pas une
                # cible).
                if team_id and p.get("team_id") == team_id:
                    continue
                if p.get("sunk"):
                    continue
                pos = p.get("position") or {}
                px = pos.get("x", 0); pz = pos.get("z", 0)
                py = pos.get("y", 0)
                dist_u = math.hypot(px - bx, pz - bz)
                dist_m = dist_u * UNIT_METERS_BOT
                # Bruit émis par le bateau cible.
                p_boat = p.get("boat") or {}
                sr = float(p.get("speedRatio") or 0)
                if sr == 0 and p.get("is_bot"):
                    p_speed = abs(float(p.get("speed", 0)))
                    p_max = float(p.get("max_speed_us", 1.0))
                    sr = min(1.0, p_speed / max(0.001, p_max))
                rev = bool(p.get("reverse"))
                rudder_max = float(p.get("rudder_max") or p_boat.get("rudderMax") or 15.0)
                rudder = abs(float(p.get("rudder", 0))) / max(0.001, rudder_max)
                emitted = compute_emitted_noise(p_boat, sr, rev, rudder)
                if emitted <= 0:
                    continue
                perceived = perceived_noise(emitted, dist_m)
                # Atténuation thermocline : -80% par couche entre la cible et la balise.
                nc = count_thermoclines_crossed(px, py, pz, bx, by, bz, world_data, UNIT_METERS_BOT)
                if nc > 0:
                    perceived *= 0.2 ** nc
                if perceived < min_noise:
                    continue
                if not line_of_sight_clear(bx, bz, px, pz, world_data):
                    continue
                # Émet la détection : tout le monde reçoit, le client filtre
                # par team_id pour afficher uniquement aux coéquipiers.
                socketio.emit("passive_sonar_detection", {
                    "bid": b["bid"],
                    "detectedId": p["id"],
                    "x": px, "y": py, "z": pz,
                    "teamId": team_id,
                    "at": now,
                })


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Virtual World server")
    ap.add_argument("--map", default=DEFAULT_MAP,
                    help="Nom de la carte (charge maps/world_<nom>.json, défaut 'world')")
    ap.add_argument("--port", type=int, default=config["server"]["port"],
                    help="Port HTTPS d'écoute")
    ap.add_argument("--maxPlayer", type=int, default=10,
                    help="Nombre maximum de joueurs humains simultanés")
    args = ap.parse_args()
    if not SAFE_NAME_RE.match(args.map):
        raise SystemExit(f"Nom de carte invalide : {args.map}")
    if not os.path.exists(map_path(args.map)):
        raise SystemExit(f"Carte introuvable : {map_path(args.map)}")
    current_map_name = args.map  # noqa: F841 (les handlers ferment sur la globale)
    globals()["current_map_name"] = args.map
    write_current_map_name(args.map)
    globals()["MAX_HUMAN_PLAYERS"] = max(1, args.maxPlayer)
    port = args.port
    print(f"Serveur démarré sur https://0.0.0.0:{port} | map={args.map} | maxPlayers={MAX_HUMAN_PLAYERS}")
    socketio.start_background_task(sonar_beacon_ticker)
    socketio.start_background_task(passive_sonar_beacon_ticker)
    socketio.start_background_task(bot_ticker)
    socketio.run(app, host="0.0.0.0", port=port,
                 certfile="certs/cert.pem", keyfile="certs/key.pem",
                 log_output=True)
