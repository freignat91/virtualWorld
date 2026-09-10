"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const BABYLON = require("../static/babylon.js");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
const handlers = {}, sent = [], listeners = {}, elements = new Map();
let frame;
const context2d = new Proxy({ measureText: text => ({ width: text.length * 6 }) }, { get: (target, key) => target[key] || (() => {}),
    set: (target, key, value) => { target[key] = value; return true; } });
function element(id = "") {
    if (elements.has(id)) return elements.get(id);
    const node = { id, style: {}, dataset: {}, value: "", textContent: "", hidden: true,
        width: 450, height: 225, children: [], classList: { add() {}, remove() {}, toggle() {} },
        addEventListener(name, fn) {
            const previous = listeners[id + ":" + name];
            listeners[id + ":" + name] = previous ? e => { previous(e); fn(e); } : fn;
        },
        appendChild(child) { this.children.push(child); }, remove() {},
        setAttribute() {}, getAttribute() { return null; }, querySelectorAll() { return []; },
        querySelector() { return null; },
        getContext: () => context2d,
        getBoundingClientRect: () => ({ left: 0, top: 0, width: 450, height: 225 }),
        contains: () => false };
    elements.set(id, node);
    return node;
}
const engine = new BABYLON.NullEngine({ renderWidth: 1000, renderHeight: 700 });
engine.runRenderLoop = fn => { frame = fn; };
engine.getDeltaTime = () => 100;
const socket = { connected: true, on(name, fn) { handlers[name] = fn; },
    emit(...args) { sent.push(args); return this; }, connect() { handlers.connect(); } };
class Camera extends BABYLON.ArcRotateCamera {
    attachControl() {} // Entrees navigateur hors du perimetre NullEngine.
}
const context = vm.createContext({
    BABYLON: { ...BABYLON, Engine: function () { return engine; }, ArcRotateCamera: Camera },
    console, performance: { now: () => 1000 }, Date, URLSearchParams, Math,
    io: () => socket, setInterval() {}, clearInterval() {}, setTimeout() {}, clearTimeout() {},
    requestAnimationFrame() {}, Image: class { addEventListener() {} },
    location: { search: "", reload() {} },
    window: { innerWidth: 1000, innerHeight: 700,
        addEventListener(name, fn) { element("window").addEventListener(name, fn); } },
    document: { body: element("body"), getElementById: element,
        createElement: tag => element(tag + elements.size), querySelectorAll: () => [],
        addEventListener(name, fn) { element("document").addEventListener(name, fn); } },
});
const run = code => vm.runInContext(code, context);
run(source);
// Monde/modeles remplaces uniquement pour eviter les chargements reseau d'assets.
run(`buildWorld = () => {
        oceanMesh = BABYLON.MeshBuilder.CreateGround("testOcean", {}, scene);
        seabedMesh = BABYLON.MeshBuilder.CreateGround("testSeabed", {}, scene);
    };
    makeDroneMesh = () => BABYLON.MeshBuilder.CreateBox("testDrone", {}, scene);
    loadBoatModel = (path, done) => done(BABYLON.MeshBuilder.CreateBox("testBoat", {}, scene));`);
listeners["document:DOMContentLoaded"]();
listeners["spectateBtn:click"]();
assert.equal(sent.at(-1)[0], "spectate");
const data = { spectator: true, world: { ground: { width: 1000, depth: 1000 }, islands: [] },
    players: { a: { id: "botA", is_bot: true, boatType: "submarine", team_id: "red",
        team_name: "Red", boat: { lengthMeters: 100, speed: 20 },
        position: { x: 10, y: -5, z: 20 }, rotation: 0 },
        b: { id: "humanB", is_bot: false, boatType: "destroyer", team_id: "blue",
            boat: { lengthMeters: 120, speed: 30, integrity: 200, radarRangeMeters: 1000 },
            integrity: 150, maxIntegrity: 200, position: { x: 50, y: -0.2, z: 20 }, rotation: 1 },
        c: { id: "botC", is_bot: true, boatType: "destroyer", team_id: "red",
            boat: { lengthMeters: 100, speed: 20, integrity: 200 },
            integrity: 100, maxIntegrity: 200, position: { x: 80, y: -0.2, z: 20 }, rotation: 2 } },
    dayCycle: { state: "off", now: Date.now() / 1000, startedAt: 0, startTimeOfDay: 0 },
    grenades: [{ gid: 1, shooterId: "botA", phase: "water", x: 20, y: -2, z: 20,
        vx: 0, vy: 0, vz: 0, impactX: 20, impactZ: 20, targetDepth: 10, sinkSpeed: 0.4 }] };
