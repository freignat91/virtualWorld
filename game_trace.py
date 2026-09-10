"""Trace serveur JSONL bornee, sans dependance au serveur ni aux capteurs."""

import dataclasses
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, Optional
import uuid


# Liste positive recursive : jamais de SID, nom, chat, configuration ou BB brut.
FIELDS = frozenset("""
id shot_id shotId u player_id owner_id shooter_id victim_id attacker_id target_id detected_id
actor_id old_position
ownerId ownerPlayerId shooterId targetId detectedId playerId victimId attackerId
tid did gid mid bid lid kind boatType boat_type is_bot external_control
x y z position rotation rudder reverse speed speedRatio speed_ratio integrity maxIntegrity max_integrity
submerged sunk depth_target_y control_target_rudder control_target_speed_ratio
control_target_depth_y dirX dirZ dir_x dir_z vx vy vz pitch target_x target_y
target_z targetX targetY targetZ initialTarget lastAcquiredPos lockedKey
acquired destroyed outgoing hit_lure direct_hit_id damage dealt value count reason
acquiredBoatId initialTargetTracked activationDistance traveledDistance
counts torpedo_counts drone_counts grenade_count cannon_counts beacon_count
lure_count mine_counts acoustic wireGuided autonomous automatic manual cannon
antiAircraft surface bottom suspended armed depthMeters targetDepth target_depth
sinkSpeed sink_speed range range_m rangeMeters noise duration duration_ms
start_x start_y start_z end_x end_y end_z startX startY startZ endX endY endZ
arc_height arcHeight impact returning autonomy traveled until observed_at tracked
at cone_deg coneDeg reveal_m revealRangeMeters rangeUnits coneAngle
fwd_x fwd_z half_cos penetration reveal waypoint
speed_mult godmode max_speed_us cruise_us max_depth_m
minNoise speedNoiseLimit flotation acousticLures sonarBeacons passiveSonarBeacons
number time pingIntervalSec thermoclinePenetration activeSonar passiveSonar
shortAngle shortAngleRange largeAngle largeAngleRange maxDepthMeters torpedoes
minTurnRadius activation maxRangeMeters radarRangeMeters radarConeDeg
automaticDrone manualDrone altitude safeDistance ammunition mineSurf mineBottom
mineSuspended delay grenade sinkSpeedMs effectRangeMeters dayDurationSeconds
""".split())

EVENTS = frozenset("""
PlayerJoined PlayerLeft PlayerMoved PositionCorrect BoatSunk OwnBoatSunk
BotTeleported RLDecision
OwnBoatAdded IntegrityChanged BoatChanged OtherBoatChanged TorpedoCounts
DroneCounts GrenadeCount CannonCounts BeaconCount LureCount MineCounts
TorpedoState TorpedoAlert TorpedoAcquisition TorpedoExploded TorpedoDead
DroneState DroneDead GrenadeLaunched GrenadeExploded MinePlaced MineArmed
MineExploded MineDead MineRevealed SonarBeaconPlaced SonarBeaconDestroyed
SonarBeaconPing PassiveSonarBeaconPlaced PassiveSonarBeaconDestroyed
PassiveSonarDetection SonarPinged LureDropped LureIntegrityChanged LureDestroyed CannonFire CannonHit CannonImpact
""".split())

NETWORK_EVENTS = frozenset("""
player_joined player_left boat_sunk own_boat_sunk integrity integrity_changed
boat_changed other_boat_changed torpedo_counts drone_counts grenade_count
cannon_counts beacon_count passive_beacon_count lure_count mine_counts
torpedo_alert torpedo_acquisition torpedo_exploded torpedo_dead drone_dead
grenade_launched grenade_exploded mine_placed mine_armed mine_exploded mine_dead
mine_revealed sonar_beacon_placed sonar_beacon_destroyed sonar_beacon_ping
sonar_beacon_revealed passive_sonar_beacon_placed passive_sonar_beacon_destroyed
passive_sonar_detection sonar_pinged lure_dropped lure_integrity lure_destroyed cannon_fire
cannon_hit cannon_impact position_correct
""".split())

