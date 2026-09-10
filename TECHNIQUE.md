# Architecture technique — Virtual World

Document de référence pour comprendre le fonctionnement client/serveur du jeu, les events réseau, les pipelines de tir, et les responsabilités de chaque côté.

## Etape 3 Torpilles Sans Cible (2026-09-09)

Absence de `targetId` (ou null) et de point manuel/memorise : les lanceurs humains
et `Sim.spawn_bot_torpedo[_autonomous]` acceptent un tir dans l'axe, avec
`initialTarget=None`, `targetId=None`, pitch zero et profondeur native conservee.
Aucun endpoint fictif ni lookup de cible cachee. Le controle de distance au point
est saute uniquement sans point ; `maxRange`, sorties de carte et collisions
restent natifs. Tout ID explicite invalide, inconnu ou masque par une ile est
rejete, meme accompagne d'un point fixe ; aucun fallback aveugle dans ce cas.
Les points connus copies et toutes les regles de selection/LOS existantes restent.

Avant activation, sans point : cap et profondeur tenus, aucun capteur. Apres
activation : acquisition acoustique/radar native seulement (cone, bruit/portee,
LOS, thermoclines), puis guidage et evitement existants. Activation humaine saisie
et clampee inchangee ; sans contact RL, activation du JSON (actuellement 500 m),
pas l'heuristique 500/200 m reservee aux contacts. Offset bot 4 m/humain 15 m et
profondeurs de lancement distinctes restent hors scope. La filoguidee humaine
sans cible garde le pilotage manuel, l'exclusivite et la destruction existants.

UI : premier clic sans selection ouvre la visee, clic radar = point fixe,
second clic sur le meme type = tir dans l'axe, ESC = annulation. Le bandeau
explicite ces choix ; aucun label ne pretend qu'une cible est acquise.
RL : actions armes 1/2 autorisees sans contact si munitions/cooldown disponibles,
dimensions/versions et rewards inchanges, cooldown 4 s. BT : action directe
`fire_torpedo_at_audible` peut tirer sans contact, cooldown natif 8 s respecte ;
contacts hors portee ne deviennent pas un tir aveugle. Les conditions des arbres
et le FSM `attack_torpedo_at_known` restent tactiquement dependants des contacts.

Regressions : `rl/test_targetless_torpedo.py`, handlers AST dans
`test_server_fire_los.py`, `tests/test_targetless_torpedo.js`, plus suites existantes.
Les politiques existantes peuvent gaspiller davantage de munitions : consequence
attendue, aucune compensation reward. Tous les scores historiques sont non
directement comparables ; aucune evaluation, formation, modification de modele,
ecoute serveur, livraison ou commit. Equite globale et parite navigateur/mobile
non prouvees. Cette section remplace les mentions historiques « etape 3 differee ».

Verification locale etape 3 : 241 tests Python passes sans skip, avec
`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1` et le venv existant ;
9 harnesses Node passes plus spectateur `--empty`, dont 32 controles client
targetless. Syntaxe JS, compilation Python ciblee et `git diff --check` passes.

## Trois Corrections Ciblees D'Equite (2026-09-09)

`bot_ai._drive_to_waypoint` conserve ses commandes throttle/rudder, rotation,
dt, profondeur et recuperations existantes. Avant d'ecrire XZ : limites fermees
`ground/2 - 4`, endpoint `geometry.point_on_any_island` et segment exact
`geometry.line_of_sight_clear`. Collision = XZ conserves, vitesse nulle et compteur
de blocage existant ; aucune nouvelle navigation/repulsion/teleportation.
Un bot deja dans une ile peut toujours choisir son waypoint de recuperation,
mais ne peut plus traverser le contour pour en sortir. Le mouvement externe Sim
reste inchange (controle endpoint seulement) : pas de preuve de parite physique totale.

`Sim.spawn_bot_torpedo` et `spawn_bot_torpedo_autonomous` initialisent le cap
horizontal a `(-cos(rotation), sin(rotation))`, comme le lanceur humain.
Le point observe XYZ reste copie dans `initialTarget` ; les snapshots restent
sans `targetId`, sans resolution de position cachee. Guidage preactivation,
acquisition reelle, perte de verrou et rayon de virage restent inchanges.
Offset bot toujours 0.4 u (4 m), maintenant vers l'avant ; humain toujours
1.5 u (15 m). Pitch initial toujours 0, profondeur bot toujours
`min(TORPEDO_CEILING_Y, by)` contre -0.3 u pour le destroyer humain : ces differences
restent differees. Le diagnostic autonome `pitch_init` est une estimation,
pas le pitch effectivement stocke au lancement. Aucun changement de pitch/guidage vertical.

Les trois affichages `updateRadarTooltip`, `buildTorpedoTooltipText` et
`updateVisuLabels` ne deduisent plus acquisition/activation de `tx/tz`.
Le paquet existant ne distingue pas point initial, dernier point acquis et verrou
courant : texte neutre **Point de référence**, distance au point si disponible,
sinon indisponible. Pas de nouveau booleen ennemi, pas de changement de protocole
ni restauration des notifications privees ; aucun verrou propre fiable transmis.
Les cercles preactivation restent des distances d'activation, pas une preuve de lock.

Regressions : `test_bt_movement.py`, `rl/test_launch_heading.py`,
`rl/test_bot_fire_los.py`, `rl/test_torpedo_guidance.py`,
`tests/test_torpedo_reference.js`. Tests locaux sans ecoute, sans pertes/victoires
attendues imposees. Scores historiques non directement comparables ; aucune
evaluation/training/promotion/modele modifie, aucun serveur/deploiement/commit.
Equite complete et parite navigateur/mobile/reseau non prouvees.
Decisions ouvertes : sonar canonique (front humain local de 5 s pour tous, ou
regle BT synchrone a specifier pour tous), canon (rejet actuel des tirs sur memoire
sans suivi, ou vraie balistique partagee sur point avec impact autoritaire).
Arbitrer les regles et valider le jeu avant de reprendre le plan RL ; aucune
nouvelle evaluation ni modification reward/schema autorisee par cette tranche.

Verification locale : 213 tests Python passes, aucun skip, via
`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 venv/bin/python -m unittest discover -v` ;
7 harnesses Node passes et variante spectateur `--empty`, dont 66 controles
de reference torpille. Syntaxe JS, compilation Python ciblee et `git diff --check`
passes. La fixture radar entrante oriente maintenant son tireur vers l'observateur,
sans modifier ses assertions ni les regles radar pour compenser le nouveau cap.

## Sortie De Carte Des Torpilles (2026-09-09)

`Sim.update_server_torpedoes` utilise le rectangle horizontal ferme
`[-ground.width/2, +ground.width/2] x [-ground.depth/2, +ground.depth/2]`,
sans marge ni limite verticale supplementaire. Toutes les torpilles deja dehors
sont supprimees avant tout guidage/capteur/collision, sans retour ni rebond.
Le segment est borne par la portee restante puis par sa premiere intersection
avec un bord s'il le franchit ; profondeur et distance cumulee utilisent ce
trajet raccourci. Atteindre exactement le bord ne constitue pas une sortie.
Les collisions existantes sur ce segment, bord inclus, ont priorite ; les centres
des bateaux, balises, leurres et mines hors carte sont exclus des collisions.
L'ordre historique des categories de collision n'est pas remanie.
Sans collision, sortie = suppression silencieuse, aucun blast/degat de sortie,
un seul `TorpedoDead(reason="map_bounds")`, notifications de fin et liberation
du slot filoguide existantes. Les autres morts gardent `reason=None` ; a egalite
exacte portee/bord, la fin de portee existante reste prioritaire.
`GameTrace` conserve `reason` via sa liste positive ; le paquet reseau
`torpedo_dead` reste ownerId/tid, avec nettoyage client existant sans nouveau JS.
L'absence autoritaire debloque normalement `waitForTorpedoes` en autogame.
Les mondes minimaux sans `ground` restent sans limite de carte (pas de dimension
factice nulle ou infinie) ; les cartes chargees utilisent leurs dimensions reelles.

Regressions sans ecoute : `test_torpedo_bounds.py` (quatre bords, coins,
premiere intersection, grand dt, pitch, trois guidages, portee, collisions,
purge avant acquisition, trace et fin de settling).
Modification source pour la prochaine session uniquement, apres redemarrage
autorise ; aucun processus live touche, aucun deploiement/entrainement/modele
modifie. Les etiquettes UI sont traitees dans la tranche distincte ci-dessus.

## Spectateur Sans Bateau (2026-09-09)

Accueil : **Observer la partie**, ou URL `/?spectate=1`. L'event `spectate`
inscrit uniquement `request.sid` dans `spectator_sids`, hors `players`, `bots`,
Sim, equipes, munitions et listes multi-bateaux. Pas de spawn, de slot humain,
de cible pour l'IA ni d'effet sur les conditions de fin autogame ; les traces
ne comptent donc pas l'observateur comme une unite supplementaire.

`GameSocketIO.on` enveloppe centralement tous les handlers enregistres : pour
un SID spectateur, seuls `spectate` (idempotent), `disconnect`, `list_teams`
et `ws_ping` passent. Toute autre commande renvoie `spectator_read_only`
avant d'appeler le handler, y compris `bsid` forge, selection/changement de bateau,
armes, sonar, teleportation, cheats, cartes, temps et commandes globales.
Un joueur deja cree ne peut pas convertir sa connexion en spectateur.
La deconnexion spectateur retire uniquement son SID ; un event applicatif forge
nomme `disconnect` est refuse tant que le transport considere le SID connecte.
Ce filtrage n'ajoute
aucun droit d'administration et ne remplace pas une authentification globale :
l'application reste publique, et la vue omnisciente est explicitement proposee.

