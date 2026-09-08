# Architecture technique — Virtual World

Document de référence pour comprendre le fonctionnement client/serveur du jeu, les events réseau, les pipelines de tir, et les responsabilités de chaque côté.

## Stack et fichiers

```
server.py        ~4000 lignes  Flask + flask-socketio (eventlet) + simu serveur
static/game.js   ~5400 lignes  Client BabylonJS monolithique (pas de modules)
templates/
  index.html     page de jeu, charge game.js?v=N (cache-bust)
  aide.html      manuel utilisateur
boats/
  destroyer.json specs (vitesse, armement, dégâts, portées)
  submarine.json idem
maps/
  world*.json    cartes (sol + îles polygonales)
config/
  conffile.json  port serveur, durée jour
certs/           cert SSL local
logs/
  server.log     RotatingFileHandler 10 MB × 3 (basicConfig INFO)
```

Lancement : `./start.sh` (logfilter active). Le serveur tourne en HTTPS sur `config.server.port` (défaut 7000).

## Modèle réseau

**Transport** : SocketIO (websockets), engine.io. Le client émet/écoute des events nommés ; le serveur fait pareil avec `socketio.emit(...)` et `@socketio.on(...)`.

**Pattern de broadcast** :
- `emit("event", data, broadcast=True, include_self=False)` — relais à tous sauf l'émetteur (peu utilisé maintenant car le serveur génère lui-même les events).
- `socketio.emit("event", data)` — broadcast à tous.
- `socketio.emit("event", data, to=sid)` — destinataire unique (resync compteurs munition, alerts, position_correct).

**Tick rate** :
- Client → serveur `move` : 50 ms en réseau rapide, 100 ms en réseau lent (adaptatif selon RTT — voir ci-dessous).
- Serveur → client : 50 ms via `bot_ticker` (`BOT_TICK_INTERVAL = 0.05`) pour `player_moved` (bots), `torpedo_state`, `drone_state` (100 ms), `integrity`, etc.

**Compression** : `compression_threshold=0` dans le constructeur SocketIO active la compression per-message deflate sur toutes les frames. Réduit la bande passante, surtout utile sous charge multi-joueurs ou sur réseau congestionné (4G). N'améliore pas la latence.

**Mesure RTT applicatif** :

Le client émet `ws_ping { ts: Date.now() }` toutes les 200 ms. Le serveur répond immédiatement `ws_pong { ts, sts }` (où `sts = time.time()` est le timestamp serveur). Le client calcule le RTT = `now - data.ts` et agrège 50 samples sur 10 s. Toutes les 10 s, il logue les stats (médiane, p95, max, directionnel →/←) et émet `ws_rtt_report` au serveur pour les logs.

`sts` permet d'isoler les deux demi-trajets (`→ = sts×1000 - ts`, `← = now - sts×1000`) — ces valeurs sont biaisées par le décalage d'horloge client/serveur et ne sont pas de vraies mesures directionnelles. Seul le RTT total (aller-retour) est fiable.

**Taux d'émission `move` adaptatif** :

```
RTT médiane < 200 ms → MOVE_EMIT_INTERVAL = 50 ms  (20 Hz — fibre/LAN)
RTT médiane > 200 ms → MOVE_EMIT_INTERVAL = 100 ms (10 Hz — 4G/réseau lent)
```

Détection automatique après les 10 premières secondes de mesure. Un log `[webSocket]` est émis dans `server.log` à chaque changement de taux. Le taux revient à 20 Hz si le réseau s'améliore.

**Diagnostic WebSocket** (`cheat "logs"`, catégorie `webSocket`) :

Logs toutes les 10 s dans `server.log` :
```
[webSocket] RTT médiane=Xms p95=Yms max=Zms n=N (→Ams ←Bms) | move(biaisé) avg=...ms n=...
```
Le `move(biaisé)` est la latence apparente des events `move` côté serveur (`time.time() - data._ts`), biaisée par le décalage d'horloge client/serveur (~200ms typiquement) — ce n'est PAS de la vraie latence réseau. Utiliser uniquement `RTT médiane` pour évaluer les performances.

Valeurs de référence mesurées :
| Réseau | RTT médiane | p95 | move/10s |
|---|---|---|---|
| Fibre locale | 9–16 ms | 35–120 ms | ~195 (20 Hz) |
| 4G | ~500 ms | variable | ~100 (10 Hz, adaptatif) |

**Gestion mémoire client** : les meshes BabylonJS temporaires doivent libérer leur matériau et leurs textures avec `dispose(false, true)` lorsqu'ils en sont propriétaires. Les points de traînée des torpilles partagent un matériau unique, utilisent `mesh.visibility` pour leur fondu et sont plafonnés à 2 000 meshes dans toute la scène. L'overlay FPS affiche `scene.meshes.length`, `scene.materials.length` et le nombre de points de traînée afin de détecter une accumulation pendant les tests longs.

**Garde-fous d'état serveur** : au maximum 32 bots, 8 bateaux par joueur, 256 balises sonar actives, 256 balises passives et 1 000 mines peuvent coexister. Ces plafonds empêchent les cheats de ravitaillement/création de produire une croissance mémoire illimitée.

## Architecture serveur authoritaire

**Principe** : pour tout ce qui a un enjeu de gameplay (tirs, dégâts, mort), le client n'envoie qu'un *intent* et le serveur arbitre. Le client ne décide **jamais** des dégâts qu'il subit ou qu'il inflige, ni de sa propre mort, ni de la consommation de ses munitions.

**Périmètre** :

| Composant | Authoritaire | Note |
|---|---|---|
| Position joueur | Client (validé serveur, étape 1) | `validate_player_move`, anti-cheat de base |
| Rotation, rudder, vitesse joueur | Client | Transmis dans `move` |
| Position bots | Serveur | `update_bot` |
| Torpilles (toutes) | Serveur | Acquisition, évitement d'îles, hits, splash |
| Drones (auto + manuel) | Serveur | Recovery, autonomie, steering manuel via `drone_steer` |
| Grenades | Serveur | Trajectoire balistique + explosion à `targetDepth` |
| Cannon / DCA | Serveur | Hit/miss, dégâts différés à l'arrivée du projectile |
| Balises sonar | Serveur | Ammo, position prise du joueur côté serveur |
| Leurres acoustiques | Serveur | Ammo, position et lid alloués serveur |
| Mines (3 types) | Serveur | Pose, armement après délai, déclenchement par proximité, splash, chaîne d'explosions |
| Multi-bateaux humains | Serveur | `add_player_boat`, autopilote `update_human_autopilot`, retrait après naufrage |
| Intégrité humaine | Serveur | `apply_player_damage`, regen, danger zone, profondeur excessive sub |
| Intégrité bots | Serveur | `bot_apply_damage` |
| Sinking (mort) | Serveur | `sink_player` / `sink_bot` émettent `boat_sunk` |
| Compteurs munitions | Serveur | Resync via events dédiés |
| Cycle jour/nuit | Serveur (toggle relayé) | État partagé, `day_cycle` |
| Sonar passif (révélation) | Client | Calcul local depuis les `move` reçus |
| Détection visuelle / drones amis | Client | Pas d'enjeu de tir |