handlers.grenade_launched({ gid: 1, shooterId: "botA", x: 10, y: 1, z: 20,
    vx: 1, vy: 1, vz: 0, targetDepth: 10, sinkSpeed: 0.4 });
const emptyInit = process.argv.includes("--empty");
handlers.init(emptyInit ? { ...data, players: {} } : data);
if (emptyInit) {
    frame();
    assert.equal(run("viewedBoat"), null);
    assert.equal(run("localBoat"), null);
    assert.equal(run("playerMesh"), null);
    assert.equal(run("allMapMode"), false);
    listeners["botsBtn:click"]();
    frame();
    handlers.player_joined(data.players.b);
    frame();
    assert.equal(run("viewedBoat.id"), "humanB");
    assert.equal(run("playerMesh === remoteBoats.humanB.mesh"), true);
    assert.equal(element("integrityDisplay").textContent, "Intégrité: 75%");
    assert.equal(run("localBoat"), null);
    assert.ok(sent.every(([event]) => ["spectate", "list_teams", "admin_list_textures"].includes(event)));
    engine.dispose();
    console.log("Spectator: empty init and first arrival auto-follow OK");
    process.exit(0);
}
assert.equal(run("localBoat"), null);
assert.equal(run("playerMesh === remoteBoats.botA.mesh"), true);
assert.equal(run("localBoats.length"), 0);
assert.equal(run("Object.keys(boatAmmo).length"), 0);
assert.equal(run("isViewingLocal()"), false);
assert.equal(run("grenades[0].phase"), "water");
assert.equal(run("grenades[0].y"), -2);
assert.equal(run("grenades.length"), 1);
handlers.player_moved({ id: "botA", position: { x: 10, y: -5, z: 20 }, rotation: 0, submerged: true });
handlers.torpedo_state({ ownerId: "botA", tid: 1, kind: "acoustic", x: 5, y: -8, z: 4, dirX: 1, dirZ: 0 });
handlers.drone_state({ ownerId: "botA", did: 1, kind: "automatic", x: 5, y: 8, z: 4, dirX: 1, dirZ: 0 });
handlers.lure_dropped({ ownerId: "botA", lid: 1, x: 0, y: -2, z: 0, durationMs: 10000 });
frame();
assert.equal(run("oceanMesh.isVisible"), false);
assert.equal(run("seabedMesh.isVisible"), true);
assert.equal(run("!allMapMode && radarVisible && radarZoom === 1"), true);
assert.equal(run("viewedBoat.id"), "botA");
assert.equal(element("botsBtn").textContent, "Changer unité");
assert.equal(run("scene.activeCamera.target === playerMesh.position"), false);
const key = (key, shiftKey = false) => listeners["window:keydown"]({ key, shiftKey, preventDefault() {} });
const type = text => { for (const letter of text) key(letter); };
const initialController = run("remoteBoats.botA");
run(`sonarObservedBoats.stale = {x: 5}; sonarRevealedUntil.stale = 5000;
    passiveSonarDetectionsUntil.stale = 5000; mineRevealedUntil.stale = 5000;`);
element("spectatorNextBtn").onclick();
assert.equal(run("[sonarObservedBoats, sonarRevealedUntil, passiveSonarDetectionsUntil, mineRevealedUntil].every(c => !c.stale)"), true);
frame();
assert.equal(run("viewedBoat.id"), "humanB");
assert.equal(run("currentBoatType"), "destroyer");
assert.equal(run("sensorTeamId()"), "blue");
assert.equal(run("localTeamId"), null);
assert.equal(run("playerId"), undefined);
assert.equal(run("boatIntegrity"), 100);
assert.equal(element("integrityDisplay").textContent, "Intégrité: 75%");
assert.equal(run("oceanMesh.isVisible && !seabedMesh.isVisible && !scene.clipPlane"), true);
assert.equal(run("otherPlayers.botA.isEnabled()"), false);
assert.equal(run("radarFrozenBoats.some(b => b.id === 'botA')"), false);
assert.equal(run("isTorpedoRadarVisible({x:500, y:0, z:500, ownerId:'enemy'})"), false);
handlers.passive_sonar_detection({ detectedId: "botA", teamId: "red" });
assert.equal(run("passiveSonarDetectionsUntil.botA"), undefined);
assert.equal(run("scene.activeCamera.target.x"), 50);
listeners["zoomBtn:click"]();
frame();
assert.equal(run("zoomMode && scene.activeCamera === scene._fpvCamera"), true);
assert.equal(run("scene.activeCamera.position.x"), 50);
listeners["botsBtn:click"]();
frame();
assert.equal(run("viewedBoat.id"), "botC");
assert.equal(element("integrityDisplay").textContent, "Intégrité: 50%");
key("Tab", true);
assert.equal(run("viewedBoat.id"), "humanB");
key("Tab");
assert.equal(run("viewedBoat.id"), "botC");
listeners["botsBtn:click"]();
frame();
assert.equal(run("viewedBoat.id"), "botA");
assert.equal(run("remoteBoats.botA"), initialController);
assert.equal(initialController.isLocal, false);
assert.equal(initialController.boatSpeed, 0);
assert.equal(run("selectedBoatId"), null);
handlers.player_left({ id: "humanB" });
handlers.player_left({ id: "botC" });
type("allmap");
assert.equal(run("allMapMode"), true);
frame();
assert.equal(run("radarView().viewW"), 1000);
const cameraRadius = run("scene.activeCamera.radius");
let prevented = false;
const wheel = deltaY => listeners["radar:wheel"]({ clientX: 180, clientY: 90, deltaY,
    preventDefault() { prevented = true; } });