RL_RESULT_FIELDS = frozenset("""
weapon_requested weapon_fired weapon_invalid weapon_kind
lure_requested lure_dropped lure_invalid sonar_requested sonar_pinged sonar_invalid
mine_requested mine_placed mine_invalid mine_kind
""".split())


def select(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ne copie que les champs connus, y compris dans les objets imbriques."""
    result = {}
    for key, value in data.items():
        if key not in FIELDS:
            continue
        if isinstance(value, dict):
            result[key] = select(value)
        elif value is None or type(value) in (str, int, float, bool):
            result[key] = value
        elif key in {"initialTarget", "lastAcquiredPos"} and isinstance(value, (tuple, list)):
            if len(value) != 3 or any(type(v) not in (int, float) for v in value):
                raise TypeError("invalid trace position")
            result[key] = list(value)
        else:
            raise TypeError("non primitive trace field")
    return result


class StrictRotatingHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        # logging avale normalement les erreurs disque : remonter pour desactiver.
        raise OSError("trace write failed")


class GameTrace:
    def __init__(self, enabled: bool = False, path: Any = "logs/game_trace.jsonl",
                 max_bytes: int = 20 * 1024 * 1024, backups: int = 5) -> None:
        self.enabled = enabled
        self.session = uuid.uuid4().hex
        self.epoch = 0
        self.tick = 0
        self.sequence = 0
        self.sim_time: Optional[float] = None
        self.elapsed = 0.0
        self._next_sample = 0.0
        self._objects: set = set()
        self._locks: dict = {}
        self._contacts: set = set()
        self._projectiles: set = set()
        self._rl_models: set = set()
        self._world: Any = None
        self._map: Optional[str] = None
        self.handler: Optional[StrictRotatingHandler] = None
        self.logger = logging.Logger("game_trace", logging.INFO)
        self.logger.propagate = False
        self.max_bytes = max_bytes
        self.records = 0
        self.bytes_written = 0
        if not enabled:
            return
        try:
            if max_bytes < 512 or backups < 1:
                raise ValueError("invalid trace bounds")
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.handler = StrictRotatingHandler(path, maxBytes=max_bytes,
                                                 backupCount=backups, encoding="utf-8")
            # Une fin de ligne interrompue ne doit pas absorber la nouvelle session.
            if path.stat().st_size:
                self.handler.doRollover()
            self.handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(self.handler)
            self._write("session", {"snapshot_hz": 4, "max_bytes": max_bytes,
                                    "backups": backups, "unit_meters": 10})
        except Exception:
            self._disable()

    def _disable(self) -> None:
        self.enabled = False
        self.close()
        # Aucun message d'exception : il pourrait contenir une donnee sensible.
        logging.getLogger(__name__).warning("Game trace disabled after capture/write failure")

    def close(self) -> None:
        self.enabled = False
        if self.handler is not None:
            self.logger.removeHandler(self.handler)
            try:
                self.handler.close()
            except Exception:
                pass
            self.handler = None

    def _write(self, kind: str, data: Dict[str, Any]) -> None:
        self.sequence += 1
        record = dict(schema=1, session=self.session, epoch=self.epoch,
                      seq=self.sequence, tick=self.tick, wall_time=time.time(),
                      sim_time=self.sim_time, stepped_seconds=self.elapsed,
                      type=kind, data=data)
        line = json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        size = len(line.encode("utf-8")) + 1
        if size >= self.max_bytes:
            raise ValueError("trace record exceeds file bound")
        self.logger.info(line)
        self.records += 1
        self.bytes_written += size

    def metadata(self, root: Any, map_name: str, world: dict) -> None:
        if not self.enabled:
            return
        try:
            root = Path(root)
            revision = None
            dirty = None
            for command in (["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"]):
                try:
                    value = subprocess.run(command, cwd=root, capture_output=True,
                                           text=True, timeout=3, check=True).stdout.strip()
                    if command[1] == "rev-parse":
                        revision = value
                    else:
                        dirty = bool(value)
                except (OSError, subprocess.SubprocessError):
                    pass
            files = [root / name for name in ("server.py", "simulation.py", "events.py",
                     "geometry.py", "bot_ai.py", "game_trace.py", "rl/rl_control.py",
                     "rl/rl_runtime.py", "autogame.py")]
            files += sorted((root / "boats").glob("*.json"))
            files += sorted((root / "bots/ai").glob("*.json"))
            fingerprints = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in files if p.is_file()}
            specs = {p.stem: select(json.loads(p.read_text()))
                     for p in sorted((root / "boats").glob("*.json"))}
            config_path = root / "config/conffile.json"
            rules = select(json.loads(config_path.read_text()).get("world", {})) if config_path.is_file() else {}
            self._write("metadata", {"git_revision": revision, "git_dirty": dirty,
                                     "sha256": fingerprints, "boat_specs": specs, "rules": rules})
            self.world(map_name, world)
        except Exception:
            self._disable()

    def world(self, name: str, world: dict) -> None:
        if not self.enabled or (self._world is world and self._map == name):
            return
        try:
            self.epoch += 1
            self._world, self._map = world, name
            self._objects.clear()
            self._locks.clear()
            self._contacts.clear()
            self._projectiles.clear()
            self._next_sample = 0
            fingerprint = hashlib.sha256(json.dumps(world, sort_keys=True,
                                                    allow_nan=False).encode()).hexdigest()
            self._write("world", {"map": name, "sha256": fingerprint})
        except Exception:
            self._disable()

    def event(self, event: Any, players: dict) -> None:
        if not self.enabled or type(event).__name__ not in EVENTS:
            return
        try:
            if type(event).__name__ == "RLDecision":
                # Schema distinct : aucune extension de la liste globale des etats.
                fields = {key: getattr(event, key) for key in (
                    "player_id", "control_version", "decision_at", "physics_dt",
                    "simulation_step", "decision_interval_s", "episode_start",
                    "model_id", "model_sha256")}
                for key, value_type in (("observation", (int, float)), ("action", (int,))):
                    values = getattr(event, key)
                    if not isinstance(values, list) or any(type(v) not in value_type for v in values):
                        raise TypeError("invalid RL trace vector")
                    fields[key] = list(values)
                fields["result"] = {key: value for key, value in event.result.items()
                                    if key in RL_RESULT_FIELDS}
                threat = event.visible_threat
                fields["visible_threat"] = (None if threat is None else
                    {key: threat[key] for key in ("owner_id", "tid") if key in threat})
                # select ne doit pas ouvrir de dictionnaire arbitraire ici.
                for values in (fields["result"], fields["visible_threat"] or {},
                               {k: v for k, v in fields.items()
                                if k not in {"result", "visible_threat", "observation", "action"}}):
                    if any(v is not None and type(v) not in (str, int, float, bool)
                           for v in values.values()):
                        raise TypeError("invalid RL trace field")
                model = (event.model_id, event.model_sha256)
                if model not in self._rl_models:
                    self._write("rl_model", dict(model_id=model[0], model_sha256=model[1]))
                    self._rl_models.add(model)
                self._write("event", {"name": "RLDecision", "fields": fields})
                return
            # Les etats continus sont remplaces par les snapshots decimes.
            if type(event).__name__ == "PlayerMoved":
                return
            if type(event).__name__ in {"TorpedoState", "DroneState", "TorpedoDead", "DroneDead"}:
                projectile = ("torpedo" if hasattr(event, "tid") else "drone",
                              event.owner_id, getattr(event, "tid", getattr(event, "did", None)))
                if type(event).__name__.endswith("State"):
                    if projectile in self._projectiles:
                        return
                    self._projectiles.add(projectile)
                else:
                    self._projectiles.discard(projectile)
            values = {f.name: getattr(event, f.name) for f in dataclasses.fields(event)
                      if f.name in FIELDS}
            for field in ("payload", "player_data"):
                if hasattr(event, field):
                    values.update(select(getattr(event, field)))
            reason = getattr(event, "reason", None)
            if reason in {"lost", "hit", "destroyed", "recovered", "crashed", "shot",
                          "speed", "bounds", "island", "depth"}:
                values["reason"] = reason
            sid = getattr(event, "bsid", None) or event.target_sid
            recipient = players.get(sid, {}).get("id")
            if recipient is not None:
                values["player_id"] = recipient
            fields = select(values)
            if "reason" in values:
                fields["reason"] = values["reason"]
            self._write("event", {"name": type(event).__name__, "fields": fields})
        except Exception:
            self._disable()

    def network(self, name: str, payload: Any, players: Optional[dict] = None,
                recipient: Optional[str] = None) -> None:
        if not self.enabled or name not in NETWORK_EVENTS:
            return
        try:
            fields = select(payload or {})
            if players is not None:
                sid = (payload or {}).get("bsid") or recipient
                player_id = players.get(sid, {}).get("id")
                if player_id is not None:
                    fields["player_id"] = player_id
            self._write("legacy_event", {"name": name, "fields": fields})
        except Exception:
            self._disable()

    def observe(self, sim: Any, server: Any, dt: Optional[float] = None) -> None:
        if not self.enabled:
            return
        try:
            if dt is not None:
                self.tick += 1
                self.elapsed += dt
            self.sim_time = sim.t
            locks = {(t["ownerPlayerId"], t["tid"]): t.get("lockedKey")
                     for t in sim.torpedoes.values()}
            for key in self._locks.keys() | locks.keys():
                if self._locks.get(key) != locks.get(key):
                    self._write("lock", {"object": list(key), "previous": self._locks.get(key),
                                         "current": locks.get(key)})
            self._locks = locks
            contacts = {(v["bot"]["id"], v["target"]["id"], "active_reveal")
                        for v in sim._sonar_reveals.values()}
            contacts.update((bot["id"], pid, "bt_detected") for bot in sim.bots.values()
                            for pid in bot.get("last_detected_ids", ()))
            for key in contacts ^ self._contacts:
                self._write("sonar_contact", {"observer_id": key[0], "target_id": key[1],
                                               "source": key[2], "acquired": key in contacts})
            self._contacts = contacts
            now = time.monotonic()
            if now < self._next_sample:
                return
            self._next_sample = now + 0.25
            objects = set()
            groups = dict(boat=sim.players, torpedo=sim.torpedoes, drone=sim.drones,
                          grenade=sim.grenades, mine=sim.mines, beacon=sim.beacons,
                          passive_beacon=server.passive_sonar_beacons, lure=sim.lures)
            for group, entries in groups.items():
                for sid, obj in entries.items():
                    fields = select(obj)
                    if group == "boat":
                        fields.update(select(sim.bots.get(sid, {})))
                        identity = (group, obj["id"])
                        ammo = {}
                        for name in ("torpedo", "drone", "grenade", "cannon", "beacon",
                                     "passive_beacon", "lure", "mine"):
                            value = getattr(server, name + "_ammo", {}).get(sid)
                            if value is not None:
                                ammo[name] = select(value) if isinstance(value, dict) else value
                        fields["ammo"] = ammo
                    else:
                        # Les cles de ces collections sont publiques, jamais des SID.
                        identity = (group, *(sid if isinstance(sid, tuple) else (sid,)))
                    objects.add(identity)
                    self._write("snapshot", {"object": list(identity),
                                "first_seen": identity not in self._objects, "fields": fields})
            for identity in self._objects - objects:
                self._write("despawn", {"object": list(identity), "inferred": True})
            self._objects = objects
            for shell in sim.cannon_shells:
                self._write("cannon_shell", select(shell))
            for ping in sim._pending_sonar_pings:
                self._write("pending_sonar_ping", dict(select(ping), player_id=ping["bot"]["id"]))
            self._write("sample", {"counts": {k: len(v) for k, v in groups.items()},
                                  "sim_multiplier": server.sim_tick_multiplier,
                                  "bots_passive": server.bots_passive,
                                  "records_written": self.records,
                                  "bytes_written": self.bytes_written})
        except Exception:
            self._disable()