**Hors périmètre** : les calculs purement informationnels (sonar passif, radar) restent côté client — un client modifié verrait juste plus, mais ne peut pas tirer plus loin que la portée d'arme imposée par le serveur.

## Cycle de vie d'un joueur

### Connexion

Client → `select_boat { boatType }` → Serveur `handle_select_boat` :
1. Génère un `player_id` (8 chars uuid).
2. Charge `boats/<type>.json`.
3. Cherche une position de spawn aléatoire (`random_ocean_position`, distance min/max d'autres joueurs, marge îles).
4. Stocke `players[sid] = { id, boatType, boat, position, rotation, ... }`.
5. Initialise tous les compteurs munition (`init_torpedo_ammo_for_sid`, `init_drone_ammo_for_sid`, `init_grenade_ammo_for_sid`, `init_cannon_ammo_for_sid`, `init_beacon_ammo_for_sid`, `init_lure_ammo_for_sid`).
6. Initialise l'intégrité (`init_player_integrity` : 100, regen budget plein).
7. Émet `init` au sid avec : world, playerId, boat, players actuels, position, rotation, day cycle, **tous les compteurs munition**, liste balises actives.
8. Émet `player_joined` à tous les autres.

### En jeu (player_moved)

Client → `move { position, rotation, rudder, reverse, speedRatio }` toutes les 50 ms.

Serveur `handle_move` :
1. `validate_player_move(p, new_pos, world, now)` :
   - Hors monde ? `False, "out_of_bounds"`.
   - Sur île ? `False, "on_island"`.
   - Profondeur impossible ? Sub : `y > surface+0.1` ou `y < seabed-0.5`. Destroyer : `|y - flotation_y| > 0.5`.
   - Distance entre `last_pos` et `new_pos` > `vmax × dt × 3` ? `False, "speed"`. Tolère un saut > 200 u (cheat `move`).
2. Si invalide → `position_correct { x, y, z, rotation, reason }` au sid. Le client se téléporte à cette position et reset speed/rudder.
3. Si valide → met à jour `players[sid]`, broadcast `player_moved` à tous sauf le sid.

### Déconnexion

Serveur `handle_disconnect` : nettoie tirs en vol (torpedoes_server, drones_server, grenades_server), compteurs munition, état intégrité. Broadcast `player_left`.

### Mort

Serveur `sink_player(sid, p, attacker_id)` :
1. Détruit toutes les torpilles, drones et grenades en vol du défunt (avec explosion visuelle).
2. Broadcast `boat_sunk { victimId, attackerId }`.
3. Le joueur reste dans `players` (en pratique le client se reconnecte ou `select_boat` à nouveau).

Côté client `socket.on("boat_sunk")` : si `victimId === playerId` → `startSinking(attackerId)` (tilt + bannière). Si `attackerId === playerId` → `showKillBanner` (kill confirmé).

## Pipeline de tir générique

Tous les tirs suivent ce pattern :

```
Client                   Serveur
  |                        |
  |---fire_intent--------->|
  |                        | valide (sub immergé ?, ammo, portée, cible existe)
  |                        | décrémente ammo
  |<--*_count(s)-----------|  resync munition au tireur
  |                        |
  |                        | spawn dans la simu
  |<--state/launched-------| broadcast à tous (rendu visuel)
  |                        |
  |                        | tick (50 ms) : avance, applique hits/dégâts
  |<--state-(N)------------| 
  |                        |
  |                        | hit !
  |<--exploded/dead/hit----| broadcast
  |<--integrity------------| (cible humaine : cache d'affichage)
  |                        |
```

### Torpilles (`torpedo_fire` → `torpedoes_server`)

**Intent client** :
```js
socket.emit("torpedo_fire", {
  kind: "acoustic" | "wireGuided" | "autonomous",
  targetId: <playerId> | undefined,
  fixedTarget: { x, z, beaconBid? } | undefined
});
```

**Serveur `spawn_torpedo`** :
- Valide : kind connu, ammo, filoguidée pas déjà active, cible (joueur ou point fixe), distance ≤ `maxRangeMeters`.
- Spawn 1.5 u devant le bateau du tireur (`-cos(rot), sin(rot)`).
- Alloue `tid` unique par tireur (`next_torpedo_tid[pid]`).
- Emet `torpedo_state` (1ère trame) et `torpedo_alert` à la cible humaine si applicable.

**`update_server_torpedoes(dt, world)` dans `bot_ticker`** :
- Pour chaque torpille active :
  - Phase pré-activation (`traveled < activation`) : cap vers `initialTarget`.
  - Phase active acoustique : `torpedo_pick_acoustic(t)` → meilleur ratio bruit/r² parmi joueurs+bots audibles + leurres serveur situés dans le cône avant `radarConeDeg`. Notifie via `torpedo_acquisition` la cible quand `acquiredBoatId` change.
  - Phase active autonome : `torpedo_pick_radar(t, world)` (cône `radarConeDeg`, portée `radarRangeMeters`, LOS clair) en priorité, fallback acoustique. Toujours émettre `torpedo_acquisition` aux cibles humaines.
  - Filoguidée (`active_wire_torpedoes[pid]`) : applique `wireYaw`/`wirePitch` reçus via `torpedo_steer`.
  - Évitement d'îles : `torpedo_avoid_island(t, des_x, des_z, horizon, world)` cherche par dichotomie ±10°→±90° une déviation libre.
  - Avance, plafond `TORPEDO_CEILING_Y = -0.2`.
  - Collisions : joueurs (humains+bots) ≤ 3 m direct (`damage`), ≤ 10 m proximity (`damage * 0.5`). Balises sonar ≤ 1 u (destruction). Leurres ≤ 3 m. Île sur le segment.
- À l'explosion (`explode_server_torpedo`) : `torpedo_exploded` + `torpedo_dead` à tous, `apply_player_damage` direct ou splash, `bot_splash_damage`, destruction des leurres dans le rayon, libération du slot wireGuided.

**Intent steering filoguidée** :
```js
socket.emit("torpedo_steer", { yaw: -1|0|+1, pitch: -1|0|+1 });
```
Change-only : émis seulement quand l'état des touches change.

**Auto-destruction** :
```js
socket.emit("torpedo_self_destruct", { kind?: ..., tid?: ... });
```

### Cannon / DCA (`cannon_fire`)

**Intent** :
```js
socket.emit("cannon_fire", {
  kind: "cannon" | "antiAircraft",
  targetType: "boat" | "drone" | "beacon",
  targetId? | ownerId+did | bid,
});
```

**Serveur `fire_cannon_intent`** :
- Valide : kind, ammo, sub immergé non, cible existe, distance ≤ portée.
- Calcule `hit_probability(kind, target_type, dist_m, range_m)` (cannon vs boat 1→0.3 dégressif, DCA vs drone 0.9→0.3, DCA vs boat 1.0, cannon vs drone refusé).
- Calcule `endX/Y/Z` (avec offset miss aléatoire si pas hit).
- Broadcast `cannon_fire { shooterId, kind, startX/Y/Z, endX/Y/Z, arcHeight, duration, impact }`.
- Pour un tir humain réussi : `socketio.start_background_task` attend
  `flight_seconds` puis :
  - boat → `cannon_hit` + `apply_player_damage` ou `bot_apply_damage`.
  - drone → `kill_server_drone(reason="shot")`.
  - beacon → `sonar_beacon_destroyed`.

**Bots tirent via** `bot_fire_cannon` et `bot_fire_aa`. Le canon consomme ses
munitions immédiatement puis place les impacts réussis dans la file déterministe
de `Sim`; `update_pending_cannon_hits()` applique les dégâts au tick prévu et
émet `CannonHit`. La DCA conserve son traitement Socket.IO différé.

### Grenades (`grenade_fire`)

**Intent** :
```js
socket.emit("grenade_fire", { side: "left" | "right", depthMeters });
```

**Serveur `spawn_grenade`** :
- Valide : destroyer, ammo, profondeur 0-500 m.
- Spawn à 1.5 u côté bateau, vélocité latérale `±GRENADE_LATERAL_SPEED`, `vy = GRENADE_INITIAL_VY`.
- Broadcast `grenade_launched { shooterId, gid, x, y, z, vx, vy, vz, targetDepth, sinkSpeed }`.

**`update_server_grenades(dt, world)`** :
- Phase air : gravité (`vy -= GRENADE_GRAVITY * dt`), avance jusqu'à `y ≤ 0`.
- Phase eau : descend à `sinkSpeedU` jusqu'à `targetDepthU`.
- Boom → `explode_server_grenade(g)` :
  - `grenade_exploded { id, gid, x, y, z, damage }`.
  - `bot_splash_damage` (rayon BOT_SPLASH_RADIUS_M = 200 m, fixe).
  - `player_splash_damage` (rayon = `effectRadiusU` du JSON, en proportion 1 - dist/r).
  - Destruction des leurres dans le rayon.

**Côté client** : `spawnGrenadeTrajectory` au `grenade_launched`, anime localement la trajectoire pour fluidité, mais clamp visuellement à `targetDepth` en attendant `grenade_exploded`. À la réception, retire le mesh local par `(shooterId, gid)` puis spawn l'explosion visuelle.

### Drones (`drone_launch` / `drone_steer` / `drone_recall` / `drone_self_destruct`)

**Intent launch** :
```js
socket.emit("drone_launch", { kind: "automatic" | "manual" });
```

**Serveur `spawn_drone`** :
- Valide : sub non immergé, ammo, manuel pas déjà actif.
- Auto : direction dispersée par rapport aux autres autos en l'air (recherche d'angle max-gap).
- Manuel : direction = cap du bateau.
- Spawn à `altitude_u`, vitesse `speedUS = speed × 0.514444`, autonomie `autonomy_km × 1000`.