const cursorBefore = run("radarToWorld(180, 90, radarView())");
wheel(-1);
assert.equal(prevented, true);
assert.equal(run("radarZoom"), 1.25);
assert.deepEqual(run("radarToWorld(180, 90, radarView())"), cursorBefore);
assert.equal(run("scene.activeCamera.radius"), cameraRadius);
listeners["radar:pointerdown"]({ button: 0, clientX: 180, clientY: 90, pointerId: 1 });
listeners["radar:pointermove"]({ clientX: 210, clientY: 110 });
listeners["radar:pointerup"]({ pointerId: 1 });
assert.notEqual(run("radarCenterX"), cursorBefore.x);
listeners["radar:click"]({ clientX: 210, clientY: 110 });
assert.equal(run("viewedBoat.id"), "botA");
for (let i = 0; i < 30; i++) wheel(-1);
assert.equal(run("radarZoom"), 100);
listeners["radar:pointerdown"]({ button: 0, clientX: 0, clientY: 0, pointerId: 2 });
listeners["radar:pointermove"]({ clientX: 100000, clientY: 100000 });
listeners["radar:pointerup"]({ pointerId: 2 });
assert.equal(run("radarCenterX"), 495);
assert.equal(run("radarCenterZ"), run("-(radarView().worldD - radarView().viewD) / 2"));
listeners["radar:click"]({ clientX: 0, clientY: 0 });
for (let i = 0; i < 30; i++) wheel(1);
assert.equal(run("radarZoom"), 1);
assert.equal(run("radarCenterX"), 0);
assert.equal(run("radarCenterZ"), 0);
const boatOnMap = run("worldToRadar(otherPlayers.botA.position.x, otherPlayers.botA.position.z, radarView())");
listeners["radar:click"]({ clientX: boatOnMap.x * 450 / run("radarCanvas.width"),
    clientY: boatOnMap.y * 225 / run("radarCanvas.height") });
assert.equal(run("viewedBoat.id"), "botA");
assert.equal(run("otherPlayers.botA.isEnabled()"), true);
assert.equal(run('remoteTorpedoes["botA:1"].mesh.isEnabled()'), true);
listeners["botsBtn:click"]();
assert.equal(run("viewedBoat.id"), "botA");
assert.equal(run("scene.activeCamera.target === otherPlayers.botA.position"), false);
run("scene.activeCamera.target.x += 100");
assert.equal(run("otherPlayers.botA.position.x"), 10);
frame();
assert.equal(run("scene.activeCamera.target.x"), 10);
handlers.player_moved({ id: "botA", position: { x: 30, y: -6, z: 20 }, rotation: 0.2,
    speedRatio: 0.5, reverse: false, integrity: 80, maxIntegrity: 100, submerged: true });
