"""Events de la simulation Virtual World.

Chaque action de gameplay qui doit être communiquée à l'extérieur (réseau,
log, replay) est enregistrée comme un Event. La couche I/O (server.py côté
réseau) dispatche ensuite ces events vers les bons sockets.

Convention :
- `target_sid` (Optional[str]) : si présent, l'event est destiné à un sid
  particulier (équivalent à `to=sid` côté socketio). Sinon broadcast.
- `exclude_sid` (Optional[str]) : si présent, ne pas envoyer à ce sid
  (équivalent à `include_self=False`).
- Les events ne contiennent que des **données primitives** (str, int, float,
  list, dict). Aucune référence vers `players`, `bots`, etc. — la simu doit
  filtrer/copier ce qui doit voyager.

Tous les events sont des dataclasses pour être trivialement sérialisables.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


# ===================== Base =====================

@dataclass
class Event:
    """Tag racine ; tous les events héritent. Permet `isinstance(e, Event)`
    et un dispatch type-based dans server.py."""
    target_sid: Optional[str] = field(default=None, kw_only=True)
    exclude_sid: Optional[str] = field(default=None, kw_only=True)


# ===================== Cycle de vie joueur =====================

@dataclass
class PlayerJoined(Event):
    """Un nouveau participant (humain, bot ou bateau secondaire) entre."""
    player_data: Dict[str, Any]  # snapshot complet du player dict (id, boatType, boat, position, rotation, ...)


@dataclass
class PlayerLeft(Event):
    player_id: str


@dataclass
class PlayerMoved(Event):
    player_id: str
    position: Dict[str, float]
    rotation: float
    rudder: float
    reverse: bool
    speed_ratio: Optional[float]
    integrity: float
    submerged: bool = False


@dataclass
class PositionCorrect(Event):
    """Anti-cheat : téléporte le client à la dernière position valide."""
    position: Dict[str, float]
    rotation: float
    reason: str


@dataclass
class BoatSunk(Event):
    victim_id: str
    attacker_id: Optional[str]


@dataclass
class OwnBoatSunk(Event):
    """Adressé au propriétaire d'un bateau secondaire qui vient de couler."""
    bsid: str
    player_id: str


@dataclass
class OwnBoatAdded(Event):
    """Réponse au cheat addsub/adddest : nouveau bateau secondaire prêt."""
    ghost_sid: str
    player_id: str
    boat_type: str
    boat: Dict[str, Any]
    position: Dict[str, float]
    rotation: float
    torpedo_counts: Dict[str, int]
    drone_counts: Dict[str, int]
    grenade_count: int
    cannon_counts: Dict[str, int]
    beacon_count: int
    lure_count: int
    mine_counts: Dict[str, int]


@dataclass
class IntegrityChanged(Event):
    bsid: Optional[str]
    value: float


@dataclass
class BoatChanged(Event):
    """Réponse au cheat change_boat (toggle dest <-> sub)."""
    boat_type: str
    boat: Dict[str, Any]
    torpedo_counts: Dict[str, int]
    drone_counts: Dict[str, int]
    grenade_count: int
    cannon_counts: Dict[str, int]
    beacon_count: int
    lure_count: int


@dataclass
class OtherBoatChanged(Event):
    player_id: str
    boat: Dict[str, Any]


# ===================== Munitions (compteurs) =====================

@dataclass
class TorpedoCounts(Event):
    bsid: Optional[str]
    counts: Dict[str, int]


@dataclass
class DroneCounts(Event):
    bsid: Optional[str]
    counts: Dict[str, int]


@dataclass
class GrenadeCount(Event):
    bsid: Optional[str]
    count: int


@dataclass
class CannonCounts(Event):
    bsid: Optional[str]
    counts: Dict[str, int]


@dataclass
class BeaconCount(Event):
    bsid: Optional[str]
    count: int


@dataclass
class LureCount(Event):
    bsid: Optional[str]
    count: int


@dataclass
class MineCounts(Event):
    bsid: Optional[str]
    counts: Dict[str, int]


# ===================== Torpilles =====================

@dataclass
class TorpedoState(Event):
    owner_id: str
    tid: int
    kind: str
    x: float; y: float; z: float
    dir_x: float; dir_z: float
    target_x: Optional[float]
    target_y: Optional[float]
    target_z: Optional[float]


@dataclass
class TorpedoAlert(Event):
    """« Une torpille a été tirée vers vous » (ou « par vous » si outgoing)."""
    shooter_id: str
    tid: int
    kind: str
    outgoing: bool = False


@dataclass
class TorpedoAcquisition(Event):
    shooter_id: str
    tid: int
    kind: str
    acquired: bool
    destroyed: bool
    reason: Optional[str]
    outgoing: bool = False


