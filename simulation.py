"""Simulation Virtual World — module pure logique de jeu.

Cette classe `Sim` encapsule tout l'état mutable du monde (joueurs, bots,
torpilles, mines, drones, grenades, balises, leurres) et expose un step(dt)
qui avance la simu d'un tick. Aucune I/O, aucune dépendance Flask/socketio.

État architectural :
- Phase A : squelette + dispatcher Events. Logique encore dans server.py.
- Phase B : torpilles migrées (update_server_torpedoes + helpers). Le serveur
  appelle `sim.update_server_torpedoes(dt, world)` qui pousse les events.
- Phases C+ : drones, grenades, mines, dégâts/intégrité, autopilote, bots IA.

La simu a besoin de fonctions externes encore non migrées (apply_player_damage,
bot_apply_damage, point_in_polygon, etc.). Elle les obtient via
`set_legacy_hooks(server_module)`. Au fur et à mesure des migrations, ces
dépendances disparaissent.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import math
import random
import time

import events as ev_mod
import geometry
from debug_log import dlog


# ===================== Constantes (alignées sur server.py) =====================

UNIT_METERS_BOT = 10.0
TORPEDO_CEILING_Y = -2.0 / UNIT_METERS_BOT  # -0.2 u (= -2 m)
SEABED_FLOOR_Y = -(500 - 10) / UNIT_METERS_BOT
MAX_WORLD_MINES = 1000
# Atténuation du son qui traverse une thermocline : -80% par couche franchie
# (facteur 0.2). Pour n couches : 0.2^n.
THERMOCLINE_NOISE_FACTOR = 0.2
BOT_SPLASH_RADIUS_M = 200.0
DRONE_RECOVERY_DISTANCE_U = 0.5  # ~5 m
GRENADE_GRAVITY = 18.0
GRENADE_INITIAL_VY = 5.0
DANGER_ZONE_OFFSET = 3.0  # u, anneau autour de chaque île
REGEN_DELAY_S = 5.0
REGEN_RATE_PER_S = 10.0 / (10.0 * 60.0)  # 10 pts en 10 minutes
REGEN_MAX_BUDGET = 10.0
REGEN_TOTAL_INITIAL = 20.0


def integrity_capacity(spec: Dict[str, Any], default: float = 100.0) -> float:
    """Valide les points configures; defaut pour les anciennes specifications."""
    value = spec.get("integrity", default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("integrity doit etre un nombre fini strictement positif")
    return float(value)


def init_hull_integrity(entity: Dict[str, Any]) -> None:
    """Fige la capacite par instance, commune aux humains, BT et RL."""
    boat = entity.get("boat") or {}
    capacity = integrity_capacity(boat)
    integrity_capacity(boat.get("acousticLures") or {}, 10.0)
    entity["maxIntegrity"] = capacity
    entity["integrity"] = capacity


# ===================== Helpers géométriques (purs, sans état) =====================

def torpedo_radar_visible(bot: Dict[str, Any], torpedo: Dict[str, Any],
                          world: Dict[str, Any]) -> bool:
    """Radar strict local, sans exemption de verrou, de type ou d'alliance."""
    pos = bot["position"]
    bx, by, bz = pos["x"], pos.get("y", 0.0), pos["z"]
    tx, tz = torpedo["x"], torpedo["z"]
    range_u = float((bot.get("boat") or {}).get("radarRangeMeters", 30000)) / UNIT_METERS_BOT
    return ((tx - bx) ** 2 + (tz - bz) ** 2 <= range_u ** 2
            and geometry.line_of_sight_clear(bx, bz, tx, tz, world)
            and not geometry.count_thermoclines_crossed(
                bx, by, bz, tx, torpedo.get("y", 0.0), tz, world, UNIT_METERS_BOT))