frame();
assert.ok(run("otherPlayers.botA.position.x > 10 && otherPlayers.botA.position.x < 30"));
assert.equal(run("scene.activeCamera.target.x"), run("otherPlayers.botA.position.x"));
assert.equal(element("integrityDisplay").textContent, "Intégrité: 80%");
const poseBeforeInput = run("JSON.stringify(playerMesh.position)");
const beforeInput = sent.length;
for (const name of ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " ", "x", "F1"]) key(name);
for (const command of ["move", "telebot", "self", "idkfa", "time8", "speed2", "tta", "ll"]) type(command);
listeners["renderCanvas:wheel"]({ deltaY: -1, preventDefault() {} });
listeners["document:pointerdown"]({ button: 0, target: element("renderCanvas"), clientX: 10, clientY: 10 });
listeners["document:pointermove"]({ clientX: 40, clientY: 30 });
listeners["document:pointerup"]({ button: 0, clientX: 40, clientY: 30 });
assert.equal(run("JSON.stringify(playerMesh.position)"), poseBeforeInput);
assert.equal(sent.length, beforeInput);
assert.equal(run("cheatMoveMode || cheatTeleBotId !== null"), false);
const lureMesh = run('acousticLures["botA:1"].mesh');
handlers.lure_dropped({ ownerId: "botA", lid: 1, x: 0, y: -2, z: 0, durationMs: 9000 });
assert.equal(lureMesh.isDisposed(), true);
handlers.boat_sunk({ victimId: "botA", attackerId: "enemy" });
frame();
assert.equal(run("viewedBoat"), null);
assert.equal(run("isSinking"), false);
assert.equal(element("sinkMessage").style.display, undefined);
handlers.player_left({ id: "botA" });
frame();
listeners["botsBtn:click"]();
assert.equal(run("viewedBoat"), null);
for (const event of ["move", "player_move", "spawn_bot", "torpedo_fire", "sonar_ping", "admin_save_map", "set_sim_speed", "select_boat", "set_active_boat", "change_boat", "pause_active_boat"]) {
    socket.emit(event, {});
}
assert.ok(sent.every(([event]) => ["spectate", "list_teams", "admin_list_textures"].includes(event)));
assert.equal(run("localBoat"), null);
assert.equal(run("playerMesh"), null);
assert.equal(run("selfControlledPlayerIds.size"), 0);
assert.ok(frame.toString().indexOf("renderSpectator") < frame.toString().indexOf("!localBoat"));
// Arrivees asynchrones : attendre le premier de la liste, pas le modele le plus rapide.
run(`loadBoatModel = (path, done) => { window.pendingModels.push(done); };`);
context.window.pendingModels = [];
handlers.player_joined({ ...data.players.b, id: "lateFirst" });
handlers.player_joined({ ...data.players.c, id: "lateSecond" });
context.window.pendingModels[1](run('BABYLON.MeshBuilder.CreateBox("lateSecond", {}, scene)'));
frame();
assert.equal(run("viewedBoat"), null);
context.window.pendingModels[0](run('BABYLON.MeshBuilder.CreateBox("lateFirst", {}, scene)'));
frame();
assert.equal(run("viewedBoat.id"), "lateFirst");
handlers.boat_sunk({ victimId: "lateFirst", attackerId: "enemy" });
frame();
assert.equal(run("viewedBoat.id"), "lateSecond");
assert.equal(run("isSinking"), false);
handlers.player_left({ id: "lateSecond" });
frame();
assert.equal(run("viewedBoat"), null);
assert.equal(run("playerMesh"), null);
assert.equal(run("localBoat"), null);
key("Tab");
key("Tab", true);
// Meme bouton en mode joueur : popup d'ajout, Tab conserve le vrai changement actif.
run(`spectatorMode = false;
    const spec = { speed: 20, lengthMeters: 100, integrity: 200 };
    localBoats = [0, 1].map(i => ({ ghostSid: i ? "secondary" : null, playerId: "own" + i,
        boat: new Boat({ isLocal: true, boatType: "destroyer", boatData: spec,
            mesh: BABYLON.MeshBuilder.CreateBox("own" + i, {}, scene) }), sunk: false }));
    localBoat = viewedBoat = localBoats[0].boat;
    playerId = "own0"; playerMesh = localBoat.mesh; activeBoatIndex = 0;
    selfControlledPlayerIds.add(playerId);`);
listeners["botsBtn:click"]();
assert.equal(element("botsPopup").style.display, "block");
key("Tab");
assert.equal(run("activeBoatIndex"), 1);
assert.equal(sent.at(-1)[0], "set_active_boat");
assert.equal(sent.at(-1)[1].bsid, "secondary");
assert.equal(run("selfControlledPlayerIds.has('own1') && !selfControlledPlayerIds.has('own0')"), true);
key("Tab", true);
assert.equal(run("activeBoatIndex"), 0);
assert.equal(sent.at(-1)[1].bsid, null);
engine.dispose();
console.log("Spectator: full client bootstrap, NullEngine frames/radar/projectiles, camera isolation, sinking and read-only emits OK");
