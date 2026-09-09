const canvas = document.getElementById("renderCanvas");
console.log("[startup] avant BABYLON.Engine t=" + performance.now().toFixed(0) + "ms");
const engine = new BABYLON.Engine(canvas, true);
console.log("[startup] après BABYLON.Engine t=" + performance.now().toFixed(0) + "ms");
// transports: ['websocket'] désactive le fallback long-polling.
// Évite l'erreur engineio "Too many packets in payload" qui survient quand le
// batching HTTP du polling déborde au-delà du cap (16 par défaut).
const socket = io({ autoConnect: false, transports: ["websocket"] });
let selectedBoatType = null;

const UNIT_METERS = 10;
const KNOTS_TO_MS = 0.514444;
const FRAMES_PER_SEC = 60;
function knotsToUnitPerFrame(nds) { return nds * KNOTS_TO_MS / UNIT_METERS / FRAMES_PER_SEC; }
function knotsToUnitPerSecond(nds) { return nds * KNOTS_TO_MS / UNIT_METERS; }
function unitPerFrameToKnots(uf) { return uf * UNIT_METERS * FRAMES_PER_SEC / KNOTS_TO_MS; }
function unitPerSecondToKnots(us) { return us * UNIT_METERS / KNOTS_TO_MS; }
function metersToUnits(m) { return m / UNIT_METERS; }

const ISLAND_TEXTURE_COLORS = {
    sol1: "#8b6f47",  // marron terre
    sol2: "#6db35c",  // vert herbe
    sol3: "#d4c190",  // sable
};
const ISLAND_TEXTURE_DEFAULT_COLOR = "#8a8a6a";  // gris-vert neutre pour textures inconnues
const islandTextureUrls = {};  // name → url, peuplé par admin_textures_list
const islandTextureImages = {};  // name → HTMLImageElement (cache pour radar)
const islandTexturePatternCanvases = {};  // name → canvas 32×32 prêt pour createPattern

function ensureRadarTextureImage(name) {
    if (islandTextureImages[name]) return;
    const img = new Image();
    img.src = islandTextureUrl(name);
    islandTextureImages[name] = img;
    img.addEventListener("load", () => {
        const c = document.createElement("canvas");
        c.width = 32;
        c.height = 32;
        const cx = c.getContext("2d");
        cx.drawImage(img, 0, 0, 32, 32);
        islandTexturePatternCanvases[name] = c;
    });
}
function islandTextureName(island) {
    const t = island && island.texture;
    return (typeof t === "string" && t.length > 0) ? t : "sol2";
}
function islandTextureUrl(name) {
    if (islandTextureUrls[name]) return islandTextureUrls[name];
    return `/images/${name}.jpg`;  // fallback historique sol1/sol2/sol3
}
function islandRadarColor(island) {
    const name = islandTextureName(island);
    return ISLAND_TEXTURE_COLORS[name] || ISLAND_TEXTURE_DEFAULT_COLOR;
}

let selectedTeamId = null;
let selectedTeamName = null;

function pickBoat(type) {
    selectedBoatType = type;
    // Highlight visuel : bordure plus claire sur le bouton choisi.
    const btnD = document.getElementById("loginBoatDest");
    const btnS = document.getElementById("loginBoatSub");
    if (btnD) btnD.style.borderColor = (type === "destroyer") ? "#88ddff" : "#2a5a8a";
    if (btnS) btnS.style.borderColor = (type === "submarine") ? "#88ddff" : "#1a4a5a";
    // Précharge uniquement le modèle sélectionné pendant que le joueur saisit son pseudo.
    const _modelPath = (type === "destroyer") ? "models/sousMarin/scene.glb" : "models/navire/scene.glb";
    const _t0 = performance.now();
    loadBoatModel(_modelPath, () => {
        console.log("[startup] préchargement modèle terminé: " + _modelPath + " +" + (performance.now() - _t0).toFixed(0) + "ms");
    });
}
window.selectBoat = pickBoat;

function refreshTeamList(teams) {
    const list = document.getElementById("teamList");
    if (!list) return;
    list.innerHTML = "";
    if (teams && teams.length > 0) {
        for (const t of teams) {
            const row = document.createElement("div");
            row.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:8px 12px;margin:4px 0;background:#1a3340;border-radius:4px;";
            const label = document.createElement("span");
            label.textContent = `${t.team_name} (${t.members} bateau${t.members > 1 ? "x" : ""}${t.is_bots ? ", bots" : ""})`;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = "Rejoindre";
            btn.style.cssText = "padding:6px 14px;font-family:monospace;font-size:13px;cursor:pointer;background:#2a5a8a;color:white;border:none;border-radius:4px;";
            btn.addEventListener("click", () => joinTeam(t.team_id, t.team_name));
            row.appendChild(label);
            row.appendChild(btn);
            list.appendChild(row);
        }
    } else {
        list.innerHTML = '<div style="color:#888;padding:8px;text-align:center;">Aucune équipe en jeu pour l\'instant.</div>';
    }
    const humanCount = (teams || []).filter(t => !t.is_bots).length;
    const defaultName = "equipe" + (humanCount + 1);
    const inp = document.getElementById("teamNameInput");
    if (inp && !inp.value) inp.value = defaultName;
}

function joinTeam(team_id, team_name) {
    if (!selectedBoatType) {
        alert("Choisissez d'abord un bateau.");
        return;
    }
    selectedTeamId = team_id;
    selectedTeamName = team_name;
    document.getElementById("boatSelect").style.display = "none";
    console.log("[startup] select_boat émis boatType=" + selectedBoatType + " t=" + performance.now().toFixed(0) + "ms");
    socket.emit("select_boat", {
        boatType: selectedBoatType,
        team_id: selectedTeamId,
        team_name: selectedTeamName,
    });
}

function createAndJoinTeam() {
    const name = (document.getElementById("teamNameInput").value || "").trim();
    if (!name) return;
    const slug = name.toLowerCase().replace(/[^a-z0-9_-]+/g, "_").slice(0, 32) || ("team" + Date.now());
    joinTeam(slug, name);
}

let adminMode = false;
let adminCurrentMapName = "world";
let adminEditMode = null;
let adminAddingPoints = [];
let adminAddingPreviewMesh = null;
let adminEditingIslandIdx = null;
let adminEditingPointIdx = null;
let adminMoveIslandIdx = null;
let adminMoveStart = null;       // { x, z } point monde au clic
let adminMoveOrigPoints = null;  // snapshot des points avant move
let adminUndoStack = [];
let adminRedoStack = [];
let adminGreyedIslandIdx = null;
let adminGreyedOriginalColor = null;
let adminDirty = false;
let adminExitPending = false;

let scene;
let playerMesh;
let playerId;
let localTeamId = null;
let playerRotation = 0;
let cameraAlphaOffset = 0;
let cameraAlpha = 0;
let cameraTargetVec = null;
let cameraBeta = 1.3;
let cameraRadius = 15;
let boatSpeed = 0;
let boatHalfLength = 2;
let currentBoatLengthMeters = 100;
// Offsets caméra zoom par bateau (mètres) ; lus dans le JSON (boat.zoomCamera).
let currentBoatZoomCamera = { forwardMeters: 0, upMeters: 0 };
let boatHalfWidth = 1;
let modelRotationOffset = 0;
let otherPlayers = {};
const otherPlayerLoadGeneration = {};
let nextOtherPlayerLoadGeneration = 1;
let keys = {};
let initialized = false;
let gridMesh = null;
let allMapMode = false;
let radarVisible = false;
let showNavGraph = false;
let cheatVisuMode = false;
let joinGraceUntil = 0; // désactivé (plus de grâce à la connexion)
let cheatBuffer = "";
let moveCheatIndex = 0;
let cheatMoveMode = false;
let botCheatIndex = 0;
// localBoat = bateau du joueur ACTUELLEMENT actif (pilotable). remoteBoats[id] = bateaux distants (joueurs/bots).
// viewedBoat = bateau à l'écran (par défaut localBoat ; pointe sur un bot en vue bot).
// Multi-bateaux : un joueur peut avoir plusieurs bateaux à lui (cheats addsub/adddest).
// localBoats[] est la liste de tous ses bateaux ; activeBoatIndex pointe sur celui que
// le joueur pilote. Les autres sont en autopilote serveur. Le bateau primaire est
// localBoats[0] avec ghostSid=null. Les secondaires ont un ghostSid (string opaque).
let localBoat = null;
let viewedBoat = null;
const remoteBoats = {};
let localBoats = [];           // [{ ghostSid, playerId, boat, sunk }]
let activeBoatIndex = 0;
const boatAmmo = {};           // ghostSidOrPrimary -> { torpedo, drone, grenade, cannon, beacon, lure, mine }
function activeBoat() { return localBoats[activeBoatIndex] || null; }
function activeGhostSid() {
    const a = activeBoat();
    return a ? a.ghostSid : null;
}
// Wrapper utilisé sur tous les socket.emit d'intents : ajoute bsid si bateau secondaire.
function withBsid(payload) {
    const b = activeGhostSid();
    if (b) payload.bsid = b;
    return payload;
}
// Clé d'ammo : "primary" pour le bateau primaire (ghostSid null), sinon le ghostSid.
function ammoKey(ghostSid) { return ghostSid || "primary"; }
function isViewingLocal() { return viewedBoat === localBoat || viewedBoat == null; }
function viewedBotId() { return isViewingLocal() ? null : (viewedBoat && viewedBoat.id) || null; }
let originalBoatData = null;
let originalBoatType = null;

class Boat {
    constructor(opts) {
        this.id = opts.id || null;             // null pour localBoat ; sid pour remotes
        this.isLocal = !!opts.isLocal;
        this.boatType = opts.boatType || null;
        this.boatData = opts.boatData || null; // JSON spec brut
        this.mesh = opts.mesh || null;         // wrapper TransformNode
        this.modelRotationOffset = (opts.boatData && opts.boatData.modelRotationOffset) || 0;
        this.lengthMeters = (opts.boatData && opts.boatData.lengthMeters) || 100;
        this.halfLength = 2;
        this.halfWidth = 1;
        // dynamique pilotage
        this.boatSpeed = 0;
        this.rudderAngle = 0;
        this.diveRate = 0;
        this.periscopeTarget = null;
        this.boatIntegrity = 100;
        this.isSinking = false;
        this.sinkTilt = 0;
        this.sinkTiltAxis = 1;
        // specs
        const b = opts.boatData || {};
        this.maxSpeed = knotsToUnitPerSecond(b.speed || 0);
        this.baseSpeed = this.maxSpeed / 2;
        this.reverseMaxSpeed = this.maxSpeed / 2;
        this.baseNoise = b.noise || 0;
        this.speedNoiseLimit = typeof b.speedNoiseLimit === "number" ? b.speedNoiseLimit : 0;
        this.flotationY = -metersToUnits(typeof b.flotation === "number" ? b.flotation : 2);
        this.maxDiveDepth = typeof b.maxDepthMeters === "number"
            ? -metersToUnits(Math.min(b.maxDepthMeters, 495)) : -metersToUnits(300);
        this.radarRangeUnits = typeof b.radarRangeMeters === "number" ? metersToUnits(b.radarRangeMeters) : metersToUnits(30000);
        const as = b.activeSonar || {};
        this.sonarReveal = metersToUnits(as.reveal || 15000);
        this.sonarShortAngleDeg = typeof as.shortAngle === "number" ? as.shortAngle : 30;
        this.sonarLargeAngleDeg = typeof as.largeAngle === "number" ? as.largeAngle : 120;
        this.sonarShortRange = metersToUnits(as.shortAngleRange || 5000);
        this.sonarLargeRange = metersToUnits(as.largeAngleRange || 2500);
        // armes / consommables (initialisés depuis le JSON)
        const t = b.torpedoes || {};
        this.torpedoCounts = {
            acoustic: (t.acoustic && t.acoustic.count) || 0,
            wireGuided: (t.wireGuided && t.wireGuided.count) || 0,
            autonomous: (t.autonomous && t.autonomous.count) || 0,
        };
        this.torpedoStats = {
            acoustic:   { speed: 50, minTurnRadius: 400, damage: 60, activation: 200, maxRangeMeters: 10000 },
            wireGuided: { speed: 35, minTurnRadius: 300, damage: 60, activation: 200, maxRangeMeters: 10000 },
            autonomous: { speed: 55, minTurnRadius: 500, damage: 60, activation: 200, maxRangeMeters: 10000, radarRangeMeters: 2000, radarConeDeg: 30 },
        };
        for (const kind of ["acoustic", "wireGuided", "autonomous"]) {
            if (t[kind]) {
                this.torpedoStats[kind] = {
                    speed: t[kind].speed || this.torpedoStats[kind].speed,
                    minTurnRadius: t[kind].minTurnRadius || this.torpedoStats[kind].minTurnRadius,
                    damage: typeof t[kind].damage === "number" ? t[kind].damage : (this.torpedoStats[kind].damage || 50),
                    activation: typeof t[kind].activation === "number" ? t[kind].activation : (this.torpedoStats[kind].activation || 0),
                    maxRangeMeters: typeof t[kind].maxRangeMeters === "number" ? t[kind].maxRangeMeters : (this.torpedoStats[kind].maxRangeMeters || 10000),
                    radarRangeMeters: typeof t[kind].radarRangeMeters === "number" ? t[kind].radarRangeMeters : (this.torpedoStats[kind].radarRangeMeters || 0),
                    radarConeDeg: typeof t[kind].radarConeDeg === "number" ? t[kind].radarConeDeg : (this.torpedoStats[kind].radarConeDeg || 30),
                };
            }
        }
        const lure = b.acousticLures || null;
        this.acousticLureSpec = lure
            ? { number: lure.number || 0, time: lure.time || 0, noise: lure.noise || 0 }
            : { number: 0, time: 0, noise: 0 };
        this.acousticLureCount = this.acousticLureSpec.number;
        const grenade = b.grenade || null;
        this.grenadeDamage = grenade && typeof grenade.damage === "number" ? grenade.damage : 50;
        this.grenadeCount = grenade && typeof grenade.number === "number" ? grenade.number : 0;
        this.grenadeEffectDistance = grenade && typeof grenade.effectRangeMeters === "number"
            ? metersToUnits(grenade.effectRangeMeters) : metersToUnits(200);
        this.grenadeSinkSpeed = grenade && typeof grenade.sinkSpeedMs === "number"
            ? metersToUnits(grenade.sinkSpeedMs) : metersToUnits(4);
        const beacon = b.sonarBeacons || null;
        this.sonarBeaconSpec = beacon
            ? { number: beacon.number || 0, pingIntervalSec: beacon.pingIntervalSec || 30, rangeMeters: beacon.rangeMeters || 5000 }
            : { number: 0, pingIntervalSec: 30, rangeMeters: 5000 };
        this.sonarBeaconCount = this.sonarBeaconSpec.number;
        this.droneSpecs = { automatic: b.automaticDrone || null, manual: b.manualDrone || null };
        this.droneCounts = {
            automatic: (this.droneSpecs.automatic && this.droneSpecs.automatic.number) || 0,
            manual: (this.droneSpecs.manual && this.droneSpecs.manual.number) || 0,
        };
        this.cannonSpec = b.cannon || null;
        this.aaSpec = b.antiAircraft || null;
        this.cannonAmmo = (this.cannonSpec && this.cannonSpec.ammunition) || 0;
        this.aaAmmo = (this.aaSpec && this.aaSpec.ammunition) || 0;
    }
    get position() { return this.mesh ? this.mesh.position : null; }
    get rotation() { return this.mesh ? this.mesh.rotation.y : 0; }
}
let rudderAngle = 0;
const RUDDER_SPEED = 0.0004;
const RUDDER_MAX = 0.006;
let maxSpeed = 0;
let baseSpeed = 0;
let reverseMaxSpeed = 0;
let localBoatBaseNoise = 0;
let localBoatMinNoise = 0;
let localSpeedNoiseLimit = 0;
let localPassiveMinNoise = 5.0;
const THROTTLE_ACCEL = 0.0001 * 60 * 60;
let autoDecelerate = false;
let worldData = null;
let currentBoatType = "";
let diveRate = 0;
const DIVE_SPEED = 0.0001;
const DIVE_MAX = 0.02;
const PERISCOPE_DEPTH = -metersToUnits(5);
const SEABED_DEPTH_METERS = 500;
const SEABED_FLOOR_Y = -metersToUnits(SEABED_DEPTH_METERS - 10);
let maxDiveDepth = -metersToUnits(300);
let boatFlotationY = -metersToUnits(2);
let clearWater = false;
let mediumWater = true;  // cheat "water" : fog intermédiaire entre normal et clear
let lastSubSubmerged = false;
let periscopeTarget = null;
let oceanMesh = null;
let seabedMesh = null;
const thermoclineMeshes = [];  // plans semi-transparents (couches thermiques)
let thermoclineSpecs = [];     // specs utilisées (pour affichage radar temporaire)
const wakePoints = [];
const boatMaterials = [];
let currentBoatTint = 1;
const WAKE_LIFETIME = 5000;
let lastWakeTime = 0;
const WAKE_INTERVAL = 60;            // bateau joueur (sillage dense)
const WAKE_INTERVAL_REMOTE = 140;    // bateaux distants (moins dense → moins de meshes)
const MAX_WAKE_POINTS = 700;         // plafond global de meshes de sillage
const WAKE_REMOTE_MAX_DIST_U = 400;  // pas de sillage pour un bateau distant au-delà (~4 km)
let dangerZones = [];
let boatIntegrity = 100;
let damageFlashUntil = 0;
let isSinking = false;
let sinkTiltAxis = 1;
let sinkTilt = 0;
const grenades = [];
const GRENADE_GRAVITY = 18;
const GRENADE_INITIAL_VY = 5;
let grenadeSinkSpeed = metersToUnits(4);
const EXPLOSION_DURATION = 0.9;
let grenadeEffectDistance = metersToUnits(200);
let grenadeDamage = 50;
let grenadeCount = 0;
let grenadeRangeMeters = 1000;
let grenadeVolleyNumber = 3;
let grenadeAiming = false;
let torpedoCounts = { acoustic: 0, wireGuided: 0, autonomous: 0 };
let torpedoInitialCounts = { acoustic: 0, wireGuided: 0, autonomous: 0 };
let torpedoStats = {
    acoustic:   { speed: 50, minTurnRadius: 400, damage: 60, activation: 200, maxRangeMeters: 10000 },
    wireGuided: { speed: 35, minTurnRadius: 300, damage: 60, activation: 200, maxRangeMeters: 10000 },
    autonomous: { speed: 55, minTurnRadius: 500, damage: 60, activation: 200, maxRangeMeters: 10000, radarRangeMeters: 2000, radarConeDeg: 30 },
};
const remoteTorpedoes = {};
let remoteTorpedoMaterial = null;
let torpedoRadarRangeUnits = metersToUnits(30000);
let aimingTorpedoKind = null;
const acquisitionPreviews = [];
let acousticLureCount = 0;
let sonarBeaconSpec = { number: 0, pingIntervalSec: 30, rangeMeters: 5000 };
let sonarBeaconCount = 0;
const sonarBeacons = {};
// Balises sonar passives : ne pingent pas, détectent en continu.
let passiveSonarBeaconSpec = { number: 0, minNoise: 20 };
let passiveSonarBeaconCount = 0;
const passiveSonarBeacons = {};
// Détections passives reçues : map detectedId → { until, x, z } pour
// révéler le bateau ennemi pendant SONAR_PERSIST_DURATION.
const passiveSonarDetectionsUntil = {};
// Mines : index par "ownerId:mid" pour gérer collisions entre joueurs.
const mines = {};
let mineSpec = {
    surface:   { number: 0, delay: 1, damage: 60, range: 40 },
    bottom:    { number: 0, delay: 1, damage: 60, range: 40 },
    suspended: { number: 0, delay: 1, damage: 60, range: 40 },
};
let mineCounts = { surface: 0, bottom: 0, suspended: 0 };
let mineInitialCounts = { surface: 0, bottom: 0, suspended: 0 };
let selectedMineKey = null;

let droneSpecs = { automatic: null, manual: null };
let droneCounts = { automatic: 0, manual: 0 };
let cannonSpec = null;
let aaSpec = null;
let cannonAmmo = 0;
let aaAmmo = 0;
const CANNON_SHELL_SPEED_MS = 500;
const AA_BULLET_SPEED_MS = 1000;
// cannonShells supprimé : la détection d'impact est désormais 100% serveur.
const cannonTracers = [];
const activeDrones = [];
let activeManualDrone = null;
let activeWireTorpedoKey = null;
let lastWireSteerYaw = 0;
let lastWirePitch = 0;
const remoteDrones = {};
let manualDroneControl = false;
let droneCamera = null;
let savedCameraBeforeDrone = null;
let dronePitch = 0;
const DRONE_PITCH_MIN = 0;
const DRONE_PITCH_MAX = Math.PI / 2 - 0.05;
const DRONE_PITCH_SENSITIVITY = 0.005;
let lastDroneSteer = { yaw: 0, throttle: 0, climb: 0 };
let acousticLureSpec = { number: 0, time: 0, noise: 0 };
const acousticLures = {};
const NOISE_BUFFER_MS = 600;
const NOISE_DETECTION_THRESHOLD = 0.5;
const otherPlayersHistory = {};
const otherPlayersInfo = {};
let lastMoveEmit = 0;
const MOVE_EMIT_INTERVAL_NORMAL = 50;   // 20 Hz réseau rapide
const MOVE_EMIT_INTERVAL_SLOW   = 100;  // 10 Hz réseau lent (>200ms RTT)
let MOVE_EMIT_INTERVAL = MOVE_EMIT_INTERVAL_NORMAL;
// Diag fluidité : intervalles entre player_moved par id.
const moveArrivalDiag = {};
window.dumpMoveDiag = function () {
    const out = {};
    for (const id in moveArrivalDiag) {
        const d = moveArrivalDiag[id];
        if (!d.intervals.length) continue;
        const arr = d.intervals.slice().sort((a, b) => a - b);
        const sum = arr.reduce((s, v) => s + v, 0);
        const mean = sum / arr.length;
        const median = arr[Math.floor(arr.length / 2)];
        const p95 = arr[Math.min(arr.length - 1, Math.floor(arr.length * 0.95))];
        const max = arr[arr.length - 1];
        const min = arr[0];
        out[id] = { count: arr.length, min: min.toFixed(0), median: median.toFixed(0), mean: mean.toFixed(0), p95: p95.toFixed(0), max: max.toFixed(0) };
    }
    console.table(out);
    return out;
};
window.resetMoveDiag = function () {
    for (const id in moveArrivalDiag) delete moveArrivalDiag[id];
    console.log("moveArrivalDiag cleared");
};
let fpsOverlayEl = null;
let fpsOverlayInterval = 0;
const fpsDtSamples = [];
let fpsLastSampleAt = 0;
function fpsRecordDt(now) {
    if (fpsLastSampleAt) {
        const dt = now - fpsLastSampleAt;
        fpsDtSamples.push(dt);
        if (fpsDtSamples.length > 240) fpsDtSamples.shift();
    }
    fpsLastSampleAt = now;
}

// Compteur de messages réseau reçus (diagnostic backlog WebSocket). onAny capte
// TOUS les events entrants sans toucher aux handlers. _netMsgCount est remis à
// zéro par l'overlay FPS pour calculer un débit msg/s.
let _netMsgCount = 0;
let _netMsgByName = {};
if (socket && typeof socket.onAny === "function") {
    socket.onAny((name) => {
        _netMsgCount++;
        _netMsgByName[name] = (_netMsgByName[name] || 0) + 1;
    });
}
function _fallbackCopy(txt) {
    try {
        const ta = document.createElement("textarea");
        ta.value = txt;
        ta.style.cssText = "position:fixed;top:-1000px;left:-1000px;";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
    } catch (_) { /* ignore */ }
}
function toggleFpsOverlay() {
    if (fpsOverlayEl) {
        clearInterval(fpsOverlayInterval);
        fpsOverlayEl.remove();
        fpsOverlayEl = null;
        fpsDtSamples.length = 0;
        fpsLastSampleAt = 0;
        return;
    }
    fpsOverlayEl = document.createElement("div");
    fpsOverlayEl.style.cssText = "position:absolute;top:6px;left:8px;background:rgba(0,0,0,0.6);color:#0f0;padding:4px 8px;border-radius:4px;font-family:monospace;font-size:12px;line-height:1.35;z-index:50;pointer-events:auto;cursor:pointer;white-space:nowrap";
    fpsOverlayEl.title = "Cliquer pour copier ces stats dans le presse-papier";
    // Clic = copie du contenu (texte brut) dans le presse-papier.
    fpsOverlayEl.addEventListener("click", () => {
        const txt = fpsOverlayEl.innerText || fpsOverlayEl.textContent || "";
        const done = () => {
            const old = fpsOverlayEl.style.background;
            fpsOverlayEl.style.background = "rgba(0,80,0,0.85)";
            setTimeout(() => { if (fpsOverlayEl) fpsOverlayEl.style.background = old; }, 600);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(txt).then(done).catch(() => {
                // Fallback (contexte non sécurisé / permission refusée).
                _fallbackCopy(txt); done();
            });
        } else {
            _fallbackCopy(txt); done();
        }
    });
    document.body.appendChild(fpsOverlayEl);
    fpsOverlayInterval = setInterval(() => {
        if (!fpsOverlayEl) return;
        const fps = engine ? engine.getFps() : 0;
        const ms = engine ? engine.getDeltaTime() : 0;
        let dtMin = 0, dtMed = 0, dtMax = 0, dtP95 = 0;
        if (fpsDtSamples.length > 5) {
            const arr = fpsDtSamples.slice().sort((a, b) => a - b);
            dtMin = arr[0];
            dtMed = arr[Math.floor(arr.length / 2)];
            dtP95 = arr[Math.floor(arr.length * 0.95)];
            dtMax = arr[arr.length - 1];
        }
        let nWrappers = 0;
        if (scene && scene.transformNodes) {
            for (let i = 0; i < scene.transformNodes.length; i++) {
                if (scene.transformNodes[i].name && scene.transformNodes[i].name.indexOf("other_") === 0) nWrappers++;
            }
        }
        const nKnown = Object.keys(otherPlayers).length;
        // Stats du bot/joueur le plus proche.
        let closestId = null, closestDist = Infinity;
        if (localBoat && localBoat.mesh) {
            const lm = localBoat.mesh;
            for (const id in otherPlayers) {
                const op = otherPlayers[id];
                const dx = op.position.x - lm.position.x;
                const dz = op.position.z - lm.position.z;
                const d = dx * dx + dz * dz;
                if (d < closestDist) { closestDist = d; closestId = id; }
            }
        }
        let line3 = "";
        if (closestId) {
            const distM = Math.sqrt(closestDist) * UNIT_METERS;
            const mv = moveArrivalDiag[closestId];
            let mvStr = "n/a";
            if (mv && mv.intervals.length > 5) {
                const a = mv.intervals.slice().sort((x, y) => x - y);
                mvStr = a[0].toFixed(0) + "/" + a[Math.floor(a.length/2)].toFixed(0) + "/" + a[Math.floor(a.length*0.95)].toFixed(0) + "/" + a[a.length-1].toFixed(0);
            }
            const wd = wrapperFrameDeltas[closestId];
            let wdStr = "n/a";
            if (wd && wd.length > 5) {
                const a = wd.slice().sort((x, y) => x - y);
                const zeros = wd.filter(v => v < 1e-5).length;
                wdStr = a[Math.floor(a.length/2)].toFixed(3) + "/" + a[Math.floor(a.length*0.95)].toFixed(3) + "/" + a[a.length-1].toFixed(3) + " z=" + zeros;
            }
            line3 = "near " + closestId + " @" + distM.toFixed(0) + "m<br>"
                + "  pkt min/med/p95/max ms: " + mvStr + "<br>"
                + "  wrap med/p95/max u (zeros): " + wdStr;
        }
        const transport = (socket && socket.io && socket.io.engine && socket.io.engine.transport && socket.io.engine.transport.name) || "?";
        // Débit réseau : msg/s depuis le dernier tick d'overlay (200 ms).
        const elapsedS = 0.2;
        const msgRate = Math.round(_netMsgCount / elapsedS);
        // Top 2 events les plus fréquents sur l'intervalle.
        const topEv = Object.entries(_netMsgByName).sort((a, b) => b[1] - a[1]).slice(0, 2)
            .map(e => e[0] + ":" + e[1]).join(" ");
        _netMsgCount = 0;
        _netMsgByName = {};
        // Total meshes scène (repère une accumulation : traînées, explosions…).
        const nMeshes = scene ? scene.meshes.length : 0;
        const nMaterials = scene ? scene.materials.length : 0;
        const nTorps = Object.keys(remoteTorpedoes).length;
        const connected = socket && socket.connected ? "ok" : "DISCONNECTED";
        fpsOverlayEl.innerHTML = "FPS " + fps.toFixed(0) + " (last " + ms.toFixed(1) + " ms)<br>"
            + "dt min/med/p95/max: " + dtMin.toFixed(1) + " / " + dtMed.toFixed(1) + " / " + dtP95.toFixed(1) + " / " + dtMax.toFixed(1) + "<br>"
            + "transport: " + transport + " [" + connected + "]  wrappers: " + nWrappers + "  known: " + nKnown + "<br>"
            + "net: " + msgRate + " msg/s  (" + topEv + ")<br>"
            + "meshes: " + nMeshes + "  materials: " + nMaterials + "  torps: " + nTorps + "  trails: " + torpedoTrailPointCount + "<br>"
            + line3;
    }, 200);
}
let sunLight = null;
let ambientLight = null;
let sunMesh = null;
let timeOfDay = 0;
let DAY_DURATION = 1800;
let dayCycleState = "off";
let dayCycleStartedAt = 0;
let dayCycleStartTimeOfDay = 0;
let dayCycleSpeed = 1;
let dayCycleEndsAt = 0;
let dayCycleClockOffset = 0;
let dayCycleDoneSignaled = false;

function pointInPolygon(x, z, points) {
    let inside = false;
    const n = points.length;
    let j = n - 1;
    for (let i = 0; i < n; i++) {
        const xi = points[i].x, zi = points[i].z;
        const xj = points[j].x, zj = points[j].z;
        if (((zi > z) !== (zj > z)) && (x < (xj - xi) * (z - zi) / (zj - zi) + xi)) {
            inside = !inside;
        }
        j = i;
    }
    return inside;
}

function distancePointSegment(px, pz, ax, az, bx, bz) {
    const dx = bx - ax;
    const dz = bz - az;
    const lenSq = dx * dx + dz * dz;
    let t = lenSq > 0 ? ((px - ax) * dx + (pz - az) * dz) / lenSq : 0;
    t = Math.max(0, Math.min(1, t));
    const cx = ax + t * dx;
    const cz = az + t * dz;
    const ex = px - cx;
    const ez = pz - cz;
    return Math.sqrt(ex * ex + ez * ez);
}

function isInDangerZone(x, z) {
    for (const zone of dangerZones) {
        if (pointInPolygon(x, z, zone.outer) && !pointInPolygon(x, z, zone.inner)) {
            return true;
        }
    }
    return false;
}

function isBoatInDangerZone(x, z, rotation) {
    const cosR = Math.cos(rotation);
    const sinR = Math.sin(rotation);
    const halfOffset = boatHalfLength / 2;
    const samples = [
        { x: x - cosR * halfOffset, z: z + sinR * halfOffset },
        { x: x + cosR * halfOffset, z: z - sinR * halfOffset },
    ];
    for (const s of samples) {
        if (isInDangerZone(s.x, s.z)) return true;
    }
    return false;
}

function isPositionBlocked(x, z, rotation) {
    if (!worldData || !worldData.islands) return false;
    const radius = currentBoatType === "submarine" ? boatHalfLength / 16 : boatHalfLength / 8;
    const cosR = Math.cos(rotation);
    const sinR = Math.sin(rotation);
    const halfOffset = boatHalfLength / 2;
    const samples = [
        { x: x - cosR * halfOffset, z: z + sinR * halfOffset },
        { x: x + cosR * halfOffset, z: z - sinR * halfOffset },
    ];
    for (const island of worldData.islands) {
        const pts = island.points;
        for (const s of samples) {
            if (pointInPolygon(s.x, s.z, pts)) return true;
            for (let i = 0; i < pts.length; i++) {
                const a = pts[i];
                const b = pts[(i + 1) % pts.length];
                if (distancePointSegment(s.x, s.z, a.x, a.z, b.x, b.z) < radius) return true;
            }
        }
    }
    return false;
}

const radarCanvas = document.getElementById("radar");
const radarCtx = radarCanvas.getContext("2d");
radarCanvas.width = 450;
radarCanvas.height = 225;
let radarZoom = 1;
let radarCenterX = 0;
let radarCenterZ = 0;

function radarView() {
    const worldW = worldData.ground.width;
    const worldD = worldData.ground.depth;
    const viewW = worldW / radarZoom;
    const viewD = worldD / radarZoom;
    const sX = radarCanvas.width / viewW;
    const sZ = radarCanvas.height / viewD;
    return { worldW, worldD, viewW, viewD, cX: radarCenterX, cZ: radarCenterZ, sX, sZ };
}

function worldToRadar(x, z, v) {
    return {
        x: radarCanvas.width / 2 - (x - v.cX) * v.sX,
        y: radarCanvas.height / 2 + (z - v.cZ) * v.sZ,
    };
}

function radarToWorld(canvasX, canvasY, v) {
    return {
        x: v.cX - (canvasX - radarCanvas.width / 2) / v.sX,
        z: v.cZ + (canvasY - radarCanvas.height / 2) / v.sZ,
    };
}

let radarDrag = null;

radarCanvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !worldData) return;
    const rect = radarCanvas.getBoundingClientRect();
    radarDrag = {
        startX: e.clientX,
        startY: e.clientY,
        lastX: e.clientX,
        lastY: e.clientY,
        scaleW: radarCanvas.width / rect.width,
        scaleH: radarCanvas.height / rect.height,
        dragging: false,
        pointerId: e.pointerId,
    };
    try { radarCanvas.setPointerCapture(e.pointerId); } catch (_) {}
});

radarCanvas.addEventListener("pointermove", (e) => {
    if (!radarDrag || !worldData) return;
    const dx = e.clientX - radarDrag.startX;
    const dy = e.clientY - radarDrag.startY;
    if (!radarDrag.dragging && Math.sqrt(dx * dx + dy * dy) >= 4) {
        radarDrag.dragging = true;
    }
    if (radarDrag.dragging) {
        const v = radarView();
        const moveX = (e.clientX - radarDrag.lastX) * radarDrag.scaleW;
        const moveY = (e.clientY - radarDrag.lastY) * radarDrag.scaleH;
        radarCenterX -= -moveX / v.sX;
        radarCenterZ -= moveY / v.sZ;
        const halfW = v.viewW / 2;
        const halfD = v.viewD / 2;
        radarCenterX = Math.max(-v.worldW / 2 + halfW, Math.min(v.worldW / 2 - halfW, radarCenterX));
        radarCenterZ = Math.max(-v.worldD / 2 + halfD, Math.min(v.worldD / 2 - halfD, radarCenterZ));
        radarDrag.lastX = e.clientX;
        radarDrag.lastY = e.clientY;
    }
});

function endRadarDrag(e) {
    if (!radarDrag) return;
    if (radarDrag.dragging) radarDraggedRecently = true;
    try { radarCanvas.releasePointerCapture(radarDrag.pointerId); } catch (_) {}
    radarDrag = null;
}
radarCanvas.addEventListener("pointerup", endRadarDrag);
radarCanvas.addEventListener("pointercancel", endRadarDrag);

radarCanvas.addEventListener("wheel", (e) => {
    if (!worldData) return;
    e.preventDefault();
    const rect = radarCanvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (radarCanvas.width / rect.width);
    const my = (e.clientY - rect.top) * (radarCanvas.height / rect.height);
    const before = radarToWorld(mx, my, radarView());
    const factor = e.deltaY < 0 ? 1.25 : 1 / 1.25;
    radarZoom = Math.max(1, Math.min(100, radarZoom * factor));
    if (radarZoom <= 1) {
        radarZoom = 1;
        radarCenterX = 0;
        radarCenterZ = 0;
        return;
    }
    const after = radarToWorld(mx, my, radarView());
    radarCenterX += before.x - after.x;
    radarCenterZ += before.z - after.z;
    const v = radarView();
    const halfW = v.viewW / 2;
    const halfD = v.viewD / 2;
    radarCenterX = Math.max(-v.worldW / 2 + halfW, Math.min(v.worldW / 2 - halfW, radarCenterX));
    radarCenterZ = Math.max(-v.worldD / 2 + halfD, Math.min(v.worldD / 2 - halfD, radarCenterZ));
}, { passive: false });

let radarDraggedRecently = false;
radarCanvas.addEventListener("click", (e) => {
    if (!worldData) return;
    if (radarDraggedRecently) { radarDraggedRecently = false; return; }
    const rect = radarCanvas.getBoundingClientRect();
    const cx = (e.clientX - rect.left) * (radarCanvas.width / rect.width);
    const cz = (e.clientY - rect.top) * (radarCanvas.height / rect.height);
    const v = radarView();
    const w = radarToWorld(cx, cz, v);
    const worldX = w.x;
    const worldZ = w.z;
    if (cheatMoveMode && playerMesh) {
        let onIsland = false;
        if (worldData.islands) {
            for (const isl of worldData.islands) {
                if (pointInPolygon(worldX, worldZ, isl.points)) { onIsland = true; break; }
            }
        }
        if (onIsland) {
            setTransientMessage("Position invalide (île)");
        } else {
            playerMesh.position.x = worldX;
            playerMesh.position.z = worldZ;
            boatSpeed = 0;
            setTransientMessage("Téléporté");
            cheatMoveMode = false;
        }
        return;
    }
    if (aimingTorpedoKind) {
        const dx = worldX - playerMesh.position.x;
        const dz = worldZ - playerMesh.position.z;
        const activationMeters = Math.sqrt(dx * dx + dz * dz) * UNIT_METERS;
        socket.emit("torpedo_fire", withBsid({ kind: aimingTorpedoKind, fixedTarget: { x: worldX, z: worldZ }, activationMeters }));
        cancelAim();
        return;
    }
    if (grenadeAiming) {
        fireGrenadeAtWorldPos(worldX, worldZ);
        cancelGrenadeAiming();
        return;
    }
    let bestBoat = null;
    let bestBoatDist = Infinity;
    for (const b of radarFrozenBoats) {
        const o = worldToRadar(b.x, b.z, v);
        const dx = o.x - cx;
        const dz = o.y - cz;
        const d = Math.sqrt(dx * dx + dz * dz);
        if (d < bestBoatDist) { bestBoatDist = d; bestBoat = b.id; }
    }
    let bestBeacon = null;
    let bestBeaconDist = Infinity;
    for (const bid in sonarBeacons) {
        const b = sonarBeacons[bid];
        const o = worldToRadar(b.x, b.z, v);
        const dx = o.x - cx;
        const dz = o.y - cz;
        const d = Math.sqrt(dx * dx + dz * dz);
        if (d < bestBeaconDist) { bestBeaconDist = d; bestBeacon = parseInt(bid, 10); }
    }
    let bestDrone = null;
    let bestDroneDist = Infinity;
    const droneRadarMax = torpedoRadarRangeUnits / 10;
    const droneRadarMax2 = droneRadarMax * droneRadarMax;
    const subSubmerged = currentBoatType === "submarine" && playerMesh && playerMesh.position.y < PERISCOPE_DEPTH;
    if (!subSubmerged) {
        for (const key in remoteDrones) {
            const r = remoteDrones[key];
            const ddx = r.x - playerMesh.position.x;
            const ddz = r.z - playerMesh.position.z;
            if (ddx * ddx + ddz * ddz > droneRadarMax2) continue;
            if (!isLineOfSightClear(r.x, r.z, null)) continue;
            const o = worldToRadar(r.x, r.z, v);
            const dx = o.x - cx;
            const dz = o.y - cz;
            const d = Math.sqrt(dx * dx + dz * dz);
            if (d < bestDroneDist) { bestDroneDist = d; bestDrone = key; }
        }
    }
    let bestLocalDrone = null;
    let bestLocalDroneDist = Infinity;
    if (!subSubmerged) {
        for (const d of activeDrones) {
            const o = worldToRadar(d.x, d.z, v);
            const ddx = o.x - cx;
            const ddz = o.y - cz;
            const dd = Math.sqrt(ddx * ddx + ddz * ddz);
            if (dd < bestLocalDroneDist) { bestLocalDroneDist = dd; bestLocalDrone = d.did; }
        }
    }
    let bestMine = null;
    let bestMineDist = Infinity;
    for (const key in mines) {
        const m = mines[key];
        if (!isMineVisibleOnRadar(m, key)) continue;
        const o = worldToRadar(m.x, m.z, v);
        const dx = o.x - cx;
        const dz = o.y - cz;
        const d = Math.sqrt(dx * dx + dz * dz);
        if (d < bestMineDist) { bestMineDist = d; bestMine = key; }
    }
    let bestTorpKey = null;
    let bestTorpDist = Infinity;
    for (const key in remoteTorpedoes) {
        const r = remoteTorpedoes[key];
        if (!allMapMode) {
            const ddx = r.x - playerMesh.position.x;
            const ddz = r.z - playerMesh.position.z;
            if (ddx * ddx + ddz * ddz > torpedoRadarRangeUnits * torpedoRadarRangeUnits) continue;
            if (r.ownerId !== playerId && !isLineOfSightClear(r.x, r.z, null)) continue;
            if (r.mesh && !r.mesh.isEnabled()) continue;
        }
        const o = worldToRadar(r.x, r.z, v);
        const dx = o.x - cx;
        const dz = o.y - cz;
        const d = Math.sqrt(dx * dx + dz * dz);
        if (d < bestTorpDist) { bestTorpDist = d; bestTorpKey = key; }
    }
    const minDist = Math.min(bestDroneDist, bestBoatDist, bestBeaconDist, bestLocalDroneDist, bestMineDist, bestTorpDist);
    const clearAll = () => {
        selectedBoatId = null;
        selectedBoatIsSonar = false;
        selectedDroneKey = null;
        selectedBeaconBid = null;
        selectedLocalDroneDid = null;
        selectedTorpedoKey = null;
        selectedMineKey = null;
    };
    if (minDist > 10) {
        clearAll();
    } else if (bestTorpDist === minDist) {
        clearAll();
        selectedTorpedoKey = "remote:" + bestTorpKey;
        tryResumeWireControl(bestTorpKey);
    } else if (bestMineDist === minDist) {
        clearAll();
        selectedMineKey = bestMine;
    } else if (bestLocalDroneDist === minDist) {
        clearAll();
        selectedLocalDroneDid = bestLocalDrone;
    } else if (bestBeaconDist === minDist) {
        clearAll();
        selectedBeaconBid = bestBeacon;
    } else if (bestDroneDist === minDist) {
        clearAll();
        selectedDroneKey = bestDrone;
    } else {
        clearAll();
        selectedBoatId = bestBoat;
        const sel = radarFrozenBoats.find(b => b.id === bestBoat);
        selectedBoatIsSonar = !!(sel && sel.sonar);
    }
});
let selectedBoatIsSonar = false;

function createScene() {
    scene = new BABYLON.Scene(engine);
    scene.clearColor = new BABYLON.Color3(0.5, 0.7, 0.9);

    new BABYLON.FreeCamera("defaultCam", new BABYLON.Vector3(0, 5, -10), scene);

    ambientLight = new BABYLON.HemisphericLight("light", new BABYLON.Vector3(0, 1, 0), scene);
    ambientLight.intensity = 1.0;
    ambientLight.groundColor = new BABYLON.Color3(0.4, 0.4, 0.4);

    sunLight = new BABYLON.DirectionalLight("sunLight", new BABYLON.Vector3(-1, -2, -1), scene);
    sunLight.intensity = 0.5;

    sunMesh = BABYLON.MeshBuilder.CreateSphere("sun", { diameter: 80 }, scene);
    const sunMat = new BABYLON.StandardMaterial("sunMat", scene);
    sunMat.emissiveColor = new BABYLON.Color3(1, 0.9, 0.3);
    sunMat.disableLighting = true;
    sunMesh.material = sunMat;
    sunMesh.isVisible = false;

    return scene;
}

function resetDayLighting() {
    sunLight.intensity = 0.5;
    sunLight.diffuse = new BABYLON.Color3(1, 0.9, 0.7);
    ambientLight.intensity = 1.0;
    ambientLight.groundColor = new BABYLON.Color3(0.4, 0.4, 0.4);
    scene.clearColor = new BABYLON.Color3(0.5, 0.7, 0.9);
    sunMesh.isVisible = false;
    applyBoatNightTint(1);
}

function updateDayCycle(deltaTime) {
    const nowServer = Date.now() / 1000 + dayCycleClockOffset;
    let t;
    if (dayCycleState === "ending" && dayCycleEndsAt > 0 && nowServer >= dayCycleEndsAt) {
        t = 0.5;
        if (!dayCycleDoneSignaled) {
            dayCycleDoneSignaled = true;
            socket.emit("day_cycle_done");
        }
    } else {
        const elapsed = Math.max(0, nowServer - dayCycleStartedAt);
        t = dayCycleStartTimeOfDay + dayCycleSpeed * elapsed / DAY_DURATION;
        t = ((t % 1) + 1) % 1;
    }
    timeOfDay = t;

    const sunAngle = timeOfDay * Math.PI * 2 - Math.PI / 2;
    const sunY = Math.sin(sunAngle);
    const sunX = Math.cos(sunAngle);

    sunLight.direction = new BABYLON.Vector3(-sunX, -sunY, -0.3);

    if (playerMesh) {
        sunMesh.position.x = playerMesh.position.x + sunX * 1500;
        sunMesh.position.y = sunY * 1500;
        sunMesh.position.z = playerMesh.position.z + 500;
    }

    const dayFactor = Math.max(0, sunY);
    const sunsetFactor = Math.max(0, Math.min(1, (sunY + 0.2) * 3));

    sunLight.intensity = dayFactor * 0.8;
    ambientLight.intensity = 0.2 + dayFactor * 0.8;
    ambientLight.groundColor = new BABYLON.Color3(
        0.1 + dayFactor * 0.3,
        0.1 + dayFactor * 0.3,
        0.15 + dayFactor * 0.25
    );

    const skyR = sunY < 0 ? Math.max(0.02, 0.1 + sunY * 0.3) : 0.3 + dayFactor * 0.2;
    const skyG = sunY < 0 ? Math.max(0.02, 0.1 + sunY * 0.2) : 0.4 + dayFactor * 0.3;
    const skyB = sunY < 0 ? Math.max(0.05, 0.15 + sunY * 0.2) : 0.5 + dayFactor * 0.4;

    if (!(currentBoatType === "submarine" && playerMesh && playerMesh.position.y < -1)) {
        scene.clearColor = new BABYLON.Color3(skyR, skyG, skyB);
    }

    sunMesh.isVisible = sunY > -0.1;

    const sunColor = sunY < 0.2
        ? new BABYLON.Color3(1, 0.4 + sunY * 2, 0.1)
        : new BABYLON.Color3(1, 0.9, 0.7);
    sunLight.diffuse = sunColor;

    const boatTint = 0.05 + Math.max(0, sunY + 0.1) * 0.95;
    applyBoatNightTint(Math.min(1, boatTint));
}

function buildWorld(worldData) {
    oceanMesh = BABYLON.MeshBuilder.CreateGround("ocean", {
        width: worldData.ground.width + 200,
        height: worldData.ground.depth + 200,
        subdivisions: 1,
    }, scene);
    const oceanMat = new BABYLON.StandardMaterial("oceanMat", scene);
    oceanMat.diffuseColor = BABYLON.Color3.FromHexString("#1a6b8a");
    oceanMat.specularColor = new BABYLON.Color3(0.1, 0.1, 0.1);
    oceanMesh.material = oceanMat;
    oceanMesh.position.y = -0.1;

    seabedMesh = BABYLON.MeshBuilder.CreateGround("seabed", {
        width: worldData.ground.width + 200,
        height: worldData.ground.depth + 200,
        subdivisions: 1,
    }, scene);
    const seabedMat = new BABYLON.StandardMaterial("seabedMat", scene);
    seabedMat.diffuseTexture = new BABYLON.Texture("/images/sol2.jpg", scene);
    seabedMat.diffuseTexture.uScale = worldData.ground.width / 30;
    seabedMat.diffuseTexture.vScale = worldData.ground.depth / 30;
    seabedMat.specularColor = new BABYLON.Color3(0, 0, 0);
    seabedMat.diffuseColor = new BABYLON.Color3(0.35, 0.35, 0.35);
    seabedMat.emissiveColor = new BABYLON.Color3(0, 0, 0);
    seabedMesh.material = seabedMat;
    seabedMesh.position.y = -metersToUnits(500);
    seabedMesh.isVisible = false;

    gridMesh = BABYLON.MeshBuilder.CreateGround("grid", {
        width: worldData.ground.width,
        height: worldData.ground.depth,
        subdivisions: 50,
    }, scene);
    const gridMat = new BABYLON.StandardMaterial("gridMat", scene);
    gridMat.emissiveColor = new BABYLON.Color3(0.3, 0.5, 0.6);
    gridMat.wireframe = true;
    gridMesh.material = gridMat;
    gridMesh.position.y = 0;
    gridMesh.isVisible = false;

    if (worldData.islands) {
        worldData.islands.forEach((island, i) => {
            const shape = island.points.map(p => new BABYLON.Vector3(p.x, 0, p.z));
            const seabedY = -metersToUnits(500);
            const topY = island.height;

            const topPoly = BABYLON.MeshBuilder.CreatePolygon("island_" + i, {
                shape: shape,
            }, scene);
            topPoly.position.y = topY;
            const topTex = islandTextureName(island);
            const topMat = new BABYLON.StandardMaterial("islandTopMat_" + i, scene);
            topMat.diffuseTexture = new BABYLON.Texture(islandTextureUrl(topTex), scene);
            topMat.diffuseTexture.uScale = 3;
            topMat.diffuseTexture.vScale = 3;
            topMat.specularColor = new BABYLON.Color3(0.1, 0.1, 0.1);
            topPoly.material = topMat;

            const pts = island.points;
            const n = pts.length;
            const topPath = [];
            const bottomPath = [];
            for (let j = 0; j <= n; j++) {
                const p = pts[j % n];
                topPath.push(new BABYLON.Vector3(p.x, topY, p.z));
                bottomPath.push(new BABYLON.Vector3(p.x, seabedY, p.z));
            }
            const walls = BABYLON.MeshBuilder.CreateRibbon("islandWall_" + i, {
                pathArray: [topPath, bottomPath],
                sideOrientation: BABYLON.Mesh.DOUBLESIDE,
                closePath: false,
                closeArray: false,
            }, scene);
            // UVs proportionnels : on construit le mesh manuellement pour contrôler les UVs
            const wallHeight = topY - seabedY;
            const texScale = 10.0;
            let perimeter = 0;
            const cumDist = [0];
            for (let j = 0; j < n; j++) {
                const p0 = pts[j];
                const p1 = pts[(j + 1) % n];
                perimeter += Math.hypot(p1.x - p0.x, p1.z - p0.z);
                cumDist.push(perimeter);
            }
            const wallPositions = [];
            const wallUVs = [];
            const wallIndices = [];
            for (let j = 0; j <= n; j++) {
                const p = pts[j % n];
                const u = cumDist[j] / texScale;
                // top vertex
                wallPositions.push(p.x, topY, p.z);
                wallUVs.push(u, wallHeight / texScale);
                // bottom vertex
                wallPositions.push(p.x, seabedY, p.z);
                wallUVs.push(u, 0);
            }
            const halfW = worldData.ground.width / 2;
            const halfD = worldData.ground.depth / 2;
            for (let j = 0; j < n; j++) {
                const p0 = pts[j];
                const p1 = pts[(j + 1) % n];
                const onBorder = (Math.abs(p0.x) >= halfW && Math.abs(p1.x) >= halfW) ||
                                 (Math.abs(p0.z) >= halfD && Math.abs(p1.z) >= halfD);
                if (onBorder) continue;
                const t0 = j * 2, b0 = j * 2 + 1;
                const t1 = (j + 1) * 2, b1 = (j + 1) * 2 + 1;
                wallIndices.push(t0, b0, t1);
                wallIndices.push(t1, b0, b1);
            }
            walls.dispose();
            const wallMesh = new BABYLON.Mesh("islandWall_" + i, scene);
            const vertexData = new BABYLON.VertexData();
            vertexData.positions = new Float32Array(wallPositions);
            vertexData.uvs = new Float32Array(wallUVs);
            vertexData.indices = wallIndices;
            vertexData.applyToMesh(wallMesh, true);
            wallMesh.createNormals(false);
            const sideMat = new BABYLON.StandardMaterial("islandSideMat_" + i, scene);
            sideMat.diffuseTexture = new BABYLON.Texture("/images/sol2.jpg", scene);
            sideMat.specularColor = new BABYLON.Color3(0.1, 0.1, 0.1);
            sideMat.backFaceCulling = false;
            wallMesh.material = sideMat;

            const dangerOffset = 3;
            let cx = 0, cz = 0;
            for (const p of island.points) { cx += p.x; cz += p.z; }
            cx /= island.points.length;
            cz /= island.points.length;
            const innerPath = island.points.map(p => new BABYLON.Vector3(p.x, 0.05, p.z));
            innerPath.push(innerPath[0].clone());
            const outerPath = island.points.map(p => {
                const dx = p.x - cx;
                const dz = p.z - cz;
                const len = Math.sqrt(dx * dx + dz * dz);
                const k = len > 0 ? (len + dangerOffset) / len : 1;
                return new BABYLON.Vector3(cx + dx * k, 0.05, cz + dz * k);
            });
            outerPath.push(outerPath[0].clone());
            dangerZones.push({
                inner: island.points.map(p => ({ x: p.x, z: p.z })),
                outer: outerPath.slice(0, -1).map(v => ({ x: v.x, z: v.z })),
            });
            const dangerRibbon = BABYLON.MeshBuilder.CreateRibbon("dangerZone_" + i, {
                pathArray: [innerPath, outerPath],
                closePath: false,
                closeArray: false,
            }, scene);
            const innerColor = [0.7, 0.7, 0.7, 1];
            const outerColor = [0.7, 0.7, 0.7, 0];
            const vertexCount = (innerPath.length) * 2;
            const colors = new Float32Array(vertexCount * 4);
            for (let v = 0; v < innerPath.length; v++) {
                colors.set(innerColor, v * 4);
            }
            for (let v = 0; v < outerPath.length; v++) {
                colors.set(outerColor, (innerPath.length + v) * 4);
            }
            dangerRibbon.setVerticesData(BABYLON.VertexBuffer.ColorKind, colors);
            const dangerNormals = new Float32Array(vertexCount * 3);
            for (let n = 0; n < vertexCount; n++) {
                dangerNormals[n * 3] = 0;
                dangerNormals[n * 3 + 1] = 1;
                dangerNormals[n * 3 + 2] = 0;
            }
            dangerRibbon.setVerticesData(BABYLON.VertexBuffer.NormalKind, dangerNormals);
            const dangerMat = new BABYLON.StandardMaterial("dangerMat_" + i, scene);
            dangerMat.specularColor = new BABYLON.Color3(0, 0, 0);
            dangerMat.backFaceCulling = false;
            dangerRibbon.material = dangerMat;
            dangerRibbon.hasVertexAlpha = true;

        });
    }

    buildThermoclines(worldData);
}

// Thermoclines (couches thermiques) : plans horizontaux semi-transparents posés
// à une certaine profondeur. Visibles des deux côtés (sub au-dessus ou en
// dessous) grâce à backFaceCulling=false. Définies par worldData.thermoclines :
//   [{ points: [{x,z}, ...], depthMeters: N, opacity: 0.08, color: "#33aaff" }]
// Créées via l'éditeur admin (bouton « Thermocline »).
const THERMOCLINE_OPACITY = 0.08;
const THERMOCLINE_COLOR = "#33aaff";
const THERMOCLINE_ISLAND_MARGIN_M = 50; // marge autour des îles découpées

// Dilate un polygone d'île de `marginU` unités vers l'extérieur (depuis son
// centroïde), pour créer un trou dans la thermocline avec une marge.
function _expandIslandPolygon(points, marginU) {
    let cx = 0, cz = 0;
    for (const p of points) { cx += p.x; cz += p.z; }
    cx /= points.length; cz /= points.length;
    return points.map(p => {
        const dx = p.x - cx;
        const dz = p.z - cz;
        const len = Math.sqrt(dx * dx + dz * dz) || 1;
        const k = (len + marginU) / len;
        return { x: cx + dx * k, z: cz + dz * k };
    });
}

function buildThermoclines(worldData) {
    for (const m of thermoclineMeshes) { try { m.dispose(false, true); } catch (_) {} }
    thermoclineMeshes.length = 0;

    const specs = worldData.thermoclines || [];
    thermoclineSpecs = specs;
    const marginU = metersToUnits(THERMOCLINE_ISLAND_MARGIN_M);
    const islands = worldData.islands || [];

    for (let i = 0; i < specs.length; i++) {
        const spec = specs[i];
        if (!spec.points || spec.points.length < 3) continue;
        const y = -metersToUnits(spec.depthMeters || 50);
        const shape = spec.points.map(p => new BABYLON.Vector3(p.x, 0, p.z));
        // Trous : pour chaque île dont au moins un point est sous la thermocline,
        // on découpe son contour dilaté de 50 m (la couche ne traverse pas l'île).
        const holes = [];
        for (const isl of islands) {
            if (!isl.points || isl.points.length < 3) continue;
            const overlaps = isl.points.some(p => pointInPolygon(p.x, p.z, spec.points))
                || spec.points.some(p => pointInPolygon(p.x, p.z, isl.points));
            if (!overlaps) continue;
            const expanded = _expandIslandPolygon(isl.points, marginU);
            holes.push(expanded.map(p => new BABYLON.Vector3(p.x, 0, p.z)));
        }
        const polyOpts = {
            shape: shape,
            sideOrientation: BABYLON.Mesh.DOUBLESIDE,  // visible des deux faces
        };
        if (holes.length) polyOpts.holes = holes;
        const poly = BABYLON.MeshBuilder.CreatePolygon("thermocline_" + i, polyOpts, scene);
        // En mode admin (vue top-down, océan opaque), on surélève la couche
        // au-dessus de l'eau pour qu'elle soit visible ; en jeu, profondeur réelle.
        poly.position.y = adminMode ? 0.5 : y;
        const mat = new BABYLON.StandardMaterial("thermoclineMat_" + i, scene);
        const col = BABYLON.Color3.FromHexString(spec.color || THERMOCLINE_COLOR);
        // En admin : couleur un peu plus foncée pour bien ressortir sur la carte top-down.
        mat.diffuseColor = adminMode ? col.scale(0.7) : col;
        mat.emissiveColor = adminMode ? col.scale(0.18) : col.scale(0.25);
        mat.specularColor = new BABYLON.Color3(0, 0, 0);
        // En admin : plus opaque pour bien voir le polygone par-dessus l'océan.
        mat.alpha = adminMode ? 0.52 : ((typeof spec.opacity === "number") ? spec.opacity : THERMOCLINE_OPACITY);
        mat.backFaceCulling = false;       // rendu des deux côtés
        poly.material = mat;
        poly.isPickable = false;
        thermoclineMeshes.push(poly);
    }
}

function _disposeDroneImportResult(result) {
    if (!result) return;
    const materials = new Set();
    for (const mesh of result.meshes || []) {
        if (!mesh || !mesh.material) continue;
        materials.add(mesh.material);
        for (const mat of mesh.material.subMaterials || []) {
            if (mat) materials.add(mat);
        }
    }
    for (const group of result.animationGroups || []) group.dispose();
    for (const root of (result.meshes || []).filter(m => m && !m.parent)) root.dispose();
    for (const skeleton of result.skeletons || []) skeleton.dispose();
    for (const mat of materials) mat.dispose(false, true);
}

function disposeDroneMesh(wrapper) {
    if (!wrapper) return;
    const result = wrapper._droneImportResult || null;
    const materials = new Set();
    const meshes = result ? (result.meshes || []) : wrapper.getChildMeshes(false);
    for (const mesh of meshes) {
        if (!mesh || !mesh.material) continue;
        materials.add(mesh.material);
        for (const mat of mesh.material.subMaterials || []) {
            if (mat) materials.add(mat);
        }
    }
    if (result) {
        for (const group of result.animationGroups || []) group.dispose();
        for (const skeleton of result.skeletons || []) skeleton.dispose();
    }
    wrapper.dispose();
    for (const mat of materials) mat.dispose(false, true);
}

function makeDroneMesh(name, lengthMeters, tint) {
    const wrapper = new BABYLON.TransformNode(name, scene);
    BABYLON.SceneLoader.ImportMeshAsync("", "/models/drone/", "scene.gltf", scene).then((result) => {
        if (wrapper.isDisposed()) {
            _disposeDroneImportResult(result);
            return;
        }
        wrapper._droneImportResult = result;
        const root = result.meshes.find(m => !m.parent) || result.meshes[0];
        root.parent = wrapper;
        root.computeWorldMatrix(true);
        const bounds = root.getHierarchyBoundingVectors(true);
        const sizeX = bounds.max.x - bounds.min.x;
        const sizeY = bounds.max.y - bounds.min.y;
        const sizeZ = bounds.max.z - bounds.min.z;
        const naturalMax = Math.max(sizeX, sizeY, sizeZ);
        const targetUnits = metersToUnits(lengthMeters);
        const s = naturalMax > 0 ? targetUnits / naturalMax : 1;
        wrapper.scaling = new BABYLON.Vector3(s, s, s);
        if (tint) {
            for (const m of result.meshes) {
                if (!m.material) continue;
                const mats = m.material.subMaterials || [m.material];
                for (const mat of mats) {
                    if (!mat) continue;
                    if (mat.albedoColor) mat.albedoColor = tint.clone();
                    if (mat.diffuseColor) mat.diffuseColor = tint.clone();
                    mat.emissiveColor = tint.scale(0.4);
                }
            }
        }
    }).catch((err) => {
        console.error("Drone model load error:", err);
        if (wrapper.isDisposed()) return;
        const fallback = BABYLON.MeshBuilder.CreateBox(name + "_fb", { size: 1 }, scene);
        const mat = new BABYLON.StandardMaterial(name + "_fbMat", scene);
        mat.emissiveColor = tint ? tint.clone() : new BABYLON.Color3(0.5, 0.5, 0.5);
        fallback.material = mat;
        fallback.parent = wrapper;
        wrapper.scaling = new BABYLON.Vector3(metersToUnits(lengthMeters), metersToUnits(lengthMeters), metersToUnits(lengthMeters));
    });
    return wrapper;
}

const DRONE_COLOR_LOCAL = new BABYLON.Color3(0.2, 0.5, 1.0);
const DRONE_COLOR_REMOTE = new BABYLON.Color3(1.0, 0.5, 0.05);

function exemptFromClipPlane(mesh) {
    let saved = null;
    mesh.onBeforeRenderObservable.add(() => {
        saved = scene.clipPlane;
        scene.clipPlane = null;
    });
    mesh.onAfterRenderObservable.add(() => {
        scene.clipPlane = saved;
    });
}

// Force le clipPlane à reprendre la valeur "frame globale" avant le rendu d'un
// mesh, au cas où un autre mesh exempté l'aurait neutralisé. À utiliser sur
// les bateaux distants pour s'assurer que leur partie au-dessus de l'eau soit
// bien clippée quand le sub local est en plongée.
function applyFrameClipPlane(mesh) {
    mesh.onBeforeRenderObservable.add(() => {
        scene.clipPlane = scene.__frameClipPlane || null;
    });
}

// Cache des modèles GLTF par chemin : on charge une fois en AssetContainer
// puis on instancie pour chaque bateau. Évite le re-téléchargement de
// plusieurs MB qui bloquait eventlet côté serveur (saccades sur les bots).
const boatModelContainerCache = {};
const boatModelPending = {};
const boatModelRetryCount = {};

function loadBoatModel(modelPath, callback) {
    const cached = boatModelContainerCache[modelPath];
    if (cached) {
        callback(instantiateBoatFromContainer(cached));
        return;
    }
    if (boatModelPending[modelPath]) {
        boatModelPending[modelPath].push(callback);
        return;
    }
    boatModelPending[modelPath] = [callback];
    const path = "/" + modelPath.substring(0, modelPath.lastIndexOf("/") + 1);
    const file = modelPath.substring(modelPath.lastIndexOf("/") + 1);
    const _loadStart = performance.now();
    console.log("[startup] LoadAssetContainer start:", modelPath);
    BABYLON.SceneLoader.LoadAssetContainerAsync(path, file, scene).then((container) => {
        const elapsed = ((performance.now() - _loadStart) / 1000).toFixed(1);
        console.log("[startup] LoadAssetContainer done:", modelPath, elapsed + "s");
        if (elapsed > 3) console.warn("[loadBoatModel] slow load:", modelPath, elapsed + "s");
        boatModelContainerCache[modelPath] = container;
        delete boatModelRetryCount[modelPath];
        // Enregistrer les matériaux d'origine pour la teinte nuit, sans les ajouter
        // à la scène (le container reste détaché).
        for (const mat of container.materials) {
            if (!mat || boatMaterials.find(e => e.mat === mat)) continue;
            const baseDiffuse = mat.diffuseColor ? mat.diffuseColor.clone() : null;
            const baseAlbedo = mat.albedoColor ? mat.albedoColor.clone() : null;
            const baseEmissive = mat.emissiveColor ? mat.emissiveColor.clone() : null;
            const baseEmissiveIntensity = (typeof mat.emissiveIntensity === "number") ? mat.emissiveIntensity : null;
            const baseEnvIntensity = (typeof mat.environmentIntensity === "number") ? mat.environmentIntensity : null;
            boatMaterials.push({ mat, baseDiffuse, baseAlbedo, baseEmissive, baseEmissiveIntensity, baseEnvIntensity });
        }
        if (currentBoatTint !== 1) applyBoatNightTint(currentBoatTint);
        const cbs = boatModelPending[modelPath] || [];
        delete boatModelPending[modelPath];
        for (const cb of cbs) {
            cb(instantiateBoatFromContainer(container));
        }
    }).catch((err) => {
        console.error("Error loading model:", modelPath, err);
        const cbs = boatModelPending[modelPath] || [];
        const retryCount = (boatModelRetryCount[modelPath] || 0) + 1;
        boatModelRetryCount[modelPath] = retryCount;
        if (retryCount >= 5) {
            delete boatModelPending[modelPath];
            delete boatModelRetryCount[modelPath];
            console.error("Abandon du chargement du modèle après 5 tentatives:", modelPath);
            return;
        }
        // Garder une seule file pendant le délai évite des chaînes de retry parallèles.
        setTimeout(() => {
            const queued = boatModelPending[modelPath] || cbs;
            delete boatModelPending[modelPath];
            for (const cb of queued) loadBoatModel(modelPath, cb);
        }, 2000);
    });
}

function instantiateBoatFromContainer(container) {
    // Instancier les meshes (clone partagé géométrie + matériaux). Ajoute à la scène.
    const inst = container.instantiateModelsToScene(name => name, false);
    let root = null;
    for (const m of inst.rootNodes) {
        if (m instanceof BABYLON.AbstractMesh || m instanceof BABYLON.TransformNode) {
            root = m;
            break;
        }
    }
    if (!root) {
        // Fallback : prendre le premier node disponible.
        root = inst.rootNodes[0] || null;
    }
    if (root && typeof root.normalizeToUnitCube === "function") {
        root.normalizeToUnitCube(true);
    }
    return root;
}

function applyBoatNightTint(factor) {
    currentBoatTint = factor;
    for (const e of boatMaterials) {
        if (e.baseDiffuse && e.mat.diffuseColor) {
            e.mat.diffuseColor.copyFrom(e.baseDiffuse).scaleInPlace(factor);
        }
        if (e.baseAlbedo && e.mat.albedoColor) {
            e.mat.albedoColor.copyFrom(e.baseAlbedo).scaleInPlace(factor);
        }
        if (e.baseEmissive && e.mat.emissiveColor) {
            e.mat.emissiveColor.copyFrom(e.baseEmissive).scaleInPlace(factor);
        }
        if (e.baseEmissiveIntensity !== null) {
            e.mat.emissiveIntensity = e.baseEmissiveIntensity * factor;
        }
        if (e.baseEnvIntensity !== null) {
            e.mat.environmentIntensity = e.baseEnvIntensity * factor;
        }
    }
}

function spawnWakeDot(x, z, now, opts) {
    // Plafond global de sillages : au-delà, on recycle le plus ancien (dispose)
    // pour éviter l'accumulation de meshes (cause majeure de chute de FPS quand
    // beaucoup de bateaux sont présents).
    if (wakePoints.length >= MAX_WAKE_POINTS) {
        const old = wakePoints.shift();
        if (old) {
            if (old.mesh) old.mesh.dispose();
            if (old.mat) old.mat.dispose();
        }
    }
    opts = opts || {};
    const radius = opts.radius || 0.25;
    const yPos = (typeof opts.y === "number") ? opts.y : 0.05;
    const baseAlpha = (typeof opts.alpha === "number") ? opts.alpha : 0.6;
    const disc = BABYLON.MeshBuilder.CreateDisc("wakeDot", { radius, tessellation: 12 }, scene);
    disc.rotation.x = Math.PI / 2;
    disc.position.x = x;
    disc.position.z = z;
    disc.position.y = yPos;
    const mat = new BABYLON.StandardMaterial("wakeDotMat", scene);
    mat.emissiveColor = new BABYLON.Color3(0.5, 0.7, 0.9);
    mat.diffuseColor = new BABYLON.Color3(0, 0, 0);
    mat.specularColor = new BABYLON.Color3(0, 0, 0);
    mat.alpha = baseAlpha;
    mat.backFaceCulling = false;
    disc.material = mat;
    wakePoints.push({ mesh: disc, mat: mat, born: now, baseAlpha });
}

function createOtherPlayer(data) {
    const boatData = data.boat;
    const offset = boatData.modelRotationOffset || 0;
    // Évite la double instanciation : si on connaît déjà ce joueur, on ne recharge pas.
    if (otherPlayers[data.id]) return;
    const loadGeneration = nextOtherPlayerLoadGeneration++;
    otherPlayerLoadGeneration[data.id] = loadGeneration;
    loadBoatModel(boatData.model, (mesh) => {
        // Un départ ou un chargement plus récent invalide ce résultat asynchrone.
        if (otherPlayerLoadGeneration[data.id] !== loadGeneration || otherPlayers[data.id]) {
            mesh.dispose();
            return;
        }
        mesh.rotation.y = offset;
        mesh.computeWorldMatrix(true);
        let bounds = mesh.getHierarchyBoundingVectors(true);
        const rawLengthX = bounds.max.x - bounds.min.x;
        const targetUnits = metersToUnits(boatData.lengthMeters || 100);
        const scale = rawLengthX > 0 ? targetUnits / rawLengthX : 1;
        mesh.scaling.scaleInPlace(scale);
        mesh.computeWorldMatrix(true);
        bounds = mesh.getHierarchyBoundingVectors(true);
        const center = bounds.min.add(bounds.max).scale(0.5);
        mesh.position.x -= center.x;
        mesh.position.z -= center.z;
        const wrapper = new BABYLON.TransformNode("other_" + data.id, scene);
        mesh.parent = wrapper;
        wrapper.position = new BABYLON.Vector3(data.position.x, data.position.y || 0, data.position.z);
        wrapper.rotation.y = data.rotation || 0;
        otherPlayers[data.id] = wrapper;
        if ((data.position.y || 0) < -0.7) wrapper.setEnabled(false);
        // S'assurer que le clipPlane de plongée est appliqué à chaque sous-mesh
        // du bateau, même si un autre mesh exempté l'a neutralisé pendant le frame.
        const childMeshes = mesh.getChildMeshes ? mesh.getChildMeshes(false) : [];
        applyFrameClipPlane(mesh);
        for (const cm of childMeshes) applyFrameClipPlane(cm);
        // Instancier (ou rafraîchir) le Boat distant correspondant.
        if (remoteBoats[data.id]) {
            remoteBoats[data.id].mesh = wrapper;
            remoteBoats[data.id].boatData = boatData;
            remoteBoats[data.id].boatType = data.boatType || remoteBoats[data.id].boatType;
        } else {
            remoteBoats[data.id] = new Boat({
                id: data.id,
                isLocal: false,
                boatType: data.boatType || null,
                boatData: boatData,
                mesh: wrapper,
            });
        }
    });
    otherPlayersInfo[data.id] = {
        baseNoise: (data.boat && data.boat.noise) || 0,
        minNoise: (data.boat && data.boat.minNoise) || 0,
        baseSpeed: knotsToUnitPerSecond(((data.boat && data.boat.speed) || 25) / 2),
        maxSpeedKnots: (data.boat && data.boat.speed) || 25,
        speedNoiseLimit: (data.boat && typeof data.boat.speedNoiseLimit === "number") ? data.boat.speedNoiseLimit : 0,
        boatType: data.boatType || null,
        lengthMeters: (data.boat && data.boat.lengthMeters) || 100,
        teamId: data.team_id || null,
        teamName: data.team_name || null,
    };
}


let _everJoinedGame = false; // passe à true dès qu'on a reçu "init" (en jeu)
// --- RTT measurement ---
// --- RTT measurement (200ms interval, médiane sur 10s) ---
let _rttSamples = [];
let _rttLastReport = 0;
setInterval(() => {
    if (socket.connected) socket.emit("ws_ping", { ts: Date.now() });
}, 200);
socket.on("ws_pong", (data) => {
    const now = Date.now();
    _rttSamples.push(now - data.ts);
    if (now - _rttLastReport >= 10000 && _rttSamples.length > 0) {
        _rttSamples.sort((a, b) => a - b);
        const n = _rttSamples.length;
        const median = _rttSamples[Math.floor(n / 2)];
        const p95 = _rttSamples[Math.floor(n * 0.95)];
        const max = _rttSamples[n - 1];
        const toServer = data.sts ? Math.round(data.sts * 1000 - data.ts) : null;
        const fromServer = data.sts ? Math.round(now - data.sts * 1000) : null;
        socket.emit("ws_rtt_report", { avg: median, max, p95, n, toServer, fromServer });
        // Taux adaptatif : 10 Hz si RTT médiane > 200ms, 20 Hz sinon
        const prevInterval = MOVE_EMIT_INTERVAL;
        MOVE_EMIT_INTERVAL = median > 200 ? MOVE_EMIT_INTERVAL_SLOW : MOVE_EMIT_INTERVAL_NORMAL;
        if (MOVE_EMIT_INTERVAL !== prevInterval)
            dlog("webSocket", `move rate adapté : ${1000/prevInterval}Hz → ${1000/MOVE_EMIT_INTERVAL}Hz (RTT médiane=${median}ms)`);
        _rttSamples = [];
        _rttLastReport = now;
    }
});

socket.on("connect", () => {
    console.log("[startup] socket connecté t=" + performance.now().toFixed(0) + "ms");
    // Si on était déjà entré en jeu, ce "connect" est une RECONNEXION après une
    // déconnexion (onglet masqué trop longtemps, réseau coupé). Le serveur a
    // retiré notre bateau ; impossible de reprendre proprement → on recharge.
    if (_everJoinedGame) {
        showConnectionLostOverlay();
        return;
    }
    // Demande la liste des équipes en jeu pour peupler le dialogue.
    socket.emit("list_teams");
    // Récupère la liste des textures disponibles (utilisé par toutes les îles
    // pour reconstruire l'URL avec la bonne extension à partir du nom JSON).
    socket.emit("admin_list_textures");
});

function showConnectionLostOverlay() {
    if (document.getElementById("connLostOverlay")) return;
    const ov = document.createElement("div");
    ov.id = "connLostOverlay";
    ov.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.85);color:#fff;font-family:sans-serif;font-size:20px;z-index:1000;text-align:center;";
    ov.innerHTML = "<div>Connexion perdue.<br><br>Rechargement…</div>";
    document.body.appendChild(ov);
    setTimeout(() => { try { location.reload(); } catch (_) {} }, 2500);
}

socket.on("disconnect", (reason) => {
    console.warn("[socket] disconnect:", reason);
    // Si on était en jeu, prévenir le joueur (la reconnexion auto de Socket.IO
    // déclenchera showConnectionLostOverlay via "connect", mais on affiche tout
    // de suite pour éviter un écran figé silencieux).
    if (_everJoinedGame) showConnectionLostOverlay();
});

socket.on("teams_list", (data) => {
    refreshTeamList(data.teams || []);
});

let clientSimMultiplier = 1;
function updateTimeMultiplierIndicator() {
    const el = document.getElementById("timeMultiplierIndicator");
    if (!el) return;
    if (clientSimMultiplier > 1) {
        el.textContent = "x" + clientSimMultiplier;
        el.style.display = "block";
    } else {
        el.style.display = "none";
    }
    // Force le repositionnement avec l'offset courant (le bloc UI gauche est
    // ancré en bas de l'écran via leftUIOffsetY).
    if (typeof applyLeftUIOffsets === "function") applyLeftUIOffsets();
}
socket.on("sim_speed_changed", (data) => {
    const n = (data && data.multiplier) || 1;
    clientSimMultiplier = n;
    setTransientMessage("Vitesse simulation : ×" + n);
    updateTimeMultiplierIndicator();
});

document.addEventListener("DOMContentLoaded", () => {
    // Boutons bateau (sélection visuelle, ne valide pas encore).
    const bd = document.getElementById("loginBoatDest");
    if (bd) bd.addEventListener("click", () => pickBoat("destroyer"));
    const bs = document.getElementById("loginBoatSub");
    if (bs) bs.addEventListener("click", () => pickBoat("submarine"));
    // Création d'équipe.
    const btn = document.getElementById("teamCreateBtn");
    if (btn) btn.addEventListener("click", createAndJoinTeam);
    const inp = document.getElementById("teamNameInput");
    if (inp) {
        inp.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); createAndJoinTeam(); }
        });
    }
    // Connexion socket immédiate pour récupérer les équipes existantes.
    socket.connect();
});

socket.on("connect_error", (err) => {
    console.error("Socket error:", err);
});

socket.on("server_full", (data) => {
    const max = (data && data.max) || "?";
    alert("Serveur plein (" + max + " joueurs maximum). Réessayez plus tard.");
    document.getElementById("boatSelect").style.display = "block";
});

let botRlModels = {};
socket.on("init", (data) => {
    botRlModels = data.botRlModels || {};
    const _startupT0 = performance.now();
    const _startupLog = (label) => console.log(`[startup] ${label} +${(performance.now() - _startupT0).toFixed(0)}ms`);
    _startupLog("init reçu — playerId=" + data.playerId + " boatType=" + data.boatType);
    _everJoinedGame = true;
    playerId = data.playerId;
    localTeamId = data.team_id || null;
    originalBoatData = data.boat;
    originalBoatType = data.boatType;
    currentBoatType = data.boatType;
    maxSpeed = knotsToUnitPerSecond(data.boat.speed);
    baseSpeed = maxSpeed / 2;
    reverseMaxSpeed = maxSpeed / 2;
    localBoatBaseNoise = (data.boat && data.boat.noise) || 0;
    localBoatMinNoise = (data.boat && data.boat.minNoise) || 0;
    localSpeedNoiseLimit = (data.boat && typeof data.boat.speedNoiseLimit === "number") ? data.boat.speedNoiseLimit : 0;
    localPassiveMinNoise = (data.boat && data.boat.passiveSonar && typeof data.boat.passiveSonar.minNoise === "number") ? data.boat.passiveSonar.minNoise : 5.0;
    boatSpeed = 0;
    boatIntegrity = 100;
    isSinking = false;
    sinkTilt = 0;
    radarVisible = true;
    radarCanvas.style.display = "block";
    const t = (data.boat && data.boat.torpedoes) || {};
    const initCounts = data.torpedoCounts || {};
    torpedoCounts = {
        acoustic: typeof initCounts.acoustic === "number" ? initCounts.acoustic : ((t.acoustic && t.acoustic.count) || 0),
        wireGuided: typeof initCounts.wireGuided === "number" ? initCounts.wireGuided : ((t.wireGuided && t.wireGuided.count) || 0),
        autonomous: typeof initCounts.autonomous === "number" ? initCounts.autonomous : ((t.autonomous && t.autonomous.count) || 0),
    };
    torpedoInitialCounts = {
        acoustic: (t.acoustic && t.acoustic.count) || 0,
        wireGuided: (t.wireGuided && t.wireGuided.count) || 0,
        autonomous: (t.autonomous && t.autonomous.count) || 0,
    };
    for (const kind of ["acoustic", "wireGuided", "autonomous"]) {
        if (t[kind]) {
            torpedoStats[kind] = {
                speed: t[kind].speed || torpedoStats[kind].speed,
                minTurnRadius: t[kind].minTurnRadius || torpedoStats[kind].minTurnRadius,
                damage: typeof t[kind].damage === "number" ? t[kind].damage : (torpedoStats[kind].damage || 50),
                activation: typeof t[kind].activation === "number" ? t[kind].activation : (torpedoStats[kind].activation || 0),
                maxRangeMeters: typeof t[kind].maxRangeMeters === "number" ? t[kind].maxRangeMeters : (torpedoStats[kind].maxRangeMeters || 10000),
                radarRangeMeters: typeof t[kind].radarRangeMeters === "number" ? t[kind].radarRangeMeters : (torpedoStats[kind].radarRangeMeters || 0),
                radarConeDeg: typeof t[kind].radarConeDeg === "number" ? t[kind].radarConeDeg : (torpedoStats[kind].radarConeDeg || 30),
            };
        }
    }
    syncTorpedoActivationInputs();
    updateTorpedoPanel();
    const lureSpec = (data.boat && data.boat.acousticLures) || null;
    if (lureSpec) {
        acousticLureSpec = { number: lureSpec.number || 0, time: lureSpec.time || 0, noise: lureSpec.noise || 0 };
        acousticLureCount = typeof data.lureCount === "number" ? data.lureCount : acousticLureSpec.number;
    } else {
        acousticLureSpec = { number: 0, time: 0, noise: 0 };
        acousticLureCount = 0;
    }
    const grenadeSpec = (data.boat && data.boat.grenade) || null;
    grenadeDamage = grenadeSpec && typeof grenadeSpec.damage === "number" ? grenadeSpec.damage : 50;
    grenadeRangeMeters = grenadeSpec && typeof grenadeSpec.rangeMeters === "number" ? grenadeSpec.rangeMeters : 1000;
    grenadeVolleyNumber = grenadeSpec && typeof grenadeSpec.volleyNumber === "number" ? grenadeSpec.volleyNumber : 3;
    grenadeCount = typeof data.grenadeCount === "number"
        ? data.grenadeCount
        : (grenadeSpec && typeof grenadeSpec.number === "number" ? grenadeSpec.number : 0);
    updateGrenadeButtons();
    updateAcousticLureButton();
    const beaconSpec = (data.boat && data.boat.sonarBeacons) || null;
    if (beaconSpec) {
        sonarBeaconSpec = {
            number: beaconSpec.number || 0,
            pingIntervalSec: beaconSpec.pingIntervalSec || 30,
            rangeMeters: beaconSpec.rangeMeters || 5000,
            thermoclinePenetration: typeof beaconSpec.thermoclinePenetration === "number" ? beaconSpec.thermoclinePenetration : 0.1,
        };
        sonarBeaconCount = typeof data.beaconCount === "number" ? data.beaconCount : sonarBeaconSpec.number;
    } else {
        sonarBeaconSpec = { number: 0, pingIntervalSec: 30, rangeMeters: 5000, thermoclinePenetration: 0.1 };
        sonarBeaconCount = 0;
    }
    const pBeaconSpec = (data.boat && data.boat.passiveSonarBeacons) || null;
    if (pBeaconSpec) {
        passiveSonarBeaconSpec = {
            number: pBeaconSpec.number || 0,
            minNoise: pBeaconSpec.minNoise || 20,
        };
        passiveSonarBeaconCount = typeof data.passiveBeaconCount === "number"
            ? data.passiveBeaconCount : passiveSonarBeaconSpec.number;
    } else {
        passiveSonarBeaconSpec = { number: 0, minNoise: 20 };
        passiveSonarBeaconCount = 0;
    }
    // Specs et compteurs mines (3 types) lus dans le JSON du bateau.
    const mineSurfSpec = (data.boat && data.boat.mineSurf) || null;
    const mineBottomSpec = (data.boat && data.boat.mineBottom) || null;
    const mineSuspSpec = (data.boat && data.boat.mineSuspended) || null;
    mineSpec = {
        surface:   mineSurfSpec   ? { number: mineSurfSpec.number || 0,   delay: mineSurfSpec.delay   || 0, damage: mineSurfSpec.damage   || 0, range: mineSurfSpec.range   || 0 } : { number: 0, delay: 0, damage: 0, range: 0 },
        bottom:    mineBottomSpec ? { number: mineBottomSpec.number || 0, delay: mineBottomSpec.delay || 0, damage: mineBottomSpec.damage || 0, range: mineBottomSpec.range || 0 } : { number: 0, delay: 0, damage: 0, range: 0 },
        suspended: mineSuspSpec   ? { number: mineSuspSpec.number || 0,   delay: mineSuspSpec.delay   || 0, damage: mineSuspSpec.damage   || 0, range: mineSuspSpec.range   || 0 } : { number: 0, delay: 0, damage: 0, range: 0 },
    };
    const mc = data.mineCounts || {};
    mineCounts = {
        surface:   typeof mc.surface   === "number" ? mc.surface   : mineSpec.surface.number,
        bottom:    typeof mc.bottom    === "number" ? mc.bottom    : mineSpec.bottom.number,
        suspended: typeof mc.suspended === "number" ? mc.suspended : mineSpec.suspended.number,
    };
    mineInitialCounts = {
        surface:   mineSpec.surface.number,
        bottom:    mineSpec.bottom.number,
        suspended: mineSpec.suspended.number,
    };
    // Charger les mines existantes (broadcast init).
    for (const mid in mines) removeMine(mines[mid].ownerId, mines[mid].mid);
    if (Array.isArray(data.mines)) {
        for (const m of data.mines) addMine(m);
    }
    updateMinePanel();
    updateSonarBeaconButton();
    updatePassiveSonarBeaconButton();
    if (data.boat && data.boat.activeSonar) {
        sonarReveal = metersToUnits(data.boat.activeSonar.reveal || 15000);
        sonarShortAngleDeg = typeof data.boat.activeSonar.shortAngle === "number" ? data.boat.activeSonar.shortAngle : 30;
        sonarLargeAngleDeg = typeof data.boat.activeSonar.largeAngle === "number" ? data.boat.activeSonar.largeAngle : 120;
        sonarShortRange = metersToUnits(data.boat.activeSonar.shortAngleRange || 5000);
        sonarLargeRange = metersToUnits(data.boat.activeSonar.largeAngleRange || 2500);
        sonarThermoclinePenetration = typeof data.boat.activeSonar.thermoclinePenetration === "number" ? data.boat.activeSonar.thermoclinePenetration : 0.1;
    }
    updateWeaponsUI();
    // Multi-bateaux : enregistre l'état initial du bateau primaire dans boatAmmo.
    // Sera réutilisé lors d'un switchActiveBoat retour vers le primaire.
    boatAmmo["primary"] = {
        torpedo: { ...torpedoCounts },
        torpedoInitial: { ...torpedoInitialCounts },
        drone: { ...droneCounts },
        grenade: grenadeCount,
        cannon: { cannon: cannonAmmo, antiAircraft: aaAmmo },
        beacon: sonarBeaconCount,
        lure: acousticLureCount,
        mine: { ...mineCounts },
        mineInitial: { ...mineInitialCounts },
    };
    if (grenadeSpec && typeof grenadeSpec.effectRangeMeters === "number") {
        grenadeEffectDistance = metersToUnits(grenadeSpec.effectRangeMeters);
    }
    if (grenadeSpec && typeof grenadeSpec.sinkSpeedMs === "number") {
        grenadeSinkSpeed = metersToUnits(grenadeSpec.sinkSpeedMs);
    }
    if (typeof data.boat.maxDepthMeters === "number") {
        const SEABED_METERS = 500;
        const clamped = Math.min(data.boat.maxDepthMeters, SEABED_METERS - 5);
        maxDiveDepth = -metersToUnits(clamped);
    }
    boatFlotationY = -metersToUnits(typeof data.boat.flotation === "number" ? data.boat.flotation : 2);
    if (typeof data.boat.radarRangeMeters === "number") torpedoRadarRangeUnits = metersToUnits(data.boat.radarRangeMeters);
    droneSpecs.automatic = (data.boat && data.boat.automaticDrone) || null;
    droneSpecs.manual = (data.boat && data.boat.manualDrone) || null;
    {
        const dc = data.droneCounts || {};
        droneCounts.automatic = typeof dc.automatic === "number" ? dc.automatic : ((droneSpecs.automatic && droneSpecs.automatic.number) || 0);
        droneCounts.manual = typeof dc.manual === "number" ? dc.manual : ((droneSpecs.manual && droneSpecs.manual.number) || 0);
    }
    cleanupAllDrones();
    updateDroneButtons();
    cannonSpec = (data.boat && data.boat.cannon) || null;
    aaSpec = (data.boat && data.boat.antiAircraft) || null;
    {
        const cc = data.cannonCounts || {};
        cannonAmmo = typeof cc.cannon === "number" ? cc.cannon : ((cannonSpec && cannonSpec.ammunition) || 0);
        aaAmmo = typeof cc.antiAircraft === "number" ? cc.antiAircraft : ((aaSpec && aaSpec.ammunition) || 0);
    }
    updateCannonButtons();
    modelRotationOffset = data.boat.modelRotationOffset || 0;
    playerRotation = data.rotation;

    worldData = data.world;
    islandBoundsCache.length = 0;
    _startupLog("buildWorld start — îles=" + (worldData.islands ? worldData.islands.length : 0));
    buildWorld(worldData);
    _startupLog("buildWorld done");
    applyDayCycleSnapshot(data.dayCycle);

    _startupLog("loadBoatModel start — " + data.boat.model);
    loadBoatModel(data.boat.model, (mesh) => {
        mesh.rotation.y = modelRotationOffset;
        mesh.computeWorldMatrix(true);
        let bounds = mesh.getHierarchyBoundingVectors(true);
        const rawLengthX = bounds.max.x - bounds.min.x;
        const targetUnits = metersToUnits(data.boat.lengthMeters || 100);
        const scale = rawLengthX > 0 ? targetUnits / rawLengthX : 1;
        mesh.scaling.scaleInPlace(scale);
        mesh.computeWorldMatrix(true);
        bounds = mesh.getHierarchyBoundingVectors(true);
        const center = bounds.min.add(bounds.max).scale(0.5);
        mesh.position.x -= center.x;
        mesh.position.z -= center.z;
        boatHalfLength = (bounds.max.x - bounds.min.x) / 2;
        boatHalfWidth = (bounds.max.z - bounds.min.z) / 2;
        currentBoatLengthMeters = data.boat.lengthMeters || 100;
        const zc = (data.boat && data.boat.zoomCamera) || {};
        currentBoatZoomCamera = {
            forwardMeters: typeof zc.forwardMeters === "number" ? zc.forwardMeters : 0,
            upMeters: typeof zc.upMeters === "number" ? zc.upMeters : 0,
        };
        const wrapper = new BABYLON.TransformNode("playerWrapper", scene);
        mesh.parent = wrapper;
        mesh.getChildMeshes(false).forEach(cm => { cm.isPickable = false; });
        if (mesh instanceof BABYLON.AbstractMesh) mesh.isPickable = false;
        wrapper.position = new BABYLON.Vector3(data.position.x, boatFlotationY, data.position.z);
        wrapper.rotation.y = playerRotation;
        playerMesh = wrapper;

        // Instancier le bateau local et le pointer comme bateau observé.
        localBoat = new Boat({
            id: null,
            isLocal: true,
            boatType: data.boatType,
            boatData: data.boat,
            mesh: wrapper,
        });
        localBoat.halfLength = boatHalfLength;
        localBoat.halfWidth = boatHalfWidth;
        viewedBoat = localBoat;
        // Multi-bateaux : enregistrer le bateau primaire dans la liste.
        localBoats = [{ ghostSid: null, playerId: data.playerId, boat: localBoat, sunk: false }];
        activeBoatIndex = 0;
        selfControlledPlayerIds.clear();
        selfControlledPlayerIds.add(data.playerId);

        const camera = new BABYLON.ArcRotateCamera("camera",
            cameraAlpha, cameraBeta, 15, playerMesh.position, scene);
        camera.inputs.clear();
        scene.activeCamera = camera;

        const fpv = new BABYLON.UniversalCamera("fpvCamera", playerMesh.position.clone(), scene);
        fpv.inputs.clear();
        fpv.minZ = 0.1;
        scene._fpvCamera = fpv;
        initialized = true;
        _startupLog("loadBoatModel done — scène prête");
    });

    const _otherCount = Object.keys(data.players).length;
    _startupLog("createOtherPlayers start — " + _otherCount + " joueurs");
    for (const sid in data.players) {
        createOtherPlayer(data.players[sid]);
    }
    _startupLog("createOtherPlayers enqueued (async)");
    if (Array.isArray(data.sonarBeacons)) {
        for (const b of data.sonarBeacons) addSonarBeacon(b);
    }
    if (Array.isArray(data.passiveSonarBeacons)) {
        for (const b of data.passiveSonarBeacons) addPassiveSonarBeacon(b);
    }
});

function applyBoatConfig(boat, boatType, opts) {
    const o = opts || {};
    currentBoatType = boatType;
    maxSpeed = knotsToUnitPerSecond(boat.speed);
    baseSpeed = maxSpeed / 2;
    reverseMaxSpeed = maxSpeed / 2;
    // Réinitialise l'état du cheat speed2 quand la config du bateau change
    // (changement de bateau, vue bot, resync) : évite la désynchronisation
    // entre maxSpeed local et le speed_mult serveur.
    window._baseMaxSpeed = maxSpeed;
    window._playerSpeedMult = 1;
    localBoatBaseNoise = boat.noise || 0;
    localBoatMinNoise = boat.minNoise || 0;
    localSpeedNoiseLimit = typeof boat.speedNoiseLimit === "number" ? boat.speedNoiseLimit : 0;
    localPassiveMinNoise = (boat.passiveSonar && typeof boat.passiveSonar.minNoise === "number") ? boat.passiveSonar.minNoise : 5.0;
    boatSpeed = 0;
    rudderAngle = 0;
    diveRate = 0;
    periscopeTarget = null;
    if (o.resetIntegrity) boatIntegrity = 100;
    if (o.resetIntegrity) { isSinking = false; sinkTilt = 0; }
    modelRotationOffset = boat.modelRotationOffset || 0;
    boatFlotationY = -metersToUnits(typeof boat.flotation === "number" ? boat.flotation : 2);
    // N'écraser la flottaison du mesh local que si c'est un destroyer (surface).
    // Un sub peut être en plongée — ne pas forcer en surface au retour de vue bot.
    if (localBoat && localBoat.mesh && isViewingLocal() && boatType !== "submarine") {
        localBoat.mesh.position.y = boatFlotationY;
    }
    radarVisible = true;
    radarCanvas.style.display = "block";
    const t = boat.torpedoes || {};
    const overrideCounts = (o.torpedoCounts) || {};
    torpedoCounts = {
        acoustic: typeof overrideCounts.acoustic === "number" ? overrideCounts.acoustic : ((t.acoustic && t.acoustic.count) || 0),
        wireGuided: typeof overrideCounts.wireGuided === "number" ? overrideCounts.wireGuided : ((t.wireGuided && t.wireGuided.count) || 0),
        autonomous: typeof overrideCounts.autonomous === "number" ? overrideCounts.autonomous : ((t.autonomous && t.autonomous.count) || 0),
    };
    torpedoInitialCounts = {
        acoustic: (t.acoustic && t.acoustic.count) || 0,
        wireGuided: (t.wireGuided && t.wireGuided.count) || 0,
        autonomous: (t.autonomous && t.autonomous.count) || 0,
    };
    for (const kind of ["acoustic", "wireGuided", "autonomous"]) {
        if (t[kind]) {
            torpedoStats[kind] = {
                speed: t[kind].speed || torpedoStats[kind].speed,
                minTurnRadius: t[kind].minTurnRadius || torpedoStats[kind].minTurnRadius,
                damage: typeof t[kind].damage === "number" ? t[kind].damage : (torpedoStats[kind].damage || 50),
                activation: typeof t[kind].activation === "number" ? t[kind].activation : (torpedoStats[kind].activation || 0),
                maxRangeMeters: typeof t[kind].maxRangeMeters === "number" ? t[kind].maxRangeMeters : (torpedoStats[kind].maxRangeMeters || 10000),
                radarRangeMeters: typeof t[kind].radarRangeMeters === "number" ? t[kind].radarRangeMeters : (torpedoStats[kind].radarRangeMeters || 0),
                radarConeDeg: typeof t[kind].radarConeDeg === "number" ? t[kind].radarConeDeg : (torpedoStats[kind].radarConeDeg || 30),
            };
        }
    }
    syncTorpedoActivationInputs();
    updateTorpedoPanel();
    const lureSpec = boat.acousticLures || null;
    if (lureSpec) {
        acousticLureSpec = { number: lureSpec.number || 0, time: lureSpec.time || 0, noise: lureSpec.noise || 0 };
        acousticLureCount = typeof o.lureCount === "number" ? o.lureCount : acousticLureSpec.number;
    } else {
        acousticLureSpec = { number: 0, time: 0, noise: 0 };
        acousticLureCount = 0;
    }
    const grenadeSpec = boat.grenade || null;
    grenadeDamage = grenadeSpec && typeof grenadeSpec.damage === "number" ? grenadeSpec.damage : 50;
    grenadeRangeMeters = grenadeSpec && typeof grenadeSpec.rangeMeters === "number" ? grenadeSpec.rangeMeters : 1000;
    grenadeVolleyNumber = grenadeSpec && typeof grenadeSpec.volleyNumber === "number" ? grenadeSpec.volleyNumber : 3;
    grenadeCount = typeof o.grenadeCount === "number"
        ? o.grenadeCount
        : (grenadeSpec && typeof grenadeSpec.number === "number" ? grenadeSpec.number : 0);
    if (grenadeSpec && typeof grenadeSpec.effectRangeMeters === "number") {
        grenadeEffectDistance = metersToUnits(grenadeSpec.effectRangeMeters);
    }
    if (grenadeSpec && typeof grenadeSpec.sinkSpeedMs === "number") {
        grenadeSinkSpeed = metersToUnits(grenadeSpec.sinkSpeedMs);
    }
    if (boat.activeSonar) {
        sonarReveal = metersToUnits(boat.activeSonar.reveal || 15000);
        sonarShortAngleDeg = typeof boat.activeSonar.shortAngle === "number" ? boat.activeSonar.shortAngle : 30;
        sonarLargeAngleDeg = typeof boat.activeSonar.largeAngle === "number" ? boat.activeSonar.largeAngle : 120;
        sonarShortRange = metersToUnits(boat.activeSonar.shortAngleRange || 5000);
        sonarLargeRange = metersToUnits(boat.activeSonar.largeAngleRange || 2500);
        sonarThermoclinePenetration = typeof boat.activeSonar.thermoclinePenetration === "number" ? boat.activeSonar.thermoclinePenetration : 0.1;
    }
    if (typeof boat.maxDepthMeters === "number") {
        const SEABED_METERS = 500;
        const clamped = Math.min(boat.maxDepthMeters, SEABED_METERS - 5);
        maxDiveDepth = -metersToUnits(clamped);
    }
    torpedoRadarRangeUnits = typeof boat.radarRangeMeters === "number" ? metersToUnits(boat.radarRangeMeters) : metersToUnits(30000);
    droneSpecs.automatic = boat.automaticDrone || null;
    droneSpecs.manual = boat.manualDrone || null;
    {
        const dc = (o.droneCounts) || {};
        droneCounts.automatic = typeof dc.automatic === "number" ? dc.automatic : ((droneSpecs.automatic && droneSpecs.automatic.number) || 0);
        droneCounts.manual = typeof dc.manual === "number" ? dc.manual : ((droneSpecs.manual && droneSpecs.manual.number) || 0);
    }
    if (o.resetDrones) cleanupAllDrones();
    updateDroneButtons();
    cannonSpec = boat.cannon || null;
    aaSpec = boat.antiAircraft || null;
    {
        const cc = (o.cannonCounts) || {};
        cannonAmmo = typeof cc.cannon === "number" ? cc.cannon : ((cannonSpec && cannonSpec.ammunition) || 0);
        aaAmmo = typeof cc.antiAircraft === "number" ? cc.antiAircraft : ((aaSpec && aaSpec.ammunition) || 0);
    }
    updateCannonButtons();
    updateGrenadeButtons();
    updateAcousticLureButton();
    const beaconSpec = boat.sonarBeacons || null;
    if (beaconSpec) {
        sonarBeaconSpec = {
            number: beaconSpec.number || 0,
            pingIntervalSec: beaconSpec.pingIntervalSec || 30,
            rangeMeters: beaconSpec.rangeMeters || 5000,
        };
        sonarBeaconCount = typeof o.beaconCount === "number" ? o.beaconCount : sonarBeaconSpec.number;
    } else {
        sonarBeaconSpec = { number: 0, pingIntervalSec: 30, rangeMeters: 5000 };
        sonarBeaconCount = 0;
    }
    const pBeaconSpec2 = boat.passiveSonarBeacons || null;
    if (pBeaconSpec2) {
        passiveSonarBeaconSpec = {
            number: pBeaconSpec2.number || 0,
            minNoise: pBeaconSpec2.minNoise || 20,
        };
        passiveSonarBeaconCount = typeof o.passiveBeaconCount === "number"
            ? o.passiveBeaconCount : passiveSonarBeaconSpec.number;
    } else {
        passiveSonarBeaconSpec = { number: 0, minNoise: 20 };
        passiveSonarBeaconCount = 0;
    }
    // Specs et compteurs mines.
    const mineSurfSpec2 = boat.mineSurf || null;
    const mineBottomSpec2 = boat.mineBottom || null;
    const mineSuspSpec2 = boat.mineSuspended || null;
    mineSpec = {
        surface:   mineSurfSpec2   ? { number: mineSurfSpec2.number || 0,   delay: mineSurfSpec2.delay   || 0, damage: mineSurfSpec2.damage   || 0, range: mineSurfSpec2.range   || 0 } : { number: 0, delay: 0, damage: 0, range: 0 },
        bottom:    mineBottomSpec2 ? { number: mineBottomSpec2.number || 0, delay: mineBottomSpec2.delay || 0, damage: mineBottomSpec2.damage || 0, range: mineBottomSpec2.range || 0 } : { number: 0, delay: 0, damage: 0, range: 0 },
        suspended: mineSuspSpec2   ? { number: mineSuspSpec2.number || 0,   delay: mineSuspSpec2.delay   || 0, damage: mineSuspSpec2.damage   || 0, range: mineSuspSpec2.range   || 0 } : { number: 0, delay: 0, damage: 0, range: 0 },
    };
    const mc2 = o.mineCounts || {};
    mineCounts = {
        surface:   typeof mc2.surface   === "number" ? mc2.surface   : mineSpec.surface.number,
        bottom:    typeof mc2.bottom    === "number" ? mc2.bottom    : mineSpec.bottom.number,
        suspended: typeof mc2.suspended === "number" ? mc2.suspended : mineSpec.suspended.number,
    };
    mineInitialCounts = {
        surface:   mineSpec.surface.number,
        bottom:    mineSpec.bottom.number,
        suspended: mineSpec.suspended.number,
    };
    updateMinePanel();
    updateSonarBeaconButton();
    updatePassiveSonarBeaconButton();
    updateWeaponsUI();
    currentBoatLengthMeters = boat.lengthMeters || 100;
    const zc2 = (boat && boat.zoomCamera) || {};
    currentBoatZoomCamera = {
        forwardMeters: typeof zc2.forwardMeters === "number" ? zc2.forwardMeters : 0,
        upMeters: typeof zc2.upMeters === "number" ? zc2.upMeters : 0,
    };
}

// Multi-bateaux : set des playerId que le client simule localement (= bateau
// actif). Les player_moved les ignorent pour ne pas combattre la simu locale.
const selfControlledPlayerIds = new Set();

function switchActiveBoat(toIndex) {
    if (toIndex === activeBoatIndex) return;
    if (toIndex < 0 || toIndex >= localBoats.length) return;
    const target = localBoats[toIndex];
    if (!target) return;
    // Si le boatRef stocké est null (cas où player_joined est arrivé après
    // own_boat_added), on retombe sur otherPlayers[playerId].
    let mesh = target.boat && target.boat.mesh;
    if (!mesh) {
        const wrapper = otherPlayers[target.playerId];
        if (!wrapper) return;
        target.boat = {
            id: target.playerId,
            isLocal: true,
            boatType: (boatAmmo[ammoKey(target.ghostSid)] || {}).boatType,
            boatData: (boatAmmo[ammoKey(target.ghostSid)] || {}).boat,
            mesh: wrapper,
        };
        mesh = wrapper;
    }
    // Le bateau qu'on quitte n'est plus simulé localement.
    const prev = localBoats[activeBoatIndex];
    if (prev && prev.playerId) {
        selfControlledPlayerIds.delete(prev.playerId);
        // Mémoriser sa vitesse/rudder pour qu'au retour on les restaure (sinon
        // on lui enverrait un move(speedRatio=0) qui l'arrêterait).
        // Mémoriser aussi les munitions actuelles : sinon au retour, on
        // restaurerait les munitions enregistrées à la création du slot
        // (donc état initial) et on perdrait les tirs/consommations effectués.
        const pak = ammoKey(prev.ghostSid);
        const slot = boatAmmo[pak] || (boatAmmo[pak] = {});
        slot.lastBoatSpeed = boatSpeed;
        slot.lastRudder = rudderAngle;
        slot.lastRotation = playerRotation;
        slot.torpedo = { ...torpedoCounts };
        slot.drone = { ...droneCounts };
        slot.grenade = grenadeCount;
        slot.cannon = { cannon: cannonAmmo, antiAircraft: aaAmmo };
        slot.beacon = sonarBeaconCount;
        slot.lure = acousticLureCount;
        slot.mine = { ...mineCounts };
    }
    // On perd le contrôle des armes manuelles en cours (drone manuel, filoguidée).
    activeManualDrone = null;
    manualDroneControl = false;
    activeWireTorpedoKey = null;
    activeBoatIndex = toIndex;
    isSinking = false;
    sinkTilt = 0;
    aimingTorpedoKind = null;
    grenadeAiming = false;
    showAimBanner(false);
    showGrenadeAimBanner(false);
    // Pointer les vars globales sur le nouveau bateau.
    localBoat = target.boat;
    viewedBoat = localBoat;
    playerMesh = mesh;
    playerId = target.playerId;
    playerRotation = mesh.rotation ? mesh.rotation.y : 0;
    // Snap caméra directement en vue arrière (pas d'animation d'introduction
    // comme à la première connexion).
    cameraAlpha = -playerRotation;
    cameraAlphaOffset = 0;
    // Reload boat config + ammos depuis boatAmmo[key].
    const ak = ammoKey(target.ghostSid);
    const a = boatAmmo[ak] || {};
    const boatData = a.boat || target.boat.boatData;
    const boatType = a.boatType || target.boat.boatType;
    applyBoatConfig(boatData, boatType, {
        torpedoCounts: a.torpedo,
        droneCounts: a.drone,
        grenadeCount: a.grenade,
        cannonCounts: a.cannon,
        beaconCount: a.beacon,
        lureCount: a.lure,
        mineCounts: a.mine,
    });
    // Restaurer la vitesse/rudder du bateau qu'on reprend.
    // Priorité : la dernière vitesse VUE DU SERVEUR (autopilote a pu arrêter
    // le bateau de lui-même). Sinon, dernière vitesse locale mémorisée.
    const restored = boatAmmo[ak] || {};
    if (typeof restored.lastServerSpeedRatio === "number" && maxSpeed > 0) {
        const dir = restored.lastServerReverse ? -1 : 1;
        boatSpeed = restored.lastServerSpeedRatio * maxSpeed * dir;
        rudderAngle = restored.lastServerRudder || 0;
    } else if (typeof restored.lastBoatSpeed === "number") {
        boatSpeed = restored.lastBoatSpeed;
        rudderAngle = restored.lastRudder || 0;
    } else {
        const hist = otherPlayersHistory[target.playerId];
        if (hist && typeof hist.speedRatio === "number" && maxSpeed > 0) {
            const dir = hist.reverse ? -1 : 1;
            boatSpeed = hist.speedRatio * maxSpeed * dir;
        }
    }
    // Le bateau actif est désormais simulé localement.
    if (target.playerId) selfControlledPlayerIds.add(target.playerId);
    // Notifie serveur.
    socket.emit("set_active_boat", { bsid: target.ghostSid });
    setTransientMessage("Bateau actif : " + (target.boatType || boatType || "?") + " (" + (toIndex + 1) + "/" + localBoats.length + ")");
}

function cycleActiveBoat(direction) {
    if (localBoats.length <= 1) return;
    const before = activeBoatIndex;
    let target = before;
    for (let i = 1; i <= localBoats.length; i++) {
        const idx = (before + direction * i + localBoats.length * 2) % localBoats.length;
        if (!localBoats[idx].sunk) { target = idx; break; }
    }
    if (target !== before) switchActiveBoat(target);
}

socket.on("boat_changed", (data) => {
    if (isViewingLocal()) {
        originalBoatData = data.boat;
        originalBoatType = data.boatType;
    }
    if (localBoat) {
        // Réinitialiser localBoat sur la nouvelle config (le mesh sera réutilisé puis re-scale).
        localBoat.boatData = data.boat;
        localBoat.boatType = data.boatType;
    }
    applyBoatConfig(data.boat, data.boatType, { resetIntegrity: true, resetGrace: true, resetDrones: true, resetShells: true, torpedoCounts: data.torpedoCounts, droneCounts: data.droneCounts, cannonCounts: data.cannonCounts, grenadeCount: data.grenadeCount, beaconCount: data.beaconCount, lureCount: data.lureCount });
    playerMesh.getChildren()[0].dispose();
    loadBoatModel(data.boat.model, (mesh) => {
        mesh.rotation.y = modelRotationOffset;
        mesh.computeWorldMatrix(true);
        let bounds = mesh.getHierarchyBoundingVectors(true);
        const rawLengthX = bounds.max.x - bounds.min.x;
        const targetUnits = metersToUnits(data.boat.lengthMeters || 100);
        const scale = rawLengthX > 0 ? targetUnits / rawLengthX : 1;
        mesh.scaling.scaleInPlace(scale);
        mesh.computeWorldMatrix(true);
        bounds = mesh.getHierarchyBoundingVectors(true);
        const center = bounds.min.add(bounds.max).scale(0.5);
        mesh.position.x -= center.x;
        mesh.position.z -= center.z;
        boatHalfLength = (bounds.max.x - bounds.min.x) / 2;
        boatHalfWidth = (bounds.max.z - bounds.min.z) / 2;
        mesh.parent = playerMesh;
    });
    console.log("Changed to:", data.boatType);
});

socket.on("other_boat_changed", (data) => {
    if (otherPlayers[data.id]) {
        const wrapper = otherPlayers[data.id];
        wrapper.getChildren()[0].dispose();
        const offset = data.boat.modelRotationOffset || 0;
        loadBoatModel(data.boat.model, (mesh) => {
            mesh.rotation.y = offset;
            mesh.computeWorldMatrix(true);
            let bounds = mesh.getHierarchyBoundingVectors(true);
            const rawLengthX = bounds.max.x - bounds.min.x;
            const targetUnits = metersToUnits(data.boat.lengthMeters || 100);
            const scale = rawLengthX > 0 ? targetUnits / rawLengthX : 1;
            mesh.scaling.scaleInPlace(scale);
            mesh.computeWorldMatrix(true);
            bounds = mesh.getHierarchyBoundingVectors(true);
            const center = bounds.min.add(bounds.max).scale(0.5);
            mesh.position.x -= center.x;
            mesh.position.z -= center.z;
            mesh.parent = wrapper;
        });
        otherPlayersInfo[data.id] = {
            baseNoise: (data.boat && data.boat.noise) || 0,
            minNoise: (data.boat && data.boat.minNoise) || 0,
            baseSpeed: knotsToUnitPerSecond(((data.boat && data.boat.speed) || 25) / 2),
            maxSpeedKnots: (data.boat && data.boat.speed) || 25,
            speedNoiseLimit: (data.boat && typeof data.boat.speedNoiseLimit === "number") ? data.boat.speedNoiseLimit : 0,
            boatType: data.boatType || null,
            lengthMeters: (data.boat && data.boat.lengthMeters) || 100,
            teamId: data.team_id || null,
            teamName: data.team_name || null,
        };
        // Rafraîchir le Boat distant.
        if (remoteBoats[data.id]) {
            const newBoat = new Boat({
                id: data.id,
                isLocal: false,
                boatType: data.boatType,
                boatData: data.boat,
                mesh: wrapper,
            });
            remoteBoats[data.id] = newBoat;
            // Si on observait ce bateau, mettre viewedBoat à jour vers la nouvelle instance.
            if (viewedBoat && viewedBoat.id === data.id) {
                viewedBoat = newBoat;
            }
        }
    }
});

socket.on("player_joined", (data) => {
    if (!initialized) return;
    createOtherPlayer(data);
    const typeLabel = data.boatType === "submarine" ? "sous-marin" : data.boatType === "destroyer" ? "destroyer" : data.boatType;
    setTransientMessage("Nouveau joueur : " + typeLabel);
});

// Multi-bateaux : le serveur signale qu'un bateau supplémentaire a été créé
// pour le joueur (cheat addsub/adddest). Le mesh est déjà créé via player_joined
// (broadcast à tous). Ici on enregistre juste le mapping ghostSid → playerId et
// les ammos. Le bateau commence en autopilote serveur (cf. handle_set_active_boat).
socket.on("own_boat_added", (data) => {
    const t = (data.boat && data.boat.torpedoes) || {};
    const initialMine = {
        surface:   ((data.boat && data.boat.mineSurf)      || {}).number || 0,
        bottom:    ((data.boat && data.boat.mineBottom)    || {}).number || 0,
        suspended: ((data.boat && data.boat.mineSuspended) || {}).number || 0,
    };
    boatAmmo[data.ghostSid] = {
        boat: data.boat,
        boatType: data.boatType,
        torpedo: data.torpedoCounts || {},
        torpedoInitial: {
            acoustic: (t.acoustic && t.acoustic.count) || 0,
            wireGuided: (t.wireGuided && t.wireGuided.count) || 0,
            autonomous: (t.autonomous && t.autonomous.count) || 0,
        },
        drone: data.droneCounts || {},
        grenade: data.grenadeCount || 0,
        cannon: data.cannonCounts || {},
        beacon: data.beaconCount || 0,
        lure: data.lureCount || 0,
        mine: data.mineCounts || {},
        mineInitial: initialMine,
    };
    // Le mesh est dans otherPlayers[playerId] (créé par player_joined). On lie le
    // bateau à localBoats avec une référence vers ce wrapper.
    const wrapper = otherPlayers[data.playerId] || null;
    let boatRef = null;
    if (wrapper) {
        // Réutilise une instance Boat-like minimal autour du wrapper.
        boatRef = {
            id: data.playerId,
            isLocal: true,
            boatType: data.boatType,
            boatData: data.boat,
            mesh: wrapper,
        };
    }
    localBoats.push({
        ghostSid: data.ghostSid,
        playerId: data.playerId,
        boat: boatRef,
        sunk: false,
    });
    setTransientMessage("Nouveau bateau prêt — Tab pour basculer (" + (data.boatType === "submarine" ? "sub" : "dest") + ")");
});

socket.on("player_left", (data) => {
    delete otherPlayerLoadGeneration[data.id];
    if (otherPlayers[data.id]) {
        otherPlayers[data.id].dispose();
        delete otherPlayers[data.id];
    }
    delete otherPlayersHistory[data.id];
    delete otherPlayersInfo[data.id];
    delete moveArrivalDiag[data.id];
    delete wrapperFrameDeltas[data.id];
    delete sonarRevealedUntil[data.id];
    delete passiveSonarDetectionsUntil[data.id];
    delete droneDiscoveredEnemies[data.id];
    if (window._botSpeedMult) delete window._botSpeedMult[data.id];
    delete remoteSinking[data.id];
    // Multi-bateaux : si c'est un de mes bateaux secondaires qui est retiré
    // après son naufrage, le sortir de localBoats.
    for (let i = localBoats.length - 1; i >= 0; i--) {
        if (localBoats[i].playerId === data.id) {
            delete boatAmmo[ammoKey(localBoats[i].ghostSid)];
            selfControlledPlayerIds.delete(localBoats[i].playerId);
            localBoats.splice(i, 1);
            if (activeBoatIndex >= localBoats.length) activeBoatIndex = Math.max(0, localBoats.length - 1);
            break;
        }
    }
    if (selectedBoatId === data.id) selectedBoatId = null;
    if (viewedBotId() === data.id) {
        // Le bot observé vient de partir : retour à localBoat.
        exitBotView();
    }
    if (remoteBoats[data.id]) {
        delete remoteBoats[data.id];
    }
    for (const key in remoteTorpedoes) {
        if (remoteTorpedoes[key].ownerId === data.id) removeRemoteTorpedo(key);
    }
    for (const key in remoteDrones) {
        const r = remoteDrones[key];
        if (r.ownerId === data.id) {
            if (r.mesh) disposeDroneMesh(r.mesh);
            if (selectedDroneKey === key) selectedDroneKey = null;
            delete remoteDrones[key];
        }
    }
    for (let i = grenades.length - 1; i >= 0; i--) {
        const grenade = grenades[i];
        if (grenade.shooterId !== data.id) continue;
        if (grenade.mesh) grenade.mesh.dispose(false, true);
        for (const effect of grenade.explosionMeshes || []) effect.mesh.dispose(false, true);
        if (grenade._hudId) removeGrenadeHud(grenade, "annulée");
        grenades.splice(i, 1);
    }
});

socket.on("position_correct", (data) => {
    // Le serveur a refusé une position (anti-cheat ou bord du monde / île)
    // ou a corrigé un saut détecté lors d'un retour de focus (autopilote
    // qui avait avancé pendant l'absence). On téléporte à la position serveur,
    // mais on garde la vitesse/rudder courants pour ne pas arrêter brutalement
    // un bateau qui était en train de naviguer normalement.
    if (!playerMesh || !data) return;
    playerMesh.position.x = data.x;
    playerMesh.position.z = data.z;
    if (typeof data.y === "number") playerMesh.position.y = data.y;
    if (typeof data.rotation === "number") {
        playerRotation = data.rotation;
        playerMesh.rotation.y = data.rotation;
    }
    // Cas spécifique : si la correction est déclenchée par "speed" (saut trop
    // grand) ou "resume" (retour d'onglet, le serveur téléporte au point où
    // l'autopilote a amené le bateau), on garde l'élan ; pour les autres
    // causes (out_of_bounds, on_island) on stoppe.
    const reason = data.reason || "";
    if (reason !== "speed" && reason !== "resume") {
        boatSpeed = 0;
        rudderAngle = 0;
    }
});

socket.on("player_moved", (data) => {
    // Multi-bateaux : on ignore les player_moved du bateau qu'on simule localement
    // pour éviter que le lissage serveur combatte la simu locale.
    if (selfControlledPlayerIds.has(data.id)) return;
    // Multi-bateaux : si c'est un de mes bateaux non actifs (autopiloté serveur),
    // on stocke les cibles sur son mesh et le lissage les interpole à 60 fps
    // (cf. smoothRemotePlayers + smoothOwnAutopilotBoats).
    for (const entry of localBoats) {
        if (entry.playerId !== data.id) continue;
        // Mémorise la dernière vitesse/cap reçus du serveur. Sert à initialiser
        // boatSpeed quand on Tab sur ce bateau : on prend l'état serveur courant
        // (qui peut être 0 si le bateau s'est arrêté de lui-même) plutôt que
        // la vitesse au moment du dernier switch.
        const ak = ammoKey(entry.ghostSid);
        const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
        slot.lastServerSpeedRatio = data.speedRatio || 0;
        slot.lastServerReverse = !!data.reverse;
        slot.lastServerRudder = data.rudder || 0;
        slot.lastServerRotation = data.rotation;
        const m = entry.boat && entry.boat.mesh;
        if (m) {
            m.targetX = data.position.x;
            m.targetZ = data.position.z;
            m.targetY = data.position.y || 0;
            m.targetRotY = data.rotation;
            if (typeof m._smoothInit === "undefined") {
                m.position.x = m.targetX;
                m.position.z = m.targetZ;
                m.position.y = m.targetY;
                m.rotation.y = m.targetRotY;
                m._smoothInit = true;
            }
        }
        // Peupler aussi otherPlayersHistory pour ce bateau secondaire — sinon
        // la génération de wake côté client ne le voit pas.
        const prevHist = otherPlayersHistory[data.id];
        const noiseSr = data.speedRatio || 0;
        const baseNoise = (data.boat && data.boat.noise) || 0;
        otherPlayersHistory[data.id] = {
            x: data.position.x, z: data.position.z, rot: data.rotation,
            t: performance.now(),
            noise: baseNoise * noiseSr,
            speedRatio: noiseSr,
            reverse: !!data.reverse,
            integrity: typeof data.integrity === "number" ? data.integrity
                       : (prevHist && prevHist.integrity),
            submerged: !!data.submerged,
        };
        return;
    }
    if (otherPlayers[data.id]) {
        const wrapper = otherPlayers[data.id];
        const prev = otherPlayersHistory[data.id];
        const info = otherPlayersInfo[data.id];
        const now = performance.now();
        const diag = moveArrivalDiag[data.id] || (moveArrivalDiag[data.id] = { last: 0, intervals: [] });
        if (diag.last) {
            const dtMs = now - diag.last;
            diag.intervals.push(dtMs);
            if (diag.intervals.length > 200) diag.intervals.shift();
        }
        diag.last = now;
        let noise = 0;
        let speedRatio = 0;
        if (prev && info && info.baseSpeed > 0) {
            if (typeof data.speedRatio === "number") {
                speedRatio = data.speedRatio;
                const baseSpeedWorld = info.baseSpeed;
                const equivInstSpeed = speedRatio * 2 * baseSpeedWorld;
                noise = info.baseNoise * (equivInstSpeed / baseSpeedWorld);
            } else {
                const dx = data.position.x - prev.x;
                const dz = data.position.z - prev.z;
                const dt = Math.max(0.001, (now - prev.t) / 1000);
                const instSpeedWorld = Math.sqrt(dx * dx + dz * dz) / dt;
                const baseSpeedWorld = info.baseSpeed;
                speedRatio = instSpeedWorld / (baseSpeedWorld * 2);
                noise = info.baseNoise * (instSpeedWorld / baseSpeedWorld);
            }
            const rudder = Math.abs(data.rudder || 0);
            const turnFactor = 1 + Math.min(1, rudder / RUDDER_MAX);
            // Marche arrière : même bruit que la marche avant (plus de bonus ×4).
            noise *= turnFactor;
        }
        otherPlayersHistory[data.id] = { x: data.position.x, z: data.position.z, rot: data.rotation, t: now, noise, speedRatio, reverse: !!data.reverse, integrity: typeof data.integrity === "number" ? data.integrity : (otherPlayersHistory[data.id] && otherPlayersHistory[data.id].integrity), submerged: !!data.submerged };
        wrapper.targetX = data.position.x;
        wrapper.targetZ = data.position.z;
        wrapper.targetY = data.position.y || 0;
        wrapper.targetRotY = data.rotation;
        if (typeof wrapper._smoothInit === "undefined") {
            wrapper.position.x = wrapper.targetX;
            wrapper.position.z = wrapper.targetZ;
            wrapper.position.y = wrapper.targetY;
            wrapper.rotation.y = wrapper.targetRotY;
            wrapper._smoothInit = true;
        }
    }
});

const wrapperFrameDeltas = {};
function smoothRemotePlayers(dt) {
    const factor = 1 - Math.exp(-dt * 12);
    // Lisse aussi les bateaux du joueur en autopilote dont le mesh n'est pas
    // dans otherPlayers (typiquement le bateau primaire). Le bateau actif est
    // exclu via selfControlledPlayerIds.
    for (const entry of localBoats) {
        if (!entry || entry.sunk) continue;
        if (entry.playerId && selfControlledPlayerIds.has(entry.playerId)) continue;
        const m = entry.boat && entry.boat.mesh;
        if (!m || typeof m.targetX !== "number") continue;
        // Si le mesh est aussi dans otherPlayers, la boucle ci-dessous le lissera ;
        // pas besoin d'agir ici.
        if (entry.playerId && otherPlayers[entry.playerId] === m) continue;
        m.position.x += (m.targetX - m.position.x) * factor;
        m.position.z += (m.targetZ - m.position.z) * factor;
        m.position.y += (m.targetY - m.position.y) * factor;
        let dr0 = m.targetRotY - m.rotation.y;
        while (dr0 > Math.PI) dr0 -= 2 * Math.PI;
        while (dr0 < -Math.PI) dr0 += 2 * Math.PI;
        m.rotation.y += dr0 * factor;
    }
    for (const id in otherPlayers) {
        // Multi-bateaux : ne pas lisser le wrapper du bateau qu'on simule
        // localement (sinon le lissage tirerait la position vers la dernière
        // cible figée et combattrait la simu locale).
        if (selfControlledPlayerIds.has(id)) continue;
        // Bateau distant en train de couler : laisser animateSecondarySinking
        // gérer la descente (sinon le lissage tirerait vers targetY=0).
        if (remoteSinking[id]) continue;
        const w = otherPlayers[id];
        if (typeof w.targetX !== "number") continue;
        const px = w.position.x, pz = w.position.z;
        w.position.x += (w.targetX - w.position.x) * factor;
        w.position.z += (w.targetZ - w.position.z) * factor;
        w.position.y += (w.targetY - w.position.y) * factor;
        let dr = w.targetRotY - w.rotation.y;
        while (dr > Math.PI) dr -= 2 * Math.PI;
        while (dr < -Math.PI) dr += 2 * Math.PI;
        w.rotation.y += dr * factor;
        if (fpsOverlayEl) {
            const dx = w.position.x - px, dz = w.position.z - pz;
            const dmove = Math.sqrt(dx * dx + dz * dz);
            const arr = wrapperFrameDeltas[id] || (wrapperFrameDeltas[id] = []);
            arr.push(dmove);
            if (arr.length > 120) arr.shift();
        }
    }
}
window.dumpWrapperDeltas = function () {
    const out = {};
    for (const id in wrapperFrameDeltas) {
        const arr = wrapperFrameDeltas[id].slice().sort((a, b) => a - b);
        if (!arr.length) continue;
        const sum = arr.reduce((s, v) => s + v, 0);
        out[id] = {
            n: arr.length,
            min: arr[0].toFixed(3),
            med: arr[Math.floor(arr.length / 2)].toFixed(3),
            mean: (sum / arr.length).toFixed(3),
            p95: arr[Math.floor(arr.length * 0.95)].toFixed(3),
            max: arr[arr.length - 1].toFixed(3),
            zeros: wrapperFrameDeltas[id].filter(v => v < 1e-5).length,
        };
    }
    console.table(out);
    return out;
};

socket.on("wake_spawned", (data) => {
    const opts = data.submerged
        ? { radius: 0.12, y: (typeof data.y === "number" ? data.y + 0.05 : 0.05), alpha: 0.25 }
        : undefined;
    spawnWakeDot(data.x, data.z, performance.now(), opts);
});

function applyDayCycleSnapshot(snap) {
    if (!snap) return;
    dayCycleClockOffset = snap.now - Date.now() / 1000;
    dayCycleStartedAt = snap.startedAt;
    dayCycleStartTimeOfDay = snap.startTimeOfDay;
    dayCycleSpeed = (typeof snap.speed === "number") ? snap.speed : 1;
    dayCycleEndsAt = snap.endsAt || 0;
    if (snap.dayDuration) DAY_DURATION = snap.dayDuration;
    dayCycleState = snap.state;
    dayCycleDoneSignaled = false;
    if (dayCycleState === "off") {
        timeOfDay = 0;
        if (sunLight) resetDayLighting();
    }
}

socket.on("day_cycle_state", (snap) => {
    applyDayCycleSnapshot(snap);
});

socket.on("grenade_exploded", (data) => {
    for (let i = grenades.length - 1; i >= 0; i--) {
        const g = grenades[i];
        if (g.shooterId === data.id && g.gid === data.gid && g.phase !== "explode") {
            const dealt = data.dealt || 0;
            const msg = dealt > 0 ? "explosion : -" + Math.round(dealt) + "%" : "explosion : raté";
            if (g._hudId) removeGrenadeHud(g, msg);
            if (g.mesh) { g.mesh.dispose(false, true); g.mesh = null; }
            grenades.splice(i, 1);
            break;
        }
    }
    spawnRemoteExplosion(data.x, data.y, data.z, false);
    destroyLuresNearExplosion(data.x, data.z);
    triggerDamageFlash(data.x, data.y, data.z);
});

socket.on("grenade_launched", (data) => {
    // La prédiction locale peut appartenir à un bateau quitté entre l'intent et
    // l'acquittement : associer par tireur plutôt que par playerId courant.
    const localG = grenades.find(g => g.local && !g.gid && g.shooterId === data.shooterId);
    if (localG) {
        localG.gid = data.gid;
        return;
    }
    spawnGrenadeTrajectory(data.x, data.y, data.z, data.vx, data.vy, data.vz, data.targetDepth, data.sinkSpeed);
    const g = grenades[grenades.length - 1];
    g.remote = true;
    g.shooterId = data.shooterId;
    g.gid = data.gid;
    revealShooterFromFire(data.shooterId);
    if (currentBoatType === "submarine" && playerMesh && isLineOfSightClear(data.x, data.z, null)) {
        showGrenadeAlert();
    }
});

function ensureIncomingTorpedoContainer() {
    let c = document.getElementById("incomingTorpedoes");
    if (!c) {
        c = document.createElement("div");
        c.id = "incomingTorpedoes";
        c.style.cssText = "position:absolute;top:10px;left:10px;display:flex;flex-direction:column;gap:4px;z-index:50;pointer-events:none;font-family:sans-serif;font-size:14px;";
        document.body.appendChild(c);
    }
    return c;
}

let grenadeAlertTimer = null;
function showGrenadeAlert() {
    const c = ensureIncomingTorpedoContainer();
    let el = document.getElementById("grenadeAlert");
    if (!el) {
        el = document.createElement("div");
        el.id = "grenadeAlert";
        el.style.cssText = "background:rgba(120,40,40,0.85);color:#fff;padding:6px 10px;border-radius:4px;";
        c.appendChild(el);
    }
    el.textContent = "⚠ Grenades anti-sous-marines !";
    el.style.display = "block";
    clearTimeout(grenadeAlertTimer);
    grenadeAlertTimer = setTimeout(() => {
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }, 5000);
}

let sonarDetectedAlertTimer = null;
function showSonarDetectedAlert() {
    const c = ensureIncomingTorpedoContainer();
    let el = document.getElementById("sonarDetectedAlert");
    if (!el) {
        el = document.createElement("div");
        el.id = "sonarDetectedAlert";
        el.style.cssText = "background:rgba(200,100,0,0.9);color:#fff;padding:8px 12px;border-radius:4px;font-weight:bold;font-size:15px;";
        c.appendChild(el);
    }
    el.textContent = "⚠ Détecté par sonar actif !";
    el.style.display = "block";
    clearTimeout(sonarDetectedAlertTimer);
    sonarDetectedAlertTimer = setTimeout(() => {
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }, 3000);
}

function revealShooterFromFire(shooterId) {
    if (!shooterId || shooterId === playerId) return;
    if (!otherPlayers[shooterId]) return;
    sonarRevealedUntil[shooterId] = performance.now() + 10000;
}

const droneDiscoveredEnemies = {};
function showDroneDiscoveryMessage(enemyId) {
    if (droneDiscoveredEnemies[enemyId]) return;
    droneDiscoveredEnemies[enemyId] = Date.now();
    let c = document.getElementById("incomingTorpedoes");
    if (!c) {
        c = document.createElement("div");
        c.id = "incomingTorpedoes";
        c.style.cssText = "position:absolute;top:10px;left:10px;display:flex;flex-direction:column;gap:4px;z-index:50;pointer-events:none;font-family:sans-serif;font-size:14px;";
        document.body.appendChild(c);
    }
    const el = document.createElement("div");
    el.style.cssText = "background:rgba(40,110,50,0.85);color:#fff;padding:6px 10px;border-radius:4px;";
    el.textContent = "Drone : contact ennemi détecté";
    c.appendChild(el);
    setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 10000);
}
function clearDroneDiscovery(enemyId) {
    delete droneDiscoveredEnemies[enemyId];
}


socket.on("torpedo_state", (data) => {
    const key = data.ownerId + ":" + data.tid;
    let r = remoteTorpedoes[key];
    if (!r) {
        const mesh = BABYLON.MeshBuilder.CreateCylinder("torpedo_" + key, { height: 1.4, diameter: 0.18 }, scene);
        mesh.rotation.z = Math.PI / 2;
        if (!remoteTorpedoMaterial) {
            remoteTorpedoMaterial = new BABYLON.StandardMaterial("torpedoRemoteMat", scene);
            remoteTorpedoMaterial.diffuseColor = new BABYLON.Color3(1, 1, 1);
            remoteTorpedoMaterial.emissiveColor = new BABYLON.Color3(0.85, 0.85, 0.85);
            remoteTorpedoMaterial.specularColor = new BABYLON.Color3(0.3, 0.3, 0.3);
        }
        mesh.material = remoteTorpedoMaterial;
        exemptFromClipPlane(mesh);
        r = { mesh, trail: null };
        remoteTorpedoes[key] = r;
        if (data.ownerId !== playerId) revealShooterFromFire(data.ownerId);
        // Si c'est ma torpille filoguidée, mémoriser la clé active.
        if (data.ownerId === playerId && data.kind === "wireGuided") {
            activeWireTorpedoKey = key;
            lastWireSteerYaw = 0;
            lastWirePitch = 0;
            updateTorpedoPanel();
        }
    }
    // Vitesse instantanée mesurée depuis le dernier état serveur pour le HUD
    // filoguidée et pour l'extrapolation 10 Hz → 60 fps côté client.
    const nowPerf = performance.now();
    if (typeof r.srvX === "number" && typeof r.lastUpdate === "number") {
        const dtMs = Math.max(1, nowPerf - r.lastUpdate);
        const ddx = data.x - r.srvX;
        const ddy = (data.y || 0) - (r.srvY || 0);
        const ddz = data.z - r.srvZ;
        const distU = Math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz);
        r.lastSpeedUS = distU / (dtMs / 1000);
    }
    // Position serveur reçue = cible d'extrapolation. r.x/y/z restent la position
    // RENDUE (extrapolée chaque frame dans updateRemoteTorpedoes).
    r.srvX = data.x; r.srvY = data.y; r.srvZ = data.z;
    r.dirX = data.dirX; r.dirZ = data.dirZ;
    r.kind = data.kind;
    r.ownerId = data.ownerId;
    r.tid = data.tid;
    r.tx = (typeof data.tx === "number") ? data.tx : null;
    r.ty = (typeof data.ty === "number") ? data.ty : null;
    r.tz = (typeof data.tz === "number") ? data.tz : null;
    r.lastUpdate = nowPerf;
    // Au premier état, initialiser la position rendue sur la position serveur.
    if (typeof r.x !== "number") {
        r.x = data.x; r.y = data.y; r.z = data.z;
    }
    r.mesh.position.set(r.x, r.y, r.z);
    r.mesh.rotation.y = -Math.atan2(r.dirZ, r.dirX);
});

socket.on("torpedo_dead", (data) => {
    const key = data.ownerId + ":" + data.tid;
    removeRemoteTorpedo(key);
    if (activeWireTorpedoKey === key) {
        activeWireTorpedoKey = null;
        updateTorpedoPanel();
    }
});

socket.on("torpedo_counts", (counts) => {
    if (!counts) return;
    const ak = ammoKey(counts.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    slot.torpedo = slot.torpedo || {};
    for (const k of ["acoustic", "wireGuided", "autonomous"]) {
        if (typeof counts[k] === "number") slot.torpedo[k] = counts[k];
    }
    // Si c'est le bateau actif, on met aussi à jour les compteurs visibles.
    if (ak === ammoKey(activeGhostSid())) {
        for (const k of ["acoustic", "wireGuided", "autonomous"]) {
            if (typeof counts[k] === "number") torpedoCounts[k] = counts[k];
        }
        updateTorpedoPanel();
    }
});

function _markEntrySunk(playerId) {
    for (const entry of localBoats) {
        if (entry.playerId === playerId) {
            if (entry.sunk) return entry;
            entry.sunk = true;
            // État d'animation de naufrage pour le mesh secondaire (le primaire
            // utilise startSinking + boucle isSinking globale).
            entry._sinkTilt = 0;
            entry._sinkTiltAxis = Math.random() < 0.5 ? 1 : -1;
            return entry;
        }
    }
    return null;
}

// Animation de naufrage pour les bateaux distants (autres joueurs ou mes
// bateaux secondaires non actifs). Indexé par playerId.
const remoteSinking = {};

socket.on("boat_sunk", (data) => {
    if (data.victimId) {
        const entry = _markEntrySunk(data.victimId);
        if (entry && data.victimId !== playerId) {
            setTransientMessage("Un de vos bateaux a coulé — Tab pour passer au suivant");
        }
        // Marquer ce playerId comme en naufrage pour l'animer côté client
        // (mesh de mes bateaux secondaires + mesh des autres joueurs).
        if (data.victimId !== playerId && !remoteSinking[data.victimId]) {
            remoteSinking[data.victimId] = {
                tilt: 0,
                tiltAxis: Math.random() < 0.5 ? 1 : -1,
            };
        }
    }
    if (data.victimId && data.victimId === playerId) {
        boatIntegrity = 0;
        startSinking(data.attackerId || null);
    }
    if (data.attackerId) {
        // Affiche le kill banner si l'attaquant est moi, un de mes bateaux
        // secondaires (multi-boat), ou un coéquipier de la même équipe.
        let isMine = (data.attackerId === playerId);
        if (!isMine && typeof localBoats !== "undefined") {
            for (const entry of localBoats) {
                if (entry.playerId === data.attackerId) { isMine = true; break; }
            }
        }
        let isAlly = false;
        if (!isMine && selectedTeamId) {
            const info = otherPlayersInfo[data.attackerId];
            if (info && info.teamId === selectedTeamId) isAlly = true;
        }
        if (isMine) {
            showKillBanner("Cible coulée !");
        } else if (isAlly) {
            // Type de la victime pour personnaliser le message.
            const vinfo = otherPlayersInfo[data.victimId];
            const vtype = vinfo && vinfo.boatType;
            const label = vtype === "submarine" ? "sous-marin"
                : vtype === "destroyer" ? "destroyer"
                : "bateau";
            const article = vtype === "destroyer" ? "Un destroyer" : "Un " + label;
            showKillBanner(article + " a été coulé");
        }
    }
});

// Émis explicitement au propriétaire pour les bateaux secondaires.
socket.on("own_boat_sunk", (data) => {
    if (!data) return;
    const entry = _markEntrySunk(data.playerId);
    if (entry) setTransientMessage("Un de vos bateaux a coulé — Tab pour passer au suivant");
});

function animateSecondarySinking(dt) {
    // Anime tous les bateaux distants en train de couler : mes bateaux
    // secondaires + les bateaux des autres joueurs (broadcast boat_sunk).
    const SINK_RATE = 0.25;
    const TILT_MAX = Math.PI / 18;
    for (const pid in remoteSinking) {
        const state = remoteSinking[pid];
        if (state.done) continue;
        // Mesh : on essaie d'abord otherPlayers (cas standard distants), puis
        // localBoats (mes bateaux secondaires).
        let m = otherPlayers[pid] || null;
        if (!m) {
            for (const entry of localBoats) {
                if (entry.playerId === pid && entry.boat && entry.boat.mesh) {
                    m = entry.boat.mesh;
                    break;
                }
            }
        }
        if (!m) continue;
        m.position.y -= SINK_RATE * dt;
        state.tilt = Math.min(TILT_MAX, state.tilt + (TILT_MAX / 8) * dt);
        const yawQ = BABYLON.Quaternion.RotationAxis(BABYLON.Axis.Y, m.rotation.y || 0);
        const pitchQ = BABYLON.Quaternion.RotationAxis(BABYLON.Axis.Z, state.tilt * state.tiltAxis);
        m.rotationQuaternion = yawQ.multiply(pitchQ);
        if (m.position.y < -8) {
            m.setEnabled(false);
            state.done = true;
        }
    }
}

function setViewedBotBanner(text) {
    let b = document.getElementById("viewedBotBanner");
    if (!text) {
        if (b) b.remove();
        return;
    }
    if (!b) {
        b = document.createElement("div");
        b.id = "viewedBotBanner";
        b.style.cssText = "position:absolute;top:36px;left:50%;transform:translateX(-50%);background:rgba(80,40,120,0.85);color:#fff;padding:6px 14px;border-radius:5px;font-family:monospace;font-size:13px;z-index:30";
        document.body.appendChild(b);
    }
    b.textContent = text;
}

function enterBotView(botId, botBoat, botBoatType) {
    const wrapper = otherPlayers[botId];
    if (!wrapper || !localBoat || !botBoat || !botBoatType) return;
    // S'assurer que remoteBoats[botId] existe et est synchronisé.
    let bot = remoteBoats[botId];
    if (!bot) {
        bot = new Boat({ id: botId, isLocal: false, boatType: botBoatType, boatData: botBoat, mesh: wrapper });
        remoteBoats[botId] = bot;
    } else {
        // Rafraîchir specs/munitions à l'instanciation.
        bot.boatData = botBoat;
        bot.boatType = botBoatType;
        bot.mesh = wrapper;
    }
    viewedBoat = bot;
    // Le serveur autopilote le destroyer pendant la vue bot.
    // On retire le playerId du filtre pour accepter les player_moved serveur.
    selfControlledPlayerIds.delete(playerId);
    // Mémoriser l'état pour restauration au retour.
    window._preBotViewMaxSpeed = maxSpeed;
    diveRate = 0;
    periscopeTarget = null;
    autoDecelerate = false;
    // Snap caméra directement derrière le bot.
    playerRotation = wrapper.rotation.y || 0;
    cameraAlpha = -playerRotation;
    cameraAlphaOffset = 0;
    applyBoatConfig(botBoat, botBoatType, {});
    setViewedBotBanner("Vue : " + botId + " (taper self pour revenir)");
}

function exitBotView() {
    viewedBoat = localBoat;
    if (originalBoatData && originalBoatType) {
        applyBoatConfig(originalBoatData, originalBoatType, {});
    }
    setViewedBotBanner(null);
    // Restaurer maxSpeed.
    if (typeof window._preBotViewMaxSpeed === "number") {
        maxSpeed = window._preBotViewMaxSpeed;
        window._preBotViewMaxSpeed = undefined;
    }
    // Reprendre le contrôle local — empêcher les player_moved serveur d'écraser la simu.
    selfControlledPlayerIds.add(playerId);
    // Lire l'état courant du destroyer depuis le serveur (position lissée + dernière vitesse reçue).
    const lm = localBoat && localBoat.mesh;
    if (lm) {
        playerRotation = lm.rotation.y;
        cameraAlpha = -playerRotation;
        cameraAlphaOffset = 0;
    }
    const ak = ammoKey(null);
    const slot = boatAmmo[ak];
    if (slot && typeof slot.lastServerSpeedRatio === "number") {
        let sr = slot.lastServerSpeedRatio;
        if (sr > 0.95) sr = 1.0;
        const rev = slot.lastServerReverse;
        boatSpeed = sr * maxSpeed * (rev ? -1 : 1);
        rudderAngle = slot.lastServerRudder || 0;
    }
    autoDecelerate = false;
    // Reset visuels de plongée au cas où on revenait d'un sub immergé.
    scene.clipPlane = null;
    scene.fogMode = BABYLON.Scene.FOGMODE_NONE;
    scene.clearColor = new BABYLON.Color3(0.5, 0.7, 0.9);
    if (oceanMesh) oceanMesh.isVisible = true;
    if (seabedMesh) seabedMesh.isVisible = false;
    lastSubSubmerged = false;
}

socket.on("cheat_view_bot", (data) => {
    if (data && data.botId && data.boat && data.boatType) {
        enterBotView(data.botId, data.boat, data.boatType);
    }
});

socket.on("cheat_view_self", () => {
    exitBotView();
});

socket.on("cheat_bots_calmdown_state", (data) => {
    setTransientMessage(data && data.passive ? "Bots passifs (calmdown ON)" : "Bots actifs (calmdown OFF)");
});

socket.on("cheat_debug_state", (data) => {
    if (data.all) updateDebugLogPanel(data.all);
});

const DEBUG_LOG_CATEGORIES = ["grenades", "torpilles", "deplacement", "sonar", "webSocket"];
let debugLogPanelEl = null;
let debugCurrentTestName = "";
let debugTestRunning = false;

function toggleDebugLogPanel() {
    if (debugLogPanelEl) {
        debugLogPanelEl.remove();
        debugLogPanelEl = null;
        return;
    }
    const panel = document.createElement("div");
    panel.id = "debugLogPanel";
    panel.style.cssText = "position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#1a1a2e;border:2px solid #0f0;border-radius:8px;padding:16px;z-index:99999;color:#0f0;font:14px monospace;min-width:280px;";
    const topBar = document.createElement("div");
    topBar.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;";
    const title = document.createElement("div");
    title.textContent = "Debug Logs";
    title.style.cssText = "font-size:16px;font-weight:bold;";
    const xBtn = document.createElement("button");
    xBtn.textContent = "×";
    xBtn.style.cssText = "background:none;border:none;color:#0f0;font-size:20px;cursor:pointer;padding:0 4px;line-height:1;";
    xBtn.addEventListener("click", () => { panel.remove(); debugLogPanelEl = null; });
    topBar.appendChild(title);
    topBar.appendChild(xBtn);
    panel.appendChild(topBar);
    for (const cat of DEBUG_LOG_CATEGORIES) {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin:6px 0;";
        const cbId = "dbgcat_" + cat;
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.id = cbId;
        cb.dataset.cat = cat;
        cb.style.cssText = "width:16px;height:16px;cursor:pointer;";
        cb.addEventListener("change", () => {
            socket.emit("cheat_debug_toggle", { category: cat });
        });
        const lbl = document.createElement("label");
        lbl.htmlFor = cbId;
        lbl.textContent = cat;
        lbl.style.cssText = "cursor:pointer;";
        row.appendChild(cb);
        row.appendChild(lbl);
        panel.appendChild(row);
    }
    const sep = document.createElement("hr");
    sep.style.cssText = "border:none;border-top:1px solid #0f0;margin:12px 0;";
    panel.appendChild(sep);
    const testRow = document.createElement("div");
    testRow.style.cssText = "display:flex;align-items:center;gap:6px;margin-bottom:8px;";
    const testInput = document.createElement("input");
    testInput.type = "text";
    testInput.placeholder = "Nom du test";
    testInput.value = debugCurrentTestName;
    testInput.style.cssText = "flex:1;padding:4px 6px;background:#111;color:#0f0;border:1px solid #0f0;border-radius:3px;font:12px monospace;";
    testInput.id = "debugTestNameInput";
    testInput.addEventListener("keydown", (e) => e.stopPropagation());
    testRow.appendChild(testInput);
    panel.appendChild(testRow);
    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;gap:8px;margin-bottom:8px;";
    const btnTest = document.createElement("button");
    if (debugTestRunning) {
        btnTest.textContent = "Fin de test";
        btnTest.style.cssText = "flex:1;padding:6px 8px;background:#3a0a0a;color:#f44;border:1px solid #f44;border-radius:4px;cursor:pointer;font:13px monospace;";
    } else {
        btnTest.textContent = "Debut de test";
        btnTest.style.cssText = "flex:1;padding:6px 8px;background:#0a3a0a;color:#0f0;border:1px solid #0f0;border-radius:4px;cursor:pointer;font:13px monospace;";
    }
    btnTest.addEventListener("click", () => {
        const name = testInput.value.trim() || debugCurrentTestName;
        if (!name) { testInput.focus(); return; }
        debugCurrentTestName = name;
        if (debugTestRunning) {
            socket.emit("cheat_debug_test", { action: "end", name: name });
            setTransientMessage("Fin de test : " + name);
            debugTestRunning = false;
        } else {
            socket.emit("cheat_debug_test", { action: "start", name: name });
            setTransientMessage("Debut de test : " + name);
            debugTestRunning = true;
        }
        panel.remove(); debugLogPanelEl = null;
    });
    btnRow.appendChild(btnTest);
    panel.appendChild(btnRow);
    document.body.appendChild(panel);
    debugLogPanelEl = panel;
    socket.emit("cheat_debug_query");
}

function updateDebugLogPanel(activeList) {
    if (!debugLogPanelEl) return;
    const cbs = debugLogPanelEl.querySelectorAll("input[type=checkbox]");
    for (const cb of cbs) {
        const catLower = cb.dataset.cat.toLowerCase();
        cb.checked = activeList.some(c => c.toLowerCase() === catLower);
    }
}

socket.on("cheat_godmode_state", (data) => {
    setTransientMessage(data && data.active ? "Invincible (iddqd ON)" : "Vulnérable (iddqd OFF)");
});

socket.on("lure_dropped", (data) => {
    const expiresAt = performance.now() + (data.durationMs || 0);
    spawnAcousticLureVisual(data.ownerId, data.lid, data.x, data.y, data.z, data.noise || 0, expiresAt);
    const lureId = "lure_" + data.ownerId + ":" + data.lid;
    if (!otherPlayers[lureId]) {
        const node = new BABYLON.TransformNode("other_" + lureId, scene);
        node.position = new BABYLON.Vector3(data.x, data.y || 0, data.z);
        otherPlayers[lureId] = node;
    }
    otherPlayersInfo[lureId] = {
        baseNoise: data.noise || 0,
        minNoise: data.noise || 0,
        baseSpeed: 0,
        maxSpeedKnots: 0,
        speedNoiseLimit: 0,
        boatType: "submarine",
        lengthMeters: 10,
        teamId: null,
        teamName: null,
    };
    otherPlayersHistory[lureId] = {
        t: performance.now(),
        speedRatio: 1,
        reverse: false,
        submerged: true,
        integrity: 100,
    };
});

socket.on("lure_destroyed", (data) => {
    const key = data.ownerId + ":" + data.lid;
    const lure = acousticLures[key];
    if (lure) {
        if (lure.mesh) lure.mesh.dispose(false, true);
        delete acousticLures[key];
    }
    const lureId = "lure_" + key;
    if (otherPlayers[lureId]) { otherPlayers[lureId].dispose(); delete otherPlayers[lureId]; }
    delete otherPlayersInfo[lureId];
    delete otherPlayersHistory[lureId];
    if (selectedBoatId === lureId) { selectedBoatId = null; selectedBoatIsSonar = false; }
});

socket.on("torpedo_exploded", (data) => {
    spawnRemoteExplosion(data.x, data.y, data.z, false);
    destroyLuresNearExplosion(data.x, data.z);
    if (data.directHitId && data.directHitId === playerId) {
        damageFlashUntil = performance.now() + 700;
        return;
    }
    triggerDamageFlash(data.x, data.y, data.z);
});

socket.on("sonar_pinged", (data) => {
    if (!playerMesh) return;
    const now = performance.now();
    const revealRange = typeof data.reveal === "number" ? data.reveal : null;
    // Les pings de balise (id "beacon:...") sont rendus visuellement par
    // l'event `sonar_beacon_ping` (cercle qui respecte la portée). Ici on ne
    // pousse PAS de cercle (sinon doublon map-wide : `range` est en mètres et
    // serait interprété en unités), on déclenche seulement l'alerte sonar.
    const isBeaconPing = typeof data.id === "string" && data.id.startsWith("beacon:");
    if (!isBeaconPing) {
        activePings.push({
            emitterId: data.id,
            x: data.x,
            z: data.z,
            y: typeof data.y === "number" ? data.y : 0,
            emittedAt: now,
            expiresAt: now + SONAR_REVEAL_DURATION,
            coneDeg: typeof data.coneDeg === "number" ? data.coneDeg : 360,
            rotation: typeof data.rotation === "number" ? data.rotation : 0,
            range: typeof data.range === "number" ? data.range : null,
            reveal: revealRange,
        });
    }
    if (currentBoatType === "submarine" && playerMesh.position.y < 0) {
        const dx = playerMesh.position.x - data.x;
        const dz = playerMesh.position.z - data.z;
        const dist = Math.hypot(dx, dz);
        const pingRange = typeof data.range === "number" ? data.range / UNIT_METERS : (revealRange ? revealRange / UNIT_METERS : Infinity);
        if (dist <= pingRange) {
            const coneDeg = typeof data.coneDeg === "number" ? data.coneDeg : 360;
            let inCone = true;
            if (coneDeg < 360 && dist > 0.01) {
                const rot = typeof data.rotation === "number" ? data.rotation : 0;
                const fwdX = -Math.cos(rot);
                const fwdZ = Math.sin(rot);
                const dot = (dx * fwdX + dz * fwdZ) / dist;
                inCone = dot >= Math.cos(coneDeg * Math.PI / 360);
            }
            if (inCone) {
                const pingerY = typeof data.y === "number" ? data.y : 0;
                const thermo = countThermoclinesCrossed(data.x, pingerY, data.z,
                    playerMesh.position.x, playerMesh.position.y, playerMesh.position.z);
                if (thermo === 0) showSonarDetectedAlert();
            }
        }
    }
});

socket.on("drone_state", (data) => {
    const key = data.ownerId + ":" + data.did;
    const isMine = data.ownerId === playerId;
    let r = remoteDrones[key];
    if (!r) {
        const tint = isMine ? DRONE_COLOR_LOCAL : DRONE_COLOR_REMOTE;
        const mesh = makeDroneMesh(isMine ? "drone_local" : "drone_remote", 2, tint);
        r = { ownerId: data.ownerId, did: data.did, mesh, kind: data.kind };
        remoteDrones[key] = r;
        if (isMine) {
            activeDrones.push(r);
            if (data.kind === "manual" && !activeManualDrone) {
                activeManualDrone = r;
                manualDroneControl = true;
                savedCameraBeforeDrone = scene.activeCamera;
                droneCamera = new BABYLON.UniversalCamera("droneCam", new BABYLON.Vector3(data.x, data.y, data.z), scene);
                droneCamera.minZ = 0.05;
                droneCamera.fov = 1.0;
                droneCamera.inputs.clear();
                scene.activeCamera = droneCamera;
                dronePitch = 0;
                lastDroneSteer = { yaw: 0, throttle: 0, climb: 0 };
                updateDroneSwitchButton();
            }
            updateDroneButtons();
        }
    }
    r.x = data.x; r.y = data.y; r.z = data.z;
    r.dirX = data.dirX; r.dirZ = data.dirZ;
    r.kind = data.kind;
    r.returning = data.returning;
    if (typeof data.speed === "number") r.speed = data.speed;
    if (typeof data.autonomy === "number") r.autonomy = data.autonomy;
    if (typeof data.traveled === "number") r.traveled = data.traveled;
    if (typeof data.rangeMeters === "number" && data.rangeMeters > 0) r.rangeMeters = data.rangeMeters;
    r.mesh.position.set(data.x, data.y, data.z);
    r.mesh.rotation.y = -Math.atan2(data.dirZ, data.dirX);
    // Visibilité : on cache mes drones quand je suis immergé (sinon le clipPlane
    // donnerait un rendu bizarre). Les drones d'autrui restent toujours visibles.
    if (isMine) {
        const submerged = currentBoatType === "submarine" && playerMesh && playerMesh.position.y < PERISCOPE_DEPTH;
        r.mesh.setEnabled(!submerged);
    }
    r.lastUpdate = performance.now();
    if (r === activeManualDrone && droneCamera && manualDroneControl) {
        droneCamera.position.set(r.x, r.y, r.z);
        const yaw = Math.atan2(r.dirX, r.dirZ);
        droneCamera.rotation.x = dronePitch;
        droneCamera.rotation.y = yaw;
    }
});

socket.on("drone_dead", (data) => {
    const key = data.ownerId + ":" + data.did;
    const r = remoteDrones[key];
    if (!r) return;
    const isMine = data.ownerId === playerId;
    const reason = data.reason;
    if (isMine) {
        if (r === activeManualDrone) {
            activeManualDrone = null;
            manualDroneControl = false;
            if (droneCamera) {
                if (savedCameraBeforeDrone) scene.activeCamera = savedCameraBeforeDrone;
                droneCamera.dispose();
                droneCamera = null;
                savedCameraBeforeDrone = null;
            }
            updateDroneSwitchButton();
        }
        const idx = activeDrones.indexOf(r);
        if (idx >= 0) activeDrones.splice(idx, 1);
        const kindLabel = r.kind === "manual" ? "manuel" : "automatique";
        if (reason === "recovered") {
            setTransientMessage("Drone " + kindLabel + " récupéré");
        } else if (reason === "shot") {
            spawnDroneCrashVisual(r.x, r.y, r.z, r.dirX, r.dirZ);
            setTransientMessage("Drone " + kindLabel + " abattu !");
        } else if (reason === "crashed") {
            setTransientMessage("Drone " + kindLabel + " perdu (autonomie épuisée)");
        } else {
            setTransientMessage("Drone " + kindLabel + " perdu");
        }
        updateDroneButtons();
    } else if (reason === "shot") {
        spawnDroneCrashVisual(r.x, r.y, r.z, r.dirX, r.dirZ);
    }
    if (r.mesh) disposeDroneMesh(r.mesh);
    if (selectedDroneKey === key) selectedDroneKey = null;
    delete remoteDrones[key];
});

socket.on("drone_counts", (counts) => {
    if (!counts) return;
    const ak = ammoKey(counts.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    slot.drone = slot.drone || {};
    if (typeof counts.automatic === "number") slot.drone.automatic = counts.automatic;
    if (typeof counts.manual === "number") slot.drone.manual = counts.manual;
    if (ak === ammoKey(activeGhostSid())) {
        if (typeof counts.automatic === "number") droneCounts.automatic = counts.automatic;
        if (typeof counts.manual === "number") droneCounts.manual = counts.manual;
        updateDroneButtons();
    }
});

socket.on("cannon_hit", (data) => {
    if (data.targetId !== playerId) return;
    damageFlashUntil = performance.now() + 700;
});

// drone_shot : le serveur émet directement `drone_dead` reason="shot" qui gère
// le crash visuel et la mise à jour des compteurs. On garde cet event broadcast
// uniquement pour signaler le tireur (utilisé par revealShooterFromFire ailleurs).

socket.on("cannon_fire", (data) => {
    spawnCannonTracer(data.kind, data.startX, data.startY, data.startZ, data.endX, data.endY, data.endZ, data.arcHeight, data.duration);
    if (data.impact) {
        setTimeout(() => spawnCannonImpactVisual(data.endX, data.endY, data.endZ), data.duration);
    }
    revealShooterFromFire(data.shooterId);
});

socket.on("cannon_counts", (counts) => {
    if (!counts) return;
    const ak = ammoKey(counts.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    slot.cannon = slot.cannon || {};
    if (typeof counts.cannon === "number") slot.cannon.cannon = counts.cannon;
    if (typeof counts.antiAircraft === "number") slot.cannon.antiAircraft = counts.antiAircraft;
    if (ak === ammoKey(activeGhostSid())) {
        if (typeof counts.cannon === "number") cannonAmmo = counts.cannon;
        if (typeof counts.antiAircraft === "number") aaAmmo = counts.antiAircraft;
        updateCannonButtons();
    }
});

socket.on("grenade_count", (data) => {
    if (!data) return;
    const ak = ammoKey(data.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    if (typeof data.count === "number") slot.grenade = data.count;
    if (ak === ammoKey(activeGhostSid())) {
        if (typeof data.count === "number") grenadeCount = data.count;
        updateGrenadeButtons();
    }
});

socket.on("beacon_count", (data) => {
    if (!data) return;
    const ak = ammoKey(data.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    if (typeof data.count === "number") slot.beacon = data.count;
    if (ak === ammoKey(activeGhostSid())) {
        if (typeof data.count === "number") sonarBeaconCount = data.count;
        updateSonarBeaconButton();
    }
});

socket.on("lure_count", (data) => {
    if (!data) return;
    const ak = ammoKey(data.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    if (typeof data.count === "number") slot.lure = data.count;
    if (ak === ammoKey(activeGhostSid())) {
        if (typeof data.count === "number") acousticLureCount = data.count;
        updateAcousticLureButton();
    }
});

socket.on("integrity", (data) => {
    if (!data || typeof data.value !== "number") return;
    // Multi-bateaux : on stocke l'intégrité par bateau dans boatAmmo[ak].integrity.
    const ak = ammoKey(data.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    const prev = typeof slot.integrity === "number" ? slot.integrity : 100;
    slot.integrity = data.value;
    // Flash rouge + UI : seulement si c'est le bateau actif.
    if (ak === ammoKey(activeGhostSid())) {
        if (data.value < boatIntegrity - 0.001) {
            damageFlashUntil = performance.now() + 700;
        }
        boatIntegrity = data.value;
    } else if (data.value < prev - 0.001) {
        // Bateau non actif qui prend des dégâts : message discret.
        setTransientMessage("Un de vos bateaux subit des dégâts");
    }
});

window.addEventListener("keydown", (e) => {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if (e.key === "Escape" && (aimingTorpedoKind || grenadeAiming)) {
        cancelAim();
        return;
    }
    // Multi-bateaux : Tab cycle vers le bateau suivant, Shift-Tab vers le précédent.
    if (e.key === "Tab") {
        e.preventDefault();
        // Si on quitte un bateau coulé, on le retire.
        const cur = localBoats[activeBoatIndex];
        if (cur && cur.sunk) {
            delete boatAmmo[ammoKey(cur.ghostSid)];
            if (cur.playerId) selfControlledPlayerIds.delete(cur.playerId);
            localBoats.splice(activeBoatIndex, 1);
            if (activeBoatIndex >= localBoats.length) activeBoatIndex = 0;
        }
        cycleActiveBoat(e.shiftKey ? -1 : 1);
        return;
    }
    keys[e.key] = true;
    if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " "].includes(e.key)) {
        e.preventDefault();
    }
    if (e.key === "o" || e.key === "O") {
        if (manualDroneControl && activeManualDrone) {
            activeManualDrone.speed = 0;
        } else {
            autoDecelerate = true;
        }
    }
    if ((e.key === "g" || e.key === "G") && e.ctrlKey && gridMesh) {
        e.preventDefault();
        gridMesh.isVisible = !gridMesh.isVisible;
    }
    if (e.key.length === 1) {
        cheatBuffer = (cheatBuffer + e.key.toLowerCase()).slice(-20);
    }
    if (cheatBuffer.endsWith("move")) {
        cheatBuffer = "";
        cheatMoveMode = !cheatMoveMode;
        setTransientMessage(cheatMoveMode ? "Mode téléport : cliquez sur la map" : "Mode téléport désactivé");
    }
    if (cheatBuffer.endsWith("rr")) {
        cheatBuffer = "";
        const now = performance.now();
        for (const id in otherPlayers) {
            sonarRevealedUntil[id] = now + SONAR_PERSIST_DURATION;
        }
        setTransientMessage("Révélation sonar de tous les bateaux (10s)");
    }
    if (cheatBuffer.endsWith("idkfa")) {
        cheatBuffer = "";
        socket.emit("cheat_resupply", withBsid({}));
        setTransientMessage("Munitions rechargées au max");
    }
    if (cheatBuffer.endsWith("allmap")) {
        cheatBuffer = "";
        allMapMode = !allMapMode;
        // Si on active, marque toutes les îles comme découvertes immédiatement.
        if (allMapMode && worldData && worldData.islands) {
            worldData.islands.forEach((island, idx) => {
                const samples = radarDiscovered["island_" + idx];
                if (samples) for (const sp of samples) sp.seen = true;
            });
        }
        setTransientMessage(allMapMode ? "Carte complète activée" : "Carte complète désactivée");
    }
    if (cheatBuffer.endsWith("speed2")) {
        cheatBuffer = "";
        const botId = viewedBotId();
        if (botId) {
            if (!window._botSpeedMult) window._botSpeedMult = {};
            const cur = window._botSpeedMult[botId] || 1;
            const mult = cur >= 8 ? 1 : cur * 2;
            window._botSpeedMult[botId] = mult;
            socket.emit("cheat_bot_speed_mult", { id: botId, multiplier: mult });
            setTransientMessage(`Bot ${botId}: vitesse ×${mult}`);
        } else {
            const base = window._baseMaxSpeed || maxSpeed || 1;
            window._baseMaxSpeed = base;
            // Cycle des multiplicateurs : ×1 → ×2 → ×4 → ×8 → ×1.
            const oldMult = window._playerSpeedMult || 1;
            const mult = oldMult >= 8 ? 1 : oldMult * 2;
            window._playerSpeedMult = mult;
            maxSpeed = base * mult;
            reverseMaxSpeed = (base / 2) * mult;
            // Applique immédiatement le nouveau multiplicateur à la vitesse
            // courante : sans ça, l'accélération progressive (THROTTLE_ACCEL)
            // mettrait plusieurs secondes à atteindre la nouvelle vitesse max
            // et l'effet du cheat serait invisible.
            boatSpeed *= mult / oldMult;
            socket.emit("cheat_speed_mult", withBsid({ multiplier: mult }));
            setTransientMessage(mult === 1 ? "Vitesse normale (×1)" : `Vitesse ×${mult}`);
        }
    }
    if (cheatBuffer.endsWith("iddqd")) {
        cheatBuffer = "";
        socket.emit("cheat_godmode", withBsid({}));
    }
    if (cheatBuffer.endsWith("mapadmin")) {
        cheatBuffer = "";
        if (adminMode) tryExitAdminMode();
        else enterAdminMode();
    }
    if (cheatBuffer.endsWith("clear")) {
        cheatBuffer = "";
        clearWater = !clearWater;
        if (clearWater) mediumWater = false;
        setTransientMessage(clearWater ? "Eau claire activée" : "Eau trouble activée");
    }
    if (cheatBuffer.endsWith("water")) {
        cheatBuffer = "";
        mediumWater = !mediumWater;
        if (mediumWater) clearWater = false;
        setTransientMessage(mediumWater ? "Eau intermédiaire activée" : "Eau trouble activée");
    }
    if (cheatBuffer.endsWith("autosub")) {
        cheatBuffer = "";
        socket.emit("spawn_bot", { boatType: "submarine", ai: "autosub" });
        setTransientMessage("Bot sous-marin (autosub) demandé");
    }
    if (cheatBuffer.endsWith("autodest")) {
        cheatBuffer = "";
        socket.emit("spawn_bot", { boatType: "destroyer", ai: "autodest" });
        setTransientMessage("Bot destroyer (autodest) demandé");
    }
    if (cheatBuffer.endsWith("addsub")) {
        cheatBuffer = "";
        socket.emit("add_player_boat", { boatType: "submarine" });
        setTransientMessage("Sous-marin supplémentaire demandé");
    }
    if (cheatBuffer.endsWith("adddest")) {
        cheatBuffer = "";
        socket.emit("add_player_boat", { boatType: "destroyer" });
        setTransientMessage("Destroyer supplémentaire demandé");
    }
    if (cheatBuffer.endsWith("bot")) {
        cheatBuffer = "";
        socket.emit("cheat_swap_to_bot", { index: botCheatIndex });
        botCheatIndex += 1;
        setTransientMessage("Vue bot");
    }
    if (cheatBuffer.endsWith("self")) {
        cheatBuffer = "";
        botCheatIndex = 0;
        socket.emit("cheat_swap_to_self");
        setTransientMessage("Retour à mon bateau");
    }
    if (cheatBuffer.endsWith("fps")) {
        cheatBuffer = "";
        toggleFpsOverlay();
    }
    if (cheatBuffer.endsWith("calmdown")) {
        cheatBuffer = "";
        socket.emit("cheat_bots_calmdown");
    }
    if (cheatBuffer.endsWith("time1")) {
        cheatBuffer = "";
        socket.emit("set_sim_speed", { multiplier: 1 });
    }
    if (cheatBuffer.endsWith("time2")) {
        cheatBuffer = "";
        socket.emit("set_sim_speed", { multiplier: 2 });
    }
    if (cheatBuffer.endsWith("time4")) {
        cheatBuffer = "";
        socket.emit("set_sim_speed", { multiplier: 4 });
    }
    if (cheatBuffer.endsWith("time8")) {
        cheatBuffer = "";
        socket.emit("set_sim_speed", { multiplier: 8 });
    }
    if (cheatBuffer.endsWith("reloadai")) {
        cheatBuffer = "";
        socket.emit("cheat_reload_ai");
        setTransientMessage("Rechargement des arbres BT...");
    }
    if (cheatBuffer.endsWith("killbot")) {
        cheatBuffer = "";
        socket.emit("cheat_kill_bot");
        setTransientMessage("Bot le plus proche supprimé");
    }
    if (cheatBuffer.endsWith("path")) {
        cheatBuffer = "";
        showNavGraph = !showNavGraph;
        setTransientMessage(showNavGraph ? "Graphe de nav affiché (rouge)" : "Graphe de nav masqué");
    }
    if (cheatBuffer.endsWith("visu")) {
        cheatBuffer = "";
        cheatVisuMode = !cheatVisuMode;
        setTransientMessage(cheatVisuMode ? "Infos torpilles activées" : "Infos torpilles désactivées");
    }
    if (cheatBuffer.endsWith("tta")) {
        cheatBuffer = "";
        fireTorpedo("acoustic");
    }
    if (cheatBuffer.endsWith("ttn")) {
        cheatBuffer = "";
        fireTorpedo("autonomous");
    }
    if (cheatBuffer.endsWith("ll") && !cheatBuffer.endsWith("ull") && !cheatBuffer.endsWith("all")) {
        cheatBuffer = "";
        dropAcousticLure();
    }
    if (cheatBuffer.endsWith("logs")) {
        cheatBuffer = "";
        toggleDebugLogPanel();
    }
    if (e.key === "F1") {
        e.preventDefault();
        socket.emit("toggle_day_cycle");
    }
});
window.addEventListener("keyup", (e) => {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    keys[e.key] = false;
});

let mouseDown = false;
let lastMouseX = 0;
let lastMouseY = 0;
const MOUSE_SENSITIVITY = 0.005;
document.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    if (e.target !== canvas) return;
    mouseDown = true;
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
}, true);
document.addEventListener("pointerup", (e) => {
    if (e.button === 0) mouseDown = false;
}, true);
document.addEventListener("pointermove", (e) => {
    if (manualDroneControl && droneCamera && mouseDown) {
        const dy = e.clientY - lastMouseY;
        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
        dronePitch = Math.max(DRONE_PITCH_MIN, Math.min(DRONE_PITCH_MAX, dronePitch + dy * DRONE_PITCH_SENSITIVITY));
        return;
    }
    if (!mouseDown) return;
    const dx = e.clientX - lastMouseX;
    const dy = e.clientY - lastMouseY;
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
    if (zoomMode) {
        fpvYaw += dx * MOUSE_SENSITIVITY;
        fpvPitch = Math.max(-Math.PI / 2 + 0.1, Math.min(10 * Math.PI / 180, fpvPitch - dy * MOUSE_SENSITIVITY * 0.5));
    } else {
        cameraAlphaOffset -= dx * MOUSE_SENSITIVITY;
        const submergedSub = currentBoatType === "submarine" && playerMesh && playerMesh.position.y < PERISCOPE_DEPTH;
        const betaMin = submergedSub ? 0.8 : 1.3;
        const betaMax = submergedSub ? 1.8 : 1.45;
        cameraBeta = Math.max(betaMin, Math.min(betaMax, cameraBeta + dy * MOUSE_SENSITIVITY * 0.3));
    }
}, true);
canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (manualDroneControl && droneCamera) {
        droneCamera.fov = Math.max(0.1, Math.min(1.5, droneCamera.fov + Math.sign(e.deltaY) * 0.05));
    } else if (zoomMode) {
        fpvFov = Math.max(0.1, Math.min(1.5, fpvFov + Math.sign(e.deltaY) * 0.05));
    } else {
        cameraRadius = Math.max(3, Math.min(300, cameraRadius + Math.sign(e.deltaY) * 5));
    }
}, { passive: false });

let zoomMode = false;
let zoomLowMode = false;
let fpvYaw = 0;
let fpvPitch = 0;
let fpvFov = 0.8;
let mouseCanvasX = 0;
let mouseCanvasY = 0;
canvas.addEventListener("pointermove", (e) => {
    mouseCanvasX = e.offsetX;
    mouseCanvasY = e.offsetY;
});

let _focusPaused = false;
function pauseClientFocus(why) {
    if (_focusPaused) return;
    _focusPaused = true;
    diveRate = 0;
    periscopeTarget = null;
    if (socket && socket.connected) {
        socket.emit("pause_active_boat", {});
        console.log("[focus] pause_active_boat (" + why + ")");
    }
}
function resumeClientFocus(why) {
    if (!_focusPaused) return;
    _focusPaused = false;
    if (socket && socket.connected) {
        const entry = (typeof localBoats !== "undefined" && typeof activeBoatIndex === "number")
            ? localBoats[activeBoatIndex] : null;
        const bsid = entry && entry.ghostSid !== entry.playerId ? entry.ghostSid : null;
        socket.emit("resume_active_boat", { bsid });
        console.log("[focus] resume_active_boat (" + why + ") bsid=", bsid);
    }
}
// Pause uniquement sur changement d'onglet/page (visibilitychange).
// On NE PAS écouter window.blur/focus : ça se déclenche aussi quand on clique
// sur les devtools, une fenêtre par-dessus, etc., ce qui causait des boucles
// pause/resume bloquantes en jeu.
document.addEventListener("visibilitychange", () => {
    if (document.hidden) pauseClientFocus("visibilitychange-hidden");
    else resumeClientFocus("visibilitychange-visible");
});

const CAMERA_SPEED = 0.03;

const radarDiscovered = {};
let sonarReveal = metersToUnits(15000);
let sonarShortAngleDeg = 30;
let sonarLargeAngleDeg = 120;
let sonarShortRange = metersToUnits(5000);
let sonarLargeRange = metersToUnits(2500);
let sonarThermoclinePenetration = 0.1;
function pingPointInCone(ping, x, z) {
    if (!ping.coneDeg || ping.coneDeg >= 360) return true;
    const dx = x - ping.x;
    const dz = z - ping.z;
    if (dx === 0 && dz === 0) return true;
    const fwdX = -Math.cos(ping.rotation || 0);
    const fwdZ = Math.sin(ping.rotation || 0);
    const len = Math.sqrt(dx * dx + dz * dz);
    const dot = (dx * fwdX + dz * fwdZ) / len;
    const halfCos = Math.cos((ping.coneDeg * Math.PI / 180) / 2);
    return dot >= halfCos;
}
function pingRangeUnits(ping) {
    if (ping.beacon) return ping.beaconRange || metersToUnits(sonarBeaconSpec.rangeMeters || 5000);
    return ping.range || sonarShortRange;
}
function pingRevealUnits(ping) {
    return ping.reveal || sonarReveal;
}
const SONAR_REVEAL_DURATION = 5000;
const SONAR_PERSIST_DURATION = 10000;
const SONAR_COOLDOWN = 3000;
let lastSonarPing = 0;

function _autoGrenadeDepthFromSonar(id) {
    if (currentBoatType !== "destroyer") return;
    const p = otherPlayers[id];
    if (!p) return;
    const depthM = Math.round(-p.position.y * UNIT_METERS);
    if (depthM <= 0) return;
    const depthInput = document.getElementById("grenadeDepth");
    if (depthInput) {
        depthInput.value = depthM;
        setTransientMessage("Profondeur grenades ajustée : " + depthM + " m");
    }
}
const activePings = [];

const islandBoundsCache = [];
function getIslandBounds(idx) {
    if (islandBoundsCache[idx]) return islandBoundsCache[idx];
    const pts = worldData.islands[idx].points;
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const p of pts) {
        if (p.x < minX) minX = p.x;
        if (p.x > maxX) maxX = p.x;
        if (p.z < minZ) minZ = p.z;
        if (p.z > maxZ) maxZ = p.z;
    }
    const b = { minX, maxX, minZ, maxZ };
    islandBoundsCache[idx] = b;
    return b;
}

function segmentIntersectsAABB(ox, oz, tx, tz, b) {
    let t0 = 0, t1 = 1;
    const dx = tx - ox, dz = tz - oz;
    const p = [-dx, dx, -dz, dz];
    const q = [ox - b.minX, b.maxX - ox, oz - b.minZ, b.maxZ - oz];
    for (let i = 0; i < 4; i++) {
        if (p[i] === 0) {
            if (q[i] < 0) return false;
        } else {
            const r = q[i] / p[i];
            if (p[i] < 0) {
                if (r > t1) return false;
                if (r > t0) t0 = r;
            } else {
                if (r < t0) return false;
                if (r < t1) t1 = r;
            }
        }
    }
    return true;
}

function isLineOfSightClearBetween(ox, oz, tx, tz, excludeIslandName) {
    if (!worldData || !worldData.islands) return true;
    const dx = tx - ox;
    const dz = tz - oz;
    const dist = Math.sqrt(dx * dx + dz * dz);
    if (dist < 0.01) return true;
    const candidates = [];
    for (let idx = 0; idx < worldData.islands.length; idx++) {
        if (excludeIslandName && excludeIslandName === ("island_" + idx)) continue;
        if (segmentIntersectsAABB(ox, oz, tx, tz, getIslandBounds(idx))) {
            candidates.push(idx);
        }
    }
    if (candidates.length === 0) return true;
    const STEP = 5;
    const steps = Math.max(2, Math.ceil(dist / STEP));
    for (let i = 1; i < steps; i++) {
        const t = i / steps;
        const x = ox + dx * t;
        const z = oz + dz * t;
        for (const idx of candidates) {
            if (pointInPolygon(x, z, worldData.islands[idx].points)) return false;
        }
    }
    return true;
}

function isLineOfSightClear(targetX, targetZ, excludeIslandName) {
    if (!playerMesh) return true;
    return isLineOfSightClearBetween(
        playerMesh.position.x, playerMesh.position.z,
        targetX, targetZ, excludeIslandName);
}

// Nombre de thermoclines traversées par le segment 3D (émetteur→récepteur).
// Sert à atténuer le son (-80%/couche) et à bloquer le sonar actif côté client.
// y en unités (négatif sous l'eau), depthMeters en mètres → y_thermo = -depthMeters/UNIT_METERS.
function countThermoclinesCrossed(x1, y1, z1, x2, y2, z2) {
    const thermos = (worldData && worldData.thermoclines) || [];
    if (!thermos.length) return 0;
    let crossed = 0;
    const dy = y2 - y1;
    for (const tc of thermos) {
        const pts = tc.points;
        if (!pts || pts.length < 3) continue;
        const yT = -(tc.depthMeters || 50) / UNIT_METERS;
        if ((y1 - yT) * (y2 - yT) > 0) continue; // même côté
        if (Math.abs(dy) < 1e-9) {
            if (pointInPolygon((x1 + x2) / 2, (z1 + z2) / 2, pts)) crossed++;
            continue;
        }
        const t = (yT - y1) / dy;
        if (t < 0 || t > 1) continue;
        const ix = x1 + (x2 - x1) * t;
        const iz = z1 + (z2 - z1) * t;
        if (pointInPolygon(ix, iz, pts)) crossed++;
    }
    return crossed;
}
const THERMOCLINE_NOISE_FACTOR = 0.2; // -80% par couche traversée

let radarFrozenBoats = [];
const sonarRevealedUntil = {};
const _sonarNewDetections = [];
// Persistance de la révélation sonar des mines (key = ownerId:mid).
const mineRevealedUntil = {};
const MINE_SONAR_REVEAL_MS = 10000;
let selectedBoatId = null;
let selectedDroneKey = null;
let selectedLocalDroneDid = null;
let selectedTorpedoKey = null;
// Tous les observateurs de mon équipe : moi (en local) + chaque coéquipier
// (depuis otherPlayers). Exclut les bateaux coulés / hors carte.
function alliedObservers() {
    const obs = [];
    if (playerMesh) {
        obs.push({
            id: playerId,
            x: playerMesh.position.x,
            z: playerMesh.position.z,
            y: playerMesh.position.y,
            submerged: playerMesh.position.y <= PERISCOPE_DEPTH,
        });
    }
    if (!localTeamId) return obs;
    for (const id in otherPlayers) {
        const info = otherPlayersInfo[id];
        if (!info || info.teamId !== localTeamId) continue;
        const op = otherPlayers[id];
        if (!op) continue;
        const hist = otherPlayersHistory[id];
        const submerged = hist ? !!hist.submerged : (op.position.y <= PERISCOPE_DEPTH);
        obs.push({
            id, x: op.position.x, z: op.position.z, y: op.position.y, submerged,
        });
    }
    return obs;
}

// Tous les drones amis : les miens (activeDrones) + ceux d'un coéquipier.
function alliedDrones() {
    const drones = [];
    for (const d of activeDrones) drones.push(d);
    if (!localTeamId) return drones;
    for (const key in remoteDrones) {
        const r = remoteDrones[key];
        if (!r || r.ownerId === playerId) continue;
        const info = otherPlayersInfo[r.ownerId];
        if (!info || info.teamId !== localTeamId) continue;
        // Adapte au format attendu (kind, x, z, rangeMeters).
        drones.push({
            kind: r.kind,
            x: r.x, y: r.y, z: r.z,
            rangeMeters: r.rangeMeters,
        });
    }
    return drones;
}

// LOS depuis n'importe quel observateur de mon équipe.
function isLOSClearFromAnyAlly(targetX, targetZ, targetY) {
    const obs = alliedObservers();
    for (const o of obs) {
        if (o.submerged) continue;
        if (!isLineOfSightClearBetween(o.x, o.z, targetX, targetZ, null)) continue;
        // Thermocline : si une couche sépare l'observateur de la cible, il ne la
        // voit pas. On exige une vue sans thermocline depuis au moins un allié.
        if (typeof targetY === "number" &&
            countThermoclinesCrossed(o.x, o.y, o.z, targetX, targetY, targetZ) > 0) {
            continue;
        }
        return true;
    }
    return false;
}

function renderRadar() {
    const now = performance.now();
    for (let i = activePings.length - 1; i >= 0; i--) {
        const pp = activePings[i];
        if (pp.expiresAt <= now && (!pp.emitterRevealedUntil || pp.emitterRevealedUntil <= now)) {
            activePings.splice(i, 1);
        }
    }
    for (const id in sonarRevealedUntil) {
        if (sonarRevealedUntil[id] <= now) delete sonarRevealedUntil[id];
    }
    for (const id in passiveSonarDetectionsUntil) {
        if (passiveSonarDetectionsUntil[id] <= now) delete passiveSonarDetectionsUntil[id];
    }
    for (const key in mineRevealedUntil) {
        if (mineRevealedUntil[key] <= now) delete mineRevealedUntil[key];
    }
    if (!radarVisible || !worldData || !playerMesh) return;
    const radarFrozen = currentBoatType === "submarine" && playerMesh.position.y < PERISCOPE_DEPTH;
    const ctx = radarCtx;
    const w = radarCanvas.width;
    const h = radarCanvas.height;
    const v = radarView();
    const scaleX = v.sX;
    const scaleZ = v.sZ;
    const proj = (x, z) => worldToRadar(x, z, v);

    ctx.fillStyle = "#001a00";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#003300";
    ctx.lineWidth = 1;
    for (let gx = 0; gx < w; gx += 30) {
        ctx.beginPath();
        ctx.moveTo(gx, 0);
        ctx.lineTo(gx, h);
        ctx.stroke();
    }
    for (let gy = 0; gy < h; gy += 30) {
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(w, gy);
        ctx.stroke();
    }

    if (worldData.islands) {
        const SAMPLE_STEP = 15;
        worldData.islands.forEach((island, idx) => {
            const islandName = "island_" + idx;
            if (!radarDiscovered[islandName]) {
                const samples = [];
                const n = island.points.length;
                for (let i = 0; i < n; i++) {
                    const a = island.points[i];
                    const b = island.points[(i + 1) % n];
                    const dx = b.x - a.x;
                    const dz = b.z - a.z;
                    const segLen = Math.sqrt(dx * dx + dz * dz);
                    const steps = Math.max(1, Math.ceil(segLen / SAMPLE_STEP));
                    for (let s = 0; s < steps; s++) {
                        const t = s / steps;
                        samples.push({ x: a.x + dx * t, z: a.z + dz * t, seen: false });
                    }
                }
                radarDiscovered[islandName] = samples;
            }
            const samples = radarDiscovered[islandName];
            // Joueurs humains : toutes les îles sont visibles d'emblée.
            for (const sp of samples) sp.seen = true;
            // Compte des samples vus pour décider remplissage vs contour partiel.
            // Seuil : 60% des points découverts → remplissage texturé.
            let nSeen = 0;
            for (const sp of samples) if (sp.seen) nSeen++;
            const allSeen = samples.length > 0 && nSeen >= samples.length * 0.6;
            const texName = islandTextureName(island);
            ensureRadarTextureImage(texName);
            const patternCanvas = islandTexturePatternCanvases[texName];
            const fillColor = islandRadarColor(island);
            let fillStyle = fillColor;
            if (patternCanvas) {
                const pattern = ctx.createPattern(patternCanvas, "repeat");
                if (pattern) {
                    // Ancre le pattern aux coordonnées monde, sinon il reste
                    // collé au canvas et glisse pendant pan/zoom. Les axes du
                    // radar : pixelX = w/2 + (cX - x) * sX (X monde inversé),
                    // pixelY = h/2 + (z - cZ) * sZ. On veut que le tile (0,0)
                    // du pattern corresponde à worldX=0, worldZ=0 sur l'écran.
                    if (typeof pattern.setTransform === "function") {
                        try {
                            const tx = radarCanvas.width / 2 + v.cX * v.sX;
                            const ty = radarCanvas.height / 2 - v.cZ * v.sZ;
                            const m = new DOMMatrix([1, 0, 0, 1, tx, ty]);
                            pattern.setTransform(m);
                        } catch (e) { /* fallback : pattern non ancré */ }
                    }
                    fillStyle = pattern;
                }
            }
            if (allSeen) {
                // Polygone plein avec la texture (ou couleur si image pas chargée).
                ctx.fillStyle = fillStyle;
                ctx.beginPath();
                island.points.forEach((pt, i) => {
                    const p = proj(pt.x, pt.z);
                    if (i === 0) ctx.moveTo(p.x, p.y);
                    else ctx.lineTo(p.x, p.y);
                });
                ctx.closePath();
                ctx.fill();
            } else {
                // Découverte partielle : trait fin reliant les samples vus
                // consécutifs (la liste samples suit le contour du polygone).
                ctx.strokeStyle = fillColor;
                ctx.lineWidth = 1;
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
                const nS = samples.length;
                ctx.beginPath();
                let started = false;
                for (let i = 0; i < nS; i++) {
                    const a = samples[i];
                    const b = samples[(i + 1) % nS];
                    if (a.seen && b.seen) {
                        const pa = proj(a.x, a.z);
                        const pb = proj(b.x, b.z);
                        if (!started) { ctx.moveTo(pa.x, pa.y); started = true; }
                        else { ctx.moveTo(pa.x, pa.y); }
                        ctx.lineTo(pb.x, pb.y);
                    }
                }
                ctx.stroke();
                // Samples isolés (un seen entouré de non-seen) : petit point.
                ctx.fillStyle = fillColor;
                for (let i = 0; i < nS; i++) {
                    const a = samples[i];
                    if (!a.seen) continue;
                    const prev = samples[(i - 1 + nS) % nS];
                    const next = samples[(i + 1) % nS];
                    if (!prev.seen && !next.seen) {
                        const pa = proj(a.x, a.z);
                        ctx.fillRect(pa.x - 0.5, pa.y - 0.5, 1, 1);
                    }
                }
            }
        });
    }

    // Cheat "path" : affiche le graphe de navigation des bots (nœuds + arêtes).
    if (showNavGraph && worldData && worldData.nav_graph) {
        const ng = worldData.nav_graph;
        const nodes = ng.nodes || [];
        const edges = ng.edges || [];
        ctx.strokeStyle = "rgba(255, 60, 60, 0.7)";
        ctx.lineWidth = 1;
        for (const e of edges) {
            const a = nodes[e[0]];
            const b = nodes[e[1]];
            if (!a || !b) continue;
            const pa = proj(a.x, a.z);
            const pb = proj(b.x, b.z);
            ctx.beginPath();
            ctx.moveTo(pa.x, pa.y);
            ctx.lineTo(pb.x, pb.y);
            ctx.stroke();
        }
        ctx.fillStyle = "#ff3030";
        for (const n of nodes) {
            const p = proj(n.x, n.z);
            ctx.fillRect(p.x - 2, p.y - 2, 4, 4);
        }
    }

    const revealed = new Set();
    for (const ping of activePings) {
        const elapsed = now - ping.emittedAt;
        const pRange = pingRangeUnits(ping);
        const pReveal = pingRevealUnits(ping);
        const frontDist = (elapsed / SONAR_REVEAL_DURATION) * pRange;
        if (ping.emitterId === playerId && worldData && worldData.islands) {
            const f2 = frontDist * frontDist;
            worldData.islands.forEach((island, idx) => {
                const islandName = "island_" + idx;
                const samples = radarDiscovered[islandName];
                if (!samples) return;
                for (const sp of samples) {
                    if (sp.seen) continue;
                    const dx = sp.x - ping.x;
                    const dz = sp.z - ping.z;
                    if (dx * dx + dz * dz > f2) continue;
                    if (!pingPointInCone(ping, sp.x, sp.z)) continue;
                    if (!isLineOfSightClear(sp.x, sp.z, islandName)) continue;
                    sp.seen = true;
                }
            });
        }
        if (ping.emitterId !== playerId) {
            const dx = ping.x - playerMesh.position.x;
            const dz = ping.z - playerMesh.position.z;
            const dist = Math.sqrt(dx * dx + dz * dz);
            if (dist <= frontDist && dist <= pReveal && isLineOfSightClear(ping.x, ping.z, null)) {
                if (!ping.emitterRevealedUntil) {
                    ping.emitterRevealedUntil = now + 5000;
                    sonarRevealedUntil[ping.emitterId] = now + 5000;
                }
            }
        }
    }
    for (const id in sonarRevealedUntil) {
        if (sonarRevealedUntil[id] <= now) delete sonarRevealedUntil[id];
        else revealed.add(id);
    }
    // Détections via balises sonar passives (uniquement coéquipier de l'owner).
    for (const id in passiveSonarDetectionsUntil) {
        if (passiveSonarDetectionsUntil[id] <= now) delete passiveSonarDetectionsUntil[id];
        else revealed.add(id);
    }
    // Note : la révélation permanente des mines par sonar (bateau ou balise)
    // est gérée côté serveur via mine_revealed. Cette boucle locale n'a plus
    // de rôle ; on garde juste le cleanup d'éventuelles entrées résiduelles.
    for (const mkey in mineRevealedUntil) {
        if (mineRevealedUntil[mkey] <= now) delete mineRevealedUntil[mkey];
    }
    const allyObsForPings = alliedObservers();
    _sonarNewDetections.length = 0;
    for (const ping of activePings) {
        if (ping.beacon) continue;
        const isMine = ping.emitterId === playerId;
        let isAllyPing = false;
        if (!isMine) {
            const info = otherPlayersInfo[ping.emitterId];
            isAllyPing = !!(localTeamId && info && info.teamId === localTeamId);
        }
        if (!isMine && !isAllyPing) continue;
        const elapsed = now - ping.emittedAt;
        const pRange = pingRangeUnits(ping);
        const pReveal = pingRevealUnits(ping);
        const detectFront = (elapsed / SONAR_REVEAL_DURATION) * pRange;
        for (const id in otherPlayers) {
            const info = otherPlayersInfo[id];
            if (info && localTeamId && info.teamId === localTeamId) continue;
            const p = otherPlayers[id];
            const dx2 = p.position.x - ping.x;
            const dz2 = p.position.z - ping.z;
            const d = Math.sqrt(dx2 * dx2 + dz2 * dz2);
            if (d > detectFront || d > pRange) continue;
            if (!pingPointInCone(ping, p.position.x, p.position.z)) continue;
            if (!isLineOfSightClearBetween(ping.x, ping.z, p.position.x, p.position.z, null)) continue;
            // Le sonar actif ne franchit PAS une thermocline (sauf pénétration aléatoire, tiré une seule fois par ping+cible).
            if (countThermoclinesCrossed(ping.x, ping.y || 0, ping.z, p.position.x, p.position.y, p.position.z) > 0) {
                if (!ping._tcRolled) ping._tcRolled = {};
                if (!(id in ping._tcRolled)) {
                    ping._tcRolled[id] = (sonarThermoclinePenetration > 0 && Math.random() < sonarThermoclinePenetration);
                }
                if (!ping._tcRolled[id]) continue;
            }
            let withinReveal = false;
            for (const o of allyObsForPings) {
                const odx = p.position.x - o.x;
                const odz = p.position.z - o.z;
                if (odx * odx + odz * odz <= pReveal * pReveal) { withinReveal = true; break; }
            }
            if (!withinReveal) continue;
            revealed.add(id);
            if (!sonarRevealedUntil[id]) {
                sonarRevealedUntil[id] = now + SONAR_PERSIST_DURATION;
                _autoGrenadeDepthFromSonar(id);
                _sonarNewDetections.push(id);
            }
        }
    }
    for (const ping of activePings) {
        if (!ping.beacon) continue;
        const elapsed = now - ping.emittedAt;
        const range = ping.beaconRange || metersToUnits(sonarBeaconSpec.rangeMeters || 5000);
        const detectFront = (elapsed / SONAR_REVEAL_DURATION) * range;
        for (const id in otherPlayers) {
            const p = otherPlayers[id];
            const dx2 = p.position.x - ping.x;
            const dz2 = p.position.z - ping.z;
            const d = Math.sqrt(dx2 * dx2 + dz2 * dz2);
            if (d <= detectFront && d <= range
                && isLineOfSightClearBetween(ping.x, ping.z, p.position.x, p.position.z, null)) {
                const tcN = countThermoclinesCrossed(ping.x, ping.y || 0, ping.z, p.position.x, p.position.y, p.position.z);
                if (tcN > 0) {
                    if (!ping._tcRolled) ping._tcRolled = {};
                    if (!(id in ping._tcRolled)) {
                        const bPen = sonarBeaconSpec.thermoclinePenetration || 0;
                        ping._tcRolled[id] = (bPen > 0 && Math.random() < bPen);
                    }
                    if (!ping._tcRolled[id]) continue;
                }
                revealed.add(id);
                if (!sonarRevealedUntil[id]) {
                    sonarRevealedUntil[id] = now + SONAR_PERSIST_DURATION;
                    _autoGrenadeDepthFromSonar(id);
                }
            }
        }
    }
    if (_sonarNewDetections.length > 0 && currentBoatType === "destroyer") {
        const subs = _sonarNewDetections.filter(id => {
            const info = otherPlayersInfo[id];
            return info && info.boatType === "submarine";
        });
        if (subs.length === 1) {
            selectedBoatId = subs[0];
            selectedBoatIsSonar = true;
        }
        _sonarNewDetections.length = 0;
    }
    // Sonar passif : détection en fonction du bruit perçu (atténué par distance)
    // versus le seuil minNoise de notre passiveSonar. Partage par équipe : si
    // un coéquipier audible la cible, elle est révélée à toute la team.
    const listenThreshold = localPassiveMinNoise || 5.0;
    const observers = alliedObservers();
    for (const id in otherPlayers) {
        const info = otherPlayersInfo[id];
        const hist = otherPlayersHistory[id];
        if (!info || !hist) continue;
        if (info.teamId && localTeamId && info.teamId === localTeamId) continue;
        if (now - hist.t > NOISE_BUFFER_MS) continue;
        const sr = hist.speedRatio || 0;
        const rev = !!hist.reverse;
        const baseNoise = info.baseNoise || 0;
        const minNoiseEmit = info.minNoise || 0;
        const snl = info.speedNoiseLimit || 0;
        // Marche arrière : même bruit que la marche avant (plus de bonus ×4).
        let emitted = 0;
        if (sr > 0 || rev) {
            if (sr > snl) emitted = baseNoise * sr;
            else if (snl > 0) emitted = minNoiseEmit * (sr / snl);
        }
        if (emitted <= 0) continue;
        const p = otherPlayers[id];
        for (const o of observers) {
            const dx = p.position.x - o.x;
            const dz = p.position.z - o.z;
            const distM = Math.sqrt(dx * dx + dz * dz) * UNIT_METERS;
            const dEff = Math.max(distM, 100.0);
            const ratio = 1000.0 / dEff;
            let perceived = emitted * ratio * ratio;
            // Atténuation thermocline : -80% par couche entre la cible et l'observateur.
            const nc = countThermoclinesCrossed(p.position.x, p.position.y, p.position.z, o.x, o.y, o.z);
            if (nc > 0) perceived *= Math.pow(THERMOCLINE_NOISE_FACTOR, nc);
            if (perceived < listenThreshold) continue;
            if (!isLineOfSightClearBetween(o.x, o.z, p.position.x, p.position.z, null)) continue;
            revealed.add(id);
            break;
        }
    }
    // Mode fullmap (cheat) : tous les bateaux toujours visibles, même en
    // plongée (radar gelé). On force l'ajout dans `revealed` avant le test
    // radarFrozen.
    if (allMapMode) {
        for (const id in otherPlayers) revealed.add(id);
    }
    // Coéquipiers : toujours visibles, peu importe distance/LOS/profondeur.
    // Avant le test radarFrozen pour rester visibles même quand on plonge.
    if (localTeamId) {
        for (const id in otherPlayers) {
            const info = otherPlayersInfo[id];
            if (info && info.teamId === localTeamId) {
                revealed.add(id);
            }
        }
    }
    if (!radarFrozen) {
        radarFrozenBoats = [];
        const allDrones = alliedDrones();
        if (allDrones.length > 0) {
            const deepThreshold = PERISCOPE_DEPTH - metersToUnits(2);
            for (const id in otherPlayers) {
                const info = otherPlayersInfo[id];
                if (info && localTeamId && info.teamId === localTeamId) continue;
                const p = otherPlayers[id];
                if (p.position.y < deepThreshold) continue;
                const hist = otherPlayersHistory[id];
                const submerged = hist ? !!hist.submerged : (p.position.y <= PERISCOPE_DEPTH);
                for (const d of allDrones) {
                    if (d.kind === "automatic" && submerged) continue;
                    const dRangeM = d.rangeMeters || (d.kind === "manual" ? 2000 : 3000);
                    const dr = metersToUnits(dRangeM);
                    const range2 = submerged ? (dr / 10) * (dr / 10) : dr * dr;
                    const ddx = p.position.x - d.x;
                    const ddz = p.position.z - d.z;
                    if (ddx * ddx + ddz * ddz <= range2) {
                        revealed.add(id);
                        sonarRevealedUntil[id] = now + SONAR_PERSIST_DURATION;
                        break;
                    }
                }
            }
        }
        for (const id in otherPlayers) {
            const p = otherPlayers[id];
            const hist = otherPlayersHistory[id];
            const isSubmerged = hist ? !!hist.submerged : (p.position.y < PERISCOPE_DEPTH + 0.05);
            const info = otherPlayersInfo[id];
            const isAlly = !!(localTeamId && info && info.teamId === localTeamId);
            if (revealed.has(id)) {
                const pinged = !!sonarRevealedUntil[id];
                radarFrozenBoats.push({ id, x: p.position.x, z: p.position.z, y: p.position.y, sonar: true, pinged, ally: isAlly });
                continue;
            }
            if (isSubmerged) continue;
            if (isAlly) {
                radarFrozenBoats.push({ id, x: p.position.x, z: p.position.z, y: p.position.y, sonar: false, ally: true });
            } else if (isLineOfSightClear(p.position.x, p.position.z, null)) {
                radarFrozenBoats.push({ id, x: p.position.x, z: p.position.z, y: p.position.y, sonar: false, ally: false });
            }
        }
        if (!isViewingLocal() && localBoat && localBoat.mesh) {
            const lm = localBoat.mesh;
            if (lm.position.y > PERISCOPE_DEPTH && isLineOfSightClear(lm.position.x, lm.position.z, null)) {
                radarFrozenBoats.push({ id: playerId, x: lm.position.x, z: lm.position.z, y: lm.position.y, sonar: false });
            }
        }
    } else {
        radarFrozenBoats = radarFrozenBoats.filter(b => !b.sonarTransient);
        for (const id of revealed) {
            const p = otherPlayers[id];
            if (!p) continue;
            const info = otherPlayersInfo[id];
            const isAlly = !!(localTeamId && info && info.teamId === localTeamId);
            radarFrozenBoats = radarFrozenBoats.filter(b => b.id !== id);
            const pinged = !!sonarRevealedUntil[id];
            radarFrozenBoats.push({ id, x: p.position.x, z: p.position.z, y: p.position.y, sonar: true, pinged, sonarTransient: true, ally: isAlly });
        }
    }
    if (selectedBoatId) {
        let cur = radarFrozenBoats.find(b => b.id === selectedBoatId);
        if (!cur) {
            const selW = otherPlayers[selectedBoatId];
            const selfY = playerMesh ? playerMesh.position.y : 0;
            if (selW && selW.isEnabled() && (selfY < PERISCOPE_DEPTH || zoomLowMode)) {
                cur = { id: selectedBoatId, x: selW.position.x, z: selW.position.z, y: selW.position.y, sonar: false, visual: true };
                radarFrozenBoats.push(cur);
            } else {
                selectedBoatId = null;
                selectedBoatIsSonar = false;
            }
        } else if (cur.visual || cur.sonar) {
            const selW = otherPlayers[selectedBoatId];
            if (selW) {
                cur.x = selW.position.x;
                cur.z = selW.position.z;
                cur.y = selW.position.y;
            }
        }
        if (cur) selectedBoatIsSonar = !!cur.sonar;
    }
    const playerProj = proj(playerMesh.position.x, playerMesh.position.z);
    const px = playerProj.x;
    const pz = playerProj.y;

    for (const ping of activePings) {
        // Affiche le front d'onde seulement si :
        // - c'est mon propre ping (visible chez moi)
        // - ou c'est un ping de balise sonar (visible par tous)
        // - ou le front m'a déjà atteint (ping.emitterRevealedUntil set)
        const isMine = ping.emitterId === playerId;
        const reachedMe = !!ping.emitterRevealedUntil;
        if (!isMine && !ping.beacon && !reachedMe) continue;
        const elapsed = now - ping.emittedAt;
        const progress = Math.min(1, elapsed / SONAR_REVEAL_DURATION);
        const cp = proj(ping.x, ping.z);
        const baseRadius = pingRangeUnits(ping);
        const r = baseRadius * progress * scaleX;
        ctx.strokeStyle = "rgba(255, 255, 0, " + (1 - progress).toFixed(2) + ")";
        ctx.lineWidth = 2;
        ctx.beginPath();
        if (!ping.beacon && ping.coneDeg && ping.coneDeg < 360) {
            // Forward radar = (cos(rot), sin(rot)) → angle écran = rot
            const rot = ping.rotation || 0;
            const half = (ping.coneDeg * Math.PI / 180) / 2;
            ctx.arc(cp.x, cp.y, r, rot - half, rot + half);
        } else {
            ctx.arc(cp.x, cp.y, r, 0, Math.PI * 2);
        }
        ctx.stroke();
    }

    for (let i = acquisitionPreviews.length - 1; i >= 0; i--) {
        const ap = acquisitionPreviews[i];
        const age = now - ap.spawnedAt;
        if (age >= 10000) { acquisitionPreviews.splice(i, 1); continue; }
        const cp = proj(ap.x, ap.z);
        const r = ap.radius * scaleX;
        const alpha = 0.9 * (1 - age / 10000);
        ctx.strokeStyle = "rgba(255, 60, 60, " + alpha.toFixed(2) + ")";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cp.x, cp.y, r, 0, Math.PI * 2);
        ctx.stroke();
    }

    ctx.fillStyle = "#ff3333";
    for (const key in remoteTorpedoes) {
        const r = remoteTorpedoes[key];
        const ddx = r.x - playerMesh.position.x;
        const ddz = r.z - playerMesh.position.z;
        if (!allMapMode && ddx * ddx + ddz * ddz > torpedoRadarRangeUnits * torpedoRadarRangeUnits) continue;
        // Les torpilles ennemies ne sont visibles que si LOS clear depuis le joueur (sauf en fullmap).
        if (!allMapMode && r.ownerId !== playerId && !isLineOfSightClear(r.x, r.z, null)) continue;
        // Thermocline : si la torpille est masquée en 3D, elle l'est aussi sur le radar.
        if (!allMapMode && r.mesh && !r.mesh.isEnabled()) continue;
        const tp = proj(r.x, r.z);
        const yawWorld = Math.atan2(r.dirX, r.dirZ);
        const dirLen = 10;
        const ex = tp.x - Math.sin(yawWorld) * dirLen;
        const ey = tp.y + Math.cos(yawWorld) * dirLen;
        // Couleur : vert si amie (la mienne ou celle d'un coéquipier), rouge sinon.
        const isMineTorp = r.ownerId === playerId;
        let torpAlly = false;
        if (!isMineTorp) {
            const oinfo = otherPlayersInfo[r.ownerId];
            torpAlly = !!(localTeamId && oinfo && oinfo.teamId === localTeamId);
        }
        const torpColor = (isMineTorp || torpAlly) ? "#33ff33" : "#ff3333";
        ctx.strokeStyle = torpColor;
        ctx.fillStyle = torpColor;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(tp.x, tp.y);
        ctx.lineTo(ex, ey);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(tp.x, tp.y, 2.5, 0, Math.PI * 2);
        ctx.fill();
        if (selectedTorpedoKey === "remote:" + key) {
            ctx.strokeStyle = "#ff0000";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(tp.x, tp.y, 7, 0, Math.PI * 2);
            ctx.stroke();
        }
    }


    const subSubmerged = currentBoatType === "submarine" && playerMesh.position.y < PERISCOPE_DEPTH;
    if (!subSubmerged) {
        for (const d of activeDrones) {
            const dRangeM = d.rangeMeters || (d.kind === "manual" ? 2000 : 3000);
            const dRadius = metersToUnits(dRangeM) * scaleX;
            const dp = proj(d.x, d.z);
            ctx.strokeStyle = "rgba(102, 204, 255, 0.45)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(dp.x, dp.y, dRadius, 0, Math.PI * 2);
            ctx.stroke();
            ctx.fillStyle = "#66ccff";
            ctx.beginPath();
            ctx.arc(dp.x, dp.y, 3, 0, Math.PI * 2);
            ctx.fill();
            if (d.kind === "manual") {
                const yawWorld = Math.atan2(d.dirX, d.dirZ);
                const dirLen = 12;
                const ex = dp.x - Math.sin(yawWorld) * dirLen;
                const ey = dp.y + Math.cos(yawWorld) * dirLen;
                ctx.strokeStyle = "#66ccff";
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(dp.x, dp.y);
                ctx.lineTo(ex, ey);
                ctx.stroke();
            }
            if (selectedLocalDroneDid === d.did) {
                ctx.strokeStyle = "#ff0000";
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(dp.x, dp.y, 7, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
        const droneRadarMax = torpedoRadarRangeUnits / 10;
        const droneRadarMax2 = droneRadarMax * droneRadarMax;
        for (const key in remoteDrones) {
            const r = remoteDrones[key];
            const ddx = r.x - playerMesh.position.x;
            const ddz = r.z - playerMesh.position.z;
            if (ddx * ddx + ddz * ddz > droneRadarMax2) continue;
            if (!isLineOfSightClear(r.x, r.z, null)) continue;
            const rp = proj(r.x, r.z);
            ctx.fillStyle = "#66ccff";
            ctx.beginPath();
            ctx.arc(rp.x, rp.y, 3, 0, Math.PI * 2);
            ctx.fill();
            if (key === selectedDroneKey) {
                ctx.strokeStyle = "#ff0000";
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(rp.x, rp.y, 7, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
    }

    // Thermoclines sur la map : polygone bleu très clair (contour + remplissage léger).
    for (const spec of thermoclineSpecs) {
        if (!spec.points || spec.points.length < 3) continue;
        ctx.beginPath();
        spec.points.forEach((pt, idx) => {
            const tp = proj(pt.x, pt.z);
            if (idx === 0) ctx.moveTo(tp.x, tp.y);
            else ctx.lineTo(tp.x, tp.y);
        });
        ctx.closePath();
        ctx.fillStyle = "rgba(51,170,255,0.20)";
        ctx.fill();
    }

    ctx.fillStyle = "#00ff00";
    ctx.beginPath();
    ctx.arc(px, pz, 4, 0, Math.PI * 2);
    ctx.fill();

    const dirLen = 10;
    const dx = px + Math.cos(playerRotation) * dirLen;
    const dz = pz + Math.sin(playerRotation) * dirLen;
    // Trait de cap de MON bateau en blanc, pour le distinguer des coéquipiers (vert).
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(px, pz);
    ctx.lineTo(dx, dz);
    ctx.stroke();

    for (const b of radarFrozenBoats) {
        const boatColor = b.ally ? "#00ff00" : "#ff8800";
        ctx.fillStyle = boatColor;
        const p = proj(b.x, b.z);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
        ctx.fill();
        // Profondeur à côté du blip uniquement pour les subs détectés au sonar actif (ping).
        if (b.pinged && typeof b.y === "number" && b.y < PERISCOPE_DEPTH) {
            const depthM = Math.round(-b.y * UNIT_METERS);
            const depthTxt = "-" + depthM + "m";
            ctx.font = "10px monospace";
            const tw = ctx.measureText(depthTxt).width;
            ctx.fillStyle = "rgba(255,255,255,0.7)";
            ctx.fillRect(p.x + 5, p.y - 5, tw + 2, 12);
            ctx.fillStyle = "#000000";
            ctx.fillText(depthTxt, p.x + 6, p.y + 3);
        }
        if (b.ally && b.id !== playerId) {
            const mesh = otherPlayers[b.id];
            const hist = otherPlayersHistory[b.id];
            let rot = null;
            if (mesh && mesh.rotation) rot = mesh.rotation.y;
            else if (hist && typeof hist.rot === "number") rot = hist.rot;
            if (rot !== null) {
                // Direction avant en monde, puis on projette un point légèrement
                // devant pour obtenir l'orientation ÉCRAN ; on trace ensuite un
                // trait de longueur FIXE en pixels (comme torpilles/drones), pour
                // qu'il soit lisible quel que soit le zoom.
                const fwdX = -Math.cos(rot);
                const fwdZ = Math.sin(rot);
                const ahead = proj(b.x + fwdX, b.z + fwdZ);
                let sx = ahead.x - p.x;
                let sy = ahead.y - p.y;
                const len = Math.hypot(sx, sy) || 1;
                const DIR_LEN_PX = 10; // même longueur que le trait de mon bateau
                sx = sx / len * DIR_LEN_PX;
                sy = sy / len * DIR_LEN_PX;
                ctx.strokeStyle = boatColor;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(p.x, p.y);
                ctx.lineTo(p.x + sx, p.y + sy);
                ctx.stroke();
            }
        }
        if (b.id === selectedBoatId) {
            ctx.strokeStyle = "#ff0000";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
            ctx.stroke();
        }
    }
    ctx.fillStyle = "#ff3333";
    for (const g of grenades) {
        if (g.phase === "explode") continue;
        if (g.shooterId !== playerId && currentBoatType !== "submarine") continue;
        const gp = proj(g.x, g.z);
        ctx.beginPath();
        ctx.arc(gp.x, gp.y, 4, 0, Math.PI * 2);
        ctx.fill();
    }
    for (const bid in sonarBeacons) {
        const b = sonarBeacons[bid];
        if (!isSonarBeaconVisibleOnRadar(b)) continue;
        const p = proj(b.x, b.z);
        ctx.fillStyle = "#ffd000";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#aa8800";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
        ctx.stroke();
        if (parseInt(bid, 10) === selectedBeaconBid) {
            // Cercle rouge = portée de détection de la balise.
            const rangeR = metersToUnits(b.rangeMeters || sonarBeaconSpec.rangeMeters || 5000) * scaleX;
            ctx.strokeStyle = "#ff0000";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(p.x, p.y, rangeR, 0, Math.PI * 2);
            ctx.stroke();
        }
    }
    // Balises sonar passives : bleu pour les miennes/coéquipiers, gris pour
    // les autres (visibles à tous mais on ne sait pas qui les a posées).
    const myTeamForPassive = localTeamId || selectedTeamId;
    for (const bid in passiveSonarBeacons) {
        const b = passiveSonarBeacons[bid];
        const p = proj(b.x, b.z);
        const isMineOrAlly = (b.ownerId === playerId)
            || (myTeamForPassive && b.teamId === myTeamForPassive);
        ctx.fillStyle = isMineOrAlly ? "#2a5596" : "#666666";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = isMineOrAlly ? "#1a3566" : "#444444";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
        ctx.stroke();
        if (parseInt(bid, 10) === selectedPassiveBeaconBid) {
            ctx.strokeStyle = "#ff0000";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 9, 0, Math.PI * 2);
            ctx.stroke();
        }
    }

    // Mines : blanc + ring gris ; sélectionnée = ring rouge + cercle range.
    // Visibilité radar : surface = LOS depuis le joueur, bottom/suspended =
    // révélée par sonar uniquement.
    for (const key in mines) {
        const m = mines[key];
        if (!isMineVisibleOnRadar(m, key)) continue;
        const p = proj(m.x, m.z);
        ctx.fillStyle = m.armed ? "#ffffff" : "#bbbbbb";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#888888";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.stroke();
        if (key === selectedMineKey) {
            ctx.strokeStyle = "#ff0000";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 8, 0, Math.PI * 2);
            ctx.stroke();
            // Cercle range jaune (en m → unités → pixels via v.sX).
            const rangeU = metersToUnits(m.range || 0);
            const rangePx = rangeU * v.sX;
            if (rangePx > 1) {
                ctx.strokeStyle = "rgba(255,220,0,0.75)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.arc(p.x, p.y, rangePx, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
    }

    {
        const speedRatio = maxSpeed > 0 ? Math.abs(boatSpeed) / maxSpeed : 0;
        const isReversing = boatSpeed < 0 && speedRatio > 0;
        const noisy = isReversing || (localSpeedNoiseLimit > 0 && speedRatio > localSpeedNoiseLimit);
        if (noisy) {
            ctx.fillStyle = "#ff6644";
            ctx.font = "bold 11px monospace";
            ctx.fillText("Déplacement bruyant", 6, 14);
        }
    }
    if (radarZoom > 1.01) {
        ctx.fillStyle = "#88ff88";
        ctx.font = "bold 10px monospace";
        ctx.fillText("x" + radarZoom.toFixed(1), w - 32, 12);
    }
    updateRadarTooltip(v);
}

function updateRadarTooltip(v) {
    let tip = document.getElementById("radarTooltip");
    if (!tip) {
        tip = document.createElement("div");
        tip.id = "radarTooltip";
        tip.style.cssText = "position:absolute;background:rgba(0,0,0,0.8);color:#0f0;padding:4px 8px;border:1px solid #0f0;border-radius:4px;font-family:monospace;font-size:11px;line-height:1.4;z-index:11;pointer-events:none;white-space:pre;display:none;";
        document.body.appendChild(tip);
    }
    let target = null;
    if (selectedTorpedoKey && selectedTorpedoKey.startsWith("remote:")) {
        const key = selectedTorpedoKey.slice("remote:".length);
        const r = remoteTorpedoes[key];
        if (r) {
            const ddx = r.x - playerMesh.position.x;
            const ddz = r.z - playerMesh.position.z;
            const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
            const depthM = Math.max(0, Math.round(-(r.y || 0) * UNIT_METERS));
            const kindLabel = r.kind === "acoustic" ? "Torpille acoustique"
                : r.kind === "wireGuided" ? "Torpille filoguidée"
                : r.kind === "autonomous" ? "Torpille autonome"
                : "Torpille";
            const isOwn = r.ownerId === playerId;
            const ownerLabel = isOwn ? "La mienne" : "Ennemie";
            const acquired = typeof r.tx === "number" && typeof r.tz === "number";
            const stateLabel = acquired ? "en acquisition" : "non activée";
            const lines = [kindLabel, ownerLabel,
                "Dist: " + distKm + " km",
                "Prof: -" + depthM + " m",
                "État: " + stateLabel];
            target = { x: r.x, z: r.z, text: lines.join("\n") };
        } else {
            selectedTorpedoKey = null;
        }
    } else if (selectedDroneKey) {
        const r = remoteDrones[selectedDroneKey];
        if (r) {
            const ddx = r.x - playerMesh.position.x;
            const ddz = r.z - playerMesh.position.z;
            const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
            const altM = Math.round((r.y || 0) * UNIT_METERS);
            target = { x: r.x, z: r.z, text: "Drone\nDist: " + distKm + " km\nAlt: " + altM + " m" };
        }
    } else if (selectedBeaconBid != null) {
        const b = sonarBeacons[selectedBeaconBid];
        if (b) {
            const ddx = b.x - playerMesh.position.x;
            const ddz = b.z - playerMesh.position.z;
            const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
            target = { x: b.x, z: b.z, text: "Balise sonar\nDist: " + distKm + " km" };
        }
    } else if (selectedLocalDroneDid != null) {
        const d = activeDrones.find(x => x.did === selectedLocalDroneDid);
        if (d) {
            const ddx = d.x - playerMesh.position.x;
            const ddz = d.z - playerMesh.position.z;
            const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
            const altM = Math.round((d.y || 0) * UNIT_METERS);
            const kindLabel = d.kind === "manual" ? "Drone manuel" : "Drone auto";
            const stateLabel = d.returning ? "retour" : "actif";
            target = { x: d.x, z: d.z, text: kindLabel + " (" + stateLabel + ")\nDist: " + distKm + " km\nAlt: " + altM + " m" };
        } else {
            selectedLocalDroneDid = null;
        }
    } else if (selectedMineKey != null) {
        const m = mines[selectedMineKey];
        if (m) {
            const ddx = m.x - playerMesh.position.x;
            const ddz = m.z - playerMesh.position.z;
            const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
            const kindLabel = m.kind === "surface" ? "Mine surface"
                : m.kind === "bottom" ? "Mine de fond"
                : m.kind === "suspended" ? "Mine suspendue"
                : "Mine";
            const depthM = Math.max(0, Math.round(-m.y * UNIT_METERS));
            const armed = m.armed ? "armée" : "en armement";
            const lines = [kindLabel + " (" + armed + ")",
                "Dist: " + distKm + " km",
                "Prof: -" + depthM + " m",
                "Range: " + Math.round(m.range || 0) + " m"];
            target = { x: m.x, z: m.z, text: lines.join("\n") };
        } else {
            selectedMineKey = null;
        }
    }
    if (!target) {
        tip.style.display = "none";
        return;
    }
    // Position fixe au-dessus à gauche du radar (hors du radar lui-même).
    const rect = radarCanvas.getBoundingClientRect();
    tip.textContent = target.text;
    tip.style.display = "block";
    tip.style.left = rect.left + "px";
    // Hauteur estimée à partir du nombre de lignes (line-height 1.4 × 11px).
    const lineCount = (target.text.match(/\n/g) || []).length + 1;
    const tipH = Math.ceil(lineCount * 11 * 1.4) + 10;
    tip.style.top = (rect.top - tipH - 4) + "px";
}

function syncTorpedoActivationInputs() {
    const map = [
        ["torpedoAcousticActivation", "acoustic"],
        ["torpedoWireGuidedActivation", "wireGuided"],
        ["torpedoAutonomousActivation", "autonomous"],
    ];
    for (const [id, kind] of map) {
        const el = document.getElementById(id);
        if (!el) continue;
        const v = (torpedoStats[kind] && torpedoStats[kind].activation) || 0;
        el.value = v;
    }
}

function readTorpedoActivation(kind) {
    const ids = {
        acoustic: "torpedoAcousticActivation",
        wireGuided: "torpedoWireGuidedActivation",
        autonomous: "torpedoAutonomousActivation",
    };
    const el = document.getElementById(ids[kind]);
    if (!el) return (torpedoStats[kind] && torpedoStats[kind].activation) || 0;
    const raw = parseFloat(el.value);
    if (isNaN(raw) || raw < 0) return (torpedoStats[kind] && torpedoStats[kind].activation) || 0;
    return raw;
}

function updateTorpedoPanel() {
    const map = [
        ["torpedoAcoustic", "acoustic", "Torpille acoustique"],
        ["torpedoWireGuided", "wireGuided", "Torpille filoguidée"],
        ["torpedoAutonomous", "autonomous", "Torpille autonome"],
    ];
    for (const [id, key, label] of map) {
        const btn = document.getElementById(id);
        if (!btn) continue;
        // Mémoriser le tooltip d'origine (HTML) une seule fois — c'est notre base.
        if (typeof btn.dataset.baseTitle !== "string") {
            btn.dataset.baseTitle = btn.title || "";
        }
        const n = torpedoCounts[key] || 0;
        const max = torpedoInitialCounts[key] || 0;
        btn.textContent = label;
        btn.title = n + " / " + max + " — " + btn.dataset.baseTitle;
        let disabled = n <= 0;
        if (key === "wireGuided" && activeWireTorpedoKey) disabled = true;
        btn.disabled = disabled;
    }
    const destroyBtn = document.getElementById("torpedoWireGuidedDestroy");
    if (destroyBtn) destroyBtn.disabled = !activeWireTorpedoKey;
    updateWeaponsUI();
}

const leftUIBaseTops = {
    radar: 10,
    botsBtn: 243,
    zoomBtn: 243,
    zoomLowBtn: 243,
    timeMultiplierIndicator: 250,
    periscopeBtn: 275,
    surfaceBtn: 275,
    targetDepthInput: 275,
    weaponsToggle: 275,
};
const leftUIBaseLefts = {
    radar: 10,
    botsBtn: 10,
    zoomBtn: 64,
    zoomLowBtn: 118,
    timeMultiplierIndicator: 270,
    periscopeBtn: 10,
    surfaceBtn: 52,
    targetDepthInput: 94,
    weaponsToggle: 10,
};
let leftUIOffsetX = 0;
let leftUIOffsetY = 0;

function applyLeftUIOffsets() {
    const isSub = currentBoatType === "submarine";
    for (const id of Object.keys(leftUIBaseTops)) {
        const el = document.getElementById(id);
        if (!el) continue;
        let top = leftUIBaseTops[id];
        if (id === "weaponsToggle" && isSub) top = 307;
        el.style.top = (top + leftUIOffsetY) + "px";
        el.style.left = ((leftUIBaseLefts[id] || 10) + leftUIOffsetX) + "px";
    }
}

function repositionLeftUI() {
    const isSub = currentBoatType === "submarine";
    // Hauteur totale du bloc UI gauche (radar + lignes de boutons + bouton Arme).
    // Destroyer : zoom/bots (243) + Arme (275→311) = 311
    // Sub : zoom/bots (243) + périscope/surface/depth (275→307) + Arme (307→343) = 343
    const total = isSub ? 343 : 311;
    const margin = 10;
    leftUIOffsetY = Math.max(0, window.innerHeight - total - margin);
    leftUIOffsetX = 0;
    applyLeftUIOffsets();
}

window.addEventListener("resize", repositionLeftUI);

(function setupLeftUIDrag() {
    let dragging = false;
    let startMx = 0, startMy = 0, startOx = 0, startOy = 0;
    const radar = document.getElementById("radar");
    if (!radar) return;
    radar.addEventListener("pointerdown", (e) => {
        if (e.button !== 0 || !e.shiftKey) return;
        dragging = true;
        startMx = e.clientX; startMy = e.clientY;
        startOx = leftUIOffsetX; startOy = leftUIOffsetY;
        try { radar.setPointerCapture(e.pointerId); } catch (_) {}
        e.preventDefault();
        e.stopPropagation();
    });
    radar.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        leftUIOffsetX = startOx + (e.clientX - startMx);
        leftUIOffsetY = startOy + (e.clientY - startMy);
        applyLeftUIOffsets();
    });
    const stop = (e) => {
        if (!dragging) return;
        dragging = false;
        try { radar.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    radar.addEventListener("pointerup", stop);
    radar.addEventListener("pointercancel", stop);
})();

function updateWeaponsUI() {
    const toggle = document.getElementById("weaponsToggle");
    const popup = document.getElementById("weaponsPopup");
    const sgPanel = document.getElementById("sonarGrenadePanel");
    const torpedo = document.getElementById("torpedoPanel");
    const has = currentBoatType === "destroyer" || currentBoatType === "submarine";
    if (toggle) toggle.style.display = has ? "block" : "none";
    if (!has && popup) popup.style.display = "none";
    if (sgPanel) sgPanel.style.display = has ? "flex" : "none";
    const grenadeRowEl = document.getElementById("grenadeRow");
    if (grenadeRowEl) grenadeRowEl.style.display = currentBoatType === "destroyer" ? "flex" : "none";
    if (torpedo) torpedo.style.display = has ? "block" : "none";
    const minePanelEl = document.getElementById("minePanel");
    if (minePanelEl) minePanelEl.style.display = has ? "block" : "none";
    const wgRow = document.getElementById("torpedoWireGuided");
    if (wgRow && wgRow.parentElement) {
        wgRow.parentElement.style.display = currentBoatType === "submarine" ? "" : "none";
    }
    const tdi = document.getElementById("targetDepthInput");
    if (tdi) tdi.style.display = currentBoatType === "submarine" ? "block" : "none";
    const pbtn = document.getElementById("periscopeBtn");
    if (pbtn) pbtn.style.display = currentBoatType === "submarine" ? "block" : "none";
    const surfBtn = document.getElementById("surfaceBtn");
    if (surfBtn) surfBtn.style.display = currentBoatType === "submarine" ? "block" : "none";
    const sbtnShort = document.getElementById("sonarShortBtn");
    if (sbtnShort) sbtnShort.textContent = "Sonar " + sonarShortAngleDeg + "°";
    const sbtnLarge = document.getElementById("sonarLargeBtn");
    if (sbtnLarge) sbtnLarge.textContent = "Sonar " + sonarLargeAngleDeg + "°";
    const zbtn = document.getElementById("zoomBtn");
    if (zbtn) zbtn.style.display = has ? "block" : "none";
    const zlbtn = document.getElementById("zoomLowBtn");
    if (zlbtn) zlbtn.style.display = (has && currentBoatType === "destroyer") ? "block" : "none";
    const bbtn = document.getElementById("botsBtn");
    if (bbtn) bbtn.style.display = has ? "block" : "none";
    repositionLeftUI();
}

function toggleWeaponsPopup() {
    const popup = document.getElementById("weaponsPopup");
    if (!popup) return;
    popup.style.display = popup.style.display === "block" ? "none" : "block";
}

function fireTorpedo(kind) {
    if (isSinking || !playerMesh) {
        console.warn("[fireTorpedo] bloqué : isSinking=" + isSinking + " playerMesh=" + !!playerMesh);
        if (isSinking) setTransientMessage("Tir impossible : bateau en perdition");
        return;
    }
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (currentBoatType !== "submarine" && currentBoatType !== "destroyer") return;
    if ((torpedoCounts[kind] || 0) <= 0) {
        console.warn("[fireTorpedo] bloqué : compteur " + kind + "=" + (torpedoCounts[kind] || 0));
        setTransientMessage("Plus de torpilles " + kind);
        return;
    }
    if (kind === "wireGuided" && activeWireTorpedoKey) {
        setTransientMessage("Une filoguidée est déjà en vol");
        return;
    }
    const activationMeters = readTorpedoActivation(kind);
    // Portée max de ce type de torpille (mètres). Sert à prévenir le joueur quand
    // sa cible est trop loin (le serveur refuserait le tir silencieusement).
    const maxRangeM = (torpedoStats[kind] && torpedoStats[kind].maxRangeMeters) || 10000;
    const outOfRange = (tx, tz) => {
        if (!playerMesh) return false;
        const dxr = tx - playerMesh.position.x;
        const dzr = tz - playerMesh.position.z;
        const distM = Math.sqrt(dxr * dxr + dzr * dzr) * UNIT_METERS;
        return distM > maxRangeM;
    };
    if (selectedBeaconBid != null && sonarBeacons[selectedBeaconBid]) {
        const b = sonarBeacons[selectedBeaconBid];
        if (outOfRange(b.x, b.z)) {
            setTransientMessage("Cible hors de portée (" + Math.round(maxRangeM / 1000) + " km max)");
            return;
        }
        socket.emit("torpedo_fire", withBsid({ kind, fixedTarget: { x: b.x, z: b.z, beaconBid: b.bid }, activationMeters }));
        return;
    }
    if (selectedBoatId && otherPlayers[selectedBoatId]) {
        const w = otherPlayers[selectedBoatId];
        if (outOfRange(w.position.x, w.position.z)) {
            setTransientMessage("Cible hors de portée (" + Math.round(maxRangeM / 1000) + " km max)");
            return;
        }
        if (selectedBoatId.startsWith("lure_")) {
            socket.emit("torpedo_fire", withBsid({ kind, fixedTarget: { x: w.position.x, z: w.position.z }, activationMeters }));
        } else {
            socket.emit("torpedo_fire", withBsid({ kind, targetId: selectedBoatId, activationMeters }));
        }
        return;
    }
    // Torpille sélectionnée : tirer vers sa position courante (fixedTarget + antiTorpedo).
    if (selectedTorpedoKey && selectedTorpedoKey.startsWith("remote:")) {
        const tkey = selectedTorpedoKey.slice(7);
        const t = remoteTorpedoes[tkey];
        if (t) {
            if (outOfRange(t.x, t.z)) {
                setTransientMessage("Cible hors de portée (" + Math.round(maxRangeM / 1000) + " km max)");
                return;
            }
            socket.emit("torpedo_fire", withBsid({ kind, fixedTarget: { x: t.x, z: t.z }, antiTorpedo: true, activationMeters }));
            return;
        }
    }
    // Aucune cible sélectionnée : on entre en mode visée, le clic suivant sur
    // le radar fournira la position de tir (fixedTarget).
    aimingTorpedoKind = kind;
    showAimBanner(true);
}

function showAimBanner(show) {
    let banner = document.getElementById("aimBanner");
    if (show && !banner) {
        banner = document.createElement("div");
        banner.id = "aimBanner";
        banner.style.cssText = "position:absolute;top:60px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.75);color:#ffaa00;padding:8px 16px;border-radius:5px;font-family:monospace;font-size:14px;z-index:20";
        banner.textContent = "Cliquez sur le radar pour cibler — ESC pour annuler";
        document.body.appendChild(banner);
    } else if (!show && banner) {
        banner.remove();
    }
}

function cancelAim() {
    aimingTorpedoKind = null;
    showAimBanner(false);
    cancelGrenadeAiming();
}

/* La simu torpille est désormais 100% serveur. Le client n'envoie qu'un intent
   de tir (`torpedo_fire`) et un steering (`torpedo_steer`) pour la filoguidée.
   Toutes les torpilles (y compris les miennes) sont rendues via `remoteTorpedoes`
   sur réception de `torpedo_state`. */

function destroyLuresNearExplosion(ex, ez) {
    const r2 = grenadeEffectDistance * grenadeEffectDistance;
    for (const key in acousticLures) {
        const lure = acousticLures[key];
        const dx = lure.x - ex;
        const dz = lure.z - ez;
        if (dx * dx + dz * dz <= r2) {
            if (lure.mesh) lure.mesh.dispose(false, true);
            delete acousticLures[key];
            const lureId = "lure_" + key;
            if (otherPlayers[lureId]) { otherPlayers[lureId].dispose(); delete otherPlayers[lureId]; }
            delete otherPlayersInfo[lureId];
            delete otherPlayersHistory[lureId];
            if (selectedBoatId === lureId) { selectedBoatId = null; selectedBoatIsSonar = false; }
        }
    }
}

function updateTorpedoes(dt) {
    updateRemoteTorpedoes(dt);
    pollWireSteer();
}

function tryResumeWireControl(key) {
    if (!key) return;
    const r = remoteTorpedoes[key];
    if (!r) return;
    if (r.ownerId !== playerId || r.kind !== "wireGuided") return;
    if (activeWireTorpedoKey === key) return;
    activeWireTorpedoKey = key;
    lastWireSteerYaw = 0;
    lastWirePitch = 0;
    updateTorpedoPanel();
    setTransientMessage("Contrôle filoguidée repris");
}

function pollWireSteer() {
    if (!activeWireTorpedoKey) return;
    const yawIn = keys["ArrowLeft"] ? -1 : keys["ArrowRight"] ? 1 : 0;
    const pitchIn = keys[" "] ? 1 : (keys["x"] || keys["X"]) ? -1 : 0;
    if (yawIn !== lastWireSteerYaw || pitchIn !== lastWirePitch) {
        lastWireSteerYaw = yawIn;
        lastWirePitch = pitchIn;
        socket.emit("torpedo_steer", withBsid({ yaw: yawIn, pitch: pitchIn }));
    }
}

const TORPEDO_TRAIL_LIFE_MS = 5000;
const TORPEDO_TRAIL_ALPHA = 0.9;
const MAX_TORPEDO_TRAIL_POINTS = 80; // plafond de points de traînée par torpille
const MAX_TORPEDO_TRAIL_POINTS_GLOBAL = 2000;
let torpedoTrailPointCount = 0;
let torpedoTrailMaterial = null;
function getTorpedoTrailMaterial() {
    if (torpedoTrailMaterial) return torpedoTrailMaterial;
    torpedoTrailMaterial = new BABYLON.StandardMaterial("torpedoTrailMat", scene);
    torpedoTrailMaterial.emissiveColor = new BABYLON.Color3(1, 1, 1);
    torpedoTrailMaterial.diffuseColor = new BABYLON.Color3(1, 1, 1);
    torpedoTrailMaterial.specularColor = new BABYLON.Color3(0, 0, 0);
    torpedoTrailMaterial.disableLighting = true;
    return torpedoTrailMaterial;
}

function disposeTorpedoTrailPoint(point) {
    if (!point || !point.mesh) return;
    point.mesh.dispose();
    point.mesh = null;
    torpedoTrailPointCount = Math.max(0, torpedoTrailPointCount - 1);
}

function addTorpedoTrail(t) {
    if (!t.trail) t.trail = [];
    const now = performance.now();
    // Points plus rapprochés (50 ms) → ligne plus continue et plus visible.
    if (!t.lastTrail || now - t.lastTrail > 50) {
        t.lastTrail = now;
        // Garde-fou : recycle le plus ancien point si on dépasse le plafond
        // (évite l'accumulation de meshes lors d'un combat à nombreuses torpilles).
        if (t.trail.length >= MAX_TORPEDO_TRAIL_POINTS) {
            const old = t.trail.shift();
            disposeTorpedoTrailPoint(old);
        }
        if (torpedoTrailPointCount < MAX_TORPEDO_TRAIL_POINTS_GLOBAL) {
            const dot = BABYLON.MeshBuilder.CreateDisc("torpedoTrail", { radius: 0.22, tessellation: 12 }, scene);
            dot.rotation.x = Math.PI / 2;
            // Traînée : si la torpille court près de la surface (jusqu'à ~3 m, ce qui
            // inclut le plafond -2 m des tirs destroyer→destroyer), on dessine le
            // sillage SUR l'eau (y=0.05) pour qu'il soit visible d'en haut. Plus
            // profond, on le dessine à la profondeur réelle (visible en plongée).
            const SURFACE_WAKE_Y = -metersToUnits(3);
            const trailY = t.y >= SURFACE_WAKE_Y ? 0.05 : t.y;
            dot.position.set(t.x, trailY, t.z);
            dot.material = getTorpedoTrailMaterial();
            dot.visibility = TORPEDO_TRAIL_ALPHA;
            // Exempter du clip plane : sinon une traînée de surface (y=0.05)
            // disparaît quand le joueur plonge (clipPlane masque tout y>0).
            exemptFromClipPlane(dot);
            t.trail.push({ mesh: dot, born: now });
            torpedoTrailPointCount++;
        }
    }
    for (let i = t.trail.length - 1; i >= 0; i--) {
        const age = (performance.now() - t.trail[i].born) / TORPEDO_TRAIL_LIFE_MS;
        if (age >= 1) {
            disposeTorpedoTrailPoint(t.trail[i]);
            t.trail.splice(i, 1);
        } else {
            t.trail[i].mesh.visibility = TORPEDO_TRAIL_ALPHA * (1 - age);
        }
    }
}

function updateRemoteTorpedoes(dt) {
    for (const key in remoteTorpedoes) {
        const r = remoteTorpedoes[key];
        if (performance.now() - r.lastUpdate > 3000) {
            removeRemoteTorpedo(key);
            continue;
        }
        if (typeof r.x !== "number" || typeof r.srvX !== "number") continue;
        // Opt 4 : le serveur n'émet l'état qu'à ~10 Hz. On lisse simplement la
        // position rendue vers la dernière position serveur (lerp exponentiel,
        // comme les bateaux). Pas d'extrapolation : un changement de cap ou un
        // paquet en retard ne provoque donc aucun saut. Le léger lag (~1 m) est
        // imperceptible.
        const f = 1 - Math.exp(-dt * 15);
        r.x += (r.srvX - r.x) * f;
        r.y += ((r.srvY || 0) - r.y) * f;
        r.z += (r.srvZ - r.z) * f;
        r.mesh.position.set(r.x, r.y, r.z);
        r.mesh.rotation.y = -Math.atan2(r.dirZ, r.dirX);
        let torpVisible = true;
        if (playerMesh) {
            if (countThermoclinesCrossed(playerMesh.position.x, playerMesh.position.y, playerMesh.position.z,
                                         r.x, r.y, r.z) > 0) {
                torpVisible = false;
            }
        }
        r.mesh.setEnabled(torpVisible);
        if (torpVisible) addTorpedoTrail(r);
    }
}

function removeRemoteTorpedo(key) {
    const r = remoteTorpedoes[key];
    if (!r) return;
    if (r.mesh) r.mesh.dispose();
    if (r.trail) {
        for (const s of r.trail) {
            disposeTorpedoTrailPoint(s);
        }
    }
    delete remoteTorpedoes[key];
}

function updateAcousticLureButton() {
    const btn = document.getElementById("acousticLureBtn");
    if (!btn) return;
    const has = acousticLureSpec && acousticLureSpec.number > 0 || acousticLureCount > 0;
    btn.style.display = has ? "block" : "none";
    btn.title = String(acousticLureCount);
    btn.disabled = acousticLureCount <= 0;
    btn.textContent = "Leurre (" + acousticLureCount + ")";
    btn.style.opacity = btn.disabled ? "0.5" : "1";
    btn.style.cursor = btn.disabled ? "not-allowed" : "pointer";
}

function dropAcousticLure() {
    if (!playerMesh || isSinking) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (acousticLureCount <= 0) { setTransientMessage("Plus de leurres acoustiques"); return; }
    socket.emit("lure_drop", withBsid({}));
}

function updateSonarBeaconButton() {
    const btn = document.getElementById("sonarBeaconBtn");
    if (!btn) return;
    const has = sonarBeaconSpec && sonarBeaconSpec.number > 0 || sonarBeaconCount > 0;
    btn.style.display = has ? "block" : "none";
    btn.disabled = sonarBeaconCount <= 0;
    btn.textContent = "Balise sonar active (" + sonarBeaconCount + ")";
    btn.style.opacity = btn.disabled ? "0.5" : "1";
    btn.style.cursor = btn.disabled ? "not-allowed" : "pointer";
}

function placeSonarBeacon() {
    if (!playerMesh || isSinking) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (sonarBeaconCount <= 0) { setTransientMessage("Plus de balises sonar actives"); return; }
    socket.emit("sonar_beacon_place", withBsid({}));
}

function addSonarBeacon(b) {
    if (!b || sonarBeacons[b.bid]) return;
    const buoyHeight = metersToUnits(3);
    const buoyDiameter = metersToUnits(1);
    const buoyTopY = metersToUnits(1);
    const buoyCenterY = buoyTopY - buoyHeight / 2;
    const buoyBottomY = buoyTopY - buoyHeight;
    const buoy = BABYLON.MeshBuilder.CreateCylinder("beacon_" + b.bid,
        { height: buoyHeight, diameter: buoyDiameter }, scene);
    buoy.position.set(b.x, buoyCenterY, b.z);
    const buoyMat = new BABYLON.StandardMaterial("beaconMat_" + b.bid, scene);
    buoyMat.diffuseColor = new BABYLON.Color3(1, 0.85, 0.1);
    buoyMat.emissiveColor = new BABYLON.Color3(0.6, 0.5, 0);
    buoyMat.specularColor = new BABYLON.Color3(0, 0, 0);
    buoy.material = buoyMat;
    exemptFromClipPlane(buoy);

    const tetherLen = metersToUnits(10);
    const tetherDiameter = metersToUnits(0.05);
    const tetherTopY = buoyBottomY;
    const tetherBottomY = tetherTopY - tetherLen;
    const tether = BABYLON.MeshBuilder.CreateCylinder("beaconTether_" + b.bid,
        { height: tetherLen, diameter: tetherDiameter }, scene);
    tether.position.set(b.x, tetherTopY - tetherLen / 2, b.z);
    const tetherMat = new BABYLON.StandardMaterial("beaconTetherMat_" + b.bid, scene);
    tetherMat.diffuseColor = new BABYLON.Color3(0.9, 0.8, 0.1);
    tetherMat.emissiveColor = new BABYLON.Color3(0.7, 0.6, 0.1);
    tetherMat.specularColor = new BABYLON.Color3(0, 0, 0);
    tether.material = tetherMat;
    exemptFromClipPlane(tether);

    const hydro = BABYLON.MeshBuilder.CreateSphere("beaconHydro_" + b.bid,
        { diameter: metersToUnits(0.2), segments: 8 }, scene);
    hydro.position.set(b.x, tetherBottomY, b.z);
    const hydroMat = new BABYLON.StandardMaterial("beaconHydroMat_" + b.bid, scene);
    hydroMat.diffuseColor = new BABYLON.Color3(1, 0.85, 0.1);
    hydroMat.emissiveColor = new BABYLON.Color3(0.8, 0.65, 0.1);
    hydroMat.specularColor = new BABYLON.Color3(0, 0, 0);
    hydro.material = hydroMat;
    exemptFromClipPlane(hydro);

    sonarBeacons[b.bid] = {
        bid: b.bid,
        ownerId: b.ownerId,
        teamId: b.teamId,
        revealedByMyTeam: !!b.revealedByMyTeam,
        x: b.x,
        z: b.z,
        rangeMeters: b.rangeMeters || sonarBeaconSpec.rangeMeters || 5000,
        mesh: buoy,
        tether,
        hydro,
        lastPingAt: 0,
    };
}

function isSonarBeaconVisibleOnRadar(b) {
    if (!b) return false;
    if (allMapMode) return true;
    if (b.teamId && selectedTeamId && b.teamId === selectedTeamId) return true;
    return !!b.revealedByMyTeam;
}

function removeSonarBeacon(bid) {
    const b = sonarBeacons[bid];
    if (!b) return;
    if (b.mesh) b.mesh.dispose(false, true);
    if (b.tether) b.tether.dispose(false, true);
    if (b.hydro) b.hydro.dispose(false, true);
    delete sonarBeacons[bid];
    if (selectedBeaconBid === bid) selectedBeaconBid = null;
}

socket.on("sonar_beacon_placed", (data) => { addSonarBeacon(data); });
socket.on("sonar_beacon_revealed", (data) => {
    const b = sonarBeacons[data.bid];
    if (b) b.revealedByMyTeam = true;
});
socket.on("sonar_beacon_destroyed", (data) => { removeSonarBeacon(data.bid); });
socket.on("sonar_beacon_ping", (data) => {
    const b = sonarBeacons[data.bid];
    if (b) b.lastPingAt = performance.now();
    const rangeM = (b && b.rangeMeters) || sonarBeaconSpec.rangeMeters || 5000;
    activePings.push({
        emitterId: "beacon:" + data.bid,
        x: data.x,
        z: data.z,
        emittedAt: performance.now(),
        expiresAt: performance.now() + SONAR_REVEAL_DURATION,
        beacon: true,
        beaconRange: metersToUnits(rangeM),
    });
    if (currentBoatType === "submarine" && playerMesh && playerMesh.position.y < 0
        && b && b.teamId && localTeamId && b.teamId !== localTeamId) {
        const dx = playerMesh.position.x - data.x;
        const dz = playerMesh.position.z - data.z;
        const dist = Math.hypot(dx, dz);
        if (dist <= metersToUnits(rangeM)) {
            const thermo = countThermoclinesCrossed(data.x, 0, data.z,
                playerMesh.position.x, playerMesh.position.y, playerMesh.position.z);
            if (thermo === 0) showSonarDetectedAlert();
        }
    }
});

let selectedBeaconBid = null;
let selectedPassiveBeaconBid = null;

// ===================== BALISES SONAR PASSIVES =====================

function updatePassiveSonarBeaconButton() {
    const btn = document.getElementById("passiveSonarBeaconBtn");
    if (!btn) return;
    const has = (passiveSonarBeaconSpec && passiveSonarBeaconSpec.number > 0)
        || passiveSonarBeaconCount > 0;
    btn.style.display = has ? "block" : "none";
    btn.disabled = passiveSonarBeaconCount <= 0;
    btn.textContent = "Balise sonar passive (" + passiveSonarBeaconCount + ")";
    btn.style.opacity = btn.disabled ? "0.5" : "1";
    btn.style.cursor = btn.disabled ? "not-allowed" : "pointer";
}

function placePassiveSonarBeacon() {
    if (!playerMesh || isSinking) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (passiveSonarBeaconCount <= 0) { setTransientMessage("Plus de balises sonar passives"); return; }
    socket.emit("passive_sonar_beacon_place", withBsid({}));
}

function addPassiveSonarBeacon(b) {
    if (!b || passiveSonarBeacons[b.bid]) return;
    const buoyHeight = metersToUnits(3);
    const buoyDiameter = metersToUnits(1);
    const buoyTopY = metersToUnits(1);
    const buoyCenterY = buoyTopY - buoyHeight / 2;
    const buoyBottomY = buoyTopY - buoyHeight;
    const buoy = BABYLON.MeshBuilder.CreateCylinder("pbeacon_" + b.bid,
        { height: buoyHeight, diameter: buoyDiameter }, scene);
    buoy.position.set(b.x, buoyCenterY, b.z);
    const buoyMat = new BABYLON.StandardMaterial("pbeaconMat_" + b.bid, scene);
    // Bleu sombre #2a5596
    buoyMat.diffuseColor = new BABYLON.Color3(0x2a / 255, 0x55 / 255, 0x96 / 255);
    buoyMat.emissiveColor = new BABYLON.Color3(0x14 / 255, 0x2a / 255, 0x4b / 255);
    buoyMat.specularColor = new BABYLON.Color3(0, 0, 0);
    buoy.material = buoyMat;
    exemptFromClipPlane(buoy);

    const tetherLen = metersToUnits(10);
    const tetherDiameter = metersToUnits(0.05);
    const tetherTopY = buoyBottomY;
    const tetherBottomY = tetherTopY - tetherLen;
    const tether = BABYLON.MeshBuilder.CreateCylinder("pbeaconTether_" + b.bid,
        { height: tetherLen, diameter: tetherDiameter }, scene);
    tether.position.set(b.x, tetherTopY - tetherLen / 2, b.z);
    const tetherMat = new BABYLON.StandardMaterial("pbeaconTetherMat_" + b.bid, scene);
    tetherMat.diffuseColor = new BABYLON.Color3(0x2a / 255, 0x4a / 255, 0x76 / 255);
    tetherMat.emissiveColor = new BABYLON.Color3(0x18 / 255, 0x30 / 255, 0x55 / 255);
    tetherMat.specularColor = new BABYLON.Color3(0, 0, 0);
    tether.material = tetherMat;
    exemptFromClipPlane(tether);

    const hydro = BABYLON.MeshBuilder.CreateSphere("pbeaconHydro_" + b.bid,
        { diameter: metersToUnits(0.2), segments: 8 }, scene);
    hydro.position.set(b.x, tetherBottomY, b.z);
    const hydroMat = new BABYLON.StandardMaterial("pbeaconHydroMat_" + b.bid, scene);
    hydroMat.diffuseColor = new BABYLON.Color3(0x2a / 255, 0x55 / 255, 0x96 / 255);
    hydroMat.emissiveColor = new BABYLON.Color3(0x18 / 255, 0x35 / 255, 0x66 / 255);
    hydroMat.specularColor = new BABYLON.Color3(0, 0, 0);
    hydro.material = hydroMat;
    exemptFromClipPlane(hydro);

    passiveSonarBeacons[b.bid] = {
        bid: b.bid,
        ownerId: b.ownerId,
        teamId: b.teamId,
        x: b.x,
        z: b.z,
        mesh: buoy,
        tether,
        hydro,
    };
}

function removePassiveSonarBeacon(bid) {
    const b = passiveSonarBeacons[bid];
    if (!b) return;
    if (b.mesh) b.mesh.dispose(false, true);
    if (b.tether) b.tether.dispose(false, true);
    if (b.hydro) b.hydro.dispose(false, true);
    delete passiveSonarBeacons[bid];
    if (selectedPassiveBeaconBid === bid) selectedPassiveBeaconBid = null;
}

socket.on("passive_sonar_beacon_placed", (data) => { addPassiveSonarBeacon(data); });
socket.on("passive_sonar_beacon_destroyed", (data) => { removePassiveSonarBeacon(data.bid); });
socket.on("passive_beacon_count", (data) => {
    if (typeof data.count === "number") passiveSonarBeaconCount = data.count;
    updatePassiveSonarBeaconButton();
});
// Durée d'affichage radar d'un bateau détecté par balise passive (= intervalle
// de tick serveur ; ainsi la détection se rafraîchit en boucle si l'ennemi
// reste à portée).
const PASSIVE_DETECTION_PERSIST_MS = 3000;
socket.on("passive_sonar_detection", (data) => {
    // Filtre côté client : seuls les coéquipiers du propriétaire de la balise
    // voient la détection. Si je n'ai pas la même team, j'ignore.
    if (!data || !data.detectedId) return;
    const myTeam = localTeamId || selectedTeamId;
    if (data.teamId && myTeam && data.teamId !== myTeam) return;
    // Marque le bateau détecté comme révélé pendant 3s (= intervalle tick).
    const now = performance.now();
    passiveSonarDetectionsUntil[data.detectedId] = now + PASSIVE_DETECTION_PERSIST_MS;
});

// ===================== MINES (rendu 3D + listeners) =====================

function _mineKey(ownerId, mid) { return ownerId + ":" + mid; }

// Visibilité d'une mine sur le radar.
//   - À nous (teamId == ma team) ou révélée à ma team de manière permanente : visible.
//   - Surface : visible aussi si LOS clear depuis le joueur (peut révéler).
//   - Bottom/suspended : sinon, visible si révélée par sonar (mineRevealedUntil).
function isMineVisibleOnRadar(m, key) {
    if (!m) return false;
    if (allMapMode) return true;
    if (m.teamId && selectedTeamId && m.teamId === selectedTeamId) return true;
    if (m.revealedByMyTeam) return true;
    return !!mineRevealedUntil[key];
}

function addMine(m) {
    if (!m) return;
    const key = _mineKey(m.ownerId, m.mid);
    if (mines[key]) return;
    const grey = new BABYLON.Color3(0.55, 0.55, 0.55);
    const dark = new BABYLON.Color3(0.18, 0.18, 0.18);
    const sphereD = metersToUnits(2);
    const sphere = BABYLON.MeshBuilder.CreateSphere("mine_" + key,
        { diameter: sphereD, segments: 12 }, scene);
    sphere.position.set(m.x, m.y, m.z);
    const mat = new BABYLON.StandardMaterial("mineMat_" + key, scene);
    mat.diffuseColor = grey;
    mat.emissiveColor = dark;
    mat.specularColor = new BABYLON.Color3(0, 0, 0);
    sphere.material = mat;
    exemptFromClipPlane(sphere);
    const spikes = [];
    if (m.kind === "surface") {
        // 6 pointes radiales en cylindres fins.
        const spikeLen = metersToUnits(1.2);
        const spikeDia = metersToUnits(0.25);
        const dirs = [
            [1, 0, 0], [-1, 0, 0],
            [0, 1, 0], [0, -1, 0],
            [0, 0, 1], [0, 0, -1],
        ];
        for (let i = 0; i < dirs.length; i++) {
            const sp = BABYLON.MeshBuilder.CreateCylinder("mineSpike_" + key + "_" + i,
                { height: spikeLen, diameter: spikeDia }, scene);
            const [dx, dy, dz] = dirs[i];
            sp.position.set(m.x + dx * spikeLen * 0.6, m.y + dy * spikeLen * 0.6, m.z + dz * spikeLen * 0.6);
            // Orienter le cylindre vers la direction.
            if (dx !== 0) sp.rotation.z = Math.PI / 2;
            else if (dz !== 0) sp.rotation.x = Math.PI / 2;
            sp.material = mat;
            exemptFromClipPlane(sp);
            spikes.push(sp);
        }
    }
    let cable = null;
    if (m.kind === "suspended") {
        const cableLen = m.y - SEABED_FLOOR_Y;
        if (cableLen > 0.05) {
            cable = BABYLON.MeshBuilder.CreateCylinder("mineCable_" + key,
                { height: cableLen, diameter: metersToUnits(0.15) }, scene);
            cable.position.set(m.x, SEABED_FLOOR_Y + cableLen / 2, m.z);
            const cmat = new BABYLON.StandardMaterial("mineCableMat_" + key, scene);
            cmat.diffuseColor = new BABYLON.Color3(0.3, 0.3, 0.3);
            cmat.emissiveColor = new BABYLON.Color3(0.1, 0.1, 0.1);
            cable.material = cmat;
            exemptFromClipPlane(cable);
        }
    }
    mines[key] = {
        ownerId: m.ownerId, mid: m.mid, kind: m.kind,
        teamId: m.teamId, revealedByMyTeam: !!m.revealedByMyTeam,
        x: m.x, y: m.y, z: m.z,
        range: m.range, armed: !!m.armed,
        depthMeters: m.depthMeters || null,
        mesh: sphere, spikes, cable,
    };
}

function removeMine(ownerId, mid) {
    const key = _mineKey(ownerId, mid);
    const m = mines[key];
    if (!m) return;
    const mineMaterial = m.mesh && m.mesh.material;
    const cableMaterial = m.cable && m.cable.material;
    if (m.mesh) m.mesh.dispose();
    if (m.cable) m.cable.dispose();
    if (m.spikes) m.spikes.forEach(s => s.dispose());
    if (mineMaterial) mineMaterial.dispose();
    if (cableMaterial) cableMaterial.dispose();
    delete mines[key];
    if (selectedMineKey === key) selectedMineKey = null;
}

socket.on("mine_placed", (data) => { addMine(data); });
socket.on("mine_revealed", (data) => {
    const m = mines[_mineKey(data.ownerId, data.mid)];
    if (m) m.revealedByMyTeam = true;
});
socket.on("mine_dead", (data) => { removeMine(data.ownerId, data.mid); });
socket.on("mine_armed", (data) => {
    const m = mines[_mineKey(data.ownerId, data.mid)];
    if (m) m.armed = true;
});
socket.on("mine_exploded", (data) => {
    if (typeof spawnRemoteExplosion === "function") {
        spawnRemoteExplosion(data.x, data.y, data.z, false);
    }
    if (typeof triggerDamageFlash === "function") {
        triggerDamageFlash(data.x, data.y, data.z);
    }
});
socket.on("mine_counts", (counts) => {
    if (!counts) return;
    const ak = ammoKey(counts.bsid);
    const slot = boatAmmo[ak] || (boatAmmo[ak] = {});
    slot.mine = slot.mine || {};
    for (const k of ["surface", "bottom", "suspended"]) {
        if (typeof counts[k] === "number") slot.mine[k] = counts[k];
    }
    if (ak === ammoKey(activeGhostSid())) {
        for (const k of ["surface", "bottom", "suspended"]) {
            if (typeof counts[k] === "number") mineCounts[k] = counts[k];
        }
        updateMinePanel();
    }
});

function placeMine(kind) {
    if ((mineCounts[kind] || 0) <= 0) { setTransientMessage("Plus de mines " + kind); return; }
    const payload = { kind };
    if (kind === "suspended") {
        const inp = document.getElementById("mineDepthMeters");
        let depth = 20;
        if (inp) {
            const v = parseFloat(inp.value);
            if (!isNaN(v)) depth = v;
        }
        payload.depthMeters = depth;
    }
    socket.emit("mine_place", withBsid(payload));
}

function updateMinePanel() {
    const map = [
        ["mineSurfBtn",      "surface",   "Mine surface"],
        ["mineBottomBtn",    "bottom",    "Mine de fond"],
        ["mineSuspendedBtn", "suspended", "Mine suspendue"],
    ];
    for (const [id, key, label] of map) {
        const btn = document.getElementById(id);
        if (!btn) continue;
        if (typeof btn.dataset.baseTitle !== "string") {
            btn.dataset.baseTitle = btn.title || "";
        }
        const n = mineCounts[key] || 0;
        const max = mineInitialCounts[key] || 0;
        btn.textContent = label;
        btn.title = n + " / " + max + " — " + btn.dataset.baseTitle;
        btn.disabled = n <= 0;
    }
    // Bouton "D" désamorçage : actif si la mine sélectionnée nous appartient
    // et que nous sommes à ≤ 200 m (côté client : feedback visuel ; le serveur
    // re-vérifie).
    const dbtn = document.getElementById("mineDisarmBtn");
    if (dbtn) {
        let canDisarm = false;
        if (selectedMineKey && playerMesh) {
            const m = mines[selectedMineKey];
            if (m && m.ownerId === playerId) {
                const dx = (m.x - playerMesh.position.x) * UNIT_METERS;
                const dz = (m.z - playerMesh.position.z) * UNIT_METERS;
                if (Math.sqrt(dx * dx + dz * dz) <= 200) canDisarm = true;
            }
        }
        dbtn.disabled = !canDisarm;
    }
}

function spawnAcousticLureVisual(ownerId, lid, x, y, z, noise, expiresAt) {
    const key = ownerId + ":" + lid;
    const sphere = BABYLON.MeshBuilder.CreateSphere("lure_" + key, { diameter: 1.2, segments: 12 }, scene);
    const yPos = typeof y === "number" ? y : 0;
    sphere.position.set(x, yPos, z);
    const mat = new BABYLON.StandardMaterial("lureMat_" + key, scene);
    mat.diffuseColor = new BABYLON.Color3(0.4, 0.4, 0.4);
    mat.emissiveColor = new BABYLON.Color3(0.1, 0.1, 0.1);
    mat.specularColor = new BABYLON.Color3(0.2, 0.2, 0.2);
    mat.alpha = 0.4;
    sphere.material = mat;
    exemptFromClipPlane(sphere);
    acousticLures[key] = { ownerId, lid, x, y: yPos, z, noise, expiresAt, mesh: sphere };
}

function updateAcousticLures() {
    const now = performance.now();
    for (const key in acousticLures) {
        const lure = acousticLures[key];
        const lureId = "lure_" + key;
        if (now >= lure.expiresAt) {
            if (lure.mesh) lure.mesh.dispose(false, true);
            delete acousticLures[key];
            if (otherPlayers[lureId]) { otherPlayers[lureId].dispose(); delete otherPlayers[lureId]; }
            delete otherPlayersInfo[lureId];
            delete otherPlayersHistory[lureId];
            if (selectedBoatId === lureId) { selectedBoatId = null; selectedBoatIsSonar = false; }
        } else {
            const hist = otherPlayersHistory[lureId];
            if (hist) hist.t = now;
        }
    }
}

function updateGrenadeButtons() {
    const btn = document.getElementById("grenadeBtn");
    if (btn) {
        btn.textContent = "Grenade (" + grenadeCount + ")";
        btn.disabled = grenadeCount <= 0;
    }
    const vBtn = document.getElementById("grenadeVolleyBtn");
    if (vBtn) vBtn.disabled = grenadeCount < grenadeVolleyNumber;
    const mBtn = document.getElementById("grenadeManualBtn");
    if (mBtn) mBtn.disabled = grenadeCount <= 0;
}

function updateDroneButtons() {
    const a = document.getElementById("droneAutoBtn");
    const m = document.getElementById("droneManualBtn");
    const ar = document.getElementById("droneAutoRecall");
    const mr = document.getElementById("droneManualRecall");
    if (a) {
        a.textContent = "Drone auto (" + droneCounts.automatic + ")";
        a.disabled = !droneSpecs.automatic || droneCounts.automatic <= 0;
    }
    if (m) {
        m.textContent = "Drone manuel (" + droneCounts.manual + ")";
        m.disabled = !droneSpecs.manual || droneCounts.manual <= 0 || activeManualDrone !== null;
    }
    const hasOutgoingAuto = activeDrones.some(d => d.kind === "automatic" && !d.returning);
    const hasOutgoingManual = activeManualDrone !== null && !activeManualDrone.returning;
    if (ar) ar.disabled = !hasOutgoingAuto;
    if (mr) mr.disabled = !hasOutgoingManual;
    updateDroneSwitchButton();
}

function canLaunchDrone() {
    if (!playerMesh || isSinking) return false;
    if (currentBoatType === "submarine" && playerMesh.position.y < PERISCOPE_DEPTH) return false;
    return true;
}

function launchDrone(kind) {
    if (kind === "manual" && activeManualDrone) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (!canLaunchDrone()) return;
    const spec = droneSpecs[kind];
    if (!spec || droneCounts[kind] <= 0) { setTransientMessage("Plus de drones " + kind); return; }
    socket.emit("drone_launch", withBsid({ kind }));
}

function recallDronesByKind(kind) {
    socket.emit("drone_recall", withBsid({ kind }));
}

function cleanupAllDrones() {
    // Coupe tous les drones côté visuel uniquement (le serveur les nettoie aussi
    // via change_boat / disconnect / sink). Évite de garder des meshes orphelins
    // quand on bascule entre vues ou bateaux.
    for (const key in remoteDrones) {
        const r = remoteDrones[key];
        if (r.ownerId !== playerId) continue;
        if (r.mesh) disposeDroneMesh(r.mesh);
        delete remoteDrones[key];
    }
    activeDrones.length = 0;
    activeManualDrone = null;
    manualDroneControl = false;
    if (droneCamera) {
        if (savedCameraBeforeDrone) scene.activeCamera = savedCameraBeforeDrone;
        droneCamera.dispose();
        droneCamera = null;
        savedCameraBeforeDrone = null;
    }
}

function switchToBoatView() {
    if (!activeManualDrone || !manualDroneControl) return;
    manualDroneControl = false;
    if (droneCamera) {
        if (savedCameraBeforeDrone) scene.activeCamera = savedCameraBeforeDrone;
        droneCamera.dispose();
        droneCamera = null;
        savedCameraBeforeDrone = null;
    }
    updateDroneSwitchButton();
}

function switchToDroneView() {
    if (!activeManualDrone || manualDroneControl) return;
    manualDroneControl = true;
    savedCameraBeforeDrone = scene.activeCamera;
    droneCamera = new BABYLON.UniversalCamera("droneCam", new BABYLON.Vector3(activeManualDrone.x, activeManualDrone.y, activeManualDrone.z), scene);
    droneCamera.minZ = 0.05;
    droneCamera.fov = 1.0;
    droneCamera.inputs.clear();
    scene.activeCamera = droneCamera;
    updateDroneSwitchButton();
}

function toggleDroneView() {
    if (!activeManualDrone) return;
    if (manualDroneControl) switchToBoatView();
    else switchToDroneView();
}

function updateDroneSwitchButton() {
    const el = document.getElementById("droneManualSwitch");
    if (!el) return;
    if (!activeManualDrone) {
        el.disabled = true;
        el.textContent = "B";
        return;
    }
    el.disabled = false;
    el.textContent = manualDroneControl ? "B" : "D";
}

function updateDrone(dt) {
    /* La simu drone est désormais 100% serveur. Le client : (a) émet le steering
       du drone manuel en change-only ; (b) propage la découverte des îles depuis
       les positions reçues via `drone_state`. */
    pollDroneSteer();
    if (!worldData || !worldData.islands) return;
    for (const key in remoteDrones) {
        const r = remoteDrones[key];
        if (r.ownerId !== playerId) continue;
        const dRangeM = r.rangeMeters || (r.kind === "manual" ? 2000 : 3000);
        const discoverR = metersToUnits(dRangeM);
        const discoverR2 = discoverR * discoverR;
        worldData.islands.forEach((island, idx) => {
            const samples = radarDiscovered["island_" + idx];
            if (!samples) return;
            for (const sp of samples) {
                if (sp.seen) continue;
                const dx = sp.x - r.x;
                const dz = sp.z - r.z;
                if (dx * dx + dz * dz <= discoverR2) sp.seen = true;
            }
        });
    }
    // Détection ennemis par drones automatiques → message joueur
    if (activeDrones.length > 0 && Object.keys(otherPlayers).length > 0) {
        const droneDetectedThisFrame = new Set();
        for (const id in otherPlayers) {
            const p = otherPlayers[id];
            const hist = otherPlayersHistory[id];
            const submerged = hist ? !!hist.submerged : (p.position.y <= PERISCOPE_DEPTH);
            // Drone auto ne voit pas les bateaux submergés (périscopique inclus).
            if (submerged) continue;
            for (const d of activeDrones) {
                if (d.kind !== "automatic") continue;
                const dRangeM = d.rangeMeters || 3000;
                const dr = metersToUnits(dRangeM);
                const range2 = dr * dr;
                const ddx = p.position.x - d.x;
                const ddz = p.position.z - d.z;
                const dist2 = ddx * ddx + ddz * ddz;
                if (dist2 <= range2) {
                    droneDetectedThisFrame.add(id);
                    showDroneDiscoveryMessage(id);
                    break;
                }
            }
        }
        for (const eid in droneDiscoveredEnemies) {
            if (!droneDetectedThisFrame.has(eid)) clearDroneDiscovery(eid);
        }
    }
}

function pollDroneSteer() {
    if (!activeManualDrone || !manualDroneControl) return;
    const yawIn = keys["ArrowLeft"] ? -1 : keys["ArrowRight"] ? 1 : 0;
    const throttleIn = keys["ArrowUp"] ? 1 : keys["ArrowDown"] ? -1 : 0;
    const climbIn = keys[" "] ? 1 : (keys["x"] || keys["X"]) ? -1 : 0;
    if (yawIn !== lastDroneSteer.yaw || throttleIn !== lastDroneSteer.throttle || climbIn !== lastDroneSteer.climb) {
        lastDroneSteer.yaw = yawIn;
        lastDroneSteer.throttle = throttleIn;
        lastDroneSteer.climb = climbIn;
        socket.emit("drone_steer", withBsid({ yaw: yawIn, throttle: throttleIn, climb: climbIn }));
    }
}

function updateCannonButtons() {
    const cb = document.getElementById("cannonBtn");
    const ab = document.getElementById("aaBtn");
    if (cb) {
        cb.textContent = "Canon (" + cannonAmmo + ")";
        cb.style.display = cannonSpec ? "" : "none";
        cb.disabled = !cannonSpec || cannonAmmo <= 0;
    }
    if (ab) {
        ab.textContent = "Antiaérien (" + aaAmmo + ")";
        ab.style.display = aaSpec ? "" : "none";
        ab.disabled = !aaSpec || aaAmmo <= 0;
    }
}

function findSelectedTarget() {
    if (selectedDroneKey) {
        const r = remoteDrones[selectedDroneKey];
        if (r && playerMesh) {
            const ddx = r.x - playerMesh.position.x;
            const ddz = r.z - playerMesh.position.z;
            const droneRadarMax = torpedoRadarRangeUnits / 10;
            const inRange = ddx * ddx + ddz * ddz <= droneRadarMax * droneRadarMax;
            if (inRange && isLineOfSightClear(r.x, r.z, null)) {
                return { type: "drone", key: selectedDroneKey, ownerId: r.ownerId, did: r.did, x: r.x, z: r.z, y: r.y };
            }
            selectedDroneKey = null;
        }
    }
    if (selectedBeaconBid != null) {
        const b = sonarBeacons[selectedBeaconBid];
        if (b) {
            return { type: "beacon", bid: b.bid, x: b.x, z: b.z, y: 0 };
        }
        selectedBeaconBid = null;
    }
    if (selectedMineKey != null) {
        const m = mines[selectedMineKey];
        // Canon/DCA ne peuvent toucher que les mines de surface.
        if (m && m.kind === "surface") {
            return { type: "mine", ownerId: m.ownerId, mid: m.mid, x: m.x, z: m.z, y: 0 };
        }
    }
    if (selectedBoatId && otherPlayers[selectedBoatId]) {
        const p = otherPlayers[selectedBoatId];
        return { type: "boat", id: selectedBoatId, x: p.position.x, z: p.position.z, y: p.position.y };
    }
    return null;
}

function fireCannon(kind) {
    if (!playerMesh || isSinking) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (currentBoatType === "submarine" && playerMesh.position.y < boatFlotationY - 0.05) {
        setTransientMessage("Canon impossible en plongée");
        return;
    }
    const spec = kind === "cannon" ? cannonSpec : aaSpec;
    if (!spec) return;
    const ammo = kind === "cannon" ? cannonAmmo : aaAmmo;
    if (ammo <= 0) { setTransientMessage("Plus de munitions " + (kind === "cannon" ? "canon" : "DCA")); return; }
    const target = findSelectedTarget();
    if (!target) {
        setTransientMessage("Pas de cible sélectionnée");
        return;
    }
    if (kind === "cannon" && target.type === "drone") {
        setTransientMessage("Canon : cible drone non autorisée, utilisez l'antiaérien");
        return;
    }
    if (target.type === "boat" && typeof target.y === "number" && target.y < -0.25) {
        setTransientMessage("Cible immergée, canon inefficace");
        return;
    }
    const dx = target.x - playerMesh.position.x;
    const dz = target.z - playerMesh.position.z;
    const distMeters = Math.sqrt(dx * dx + dz * dz) * UNIT_METERS;
    if (distMeters > spec.range) {
        setTransientMessage("Cible hors de portée");
        return;
    }
    const intent = { kind, targetType: target.type };
    if (target.type === "boat") intent.targetId = target.id;
    else if (target.type === "drone") { intent.ownerId = target.ownerId; intent.did = target.did; }
    else if (target.type === "beacon") intent.bid = target.bid;
    else if (target.type === "mine") { intent.ownerId = target.ownerId; intent.mid = target.mid; }
    socket.emit("cannon_fire", withBsid(intent));
}

function spawnCannonTracer(kind, startX, startY, startZ, endX, endY, endZ, arcHeight, durationMs) {
    if (kind === "cannon") {
        const mesh = BABYLON.MeshBuilder.CreateSphere("shell", { diameter: 0.2 }, scene);
        const mat = new BABYLON.StandardMaterial("shellMat", scene);
        mat.emissiveColor = new BABYLON.Color3(0.9, 0.7, 0.2);
        mat.diffuseColor = new BABYLON.Color3(0, 0, 0);
        mesh.material = mat;
        mesh.position.set(startX, startY, startZ);
        cannonTracers.push({
            type: "shell",
            mesh,
            startX, startY, startZ,
            endX, endY, endZ,
            arcHeight,
            startedAt: performance.now(),
            duration: durationMs,
        });
    } else {
        const segments = 20;
        const lineMeshes = [];
        for (let i = 0; i < segments; i++) {
            if (i % 2 === 1) continue;
            const u0 = i / segments;
            const u1 = (i + 1) / segments;
            const p0 = arcPoint(startX, startY, startZ, endX, endY, endZ, arcHeight, u0);
            const p1 = arcPoint(startX, startY, startZ, endX, endY, endZ, arcHeight, u1);
            const line = BABYLON.MeshBuilder.CreateLines("aaLine", { points: [p0, p1] }, scene);
            line.color = new BABYLON.Color3(1, 0.8, 0.2);
            lineMeshes.push(line);
        }
        cannonTracers.push({
            type: "aa",
            startedAt: performance.now(),
            duration: 2000,
            meshes: lineMeshes,
        });
    }
}

function setTransientMessage(msg) {
    let el = document.getElementById("transientMsg");
    if (!el) {
        el = document.createElement("div");
        el.id = "transientMsg";
        el.style.cssText = "position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(120,40,40,0.85);color:#fff;padding:10px 18px;border-radius:6px;font-family:sans-serif;font-size:16px;z-index:50;pointer-events:none";
        document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.display = "block";
    clearTimeout(setTransientMessage._t);
    setTransientMessage._t = setTimeout(() => { el.style.display = "none"; }, 1500);
}

function arcPoint(sx, sy, sz, ex, ey, ez, h, u) {
    const x = sx + (ex - sx) * u;
    const z = sz + (ez - sz) * u;
    const arc = 4 * u * (1 - u);
    const y = sy + (ey - sy) * u + arc * h;
    return new BABYLON.Vector3(x, y, z);
}

function updateCannonShells() {
    const now = performance.now();
    for (let i = cannonTracers.length - 1; i >= 0; i--) {
        const t = cannonTracers[i];
        const age = now - t.startedAt;
        const u = Math.min(1, age / t.duration);
        if (t.type === "shell") {
            const p = arcPoint(t.startX, t.startY, t.startZ, t.endX, t.endY, t.endZ, t.arcHeight, u);
            t.mesh.position.copyFrom(p);
            if (u >= 1) {
                t.mesh.dispose(false, true);
                cannonTracers.splice(i, 1);
            }
        } else if (t.type === "aa") {
            const fade = 1 - u;
            for (const m of t.meshes) {
                m.alpha = Math.max(0, fade);
            }
            if (u >= 1) {
                for (const m of t.meshes) m.dispose();
                cannonTracers.splice(i, 1);
            }
        }
    }
    /* La détection d'impact / dégâts est désormais 100% serveur. Les events
       `cannon_hit`, `drone_dead reason="shot"` et `sonar_beacon_destroyed` reçus
       depuis le serveur déclenchent les visuels et dégâts ; rien à faire ici. */
}

function spawnCannonImpactVisual(x, y, z) {
    const ring = BABYLON.MeshBuilder.CreateDisc("cannonImpact", { radius: 1, tessellation: 24 }, scene);
    ring.rotation.x = Math.PI / 2;
    ring.position.set(x, Math.max(0.1, y), z);
    const mat = new BABYLON.StandardMaterial("cannonImpactMat", scene);
    mat.emissiveColor = new BABYLON.Color3(1, 0.6, 0.1);
    mat.diffuseColor = new BABYLON.Color3(0, 0, 0);
    mat.alpha = 0.9;
    mat.disableLighting = true;
    ring.material = mat;
    cannonImpacts.push({ mesh: ring, mat, born: performance.now() });
}

const cannonImpacts = [];

function updateCannonImpacts() {
    const now = performance.now();
    const D = 700;
    for (let i = cannonImpacts.length - 1; i >= 0; i--) {
        const e = cannonImpacts[i];
        const age = now - e.born;
        if (age >= D) {
            e.mesh.dispose(false, true);
            cannonImpacts.splice(i, 1);
            continue;
        }
        const t = age / D;
        const s = 1 + t * 6;
        e.mesh.scaling.x = s;
        e.mesh.scaling.y = s;
        e.mat.alpha = 0.9 * (1 - t);
    }
}

function spawnDroneCrashVisual(x, y, z, dirX, dirZ) {
    spawnDroneExplosionFlash(x, y, z);
    const debris = makeDroneMesh("droneCrash", 2);
    debris.position.set(x, y, z);
    const fall = { mesh: debris, x, y, z, vy: -2, vx: dirX * knotsToUnitPerSecond(50), vz: dirZ * knotsToUnitPerSecond(50), born: performance.now() };
    droneCrashes.push(fall);
}

const droneExplosions = [];

function spawnDroneExplosionFlash(x, y, z) {
    const sphere = BABYLON.MeshBuilder.CreateSphere("droneExpl", { diameter: 1, segments: 12 }, scene);
    sphere.position.set(x, y, z);
    const mat = new BABYLON.StandardMaterial("droneExplMat", scene);
    mat.emissiveColor = new BABYLON.Color3(1, 0.6, 0.1);
    mat.diffuseColor = new BABYLON.Color3(0, 0, 0);
    mat.disableLighting = true;
    mat.alpha = 0.95;
    sphere.material = mat;
    droneExplosions.push({ mesh: sphere, mat, born: performance.now() });
    for (let i = 0; i < 12; i++) {
        const sp = BABYLON.MeshBuilder.CreateSphere("droneSpark", { diameter: 0.3, segments: 6 }, scene);
        sp.position.set(x, y, z);
        const sm = new BABYLON.StandardMaterial("droneSparkMat", scene);
        sm.emissiveColor = new BABYLON.Color3(1, 0.8, 0.2);
        sm.disableLighting = true;
        sp.material = sm;
        const ang = Math.random() * Math.PI * 2;
        const vert = (Math.random() - 0.3) * 0.6;
        const spd = 8 + Math.random() * 6;
        droneExplosions.push({
            mesh: sp,
            mat: sm,
            born: performance.now(),
            kind: "spark",
            x, y, z,
            vx: Math.cos(ang) * spd,
            vy: vert * spd,
            vz: Math.sin(ang) * spd,
        });
    }
}

function updateDroneExplosions(dt) {
    const now = performance.now();
    const D = 800;
    for (let i = droneExplosions.length - 1; i >= 0; i--) {
        const e = droneExplosions[i];
        const age = now - e.born;
        if (age >= D) {
            e.mesh.dispose(false, true);
            droneExplosions.splice(i, 1);
            continue;
        }
        const t = age / D;
        if (e.kind === "spark") {
            e.x += e.vx * dt;
            e.y += e.vy * dt;
            e.z += e.vz * dt;
            e.vy -= 4 * dt;
            e.mesh.position.set(e.x, e.y, e.z);
            e.mat.alpha = 1 - t;
        } else {
            const s = 1 + t * 5;
            e.mesh.scaling.x = s;
            e.mesh.scaling.y = s;
            e.mesh.scaling.z = s;
            e.mat.alpha = 0.95 * (1 - t);
        }
    }
}

const droneCrashes = [];

function updateDroneCrashes(dt) {
    const now = performance.now();
    for (let i = droneCrashes.length - 1; i >= 0; i--) {
        const c = droneCrashes[i];
        c.vy -= 9.81 / UNIT_METERS * dt;
        c.x += c.vx * dt;
        c.y += c.vy * dt;
        c.z += c.vz * dt;
        c.mesh.position.set(c.x, c.y, c.z);
        c.mesh.rotation.x += 5 * dt;
        c.mesh.rotation.z += 3 * dt;
        if (c.y <= 0 || now - c.born > 6000) {
            disposeDroneMesh(c.mesh);
            droneCrashes.splice(i, 1);
        }
    }
}

function spawnGrenadeTrajectory(x, y, z, vx, vy, vz, targetDepth, sinkSpeed) {
    const mesh = BABYLON.MeshBuilder.CreateCylinder("grenade", { diameter: metersToUnits(2), height: metersToUnits(4) }, scene);
    const mat = new BABYLON.StandardMaterial("grenadeMat", scene);
    mat.diffuseColor = new BABYLON.Color3(0.2, 0.2, 0.2);
    mat.emissiveColor = new BABYLON.Color3(0.1, 0.1, 0.1);
    mat.specularColor = new BABYLON.Color3(0.3, 0.3, 0.3);
    mat.disableLighting = true;
    mesh.material = mat;
    mesh.applyFog = false;
    mesh.position.set(x, y, z);
    exemptFromClipPlane(mesh);
    const disc = vy * vy + 2.0 * GRENADE_GRAVITY * y;
    const tFlight = (vy + Math.sqrt(Math.max(0, disc))) / GRENADE_GRAVITY;
    grenades.push({
        phase: "air",
        mesh,
        x, y, z,
        vx, vy, vz,
        targetDepth,
        sinkSpeed,
        createdAt: performance.now(),
        impactX: x + vx * tFlight,
        impactZ: z + vz * tFlight,
        explosionTime: 0,
        explosionMeshes: [],
        remote: false,
    });
}

function toggleGrenadeAiming() {
    if (!playerMesh || isSinking) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (currentBoatType !== "destroyer") return;
    if (grenadeCount <= 0) { setTransientMessage("Plus de grenades"); return; }
    if (!selectedBoatId) {
        setTransientMessage("Sélectionnez d'abord une cible sur le radar");
        return;
    }
    const targetMesh = otherPlayers[selectedBoatId];
    if (!targetMesh) { setTransientMessage("Cible introuvable"); return; }
    const worldX = targetMesh.position.x;
    const worldZ = targetMesh.position.z;
    const depthMeters = Math.max(5, Math.min(500, Math.round(-targetMesh.position.y * UNIT_METERS)));
    const px = playerMesh.position.x;
    const pz = playerMesh.position.z;
    const dx = worldX - px;
    const dz = worldZ - pz;
    const distU = Math.hypot(dx, dz);
    const distM = distU * UNIT_METERS;
    if (distM > grenadeRangeMeters) {
        setTransientMessage("Cible trop loin ! Portée max : " + grenadeRangeMeters + " m");
        return;
    }
    socket.emit("grenade_fire", withBsid({ targetX: worldX, targetZ: worldZ, depthMeters }));
    // Spawn visuel immédiat (même balistique que le serveur).
    const y0 = 1.5;
    const disc = GRENADE_INITIAL_VY * GRENADE_INITIAL_VY + 2.0 * GRENADE_GRAVITY * y0;
    const tFlight = (GRENADE_INITIAL_VY + Math.sqrt(disc)) / GRENADE_GRAVITY;
    const vHoriz = distU / (tFlight > 0.01 ? tFlight : 1);
    const vx = distU > 0.001 ? (dx / distU) * vHoriz : 0;
    const vz = distU > 0.001 ? (dz / distU) * vHoriz : 0;
    spawnGrenadeTrajectory(px, y0, pz, vx, GRENADE_INITIAL_VY, vz, depthMeters / UNIT_METERS, grenadeSinkSpeed);
    const localG = grenades[grenades.length - 1];
    localG.local = true;
    localG.shooterId = playerId;
    addGrenadeHud(localG);
    setTransientMessage("Grenade larguée à " + Math.round(distM) + " m, prof " + depthMeters + " m");
}

function fireGrenadeAtWorldPos(worldX, worldZ) {
    if (!playerMesh || isSinking) return;
    if (grenadeCount <= 0) { setTransientMessage("Plus de grenades"); return; }
    const px = playerMesh.position.x;
    const pz = playerMesh.position.z;
    const dx = worldX - px;
    const dz = worldZ - pz;
    const distU = Math.hypot(dx, dz);
    const distM = distU * UNIT_METERS;
    if (distM > grenadeRangeMeters) {
        setTransientMessage("Trop loin ! Portée max : " + grenadeRangeMeters + " m");
        return;
    }
    const depthInput = document.getElementById("grenadeDepth");
    const rawDepth = depthInput ? parseFloat(depthInput.value) : 10;
    const depthMeters = Math.max(5, Math.min(500, isNaN(rawDepth) ? 10 : rawDepth));
    socket.emit("grenade_fire", withBsid({ targetX: worldX, targetZ: worldZ, depthMeters }));
    const y0 = 1.5;
    const disc = GRENADE_INITIAL_VY * GRENADE_INITIAL_VY + 2.0 * GRENADE_GRAVITY * y0;
    const tFlight = (GRENADE_INITIAL_VY + Math.sqrt(disc)) / GRENADE_GRAVITY;
    const vHoriz = distU / (tFlight > 0.01 ? tFlight : 1);
    const vx = distU > 0.001 ? (dx / distU) * vHoriz : 0;
    const vz = distU > 0.001 ? (dz / distU) * vHoriz : 0;
    spawnGrenadeTrajectory(px, y0, pz, vx, GRENADE_INITIAL_VY, vz, depthMeters / UNIT_METERS, grenadeSinkSpeed);
    const localG = grenades[grenades.length - 1];
    localG.local = true;
    localG.shooterId = playerId;
    addGrenadeHud(localG);
    setTransientMessage("Grenade manuelle à " + Math.round(distM) + " m, prof " + depthMeters + " m");
}

function startGrenadeManualAiming() {
    if (!playerMesh || isSinking) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (currentBoatType !== "destroyer") return;
    if (grenadeCount <= 0) { setTransientMessage("Plus de grenades"); return; }
    grenadeAiming = true;
    aimingTorpedoKind = null;
    showGrenadeAimBanner(true);
}

function cancelGrenadeAiming() {
    grenadeAiming = false;
    showGrenadeAimBanner(false);
}

function showGrenadeAimBanner(show) {
    let banner = document.getElementById("grenadeAimBanner");
    if (show && !banner) {
        banner = document.createElement("div");
        banner.id = "grenadeAimBanner";
        banner.style.cssText = "position:absolute;top:60px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.75);color:#44dd44;padding:8px 16px;border-radius:5px;font-family:monospace;font-size:14px;z-index:20";
        banner.textContent = "Grenade manuelle — cliquez sur la carte ou la scène — ESC pour annuler";
        document.body.appendChild(banner);
    } else if (!show && banner) {
        banner.remove();
    }
}

function fireGrenadeSalve() {
    if (!playerMesh || isSinking) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    if (currentBoatType !== "destroyer") return;
    const vn = grenadeVolleyNumber;
    if (grenadeCount < vn) {
        setTransientMessage("Il faut au moins " + vn + " grenades pour une salve (" + grenadeCount + " restantes)");
        return;
    }
    if (!selectedBoatId) {
        setTransientMessage("Sélectionnez d'abord une cible sur le radar");
        return;
    }
    const targetMesh = otherPlayers[selectedBoatId];
    if (!targetMesh) { setTransientMessage("Cible introuvable"); return; }
    const tx = targetMesh.position.x;
    const tz = targetMesh.position.z;
    const depthMeters = Math.max(5, Math.min(500, Math.round(-targetMesh.position.y * UNIT_METERS)));
    const px = playerMesh.position.x;
    const pz = playerMesh.position.z;
    const dx = tx - px;
    const dz = tz - pz;
    const distU = Math.hypot(dx, dz);
    const distM = distU * UNIT_METERS;
    if (distM > grenadeRangeMeters) {
        setTransientMessage("Cible trop loin ! Portée max : " + grenadeRangeMeters + " m");
        return;
    }
    const fwdX = dx / (distU || 1);
    const fwdZ = dz / (distU || 1);
    const perpX = -dz / (distU || 1);
    const perpZ = dx / (distU || 1);
    const directions = [
        { x: perpX, z: perpZ },
        { x: -perpX, z: -perpZ },
        { x: fwdX, z: fwdZ },
        { x: -fwdX, z: -fwdZ },
    ];
    const offsets = [{ x: 0, z: 0 }];
    let dirIdx = 0;
    let ring = 1;
    while (offsets.length < vn) {
        const distOffset = metersToUnits(50 * ring);
        const d = directions[dirIdx];
        offsets.push({ x: d.x * distOffset, z: d.z * distOffset });
        dirIdx++;
        if (dirIdx >= directions.length) { dirIdx = 0; ring++; }
    }
    const y0 = 1.5;
    const disc = GRENADE_INITIAL_VY * GRENADE_INITIAL_VY + 2.0 * GRENADE_GRAVITY * y0;
    const tFlight = (GRENADE_INITIAL_VY + Math.sqrt(disc)) / GRENADE_GRAVITY;
    for (const off of offsets) {
        const gx = tx + off.x;
        const gz = tz + off.z;
        socket.emit("grenade_fire", withBsid({ targetX: gx, targetZ: gz, depthMeters }));
        const gdx = gx - px;
        const gdz = gz - pz;
        const gDistU = Math.hypot(gdx, gdz);
        const vHoriz = gDistU / (tFlight > 0.01 ? tFlight : 1);
        const vx = gDistU > 0.001 ? (gdx / gDistU) * vHoriz : 0;
        const vz = gDistU > 0.001 ? (gdz / gDistU) * vHoriz : 0;
        spawnGrenadeTrajectory(px, y0, pz, vx, GRENADE_INITIAL_VY, vz, depthMeters / UNIT_METERS, grenadeSinkSpeed);
        const localG = grenades[grenades.length - 1];
        localG.local = true;
        localG.shooterId = playerId;
        addGrenadeHud(localG);
    }
    setTransientMessage("Salve de " + vn + " grenades à " + Math.round(distM) + " m, prof " + depthMeters + " m");
}

function showKillBanner(message) {
    let banner = document.getElementById("killBanner");
    if (!banner) {
        banner = document.createElement("div");
        banner.id = "killBanner";
        banner.style.cssText = "position:absolute;top:30%;left:50%;transform:translate(-50%,-50%);background:rgba(120,0,0,0.85);color:#fff;padding:20px 36px;border-radius:8px;font-family:sans-serif;font-size:22px;font-weight:bold;text-align:center;z-index:50;box-shadow:0 0 20px rgba(0,0,0,0.6)";
        document.body.appendChild(banner);
    }
    banner.textContent = message || "Cible coulée !";
    banner.style.display = "block";
    banner.style.opacity = "1";
    clearTimeout(banner._hideTimer);
    clearInterval(banner._fadeInterval);
    banner._hideTimer = setTimeout(() => {
        let alpha = 1;
        banner._fadeInterval = setInterval(() => {
            alpha -= 0.05;
            if (alpha <= 0) {
                banner.style.display = "none";
                clearInterval(banner._fadeInterval);
            } else {
                banner.style.opacity = String(alpha);
            }
        }, 50);
    }, 3000);
}

function startSinking(attackerId) {
    // Appelé via l'event boat_sunk du serveur quand victimId === playerId.
    // Affiche le tilt + bannière. Pas d'emit côté client : le serveur arbitre.
    if (isSinking) return;
    isSinking = true;
    sinkTiltAxis = Math.random() < 0.5 ? 1 : -1;
    const sinkMsg = document.getElementById("sinkMessage");
    if (sinkMsg) sinkMsg.style.display = "";
}

function triggerDamageFlash(ex, ey, ez) {
    // Flash visuel local immédiat (sans attendre le verdict serveur). Déclenché
    // quand une explosion est dans le rayon d'effet du joueur. Les dégâts
    // réels sont calculés et envoyés par le serveur via l'event `integrity`.
    if (isSinking || !localBoat || !localBoat.mesh) return;
    const lm = localBoat.mesh;
    const dx = ex - lm.position.x;
    const dy = ey - lm.position.y;
    const dz = ez - lm.position.z;
    const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (dist >= grenadeEffectDistance) return;
    damageFlashUntil = performance.now() + 700;
}

function createExplosionVisual(x, z, depth) {
    const ring = BABYLON.MeshBuilder.CreateDisc("expRing", { radius: 0.5, tessellation: 32 }, scene);
    ring.rotation.x = Math.PI / 2;
    ring.position.set(x, 0.06, z);
    const ringMat = new BABYLON.StandardMaterial("expRingMat", scene);
    ringMat.diffuseColor = new BABYLON.Color3(1, 1, 1);
    ringMat.emissiveColor = new BABYLON.Color3(1, 1, 1);
    ringMat.specularColor = new BABYLON.Color3(0, 0, 0);
    ringMat.alpha = 0.9;
    ringMat.backFaceCulling = false;
    ring.material = ringMat;
    exemptFromClipPlane(ring);
    const meshes = [{ mesh: ring, kind: "ring" }];
    const splashScale = Math.max(0, 1 - (depth || 0) / 50);
    if (splashScale > 0) {
        const splash = BABYLON.MeshBuilder.CreateSphere("expSplash", { diameter: 1.2, segments: 12 }, scene);
        splash.position.set(x, 0.3, z);
        const splashMat = new BABYLON.StandardMaterial("expSplashMat", scene);
        splashMat.diffuseColor = new BABYLON.Color3(0.85, 0.9, 1);
        splashMat.emissiveColor = new BABYLON.Color3(0.6, 0.7, 0.9);
        splashMat.specularColor = new BABYLON.Color3(0, 0, 0);
        splashMat.alpha = 0.85;
        splash.material = splashMat;
        exemptFromClipPlane(splash);
        meshes.push({ mesh: splash, kind: "splash", scale: splashScale });
    }
    return meshes;
}

function spawnRemoteExplosion(x, y, z, applyDamage) {
    const meshes = createExplosionVisual(x, z, -y);
    grenades.push({
        phase: "explode",
        mesh: null,
        x,
        y,
        z,
        explosionTime: 0,
        explosionMeshes: meshes,
        targetDepth: -y,
    });
    if (applyDamage !== false) triggerDamageFlash(x, y, z);
}

// --- HUD grenades (tracking pour le tireur) ---
const grenadeHudEntries = {};
let grenadeHudNextId = 0;
function getGrenadeHudContainer() {
    let c = document.getElementById("grenadeHud");
    if (!c) {
        c = document.createElement("div");
        c.id = "grenadeHud";
        c.style.cssText = "position:absolute;top:60px;left:10px;display:flex;flex-direction:column;gap:3px;z-index:50;pointer-events:none;font-family:monospace;font-size:12px;";
        document.body.appendChild(c);
    }
    return c;
}
function addGrenadeHud(g) {
    const id = ++grenadeHudNextId;
    g._hudId = id;
    const el = document.createElement("div");
    el.style.cssText = "background:rgba(0,0,0,0.7);color:#ffcc00;padding:3px 8px;border-radius:3px;";
    el.textContent = "Grenade #" + id + " : lancée";
    getGrenadeHudContainer().appendChild(el);
    grenadeHudEntries[id] = el;
}
function updateGrenadeHud(g) {
    const el = grenadeHudEntries[g._hudId];
    if (!el) return;
    if (g.phase === "air") {
        el.textContent = "Grenade #" + g._hudId + " : vol";
    } else if (g.phase === "water") {
        const depthM = Math.round(-g.y * UNIT_METERS);
        const targetM = Math.round(g.targetDepth * UNIT_METERS);
        el.textContent = "Grenade #" + g._hudId + " : descente " + depthM + "m / " + targetM + "m";
    }
}
function removeGrenadeHud(g, reason) {
    const el = grenadeHudEntries[g._hudId];
    if (!el) return;
    el.textContent = "Grenade #" + g._hudId + " : " + reason;
    el.style.color = reason === "explosion" ? "#ff4400" : "#888";
    setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); delete grenadeHudEntries[g._hudId]; }, 3000);
}

function updateGrenades(dt) {
    const now = performance.now();
    for (let i = grenades.length - 1; i >= 0; i--) {
        const g = grenades[i];
        if (g.local && !g.gid && now - g.createdAt > 10000) {
            if (g.mesh) g.mesh.dispose(false, true);
            if (g._hudId) removeGrenadeHud(g, "tir refusé");
            grenades.splice(i, 1);
            continue;
        }
        if (g.phase === "air") {
            g.vy -= GRENADE_GRAVITY * dt;
            g.x += g.vx * dt;
            g.y += g.vy * dt;
            g.z += g.vz * dt;
            if (g.y <= 0) {
                g.y = 0;
                g.x = g.impactX;
                g.z = g.impactZ;
                g.phase = "water";
                if (g.mesh) {
                    g.mesh.scaling.scaleInPlace(1.5);
                    if (g.mesh.material) {
                        g.mesh.material.diffuseColor = new BABYLON.Color3(1, 1, 1);
                        g.mesh.material.emissiveColor = new BABYLON.Color3(1, 1, 1);
                    }
                }
            }
            if (g._hudId) updateGrenadeHud(g);
            g.mesh.position.set(g.x, g.y, g.z);
        } else if (g.phase === "water") {
            g.y -= (g.sinkSpeed || grenadeSinkSpeed) * dt;
            g.mesh.position.set(g.x, g.y, g.z);
            // L'explosion est arbitrée par le serveur (event grenade_exploded).
            // On clamp visuellement à targetDepth en attendant le signal.
            if (g.y < -g.targetDepth) g.y = -g.targetDepth;
            if (g._hudId) updateGrenadeHud(g);
        } else if (g.phase === "explode") {
            g.explosionTime += dt;
            const t = g.explosionTime / EXPLOSION_DURATION;
            for (const e of g.explosionMeshes) {
                if (e.kind === "ring") {
                    const s = (1 + t * 14) / 3;
                    e.mesh.scaling.x = s;
                    e.mesh.scaling.y = s;
                    e.mesh.material.alpha = Math.max(0, 0.9 * (1 - t));
                } else if (e.kind === "splash") {
                    const sFactor = e.scale || 1;
                    const s = ((1 + t * 4) / 3) * sFactor;
                    e.mesh.scaling.x = s;
                    e.mesh.scaling.y = (s + t * 2 / 3) * sFactor;
                    e.mesh.scaling.z = s;
                    e.mesh.position.y = 0.3 + (t * 1.2 / 3) * sFactor;
                    e.mesh.material.alpha = Math.max(0, 0.85 * (1 - t));
                }
            }
            if (g.explosionTime >= EXPLOSION_DURATION) {
                for (const e of g.explosionMeshes) e.mesh.dispose(false, true);
                grenades.splice(i, 1);
            }
        }
    }
}

const grenadeBtn = document.getElementById("grenadeBtn");
if (grenadeBtn) grenadeBtn.addEventListener("click", () => toggleGrenadeAiming());
const grenadeVolleyBtn = document.getElementById("grenadeVolleyBtn");
if (grenadeVolleyBtn) grenadeVolleyBtn.addEventListener("click", () => fireGrenadeSalve());
const grenadeManualBtn = document.getElementById("grenadeManualBtn");
if (grenadeManualBtn) grenadeManualBtn.addEventListener("click", () => startGrenadeManualAiming());
const torpedoAcousticBtn = document.getElementById("torpedoAcoustic");
const torpedoWireGuidedBtn = document.getElementById("torpedoWireGuided");
const torpedoAutonomousBtn = document.getElementById("torpedoAutonomous");
if (torpedoAcousticBtn) torpedoAcousticBtn.addEventListener("click", () => fireTorpedo("acoustic"));
if (torpedoWireGuidedBtn) torpedoWireGuidedBtn.addEventListener("click", () => fireTorpedo("wireGuided"));
if (torpedoAutonomousBtn) torpedoAutonomousBtn.addEventListener("click", () => fireTorpedo("autonomous"));
const torpedoWireGuidedDestroyBtn = document.getElementById("torpedoWireGuidedDestroy");
if (torpedoWireGuidedDestroyBtn) torpedoWireGuidedDestroyBtn.addEventListener("click", () => {
    if (activeWireTorpedoKey) socket.emit("torpedo_self_destruct", withBsid({ kind: "wireGuided" }));
});

const torpedoAcousticDestroyBtn = document.getElementById("torpedoAcousticDestroy");
if (torpedoAcousticDestroyBtn) torpedoAcousticDestroyBtn.addEventListener("click", () => socket.emit("torpedo_self_destruct", withBsid({ kind: "acoustic" })));
const torpedoAutonomousDestroyBtn = document.getElementById("torpedoAutonomousDestroy");
if (torpedoAutonomousDestroyBtn) torpedoAutonomousDestroyBtn.addEventListener("click", () => socket.emit("torpedo_self_destruct", withBsid({ kind: "autonomous" })));

function previewAcquisitionRange(kind) {
    if (!playerMesh) return;
    const meters = readTorpedoActivation(kind);
    if (!(meters > 0)) return;
    acquisitionPreviews.push({
        x: playerMesh.position.x,
        z: playerMesh.position.z,
        radius: metersToUnits(meters),
        spawnedAt: performance.now(),
    });
}
const ackPreviewAcoustic = document.getElementById("torpedoAcousticPreview");
const ackPreviewAutonomous = document.getElementById("torpedoAutonomousPreview");
if (ackPreviewAcoustic) ackPreviewAcoustic.addEventListener("click", () => previewAcquisitionRange("acoustic"));
if (ackPreviewAutonomous) ackPreviewAutonomous.addEventListener("click", () => previewAcquisitionRange("autonomous"));
const droneAutoBtnEl = document.getElementById("droneAutoBtn");
const droneManualBtnEl = document.getElementById("droneManualBtn");
const droneAutoRecallEl = document.getElementById("droneAutoRecall");
const droneManualRecallEl = document.getElementById("droneManualRecall");
if (droneAutoBtnEl) droneAutoBtnEl.addEventListener("click", () => launchDrone("automatic"));
if (droneManualBtnEl) droneManualBtnEl.addEventListener("click", () => launchDrone("manual"));
if (droneAutoRecallEl) droneAutoRecallEl.addEventListener("click", () => recallDronesByKind("automatic"));
if (droneManualRecallEl) droneManualRecallEl.addEventListener("click", () => recallDronesByKind("manual"));
const droneManualSwitchEl = document.getElementById("droneManualSwitch");
if (droneManualSwitchEl) droneManualSwitchEl.addEventListener("click", toggleDroneView);
const cannonBtnEl = document.getElementById("cannonBtn");
const aaBtnEl = document.getElementById("aaBtn");
if (cannonBtnEl) cannonBtnEl.addEventListener("click", () => fireCannon("cannon"));
if (aaBtnEl) aaBtnEl.addEventListener("click", () => fireCannon("antiAircraft"));
const acousticLureButton = document.getElementById("acousticLureBtn");
if (acousticLureButton) acousticLureButton.addEventListener("click", dropAcousticLure);
const sonarBeaconButton = document.getElementById("sonarBeaconBtn");
if (sonarBeaconButton) sonarBeaconButton.addEventListener("click", placeSonarBeacon);
const passiveSonarBeaconButton = document.getElementById("passiveSonarBeaconBtn");
if (passiveSonarBeaconButton) passiveSonarBeaconButton.addEventListener("click", placePassiveSonarBeacon);
const mineSurfBtn = document.getElementById("mineSurfBtn");
if (mineSurfBtn) mineSurfBtn.addEventListener("click", () => placeMine("surface"));
const mineBottomBtn = document.getElementById("mineBottomBtn");
if (mineBottomBtn) mineBottomBtn.addEventListener("click", () => placeMine("bottom"));
const mineSuspendedBtn = document.getElementById("mineSuspendedBtn");
if (mineSuspendedBtn) mineSuspendedBtn.addEventListener("click", () => placeMine("suspended"));
const mineDisarmBtn = document.getElementById("mineDisarmBtn");
if (mineDisarmBtn) mineDisarmBtn.addEventListener("click", () => {
    if (!selectedMineKey) return;
    const m = mines[selectedMineKey];
    if (!m || m.ownerId !== playerId) return;
    socket.emit("mine_disarm", withBsid({ ownerId: m.ownerId, mid: m.mid }));
});
const weaponsToggleBtn = document.getElementById("weaponsToggle");
if (weaponsToggleBtn) weaponsToggleBtn.addEventListener("click", toggleWeaponsPopup);
const periscopeBtnEl = document.getElementById("periscopeBtn");
if (periscopeBtnEl) {
    periscopeBtnEl.addEventListener("click", () => {
        if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
        if (currentBoatType !== "submarine" || !playerMesh) return;
        periscopeTarget = PERISCOPE_DEPTH;
    });
}
const surfaceBtnEl = document.getElementById("surfaceBtn");
if (surfaceBtnEl) {
    surfaceBtnEl.addEventListener("click", () => {
        if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
        if (currentBoatType !== "submarine" || !playerMesh) return;
        periscopeTarget = -0.2;
    });
}
function triggerSonarPing(coneDeg, rangeUnits) {
    if (!playerMesh) return;
    if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
    const now = performance.now();
    const hasOwnPing = activePings.some(p => p.emitterId === playerId);
    if (!hasOwnPing && now - lastSonarPing <= SONAR_COOLDOWN) return;
    for (let i = activePings.length - 1; i >= 0; i--) {
        if (activePings[i].emitterId === playerId) activePings.splice(i, 1);
    }
    lastSonarPing = now;
    activePings.push({
        emitterId: playerId,
        x: playerMesh.position.x,
        z: playerMesh.position.z,
        y: playerMesh.position.y,
        emittedAt: now,
        expiresAt: now + SONAR_REVEAL_DURATION,
        coneDeg: coneDeg,
        rotation: playerRotation,
        range: rangeUnits,
    });
    socket.emit("sonar_ping", withBsid({
        x: playerMesh.position.x,
        z: playerMesh.position.z,
        coneDeg: coneDeg,
        rotation: playerRotation,
        rangeMeters: rangeUnits * UNIT_METERS,
    }));
}
const sonarShortBtnEl = document.getElementById("sonarShortBtn");
if (sonarShortBtnEl) sonarShortBtnEl.addEventListener("click", () => triggerSonarPing(sonarShortAngleDeg, sonarShortRange));
const sonarLargeBtnEl = document.getElementById("sonarLargeBtn");
if (sonarLargeBtnEl) sonarLargeBtnEl.addEventListener("click", () => triggerSonarPing(sonarLargeAngleDeg, sonarLargeRange));

function toggleZoomMode() {
    if (zoomMode) {
        zoomMode = false;
        zoomLowMode = false;
        const arc = scene.getCameraByName("camera");
        if (arc) scene.activeCamera = arc;
    } else if (playerMesh && scene._fpvCamera) {
        const fwdX = -Math.cos(playerRotation);
        const fwdZ = Math.sin(playerRotation);
        fpvYaw = Math.atan2(fwdX, fwdZ);
        fpvPitch = 0;
        fpvFov = 0.8;
        scene.activeCamera = scene._fpvCamera;
        zoomMode = true;
        zoomLowMode = false;
    }
}
const zoomBtnEl = document.getElementById("zoomBtn");
if (zoomBtnEl) zoomBtnEl.addEventListener("click", toggleZoomMode);

function toggleZoomLowMode() {
    if (zoomLowMode) {
        zoomLowMode = false;
        zoomMode = false;
        const arc = scene.getCameraByName("camera");
        if (arc) scene.activeCamera = arc;
    } else if (playerMesh && scene._fpvCamera) {
        const fwdX = -Math.cos(playerRotation);
        const fwdZ = Math.sin(playerRotation);
        fpvYaw = Math.atan2(fwdX, fwdZ);
        fpvPitch = 0;
        fpvFov = 0.8;
        scene.activeCamera = scene._fpvCamera;
        zoomMode = true;
        zoomLowMode = true;
    }
}
const zoomLowBtnEl = document.getElementById("zoomLowBtn");
if (zoomLowBtnEl) zoomLowBtnEl.addEventListener("click", toggleZoomLowMode);

// Popup d'ajout d'unité (bateau manuel ou bot)
let botsPopupSelectedAi = null;
const MANUAL_BOAT_KINDS = new Set(["addsub", "adddest"]);
function setBotsPopupStatus(msg) {
    const el = document.getElementById("botsStatus");
    if (el) el.textContent = msg || "";
}
function setBotsPopupSelectedAi(kind) {
    botsPopupSelectedAi = kind;
    const buttons = document.querySelectorAll("#botsTypeRow .botsTypeBtn");
    buttons.forEach(b => {
        if (b.dataset.bot === kind) b.classList.add("selected");
        else b.classList.remove("selected");
    });
    // Affiche la section adaptée : manuel = pas de choix d'équipe, bot = choix.
    const isManual = MANUAL_BOAT_KINDS.has(kind);
    const teamSec = document.getElementById("botsTeamSection");
    const manualSec = document.getElementById("botsManualSection");
    if (teamSec) teamSec.style.display = isManual ? "none" : "block";
    if (manualSec) manualSec.style.display = isManual ? "block" : "none";
}
function spawnUnitFromPopup(useMyTeam) {
    if (!botsPopupSelectedAi) {
        setBotsPopupStatus("Choisissez d'abord un type d'unité.");
        return;
    }
    // Bateaux manuels : utilise add_player_boat (équipe = celle du joueur).
    if (botsPopupSelectedAi === "addsub") {
        socket.emit("add_player_boat", { boatType: "submarine" });
        setBotsPopupStatus("Sous-marin manuel ajouté à votre flotte");
        return;
    }
    if (botsPopupSelectedAi === "adddest") {
        socket.emit("add_player_boat", { boatType: "destroyer" });
        setBotsPopupStatus("Destroyer manuel ajouté à votre flotte");
        return;
    }
    // Bots (auto/IA)
    let boatType, finalAi;
    switch (botsPopupSelectedAi) {
        case "autosub":  boatType = "submarine"; finalAi = "autosub"; break;
        case "autodest": boatType = "destroyer"; finalAi = "autodest"; break;
        case "rlsub":    boatType = "submarine"; finalAi = botRlModels.bot_rl_sub; break;
        case "rldest":   boatType = "destroyer"; finalAi = botRlModels.bot_rl_destroyer; break;
        default: setBotsPopupStatus("Type inconnu."); return;
    }
    if (botsPopupSelectedAi === "rlsub" || botsPopupSelectedAi === "rldest") {
        if (typeof finalAi !== "string" || !finalAi) {
            setBotsPopupStatus("Configuration RL indisponible.");
            return;
        }
        finalAi = `rl_${finalAi}`;
    }
    const payload = { boatType, ai: finalAi };
    if (useMyTeam) {
        if (!localTeamId) {
            setBotsPopupStatus("Pas d'équipe locale connue.");
            return;
        }
        payload.team_id = localTeamId;
        payload.team_name = (typeof selectedTeamName === "string" && selectedTeamName) ? selectedTeamName : localTeamId;
    } else {
        payload.team_id = "bots";
        payload.team_name = "Bots";
    }
    socket.emit("spawn_bot", payload);
    setBotsPopupStatus(`Bot ${botsPopupSelectedAi} ajouté à l'équipe ${payload.team_name}`);
}
function spawnRlBot(runName, useMyTeam = false, checkpoint = "", boatType = "submarine") {
    if (!/^[a-zA-Z0-9_.-]+$/.test(runName) || (checkpoint && !/^[a-zA-Z0-9_.-]+$/.test(checkpoint))) {
        throw new Error("Nom de modèle RL invalide");
    }
    if (!["submarine", "destroyer"].includes(boatType)) {
        throw new Error("Type de bateau RL invalide");
    }
    if (useMyTeam && !localTeamId) {
        throw new Error("Pas d'équipe locale connue");
    }
    const ai = `rl_${runName}${checkpoint ? `:${checkpoint}` : ""}`;
    const payload = { boatType, ai };
    if (useMyTeam) {
        payload.team_id = localTeamId;
        payload.team_name = selectedTeamName || localTeamId;
    } else {
        payload.team_id = "bots";
        payload.team_name = "Bots";
    }
    socket.emit("spawn_bot", payload);
    setTransientMessage(`Bot RL ${runName} demandé`);
}
window.spawnRlBot = spawnRlBot;
function toggleBotsPopup() {
    const pop = document.getElementById("botsPopup");
    if (!pop) return;
    pop.style.display = pop.style.display === "block" ? "none" : "block";
}
const botsBtnEl = document.getElementById("botsBtn");
if (botsBtnEl) botsBtnEl.addEventListener("click", toggleBotsPopup);
const botsPopupCloseEl = document.getElementById("botsPopupClose");
if (botsPopupCloseEl) botsPopupCloseEl.addEventListener("click", () => {
    document.getElementById("botsPopup").style.display = "none";
});
document.querySelectorAll("#botsTypeRow .botsTypeBtn").forEach(btn => {
    btn.addEventListener("click", () => setBotsPopupSelectedAi(btn.dataset.bot));
});
const botsAddMineEl = document.getElementById("botsAddMine");
if (botsAddMineEl) botsAddMineEl.addEventListener("click", () => spawnUnitFromPopup(true));
const botsAddBotsEl = document.getElementById("botsAddBots");
if (botsAddBotsEl) botsAddBotsEl.addEventListener("click", () => spawnUnitFromPopup(false));
const botsAddManualEl = document.getElementById("botsAddManual");
if (botsAddManualEl) botsAddManualEl.addEventListener("click", () => spawnUnitFromPopup(true));
const targetDepthEl = document.getElementById("targetDepthInput");
if (targetDepthEl) {
    targetDepthEl.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        if (!isViewingLocal()) { setTransientMessage("Désactivé en vue bot"); return; }
        if (currentBoatType !== "submarine" || !playerMesh) return;
        const v = parseFloat(targetDepthEl.value);
        if (isNaN(v) || v < 0) return;
        const targetUnits = -metersToUnits(v);
        periscopeTarget = Math.max(SEABED_FLOOR_Y, Math.min(-0.2, targetUnits));
        targetDepthEl.blur();
    });
}
const weaponsCloseBtn = document.getElementById("weaponsClose");
if (weaponsCloseBtn) weaponsCloseBtn.addEventListener("click", () => {
    const popup = document.getElementById("weaponsPopup");
    if (popup) popup.style.display = "none";
});

(function setupWeaponsPopupDrag() {
    const popup = document.getElementById("weaponsPopup");
    const header = popup ? popup.querySelector(".weaponsHeader") : null;
    if (!popup || !header) return;
    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;
    header.addEventListener("pointerdown", (e) => {
        if (e.target.closest(".weaponsClose")) return;
        const rect = popup.getBoundingClientRect();
        offsetX = e.clientX - rect.left;
        offsetY = e.clientY - rect.top;
        popup.style.right = "auto";
        popup.style.bottom = "auto";
        popup.style.left = rect.left + "px";
        popup.style.top = rect.top + "px";
        dragging = true;
        header.setPointerCapture(e.pointerId);
        e.preventDefault();
    });
    header.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        const x = Math.max(0, Math.min(window.innerWidth - 40, e.clientX - offsetX));
        const y = Math.max(0, Math.min(window.innerHeight - 40, e.clientY - offsetY));
        popup.style.left = x + "px";
        popup.style.top = y + "px";
    });
    const stop = (e) => {
        if (!dragging) return;
        dragging = false;
        try { header.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    header.addEventListener("pointerup", stop);
    header.addEventListener("pointercancel", stop);
})();

function clearWorld() {
    for (const m of scene.meshes.slice()) {
        if (!m.name) continue;
        if (m.name === "ocean" || m.name === "seabed" || m.name === "grid"
            || m.name.startsWith("island_") || m.name.startsWith("islandWall_")
            || m.name.startsWith("islandTop_") || m.name.startsWith("islandUnder_")
            || m.name.startsWith("dangerZone_") || m.name.startsWith("addingPreview_")
            || m.name.startsWith("thermocline_")) {
            m.dispose(false, true);
        }
    }
    if (oceanMesh) oceanMesh = null;
    if (seabedMesh) seabedMesh = null;
    if (gridMesh) gridMesh = null;
    thermoclineMeshes.length = 0;
    dangerZones.length = 0;
    islandBoundsCache.length = 0;
    for (const k of Object.keys(radarDiscovered)) delete radarDiscovered[k];
}

let adminCamera = null;
function setupTopDownCamera() {
    if (adminCamera) {
        adminCamera.detachControl(canvas);
        adminCamera.dispose();
    }
    const w = (worldData && worldData.ground && worldData.ground.width) || 4000;
    const d = (worldData && worldData.ground && worldData.ground.depth) || 2000;
    const radius = Math.max(w, d) * 0.7;
    const cam = new BABYLON.ArcRotateCamera("adminCam", -Math.PI / 2, 0.001, radius, BABYLON.Vector3.Zero(), scene);
    // Vue 2D plat : alpha et beta verrouillés à la valeur top-down.
    cam.lowerAlphaLimit = -Math.PI / 2;
    cam.upperAlphaLimit = -Math.PI / 2;
    cam.lowerBetaLimit = 0.001;
    cam.upperBetaLimit = 0.001;
    cam.lowerRadiusLimit = 100;
    cam.upperRadiusLimit = Math.max(w, d) * 2;
    cam.panningSensibility = 5;
    cam.attachControl(canvas, true);
    // Désactive le drag de rotation (clic gauche/droit qui tourne la vue).
    if (cam.inputs && cam.inputs.attached && cam.inputs.attached.pointers) {
        cam.inputs.attached.pointers.angularSensibilityX = Infinity;
        cam.inputs.attached.pointers.angularSensibilityY = Infinity;
    }
    scene.activeCamera = cam;
    adminCamera = cam;
}

function enterAdminMode() {
    if (adminMode) return;
    adminMode = true;
    document.getElementById("adminMenu").style.display = "block";
    if (playerMesh) {
        try { playerMesh.dispose(); } catch (_) {}
        playerMesh = null;
    }
    initialized = false;
    if (!worldData) {
        worldData = { ground: { width: 4000, depth: 2000, color: "#4fb5cc" }, islands: [] };
        buildWorld(worldData);
    } else {
        // Reconstruit le monde pour passer les thermoclines en rendu admin
        // (surélevées + plus opaques, visibles en vue top-down).
        clearWorld();
        buildWorld(worldData);
    }
    setupTopDownCamera();
    const elInfo = document.getElementById("info");
    if (elInfo) elInfo.style.display = "none";
    const elWeap = document.getElementById("weaponsToggle");
    if (elWeap) elWeap.style.display = "none";
    const elPop = document.getElementById("weaponsPopup");
    if (elPop) elPop.style.display = "none";
    if (radarCanvas) radarCanvas.style.display = "none";
    adminUndoStack = [JSON.stringify(worldData)];
    adminRedoStack = [];
}

function exitAdminMode() {
    adminMode = false;
    adminEditMode = null;
    adminAddingPoints = [];
    clearAddingPreview();
    adminEditingIslandIdx = null;
    adminEditingPointIdx = null;
    adminMoveIslandIdx = null;
    adminMoveStart = null;
    adminMoveOrigPoints = null;
    if (adminGreyedIslandIdx !== null) restoreGreyedIsland();
    document.getElementById("adminMenu").style.display = "none";
    location.reload();
}

function tryExitAdminMode() {
    if (!adminMode) return;
    if (adminDirty) {
        const ans = confirm("Modifications non sauvegardées. Sauvegarder avant de quitter le mode admin ?\n\nOK = sauvegarder puis quitter\nAnnuler = quitter sans sauvegarder");
        if (ans) {
            adminExitPending = true;
            socket.emit("admin_save_map", { name: adminCurrentMapName, world: worldData });
            return;
        }
    }
    exitAdminMode();
}

function setAdminStatus(msg) {
    const el = document.getElementById("admStatus");
    if (!el) return;
    el.textContent = msg || "";
    if (msg) {
        clearTimeout(setAdminStatus._t);
        setAdminStatus._t = setTimeout(() => { el.textContent = ""; }, 4000);
    }
}

function pushUndoSnapshot() {
    adminUndoStack.push(JSON.stringify(worldData));
    if (adminUndoStack.length > 50) adminUndoStack.shift();
    adminRedoStack = [];
    adminDirty = true;
}

function adminUndo() {
    if (adminUndoStack.length <= 1) return;
    adminRedoStack.push(adminUndoStack.pop());
    worldData = JSON.parse(adminUndoStack[adminUndoStack.length - 1]);
    clearWorld();
    buildWorld(worldData);
    setAdminStatus("Annulé");
}

function adminRedo() {
    if (adminRedoStack.length === 0) return;
    const snap = adminRedoStack.pop();
    adminUndoStack.push(snap);
    worldData = JSON.parse(snap);
    clearWorld();
    buildWorld(worldData);
    setAdminStatus("Refait");
}

function clearAddingPreview() {
    for (const m of scene.meshes.slice()) {
        if (m.name && m.name.startsWith("addingPreview_")) m.dispose(false, true);
    }
    adminAddingPreviewMesh = null;
}

function drawAddingPreview() {
    clearAddingPreview();
    if (adminAddingPoints.length === 0) return;
    const pts = adminAddingPoints.map(p => new BABYLON.Vector3(p.x, 0.2, p.z));
    if (pts.length >= 2) {
        const lines = BABYLON.MeshBuilder.CreateLines("addingPreview_line", { points: pts }, scene);
        lines.color = new BABYLON.Color3(1, 1, 0);
        adminAddingPreviewMesh = lines;
    }
    pts.forEach((p, i) => {
        const dot = BABYLON.MeshBuilder.CreateSphere("addingPreview_dot_" + i, { diameter: 4 }, scene);
        dot.position = p.clone();
        const mat = new BABYLON.StandardMaterial("addingPreview_mat_" + i, scene);
        mat.emissiveColor = new BABYLON.Color3(1, 1, 0);
        mat.disableLighting = true;
        dot.material = mat;
    });
}

function startAddIsland() {
    adminEditMode = "add";
    adminAddingPoints = [];
    clearAddingPreview();
    setAdminStatus("Cliquez les points de l'île. Enter pour fermer, Esc pour annuler.");
}

function finishAddIsland() {
    if (adminAddingPoints.length < 3) {
        setAdminStatus("Au moins 3 points requis");
        return;
    }
    const island = {
        name: "island_user_" + Date.now(),
        points: adminAddingPoints.slice(),
        height: 30,
        color: "#8db87c",
    };
    worldData.islands.push(island);
    adminAddingPoints = [];
    adminEditMode = null;
    clearAddingPreview();
    pushUndoSnapshot();
    clearWorld();
    buildWorld(worldData);
    setAdminStatus("Île ajoutée");
}

function startDeleteIsland() {
    adminEditMode = "delete";
    setAdminStatus("Cliquez sur une île à supprimer. Esc pour annuler.");
}

function startEditIsland() {
    adminEditMode = "edit";
    setAdminStatus("Cliquez et glissez un point d'île pour le déplacer. Esc pour annuler.");
}

function startMoveIsland() {
    adminEditMode = "move";
    setAdminStatus("Cliquez à l'intérieur d'une île et glissez pour la déplacer. Esc pour annuler.");
}

// ---- Thermoclines (mode admin) ----
let adminThermoclineDepth = 60;
function startAddThermocline() {
    const raw = prompt("Profondeur de la thermocline (mètres) :", String(adminThermoclineDepth));
    if (raw === null) return;
    const d = parseFloat(raw);
    if (isNaN(d) || d <= 0 || d > 495) {
        setAdminStatus("Profondeur invalide (1–495 m)");
        return;
    }
    adminThermoclineDepth = d;
    adminEditMode = "thermo_add";
    adminAddingPoints = [];
    clearAddingPreview();
    setAdminStatus("Thermocline " + d + " m : cliquez les points, Entrée pour fermer, Esc pour annuler.");
}

function finishAddThermocline() {
    if (adminAddingPoints.length < 3) {
        setAdminStatus("Au moins 3 points requis");
        return;
    }
    if (!worldData.thermoclines) worldData.thermoclines = [];
    worldData.thermoclines.push({
        points: adminAddingPoints.slice(),
        depthMeters: adminThermoclineDepth,
        opacity: THERMOCLINE_OPACITY,
        color: THERMOCLINE_COLOR,
    });
    adminAddingPoints = [];
    adminEditMode = null;
    clearAddingPreview();
    pushUndoSnapshot();
    clearWorld();
    buildWorld(worldData);
    setAdminStatus("Thermocline ajoutée (" + adminThermoclineDepth + " m)");
}

function startDeleteThermocline() {
    adminEditMode = "thermo_delete";
    setAdminStatus("Cliquez dans une thermocline à supprimer. Esc pour annuler.");
}

function findThermoclineAt(x, z) {
    const list = worldData.thermoclines || [];
    for (let i = list.length - 1; i >= 0; i--) {
        if (pointInPolygon(x, z, list[i].points)) return i;
    }
    return null;
}

let adminTextureSelected = null;
function startIslandTextureMode() {
    adminEditMode = "texture";
    adminTextureSelected = null;
    const popup = document.getElementById("islandTexturePopup");
    if (popup) popup.style.display = "block";
    socket.emit("admin_list_textures");
    setAdminStatus("Mode texture île : choisis une texture puis clique sur les îles.");
}

function stopIslandTextureMode() {
    if (adminEditMode === "texture") adminEditMode = null;
    adminTextureSelected = null;
    const popup = document.getElementById("islandTexturePopup");
    if (popup) popup.style.display = "none";
    setAdminStatus("");
}

function applyIslandTexture(islandIdx, textureName) {
    if (!worldData || !worldData.islands) return;
    const island = worldData.islands[islandIdx];
    if (!island) return;
    pushUndoSnapshot();
    island.texture = textureName;
    adminDirty = true;
    refreshIslandMaterial(islandIdx);
}

function refreshIslandMaterial(islandIdx) {
    if (!worldData || !worldData.islands) return;
    const island = worldData.islands[islandIdx];
    if (!island) return;
    const topMesh = scene.getMeshByName("island_" + islandIdx);
    if (topMesh && topMesh.material && topMesh.material.diffuseTexture) {
        const tex = islandTextureName(island);
        const newTex = new BABYLON.Texture(islandTextureUrl(tex), scene);
        newTex.uScale = 3;
        newTex.vScale = 3;
        const oldTex = topMesh.material.diffuseTexture;
        topMesh.material.diffuseTexture = newTex;
        if (oldTex && typeof oldTex.dispose === "function") oldTex.dispose();
    }
}

function rescaleMap() {
    if (!worldData || !worldData.ground) return;
    const curWkm = (worldData.ground.width / 100).toFixed(1);
    const curDkm = (worldData.ground.depth / 100).toFixed(1);
    const newWkm = parseFloat(prompt(`Nouvelle largeur en km (actuelle: ${curWkm}) :`, curWkm));
    if (isNaN(newWkm) || newWkm <= 0) return;
    const newDkm = parseFloat(prompt(`Nouvelle profondeur en km (actuelle: ${curDkm}) :`, curDkm));
    if (isNaN(newDkm) || newDkm <= 0) return;
    const newW = newWkm * 100;  // km → unités (1u = 10m)
    const newD = newDkm * 100;
    const sx = newW / worldData.ground.width;
    const sz = newD / worldData.ground.depth;
    pushUndoSnapshot();
    worldData.ground.width = newW;
    worldData.ground.depth = newD;
    if (Array.isArray(worldData.islands)) {
        for (const isl of worldData.islands) {
            if (!isl || !Array.isArray(isl.points)) continue;
            for (const p of isl.points) {
                p.x = p.x * sx;
                p.z = p.z * sz;
            }
        }
    }
    // Rebuild
    clearWorld();
    buildWorld(worldData);
    if (adminMode) setupTopDownCamera();
    adminDirty = true;
    setAdminStatus(`Carte redimensionnée à ${newWkm} × ${newDkm} km (facteurs ${sx.toFixed(2)}×${sz.toFixed(2)})`);
}

function cancelAdminEdit() {
    if (adminEditMode === "texture") stopIslandTextureMode();
    adminEditMode = null;
    adminAddingPoints = [];
    clearAddingPreview();
    if (adminGreyedIslandIdx !== null) restoreGreyedIsland();
    adminEditingIslandIdx = null;
    adminEditingPointIdx = null;
    adminMoveIslandIdx = null;
    adminMoveStart = null;
    adminMoveOrigPoints = null;
    setAdminStatus("Annulé");
}

function findIslandAt(x, z) {
    if (!worldData || !worldData.islands) return null;
    for (let i = 0; i < worldData.islands.length; i++) {
        if (pointInPolygon(x, z, worldData.islands[i].points)) return i;
    }
    return null;
}

function findIslandPointAt(x, z) {
    if (!worldData || !worldData.islands) return null;
    const threshold = 5;
    let best = null;
    let bestD2 = threshold * threshold;
    for (let i = 0; i < worldData.islands.length; i++) {
        const isl = worldData.islands[i];
        for (let j = 0; j < isl.points.length; j++) {
            const dx = isl.points[j].x - x;
            const dz = isl.points[j].z - z;
            const d2 = dx * dx + dz * dz;
            if (d2 < bestD2) { bestD2 = d2; best = { island: i, point: j }; }
        }
    }
    return best;
}

function greyIsland(idx) {
    adminGreyedIslandIdx = idx;
    adminGreyedOriginalColor = worldData.islands[idx].color;
    worldData.islands[idx].color = "#888888";
    clearWorld();
    buildWorld(worldData);
}

function restoreGreyedIsland() {
    if (adminGreyedIslandIdx !== null && adminGreyedOriginalColor) {
        worldData.islands[adminGreyedIslandIdx].color = adminGreyedOriginalColor;
        clearWorld();
        buildWorld(worldData);
    }
    adminGreyedIslandIdx = null;
    adminGreyedOriginalColor = null;
}

function confirmDeleteIsland(idx) {
    greyIsland(idx);
    setTimeout(() => {
        const ok = confirm("Supprimer cette île ?");
        if (ok) {
            worldData.islands.splice(idx, 1);
            adminGreyedIslandIdx = null;
            adminGreyedOriginalColor = null;
            pushUndoSnapshot();
            clearWorld();
            buildWorld(worldData);
            setAdminStatus("Île supprimée");
        } else {
            restoreGreyedIsland();
            setAdminStatus("Annulé");
        }
    }, 50);
}

function setupAdminButtons() {
    // Wrapper : tout autre bouton admin annule le mode texture en cours.
    const cancelTextureFirst = (fn) => () => {
        if (adminEditMode === "texture") stopIslandTextureMode();
        fn();
    };
    const bind = (id, fn) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("click", fn);
    };
    bind("admLoad", cancelTextureFirst(() => {
        const name = prompt("Nom de la carte à charger :", "world");
        if (!name) return;
        socket.emit("admin_load_map", { name: name.trim() });
    }));
    bind("admNew", cancelTextureFirst(() => {
        const name = prompt("Nom de la nouvelle carte :");
        if (!name) return;
        const w = parseFloat(prompt("Largeur en km :", "40"));
        if (isNaN(w) || w <= 0) return;
        const d = parseFloat(prompt("Profondeur en km :", "20"));
        if (isNaN(d) || d <= 0) return;
        socket.emit("admin_create_map", { name: name.trim(), widthKm: w, depthKm: d });
    }));
    bind("admAdd", cancelTextureFirst(startAddIsland));
    bind("admDelete", cancelTextureFirst(startDeleteIsland));
    bind("admEdit", cancelTextureFirst(startEditIsland));
    bind("admMove", cancelTextureFirst(startMoveIsland));
    bind("admRescale", cancelTextureFirst(rescaleMap));
    bind("admCopy", cancelTextureFirst(() => {
        const name = prompt("Nouveau nom de la carte (copie) :");
        if (!name) return;
        socket.emit("admin_copy_map", { name: name.trim(), world: worldData });
    }));
    bind("admIslandTexture", () => {
        if (adminEditMode === "texture") {
            stopIslandTextureMode();
        } else {
            startIslandTextureMode();
        }
    });
    bind("admTextureClose", stopIslandTextureMode);
    bind("admAddThermocline", cancelTextureFirst(startAddThermocline));
    bind("admDeleteThermocline", cancelTextureFirst(startDeleteThermocline));
    bind("admSave", cancelTextureFirst(() => {
        socket.emit("admin_save_map", { name: adminCurrentMapName, world: worldData });
    }));
}

socket.on("admin_textures_list", (data) => {
    const textures = (data && data.textures) || [];
    // Mémorise les URLs avant tout rendu de galerie (utile aussi hors mode admin).
    const newlyKnown = [];
    for (const t of textures) {
        if (!islandTextureUrls[t.name]) newlyKnown.push(t.name);
        islandTextureUrls[t.name] = t.url;
    }
    // Si des îles existaient déjà et utilisent des textures qu'on vient
    // d'apprendre, rafraîchit leur matériau 3D pour utiliser la bonne URL
    // (par ex. .gif au lieu du fallback .jpg).
    if (newlyKnown.length > 0 && worldData && worldData.islands) {
        worldData.islands.forEach((island, idx) => {
            const name = islandTextureName(island);
            if (newlyKnown.includes(name)) refreshIslandMaterial(idx);
        });
    }
    // Galerie réservée au mode admin.
    const gallery = document.getElementById("textureGallery");
    if (!gallery) return;
    gallery.innerHTML = "";
    for (const t of textures) {
        const item = document.createElement("div");
        item.style.cssText = "cursor:pointer;border:2px solid transparent;padding:2px;text-align:center;border-radius:4px;";
        item.dataset.name = t.name;
        item.title = t.name;
        item.innerHTML = `<img src="${t.url}" style="width:64px;height:64px;display:block;object-fit:cover;"><div style="font-size:11px;margin-top:2px;">${t.name}</div>`;
        item.addEventListener("click", () => {
            adminTextureSelected = t.name;
            // Ferme le popup pour libérer le clic sur les îles, mais garde le
            // mode texture actif jusqu'à Esc / autre bouton admin.
            const popup = document.getElementById("islandTexturePopup");
            if (popup) popup.style.display = "none";
            setAdminStatus(`Texture ${t.name} : clique sur les îles à modifier. Esc pour annuler.`);
        });
        gallery.appendChild(item);
    }
});

socket.on("admin_world_loaded", (data) => {
    clearWorld();
    worldData = data.world;
    adminCurrentMapName = data.name || "world";
    buildWorld(worldData);
    if (adminMode) setupTopDownCamera();
    adminUndoStack = [JSON.stringify(worldData)];
    adminRedoStack = [];
    adminDirty = false;
    setAdminStatus("Carte chargée: " + adminCurrentMapName);
});

socket.on("admin_save_ok", (data) => {
    setAdminStatus("Sauvegardé: " + (data && data.name));
    adminDirty = false;
    if (adminExitPending) {
        adminExitPending = false;
        exitAdminMode();
    }
});

socket.on("admin_error", (data) => {
    setAdminStatus("Erreur: " + (data && data.message));
    adminExitPending = false;
});

// Sélection par clic dans la scène 3D (clic gauche, hors mode admin/aim).
// Identifie l'entité touchée et la sélectionne comme un clic sur le radar.
function _topMostNamed(node) {
    let n = node;
    while (n) {
        if (n.name) return n;
        if (!n.parent) break;
        n = n.parent;
    }
    return node;
}

function _findAncestorByPredicate(node, pred) {
    let n = node;
    while (n) {
        if (pred(n)) return n;
        n = n.parent;
    }
    return null;
}

function _findOtherPlayerIdFromMesh(node) {
    // Le wrapper d'un bateau distant s'appelle "other_<id>".
    const m = _findAncestorByPredicate(node, (x) => x && x.name && x.name.startsWith("other_"));
    if (m) return m.name.slice(6);
    // Ou bien on est dans le wrapper d'un sub bot pour la vue (rare via pick).
    return null;
}

function _findMineKeyFromMesh(node) {
    // Tous les meshes de mine ont un name commençant par "mine_<key>", ou
    // "mineSpike_<key>_i", ou "mineCable_<key>".
    const m = _findAncestorByPredicate(node, (x) => x && x.name && (
        x.name.startsWith("mine_") || x.name.startsWith("mineSpike_") || x.name.startsWith("mineCable_")));
    if (!m) return null;
    if (m.name.startsWith("mine_")) return m.name.slice(5);
    if (m.name.startsWith("mineCable_")) return m.name.slice("mineCable_".length);
    if (m.name.startsWith("mineSpike_")) {
        const rest = m.name.slice("mineSpike_".length);
        const idx = rest.lastIndexOf("_");
        return idx >= 0 ? rest.slice(0, idx) : rest;
    }
    return null;
}

function _findBeaconBidFromMesh(node) {
    const m = _findAncestorByPredicate(node, (x) => x && x.name && (
        x.name.startsWith("beacon_") || x.name.startsWith("beaconTether_") || x.name.startsWith("beaconHydro_")));
    if (!m) return null;
    const rest = m.name.split("_").pop();
    const bid = parseInt(rest, 10);
    return isNaN(bid) ? null : bid;
}

function _findTorpedoKeyFromMesh(node) {
    // Pas de suffixe dans le name. On recherche par identité de mesh.
    const top = _topMostNamed(node);
    for (const key in remoteTorpedoes) {
        const r = remoteTorpedoes[key];
        if (!r || !r.mesh) continue;
        if (r.mesh === node || r.mesh === top) return key;
    }
    return null;
}

function _findDroneKeyFromMesh(node) {
    const m = _findAncestorByPredicate(node, (x) => x && x.name && (
        x.name === "drone_local" || x.name === "drone_remote"
        || (typeof x.name === "string" && (x.name.startsWith("drone_local") || x.name.startsWith("drone_remote")))));
    if (!m) return null;
    // Identifier par identité du mesh.
    for (const key in remoteDrones) {
        const r = remoteDrones[key];
        if (!r || !r.mesh) continue;
        if (r.mesh === m || r.mesh === node) return { kind: "remote", key };
    }
    for (const d of activeDrones) {
        if (!d || !d.mesh) continue;
        if (d.mesh === m || d.mesh === node) return { kind: "local", did: d.did };
    }
    return null;
}

function selectEntityFromPick(pickInfo) {
    if (!pickInfo || !pickInfo.hit || !pickInfo.pickedMesh) return false;
    const node = pickInfo.pickedMesh;
    // Helper : nettoyer toutes les sélections (mêmes clés que le radar click).
    const clearAll = () => {
        selectedBoatId = null;
        selectedBoatIsSonar = false;
        selectedDroneKey = null;
        selectedBeaconBid = null;
        selectedLocalDroneDid = null;
        selectedTorpedoKey = null;
        selectedMineKey = null;
    };
    // Mines (priorité haute car geometrie petite et discriminante).
    const mineKey = _findMineKeyFromMesh(node);
    if (mineKey && mines[mineKey]) {
        const m = mines[mineKey];
        if (!isMineVisibleOnRadar(m, mineKey)) {
            // Clic 3D sur mine ennemie non encore détectée : on signale au serveur
            // qui la révèle à toute notre team de manière permanente.
            socket.emit("mine_spotted", { ownerId: m.ownerId, mid: m.mid });
            // Optimisation locale : marque immédiatement (le serveur confirmera).
            m.revealedByMyTeam = true;
        }
        clearAll();
        selectedMineKey = mineKey;
        return true;
    }
    // Balises sonar.
    const bid = _findBeaconBidFromMesh(node);
    if (bid != null && sonarBeacons[bid]) {
        clearAll();
        selectedBeaconBid = bid;
        return true;
    }
    // Drones (mes drones locaux ou drones distants).
    const droneInfo = _findDroneKeyFromMesh(node);
    if (droneInfo) {
        clearAll();
        if (droneInfo.kind === "local") selectedLocalDroneDid = droneInfo.did;
        else selectedDroneKey = droneInfo.key;
        return true;
    }
    // Torpilles.
    const torpKey = _findTorpedoKeyFromMesh(node);
    if (torpKey && remoteTorpedoes[torpKey]) {
        clearAll();
        selectedTorpedoKey = "remote:" + torpKey;
        tryResumeWireControl(torpKey);
        return true;
    }
    // Bateau distant (humain ou bot).
    const otherId = _findOtherPlayerIdFromMesh(node);
    if (otherId && otherPlayers[otherId]) {
        clearAll();
        selectedBoatId = otherId;
        const sel = (radarFrozenBoats || []).find(b => b.id === otherId);
        selectedBoatIsSonar = !!(sel && sel.sonar);
        return true;
    }
    return false;
}

canvas.addEventListener("pointerdown", (e) => {
    if (!adminMode || !adminEditMode || e.button !== 0) return;
    const pick = scene.pick(e.clientX, e.clientY);
    if (!pick || !pick.hit || !pick.pickedPoint) return;
    const wx = pick.pickedPoint.x;
    const wz = pick.pickedPoint.z;
    if (adminEditMode === "add") {
        adminAddingPoints.push({ x: wx, z: wz });
        drawAddingPreview();
    } else if (adminEditMode === "thermo_add") {
        adminAddingPoints.push({ x: wx, z: wz });
        drawAddingPreview();
    } else if (adminEditMode === "thermo_delete") {
        const idx = findThermoclineAt(wx, wz);
        if (idx !== null) {
            worldData.thermoclines.splice(idx, 1);
            pushUndoSnapshot();
            clearWorld();
            buildWorld(worldData);
            setAdminStatus("Thermocline supprimée");
        }
    } else if (adminEditMode === "delete") {
        const idx = findIslandAt(wx, wz);
        if (idx !== null) confirmDeleteIsland(idx);
    } else if (adminEditMode === "edit") {
        const found = findIslandPointAt(wx, wz);
        if (found) {
            adminEditingIslandIdx = found.island;
            adminEditingPointIdx = found.point;
        }
    } else if (adminEditMode === "move") {
        const idx = findIslandAt(wx, wz);
        if (idx !== null) {
            adminMoveIslandIdx = idx;
            adminMoveStart = { x: wx, z: wz };
            adminMoveOrigPoints = worldData.islands[idx].points.map(p => ({ x: p.x, z: p.z }));
        }
    } else if (adminEditMode === "texture") {
        if (!adminTextureSelected) {
            setAdminStatus("Choisis d'abord une texture dans le popup.");
            return;
        }
        const idx = findIslandAt(wx, wz);
        if (idx !== null) {
            applyIslandTexture(idx, adminTextureSelected);
            setAdminStatus(`Île ${idx} → ${adminTextureSelected}`);
        }
    }
});

canvas.addEventListener("pointermove", (e) => {
    if (!adminMode) return;
    if (adminEditMode === "edit" && adminEditingPointIdx !== null) {
        const pick = scene.pick(e.clientX, e.clientY);
        if (!pick || !pick.hit || !pick.pickedPoint) return;
        const isl = worldData.islands[adminEditingIslandIdx];
        isl.points[adminEditingPointIdx].x = pick.pickedPoint.x;
        isl.points[adminEditingPointIdx].z = pick.pickedPoint.z;
        clearWorld();
        buildWorld(worldData);
    } else if (adminEditMode === "move" && adminMoveIslandIdx !== null) {
        const pick = scene.pick(e.clientX, e.clientY);
        if (!pick || !pick.hit || !pick.pickedPoint) return;
        const dx = pick.pickedPoint.x - adminMoveStart.x;
        const dz = pick.pickedPoint.z - adminMoveStart.z;
        // Clamp pour rester dans la carte : les points décalés ne doivent pas
        // sortir de [-half_w, half_w] x [-half_d, half_d].
        const halfW = worldData.ground.width / 2;
        const halfD = worldData.ground.depth / 2;
        let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
        for (const p of adminMoveOrigPoints) {
            minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
            minZ = Math.min(minZ, p.z); maxZ = Math.max(maxZ, p.z);
        }
        let clampedDx = dx;
        let clampedDz = dz;
        if (minX + clampedDx < -halfW) clampedDx = -halfW - minX;
        if (maxX + clampedDx >  halfW) clampedDx =  halfW - maxX;
        if (minZ + clampedDz < -halfD) clampedDz = -halfD - minZ;
        if (maxZ + clampedDz >  halfD) clampedDz =  halfD - maxZ;
        const isl = worldData.islands[adminMoveIslandIdx];
        for (let i = 0; i < adminMoveOrigPoints.length; i++) {
            isl.points[i].x = adminMoveOrigPoints[i].x + clampedDx;
            isl.points[i].z = adminMoveOrigPoints[i].z + clampedDz;
        }
        clearWorld();
        buildWorld(worldData);
    }
});

canvas.addEventListener("pointerup", () => {
    if (!adminMode) return;
    if (adminEditMode === "edit" && adminEditingPointIdx !== null) {
        pushUndoSnapshot();
        adminEditingIslandIdx = null;
        adminEditingPointIdx = null;
    } else if (adminEditMode === "move" && adminMoveIslandIdx !== null) {
        pushUndoSnapshot();
        adminMoveIslandIdx = null;
        adminMoveStart = null;
        adminMoveOrigPoints = null;
    }
});

// --- Fonctions tooltip partagées (hover + mode visu) ---
function buildBoatTooltipText(id) {
    const info = otherPlayersInfo[id];
    const hist = otherPlayersHistory[id];
    const selMesh = otherPlayers[id];
    if (!selMesh) return null;
    const posX = selMesh.position.x;
    const posZ = selMesh.position.z;
    const posY = selMesh.position.y;
    const t = info && info.boatType;
    const typeLabel = t === "submarine" ? "Sous-marin" : t === "destroyer" ? "Destroyer" : "Bateau";
    const ddx = posX - playerMesh.position.x;
    const ddz = posZ - playerMesh.position.z;
    const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
    const integrity = hist && typeof hist.integrity === "number" ? Math.max(0, Math.round(hist.integrity)) : null;
    const head = integrity != null ? typeLabel + " (" + integrity + "%)" : typeLabel;
    const lines = [head, "Dist: " + distKm + " km"];
    if (t === "submarine" && typeof posY === "number") {
        lines.push("Prof: " + Math.round(-posY * UNIT_METERS) + " m");
    }
    if (info && hist && typeof hist.speedRatio === "number") {
        const knots = hist.speedRatio * info.maxSpeedKnots;
        const dirLabel = hist.reverse ? " (arrière)" : "";
        lines.push("Vit: " + knots.toFixed(0) + " nds" + dirLabel);
    }
    return lines.join("\n");
}
function buildDroneTooltipText(droneInfo) {
    if (droneInfo.kind === "local") {
        const d = activeDrones.find(x => x.did === droneInfo.did);
        if (!d) return null;
        const ddx = d.x - playerMesh.position.x;
        const ddz = d.z - playerMesh.position.z;
        const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
        const altM = Math.round((d.y || 0) * UNIT_METERS);
        const kindLabel = d.kind === "manual" ? "Drone manuel" : "Drone auto";
        const stateLabel = d.returning ? "retour" : "actif";
        return kindLabel + " (" + stateLabel + ")\nDist: " + distKm + " km\nAlt: " + altM + " m";
    } else {
        const r = remoteDrones[droneInfo.key];
        if (!r) return null;
        const ddx = r.x - playerMesh.position.x;
        const ddz = r.z - playerMesh.position.z;
        const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
        const altM = Math.round((r.y || 0) * UNIT_METERS);
        return "Drone\nDist: " + distKm + " km\nAlt: " + altM + " m";
    }
}
function buildTorpedoTooltipText(tkey) {
    const r = remoteTorpedoes[tkey];
    if (!r) return null;
    if (!allMapMode && r.ownerId !== playerId && !isLineOfSightClear(r.x, r.z, null)) return null;
    const ddx = r.x - playerMesh.position.x;
    const ddz = r.z - playerMesh.position.z;
    const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
    const isMine = r.ownerId === playerId;
    let isAlly = false;
    if (!isMine) {
        const oinfo = otherPlayersInfo[r.ownerId];
        isAlly = !!(localTeamId && oinfo && oinfo.teamId === localTeamId);
    }
    const sideLabel = isMine ? "amie" : (isAlly ? "alliée" : "ennemie");
    const showKind = isMine || isAlly || allMapMode;
    const kindLabel = r.kind === "acoustic" ? "Torpille acoustique"
        : r.kind === "wireGuided" ? "Torpille filoguidée"
        : r.kind === "autonomous" ? "Torpille autonome"
        : "Torpille";
    const headLabel = showKind
        ? kindLabel + " (" + sideLabel + ")"
        : "Torpille (" + sideLabel + ")";
    const acquired = (typeof r.tx === "number") && (typeof r.tz === "number");
    const acqLabel = acquired ? "en acquisition" : "non activée";
    const lines = [headLabel, "État: " + acqLabel, "Dist: " + distKm + " km"];
    if (acquired) {
        const tdx = r.tx - r.x;
        const tdz = r.tz - r.z;
        const tdy = (typeof r.ty === "number" ? (r.ty - (r.y || 0)) : 0);
        const distTargetKm = (Math.sqrt(tdx * tdx + tdy * tdy + tdz * tdz) * UNIT_METERS / 1000).toFixed(2);
        lines.push("Dist cible: " + distTargetKm + " km");
    }
    if (typeof r.y === "number") {
        const depthM = Math.max(0, Math.round(-r.y * UNIT_METERS));
        lines.push("Prof: -" + depthM + " m");
    }
    return lines.join("\n");
}
function buildMineTooltipText(mineKey) {
    const m = mines[mineKey];
    if (!m) return null;
    if (!isMineVisibleOnRadar(m, mineKey)) return null;
    const ddx = m.x - playerMesh.position.x;
    const ddz = m.z - playerMesh.position.z;
    const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
    const kindLabel = m.kind === "surface" ? "Mine surface"
        : m.kind === "bottom" ? "Mine de fond"
        : m.kind === "suspended" ? "Mine suspendue"
        : "Mine";
    const depthM = Math.max(0, Math.round(-m.y * UNIT_METERS));
    const armed = m.armed ? "armée" : "en armement";
    const lines = [kindLabel + " (" + armed + ")",
        "Dist: " + distKm + " km",
        "Prof: -" + depthM + " m",
        "Range: " + Math.round(m.range || 0) + " m"];
    return lines.join("\n");
}
function buildBeaconTooltipText(bid) {
    const b = sonarBeacons[bid];
    if (!b) return null;
    const ddx = b.x - playerMesh.position.x;
    const ddz = b.z - playerMesh.position.z;
    const distKm = (Math.sqrt(ddx * ddx + ddz * ddz) * UNIT_METERS / 1000).toFixed(1);
    return "Balise sonar\nDist: " + distKm + " km";
}


// --- Mode visu : labels permanents au-dessus des entités visibles ---
// NB : updateVisuLabels() est appelé depuis la boucle de rendu (après
// createScene()), pas au chargement du script — sinon `scene` est undefined.
const _visuLabels = [];
let _visuContainer = null;
function _getVisuLabel(idx) {
    if (!_visuContainer) {
        _visuContainer = document.createElement("div");
        _visuContainer.id = "visuLabelsContainer";
        _visuContainer.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:40;overflow:hidden;";
        document.body.appendChild(_visuContainer);
        document.addEventListener("click", (e) => {
            const el = e.target.closest("#visuLabelsContainer [data-entity-id]");
            if (!el) return;
            const id = el.dataset.entityId;
            const type = el.dataset.entityType;
            // Sélection identique au clic radar.
            selectedBoatId = null;
            selectedBoatIsSonar = false;
            selectedDroneKey = null;
            selectedBeaconBid = null;
            selectedLocalDroneDid = null;
            selectedTorpedoKey = null;
            selectedMineKey = null;
            if (type === "boat") {
                selectedBoatId = id;
                const sel = (radarFrozenBoats || []).find(b => b.id === id);
                selectedBoatIsSonar = !!(sel && sel.sonar);
            } else if (type === "torpedo") {
                selectedTorpedoKey = "remote:" + id;
                tryResumeWireControl(id);
            }
        });
    }
    while (_visuLabels.length <= idx) {
        const el = document.createElement("div");
        el.style.cssText = "position:absolute;background:rgba(0,0,0,0.8);color:#0f0;padding:3px 6px;border:1px solid #0f0;border-radius:4px;font-family:monospace;font-size:10px;line-height:1.3;white-space:pre;text-align:center;transform:translate(-50%,-100%);pointer-events:auto;cursor:pointer;display:none;";
        _visuContainer.appendChild(el);
        _visuLabels.push(el);
    }
    return _visuLabels[idx];
}
function _visuWorldToScreen(pos) {
    const cam = scene.activeCamera;
    if (!cam) return null;
    const projected = BABYLON.Vector3.Project(
        pos, BABYLON.Matrix.Identity(), scene.getTransformMatrix(),
        cam.viewport.toGlobal(engine.getRenderWidth(), engine.getRenderHeight()));
    if (projected.z < 0 || projected.z > 1) return null;
    return { x: projected.x, y: projected.y };
}
// Occlusion visuelle réelle : un rayon caméra → cible touche-t-il une île
// AVANT la cible ? Sert à masquer le label d'un bateau caché derrière une île
// dans la vue 3D (la LOS 2D horizontale ne suffit pas).
function _visuOccludedByIsland(targetPos) {
    const cam = scene.activeCamera;
    if (!cam) return false;
    const camPos = cam.globalPosition || cam.position;
    const dir = targetPos.subtract(camPos);
    const targetDist = dir.length();
    if (targetDist < 0.01) return false;
    dir.normalize();
    const ray = new BABYLON.Ray(camPos, dir, targetDist - 1.0);
    const hit = scene.pickWithRay(ray, (m) => {
        const n = m && m.name ? m.name : "";
        return n.startsWith("island_") || n.startsWith("islandWall_")
            || n.startsWith("islandTop_") || n.startsWith("islandUnder_");
    });
    return !!(hit && hit.hit);
}
function updateVisuLabels() {
    if (!scene || !playerMesh) return;
    let idx = 0;
    // Labels BATEAUX : toujours actifs (pas de cheat requis).
    // Visibilité 3D directe.
    // - Mon sub immergé : je vois tous les bateaux (LOS clear). Un destroyer de
    //   surface est masqué par le clip plane (y>0), donc on place son label SOUS
    //   lui (point projeté sous la ligne d'eau) pour qu'il reste visible.
    // - Moi en surface : je ne vois QUE les bateaux de surface ; les subs
    //   immergés sont invisibles → pas de label.
    const iAmSubmerged = (currentBoatType === "submarine" && playerMesh.position.y < PERISCOPE_DEPTH) || zoomLowMode;
    for (const id in otherPlayers) {
        const mesh = otherPlayers[id];
        if (!mesh) continue;
        // Le label ne s'affiche QUE si le bateau lui-même est visible (mesh
        // activé) : englobe tout le masquage déjà calculé (profondeur, clip
        // plane, thermoclines). Un bateau masqué → pas de label.
        if (!mesh.isEnabled()) continue;
        const hist = otherPlayersHistory[id];
        const otherSubmerged = hist ? !!hist.submerged : (mesh.position.y < PERISCOPE_DEPTH + 0.05);
        // En surface, on ne voit pas les subs immergés.
        if (!iAmSubmerged && otherSubmerged) continue;
        // Ligne de vue dégagée (îles) — filtre rapide horizontal.
        if (!isLineOfSightClear(mesh.position.x, mesh.position.z, null)) continue;
        const text = buildBoatTooltipText(id);
        if (!text) continue;
        // Point d'ancrage du label : pour un bateau de surface vu depuis un sub
        // immergé, on descend sous la surface (clip plane), sinon position réelle.
        const anchor = mesh.position.clone();
        if (iAmSubmerged && !otherSubmerged) {
            anchor.y = -metersToUnits(3);
        }
        // Occlusion caméra : masque le label si une île est entre la caméra et
        // le bateau (la LOS 2D ne capte pas l'occlusion en 3D selon l'angle).
        if (_visuOccludedByIsland(anchor)) continue;
        const sp = _visuWorldToScreen(anchor);
        if (!sp) continue;
        const el = _getVisuLabel(idx++);
        el.textContent = text;
        el.dataset.entityId = id;
        el.dataset.entityType = "boat";
        el.style.background = "rgba(0,0,0,0.8)";
        el.style.borderColor = "#0f0";
        el.style.display = "block";
        // Centré horizontalement, au-dessus de l'ancre (transform translate -50%,-100%).
        el.style.left = sp.x + "px";
        el.style.top = (sp.y - 12) + "px";
    }
    // Labels TORPILLES : toujours affichés. Mode visu off → état acquisition +
    // distance cible, fond coloré par type. Mode visu on → texte complet.
    for (const key in remoteTorpedoes) {
        const r = remoteTorpedoes[key];
        if (!r || !r.mesh) continue;
        // Label seulement si la torpille est visible (masquée par thermocline → pas de label).
        if (!r.mesh.isEnabled()) continue;
        if (r.ownerId !== playerId) {
            if (!isLineOfSightClear(r.x, r.z, null)) continue;
        }
        let text;
        let bgColor = null;
        if (cheatVisuMode) {
            text = buildTorpedoTooltipText(key);
        } else {
            const acquired = (typeof r.tx === "number") && (typeof r.tz === "number");
            if (acquired) {
                const tdx = r.tx - r.x;
                const tdz = r.tz - r.z;
                const tdy = (typeof r.ty === "number" ? (r.ty - (r.y || 0)) : 0);
                const distM = Math.round(Math.sqrt(tdx * tdx + tdy * tdy + tdz * tdz) * UNIT_METERS);
                text = "Acquisition: " + distM + " m";
            } else {
                text = "Non activée";
            }
        }
        // Couleur de fond selon le type de torpille.
        if (r.kind === "acoustic") bgColor = "rgba(30, 80, 180, 0.85)";
        else if (r.kind === "autonomous") bgColor = "rgba(200, 120, 0, 0.85)";
        else if (r.kind === "wireGuided") bgColor = "rgba(180, 30, 30, 0.85)";
        if (!text) continue;
        // Occlusion caméra : masquer si une île est entre la caméra et la torpille.
        if (_visuOccludedByIsland(r.mesh.position)) continue;
        const sp = _visuWorldToScreen(r.mesh.position);
        if (!sp) continue;
        const el = _getVisuLabel(idx++);
        el.textContent = text;
        el.dataset.entityId = key;
        el.dataset.entityType = "torpedo";
        el.style.display = "block";
        el.style.left = sp.x + "px";
        el.style.top = (sp.y - 12) + "px";
        if (bgColor) el.style.background = bgColor;
        else el.style.background = "rgba(0,0,0,0.8)";
        // Bordure : vert si amie, rouge si ennemie.
        const isMine = r.ownerId === playerId;
        let torpIsAlly = false;
        if (!isMine) {
            const oinfo = otherPlayersInfo[r.ownerId];
            torpIsAlly = !!(localTeamId && oinfo && oinfo.teamId === localTeamId);
        }
        el.style.borderColor = (isMine || torpIsAlly) ? "#0f0" : "#f00";
    }
    // Masquer les labels en excès et nettoyer leur dataset.
    for (let i = idx; i < _visuLabels.length; i++) {
        _visuLabels[i].style.display = "none";
        delete _visuLabels[i].dataset.entityId;
        delete _visuLabels[i].dataset.entityType;
    }
}

// Sélection 3D au clic (hors mode admin et hors aim torpille).
let _sceneClickStart = null;
canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    if (adminMode) return;
    _sceneClickStart = { x: e.clientX, y: e.clientY, t: performance.now() };
}, true);
canvas.addEventListener("pointerup", (e) => {
    if (e.button !== 0) return;
    if (!_sceneClickStart) return;
    const start = _sceneClickStart;
    _sceneClickStart = null;
    if (adminMode) return;
    if (aimingTorpedoKind) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const dt = performance.now() - start.t;
    if (dist > 6 || dt > 500) return;
    if (grenadeAiming) {
        if (zoomMode && scene.activeCamera) scene.activeCamera.getViewMatrix(true);
        const gPick = scene.pick(e.clientX, e.clientY);
        if (gPick && gPick.hit && gPick.pickedPoint) {
            fireGrenadeAtWorldPos(gPick.pickedPoint.x, gPick.pickedPoint.z);
            cancelGrenadeAiming();
        }
        return;
    }
    const submerged = (currentBoatType === "submarine" && playerMesh && playerMesh.position.y < PERISCOPE_DEPTH) || zoomLowMode;
    if (zoomMode && scene.activeCamera) scene.activeCamera.getViewMatrix(true);
    const pick = scene.pick(e.clientX, e.clientY, (m) => {
        if (!m.isPickable) return false;
        if (submerged) {
            let n = m;
            while (n) {
                const name = n.name || "";
                if (name.startsWith("other_") || name.startsWith("mine_") ||
                    name.startsWith("beacon_") || name.startsWith("drone_") ||
                    name.startsWith("torpedo_")) return true;
                n = n.parent;
            }
            return false;
        }
        return true;
    });
    selectEntityFromPick(pick);
}, true);

window.addEventListener("keydown", (e) => {
    if (!adminMode) return;
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if (e.key === "Enter" && adminEditMode === "add") {
        e.preventDefault();
        finishAddIsland();
    } else if (e.key === "Enter" && adminEditMode === "thermo_add") {
        e.preventDefault();
        finishAddThermocline();
    } else if (e.key === "Escape") {
        cancelAdminEdit();
    } else if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z") && !e.shiftKey) {
        e.preventDefault();
        adminUndo();
    } else if ((e.ctrlKey || e.metaKey) && (e.key === "y" || e.key === "Y" || (e.shiftKey && (e.key === "z" || e.key === "Z")))) {
        e.preventDefault();
        adminRedo();
    }
});

setupAdminButtons();

createScene();

engine.runRenderLoop(() => {
    if (fpsOverlayEl) fpsRecordDt(performance.now());
    if (!localBoat || !localBoat.mesh || !initialized) {
        if (dayCycleState !== "off") updateDayCycle(engine.getDeltaTime() / 1000);
        scene.render();
        return;
    }
    // Synchroniser playerMesh sur le bateau actuellement observé (localBoat ou bot).
    playerMesh = (viewedBoat && viewedBoat.mesh) ? viewedBoat.mesh : localBoat.mesh;
    // En vue bot, playerRotation reflète le bot.
    if (!isViewingLocal() && viewedBoat && viewedBoat.mesh) {
        playerRotation = viewedBoat.mesh.rotation.y;
    }

    // Cap dt à 100ms : au retour de focus après un onglet masqué, getDeltaTime()
    // peut renvoyer plusieurs secondes. Sans cap, les pas de physique sont énormes
    // et la condition "boatSpeed < throttleStep × 2" se déclenche, arrêtant le bateau.
    const dt = Math.min(0.1, engine.getDeltaTime() / 1000);
    smoothRemotePlayers(dt);
    animateSecondarySinking(dt);

    if (isSinking) {
        boatSpeed = 0;
        rudderAngle = 0;
        diveRate = 0;
        const SINK_RATE = 0.25;
        const TILT_MAX = Math.PI / 18;
        // Toujours appliquer le naufrage au mesh local, quel que soit la vue.
        const lm = localBoat.mesh;
        lm.position.y -= SINK_RATE * dt;
        sinkTilt = Math.min(TILT_MAX, sinkTilt + (TILT_MAX / 8) * dt);
        const localRot = isViewingLocal() ? playerRotation : (localBoat.mesh.rotation.y || 0);
        const yawQ = BABYLON.Quaternion.RotationAxis(BABYLON.Axis.Y, localRot);
        const pitchQ = BABYLON.Quaternion.RotationAxis(BABYLON.Axis.Z, sinkTilt * sinkTiltAxis);
        lm.rotationQuaternion = yawQ.multiply(pitchQ);
        if (lm.position.y < -8) {
            lm.setEnabled(false);
        }
        const cam = scene.activeCamera;
        if (cam && cam.target) {
            const tm = (viewedBoat && viewedBoat.mesh) ? viewedBoat.mesh : lm;
            cam.target = new BABYLON.Vector3(tm.position.x, 0, tm.position.z);
        }
        const nowMove = performance.now();
        if (nowMove - lastMoveEmit >= MOVE_EMIT_INTERVAL) {
            lastMoveEmit = nowMove;
            socket.emit("move", withBsid({
                position: { x: lm.position.x, y: lm.position.y, z: lm.position.z },
                rotation: localBoat.mesh.rotation.y || 0,
                _ts: Date.now() / 1000,
            }));
        }
        const integrityEl = document.getElementById("integrityDisplay");
        if (integrityEl) integrityEl.textContent = "Intégrité: 0%";
        updateGrenades(dt);
        updateTorpedoes(dt);
        updateAcousticLures();
        scene.render();
        return;
    }

    // Intégrité, regen, danger zone : tout côté serveur. Le client se contente
    // d'afficher la dernière valeur reçue via l'event `integrity`.
    const nowMs = performance.now();
    const integrityEl = document.getElementById("integrityDisplay");
    if (integrityEl) integrityEl.textContent = "Intégrité: " + boatIntegrity.toFixed(0) + "%";
    const overlay = document.getElementById("damageOverlay");
    if (overlay) {
        if (nowMs < damageFlashUntil) {
            const t = (damageFlashUntil - nowMs) / 700;
            const pulse = 0.4 + 0.6 * Math.abs(Math.sin(nowMs / 80));
            overlay.style.display = "block";
            overlay.style.opacity = (t * pulse).toFixed(2);
        } else {
            overlay.style.display = "none";
        }
    }

    const ctrlBoat = !manualDroneControl && !activeWireTorpedoKey && isViewingLocal();
    // En vue bot, figer vitesse et rudder — pas de décélération ni retour rudder.
    if (!isViewingLocal()) {
        // Ne rien toucher à boatSpeed / rudderAngle (figés sur dernière valeur).
    } else if (ctrlBoat && keys["ArrowLeft"] && !keys["Control"] && !keys["Shift"]) {
        rudderAngle = Math.max(-RUDDER_MAX, rudderAngle - RUDDER_SPEED / clientSimMultiplier);
    } else if (ctrlBoat && keys["ArrowRight"] && !keys["Control"] && !keys["Shift"]) {
        rudderAngle = Math.min(RUDDER_MAX, rudderAngle + RUDDER_SPEED / clientSimMultiplier);
    } else {
        const RUDDER_RETURN = RUDDER_SPEED * 0.5;
        if (Math.abs(rudderAngle) < RUDDER_RETURN * 2) {
            rudderAngle = 0;
        } else {
            rudderAngle -= Math.sign(rudderAngle) * RUDDER_RETURN;
        }
    }

    const throttleStep = THROTTLE_ACCEL * dt;
    if (!isViewingLocal()) {
        // Vitesse figée en vue bot.
    } else if (ctrlBoat && keys["ArrowUp"] && !keys["Control"] && !keys["Shift"]) {
        autoDecelerate = false;
        boatSpeed = Math.min(maxSpeed, boatSpeed + throttleStep);
    } else if (ctrlBoat && keys["ArrowDown"] && !keys["Control"] && !keys["Shift"]) {
        autoDecelerate = false;
        boatSpeed = Math.max(-reverseMaxSpeed, boatSpeed - throttleStep);
    } else if (autoDecelerate) {
        if (Math.abs(boatSpeed) < throttleStep * 2) {
            boatSpeed = 0;
            autoDecelerate = false;
        } else {
            boatSpeed -= Math.sign(boatSpeed) * throttleStep;
        }
    } else if (ctrlBoat && Math.abs(boatSpeed) < throttleStep * 2) {
        boatSpeed = 0;
    }

    if (currentBoatType === "submarine") {
        const PERISCOPE_RATE_FIXED = DIVE_MAX * 0.6;
        if (ctrlBoat && (keys["x"] || keys["X"])) {
            periscopeTarget = null;
            diveRate = -PERISCOPE_RATE_FIXED;
        } else if (ctrlBoat && keys[" "]) {
            periscopeTarget = null;
            diveRate = PERISCOPE_RATE_FIXED;
        } else {
            diveRate = 0;
        }
        // Le pilotage de la plongée n'agit que sur localBoat. En vue bot, le mesh local n'est plus piloté.
        if (isViewingLocal()) {
            const lm = localBoat.mesh;
            const yBefore = lm.position.y;
            if (periscopeTarget !== null) {
                const dy = periscopeTarget - lm.position.y;
                const PERISCOPE_RATE = DIVE_MAX * 0.6;
                if (Math.abs(dy) < PERISCOPE_RATE) {
                    lm.position.y = periscopeTarget;
                    periscopeTarget = null;
                } else {
                    lm.position.y += Math.sign(dy) * PERISCOPE_RATE;
                }
                diveRate = 0;
            } else {
                lm.position.y = Math.max(SEABED_FLOOR_Y, Math.min(boatFlotationY, lm.position.y + diveRate));
            }
            // Profondeur excessive : dégâts arbitrés par le serveur.
            const yDelta = lm.position.y - yBefore;
            const targetPitch = yDelta < -0.001 ? Math.PI / 18 : (yDelta > 0.001 ? -Math.PI / 18 : 0);
            if (typeof lm.subPitch !== "number") lm.subPitch = 0;
            lm.subPitch += (targetPitch - lm.subPitch) * Math.min(1, dt * 4);
        }
        // L'effet de plongée (clipPlane, visibilité océan) dépend du bateau OBSERVÉ
        // ou du zoom bas (destroyer regarde sous l'eau).
        const submerged = playerMesh.position.y < PERISCOPE_DEPTH || zoomLowMode;
        if (submerged && !lastSubSubmerged) cameraBeta = Math.PI / 2 - 0.0785;
        else if (!submerged && lastSubSubmerged) cameraBeta = 1.3;
        lastSubSubmerged = submerged;
        if (oceanMesh) oceanMesh.isVisible = !submerged;
        if (seabedMesh) seabedMesh.isVisible = submerged;
        if (gridMesh && submerged) gridMesh.isVisible = false;
        if (submerged) {
            scene.clearColor = new BABYLON.Color3(0.05, 0.15, 0.3);
            scene.clipPlane = new BABYLON.Plane(0, 1, 0, 0);
            scene.__frameClipPlane = scene.clipPlane;
            if (clearWater) {
                scene.fogMode = BABYLON.Scene.FOGMODE_NONE;
            } else if (mediumWater) {
                scene.fogMode = BABYLON.Scene.FOGMODE_EXP2;
                scene.fogDensity = 0.01;
                scene.fogColor = new BABYLON.Color3(0.05, 0.15, 0.3);
            } else {
                scene.fogMode = BABYLON.Scene.FOGMODE_EXP2;
                scene.fogDensity = 0.05;
                scene.fogColor = new BABYLON.Color3(0.05, 0.15, 0.3);
            }
        } else {
            scene.clearColor = new BABYLON.Color3(0.5, 0.7, 0.9);
            scene.fogMode = BABYLON.Scene.FOGMODE_NONE;
            scene.clipPlane = null;
            scene.__frameClipPlane = null;
        }
    } else if (zoomLowMode) {
        if (oceanMesh) oceanMesh.isVisible = false;
        if (seabedMesh) seabedMesh.isVisible = true;
        if (gridMesh) gridMesh.isVisible = false;
        scene.clearColor = new BABYLON.Color3(0.05, 0.15, 0.3);
        scene.clipPlane = new BABYLON.Plane(0, 1, 0, 0);
        scene.__frameClipPlane = scene.clipPlane;
        if (clearWater) {
            scene.fogMode = BABYLON.Scene.FOGMODE_NONE;
        } else if (mediumWater) {
            scene.fogMode = BABYLON.Scene.FOGMODE_EXP2;
            scene.fogDensity = 0.01;
            scene.fogColor = new BABYLON.Color3(0.05, 0.15, 0.3);
        } else {
            scene.fogMode = BABYLON.Scene.FOGMODE_EXP2;
            scene.fogDensity = 0.05;
            scene.fogColor = new BABYLON.Color3(0.05, 0.15, 0.3);
        }
        lastSubSubmerged = true;
    } else {
        if (lastSubSubmerged) {
            if (oceanMesh) oceanMesh.isVisible = true;
            if (seabedMesh) seabedMesh.isVisible = false;
            scene.clearColor = new BABYLON.Color3(0.5, 0.7, 0.9);
            scene.fogMode = BABYLON.Scene.FOGMODE_NONE;
            lastSubSubmerged = false;
        }
        scene.clipPlane = null;
        scene.__frameClipPlane = null;
    }

    // Visibilité des sub adverses sous l'eau : ils sont normalement masqués
    // pour cacher leur position au joueur en surface (le clipPlane masque déjà
    // tout y>0 quand on plonge). Quand on est soi-même immergé, on doit les voir.
    const selfMesh = (viewedBoat && viewedBoat.mesh) ? viewedBoat.mesh : (localBoat && localBoat.mesh);
    const selfSubmerged = !!(selfMesh && selfMesh.position.y < PERISCOPE_DEPTH) || zoomLowMode;
    for (const id in otherPlayers) {
        const op = otherPlayers[id];
        const hist = otherPlayersHistory[id];
        const otherSubmerged = hist ? !!hist.submerged : (op.position.y < -0.7);
        const isViewed = !isViewingLocal() && viewedBoat && viewedBoat.id === id;
        let visible = !otherSubmerged || isViewed || selfSubmerged;
        if (visible && !isViewed && selfMesh) {
            const oqx = (typeof op.targetX === "number") ? op.targetX : op.position.x;
            const oqy = (typeof op.targetY === "number") ? op.targetY : op.position.y;
            const oqz = (typeof op.targetZ === "number") ? op.targetZ : op.position.z;
            if (countThermoclinesCrossed(selfMesh.position.x, selfMesh.position.y, selfMesh.position.z,
                                         oqx, oqy, oqz) > 0) {
                visible = false;
            }
        }
        op.setEnabled(visible);
    }

    if (isViewingLocal()) {
        const physDt = dt * clientSimMultiplier;
        const speedRatio = maxSpeed > 0 ? Math.min(1, Math.abs(boatSpeed) / (maxSpeed * 0.5)) : 0;
        // Plancher de manœuvrabilité : même à l'arrêt, la barre fait tourner le bateau
        // comme s'il avançait à 10% de sa vitesse max (jouabilité).
        const turnRatio = Math.max(speedRatio, 0.6);
        const turnSign = boatSpeed >= 0 ? 1 : -1;
        playerRotation += rudderAngle * turnRatio * turnSign * clientSimMultiplier;
        const nextX = playerMesh.position.x - Math.cos(playerRotation) * boatSpeed * physDt;
        const nextZ = playerMesh.position.z + Math.sin(playerRotation) * boatSpeed * physDt;
        // Bord du monde : marge 40 m (4 u), on accepte le mouvement seulement
        // s'il rapproche du centre quand on est au-delà de la marge.
        const EDGE_MARGIN_U = 4.0;
        let blockedByEdge = false;
        if (worldData && worldData.ground) {
            const hw = worldData.ground.width / 2 - EDGE_MARGIN_U;
            const hd = worldData.ground.depth / 2 - EDGE_MARGIN_U;
            const curX = playerMesh.position.x;
            const curZ = playerMesh.position.z;
            const xOk = (nextX >= -hw && nextX <= hw) || Math.abs(nextX) < Math.abs(curX);
            const zOk = (nextZ >= -hd && nextZ <= hd) || Math.abs(nextZ) < Math.abs(curZ);
            if (!xOk || !zOk) blockedByEdge = true;
        }
        if (blockedByEdge || isPositionBlocked(nextX, nextZ, playerRotation)) {
            boatSpeed = 0;
        } else {
            playerMesh.position.x = nextX;
            playerMesh.position.z = nextZ;
        }
        if (currentBoatType === "submarine" && typeof playerMesh.subPitch === "number" && Math.abs(playerMesh.subPitch) > 0.001) {
            const yawQ = BABYLON.Quaternion.RotationAxis(BABYLON.Axis.Y, playerRotation);
            const pitchQ = BABYLON.Quaternion.RotationAxis(BABYLON.Axis.Z, playerMesh.subPitch);
            playerMesh.rotationQuaternion = yawQ.multiply(pitchQ);
        } else {
            playerMesh.rotationQuaternion = null;
            playerMesh.rotation.y = playerRotation;
        }
        if (localBoat) localBoat.boatSpeed = boatSpeed;
    } else if (viewedBoat && viewedBoat.mesh) {
        // Vue bot : le serveur autopilote le destroyer (via player_moved + lissage).
        // On ne fait que suivre le bot avec la caméra.
        playerRotation = viewedBoat.mesh.rotation.y;
    }

    const now = performance.now();
    if (isViewingLocal() && Math.abs(boatSpeed) > 0.0001 && now - lastWakeTime > WAKE_INTERVAL) {
        const lm = localBoat.mesh;
        const lrot = lm.rotation.y || playerRotation;
        const isSurface = lm.position.y >= -0.4;
        const isSubmerged = currentBoatType === "submarine" && lm.position.y < -0.4;
        if (isSurface || isSubmerged) {
            lastWakeTime = now;
            const sternOffset = boatHalfLength;
            const sternX = lm.position.x + Math.cos(lrot) * sternOffset * Math.sign(boatSpeed);
            const sternZ = lm.position.z - Math.sin(lrot) * sternOffset * Math.sign(boatSpeed);
            const opts = isSubmerged
                ? { radius: 0.12, y: lm.position.y + 0.05, alpha: 0.25 }
                : undefined;
            spawnWakeDot(sternX, sternZ, now, opts);
            socket.emit("wake", { x: sternX, z: sternZ, submerged: isSubmerged, y: lm.position.y });
        }
    }
    // Wake locale pour TOUS les bateaux distants (autres joueurs, bots, mes
    // bateaux secondaires autopilotés). Le serveur n'émet pas de wake — chaque
    // client génère sa propre traînée à partir des positions interpolées et
    // des dernières vitesses connues. Évite de saturer le réseau à 20+ Hz.
    for (const id in otherPlayers) {
        if (selfControlledPlayerIds.has(id)) continue; // bateau actif local
        const m = otherPlayers[id];
        if (!m) continue;
        if (remoteSinking[id]) continue;
        // Sillage uniquement pour les bateaux RÉELLEMENT VISIBLES à l'écran
        // (mesh activé) : inutile de générer des meshes pour un bateau masqué
        // (immergé) ou hors de portée visuelle.
        if (!m.isEnabled()) continue;
        if (playerMesh) {
            const ddx = m.position.x - playerMesh.position.x;
            const ddz = m.position.z - playerMesh.position.z;
            if (ddx * ddx + ddz * ddz > WAKE_REMOTE_MAX_DIST_U * WAKE_REMOTE_MAX_DIST_U) continue;
        }
        const hist = otherPlayersHistory[id];
        if (!hist) continue;
        const sr = Math.abs(hist.speedRatio || 0);
        if (sr < 0.02) continue;
        const lastT = m._lastWakeTime || 0;
        if (now - lastT < WAKE_INTERVAL_REMOTE) continue;
        m._lastWakeTime = now;
        const info = otherPlayersInfo[id] || {};
        const halfM = ((info.lengthMeters) || 100) * 0.5;
        const halfU = halfM / UNIT_METERS;
        const rot = m.rotation.y || 0;
        const dirSign = hist.reverse ? -1 : 1;
        const sternX = m.position.x + Math.cos(rot) * halfU * dirSign;
        const sternZ = m.position.z - Math.sin(rot) * halfU * dirSign;
        const isSubmerged = m.position.y < -0.4;
        const opts = isSubmerged
            ? { radius: 0.12, y: m.position.y + 0.05, alpha: 0.25 }
            : undefined;
        spawnWakeDot(sternX, sternZ, now, opts);
    }
    // Le bateau primaire en autopilote (pas dans otherPlayers : son mesh est
    // localBoat.mesh). On le traite séparément.
    for (const entry of localBoats) {
        if (!entry || entry.sunk) continue;
        if (entry.ghostSid) continue; // secondaires sont dans otherPlayers
        if (selfControlledPlayerIds.has(entry.playerId)) continue;
        const m = entry.boat && entry.boat.mesh;
        if (!m) continue;
        if (!m.isEnabled()) continue;
        const slot = boatAmmo["primary"] || {};
        const sr = Math.abs(slot.lastServerSpeedRatio || 0);
        const reverse = !!slot.lastServerReverse;
        if (sr < 0.02) continue;
        const lastT = m._lastWakeTime || 0;
        if (now - lastT < WAKE_INTERVAL_REMOTE) continue;
        m._lastWakeTime = now;
        const halfM = ((slot.boat && slot.boat.lengthMeters) || 100) * 0.5;
        const halfU = halfM / UNIT_METERS;
        const rot = m.rotation.y || 0;
        const dirSign = reverse ? -1 : 1;
        const sternX = m.position.x + Math.cos(rot) * halfU * dirSign;
        const sternZ = m.position.z - Math.sin(rot) * halfU * dirSign;
        const isSubmerged = m.position.y < -0.4;
        const opts = isSubmerged
            ? { radius: 0.12, y: m.position.y + 0.05, alpha: 0.25 }
            : undefined;
        spawnWakeDot(sternX, sternZ, now, opts);
    }
    let wakeTint = 1;
    if (dayCycleState !== "off") {
        const sunY = Math.sin(timeOfDay * Math.PI * 2 - Math.PI / 2);
        wakeTint = Math.min(1, 0.05 + Math.max(0, sunY + 0.1) * 0.95);
    }
    for (let wi = wakePoints.length - 1; wi >= 0; wi--) {
        const p = wakePoints[wi];
        const age = now - p.born;
        if (age >= WAKE_LIFETIME) {
            p.mesh.dispose();
            p.mat.dispose();
            wakePoints.splice(wi, 1);
        } else {
            const fade = 1 - age / WAKE_LIFETIME;
            p.mat.alpha = (p.baseAlpha || 0.6) * fade * wakeTint;
            p.mat.emissiveColor.set(0.5 * wakeTint, 0.7 * wakeTint, 0.9 * wakeTint);
            p.mesh.scaling.x = 1 + (1 - fade) * 0.4;
            p.mesh.scaling.y = 1 + (1 - fade) * 0.4;
        }
    }

    // Garde-fou : si le bot observé n'existe plus côté monde, retour automatique.
    if (!isViewingLocal() && (!viewedBoat || !viewedBoat.mesh || !otherPlayers[viewedBoat.id])) {
        exitBotView();
    }
    const camTargetMesh = (viewedBoat && viewedBoat.mesh) ? viewedBoat.mesh : playerMesh;
    const camera = scene.activeCamera;
    if (camera === droneCamera) {
        // managed in updateDrone; skip default camera handling
    } else if (zoomMode) {
        camera.position.copyFrom(camTargetMesh.position);
        const zc = currentBoatZoomCamera || { forwardMeters: 0, upMeters: 0 };
        const fwd = metersToUnits(zc.forwardMeters || 0);
        const up = metersToUnits(zc.upMeters || 0);
        if (fwd) {
            const camRot = (viewedBoat && viewedBoat.mesh) ? viewedBoat.mesh.rotation.y : playerRotation;
            camera.position.x += -Math.cos(camRot) * fwd;
            camera.position.z += Math.sin(camRot) * fwd;
        }
        if (zoomLowMode) {
            camera.position.y = -metersToUnits(10);
        } else {
            camera.position.y += up;
        }
        camera.rotation.x = -fpvPitch;
        camera.rotation.y = fpvYaw;
        camera.fov = fpvFov;
    } else {
        // Spring-back : la caméra revient derrière le bateau seulement quand on
        // avance à une vitesse significative. Immobile ou quasi immobile → libre.
        const _speedRatioForCam = maxSpeed > 0 ? Math.abs(boatSpeed) / maxSpeed : 0;
        if (!mouseDown && _speedRatioForCam > 0.1 && Math.abs(cameraAlphaOffset) > 0.001) {
            let off = cameraAlphaOffset;
            while (off > Math.PI) off -= 2 * Math.PI;
            while (off < -Math.PI) off += 2 * Math.PI;
            cameraAlphaOffset = off * 0.985;
            if (Math.abs(cameraAlphaOffset) < 0.001) cameraAlphaOffset = 0;
        }
        const targetAlpha = -playerRotation + cameraAlphaOffset;
        let delta = targetAlpha - cameraAlpha;
        while (delta > Math.PI) delta -= 2 * Math.PI;
        while (delta < -Math.PI) delta += 2 * Math.PI;
        cameraAlpha += delta * (isViewingLocal() ? 0.030 : 0.08);
        camera.alpha = cameraAlpha;
        camera.beta = cameraBeta;
        camera.radius = cameraRadius;
        if (!cameraTargetVec) cameraTargetVec = new BABYLON.Vector3();
        cameraTargetVec.copyFrom(camTargetMesh.position);
        camera.target = cameraTargetVec;
        if (camTargetMesh.position.y < PERISCOPE_DEPTH) {
            const maxCamY = -0.15;
            const cosMax = (maxCamY - camTargetMesh.position.y) / camera.radius;
            if (cosMax > 0 && cosMax < 1) {
                const minBeta = Math.acos(cosMax);
                if (camera.beta < minBeta) camera.beta = minBeta;
            }
        }
        if (worldData && worldData.islands) {
            camera.computeWorldMatrix();
            const cx = camera.position.x;
            const cz = camera.position.z;
            let inside = false;
            for (const island of worldData.islands) {
                if (pointInPolygon(cx, cz, island.points)) { inside = true; break; }
            }
            if (inside) {
                const tx = camTargetMesh.position.x;
                const tz = camTargetMesh.position.z;
                const dx = cx - tx;
                const dz = cz - tz;
                const dist = Math.sqrt(dx * dx + dz * dz);
                if (dist > 0.01) {
                    const nx = dx / dist;
                    const nz = dz / dist;
                    let r = camera.radius;
                    while (r > 1) {
                        r -= 0.5;
                        const testX = tx + nx * r;
                        const testZ = tz + nz * r;
                        let ok = true;
                        for (const island of worldData.islands) {
                            if (pointInPolygon(testX, testZ, island.points)) { ok = false; break; }
                        }
                        if (ok) break;
                    }
                    camera.radius = Math.max(1, r);
                }
            }
        }
    }

    const nowMove = performance.now();
    if (nowMove - lastMoveEmit >= MOVE_EMIT_INTERVAL && isViewingLocal()) {
        lastMoveEmit = nowMove;
        socket.emit("move", withBsid({
            position: {
                x: playerMesh.position.x,
                y: playerMesh.position.y,
                z: playerMesh.position.z,
            },
            rotation: playerRotation,
            rudder: rudderAngle,
            reverse: boatSpeed < 0,
            speedRatio: maxSpeed > 0 ? Math.abs(boatSpeed) / maxSpeed : 0,
            _ts: Date.now() / 1000,
        }));
    }

    const headingDeg = (((-playerRotation * 180 / Math.PI) % 360) + 360) % 360;
    const depthEl = document.getElementById("depthDisplay");
    if (activeWireTorpedoKey && remoteTorpedoes[activeWireTorpedoKey]) {
        // HUD pilotage filoguidée : remplace les infos sub par celles de la torpille.
        const r = remoteTorpedoes[activeWireTorpedoKey];
        const speedEl = document.getElementById("speedDisplay");
        const headingEl = document.getElementById("headingDisplay");
        const modeElW = document.getElementById("modeDisplay");
        // Cap torpille — convention serveur : dirX = -cos(rot), dirZ = sin(rot).
        const torpYaw = Math.atan2(r.dirZ, -r.dirX);
        const torpHeadingDeg = (((-torpYaw * 180 / Math.PI) % 360) + 360) % 360;
        // Cap nécessaire vers la cible (si on en a une).
        let needHeadingDeg = null;
        let distLabel = "—";
        let targetDepthLabel = "—";
        if (typeof r.tx === "number" && typeof r.tz === "number") {
            const dx = r.tx - r.x;
            const dz = r.tz - r.z;
            const distM = Math.sqrt(dx * dx + dz * dz) * UNIT_METERS;
            distLabel = distM >= 1000 ? (distM / 1000).toFixed(1) + " km" : Math.round(distM) + " m";
            const wantYaw = Math.atan2(dz, -dx);
            needHeadingDeg = (((-wantYaw * 180 / Math.PI) % 360) + 360) % 360;
            if (typeof r.ty === "number") {
                targetDepthLabel = "-" + Math.max(0, Math.round(-r.ty * UNIT_METERS)) + " m";
            }
        }
        const torpDepthLabel = "-" + Math.max(0, Math.round(-r.y * UNIT_METERS)) + " m";
        // Vitesse nominale lue dans le JSON (constante) — la mesure inter-trame
        // jitterait à cause du réseau.
        const wireSpec = (torpedoStats && torpedoStats.wireGuided) || null;
        const speedKn = wireSpec && wireSpec.speed ? wireSpec.speed : 0;
        speedEl.textContent = "Torpille: " + speedKn.toFixed(0) + " nds";
        const headTxt = needHeadingDeg != null
            ? "Cap: " + torpHeadingDeg.toFixed(0) + "° / requis " + needHeadingDeg.toFixed(0) + "°"
            : "Cap: " + torpHeadingDeg.toFixed(0) + "°";
        headingEl.textContent = headTxt;
        depthEl.style.display = "";
        depthEl.textContent = "Prof: torp " + torpDepthLabel + " / cible " + targetDepthLabel;
        if (modeElW) {
            modeElW.style.display = "";
            modeElW.textContent = "Cible: " + distLabel;
        }
    } else if (manualDroneControl && activeManualDrone) {
        const d = activeManualDrone;
        const droneKnots = unitPerSecondToKnots(d.speed);
        const droneYawRad = Math.atan2(d.dirX, d.dirZ);
        const droneHeadingDeg = ((droneYawRad * 180 / Math.PI) % 360 + 360) % 360;
        const remaining = Math.max(0, d.autonomy - d.traveled);
        const pct = d.autonomy > 0 ? (remaining / d.autonomy) * 100 : 0;
        const altM = Math.round(d.y * UNIT_METERS);
        document.getElementById("speedDisplay").textContent = "Drone: " + droneKnots.toFixed(1) + " nds";
        document.getElementById("headingDisplay").textContent = "Cap drone: " + droneHeadingDeg.toFixed(0) + "°";
        depthEl.style.display = "";
        depthEl.textContent = "Autonomie: " + pct.toFixed(0) + "%";
        const modeEl = document.getElementById("modeDisplay");
        if (modeEl) {
            modeEl.style.display = "";
            modeEl.textContent = "Altitude: " + altM + " m";
        }
    } else if (!isViewingLocal() && viewedBoat && otherPlayers[viewedBoat.id]) {
        const bid = viewedBoat.id;
        const bhist = otherPlayersHistory[bid];
        const binfo = otherPlayersInfo[bid];
        const botKnots = (bhist && binfo) ? (bhist.speedRatio || 0) * (binfo.maxSpeedKnots || 0) : 0;
        document.getElementById("speedDisplay").textContent = "Vitesse: " + botKnots.toFixed(1) + " nds";
        document.getElementById("headingDisplay").textContent = "Cap: " + headingDeg.toFixed(0) + "°";
        if (currentBoatType === "submarine") {
            depthEl.style.display = "";
            depthEl.textContent = "Profondeur: " + (-playerMesh.position.y * UNIT_METERS).toFixed(0) + "m";
        } else {
            depthEl.style.display = "none";
        }
    }
    else {
        document.getElementById("speedDisplay").textContent = "Vitesse: " + unitPerSecondToKnots(boatSpeed).toFixed(1) + " nds";
        document.getElementById("headingDisplay").textContent = "Cap: " + headingDeg.toFixed(0) + "°";
        if (currentBoatType === "submarine") {
            depthEl.style.display = "";
            depthEl.textContent = "Profondeur: " + (-playerMesh.position.y * UNIT_METERS).toFixed(0) + "m";
        } else {
            depthEl.style.display = "none";
        }
    }

    if (dayCycleState !== "off") updateDayCycle(engine.getDeltaTime() / 1000);
    const modeEl = document.getElementById("modeDisplay");
    if (activeWireTorpedoKey && remoteTorpedoes[activeWireTorpedoKey]) {
        // déjà géré dans la branche HUD filoguidée
    } else if (manualDroneControl && activeManualDrone) {
        // altitude already set above
    } else if (dayCycleState === "off") {
        modeEl.style.display = "none";
    } else {
        modeEl.style.display = "";
        const sunY = Math.sin(timeOfDay * Math.PI * 2 - Math.PI / 2);
        modeEl.textContent = "Mode: " + (sunY >= 0 ? "jour" : "nuit");
    }
    updateGrenades(dt);
    updateTorpedoes(dt);
    updateAcousticLures();
    updateDrone(dt);
    updateCannonShells();
    updateCannonImpacts();
    updateDroneCrashes(dt);
    updateDroneExplosions(dt);
    renderRadar();
    // Bouton désamorçage mine : son état dépend de la distance courante.
    updateMinePanel();
    updateVisuLabels();
    scene.render();
});


window.addEventListener("resize", () => { engine.resize(); });
