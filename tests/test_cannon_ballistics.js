"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
const handlers = {}, tracers = [], impacts = [], intents = [];
let disposed = 0;
const context = vm.createContext({
    socket: { on: (name, fn) => { handlers[name] = fn; }, emit: (_, data) => intents.push(data) },
    cannonTracers: tracers,
    spawnCannonTracer: (...args) => tracers.push({ type: "shell", shotId: args[9], args,
        mesh: { dispose: () => { disposed++; } } }),
    spawnCannonImpactVisual: (...args) => impacts.push(args),
    revealShooterFromFire: () => {},
    setTimeout: () => { throw new Error("Impact local interdit"); },
    BABYLON: { Vector3: class { constructor(x, y, z) { Object.assign(this, { x, y, z }); } } },
    playerMesh: { position: { x: 0, y: -0.2, z: 0 } }, isSinking: false,
    isViewingLocal: () => true, currentBoatType: "destroyer", boatFlotationY: -0.2,
    cannonSpec: { range: 2000 }, cannonAmmo: 50, UNIT_METERS: 10,
    findSelectedTarget: () => ({ type: "boat", id: "hidden-id", x: 80, y: -0.2, z: 0 }),
    withBsid: data => data,
});
for (const name of ["cannon_fire", "cannon_impact"]) {
    const match = source.match(new RegExp('socket.on\\("' + name + '", \\(data\\) => \\{[^]*?^\\}\\);', "m"));
    assert.ok(match, name);
    vm.runInContext(match[0], context);
}
for (const name of ["arcPoint", "fireCannon"]) {
    vm.runInContext(source.match(new RegExp("^function " + name + "\\([^]*?^}", "m"))[0], context);
}
const shot = { kind: "cannon", shooterId: "a", shotId: 7,
    startX: 0, startY: 0.5, startZ: 0, endX: 80, endY: -0.2, endZ: 0,
    arcHeight: 8, duration: 1600, impact: true };
handlers.cannon_fire(shot);
assert.equal(impacts.length, 0);
assert.equal(tracers[0].shotId, 7);
assert.equal(context.arcPoint(0, 0.5, 0, 80, -0.2, 0, 8, 0.5).y, 8.15);
handlers.cannon_fire({ ...shot, shotId: 8 });
handlers.cannon_impact({ shotId: 7, x: 40, y: 8.15, z: 0, reason: "island" });
assert.equal(disposed, 1);
assert.equal(tracers.length, 1);
assert.equal(tracers[0].shotId, 8);
assert.deepEqual(impacts[0], [40, 8.15, 0]);
context.fireCannon("cannon");
assert.equal(intents[0].targetType, "point");
assert.equal(intents[0].targetId, undefined);
assert.equal(intents[0].fixedTarget.x, 80);
console.log("Cannon trajectory, authoritative impacts and copied point intent checks passed");