@dataclass
class TorpedoExploded(Event):
    owner_id: str
    x: float; y: float; z: float
    damage: float
    direct_hit_id: Optional[str]
    hit_lure: bool = False


@dataclass
class TorpedoDead(Event):
    owner_id: str
    tid: int


# ===================== Drones =====================

@dataclass
class DroneState(Event):
    owner_id: str
    did: int
    kind: str
    x: float; y: float; z: float
    dir_x: float; dir_z: float
    returning: bool
    speed: float
    autonomy: float
    traveled: float
    range_m: float = 0.0


@dataclass
class DroneDead(Event):
    owner_id: str
    did: int
    reason: str  # "recovered" | "crashed" | "shot" | "lost"


# ===================== Grenades =====================

@dataclass
class GrenadeLaunched(Event):
    shooter_id: str
    gid: int
    x: float; y: float; z: float
    vx: float; vy: float; vz: float
    target_depth: float
    sink_speed: float


@dataclass
class GrenadeExploded(Event):
    shooter_id: str
    gid: int
    x: float; y: float; z: float
    damage: float
    dealt: float = 0.0


# ===================== Mines =====================

@dataclass
class MinePlaced(Event):
    payload: Dict[str, Any]  # cf. _mine_payload côté serveur


@dataclass
class MineArmed(Event):
    owner_id: str
    mid: int


@dataclass
class MineExploded(Event):
    owner_id: str
    mid: int
    kind: str
    x: float; y: float; z: float
    range: float


@dataclass
class MineDead(Event):
    owner_id: str
    mid: int


@dataclass
class MineRevealed(Event):
    """Mine ennemie devient visible pour une team (détection bot, ping, clic)."""
    owner_id: str
    mid: int
    target_team: str


# ===================== Balises sonar =====================

@dataclass
class SonarBeaconPlaced(Event):
    payload: Dict[str, Any]  # le dict beacon complet


@dataclass
class SonarBeaconDestroyed(Event):
    bid: int


@dataclass
class SonarBeaconPing(Event):
    bid: int
    x: float; z: float
    at: float


@dataclass
class PassiveSonarBeaconPlaced(Event):
    """Une balise sonar passive vient d'être posée. Visible par tous (mesh 3D),
    ne ping pas. Détecte en continu les bateaux audibles en LOS et notifie
    seulement l'équipe du propriétaire."""
    payload: Dict[str, Any]  # dict beacon complet


@dataclass
class PassiveSonarBeaconDestroyed(Event):
    bid: int


@dataclass
class PassiveSonarDetection(Event):
    """Une balise passive a détecté un ennemi → révéler à l'équipe du propriétaire.
    Le client filtre par appartenance à l'équipe via le payload `team_id`."""
    bid: int
    detected_id: str   # playerId du bateau détecté
    x: float; z: float; y: float
    team_id: str       # team du propriétaire de la balise (filtre client)


# ===================== Sonar / Leurres =====================

@dataclass
class SonarPinged(Event):
    """Un autre joueur a déclenché son sonar actif."""
    player_id: str
    x: float; z: float
    cone_deg: float = 360.0
    rotation: float = 0.0
    range_m: float = 0.0
    reveal_m: float = 0.0


@dataclass
class LureDropped(Event):
    owner_id: str
    lid: int
    x: float; y: float; z: float
    noise: float
    duration_ms: float


@dataclass
class LureDestroyed(Event):
    owner_id: str
    lid: int


# ===================== Canon / DCA =====================

@dataclass
class CannonFire(Event):
    shooter_id: str
    kind: str
    start_x: float; start_y: float; start_z: float
    end_x: float; end_y: float; end_z: float
    arc_height: float
    duration: float
    impact: bool


@dataclass
class CannonHit(Event):
    shooter_id: str
    target_id: str
    damage: float


# ===================== Wake / divers =====================

@dataclass
class WakeSpawned(Event):
    player_id: str
    x: float; z: float
    submerged: bool
    y: float


@dataclass
class DayCycleState(Event):
    snapshot: Dict[str, Any]


# ===================== Cheats / admin (réponses sid-only) =====================

@dataclass
class CheatViewBot(Event):
    payload: Dict[str, Any]


@dataclass
class CheatViewSelf(Event):
    pass


@dataclass
class CheatBotsCalmdownState(Event):
    passive: bool


@dataclass
class CheatReloadAiDone(Event):
    count: int


@dataclass
class BotSpawned(Event):
    bot_id: str
    boat_type: str
    ai: str


@dataclass
class AdminWorldLoaded(Event):
    world: Dict[str, Any]
    name: str


@dataclass
class AdminSaveOk(Event):
    name: str


@dataclass
class AdminError(Event):
    message: str
