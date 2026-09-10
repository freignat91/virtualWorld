"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
const handlers = {};
let disposed = 0;
const context = vm.createContext({
    socket: { on: (name, fn) => { handlers[name] = fn; } },
    performance: { now: () => 1000 },
    acousticLures: { "owner:1": { mesh: { dispose: () => { disposed++; } } } },
    otherPlayersHistory: { "lure_owner:1": { integrity: 10, maxIntegrity: 10 } },
    otherPlayers: { "lure_owner:1": { dispose: () => { disposed++; } } },
    otherPlayersInfo: { "lure_owner:1": {} }, selectedBoatId: "lure_owner:1",
    selectedBoatIsSonar: true, boatAmmo: {}, boatIntegrity: 100, damageFlashUntil: 0,
    ammoKey: bsid => bsid ?? "primary", activeGhostSid: () => null,
    setTransientMessage: () => {}, spawnRemoteExplosion: () => {},
    triggerDamageFlash: () => {}, playerId: "human",
});
vm.runInContext(source.match(/function integrityPercent\([^]*?^\}/m)[0], context);
for (const name of ["integrity", "lure_integrity", "lure_destroyed", "torpedo_exploded"]) {
    const match = source.match(new RegExp('socket.on\\("' + name + '", \\(data\\) => \\{[^]*?^\\}\\);', "m"));
    assert.ok(match, name);
    vm.runInContext(match[0], context);
}
handlers.integrity({ value: 200, maxIntegrity: 200 });
assert.equal(context.boatIntegrity, 100);
assert.equal(context.damageFlashUntil, 0);
handlers.integrity({ value: 120, maxIntegrity: 200 });
assert.equal(context.boatIntegrity, 60);
assert.equal(context.boatAmmo.primary.integrity, 120);
assert.equal(context.boatAmmo.primary.maxIntegrity, 200);
handlers.integrity({ value: 20, maxIntegrity: 100 });
assert.equal(context.boatIntegrity, 20);
handlers.integrity({ value: 150, maxIntegrity: 200, bsid: "secondary" });
assert.equal(context.boatIntegrity, 20);
assert.equal(context.boatAmmo.secondary.integrity, 150);
handlers.lure_integrity({ ownerId: "owner", lid: 1, integrity: 6, maxIntegrity: 10 });
assert.equal(context.acousticLures["owner:1"].integrity, 6);
assert.equal(context.otherPlayersHistory["lure_owner:1"].integrity, 6);
assert.equal(context.integrityPercent(6, 10), 60);
handlers.torpedo_exploded({ x: 0, y: 0, z: 0 });
assert.ok(context.acousticLures["owner:1"]);
assert.equal(disposed, 0);
assert.ok(!source.includes("destroyLuresNearExplosion"));
handlers.lure_destroyed({ ownerId: "owner", lid: 1 });
handlers.lure_destroyed({ ownerId: "owner", lid: 1 });
assert.equal(disposed, 2);
assert.equal(context.acousticLures["owner:1"], undefined);
assert.equal(context.selectedBoatId, null);
handlers.lure_integrity({ ownerId: "owner", lid: 1, integrity: 6, maxIntegrity: 10 });
assert.equal(context.acousticLures["owner:1"], undefined);
console.log("Integrity HUD, raw points, nonlethal lure and authoritative deletion: OK");
