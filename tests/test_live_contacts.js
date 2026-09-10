"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
new vm.Script(source);
const body = name => {
    const match = source.match(new RegExp("^function " + name + "\\([^]*?^}", "m"));
    assert.ok(match, name);
    return match[0];
};
let now = 100;
let clear = true;
let layers = 0;
let alerts = 0;
const handlers = {};
const sent = [];
const tip = { style: {} };
const context = vm.createContext({
    spectatorMode: false,
    performance: { now: () => now },
    metersToUnits: n => n / 10, UNIT_METERS: 10,
    playerMesh: { position: { x: 0, y: -2, z: 0 } }, playerId: "me",
    playerRotation: 0, currentBoatType: "submarine", localTeamId: null,
    activePings: [], SONAR_REVEAL_DURATION: 5000, SONAR_COOLDOWN: 3000,
    lastSonarPing: 0, sonarShortRange: 800, sonarReveal: 1500,
    torpedoRadarRangeUnits: 3000, allMapMode: false,
    isLineOfSightClear: () => clear, isLineOfSightClearBetween: () => clear,
    countThermoclinesCrossed: () => layers, showSonarDetectedAlert: () => alerts++,
    socket: { on: (name, fn) => { handlers[name] = fn; }, emit: (...args) => sent.push(args) },
    isSinking: false, torpedoCounts: { acoustic: 10 }, torpedoStats: {},
    readTorpedoActivation: () => 100, showAimBanner: () => {}, aimingTorpedoKind: null,
    isViewingLocal: () => true, withBsid: x => x,
    sonarRevealedUntil: { enemy: 10100 }, passiveSonarDetectionsUntil: {},
    sonarObservedBoats: {}, radarFrozenBoats: [], selectedBoatId: "enemy",
    selectedBoatIsSonar: true, selectedTorpedoKey: "remote:t",
    selectedDroneKey: null, selectedBeaconBid: null, selectedLocalDroneDid: null, selectedMineKey: null,
    otherPlayers: { enemy: { position: { x: -100, y: -3, z: 0 }, isEnabled: () => false } },
    otherPlayersInfo: {}, otherPlayersHistory: {}, remoteTorpedoes: {},
    alliedObservers: () => [{ x: 0, y: -2, z: 0 }], alliedDrones: () => [],
    PERISCOPE_DEPTH: -1, localBoat: null, zoomLowMode: false,
    document: { getElementById: () => tip },
    radarCanvas: { getBoundingClientRect: () => ({ left: 0, top: 300 }) },
    TORPEDO_TRAIL_LIFE_MS: 1000, TORPEDO_TRAIL_ALPHA: 0.5,
    disposeTorpedoTrailPoint: p => { p.disposed = true; },
});
vm.runInContext([
    "pingRangeUnits", "pingRevealUnits", "triggerSonarPing", "selectedBoatContact",
    "isTorpedoRadarVisible", "updateRadarTooltip", "addTorpedoTrail", "fireTorpedo", "removeRemoteTorpedo",
].map(body).join("\n"), context);
const received = source.match(/socket.on\("sonar_pinged", \(data\) => \{[^]*?^\}\);/m)[0];
vm.runInContext(received, context);
for (const id of ["human", "bot"]) {
    handlers.sonar_pinged({ id, x: -100, y: -17, z: 0, range: 8000, reveal: 15000, coneDeg: 360 });
    const ping = context.activePings.at(-1);
    assert.equal(ping.y, -17);
    assert.equal(context.pingRangeUnits(ping), 800);
    assert.equal(context.pingRevealUnits(ping), 1500);
}
const count = context.activePings.length;
handlers.sonar_pinged({ id: "beacon:1", x: 0, y: -2, z: 0, range: 8000, reveal: 8000 });
assert.equal(context.activePings.length, count);
clear = false;
const previousAlerts = alerts;
handlers.sonar_pinged({ id: "hidden", x: -100, y: -2, z: 0, range: 8000 });
assert.equal(alerts, previousAlerts);
now = 4000;
context.triggerSonarPing(30, 800);
assert.equal(context.pingRangeUnits(context.activePings.at(-1)), 800);