Bootstrap `init` avec `spectator: true`, monde, joueurs existants, cycle jour,
balises actives/passives, mines et grenades dans leur phase/position courante.
Puis unicast des etats publics courants des torpilles, drones et leurres
(duree restante, integrite), via `_emit_one` non journalise pour ne pas compter
un rattrapage comme un nouveau tir/largage. Aucun appel de spawn, drainage d'evenements Sim
ou nouvelle lecture capteur. Les broadcasts habituels alimentent ensuite les
positions, tirs, explosions et naufrages ; pas de forwarding de donnees privees
BT/RL ou de compteurs propres a un joueur. Les explosions/obus deja passes et
les fronts sonar anterieurs ne sont pas rejoues.

Le client branche avant le bootstrap du bateau : `localBoat` reste null,
listes locales, `boatAmmo` et `selfControlledPlayerIds` restent vides.
`viewedBoat` pointe sur le premier bateau de la liste init et `playerMesh`
devient son mesh distant existant, sans copie de coque, mutation de controleur
ou attribution de `playerId`/equipe locale. Les cameras ArcRotate et embarquee
sont construites par `createBoatCameras`, commun au joueur. La boucle joueur
reutilise la branche vue bot : interpolation, suivi, zoom, clipPlane, eau/fond,
HUD vitesse/cap/profondeur et projectiles ; `isViewingLocal()` reste false,
donc aucune physique locale ni intent de mouvement. Integrite lue depuis
l'historique distant et convertie en pourcentage, sans ecraser `boatIntegrity`.
Les stocks distants ne sont pas publics : afficher "non communiquees", jamais
les capacites JSON comme stock courant. Coque/armes/admin masques, emits filtres.

Le bouton existant `botsBtn` (Unites, ajout chez le joueur) devient **Changer
unite** en observation ; Tab/Shift-Tab et `movebot` parcourent humains/bots de
toutes equipes. Aucun bouton spectateur de pilotage/camera libre ajoute.
Le radar reutilise les regles joueur et l'identite/equipe de vue via
`sensorPlayerId`/`sensorTeamId`, sans changer l'identite locale : gel en plongee,
LOS, thermoclines, sonar et partage allie habituels. `allMapMode=false` par
defaut ; `allmap` est une bascule locale de diagnostic autorisee (radar complet,
pas de rendu 3D omniscient). Zoom radar x1 a x100 et pan bornes conserves.
Les caches de contacts sont effaces au changement de vue pour ne pas transmettre
la connaissance de l'autre equipe ; detections privees et historique anterieur
non rejoues, donc pas de garantie de parite exacte avec le joueur observe ou RL.
Carte : seuls les contacts affiches non memorises peuvent etre suivis ; clic
vide sans effet sur la vue et sans ciblage. Etiquettes 3D visibles : meme suivi.
Naufrage/depart choisit le survivant suivant, sans popup de mort ; sans bateau,
`renderSpectator` assure une vue neutre et les effets, puis suit la premiere
arrivee disponible dans l'ordre de la liste (chargements modeles asynchrones).
La fin autogame reste independante des spectateurs et ferme la connexion.

Tests : `test_spectator.py`, vrais handlers et filtre avec clients SocketIO
en memoire, sans port ; `tests/test_spectator.js`, chargement du client complet
et frames Babylon NullEngine avec DOM et assets factices (premier bateau,
bouton existant/Tab toutes equipes, cameras embarquee/suivi, profondeur/HP,
radar normal/allmap, clavier/souris sans intents, arrivees asynchrones,
naufrage/depart, aucun bateau local, vrai changement actif joueur). Les autres harnais JS
gardent `spectatorMode=false`. Pas de validation visuelle navigateur/mobile,
de transport live, de lancement serveur ou de deploiement implique.

## Scenario automatique et grenades (2026-09-09)

Le serveur lit `autogame.json` a la racine du depot uniquement avec `--autogame`
(booleen, desactive par defaut), une seule fois au demarrage, apres selection de
la carte et avant les taches de fond et
l'ecoute HTTPS. `{"boats": []}` reste le scenario vide ; le fichier local autorise
contient actuellement destroyer v3 / sous-marin v15, preparation 30 s,
`anyBoatSunk` et `maxDurationSeconds: 600`, aux positions deja autorisees.
Sans ce flag, aucune lecture ni validation du fichier, aucun prechargement d'IA
ni spawn du scenario, meme si le fichier est absent ou invalide.
Pas de creation a la connexion d'un client, ni de relecture au changement de carte.
Les bots jouent sans humain connecte via le ticker et la Sim habituels.

Schema strict : objet `boats` obligatoire (liste, maximum 32), `map` optionnel
mais, s'il est present, identique a `--map` (il ne selectionne pas une autre carte).
Chaque bateau exige `boatType` (`destroyer`/`submarine`), `ai`, `teamId` et
`position: {x, y, z}`. `rotation` est optionnelle (defaut 0 rad), `teamName`
optionnel (defaut teamId). Equipes explicites : meme ID = allies ; IDs differents
= adversaires. IDs/noms d'equipe : 1-64 caracteres ASCII lettres/chiffres/_/-.
Les autres champs sont refuses, notamment vitesse, seed et etat de combat.

XYZ sont en **unites monde (10 metres/unite)**, centre de carte a XZ=0 ;
Y negatif sous l'eau. Destroyer : Y = -flotation/10, soit -0.2 actuellement.
Sous-marin : entre -maxDepthMeters/10 et -flotation/10. Cap en radians,
0 vers -X, pi/2 vers +Z, pi vers +X. Positions finies, hors iles et a 2 unites minimum
des limites. Pas de placement aleatoire suivi d'une teleportation : position,
profondeur demandee, orientation et miroirs sont initialises directement, vitesse 0.
L'IA peut changer ces consignes des sa premiere decision ; aucune garantie de
replay deterministe, de degagement de coque ou d'absence de collision entre spawns.

Exemple de deux destroyers RL a 2 km, caps opposes, points verifies hors iles
sur `maps/world.json` actuel (template seulement, non active dans le fichier livre) :

```json
{
  "map": "world",
  "endCondition": {"type": "anyTeamEliminated"},
  "maxDurationSeconds": 600,
  "boats": [
    {"boatType": "destroyer", "ai": "rl_aidest_v4_scripted", "teamId": "red",
     "position": {"x": -100, "y": -0.2, "z": 600}, "rotation": 3.141592653589793},
    {"boatType": "destroyer", "ai": "rl_aidest_v4_scripted", "teamId": "blue",
     "position": {"x": 100, "y": -0.2, "z": 600}, "rotation": 0}
  ]
}
```

Activation au prochain demarrage autorise via `./start.sh --trace --autogame --map world`.
IA BT : nom complet du fichier sans `.json` (`autodest`, `autosub`, etc.).
RL : `rl_<run>` ou `rl_<run>:<checkpoint>`, resolution existante sous
`rl/models_rl` uniquement ; `best/best_model.zip`, sinon `policy_final.zip`
sans checkpoint explicite. Les modeles sont charges et leurs espaces verifies
avant tout spawn ; les controleurs prepares sont reutilises, pas reinitialises.
Avec `--autogame`, fichier absent, JSON invalide, champ inconnu, mauvaise carte/profondeur/position,
BT absent/invalide ou modele absent/incompatible : demarrage refuse avant ecoute,
detail dans `logs/server.log`. Aucun repli RL vers BT pour autogame. Toutes les
entrees sont preparees avant creation ; une erreur inattendue pendant creation
arrete aussi le processus avant service, sans exposer une partie partielle.

Sous `--trace --autogame`, uniquement apres application du scenario,
enregistrement `autogame` des placements, IA et equipes demandes
(sans objets controleurs), snapshot initial et empreintes monde/modeles existantes.
Une panne de trace desactive la trace sans refuser un scenario valide.

### Preparation Avant Combat

Champ racine optionnel `startDelaySeconds` : nombre fini >= 0, defaut 0 ;
booleens, null, chaines et valeurs negatives/non finies refuses avant spawn.
Une valeur positive exige au moins un bateau. Le delai monotone commence apres
prechargement des modeles, creation des bateaux et trace initiale, avant ecoute.
Il ne bloque pas le demarrage : les tickers cedent normalement la main, HTTPS
et `spectate`/`init` restent accessibles avec les positions de spawn.
Ce delai inclut le court temps de mise en ecoute, pas le prechargement RL.

Jusqu'au premier tick a l'echeance, aucun `Sim.step`, decision BT/RL, progression
physique/combat, detection des deux tickers de balises, drainage ou evaluation
de fin. `last` est rafraichi a chaque tick d'attente, sans rattrapage de 30 s.
Le filtre SocketIO existant refuse temporairement les intents mutateurs de tous
les clients avec `autogame_preparing` (y compris selection de bateau et cheats) ;
connexion, deconnexion, observation, equipes et diagnostics ping restent permis.
Le verrou spectateur permanent reste independant. Les intents refuses ne sont
pas mis en attente : un humain doit reessayer apres le depart.

