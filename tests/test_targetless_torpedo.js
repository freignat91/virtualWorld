"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(require("node:path").join(__dirname, "../static/game.js"), "utf8");
let checks = 0;
for (const kind of ["acoustic", "autonomous", "wireGuided"]) {
    const sent = [], messages = [];
    const context = vm.createContext({
        isSinking: false, playerMesh: { position: { x: 0, z: 0 } },
        isViewingLocal: () => true, currentBoatType: "submarine",
        torpedoCounts: { [kind]: 2 }, activeWireTorpedoKey: null,
        readTorpedoActivation: () => 500, torpedoStats: {}, UNIT_METERS: 10,
        selectedBeaconBid: null, selectedBoatId: null, selectedTorpedoKey: null,
        aimingTorpedoKind: null, showAimBanner: () => {}, cancelGrenadeAiming: () => {},
        socket: { emit: (event, payload) => sent.push({ event, payload }) },
        withBsid: x => x, setTransientMessage: x => messages.push(x),
        selectedBoatContact: () => null, console,
    });
    for (const name of ["fireTorpedo", "cancelAim"]) {
        vm.runInContext(source.match(new RegExp("^function " + name + "\\([^]*?^}", "m"))[0], context);
    }
    context.fireTorpedo(kind);
    assert.equal(sent.length, 0);
    assert.equal(context.aimingTorpedoKind, kind);
    context.fireTorpedo(kind);
    assert.equal(sent.length, 1);
    assert.equal(JSON.stringify(sent[0].payload), JSON.stringify({ kind, activationMeters: 500 }));
    assert.equal(context.aimingTorpedoKind, null);
    assert.match(messages[0], /axe du bateau, sans cible acquise/);
    context.selectedBoatId = "stale";
    context.fireTorpedo(kind);
    assert.equal(sent.length, 1);
    context.selectedBoatId = null;
    context.torpedoCounts[kind] = 0;
    context.fireTorpedo(kind);
    assert.equal(sent.length, 1);
    checks += 8;
    context.torpedoCounts[kind] = 2;
    context.selectedBeaconBid = 7;
    context.sonarBeacons = { 7: { x: -60, z: 20, bid: 7 } };
    context.fireTorpedo(kind);
    assert.equal(sent.length, 2);
    assert.equal(JSON.stringify(sent[1].payload.fixedTarget), JSON.stringify({ x: -60, z: 20, beaconBid: 7 }));
    checks += 2;
    if (kind === "wireGuided") {
        context.activeWireTorpedoKey = "owner:1";
        context.fireTorpedo(kind);
        assert.equal(sent.length, 2);
        checks += 1;
    }
}
assert.match(source, /Radar : point de reference.*tir dans l'axe, sans cible/);
console.log(`${checks + 1} targetless torpedo client checks passed`);