**`update_server_drones(dt, world)`** :
- Auto : avance, rebond aux bords du monde, retour quand `remaining ≤ dist_to_owner × 1.25`.
- Manuel : applique `steerYaw`/`steerThrottle`/`steerClimb` du tireur (turn_rate 0.6 rad/s, accel `maxSpeed × 0.15`, climb 4 u/s = 40 m/s). Plancher `floor_island + 5 m`, plafond 1000 m.
- Recovery : `returning && dist_to_owner ≤ speed × dt + 0.5 u && owner_visible` (sub non immergé) → `kill_server_drone(reason="recovered", refund=True)` → +1 ammo + `drone_counts` au tireur.
- Crash autonomie : `traveled ≥ autonomy` → `drone_dead reason="crashed"`.
- Émission `drone_state` à 100 ms.

**Intent steer** (manuel uniquement, change-only) :
```js
socket.emit("drone_steer", { yaw: -1|0|+1, throttle: -1|0|+1, climb: -1|0|+1 });
```

### Balises sonar (`sonar_beacon_place` / `sonar_beacon_destroy`)

**Intent place** : payload vide (`{}`), le serveur prend la position du joueur.

**Serveur** : valide ammo + sub non immergé, alloue `bid`, stocke dans `sonar_beacons[bid]`, broadcast `sonar_beacon_placed`. Décrément ammo + `beacon_count` au tireur.

**Pings** : `sonar_beacon_ticker()` (background task indépendante) émet `sonar_beacon_ping { bid, x, z, at }` à chaque `SONAR_BEACON_PING_INTERVAL` (30 s).

**Destruction** : `sonar_beacon_destroy { bid }` accepté de tout joueur (ou triggered par hit serveur).

### Leurres acoustiques (`lure_drop`)

**Intent** : payload vide, le serveur calcule la position 1.5 u derrière le bateau.

**Serveur** : valide ammo, alloue `lid`, stocke dans `server_lures[(pid, lid)]` avec `expiresAt`, broadcast `lure_dropped`. Décrément + `lure_count` au tireur. Les leurres sont consommés automatiquement à expiration ou par explosion proche.

**Effet** : `torpedo_pick_acoustic` itère `server_lures` comme cible candidate (bruit/r²). Une torpille acoustique peut être leurrée.

### Mines (`mine_place` / `mine_disarm`)

**Trois types** définis dans `boats/*.json` (`mineSurf`, `mineBottom`, `mineSuspended`) avec `{ number, delay, damage, range }`.

**Intent place** :
```js
socket.emit("mine_place", { kind: "surface" | "bottom" | "suspended", depthMeters? });
```
- `surface` : y = 0.
- `bottom` : y = `SEABED_FLOOR_Y` (-49 u).
- `suspended` : y calculé à partir de `depthMeters` (profondeur sous la surface en mètres, clampé 1–495).

**Serveur `handle_mine_place`** : valide l'identité et le payload, puis délègue à
`simulation.Sim.place_mine()`. La simulation valide la limite mondiale, les
munitions et le type, utilise la position du bateau, alloue `mid` par tireur,
stocke la mine avec `armAt = now + delay × 60 s`, puis émet `mine_placed`. Cette
même méthode autoritaire est utilisée par le serveur live et l'environnement
headless RL.

**Intent disarm** :
```js
socket.emit("mine_disarm", { ownerId, mid });
```
Conditions : être le poseur ET à ≤ 200 m de la mine. La munition est restituée, broadcast `mine_dead`.

**`Sim.update_server_mines(dt, world)` dans la boucle de simulation** :
- Armement : si `now >= armAt`, `armed = True` + emit `mine_armed`.
- Détection bateaux dans le rayon (distance horizontale uniquement). Logique d'attente : la mine mémorise la **distance min** atteinte par chaque bateau dans la zone (`m["watch"][pid]`). Tant que le bateau se rapproche, rien. Dès qu'il commence à s'éloigner (distance > min précédent + EPS), la mine **explose** et le bateau est crédité comme déclencheur. Si le bateau quitte la zone, son entrée est nettoyée.
- Pas d'autopilote, pas de mouvement de la mine.

**`Sim.explode_server_mine(mine, trigger_id)`** :
- Émet `mine_exploded { ownerId, mid, kind, x, y, z, range }` puis `mine_dead`.
- Splash damage proportionnel : `damage × (1.0 - 0.5 × dist/range)` (1×damage au centre, 0.5×damage à `range`). Itère humains+bots, distance horizontale. Applique via `apply_player_damage` / `bot_apply_damage`. `attacker_id = trigger_id` (ou `ownerId` si pas de trigger).
- **Chaîne d'explosions** : toutes les mines armées dans le rayon de cette explosion sont déclenchées en cascade (`_chain_visited` évite les boucles infinies).