def torpedo_radar_threat(bot: Dict[str, Any], torpedo: Dict[str, Any],
                         world: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
    """Distance, CPA et ETA planes observables ; aucun acces au verrou prive."""
    if torpedo.get("ownerPlayerId") == bot.get("id"):
        return None
    if not torpedo_radar_visible(bot, torpedo, world):
        return None
    speed = torpedo.get("speed", 0.0)
    if speed <= 0.001:
        return None
    bx, bz = bot["position"]["x"], bot["position"]["z"]
    tx, tz = torpedo["x"], torpedo["z"]
    t_raw, cpa = geometry.closest_approach_on_segment(
        bx, bz, tx, tz, tx + torpedo.get("dirX", 0.0) * speed * 10.0,
        tz + torpedo.get("dirZ", 0.0) * speed * 10.0)
    if cpa * UNIT_METERS_BOT > 200.0:
        return None
    return (math.hypot(tx - bx, tz - bz) * UNIT_METERS_BOT,
            cpa * UNIT_METERS_BOT, max(0.0, min(10.0, t_raw * 10.0)))


def boat_torpedo_specs(boat: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Retourne le dict torpedoes du bateau, avec valeurs par défaut alignées
    sur le client."""
    raw = (boat or {}).get("torpedoes") or {}
    defaults = {
        "acoustic":   {"speed": 50, "minTurnRadius": 400, "damage": 60, "activation": 200, "maxRangeMeters": 10000, "count": 0},
        "wireGuided": {"speed": 35, "minTurnRadius": 300, "damage": 60, "activation": 200, "maxRangeMeters": 10000, "count": 0},
        "autonomous": {"speed": 55, "minTurnRadius": 500, "damage": 60, "activation": 200, "maxRangeMeters": 10000, "count": 0, "radarRangeMeters": 0, "radarConeDeg": 30},
    }
    out = {}
    for kind, base in defaults.items():
        spec = raw.get(kind)
        if spec is None:
            continue
        merged = dict(base)
        merged.update(spec)
        out[kind] = merged
    return out


def boat_drone_specs(boat: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Specs des deux types de drone, avec defaults."""
    raw_auto = (boat or {}).get("automaticDrone") or None
    raw_man = (boat or {}).get("manualDrone") or None
    out = {}
    if raw_auto:
        out["automatic"] = {
            "number": raw_auto.get("number", 0),
            "speed": raw_auto.get("speed", 80),
            "altitude": raw_auto.get("altitude", 200),
            "autonomy": raw_auto.get("autonomy", 30),
        }
    if raw_man:
        out["manual"] = {
            "number": raw_man.get("number", 0),
            "speed": raw_man.get("speed", 100),
            "altitude": raw_man.get("altitude", 200),
            "autonomy": raw_man.get("autonomy", 30),
        }
    return out


def boat_grenade_spec(boat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    g = (boat or {}).get("grenade") or None
    if not g:
        return None
    return {
        "number": g.get("number", 0),
        "damage": g.get("damage", 50),
        "sinkSpeedMs": g.get("sinkSpeedMs", 4),
        "effectRangeMeters": g.get("effectRangeMeters", 200),
        "rangeMeters": g.get("rangeMeters", 8000),
    }


MINE_KIND_TO_KEY = {
    "surface": "mineSurf",
    "bottom": "mineBottom",
    "suspended": "mineSuspended",
}


def boat_mine_spec(boat: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    """Retourne les caractéristiques d'un type de mine disponible."""
    return (boat or {}).get(MINE_KIND_TO_KEY.get(kind, "")) or None


def mine_payload(mine: Dict[str, Any]) -> Dict[str, Any]:
    """Filtre mine pour broadcast (pas d'ownerSid)."""
    return {
        "ownerId": mine["ownerId"],
        "mid": mine["mid"],
        "kind": mine["kind"],
        "x": mine["x"], "y": mine["y"], "z": mine["z"],
        "range": mine["range"],
        "armed": mine["armed"],
        "depthMeters": mine.get("depthMeters"),
    }


def torpedo_segment_blocked(x1, z1, x2, z2, world_data, *, point_in_polygon, ensure_island_bounds) -> bool:
    """Occlusion exacte commune ; signature conservee pour les hooks serveur."""
    return not geometry.line_of_sight_clear(x1, z1, x2, z2, world_data)


def torpedo_avoid_island(t, des_x, des_z, horizon, world_data, *, point_in_polygon, ensure_island_bounds):
    """Évitement d'île par dichotomie ±10° → ±90°. Port de la version JS."""
    if not world_data or not world_data.get("islands"):
        return des_x, des_z

    def test(dxv, dzv):
        return not torpedo_segment_blocked(
            t["x"], t["z"], t["x"] + dxv * horizon, t["z"] + dzv * horizon,
            world_data, point_in_polygon=point_in_polygon,
            ensure_island_bounds=ensure_island_bounds,
        )
    if test(des_x, des_z):
        return des_x, des_z
    cur = math.atan2(t["dirZ"], t["dirX"])
    for deg in range(10, 91, 10):
        a = deg * math.pi / 180
        ca = math.cos(a)
        sa = math.sin(a)
        lx = des_x * ca - des_z * sa
        lz = des_x * sa + des_z * ca
        rx = des_x * ca + des_z * sa
        rz = -des_x * sa + des_z * ca
        l_ok = test(lx, lz)
        r_ok = test(rx, rz)
        if l_ok and r_ok:
            l_delta = abs(((math.atan2(lz, lx) - cur) + math.pi * 3) % (math.pi * 2) - math.pi)
            r_delta = abs(((math.atan2(rz, rx) - cur) + math.pi * 3) % (math.pi * 2) - math.pi)
            return (rx, rz) if r_delta < l_delta else (lx, lz)
        if l_ok:
            return lx, lz
        if r_ok:
            return rx, rz
    return des_x, des_z


# ===================== Noise / Passive Sonar =====================

def compute_emitted_noise(boat: Dict[str, Any], speed_ratio: float,
                          reverse: bool, rudder_ratio: float = 0.0) -> float:
    """Bruit émis par un bateau, formule unifiée (CLAUDE.md).
    - speed_ratio : 0..1 par rapport à maxSpeed.
    - reverse : True si marche arrière.
    - rudder_ratio : |rudder| / rudder_max (0..1).
    Retourne le bruit "à la source" (sans atténuation distance).
    """
    if speed_ratio <= 0 and not reverse:
        return 0.0
    base_noise = float(boat.get("noise", 0))
    min_noise = float(boat.get("minNoise", 0))
    snl = float(boat.get("speedNoiseLimit", 0))
    # Marche arrière : même bruit que la marche avant (plus de bonus ×4).
    rev_mult = 1.0
    rudder_mult = 1.0 + max(0.0, min(1.0, rudder_ratio))
    if speed_ratio > snl:
        return base_noise * speed_ratio * rudder_mult * rev_mult
    # Sous le seuil : formule "minNoise" proportionnel à sr/snl.
    if snl <= 0:
        return 0.0
    return min_noise * (speed_ratio / snl) * rudder_mult * rev_mult


def perceived_noise(emitted_noise: float, distance_m: float) -> float:
    """Bruit perçu à une distance donnée. Atténuation quadratique au-delà de 100m.
    perçu = émis × (1000 / max(distance_m, 100))²
    Constante de référence 1000m (= émis), mais plancher à 100m :
      - À ≥1km : 1/d² standard (à 2km perçu=émis/4, à 10km perçu=émis/100)
      - À 1km : perçu = émis (point de référence)
      - À 500m : perçu = 4 × émis
      - À 200m : perçu = 25 × émis
      - À ≤100m : perçu = 100 × émis (plancher, on est "collé")
    Le plancher à 100m donne la résolution fine sous 1km : la torpille
    acoustique peut distinguer un bateau à 200m d'un autre à 800m."""
    if emitted_noise <= 0:
        return 0.0
    d = max(distance_m, 100.0)
    ratio = 1000.0 / d
    return emitted_noise * ratio * ratio


# ===================== Teams =====================

DEFAULT_BOT_TEAM_ID = "bots"
DEFAULT_BOT_TEAM_NAME = "Bots"
DEFAULT_HUMAN_TEAM_ID = "team1"
DEFAULT_HUMAN_TEAM_NAME = "Équipe 1"


def get_team_id(player_dict: Dict[str, Any]) -> str:
    """Retourne le team_id de l'entité (player ou bot dict). Fallback :
    - is_bot=True → DEFAULT_BOT_TEAM_ID
    - sinon → DEFAULT_HUMAN_TEAM_ID
    """
    if not player_dict:
        return DEFAULT_HUMAN_TEAM_ID
    tid = player_dict.get("team_id")
    if tid:
        return tid
    return DEFAULT_BOT_TEAM_ID if player_dict.get("is_bot") else DEFAULT_HUMAN_TEAM_ID


def same_team(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Vrai si a et b sont dans la même équipe."""
    return get_team_id(a) == get_team_id(b)


# ===================== Sim =====================

class Sim:
    def __init__(self, world_data: Dict[str, Any], clock=None):
        """`clock` : callable() -> float renvoyant le temps en secondes. Si None,
        utilise time.time() (mode serveur live). En mode RL/test, on peut
        injecter une horloge contrôlée pour découpler du wall-clock :
            sim_t = [0.0]
            sim = Sim(world, clock=lambda: sim_t[0])
            # à chaque step : sim_t[0] += dt"""
        self.world_data = world_data
        self._clock = clock if clock is not None else time.time
        self.t: float = self._clock()
        self.trace_rl_decisions: bool = False
        self.trace_step: int = 0

        # État principal (pointé vers les globals server.py via set_legacy_hooks).
        self.players: Dict[str, Any] = {}
        self.bots: Dict[str, Any] = {}
        self.torpedoes: Dict[Any, Any] = {}
        self.drones: Dict[Any, Any] = {}
        self.grenades: Dict[Any, Any] = {}
        self.mines: Dict[Any, Any] = {}
        self.beacons: Dict[int, Any] = {}
        self.lures: Dict[Any, Any] = {}
        # Stockage des torpilles filo actives par tireur (pointé vers server.active_wire_torpedoes).
        self._active_wire = {}

        # Cache zones danger (couronne autour des îles), invalidé sur changement de monde.
        self._danger_zones_cache: Dict[str, Any] = {"world_id": None, "zones": []}

        # Buffer d'events.
        self._events: List[ev_mod.Event] = []

        # Obus sans cible vivante, avances par l'horloge de simulation.
        self.cannon_shells: List[Dict[str, Any]] = []
        self._next_cannon_shot = 0
        self._pending_sonar_pings: List[Dict[str, Any]] = []
        self._sonar_reveals: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Hooks legacy.
        self._legacy = None

    # ===================== Horloge =====================

    def now(self) -> float:
        """Heure courante de la simu. En mode serveur live = time.time().
        En mode RL/test, l'horloge injectée avance en pas de simu."""
        return self._clock()

    def set_clock(self, clock) -> None:
        self._clock = clock

    # ===================== Hooks =====================

    def set_legacy_hooks(self, server_module):
        self._legacy = server_module
        self.players = server_module.players
        self.bots = server_module.bots
        self.torpedoes = server_module.torpedoes_server
        self.drones = server_module.drones_server
        self.grenades = server_module.grenades_server
        self.mines = server_module.mines_server
        self.beacons = server_module.sonar_beacons
        self.lures = server_module.server_lures
        self._active_wire = server_module.active_wire_torpedoes

    # ===================== Events =====================

    def emit(self, event: ev_mod.Event) -> None:
        self._events.append(event)

    def drain_events(self) -> List[ev_mod.Event]:
        out = self._events
        self._events = []
        return out

    # ===================== Helpers privés (notifications torpilles) =====================

    def _owner_sid_for_player(self, sid: str) -> Optional[str]:
        """Pour un sid d'un humain (primaire ou secondaire), renvoie le sid
        socket réel du propriétaire. Pour un bot, None."""
        if not sid:
            return None
        if sid.startswith("__bot__"):
            return None
        return self._legacy.human_owner_sid.get(sid, sid)

    def _notify_torpedo_acquisition(self, t, target_id, *, acquired, destroyed=False, reason=None):
        """Émet TorpedoAcquisition au sid humain dont le playerId == target_id.
        Pas d'événement pour les bots (pas d'UI)."""
        if not target_id:
            return
        for sid, p in self.players.items():
            if p.get("id") != target_id:
                continue
            if p.get("is_bot"):
                return
            socket_sid = self._owner_sid_for_player(sid)
            if not socket_sid:
                return
            self.emit(ev_mod.TorpedoAcquisition(
                shooter_id=t["ownerPlayerId"],
                tid=t["tid"],
                kind=t["kind"],
                acquired=bool(acquired),
                destroyed=bool(destroyed),
                reason=reason,
                outgoing=False,
                target_sid=socket_sid,
            ))
            return

    def _notify_shooter_status(self, t, *, acquired=None, destroyed=False, reason=None, launched=False):
        """Miroir tireur (vert) : TorpedoAlert si launched, sinon TorpedoAcquisition outgoing."""
        sid = t.get("ownerSid")
        if not sid:
            return
        p = self.players.get(sid)
        if not p or p.get("is_bot"):
            return
        socket_sid = self._owner_sid_for_player(sid)
        if not socket_sid:
            return
        if launched:
            self.emit(ev_mod.TorpedoAlert(
                shooter_id=t["ownerPlayerId"],
                tid=t["tid"],
                kind=t["kind"],
                outgoing=True,
                target_sid=socket_sid,
            ))
            return
        self.emit(ev_mod.TorpedoAcquisition(
            shooter_id=t["ownerPlayerId"],
            tid=t["tid"],
            kind=t["kind"],
            acquired=bool(acquired),
            destroyed=bool(destroyed),
            reason=reason,
            outgoing=True,
            target_sid=socket_sid,
        ))

    def _emit_torpedo_state(self, t):
        """Emet TorpedoState avec le point connu, sans resoudre de cible vivante."""
        tx = ty = tz = None
        activated = t["traveled"] >= t["activation"]
        # Avant la distance d'activation, la torpille ne fait que rejoindre son
        # cap initial : pas de cible acquise → on ne transmet aucune cible (sinon
        # le client affiche "en acquisition" alors qu'elle n'est pas armée).
        if activated:
            last = t.get("lastAcquiredPos")
            if last:
                tx = last[0]
                tz = last[2]
                if len(last) > 1 and last[1] is not None:
                    ty = last[1]
            elif t.get("initialTarget"):
                it = t["initialTarget"]
                if len(it) == 3:
                    tx, ty, tz = it
                else:
                    tx = it[0]
                    tz = it[1]
        self.emit(ev_mod.TorpedoState(
            owner_id=t["ownerPlayerId"],
            tid=t["tid"],
            kind=t["kind"],
            x=t["x"], y=t["y"], z=t["z"],
            dir_x=t["dirX"], dir_z=t["dirZ"],
            target_x=tx, target_y=ty, target_z=tz,
        ))

    # ===================== Acquisition =====================

    def _pick_acoustic(self, t, block_thermocline=False):
        """Acquisition acoustique : cherche la meilleure cible (bateau ou leurre)
        dont le bruit perçu (atténué par la distance) dépasse le seuil minNoise
        de la torpille et qui se trouve dans son cône avant. Requiert LOS directe.

        block_thermocline=True : toute cible séparée de la torpille par une
        thermocline est IGNORÉE (pas seulement atténuée). Utilisé par la torpille
        autonome dont le fallback acoustique ne doit pas voir à travers une
        thermocline (cohérent avec son sonar actif). Pour la torpille acoustique
        (False), l'atténuation -80% par couche s'applique normalement."""
        threshold = float(t.get("minNoise", 4.0))
        best_perceived = 0.0
        best_pos = None
        best_key = None
        best_boat_id = None
        line_of_sight_clear = self._legacy.line_of_sight_clear
        count_thermoclines = self._legacy.count_thermoclines_crossed
        world_data = self.world_data
        tx = t["x"]
        ty = t.get("y", 0)
        tz = t["z"]
        half_angle = max(0.0, min(math.pi, float(t.get("radarHalfAngle", math.pi))))
        cos_half = math.cos(half_angle)
        fwd_len = math.hypot(t["dirX"], t["dirZ"])
        fx = t["dirX"] / fwd_len if fwd_len > 0.001 else 0.0
        fz = t["dirZ"] / fwd_len if fwd_len > 0.001 else 0.0
        # Bateaux
        for sid, p in self.players.items():
            boat = p.get("boat") or {}
            sr = float(p.get("speedRatio") or 0)
            if sr == 0 and p.get("is_bot"):
                p_speed = abs(float(p.get("speed", 0)))
                p_max = float(p.get("max_speed_us", 1.0))
                sr = min(1.0, p_speed / max(0.001, p_max))
            rev = bool(p.get("reverse"))
            rudder_max = float(p.get("rudder_max") or boat.get("rudderMax") or 15.0)
            rud = abs(float(p.get("rudder", 0))) / max(0.001, rudder_max)
            emitted = compute_emitted_noise(boat, sr, rev, rud)
            if emitted <= 0:
                continue
            pos = p.get("position") or {}
            px = pos.get("x", 0)
            pz = pos.get("z", 0)
            py = pos.get("y", 0)
            dx = px - tx
            dz = pz - tz
            dist = math.hypot(dx, dz)
            if fwd_len > 0.001 and dist > 0.001 and (dx * fx + dz * fz) / dist < cos_half:
                continue
            dist_m = dist * UNIT_METERS_BOT
            perceived = perceived_noise(emitted, dist_m)
            # Thermocline : -80% par couche (acoustique) OU blocage total (autonome).
            nc = count_thermoclines(px, py, pz, tx, ty, tz, world_data, UNIT_METERS_BOT)
            if nc > 0:
                if block_thermocline:
                    continue
                perceived *= THERMOCLINE_NOISE_FACTOR ** nc
            if perceived < threshold:
                continue
            if perceived > best_perceived:
                if not line_of_sight_clear(tx, tz, px, pz, world_data):
                    continue
                best_perceived = perceived
                best_pos = (px, py, pz)
                best_key = "boat:" + p["id"]
                best_boat_id = p["id"]
        # Leurres acoustiques
        now = self.t
        expired_keys = []
        for lkey, lure in self.lures.items():
            if now >= lure["expiresAt"]:
                expired_keys.append(lkey)
                continue
            lure_emit = float(lure.get("noise") or 0)
            if lure_emit <= 0:
                continue
            lx = lure["x"]
            lz = lure["z"]
            ly = lure.get("y", 0)
            dx = lx - tx
            dz = lz - tz
            dist = math.hypot(dx, dz)
            if fwd_len > 0.001 and dist > 0.001 and (dx * fx + dz * fz) / dist < cos_half:
                continue
            dist_m = dist * UNIT_METERS_BOT
            perceived = perceived_noise(lure_emit, dist_m)
            # Thermocline : -80% par couche (acoustique) OU blocage total (autonome).
            nc = count_thermoclines(lx, ly, lz, tx, ty, tz, world_data, UNIT_METERS_BOT)
            if nc > 0:
                if block_thermocline:
                    continue
                perceived *= THERMOCLINE_NOISE_FACTOR ** nc
            if perceived < threshold:
                continue
            if perceived > best_perceived:
                if not line_of_sight_clear(tx, tz, lx, lz, world_data):
                    continue
                best_perceived = perceived
                best_pos = (lx, ly, lz)
                best_key = "lure:" + str(lkey[0]) + ":" + str(lkey[1])
                best_boat_id = None
        for k in expired_keys:
            lure = self.lures.pop(k, None)
            if lure:
                self.emit(ev_mod.LureDestroyed(owner_id=lure["ownerId"], lid=lure["lid"]))
        return {"key": best_key, "pos": best_pos, "boatId": best_boat_id, "intensity": best_perceived}

    def _pick_radar(self, t, world_data):
        """Acquisition radar : le tireur est exclu. Les leurres acoustiques actifs
        sont aussi vus comme des échos radar (contre-mesure radar).
        Mode poursuite : si la torpille a déjà verrouillé une cible radar (lockedKey
        commence par 'radar:'), elle accepte un cône élargi (×3) pour la garder
        verrouillée pendant les manœuvres d'esquive. Sinon, cône standard.
        """
        rng = t.get("radarRange", 0.0)
        if rng <= 0:
            return None
        half_angle = t.get("radarHalfAngle", 0.0)
        cos_half = math.cos(half_angle)
        # Cône élargi pour le tracking d'une cible déjà acquise.
        # half_angle ×3 (par ex 30° → 90°), capé à 90° (demi-cercle avant).
        wide_half = min(math.pi / 2, half_angle * 3.0)
        cos_wide = math.cos(wide_half)
        prev_locked_key = t.get("lockedKey") or ""
        prev_locked_kind = None  # "boat" | "lure" | "torp" | None
        prev_locked_id = None
        if prev_locked_key.startswith("radar_torp:"):
            prev_locked_kind = "torp"
            prev_locked_id = prev_locked_key[len("radar_torp:"):]
        elif prev_locked_key.startswith("radar:"):
            prev_locked_kind = "boat"
            prev_locked_id = prev_locked_key[len("radar:"):]
        elif prev_locked_key.startswith("radar_lure:"):
            prev_locked_kind = "lure"
            prev_locked_id = prev_locked_key[len("radar_lure:"):]
        fwd_len = math.hypot(t["dirX"], t["dirZ"]) or 1.0
        fx = t["dirX"] / fwd_len
        fz = t["dirZ"] / fwd_len
        best_dist = float("inf")
        best_pos = None
        best_boat_id = None
        best_key = None
        owner_pid = t["ownerPlayerId"]
        line_of_sight_clear = self._legacy.line_of_sight_clear
        _count_thermo = self._legacy.count_thermoclines_crossed
        ty = t.get("y", 0)
        # La torpille autonome utilise un SONAR ACTIF : il ne franchit pas une
        # thermocline (sauf pénétration aléatoire via thermoclinePenetration).
        _tc_pen = t.get("thermoclinePenetration", 0)
        # Un resultat par entite et par passe, partage entre priorite/suivi/scan.
        thermo_results: Dict[Tuple[str, Any], bool] = {}
        def thermo_blocks(key: Tuple[str, Any], px: float, py: float, pz: float) -> bool:
            if key not in thermo_results:
                crossed = _count_thermo(t["x"], ty, t["z"], px, py, pz, world_data, UNIT_METERS_BOT) > 0
                thermo_results[key] = crossed and (_tc_pen <= 0 or random.random() >= _tc_pen)
            return thermo_results[key]
        now = self.t

        # Purge des leurres expirés.
        expired_keys = [k for k, lure in self.lures.items() if now >= lure["expiresAt"]]
        for k in expired_keys:
            lure = self.lures.pop(k, None)
            if lure:
                self.emit(ev_mod.LureDestroyed(owner_id=lure["ownerId"], lid=lure["lid"]))

        # -1) LEURRE PRIORITAIRE : un leurre acoustique actif dans le cône radar et
        #     à courte portée (largué juste devant la torpille) rompt le verrou et
        #     détourne la torpille — y compris une autonome verrouillée sur sa
        #     cible initiale. C'est le rôle d'une contre-mesure. On prend le leurre
        #     le plus proche dans le cône, sous une portée de capture généreuse.
        LURE_RADAR_CAPTURE_U = 2000.0 / UNIT_METERS_BOT  # 2 km
        best_lure_dist = float("inf")
        best_lure = None
        for lkey, lure in self.lures.items():
            lx = lure["x"]
            lz = lure["z"]
            ly = lure.get("y", 0)
            dx = lx - t["x"]
            dz = lz - t["z"]
            dist = math.hypot(dx, dz)
            if dist <= 0.001 or dist > min(rng, LURE_RADAR_CAPTURE_U):
                continue
            cos_ang = (dx * fx + dz * fz) / dist
            if cos_ang < cos_wide:
                continue
            if not line_of_sight_clear(t["x"], t["z"], lx, lz, world_data):
                continue
            if thermo_blocks(("lure", lkey), lx, ly, lz):
                continue
            if dist < best_lure_dist:
                best_lure_dist = dist
                best_lure = (lx, ly, lz, lkey)
        if best_lure is not None:
            lx, ly, lz, lkey = best_lure
            return {
                "key": "radar_lure:" + str(lkey[0]) + ":" + str(lkey[1]),
                "pos": (lx, ly, lz),
                "boatId": None,
                "intensity": 1.0 / max(1.0, best_lure_dist * best_lure_dist),
            }

        # 0) Priorité ABSOLUE à la cible initiale du lancement : tant qu'elle est
        #    dans le radar (cône élargi + portée + LOS), la torpille ne la lâche
        #    JAMAIS pour une autre, même si une cible plus proche apparaît. Elle ne
        #    cherche une nouvelle cible que si la cible initiale sort du radar.
        initial_target_id = t.get("targetId")
        if initial_target_id and initial_target_id != owner_pid:
            for sid, p in self.players.items():
                if p.get("id") != initial_target_id:
                    continue
                pos = p.get("position") or {}
                px = pos.get("x", 0)
                pz = pos.get("z", 0)
                py = pos.get("y", 0)
                dx = px - t["x"]
                dz = pz - t["z"]
                dist = math.hypot(dx, dz)
                if dist <= 0.001 or dist > rng:
                    break
                cos_ang = (dx * fx + dz * fz) / dist
                # Cône élargi : on garde la cible initiale tant qu'elle reste dans
                # le demi-cercle avant (même tolérance que le tracking d'esquive).
                if cos_ang < cos_wide:
                    break
                if not line_of_sight_clear(t["x"], t["z"], px, pz, world_data):
                    break
                if thermo_blocks(("boat", p["id"]), px, py, pz):
                    break
                return {
                    "key": "radar:" + initial_target_id,
                    "pos": (px, py, pz),
                    "boatId": initial_target_id,
                    "intensity": 1.0 / max(1.0, dist * dist),
                }

        # 1) Tracking : si on avait déjà verrouillé une cible radar, on tente de la
        #    retrouver dans le cône élargi en priorité.
        if prev_locked_kind == "boat":
            for sid, p in self.players.items():
                if p.get("id") != prev_locked_id:
                    continue
                if p.get("id") == owner_pid:
                    break
                pos = p.get("position") or {}
                px = pos.get("x", 0)
                pz = pos.get("z", 0)
                py = pos.get("y", 0)
                dx = px - t["x"]
                dz = pz - t["z"]
                dist = math.hypot(dx, dz)
                if dist <= 0.001 or dist > rng:
                    break
                cos_ang = (dx * fx + dz * fz) / dist
                if cos_ang < cos_wide:
                    break
                if not line_of_sight_clear(t["x"], t["z"], px, pz, world_data):
                    break
                if thermo_blocks(("boat", p["id"]), px, py, pz):
                    break
                return {
                    "key": "radar:" + prev_locked_id,
                    "pos": (px, py, pz),
                    "boatId": prev_locked_id,
                    "intensity": 1.0 / max(1.0, dist * dist),
                }
        elif prev_locked_kind == "lure":
            for lkey, lure in self.lures.items():
                lure_key = str(lkey[0]) + ":" + str(lkey[1])
                if lure_key != prev_locked_id:
                    continue
                lx = lure["x"]
                lz = lure["z"]
                ly = lure.get("y", 0)
                dx = lx - t["x"]
                dz = lz - t["z"]
                dist = math.hypot(dx, dz)
                if dist <= 0.001 or dist > rng:
                    break
                cos_ang = (dx * fx + dz * fz) / dist
                if cos_ang < cos_wide:
                    break
                if not line_of_sight_clear(t["x"], t["z"], lx, lz, world_data):
                    break
                if thermo_blocks(("lure", lkey), lx, ly, lz):
                    break
                return {
                    "key": "radar_lure:" + lure_key,
                    "pos": (lx, ly, lz),
                    "boatId": None,
                    "intensity": 1.0 / max(1.0, dist * dist),
                }
        elif prev_locked_kind == "torp":
            for okey, ot in self.torpedoes.items():
                ot_lock_key = str(okey[0]) + ":" + str(okey[1])
                if ot_lock_key != prev_locked_id:
                    continue
                ox = ot["x"]
                oz = ot["z"]
                oy = ot["y"]
                dx = ox - t["x"]
                dz = oz - t["z"]
                dist = math.hypot(dx, dz)
                if dist <= 0.001 or dist > rng:
                    break
                cos_ang = (dx * fx + dz * fz) / dist
                if cos_ang < cos_wide:
                    break
                if not line_of_sight_clear(t["x"], t["z"], ox, oz, world_data):
                    break
                if thermo_blocks(("torp", okey), ox, oy, oz):
                    break
                return {
                    "key": "radar_torp:" + ot_lock_key,
                    "pos": (ox, oy, oz),
                    "boatId": None,
                    "intensity": 1.0 / max(1.0, dist * dist),
                }
        # 2) Acquisition initiale : cône standard (étroit). Plus proche gagne,
        #    La cible initiale a déjà été traitée en priorité absolue (section 0)
        #    tant qu'elle est dans le radar ; ici on cherche une cible de
        #    remplacement (plus proche gagne) quand elle est sortie du radar.
        for sid, p in self.players.items():
            if p.get("id") == owner_pid:
                continue
            pos = p.get("position") or {}
            px = pos.get("x", 0)
            pz = pos.get("z", 0)
            py = pos.get("y", 0)
            dx = px - t["x"]
            dz = pz - t["z"]
            dist = math.hypot(dx, dz)
            if dist <= 0.001 or dist > rng:
                continue
            cos_ang = (dx * fx + dz * fz) / dist
            if cos_ang < cos_half:
                continue
            if not line_of_sight_clear(t["x"], t["z"], px, pz, world_data):
                continue
            if thermo_blocks(("boat", p["id"]), px, py, pz):
                continue
            if dist < best_dist:
                best_dist = dist
                best_pos = (px, py, pz)
                best_boat_id = p["id"]
                best_key = "radar:" + p["id"]
        for lkey, lure in self.lures.items():
            lx = lure["x"]
            lz = lure["z"]
            ly = lure.get("y", 0)
            dx = lx - t["x"]
            dz = lz - t["z"]
            dist = math.hypot(dx, dz)
            if dist <= 0.001 or dist > rng:
                continue
            cos_ang = (dx * fx + dz * fz) / dist
            if cos_ang < cos_half:
                continue
            if not line_of_sight_clear(t["x"], t["z"], lx, lz, world_data):
                continue
            if thermo_blocks(("lure", lkey), lx, ly, lz):
                continue
            if dist < best_dist:
                best_dist = dist
                best_pos = (lx, ly, lz)
                best_boat_id = None
                best_key = "radar_lure:" + str(lkey[0]) + ":" + str(lkey[1])
        # 3) Anti-torpille : scan des torpilles PRIORITAIRE sur bateaux/leurres.
        #    Si une torpille est dans le cône, elle est choisie même si un bateau
        #    est plus proche.
        if t.get("antiTorpedo"):
            tkey_self = (t["ownerPlayerId"], t["tid"])
            torp_best_dist = float("inf")
            torp_best_pos = None
            torp_best_key = None
            for okey, ot in self.torpedoes.items():
                if okey == tkey_self:
                    continue
                ox = ot["x"]
                oz = ot["z"]
                oy = ot["y"]
                dx = ox - t["x"]
                dz = oz - t["z"]
                dist = math.hypot(dx, dz)
                if dist <= 0.001 or dist > rng:
                    continue
                cos_ang = (dx * fx + dz * fz) / dist
                ot_lock_key = "radar_torp:" + str(okey[0]) + ":" + str(okey[1])
                use_cos = cos_wide if prev_locked_key == ot_lock_key else cos_half
                if cos_ang < use_cos:
                    continue
                if not line_of_sight_clear(t["x"], t["z"], ox, oz, world_data):
                    continue
                if thermo_blocks(("torp", okey), ox, oy, oz):
                    continue
                if dist < torp_best_dist:
                    torp_best_dist = dist
                    torp_best_pos = (ox, oy, oz)
                    torp_best_key = ot_lock_key
            if torp_best_pos is not None:
                return {
                    "key": torp_best_key,
                    "pos": torp_best_pos,
                    "boatId": None,
                    "intensity": 1.0 / max(1.0, torp_best_dist * torp_best_dist),
                }
        if best_pos is None:
            return None
        return {
            "key": best_key,
            "pos": best_pos,
            "boatId": best_boat_id,
            "intensity": 1.0 / max(1.0, best_dist * best_dist),
        }

    # ===================== Explosion =====================

    def _explode_torpedo(self, t, *, direct_hit_id, damage, hit_target_id, hit_lure=False, silent=False, reason=None):
        if silent:
            self.emit(ev_mod.TorpedoDead(owner_id=t["ownerPlayerId"], tid=t["tid"], reason=reason))
            for tgt in t.get("notifiedTargets") or []:
                self._notify_torpedo_acquisition(t, tgt, acquired=False, destroyed=True, reason="lost")
            self._notify_shooter_status(t, acquired=False, destroyed=True, reason="lost")
            pid_s = t["ownerPlayerId"]
            if self._active_wire.get(pid_s) == (pid_s, t["tid"]):
                self._active_wire.pop(pid_s, None)
            return
        self.emit(ev_mod.TorpedoExploded(
            owner_id=t["ownerPlayerId"],
            x=t["x"], y=t["y"], z=t["z"],
            damage=damage,
            direct_hit_id=direct_hit_id,
            hit_lure=hit_lure,
        ))
        self.emit(ev_mod.TorpedoDead(owner_id=t["ownerPlayerId"], tid=t["tid"]))
        hit_a_boat = bool(hit_target_id)
        for tgt in t.get("notifiedTargets") or []:
            if hit_a_boat and tgt == hit_target_id:
                reason = "hit_self"
            elif hit_a_boat:
                reason = "hit_other"
            else:
                reason = "lost"
            self._notify_torpedo_acquisition(t, tgt, acquired=False, destroyed=True, reason=reason)
        shooter_reason = "hit_other" if (hit_a_boat or hit_lure) else "lost"
        self._notify_shooter_status(t, acquired=False, destroyed=True, reason=shooter_reason)
        # Dégâts directs.
        attacker_id = t["ownerPlayerId"]
        splash_radius_u = BOT_SPLASH_RADIUS_M / UNIT_METERS_BOT
        if direct_hit_id:
            bsid, bot = self.find_bot_by_player_id(direct_hit_id)
            if bot is not None:
                self.bot_apply_damage(bsid, bot, damage, attacker_id)
            else:
                for sid_h, p_h in self.players.items():
                    if p_h.get("id") == direct_hit_id and not p_h.get("is_bot"):
                        self.apply_player_damage(sid_h, p_h, damage, attacker_id)
                        break
        else:
            self.bot_splash_damage(t["x"], t["y"], t["z"], damage, attacker_id)
            self.player_splash_damage(t["x"], t["y"], t["z"], damage, attacker_id, splash_radius_u)
        self.lure_splash_damage(t["x"], t["y"], t["z"], damage, splash_radius_u)
        # Filoguidée : libérer le slot.
        pid = t["ownerPlayerId"]
        if self._active_wire.get(pid) == (pid, t["tid"]):
            self._active_wire.pop(pid, None)

    # ===================== Tick principal des torpilles =====================

    def update_server_torpedoes(self, dt: float, world_data: Dict[str, Any]) -> None:
        """Avance toutes les torpilles serveur d'un tick. Émet via events."""
        legacy = self._legacy
        if legacy is None:
            return
        now_t = self.now()
        for key, lure in list(self.lures.items()):
            if now_t < lure["expiresAt"]:
                continue
            self.lures.pop(key, None)
            self.emit(ev_mod.LureDestroyed(owner_id=lure["ownerId"], lid=lure["lid"]))
        # Refs vers helpers legacy encore externes.
        point_in_polygon = legacy.point_in_polygon
        ensure_island_bounds = legacy._ensure_island_bounds
        closest_approach_on_segment = legacy.closest_approach_on_segment
        segments_intersect = legacy.segments_intersect
        distance_point_segment = legacy.distance_point_segment
        explode_server_mine = self.explode_server_mine

        HIT_VERTICAL_U = 0.4
        PROX_VERTICAL_U = 1.0
        PROX_DISTANCE_U = 80.0 / UNIT_METERS_BOT
        TORPEDO_EMIT_INTERVAL = 0.1
        ground = world_data.get("ground")
        bounds = (ground["width"] / 2, ground["depth"] / 2) if ground else None

        def inside_map(x: float, z: float) -> bool:
            return bounds is None or (-bounds[0] <= x <= bounds[0] and
                                      -bounds[1] <= z <= bounds[1])

        # Purger avant tout capteur ou collision, independamment de l'ordre des tirs.
        for key, t in list(self.torpedoes.items()):
            if not inside_map(t["x"], t["z"]):
                self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None,
                                      silent=True, reason="map_bounds")
                self.torpedoes.pop(key, None)
        for key in list(self.torpedoes.keys()):
            t = self.torpedoes.get(key)
            if t is None:
                continue
            activated = t["traveled"] >= t["activation"]
            target = None  # (x, y, z)

            # ---- Acquisition / pilotage ----
            if t["kind"] == "wireGuided" and self._active_wire.get(t["ownerPlayerId"]) == key:
                yaw_in = t.get("wireYaw", 0)
                pitch_in = t.get("wirePitch", 0)
                if yaw_in != 0:
                    turn_rate = t["speed"] / max(0.1, t["minTurnRadius"])
                    rot = math.atan2(t["dirZ"], -t["dirX"])
                    rot += yaw_in * turn_rate * dt
                    t["dirX"] = -math.cos(rot)
                    t["dirZ"] = math.sin(rot)
                PITCH_RATE = math.pi / 4
                PITCH_MAX = math.pi / 6
                if pitch_in > 0:
                    t["pitch"] = min(PITCH_MAX, t["pitch"] + PITCH_RATE * dt)
                elif pitch_in < 0:
                    t["pitch"] = max(-PITCH_MAX, t["pitch"] - PITCH_RATE * dt)
            elif activated and t["kind"] in ("acoustic", "autonomous"):
                pick = None
                if t["kind"] == "autonomous":
                    pick = self._pick_radar(t, world_data)
                if not pick:
                    # La torpille autonome ne voit pas à travers une thermocline,
                    # même en fallback acoustique (blocage total). L'acoustique
                    # pure garde son atténuation -80%.
                    pick = self._pick_acoustic(t, block_thermocline=(t["kind"] == "autonomous"))
                if pick and pick.get("pos"):
                    target = pick["pos"]
                    t["lastAcquiredPos"] = target
                    if t["lockedKey"] == pick["key"]:
                        if pick["intensity"] > t["lastIntensity"]:
                            t["lastIntensity"] = pick["intensity"]
                            t["acquired"] = True
                    else:
                        t["lockedKey"] = pick["key"]
                        t["lastIntensity"] = pick["intensity"]
                        t["acquired"] = False
                    if not t.get("inAcquisition"):
                        t["inAcquisition"] = True
                        for tgt in list(t.get("notifiedTargets") or []):
                            self._notify_torpedo_acquisition(t, tgt, acquired=True)
                        self._notify_shooter_status(t, acquired=True)
                    locked_boat_id = pick.get("boatId")
                    if locked_boat_id and locked_boat_id not in t["notifiedTargets"]:
                        self._notify_torpedo_acquisition(t, locked_boat_id, acquired=True)
                        t["notifiedTargets"].add(locked_boat_id)
                    t["acquiredBoatId"] = locked_boat_id
                else:
                    if t.get("inAcquisition"):
                        t["inAcquisition"] = False
                        for tgt in list(t.get("notifiedTargets") or []):
                            self._notify_torpedo_acquisition(t, tgt, acquired=False)
                        self._notify_shooter_status(t, acquired=False)
                    t["acquiredBoatId"] = None
                    t["lockedKey"] = None
                    t["lastIntensity"] = 0
                    t["acquired"] = False
                    # Sans capteur : profondeur tenue, cap courant avec evitement
                    # local conserve. Ce point projete n'est pas un souvenir cible.
                    horizon = max(t["minTurnRadius"] * 1.5, t["speed"] * 1.5)
                    target = (t["x"] + t["dirX"] * horizon, None,
                              t["z"] + t["dirZ"] * horizon)
                    t["pitch"] = 0.0
            elif not activated and t["initialTarget"]:
                it = t["initialTarget"]
                itx2 = it[0]
                if len(it) == 3:
                    ity2, itz2 = it[1], it[2]
                else:
                    ity2, itz2 = None, it[1]
                dist2d2 = math.hypot(itx2 - t["x"], itz2 - t["z"])
                if dist2d2 < 1.0:
                    t["initialTarget"] = None
                else:
                    ahead2 = (itx2 - t["x"]) * t["dirX"] + (itz2 - t["z"]) * t["dirZ"]
                    if ahead2 >= 0:
                        t["initialTargetTracked"] = True
                        target = (itx2, ity2, itz2)
                    elif t.get("initialTargetTracked"):
                        t["initialTarget"] = None  # dépassé → cap maintenu
                    else:
                        target = (itx2, ity2, itz2)  # pas encore pointé vers lui

            # ---- Cap & pitch vers la cible ----
            if target:
                tx = target[0]
                ty = target[1]
                tz = target[2]
                tdx = tx - t["x"]
                tdz = tz - t["z"]
                td_len = math.hypot(tdx, tdz)
                if td_len > 0.001:
                    des_x = tdx / td_len
                    des_z = tdz / td_len
                    horizon = min(td_len, max(t["minTurnRadius"] * 1.5, t["speed"] * 1.5))
                    des_x, des_z = torpedo_avoid_island(
                        t, des_x, des_z, horizon, world_data,
                        point_in_polygon=point_in_polygon,
                        ensure_island_bounds=ensure_island_bounds,
                    )
                    max_step = (t["speed"] * dt) / max(0.1, t["minTurnRadius"])
                    cur = math.atan2(t["dirZ"], t["dirX"])
                    want = math.atan2(des_z, des_x)
                    delta = ((want - cur) + math.pi * 3) % (math.pi * 2) - math.pi
                    step = max(-max_step, min(max_step, delta))
                    nu = cur + step
                    t["dirX"] = math.cos(nu)
                    t["dirZ"] = math.sin(nu)
                if ty is not None:
                    dy_t = ty - t["y"]
                    dy_m = abs(dy_t) * UNIT_METERS_BOT
                    # Pitch agressif tant qu'on est loin de la profondeur cible.
                    # Évite le problème du proportional controller asymptotique :
                    # sur 2km, pitch=atan2(dy, dist) donne 1° → la torpille n'a
                    # pas le temps de descendre. On force ±15° (~6.5 m/s vert.
                    # à 50 nds) tant qu'on est à plus de 5m de la profondeur
                    # cible, puis on stabilise par calcul classique pour le
                    # rapprochement final.
                    if dy_m > 2.0:
                        AGGRESSIVE_PITCH = math.radians(15.0)
                        t["pitch"] = AGGRESSIVE_PITCH if dy_t > 0 else -AGGRESSIVE_PITCH
                    else:
                        # Très proche : recalibre finement sur petit horizon.
                        # Plancher à 1 u (10 m) : évite pitch ≈ 90° quand
                        # td_len → 0 (torpille directement au-dessus de la
                        # cible), ce qui bloque l'avance horizontale.
                        horiz_dist = max(1.0, min(td_len, 5.0))
                        t["pitch"] = math.atan2(dy_t, horiz_dist)

            # ---- Avancée ----
            # Borner le segment avant les collisions, pas seulement apres l'avancee.
            travel_step = t["speed"] * dt
            if t["maxRange"] > 0:
                travel_step = min(travel_step, max(0.0, t["maxRange"] - t["traveled"]))
            cos_p = math.cos(t["pitch"])
            sin_p = math.sin(t["pitch"])
            nx = t["x"] + t["dirX"] * cos_p * travel_step
            nz = t["z"] + t["dirZ"] * cos_p * travel_step
            leaves_map = not inside_map(nx, nz)
            if leaves_map:
                fraction = 1.0
                for start, end, half in ((t["x"], nx, bounds[0]),
                                         (t["z"], nz, bounds[1])):
                    if end > half:
                        fraction = min(fraction, (half - start) / (end - start))
                    elif end < -half:
                        fraction = min(fraction, (-half - start) / (end - start))
                travel_step *= fraction
                nx = max(-bounds[0], min(bounds[0], t["x"] + (nx - t["x"]) * fraction))
                nz = max(-bounds[1], min(bounds[1], t["z"] + (nz - t["z"]) * fraction))
            ny = min(TORPEDO_CEILING_Y, t["y"] + sin_p * travel_step)

            # ---- Collisions (uniquement APRÈS la distance d'activation) ----
            # Avant activation, la torpille ne fait QUE rejoindre sa cible initiale :
            # elle ignore totalement bateaux, balises, leurres, mines et torpilles
            # (elle ne peut ni exploser ni être détournée). Seules les îles la
            # bloquent (sinon elle traverserait le terrain).
            exploded = False
            owner_pid = t["ownerPlayerId"]
            if activated:
                for sid_p, p in list(self.players.items()):
                    pos = p.get("position") or {}
                    px = pos.get("x", 0)
                    py = pos.get("y", 0)
                    pz = pos.get("z", 0)
                    if not inside_map(px, pz):
                        continue
                    dy = abs(py - t["y"])
                    if dy > PROX_VERTICAL_U:
                        continue
                    boat = p.get("boat") or {}
                    length_m = float(boat.get("lengthMeters") or 100.0)
                    half_u = (length_m * 0.5) / UNIT_METERS_BOT
                    rot = float(p.get("rotation") or 0)
                    hx = -math.cos(rot)
                    hz = math.sin(rot)
                    bow_x = px + hx * half_u
                    bow_z = pz + hz * half_u
                    stern_x = px - hx * half_u
                    stern_z = pz - hz * half_u
                    direct = dy <= HIT_VERTICAL_U and segments_intersect(
                        t["x"], t["z"], nx, nz, bow_x, bow_z, stern_x, stern_z
                    )
                    if direct:
                        t["x"], t["z"] = px, pz
                        self._explode_torpedo(t, direct_hit_id=p["id"], damage=t["damage"], hit_target_id=p["id"])
                        exploded = True
                        break
                    t_raw, cpa = closest_approach_on_segment(px, pz, t["x"], t["z"], nx, nz)
                    if 0.0 <= t_raw <= 1.0 and cpa <= PROX_DISTANCE_U:
                        t["x"], t["z"] = nx, nz
                        self._explode_torpedo(t, direct_hit_id=None, damage=t["damage"] * 0.5, hit_target_id=p["id"])
                        exploded = True
                        break
                if exploded:
                    self.torpedoes.pop(key, None)
                    continue

                # ---- Balises sonar ----
                for bid, b in list(self.beacons.items()):
                    if not inside_map(b["x"], b["z"]):
                        continue
                    d = distance_point_segment(b["x"], b["z"], t["x"], t["z"], nx, nz)
                    if d <= 1.0:
                        t["x"], t["z"] = b["x"], b["z"]
                        self.beacons.pop(bid, None)
                        self.emit(ev_mod.SonarBeaconDestroyed(bid=bid))
                        self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None)
                        exploded = True
                        break
                if exploded:
                    self.torpedoes.pop(key, None)
                    continue

                # ---- Leurres acoustiques ----
                LURE_HIT_U = 3.0 / UNIT_METERS_BOT
                for lkey, lure in list(self.lures.items()):
                    if not inside_map(lure["x"], lure["z"]):
                        continue
                    # Collision 3D sur le segment, pas de leurre touche a une autre profondeur.
                    vx, vy, vz = nx - t["x"], ny - t["y"], nz - t["z"]
                    length2 = vx * vx + vy * vy + vz * vz
                    projection = ((lure["x"] - t["x"]) * vx +
                                  (lure.get("y", 0) - t["y"]) * vy + (lure["z"] - t["z"]) * vz)
                    fraction = max(0.0, min(1.0, projection / length2)) if length2 else 0.0
                    d = math.dist((lure["x"], lure.get("y", 0), lure["z"]),
                                  (t["x"] + fraction * vx, t["y"] + fraction * vy, t["z"] + fraction * vz))
                    if d <= LURE_HIT_U:
                        t["x"], t["y"], t["z"] = lure["x"], lure.get("y", 0), lure["z"]
                        self._explode_torpedo(t, direct_hit_id=None, damage=t["damage"], hit_target_id=None, hit_lure=True)
                        exploded = True
                        break
                if exploded:
                    self.torpedoes.pop(key, None)
                    continue

                # ---- Mines (proximité 80 m comme un bateau) ----
                for mkey, m in list(self.mines.items()):
                    if not inside_map(m["x"], m["z"]):
                        continue
                    t_raw, cpa = closest_approach_on_segment(m["x"], m["z"], t["x"], t["z"], nx, nz)
                    if 0.0 <= t_raw <= 1.0 and cpa <= PROX_DISTANCE_U:
                        t["x"], t["z"] = nx, nz
                        if m.get("armed"):
                            explode_server_mine(m, trigger_id=t["ownerPlayerId"])
                            self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None)
                        else:
                            self.emit(ev_mod.MineDead(owner_id=m["ownerId"], mid=m["mid"]))
                            self.mines.pop(mkey, None)
                            self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None, silent=True)
                        exploded = True
                        break
                if exploded:
                    self.torpedoes.pop(key, None)
                    continue

            # ---- Torpille vs torpille (proximité 50 m) — uniquement si antiTorpedo ----
            TORPEDO_VS_TORPEDO_U = 50.0 / UNIT_METERS_BOT
            if activated and t.get("antiTorpedo"):
                for other_key in list(self.torpedoes.keys()):
                    if other_key == key:
                        continue
                    ot = self.torpedoes.get(other_key)
                    if ot is None:
                        continue
                    dx_tt = ot["x"] - nx
                    dz_tt = ot["z"] - nz
                    dy_tt = abs(ot["y"] - ny)
                    dist_tt = math.hypot(dx_tt, dz_tt)
                    if dist_tt <= TORPEDO_VS_TORPEDO_U and dy_tt <= PROX_VERTICAL_U:
                        t["x"], t["z"] = nx, nz
                        self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None)
                        ot["x"], ot["z"] = ot["x"], ot["z"]
                        self._explode_torpedo(ot, direct_hit_id=None, damage=0, hit_target_id=None)
                        self.torpedoes.pop(other_key, None)
                        exploded = True
                        break
            if exploded:
                self.torpedoes.pop(key, None)
                continue

            # ---- Île sur le segment courant → explose ----
            if torpedo_segment_blocked(
                t["x"], t["z"], nx, nz, world_data,
                point_in_polygon=point_in_polygon,
                ensure_island_bounds=ensure_island_bounds,
            ):
                t["x"], t["z"] = nx, nz
                self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None)
                self.torpedoes.pop(key, None)
                continue

            # Avancée validée.
            t["traveled"] += travel_step
            t["x"] = nx
            t["z"] = nz
            t["y"] = ny
            if leaves_map:
                self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None,
                                      silent=True, reason="map_bounds")
                self.torpedoes.pop(key, None)
                continue
            # Hors portée.
            if t["maxRange"] > 0 and t["traveled"] >= t["maxRange"]:
                self._explode_torpedo(t, direct_hit_id=None, damage=0, hit_target_id=None)
                self.torpedoes.pop(key, None)
                continue
            # Opt 4 : throttle de l'état torpille à ~10 Hz (le client extrapole la
            # position entre deux trames via dirX/dirZ × vitesse). L'explosion/mort
            # émet ses propres events avec la position finale.
            if now_t - t.get("lastEmit", 0) >= TORPEDO_EMIT_INTERVAL:
                t["lastEmit"] = now_t
                self._emit_torpedo_state(t)

    # ===================== DRONES =====================

    def _emit_drone_state(self, d: Dict[str, Any]) -> None:
        self.emit(ev_mod.DroneState(
            owner_id=d["ownerPlayerId"],
            did=d["did"],
            kind=d["kind"],
            x=d["x"], y=d["y"], z=d["z"],
            dir_x=d["dirX"], dir_z=d["dirZ"],
            returning=bool(d.get("returning")),
            speed=d["speed"],
            autonomy=d["autonomy"],
            traveled=d["traveled"],
            range_m=float(d.get("range_m", 0.0)),
        ))

    def kill_server_drone(self, d: Dict[str, Any], reason: str, refund: bool) -> None:
        """Émet DroneDead. Si refund=True, restaure une munition au tireur."""
        self.emit(ev_mod.DroneDead(
            owner_id=d["ownerPlayerId"],
            did=d["did"],
            reason=reason,
        ))
        if refund:
            sid = d.get("ownerSid")
            ammo = self._legacy.drone_ammo.get(sid)
            if ammo is not None:
                ammo[d["kind"]] = ammo.get(d["kind"], 0) + 1
                self._legacy.emit_drone_counts(sid)

    def spawn_drone(self, sid: str, player_dict: Dict[str, Any], data: Dict[str, Any]) -> None:
        """Crée un drone serveur sur intention de tir."""
        import random as _random
        kind = data.get("kind")
        if kind not in ("automatic", "manual"):
            return
        boat = player_dict.get("boat") or {}
        specs = boat_drone_specs(boat)
        spec = specs.get(kind)
        if not spec:
            return
        pid = player_dict["id"]
        ammo = self._legacy.drone_ammo.get(sid)
        if ammo is None:
            self._legacy.init_drone_ammo_for_sid(sid)
            ammo = self._legacy.drone_ammo.get(sid) or {}
        if ammo.get(kind, 0) <= 0:
            return
        pos = player_dict.get("position") or {}
        by = pos.get("y", 0)
        boat_type = player_dict.get("boatType") or ""
        if boat_type == "submarine":
            flotation_m = boat.get("flotation", 2)
            surface_y = -flotation_m / UNIT_METERS_BOT
            if by < surface_y - 0.05:
                return
        if kind == "manual":
            for k, drone in self.drones.items():
                if k[0] == pid and drone["kind"] == "manual" and not drone.get("returning"):
                    return
        bx = pos.get("x", 0)
        bz = pos.get("z", 0)
        rotation = float(player_dict.get("rotation") or 0)
        altitude_u = (spec.get("altitude") or 200) / UNIT_METERS_BOT
        speed_us = (spec.get("speed") or 80) * 0.514444 / UNIT_METERS_BOT
        autonomy_u = (spec.get("autonomy") or 30) * 1000.0 / UNIT_METERS_BOT
        # Rayon de vision (range) : 3000m auto / 2000m manuel par défaut.
        default_range_m = 3000.0 if kind == "automatic" else 2000.0
        range_m = float(spec.get("range") or default_range_m)
        range_u = range_m / UNIT_METERS_BOT
        # Distance de sécurité (safeDistance) : ne s'applique qu'au drone auto.
        safe_dist_m = float(spec.get("safeDistance") or 1800.0)
        safe_dist_u = safe_dist_m / UNIT_METERS_BOT
        launch_angle = rotation
        if kind == "automatic":
            existing = []
            for k, drone in self.drones.items():
                if k[0] == pid and drone["kind"] == "automatic" and not drone.get("returning"):
                    existing.append(math.atan2(drone["dirZ"], -drone["dirX"]))
            best_angle = launch_angle + (_random.random() - 0.5) * 0.4
            best_min_gap = -1
            for i in range(24):
                cand = launch_angle + (i / 24.0) * math.tau
                min_gap = math.tau
                for a in existing:
                    diff = abs(((cand - a) + math.pi) % math.tau - math.pi)
                    if diff < min_gap:
                        min_gap = diff
                if not existing:
                    best_angle = cand
                    break
                if min_gap > best_min_gap:
                    best_min_gap = min_gap
                    best_angle = cand
            launch_angle = best_angle + (_random.random() - 0.5) * 0.15
        dir_x = -math.cos(launch_angle)
        dir_z = math.sin(launch_angle)
        next_did = self._legacy.next_drone_did
        did = next_did.get(pid, 1)
        next_did[pid] = did + 1
        drone = {
            "ownerSid": sid,
            "ownerPlayerId": pid,
            "did": did,
            "kind": kind,
            "x": bx, "y": altitude_u, "z": bz,
            "dirX": dir_x, "dirZ": dir_z,
            "rotation": launch_angle,
            "speed": speed_us if kind == "automatic" else 0.0,
            "maxSpeed": speed_us,
            "altitude": altitude_u,
            "autonomy": autonomy_u,
            "range_u": range_u,
            "range_m": range_m,
            "safe_dist_u": safe_dist_u,
            "safe_dist_m": safe_dist_m,
            "traveled": 0.0,
            "returning": False,
            "steerYaw": 0,
            "steerThrottle": 0,
            "steerClimb": 0,
            "lastEmit": 0.0,
            "bornAt": self.now(),
        }
        self.drones[(pid, did)] = drone
        ammo[kind] = max(0, ammo.get(kind, 0) - 1)
        self._legacy.emit_drone_counts(sid)
        self._emit_drone_state(drone)

    def update_server_drones(self, dt: float, world_data: Dict[str, Any]) -> None:
        """Tick drones serveur."""
        if not world_data:
            return
        legacy = self._legacy
        if legacy is None:
            return
        point_in_polygon = legacy.point_in_polygon
        half_w = world_data["ground"]["width"] / 2
        half_d = world_data["ground"]["depth"] / 2
        DRONE_EMIT_INTERVAL = 0.1
        now = self.now()
        for key in list(self.drones.keys()):
            d = self.drones.get(key)
            if d is None:
                continue
            owner_pid = d["ownerPlayerId"]
            owner = None
            for sid, p in self.players.items():
                if p.get("id") == owner_pid:
                    owner = p
                    break
            owner_pos = owner.get("position") if owner else None
            ox = owner_pos.get("x") if owner_pos else None
            oz = owner_pos.get("z") if owner_pos else None
            owner_visible = True
            if owner and owner.get("boatType") == "submarine" and owner_pos:
                flotation_m = (owner.get("boat") or {}).get("flotation", 2)
                surface_y = -flotation_m / UNIT_METERS_BOT
                owner_visible = owner_pos.get("y", 0) >= surface_y - 0.05
            if d["returning"] and ox is not None and owner_visible:
                d["speed"] = d["maxSpeed"]
                ddx = ox - d["x"]
                ddz = oz - d["z"]
                length = math.hypot(ddx, ddz)
                if length < d["speed"] * dt + DRONE_RECOVERY_DISTANCE_U:
                    self.kill_server_drone(d, reason="recovered", refund=True)
                    self.drones.pop(key, None)
                    continue
                d["dirX"] = ddx / length
                d["dirZ"] = ddz / length
            elif d["kind"] == "automatic" and not d["returning"]:
                remaining = d["autonomy"] - d["traveled"]
                dist_to_owner = 0
                if ox is not None:
                    dist_to_owner = math.hypot(d["x"] - ox, d["z"] - oz)
                if remaining <= dist_to_owner * 1.25:
                    d["returning"] = True
                else:
                    # Évitement ennemi : si un bateau adverse est détecté dans
                    # le rayon de vision du drone, garder la distance de sécurité du JSON.
                    DRONE_DISCOVER_U = d.get("range_u", 3000.0 / UNIT_METERS_BOT)
                    keep_dist_u = d.get("safe_dist_u", 1800.0 / UNIT_METERS_BOT)
                    closest_enemy = None
                    closest_d2 = float("inf")
                    for esid, ep in self.players.items():
                        if ep.get("id") == owner_pid:
                            continue
                        if ep.get("sunk") or ep.get("integrity", 100) <= 0:
                            continue
                        epos = ep.get("position") or {}
                        # Drone automatique : ne détecte pas les bateaux submergés
                        # (même critère que le flag submerged broadcast : y <= -5m).
                        if epos.get("y", 0) <= -5.0 / UNIT_METERS_BOT:
                            continue
                        edx = epos.get("x", 0) - d["x"]
                        edz = epos.get("z", 0) - d["z"]
                        d2 = edx * edx + edz * edz
                        if d2 > DRONE_DISCOVER_U * DRONE_DISCOVER_U:
                            continue
                        if d2 < closest_d2:
                            closest_d2 = d2
                            closest_enemy = (edx, edz, math.sqrt(d2))
                    if closest_enemy is not None:
                        edx, edz, ed = closest_enemy
                        if ed < keep_dist_u:
                            # Tourner pour s'éloigner : direction (-edx, -edz) normalisée
                            if ed > 0.001:
                                away_x = -edx / ed
                                away_z = -edz / ed
                                # Lerp doux entre dir actuelle et fuite
                                blend = 0.15
                                nx_dir = d["dirX"] * (1 - blend) + away_x * blend
                                nz_dir = d["dirZ"] * (1 - blend) + away_z * blend
                                nlen = math.hypot(nx_dir, nz_dir)
                                if nlen > 0.001:
                                    d["dirX"] = nx_dir / nlen
                                    d["dirZ"] = nz_dir / nlen
                                    d["rotation"] = math.atan2(d["dirZ"], -d["dirX"])
            elif d["kind"] == "manual" and not d["returning"]:
                yaw_in = d.get("steerYaw", 0)
                throttle_in = d.get("steerThrottle", 0)
                climb_in = d.get("steerClimb", 0)
                turn_rate = 0.6
                if yaw_in != 0:
                    d["rotation"] += yaw_in * turn_rate * dt
                accel = d["maxSpeed"] * 0.15
                if throttle_in > 0:
                    d["speed"] = min(d["maxSpeed"], d["speed"] + accel * dt)
                elif throttle_in < 0:
                    d["speed"] = max(-d["maxSpeed"] * 0.5, d["speed"] - accel * dt)
                climb_rate = 40.0 / UNIT_METERS_BOT
                if climb_in > 0:
                    d["y"] += climb_rate * dt
                elif climb_in < 0:
                    d["y"] -= climb_rate * dt
                floor = 0.0
                for island in world_data.get("islands", []):
                    if point_in_polygon(d["x"], d["z"], island["points"]):
                        h = island.get("height", 0)
                        if h > floor:
                            floor = h
                min_y = floor + 5.0 / UNIT_METERS_BOT
                max_y = 1000.0 / UNIT_METERS_BOT
                if d["y"] < min_y:
                    d["y"] = min_y
                if d["y"] > max_y:
                    d["y"] = max_y
                d["dirX"] = -math.cos(d["rotation"])
                d["dirZ"] = math.sin(d["rotation"])
            nx = d["x"] + d["dirX"] * d["speed"] * dt
            nz = d["z"] + d["dirZ"] * d["speed"] * dt
            if nx <= -half_w and d["dirX"] < 0:
                d["dirX"] = -d["dirX"]
                if d["kind"] == "manual":
                    d["rotation"] = math.atan2(d["dirZ"], -d["dirX"])
            if nx >= half_w and d["dirX"] > 0:
                d["dirX"] = -d["dirX"]
                if d["kind"] == "manual":
                    d["rotation"] = math.atan2(d["dirZ"], -d["dirX"])
            if nz <= -half_d and d["dirZ"] < 0:
                d["dirZ"] = -d["dirZ"]
                if d["kind"] == "manual":
                    d["rotation"] = math.atan2(d["dirZ"], -d["dirX"])
            if nz >= half_d and d["dirZ"] > 0:
                d["dirZ"] = -d["dirZ"]
                if d["kind"] == "manual":
                    d["rotation"] = math.atan2(d["dirZ"], -d["dirX"])
            d["x"] = max(-half_w, min(half_w, nx))
            d["z"] = max(-half_d, min(half_d, nz))
            d["traveled"] += abs(d["speed"]) * dt
            if d["traveled"] >= d["autonomy"]:
                self.kill_server_drone(d, reason="crashed", refund=False)
                self.drones.pop(key, None)
                continue
            if now - d.get("lastEmit", 0) >= DRONE_EMIT_INTERVAL:
                d["lastEmit"] = now
                self._emit_drone_state(d)

    # ===================== GRENADES =====================

    def spawn_grenade(self, sid: str, player_dict: Dict[str, Any], data: Dict[str, Any]) -> None:
        """Lance une grenade vers la position cible (targetX, targetZ)."""
        if (player_dict.get("boatType") or "") != "destroyer":
            return
        boat = player_dict.get("boat") or {}
        spec = boat_grenade_spec(boat)
        if not spec:
            return
        pid = player_dict["id"]
        if self._legacy.grenade_ammo.get(sid, 0) <= 0:
            return
        raw_depth = data.get("depthMeters", 10)
        try:
            depth_m = float(raw_depth)
        except (TypeError, ValueError):
            depth_m = 10.0
        depth_m = max(5.0, min(500.0, depth_m))
        target_depth_u = depth_m / UNIT_METERS_BOT
        pos = player_dict.get("position") or {}
        start_x = pos.get("x", 0)
        start_z = pos.get("z", 0)
        start_y = 1.5
        # Cible : coordonnées monde envoyées par le client
        try:
            tx = float(data.get("targetX", start_x))
            tz = float(data.get("targetZ", start_z))
        except (TypeError, ValueError):
            tx, tz = start_x, start_z
        dx = tx - start_x
        dz = tz - start_z
        dist_u = math.hypot(dx, dz)
        dist_m = dist_u * UNIT_METERS_BOT
        range_m = spec.get("rangeMeters", 1000)
        if dist_m > range_m:
            return
        # Balistique : y0 + vy*t - 0.5*g*t² = 0
        # t = (vy + sqrt(vy² + 2*g*y0)) / g
        y0 = 1.5
        discriminant = GRENADE_INITIAL_VY * GRENADE_INITIAL_VY + 2.0 * GRENADE_GRAVITY * y0
        t_flight = (GRENADE_INITIAL_VY + discriminant ** 0.5) / GRENADE_GRAVITY
        v_horiz = dist_u / t_flight if t_flight > 0.01 else 0.0
        if dist_u > 0.001:
            vx = (dx / dist_u) * v_horiz
            vz = (dz / dist_u) * v_horiz
        else:
            vx = 0.0
            vz = 0.0
        vy = GRENADE_INITIAL_VY
        sink_speed = (spec.get("sinkSpeedMs", 4)) / UNIT_METERS_BOT
        next_gid = self._legacy.next_grenade_gid
        gid = next_gid.get(pid, 1)
        next_gid[pid] = gid + 1
        g = {
            "ownerSid": sid,
            "ownerPlayerId": pid,
            "gid": gid,
            "phase": "air",
            "x": start_x, "y": start_y, "z": start_z,
            "vx": vx, "vy": vy, "vz": vz,
            "impactX": tx, "impactZ": tz,
            "targetDepthU": target_depth_u,
            "sinkSpeedU": sink_speed,
            "damage": spec.get("damage", 50),
            "effectRadiusU": spec.get("effectRangeMeters", 200) / UNIT_METERS_BOT,
            "bornAt": self.now(),
        }
        self.grenades[(pid, gid)] = g
        dlog("grenades", f"spawn gid={gid} owner={pid} targetDepth={depth_m:.0f}m ({target_depth_u:.2f}u) pos=({start_x:.1f},{start_y:.1f},{start_z:.1f}) v=({vx:.2f},{vy:.2f},{vz:.2f})")
        self._legacy.grenade_ammo[sid] = max(0, self._legacy.grenade_ammo.get(sid, 0) - 1)
        self._legacy.emit_grenade_count(sid)
        self.emit(ev_mod.GrenadeLaunched(
            shooter_id=pid, gid=gid,
            x=start_x, y=start_y, z=start_z,
            vx=vx, vy=vy, vz=vz,
            target_depth=target_depth_u,
            sink_speed=sink_speed,
        ))

    def _alert_bots_grenade_splash(self, g: Dict[str, Any]) -> None:
        """Alerte les bots sub proches quand une grenade touche l'eau."""
        gx, gz = g["x"], g["z"]
        alert_radius = g["effectRadiusU"] * 3
        r2 = alert_radius * alert_radius
        dlog("grenades", f"splash gid={g['gid']} pos=({gx:.1f},{gz:.1f}) alert_radius={alert_radius * UNIT_METERS_BOT:.0f}m")
        for sid, bot in self.bots.items():
            if bot.get("boatType") != "submarine":
                continue
            pos = bot["position"]
            dx = gx - pos["x"]
            dz = gz - pos["z"]
            dist = (dx * dx + dz * dz) ** 0.5
            if dx * dx + dz * dz < r2:
                bb = bot.setdefault("bb", {})
                bb["enemy_aware_until"] = self.now() + 60.0
                dlog("grenades", f"splash {bot['id']} alerté (dist={dist * UNIT_METERS_BOT:.0f}m, depth={-pos['y'] * UNIT_METERS_BOT:.0f}m)")
            else:
                dlog("grenades", f"splash {bot['id']} hors portée (dist={dist * UNIT_METERS_BOT:.0f}m > {alert_radius * UNIT_METERS_BOT:.0f}m)")

    def explode_server_grenade(self, g: Dict[str, Any]) -> None:
        """Applique le souffle a tous, sans compter l'auto-degat comme degat inflige."""
        ex = g["x"]
        ez = g["z"]
        ey = -g["targetDepthU"]
        damage = g["damage"]
        attacker_id = g["ownerPlayerId"]
        radius = g["effectRadiusU"]
        dlog("grenades", f"explode gid={g['gid']} pos=({ex:.1f},{ey:.1f},{ez:.1f}) depth={g['targetDepthU'] * UNIT_METERS_BOT:.0f}m damage={damage}")
        total_dmg = 0.0
        bot_radius = BOT_SPLASH_RADIUS_M / UNIT_METERS_BOT
        for sid, bot in list(self.bots.items()):
            pos = bot["position"]
            dx = ex - pos["x"]; dy = ey - pos["y"]; dz = ez - pos["z"]
            dist = (dx*dx + dy*dy + dz*dz) ** 0.5
            if dist < bot_radius:
                dmg_dealt = damage * (1 - dist / bot_radius)
                if bot.get("id") != attacker_id:
                    total_dmg += min(bot["integrity"], dmg_dealt)
                dlog("grenades", f"explode {bot['id']} touché dist3D={dist * UNIT_METERS_BOT:.0f}m dmg={dmg_dealt:.1f} pts (bot_depth={-pos['y'] * UNIT_METERS_BOT:.0f}m)")
            else:
                dlog("grenades", f"explode {bot['id']} raté dist3D={dist * UNIT_METERS_BOT:.0f}m (bot_depth={-pos['y'] * UNIT_METERS_BOT:.0f}m)")
        for sid, p in list(self.players.items()):
            if p.get("is_bot") or p.get("godmode") or p.get("integrity", 100.0) <= 0:
                continue
            if p.get("id") == attacker_id:
                continue
            pos = p.get("position") or {}
            dx = ex - pos.get("x", 0); dy = ey - pos.get("y", 0); dz = ez - pos.get("z", 0)
            dist = (dx*dx + dy*dy + dz*dz) ** 0.5
            if dist < radius:
                total_dmg += min(p.get("integrity", 100.0), damage * (1 - dist / radius))
        total_dmg += self.lure_splash_damage(ex, ey, ez, damage, radius)
        self.emit(ev_mod.GrenadeExploded(
            shooter_id=attacker_id, gid=g["gid"],
            x=ex, y=ey, z=ez, damage=damage, dealt=round(total_dmg, 1),
        ))
        self.bot_splash_damage(ex, ey, ez, damage, attacker_id)
        self.player_splash_damage(ex, ey, ez, damage, attacker_id, radius)
        r2 = radius * radius
        for mkey in list(self.mines.keys()):
            m = self.mines.get(mkey)
            if m is None or m["kind"] == "surface":
                continue
            dx = m["x"] - ex
            dz = m["z"] - ez
            if dx * dx + dz * dz <= r2:
                self.explode_server_mine(m, trigger_id=attacker_id)

    def update_server_grenades(self, dt: float, world_data: Dict[str, Any]) -> None:
        """Tick grenades : air → eau → boom à targetDepth."""
        for key in list(self.grenades.keys()):
            g = self.grenades.get(key)
            if g is None:
                continue
            phase = g["phase"]
            if phase == "air":
                g["vy"] -= GRENADE_GRAVITY * dt
                g["x"] += g["vx"] * dt
                g["y"] += g["vy"] * dt
                g["z"] += g["vz"] * dt
                if g["y"] <= 0:
                    g["y"] = 0.0
                    g["x"] = g["impactX"]
                    g["z"] = g["impactZ"]
                    g["phase"] = "water"
                    dlog("grenades", f"gid={g['gid']} → phase water, targetDepthU={g['targetDepthU']:.2f}")
                    self._alert_bots_grenade_splash(g)
            elif phase == "water":
                g["y"] -= g["sinkSpeedU"] * dt
                if g["y"] <= -g["targetDepthU"]:
                    self.explode_server_grenade(g)
                    self.grenades.pop(key, None)
                    continue

    # ===================== MINES =====================

    def place_mine(self, sid: str, player: Dict[str, Any], kind: str,
                   depth_m: float = 20.0) -> bool:
        """Pose une mine à la position du bateau et consomme une munition."""
        if len(self.mines) >= MAX_WORLD_MINES or kind not in MINE_KIND_TO_KEY:
            return False
        spec = boat_mine_spec(player.get("boat") or {}, kind)
        ammo = self._legacy.mine_ammo.get(sid) or {}
        if not spec or ammo.get(kind, 0) <= 0:
            return False
        pid = player["id"]
        position = player.get("position") or {}
        if kind == "surface":
            mine_y = 0.0
            selected_depth_m = None
        elif kind == "bottom":
            mine_y = SEABED_FLOOR_Y
            selected_depth_m = None
        else:
            selected_depth_m = max(1.0, min(495.0, float(depth_m)))
            mine_y = max(SEABED_FLOOR_Y, min(-0.1, -selected_depth_m / UNIT_METERS_BOT))
        mid = self._legacy.next_mine_id.get(pid, 1)
        self._legacy.next_mine_id[pid] = mid + 1
        now = self.now()
        mine = {
            "ownerSid": sid,
            "ownerId": pid,
            "teamId": player.get("team_id"),
            "mid": mid,
            "kind": kind,
            "x": float(position.get("x", 0.0)),
            "y": mine_y,
            "z": float(position.get("z", 0.0)),
            "range": float(spec.get("range", 40)),
            "damage": float(spec.get("damage", 60)),
            "armed": False,
            "armAt": now + float(spec.get("delay", 1) or 0) * 60.0,
            "placedAt": now,
            "depthMeters": selected_depth_m,
            "revealedTeams": set(),
        }
        self.mines[(pid, mid)] = mine
        ammo[kind] = max(0, ammo.get(kind, 0) - 1)
        self._legacy.emit_mine_counts(sid)
        payload = mine_payload(mine)
        payload["teamId"] = mine["teamId"]
        self.emit(ev_mod.MinePlaced(payload=payload))
        return True

    def explode_server_mine(self, mine: Dict[str, Any], trigger_id: Optional[str] = None,
                            _chain_visited: Optional[set] = None) -> None:
        """Explosion + splash + chaîne sur les autres mines armées dans le rayon."""
        if _chain_visited is None:
            _chain_visited = set()
        key = (mine["ownerId"], mine["mid"])
        if key in _chain_visited:
            return
        _chain_visited.add(key)
        if key not in self.mines:
            return
        self.emit(ev_mod.MineExploded(
            owner_id=mine["ownerId"], mid=mine["mid"],
            kind=mine["kind"],
            x=mine["x"], y=mine["y"], z=mine["z"],
            range=mine["range"],
        ))
        self.emit(ev_mod.MineDead(owner_id=mine["ownerId"], mid=mine["mid"]))
        self.mines.pop(key, None)
        range_u = mine["range"] / UNIT_METERS_BOT
        range_u_sq = range_u * range_u
        base_dmg = mine["damage"]
        attacker_id = trigger_id or mine["ownerId"]
        self.lure_splash_damage(mine["x"], mine["y"], mine["z"], base_dmg, range_u, falloff=0.5)
        for sid_p, p in list(self.players.items()):
            pos = p.get("position") or {}
            dx = pos.get("x", 0) - mine["x"]
            dy = pos.get("y", 0) - mine["y"]
            dz = pos.get("z", 0) - mine["z"]
            d_sq = dx * dx + dy * dy + dz * dz
            if d_sq > range_u_sq:
                continue
            d = math.sqrt(d_sq)
            ratio = d / range_u if range_u > 0 else 0
            dmg = base_dmg * (1.0 - 0.5 * ratio)
            if dmg <= 0:
                continue
            if p.get("is_bot"):
                bot = self.bots.get(sid_p)
                if bot is not None:
                    self.bot_apply_damage(sid_p, bot, dmg, attacker_id)
            else:
                self.apply_player_damage(sid_p, p, dmg, attacker_id)
        # Pas de réaction en chaîne : chaque mine est indépendante et n'explose
        # que sur déclenchement par un bateau dans sa propre zone.

    def update_server_mines(self, dt: float, world_data: Dict[str, Any]) -> None:
        """Arme les mines après le délai, surveille les bateaux dans la zone."""
        now = self.now()
        EPS = 0.005
        for key in list(self.mines.keys()):
            m = self.mines.get(key)
            if m is None:
                continue
            if not m["armed"]:
                if now >= m["armAt"]:
                    m["armed"] = True
                    self.emit(ev_mod.MineArmed(owner_id=m["ownerId"], mid=m["mid"]))
                continue
            range_u_sq = (m["range"] / UNIT_METERS_BOT) ** 2
            watch = m.setdefault("watch", {})
            triggered_by = None
            active_pids = set()
            for sid_p, p in list(self.players.items()):
                pos = p.get("position") or {}
                dx = pos.get("x", 0) - m["x"]
                dy = pos.get("y", 0) - m["y"]
                dz = pos.get("z", 0) - m["z"]
                d_sq = dx * dx + dy * dy + dz * dz
                if d_sq > range_u_sq:
                    continue
                pid = p.get("id")
                if not pid:
                    continue
                active_pids.add(pid)
                d = d_sq ** 0.5
                prev_min = watch.get(pid)
                if prev_min is None:
                    watch[pid] = d
                    continue
                if d < prev_min - EPS:
                    watch[pid] = d
                    continue
                if d > prev_min + EPS:
                    triggered_by = pid
                    break
            for old in list(watch.keys()):
                if old not in active_pids:
                    watch.pop(old, None)
            if triggered_by is not None:
                self.explode_server_mine(m, trigger_id=triggered_by)

    # ===================== INTÉGRITÉ / DÉGÂTS / NAUFRAGE =====================

    def _bsid_for(self, sid: str) -> Optional[str]:
        """Renvoie le bsid pour un sid (None si bateau primaire ou bot)."""
        return sid if sid in self._legacy.human_owner_sid else None

    def lure_splash_damage(self, ex: float, ey: float, ez: float, damage: float,
                           radius: float, *, falloff: float = 1.0) -> float:
        """Degats absolus 3D; mines a demi-attenuation, torpilles/grenades lineaires."""
        if not math.isfinite(damage) or damage <= 0 or radius <= 0:
            return 0.0
        dealt = 0.0
        for key, lure in list(self.lures.items()):
            if self.now() >= lure["expiresAt"]:
                continue
            distance = math.dist((ex, ey, ez), (lure["x"], lure.get("y", 0), lure["z"]))
            if distance > radius:
                continue
            loss = damage * (1.0 - falloff * distance / radius)
            if loss <= 0:
                continue
            capacity = lure["maxIntegrity"]
            before = lure["integrity"]
            lure["integrity"] = max(0.0, before - loss)
            dealt += before - lure["integrity"]
            if lure["integrity"] <= 0:
                self.lures.pop(key)
                self.emit(ev_mod.LureDestroyed(owner_id=lure["ownerId"], lid=lure["lid"]))
            else:
                self.emit(ev_mod.LureIntegrityChanged(owner_id=lure["ownerId"], lid=lure["lid"],
                          integrity=lure["integrity"], max_integrity=capacity))
        return dealt

    def _emit_integrity(self, sid: str, p: Dict[str, Any]) -> None:
        """Émet IntegrityChanged au propriétaire du sid (humain seulement)."""
        socket_sid = self._owner_sid_for_player(sid)
        if not socket_sid:
            return
        self.emit(ev_mod.IntegrityChanged(
            bsid=self._bsid_for(sid),
            value=float(p.get("integrity", 100.0)),
            max_integrity=p.get("maxIntegrity", 100.0),
            target_sid=socket_sid,
        ))

    def init_player_integrity(self, sid: str) -> None:
        p = self.players.get(sid)
        if not p:
            return
        init_hull_integrity(p)
        p["last_integrity"] = p["integrity"]
        p["regen_budget"] = REGEN_MAX_BUDGET
        p["regen_paused_at"] = 0.0
        p["regen_total_remaining"] = REGEN_TOTAL_INITIAL

    def find_bot_by_player_id(self, pid: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        for sid, bot in self.bots.items():
            if bot["id"] == pid:
                return sid, bot
        return None, None

    def apply_player_damage(self, sid: str, p: Dict[str, Any], damage: float, attacker_id: Optional[str]) -> None:
        """Dégâts à un joueur humain. Sink + emit BoatSunk si <=0."""
        if not math.isfinite(damage) or damage <= 0 or p.get("is_bot"):
            return
        if p.get("godmode"):
            return
        if p.get("integrity", 100.0) <= 0:
            return
        p["integrity"] = max(0.0, p.get("integrity", 100.0) - damage)
        p["regen_paused_at"] = self.now()
        p["regen_budget"] = min(REGEN_MAX_BUDGET, p.get("regen_total_remaining", 0))
        self._emit_integrity(sid, p)
        if p["integrity"] <= 0:
            self.sink_player(sid, p, attacker_id)

    def sink_player(self, sid: str, p: Dict[str, Any], attacker_id: Optional[str]) -> None:
        """Joueur humain coulé : nettoie ses tirs en vol et broadcast BoatSunk."""
        legacy = self._legacy
        pid = p["id"]
        for k in list(self.drones.keys()):
            if self.drones[k]["ownerPlayerId"] == pid:
                self.kill_server_drone(self.drones[k], reason="lost", refund=False)
                self.drones.pop(k, None)
        p["sunk"] = True
        legacy.autopiloted_sids.discard(sid)
        # Notifier le propriétaire si c'est un bateau secondaire (multi-bateaux).
        owner = legacy.human_owner_sid.get(sid)
        if owner:
            self.emit(ev_mod.OwnBoatSunk(bsid=sid, player_id=pid, target_sid=owner))
            # Retirer le bateau après l'animation de naufrage (~35s).
            ghost_sid = sid
            ghost_pid = pid
            owner_sid = owner

            def _retire_secondary():
                legacy.socketio.sleep(35)
                if ghost_sid not in self.players:
                    return
                legacy._cleanup_player_entities(ghost_sid, ghost_pid)
                legacy.human_owner_sid.pop(ghost_sid, None)
                legacy.autopiloted_sids.discard(ghost_sid)
                owned = legacy.player_boats_sids.get(owner_sid)
                if owned and ghost_sid in owned:
                    owned.remove(ghost_sid)
                del self.players[ghost_sid]
                legacy.socketio.emit("player_left", {"id": ghost_pid})
            legacy.socketio.start_background_task(_retire_secondary)
        self.emit(ev_mod.BoatSunk(victim_id=pid, attacker_id=attacker_id))

    def player_splash_damage(self, ex: float, ey: float, ez: float,
                             base_damage: float, attacker_id: Optional[str],
                             effect_radius_u: float, exclude_id: Optional[str] = None) -> None:
        """Splash sur tous les joueurs humains dans le rayon."""
        if base_damage <= 0:
            return
        r2 = effect_radius_u * effect_radius_u
        for sid, p in list(self.players.items()):
            if p.get("is_bot"):
                continue
            if exclude_id and p.get("id") == exclude_id:
                continue
            if p.get("integrity", 100.0) <= 0:
                continue
            pos = p.get("position") or {}
            dx = ex - pos.get("x", 0)
            dy = ey - pos.get("y", 0)
            dz = ez - pos.get("z", 0)
            dist2 = dx * dx + dy * dy + dz * dz
            if dist2 >= r2:
                continue
            dist = dist2 ** 0.5
            dmg = base_damage * (1.0 - dist / effect_radius_u)
            self.apply_player_damage(sid, p, dmg, attacker_id)

    def bot_apply_damage(self, sid: str, bot: Dict[str, Any], damage: float, attacker_id: Optional[str]) -> None:
        if not math.isfinite(damage) or damage <= 0 or bot["integrity"] <= 0:
            return
        bot["integrity"] = max(0.0, bot["integrity"] - damage)
        if sid in self.players:
            self.players[sid]["integrity"] = bot["integrity"]
            self.players[sid]["maxIntegrity"] = bot.get("maxIntegrity", 100.0)
        bb = bot.setdefault("bb", {})
        bb["enemy_aware_until"] = self.now() + 60.0
        if bot["integrity"] <= 0:
            self.sink_bot(sid, bot, attacker_id)

    def teleport_bot(self, actor_id: str, bot_id: Any, x: Any, z: Any) -> Optional[str]:
        """Cheat explicite : placement horizontal, sans effacer les contacts."""
        if not isinstance(bot_id, str):
            return "Identifiant de bot invalide"
        entry = next(((sid, b) for sid, b in self.bots.items() if b.get("id") == bot_id), None)
        if entry is None:
            return "Bot introuvable (selection perimee ou joueur humain)"
        sid, bot = entry
        player = self.players.get(sid)
        if (not player or not player.get("is_bot") or player.get("id") != bot_id
                or bot.get("sunk") or player.get("sunk")
                or bot.get("integrity", 100) <= 0 or player.get("integrity", 100) <= 0):
            return "Bot indisponible ou coule"
        if any(type(v) not in (int, float) for v in (x, z)):
            return "Coordonnees invalides"
        try:
            if not all(math.isfinite(v) for v in (x, z)):
                return "Coordonnees invalides"
        except OverflowError:
            return "Coordonnees invalides"
        ground = self.world_data["ground"]
        if abs(x) > ground["width"] / 2 - 4 or abs(z) > ground["depth"] / 2 - 4:
            return "Position invalide (bord de carte)"
        if not geometry.line_of_sight_clear(x, z, x, z, self.world_data):
            return "Position invalide (ile)"
        old_position = dict(bot["position"])
        bot["position"] = dict(old_position, x=float(x), z=float(z))
        bot["speed"] = bot["rudder"] = 0.0
        bot["waypoint"] = None
        bot["control_target_speed_ratio"] = bot["control_target_rudder"] = 0.0
        for key in ("_evade_until", "_threat_cache"):
            bot.pop(key, None)
        # Seuls les plans lies a l'ancien emplacement sont invalides, pas la memoire tactique.
        bb = bot.get("bb", {})
        for key in ("nav_node", "nav_prev_node", "nav_island", "nav_mode",
                    "nav_perim_remaining", "nav_perim_after", "nav_banned_nodes", "nav_banned_until",
                    "_stuck_ticks", "_ref_wp_dist", "_ref_wp_t", "_ref_wp_key",
                    "_yvan_until", "_yvan_pending_from", "_yvan_pending_dist_u",
                    "_evade", "_evade_pinged", "_evade_surprise", "_evade_avoid_dir"):
            bb.pop(key, None)
        player.update(position=dict(bot["position"]), speed=0.0, speedRatio=0.0,
                      rudder=0.0, reverse=False)
        self.emit(ev_mod.BotTeleported(actor_id=actor_id, player_id=bot_id,
                                      old_position=old_position, position=dict(bot["position"])))
        self.emit(ev_mod.PlayerMoved(player_id=bot_id, position=dict(bot["position"]),
                                    rotation=bot["rotation"], rudder=0.0, reverse=False,
                                    speed_ratio=0.0, integrity=bot.get("integrity", 100.0),
                                    max_integrity=bot.get("maxIntegrity", 100.0),
                                    submerged=bot["position"].get("y", 0) <= -5.0 / UNIT_METERS_BOT))
        return None

    def sink_bot(self, sid: str, bot: Dict[str, Any], attacker_id: Optional[str]) -> None:
        if sid not in self.bots:
            return
        legacy = self._legacy
        pid = bot["id"]
        self._active_wire.pop(pid, None)
        legacy.next_torpedo_tid.pop(pid, None)
        legacy.torpedo_ammo.pop(sid, None)
        for k in list(self.drones.keys()):
            if self.drones[k]["ownerPlayerId"] == pid:
                self.kill_server_drone(self.drones[k], reason="lost", refund=False)
                self.drones.pop(k, None)
        legacy.next_drone_did.pop(pid, None)
        legacy.drone_ammo.pop(sid, None)
        legacy.next_grenade_gid.pop(pid, None)
        legacy.grenade_ammo.pop(sid, None)
        legacy.cannon_ammo.pop(sid, None)
        legacy.beacon_ammo.pop(sid, None)
        legacy.passive_beacon_ammo.pop(sid, None)
        for bid in list(legacy.passive_sonar_beacons.keys()):
            beacon = legacy.passive_sonar_beacons[bid]
            if beacon.get("ownerSid") != sid:
                continue
            legacy.passive_sonar_beacons.pop(bid, None)
            self.emit(ev_mod.PassiveSonarBeaconDestroyed(bid=bid))
        for k in list(self.lures.keys()):
            if k[0] == pid:
                lure = self.lures.pop(k, None)
                if lure:
                    self.emit(ev_mod.LureDestroyed(owner_id=lure["ownerId"], lid=lure["lid"]))
        legacy.next_lure_lid.pop(pid, None)
        legacy.lure_ammo.pop(sid, None)
        legacy.next_mine_id.pop(pid, None)
        legacy.mine_ammo.pop(sid, None)
        self.emit(ev_mod.BoatSunk(victim_id=pid, attacker_id=attacker_id))
        self.emit(ev_mod.PlayerLeft(player_id=pid))
        self.bots.pop(sid, None)
        self.players.pop(sid, None)

    def bot_splash_damage(self, ex: float, ey: float, ez: float,
                          base_damage: float, attacker_id: Optional[str],
                          depth_check: bool = True) -> None:
        if base_damage <= 0:
            return
        radius_units = BOT_SPLASH_RADIUS_M / UNIT_METERS_BOT
        for sid, bot in list(self.bots.items()):
            bx = bot["position"]["x"]
            by = bot["position"]["y"]
            bz = bot["position"]["z"]
            dx = ex - bx
            dy = (ey - by) if depth_check else 0.0
            dz = ez - bz
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            if dist >= radius_units:
                continue
            dmg = base_damage * (1 - dist / radius_units)
            self.bot_apply_damage(sid, bot, dmg, attacker_id)

    def _danger_zones(self, world_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        cache = self._danger_zones_cache
        if cache["world_id"] is id(world_data) and cache["zones"]:
            return cache["zones"]
        zones = []
        for island in world_data.get("islands", []):
            pts = island.get("points") or []
            if not pts:
                continue
            cx = sum(p["x"] for p in pts) / len(pts)
            cz = sum(p["z"] for p in pts) / len(pts)
            outer = []
            for p in pts:
                dx = p["x"] - cx
                dz = p["z"] - cz
                length = (dx * dx + dz * dz) ** 0.5
                k = (length + DANGER_ZONE_OFFSET) / length if length > 0 else 1.0
                outer.append({"x": cx + dx * k, "z": cz + dz * k})
            zones.append({"inner": pts, "outer": outer})
        cache["world_id"] = id(world_data)
        cache["zones"] = zones
        return zones

    def is_in_danger_zone(self, x: float, z: float, world_data: Dict[str, Any]) -> bool:
        """Vrai si dans la couronne (outer) ; inclut l'intérieur de l'île pour
        qu'un bateau échoué prenne quand même des dégâts."""
        point_in_polygon = self._legacy.point_in_polygon
        for zone in self._danger_zones(world_data):
            if point_in_polygon(x, z, zone["outer"]):
                return True
        return False

    def _should_emit_moved(self, holder, now, pos, rotation, speed_ratio,
                           reverse, submerged, integrity):
        """Opt 3 : change-detection pour PlayerMoved (bots/autopilotés).

        Le client lisse les positions reçues (lerp) mais ne fait PAS de
        dead-reckoning des bateaux : il faut donc continuer d'émettre à 20 Hz
        dès que l'entité bouge, sinon le bateau saccade. On ne SKIP que les
        entités strictement immobiles (vitesse ~0 ET cap/flags inchangés), avec
        un keepalive 1 s pour les nouveaux clients. C'est là qu'est le gain
        (bots à l'arrêt, en attente), sans dégrader le mouvement."""
        prev = holder.get("_last_emit_state")
        changed = True
        if prev is not None:
            drot = abs(rotation - prev["rot"])
            if drot > math.pi:
                drot = 2 * math.pi - drot
            # Quasi-immobile : vitesse négligeable, pas de rotation, flags stables.
            still = (abs(speed_ratio) < 0.005
                     and drot < 0.002
                     and reverse == prev["rev"]
                     and submerged == prev["sub"]
                     and abs(integrity - prev["int"]) < 0.05)
            keepalive = (now - prev["t"]) >= 1.0
            changed = (not still) or keepalive
        if changed:
            holder["_last_emit_state"] = {
                "x": pos.get("x", 0), "y": pos.get("y", 0), "z": pos.get("z", 0),
                "rot": rotation, "sr": speed_ratio, "rev": reverse,
                "sub": submerged, "int": integrity, "t": now,
            }
        return changed

    def update_player_integrity(self, dt: float, world_data: Dict[str, Any]) -> None:
        """Tick d'intégrité humains : danger zone, profondeur excessive, regen."""
        now = self.now()
        for sid, p in list(self.players.items()):
            if p.get("is_bot"):
                continue
            if p.get("integrity", 100.0) <= 0:
                continue
            boat = p.get("boat") or {}
            boat_type = p.get("boatType") or ""
            pos = p.get("position") or {}
            if self.is_in_danger_zone(pos.get("x", 0), pos.get("z", 0), world_data):
                self.apply_player_damage(sid, p, dt, None)
                if p.get("integrity", 100.0) <= 0:
                    continue
            if boat_type == "submarine":
                max_depth_m = boat.get("maxDepthMeters", 200)
                max_dive_y = -min(max_depth_m, 500 - 5) / UNIT_METERS_BOT
                y = pos.get("y", 0)
                if y < max_dive_y:
                    overshoot_m = (max_dive_y - y) * UNIT_METERS_BOT
                    damage = 0.5 * overshoot_m * dt
                    self.apply_player_damage(sid, p, damage, None)
                    if p.get("integrity", 100.0) <= 0:
                        continue
            last_dmg = p.get("regen_paused_at", 0)
            if (p.get("regen_budget", 0) > 0
                    and p.get("regen_total_remaining", 0) > 0
                    and p.get("integrity", 100.0) < p.get("maxIntegrity", 100.0)
                    and (now - last_dmg) >= REGEN_DELAY_S):
                gain = min(REGEN_RATE_PER_S * dt,
                           p.get("regen_budget", 0),
                           p.get("regen_total_remaining", 0),
                           p.get("maxIntegrity", 100.0) - p.get("integrity", 100.0))
                if gain > 0:
                    p["integrity"] = p.get("integrity", 100.0) + gain
                    p["regen_budget"] = p.get("regen_budget", 0) - gain
                    p["regen_total_remaining"] = p.get("regen_total_remaining", 0) - gain
                    # Opt 2 : throttle de la regen à ~4 Hz. On émet seulement tous
                    # les 0.25 s, OU quand la regen vient de se terminer (intégrité
                    # pleine, budget ou réserve épuisés) pour garantir la valeur
                    # finale exacte côté client.
                    regen_done = (p.get("integrity", 100.0) >= p.get("maxIntegrity", 100.0)
                                  or p.get("regen_budget", 0) <= 0
                                  or p.get("regen_total_remaining", 0) <= 0)
                    if regen_done or (now - p.get("last_regen_emit", 0)) >= 0.25:
                        p["last_regen_emit"] = now
                        self._emit_integrity(sid, p)

    # ===================== AUTOPILOTE HUMAIN (multi-bateaux) =====================

    def update_human_autopilot(self, p: Dict[str, Any], dt: float, world_data: Dict[str, Any]) -> None:
        """Avance un bateau de joueur humain non actif. Garde son rudder/speed
        d'origine. Trois états : cruise → backup (recule pour sortir d'une danger
        zone) → stopped. Pas de waypoint ; figé sur les derniers inputs de move()."""
        legacy = self._legacy
        point_on_any_island = legacy.point_on_any_island
        pos = p.get("position") or {}
        rot = float(p.get("rotation") or 0)
        rudder = float(p.get("rudder") or 0)
        sr = float(p.get("speedRatio") or 0)
        reverse = bool(p.get("reverse"))
        boat = p.get("boat") or {}
        max_speed_kn = boat.get("speed", 25)
        max_speed_us = max_speed_kn * 0.514444 / UNIT_METERS_BOT
        speed = sr * max_speed_us * (-1.0 if reverse else 1.0)
        state = p.get("_autopilot_state") or "cruise"
        cur_x = pos.get("x", 0)
        cur_z = pos.get("z", 0)
        look_ahead_u = 15.0
        fwd_x = -math.cos(rot) * look_ahead_u
        fwd_z = math.sin(rot) * look_ahead_u
        ahead_in_danger = self.is_in_danger_zone(cur_x + fwd_x, cur_z + fwd_z, world_data)
        here_in_danger = self.is_in_danger_zone(cur_x, cur_z, world_data)

        # Bateau mis en autopilote par perte de focus (visibilitychange) : on
        # n'applique pas la logique défensive (cruise/backup/stopped) — il garde
        # sa vitesse et son cap. Au pire, il finira en danger zone si l'utilisateur
        # ne revient pas, mais c'est un bug user-side acceptable.
        paused_by_vis = bool(p.get("_paused_by_visibility"))
        if paused_by_vis:
            # Onglet inactif : on garde la vitesse/cap mémorisés sans appliquer
            # la logique défensive. On ignore aussi un éventuel ancien état
            # "stopped" hérité d'une session précédente.
            state = "cruise"
        elif state == "cruise":
            if here_in_danger:
                state = "backup"
                p["speedRatio"] = 0.5
                p["reverse"] = True
                p["rudder"] = 0
                sr = 0.5
                reverse = True
                speed = sr * max_speed_us * -1.0
            elif ahead_in_danger:
                state = "stopped"
                p["speedRatio"] = 0
                p["reverse"] = False
                p["rudder"] = 0
                sr = 0
                speed = 0
        elif state == "backup":
            if not here_in_danger:
                state = "stopped"
                p["speedRatio"] = 0
                p["reverse"] = False
                p["rudder"] = 0
                sr = 0
                speed = 0
        elif state == "stopped":
            sr = 0
            speed = 0
        p["_autopilot_state"] = state

        new_rot = rot + rudder * sr * (1 if speed >= 0 else -1) * dt
        nx = cur_x - math.cos(new_rot) * speed * dt
        nz = cur_z + math.sin(new_rot) * speed * dt
        if point_on_any_island(nx, nz, world_data):
            return
        p["rotation"] = new_rot
        pos["x"] = nx
        pos["z"] = nz

    # ===================== HELPERS BOTS =====================

    def segment_min_island_distance(self, x1, z1, x2, z2, world_data, cap=None):
        legacy = self._legacy
        point_on_any_island = legacy.point_on_any_island
        min_distance_to_islands = legacy.min_distance_to_islands
        dx = x2 - x1
        dz = z2 - z1
        length = (dx * dx + dz * dz) ** 0.5
        steps = max(2, int(length / 5) + 1)
        best = float("inf")
        for i in range(steps + 1):
            ti = i / steps
            x = x1 + dx * ti
            z = z1 + dz * ti
            if point_on_any_island(x, z, world_data):
                return 0.0
            d = min_distance_to_islands(x, z, world_data, cap=cap)
            if d < best:
                best = d
            if cap is not None and best < cap:
                return best
            if best == 0:
                return 0.0
        return best

    def pick_bot_waypoint(self, bot: Dict[str, Any], world_data: Dict[str, Any]) -> Optional[Dict[str, float]]:
        legacy = self._legacy
        min_distance_to_islands = legacy.min_distance_to_islands
        import random as _random
        half_w = world_data["ground"]["width"] / 2 - 20
        half_d = world_data["ground"]["depth"] / 2 - 20
        px = bot["position"]["x"]
        pz = bot["position"]["z"]
        profiles = [
            (300.0 / UNIT_METERS_BOT, 2000.0 / UNIT_METERS_BOT, 8000.0 / UNIT_METERS_BOT, 60),
            (150.0 / UNIT_METERS_BOT, 800.0 / UNIT_METERS_BOT, 5000.0 / UNIT_METERS_BOT, 60),
            (60.0 / UNIT_METERS_BOT, 300.0 / UNIT_METERS_BOT, 3000.0 / UNIT_METERS_BOT, 80),
        ]
        socketio = getattr(legacy, "socketio", None)
        for min_margin, min_dist, max_dist, attempts in profiles:
            for i in range(attempts):
                if i and (i % 10) == 0 and socketio is not None:
                    socketio.sleep(0)
                ang = _random.uniform(0, math.tau)
                dist = _random.uniform(min_dist, max_dist)
                wx = max(-half_w, min(half_w, px + math.cos(ang) * dist))
                wz = max(-half_d, min(half_d, pz + math.sin(ang) * dist))
                if min_distance_to_islands(wx, wz, world_data, cap=min_margin) < min_margin:
                    continue
                if self.segment_min_island_distance(px, pz, wx, wz, world_data, cap=min_margin) < min_margin:
                    continue
                return {"x": wx, "z": wz}
        return None

    def detect_enemies_passive(self, bot: Dict[str, Any], world_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Sonar passif : détecte les bateaux dont le bruit perçu (atténué par
        la distance) dépasse le seuil minNoise du bot écoutant. LOS requise.
        Cônes avant et arrière ±45° (90° chacun) : sensibilité x4 (portée x2
        effective). Les côtés (latéral 90° centré perpendiculaire au cap)
        restent en sensibilité normale."""
        legacy = self._legacy
        line_of_sight_clear = legacy.line_of_sight_clear
        count_thermoclines = legacy.count_thermoclines_crossed
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        by = bot["position"].get("y", 0)
        # Cap du bot écouteur (axe -X dans la convention world).
        bot_rot = float(bot.get("rotation") or 0)
        cap_x = -math.cos(bot_rot)
        cap_z = math.sin(bot_rot)
        AXIAL_CONE_HALF_DEG = 45.0
        cos_cone = math.cos(math.radians(AXIAL_CONE_HALF_DEG))
        AXIAL_CONE_GAIN = 4.0  # portée x2 effective
        bot_boat = bot.get("boat") or {}
        passive = bot_boat.get("passiveSonar") or {}
        listen_threshold = float(passive.get("minNoise", 5.0))
        detected = []
        for sid, p in self.players.items():
            if p.get("id") == bot.get("id"):
                continue
            if same_team(bot, p):
                continue
            if p.get("sunk"):
                continue
            boat = p.get("boat") or {}
            sr = float(p.get("speedRatio") or 0)
            if sr == 0 and p.get("is_bot"):
                p_speed = abs(float(p.get("speed", 0)))
                p_max = float(p.get("max_speed_us", 1.0))
                sr = min(1.0, p_speed / max(0.001, p_max))
            rev = bool(p.get("reverse"))
            rudder_max = float(p.get("rudder_max") or boat.get("rudderMax") or 15.0)
            rudder = abs(float(p.get("rudder", 0))) / max(0.001, rudder_max)
            emitted = compute_emitted_noise(boat, sr, rev, rudder)
            if emitted <= 0:
                continue
            pos = p.get("position") or {}
            px = pos.get("x", 0)
            pz = pos.get("z", 0)
            py = pos.get("y", 0)
            dist_u = math.hypot(px - bx, pz - bz)
            dist_m = dist_u * UNIT_METERS_BOT
            perceived = perceived_noise(emitted, dist_m)
            # Atténuation thermocline : -80% par couche entre la source et l'écouteur.
            nc = count_thermoclines(px, py, pz, bx, by, bz, world_data, UNIT_METERS_BOT)
            if nc > 0:
                perceived *= THERMOCLINE_NOISE_FACTOR ** nc
            # Bonus cônes axiaux (avant ±15° ET arrière ±15°) : sensibilité
            # x4. |cos| compare à cos(15°) ce qui couvre les deux cônes
            # symétriques par rapport au cap du bateau.
            if dist_u > 1e-3:
                to_src_x = (px - bx) / dist_u
                to_src_z = (pz - bz) / dist_u
                cos_to_src = to_src_x * cap_x + to_src_z * cap_z
                if abs(cos_to_src) >= cos_cone:
                    perceived *= AXIAL_CONE_GAIN
            if perceived < listen_threshold:
                continue
            if not line_of_sight_clear(bx, bz, px, pz, world_data):
                continue
            detected.append({
                "id": p["id"],
                "sid": sid,
                "x": px, "z": pz, "y": py,
                "dist_m": dist_m,
                "speedRatio": sr,
                "noise_emitted": emitted,
                "noise_perceived": perceived,
            })
        return detected

    def bot_drop_lure(self, bot: Dict[str, Any]) -> bool:
        """Largue un leurre depuis le bot (mêmes règles que handle_lure_drop).
        Émet LureDropped event."""
        legacy = self._legacy
        boat = bot.get("boat") or {}
        spec = boat.get("acousticLures")
        if not spec:
            return False
        sid = bot["sid"]
        if legacy.lure_ammo.get(sid, 0) <= 0:
            return False
        pos = bot["position"]
        rotation = float(bot.get("rotation") or 0)
        cos_r = math.cos(rotation)
        sin_r = math.sin(rotation)
        stern = 1.5
        x = pos["x"] + cos_r * stern
        z = pos["z"] - sin_r * stern
        boat_type = bot.get("boatType") or ""
        y = pos.get("y", 0) if boat_type == "submarine" else 0.0
        noise = float(spec.get("noise", 0))
        duration_ms = float(spec.get("time", 0)) * 60.0 * 1000.0
        capacity = integrity_capacity(spec, 10.0)
        pid = bot["id"]
        next_lid = legacy.next_lure_lid
        lid = next_lid.get(pid, 1)
        next_lid[pid] = lid + 1
        expires_at = self.now() + duration_ms / 1000.0
        self.lures[(pid, lid)] = {
            "ownerId": pid, "lid": lid,
            "x": x, "y": y, "z": z, "noise": noise,
            "expiresAt": expires_at,
            "integrity": capacity, "maxIntegrity": capacity,
        }
        legacy.lure_ammo[sid] = max(0, legacy.lure_ammo.get(sid, 0) - 1)
        self.emit(ev_mod.LureDropped(
            owner_id=pid, lid=lid,
            x=x, y=y, z=z,
            noise=noise, duration_ms=duration_ms,
            integrity=capacity, max_integrity=capacity,
        ))
        return True

    def bot_sonar_ping(self, bot: Dict[str, Any], world_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Emet un ping BT/RL ; retourne [], acquisition differee dans Sim.step."""
        now = self.now()
        boat = bot.get("boat") or {}
        active_sonar = boat.get("activeSonar") or {}
        cone_deg = float(active_sonar.get("largeAngle", 120))
        detect_m = float(active_sonar.get("largeAngleRange", 2500))
        reveal_m = float(active_sonar.get("reveal", 15000))
        detect_u = detect_m / UNIT_METERS_BOT
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        by = bot["position"].get("y", 0)
        rotation = float(bot.get("rotation", 0))
        half_cos = math.cos(math.radians(cone_deg) / 2.0) if cone_deg < 360 else -2.0
        fwd_x = -math.cos(rotation)
        fwd_z = math.sin(rotation)
        # Broadcast animation aux clients via event.
        self.emit(ev_mod.SonarPinged(
            player_id=bot["id"], x=bx, z=bz, y=by,
            cone_deg=cone_deg, rotation=rotation,
            range_m=detect_m, reveal_m=reveal_m,
        ))
        bb = bot.setdefault("bb", {})
        bb["last_ping_at"] = now

        self._pending_sonar_pings.append({
            "bot": bot, "at": now, "x": bx, "y": by, "z": bz,
            "range": detect_u, "reveal": reveal_m / UNIT_METERS_BOT,
            "half_cos": half_cos, "fwd_x": fwd_x, "fwd_z": fwd_z,
            "penetration": float(active_sonar.get("thermoclinePenetration", 0)),
            "rolls": {},
        })
        return []

    def update_active_sonar(self, world_data: Dict[str, Any]) -> None:
        """Front du ping local humain : 5 s strictes, puis revelation de 10 s."""
        now = self.now()
        for key, reveal in list(self._sonar_reveals.items()):
            observer, target = reveal["bot"], reveal["target"]
            registry = self.bots if reveal["target_registry"] == "bots" else self.players
            if (now >= reveal["until"] or observer.get("sunk") or target.get("sunk")
                    or self.bots.get(observer["sid"]) is not observer
                    or registry.get(reveal["sid"]) is not target):
                del self._sonar_reveals[key]
            elif self.bot_target_los(observer, target["position"]):
                reveal["position"] = dict(target["position"])
                reveal["observed_at"] = now
        pending = []
        for ping in self._pending_sonar_pings:
            bot = ping["bot"]
            elapsed = now - ping["at"]
            if elapsed >= 5.0 or bot.get("sunk") or self.bots.get(bot["sid"]) is not bot:
                continue
            pending.append(ping)
            if elapsed <= 0:
                continue
            front = elapsed / 5.0 * ping["range"]
            targets = [("players", sid, p) for sid, p in self.players.items() if not p.get("is_bot")]
            targets.extend(("bots", sid, p) for sid, p in self.bots.items())
            for target_registry, sid, target in targets:
                if target is bot or target.get("sunk") or same_team(bot, target):
                    continue
                pos = target.get("position") or {}
                x, y, z = pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)
                dx, dz = x - ping["x"], z - ping["z"]
                distance = math.hypot(dx, dz)
                if distance > front or distance > ping["range"]:
                    continue
                if distance > 0 and (dx * ping["fwd_x"] + dz * ping["fwd_z"]) / distance < ping["half_cos"]:
                    continue
                if not geometry.line_of_sight_clear(ping["x"], ping["z"], x, z, world_data):
                    continue
                if geometry.count_thermoclines_crossed(
                        ping["x"], ping["y"], ping["z"], x, y, z, world_data, UNIT_METERS_BOT) > 0:
                    if target["id"] not in ping["rolls"]:
                        ping["rolls"][target["id"]] = (
                            ping["penetration"] > 0 and random.random() < ping["penetration"])
                    if not ping["rolls"][target["id"]]:
                        continue
                origin = bot["position"]
                if math.hypot(x - origin["x"], z - origin["z"]) > ping["reveal"]:
                    continue
                key = (bot["sid"], target["id"])
                if key not in self._sonar_reveals:
                    self._sonar_reveals[key] = {
                        "bot": bot, "target": target, "sid": sid, "until": now + 10.0,
                        # Le miroir players d'un bot live est un objet distinct.
                        "target_registry": target_registry,
                        "position": {"x": x, "y": y, "z": z}, "observed_at": now,
                    }
                    if target_registry == "bots":
                        bb = target.setdefault("bb", {})
                        bb["pinged_at"] = now
                        bb["pinged_by_pos"] = {"x": ping["x"], "z": ping["z"], "id": bot["id"]}
        self._pending_sonar_pings = pending

    def active_sonar_contacts(self, bot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Revelation acquise : dernier point observe, fige derriere une ile."""
        contacts = []
        for reveal in self._sonar_reveals.values():
            target = reveal["target"]
            registry = self.bots if reveal["target_registry"] == "bots" else self.players
            if (reveal["bot"] is not bot or self.now() >= reveal["until"]
                    or bot.get("sunk") or target.get("sunk")
                    or self.bots.get(bot["sid"]) is not bot
                    or registry.get(reveal["sid"]) is not target):
                continue
            tracked = self.bot_target_los(bot, target["position"])
            if tracked:
                reveal["position"] = dict(target["position"])
                reveal["observed_at"] = self.now()
            pos = reveal["position"]
            contacts.append({
                "id": target["id"], "sid": reveal["sid"],
                "x": pos["x"], "y": pos.get("y", 0), "z": pos["z"],
                "dist_m": math.hypot(pos["x"] - bot["position"]["x"],
                                     pos["z"] - bot["position"]["z"]) * UNIT_METERS_BOT,
                "active_detected_until": reveal["until"],
                "observed_at": reveal["observed_at"], "tracked": tracked,
            })
        return contacts

    def bot_target_los(self, bot: Dict[str, Any], position: Dict[str, Any]) -> bool:
        """LOS de perception ; ne conditionne pas un lancement vers un point."""
        origin = bot["position"]
        return geometry.line_of_sight_clear(
            origin["x"], origin["z"], position["x"], position["z"], self.world_data)

    def spawn_bot_torpedo(self, bot: Dict[str, Any], target_player: Optional[Dict[str, Any]] = None) -> bool:
        """Lance une torpille tirée par un bot (même simu serveur que les humains)."""
        legacy = self._legacy
        boat = bot.get("boat") or {}
        specs = boat_torpedo_specs(boat)
        spec = specs.get("acoustic") or specs.get("autonomous")
        if not spec:
            return False
        kind = "acoustic" if specs.get("acoustic") and spec is specs.get("acoustic") else "autonomous"
        sid = bot["sid"]
        ammo = legacy.torpedo_ammo.get(sid)
        if ammo is None:
            legacy.init_torpedo_ammo_for_sid(sid)
            ammo = legacy.torpedo_ammo.get(sid) or {}
        if ammo.get(kind, 0) <= 0:
            return False
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        by = bot["position"]["y"]
        max_range_m = spec.get("maxRangeMeters", 10000)
        initial_target = None
        if target_player is not None:
            px = target_player["position"]["x"]
            pz = target_player["position"]["z"]
            py = target_player["position"].get("y", 0)
            initial_target = (px, py, pz)
            if math.hypot(px - bx, pz - bz) * UNIT_METERS_BOT > max_range_m * 0.7:
                return False
        dir_x = -math.cos(bot["rotation"])
        dir_z = math.sin(bot["rotation"])
        pid = bot["id"]
        next_tid = legacy.next_torpedo_tid
        tid = next_tid.get(pid, 1)
        next_tid[pid] = tid + 1
        spawn_x = bx + dir_x * 0.4
        spawn_z = bz + dir_z * 0.4
        # Spawn à la profondeur du tireur (clampé au plafond -2m sous la surface).
        spawn_y = min(TORPEDO_CEILING_Y, by)
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
            "activation": spec.get("activation", 0) / UNIT_METERS_BOT,
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
            "initialTarget": initial_target,
            "targetId": None if target_player is None or "observed_at" in target_player else target_player["id"],
            "wireYaw": 0,
            "wirePitch": 0,
            "notifiedTargets": set(),
            "bornAt": self.now(),
        }
        self.torpedoes[(pid, tid)] = t
        ammo[kind] = max(0, ammo.get(kind, 0) - 1)
        self._emit_torpedo_state(t)
        target_id = target_player["id"] if target_player is not None else None
        if target_player is not None and "observed_at" not in target_player and not target_player.get("is_bot"):
            for sid2, other in self.players.items():
                if other.get("id") == target_id:
                    self.emit(ev_mod.TorpedoAlert(
                        shooter_id=pid,
                        tid=tid,
                        kind=kind,
                        outgoing=False,
                        target_sid=sid2,
                    ))
                    break
            t["notifiedTargets"].add(target_id)
        return True

    def spawn_bot_torpedo_autonomous(self, bot: Dict[str, Any], target_player: Optional[Dict[str, Any]] = None,
                                     activation_m: float = None) -> bool:
        """Lance une torpille autonome avec activation_distance personnalisée.
        Si activation_m est None, utilise la valeur du JSON spec."""
        legacy = self._legacy
        boat = bot.get("boat") or {}
        specs = boat_torpedo_specs(boat)
        spec = specs.get("autonomous")
        if not spec:
            return False
        sid = bot["sid"]
        ammo = legacy.torpedo_ammo.get(sid)
        if ammo is None:
            legacy.init_torpedo_ammo_for_sid(sid)
            ammo = legacy.torpedo_ammo.get(sid) or {}
        if ammo.get("autonomous", 0) <= 0:
            return False
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        by = bot["position"]["y"]
        max_range_m = spec.get("maxRangeMeters", 20000)
        initial_target = None
        if target_player is not None:
            px = target_player["position"]["x"]
            pz = target_player["position"]["z"]
            py = target_player["position"].get("y", 0)
            initial_target = (px, py, pz)
            dist_u = math.hypot(px - bx, pz - bz)
            if dist_u * UNIT_METERS_BOT > max_range_m * 0.7:
                return False
        dir_x = -math.cos(bot["rotation"])
        dir_z = math.sin(bot["rotation"])
        pid = bot["id"]
        next_tid = legacy.next_torpedo_tid
        tid = next_tid.get(pid, 1)
        next_tid[pid] = tid + 1
        spawn_x = bx + dir_x * 0.4
        spawn_z = bz + dir_z * 0.4
        # Spawn à la profondeur du tireur (clampé au plafond -2m sous la surface).
        spawn_y = min(TORPEDO_CEILING_Y, by)
        speed_us = spec.get("speed", 55) * 0.514444 / UNIT_METERS_BOT
        radar_range_m = spec.get("radarRangeMeters", 10000)
        if activation_m is None:
            activation_m = spec.get("activation", 500)
        t = {
            "ownerSid": sid,
            "ownerPlayerId": pid,
            "tid": tid,
            "kind": "autonomous",
            "x": spawn_x, "y": spawn_y, "z": spawn_z,
            "dirX": dir_x, "dirZ": dir_z,
            "pitch": 0.0,
            "speed": speed_us,
            "minTurnRadius": spec.get("minTurnRadius", 500) / UNIT_METERS_BOT,
            "maxRange": max_range_m / UNIT_METERS_BOT,
            "activation": activation_m / UNIT_METERS_BOT,
            "damage": spec.get("damage", 80),
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
            "initialTarget": initial_target,
            "targetId": None if target_player is None or "observed_at" in target_player else target_player["id"],
            "wireYaw": 0,
            "wirePitch": 0,
            "notifiedTargets": set(),
            "bornAt": self.now(),
        }
        # Diagnostic profondeur tir : pitch initial calculé sur horizon = minTurnRadius*1.5.
        try:
            import logging as _lg
            if initial_target is None:
                dist_u, py = 0.0, spawn_y
            horiz_clamp_u = max(0.001, min(dist_u, t["minTurnRadius"] * 1.5))
            init_pitch_deg = math.degrees(math.atan2(py - spawn_y, horiz_clamp_u))
            _lg.info(
                f"[torp-spawn] {pid} autonomous "
                f"shooter_y={by * UNIT_METERS_BOT:.1f}m → spawn_y={spawn_y * UNIT_METERS_BOT:.1f}m "
                f"target_y={py * UNIT_METERS_BOT:.1f}m dist={dist_u * UNIT_METERS_BOT:.0f}m "
                f"activ={activation_m:.0f}m pitch_init={init_pitch_deg:.1f}°"
            )
        except Exception:
            pass
        self.torpedoes[(pid, tid)] = t
        ammo["autonomous"] = max(0, ammo.get("autonomous", 0) - 1)
        self._emit_torpedo_state(t)
        target_id = target_player["id"] if target_player is not None else None
        if target_player is not None and "observed_at" not in target_player and not target_player.get("is_bot"):
            for sid2, other in self.players.items():
                if other.get("id") == target_id:
                    self.emit(ev_mod.TorpedoAlert(
                        shooter_id=pid,
                        tid=tid,
                        kind="autonomous",
                        outgoing=False,
                        target_sid=sid2,
                    ))
                    break
            t["notifiedTargets"].add(target_id)
        return True

    def bot_fire_cannon(self, bot: Dict[str, Any], target_player: Dict[str, Any]) -> bool:
        """Le contact observe ou memorise fournit uniquement un point copie."""
        return self.fire_cannon(bot["sid"], bot, target_player.get("position"))

    def fire_cannon(self, sid: str, shooter: Dict[str, Any], point: Any,
                    target_type: str = "boat") -> bool:
        """Lance la meme parabole pour humains/BT/RL, sans guidage par identifiant."""
        legacy = self._legacy
        boat = shooter.get("boat") or {}
        cannon = boat.get("cannon")
        if not cannon or shooter.get("sunk") or self.now() < shooter.get("next_cannon_at", 0):
            return False
        if not isinstance(point, dict):
            return False
        coords = [point.get("x"), point.get("y", 0.0), point.get("z")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in coords):
            return False
        px, py, pz = coords
        bx, by, bz = (shooter["position"][axis] for axis in ("x", "y", "z"))
        if shooter.get("boatType") == "submarine" and by < -boat.get("flotation", 2) / UNIT_METERS_BOT - 0.05:
            return False
        range_m = cannon.get("range", 8000)
        dx, dz = px - bx, pz - bz
        dist_m = math.hypot(dx, dz) * UNIT_METERS_BOT
        # Un deplacement non resoluble au carre annule le solveur, voire la duree.
        if not math.isfinite(dist_m) or not 0 < dist_m <= range_m or dx * dx + dz * dz == 0:
            return False
        ammo = legacy.cannon_ammo.get(sid)
        if ammo is None:
            legacy.init_cannon_ammo_for_sid(sid)
            ammo = legacy.cannon_ammo.get(sid) or {}
        if ammo.get("cannon", 0) <= 0:
            return False
        ammo["cannon"] = max(0, ammo.get("cannon", 0) - 1)
        legacy.emit_cannon_counts(sid)
        max_prob, min_prob = 1.0, 0.3
        half_range = range_m / 2
        if dist_m <= half_range:
            hit_prob = max_prob
        else:
            hit_prob = max_prob - (max_prob - min_prob) * ((dist_m - half_range) / max(1.0, range_m - half_range))
        hit = random.random() < (hit_prob if target_type in ("boat", "point") else 1.0)
        end_x, end_y, end_z = px, py, pz
        if not hit:
            miss_r = 8.0 / UNIT_METERS_BOT
            ang = random.uniform(0, math.tau)
            end_x += math.cos(ang) * miss_r
            end_z += math.sin(ang) * miss_r
        CANNON_SHELL_SPEED_MS = 500.0
        flight_s = dist_m / CANNON_SHELL_SPEED_MS
        duration_ms = flight_s * 1000.0
        dist_u = math.hypot(end_x - bx, end_z - bz)
        range_u = range_m / UNIT_METERS_BOT
        if dist_u > range_u:
            end_x = bx + (end_x - bx) * range_u / dist_u
            end_z = bz + (end_z - bz) * range_u / dist_u
            dist_u = range_u
        arc_height = dist_u * 0.25 * min(1.0, dist_u / max(1.0, range_u))
        start_y = 0.5 if shooter.get("boatType") == "destroyer" else 0.0
        shot_id = self._next_cannon_shot
        self._next_cannon_shot += 1
        self.emit(ev_mod.CannonFire(
            shooter_id=shooter["id"], kind="cannon",
            start_x=bx, start_y=start_y, start_z=bz,
            end_x=end_x, end_y=end_y, end_z=end_z,
            arc_height=arc_height, duration=duration_ms,
            impact=True, shot_id=shot_id,
        ))
        self.cannon_shells.append({
            "shot_id": shot_id, "shooter_id": shooter["id"], "at": self.now(),
            "duration": flight_s, "u": 0.0, "start_x": bx, "start_y": start_y, "start_z": bz,
            "end_x": end_x, "end_y": end_y, "end_z": end_z, "arc_height": arc_height,
            "damage": float(cannon.get("damage", 30)), "range_m": range_m,
        })
        return True

    def update_cannon_shells(self) -> None:
        """Collision continue sur la parabole; volumes reels echantillonnes au tick."""
        pending = []
        for shell in self.cannon_shells:
            lo = shell["u"]
            hi = min(1.0, max(lo, (self.now() - shell["at"]) / shell["duration"]))
            sx, sy, sz = (shell["start_" + axis] for axis in ("x", "y", "z"))
            dx, dz = shell["end_x"] - sx, shell["end_z"] - sz
            a = -4 * shell["arc_height"]
            b = shell["end_y"] - sy - a
            def position(u: float) -> Tuple[float, float, float]:
                return sx + dx * u, sy + b * u + a * u * u, sz + dz * u
            x0, _, z0 = position(lo)
            x1, _, z1 = position(hi)
            island = geometry.first_island_intersection(x0, z0, x1, z1, self.world_data)
            best = lo + (hi - lo) * island if island is not None else float("inf")
            victim = None
            reason = "island"
            # Le rayon reprend la demi-longueur torpille (100 m par defaut),
            # la tolerance verticale directe existante vaut 0.4 u (4 m).
            objects = []
            for sid, p in list(self.players.items()):
                if p.get("sunk") or p.get("id") == shell["shooter_id"]:
                    continue
                pos, boat = p.get("position") or {}, p.get("boat") or {}
                if pos.get("y", 0) < -boat.get("flotation", 2) / UNIT_METERS_BOT - 0.05:
                    continue
                objects.append(("boat", sid, p, pos,
                                float(boat.get("lengthMeters") or 100) / (2 * UNIT_METERS_BOT), 0.4))
            for kind, store in (("beacon", self.beacons),
                                ("passive_beacon", self._legacy.passive_sonar_beacons), ("mine", self.mines)):
                for key, obj in list(store.items()):
                    if kind != "mine" or obj.get("kind") == "surface":
                        objects.append((kind, key, obj, dict(obj, y=0.0), 1.0, 0.4))
            for kind, key, obj, pos, radius, vertical in objects:
                ox, oz = sx - pos.get("x", 0), sz - pos.get("z", 0)
                qa, qb = dx * dx + dz * dz, 2 * (ox * dx + oz * dz)
                qc = ox * ox + oz * oz - radius * radius
                if not math.isfinite(qa) or qa <= 0:
                    continue
                disc = qb * qb - 4 * qa * qc
                if not math.isfinite(disc) or disc < 0:
                    continue
                root = math.sqrt(disc)
                enter, leave = max(lo, (-qb - root) / (2 * qa)), min(hi, (-qb + root) / (2 * qa))
                if enter > leave:
                    continue
                cuts = [enter, leave]
                for level in (pos.get("y", 0) - vertical, pos.get("y", 0) + vertical):
                    c = sy - level
                    if a:
                        d = b * b - 4 * a * c
                        if d >= 0:
                            cuts.extend(u for u in ((-b - math.sqrt(d)) / (2 * a),
                                                   (-b + math.sqrt(d)) / (2 * a)) if enter <= u <= leave)
                    elif b and enter <= -c / b <= leave:
                        cuts.append(-c / b)
                for u in sorted(cuts):
                    if abs(position(u)[1] - pos.get("y", 0)) <= vertical + 1e-9 and u < best:
                        best, victim, reason = u, (kind, key, obj), kind
                        break
            if best == float("inf") and hi < 1:
                shell["u"] = hi
                pending.append(shell)
                continue
            if best == float("inf"):
                best, reason = 1.0, "range"
            x, y, z = position(best)
            self.emit(ev_mod.CannonImpact(shooter_id=shell["shooter_id"], shot_id=shell["shot_id"],
                                         x=x, y=y, z=z, reason=reason))
            if victim:
                kind, key, obj = victim
                if kind == "boat":
                    self.emit(ev_mod.CannonHit(shooter_id=shell["shooter_id"], target_id=obj["id"], damage=shell["damage"]))
                    if key in self.bots:
                        self.bot_apply_damage(key, self.bots[key], shell["damage"], shell["shooter_id"])
                    else:
                        self.apply_player_damage(key, obj, shell["damage"], shell["shooter_id"])
                elif kind == "mine":
                    self.explode_server_mine(obj, trigger_id=shell["shooter_id"])
                elif kind == "beacon":
                    self.beacons.pop(key, None)
                    self.emit(ev_mod.SonarBeaconDestroyed(bid=key))
                else:
                    self._legacy.passive_sonar_beacons.pop(key, None)
                    self.emit(ev_mod.PassiveSonarBeaconDestroyed(bid=key))
        self.cannon_shells = pending

    def bot_fire_aa(self, bot: Dict[str, Any], drone: Dict[str, Any]) -> bool:
        """Tir DCA bot vers un drone. Émet CannonFire ; kill différé via socketio."""
        if not self.bot_target_los(bot, drone):
            return False
        import random as _random
        legacy = self._legacy
        aa = (bot.get("boat") or {}).get("antiAircraft")
        if not aa:
            return False
        range_m = aa.get("range", 5000)
        bx, by, bz = bot["position"]["x"], bot["position"]["y"], bot["position"]["z"]
        dx_m = (drone["x"] - bx) * UNIT_METERS_BOT
        dz_m = (drone["z"] - bz) * UNIT_METERS_BOT
        dy_m = (drone["y"] - by) * UNIT_METERS_BOT
        dist_m = (dx_m * dx_m + dy_m * dy_m + dz_m * dz_m) ** 0.5
        if dist_m > range_m:
            return False
        max_prob = 0.9
        min_prob = 0.3
        half_range = range_m / 2
        if dist_m <= half_range:
            hit_prob = max_prob
        else:
            hit_prob = max_prob - (max_prob - min_prob) * ((dist_m - half_range) / max(1.0, range_m - half_range))
        hit = _random.random() < hit_prob
        end_x, end_y, end_z = drone["x"], drone["y"], drone["z"]
        if not hit:
            miss_r = 5.0 / UNIT_METERS_BOT
            ang = _random.uniform(0, math.tau)
            end_x += math.cos(ang) * miss_r
            end_z += math.sin(ang) * miss_r
        start_y = 0.5 if bot["boatType"] == "destroyer" else 0.0
        AA_BULLET_SPEED_MS = 1000.0
        flight_s = dist_m / AA_BULLET_SPEED_MS
        duration_ms = flight_s * 1000.0
        self.emit(ev_mod.CannonFire(
            shooter_id=bot["id"], kind="antiAircraft",
            start_x=bx, start_y=start_y, start_z=bz,
            end_x=end_x, end_y=end_y, end_z=end_z,
            arc_height=0.0, duration=duration_ms,
            impact=False,
        ))
        if hit:
            owner_id = drone["ownerPlayerId"]
            did = drone["did"]
            socketio = getattr(legacy, "socketio", None)

            def _delayed_kill():
                if socketio is not None:
                    socketio.sleep(flight_s)
                d = self.drones.get((owner_id, did))
                if d:
                    self.kill_server_drone(d, reason="shot", refund=False)
                    self.drones.pop((owner_id, did), None)
            if socketio is not None:
                socketio.start_background_task(_delayed_kill)
        return True

    def bot_torpedoes_threat(self, bot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """ETA positives d'abord ; les CPA passes proches restent representes."""
        out = []
        for t in self.torpedoes.values():
            threat = torpedo_radar_threat(bot, t, self.world_data)
            if threat is None:
                continue
            dist_now, cpa_m, eta_s = threat
            out.append({
                "tid": t.get("tid"), "ownerId": t.get("ownerPlayerId"), "kind": None,
                "ownerPlayerId": t.get("ownerPlayerId"),
                "dist_m": dist_now, "cpa_m": cpa_m, "eta_s": eta_s,
                "x": t["x"], "z": t["z"], "dirX": t.get("dirX", 0), "dirZ": t.get("dirZ", 0),
                "speed": t.get("speed", 0),
            })
        out.sort(key=lambda d: (d["eta_s"] <= 0.0, d["eta_s"]))
        return out

    # ===================== TICK BOT (BT + legacy fallback) =====================

    def detect_beacons_for_bot(self, bot: Dict[str, Any], world_data: Dict[str, Any]) -> None:
        """Un bot détecte une balise active ennemie dès qu'il entre dans son
        rayon de ping + 10 %, en LOS clear. Pose _flee_from pour déclencher
        une réorientation immédiate (sans attendre le ping toutes les 30 s)."""
        bot_team = bot.get("team_id")
        if not bot_team or self._legacy is None:
            return
        line_of_sight_clear = self._legacy.line_of_sight_clear
        bpos = bot.get("position") or {}
        bx = bpos.get("x", 0); bz = bpos.get("z", 0)
        bb_bot = bot.setdefault("bb", {})
        for b in self.beacons.values():
            b_team = b.get("teamId")
            if not b_team or b_team == bot_team:
                continue
            range_m = float(b.get("rangeMeters", 1000)) * 1.10
            range_u = range_m / UNIT_METERS_BOT
            dx = b["x"] - bx
            dz = b["z"] - bz
            if dx * dx + dz * dz > range_u * range_u:
                continue
            if not line_of_sight_clear(bx, bz, b["x"], b["z"], world_data):
                continue
            bb_bot["_flee_from"] = (b["x"], b["z"])
            bb_bot["_flee_at"] = self.now()
            return  # un seul flee à la fois suffit

    def detect_mines_for_bot(self, bot: Dict[str, Any], world_data: Dict[str, Any]) -> None:
        """- Mine déjà connue de la team : fuite à ≤ 1.2× la portée (3D, sans
          LOS — la team a déjà la position).
        - Mine inconnue : détection à ≤ 1.1× la portée (3D, LOS clear) →
          révèle à la team + fuite immédiate.
        Le seuil de fuite (1.2) > seuil de détection (1.1) garantit qu'une
        mine fraîchement détectée est dans la zone de fuite des mines connues
        au tick suivant."""
        bot_team = bot.get("team_id")
        if not bot_team or self._legacy is None:
            return
        line_of_sight_clear = self._legacy.line_of_sight_clear
        bpos = bot.get("position") or {}
        bx = bpos.get("x", 0); by = bpos.get("y", 0); bz = bpos.get("z", 0)
        bb_bot = bot.setdefault("bb", {})
        active_teams = {p.get("team_id") for p in self.players.values() if p.get("team_id")}
        for m in self.mines.values():
            revealed_teams = m.setdefault("revealedTeams", set())
            revealed_teams.intersection_update(active_teams)
            m_team = m.get("teamId")
            if not m_team or m_team == bot_team:
                continue
            r_u = float(m.get("range", 60)) / UNIT_METERS_BOT
            dx = m["x"] - bx
            dy = m.get("y", 0) - by
            dz = m["z"] - bz
            d_sq = dx * dx + dy * dy + dz * dz
            is_known = bot_team in revealed_teams
            if is_known:
                flee_r = 1.2 * r_u
                if d_sq > flee_r * flee_r:
                    continue
                bb_bot["_flee_from"] = (m["x"], m["z"])
                bb_bot["_flee_at"] = self.now()
            else:
                detect_r = 1.1 * r_u
                if d_sq > detect_r * detect_r:
                    continue
                if not line_of_sight_clear(bx, bz, m["x"], m["z"], world_data):
                    continue
                revealed_teams.add(bot_team)
                self.emit(ev_mod.MineRevealed(
                    owner_id=m["ownerId"], mid=m["mid"], target_team=bot_team
                ))
                bb_bot["_flee_from"] = (m["x"], m["z"])
                bb_bot["_flee_at"] = self.now()

    def _bot_evasion_depth(self, bot: Dict[str, Any], dt: float, world_data: Dict[str, Any]) -> None:
        """Subs sous attaque plongent sous la thermocline la plus proche ou à profondeur max."""
        if bot.get("boatType") != "submarine":
            return
        now = self.now()
        bb = bot.get("bb") or {}
        under_fire = bb.get("enemy_aware_until", 0) > now
        if not under_fire:
            bot.pop("_evasion_logged", None)
            return
        bot_y = bot["position"]["y"]
        bot_depth_m = -bot_y * UNIT_METERS_BOT
        max_depth_m = bot.get("max_depth_m", 300) * 0.9
        target_depth_m = max_depth_m
        thermos = world_data.get("thermoclines") or []
        if thermos:
            best_tc = None
            for tc in thermos:
                pts = tc.get("points")
                if not pts or len(pts) < 3:
                    continue
                tc_depth_m = float(tc.get("depthMeters", 50))
                if tc_depth_m >= max_depth_m:
                    continue
                if tc_depth_m > bot_depth_m - 30:
                    if best_tc is None or tc_depth_m < best_tc:
                        best_tc = tc_depth_m
            if best_tc is not None:
                target_depth_m = best_tc + 20
                if not bot.get("_evasion_logged"):
                    dlog("grenades", f"evasion {bot['id']} plonge sous thermocline {best_tc}m → cible {target_depth_m:.0f}m (actuel {bot_depth_m:.0f}m)")
                    bot["_evasion_logged"] = True
        else:
            if not bot.get("_evasion_logged"):
                dlog("grenades", f"evasion {bot['id']} pas de thermocline, plonge à {target_depth_m:.0f}m (actuel {bot_depth_m:.0f}m)")
                bot["_evasion_logged"] = True
        bot["depth_target_y"] = -target_depth_m / UNIT_METERS_BOT
        dy = bot["depth_target_y"] - bot["position"]["y"]
        rate = 0.5 * dt
        if abs(dy) < rate:
            bot["position"]["y"] = bot["depth_target_y"]
        else:
            bot["position"]["y"] += math.copysign(rate, dy)

    def update_bot(self, bot: Dict[str, Any], dt: float, world_data: Dict[str, Any]) -> None:
        """Dispatch : contrôle externe > BT > legacy."""
        legacy = self._legacy
        if bot.get("external_control"):
            controller = bot.get("rl_controller")
            if controller is not None:
                try:
                    controller.tick(bot, self, world_data, dt)
                except Exception:
                    logging.exception(f"[rl] tick error for {bot.get('id')}")
                    bot["rl_controller"] = None
                    bot["control_target_speed_ratio"] = 0.0
            self.update_bot_external(bot, dt, world_data)
            return
        tree = bot.get("ai_tree")
        if tree is not None:
            ctx = {
                "bot": bot,
                "world": world_data,
                "dt": dt,
                "now": self.now(),
                "deps": legacy._get_bt_deps() if hasattr(legacy, "_get_bt_deps") else {},
            }
            try:
                tree.tick(ctx)
            except Exception:
                logging.exception(f"[bt] tick error for {bot.get('id')}")
                self.update_bot_legacy(bot, dt, world_data)
            self._bot_evasion_depth(bot, dt, world_data)
            return
        self.update_bot_legacy(bot, dt, world_data)

    def update_bot_external(self, bot: Dict[str, Any], dt: float,
                            world_data: Dict[str, Any]) -> None:
        """Applique uniquement les commandes d'un contrôleur externe.

        Aucun comportement, capteur ou armement automatique n'est exécuté ici :
        le contrôleur RL reste l'unique auteur des décisions.
        """
        target_rudder = max(-1.0, min(1.0, float(
            bot.get("control_target_rudder", 0.0)))) * float(bot.get("rudder_max", 0.36))
        rudder_step = float(bot.get("rudder_speed", 0.3)) * dt
        rudder_delta = target_rudder - float(bot.get("rudder", 0.0))
        if abs(rudder_delta) <= rudder_step:
            bot["rudder"] = target_rudder
        else:
            bot["rudder"] += math.copysign(rudder_step, rudder_delta)

        target_speed = max(-1.0, min(1.0, float(
            bot.get("control_target_speed_ratio", 0.0)))) * float(bot.get("max_speed_us", 0.0))
        throttle_step = float(bot.get("throttle_accel", 0.4)) * dt
        speed_delta = target_speed - float(bot.get("speed", 0.0))
        if abs(speed_delta) <= throttle_step:
            bot["speed"] = target_speed
        else:
            bot["speed"] += math.copysign(throttle_step, speed_delta)

        speed = float(bot.get("speed", 0.0))
        max_speed = max(0.001, float(bot.get("max_speed_us", 0.0)))
        speed_ratio = min(1.0, abs(speed) / max_speed)
        turn_ratio = max(speed_ratio, 0.2)
        bot["rotation"] += float(bot.get("rudder", 0.0)) * turn_ratio * (1 if speed >= 0 else -1) * dt
        nx = bot["position"]["x"] - math.cos(bot["rotation"]) * speed * dt
        nz = bot["position"]["z"] + math.sin(bot["rotation"]) * speed * dt
        half_w = world_data["ground"]["width"] / 2 - 4.0
        half_d = world_data["ground"]["depth"] / 2 - 4.0
        if (-half_w <= nx <= half_w and -half_d <= nz <= half_d
                and not self._legacy.point_on_any_island(nx, nz, world_data)):
            bot["position"]["x"] = nx
            bot["position"]["z"] = nz
        else:
            bot["speed"] = 0.0

        if bot.get("boatType") == "submarine":
            max_depth_m = float(bot.get("max_depth_m", 200.0))
            target_y = float(bot.get("control_target_depth_y", bot["position"].get("y", 0.0)))
            target_y = max(-max_depth_m / UNIT_METERS_BOT, min(TORPEDO_CEILING_Y, target_y))
            depth_delta = target_y - float(bot["position"].get("y", 0.0))
            depth_step = 0.5 * dt
            if abs(depth_delta) <= depth_step:
                bot["position"]["y"] = target_y
            else:
                bot["position"]["y"] += math.copysign(depth_step, depth_delta)

        sync = self.players.get(bot["sid"])
        if sync is not None:
            sync["position"] = dict(bot["position"])
            sync["rotation"] = bot["rotation"]
            sync["speed"] = bot["speed"]
            sync["speedRatio"] = min(1.0, abs(bot["speed"]) / max_speed)
            sync["reverse"] = bot["speed"] < 0
            sync["rudder"] = bot["rudder"]
            sync["integrity"] = bot.get("integrity", 100.0)
            sync["maxIntegrity"] = bot.get("maxIntegrity", 100.0)

    def update_bot_legacy(self, bot: Dict[str, Any], dt: float, world_data: Dict[str, Any]) -> None:
        """Tick legacy : navigation waypoint + détection passive + tirs réactifs."""
        import random as _random
        legacy = self._legacy
        point_on_any_island = legacy.point_on_any_island
        if bot["waypoint"] is None:
            bot["waypoint"] = self.pick_bot_waypoint(bot, world_data)
        wp = bot["waypoint"]
        if wp is not None:
            dx = wp["x"] - bot["position"]["x"]
            dz = wp["z"] - bot["position"]["z"]
            dist_to_wp = (dx * dx + dz * dz) ** 0.5
            if dist_to_wp < 150.0 / UNIT_METERS_BOT:
                bot["waypoint"] = None
            else:
                want_heading = math.atan2(dz, -dx)
                hd = ((want_heading - bot["rotation"]) + math.pi * 3) % (math.pi * 2) - math.pi
                target_rudder = max(-bot["rudder_max"], min(bot["rudder_max"], hd * 2.0))
                step = bot["rudder_speed"] * dt
                if abs(target_rudder - bot["rudder"]) < step:
                    bot["rudder"] = target_rudder
                else:
                    bot["rudder"] += math.copysign(step, target_rudder - bot["rudder"])
                cruise = bot["cruise_us"]
                tstep = bot["throttle_accel"] * dt
                if abs(bot["speed"] - cruise) < tstep:
                    bot["speed"] = cruise
                else:
                    bot["speed"] += math.copysign(tstep, cruise - bot["speed"])
        speed = bot["speed"]
        speed_ratio = min(1.0, abs(speed) / max(0.001, bot["max_speed_us"] * 0.5))
        turn_ratio = max(speed_ratio, 0.6)
        bot["rotation"] += bot["rudder"] * turn_ratio * (1 if speed >= 0 else -1) * dt
        nx = bot["position"]["x"] - math.cos(bot["rotation"]) * speed * dt
        nz = bot["position"]["z"] + math.sin(bot["rotation"]) * speed * dt
        half_w = world_data["ground"]["width"] / 2 - 4.0
        half_d = world_data["ground"]["depth"] / 2 - 4.0
        if nx < -half_w or nx > half_w or nz < -half_d or nz > half_d:
            bot["speed"] = 0
            bot["waypoint"] = None
        elif not point_on_any_island(nx, nz, world_data):
            bot["position"]["x"] = nx
            bot["position"]["z"] = nz
        else:
            bot["speed"] = 0
            bot["waypoint"] = None
        if bot["boatType"] == "submarine":
            now = self.now()
            bb = bot.get("bb") or {}
            under_fire = bb.get("enemy_aware_until", 0) > now
            if not under_fire and now >= bot["next_depth_change_at"]:
                bot["next_depth_change_at"] = now + _random.uniform(20, 60)
                r = _random.random()
                if r < 0.3:
                    bot["depth_target_y"] = -5.0 / UNIT_METERS_BOT
                else:
                    min_depth_m = 30
                    max_depth_m = max(min_depth_m + 1, bot["max_depth_m"] * 0.7)
                    depth_m = _random.uniform(min_depth_m, max_depth_m)
                    bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
            if not under_fire:
                dy = bot["depth_target_y"] - bot["position"]["y"]
                rate = 0.5 * dt
                if abs(dy) < rate:
                    bot["position"]["y"] = bot["depth_target_y"]
                else:
                    bot["position"]["y"] += math.copysign(rate, dy)
        sync = self.players.get(bot["sid"])
        if sync is not None:
            sync["position"] = dict(bot["position"])
            sync["rotation"] = bot["rotation"]
        # Détection passive (~1 Hz).
        from bot_ai import _remember_contacts
        now = self.now()
        if now - bot.get("next_detect_at", 0) >= 0:
            bot["next_detect_at"] = now + 1.0
            detected = self.detect_enemies_passive(bot, world_data)
            _remember_contacts(bot, detected, self.players, now)
            new_ids = {d["id"] for d in detected}
            bot["last_detected_ids"] = new_ids
        bots_passive = bool(getattr(legacy, "bots_passive", False))
        flotation_m = (bot.get("boat") or {}).get("flotation", 2)
        surface_y = -flotation_m / UNIT_METERS_BOT
        can_fire_air = bot["position"]["y"] >= surface_y - 0.05
        # Torpille réactive.
        if not bots_passive and now >= bot.get("next_torpedo_at", 0):
            torps = (bot.get("boat") or {}).get("torpedoes") or {}
            if torps.get("acoustic") or torps.get("autonomous"):
                spec = torps.get("acoustic") or torps.get("autonomous")
                max_range_m = spec.get("maxRangeMeters", 10000)
                target_player = None
                best_dist = float("inf")
                for p in bot.get("detected_targets", {}).values():
                    if p["id"] not in (bot.get("last_detected_ids") or set()):
                        continue
                    pos = p.get("position") or {}
                    d_u = ((pos.get("x", 0) - bot["position"]["x"]) ** 2
                           + (pos.get("z", 0) - bot["position"]["z"]) ** 2) ** 0.5
                    if d_u * UNIT_METERS_BOT > max_range_m * 0.7:
                        continue
                    if d_u < best_dist:
                        best_dist = d_u
                        target_player = p
                if target_player is not None:
                    if self.spawn_bot_torpedo(bot, target_player):
                        bot["next_torpedo_at"] = now + 8.0
        # Cannon.
        if not bots_passive and can_fire_air and (bot.get("boat") or {}).get("cannon") and now >= bot.get("next_cannon_at", 0):
            cannon = (bot.get("boat") or {}).get("cannon") or {}
            range_m = cannon.get("range", 8000)
            target_player = None
            best_dist = float("inf")
            for p in bot.get("detected_targets", {}).values():
                if p["id"] not in (bot.get("last_detected_ids") or set()):
                    continue
                if not self.bot_target_los(bot, p["position"]):
                    continue
                pos = p.get("position") or {}
                if pos.get("y", 0) < -0.6:
                    continue
                d_u = ((pos.get("x", 0) - bot["position"]["x"]) ** 2
                       + (pos.get("z", 0) - bot["position"]["z"]) ** 2) ** 0.5
                if d_u * UNIT_METERS_BOT > range_m:
                    continue
                if d_u < best_dist:
                    best_dist = d_u
                    target_player = p
            if target_player is not None and self.bot_fire_cannon(bot, target_player):
                bot["next_cannon_at"] = now + 3.0
        # DCA.
        if not bots_passive and can_fire_air and (bot.get("boat") or {}).get("antiAircraft") and now >= bot.get("next_aa_at", 0):
            per_drone_cd = bot.setdefault("aa_per_drone", {})
            for key, deadline in list(per_drone_cd.items()):
                if key not in self.drones or deadline <= now:
                    per_drone_cd.pop(key, None)
            for key, drone in list(self.drones.items()):
                owner_pid = drone["ownerPlayerId"]
                owner = None
                for sid, p in self.players.items():
                    if p["id"] == owner_pid:
                        owner = p
                        break
                if owner is None or same_team(bot, owner):
                    continue
                if now < per_drone_cd.get(key, 0):
                    continue
                if self.bot_fire_aa(bot, drone):
                    bot["next_aa_at"] = now + 0.4
                    per_drone_cd[key] = now + 1.5
                    break

    # ===================== Avancement temporel =====================

    def step(self, dt: float, world_data: Optional[Dict[str, Any]] = None) -> None:
        """Avance la simu d'un tick complet : torpilles, drones, grenades, mines,
        intégrité, autopilote humains, bots. Émet PlayerMoved pour les bots et
        bateaux humains autopilotés via events."""
        if self._legacy is None:
            return
        self.t = self.now()
        if world_data is None:
            world_data = self.world_data
        if not world_data:
            return
        self.update_cannon_shells()
        self.update_active_sonar(world_data)
        self.update_server_torpedoes(dt, world_data)
        self.update_server_drones(dt, world_data)
        self.update_server_grenades(dt, world_data)
        self.update_server_mines(dt, world_data)
        self.update_player_integrity(dt, world_data)
        # Autopilote humains non actifs.
        autopiloted = self._legacy.autopiloted_sids
        now = self.now()
        for sid_h in list(autopiloted):
            p = self.players.get(sid_h)
            if p is None or p.get("is_bot"):
                autopiloted.discard(sid_h)
                continue
            if p.get("sunk"):
                continue
            self.update_human_autopilot(p, dt, world_data)
            if now - p.get("last_autopilot_emit", 0) >= 0.05:
                p["last_autopilot_emit"] = now
                py = p["position"].get("y", 0)
                _sub = py <= -5.0 / UNIT_METERS_BOT
                _sr = p.get("speedRatio", 0)
                _rev = p.get("reverse", False)
                _int = float(p.get("integrity", 100.0))
                if self._should_emit_moved(p, now, p["position"], p["rotation"],
                                           _sr, _rev, _sub, _int):
                    self.emit(ev_mod.PlayerMoved(
                        player_id=p["id"],
                        position=p["position"],
                        rotation=p["rotation"],
                        rudder=p.get("rudder", 0),
                        reverse=_rev,
                        speed_ratio=_sr,
                        integrity=_int,
                        max_integrity=p.get("maxIntegrity", 100.0),
                        submerged=_sub,
                    ))
        # Bots.
        for sid, bot in list(self.bots.items()):
            try:
                self.detect_mines_for_bot(bot, world_data)
                self.detect_beacons_for_bot(bot, world_data)
                self.update_bot(bot, dt, world_data)
            except Exception:
                logging.exception(f"bot update error: {bot.get('id')}")
                continue
            if now - bot["last_emit"] >= 0.05:
                bot["last_emit"] = now
                speed_ratio = abs(bot["speed"]) / max(0.001, bot["max_speed_us"])
                bot_y = bot["position"].get("y", 0)
                _sub = bot_y <= -5.0 / UNIT_METERS_BOT
                _rev = bot["speed"] < 0
                _int = float(bot.get("integrity", 100.0))
                if self._should_emit_moved(bot, now, bot["position"], bot["rotation"],
                                           speed_ratio, _rev, _sub, _int):
                    self.emit(ev_mod.PlayerMoved(
                        player_id=bot["id"],
                        position=bot["position"],
                        rotation=bot["rotation"],
                        rudder=bot["rudder"] / 15.0,
                        reverse=_rev,
                        speed_ratio=speed_ratio,
                        integrity=_int,
                        max_integrity=bot.get("maxIntegrity", 100.0),
                        submerged=_sub,
                    ))

    # ===================== Reset / Done (training) =====================

    def reset(self) -> None:
        """Vide tout l'état : prêt à recevoir un nouveau scénario.
        N'efface PAS world_data ; recréer le Sim ou réassigner pour cela."""
        self.players.clear()
        self.bots.clear()
        self.torpedoes.clear()
        self.drones.clear()
        self.grenades.clear()
        self.mines.clear()
        self.beacons.clear()
        self.lures.clear()
        self._active_wire.clear()
        self._events.clear()
        self.cannon_shells.clear()
        self._next_cannon_shot = 0
        self._pending_sonar_pings.clear()
        self._sonar_reveals.clear()
        self._danger_zones_cache = {"world_id": None, "zones": []}
        self.t = self.now()

    def done(self) -> bool:
        """Épisode terminé : aucun humain vivant OU aucun bot vivant.
        Pour l'entraînement RL : la condition de fin se définit côté wrapper Gym."""
        humans_alive = any(
            (not p.get("is_bot")) and p.get("integrity", 100) > 0 and not p.get("sunk")
            for p in self.players.values()
        )
        bots_alive = any(b.get("integrity", 100) > 0 for b in self.bots.values())
        return (not humans_alive) or (not bots_alive)

    # ===================== API publique =====================

    def get_state_snapshot(self) -> Dict[str, Any]:
        return {
            "t": self.t,
            "n_players": len(self.players),
            "n_bots": len(self.bots),
            "n_torpedoes": len(self.torpedoes),
            "n_drones": len(self.drones),
            "n_mines": len(self.mines),
        }
