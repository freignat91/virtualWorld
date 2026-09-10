"""Behavior Tree pour les bots IA.

Moteur BT minimal + registre de conditions et actions.
Les arbres sont chargés depuis bots/ai/<name>.json et associés à un bot
via son champ `boat["ai"]` ou via le cheat `autosub <ai_name>`.

Architecture :

    Status        : SUCCESS / FAILURE / RUNNING (chaînes)
    Node          : interface tick(ctx) -> Status
    Sequence(*c)  : tous les enfants doivent réussir (s'arrête au premier FAILURE)
    Selector(*c)  : un seul enfant doit réussir (s'arrête au premier SUCCESS/RUNNING)
    Condition(fn) : feuille qui retourne SUCCESS/FAILURE selon fn(ctx)
    Action(fn)    : feuille qui exécute fn(ctx). Le retour de fn (Status ou None)
                    devient le résultat (None → SUCCESS).

Le contexte `ctx` passé à chaque tick contient :
    bot         dict du bot (état IA + position synchronisée)
    world       world_data
    dt          delta time du tick
    now         time.time() du tick
    deps        dict de fonctions externes (server.py les fournit) pour éviter
                un import circulaire bot_ai → server
"""

import copy
import json
import logging
import math
import os
import random
import time
import simulation
import geometry
from typing import Any, Dict, Iterable, Optional

# ===================== Status & Nodes =====================

class Status:
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


class Node:
    def __init__(self, name=None):
        self.name = name

    def tick(self, ctx):
        raise NotImplementedError


class Sequence(Node):
    def __init__(self, children, name=None):
        super().__init__(name)
        self.children = children

    def tick(self, ctx):
        for c in self.children:
            r = c.tick(ctx)
            if r != Status.SUCCESS:
                return r
        return Status.SUCCESS


class Selector(Node):
    def __init__(self, children, name=None):
        super().__init__(name)
        self.children = children

    def tick(self, ctx):
        for c in self.children:
            r = c.tick(ctx)
            if r != Status.FAILURE:
                return r
        return Status.FAILURE


class Parallel(Node):
    """Tick TOUS les enfants. Renvoie SUCCESS si au moins un réussit."""
    def __init__(self, children, name=None):
        super().__init__(name)
        self.children = children

    def tick(self, ctx):
        any_success = False
        for c in self.children:
            r = c.tick(ctx)
            if r == Status.SUCCESS:
                any_success = True
        return Status.SUCCESS if any_success else Status.FAILURE


class AlwaysSuccess(Node):
    """Décorateur : tick l'enfant et retourne toujours SUCCESS (ignore l'échec).
    Utile pour des branches optionnelles dans une Sequence."""
    def __init__(self, child, name=None):
        super().__init__(name)
        self.child = child

    def tick(self, ctx):
        self.child.tick(ctx)
        return Status.SUCCESS


class Condition(Node):
    def __init__(self, fn_name, params, name=None, negate=False):
        super().__init__(name or fn_name)
        self.fn_name = fn_name
        self.params = params or {}
        self.negate = negate

    def tick(self, ctx):
        fn = CONDITIONS.get(self.fn_name)
        if fn is None:
            logging.warning(f"[bt] Unknown condition: {self.fn_name}")
            return Status.FAILURE
        result = fn(ctx, self.params)
        if self.negate:
            result = not result
        return Status.SUCCESS if result else Status.FAILURE


class Action(Node):
    def __init__(self, fn_name, params, name=None):
        super().__init__(name or fn_name)
        self.fn_name = fn_name
        self.params = params or {}

    def tick(self, ctx):
        fn = ACTIONS.get(self.fn_name)
        if fn is None:
            logging.warning(f"[bt] Unknown action: {self.fn_name}")
            return Status.FAILURE
        r = fn(ctx, self.params)
        if r is None:
            return Status.SUCCESS
        return r


# ===================== Loader JSON =====================

def build_tree(node_json):
    t = node_json.get("type")
    name = node_json.get("name")
    if t == "Sequence":
        return Sequence([build_tree(c) for c in (node_json.get("children") or [])], name)
    if t == "Selector":
        return Selector([build_tree(c) for c in (node_json.get("children") or [])], name)
    if t == "Parallel":
        return Parallel([build_tree(c) for c in (node_json.get("children") or [])], name)
    if t == "AlwaysSuccess":
        return AlwaysSuccess(build_tree(node_json["child"]), name)
    if t == "Condition":
        return Condition(node_json["fn"], node_json.get("params"), name, negate=bool(node_json.get("negate")))
    if t == "Action":
        return Action(node_json["fn"], node_json.get("params"), name)
    raise ValueError(f"Unknown BT node type: {t!r}")


_AI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots", "ai")
_ai_cache = {}


def load_ai(name):
    """Charge bots/ai/<name>.json (avec cache). Retourne le root Node ou None
    si introuvable / invalide."""
    if not name:
        return None
    if name in _ai_cache:
        return _ai_cache[name]
    path = os.path.join(_AI_DIR, name + ".json")
    if not os.path.exists(path):
        logging.warning(f"[bt] AI file not found: {path}")
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        tree = build_tree(data["tree"])
    except Exception as e:
        logging.exception(f"[bt] Failed to load AI {name}: {e}")
        return None
    _ai_cache[name] = tree
    logging.info(f"[bt] Loaded AI '{name}' ({data.get('description', 'no description')})")
    return tree


def reload_ai(name=None):
    """Vide le cache (tout ou par nom). Utile pour itérer sans redémarrer."""
    if name:
        _ai_cache.pop(name, None)
    else:
        _ai_cache.clear()


# ===================== Registres =====================
# Conditions : (ctx, params) -> bool
# Actions    : (ctx, params) -> Status | None (None = SUCCESS)
#
# Toutes les conditions/actions reçoivent le ctx ; les dépendances externes
# (fonctions du serveur, dictionnaires globaux) sont injectées via ctx["deps"].
# Cela évite un import circulaire bot_ai ↔ server.

CONDITIONS = {}
ACTIONS = {}


def register_condition(name):
    def deco(fn):
        CONDITIONS[name] = fn
        return fn
    return deco


def register_action(name):
    def deco(fn):
        ACTIONS[name] = fn
        return fn
    return deco


# ===================== Conditions =====================

@register_condition("is_submarine")
def cond_is_submarine(ctx, params):
    return ctx["bot"].get("boatType") == "submarine"


@register_condition("is_destroyer")
def cond_is_destroyer(ctx, params):
    return ctx["bot"].get("boatType") == "destroyer"


@register_condition("can_fire_air")
def cond_can_fire_air(ctx, params):
    """Vrai si le bateau est en surface (pour canon / DCA)."""
    bot = ctx["bot"]
    boat = bot.get("boat") or {}
    flotation_m = boat.get("flotation", 2)
    surface_y = -flotation_m / ctx["deps"]["UNIT_METERS_BOT"]
    return bot["position"]["y"] >= surface_y - 0.05


@register_condition("bots_active")
def cond_bots_active(ctx, params):
    """Faux si le toggle global `bots_passive` est activé (cheat calmdown)."""
    return not ctx["deps"]["bots_passive_get"]()


@register_condition("torpedo_cooldown_ok")
def cond_torpedo_cooldown_ok(ctx, params):
    return ctx["now"] >= ctx["bot"].get("next_torpedo_at", 0)


@register_condition("cannon_cooldown_ok")
def cond_cannon_cooldown_ok(ctx, params):
    return ctx["now"] >= ctx["bot"].get("next_cannon_at", 0)


@register_condition("aa_cooldown_ok")
def cond_aa_cooldown_ok(ctx, params):
    return ctx["now"] >= ctx["bot"].get("next_aa_at", 0)


@register_condition("has_cannon")
def cond_has_cannon(ctx, params):
    return bool((ctx["bot"].get("boat") or {}).get("cannon"))


@register_condition("has_aa")
def cond_has_aa(ctx, params):
    return bool((ctx["bot"].get("boat") or {}).get("antiAircraft"))


@register_condition("has_torpedo")
def cond_has_torpedo(ctx, params):
    """Vrai si le bot a au moins une torpille acoustique ou autonome dans son JSON."""
    torps = (ctx["bot"].get("boat") or {}).get("torpedoes") or {}
    return bool(torps.get("acoustic") or torps.get("autonomous"))


@register_condition("has_audible_enemy")
def cond_has_audible_enemy(ctx, params):
    """Vrai si la dernière détection passive a au moins un ennemi humain."""
    return bool(ctx["bot"].get("last_detected_ids"))


@register_condition("torpedo_incoming")
def cond_torpedo_incoming(ctx, params):
    """Vrai si une ou plusieurs torpilles menacent ce bot. Cache le résultat
    sur le bot pour 0.5 s pour éviter de recalculer à 20 Hz.
    Params optionnels :
      - max_eta_s : ne déclenche que si une torpille arrive dans ≤ X s (défaut : 10)
    """
    bot = ctx["bot"]
    now = ctx["now"]
    cache = bot.get("_threat_cache")
    if not cache or cache["at"] + 0.5 < now:
        threats = ctx["deps"]["bot_torpedoes_threat"](bot)
        cache = {"at": now, "threats": threats}
        bot["_threat_cache"] = cache
    threats = cache["threats"]
    if not threats:
        return False
    max_eta = float(params.get("max_eta_s", 10.0))
    return any(t["eta_s"] <= max_eta for t in threats)


@register_condition("torpedo_far")
def cond_torpedo_far(ctx, params):
    """Vrai si la torpille la plus proche est à plus de `threshold_m` (défaut 1000).
    Utilise le cache _threat_cache."""
    bot = ctx["bot"]
    now = ctx["now"]
    cache = bot.get("_threat_cache")
    if not cache or cache["at"] + 0.5 < now:
        threats = ctx["deps"]["bot_torpedoes_threat"](bot)
        cache = {"at": now, "threats": threats}
        bot["_threat_cache"] = cache
    threats = cache["threats"]
    if not threats:
        return False
    threshold_m = float(params.get("threshold_m", 1000.0))
    closest = min(threats, key=lambda t: t["dist_m"])
    return closest["dist_m"] > threshold_m


@register_condition("torpedo_acquired")
def cond_torpedo_acquired(ctx, params):
    """ETA geometrique nulle ou evasion en cours ; ne prouve aucun verrou."""
    bb = ctx["bot"].setdefault("bb", {})
    if bb.get("_evade") is not None:
        return True
    bot = ctx["bot"]
    now = ctx["now"]
    cache = bot.get("_threat_cache")
    if not cache or cache["at"] + 0.5 < now:
        threats = ctx["deps"]["bot_torpedoes_threat"](bot)
        cache = {"at": now, "threats": threats}
        bot["_threat_cache"] = cache
    threats = cache["threats"]
    if not threats:
        return False
    acquired = [t for t in threats if t["eta_s"] == 0.0 and t["dist_m"] < float(params.get("max_dist_m", 5000.0))]
    if acquired:
        logging.info(f"[bt-evade] {bot['id']} ETA nulle ({len(acquired)} menace(s), plus proche a {acquired[0]['dist_m']:.0f}m)")
        return True
    return False


@register_condition("state_is")
def cond_state_is(ctx, params):
    """Vrai si bb['state'] == params['name']. Initialise à 'SEARCH' si absent."""
    bb = ctx["bot"].setdefault("bb", {})
    if "state" not in bb:
        bb["state"] = "SEARCH"
        bb["t_enter"] = ctx["now"]
    return bb["state"] == params.get("name")


@register_condition("enemy_known_recent")
def cond_enemy_known_recent(ctx, params):
    """Vrai si bb['last_enemy_pos'] a été mis à jour il y a moins de max_age_s."""
    bb = ctx["bot"].setdefault("bb", {"state": "SEARCH"})
    last = bb.get("last_enemy_pos")
    if not last:
        return False
    return (ctx["now"] - last.get("t", 0)) <= float(params.get("max_age_s", 30.0))


@register_condition("was_pinged_recently")
def cond_was_pinged_recently(ctx, params):
    """Vrai si le bot a été révélé par un ping sonar il y a moins de max_age_s (défaut 10),
    OU si une évasion ping est en cours (_evade_pinged non None)."""
    bb = ctx["bot"].setdefault("bb", {"state": "SEARCH"})
    if bb.get("_evade_pinged") is not None:
        return True
    pinged_at = bb.get("pinged_at")
    if pinged_at is None:
        return False
    return (ctx["now"] - pinged_at) <= float(params.get("max_age_s", 10.0))


@register_condition("sonar_ping_cooldown_ok")
def cond_sonar_ping_cooldown_ok(ctx, params):
    """Vrai si le cooldown du ping sonar est écoulé."""
    bb = ctx["bot"].setdefault("bb", {"state": "SEARCH"})
    return ctx["now"] >= bb.get("next_sonar_ping_at", 0)


@register_condition("has_human_drone_in_range")
def cond_has_human_drone_in_range(ctx, params):
    """Vrai s'il existe au moins un drone d'humain à portée de la DCA."""
    bot = ctx["bot"]
    aa = (bot.get("boat") or {}).get("antiAircraft") or {}
    range_m = aa.get("range", 3000)
    range_u_sq = (range_m / ctx["deps"]["UNIT_METERS_BOT"]) ** 2
    drones_server = ctx["deps"]["drones_server"]
    players = ctx["deps"]["players"]
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    for key, drone in drones_server.items():
        owner_pid = drone["ownerPlayerId"]
        owner = next((p for p in players.values() if p["id"] == owner_pid), None)
        if owner is None or owner.get("is_bot"):
            continue
        if not ctx["deps"]["bot_target_los"](bot, drone):
            continue
        dx = drone["x"] - bx
        dz = drone["z"] - bz
        if dx * dx + dz * dz <= range_u_sq:
            return True
    return False


@register_condition("enemy_surprise_close")
def cond_enemy_surprise_close(ctx, params):
    """Vrai si un ennemi vient d'être détecté à moins de threshold_m (défaut 1500)
    alors que le bot n'était PAS déjà en STALK/APPROACH/ATTACK (contact surprise),
    OU si une évasion surprise est en cours."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    if bb.get("_evade_surprise") is not None:
        return True
    state = bb.get("state", "SEARCH")
    if state in ("STALK", "APPROACH", "ATTACK", "EVADE_PINGED", "EVADE_SURPRISE"):
        return False
    if bb.get("_evade") is not None:
        return False
    last = bb.get("last_enemy_pos")
    if not last:
        return False
    threshold_m = float(params.get("threshold_m", 1500.0))
    if last["dist_m"] > threshold_m:
        return False
    age = ctx["now"] - last.get("t", 0)
    if age > 2.0:
        return False
    return True


@register_condition("is_enemy_aware")
def cond_is_enemy_aware(ctx, params):
    """Vrai si le bot sait qu'il a été détecté (pingé, touché, torpille acquise).
    Se dissipe après timeout_s (défaut 60) sans nouvel événement."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    aware_until = bb.get("enemy_aware_until", 0)
    return ctx["now"] < aware_until


# ===================== Actions =====================

