"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
const handlers = {};
const sent = [];
const messages = [];
const context = vm.createContext({
    spectatorMode: false,
    window: { addEventListener: (name, fn) => { handlers[name] = fn; } },
    socket: { emit: (...args) => sent.push(args), on: (name, fn) => { handlers[name] = fn; } },
    radarCanvas: { addEventListener: (name, fn) => { handlers[name] = fn; },
        width: 100, height: 100, getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }) },
    worldData: { islands: [] }, radarDraggedRecently: false,
    radarView: () => ({}), radarToWorld: (x, z) => ({ x, z }), worldToRadar: (x, z) => ({ x, y: z }),
    playerMesh: { position: { x: 0, y: -2, z: 0 } }, boatSpeed: 3,
    cheatBuffer: "", cheatMoveMode: false, cheatTeleBotId: null, botCheatIndex: 0,
    selectedBoatId: null, selectedTorpedoKey: null, selectedDroneKey: null,
    selectedBeaconBid: null, selectedMineKey: null, selectedLocalDroneDid: null,
    selectedBoatIsSonar: false, remoteSinking: {}, otherPlayersInfo: { bot: { isBot: true }, human: {} },
    radarFrozenBoats: [{ id: "bot", x: 10, z: 10 }], sonarBeacons: {}, remoteDrones: {},
    remoteTorpedoes: {}, mines: {}, activeDrones: [], torpedoRadarRangeUnits: 100,
    currentBoatType: "destroyer", PERISCOPE_DEPTH: -1,
    keys: {}, manualDroneControl: false, aimingTorpedoKind: null, grenadeAiming: false,
    setTransientMessage: text => messages.push(text), cancelAim: () => {},
    pointInPolygon: () => false,
});
for (const pattern of [
    /window.addEventListener\("keydown", \(e\) => \{[^]*?^\}\);/m,
    /radarCanvas.addEventListener\("click", \(e\) => \{[^]*?^\}\);/m,
    /socket.on\("cheat_move_bot_result", \(data\) => \{[^]*?^\}\);/m,
]) {
    const match = source.match(pattern);
    assert.ok(match);
    vm.runInContext(match[0], context);
}
const type = text => { for (const key of text) handlers.keydown({ key }); };
const click = (x, z) => handlers.click({ clientX: x, clientY: z });
click(10, 10);
assert.equal(context.selectedBoatId, "bot");
type("telebot");
assert.equal(context.cheatTeleBotId, "bot");
assert.equal(context.cheatMoveMode, false);
assert.equal(sent.length, 0); // Ni changement de vue ni teleport avant le clic.
context.selectedBoatId = "human";
click(70, 80);
assert.equal(JSON.stringify(sent.pop()), JSON.stringify(["cheat_move_bot", { id: "bot", x: 70, z: 80 }]));
assert.equal(context.selectedBoatId, "human");
assert.equal(context.playerMesh.position.x, 0);
assert.equal(context.playerMesh.position.z, 0);
assert.equal(context.cheatTeleBotId, null);

for (const selection of [null, "human", "missing", "bot"]) {
    context.selectedBoatId = selection;
    context.selectedTorpedoKey = selection === "bot" ? "remote:t" : null;
    type("telebot");
    assert.equal(context.cheatMoveMode, false);
    assert.equal(context.cheatTeleBotId, null);
    assert.match(messages.at(-1), /sélectionnez un bot/);
}
context.selectedTorpedoKey = null;
context.selectedBoatId = "bot";
context.remoteSinking.bot = {};
type("telebot");
assert.equal(context.cheatTeleBotId, null);
delete context.remoteSinking.bot;
type("telebot");
handlers.keydown({ key: "Escape" });
assert.equal(context.cheatTeleBotId, null);
assert.equal(context.cheatMoveMode, false);
assert.equal(sent.length, 0);

type("telebot");
context.radarDraggedRecently = true;
click(50, 60);
assert.equal(sent.length, 0);
assert.equal(context.cheatTeleBotId, "bot");
click(50, 60);
assert.equal(sent.length, 1);
sent.length = 0;
handlers.cheat_move_bot_result({ ok: false, message: "Bot introuvable" });
assert.equal(messages.at(-1), "Bot introuvable");
assert.equal(context.cheatMoveMode, false);

type("move");
assert.equal(context.cheatMoveMode, true);
handlers.keydown({ key: "Shift" });
assert.equal(context.cheatMoveMode, true);
click(40, 50);
assert.equal(context.playerMesh.position.x, 40);
assert.equal(context.playerMesh.position.z, 50);
assert.equal(context.boatSpeed, 0);
assert.equal(context.cheatMoveMode, false);
for (const code of ["movebot", "movebot", "bot"]) {
    const index = context.botCheatIndex;
    type(code);
    assert.equal(JSON.stringify(sent.pop()), JSON.stringify(["cheat_swap_to_bot", { index }]));
    assert.equal(context.botCheatIndex, index + 1);
    assert.equal(context.cheatMoveMode, false);
    assert.equal(context.cheatTeleBotId, null);
    click(10, 10);
    assert.equal(sent.length, 0);
    assert.equal(context.playerMesh.position.x, 40);
    assert.equal(context.playerMesh.position.z, 50);
}
type("self");
assert.equal(sent.pop()[0], "cheat_swap_to_self");
assert.equal(context.botCheatIndex, 0);

for (const tagName of ["INPUT", "TEXTAREA"]) {
    for (const key of "telebot") handlers.keydown({ key, target: { tagName } });
    assert.equal(context.cheatTeleBotId, null);
    assert.equal(sent.length, 0);
}
type("TELEBOT");
assert.equal(context.cheatTeleBotId, "bot");
type("movebot");
assert.equal(sent.pop()[0], "cheat_swap_to_bot");
assert.equal(context.cheatTeleBotId, null);
assert.equal(context.cheatMoveMode, false);
type("move");
handlers.keydown({ key: "Escape" });
assert.equal(context.cheatMoveMode, false);
assert.equal(context.cheatBuffer, "");
console.log("telebot: selection, parsing, target capture, click, cancellation; move/movebot/bot/self regressions OK");