**Destruction par autres armes** :
- **Torpille proximité ≤ 80 m** : déclenche l'explosion de la mine si activée, sinon destruction silencieuse mutuelle. La torpille est toujours détruite.
- **Canon / DCA** : peut viser une mine de **surface** (UI : sélection mine surface autorisée). Déclenche l'explosion complète.
- **Grenade** : `explode_server_grenade` itère les mines `bottom` et `suspended` dans son rayon → `explode_server_mine`.

**Visibilité radar côté client** :
- `mineRevealedUntil[key]` (10 s) marqué par tout ping (mon ping ou ping de balise) qui couvre la mine.
- **Surface** : visible si LOS clear depuis le joueur (comme une balise).
- **Bottom** : révélée seulement si dist `≥ 2 × range` (d'où le ping).
- **Suspended** : révélée par tout ping qui la couvre.
- Mesh 3D toujours visible (pas de filtre clip plane), pratique en plongée.

### Multi-bateaux par joueur (`add_player_boat` / `set_active_boat`)

**Globals serveur** :
- `human_owner_sid[ghost_sid] = sid_humain` — mapping retour.
- `player_boats_sids[sid_humain] = [sid1, sid2, ...]` — premier = primaire (`request.sid`).
- `autopiloted_sids` — set de sids actuellement en autopilote.

**Intent `add_player_boat`** :
```js
socket.emit("add_player_boat", { boatType: "submarine" | "destroyer" });
```
Cheats clients : `addsub` / `adddest`. Spawn 100 m à tribord du bateau actif, même cap. Si la position est sur une île, fallback `random_ocean_position`.

**Serveur `handle_add_player_boat`** :
- Crée `players[ghost_sid]` avec un nouveau `playerId` (UUID). `ghost_sid = f"__own__{request.sid}__{n}"`.
- Initialise toutes les ammos + intégrité comme un nouveau joueur.
- Ajoute à `human_owner_sid` + `player_boats_sids` + `autopiloted_sids`.
- Broadcast `player_joined` (les autres joueurs voient un participant indépendant).
- Émet `own_boat_added` au propriétaire avec specs + ammos.

**Intent `set_active_boat`** :
```js
socket.emit("set_active_boat", { bsid: <ghost_sid_or_null> });
```
Émis par le client à chaque Tab (Tab/Shift-Tab cyclent `activeBoatIndex`). `bsid: null` = bateau primaire.

**Serveur `handle_set_active_boat`** : passe les autres bateaux du joueur en `autopiloted_sids`. Reset le state autopilote du bateau qu'on reprend.

**`update_human_autopilot(p, dt, world)`** :
- Lit le dernier `rudder/speedRatio/reverse` reçu via `move`.
- Machine à états (`p["_autopilot_state"]`) :
  - `cruise` (défaut) : avance avec rudder/speedRatio figés.
  - Si `is_in_danger_zone(here)` → `backup` : marche arrière à 0.5×, pas de rudder.
  - Sinon, si `is_in_danger_zone(150 m devant)` → `stopped`.
  - `backup` → `stopped` quand sort de la danger zone.
- Émet `player_moved` à 20 Hz (broadcast à tous, incluant `integrity`).

**Routage des intents** : helper `resolve_acting_sid(request_sid, data)` :
```python
def resolve_acting_sid(request_sid, data):
    bsid = (data or {}).get("bsid")
    if bsid and human_owner_sid.get(bsid) == request_sid and bsid in players:
        return bsid
    return request_sid
```
Tous les handlers d'action (`move`, `torpedo_*`, `cannon_fire`, `grenade_fire`, `drone_*`, `lure_drop`, `sonar_beacon_*`, `sonar_ping`, `mine_place`, `mine_disarm`) appellent ce helper et utilisent `acting_sid` au lieu de `request.sid` pour ammos/positions.

**Routage des emit count(s)** :
- `_owner_socket_sid(sid)` → sid réel du propriétaire (humain) ou `None` (bot).
- `_bsid_for(sid)` → ghost sid si secondaire, `None` si primaire.
- Tous les `emit_*_count(s)` envoient `{..., bsid}` au socket du propriétaire. Côté client, dispatch dans `boatAmmo[bsid]` ; UI mise à jour seulement si bateau actif.

**Naufrage d'un bateau secondaire** :
- `sink_player(sid, p)` : marque `p["sunk"] = True`, retire de `autopiloted_sids`, émet `boat_sunk` (broadcast) + `own_boat_sunk { bsid, playerId }` au propriétaire.
- Background task `_retire_secondary` : 35 s plus tard, cleanup ammos + retire de `players` + `human_owner_sid` + `player_boats_sids`. Émet `player_left` (broadcast).

**Disconnect** : itère `player_boats_sids[sid]` pour nettoyer chaque bateau secondaire (player_left, ammos, tirs en vol).

**`integrity` dans `player_moved`** : pour permettre l'affichage de l'intégrité dans le tooltip d'un bateau distant cliqué, le champ `integrity` (0-100) est inclus dans **tous** les `player_moved` (humains, autopilotés, bots).

## Intégrité et dégâts

### Source des dégâts

Tous les chemins passent par `apply_player_damage(sid, p, damage, attacker_id)` (humains) ou `bot_apply_damage(sid, bot, damage, attacker_id)` (bots) :

1. **Hit direct torpille** : `update_server_torpedoes` détecte collision joueur ≤ 3 m → `explode_server_torpedo(direct_hit_id=p["id"], damage=t["damage"])`.
2. **Splash torpille** : `≤ 10 m → damage × 0.5` direct, ou splash radius BOT_SPLASH_RADIUS_M = 200 m sur tous les bateaux dans le rayon.
3. **Splash grenade** : `effectRadiusU` (= effectRangeMeters / 10) du JSON.
4. **Cannon hit** : `_delayed_boat()` après `flight_seconds` (cible boat).
5. **DCA hit boat** : pareil avec `damage = 1` typiquement.
6. **Danger zone autour des îles** : 1 pt/seconde en `update_player_integrity`. Polygone outer = polygone d'île agrandi de 3 u (30 m).
7. **Profondeur excessive sub** : `y < max_dive_y` → `0.5 × overshoot_m × dt` par seconde.
8. **DCA bot vs joueur humain** : `bot_fire_aa` → kill drone uniquement (pas de dégâts au pilote).

### Régénération

`update_player_integrity` à chaque tick :
- Pas de regen pendant `REGEN_DELAY_S = 5 s` après un dégât.
- Burst budget `REGEN_MAX_BUDGET = 10 pts` (consommé) puis épuisement.
- Total session `REGEN_TOTAL_INITIAL = 20 pts` cumulés sur toute la partie.
- Taux : `REGEN_RATE_PER_S = 10 / (10 × 60)` ≈ 1/60 pt/s (10 pts en 10 minutes).

### Notification au client

- À chaque baisse d'intégrité → `socketio.emit("integrity", {value}, to=sid)`.
- À 0 → `sink_player` puis broadcast `boat_sunk`.

Côté client, `socket.on("integrity")` met à jour `boatIntegrity` (cache d'affichage) ET déclenche un flash rouge (`damageFlashUntil`) sur baisse. En complément, `triggerDamageFlash(ex, ey, ez)` est appelé localement à la réception de `torpedo_exploded` / `grenade_exploded` / `cannon_hit` pour un flash immédiat sans attendre l'event `integrity` (latence RTT/2).

## Bots IA serveur

Un bot est un faux joueur :
- `sid = "__bot__<id>"` (préfixe pour distinguer).
- Présent dans `players[sid]` avec `is_bot: True` → passe par tout le pipeline normal (`player_joined`, `player_moved`, etc.).
- Stocké aussi dans `bots[sid]` avec état additionnel (waypoint, last_detected_ids, cooldowns).

**`bot_ticker` 20 Hz** dans `server.py:bot_ticker()` :
1. Calcule `dt`, log un warning si `gap > 150 ms`.
2. Skip si pas d'humains ni bots ni tirs en vol.
3. Cache le `world_data` (changement de carte invalide).
4. `update_server_torpedoes`, `update_server_drones`, `update_server_grenades`, `update_player_integrity` (tournent même sans bots).
5. Pour chaque bot : `update_bot(bot, dt, world_data)` (pilotage AI), puis broadcast `player_moved` toutes les 50 ms.
6. `socketio.sleep(0)` entre bots pour ne pas bloquer eventlet.

**`update_bot` (sub ou destroyer)** :
- Choix waypoint via `pick_bot_waypoint` (2-8 km, marge 300 m îles).
- Pilotage rudder progressif (P=2 sur l'erreur de cap), accel 0.4 u/s², croisière 60% du max.
- Sub : alterne périscope (~5 m) / profondeur 30-70% maxDepthMeters toutes les 20-60 s. **Jamais en surface**.
- Détection passive 1 Hz (`detect_enemies_passive`) → `last_detected_ids`.
- Tir torpilles (cooldown 8 s), canon (3 s, surface uniquement), DCA contre drones humains (0.4 s/tir, 1.5 s/drone).
- Sub immergé ne tire pas DCA.

**Désactivation tirs bots** : cheat `calmdown` toggle `bots_passive` global.

## Resync compteurs munition

À chaque consommation/recovery, le serveur émet au sid concerné :

| Event | Payload |
|---|---|
| `torpedo_counts` | `{ acoustic, wireGuided, autonomous }` |
| `drone_counts` | `{ automatic, manual }` |
| `grenade_count` | `{ count }` |
| `cannon_counts` | `{ cannon, antiAircraft }` |
| `beacon_count` | `{ count }` |
| `lure_count` | `{ count }` |

Le payload `init` (et `boat_changed` au cheat) inclut aussi tous ces compteurs pour le bootstrap : `torpedoCounts`, `droneCounts`, `grenadeCount`, `cannonCounts`, `beaconCount`, `lureCount`.

## Inventaire des events réseau

### Client → Serveur (intents)

| Event | Description |
|---|---|
| `select_boat` | Choix initial de bateau |
| `change_boat` | Cheat : bascule destroyer ↔ submarine |
| `move` | Position + rotation + rudder + reverse + speedRatio (50 ms) |
| `wake` | Spawn d'un dot de sillage côté ennemi |
| `toggle_day_cycle` / `day_cycle_done` | Cycle jour/nuit |
| `torpedo_fire` | Intent de tir torpille |
| `torpedo_steer` | Steering filoguidée (change-only) |
| `torpedo_self_destruct` | Auto-destruction torpille |
| `cannon_fire` | Intent tir cannon ou DCA |
| `grenade_fire` | Intent largage grenade |
| `drone_launch` | Intent lancement drone |
| `drone_steer` | Steering drone manuel (change-only) |
| `drone_recall` | Rappel drones d'un kind |
| `drone_self_destruct` | Auto-destruction drone |
| `sonar_beacon_place` | Intent largage balise |
| `sonar_beacon_destroy` | Destruction balise (par hit ou tir) |
| `lure_drop` | Intent largage leurre |
| `sonar_ping` | Ping sonar actif (broadcast) |
| `mine_place` | Intent pose de mine (kind + depthMeters pour suspended) |
| `mine_disarm` | Désamorçage d'une mine (poseur seul, ≤200 m) |
| `add_player_boat` | Cheat addsub/adddest |
| `set_active_boat` | Multi-bateaux : bascule du bateau piloté |
| `cheat_swap_to_bot` / `cheat_swap_to_self` / `cheat_bots_calmdown` | Cheats |
| `spawn_bot` | Cheat autosub/autodest |
| `admin_load_map` / `admin_create_map` / `admin_copy_map` / `admin_save_map` | Admin |
| `ws_ping` | Mesure RTT applicatif : `{ ts: Date.now() }` — serveur répond `ws_pong` immédiatement |
| `ws_rtt_report` | Rapport RTT agrégé (médiane, p95, max, n) envoyé toutes les 10 s au serveur pour les logs |

Tous les intents d'action (move, torpedo_fire, cannon_fire, grenade_fire, drone_*, lure_drop, sonar_*, mine_*) acceptent un champ optionnel `bsid` (ghost sid d'un bateau secondaire). En son absence, l'intent vise le bateau primaire.

### Serveur → Client (broadcasts ou unicasts)

| Event | Cible | Description |
|---|---|---|
| `init` | sid | Bootstrap complet |
| `player_joined` / `player_left` / `player_moved` | tous | Présence et mouvement |
| `boat_changed` | sid | Confirmation change_boat avec compteurs |
| `other_boat_changed` | tous | Autre joueur a changé de type |
| `position_correct` | sid | Anti-cheat : téléporte à dernière pos valide |
| `wake_spawned` | autres | Sillage d'un autre |
| `day_cycle_state` | tous | Snapshot cycle jour/nuit |
| `sonar_pinged` | tous | Ping sonar d'un autre |
| `sonar_beacon_placed` / `sonar_beacon_destroyed` / `sonar_beacon_ping` | tous | Balises |
| `lure_dropped` | tous | Visuel leurre |
| `torpedo_state` | tous | Snapshot torpille (50 ms) |
| `torpedo_alert` | cible | "Torpille lancée vers vous" |
| `torpedo_acquisition` | cible | acquired/lost/destroyed |
| `torpedo_exploded` / `torpedo_dead` | tous | Fin de torpille |
| `torpedo_counts` | sid | Resync ammo |
| `drone_state` | tous | Snapshot drone (100 ms) |
| `drone_dead` | tous | Fin de drone (avec `reason`) |
| `drone_shot` | tous | (legacy, encore utilisé pour `revealShooterFromFire`) |
| `drone_counts` | sid | Resync ammo |
| `grenade_launched` / `grenade_exploded` | tous | Vie de la grenade |
| `grenade_count` | sid | Resync ammo |
| `cannon_fire` | tous | Tracer projectile |
| `cannon_hit` | tous | Hit boat différé |
| `cannon_counts` | sid | Resync ammo (incl. `bsid`) |
| `beacon_count` | sid | Resync ammo (incl. `bsid`) |
| `lure_count` | sid | Resync ammo (incl. `bsid`) |
| `mine_counts` | sid | Resync ammo mines (incl. `bsid`) |
| `mine_placed` / `mine_armed` / `mine_dead` / `mine_exploded` | tous | Cycle de vie d'une mine |
| `integrity` | sid | Nouvelle valeur d'intégrité (incl. `bsid` pour multi-bateaux) |
| `boat_sunk` | tous | Joueur ou bot coulé |
| `own_boat_added` | sid | Confirmation `addsub`/`adddest` (specs + ammos du nouveau bateau) |
| `own_boat_sunk` | sid | Notif au propriétaire qu'un de ses bateaux secondaires a coulé |
| `ws_pong` | sid | Réponse au `ws_ping` : `{ ts, sts }` — ts est renvoyé tel quel, sts = timestamp serveur |
| `cheat_view_bot` / `cheat_view_self` / `cheat_bots_calmdown_state` | sid | Réponses cheats |
| `bot_spawned` | sid | Confirmation autosub/autodest |
| `admin_world_loaded` / `admin_save_ok` / `admin_error` | sid | Admin |

Les `*_count(s)` incluent désormais un champ `bsid` (`null` pour le bateau primaire, ghost sid pour un secondaire) afin que le client puisse dispatcher dans `boatAmmo[bsid]`. Les `player_moved` incluent un champ `integrity` (0-100) pour permettre l'affichage dans les tooltips radar des bateaux distants.

## Inventaire des fonctions principales

### Serveur (`server.py`)

**Géométrie / monde**
- `point_in_polygon(x, z, points)` — test point-dans-polygone.
- `point_on_any_island(x, z, world)` — test rapide pré-filtré AABB.
- `_ensure_island_bounds(world)` — cache AABB par île.
- `line_of_sight_clear(x1, z1, x2, z2, world)` — LOS échantillonnée 5 u.
- `distance_point_segment(...)` — distance projetée.
- `_danger_zones(world)` / `is_in_danger_zone(x, z, world)` — anneau autour des îles.

**Cycle de vie**
- `handle_select_boat` / `handle_disconnect` / `handle_change_boat`.
- `init_player_integrity` / `init_*_ammo_for_sid` (6 fonctions, une par type d'arme).

**Position**
- `validate_player_move(p, new_pos, world, now)` / `emit_position_correct`.
- `handle_move` (le seul handler avec validation anti-cheat).

**Torpilles**
- `boat_torpedo_specs(boat)` — defaults JSON.
- `torpedo_segment_blocked` / `torpedo_avoid_island` — évitement d'île.
- `torpedo_pick_acoustic(t)` / `torpedo_pick_radar(t, world)` — acquisition.
- `spawn_torpedo` (humain) / `spawn_bot_torpedo` (bot).
- `update_server_torpedoes(dt, world)` — tick principal.
- `explode_server_torpedo(t, direct_hit_id, damage, hit_target_id)`.
- `notify_torpedo_acquisition` / `emit_torpedo_state_broadcast`.
- Handlers : `torpedo_fire`, `torpedo_steer`, `torpedo_self_destruct`.

**Drones**
- `spawn_drone` / `kill_server_drone(d, reason, refund)` / `update_server_drones(dt, world)`.
- Handlers : `drone_launch`, `drone_steer`, `drone_recall`, `drone_self_destruct`, `drone_shot` (legacy).

**Grenades**
- `spawn_grenade` / `explode_server_grenade(g)` / `update_server_grenades(dt, world)`.
- Handler : `grenade_fire`.

**Cannon / DCA**
- `hit_probability(kind, target_type, dist_m, range_m)`.
- `fire_cannon_intent(sid, shooter, data)` (humain).
- `bot_fire_cannon(bot, target_player)` / `bot_fire_aa(bot, drone)` (bots).
- Handler : `cannon_fire`.

**Balises et leurres**
- Handlers : `sonar_beacon_place`, `sonar_beacon_destroy`, `lure_drop`.
- `sonar_beacon_ticker()` : background task de ping périodique.

**Mines**
- Handlers : `mine_place`, `mine_disarm`.
- `boat_mine_spec(boat, kind)` — lookup spec.
- `init_mine_ammo_for_sid` / `emit_mine_counts`.
- `Sim.place_mine(sid, player, kind, depth_m)` — validation et pose autoritaire.
- `Sim.update_server_mines(dt, world)` — armement + détection bateaux par CPA.
- `Sim.explode_server_mine(mine, trigger_id, _chain_visited)` — splash proportionnel + chaîne d'explosions.
- `simulation.mine_payload(mine)` — filtre pour broadcast.

**Multi-bateaux humains**
- Handlers : `add_player_boat`, `set_active_boat`.
- Helpers : `resolve_acting_sid`, `_owner_socket_sid`, `_bsid_for`.
- `update_human_autopilot(p, dt, world)` — autopilote bateau non actif.
- Cleanup différé `_retire_secondary` (background task) après naufrage d'un secondaire.

**Intégrité humaine**
- `apply_player_damage(sid, p, damage, attacker_id)` / `sink_player`.
- `player_splash_damage(ex, ey, ez, damage, attacker_id, radius_u)`.
- `update_player_integrity(dt, world)` — danger zone, profondeur excessive, regen.
- `emit_integrity(sid, p)`.

**Bots**
- `spawn_bot(boat_type)` / `sink_bot(sid, bot, attacker_id)` / `bot_apply_damage`.
- `bot_splash_damage` (rayon BOT_SPLASH_RADIUS_M = 200 m).
- `update_bot(bot, dt, world)` / `pick_bot_waypoint(bot, world)`.
- `detect_enemies_passive(bot, world)`.
- `bot_ticker()` — main loop 20 Hz.

### Client (`game.js`)

**Init**
- `selectBoat(type)` — UI de choix.
- `socket.on("init")` — bootstrap.
- `applyBoatConfig(boat, boatType, opts)` — config bateau (+ compteurs munition du serveur).
- `loadBoatModel` / `instantiateBoatFromContainer` — GLTF + cache.
- `buildWorld(world)` — construction îles, mer, sol.

**Boucle render**
- `scene.onBeforeRenderObservable.add(...)` ~4540 — appelée à chaque frame :
  - Anime grenades, torpilles, drones, lures, cannon tracers, ping waves.
  - Met à jour pilotage local (rudder, throttle, plongée).
  - Émet `move` toutes les 50 ms.
  - Met à jour caméra (FPV / drone / arc).

**Pilotage joueur**
- Lecture `keys[ArrowUp/Down/Left/Right/Space/X]` dans la boucle render.
- `boatSpeed`, `rudderAngle`, `diveRate`, `periscopeTarget`.

**Réseau (réception)**
- `player_moved`, `position_correct`, `player_joined`, `player_left`, `boat_changed`, `other_boat_changed`.
- `torpedo_*` → `remoteTorpedoes` indexé `ownerId:tid`.
- `drone_state` / `drone_dead` / `drone_counts` → `remoteDrones`, `activeDrones` (sous-set local).
- `grenade_launched` / `grenade_exploded` / `grenade_count` → `grenades[]` local pour rendu.
- `cannon_fire` → `spawnCannonTracer` + impact visuel.
- `cannon_hit` / `torpedo_exploded` → `triggerDamageFlash`.
- `integrity` → `boatIntegrity` (affichage) + flash sur baisse.
- `boat_sunk` → `startSinking` (si moi) + `showKillBanner` (si je l'ai tué).
- `sonar_pinged`, `sonar_beacon_*`, `lure_dropped` — visuels.

**Tirs (intents)**
- `fireTorpedo(kind)` → emit `torpedo_fire` (incl. `activationMeters` lu du champ UI).
- `fireCannon(kind)` → emit `cannon_fire` avec target.
- `launchGrenade(side)` → emit `grenade_fire`.
- `launchDrone(kind)` → emit `drone_launch`.
- `recallDronesByKind(kind)` → emit `drone_recall`.
- `placeSonarBeacon` → emit `sonar_beacon_place {}`.
- `dropAcousticLure` → emit `lure_drop {}`.
- `placeMine(kind)` → emit `mine_place` (avec `depthMeters` pour suspended).
- Bouton `D` mineDisarmBtn → emit `mine_disarm`.
- `pollWireSteer` / `pollDroneSteer` — change-only steering.
- **Tous** les emit d'intents passent par `withBsid(payload)` qui ajoute le `bsid` du bateau actif si secondaire.

**Multi-bateaux client**
- `localBoats[]` (entries `{ ghostSid, playerId, boat, sunk }`), `activeBoatIndex`, `activeBoat()`, `activeGhostSid()`.
- `boatAmmo[ammoKey]` — ammos par bateau (clé `"primary"` ou ghost sid).
- `selfControlledPlayerIds` — set des playerId simulés localement (le bateau actif).
- `switchActiveBoat(toIndex)` — bascule : reset état, recharge ammos, restaure vitesse depuis `lastServerSpeedRatio`, émet `set_active_boat`.
- `cycleActiveBoat(direction)` — Tab / Shift-Tab.
- `animateSecondarySinking(dt)` — anime localement les bateaux distants en train de couler (mes secondaires + autres joueurs via `remoteSinking[playerId]`).

**Sélection 3D au clic**
- `selectEntityFromPick(pickInfo)` — identifie l'entité touchée par scene.pick, applique la même sélection que le radar. Helpers `_findOtherPlayerIdFromMesh`, `_findMineKeyFromMesh`, `_findBeaconBidFromMesh`, `_findTorpedoKeyFromMesh`, `_findDroneKeyFromMesh`.
- Listeners `pointerdown`/`pointerup` `capture: true` qui détectent le clic court (déplacement ≤ 6 px, durée ≤ 500 ms) hors mode admin et hors aim.

**Radar et UI**
- `renderRadar()` ~2400 — canvas 2D : drones, bateaux, balises, torpilles, joueur, ping waves.
- `renderMinimap()`, `worldToRadar` / `radarToWorld`.
- `setIncomingTorpedoMessage(shooterId, tid, msg)` — bandeau "torpille X : état".
- Tooltip radar avec dist/altitude/vit selon la sélection.

**Visuels**
- `spawnGrenadeTrajectory` / `createExplosionVisual` / `spawnRemoteExplosion` / `spawnDroneCrashVisual` / `spawnDroneExplosionFlash`.
- `addTorpedoTrail(r)` — petits dots blancs sur la trajectoire.
- `spawnAcousticLureVisual` — disque sombre.
- `spawnCannonTracer(kind, ...)` / `spawnCannonImpactVisual`.
- `spawnWakeDot` — sillage local.

**Audio (cas particulier)**
- `triggerDamageFlash(ex, ey, ez)` — flash rouge écran sur explosion proche (latence zéro).

**Caméras**
- ArcRotateCamera principale, UniversalCamera FPV (cheat zoom), UniversalCamera drone manuel.
- `enterBotView` / `exitBotView` — cheat `bot`/`self`.

## Pièges réseau / synchronisation

**Jitter `speedRatio`** : NE JAMAIS recalculer `dist/dt` côté receveur. Toujours utiliser `data.speedRatio` transmis par l'émetteur dans `move` — le sonar passif clignoterait au seuil sinon.

**Cache du monde validation** : `_world_for_validation()` côté serveur invalide automatiquement quand `current_map_name` change.

**Eventlet et I/O** : tout fichier > 100 KB lu de manière synchrone bloque le thread serveur (et donc le bot_ticker → saccades). C'est pourquoi `_preload_asset_dir` charge tout en RAM au boot.

**Ordre de réception** : SocketIO garantit l'ordre par socket. Donc `torpedo_state`(N+1) arrive après `torpedo_state`(N), pas de risque d'inversion. Mais entre `torpedo_state` et `torpedo_dead` du même tireur, l'ordre est garanti aussi (FIFO sur le canal).

**Reconnexion** : un client qui se reconnecte fait un nouveau `select_boat` → nouveau `playerId`. Pas de session persistante.

## Constants critiques

| Côté | Constante | Valeur | Sens |
|---|---|---|---|
| client+serveur | `UNIT_METERS` / `UNIT_METERS_BOT` | 10 | 1 unité = 10 m |
| client | `SEABED_DEPTH_METERS` | 500 | profondeur seabed |
| client | `SEABED_FLOOR_Y` | -49 | y du seabed |
| serveur | `SEABED_FLOOR_Y` | -49.0 | idem |
| client | `PERISCOPE_DEPTH` | -0.5 | y de plongée détectable |
| client+serveur | `TORPEDO_CEILING_Y` | -0.2 | plafond torpille |
| client | `MOVE_EMIT_INTERVAL_NORMAL` | 50 | période move ms réseau rapide (20 Hz) |
| client | `MOVE_EMIT_INTERVAL_SLOW` | 100 | période move ms réseau lent (10 Hz, RTT > 200 ms) |
| client | `MOVE_EMIT_INTERVAL` | adaptatif | valeur courante — bascule entre NORMAL et SLOW |
| serveur | `BOT_TICK_INTERVAL` | 0.05 | période ticker s |
| serveur | `MOVE_VALIDATION_MARGIN` | 3.0 | tolérance vitesse |
| serveur | `DANGER_ZONE_OFFSET` | 3.0 | u, anneau île |
| serveur | `BOT_SPLASH_RADIUS_M` | 200.0 | splash bots |
| serveur | `REGEN_DELAY_S` | 5.0 | s avant regen |
| serveur | `REGEN_RATE_PER_S` | ~0.0167 | pts/s |
| serveur | `REGEN_MAX_BUDGET` | 10 | burst max |
| serveur | `REGEN_TOTAL_INITIAL` | 20 | session total |
| serveur | `SONAR_BEACON_PING_INTERVAL` | 30 | s entre pings |
| serveur | `CANNON_SHELL_SPEED_MS` | 500 | m/s |
| serveur | `AA_BULLET_SPEED_MS` | 1000 | m/s |
| serveur | `GRENADE_GRAVITY` | 18 | m/s² |
| serveur | `DRONE_DISCOVER_RADIUS_M` | 3000 | m |
| serveur | `DRONE_RECOVERY_DISTANCE_U` | 0.5 | u |
## Entraînement RL

Le pipeline entraîne des sous-marins et des destroyers en duel 1v1 sans serveur
Flask. Il réutilise directement `simulation.Sim` grâce à `headless.py` : les
règles d'armement, de dégâts, de sonar et de leurres sont donc celles du jeu
autoritaire. `TRAINING_RL.md` décrit les commandes et le diagnostic en détail.

La configuration `aisub_v14` entraîne un sous-marin.
Les adversaires BT sont configurés par coque, IA et poids. La politique reste
toujours un sous-marin ; elle affronte à parts égales `submarine/autosub` et
`destroyer/autodest`. Les impacts du canon des destroyers sont résolus selon
l'horloge de simulation et consomment les munitions comme sur le serveur live.

Un bot RL porte `external_control=true`. Dans ce mode, `Sim.update_bot()`
n'exécute aucun Behavior Tree et aucun tir réactif. La politique fixe seulement
les commandes ; `Sim.update_bot_external()` applique la physique à 20 Hz. La
politique prend une décision toutes les 0,25 s, en entraînement comme en live.

L'observation `sub_duel_v1` contient 32 valeurs normalisées : état propre,
munitions et cooldowns, bruit émis, dernier contact sonar passif, menace de
torpille et huit rayons anticollision égocentriques. Un adversaire non détecté
n'est jamais lu directement ; sa dernière position connue expire après 30 s.

L'action est `MultiDiscrete([5, 5, 5, 3, 2])` : gouvernail, vitesse, profondeur,
choix de tir (`aucun`, `acoustique`, `autonome`) et leurre. Une arme ne peut être
tirée que sur un contact datant de moins d'une seconde.

### Phase 1 : adversaire algorithmique

```bash
venv/bin/python train_ai.py --config configs/aisub_v14.json \
  --stage scripted --run-name aisub_v14_scripted \
  --resume models_rl/aisub_v13_scripted/best/best_model.zip
```

Les huit environnements affrontent un mélange équilibré de sous-marins
`autosub` et de destroyers `autodest`. Une évaluation agrégée se déroule sur
`world_testCombats.json` et conserve le meilleur modèle dans
`models_rl/aisub_v14_scripted/best/best_model.zip`.

### Phase 2 : ligue self-play

```bash
venv/bin/python train_ai.py --config configs/aisub_v14.json \
  --stage selfplay --run-name aisub_v14_selfplay \
  --resume models_rl/aisub_v14_scripted/best/best_model.zip
```

Le checkpoint initial et les snapshots périodiques alimentent le répertoire
`league/`. À chaque épisode, l'adversaire est choisi entre une politique
historique sous-marine et le mélange BT sous-marin/destroyer. Les politiques
RL décident à la même fréquence.

### Évaluation et jeu live

```bash
venv/bin/python evaluate_ai.py \
  models_rl/aisub_v14_selfplay/best/best_model.zip \
  --maps combats,testCombats \
  --opponents submarine/autosub,destroyer/autodest --episodes 100
```

Dans la console du navigateur, `spawnRlBot("aisub_v14_selfplay")` charge d'abord `best/best_model.zip`,
puis `policy_final.zip` si aucun meilleur modèle n'existe. La forme des espaces
d'observation et d'action est validée au chargement ; un échec replie le bot sur
`autosub` et écrit la cause dans le journal serveur.

### Phase 3 : politique destroyer

La configuration `aidest_v1` entraîne une politique distincte pour le destroyer.
L'observation `destroyer_duel_v1` contient 36 valeurs : état de navigation,
intégrité, bruit, munitions et cooldowns des torpilles, du canon, des grenades,
des leurres et du sonar actif, dernier contact, menace de torpille et huit rayons
anticollision. L'action `MultiDiscrete([5, 5, 5, 2, 2])` contrôle le gouvernail,
la vitesse, l'arme (`aucune`, `acoustique`, `autonome`, `canon`, `grenade`), le
leurre et le sonar actif.

La phase scripted oppose le destroyer à parts égales au meilleur sous-marin RL
gelé et à un mélange équilibré de `submarine/autosub` et
`destroyer/autodest` :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  venv/bin/python train_ai.py --config configs/aidest_v1.json \
  --stage scripted --run-name aidest_v1_scripted --device cuda
```

Le nombre de threads est limité car chaque worker charge la politique adverse
sur CPU. Après évaluation, la ligue destroyer peut reprendre le meilleur modèle
scripted avec `--stage selfplay --run-name aidest_v1_selfplay --resume <modele>`.
Les snapshots de cette ligue restent des destroyers, tandis que le sous-marin RL
gelé demeure dans le mélange d'adversaires.

L'évaluation et le chargement live précisent la coque contrôlée :

```bash
venv/bin/python evaluate_ai.py models_rl/aidest_v1_scripted/best/best_model.zip \
  --agent-boat-type destroyer --opponents submarine/autosub,destroyer/autodest
```

Dans la console du navigateur,
`spawnRlBot("aidest_v1_scripted", false, "", "destroyer")` charge le destroyer
RL. Un modèle incompatible replie désormais vers le BT correspondant à la coque
(`autosub` ou `autodest`).

#### Raffinement anti-sous-marin

`aidest_v2` reprend le meilleur checkpoint v1 et cible uniquement `autosub` et
le meilleur sous-marin RL, à parts égales et aux distances complètes. Les
commandes d'arme et de sonar maintenues pendant leur cooldown sont traitées
comme des attentes, sans pénalité répétée. Le taux d'apprentissage et l'entropie
sont réduits pour préserver les acquis du checkpoint :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  venv/bin/python train_ai.py --config configs/aidest_v2.json \
  --stage scripted --run-name aidest_v2_scripted \
  --resume models_rl/aidest_v1_scripted/best/best_model.zip --device cuda
```

#### Mines secondaires et télémétrie

`destroyer_duel_v2` étend l'observation à 40 valeurs avec les trois stocks de
mines et leur cooldown. L'action devient
`MultiDiscrete([5, 5, 5, 2, 2, 4])` ; la dernière valeur choisit `aucune`,
`surface`, `fond` ou `suspendue`. Une grenade demandée dans la même décision est
toujours prioritaire et empêche la pose de mine. Une mine coûte quatre fois plus
qu'un tir dans `aidest_v3`, afin qu'elle reste une option tactique secondaire.

Le placement est désormais exécuté par `simulation.Sim.place_mine()` en mode
serveur comme en headless. Les évaluations détaillent séparément torpilles,
canon, grenades et chaque type de mine. Le nouvel espace étant incompatible avec
les checkpoints destroyer précédents, v3 démarre une nouvelle politique :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  venv/bin/python train_ai.py --config configs/aidest_v3.json \
  --stage scripted --run-name aidest_v3_scripted --device cuda
```

Le run v3 affronte `submarine/autosub` et le meilleur sous-marin RL gelé avec
une probabilité de 50 % chacun. Son curriculum étend progressivement les
distances de 600-1 200 m vers 600-2 000 m. L'évaluation indépendante couvre les
deux familles d'adversaires :

```bash
venv/bin/python evaluate_ai.py \
  models_rl/aidest_v3_scripted/best/best_model.zip \
  --agent-boat-type destroyer --opponents submarine/autosub \
  --opponent-pools models_rl/aisub_v14_selfplay/best \
  --opponent-pool-boat-type submarine --episodes 100
```

Dans la console du navigateur,
`spawnRlBot("aidest_v3_scripted", false, "", "destroyer")` charge le meilleur
checkpoint v3 compatible.
