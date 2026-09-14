"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(require("node:path").join(__dirname, "../static/game.js"), "utf8");
let checks = 0;

for (const kind of ["acoustic", "autonomous", "wireGuided"]) {
    const sent = [];
    const context = vm.createContext({
        isSinking: false, playerMesh: { position: { x: 0, z: 0 } },
        isViewingLocal: () => true, currentBoatType: "submarine",
        torpedoCounts: { [kind]: 2 }, activeWireTorpedoKey: null,
        readTorpedoActivation: () => 500, torpedoStats: {}, UNIT_METERS: 10,
        selectedBeaconBid: null, sonarBeacons: {}, selectedBoatId: null,
        selectedTorpedoKey: null, aimingTorpedoKind: null,
        showAimBanner: () => {},
        socket: { emit: (event, payload) => sent.push({ event, payload }) },
        withBsid: value => value, setTransientMessage: () => {},
        selectedBoatContact: () => null, console,
    });
    vm.runInContext(source.match(/^function fireTorpedo\([^]*?^}/m)[0], context);

    context.fireTorpedo(kind);
    context.fireTorpedo(kind);
    assert.equal(sent.length, 0);
    assert.equal(context.aimingTorpedoKind, kind);
    checks += 2;

    context.selectedBeaconBid = 7;
    context.sonarBeacons = { 7: { x: -60, z: 20, bid: 7 } };
    context.fireTorpedo(kind);
    assert.equal(sent.length, 1);
    assert.equal(JSON.stringify(sent[0].payload.fixedTarget),
        JSON.stringify({ x: -60, z: 20, beaconBid: 7 }));
    checks += 2;
}

assert.match(source, /Radar : sélectionnez une cible ou un point de tir/);
assert.doesNotMatch(source, /Tir dans l'axe du bateau, sans cible acquise/);
console.log(`${checks + 2} selected-target torpedo client checks passed`);