L'horloge live reste murale, sans nouveau multiplicateur/offset global : `sim.t`
et l'etat RL restent intacts faute de step, les munitions sont pleines et aucun
cooldown de tir n'est arme au spawn. L'echeance initiale `next_depth_change_at`
est decalee du temps reel de preparation a la reprise pour ne pas expirer pendant
l'attente. Aucun gel de l'horloge du navigateur ni du cycle jour/nuit d'affichage.

Sous `--trace`, `autogame` inclut le delai ; `autogame_ready` contient
`startDelaySeconds`, `readyMonotonic`, `readyAt`, `plannedStartMonotonic`,
`plannedStartAt` (temps monotones locaux et timestamps muraux en secondes).
`autogame_started`, emis une seule fois avant le premier step meme avec delai 0,
ajoute `startedMonotonic` et `startedAt`, puis force un snapshot initial.
Les snapshots d'attente n'incrementent ni le tick physique ni le temps simule.
La limite de duree et les naufrages ne sont armes qu'a ce depart effectif.
Tests sans ecoute : delais 0/30 s et horloges factices, validation, absence de
steps/detection/fin pendant l'attente, init observateur et refus des intents,
timeout apres depart, trace unique et cycle de vie en sous-processus factice.

### Fin Automatique

Deux champs racine optionnels, actifs seulement avec `--autogame` :

- `"endCondition": {"type": "anyBoatSunk"}` : un bateau initial du scenario coule.
- `"endCondition": {"type": "anyTeamEliminated"}` : tous les bateaux initiaux d'au moins une equipe coulent.
- `"endCondition": {"type": "teamEliminated", "teamId": "red"}` : tous les bateaux initiaux de cette equipe coulent.
- `"maxDurationSeconds": 600` : limite reelle monotone, independante du multiplicateur Sim, utilisable seule ou comme secours (OU).

Sans ces deux champs, aucun arret automatique, meme apres destruction totale.
Une fin active exige au moins un bateau ; l'equipe cible doit exister dans le
scenario. Types/champs inconnus, `null`, duree non numerique, booleenne, non finie
ou non positive sont refuses avant spawn. Pas de DSL booleen ni condition sur les humains.
Le chrono commence au depart effectif, apres la preparation optionnelle ; verification
a la fin de chaque tick serveur (donc pas un watchdog contre un blocage du processus).

Seuls les `BoatSunk` natifs des IDs publics crees au demarrage comptent, collectes
avant dispatch ; humains et bots ajoutes ensuite sont ignores. Suppression manuelle,
changement de carte/reset et disparition sans naufrage ne comptent jamais comme
victoire et ne reinitialisent pas le suivi : utiliser le timeout pour borner ces sessions.
Tous les naufrages du tick, y compris ses sous-pas acceleres, sont regroupes avant
decision. Si toutes les equipes coulent dans ce lot, `draw=true`, aucun vainqueur.
Une condition satisfaite sans torpilles a attendre prime sur le timeout au meme tick. Un vainqueur n'est
designe que si une equipe a ete eliminee et une seule reste ; sinon liste vide,
notamment pour un timeout ou une premiere perte sans elimination d'equipe.

Option commune aux trois types :
`"endCondition": {"type": "anyBoatSunk", "waitForTorpedoes": true}`.
`waitForTorpedoes` est strictement booleen ; absent ou `false`, comportement
immediat conserve. Le scenario local v3/v15 l'active, sans changer XYZ/caps,
preparation de 30 s ni limite de 600 s. Une condition atteinte reste acquise via
l'ensemble monotone des naufrages initiaux. A chaque evaluation, seules les
torpilles actuellement dans `torpedoes_server`, identifiees par le couple public
`ownerPlayerId`/`tid`, dont le proprietaire initial a coule, retardent la fin.
Tous les proprietaires coules comptent, pas seulement la victime declenchante ;
un nouveau naufrage pendant l'attente ajoute aussi ses torpilles encore en vol.
Les survivants continuent leurs actions, Sim/BT/RL et tickers restent actifs :
aucune pause ni annulation d'effets. Impact, explosion, portee ou retrait de la
torpille liberent l'attente ; pas d'historique artificiel, ni attente du souffle,
des leurres/drones ou des torpilles de survivants ou membres non initiaux.
Le bilan est recalcule apres ces naufrages, permettant kill posthume et match nul.
Si le timeout expire avec des torpilles a attendre, `reason="timeout"`, sans
vainqueur ni draw ; le chrono reste celui du depart apres preparation. Sans
maxDurationSeconds, pas de borne supplementaire contre une torpille bloquee.
Avec `--trace`, `autogame_settling` est emis une seule fois au premier report :
`reason`, `elapsedSeconds`, `triggeringBoatIds`, `sunkBoatIds`,
`outstandingTorpedoes` (liste de couples publics `ownerPlayerId`/`tid`),
`outstandingTorpedoCount`, `outstandingOwnerCount`. C'est un instantane d'entree,
pas un bilan ni une liste mise a jour ; aucun gagnant n'est annonce avant la fin.

