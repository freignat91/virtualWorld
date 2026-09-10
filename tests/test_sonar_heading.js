"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
const context = vm.createContext({ radarCanvas: { width: 800, height: 800 } });
for (const name of ["pingPointInCone", "worldToRadar"]) {
    const match = source.match(new RegExp("^function " + name + "\\([^]*?^}", "m"));
    assert.ok(match, "Missing client function: " + name);
    vm.runInContext(match[0], context);
}

let checks = 0;
for (let heading = 0; heading < 360; heading += 45) {
    const rotation = heading * Math.PI / 180;
    const ping = { x: 123, z: -456, rotation, coneDeg: 30 };
    for (const distance of [200, 300]) {
        for (const offset of [0, -14.99, 14.99, -15.01, 15.01, 180]) {
            const bearing = rotation + offset * Math.PI / 180;
            const x = ping.x - Math.cos(bearing) * distance;
            const z = ping.z + Math.sin(bearing) * distance;
            assert.equal(context.pingPointInCone(ping, x, z), Math.abs(offset) < 15,
                `heading=${heading}, distance=${distance}, offset=${offset}`);
            checks++;
        }
    }
    // L'axe X inverse du radar explique le cosinus positif du cone affiche.
    const view = { cX: 0, cZ: 0, sX: 0.5, sZ: 0.5 };
    const origin = context.worldToRadar(ping.x, ping.z, view);
    const bow = context.worldToRadar(ping.x - Math.cos(rotation), ping.z + Math.sin(rotation), view);
    assert.ok(Math.abs(bow.x - origin.x - Math.cos(rotation) * view.sX) < 1e-10);
    assert.ok(Math.abs(bow.y - origin.y - Math.sin(rotation) * view.sZ) < 1e-10);
    checks += 2;
}
console.log(`${checks} client sonar heading checks passed`);
