"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
const fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, "geometry_visibility.json"), "utf8"));
// Execute les vraies fonctions du client, sans charger Babylon ni le DOM.
const names = ["pointInPolygon", "getIslandBounds", "segmentsIntersectClosed", "isLineOfSightClearBetween"];
const functions = names.map(name => {
    const match = source.match(new RegExp("^function " + name + "\\([^]*?^}", "m"));
    assert.ok(match, "Missing client function: " + name);
    return match[0];
}).join("\n");
const context = vm.createContext({ worldData: null, islandBoundsCache: [] });
vm.runInContext(functions, context);
let checks = 0;
for (const test of fixtures.cases) {
    for (const reverse of [false, true]) {
        for (const winding of [false, true]) {
            for (const closed of [false, true]) {
                context.worldData = { islands: test.islands.map(name => {
                    const points = fixtures.polygons[name].map(([x, z]) => ({ x, z }));
                    if (winding) points.reverse();
                    if (closed && points.length) points.push({ ...points[0] });
                    return { points };
                }) };
                context.islandBoundsCache.length = 0;
                const s = test.segment;
                const segment = reverse ? [...s.slice(2), ...s.slice(0, 2)] : s;
                assert.equal(context.isLineOfSightClearBetween(...segment, null), test.clear,
                    `${test.name}: reverse=${reverse}, winding=${winding}, closed=${closed}`);
                checks++;
            }
        }
    }
}
context.worldData = { islands: ["square", "thin"].map(name => ({
    points: fixtures.polygons[name].map(([x, z]) => ({ x, z }))
})) };
context.islandBoundsCache.length = 0;
assert.equal(context.isLineOfSightClearBetween(-1, 1.5, 3, 1.5, "island_0"), true);
assert.equal(context.isLineOfSightClearBetween(-1, 0.5, 3, 0.5, "island_0"), false);
assert.equal(context.isLineOfSightClearBetween(-1, 1.5, 3, 1.5, "island_1"), false);
context.worldData = null;
assert.equal(context.isLineOfSightClearBetween(0, 0, 1, 1, null), true);
console.log(`${checks + 4} client visibility checks passed`);