@register_action("navigate_waypoint")
def act_navigate_waypoint(ctx, params):
    """Pilotage par waypoint : choisit un waypoint si nécessaire, ajuste rudder
    et speed vers le cap voulu.
    Params optionnels :
      - cruise_pct : % de la vitesse max comme cible de croisière (défaut 0.6).
    """
    bot = ctx["bot"]
    world = ctx["world"]
    dt = ctx["dt"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    if bot["waypoint"] is None:
        bot["waypoint"] = deps["pick_bot_waypoint"](bot, world)
    wp = bot["waypoint"]
    cruise_pct = float(params.get("cruise_pct", 0.6))
    cruise_target = bot["max_speed_us"] * cruise_pct
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
            tstep = bot["throttle_accel"] * dt
            if abs(bot["speed"] - cruise_target) < tstep:
                bot["speed"] = cruise_target
            else:
                bot["speed"] += math.copysign(tstep, cruise_target - bot["speed"])
    # Avancée physique.
    speed = bot["speed"]
    speed_ratio = min(1.0, abs(speed) / max(0.001, bot["max_speed_us"] * 0.5))
    bot["rotation"] += bot["rudder"] * speed_ratio * (1 if speed >= 0 else -1) * dt
    nx = bot["position"]["x"] - math.cos(bot["rotation"]) * speed * dt
    nz = bot["position"]["z"] + math.sin(bot["rotation"]) * speed * dt
    if not deps["point_on_any_island"](nx, nz, world):
        bot["position"]["x"] = nx
        bot["position"]["z"] = nz
    else:
        bot["speed"] = 0
        bot["waypoint"] = None
    return Status.SUCCESS


@register_action("submarine_depth_cycle")
def act_submarine_depth_cycle(ctx, params):
    """Pour les sub : alterne profondeur périscopique (~5 m) et plongée
    aléatoire toutes les 20-60 s. No-op (SUCCESS) pour les destroyers."""
    bot = ctx["bot"]
    if bot.get("boatType") != "submarine":
        return Status.SUCCESS
    UNIT_METERS_BOT = ctx["deps"]["UNIT_METERS_BOT"]
    now = ctx["now"]
    dt = ctx["dt"]
    if now >= bot["next_depth_change_at"]:
        bot["next_depth_change_at"] = now + random.uniform(20, 60)
        if random.random() < 0.3:
            bot["depth_target_y"] = -5.0 / UNIT_METERS_BOT
        else:
            min_depth_m = 30
            max_depth_m = max(min_depth_m + 1, bot["max_depth_m"] * 0.7)
            depth_m = random.uniform(min_depth_m, max_depth_m)
            bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
    dy = bot["depth_target_y"] - bot["position"]["y"]
    rate = 0.5 * dt
    if abs(dy) < rate:
        bot["position"]["y"] = bot["depth_target_y"]
    else:
        bot["position"]["y"] += math.copysign(rate, dy)
    return Status.SUCCESS


@register_action("sync_player")
def act_sync_player(ctx, params):
    """Synchronise position, rotation, speed, speedRatio du bot dans `players[sid]`."""
    bot = ctx["bot"]
    sync = ctx["deps"]["players"].get(bot["sid"])
    if sync is not None:
        sync["position"] = dict(bot["position"])
        sync["rotation"] = bot["rotation"]
        speed = float(bot.get("speed", 0))
        max_speed = max(0.001, float(bot.get("max_speed_us", 1.0)))
        sync["speed"] = speed
        sync["speedRatio"] = min(1.0, abs(speed) / max_speed)
        sync["reverse"] = speed < 0
    return Status.SUCCESS


def _remember_contacts(bot: Dict[str, Any], detected: Iterable[Dict[str, Any]],
                       players: Dict[str, Any], now: float) -> None:
    """Copie les donnees au moment de la detection, jamais au moment du tir."""
    targets = {}
    for contact in detected:
        player = next((p for p in players.values() if p.get("id") == contact["id"]), None)
        if player is None:
            continue
        targets[contact["id"]] = {
            "id": contact["id"], "sid": contact["sid"],
            "position": {axis: contact[axis]
                         for axis in ("x", "y", "z")},
            "boat": copy.deepcopy(player.get("boat") or {}),
            "boatType": player.get("boatType"), "is_bot": player.get("is_bot"),
            "observed_at": contact.get("observed_at", now),
        }
    bot["detected_targets"] = targets


def _known_targets(bot: Dict[str, Any], now: float,
                   max_age_s: Optional[float] = None) -> Iterable[Dict[str, Any]]:
    """Selection sur snapshots ; la memoire n'ajoute pas de detection actuelle."""
    ids = bot.get("last_detected_ids") or set()
    targets = {pid: dict(target, tracked=True)
               for pid, target in bot.get("detected_targets", {}).items() if pid in ids}
    last = (bot.get("bb") or {}).get("last_enemy_pos") or {}
    if max_age_s is not None and now - last.get("t", 0) < max_age_s and last.get("target"):
        target = last["target"]
        targets.setdefault(target["id"], dict(target, tracked=False))
    return targets.values()


@register_action("passive_detection")
def act_passive_detection(ctx, params):
    """Passif a 1 Hz, revelations actives a chaque tick ; memoire sans suivi cache."""
    bot = ctx["bot"]
    now = ctx["now"]
    if now >= bot.get("next_detect_at", 0):
        bot["next_detect_at"] = now + 1.0
        bot["passive_contacts"] = [dict(contact, observed_at=now) for contact in
                                   ctx["deps"]["detect_enemies_passive"](bot, ctx["world"])]
    active = ctx["deps"]["active_sonar_contacts"](bot)
    contacts = {contact["id"]: contact for contact in bot.get("passive_contacts", [])}
    for contact in active:
        previous = contacts.get(contact["id"])
        if previous is None or contact["observed_at"] >= previous["observed_at"]:
            contacts[contact["id"]] = contact
    detected = list(contacts.values())
    _remember_contacts(bot, detected, ctx["deps"]["players"], now)
    prev = bot.get("last_detected_ids") or set()
    new_ids = {d["id"] for d in detected if d.get("tracked", True)}
    added = new_ids - prev
    lost = prev - new_ids
    for d in detected:
        if d["id"] in added:
            logging.info(f"[bot-detect] {bot['id']} detecte {d['id']} a {d['dist_m']:.0f} m")
    for pid in lost:
        logging.info(f"[bot-detect] {bot['id']} perd {pid}")
    bot["last_detected_ids"] = new_ids
    # Enregistrer la position de l'ennemi le plus proche dans le blackboard.
    bb = bot.setdefault("bb", {})
    if detected:
        closest = min(detected, key=lambda d: (d["id"] not in new_ids, d["dist_m"]))
        if closest["observed_at"] < bb.get("last_enemy_pos", {}).get("t", -float("inf")):
            return Status.SUCCESS
        bb["last_enemy_pos"] = {
            "x": closest["x"], "y": closest.get("y", 0), "z": closest["z"],
            "target": bot["detected_targets"].get(closest["id"]),
            "id": closest["id"],
            "dist_m": closest["dist_m"],
            "t": closest["observed_at"],
        }
    return Status.SUCCESS


@register_action("sonar_ping")
def act_sonar_ping(ctx, params):
    """Ping sonar actif. Cooldown configurable (défaut 30s).
    L'acquisition attend le front autoritaire dans Sim.step.
    Révèle le bot aux clients (broadcast). Retourne SUCCESS si ping effectué."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    deps = ctx["deps"]
    cooldown_s = float(params.get("cooldown_s", 30.0))
    if now < bb.get("next_sonar_ping_at", 0):
        return Status.FAILURE
    bb["next_sonar_ping_at"] = now + cooldown_s
    deps["bot_sonar_ping"](bot, ctx["world"])
    logging.info(f"[bt-sonar] {bot['id']} ping emis, acquisition differee")
    return Status.SUCCESS


@register_action("fire_torpedo_at_audible")
def act_fire_torpedo_at_audible(ctx, params):
    """Tire une torpille sur l'humain audible le plus proche dans 70% de portée
    max, ou dans l'axe sans contact connu. Cooldown 8 s. SUCCESS si tir."""
    if ctx["deps"]["bots_passive_get"]():
        return Status.FAILURE
    bot = ctx["bot"]
    deps = ctx["deps"]
    torps = (bot.get("boat") or {}).get("torpedoes") or {}
    if ctx["now"] < bot.get("next_torpedo_at", 0.0):
        return Status.FAILURE
    spec = torps.get("acoustic") or torps.get("autonomous")
    if not spec:
        return Status.FAILURE
    max_range_m = spec.get("maxRangeMeters", 10000)
    range_pct = float(params.get("range_pct", 0.7))
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    target_player = None
    best_dist = float("inf")
    targets = list(_known_targets(bot, ctx["now"]))
    for p in targets:
        pos = p.get("position") or {}
        d_u = ((pos.get("x", 0) - bot["position"]["x"]) ** 2
               + (pos.get("z", 0) - bot["position"]["z"]) ** 2) ** 0.5
        if d_u * UNIT_METERS_BOT > max_range_m * range_pct:
            continue
        if d_u < best_dist:
            best_dist = d_u
            target_player = p
    if targets and target_player is None:
        return Status.FAILURE
    if deps["spawn_bot_torpedo"](bot, target_player):
        bot["next_torpedo_at"] = ctx["now"] + float(params.get("cooldown_s", 8.0))
        logging.info(f"[bot-fire] {bot['id']} tire torpille sur {target_player['id'] if target_player else 'cap courant'}")
        return Status.SUCCESS
    return Status.FAILURE


@register_action("fire_cannon_at_surface_enemy")
def act_fire_cannon_at_surface_enemy(ctx, params):
    """Tire au canon sur l'humain en surface détecté le plus proche. Cooldown 3 s."""
    bot = ctx["bot"]
    deps = ctx["deps"]
    cannon = (bot.get("boat") or {}).get("cannon") or {}
    if not cannon:
        return Status.FAILURE
    range_m = cannon.get("range", 8000)
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    target_player = None
    best_dist = float("inf")
    for p in _known_targets(bot, ctx["now"]):
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
    if target_player is None:
        return Status.FAILURE
    if deps["bot_fire_cannon"](bot, target_player):
        bot["next_cannon_at"] = ctx["now"] + float(params.get("cooldown_s", 3.0))
        return Status.SUCCESS
    return Status.FAILURE


@register_action("drop_lure")
def act_drop_lure(ctx, params):
    """Largue un leurre acoustique. Cooldown configurable (défaut 6 s) pour ne
    pas tout consommer en une frame. Retourne SUCCESS si largué."""
    bot = ctx["bot"]
    now = ctx["now"]
    cooldown = float(params.get("cooldown_s", 6.0))
    if now < bot.get("next_lure_at", 0):
        return Status.FAILURE
    if ctx["deps"]["bot_drop_lure"](bot):
        bot["next_lure_at"] = now + cooldown
        logging.info(f"[bot-evade] {bot['id']} largue leurre")
        return Status.SUCCESS
    return Status.FAILURE


@register_action("evade_perpendicular")
def act_evade_perpendicular(ctx, params):
    """Manoeuvre d'esquive : choisit un waypoint à 90° de la trajectoire de la
    torpille la plus menaçante, à `distance_m` (défaut 800 m). Le bateau y va
    via la navigation normale (`navigate_waypoint` au tick suivant).
    Le waypoint est commité pour `commit_s` secondes : pendant cette période,
    on ne recalcule pas (sinon le bot tourne en zigzag à chaque tick et
    n'avance plus)."""
    import math
    bot = ctx["bot"]
    now = ctx["now"]
    if now < bot.get("_evade_until", 0):
        # Esquive déjà engagée : on ne touche pas au waypoint.
        return Status.SUCCESS
    cache = bot.get("_threat_cache")
    if not cache or not cache.get("threats"):
        return Status.FAILURE
    t = cache["threats"][0]  # la plus imminente
    UNIT_METERS_BOT = ctx["deps"]["UNIT_METERS_BOT"]
    dist_u = float(params.get("distance_m", 800.0)) / UNIT_METERS_BOT
    dirX = t.get("dirX", 0)
    dirZ = t.get("dirZ", 0)
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    rx = bx - t.get("x", 0)
    rz = bz - t.get("z", 0)
    rmag = math.hypot(rx, rz) or 1.0
    rx /= rmag
    rz /= rmag
    px1, pz1 = -dirZ, dirX
    px2, pz2 = dirZ, -dirX
    if px1 * rx + pz1 * rz >= px2 * rx + pz2 * rz:
        px, pz = px1, pz1
    else:
        px, pz = px2, pz2
    bot["waypoint"] = {"x": bx + px * dist_u, "z": bz + pz * dist_u}
    bot["_evade_until"] = now + float(params.get("commit_s", 6.0))
    logging.info(f"[bot-evade] {bot['id']} virage perpendiculaire vers ({bot['waypoint']['x']:.1f}, {bot['waypoint']['z']:.1f})")
    return Status.SUCCESS


@register_action("dive_deep")
def act_dive_deep(ctx, params):
    """Sub uniquement : forçage immédiat de la profondeur cible à `depth_m`
    (défaut 80 m). Bypass le cycle aléatoire pour `hold_s` secondes.
    Commit pour ne pas reset le hold à chaque tick d'esquive."""
    bot = ctx["bot"]
    if bot.get("boatType") != "submarine":
        return Status.FAILURE
    now = ctx["now"]
    if now < bot.get("_dive_deep_until", 0):
        return Status.SUCCESS
    UNIT_METERS_BOT = ctx["deps"]["UNIT_METERS_BOT"]
    depth_m = float(params.get("depth_m", 80.0))
    max_depth_m = bot.get("max_depth_m", 200) * 0.9
    depth_m = min(depth_m, max_depth_m)
    bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
    hold_s = float(params.get("hold_s", 30.0))
    bot["next_depth_change_at"] = now + hold_s
    bot["_dive_deep_until"] = now + hold_s
    return Status.SUCCESS


@register_action("evade_torpedo")
def act_evade_torpedo(ctx, params):
    """Esquive torpille — machine à états interne.
    Trigger : torpille acquise sur le bot.
    Phases :
      'flee'  → virage 90° + 1 leurre + plongée, reste sur trajectoire 30s.
                Change de profondeur toutes les 8-12s.
                Si nouvelles torpilles acquises → 1 leurre par torpille (min 5s entre).
      'cover' → après 30s, cherche à se cacher (retreat_to_cover) en évitant
                la direction des leurres.
    """
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    cache = bot.get("_threat_cache")
    threats = (cache or {}).get("threats") or []

    evade = bb.get("_evade")
    if evade is None:
        # --- Initialisation : virage 90° par rapport à la torpille la plus proche ---
        acquired = [t for t in threats if t["eta_s"] == 0.0]
        if not acquired:
            return Status.FAILURE
        t = min(acquired, key=lambda x: x["dist_m"])
        dirX = t.get("dirX", 0)
        dirZ = t.get("dirZ", 0)
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        # Perpendiculaire à la torpille, côté opposé
        rx = bx - t.get("x", 0)
        rz = bz - t.get("z", 0)
        rmag = math.hypot(rx, rz) or 1.0
        rx /= rmag
        rz /= rmag
        px1, pz1 = -dirZ, dirX
        px2, pz2 = dirZ, -dirX
        if px1 * rx + pz1 * rz >= px2 * rx + pz2 * rz:
            flee_dx, flee_dz = px1, pz1
        else:
            flee_dx, flee_dz = px2, pz2
        # Waypoint loin (800m) dans la direction de fuite
        dist_u = float(params.get("flee_distance_m", 800.0)) / UNIT_METERS_BOT
        wp = {"x": bx + flee_dx * dist_u, "z": bz + flee_dz * dist_u}
        bot["waypoint"] = wp
        # Larguer 1 leurre
        lure_ok = deps["bot_drop_lure"](bot)
        logging.info(f"[bot-evade] {bot['id']} leurre initial: {'OK' if lure_ok else 'ECHEC (pas de munitions?)'}")
        # Plongée initiale
        depth_m = random.uniform(60.0, 120.0)
        max_depth_m = bot.get("max_depth_m", 200) * 0.9
        depth_m = min(depth_m, max_depth_m)
        bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
        bot["next_depth_change_at"] = now + random.uniform(8, 12)
        evade = {
            "phase": "flee",
            "started_at": now,
            "wp": wp,
            "flee_dir": (flee_dx, flee_dz),
            "lure_pos": (bx, bz),
            "last_lure_at": now,
            "lures_for_tids": {t["tid"]},
            "next_depth_at": now + random.uniform(8, 12),
        }
        bb["_evade"] = evade
        bb["enemy_aware_until"] = now + 60.0
        logging.info(f"[bot-evade] {bot['id']} EVADE flee: 90° + dive {depth_m:.0f}m + leurre (torp à {t['dist_m']:.0f}m)")

    phase = evade["phase"]

    if phase == "flee":
        # Changement de profondeur régulier
        if now >= evade["next_depth_at"]:
            depth_m = random.uniform(40.0, 140.0)
            max_depth_m = bot.get("max_depth_m", 200) * 0.9
            depth_m = min(depth_m, max_depth_m)
            bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
            bot["next_depth_change_at"] = now + 30.0
            evade["next_depth_at"] = now + random.uniform(8, 12)

        # Vérifier nouvelles torpilles acquises → 1 leurre par nouvelle torpille (min 5s)
        acquired_now = [t for t in threats if t["eta_s"] == 0.0]
        new_acquired = [t for t in acquired_now if t["tid"] not in evade["lures_for_tids"]]
        if new_acquired and now - evade["last_lure_at"] >= 5.0:
            if deps["bot_drop_lure"](bot):
                evade["last_lure_at"] = now
                for t in new_acquired:
                    evade["lures_for_tids"].add(t["tid"])
                logging.info(f"[bot-evade] {bot['id']} leurre supplémentaire ({len(new_acquired)} nouvelle(s) torpille(s))")

        # Navigation : rester sur la trajectoire de fuite (vitesse max)
        wp = evade["wp"]
        flee_params = dict(params)
        flee_params["full_speed"] = True
        _drive_to_waypoint(bot, ctx, wp, flee_params)

        # Après 30s → phase cover
        if now - evade["started_at"] >= float(params.get("flee_duration_s", 30.0)):
            evade["phase"] = "cover"
            logging.info(f"[bot-evade] {bot['id']} EVADE → cover (30s écoulées)")

        return Status.SUCCESS

    elif phase == "cover":
        # Chercher un point de couverture en évitant la direction des leurres
        bb["_evade"] = None
        bb["state"] = "RETREAT"
        bb["t_enter"] = now
        # Mémoriser la direction à éviter (vers les leurres)
        lx, lz = evade["lure_pos"]
        bb["_evade_avoid_dir"] = (lx, lz)
        logging.info(f"[bot-evade] {bot['id']} EVADE → RETREAT (cherche couverture)")
        return Status.SUCCESS

    return Status.SUCCESS


@register_action("evade_pinged")
def act_evade_pinged(ctx, params):
    """Réaction à un ping sonar ennemi : plongée + virage aléatoire + vitesse
    silencieuse pendant duration_s (défaut 20). Pose enemy_aware.
    Phases : 'dive' (plonge + vire) → termine → RETREAT."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]

    evp = bb.get("_evade_pinged")
    if evp is None:
        ping_pos = bb.get("pinged_by_pos") or {}
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        # S'éloigner de la source du ping
        px = ping_pos.get("x", bx)
        pz = ping_pos.get("z", bz)
        dx = bx - px
        dz = bz - pz
        dmag = math.hypot(dx, dz) or 1.0
        # Ajouter une composante aléatoire (±45°) pour ne pas être prédictible
        angle_offset = random.uniform(-0.8, 0.8)
        cos_a = math.cos(angle_offset)
        sin_a = math.sin(angle_offset)
        flee_dx = (dx / dmag) * cos_a - (dz / dmag) * sin_a
        flee_dz = (dx / dmag) * sin_a + (dz / dmag) * cos_a
        dist_u = float(params.get("flee_distance_m", 600.0)) / UNIT_METERS_BOT
        wp = {"x": bx + flee_dx * dist_u, "z": bz + flee_dz * dist_u}
        # Plongée profonde
        depth_m = random.uniform(80.0, 150.0)
        max_depth_m = bot.get("max_depth_m", 200) * 0.9
        depth_m = min(depth_m, max_depth_m)
        bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
        duration_s = float(params.get("duration_s", 20.0))
        evp = {"wp": wp, "started_at": now, "duration_s": duration_s}
        bb["_evade_pinged"] = evp
        bb["enemy_aware_until"] = now + 60.0
        bb.pop("pinged_at", None)
        bb.pop("pinged_by_pos", None)
        logging.info(f"[bot-evade] {bot['id']} EVADE_PINGED: plongée {depth_m:.0f}m + fuite silencieuse {duration_s:.0f}s")

    elapsed = now - evp["started_at"]
    if elapsed >= evp["duration_s"]:
        bb["_evade_pinged"] = None
        bb["state"] = "RETREAT"
        bb["t_enter"] = now
        logging.info(f"[bot-evade] {bot['id']} EVADE_PINGED → RETREAT")
        return Status.SUCCESS

    _drive_to_waypoint(bot, ctx, evp["wp"], params)
    return Status.SUCCESS


@register_action("evade_surprise")
def act_evade_surprise(ctx, params):
    """Réaction à un contact surprise (ennemi détecté très proche sans préparation).
    Leurre + plongée + fuite perpendiculaire à l'ennemi pendant duration_s (défaut 15).
    Pose enemy_aware. Après → RETREAT."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]

    evs = bb.get("_evade_surprise")
    if evs is None:
        last = bb.get("last_enemy_pos") or {}
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        ex = last.get("x", bx)
        ez = last.get("z", bz)
        dx = bx - ex
        dz = bz - ez
        dmag = math.hypot(dx, dz) or 1.0
        # Fuite perpendiculaire (côté aléatoire)
        if random.random() < 0.5:
            flee_dx, flee_dz = -dz / dmag, dx / dmag
        else:
            flee_dx, flee_dz = dz / dmag, -dx / dmag
        dist_u = float(params.get("flee_distance_m", 600.0)) / UNIT_METERS_BOT
        wp = {"x": bx + flee_dx * dist_u, "z": bz + flee_dz * dist_u}
        # Leurre + plongée
        deps["bot_drop_lure"](bot)
        depth_m = random.uniform(70.0, 130.0)
        max_depth_m = bot.get("max_depth_m", 200) * 0.9
        depth_m = min(depth_m, max_depth_m)
        bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
        duration_s = float(params.get("duration_s", 15.0))
        evs = {"wp": wp, "started_at": now, "duration_s": duration_s}
        bb["_evade_surprise"] = evs
        bb["enemy_aware_until"] = now + 60.0
        logging.info(f"[bot-evade] {bot['id']} EVADE_SURPRISE: leurre + plongée {depth_m:.0f}m + fuite {duration_s:.0f}s (ennemi à {last.get('dist_m', 0):.0f}m)")

    elapsed = now - evs["started_at"]
    if elapsed >= evs["duration_s"]:
        bb["_evade_surprise"] = None
        bb["state"] = "RETREAT"
        bb["t_enter"] = now
        logging.info(f"[bot-evade] {bot['id']} EVADE_SURPRISE → RETREAT")
        return Status.SUCCESS

    _drive_to_waypoint(bot, ctx, evs["wp"], params)
    return Status.SUCCESS


@register_action("set_state")
def act_set_state(ctx, params):
    """Écrit bb['state'] = params['name']. Mémorise t_enter pour les actions
    qui veulent savoir depuis combien de temps on est dans cet état."""
    bb = ctx["bot"].setdefault("bb", {})
    new_state = params.get("name")
    if not new_state:
        return Status.FAILURE
    if bb.get("state") != new_state:
        bb["state"] = new_state
        bb["t_enter"] = ctx["now"]
        logging.info(f"[bt-fsm] {ctx['bot']['id']} → {new_state}")
    return Status.SUCCESS


@register_action("stalk_enemy")
def act_stalk_enemy(ctx, params):
    """STALK : se rapproche de la dernière position connue de l'ennemi
    à vitesse silencieuse. Reste en immersion périscopique.
    Intègre l'évaluation : quand on arrive en zone ou que le contact est perdu,
    change l'état directement (EVAL/SEARCH). Tant qu'on se rapproche → SUCCESS
    (le BT continue à ticker)."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    deps = ctx["deps"]
    now = ctx["now"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    last = bb.get("last_enemy_pos")
    if not last:
        bb["state"] = "SEARCH"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} STALK → SEARCH (pas de position)")
        return Status.SUCCESS
    # Contact perdu depuis trop longtemps → retour SEARCH.
    age_s = now - last.get("t", 0)
    lost_timeout_s = float(params.get("lost_timeout_s", 30.0))
    if age_s > lost_timeout_s and not bot.get("last_detected_ids"):
        bb["state"] = "SEARCH"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} STALK → SEARCH (contact perdu {age_s:.0f}s)")
        return Status.SUCCESS
    target = {"x": last["x"], "z": last["z"]}
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    dist_m = math.hypot(target["x"] - bx, target["z"] - bz) * UNIT_METERS_BOT
    # Arrivé à portée d'évaluation ET ennemi toujours audible → transition
    # (seulement si l'état cible existe dans le BT, sinon on reste en STALK).
    eval_range_m = float(params.get("eval_range_m", 5000.0))
    attack_range_m = float(params.get("attack_range_m", 3000.0))
    tree = bot.get("ai_tree") or {}
    bt_has_attack = _bt_has_state(tree, "ATTACK")
    bt_has_approach = _bt_has_state(tree, "APPROACH")
    if dist_m < eval_range_m and bot.get("last_detected_ids"):
        if dist_m < attack_range_m and bt_has_attack:
            bb["state"] = "ATTACK"
            bb["t_enter"] = now
            logging.info(f"[bt-fsm] {bot['id']} STALK → ATTACK (dist={dist_m:.0f}m)")
            return Status.SUCCESS
        elif dist_m >= attack_range_m and bt_has_approach:
            bb["state"] = "APPROACH"
            bb["t_enter"] = now
            logging.info(f"[bt-fsm] {bot['id']} STALK → APPROACH (dist={dist_m:.0f}m)")
            return Status.SUCCESS
    # Continuer à se rapprocher (mise à jour cible si position fraîche).
    if bot.get("last_detected_ids") and last:
        target = {"x": last["x"], "z": last["z"]}
    return _drive_to_waypoint(bot, ctx, target, params)


@register_action("eval_situation")
def act_eval_situation(ctx, params):
    """EVAL : évalue la situation tactique et décide de la transition.
    - Ennemi toujours audible et < attack_range_m → set_state ATTACK
    - Ennemi toujours audible et < approach_range_m → set_state APPROACH
    - Contact perdu depuis > lost_timeout_s → set_state SEARCH
    - Sinon → reste en STALK (retourne FAILURE pour que le Selector essaie STALK)
    """
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    last = bb.get("last_enemy_pos")
    if not last:
        bb["state"] = "SEARCH"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} EVAL → SEARCH (pas d'ennemi)")
        return Status.SUCCESS
    age_s = now - last.get("t", 0)
    lost_timeout_s = float(params.get("lost_timeout_s", 30.0))
    if age_s > lost_timeout_s:
        bb["state"] = "SEARCH"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} EVAL → SEARCH (contact perdu depuis {age_s:.0f}s)")
        return Status.SUCCESS
    # Distance actuelle à la dernière position connue.
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    dist_m = math.hypot(last["x"] - bx, last["z"] - bz) * UNIT_METERS_BOT
    attack_range_m = float(params.get("attack_range_m", 3000.0))
    approach_range_m = float(params.get("approach_range_m", 6000.0))
    if dist_m < attack_range_m and bot.get("last_detected_ids"):
        bb["state"] = "ATTACK"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} EVAL → ATTACK (dist={dist_m:.0f}m)")
        return Status.SUCCESS
    if dist_m < approach_range_m and bot.get("last_detected_ids"):
        bb["state"] = "APPROACH"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} EVAL → APPROACH (dist={dist_m:.0f}m)")
        return Status.SUCCESS
    # Encore audible mais trop loin → reste en STALK (continuer à se rapprocher).
    if bot.get("last_detected_ids"):
        bb["state"] = "STALK"
        bb["t_enter"] = now
        return Status.SUCCESS
    # Plus audible mais pas encore timeout → reste en STALK vers dernière position.
    bb["state"] = "STALK"
    return Status.SUCCESS


@register_action("submerge_random")
def act_submerge_random(ctx, params):
    """Sub uniquement : plongée aléatoire à profondeur entre `min_depth_m`
    (défaut 20m) et `max_depth_m` (défaut 100m). Change de profondeur toutes
    les `hold_s` secondes (défaut 60s). Si `need_surface_for_drones` est
    actif, force la remontée à la surface."""
    bot = ctx["bot"]
    if bot.get("boatType") != "submarine":
        return Status.SUCCESS
    UNIT_METERS_BOT = ctx["deps"]["UNIT_METERS_BOT"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    if bb.get("need_surface_for_drones"):
        flotation_m = (bot.get("boat") or {}).get("flotation", 2)
        bot["depth_target_y"] = -flotation_m / UNIT_METERS_BOT
        bot["next_depth_change_at"] = now + 5.0
    elif now >= bot.get("next_depth_change_at", 0):
        min_d = float(params.get("min_depth_m", 20.0))
        max_d = float(params.get("max_depth_m", 100.0))
        max_allowed = bot.get("max_depth_m", 200) * 0.9
        max_d = min(max_d, max_allowed)
        depth_m = random.uniform(min_d, max_d)
        bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
        bot["next_depth_change_at"] = now + float(params.get("hold_s", 60.0))
    dy = bot["depth_target_y"] - bot["position"]["y"]
    rate = float(params.get("rate_u_s", 0.5)) * ctx["dt"]
    if abs(dy) < rate:
        bot["position"]["y"] = bot["depth_target_y"]
    else:
        bot["position"]["y"] += math.copysign(rate, dy)
    return Status.SUCCESS


@register_action("submerge_periscope")
def act_submerge_periscope(ctx, params):
    """Sub uniquement : pose la profondeur cible à ~5 m (immersion périscopique)
    et applique le mouvement vertical à `rate_u_s` u/s (défaut 0.5).
    Si bb['need_surface_for_drones'] est vrai, force la profondeur cible à la
    surface à la place (utile pour SEARCH : remonter pour lancer les drones).
    Si enemy_aware est actif, reste à 50-80m au lieu de remonter.
    Bypass le cycle aléatoire via next_depth_change_at."""
    bot = ctx["bot"]
    if bot.get("boatType") != "submarine":
        return Status.SUCCESS
    UNIT_METERS_BOT = ctx["deps"]["UNIT_METERS_BOT"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    if bb.get("need_surface_for_drones"):
        flotation_m = (bot.get("boat") or {}).get("flotation", 2)
        bot["depth_target_y"] = -flotation_m / UNIT_METERS_BOT
    elif now < bb.get("enemy_aware_until", 0):
        aware_depth_m = float(params.get("aware_depth_m", 60.0))
        max_depth_m = bot.get("max_depth_m", 200) * 0.7
        depth_m = min(aware_depth_m, max_depth_m)
        bot["depth_target_y"] = -depth_m / UNIT_METERS_BOT
    else:
        bot["depth_target_y"] = -5.0 / UNIT_METERS_BOT
    bot["next_depth_change_at"] = now + float(params.get("hold_s", 30.0))
    dy = bot["depth_target_y"] - bot["position"]["y"]
    rate = float(params.get("rate_u_s", 0.5)) * ctx["dt"]
    if abs(dy) < rate:
        bot["position"]["y"] = bot["depth_target_y"]
    else:
        bot["position"]["y"] += math.copysign(rate, dy)
    return Status.SUCCESS


@register_action("launch_auto_drones")
def act_launch_auto_drones(ctx, params):
    """Lance jusqu'à `n` drones automatiques (défaut 2) en respectant les munitions
    et les contraintes d'immersion (sub doit être en surface ou périscope).
    Espacés dans le temps via bb['next_auto_drone_at']."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    if now < bb.get("next_auto_drone_at", 0):
        return Status.FAILURE
    deps = ctx["deps"]
    sid = bot["sid"]
    pid = bot["id"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    # Compte combien de mes drones automatiques sont déjà en l'air.
    drones_server = deps["drones_server"]
    in_flight = sum(1 for k, d in drones_server.items()
                    if k[0] == pid and d["kind"] == "automatic" and not d.get("returning"))
    n_target = int(params.get("n", 2))
    if in_flight >= n_target:
        bb["need_surface_for_drones"] = False
        return Status.SUCCESS
    # Munitions ?
    ammo = deps.get("drone_ammo", {}).get(sid, {}) or {}
    if ammo.get("automatic", 0) <= 0:
        bb["need_surface_for_drones"] = False
        return Status.FAILURE
    # Sub trop profond → demander à submerge_periscope de remonter, attendre.
    if bot.get("boatType") == "submarine":
        boat = bot.get("boat") or {}
        flotation_m = boat.get("flotation", 2)
        surface_y = -flotation_m / UNIT_METERS_BOT
        if bot["position"]["y"] < surface_y - 0.05:
            bb["need_surface_for_drones"] = True
            return Status.FAILURE
    bb["need_surface_for_drones"] = False
    player_dict = deps["players"].get(sid)
    if not player_dict:
        return Status.FAILURE
    deps["spawn_drone"](sid, player_dict, {"kind": "automatic"})
    bb["next_auto_drone_at"] = now + float(params.get("interval_s", 8.0))
    logging.info(f"[bt-search] {pid} lance drone automatique")
    return Status.SUCCESS


def _nav_graph_adjacency(world):
    """Construit (et cache sur le world) la liste d'adjacence du nav_graph
    et le mapping node_idx → island_idx."""
    ng = world.get("nav_graph")
    if not ng:
        return None, None
    cache = world.get("_nav_adj_cache")
    if cache and cache["nodes"] is ng.get("nodes"):
        return cache["adj"], cache["node_to_island"]
    adj = {i: [] for i in range(len(ng.get("nodes") or []))}
    for a, b in ng.get("edges") or []:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    node_to_island = {}
    for ii, idxs in enumerate(ng.get("island_nodes") or []):
        for ni in idxs:
            node_to_island[ni] = ii
    world["_nav_adj_cache"] = {
        "nodes": ng.get("nodes"),
        "adj": adj,
        "node_to_island": node_to_island,
    }
    return adj, node_to_island


def _bfs_path(adj, nodes, start, goal, los_fn=None, world=None):
    """BFS sur le nav_graph entre `start` et `goal`. Retourne la liste de
    nœuds [start, ..., goal] ou None si pas de chemin. On enrichit l'adjacence
    avec les arêtes "LOS clear" inter-nœuds (sauts directs en mer ouverte)
    si los_fn et world sont fournis. Le chemin retourné est ensuite raccourci
    par "string pulling" : on saute les nœuds intermédiaires inutiles si
    deux nœuds non adjacents dans la séquence sont en LOS directe."""
    if start == goal:
        return [start]
    from collections import deque
    parent = {start: None}
    q = deque([start])
    found = False
    while q:
        n = q.popleft()
        if n == goal:
            found = True
            break
        # Voisins du graphe.
        for nb in adj.get(n, []):
            if nb not in parent:
                parent[nb] = n
                q.append(nb)
        # Voisins par LOS (sauts inter-îles à courte distance).
        if los_fn and world and nodes:
            nx, nz = nodes[n]["x"], nodes[n]["z"]
            # Limite : ne tester que les 30 nœuds les plus proches pour le coût.
            cands = sorted(range(len(nodes)),
                           key=lambda i: (nodes[i]["x"] - nx) ** 2 + (nodes[i]["z"] - nz) ** 2)[:30]
            for nb in cands:
                if nb in parent or nb == n:
                    continue
                if los_fn(nx, nz, nodes[nb]["x"], nodes[nb]["z"], world):
                    parent[nb] = n
                    q.append(nb)
    if not found:
        return None
    # Reconstitue le chemin brut.
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    # String pulling : tente de raccourcir en sautant les nœuds intermédiaires
    # quand un saut plus loin est en LOS directe.
    if los_fn and world and len(path) > 2:
        smoothed = [path[0]]
        i = 0
        while i < len(path) - 1:
            j = len(path) - 1
            # Cherche le j le plus loin tel que LOS clear depuis path[i].
            while j > i + 1:
                a = path[i]
                b = path[j]
                if los_fn(nodes[a]["x"], nodes[a]["z"],
                          nodes[b]["x"], nodes[b]["z"], world):
                    break
                j -= 1
            smoothed.append(path[j])
            i = j
        path = smoothed
    return path


def _midpoint_offset_outward(node_a, node_b, adj, nodes, point_on_any_island,
                              world, offset_u=25.0):
    """Retourne le point médian entre deux nœuds adjacents du périmètre,
    décalé vers l'extérieur de l'île. Direction extérieure = perpendiculaire
    au segment AB, du côté opposé au reste de l'île (testé via le centre
    moyen des autres voisins).
    """
    a = nodes[node_a]
    b = nodes[node_b]
    mx = (a["x"] + b["x"]) / 2.0
    mz = (a["z"] + b["z"]) / 2.0
    sx = b["x"] - a["x"]
    sz = b["z"] - a["z"]
    seg_len = math.hypot(sx, sz) or 1.0
    # Deux normales au segment (perpendiculaires unitaires).
    nx1 = -sz / seg_len
    nz1 = sx / seg_len
    # Pour choisir le côté extérieur : on regarde vers où pointent les autres
    # voisins de l'île (somme des vecteurs depuis A vers les voisins != B et
    # depuis B vers les voisins != A). L'extérieur est le côté opposé.
    inner_x = 0.0
    inner_z = 0.0
    for nd_idx, other in ((node_a, node_b), (node_b, node_a)):
        for nb in adj.get(nd_idx, []):
            if nb == other:
                continue
            inner_x += nodes[nb]["x"] - nodes[nd_idx]["x"]
            inner_z += nodes[nb]["z"] - nodes[nd_idx]["z"]
    if math.hypot(inner_x, inner_z) > 1e-3:
        # Si la normale1 va dans le sens de inner → on prend l'opposée.
        if nx1 * inner_x + nz1 * inner_z > 0:
            nx1 = -nx1
            nz1 = -nz1
    # Essai dégressif si on tombe sur une île.
    for f in (1.0, 0.7, 0.5, 0.3, 0.1):
        ox = mx + nx1 * offset_u * f
        oz = mz + nz1 * offset_u * f
        if not point_on_any_island(ox, oz, world):
            return {"x": ox, "z": oz}
    return {"x": mx, "z": mz}


def _node_offset_outward(node_idx, adj, nodes, point_on_any_island, world,
                        offset_u=8.0):
    """Retourne un point décalé de offset_u à l'extérieur de l'île au niveau
    du nœud `node_idx`. Direction : opposée à la moyenne des vecteurs vers
    les voisins. Si le décalage tombe sur une île, on réduit l'offset.
    """
    n = nodes[node_idx]
    nbs = [nb for nb in adj.get(node_idx, [])]
    if not nbs:
        return {"x": n["x"], "z": n["z"]}
    # Direction vers les voisins, normalisée → on prendra l'opposée.
    sx = sz = 0.0
    for nb in nbs:
        dx = nodes[nb]["x"] - n["x"]
        dz = nodes[nb]["z"] - n["z"]
        d = math.hypot(dx, dz) or 1.0
        sx += dx / d
        sz += dz / d
    m = math.hypot(sx, sz)
    if m < 1e-3:
        return {"x": n["x"], "z": n["z"]}
    # Vecteur extérieur unitaire.
    ext_x = -sx / m
    ext_z = -sz / m
    # Essaie offset_u, puis dégressif si en île.
    for f in (1.0, 0.7, 0.5, 0.3, 0.1):
        ox = n["x"] + ext_x * offset_u * f
        oz = n["z"] + ext_z * offset_u * f
        if not point_on_any_island(ox, oz, world):
            return {"x": ox, "z": oz}
    return {"x": n["x"], "z": n["z"]}


@register_action("navigate_island_hop")
def act_navigate_island_hop(ctx, params):
    """Exploration par saut d'île en île avec suivi du périmètre.

    Algorithme :
    1. Calcul d'une direction agrégée (somme pondérée 1/d² vers nœuds non-vus).
    2. Le bot navigue vers le nœud cible le plus proche du point d'impact.
    3. Une fois arrivé, il passe en mode "suivi périmètre" : suit les nœuds de
       l'île courante pour la moitié du périmètre (N/2 nœuds).
    4. Après la demi-boucle, recalcul de direction vers une nouvelle île.
    5. Si la direction pointe dans l'île, choisit au hasard un nœud du
       périmètre ayant LOS vers une autre île.

    Si pingé par sonar → arrêt immédiat (STALK).
    """
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    world = ctx["world"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]

    pinged_at = bb.get("pinged_at")
    now = ctx["now"]
    if pinged_at is not None and (now - pinged_at) < 10.0:
        bb.pop("pinged_at", None)
        bb["state"] = "STALK"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} SEARCH → STALK (pingé par sonar)")
        return Status.SUCCESS

    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    arrive_radius_u = float(params.get("arrive_radius_m", 50.0)) / UNIT_METERS_BOT
    bb["_last_now"] = ctx["now"]

    ng = world.get("nav_graph")
    nodes = (ng or {}).get("nodes") or []
    island_nodes_list = (ng or {}).get("island_nodes") or []
    adj, node_to_island = (_nav_graph_adjacency(world) if ng else (None, None))
    if not nodes or not adj:
        ahead = 1000.0 / UNIT_METERS_BOT
        target = {
            "x": bx - math.cos(bot["rotation"]) * ahead,
            "z": bz + math.sin(bot["rotation"]) * ahead,
        }
        return _drive_to_waypoint(bot, ctx, target, params)

    # --- Signal de fuite (mine détectée ou ping de balise) ---
    flee = bb.pop("_flee_from", None)
    bb.pop("_flee_at", None)
    if flee is not None:
        fx, fz = flee
        flee_node = _pick_flee_target(bx, bz, fx, fz, nodes, world, deps)
        if flee_node is not None:
            bb["nav_node"] = flee_node
            bb["nav_prev_node"] = None
            bb["nav_island"] = node_to_island.get(flee_node)
            bb["nav_mode"] = "goto"
            bb["nav_perim_remaining"] = 0
            bb["_ref_wp_dist"] = None
            bb["_ref_wp_t"] = 0
            bb["_stuck_ticks"] = 0
            bb["_orbit_ticks"] = 0
            bb["_orbit_last_dist"] = -1
            logging.info(f"[bt-search] {bot['id']} fuite vers nœud #{flee_node} "
                         f"(danger en {fx:.0f},{fz:.0f})")

    # --- Initialisation : nœud le plus proche (en respectant les bans) ---
    cur = bb.get("nav_node")
    if cur is None or cur >= len(nodes):
        banned = set(bb.get("nav_banned_nodes") or [])
        now_t = ctx.get("now", 0)
        # Expiration des bans (60 s).
        if banned and now_t > bb.get("nav_banned_until", 0):
            banned = set()
            bb["nav_banned_nodes"] = []
        candidates = [i for i in range(len(nodes)) if i not in banned]
        if not candidates:
            # Tous les nœuds bannis → forcer le dé-ban.
            banned = set()
            bb["nav_banned_nodes"] = []
            candidates = list(range(len(nodes)))
        best = min(candidates,
                   key=lambda i: (nodes[i]["x"] - bx) ** 2 + (nodes[i]["z"] - bz) ** 2)
        bb["nav_node"] = best
        bb["nav_prev_node"] = None
        bb["nav_island"] = node_to_island.get(best)
        bb["nav_mode"] = "goto"  # modes: goto, perimeter
        bb["nav_perim_remaining"] = 0
        cur = best
        logging.info(f"[bt-search] {bot['id']} démarre nav au nœud #{cur} (île #{bb['nav_island']})")

    target = nodes[cur]
    dx = target["x"] - bx
    dz = target["z"] - bz
    dist_to_target_u = math.hypot(dx, dz)

    # Log périodique.
    if ctx["now"] - bb.get("_log_at", 0) > 5.0:
        bb["_log_at"] = ctx["now"]
        mode = bb.get("nav_mode", "goto")
        perim = bb.get("nav_perim_remaining", 0)
        logging.info(
            f"[bt-search] {bot['id']} pos=({bx:.0f},{bz:.0f}) → nœud #{cur} "
            f"dist={dist_to_target_u*UNIT_METERS_BOT:.0f}m mode={mode} perim_left={perim} "
            f"speed={bot['speed']:.3f}"
        )

    # Détection d'orbite (incapacité à atteindre le nœud exact).
    ORBIT_RADIUS_U = 200.0 / UNIT_METERS_BOT
    is_close_orbiting = (dist_to_target_u < ORBIT_RADIUS_U
                         and abs(bot.get("speed", 0)) < bot["max_speed_us"] * 0.5)
    if is_close_orbiting:
        last_dist = bb.get("_orbit_last_dist", -1)
        ticks = bb.get("_orbit_ticks", 0)
        if last_dist > 0 and abs(dist_to_target_u - last_dist) * UNIT_METERS_BOT < 20.0:
            ticks += 1
        else:
            ticks = 0
        bb["_orbit_last_dist"] = dist_to_target_u
        bb["_orbit_ticks"] = ticks
        if ticks > 60:
            bb["_orbit_ticks"] = 0
            bb["_orbit_last_dist"] = -1
            logging.info(f"[bt-search] {bot['id']} orbite nœud #{cur} → considéré atteint")
            dist_to_target_u = 0
    else:
        bb["_orbit_ticks"] = 0
        bb["_orbit_last_dist"] = -1

    # --- Arrivée au nœud courant ---
    if dist_to_target_u < arrive_radius_u:
        _update_vision_coverage(bb, bx, bz, nodes, world, deps)
        prev_target = cur
        mode = bb.get("nav_mode", "goto")
        was_goto = (mode == "goto")
        was_perim_done = False

        if mode == "goto":
            # Vient d'atteindre la cible direction → passer en mode périmètre.
            island_idx = node_to_island.get(cur)
            if island_idx is not None and island_idx < len(island_nodes_list):
                island_nds = island_nodes_list[island_idx]
                half_perim = max(1, len(island_nds) // 2)
            else:
                half_perim = 3
            bb["nav_mode"] = "perimeter"
            bb["nav_perim_remaining"] = half_perim
            bb["nav_prev_node"] = cur
            logging.info(f"[bt-search] {bot['id']} atteint cible → mode périmètre "
                         f"(île #{island_idx}, {half_perim} segments)")
            # Premier nœud du périmètre = 2ème point du segment d'intersection
            # (mémorisé dans nav_perim_after par _pick_direction_target).
            next_node = bb.pop("nav_perim_after", None)
            if next_node is None or next_node not in adj.get(cur, []):
                # Sinon fallback : voisin sur la même île.
                next_node = _pick_perimeter_next(cur, bb, adj, node_to_island, nodes)
            if next_node is not None:
                bb["nav_node"] = next_node
                bb["nav_perim_remaining"] -= 1
            else:
                # Île à 1 nœud ou pas de voisin : relance direction.
                bb["nav_mode"] = "goto"
                goal = _pick_direction_target(cur, bb, adj, node_to_island,
                                             nodes, island_nodes_list, bx, bz,
                                             world, deps)
                if goal is not None:
                    bb["nav_node"] = goal

        elif mode == "perimeter":
            remaining = bb.get("nav_perim_remaining", 0)
            if remaining > 0:
                # Continuer le suivi du périmètre.
                next_node = _pick_perimeter_next(cur, bb, adj, node_to_island, nodes)
                if next_node is not None:
                    bb["nav_prev_node"] = cur
                    bb["nav_node"] = next_node
                    bb["nav_perim_remaining"] = remaining - 1
                else:
                    bb["nav_mode"] = "goto"
                    bb["nav_perim_remaining"] = 0
            else:
                # Demi-périmètre terminé : recalcul de direction.
                was_perim_done = True
                bb["nav_mode"] = "goto"
                goal = _pick_direction_target(cur, bb, adj, node_to_island,
                                             nodes, island_nodes_list, bx, bz,
                                             world, deps)
                if goal is not None:
                    bb["nav_prev_node"] = cur
                    bb["nav_node"] = goal
                    logging.info(f"[bt-search] {bot['id']} fin périmètre → "
                                 f"nouvelle cible #{goal} (île #{node_to_island.get(goal)})")

        # Si la cible a changé : reset les compteurs de progression. Sinon le
        # gros saut de distance vers le nouveau waypoint déclencherait à tort
        # _stuck_ticks → reset nav infini.
        if bb.get("nav_node") != prev_target:
            bb["_ref_wp_dist"] = None
            bb["_ref_wp_t"] = 0
            bb["_stuck_ticks"] = 0
            bb["_orbit_ticks"] = 0
            bb["_orbit_last_dist"] = -1
            # "Yvan le fou" : sub uniquement, à la sortie de périmètre vers
            # une nouvelle île (transition perimeter → goto), on programme un
            # scan 360° à exécuter une fois que le sub aura parcouru ~300m
            # depuis le départ de l'île (le temps de s'éloigner du contour).
            if (bot.get("boatType") == "submarine"
                    and was_perim_done
                    and bb.get("_yvan_until", 0) <= ctx["now"]):
                bb["_yvan_pending_from"] = (bx, bz)
                bb["_yvan_pending_dist_u"] = 30.0  # 300m
                logging.info(f"[bt-search] {bot['id']} yvan programmé après 300m")

    # Phase "Yvan le fou" en cours : ignore le waypoint, tourne sur place.
    if (bot.get("boatType") == "submarine"
            and bb.get("_yvan_until", 0) > ctx["now"]):
        return _yvan_le_fou(bot, ctx)

    # Yvan programmé : déclenche dès que le sub a parcouru `dist_u` depuis
    # le point de départ enregistré, ET que l'espace autour est dégagé.
    pending_from = bb.get("_yvan_pending_from")
    if pending_from is not None and bot.get("boatType") == "submarine":
        dist_traveled_u = math.hypot(bx - pending_from[0], bz - pending_from[1])
        if dist_traveled_u >= bb.get("_yvan_pending_dist_u", 30.0):
            # Vérifie l'espace libre autour : rayon de virage ~1m + marge 20%,
            # arrondi à 5u (50m) pour tenir compte de la dérive.
            point_on_any_island = deps.get("point_on_any_island")
            safety_u = 5.0
            free = True
            if point_on_any_island is not None:
                # Échantillonne 8 points sur le cercle de rayon safety_u.
                for k in range(8):
                    a = (k / 8.0) * 2.0 * math.pi
                    px = bx + safety_u * math.cos(a)
                    pz = bz + safety_u * math.sin(a)
                    if point_on_any_island(px, pz, world):
                        free = False
                        break
            if free:
                bb["_yvan_until"] = ctx["now"] + 6.0
                bb.pop("_yvan_pending_from", None)
                bb.pop("_yvan_pending_dist_u", None)
                logging.info(f"[bt-search] {bot['id']} yvan le fou (360° scan)")
                return _yvan_le_fou(bot, ctx)
            else:
                # Pas assez d'espace : annule le yvan pending, on reprendra
                # éventuellement à la prochaine transition d'île.
                bb.pop("_yvan_pending_from", None)
                bb.pop("_yvan_pending_dist_u", None)
                logging.info(f"[bt-search] {bot['id']} yvan annulé (espace insuffisant)")

    # Cible = directement le nœud.
    target = nodes[bb["nav_node"]]
    return _drive_to_waypoint(bot, ctx, target, params)


def _yvan_le_fou(bot, ctx):
    """Rotation 360° sur place : le sub tourne très lentement pour minimiser
    son rayon de virage et balayer en ~6s avec son sonar passif directionnel."""
    dt = ctx["dt"]
    bb = bot.setdefault("bb", {})
    # Vitesse très réduite : 5% du max → rayon de virage tout petit.
    target_speed = bot["max_speed_us"] * 0.05
    tstep = bot["throttle_accel"] * dt
    if abs(bot["speed"] - target_speed) < tstep:
        bot["speed"] = target_speed
    else:
        bot["speed"] += math.copysign(tstep, target_speed - bot["speed"])
    # Rudder à fond pour pivoter sur place.
    bot["rudder"] = bot["rudder_max"]
    speed = bot["speed"]
    speed_ratio = min(1.0, abs(speed) / max(0.001, bot["max_speed_us"] * 0.5))
    bot["rotation"] += bot["rudder"] * speed_ratio * (1 if speed >= 0 else -1) * dt
    nx = bot["position"]["x"] - math.cos(bot["rotation"]) * speed * dt
    nz = bot["position"]["z"] + math.sin(bot["rotation"]) * speed * dt
    world = ctx["world"]
    half_w = world["ground"]["width"] / 2 - 4.0
    half_d = world["ground"]["depth"] / 2 - 4.0
    if -half_w <= nx <= half_w and -half_d <= nz <= half_d:
        bot["position"]["x"] = nx
        bot["position"]["z"] = nz
    # Pendant le yvan, on neutralise les compteurs de "coincé" (sinon le
    # tour sur place déclenche stuck → reset nav).
    bb["_stuck_ticks"] = 0
    bb["_ref_wp_dist"] = None
    bb["_ref_wp_t"] = ctx["now"]
    bb["_ref_wp_key"] = None
    return Status.SUCCESS


def _pick_perimeter_next(cur, bb, adj, node_to_island, nodes):
    """Choisit le prochain nœud du périmètre de l'île courante.
    Préfère un voisin non encore visité récemment, en continuant dans le
    même sens de rotation (éloigné du prev_node)."""
    cur_island = node_to_island.get(cur)
    prev_node = bb.get("nav_prev_node")
    neighbors = adj.get(cur, [])
    same_island = [n for n in neighbors if node_to_island.get(n) == cur_island]
    if not same_island:
        return None
    # Préférer le voisin qui n'est pas le prev (continue dans le même sens).
    candidates = [n for n in same_island if n != prev_node]
    if not candidates:
        candidates = same_island
    # Parmi les candidats, prendre le plus éloigné du prev pour garder le sens.
    if prev_node is not None and prev_node < len(nodes):
        ref = nodes[prev_node]
        return max(candidates,
                   key=lambda n: (nodes[n]["x"] - ref["x"])**2 + (nodes[n]["z"] - ref["z"])**2)
    return candidates[0]


def _pick_flee_target(bx, bz, fx, fz, nodes, world, deps):
    """Choisit aléatoirement un nœud en LOS qui s'éloigne du danger (fx, fz).
    Critères : LOS clear depuis le bot, dans la carte, et à une distance du
    danger > distance bot-danger × 1.2. Renvoie l'index du nœud, ou None."""
    los_fn = (deps or {}).get("line_of_sight_clear")
    half_w = world["ground"]["width"] / 2 - 1.0
    half_d = world["ground"]["depth"] / 2 - 1.0
    bot_to_danger = math.hypot(bx - fx, bz - fz)
    min_safe_dist = bot_to_danger * 1.2
    candidates = []
    for ni, nd in enumerate(nodes):
        nx = nd["x"]; nz = nd["z"]
        if not (-half_w <= nx <= half_w and -half_d <= nz <= half_d):
            continue
        if math.hypot(nx - fx, nz - fz) < min_safe_dist:
            continue
        if los_fn is not None and not los_fn(bx, bz, nx, nz, world):
            continue
        candidates.append(ni)
    if not candidates:
        return None
    return random.choice(candidates)


def _ray_segment_intersection(ox, oz, dx, dz, ax, az, bx_, bz_):
    """Intersection entre une demi-droite (origine (ox,oz), direction unitaire
    (dx,dz), t≥0) et un segment AB. Retourne (t, ix, iz) ou None.
    """
    sx = bx_ - ax
    sz = bz_ - az
    # Résolution :
    #   ox + t·dx = ax + s·sx
    #   oz + t·dz = az + s·sz
    det = dx * (-sz) - dz * (-sx)  # = dz·sx - dx·sz
    if abs(det) < 1e-9:
        return None
    rhs1 = ax - ox
    rhs2 = az - oz
    t = (rhs1 * (-sz) - rhs2 * (-sx)) / det
    s = (dx * rhs2 - dz * rhs1) / det
    if t < 0 or s < -1e-6 or s > 1 + 1e-6:
        return None
    return t, ox + t * dx, oz + t * dz


def _pick_direction_target(cur, bb, adj, node_to_island, nodes,
                           island_nodes_list, bx, bz, world, deps):
    """Choisit un nœud cible selon l'algorithme :
    1. Direction = somme pondérée 1/d² des vecteurs vers les nœuds non-vus.
    2. Trouve le segment du nav_graph le plus proche intersecté par la
       demi-droite (bot, direction).
    3. LOS depuis le bot vers les 2 extrémités A, B du segment :
       - Aucune visible : choisit le nœud non-vu en LOS, le plus proche, qui
         n'appartient pas à l'île la plus proche du bot.
       - Une seule visible : ce point devient cible. L'autre point sera le
         départ du suivi périmètre.
       - Les deux visibles : le plus proche du point d'intersection est cible ;
         l'autre point sera le départ du périmètre.
    Renvoie le nœud cible (et stocke dans bb['nav_perim_after'] le 2ème point
    du segment, qui guidera le suivi périmètre après l'arrivée).
    """
    bb.pop("nav_perim_after", None)  # reset par défaut
    seen = set(bb.get("nav_seen_nodes") or [])
    los_fn = deps.get("line_of_sight_clear") if deps else None
    cur_island = node_to_island.get(cur)

    half_w = world["ground"]["width"] / 2 - 1.0
    half_d = world["ground"]["depth"] / 2 - 1.0

    all_unseen = [ni for ni in range(len(nodes))
                  if ni not in seen and ni != cur
                  and -half_w <= nodes[ni]["x"] <= half_w
                  and -half_d <= nodes[ni]["z"] <= half_d]
    if not all_unseen:
        return None

    # 1) Direction agrégée pondérée 1/d² sur tous les non-vus (depuis bot).
    sum_x = 0.0
    sum_z = 0.0
    for ni in all_unseen:
        ndx = nodes[ni]["x"] - bx
        ndz = nodes[ni]["z"] - bz
        dist = math.hypot(ndx, ndz)
        if dist < 1e-3:
            continue
        w = 1.0 / (dist * dist)
        sum_x += (ndx / dist) * w
        sum_z += (ndz / dist) * w
    mag = math.hypot(sum_x, sum_z)
    if mag < 1e-6:
        return random.choice(all_unseen)
    dir_x = sum_x / mag
    dir_z = sum_z / mag

    # 2) Segment du nav_graph le plus proche intersecté par la demi-droite.
    # On EXCLUT les segments de l'île courante : on cherche à atteindre une
    # AUTRE île à la fin de chaque demi-périmètre.
    edges = (world.get("nav_graph") or {}).get("edges") or []
    best_t = float("inf")
    best_seg = None  # (a, b, ix, iz)
    for (a, b) in edges:
        if a >= len(nodes) or b >= len(nodes):
            continue
        if (node_to_island.get(a) == cur_island
                and node_to_island.get(b) == cur_island):
            continue
        ax, az = nodes[a]["x"], nodes[a]["z"]
        bx_, bz_ = nodes[b]["x"], nodes[b]["z"]
        hit = _ray_segment_intersection(bx, bz, dir_x, dir_z, ax, az, bx_, bz_)
        if hit is None:
            continue
        t, ix, iz = hit
        if t < best_t:
            best_t = t
            best_seg = (a, b, ix, iz)

    # 3) Choix selon LOS aux extrémités du segment trouvé.
    if best_seg is not None and los_fn is not None:
        a, b, ix, iz = best_seg
        ax, az = nodes[a]["x"], nodes[a]["z"]
        bx_, bz_ = nodes[b]["x"], nodes[b]["z"]
        los_a = los_fn(bx, bz, ax, az, world)
        los_b = los_fn(bx, bz, bx_, bz_, world)

        if los_a and los_b:
            # Cible = extrémité la plus proche du point d'intersection.
            da = math.hypot(ax - ix, az - iz)
            db = math.hypot(bx_ - ix, bz_ - iz)
            if da <= db:
                target, other = a, b
            else:
                target, other = b, a
            bb["nav_perim_after"] = other
            bb["nav_island"] = node_to_island.get(target)
            logging.info(f"[bt-search] direction → segment ({a},{b}), "
                         f"cible #{target} (LOS A+B), périmètre via #{other}")
            return target
        elif los_a:
            bb["nav_perim_after"] = b
            bb["nav_island"] = node_to_island.get(a)
            logging.info(f"[bt-search] direction → segment ({a},{b}), "
                         f"cible #{a} (LOS A seul), périmètre via #{b}")
            return a
        elif los_b:
            bb["nav_perim_after"] = a
            bb["nav_island"] = node_to_island.get(b)
            logging.info(f"[bt-search] direction → segment ({a},{b}), "
                         f"cible #{b} (LOS B seul), périmètre via #{a}")
            return b
        # else : aucune extrémité en LOS → fallback ci-dessous.

    # Fallback : aucun segment intersecté en LOS.
    # Trouve l'île la plus proche du bot = île dont le nœud le plus proche du
    # bot a la plus petite distance.
    nearest_island = None
    nearest_d2 = float("inf")
    for ni, nd in enumerate(nodes):
        d2 = (nd["x"] - bx) ** 2 + (nd["z"] - bz) ** 2
        if d2 < nearest_d2:
            nearest_d2 = d2
            nearest_island = node_to_island.get(ni)
    # Choisir le nœud non-vu en LOS, le plus proche, hors île la plus proche.
    candidates = []
    for ni in all_unseen:
        if node_to_island.get(ni) == nearest_island:
            continue
        if los_fn is not None and not los_fn(bx, bz,
                                              nodes[ni]["x"], nodes[ni]["z"],
                                              world):
            continue
        d2 = (nodes[ni]["x"] - bx) ** 2 + (nodes[ni]["z"] - bz) ** 2
        candidates.append((d2, ni))
    if candidates:
        candidates.sort()
        target = candidates[0][1]
        bb["nav_island"] = node_to_island.get(target)
        logging.info(f"[bt-search] fallback → nœud LOS le plus proche #{target} "
                     f"(île proche #{nearest_island} exclue)")
        return target
    # Ultime recours : nœud non-vu le plus proche du bot.
    target = min(all_unseen,
                 key=lambda ni: (nodes[ni]["x"] - bx) ** 2 + (nodes[ni]["z"] - bz) ** 2)
    bb["nav_island"] = node_to_island.get(target)
    logging.info(f"[bt-search] fallback ultime → nœud non-vu le plus proche #{target}")
    return target


def _bt_has_state(node, state_name):
    """Vérifie récursivement si le BT contient une Condition state_is(name)."""
    if node is None:
        return False
    if isinstance(node, Condition) and node.fn_name == "state_is" and node.params.get("name") == state_name:
        return True
    for child in getattr(node, "children", None) or []:
        if _bt_has_state(child, state_name):
            return True
    child = getattr(node, "child", None)
    if child and _bt_has_state(child, state_name):
        return True
    return False


def _update_vision_coverage(bb, bx, bz, nodes, world, deps):
    """Marque comme 'vus' tous les nœuds du graphe en LOS depuis (bx, bz).
    Utilise bb['nav_seen_nodes'] (set d'indices). Reset à 80% de couverture
    des nœuds intra-carte (pour éviter de tourner en rond sur les derniers
    nœuds inaccessibles).
    Les nœuds hors carte sont marqués comme déjà vus dès l'init : ils ne sont
    jamais atteignables physiquement par le bot, on les exclut du calcul."""
    seen = set(bb.get("nav_seen_nodes") or [])
    los_fn = deps.get("line_of_sight_clear") if deps else None
    if not los_fn or not world:
        return seen
    half_w = world["ground"]["width"] / 2 - 1.0
    half_d = world["ground"]["depth"] / 2 - 1.0
    # Liste des nœuds intra-carte (= ceux qui doivent réellement être vus).
    in_map_idxs = [i for i, nd in enumerate(nodes)
                   if -half_w <= nd["x"] <= half_w and -half_d <= nd["z"] <= half_d]
    n_in_map = len(in_map_idxs)
    # Marque les nœuds hors carte comme déjà vus (jamais atteignables).
    def _mark_oob(s):
        for i, nd in enumerate(nodes):
            if not (-half_w <= nd["x"] <= half_w and -half_d <= nd["z"] <= half_d):
                s.add(i)
        return s
    if not bb.get("_oob_nodes_marked"):
        seen = _mark_oob(seen)
        bb["_oob_nodes_marked"] = True
    for i, nd in enumerate(nodes):
        if i in seen:
            continue
        if los_fn(bx, bz, nd["x"], nd["z"], world):
            seen.add(i)
    # Reset à 80% des nœuds intra-carte vus (≈ couverture suffisante).
    seen_in_map = sum(1 for i in in_map_idxs if i in seen)
    if n_in_map > 0 and seen_in_map >= 0.8 * n_in_map:
        logging.info(f"[bt-search] couverture {seen_in_map}/{n_in_map} ≥ 80% → reset")
        # Reset mais on remarque immédiatement les hors-carte pour qu'ils
        # restent exclus du calcul de direction.
        seen = _mark_oob(set())
        # Reset aussi les nœuds bannis : sinon ils restent exclus alors que
        # la nouvelle phase d'exploration peut vouloir les revisiter.
        bb["nav_banned_nodes"] = []
        bb["nav_banned_until"] = 0
    bb["nav_seen_nodes"] = list(seen)
    return seen




def _point_in_polygon(px, pz, poly):
    """Test ray-casting standard. poly = liste de dicts {x, z}."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, zi = poly[i]["x"], poly[i]["z"]
        xj, zj = poly[j]["x"], poly[j]["z"]
        if ((zi > pz) != (zj > pz)) and (
            px < (xj - xi) * (pz - zi) / (zj - zi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _ensure_path_polygons(world):
    """Construit (et cache) la liste des polygones formés par les nœuds de
    path autour de chaque île. Indice = numéro d'île, valeur = liste ordonnée
    de dicts {x, z} qui forment le polygone du path. Retourne aussi la liste
    plate des nœuds par île pour le fallback "nœud le plus proche"."""
    cache = world.get("_path_polys_cache")
    ng = world.get("nav_graph") or {}
    nodes = ng.get("nodes") or []
    island_nodes = ng.get("island_nodes") or []
    if cache and cache.get("nodes_id") is id(nodes):
        return cache["polys"], cache["island_nodes_xz"]
    # Pour chaque île, on a les indices des nœuds. On ordonne en chaîne via
    # l'adjacence (anneau autour de l'île).
    edges = ng.get("edges") or []
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    polys = []
    island_nodes_xz = []
    for ins in island_nodes:
        if not ins:
            polys.append([])
            island_nodes_xz.append([])
            continue
        # Parcours en chaîne : démarre au premier, suit les voisins en évitant
        # le précédent. Si l'anneau n'est pas connexe, on prend ce qu'on peut.
        ordered = []
        node_set = set(ins)
        visited = set()
        cur = ins[0]
        prev = None
        while cur not in visited:
            visited.add(cur)
            ordered.append(cur)
            # Voisin sur la même île, différent du prev.
            nxt = None
            for nb in adj.get(cur, []):
                if nb in node_set and nb != prev:
                    nxt = nb
                    break
            if nxt is None:
                break
            prev = cur
            cur = nxt
        # Si tous les nœuds n'ont pas été parcourus (anneau cassé), ajouter
        # les manquants en fin (pour garder la couverture du polygone).
        for ni in ins:
            if ni not in visited:
                ordered.append(ni)
        poly = [{"x": nodes[i]["x"], "z": nodes[i]["z"]} for i in ordered]
        polys.append(poly)
        island_nodes_xz.append([(nodes[i]["x"], nodes[i]["z"], i) for i in ins])
    world["_path_polys_cache"] = {
        "nodes_id": id(nodes),
        "polys": polys,
        "island_nodes_xz": island_nodes_xz,
    }
    return polys, island_nodes_xz


def _redirect_if_inside_path(bx, bz, world, target_node_idx=None,
                              point_on_any_island=None, banned_nodes=None):
    """Si (bx, bz) est sur une vraie île (selon le contour du world data),
    retourne le nœud du nav_graph le plus proche du bot pour sortir vers la
    mer. Sinon None.

    On utilise point_on_any_island plutôt que le polygone reconstruit des
    nœuds : ce dernier peut avoir des artefacts pour les îles non convexes
    et déclencher à tort sur des points en eau.

    Respecte la liste banned_nodes pour ne pas renvoyer un nœud déjà banni
    (boucle infinie sinon). Vérifie aussi que le milieu du segment bot→nœud
    est hors île (évite de cibler un nœud de l'autre côté de l'île)."""
    if point_on_any_island is None or not point_on_any_island(bx, bz, world):
        return None
    banned = set(banned_nodes or [])
    ng = world.get("nav_graph") or {}
    nodes = ng.get("nodes") or []
    TOO_CLOSE_U = 2.0
    best = None
    best_d2 = float("inf")
    for ni, n in enumerate(nodes):
        if ni in banned:
            continue
        d2 = (n["x"] - bx) ** 2 + (n["z"] - bz) ** 2
        if d2 < TOO_CLOSE_U * TOO_CLOSE_U:
            continue
        # Vérifier que le milieu du segment bot→nœud est hors île (évite
        # de cibler un nœud de l'autre côté de l'île traversée).
        mx = (bx + n["x"]) * 0.5
        mz = (bz + n["z"]) * 0.5
        if point_on_any_island(mx, mz, world):
            continue
        if d2 < best_d2:
            best_d2 = d2
            best = (n["x"], n["z"], ni)
    # Fallback : si tous les nœuds proches sont bannis ou traversent l'île,
    # essayer sans le filtre mid-point mais toujours avec ban.
    if best is None:
        for ni, n in enumerate(nodes):
            if ni in banned:
                continue
            d2 = (n["x"] - bx) ** 2 + (n["z"] - bz) ** 2
            if d2 < TOO_CLOSE_U * TOO_CLOSE_U:
                continue
            if d2 < best_d2:
                best_d2 = d2
                best = (n["x"], n["z"], ni)
    if best is not None:
        return {"x": best[0], "z": best[1], "_node_idx": best[2]}
    return None


def _drive_to_waypoint(bot, ctx, wp, params):
    """Pilotage commun (rudder + speed) vers un waypoint donné.
    Par défaut reste sous le seuil bruyant (speedNoiseLimit - noise_margin).
    Si params['full_speed'] est vrai, utilise la vitesse max.

    Garde-fou anti-île : si le bot se trouve à l'intérieur du polygone de
    path d'une île (pas le contour de l'île, le périmètre des nœuds), on
    remplace le waypoint par le nœud du périmètre le plus proche pour le
    faire sortir. Actif dans tous les modes (SEARCH, RETREAT, EVADE, etc.).
    """
    deps = ctx["deps"]
    dt = ctx["dt"]
    world = ctx["world"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    boat = bot.get("boat") or {}
    if params.get("full_speed"):
        cruise_target = bot["max_speed_us"]
    else:
        noise_limit = float(boat.get("speedNoiseLimit", 0.5))
        noise_margin = float(params.get("noise_margin", 0.05))
        quiet_ratio = max(0.1, noise_limit - noise_margin)
        cruise_target = bot["max_speed_us"] * quiet_ratio
    bx_pos = bot["position"]["x"]
    bz_pos = bot["position"]["z"]
    # Recherche d'un nœud cible (si le caller a passé un nœud de nav_graph,
    # on tente de retrouver son indice pour ne pas se dévier soi-même).
    target_node_idx = wp.get("_node_idx") if isinstance(wp, dict) else None
    bb_pre = bot.get("bb") or {}
    if target_node_idx is None:
        target_node_idx = bb_pre.get("nav_node")
    bb_local2 = bot.setdefault("bb", {})
    redirect = _redirect_if_inside_path(
        bx_pos, bz_pos, world, target_node_idx,
        point_on_any_island=deps.get("point_on_any_island"),
        banned_nodes=bb_local2.get("nav_banned_nodes"))
    if redirect is not None:
        # Force la cible nav vers le nœud du redirect : ça change
        # permanemment la trajectoire au lieu d'osciller entre l'ancienne
        # cible et le nœud de sortie. Le BT reprendra son fonctionnement
        # normal une fois ce nœud atteint.
        new_target = redirect.get("_node_idx")
        if new_target is not None and bb_local2.get("nav_node") != new_target:
            bb_local2["nav_node"] = new_target
            bb_local2["nav_mode"] = "goto"
            bb_local2["nav_perim_remaining"] = 0
            # Reset compteurs de progression (changement de cible).
            bb_local2["_ref_wp_dist"] = None
            bb_local2["_ref_wp_t"] = ctx.get("now", 0)
            bb_local2["_ref_wp_key"] = None
            bb_local2["_stuck_ticks"] = 0
            bb_local2["_orbit_ticks"] = 0
            bb_local2["_orbit_last_dist"] = -1
            last_log = bb_local2.get("_inside_path_log_at", 0)
            now_t = ctx.get("now", 0)
            if now_t - last_log > 2.0:
                bb_local2["_inside_path_log_at"] = now_t
                logging.info(f"[bt-coll] {bot['id']} sur île → cible forcée nœud "
                             f"#{new_target}")
        wp = redirect
    bot["waypoint"] = wp
    dx = wp["x"] - bot["position"]["x"]
    dz = wp["z"] - bot["position"]["z"]
    want_heading = math.atan2(dz, -dx)
    hd = ((want_heading - bot["rotation"]) + math.pi * 3) % (math.pi * 2) - math.pi
    # Gain agressif : sature le rudder dès ~7° d'erreur de cap pour braquer fort
    # à l'approche des coins. Sinon le sub coupe les angles.
    target_rudder = max(-bot["rudder_max"], min(bot["rudder_max"], hd * 5.0))
    step = bot["rudder_speed"] * dt
    if abs(target_rudder - bot["rudder"]) < step:
        bot["rudder"] = target_rudder
    else:
        bot["rudder"] += math.copysign(step, target_rudder - bot["rudder"])
    # Réduit la vitesse quand l'erreur de cap est grande : un U-turn à pleine
    # vitesse trace un grand cercle (rayon ~300m). En ralentissant à 30%
    # quand |hd| > 60°, le rayon de virage chute drastiquement → demi-tour
    # compact, pas d'effet "tour sur lui-même".
    abs_hd_deg = abs(hd) * 180.0 / math.pi
    if abs_hd_deg > 60.0:
        cruise_target = cruise_target * 0.3
    elif abs_hd_deg > 30.0:
        # Transition douce entre 30° et 60°.
        scale = 1.0 - (abs_hd_deg - 30.0) / 30.0 * 0.7  # 1.0 → 0.3
        cruise_target = cruise_target * scale
    tstep = bot["throttle_accel"] * dt
    if abs(bot["speed"] - cruise_target) < tstep:
        bot["speed"] = cruise_target
    else:
        bot["speed"] += math.copysign(tstep, cruise_target - bot["speed"])
    # Avancee physique bornee par le segment exact, sans repulsion ni teleportation.
    speed = bot["speed"]
    speed_ratio = min(1.0, abs(speed) / max(0.001, bot["max_speed_us"] * 0.5))
    bot["rotation"] += bot["rudder"] * speed_ratio * (1 if speed >= 0 else -1) * dt
    nx = bot["position"]["x"] - math.cos(bot["rotation"]) * speed * dt
    nz = bot["position"]["z"] + math.sin(bot["rotation"]) * speed * dt
    bb_local = bot.setdefault("bb", {})
    # Bord du monde et iles : aucun franchissement, meme sur un grand pas.
    half_w = world["ground"]["width"] / 2 - 4.0
    half_d = world["ground"]["depth"] / 2 - 4.0
    out_of_bounds = (nx < -half_w or nx > half_w or nz < -half_d or nz > half_d)
    if (not out_of_bounds
            and not geometry.point_on_any_island(nx, nz, world)
            and geometry.line_of_sight_clear(bx_pos, bz_pos, nx, nz, world)):
        bot["position"]["x"] = nx
        bot["position"]["z"] = nz
        # Détection de non-progression : on compare la distance actuelle au
        # waypoint à une distance de référence prise toutes les 3 secondes.
        # Si le bot n'a pas progressé d'au moins 5m sur cet intervalle, on
        # considère qu'il piétine. Robuste aux virages lents où il avance à
        # ~0.5m/tick (= 10m/3s, marge confortable).
        cur_wp_dist = math.hypot(wp["x"] - nx, wp["z"] - nz)
        # Reset du suivi si le waypoint a changé (redirect, changement cible,
        # action différente). Sinon ref_dist correspondrait à l'ancien wp et
        # le bot serait à tort considéré comme bloqué.
        wp_key = (round(wp["x"], 1), round(wp["z"], 1))
        last_wp_key = bb_local.get("_ref_wp_key")
        if wp_key != last_wp_key:
            bb_local["_ref_wp_dist"] = cur_wp_dist
            bb_local["_ref_wp_t"] = ctx["now"]
            bb_local["_ref_wp_key"] = wp_key
        else:
            ref_dist = bb_local.get("_ref_wp_dist")
            ref_t = bb_local.get("_ref_wp_t", 0)
            now_t = ctx["now"]
            if ref_dist is None or (now_t - ref_t) > 3.0:
                if ref_dist is not None:
                    progress_m = (ref_dist - cur_wp_dist) * UNIT_METERS_BOT
                    if progress_m < 5.0:
                        bb_local["_stuck_ticks"] = bb_local.get("_stuck_ticks", 0) + 60
                    else:
                        bb_local["_stuck_ticks"] = max(0, bb_local.get("_stuck_ticks", 0) - 30)
                bb_local["_ref_wp_dist"] = cur_wp_dist
                bb_local["_ref_wp_t"] = now_t
    else:
        # Collision : arret, avec le suivi de blocage existant conserve.
        bot["speed"] = 0.0
        bb_local["_stuck_ticks"] = bb_local.get("_stuck_ticks", 0) + 2
    if bb_local.get("_stuck_ticks", 0) > 100:
        # Ban temporaire de la cible courante : sinon le bot recalcule la même
        # direction et reprend la même cible → boucle infinie de reset.
        banned = set(bb_local.get("nav_banned_nodes") or [])
        if bb_local.get("nav_node") is not None:
            banned.add(bb_local["nav_node"])
        bb_local["nav_banned_nodes"] = list(banned)
        bb_local["nav_banned_until"] = ctx["now"] + 60.0  # 60s ban
        bb_local["nav_node"] = None
        bb_local["nav_prev_node"] = None
        bb_local["nav_mode"] = "goto"
        bb_local["nav_perim_remaining"] = 0
        bb_local["_stuck_ticks"] = 0
        bb_local["_ref_wp_dist"] = None
        bb_local["_ref_wp_t"] = 0
        # Force aussi un nouveau waypoint en effaçant celui en cours.
        bot["waypoint"] = None
        logging.info(f"[bt-search] {bot['id']} reset nav (coincé > 5s, banni #{list(banned)[-1] if banned else '?'})")
    if bot["boatType"] == "submarine" and "depth_target_y" in bot:
        dy = bot["depth_target_y"] - bot["position"]["y"]
        rate = 0.5 * dt
        if abs(dy) < rate:
            bot["position"]["y"] = bot["depth_target_y"]
        else:
            bot["position"]["y"] += math.copysign(rate, dy)
    return Status.SUCCESS


# ============================================================
# FSM combat simplifiée : COMBAT (defense/attaque) > SEARCH
# ============================================================

def _torpedoes_in_los_5km(bot, deps):
    """Activite radar dans 5 km, thermoclines incluses, sans critere CPA."""
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    torpedoes = deps.get("torpedoes_server") or {}
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    R_U = 5000.0 / UNIT_METERS_BOT
    R_U2 = R_U * R_U
    out = []
    for t in torpedoes.values():
        # Inclut les torpilles propres si elles restent visibles.
        tx = t["x"]
        tz = t["z"]
        d2 = (tx - bx) ** 2 + (tz - bz) ** 2
        if d2 > R_U2:
            continue
        if not simulation.torpedo_radar_visible(bot, t, ctx_world(bot)):
            continue
        out.append(t)
    return out


def ctx_world(bot):
    """Helper : récupère world_data depuis le bot (stocké lors du tick)."""
    return bot.get("_ctx_world")


@register_condition("combat_active")
def cond_combat_active(ctx, params):
    """Vrai si une torpille (propre incluse) est visible au radar dans 5 km."""
    bot = ctx["bot"]
    bot["_ctx_world"] = ctx["world"]
    return bool(_torpedoes_in_los_5km(bot, ctx["deps"]))


def _bot_threats(bot, deps):
    """Memes menaces radar/CPA que les conditions BT et le RL."""
    return deps["bot_torpedoes_threat"](bot)


def _i_have_torpedo_in_flight(bot, deps):
    """Vrai si une de mes torpilles est encore vivante (= 'j'ai tiré dans la session')."""
    bot_id = bot.get("id")
    torpedoes = deps.get("torpedoes_server") or {}
    return any(t.get("ownerPlayerId") == bot_id for t in torpedoes.values())


def _find_attacker_player(threat_torpedo, deps, bot, now):
    """L'identite du tireur ne revele pas sa position actuelle."""
    owner_id = threat_torpedo.get("ownerPlayerId")
    if owner_id is None:
        return None
    for p in _known_targets(bot, now, 30.0):
        if p["id"] == owner_id:
            return p
    return None


def _fire_best_torpedo(bot, target_player, deps, dist_m):
    """Tire la meilleure torpille disponible :
    - autonome (radar) si stock dispo : précise, activation adaptative
    - sinon acoustique (suit le bruit) : portée 20km
    Retourne True si tirée."""
    sid = bot["sid"]
    ammo_dict = deps.get("torpedo_ammo") or {}
    ammo = ammo_dict.get(sid) or {}
    # Autonome en priorité.
    if ammo.get("autonomous", 0) > 0:
        if dist_m >= 1000.0:
            activation_m = 500.0
        else:
            activation_m = 200.0
        return deps["spawn_bot_torpedo_autonomous"](
            bot, target_player, activation_m=activation_m)
    # Sinon acoustique.
    if ammo.get("acoustic", 0) > 0:
        return deps["spawn_bot_torpedo"](bot, target_player)
    return False


@register_action("combat_react")
def act_combat_react(ctx, params):
    """Action unique gérant DEFENSE et ATTAQUE selon contexte.

    DEFENSE (declenche par une menace radar, CPA <= 200 m sur 10 s) :
    - Largue 1 leurre.
    - Si je n'ai PAS de torpille en vol : contre-attaque (1 torpille sur
      l'ennemi qui m'a tiré, devenu visible).
    - Cap à 90° par rapport au vecteur vitesse de la torpille (côté
      éloignant des leurres déjà lâchés).
    - Si nouvelle torpille apparaît plus tard : recalcule le cap (90° de la
      nouvelle, en évitant les leurres).

    ATTAQUE (pas de menace, mais condition d'attaque réunie : ennemi connu
             en LOS et pas de torpille à moi en vol) :
    - Tire 1 torpille.
    - Speed = 0, attend.

    Hors combat : ne fait rien (FAILURE → bascule sur SEARCH).
    """
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    deps = ctx["deps"]
    now = ctx["now"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]

    threats = _bot_threats(bot, deps)
    have_torp = _i_have_torpedo_in_flight(bot, deps)
    combat = bb.setdefault("_combat", {})
    lure_positions = combat.setdefault("lure_positions", [])
    last_threat_tids = set(combat.get("threat_tids") or [])

    # ----- Mode DEFENSE -----
    if threats:
        # Identifie nouvelles torpilles (non encore traitées).
        new_threats = [t for t in threats if t.get("tid") not in last_threat_tids]
        cur_threat_tids = set(t.get("tid") for t in threats)
        # Cas particulier : nouvelle menace OU pas encore initialisé → recalcul cap.
        if new_threats or "flee_cap" not in combat:
            primary = min(threats, key=lambda t: math.hypot(
                t["x"] - bot["position"]["x"], t["z"] - bot["position"]["z"]))
            dirX = primary.get("dirX", 0)
            dirZ = primary.get("dirZ", 0)
            # Deux perpendiculaires unitaires.
            mag = math.hypot(dirX, dirZ) or 1.0
            dirX /= mag
            dirZ /= mag
            perp_a = (-dirZ, dirX)
            perp_b = (dirZ, -dirX)
            bx = bot["position"]["x"]
            bz = bot["position"]["z"]
            # Choix : on minimise la "proximité aux leurres lâchés".
            def _score(perp):
                dx, dz = perp
                # On simule un point à 800m dans cette direction.
                fx = bx + dx * 80.0
                fz = bz + dz * 80.0
                # Pénalité = somme inverse distance² aux leurres.
                penalty = 0.0
                for (lx, lz) in lure_positions:
                    d2 = (fx - lx) ** 2 + (fz - lz) ** 2
                    if d2 < 1.0:
                        d2 = 1.0
                    penalty += 1.0 / d2
                return penalty
            best = perp_a if _score(perp_a) <= _score(perp_b) else perp_b
            combat["flee_cap"] = best
            combat["last_threat_recalc_at"] = now
            logging.info(f"[bt-combat] {bot['id']} DEFENSE → cap 90° {best}, "
                         f"{len(new_threats)} nouvelle(s) menace(s)")
            # Largue 1 leurre par nouvelle menace (max 1 par 5s).
            last_lure = combat.get("last_lure_at", 0)
            if now - last_lure >= 5.0:
                if deps["bot_drop_lure"](bot):
                    combat["last_lure_at"] = now
                    bx_l = bot["position"]["x"]
                    bz_l = bot["position"]["z"]
                    lure_positions.append((bx_l, bz_l))
                    logging.info(f"[bt-combat] {bot['id']} largue leurre")
            # Contre-attaque si pas tiré dans la session.
            if not have_torp:
                attacker = _find_attacker_player(threats[0], deps, bot, now)
                if attacker is not None:
                    bx_b = bot["position"]["x"]
                    bz_b = bot["position"]["z"]
                    ex_a = attacker["position"]["x"]
                    ez_a = attacker["position"]["z"]
                    cur_dist_m_d = math.hypot(ex_a - bx_b, ez_a - bz_b) * UNIT_METERS_BOT
                    if cur_dist_m_d >= 500.0:
                        fired = _fire_best_torpedo(bot, attacker, deps, cur_dist_m_d)
                        if fired:
                            bot["next_torpedo_at"] = now + 8.0
                            logging.info(f"[bt-combat] {bot['id']} contre-attaque "
                                         f"sur ennemi {attacker.get('id')} "
                                         f"(à {cur_dist_m_d:.0f}m)")

        combat["threat_tids"] = list(cur_threat_tids)
        # Pilotage : cap à 90° (waypoint à 800m dans la direction).
        flee_cap = combat["flee_cap"]
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        wp = {"x": bx + flee_cap[0] * 80.0, "z": bz + flee_cap[1] * 80.0}
        # Plein gaz.
        params2 = dict(params)
        params2["full_speed"] = True
        return _drive_to_waypoint(bot, ctx, wp, params2)

    # Plus de menace.
    # ----- Mode ATTAQUE -----
    # Conditions : ennemi connu en LOS, à portée de tir, distance min de
    # sécurité respectée, et je n'ai pas déjà une torpille en vol.
    # Distance d'activation adaptative :
    #   - cible ≥ 1000m : activation 500m (défaut)
    #   - cible 500-1000m : activation 200m (laisse moins de temps mais évite l'auto-tir)
    #   - cible < 500m : pas de tir (auto-torpillage probable).
    last_enemy = bb.get("last_enemy_pos")
    enemy_recent = (last_enemy is not None
                    and (now - (last_enemy.get("t", 0))) < 30.0)
    attack_range_m = float(params.get("attack_range_m", 3000.0))
    cur_dist_m = last_enemy.get("dist_m", 99999) if last_enemy else 99999
    in_range = (enemy_recent
                and cur_dist_m <= attack_range_m
                and cur_dist_m >= 500.0)
    if in_range and not have_torp:
        attacker = next(iter(_known_targets(bot, now, 30.0)), None)
        if attacker is not None and now >= bot.get("next_torpedo_at", 0):
            aim = attacker["position"]
            aim_dist_m = math.hypot(aim["x"] - bot["position"]["x"],
                                    aim["z"] - bot["position"]["z"]) * deps["UNIT_METERS_BOT"]
            fired = _fire_best_torpedo(bot, attacker, deps, aim_dist_m)
            if fired:
                bot["next_torpedo_at"] = now + 8.0
                logging.info(f"[bt-combat] {bot['id']} ATTAQUE sur ennemi "
                             f"{attacker.get('id')} (initiative, à {cur_dist_m:.0f}m)")
                combat["attack_at"] = now

    # Si on a une torpille en vol, on s'arrête et on observe.
    if have_torp:
        bot["speed"] = 0.0
        bot["rudder"] = 0.0
        return Status.SUCCESS

    # Pas de torpille en vol : on peut re-tirer la prochaine fois (efface
    # le marker attack_at qui ne sert qu'à figer pendant le tir).
    combat.pop("attack_at", None)

    # Pas de menace, pas d'opportunité de tir → FAILURE pour que le selector
    # passe au noeud suivant (combat_approach ou search).
    return Status.FAILURE


@register_action("combat_approach")
def act_combat_approach(ctx, params):
    """Approche l'ennemi connu sans être en combat actif.

    Sub : silencieux (sous le seuil de bruit). Si la trajectoire de l'ennemi
          va l'amener dans `attack_range_m` dans les 30s, on reste vitesse 0
          et on attend ; sinon on se met en approche silencieuse vers la
          dernière position connue.
    Destroyer : plein gaz, vise la dernière position connue (le sonar ping
                est géré dans son BT, branche dédiée).

    Renvoie FAILURE si pas d'ennemi connu (→ bascule sur SEARCH).
    """
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    now = ctx["now"]

    last_enemy = bb.get("last_enemy_pos")
    if last_enemy is None or (now - last_enemy.get("t", 0)) > 30.0:
        return Status.FAILURE

    # Si le bot n'a plus de torpilles utilisables, abandonner l'approche
    # (sinon il reste figé à portée). Renvoie FAILURE → bascule vers SEARCH.
    sid = bot["sid"]
    ammo_dict = deps.get("torpedo_ammo") or {}
    ammo = ammo_dict.get(sid) or {}
    if ammo.get("autonomous", 0) <= 0 and ammo.get("acoustic", 0) <= 0:
        if now - bb.get("_approach_log_at", 0) > 5.0:
            bb["_approach_log_at"] = now
            logging.info(f"[bt-approach] {bot['id']} stock vide → abandonne approche")
        return Status.FAILURE

    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    ex = last_enemy["x"]
    ez = last_enemy["z"]
    dist_u = math.hypot(ex - bx, ez - bz)
    dist_m = dist_u * UNIT_METERS_BOT
    attack_range_m = float(params.get("attack_range_m", 3000.0))
    is_sub = bot.get("boatType") == "submarine"

    # Si on est trop près (zone dangereuse pour ses propres torpilles),
    # s'éloigner jusqu'à au moins min_fire_dist_m.
    min_fire_dist_m = float(params.get("min_fire_dist_m", 800.0))
    if dist_m < min_fire_dist_m:
        # Cap opposé à l'ennemi.
        dx = bot["position"]["x"] - ex
        dz = bot["position"]["z"] - ez
        d = math.hypot(dx, dz) or 1.0
        away_x = dx / d
        away_z = dz / d
        wp = {"x": bot["position"]["x"] + away_x * 80.0,
              "z": bot["position"]["z"] + away_z * 80.0}
        params2 = dict(params)
        params2["full_speed"] = True
        if now - bb.get("_approach_log_at", 0) > 5.0:
            bb["_approach_log_at"] = now
            logging.info(f"[bt-approach] {bot['id']} trop près ({dist_m:.0f}m) → éloigne")
        return _drive_to_waypoint(bot, ctx, wp, params2)

    # Si on est à portée d'attaque (entre min_fire et attack_range), on s'arrête.
    if dist_m <= attack_range_m:
        bot["speed"] = 0.0
        bot["rudder"] = 0.0
        return Status.SUCCESS

    # --- Sub : nuance "attendre que l'ennemi vienne" ---
    if is_sub:
        # Estimation trajectoire ennemi : on a sa pos + un timestamp ancien.
        # Si on a 2 positions successives (séparées de >2s), on calcule sa
        # vitesse et on prédit s'il va entrer dans attack_range dans 30s.
        prev_enemy = bb.get("_prev_enemy_pos")
        if prev_enemy and last_enemy.get("t", 0) - prev_enemy.get("t", 0) > 2.0:
            dt_e = last_enemy["t"] - prev_enemy["t"]
            vx = (last_enemy["x"] - prev_enemy["x"]) / dt_e
            vz = (last_enemy["z"] - prev_enemy["z"]) / dt_e
            # Position ennemie dans 30 s.
            pred_x = ex + vx * 30.0
            pred_z = ez + vz * 30.0
            pred_dist_m = math.hypot(pred_x - bx, pred_z - bz) * UNIT_METERS_BOT
            if pred_dist_m <= attack_range_m:
                # L'ennemi vient à nous → on attend vitesse 0.
                bot["speed"] = 0.0
                bot["rudder"] = 0.0
                if now - bb.get("_approach_log_at", 0) > 5.0:
                    bb["_approach_log_at"] = now
                    logging.info(f"[bt-approach] {bot['id']} attend vitesse 0 "
                                 f"(ennemi à {dist_m:.0f}m, prédit à {pred_dist_m:.0f}m dans 30s)")
                return Status.SUCCESS
        # Mémorise la position courante pour calculer la vitesse au prochain tick.
        # On ne stocke que si la position a changé (sinon dt=0).
        if prev_enemy is None or prev_enemy.get("t") != last_enemy.get("t"):
            bb["_prev_enemy_pos"] = dict(last_enemy)

    # --- Approche active ---
    wp = {"x": ex, "z": ez}
    params2 = dict(params)
    if is_sub:
        # Silencieux : noise_margin par défaut (~quiet_ratio).
        params2["full_speed"] = False
        params2["noise_margin"] = float(params.get("noise_margin", 0.05))
    else:
        # Destroyer : plein gaz.
        params2["full_speed"] = True
    if now - bb.get("_approach_log_at", 0) > 5.0:
        bb["_approach_log_at"] = now
        logging.info(f"[bt-approach] {bot['id']} approche ennemi à {dist_m:.0f}m "
                     f"(silencieux={is_sub})")
    return _drive_to_waypoint(bot, ctx, wp, params2)


@register_condition("combat_should_continue")
def cond_combat_should_continue(ctx, params):
    """Reste en combat tant qu'une torpille est visible au radar dans 5 km."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    bot["_ctx_world"] = ctx["world"]
    if _torpedoes_in_los_5km(bot, ctx["deps"]):
        return True
    # Reset combat state si plus de torpille.
    bb.pop("_combat", None)
    return False


def _pick_cover_node(bot, world, enemy, deps):
    """Choisit le nœud de couvert optimal pour se cacher du destroyer.
    Priorité 1 : nœud visible par le bot ET caché du dest, le plus proche.
    Priorité 2 : nœud caché du dest, le plus proche (même sans LOS bot)."""
    ng = world.get("nav_graph")
    if not ng:
        return None
    nodes = ng.get("nodes") or []
    if not nodes:
        return None
    los_fn = deps.get("line_of_sight_clear")
    if los_fn is None:
        return None
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    ex = enemy["x"]
    ez = enemy["z"]

    visible_and_hidden = []
    hidden_only = []
    for i, nd in enumerate(nodes):
        nx, nz = nd["x"], nd["z"]
        hidden_from_enemy = not los_fn(nx, nz, ex, ez, world)
        if not hidden_from_enemy:
            continue
        d2 = (nx - bx) ** 2 + (nz - bz) ** 2
        visible_from_bot = los_fn(bx, bz, nx, nz, world)
        if visible_from_bot:
            visible_and_hidden.append((d2, i))
        hidden_only.append((d2, i))

    logging.info(f"[bt-cover] bot=({bx:.0f},{bz:.0f}) enemy=({ex:.0f},{ez:.0f}) "
                 f"vis+hid={len(visible_and_hidden)} hid_only={len(hidden_only)}")
    hidden_only.sort()
    for d2, i in hidden_only[:8]:
        nd = nodes[i]
        vis = (d2, i) in visible_and_hidden or any(j == i for _, j in visible_and_hidden)
        logging.info(f"[bt-cover]   #{i:2d} ({nd['x']:7.1f},{nd['z']:7.1f}) "
                     f"d={math.sqrt(d2)*deps['UNIT_METERS_BOT']:.0f}m vis_bot={'Y' if vis else 'N'}")

    if visible_and_hidden:
        visible_and_hidden.sort()
        _, idx = visible_and_hidden[0]
        nd = nodes[idx]
        logging.info(f"[bt-cover] → nœud #{idx} ({nd['x']:.0f},{nd['z']:.0f}) "
                     f"visible+caché, dist={math.sqrt(visible_and_hidden[0][0])*deps['UNIT_METERS_BOT']:.0f}m")
        return idx
    if hidden_only:
        _, idx = hidden_only[0]
        nd = nodes[idx]
        logging.info(f"[bt-cover] → nœud #{idx} ({nd['x']:.0f},{nd['z']:.0f}) "
                     f"caché (pas de LOS bot), dist={math.sqrt(hidden_only[0][0])*deps['UNIT_METERS_BOT']:.0f}m")
        return idx
    logging.warning(f"[bt-cover] aucun nœud caché trouvé")
    return None


def _ring_path(island_nodes, start_idx, end_idx, nodes):
    """Calcule le chemin le plus court entre deux nœuds sur l'anneau d'une île.
    island_nodes = liste ordonnée des index de nœuds de l'île.
    Retourne la liste d'index du chemin (inclut start et end)."""
    if start_idx == end_idx:
        return [start_idx]
    try:
        pos_start = island_nodes.index(start_idx)
        pos_end = island_nodes.index(end_idx)
    except ValueError:
        return None
    n = len(island_nodes)
    # Chemin sens horaire (start → end en avançant dans la liste)
    if pos_end >= pos_start:
        path_cw = island_nodes[pos_start:pos_end + 1]
    else:
        path_cw = island_nodes[pos_start:] + island_nodes[:pos_end + 1]
    # Chemin sens anti-horaire (start → end en reculant dans la liste)
    if pos_start >= pos_end:
        path_ccw = island_nodes[pos_end:pos_start + 1][::-1]
    else:
        path_ccw = (island_nodes[pos_end:] + island_nodes[:pos_start + 1])[::-1]
    # Calculer les distances
    def path_length(path):
        total = 0.0
        for k in range(len(path) - 1):
            a, b = nodes[path[k]], nodes[path[k + 1]]
            total += math.hypot(a["x"] - b["x"], a["z"] - b["z"])
        return total
    dist_cw = path_length(path_cw)
    dist_ccw = path_length(path_ccw)
    chosen = path_cw if dist_cw <= dist_ccw else path_ccw
    logging.info(f"[bt-ring] P0=#{start_idx}→cible=#{end_idx} : "
                 f"cw={dist_cw:.0f}u ({len(path_cw)} nœuds) "
                 f"ccw={dist_ccw:.0f}u ({len(path_ccw)} nœuds) → {'CW' if dist_cw <= dist_ccw else 'CCW'}")
    return chosen


def _nearest_node(x, z, nodes):
    """Retourne l'index du nœud le plus proche de (x,z)."""
    best = 0
    best_d2 = float("inf")
    for i, nd in enumerate(nodes):
        d2 = (nd["x"] - x) ** 2 + (nd["z"] - z) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = i
    return best


@register_action("back_away_to_cover")
def act_back_away_to_cover(ctx, params):
    """STALK : recule à vitesse silencieuse vers le nœud nav_graph le plus
    proche caché de l'ennemi (LOS bloquée). Transitionne vers EVAL quand on
    arrive au couvert ou si aucun couvert trouvé.
    Si la LOS depuis le bot vers l'ennemi est déjà bloquée (on est déjà caché),
    transitionne immédiatement vers EVAL.
    """
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    deps = ctx["deps"]
    world = ctx["world"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    now = ctx["now"]

    last = bb.get("last_enemy_pos")
    if not last:
        bb["state"] = "SEARCH"
        bb["t_enter"] = now
        bb.pop("cover_node", None)
        logging.info(f"[bt-fsm] {bot['id']} STALK → SEARCH (pas d'ennemi connu)")
        return Status.SUCCESS

    # Si on est déjà hors LOS de l'ennemi → directement EVAL.
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    los_fn = deps.get("line_of_sight_clear")
    already_hidden = los_fn and not los_fn(bx, bz, last["x"], last["z"], world)
    if already_hidden:
        bb["state"] = "EVAL"
        bb["t_enter"] = now
        bb.pop("cover_node", None)
        logging.info(f"[bt-fsm] {bot['id']} STALK → EVAL (déjà caché)")
        return Status.SUCCESS

    # Timeout STALK : si on n'atteint pas le couvert en 30s, EVAL sur place.
    stalk_timeout_s = float(params.get("stalk_timeout_s", 30.0))
    if now - bb.get("t_enter", now) > stalk_timeout_s:
        bb["state"] = "EVAL"
        bb["t_enter"] = now
        bb.pop("cover_node", None)
        logging.info(f"[bt-fsm] {bot['id']} STALK → EVAL (timeout {stalk_timeout_s:.0f}s)")
        return Status.SUCCESS

    # Sélection / re-sélection du nœud de couvert (toutes les 3 s).
    cover_node = bb.get("cover_node")
    cover_chosen_at = bb.get("cover_chosen_at", 0)
    nodes = (world.get("nav_graph") or {}).get("nodes") or []
    if cover_node is None or cover_node >= len(nodes) or now - cover_chosen_at > 3.0:
        cover_node = _pick_cover_node(bot, world, last, deps)
        bb["cover_node"] = cover_node
        bb["cover_chosen_at"] = now
        if cover_node is not None:
            logging.info(f"[bt-stalk] {bot['id']} cherche couvert → nœud #{cover_node}")

    if cover_node is None:
        bb["state"] = "EVAL"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} STALK → EVAL (aucun couvert dispo)")
        return Status.SUCCESS

    target = nodes[cover_node]
    dist_u = math.hypot(target["x"] - bx, target["z"] - bz)
    arrive_radius_u = float(params.get("arrive_radius_m", 100.0)) / UNIT_METERS_BOT
    if dist_u < arrive_radius_u:
        bb["state"] = "EVAL"
        bb["t_enter"] = now
        bb.pop("cover_node", None)
        logging.info(f"[bt-fsm] {bot['id']} STALK → EVAL (couvert atteint nœud #{cover_node})")
        return Status.SUCCESS

    return _drive_to_waypoint(bot, ctx, target, params)


@register_action("wait_observe")
def act_wait_observe(ctx, params):
    """EVAL : freine doucement, reste sur place et observe pendant `secs`
    secondes. À la fin, écrit bb['state'] = `set_state_after` (défaut SEARCH).
    Le timer démarre à la première entrée dans l'action depuis le dernier
    set_state. Pendant l'attente, le bot ne tire pas (la branche DCA reste
    autorisée car elle est dans une autre partie du tree).
    Si pingé par sonar → tir diversion + RETREAT."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    dt = ctx["dt"]
    deps = ctx["deps"]
    secs = float(params.get("secs", 10.0))

    # Réaction ping sonar : découvert pendant l'observation → riposte + fuite.
    pinged_at = bb.get("pinged_at")
    if pinged_at is not None and (now - pinged_at) < 10.0:
        bb.pop("pinged_at", None)
        bb.pop("eval_until", None)
        bb.pop("eval_state_for", None)
        logging.info(f"[bt-fsm] {bot['id']} STALK → RETREAT (pingé par sonar, diversion)")
        fire = ACTIONS.get("fire_torpedo_at_audible")
        if fire and bot.get("last_detected_ids"):
            fire(ctx, params)
        bb["state"] = "RETREAT"
        bb["t_enter"] = now
        return Status.SUCCESS

    cur_state = bb.get("state")
    # Démarre/reset le timer si on entre dans cet état (ou après transition).
    if bb.get("eval_state_for") != cur_state:
        bb["eval_until"] = now + secs
        bb["eval_state_for"] = cur_state
        logging.info(f"[bt-eval] {bot['id']} commence observation {secs:.0f}s")

    # Freinage progressif : approche bot["speed"] vers 0.
    tstep = bot["throttle_accel"] * dt
    if abs(bot["speed"]) < tstep:
        bot["speed"] = 0
    else:
        bot["speed"] -= math.copysign(tstep, bot["speed"])
    # Rudder vers 0.
    rstep = bot["rudder_speed"] * dt
    if abs(bot["rudder"]) < rstep:
        bot["rudder"] = 0
    else:
        bot["rudder"] -= math.copysign(rstep, bot["rudder"])

    # Avance physique du résiduel de speed.
    speed = bot["speed"]
    if speed != 0:
        speed_ratio = min(1.0, abs(speed) / max(0.001, bot["max_speed_us"] * 0.5))
        bot["rotation"] += bot["rudder"] * speed_ratio * (1 if speed >= 0 else -1) * dt
        nx = bot["position"]["x"] - math.cos(bot["rotation"]) * speed * dt
        nz = bot["position"]["z"] + math.sin(bot["rotation"]) * speed * dt
        if not deps["point_on_any_island"](nx, nz, ctx["world"]):
            bot["position"]["x"] = nx
            bot["position"]["z"] = nz
        else:
            bot["speed"] = 0

    if now >= bb.get("eval_until", 0):
        # Décision après observation : ATTACK si à portée, sinon APPROACH,
        # sinon SEARCH (plus aucun ennemi mémorisé).
        last = bb.get("last_enemy_pos")
        clear_after_s = float(params.get("clear_after_s", 30.0))
        UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
        bx = bot["position"]["x"]
        bz = bot["position"]["z"]
        bt_has = lambda s: _bt_has_state(bot.get("ai_tree") or {}, s)
        if last and (now - last.get("t", 0)) < clear_after_s:
            dist_m = math.hypot(last["x"] - bx, last["z"] - bz) * UNIT_METERS_BOT
            attack_range_m = float(params.get("attack_range_m", 3000.0))
            if dist_m < attack_range_m and bt_has("ATTACK") and bot.get("last_detected_ids"):
                new_state = "ATTACK"
            elif bt_has("APPROACH"):
                new_state = "APPROACH"
            else:
                new_state = params.get("set_state_after", "SEARCH")
        else:
            new_state = params.get("set_state_after", "SEARCH")
        bb["state"] = new_state
        bb["t_enter"] = now
        bb.pop("eval_until", None)
        bb.pop("eval_state_for", None)
        logging.info(f"[bt-eval] {bot['id']} fin observation → {new_state}")
    return Status.SUCCESS


@register_action("engage_destroyer_runaway")
def act_engage_destroyer_runaway(ctx, params):
    """Spécifique destroyer vs destroyer : reste hors portée canon adverse en tirant.
    - Identifie le destroyer ennemi détecté le plus proche
    - Si pas de destroyer détecté → FAILURE (laisse passer la FSM)
    - Sinon : vise un waypoint à 1.2 × range canon adverse, dans la direction opposée
    - Tire au canon dès que cooldown OK et dans portée
    - Recule (waypoint derrière soi) si trop près
    """
    bot = ctx["bot"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    now = ctx["now"]

    # Cherche le destroyer ennemi détecté le plus proche, vivant.
    detected = bot.get("last_detected_ids") or set()
    if not detected:
        return Status.FAILURE
    target = None
    best_dist = float("inf")
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    for p in _known_targets(bot, now):
        if p.get("boatType") != "destroyer":
            continue
        if p.get("sunk") or p.get("integrity", 100) <= 0:
            continue
        pos = p.get("position") or {}
        d_u = math.hypot(pos.get("x", 0) - bx, pos.get("z", 0) - bz)
        if d_u < best_dist:
            best_dist = d_u
            target = p
    if target is None:
        return Status.FAILURE

    target_pos = target["position"]
    dx = target_pos["x"] - bx
    dz = target_pos["z"] - bz
    dist_u = math.hypot(dx, dz) or 0.001
    dist_m = dist_u * UNIT_METERS_BOT

    # Portée canon adverse : seuil au-delà duquel on est en sécurité.
    target_cannon = (target.get("boat") or {}).get("cannon") or {}
    enemy_range_m = float(target_cannon.get("range", 4000))
    safe_dist_m = enemy_range_m * 1.2  # 20% au-delà pour marge

    # Si on est déjà hors portée adverse, FAILURE → la FSM normale prend le relais.
    if dist_m > safe_dist_m:
        return Status.FAILURE

    # Mémorise la position ennemie pour que RETREAT puisse choisir le couvert.
    bb = bot.setdefault("bb", {})
    bb["last_enemy_pos"] = {
        "x": target_pos["x"], "y": target_pos["y"], "z": target_pos["z"],
        "id": target["id"], "dist_m": dist_m, "t": target["observed_at"],
        "target": target,
    }
    # Force le passage en RETREAT (cherche couvert derrière une île, full speed via JSON).
    if bb.get("state") != "RETREAT":
        # Cleanup pour permettre à retreat_to_cover de recalculer le chemin.
        for k in ("retreat_path", "retreat_enemy_ref", "cover_node"):
            bb.pop(k, None)
        bb["state"] = "RETREAT"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} → RETREAT (destroyer ennemi à {dist_m:.0f}m)")

    # Tir canon opportuniste pendant la fuite (en parallèle de RETREAT qui pilote).
    own_cannon = (bot.get("boat") or {}).get("cannon") or {}
    own_range_m = float(own_cannon.get("range", 4000))
    cooldown_s = float(params.get("cannon_cooldown_s", 3.0))
    if dist_m <= own_range_m and now >= bot.get("next_cannon_at", 0):
        if not deps["bots_passive_get"]() and own_cannon:
            if deps["bot_fire_cannon"](bot, target):
                bot["next_cannon_at"] = now + cooldown_s

    # On retourne FAILURE pour laisser la FSM exécuter la branche RETREAT (qui pilote).
    return Status.FAILURE


@register_action("approach_enemy")
def act_approach_enemy(ctx, params):
    """APPROACH : se rapproche de la dernière position connue de l'ennemi
    à vitesse silencieuse (le sub est furtif → aller directement vers la cible).
    Quand on arrive à portée d'attaque → ATTACK.
    Si pingé par sonar → tire 1-2 torpilles de diversion + RETREAT.
    Si le contact expire → SEARCH."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    deps = ctx["deps"]
    world = ctx["world"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    now = ctx["now"]

    # Détection ping sonar : on est découvert → tir de diversion + retraite.
    pinged_at = bb.get("pinged_at")
    if pinged_at is not None and (now - pinged_at) < 10.0:
        bb.pop("pinged_at", None)
        logging.info(f"[bt-fsm] {bot['id']} APPROACH → ATTACK (pingé par sonar, diversion)")
        fire = ACTIONS.get("fire_torpedo_at_audible")
        if fire:
            fire(ctx, params)
        bb["attack_shots"] = 1
        bb["state"] = "RETREAT"
        bb["t_enter"] = now
        return Status.SUCCESS

    last = bb.get("last_enemy_pos")
    clear_after_s = float(params.get("clear_after_s", 30.0))
    if not last or (now - last.get("t", 0)) > clear_after_s:
        bb["state"] = "SEARCH"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} APPROACH → SEARCH (contact perdu)")
        return Status.SUCCESS

    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    dist_to_enemy_m = math.hypot(last["x"] - bx, last["z"] - bz) * UNIT_METERS_BOT
    attack_range_m = float(params.get("attack_range_m", 3000.0))
    if dist_to_enemy_m < attack_range_m and bot.get("last_detected_ids"):
        bb["state"] = "ATTACK"
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} APPROACH → ATTACK (dist={dist_to_enemy_m:.0f}m)")
        return Status.SUCCESS

    # Si la cible se rapproche d'elle-même, rester immobile (aucun bruit émis).
    prev_dist = bb.get("_approach_prev_dist_m")
    bb["_approach_prev_dist_m"] = dist_to_enemy_m
    if prev_dist is not None and dist_to_enemy_m < prev_dist:
        # La cible converge — couper les moteurs et attendre.
        dt = ctx["dt"]
        tstep = bot["throttle_accel"] * dt
        if abs(bot["speed"]) < tstep:
            bot["speed"] = 0
        else:
            bot["speed"] -= math.copysign(tstep, bot["speed"])
        return Status.SUCCESS

    target = {"x": last["x"], "z": last["z"]}
    return _drive_to_waypoint(bot, ctx, target, params)


@register_action("attack_torpedo_at_known")
def act_attack_torpedo_at_known(ctx, params):
    """ATTACK : pattern tir-bouger-observer-retir avec torpilles autonomes.
    Sous-états internes (bb['_atk_phase']):
      'salvo'    → tire 2 torpilles autonomes (activation = dist - 200m)
      'relocate' → déplacement latéral silencieux, surveille acquisitions
      'observe'  → torpilles en acquisition → attend impact/perte
      'salvo2'   → retir 2 torpilles si acquisition perdue (max 4 total)
    Après salvo terminée ou 4 tirs → RETREAT.
    Garde-fou : ne s'approche pas à < 1500m d'un destroyer."""
    if ctx["deps"]["bots_passive_get"]():
        return Status.FAILURE
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    now = ctx["now"]
    deps = ctx["deps"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    bt_has = lambda s: _bt_has_state(bot.get("ai_tree") or {}, s)
    salvo_size = int(params.get("salvo_size", 2))
    max_total = int(params.get("max_torpedoes", 4))
    relocate_m = float(params.get("relocate_m", 250.0))
    min_dist_destroyer_m = float(params.get("min_dist_destroyer_m", 1500.0))
    cooldown_s = float(params.get("cooldown_s", 8.0))

    def _cleanup():
        for k in ("attack_shots", "_atk_phase", "_atk_reloc_target",
                  "_atk_torp_keys", "_atk_salvo_done"):
            bb.pop(k, None)

    def _end_attack(next_state, reason):
        _cleanup()
        bb["state"] = next_state
        bb["t_enter"] = now
        logging.info(f"[bt-fsm] {bot['id']} ATTACK → {next_state} ({reason})")
        return Status.SUCCESS

    # Un point memorise reste une solution de tir jusqu'a expiration.
    targets = list(_known_targets(bot, now, float(params.get("clear_after_s", 30.0))))
    if not targets:
        return _end_attack("SEARCH", "plus de cible")

    # Max total atteint → RETREAT.
    shots = bb.get("attack_shots", 0)
    if shots >= max_total:
        return _end_attack("RETREAT" if bt_has("RETREAT") else "STALK",
                           f"{shots} torpilles tirées, rompt le combat")

    # Trouver la cible la plus proche.
    target_player = None
    best_dist = float("inf")
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    for p in targets:
        pos = p.get("position") or {}
        d_u = math.hypot(pos.get("x", 0) - bx, pos.get("z", 0) - bz)
        if d_u < best_dist:
            best_dist = d_u
            target_player = p
    if target_player is None:
        return Status.SUCCESS

    dist_m = best_dist * UNIT_METERS_BOT

    # Garde-fou destroyer.
    target_boat = target_player.get("boat") or {}
    is_destroyer = target_boat.get("boatType") == "destroyer" or not target_boat.get("maxDepthMeters")
    if is_destroyer and dist_m < min_dist_destroyer_m:
        return _end_attack("RETREAT" if bt_has("RETREAT") else "STALK",
                           f"trop proche destroyer {dist_m:.0f}m")

    phase = bb.get("_atk_phase", "salvo")

    # --- Phase SALVO (tir de 2 torpilles) ---
    if phase == "salvo" or phase == "salvo2":
        # Cooldown entre tirs.
        if now < bot.get("next_torpedo_at", 0):
            dt = ctx["dt"]
            tstep = bot["throttle_accel"] * dt
            if abs(bot["speed"]) < tstep:
                bot["speed"] = 0
            else:
                bot["speed"] -= math.copysign(tstep, bot["speed"])
            return Status.SUCCESS

        # Combien de tirs dans cette salve.
        salvo_shots = bb.get("_atk_salvo_done", 0)
        if salvo_shots >= salvo_size:
            # Salve terminée. Décide retraite ou continuer en attaque.
            bb["_atk_salvo_done"] = 0
            retreat_proba = float(params.get("retreat_after_attack_proba", 0.0))
            if phase == "salvo":
                if retreat_proba > 0.0 and random.random() < retreat_proba:
                    # Tirage : on rompt le combat avant max_torpedoes.
                    return _end_attack("RETREAT" if bt_has("RETREAT") else "STALK",
                                       f"choix aléatoire RETREAT après {shots} tir(s)")
                # Sinon : relocalisation latérale puis re-attaque.
                ex = target_player["position"]["x"]
                ez = target_player["position"]["z"]
                dx, dz = ex - bx, ez - bz
                d = math.hypot(dx, dz) or 1.0
                perp_x, perp_z = -dz / d, dx / d
                if random.random() < 0.5:
                    perp_x, perp_z = -perp_x, -perp_z
                reloc_u = relocate_m / UNIT_METERS_BOT
                bb["_atk_reloc_target"] = {"x": bx + perp_x * reloc_u,
                                           "z": bz + perp_z * reloc_u}
                bb["_atk_phase"] = "relocate"
                logging.info(f"[bt-attack] {bot['id']} salve terminée ({shots}/{max_total}), relocalisation")
            else:
                # salvo2 terminée → RETREAT (combat fini).
                return _end_attack("RETREAT" if bt_has("RETREAT") else "STALK",
                                   f"{shots} torpilles tirées, rompt le combat")
            return Status.SUCCESS

        # Tir torpille autonome. La torpille s'active après une courte distance
        # parcourue depuis le tireur, ce qui lui laisse le maximum de chemin
        # pour corriger sa trajectoire en radar actif. Préfère 500m, sinon
        # 200m, sinon refuse de tirer (cible trop proche).
        if dist_m >= 700.0:
            activation_m = 500.0
        elif dist_m >= 400.0:
            activation_m = 200.0
        else:
            logging.info(f"[bt-attack] {bot['id']} tir refusé : dist={dist_m:.0f}m trop courte")
            return Status.FAILURE
        fired = deps["spawn_bot_torpedo_autonomous"](bot, target_player, activation_m)
        if fired:
            shots += 1
            bb["attack_shots"] = shots
            bb["_atk_salvo_done"] = salvo_shots + 1
            bot["next_torpedo_at"] = now + cooldown_s
            # Mémoriser les clés des torpilles tirées pour suivre l'acquisition.
            torp_keys = bb.setdefault("_atk_torp_keys", [])
            torp_keys.append((bot["id"], bot.get("_last_tid", shots)))
            logging.info(f"[bt-attack] {bot['id']} tir autonome #{shots}/{max_total} "
                         f"dist={dist_m:.0f}m activ={activation_m:.0f}m")
        return Status.SUCCESS

    # --- Phase RELOCATE + OBSERVE (se déplacer et surveiller les torpilles) ---
    if phase == "relocate" or phase == "observe":
        # Vérifier l'état des torpilles.
        acq_status = _check_own_torpedoes(bot, deps)
        if acq_status == "all_lost":
            bb.pop("_atk_reloc_target", None)
            bb["_atk_phase"] = "salvo2"
            logging.info(f"[bt-attack] {bot['id']} acquisition perdue → salvo2")
            return Status.SUCCESS
        elif acq_status == "none_alive":
            return _end_attack("RETREAT" if bt_has("RETREAT") else "STALK",
                               "torpilles terminées")
        # Continuer à se déplacer silencieusement.
        reloc = bb.get("_atk_reloc_target")
        if reloc:
            dist_to_reloc = math.hypot(reloc["x"] - bx, reloc["z"] - bz)
            arrive_u = relocate_m * 0.3 / UNIT_METERS_BOT
            if dist_to_reloc < arrive_u:
                # Arrivé au point reloc → continuer tout droit (phase observe).
                bb["_atk_phase"] = "observe"
                bb.pop("_atk_reloc_target", None)
                logging.info(f"[bt-attack] {bot['id']} reloc atteint, observe en mouvement")
            else:
                return _drive_to_waypoint(bot, ctx, reloc, params)
        # En observe sans cible reloc : avancer tout droit à vitesse silencieuse.
        wp = {"x": bx - math.cos(bot["rotation"]) * 10,
              "z": bz + math.sin(bot["rotation"]) * 10}
        return _drive_to_waypoint(bot, ctx, wp, params)

    return Status.SUCCESS


def _check_own_torpedoes(bot, deps):
    """Vérifie l'état des torpilles du bot en vol.
    Retourne: 'acquired' si au moins une en acquisition,
              'all_lost' si toutes vivantes ont perdu l'acquisition,
              'none_alive' si aucune en vol,
              'in_flight' si en vol mais pas encore en acquisition."""
    pid = bot["id"]
    torpedoes = deps.get("bot_torpedoes_status")
    if not torpedoes:
        # Fallback : lire directement depuis le dict global via deps.
        return "none_alive"
    alive = torpedoes(pid)
    if not alive:
        return "none_alive"
    any_acquired = any(t.get("acquired") or t.get("inAcquisition") for t in alive)
    if any_acquired:
        return "acquired"
    # Toutes en vol mais aucune en acquisition.
    any_activated = any(t.get("traveled", 0) >= t.get("activation", 0) for t in alive)
    if any_activated:
        return "all_lost"
    return "in_flight"


@register_action("retreat_to_cover")
def act_retreat_to_cover(ctx, params):
    """RETREAT : après avoir tiré, se met à couvert (nœud nav_graph caché de
    l'ennemi et accessible). Ne termine que quand le nœud est atteint.
    Si pas de couvert accessible → STALK directement (geler sur place)."""
    bot = ctx["bot"]
    bb = bot.setdefault("bb", {})
    deps = ctx["deps"]
    world = ctx["world"]
    UNIT_METERS_BOT = deps["UNIT_METERS_BOT"]
    now = ctx["now"]

    # Figer la position ennemi de référence au moment de l'entrée en RETREAT.
    # Priorite au snapshot detecte, jamais a la position live cachee.
    if "retreat_enemy_ref" not in bb:
        enemy_pos = None
        detected_ids = bot.get("last_detected_ids") or set()
        same_team_fn = deps.get("same_team")
        if detected_ids:
            for p in _known_targets(bot, now):
                if p.get("id") in detected_ids and not (same_team_fn and same_team_fn(bot, p)):
                    if not deps["bot_target_los"](bot, p["position"]):
                        continue
                    pos = p.get("position") or {}
                    enemy_pos = {"x": pos.get("x", 0), "z": pos.get("z", 0)}
                    break
        if enemy_pos is None:
            last = bb.get("last_enemy_pos")
            if not last:
                bb["state"] = "STALK"
                bb["t_enter"] = now
                bb.pop("cover_node", None)
                return Status.SUCCESS
            enemy_pos = {"x": last["x"], "z": last["z"]}
        bb["retreat_enemy_ref"] = enemy_pos
        logging.info(f"[bt-retreat] {bot['id']} enemy_ref=({enemy_pos['x']:.0f},{enemy_pos['z']:.0f})")

    enemy_ref = bb["retreat_enemy_ref"]

    # Timeout : si trop long, abandonner et geler.
    stalk_timeout_s = float(params.get("timeout_s", 30.0))
    if now - bb.get("t_enter", now) > stalk_timeout_s:
        bb["state"] = "STALK"
        bb["t_enter"] = now
        bb.pop("cover_node", None)
        bb.pop("retreat_enemy_ref", None)
        logging.info(f"[bt-fsm] {bot['id']} RETREAT → STALK (timeout)")
        return Status.SUCCESS

    # Sélection nœud de couvert + calcul du chemin (une seule fois).
    ng = world.get("nav_graph") or {}
    nodes = ng.get("nodes") or []
    island_nodes_list = ng.get("island_nodes") or []
    retreat_path = bb.get("retreat_path")
    if retreat_path is None:
        cover_node = _pick_cover_node(bot, world, enemy_ref, deps)
        if cover_node is None:
            bb["state"] = "STALK"
            bb["t_enter"] = now
            bb.pop("retreat_enemy_ref", None)
            logging.info(f"[bt-fsm] {bot['id']} RETREAT → STALK (pas de couvert)")
            return Status.SUCCESS
        # Trouver l'île du nœud cible.
        _, node_to_island = _nav_graph_adjacency(world)
        target_island_idx = node_to_island.get(cover_node)
        if target_island_idx is None:
            bb["retreat_path"] = [cover_node]
        else:
            island_ring = island_nodes_list[target_island_idx]
            # Trouver P0 : le nœud de cette île visible par le bot, le plus proche.
            bx = bot["position"]["x"]
            bz = bot["position"]["z"]
            los_fn = deps.get("line_of_sight_clear")
            p0 = None
            p0_d2 = float("inf")
            for ni in island_ring:
                nd = nodes[ni]
                d2 = (nd["x"] - bx) ** 2 + (nd["z"] - bz) ** 2
                if d2 < p0_d2:
                    if los_fn and los_fn(bx, bz, nd["x"], nd["z"], world):
                        p0 = ni
                        p0_d2 = d2
            if p0 is None:
                # Aucun nœud visible sur l'île → aller directement au nœud cible.
                p0 = _nearest_node(bx, bz, [nodes[ni] for ni in island_ring])
                p0 = island_ring[p0]
            if p0 == cover_node:
                bb["retreat_path"] = [cover_node]
            else:
                ring_path = _ring_path(island_ring, p0, cover_node, nodes)
                if ring_path:
                    bb["retreat_path"] = ring_path
                else:
                    bb["retreat_path"] = [cover_node]
        retreat_path = bb["retreat_path"]
        logging.info(f"[bt-retreat] {bot['id']} chemin vers couvert #{cover_node}: "
                     f"{len(retreat_path)} nœuds, path={retreat_path}")

    if not retreat_path:
        bb["state"] = "STALK"
        bb["t_enter"] = now
        bb.pop("retreat_path", None)
        bb.pop("retreat_enemy_ref", None)
        logging.info(f"[bt-fsm] {bot['id']} RETREAT → STALK (chemin vide)")
        return Status.SUCCESS

    # Naviguer vers le prochain nœud du chemin.
    bx = bot["position"]["x"]
    bz = bot["position"]["z"]
    next_idx = retreat_path[0]
    if next_idx >= len(nodes):
        bb.pop("retreat_path", None)
        bb.pop("retreat_enemy_ref", None)
        bb["state"] = "STALK"
        bb["t_enter"] = now
        return Status.SUCCESS
    target = nodes[next_idx]
    arrive_radius_u = float(params.get("arrive_radius_m", 100.0)) / UNIT_METERS_BOT
    dist_u = math.hypot(target["x"] - bx, target["z"] - bz)
    if dist_u < arrive_radius_u:
        retreat_path.pop(0)
        if not retreat_path:
            bb["state"] = "STALK"
            bb["t_enter"] = now
            bb.pop("retreat_path", None)
            bb.pop("retreat_enemy_ref", None)
            logging.info(f"[bt-fsm] {bot['id']} RETREAT → STALK (couvert atteint)")
            return Status.SUCCESS
        next_idx = retreat_path[0]
        target = nodes[next_idx]

    return _drive_to_waypoint(bot, ctx, target, params)


@register_action("fire_aa_at_human_drone")
def act_fire_aa_at_human_drone(ctx, params):
    """Tire à la DCA sur le premier drone d'humain à portée. Cooldown 0.4 s/tir,
    1.5 s par drone (anti-mitraillage)."""
    bot = ctx["bot"]
    deps = ctx["deps"]
    if not (bot.get("boat") or {}).get("antiAircraft"):
        return Status.FAILURE
    now = ctx["now"]
    per_drone_cd = bot.setdefault("aa_per_drone", {})
    drones_server = deps["drones_server"]
    for key, deadline in list(per_drone_cd.items()):
        if key not in drones_server or deadline <= now:
            per_drone_cd.pop(key, None)
    players = deps["players"]
    same_team_fn = deps.get("same_team")
    for key, drone in list(drones_server.items()):
        owner_pid = drone["ownerPlayerId"]
        owner_sid = next((sid for sid, p in players.items() if p["id"] == owner_pid), None)
        owner = players.get(owner_sid) if owner_sid else None
        if owner is None:
            continue
        if same_team_fn and same_team_fn(bot, owner):
            continue
        if now < per_drone_cd.get(key, 0):
            continue
        if not deps["bot_target_los"](bot, drone):
            continue
        if deps["bot_fire_aa"](bot, drone):
            bot["next_aa_at"] = now + float(params.get("cooldown_s", 0.4))
            per_drone_cd[key] = now + float(params.get("per_drone_cooldown_s", 1.5))
            return Status.SUCCESS
    return Status.FAILURE
