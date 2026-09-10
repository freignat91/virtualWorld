"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/game.js"), "utf8");
const tip = { style: {} }, label = { style: {}, dataset: {} };
const context = vm.createContext({
    remoteTorpedoes: {}, playerId: "owner", sensorPlayerId: () => "owner",
    sensorTeamId: () => "team", otherPlayersInfo: {}, otherPlayers: {},
    playerMesh: { position: { x: 0, y: 0, z: 0 } }, UNIT_METERS: 10,
    allMapMode: false, spectatorMode: false, scene: {}, currentBoatType: "destroyer",
    PERISCOPE_DEPTH: -0.2, zoomLowMode: false, cheatVisuMode: false,
    isLineOfSightClear: () => true, isTorpedoRadarVisible: () => true,
    _visuOccludedByIsland: () => false, _visuWorldToScreen: () => ({ x: 10, y: 20 }),
    _getVisuLabel: () => label, _visuLabels: [label],
    selectedTorpedoKey: "remote:t", selectedDroneKey: null,
    document: { getElementById: () => tip },
    worldToRadar: () => ({ x: 10, y: 20 }),
    radarCanvas: { getBoundingClientRect: () => ({ left: 0, top: 0 }) },
});
for (const name of ["buildTorpedoTooltipText", "updateRadarTooltip", "updateVisuLabels"]) {
    const match = source.match(new RegExp("^function " + name + "\\([^]*?^}", "m"));
    assert.ok(match, name);
    vm.runInContext(match[0], context);
}

let checks = 0;
for (const ownerId of ["owner", "enemy"]) {
    for (const phase of ["initial", "lost", "absent"]) {
        const r = { ownerId, kind: "acoustic", x: -2, y: -1, z: 0,
            mesh: { isEnabled: () => true, position: { x: -2, y: -1, z: 0 } } };
        // Les memes coordonnees publiques peuvent preceder ou suivre un verrou.
        if (phase !== "absent") Object.assign(r, { tx: -32, ty: -1, tz: 40 });
        context.remoteTorpedoes.t = r;
        context.updateRadarTooltip({});
        context.updateVisuLabels();
        for (const text of [context.buildTorpedoTooltipText("t"), tip.textContent, label.textContent]) {
            assert.match(text, /Point de référence:/);
            assert.doesNotMatch(text, /acquisition|acquis|activée|verrou|Dist cible/i);
            assert.equal(text.includes("indisponible"), phase === "absent");
            checks += 3;
        }
        if (phase !== "absent") {
            assert.match(context.buildTorpedoTooltipText("t"), /Point de référence: 0\.50 km/);
            assert.equal(label.textContent, "Point de référence: 500 m");
            assert.match(tip.textContent, /Point de référence: 0\.50 km/);
            checks += 3;
        }
    }
}
console.log(`${checks} client torpedo reference checks passed`);