Apres drainage/dispatch de tous les evenements natifs, le serveur ecrit le bilan
`autogame_end` dans le log et stdout ; avec `--trace`, il force un snapshot final
puis ecrit `autogame_end` et ferme la trace avant de terminer. Le bilan contient
`reason`, `elapsedSeconds`, `triggeringBoatIds` (nouveaux naufrages du dernier lot),
`sunkBoatIds`, `eliminatedTeamIds`, `survivingTeamIds`, `winningTeamIds`, `draw`,
`map` et `boats` (IDs publics, placements, equipes et noms d'IA demandes, sans controleur).
Les empreintes RL restent dans les enregistrements `rl_model` existants.

Uniquement pour une fin configuree, l'ecoute tourne dans un greenlet et le
greenlet principal attend un `eventlet.event.Event` : la fin le reveille, ferme
les logs et laisse sortir normalement le processus avec code 0, sans `os._exit`,
signal externe ni `socketio.stop()` dans le ticker. Les erreurs de l'ecoute remontent
au principal. Les connexions clientes se ferment avec le processus ; pas d'attente
d'acquittement reseau, ni de garantie que le navigateur affiche le dernier evenement.
Le pipeline de `start.sh` atteint EOF normalement ; aucun redemarrage automatique.
Tests : `test_autogame_end.py`, conditions, ordre de trace/arret, panne trace et
sous-processus eventlet factices sans port (fin, retour et erreur serveur).

Grenades : plus d'immunite propre au tireur humain ; humains, BT et RL subissent
le souffle, allies compris. Formules/rayons existants conserves (200 m actuellement).
Le compteur `GrenadeExploded.dealt` exclut desormais aussi l'auto-degat bot,
comme celui humain ; aucun coefficient de reward ni schema RL ne change.
Le cheat explicite `godmode` reste distinct et inchange. Scores historiques non
directement comparables ; pas de modeles remplaces ni d'entrainement relance.

Tests : `test_autogame.py` (CLI opt-in, absence d'I/O sans flag, ordre de demarrage,
validation, vrais spawn/hook serveur extraits par AST,
Sim et munitions headless, positions monde), `test_integrity.py` (humain/BT/RL,
miroirs distincts, souffle propre/collateral). Ni transport ni partie live testes.

## Trace serveur JSONL (2026-09-09)

Activation locale uniquement : `./start.sh --trace --map world` (ou un nom de
carte existant). OFF par defaut ; `debug <cat>` reste un outil distinct.
`game_trace.py` est stdlib uniquement et ne change ni les capteurs, ni les
intentions, ni les regles. Un logger prive non propage possede un unique
`RotatingFileHandler` : `logs/game_trace.jsonl`, 20 MiB, cinq backups, flush a
chaque ligne. Une ligne trop grosse ou une erreur de capture/serialisation/disque
desactive la trace avec warning sans contenu sensible et sans arreter le jeu.
Fermeture via atexit ; un kill brutal peut laisser une derniere ligne incomplete.
Au redemarrage, un fichier courant non vide est archive par rotation avant la
nouvelle session ; ignorer une eventuelle derniere ligne incomplete des archives.
Un seul processus serveur doit ecrire dans ce chemin.

Chaque ligne porte `schema=1`, `session` UUID neuf au demarrage, `epoch` de
chargement du monde, `seq`, `tick`, `wall_time` Unix, `sim_time` (`Sim.t`, nul
avant observation) et `stepped_seconds` (somme des dt executes). En live `Sim.t`
utilise l'horloge murale : un multiplicateur x8 avance huit pas physiques mais
pas huit fois les timers muraux. `tick` compte les appels reussis a Sim.step ;
les evenements portent le dernier tick observe, pas un timestamp exact de leur
creation. Le buffer Sim est draine apres les sous-pas du multiplicateur existant.

Types principaux :

- `session`, `metadata`, `world` : bornes, unites (10 m/u), revision Git et dirty
  (null si indisponible), SHA-256 code/specs/arbres BT et monde charge, specs
  numeriques filtrees des bateaux et duree du jour. Git n'est appele qu'au
  demarrage, jamais par tick. Ce manifeste n'archive ni carte ni checkpoints RL.
- `snapshot` : une ligne par objet a 4 Hz maximum monotone (pas x8). Identite
  `[famille, playerId]`, `[famille, ownerId, numero]` ou `[famille, numero]` ;
  qualifier par session/epoch. XYZ, rotation, vitesse/ratio, profondeur demandee,
  commandes RL stockees, integrite, cible/verrou, munitions disponibles. Pour un
  humain actif, la position est la derniere acceptee du client, pas une nouvelle
  integration physique independante. Les identifiants SID internes sont resolus
  en identifiants publics pour les bateaux et les compteurs Sim adresses.
- `event` : liste positive des dataclasses gameplay au drainage, avant dispatch.
  Les mouvements continus sont echantillonnes ; TorpedoState/DroneState ne sont
  gardes qu'a leur premiere apparition, jusqu'au Dead correspondant. Les autres
  lancements, explosions, degats, pings, destructions restent au rythme natif.
- `event/RLDecision` : chaque decision du `RuntimeController` live, uniquement
  sous `--trace`, apres `apply_action`. `observation` est le vecteur float32
  complet copie avant `predict`, `action` la sortie choisie, `result` les flags
  retournes (weapon/lure/sonar/mine requested, fired/dropped/pinged/placed,
  invalid et kind). Ce ne sont pas des degats futurs ni des impacts garantis.
  `player_id`, `control_version`, `episode_start`, `decision_interval_s`,
  `decision_at` (Sim.now a l'entree), `physics_dt` et `simulation_step` (pas
  serveur 1-based depuis le demarrage) identifient la decision, meme si plusieurs
  sous-pas sont draines ensemble. L'enveloppe garde le timestamp de drainage.
  `visible_threat` vaut null ou `{owner_id, tid}` publics, copies pendant l'unique
  construction du slot menace ; aucun second appel radar/sonar, aucun verrou.
  Les slots et dimensions 32/36/40 restent inchanges. Aucun dispatch reseau.
- `rl_model` : identite relative sous models_rl et SHA-256 des octets ZIP
  effectivement charges, une fois par couple modele/hash dans la session ; les
  decisions referencent aussi `model_id`/`model_sha256`. Lecture et hash seulement
  au premier chargement opt-in, pas par decision. Un modele injecte sans fichier
  ou deja en cache avant activation peut avoir un hash null, jamais recalcule
  depuis un fichier potentiellement remplace. Les checkpoints ne sont pas archives.
- `legacy_event` : liste positive des emissions directes SocketIO, y compris
  emit Flask (qui delegue a SocketIO.emit). `_emit_one` contourne ce hook car
  son event Sim est deja trace. Les emissions par equipe peuvent se repeter
  (notamment MineRevealed) : ne pas compter les notifications comme autant de tirs.
  Les options reseau et le routage ne sont jamais serialises.
- `lock`, `sonar_contact` : differences a chaque pas, sans appel de capteur.
  Verrous torpilles, revelations actives Sim et `last_detected_ids` BT ; une
  revelation memorisee n'est pas une acquisition visuelle courante. Les pings
  et detections de balises humaines sont aussi des evenements legacy.
- `despawn` : disparition deduite entre deux echantillons, sans cause inventee.
  `first_seen` signifie premiere observation, pas necessairement creation.
  Un objet ne vivant qu'entre deux snapshots peut manquer ; ses evenements
  disponibles restent traces. Une nouvelle epoch efface les caches de suivi.
- `cannon_shell`, `pending_sonar_ping` : obus complets et pings Sim echantillonnes.
  Les callbacks canon/DCA humains ne sont pas une collection Sim : leurs tirs,
  hits/destructions emis sont traces, pas la file interne eventlet.
- `sample` : effectifs par famille, multiplicateur, mode passif bots, compteurs
  cumules `records_written` et `bytes_written` avant la ligne courante.

Volume : une ligne bateau typique de 0.5 a 1 KiB donne environ 20 a 40 KiB/s
pour dix bateaux a 4 Hz, plus projectiles et evenements natifs. Ce sont des
estimations, pas un benchmark live ; les compteurs permettent de mesurer le
debit reel. Les six fichiers bornent le disque a 120 MiB ; la duree conservee
depend de l'activite. Les ecritures synchrones ont un cout I/O, non mesure en
session reelle. Lire `.5` vers `.1`, puis le fichier courant ; `session`/`seq`
ordonnent les lignes, meme si la rotation a deja elimine le debut du manifeste.
Conserver les sources/cartes/specs correspondant aux empreintes pour l'analyse.

Limites : pas de chat/IP/SID/session socket/secret/nom de joueur, pas de dump
global, pas de BB brut ni de tenseurs LSTM ; seul le vecteur RL reel est capture.
Aucune preuve de ce que le navigateur
voyait, de la legalite complete du sonar humain, de la latence/interpolation ou
de fairness globale. Les intentions refusees ne sont pas toutes instrumentees.
Ce n'est pas un replay deterministe ni une garantie d'exhaustivite des decisions
capteurs entre deux pas. Pas de nouvel entrainement long avant collecte humaine
autorisee et analyse ; ni serveur, ni entrainement, ni deploiement lance ici.

Tests : `test_game_trace.py`, sans serveur live ; objets, evenements, transitions,
confidentialite, erreurs, rotation, identites inter-sessions et hooks serveur AST.
Les tests AST ne valident pas le transport Flask/eventlet en situation reelle.

### Classement des menaces corrige (2026-09-09)

Sim/BT et le slot RL classent les candidats par `(eta <= 0, eta)` : projections
brutes positives d'abord, ETA croissante, puis CPA deja passes/tangentiels ou au
contact (ETA=0), ordre d'insertion stable a egalite. Le bornage existant de l'ETA
preserve exactement le signe positif de la projection brute. Une fuyante proche
reste representee lorsqu'elle est seule : ne pas supprimer un risque d'explosion
de proximite, notamment pres d'un leurre. Aucun changement de portee radar, LOS,
thermocline, horizon projete de 10 s, CPA <= 200 m, vitesse > 0.001 u/s ou schema.
Les candidats au-dela de 10 s encore a <= 200 m du bout du segment gardent ETA=10.
Pas de donnees privees ni de modification des conditions defensives BT existantes.
Les checkpoints restent chargeables, mais les resultats historiques ne sont pas
directement comparables aux decisions sous ce classement. Recuperation automatique
d'un bot bloque, navigation et physique non modifiees par cette correction.

## Tirs humains par ID et menaces BT (2026-09-09)

`server.spawn_torpedo` verifie `Sim.bot_target_los` avant de convertir une cible
`targetId` en XYZ courant, pour les trois types et le mode anti-torpille.
Un ID masque ou inexistant est refuse, meme accompagne d'un `fixedTarget`.
`fire_cannon_intent` applique la meme garde avant resolution XYZ pour bateau,
drone DCA, balise active/passive et mine de surface. Ile fine, bord et sommet
bloquent via le predicat exact commun. Refus avant initialisation/consommation
des munitions, allocation, evenements et programmation de degats.

Regle tactique explicite : viser un point manuel ou memorise reste permis,
meme derriere une ile. `fixedTarget` sans ID conserve son contrat XZ et sa
profondeur initiale historique ; les grenades et snapshots bots restent inchanges.
La garde est une condition LOS locale au tireur, PAS une preuve de contact sonar :
bruit, portee/cone sonar, thermoclines, revelations temporisees et partage allie
ne sont pas valides comme autorisation humaine complete. Les etats ennemis sont
encore distribues aux clients ; aucun contrat anti-client modifie n'est etabli.

`simulation.torpedo_radar_visible` et `torpedo_radar_threat` partagent le filtre
RL avec `Sim.bot_torpedoes_threat` et les consommateurs BT : portee radar locale,
LOS exacte, aucune thermocline franchie, vitesse > 0.001 u/s, CPA <= 200 m sur
10 s et ETA geometrique. Aucun bypass/priorite par verrou ; type neutralise dans
les snapshots BT. Le combat BT abandonne son ancien cone de 15 degres/lock prive.
Les conditions d'activite utilisent `_torpedoes_in_los_5km` avec le meme filtre
de visibilite, sans CPA et en incluant les torpilles propres visibles. Le cache BT
de 0.5 s reste une memoire figee ; `torpedo_acquired` signifie desormais ETA nulle
ou evasion en cours, pas connaissance d'un verrou. Schemas/rewards RL inchanges.

Tests : `test_server_fire_los.py` execute les vraies fonctions et handlers extraits
par AST, avec Sim reel et I/O simulees ; ni serveur Flask ni transport/authentification
ni execution des degats differes ne sont testes. `test_torpedo_threat_visibility.py`
et les regressions RL couvrent les filtres et l'invariance aux verrous/types caches.

## Guidage torpille : perte capteur (2026-09-09)

En phase active acoustique/autonome, un echec des capteurs efface le verrou :
cap courant conserve, pitch remis a zero pour tenir la profondeur courante.
Ni `lastAcquiredPos` ni `initialTarget` ne pilotent apres cet echec, meme si
aucune cible n'a encore ete acquise. Le point initial reste utilise avant activation.
L'evitement local existant reste actif sans contact, avec le meme horizon et la
meme limite de virage ; il peut donc devier le cap. Aucun pathfinding ni garantie
de contournement n'est ajoute. Les commandes filoguidees humaines sont inchangees.

Reacquisition uniquement par les capteurs existants : cone/portee/bruit,
thermoclines et LOS exacte des iles. Scan anti-torpille ET suivi du verrou
precedent verifient maintenant cette LOS, comme les branches bateau/leurre.
Le sonar autonome reutilise un resultat de penetration par entite et par passe
`_pick_radar`, entre priorite, suivi et scan ; bateau, leurre et torpille ont des
cles distinctes. Nouvelle tentative a chaque passe/tick admissible (20 Hz nominal),
sans timer ajoute. La probabilite cumulee depend encore de cette frequence :
l'equilibrage temporel reste ouvert, pas assimile au sonar actif des bateaux.

`_emit_torpedo_state` ne resout plus jamais un `targetId` vivant : uniquement le
dernier point reellement acquis ou le point de lancement fige, sinon aucune cible.
Ces coordonnees memorisees ne prouvent pas un verrou courant et ne pilotent pas
la torpille apres perte. Le payload historique ne distingue pas memoire/verrou.
Regressions Sim/headless : `rl/test_torpedo_guidance.py`. Fairness globale,
parite navigateur/reseau et reevaluation des modeles restent incompletes.

## Tir bot : perception et memoire (2026-09-09)

`Sim.bot_target_los` reutilise la LOS exacte fermee des iles deja partagee avec
le client : ile fine, bord et sommet inclus. Elle gouverne la perception et
l'acquisition, pas l'autorisation globale de lancement. Le RL conserve le dernier
point observe sans actualiser ses coordonnees derriere une ile, meme pendant une
revelation sonar encore valide.

BT, fallback legacy et RL transmettent aux torpilles un snapshot de forme cible :
`id`, `position` XYZ copiee, `observed_at` et metadonnees observees. `tracked`
distingue le dernier contact capteur de la memoire seule ; conserver un souvenir
n'ajoute jamais son ID aux detections. Salves BT et combat peuvent utiliser le
dernier point pendant leur delai existant (30 s par defaut, `clear_after_s` pour
les salves). RL : memoire 30 s, tir au plus 1 s apres observation et avant
l'expiration d'une revelation active, comme auparavant.

`spawn_bot_torpedo` et `spawn_bot_torpedo_autonomous` autorisent un lancement
vers ce point, meme masque : cap, profondeur visee et activation adaptative
ne consultent plus l'objet ennemi courant. Ces snapshots produisent `targetId=None`,
sans alerte cible au lancement ni priorite radar par ancien ID ; seuls les capteurs
de la torpille peuvent acquerir ensuite (LOS exacte, cone, portee, thermoclines/bruit).
`spawn_grenade` accepte egalement un point masque, avec les contraintes existantes
de portee, profondeur et munitions. Aucun changement aux intentions humaines.

Etape 2 canon : cette ancienne limite est levee par `Sim.fire_cannon`, trajectoire
partagee sur point copie et collision physique (voir Cannon / DCA ci-dessous).
La memoire non suivie peut fournir un point, jamais programmer des degats par ID.
La DCA conserve sa validation LOS et ses effets differes distincts.

Pas de changement des durees sonar, thermoclines, coefficients de reward ou
schemas RL. Les revelations sonar gardent leur expiration originale ; elles ne
dispensent plus du filtre LOS de selection RL. Les scores historiques ne valident
pas ces nouvelles regles. Regressions : `rl/test_bot_fire_los.py` en vrai headless.
Hors tranche : attaque automatique des drones, degats des armes deja
tirees, comptabilite DCA existante, parite reseau, pathfinding et audit global.

## Parite sonar live : identite canonique (2026-09-09)

`server.spawn_bot` cree deux dictionnaires distincts sous le meme SID et ID
public : l'objet canonique dans `bots`, son miroir dans `players`. Seul le miroir
porte `is_bot`. Le headless les aliasait, masquant un defaut du sonar temporise :
la validation cherchait la cible bot dans `players`, rejetait le contact RL et
supprimait/recreait sa revelation a chaque tick jusqu'a expiration du front.

Chaque acquisition conserve maintenant son registre source (`bots` ou `players`).
La validation exige l'identite exacte de l'objet dans ce registre, et celle de
l'emetteur dans `bots` ; un remplacement sous le meme ID/SID ne ressuscite pas
l'ancien contact ou le ping d'un ancien emetteur. Le marquage `pinged_at` utilise
aussi le registre canonique, pas le flag absent. Le front de 5 s, la revelation
de 10 s depuis acquisition, la LOS/memoire figee, les thermoclines, rewards et
schemas RL ne changent pas.

`rl/test_active_sonar.py` rejoue les regressions avec alias headless et objets
server-shaped distincts, RuntimeController et trace JSONL temporaire inclus.
Acquisition a 0.625 s, expiration a 10.625 s sans prolongation ni perte a 5 s.
Ce test n'execute pas Flask/SocketIO ni une partie humaine. Les anciens tests
headless et etats `active_reveal` traces ne prouvaient pas un contact exploitable
en live ; les observations de jeu anterieures ne valident donc pas les politiques
sous sonar corrige. Revalidation humaine candidate/reference reste necessaire,
sans effacer les resultats headless historiques ni relancer les evaluations ici.

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
conffile.json  port serveur, durée jour, sélection des bots RL
certs/           cert SSL local
logs/
  server.log     RotatingFileHandler 10 MB × 3 (basicConfig INFO)
```

Lancement : `./start.sh` (logfilter actif). Le serveur tourne en HTTPS sur
`config.server.port` (défaut 7000). Si la paire `certs/cert.pem` et
`certs/key.pem` est absente, le script génère avant le démarrage un certificat
auto-signé contenant le nom d'hôte et les adresses IP locales. La clé Flask est
lue depuis `VIRTUALWORLD_SECRET_KEY` (32 caractères minimum) ou générée
aléatoirement pour la durée du processus si cette variable est absente.

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
6. Initialise l'intégrité (`init_player_integrity` : capacite du JSON, regen budget plein).
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

Portee des torpilles : `maxRangeMeters / 10` est le budget cumule depuis
le point de creation du projectile, commun aux humains/BT/RL/headless.
`traveled` consomme vitesse 3D * dt, virages et pre-activation compris, sans
remise a zero lors de l'acquisition/perte de cible. Au plafond de profondeur,
le deplacement reel peut etre inferieur au budget consomme. Ce n'est ni la
distance au tireur mobile, ni la distance droite a la cible. Le spawn est
decale de 15 m pour les humains et 4 m pour les bots par rapport au bateau.
Le dernier segment est borne au budget restant AVANT les collisions ; les
collisions sur ce segment gardent leur priorite, sinon expiration sans degats
avec `TorpedoExploded`/`TorpedoDead` et liberation du slot filoguide.
Les rayons de collision et de souffle ne sont pas des metres de propulsion.
Le client lisse vers le dernier etat recu (sans extrapolation), supprime mesh
et trainee sur `torpedo_dead`, et purge un etat vieux de plus de 3 s.
Regressions : `test_torpedo_range.py`, `test_server_fire_los.py` et
`rl/test_torpedo_guidance.py`. Correction du depassement d'un tick uniquement,
sans changement des portees JSON, observations, recompenses ou modeles.

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

**Etape 2, canon physique partage (2026-09-09)** :

- `fire_cannon_intent` resout les anciens IDs visibles a cet instant seulement,
  puis appelle `Sim.fire_cannon`, comme `bot_fire_cannon` pour BT/RL.
  `targetType: "point", fixedTarget: {x,y?,z}` accepte un point manuel/observe,
  meme masque, sans lookup ID. Le client bateau transmet ses coordonnees observees.
- Validation avant consommation : point numerique fini (pas de bool), distance
  XZ strictement positive et dans la portee, armement/munitions, tireur non coule,
  sous-marin non plonge, cooldown existant `next_cannon_at`. Cadences BT/RL 3 s
  conservees par leurs appelants; aucune nouvelle cadence humaine n'est inventee.
- Garde numerique : longueur calculee finie et deplacement XZ resoluble au carre
  avant consommation (sinon sous-flux du solveur ou de la duree). Aucun minimum
  de portee gameplay ajoute; coefficients XZ nuls/non finis et discriminants
  non finis ne sont pas divises par le solveur de collision.
- Chaque obus garde seulement tireur public, shot ID, depart/arrivee copies,
  arc, duree, date Sim, progression, portee et degats (spec actuelle 30 points).
  Ni reference a la cible, ni lecture future pour guider, ni tir garanti par ID.
- Courbe historique client exacte : `P(u) = lerp(start,end,u) + (0,4*h*u*(1-u),0)`.
  Vitesse nominale XZ 500 m/s; `T = distance_initiale_m / 500`;
  `h = distance_finale_u * .25 * min(1, distance_finale_u / max(1, portee_u))`.
  Depart Y destroyer .5 u, sous-marin 0 u. Aucune gravite canon en spec;
  acceleration derivee `g = 8*h/T^2` en u/s2, et non gravite grenade/terrestre.
- Dispersion conservee : probabilite 1 jusqu'a demi-portee puis .3 en limite,
  sinon decalage radial aleatoire 8 m. Balises/mines sans dispersion historique.
  Le point disperse est borne a la portee XZ. Le tirage ne decide PLUS les degats :
  meme un point disperse peut rencontrer une coque. Aucun nouveau coefficient HP.
- `update_cannon_shells` dans `Sim.step` cherche le premier contact sur la partie
  parcourue de la parabole, analytiquement en XZ et Y. Les iles utilisent le segment
  ferme exact, tangences/coins/colinearite inclus, et bloquent a toute hauteur
  (pas de nouveau relief). Priorite ile en cas d'egalite, puis ordre stable objets.
- Coque approximative cylindrique, pas mesh : rayon = demi-`lengthMeters`, defaut
  existant torpille 100 m, tolerance verticale directe existante +/-4 m. Rotation
  non representee par cette approximation. Un bateau sous `-flotation/10-.05`
  est intangible au canon; position/profondeur reelles sont verifiees a l'impact.
  Un obstacle plus proche peut etre survole si la parabole est au-dessus de lui.
- Autre victime et tir ami possibles, degats natifs sans filtre d'equipe ajoute.
  Tireur exclu de sa propre coque au depart; ses obus survivent a son naufrage.
  Balises actives/passives : rayon existant 1 u; mines de surface meme enveloppe
  ponctuelle de 1 u, tolerance verticale 4 m, explosion native. Pas de nouveau HP,
  pas d'extension canon aux drones, leurres ou mines immergees.
- `CannonFire` ajoute `shot_id` / reseau `shotId`. `CannonImpact` / `cannon_impact`
  porte shotId, XYZ reels et raison (boat/island/beacon/passive_beacon/mine/range),
  supprime le visuel correspondant et remplace le timer d'explosion client.
  `CannonHit` identifie uniquement la victime dynamique effective. Fin de trajet
  sans contact = impact au point, suppression unique, aucun degat automatique.
- Trace native whitelist : CannonFire/Impact/Hit et chaque `cannon_shell` complet
  a 4 Hz. Aucun SID ni ID cible de guidage. Un spectateur connecte voit le tir
  via les memes evenements; pas de reconstruction des obus precedant sa connexion.
- Horloge `Sim.now()` commune live/headless, sans sleep canon. Les volumes mobiles
  sont echantillonnes au tick, pas balayes entre deux positions de bateaux; les
  racines de la trajectoire obus sont continues. Pas de garantie reseau/mobile.
  Le mode autogame attend toujours les torpilles seulement, pas les obus.

La **DCA** reste distincte : probabilite, LOS, vitesse 1000 m/s humaine,
degats/destructions par ID et taches Socket.IO historiques inchanges.
Tests : `test_cannon_ballistics.py`, `test_server_fire_los.py`, regressions RL,
`tests/test_cannon_ballistics.js`. Aucun changement de shape/version observation,
rewards ou modele; resultats historiques non comparables. Pas de lancement live,
entrainement, evaluation, deploiement, modification de modele ou commit.

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
   - Degats persistants aux leurres : meme attenuation 3D `1 - dist/r`, rayon JSON.

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

**`integrity` dans `player_moved`** : points restants et `maxIntegrity` par instance dans tous les mouvements humains, autopilotes et bots. Les tooltips calculent `100 * integrity / maxIntegrity`.

## Intégrité et dégâts

### Capacites configurees (equilibrage approuve 2026-09-09)

- `boats/destroyer.json`: `integrity: 200`; `boats/submarine.json`: `integrity: 100`.
- Les deux `acousticLures.integrity` valent 10. Aucun HP ajoute aux autres destructibles
  (mines, balises, drones, torpilles), dont l'evolution est differee.
- `integrity_capacity` valide des nombres finis strictement positifs, sans booleens ni
  chaines. Anciennes specifications sans cle : 100 points coque, 10 points leurre.
- `init_hull_integrity` partage par humains, BT, RL live et headless; `maxIntegrity`
  est copie dans chaque instance, jamais recalcule depuis une specification mutable.
- Les degats et budgets de regeneration restent des points absolus : 80 points
  laissent un destroyer a 120/200 (60%) et un sous-marin a 20/100 (20%).
- Les leurres persistent apres un coup non letal. Torpilles : rayon 200 m,
  attenuation 3D `damage * (1 - distance/rayon)`; proximite bateau conserve
  le facteur nominal 0.5. Impact leurre a <= 3 m du segment 3D : explosion au
  centre du leurre, degats nominaux (80 actuellement), plus de raccourci `damage=0`.
- Grenades : rayon `effectRadiusU` et attenuation lineaire 3D pour les leurres;
  les bateaux gardent leurs rayons existants (bots 200 m, humains rayon JSON).
  Mines : rayon JSON, `damage * (1 - 0.5 * distance/rayon)`, bord inclus.
- `lure_dropped` transporte `integrity` et `maxIntegrity`; `LureIntegrityChanged`
  devient `lure_integrity {ownerId, lid, integrity, maxIntegrity}`. Il ne supprime
  rien et ne rembourse aucune munition. `lure_destroyed` ne suit les degats qu'a
  zero, une fois; expiration et nettoyage du proprietaire restent independants.
- Le client ne detruit plus les leurres selon une distance horizontale estimee.
  HUD/tooltips en pourcentages, texte des degats de grenade en points effectivement
  perdus (plafonne aux HP restants), etat reseau en points. La trace autorise
  `maxIntegrity`, `max_integrity` et les mises a jour non letales publiques.
- RL : ratio propre courant/maximum, dimensions inchangees (32/36/40), HP precedents
  initialises aux valeurs reelles au reset; shaping conserve par point absolu perdu.
  Aucun acces supplementaire aux HP ennemis/leurres dans les observations des bots.
- Changement explicite d'equilibrage : tous les scores anterieurs sont historiques,
  non directement comparables. Champions inchanges, aucune promotion ni nouvelle
  evaluation/training autorisee implicitement; validation humaine toujours en attente.

Regressions : `test_integrity.py`, `test_game_trace.py`, `tests/test_integrity.js`.
Les handlers serveur sont executes par extraction AST sans serveur live; les tests
Node executent les handlers clients avec doublures, pas un navigateur/reseau reel.

### Source des dégâts

Tous les chemins passent par `apply_player_damage(sid, p, damage, attacker_id)` (humains) ou `bot_apply_damage(sid, bot, damage, attacker_id)` (bots) :

1. **Hit direct torpille** : `update_server_torpedoes` détecte collision joueur ≤ 3 m → `explode_server_torpedo(direct_hit_id=p["id"], damage=t["damage"])`.
2. **Splash torpille** : CPA sur le segment <= 80 m et ecart vertical <= 10 m, base `damage * 0.5`, puis attenuation 3D sur 200 m.
3. **Splash grenade** : `effectRadiusU` (= effectRangeMeters / 10) du JSON.
4. **Cannon hit** : `Sim.update_cannon_shells()` au premier contact physique, victime dynamique.
5. **DCA hit boat** : `_delayed_boat()` apres `flight_seconds`, `damage = 1` typiquement.
6. **Danger zone autour des îles** : 1 pt/seconde en `update_player_integrity`. Polygone outer = polygone d'île agrandi de 3 u (30 m).
7. **Profondeur excessive sub** : `y < max_dive_y` → `0.5 × overshoot_m × dt` par seconde.
8. **DCA bot vs joueur humain** : `bot_fire_aa` → kill drone uniquement (pas de dégâts au pilote).

### Régénération

`update_player_integrity` à chaque tick :
- Pas de regen pendant `REGEN_DELAY_S = 5 s` après un dégât.
- Burst budget `REGEN_MAX_BUDGET = 10 pts` (consommé) puis épuisement.
- Total session `REGEN_TOTAL_INITIAL = 20 pts` cumulés sur toute la partie.
- Taux : `REGEN_RATE_PER_S = 10 / (10 × 60)` ≈ 1/60 pt/s (10 pts en 10 minutes).
- Plafond par instance `maxIntegrity`, pas 100; regeneration humaine uniquement comme auparavant.

### Notification au client

- À chaque baisse d'intégrité → `integrity {value, maxIntegrity, bsid}` au proprietaire.
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
| `cheat_move_bot` | `{id, x, z}` : teleport du bot selectionne par identifiant public, allie ou ennemi |
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
| `cheat_move_bot_result` | sid | `{ok, message}` : confirmation ou refus du placement |

**Placement de trace (`telebot`)** : selection radar/3D d'un bot vivant, saisie
`telebot` hors champ texte, puis clic sur la carte radar ; `Echap` annule.
`allmap` facilite la selection. L'identifiant est fige a l'activation ; la
destination ne change ni la selection ni la position du bateau humain.
Le parseur consomme `telebot` avant le suffixe `bot`. `movebot` conserve la vue
bot (comme `bot`, cycle par proximite), `self` revient au bateau du joueur.
Le prefixe `move` reste disponible pour placer son bateau ; poursuivre avec
`bot` annule ce placement et passe en vue bot. L'evenement reseau de placement
reste `cheat_move_bot`, sans alias de teleportation `movebot`.
Regressions : `test_telebot.py` et `tests/test_telebot.js`.
Le serveur exige une session dans `players`, comme les cheats existants, sans
role administrateur distinct ; les sessions non initialisees et cibles humaines
(y compris les bateaux humains en autopilote) sont refusees.
`Sim.teleport_bot` valide le bot encore vivant, les nombres finis, les limites
avec marge de 4 u et les iles (bords inclus). Seuls x/z changent : profondeur,
cap, armes et integrite restent intacts. Vitesse/barre/commandes horizontales
sont remises a zero ; waypoints, plans d'esquive/navigation et compteurs de
blocage sont invalides. Contacts, souvenirs ennemis, exploration et memoire
recurrente RL restent conserves ; l'IA reprend au tick suivant, sans gel.
Les dictionnaires `bots` et `players` sont synchronises et `PlayerMoved` diffuse
le placement par le reseau habituel. Avec `--trace`, `BotTeleported` consigne
`actor_id`, `player_id` (bot), `old_position` et `position`, sans SID ; cet
evenement de preparation n'est pas un mouvement naturel ni une preuve de fairness.
| `bot_spawned` | sid | Confirmation autosub/autodest |
| `admin_world_loaded` / `admin_save_ok` / `admin_error` | sid | Admin |

Les `*_count(s)` incluent un champ `bsid` (`null` pour le primaire, ghost sid pour un secondaire) pour dispatcher dans `boatAmmo[bsid]`. Les `player_moved` incluent `integrity` et `maxIntegrity` en points; les tooltips radar affichent leur ratio en pourcentage.

## Inventaire des fonctions principales

### Serveur (`server.py`)

**Géométrie / monde**
- `point_in_polygon(x, z, points)` — test point-dans-polygone.
- `point_on_any_island(x, z, world)` — test rapide pré-filtré AABB.
- `_ensure_island_bounds(world)` — cache AABB par île.
- `line_of_sight_clear(x1, z1, x2, z2, world)` — occlusion exacte segment/polygone,
  prefiltre AABB, sans echantillonnage ni marge epsilon. Interieur, extremites,
  tangences et recouvrements collineaires bloquent, meme pour un segment nul.
  Meme predicat dans `isLineOfSightClearBetween` (exclusion d'ile conservee) et les
  trajets/evitements de torpilles Sim. Marges de navigation, limites du monde et
  impacts sur les coques inchanges. Fixtures Python/JS : `test_geometry_visibility.py`,
  `tests/geometry_visibility.json` et `tests/test_geometry_visibility.js` (Node optionnel).
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
Flask. Il réutilise directement `simulation.Sim` grâce à `rl/headless.py` : les
règles d'armement, de dégâts, de sonar et de leurres sont donc celles du jeu
autoritaire. `rl/TRAINING_RL.md` décrit les commandes et le diagnostic en détail.

La configuration `aisub_v14` entraîne un sous-marin.
Les adversaires BT sont configurés par coque, IA et poids. La politique reste
toujours un sous-marin ; elle affronte à parts égales `submarine/autosub` et
`destroyer/autodest`. Les impacts du canon des destroyers sont résolus selon
l'horloge de simulation et consomment les munitions comme sur le serveur live.

Le canon du destroyer RL (v1/v2) applique maintenant le seuil de profondeur cible
de `server.py::fire_cannon_intent` : refus si
`y < -boat.get("flotation", 2) / UNIT_METERS_BOT - 0.05`, limite exacte incluse
dans les tirs autorises (2,5 m pour une flottaison de 2 m, ancien seuil RL 6 m).
La regression `rl/test_fairness_diagnostics.py` utilise Sim/headless et verifie
notamment l'absence de consommation et de degats differes sur refus ; elle
n'execute pas le handler reseau. Sonar, torpilles et reward ne sont pas modifies.
Les shapes d'observation/action restent compatibles avec les checkpoints, mais
les metriques de resultat avant/apres ne sont pas directement comparables :
reevaluer candidats et references sous les memes regles corrigees.

Les menaces torpilles RL (sous-marin, destroyer v1/v2) suivent le radar strict
choisi par l'utilisateur : portee horizontale de la coque (defaut 30000 m,
egalite incluse), LOS locale et aucune thermocline croisee, avant selection.
`rl_control.py::_torpedo_observation` reutilise la LOS exacte commune ; l'ancien
complement local `ceil`/`floor` est supprime. Selection par ETA plane sur 10 s et CPA <= 200 m,
sans inclusion ni priorite issue du verrou serveur ; egalites stables.
Les slots verrou exact et type sont toujours zero : ces informations ennemies
ne sont pas exposees telles quelles au joueur. Cela remplace la correction
anterieure de collision `(ownerPlayerId, tid)`. Pas de fullmap ni relais allie.
Regressions Sim/headless et limites de timing/vitesse dans `rl/AUDIT_FOLLOWUP.md`.
Sim/BT, sonar, rewards, shapes et versions inchanges ; checkpoints chargeables
mais semantique et trajectoires differentes : reevaluer candidats et references
plus tard, sans comparer directement les anciens scores.

Le sonar actif BT et RL (destroyer v1/v2) utilise le ping local humain comme
reference, via `Sim.bot_sonar_ping(...)` puis `Sim.step`, en headless
comme en live. Emission d'un seul `SonarPinged`, sans lecture des cibles a l'emission.
Le front parcourt la portee large en 5 s ; expiration stricte a `elapsed >= 5`.
Avec la coque actuelle (30 degres, 8000 m), une cible immobile a 1000/4000 m
est eligible a 0,625/2,5 s, au premier tick disponible ; a 8000 m exactement,
le ping expire avant de pouvoir l'acquerir. Ce n'est pas un aller-retour acoustique.
Position et orientation d'emission sont figees, mais cible, LOS et thermoclines
sont reexaminees pendant la propagation. Un seul tirage de penetration par
ping/cible traversee ; aucune chance liee au bruit/vitesse. Portee de revelation
depuis l'emetteur courant uniquement (pas de relais allie). LOS exacte commune
au navigateur et a Python, sans double echantillonnage ; timing inchange.

Une acquisition conserve un delai fixe de 10 s, meme hors cone/portee, sans
prolongation a chaque tick. Sim memorise XYZ et l'instant de derniere observation :
une ile bloque tout rafraichissement live, sans supprimer le point deja observe.
Une reapparition en LOS pendant ce delai autorise de nouveau le suivi courant,
sans prolonger le delai ni refaire le tirage thermocline d'acquisition.
Les observations RL ne traitent jamais ce souvenir comme une detection fraiche
(`tracked=false`), et choisissent le contact
le plus proche parmi passif et actif. A expiration, la derniere position observee
reste memorisee 30 s, sans suivi ni tir par le contact sonar expire, meme s'il a
moins d'une seconde. Un ping ne permet donc plus d'acquerir et tirer dans la meme
action ; un contact deja acquis par ailleurs peut toujours permettre le tir.
Cooldown RL de 30 s, shapes, versions et coefficients de reward inchanges.
Pending/revelations sont effaces par `Sim.reset`.
Les metriques doivent etre reevaluees pour candidats et references ; les anciens
checkpoints chargent encore, mais leurs resultats restent historiques.
Transport : `SonarPinged.y` contient la profondeur reelle de l'emetteur (BT et RL),
transmise par le dispatcher comme pour les pings humains. `range`/`reveal` voyagent
en metres ; le recepteur JS les convertit une seule fois en unites monde, sans
reconvertir les pings locaux ni les portees de balises deja converties. L'alerte
de ping recu respecte aussi la LOS des iles ; penetration et cooldown inchanges.

Etape 1 sonar BT (2026-09-09) : suppression de la branche synchrone et du flag
`timed`, tous les appelants internes et regressions migres. Le retour immediat
est toujours `[]`, avec un event emis, sans `detected_ids` ni souvenir premature.
L'action BT `passive_detection` consulte `Sim.active_sonar_contacts` a chaque
passage du BT apres le tick d'onde, via les memes dependances serveur/headless.
Le passif reste echantillonne a 1 Hz, sans double appel capteur ; les contacts
sont dedupliques par ID. Les snapshots copient XYZ et `observed_at` du fournisseur,
sans charger la position courante depuis le miroir `players` (humain sans `sid`
inclus). Une revelation masquee alimente seulement la memoire figee, jamais les
IDs courants ni un nouvel instant frais ; une expiration retire le contact actif.
La memoire BT et ses tirs existants vers un point observe restent autorises selon
leurs regles, sans suivi cache. Cooldowns BT inchanges : autodest 10/20 s, defaut
d'action 30 s. Pas de modification des JSON de coques/arbres, du canon, des
torpilles ou du sonar humain local. Tests : `test_bt_sonar.py` (vrai autodest
headless), regressions RL conservees avec leur appel differe unique.
Changement semantique sans nouvelle version de schema ; anciens scores non
directement comparables. Le canon physique partage est desormais implemente en
etape 2; tir torpille sans cible et reevaluation restent differes. Canonisation humaine serveur,
RNG dynamique global et parite navigateur/reseau restent hors perimetre.

Le radar JS conserve un snapshot XYZ des revelations, fige en occlusion et purge
a expiration ; une LOS alliee autorisee permet le rafraichissement. La selection
sonar ne recopie plus le mesh cache. Torpille sur souvenir : `fixedTarget` XZ sans
`targetId` ; grenades simples/salves : XYZ observe ; canon sur point copie depuis
l'etape 2, y compris souvenir masque sans guidage par ID. La voie humaine de torpille
au point conserve sa profondeur de lancement existante, sans ajouter de champ Y.
Selection, tooltip, radar et affichage 3D des torpilles utilisent le meme filtre
radar courant (portee, LOS ennemie, thermocline ; exemptions own/fullmap existantes).
Une torpille masquee est deselectionnee et ne fournit aucun tir anti-torpille.
Les points de trainee deja visibles vieillissent sans ajout de points caches.

Tests : `rl/test_active_sonar.py`, `rl/test_bot_fire_los.py`,
`test_live_contacts.py` et `tests/test_live_contacts.js`. Le reseau transporte
encore des etats caches : ces corrections du client normal ne sont pas une
frontiere de securite. Validation humaine serveur par ID, interpolation/latence,
capteurs allies/balises/drones et parite globale restent a auditer ; voir le suivi.

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
venv/bin/python -m rl.train_ai --config rl/configs/aisub_v14.json \
  --stage scripted --run-name aisub_v14_scripted \
  --resume rl/models_rl/aisub_v13_scripted/best/best_model.zip
```

Les huit environnements affrontent un mélange équilibré de sous-marins
`autosub` et de destroyers `autodest`. Une évaluation agrégée se déroule sur
`world_testCombats.json` et conserve le meilleur modèle dans
`rl/models_rl/aisub_v14_scripted/best/best_model.zip`.

### Phase 2 : ligue self-play

```bash
venv/bin/python -m rl.train_ai --config rl/configs/aisub_v14.json \
  --stage selfplay --run-name aisub_v14_selfplay \
  --resume rl/models_rl/aisub_v14_scripted/best/best_model.zip
```

Le checkpoint initial et les snapshots périodiques alimentent le répertoire
`league/`. À chaque épisode, l'adversaire est choisi entre une politique
historique sous-marine et le mélange BT sous-marin/destroyer. Les politiques
RL décident à la même fréquence.

### Évaluation et jeu live

```bash
venv/bin/python -m rl.evaluate_ai \
  rl/models_rl/aisub_v14_selfplay/best/best_model.zip \
  --maps combats,testCombats \
  --opponents submarine/autosub,destroyer/autodest --episodes 100
```

Dans la console du navigateur, `spawnRlBot("aisub_v14_selfplay")` charge d'abord `best/best_model.zip`,
puis `policy_final.zip` si aucun meilleur modèle n'existe. La forme des espaces
d'observation et d'action est validée au chargement ; un échec replie le bot sur
`autosub` et écrit la cause dans le journal serveur.

### Sélection et déploiement des modèles live

Les boutons `Sub IA` / `Destroyer IA` utilisent les clés à la racine de
`config/conffile.json`, avec les champions actuels comme valeurs par défaut :

```json
{
  "bot_rl_sub": "aisub_v15_scripted",
  "bot_rl_destroyer": "aidest_v3_scripted",
  "server": { "port": 7000 },
  "world": { "dayDurationSeconds": 1800 }
}
```

`bub` est intentionnel. `rl/model_config.py` valide les identifiants au démarrage
et ne publie que ces deux valeurs dans `init.botRlModels`. Le client ajoute
`rl_` à la sélection lors de `spawn_bot` ; aucune version plus récente ne la
remplace automatiquement et aucun accès HTTP au fichier de configuration
n'est ajouté. Une valeur absente utilise le défaut ; une valeur invalide
interrompt le démarrage avec le nom de la clé.

La syntaxe existante `run:checkpoint` reste disponible, par exemple
`"bot_rl_destroyer": "aidest_v4_scripted:policy_250000_steps"`. Le runtime cherche
ce fichier à la racine du run puis dans `checkpoints/`, avec `.zip` facultatif.
Sans checkpoint : `best/best_model.zip`, sinon `policy_final.zip`. Les identifiants
ne sont pas des chemins ; la résolution refuse aussi les liens sortant de
`models_rl`. Les espaces observation/action sont toujours validés pour le bateau
au chargement. Un échec conserve le repli journalisé `autosub` / `autodest`.
Redémarrer puis reconnecter le client pour appliquer une nouvelle sélection.

Sur la machine cible, `./update_server.sh [utilisateur@source] [/chemin/source]`
conserve la mise à jour Git fast-forward puis utilise `rl/sync_models.py` :
inventaire récursif via SSH/Python 3, copie SCP de **tous** les ZIP sous
`rl/models_rl`, dossiers conservés (`best`, `checkpoints`, finaux, `league`,
`archive`, toutes versions). Aucun log, TensorBoard ou rapport n'est copié,
aucune suppression des artefacts propres à la cible, aucune promotion.
Le dépôt doit être propre et une différence distante de `config/conffile.json`
bloque le pull pour imposer une réconciliation explicite, sans écrasement local.

Les chemins et liens cibles sont contrôlés ; chaque ZIP est vérifié par CRC
et présence des membres SB3, sans chargement pickle. Tous les transferts sont
validés avant installation ; le staging est sur le système de fichiers cible
et `os.replace` est atomique par fichier, pas pour l'ensemble des modèles.
Une panne pendant l'installation peut donc laisser un mélange de versions.
Utiliser une source SSH de confiance et stable pendant la copie, prévoir
l'espace pour tous les ZIP. Pas de dépendance `rsync`, seulement SSH/SCP et
Python 3 local/distant ; chemin source absolu sans espaces. Le script ne lance
ni n'arrête le serveur : redémarrage explicite pour vider le cache RL.

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
venv/bin/python -m rl.train_ai --config rl/configs/aidest_v1.json \
  --stage scripted --run-name aidest_v1_scripted --device cuda
```

Le nombre de threads est limité car chaque worker charge la politique adverse
sur CPU. Après évaluation, la ligue destroyer peut reprendre le meilleur modèle
scripted avec `--stage selfplay --run-name aidest_v1_selfplay --resume <modele>`.
Les snapshots de cette ligue restent des destroyers, tandis que le sous-marin RL
gelé demeure dans le mélange d'adversaires.

L'évaluation et le chargement live précisent la coque contrôlée :

```bash
venv/bin/python -m rl.evaluate_ai rl/models_rl/aidest_v1_scripted/best/best_model.zip \
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
venv/bin/python -m rl.train_ai --config rl/configs/aidest_v2.json \
  --stage scripted --run-name aidest_v2_scripted \
  --resume rl/models_rl/aidest_v1_scripted/best/best_model.zip --device cuda
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
venv/bin/python -m rl.train_ai --config rl/configs/aidest_v3.json \
  --stage scripted --run-name aidest_v3_scripted --device cuda
```

Le run v3 affronte `submarine/autosub` et le meilleur sous-marin RL gelé avec
une probabilité de 50 % chacun. Son curriculum étend progressivement les
distances de 600-1 200 m vers 600-2 000 m. L'évaluation indépendante couvre les
deux familles d'adversaires :

```bash
venv/bin/python -m rl.evaluate_ai \
  rl/models_rl/aidest_v3_scripted/best/best_model.zip \
  --agent-boat-type destroyer --opponents submarine/autosub \
  --opponent-pools rl/models_rl/aisub_v14_selfplay/best \
  --opponent-pool-boat-type submarine --episodes 100
```

Dans la console du navigateur,
`spawnRlBot("aidest_v3_scripted", false, "", "destroyer")` charge le meilleur
checkpoint v3 compatible. Dans la fenêtre `Unités`, les boutons `Sub IA` et
`Destroyer IA` chargent respectivement les meilleurs checkpoints de
`aisub_v15_scripted` et `aidest_v3_scripted`, dans l'équipe choisie.

Après les 5 millions d'étapes, une évaluation indépendante de 100 épisodes par
adversaire et par candidat a confirmé le checkpoint `best_model.zip` issu de
3,6 millions d'étapes : 24 % de victoires contre `autosub` et 43 % contre
`aisub_v14_selfplay`. Le modèle final obtient respectivement 15 % et 36 % ; il
n'est donc pas promu.

### Phase 4 : alternance sous-marin v15

`aisub_v15` reprend le meilleur sous-marin v14 avec un taux d'apprentissage et
une entropie réduits. Il affronte le meilleur destroyer v3 gelé dans 50 % des
épisodes ; les autres duels restent répartis entre `submarine/autosub` et
`destroyer/autodest`. Un curriculum court passe de 600-1 200 m aux distances
complètes de 600-2 000 m :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  venv/bin/python -m rl.train_ai --config rl/configs/aisub_v15.json \
  --stage scripted --run-name aisub_v15_scripted \
  --resume rl/models_rl/aisub_v14_selfplay/best/best_model.zip --device cuda
```

Après 3 millions d'étapes, six candidats ont été évalués sur les mêmes graines,
avec 100 épisodes contre chacun de `autosub`, `autodest` et le meilleur
destroyer v3. Le checkpoint 500 k est retenu : 32/10/58, 74/3/23 et 61/34/5
(victoires/défaites/nuls), soit un score de match agrégé de 70 %. Il remplace
`best_model.zip` ; le meilleur du callback à 400 k est conservé sous
`archive/callback_best_model.zip`.

### Phase 5 : alternance destroyer v4

La sélection automatique ne repose plus sur la récompense moyenne. Le callback
évalue chaque adversaire séparément et conserve le meilleur score pondéré
`victoire + 0,5 × nul` dans `best/best_model.zip`. Les détails sont écrits dans
`evaluation/match_scores.jsonl` et `best/selection.json`.

`aidest_v4` reprend le champion v3, affronte à parts égales `autosub` et le
champion `aisub_v15_scripted`, et conserve l'interface `destroyer_duel_v2`. Le
taux d'apprentissage et l'entropie sont réduits pour un raffinement de 2 millions
d'étapes :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  venv/bin/python -m rl.train_ai --config rl/configs/aidest_v4.json \
  --stage scripted --run-name aidest_v4_scripted \
  --resume rl/models_rl/aidest_v3_scripted/best/best_model.zip --device cuda
```

Après 2 millions d'étapes, le callback retient le checkpoint 300 k avec un
score interne de 50 %. L'évaluation indépendante compare ce candidat au
champion v3 sur deux séries de graines et 200 épisodes par adversaire. V4
obtient 65/35/100 contre `autosub` et 55/128/17 contre `aisub_v15` ; v3 obtient
respectivement 32/5/163 et 58/128/14. Les deux modèles atteignent exactement
44,625 % au score agrégé. V4 ne satisfait donc pas le gain minimal de trois
points et n'est pas promu ; le bouton `Destroyer IA` reste sur v3.