// Execute les blocs reels de persistance/radar avec un DOM et des capteurs minimaux.
const radar = body("renderRadar");
const persist = radar.slice(radar.indexOf("    const revealObservers ="), radar.indexOf("    // Note :"));
const boats = radar.slice(radar.indexOf("    if (!radarFrozen) {"), radar.indexOf("    const playerProj ="));
vm.runInContext("function frame(now, radarFrozen) { const revealed = new Set();\n" + persist + boats + "\n}", context);
for (const frozen of [false, true]) {
    now = 100;
    clear = true;
    context.sonarRevealedUntil.enemy = 10100;
    context.otherPlayers.enemy.position = { x: -100, y: -3, z: 0 };
    context.radarFrozenBoats = [];
    context.sonarObservedBoats = {};
    context.selectedBoatId = "enemy";
    context.frame(now, frozen);
    assert.equal(context.selectedBoatContact().x, -100);
    clear = false;
    for (const [x, y] of [[-150, -20], [-200, -40]]) {
        now += 500;
        context.otherPlayers.enemy.position = { x, y, z: 0 };
        context.frame(now, frozen);
        const contact = context.selectedBoatContact();
        assert.equal(contact.x, -100);
        assert.equal(contact.y, -3);
        assert.equal(contact.remembered, true);
        assert.equal(context.sonarRevealedUntil.enemy, 10100);
        context.fireTorpedo("acoustic");
        const [event, payload] = sent.at(-1);
        assert.equal(event, "torpedo_fire");
        assert.equal(payload.fixedTarget.x, -100);
        assert.equal(payload.fixedTarget.z, 0);
        assert.equal(payload.targetId, undefined);
    }
    clear = true;
    context.frame(2000, frozen);
    assert.equal(context.selectedBoatContact().x, -200);
    assert.equal(context.selectedBoatContact().y, -40);
    assert.equal(context.sonarRevealedUntil.enemy, 10100);
    now = 10100;
    context.frame(now, frozen);
    assert.equal(context.radarFrozenBoats.length, 0);
}

const torpedo = { x: 100, y: -3, z: 0, ownerId: "enemy" };
context.remoteTorpedoes.t = torpedo;
clear = true;
assert.equal(context.isTorpedoRadarVisible(torpedo), true);
context.updateRadarTooltip({});
assert.equal(tip.style.display, "block");
for (const reason of ["island", "range", "thermocline"]) {
    clear = reason !== "island";
    layers = reason === "thermocline" ? 1 : 0;
    torpedo.x = reason === "range" ? 3001 : 100;
    context.selectedTorpedoKey = "remote:t";
    context.updateRadarTooltip({});
    assert.equal(context.selectedTorpedoKey, null);
    assert.equal(tip.style.display, "none");
    context.selectedTorpedoKey = "remote:t";
    context.selectedBoatId = null;
    const before = sent.length;
    context.fireTorpedo("acoustic");
    assert.equal(sent.length, before);
    assert.equal(context.selectedTorpedoKey, null);
}
const dot = { born: now - 500, mesh: {} };
const trail = { trail: [dot] };
context.addTorpedoTrail(trail, false);
assert.equal(trail.trail.length, 1);
assert.equal(dot.mesh.visibility, 0.25);
now += 500;
context.addTorpedoTrail(trail, false);
assert.equal(trail.trail.length, 0);
assert.equal(dot.disposed, true);
vm.runInContext(source.match(/socket.on\("torpedo_dead", \(data\) => \{[^]*?^\}\);/m)[0], context);
let meshDisposed = 0;
let panelUpdates = 0;
const deadTrail = { mesh: {} };
context.remoteTorpedoes["me:1"] = {
    mesh: { dispose: () => meshDisposed++ }, trail: [deadTrail],
};
context.activeWireTorpedoKey = "me:1";
context.selectedTorpedoKey = "remote:me:1";
context.selectedBoatId = null;
context.updateTorpedoPanel = () => panelUpdates++;
handlers.torpedo_dead({ ownerId: "me", tid: 1 });
assert.equal(context.remoteTorpedoes["me:1"], undefined);
assert.equal(meshDisposed, 1);
assert.equal(deadTrail.disposed, true);
assert.equal(context.activeWireTorpedoKey, null);
assert.equal(panelUpdates, 1);
context.updateRadarTooltip({});
assert.equal(context.selectedTorpedoKey, null);
handlers.torpedo_dead({ ownerId: "me", tid: 1 });
assert.equal(meshDisposed, 1);
console.log("Live contact transport, frozen caches, selection and trail contracts passed");
