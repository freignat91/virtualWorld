# Suivi de l'audit RL

## Training V5 Actif (2026-09-10)

Derniere autorisation explicite executee : PID210501 depuis01:09:11+02:00,
actif a01:10:30+02:00, run neuf `aidest_v5_scripted_seed1542`, CUDA RTX5080,
huit workers, warm-start v4best300k intact, seed1542/config2M inchangee.
Premier rollout8192 puis24576 steps/523FPS cumules apres optimiseur ; pertes/KL
finis, aucun resultat d'evaluation encore disponible (premiere a100k).
Snapshot98 fichiers incluant Python non suivis/configs/cartes/coques/BT,
git diff/statut/revision et SHA sous `models_rl/launch_manifests/aidest_v5_scripted_seed1542/`.
98 empreintes et modeles v3/v4/sub15 verifies inchanges apres lancement,
avant les presentes mises a jour documentaires. Commande, PID, SHA complets,
ressources et limites dans TRAINING_RL.md ; log actif dans
`/tmp/virtualWorld_aidest_v5_scripted_seed1542.log`.
Remplace les statuts historiques "non lance", pas les limites de validation.
Training NON termine ; aucune promotion/deploiement/live/reward/ancien ZIP/commit
modifie, aucune promesse de surveillance automatique apres ce tour.

## Diagnostic80 Termine (2026-09-10)

Nouvelle autorisation explicite executee : 80 duels instrumentes v3/v4 best300k,
autosub/sub15, graines98000-98019 ; deux jobs exit0 CPU mono-thread,79 empreintes
inchangees chacun. Voir `DUEL_DIAGNOSTICS.md` pour les comptes et les artefacts.
Scores premier endpoint67,50/76,25%, settling65,00/73,75% ; quatre W->D,
aucune borne600s atteinte. V4 :432 torpilles dont354blind avant endpoint,
93,79% des degats adverses dus aux grenades. Aucun nouveau bug physique confirme.
Flags de penalite, rewards, regles et fins standard inchanges ; runner dedie
sans inference des morts, avec controles natifs des survivants. Le parent est
explicitement autorise pour le training autonome ulterieur, non lance ici.
Recommendation unique : warm-start v4best300k, ~2M nouveaux steps,seed1542,
nouveau repertoire, autres parametres v4 scripted inchanges ; aucune promotion.
Cette autorisation remplace les interdictions historiques de cette campagne,
pas les limites de validation humaine/reseau ni l'interdiction d'ecraser les ZIP.

## STEP4 Reevaluation Terminee (2026-09-10)

Autorisation explicite executee apres STEP1/2/3, HP 200/100/10 : six jobs CPU
mono-thread, 1200 matchs valides, testCombats, config/reward aidest_v4 exacte,
100 episodes/adversaire/serie 96000 et 97000, autosub et sous-marin v15 best gele.
Tous exit 0/stderr vide, 125 hashes de lancement inchanges apres execution.
Scores 50/50 v3/v4 300k/v4 2M : 67,00/75,50/66,50 % ; differences a v3
+8,50 [4,727 ; 12,273] et -0,50 [-4,481 ; 3,481] points, IC 95 % apparies
groupes par graine entre adversaires (200 graines, 400 paires/comparaison).
Archive neuve `models_rl/aidest_v4_scripted/evaluation/rules_steps123/` ;
W/L/D, hashes exacts, ressources, protocole et limites dans FAIRNESS_EVALUATION.

V4 300k tire 10,3125 torpilles et fait 147 demandes d'armes invalides/episode,
contre 0,3425 et 42,245 pour v3 ; epuisement acoustique 23/400 contre 0/400.
Pas d'etiquette de tir aveugle, raison de rejet ou degat attribue aux armes :
consommation mesuree, gaspillage/causalite non demontres. V15 garde ses poids
mais subit aussi les nouvelles observations/regles. Robustesse limitee a cette
suite, aucune fusion avec anciens scores. Evaluation au premier mort/300 s,
contrairement a l'autogame avec attente des torpilles/600 s ; terminaison inchangee.

247 tests Python passes, analyseur reutilisable corrige pour covariance et teste.
Aucun gameplay, modele, reward, config, training long, promotion, deploiement,
live ou commit. Ces resultats remplacent uniquement le statut "reevaluation
differee" des notes historiques ci-dessous, pas leurs limites de validation.
Avant tout RL long : proposer 80 trajectoires instrumentees v3/v4 300k sur
nouvelles graines, contexte des tirs/rejets et sensibilite au settling, sur
autorisation distincte ; revue humaine/live et charge de production restent dues.

## Etape 3 Torpilles Sans Contact (2026-09-09)

Les actions RL acoustique/autonome peuvent tirer sans contact observe ou memorise
si ammo/cooldown permettent : point initial et ID nuls, cap/profondeur de lancement
natifs, activation JSON (500 m), aucune coordonnee cachee/predite. Les tirs avec
contact conservent le point copie et l'heuristique d'activation 500/200 m. Sim ne
cherche une cible qu'apres activation par capteurs natifs, LOS/portee/thermoclines.
Humains : second clic sur le bouton sans selection tire dans l'axe ; radar manuel
et filoguidage conserves, ID explicite invalide toujours rejete. BT direct audible
peut tirer sans contact, mais gating des arbres et FSM de combat conserves.

Observation/action dimensions et versions, rewards, modeles et champions inchanges.
Gaspillage de munitions par les politiques existantes attendu, pas de compensation
reward ; tous scores historiques non directement comparables. Reevaluation reste
differee ; aucun serveur/train/eval/deploiement/commit autorise. Voir TECHNIQUE et
`rl/test_targetless_torpedo.py`, `test_server_fire_los.py`,
`tests/test_targetless_torpedo.js`. Remplace les mentions de torpille sans cible
encore differee dans les etapes historiques ci-dessous.

## Etape 2 Canon Physique (2026-09-09)

La limite historique canon par ID decrite plus bas est remplacee par
`Sim.fire_cannon`, commun aux humains/BT/RL, et `update_cannon_shells` sur horloge
Sim. Visee copiee observee/memorisee ou point manuel, jamais lookup futur pour
guider. Parabole visuelle historique 500 m/s et dispersion 8 m conservees;
premier contact reel, ile ferme exacte, coque cylindrique demi-longueur existante
et tolerance verticale 4 m. Plongee sous flotation, mouvement et obstacles
permettent d'eviter les degats; tir ami natif et obus posthumes possibles.
Balises et mines de surface passent aussi par la trajectoire, sans nouveaux HP.
DCA distincte inchangee. Voir TECHNIQUE pour derives, approximation et protocole.

Tests reels : root `test_cannon_ballistics.py`, handlers AST `test_server_fire_los.py`,
regressions contact/memoire/profondeur/pipeline RL et `tests/test_cannon_ballistics.js`.
Les attentes anciennes de rejet sur souvenir canon et hit garanti ont ete changees
en tirs au point avec dommages uniquement a collision. Trace whitelist des obus
et evenements CannonFire/Impact/Hit. Aucune shape/version/reward/modele modifie;
historique des scores non comparable. Mouvement des coques echantillonne au tick,
pas de mesh ni collision continue entre deux positions de bateaux; pas de parite
navigateur/reseau/mobile prouvee. Step3 torpilles et reevaluation restent differes.
Aucun serveur live, entrainement/evaluation, deploiement, modele ou commit autorise.

## Mouvement BT, Cap Initial Et Etiquettes (2026-09-09)

Trois corrections confirmees, testees separement : `_drive_to_waypoint` bloque
segment exact/endpoint ile et bord du monde, XZ conserves et vitesse nulle ;
recuperation existante preservee, aucune nouvelle aide automatique. Les lanceurs
Sim bots acoustique/autonome partent dans le cap du bateau, conservent snapshot
XYZ sans targetId et virent uniquement par le guidage normal. Les trois etiquettes
client utilisent **Point de référence** plutot qu'une acquisition deduite de tx/tz.
Aucun protocole/booleen de lock ennemi ajoute ; cercles = activation seulement.

Tests : root `test_bt_movement.py`, `rl/test_launch_heading.py`,
`rl/test_bot_fire_los.py`, `rl/test_torpedo_guidance.py` et
`tests/test_torpedo_reference.js` (fonctions JS reelles avec DOM simule).
Sans lancement live, evaluation, training, deploiement, commit ou edition de modele.
Schemas, rewards et champions inchanges, mais scores historiques non directement
comparables, y compris les evaluations precedemment dites "corrigees".
Equite globale et parite navigateur/reseau/mobile toujours non prouvees.

Restent a decider avant le plan RL : sonar canonique humain local (front 5 s)
pour tous OU contrat BT synchrone explicite pour tous ; canon avec rejet actuel
sur souvenir non suivi OU vraie balistique partagee sur point/impact autoritaire.
Offset torpille bot 4 m vs humain 15 m et profondeur de depart restent differes ;
pitch initial nul et regles verticales inchanges. Mouvement externe Sim endpoint
seulement inchange ; une unite deja sur ile n'est pas extraite automatiquement.
Voir `TECHNIQUE.md` pour le perimetre exact. Ensuite seulement : validation du jeu
puis reevaluation candidats ET references sous les memes regles, sur autorisation.

Verification locale : 213 tests Python passes sans skip (trois limites de threads
a 1), 7 harnesses Node et variante spectateur vide passes, 66 controles UI de
reference torpille. Compilation Python ciblee, syntaxe JS et diff-check passes.
La fixture de menace entrante regarde maintenant l'observateur au lancement,
sans relacher les assertions radar ni imposer un resultat de combat.

## Equilibrage des integrites (2026-09-09)

Approbation explicite : destroyer 200, sous-marin 100, leurres acoustiques 10 points,
dans les deux JSON reels. `maxIntegrity` par instance, validation finie positive
partagee humain/BT/RL/headless; anciens specs sans cle gardent coque 100/leurre 10.
Observations propres courant/maximum, formes 32/36/40 conservees, aucun HP cache
ennemi ou leurre ajoute. Reset des HP precedents depuis les instances reelles,
shaping inchange par point absolu perdu. Les leurres subissent les explosions 3D
avec HP persistants et notification non letale, sans remboursement ni double retrait.
La trace conserve maxima et evenements publics; ce stockage ne prouve pas la
visibilite client. Autres destructibles differes, aucune capacite inventee.

Tests Sim/headless et handlers serveur AST : `test_integrity.py`; client Node :
`tests/test_integrity.js`; trace : `test_game_trace.py`. Ni navigateur/reseau reel,
ni validation humaine ou nouvelle evaluation des politiques. Tous les scores
precedents restent historiques et non directement comparables apres ce changement
d'equilibrage. Champions inchanges, aucun modele ecrase, aucune promotion/training.

## Machines de verification

Les parties tracees pour analyser les comportements et preparer les ameliorations
des bots se deroulent sur `friatech`. La machine distante est reservee aux tests
humains. Ne pas confondre les mesures locales avec celles du serveur distant.

## Trace serveur disponible, validation humaine en attente

Suivi approuve du classement et des decisions (2026-09-09) : le contre-exemple
historique ci-dessous est maintenant une regression passante, sans expectedFailure.
Sim/BT et RL classent `(eta <= 0, eta)` : projections brutes positives puis les
CPA passes proches, ordre stable a egalite. Les fuyantes ne sont pas supprimees :
elles restent candidates a <= 200 m, notamment pour le risque de proximite/leurre.
Portee, horizon 10 s, filtres radar, schemas et slots prives neutralises inchanges.
Les scores historiques ne sont pas directement comparables apres ce changement.

La trace opt-in `RLDecision` capture maintenant le vecteur reel complet avant
prediction, l'action choisie et les flags exacts apres application, identite
publique du bot, version, timestamp de decision, dt et numero du sous-pas serveur.
L'identite publique owner/tid du slot menace provient du meme passage capteur ;
aucun second appel sonar stochastique. Manifeste `rl_model` deduplique par session,
hash des octets charges une seule fois si trace active au chargement (sinon null).
Pas de BB, SID, verrou de menace ou etat recurrent, pas de broadcast RLDecision.
Tests locaux : `rl/test_decision_trace.py`, trois schemas, vrai RuntimeController,
modele recurrent minuscule sans apprentissage, trace off, erreurs et liste positive.
Voir `TECHNIQUE.md` pour la temporalite et les champs ; les anciennes traces ne
permettent toujours pas de reconstruire les observations absentes.
Recuperation automatique du blocage non modifiee ; aucune nouvelle session humaine,
evaluation de champion ou mesure du cout I/O live dans ce suivi.

Verification locale du suivi : 146 tests passes, aucun echec attendu,
`node --check static/game.js`, compilation Python et `git diff --check` passes.
La suite inclut ses smoke tests existants ; aucun job autonome d'entrainement
ou d'evaluation, serveur, deploiement ou commit n'a ete lance.

`./start.sh --trace --map world` active `logs/game_trace.jsonl` (OFF par defaut,
20 MiB x 6 fichiers). Snapshots serveur 4 Hz pour toutes les familles d'objets,
evenements Sim/legacy filtres, transitions de verrou/contact et manifeste avec
empreintes ; voir `TECHNIQUE.md` pour les contrats et limites exacts.
Les tests stdlib n'ouvrent pas de serveur. Aucun lancement de session humaine,
deploiement, promotion ou entrainement n'est effectue par cette instrumentation.
Pas de nouvel entrainement long avant collecte humaine autorisee et analyse.
Etat stocke autoritaire != preuve de visibilite client, de legalite de chaque
action ou de fairness globale. Les intentions refusees, contacts humains locaux,
replay deterministe et cout I/O en partie reelle restent hors couverture.

## Premiere tranche : reproductibilite et mesure

- `rng.py` isole Python, NumPy, Torch CPU et CUDA deja initialise pendant
  l'evaluation et le chargement d'un adversaire. Restauration aussi sur exception.
- `train_ai.py` synchronise gamma/lambda du modele repris et du buffer GAE.
- `evaluate_ai.py --report --config ...` conserve les resultats par episode,
  graines, options effectives et empreintes SHA-256 des artefacts.
- La sortie agregee historique reste le mode par defaut.
- Aucun changement de reward, d'espace, de champion ou de regle de combat.

Ces protections sont sequentielles et locales au processus, pas un mecanisme
d'isolation pour plusieurs threads utilisant les memes RNG. Les pools doivent
rester immuables pendant une evaluation : le manifeste ne verrouille pas les ZIP.
Les rapports ne constituent pas encore un manifeste complet du code, des cartes
et des specifications de bateaux. La signature du callback doit encore integrer
les contenus des adversaires, pas seulement leurs chemins.

## Diagnostics de fairness

`test_fairness_diagnostics.py` rejette maintenant l'acquisition sonar et le tir
dans la meme action sans contact preexistant ; l'ancien diagnostic est remplace.
L'ancien diagnostic de torpille cachee est devenu une regression de radar strict.
Les chemins Sim/headless sont executes ; la comparaison au navigateur et au
handler humain repose sur la lecture du code, pas sur une execution reseau.

### Correction minimale : profondeur cible du canon RL

Le destroyer RL (v1 et v2) rejette maintenant une cible si
`y < -boat.get("flotation", 2) / UNIT_METERS_BOT - 0.05`, comme le handler
humain `server.py::fire_cannon_intent`. La limite exacte reste autorisee :
2,5 m avec la flottaison actuelle de 2 m, au lieu de l'ancien seuil RL de 6 m.
Le test canon est devenu une regression Sim/headless : surface, limite exacte,
valeurs flottantes voisines, ancien cas 4,5 m, cible profonde, flottaison variable
et valeur par defaut. Un refus ne consomme ni munition ni cooldown et ne programme
aucun impact ni degat differe. Le handler reseau lui-meme n'est pas execute.

Aucun changement de sonar, torpille, reward ou champion. Les shapes d'observation
et d'action restent compatibles avec les checkpoints existants, mais les metriques
de resultat avant/apres ne sont pas directement comparables : tirs, degats et
penalites deja configurees peuvent changer. Reevaluer candidats et references
avec les memes regles corrigees ; les resultats ci-dessous restent historiques,
anterieurs a cette correction.

### Radar strict RL : decision utilisateur appliquee

La premiere correction associait le verrou a `(ownerPlayerId, tid)` pour eviter
les collisions d'identifiants locaux. Elle est maintenant depassee : le verrou
exact et le type sont neutralises a zero dans les trois schemas, sans retirer
de slot. La regression de collision de `tid` exige desormais cette neutralite.

Le helper partage `rl_control.py::_torpedo_observation` applique avant selection :
- portee horizontale `boat.radarRangeMeters`, sinon 30000 m, egalite incluse
  (`static/game.js:2045,4475-4484` ; valeur explicite destroyer, defaut sous-marin) ;
- LOS depuis le bot seul, sans relais allie ni exception fullmap/3D ;
- aucune thermocline croisee entre bot et torpille
  (`static/game.js:5270-5278`, `geometry.count_thermoclines_crossed`) ;
- LOS Python partagee plus echantillons `ceil(distance/5)` du client quand les
  grilles different (`static/game.js:3844-3868`). C'est volontairement conservateur :
  une ile vue seulement par la grille Python peut encore bloquer le RL.
  Aucun changement global de `geometry.py`.

La selection ne passe plus par `Sim.bot_torpedoes_threat`, dont le verrou ajoutait
des candidats et forcait ETA=0. Elle reutilise `geometry.closest_approach_on_segment`
et son cas non verrouille : vitesse > 0,001 u/s, projection plane de 10 s,
CPA <= 200 m, ETA bornee a [0,10] s. Depuis le suivi de classement, ETA positives
avant ETA nulles, ordre stable a egalite ; torpilles propres toujours exclues.
La distance ne departage pas les ETA. Position/direction/vitesse suffisent : aucun
acquiredBoatId, tid, cible d'acquisition ou type n'intervient dans la selection.

`server.py::_dispatch_torpedo_state` ne transmet pas `acquiredBoatId` et les
dispatchers acquisition/alert sont des `pass`. `static/game.js:7802-7809` masque
explicitement le type ennemi hors fullmap. Les deux slots restent donc inconnus
(zero), y compris pour les torpilles alliees par simplification conservative.
L'etat "en acquisition" du tooltip n'est pas un verrou exact sur l'observateur.

Limites : positions et vitesses instantanees Sim, pas d'estimation sur historique
radar ni de latence/interpolation navigateur ; approximation plane historique
`direction * speed` sans correction du pitch. Les helpers thermocline partagent
les regles des cartes normales, sans pretendre aligner les donnees invalides
(ex. profondeur nulle avec fallback JavaScript). La parite reseau complete et
le diagnostic de timing sonar restaient ouverts a cette tranche radar. La correction
sonar ci-dessous est ulterieure ; Sim/BT, sonar et rewards etaient alors inchanges.

Shapes, versions et chargement des checkpoints preserves, mais changement
semantique des observations : trajectoires et metriques avant/apres ne sont pas
comparables. Reevaluer candidats ET references plus tard sous le radar strict.
Aucun checkpoint existant ecrase, aucun run hors tests ni deploiement.
Validation : 44 tests via `venv/bin/python -m unittest -v`, avec
`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1` ; invariance complete
avec torpille cachee seule ou devant une visible, LOS ceil, limites de portee,
trois schemas, collisions de tid, inclusion/ordre/ETA independants du verrou.
Compilation (`compileall`) et `git diff --check` OK.
Les smoke tests existants utilisent leurs artefacts temporaires.

### Sonar BT/RL : etape 1 temporelle partagee

BT consomme les revelations acquises via `Sim.active_sonar_contacts`, branche
dans les dependances serveur/headless. Rafraichissement actif a chaque passage
de perception BT, passif cache a 1 Hz, un seul contact par ID, XYZ et date copies
du fournisseur. Un souvenir masque n'est ni un ID detecte courant ni une nouvelle
observation fraiche ; aucun chargement live cache dans les snapshots/RETREAT.
Cooldowns autodest 10/20 s et defaut 30 s preserves. `test_bt_sonar.py` execute
le vrai arbre autodest : distance/5 s, pas de tir au tick d'emission, gel/reprise,
expiration 10 s, plusieurs couches/cibles avec un tirage par ping/cible, miroirs
serveur sans sid et absence de duplication capteur/event. Regressions RL
temporelles/LOS/identite conservees ; aucune nouvelle version de schema/reward.
Les scores historiques ne sont pas directement comparables. Etapes canon
physique partage, torpille sans cible et reevaluation differees ; aucune evaluation,
campagne d'entrainement, modification de modele, lancement serveur ou commit.
Sonar humain local inchange ; canonisation serveur complete, politique RNG
dynamique globale et parite navigateur/reseau restent hors perimetre.

Reference choisie : ping propre local humain, pas le ping recu/allie dont les
metres sont actuellement interpretes comme unites monde cote radar (bug separe).
`Sim.bot_sonar_ping(..., timed=True)` emet un seul event compatible puis attend
`Sim.step`. Aucune cible ni position cachee n'est memorisee a l'emission.
Le contrat BT synchrone par defaut est preserve. Aucun timer propre au headless.

Front lineaire sur 5 s, origine et cone d'emission fixes, expiration stricte
avant detection a 5 s. Pour 8000 m / 30 degres : 1000 m a 0,625 s, 4000 m a
2,5 s, maximum exact jamais acquis. Resolution au premier tick admissible
(20 Hz normalement), puis observation/decision RL a 4 Hz. Cibles mobiles
evaluees a leur position courante ; elles peuvent sortir ou entrer dans le front
pendant le ping. LOS, cone, portee et thermoclines controles a l'acquisition.
Un tirage de penetration par ping/cible au premier croisement eligible, reutilise
ensuite ; echec non bloquant si la cible revient du meme cote de la thermocline.
Pas de chance de detection selon vitesse/bruit. Revelation locale a portee
`activeSonar.reveal` de l'emetteur courant, sans relais allie. LOS conservatrice
Python plus grille ceil navigateur ; aucune modification du helper global/BT.

Revelation 10 s depuis acquisition, non prolongee par les ticks : positions
courantes legitimes pendant cette fenetre, meme apres sortie de portee/cone/LOS.
Puis souvenir fige de la derniere observation, expiration apres 30 s ; le sonar
expire ne permet plus le tir via la tolerance historique de fraicheur de 1 s.
Le passif continue normalement et peut permettre un tir simultane au ping.
Cooldown 30 s et comportement d'attente pendant cooldown inchanges.
Un seul contact selectionne par proximite parmi passif/actif ; reward existant
de transition vers contact frais, pas une reward par tick de revelation.

`test_active_sonar.py` couvre deux schemas, distances/frontiere, mouvement,
revelation/expiration, LOS/portee/eligibilite, tirages uniques multi-cibles,
events/cooldown, cible humaine sans sid, nettoyage/reset, RuntimeController et
reward/comptage via les vrais ticks Headless/Sim. L'ancien test instantane est
devenu un refus suivi d'un tir apres acquisition. Aucun test navigateur/reseau.
Shapes et versions chargeables inchangees ; semantique modifiee, reevaluer
candidats ET references avant toute promotion. Aucun checkpoint ecrase.
Validation finale : 54 tests passes via `venv/bin/python -m unittest -v`, avec
`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1` ;
`venv/bin/python -m compileall -q simulation.py rl` et `git diff --check` OK.
Les smoke tests existants utilisent uniquement leurs artefacts temporaires.

## Petite comparaison apres isolation RNG (historique)

Protocole : carte `testCombats`, graines 91000 a 91019, 20 episodes par adversaire,
inference CPU deterministe, options d'environnement et reward de `aidest_v4.json`.
Adversaires : `autosub` et champion sous-marin v15. Aucun apprentissage.

| Candidat | Autosub V/D/N | V15 V/D/N | Score agrege |
|---|---|---|---|
| Champion v3 | 2/2/16 | 7/12/1 | 43,75 % |
| V4 retenu, 300k | 5/5/10 | 6/14/0 | 40,00 % |
| V4 tardif, 2M | 3/4/13 | 5/14/1 | 37,50 % |

Score = (victoires + 0,5 * nuls) / episodes, poids egaux entre adversaires.
Les trois rapports complets sont conserves localement sous
`models_rl/aidest_v4_scripted/evaluation/audit_rng_isolated/` dans ce repertoire.

Ce petit echantillon valide le protocole et reste compatible avec une degradation
tardive ; il ne demontre ni une difference significative ni une cause. Les memes
graines permettent une analyse appariee ulterieure, mais ne garantissent pas les
memes tirages de combat apres divergence des actions. Ne pas fusionner ces
resultats avec les anciens rapports : isolation RNG et reward explicite changent
le protocole. Aucun modele n'est promu.

## Reevaluation corrigee terminee le 2026-09-09

Six evaluations independantes CPU mono-thread sont terminees : v3, v4 300k et
v4 2M, chacun sur les series 92000 et 93000, 100 episodes par adversaire
(`autosub`, sous-marin v15 gele), `testCombats`, config/reward v4 explicite.
1200 matchs valides sous canon corrige, radar strict et sonar RL differe ; six
codes de sortie zero et 38 hashes d'entrees inchanges apres completion.
Scores 50/50 : v3 54,000 %, v4 300k 60,875 %, v4 2M 45,250 %.
Ecarts apparies a v3 : +6,875 points [2,447 ; 11,303] et -8,750
[-13,708 ; -3,792] (IC 95 % analytique, quatre strates a poids fixes).
Voir `FAIRNESS_EVALUATION.md` pour W/L/D, detail par graine et limites.
Le repertoire local `models_rl/aidest_v4_scripted/evaluation/fairness_corrected/`
conserve diff initial, archive des sources/entrees, hashes et manifeste des jobs.
HEAD seul ne suffit pas a identifier les corrections non committees.

Ajout de `analyze_evaluation_reports.py` et de trois tests : validation des issues,
graines et identites, differences appariees a poids fixes et IC analytique 95 %.
57 tests passes avec les regressions Sim/RL ; aucune modification de production,
champion, reward ou entrainement. V4 300k passe les seuils ponctuels mais son IC
ne garantit pas +3 points ; v4 2M regresse surtout contre autosub. Ni preuve
d'equivalence ni cause identifiee. Prochaine experience recommandee, non lancee :
v3/v4 300k, serie 94000, 400 matchs au total ; validation humaine/latence requise
avant promotion. Les rapports historiques restent separes.

## Confirmation 94000 terminee le 2026-09-09

Le plan ci-dessus a ete execute sans relancer les six jobs precedents : v3 et
v4 best 300k seulement, 100 matchs par adversaire sur 94000-94099, 400 matchs
valides, deux codes zero, stderr vide, NLWP=1. Memes regles, config/reward v4,
testCombats et adversaires geles. Scores frais 55,25 % contre 58,00 % ; gain
+2,75 points, IC 95 % groupe par graine [-3,073 ; 8,573]. Cumul des trois series
pour ces deux modeles uniquement : 54,416667 % contre 59,916667 %, +5,50 points
[2,016 ; 8,984]. 600 paires de matchs, mais seulement 300 graines distinctes.

L'analyseur existant est reutilise sans modification ; la reanalyse locale
conserve la covariance entre adversaires partageant une graine, au lieu de
supposer les strates independantes. Confirmation post hoc apres selection,
pas de nouveau gate statistique ni de preuve que le gain frais soit positif.
Voir `FAIRNESS_EVALUATION.md` pour les deux methodes, W/L/D, IC et limites.
Nouveau repertoire ignore `fairness_corrected/confirmation_94000/` : manifestes,
rapports complets, diff/code sale archive, 40 hashes d'entrees inchanges,
reproduction de l'analyse et captures des 57 regressions plus 3 tests covariance.
Compilation et `git diff --check` OK ; les tests smoke ont leurs modeles temporaires.

Aucun changement gameplay/reward/runtime/champion, aucun entrainement
experimental ni commit. Revue humaine non faite, latence de production non
mesuree faute de cible CPU accessible identifiee : aucune promotion. La prochaine
action est d'identifier cette cible et faire la revue humaine, puis mesurer les
deux vrais `RuntimeController.model.predict` CPU apres warmup, >=100 mesures,
p50/p95/p99/max et threads documentes, hors simulation/reseau/multi-bots.

## Benchmark local friatech du 2026-09-09

La mesure locale autorisee est maintenant terminee, sans etablir friatech comme
representative de production : i9-12900F, Linux 7.0.0-30-generic, Python 3.12.3,
Torch 2.11.0, intra-op=1/inter-op=1, OMP/MKL/OpenBLAS=1 dans le seul processus CLI.
Le nouveau `rl/benchmark_inference.py` appelle le vrai `load_model` CPU et
`RuntimeController.model.predict` recurrent deterministe. Corpus de 64 observations
headless reelles par modele, prepare hors chrono ; 100 warmup et 1000 mesures,
etat conserve entre decisions et reset aux frontieres d'episode/corpus.

| Modele | p50 ms | p95 ms | p99 ms | Max ms | Moyenne ms | Predictions/s |
|---|---|---|---|---|---|---|
| v3 champion | 0,442635 | 0,460407 | 0,482280 | 0,553090 | 0,443825 | 2253,14 |
| v4 best 300k | 0,440122 | 0,461595 | 0,484843 | 0,509959 | 0,442058 | 2262,15 |

Archive sans ecrasement :
`rl/models_rl/aidest_v4_scripted/evaluation/latency_friatech/20260909_threads1/results.json`.
Latences brutes, hashes ZIP/corpus/sources, environnement et options conserves ;
entrees verifiees inchangees. Commande et SHA-256 complets dans
`FAIRNESS_EVALUATION.md`, section Latence CPU Locale Friatech. Aucun benchmark
separe des defauts natifs ; aucun changement des defaults threads de production.

Exclut simulation, observation, application d'action, reseau et charge multi-bots ;
le debit est celui de predict seul, pas celui du jeu. Corpus court repete, pas un
match complet. **Latence de production et inspection humaine toujours manquantes**,
aucune promotion ni validation du budget complet de 250 ms. Aucun gameplay,
champion ou runtime modifie, aucun serveur lance ni commit. Le parent/utilisateur
garde le demarrage du test local et la revue v3/v4 (passivite, tirs invalides,
sonar, absence d'omniscience) ; le benchmark ne remplace pas cette revue.
Verification : 56 tests RL, dont 3 dans `rl/test_benchmark_inference.py`, et
4 tests simulation passes ; compilation des nouveaux modules et diff check OK.

## Perception LOS et tir sur souvenir (2026-09-09, correction utilisateur)

La LOS ne constitue pas une interdiction globale de tirer vers un ancien contact.
Elle interdit de rafraichir sa position cachee ou de l'acquerir sans capteur. Le helper
`Sim.bot_target_los` utilise la LOS exacte fermee deja presente dans le worktree,
pas l'ancien echantillonnage floor/ceil decrit dans la tranche radar historique.

- BT et fallback legacy copient XYZ, horodatage et metadonnees au moment de la
  detection. Les selections de tir n'accedent plus aux positions courantes des
  joueurs ; salves/combat/contre-attaque peuvent utiliser le dernier snapshot
  pendant la validite existante (30 s, configurable pour les salves).
- RL : `_update_contact` ne rafraichit plus les coordonnees masquees par une ile ;
  `_contact_target` retourne un snapshot, jamais le joueur courant par ID.
  Le dernier point observe reste memorise ; aucune modification des durees de
  revelation, de memoire ou de validite de tir, ni des thermoclines.
- Torpilles et grenades : suppression des refus LOS globaux au lancement.
  Les torpilles sur snapshot ont `targetId=None` : pas de resolution live dans
  les evenements ni de priorite radar accordee a l'ancien ID. Acquisition future
  soumise aux capteurs normaux et a la geometrie exacte inchangee.
- Canon : aucun chemin de tir au point existant, seulement des degats differes
  par ID. Refus sur memoire non suivie ou cible actuellement masquee, sans effets.
  Un vrai tir aveugle exige de definir une balistique/validation d'impact partagee,
  pas d'inventer un auto-hit. DCA et intentions humaines inchangees.
- `rl/test_bot_fire_los.py` : vrais Headless/Sim et actions BT/RL, trois schemas,
  acquisition puis positions/profondeurs cachees differentes : memes caps, visees,
  activations et evenements, munitions consommees, aucun faux contact ni hit canon.
  Expirations, acquisition capteur, snapshots sonar/legacy, DCA et bords inclus.

Aucun coefficient de reward, schema, checkpoint, champion ou resultat archive
modifie. Les actions autorisees peuvent changer les penalites effectivement
recues et les resultats : les evaluations precedentes restent historiques.
Pas de nouveau run, commit, pathfinding ni trace/audit global dans cette tranche.
Limites : attaque automatique des drones non corrigee ici ; armes deja lancees
et degats de zone inchanges. La DCA garde sa comptabilite existante (pas de debit
de munition dans `bot_fire_aa`) et son kill differe Socket.IO, non execute par le
headless ; le test verifie l'absence de programmation sur refus. Pas de test
navigateur/reseau ni de validation de parite humaine complete.

Verification : `venv/bin/python -m unittest discover -v` : 85 tests,
84 reussis, 1 ignore (fixtures JavaScript, Node.js indisponible).
Compilation Python de `simulation.py`,
`bot_ai.py`, `server.py`, `geometry.py`, `rl/` et des tests racine reussie ;
`git diff --check` propre. Le Python systeme sans dependances RL ne convient pas
a la suite complete ; le venv existant a ete utilise sans installation.

## Guidage torpille : perte capteur et LOS anti-torpille

- Acoustique/autonome actives : echec capteur = perte du verrou, maintien du cap
  et de la profondeur courants (pitch zero), sans homing vers `lastAcquiredPos`
  ni `initialTarget`. Le lancement vers un souvenir reste autorise ; la phase
  pre-activation vise encore le point initial. Aucun refus LOS global reinstalle.
- L'evitement local existant tourne encore sans cible avec ses limites de virage
  et son horizon existants. Pas de nouveau pathfinding ni garantie de contourner
  une ile ; commandes humaines filoguidees inchangees.
- Audit des branches bateau/leurre/torpille : LOS exacte deja presente pour les
  bateaux/leurres, ajoutee au scan anti-torpille ET au suivi du verrou precedent.
  Reacquisition uniquement par capteurs reels, jamais par souvenir seul.
- Penetration autonome : un resultat par entite/passe partage entre priorite,
  suivi et scan, avec cles distinctes bateau/leurre/torpille. Les echecs pouvaient
  auparavant etre retentes plusieurs fois dans la meme passe. Nouvelle tentative
  a chaque passe/tick admissible conservee (20 Hz nominal) : probabilite cumulee
  encore dependante de la frequence, equilibrage ouvert, aucun timer arbitraire.
- `_emit_torpedo_state` ne consulte plus le joueur vivant par `targetId`, meme
  avant la premiere acquisition. Dernier point acquis ou lancement fige permis
  dans le payload historique, sans pilotage sur souvenir apres perte. Ce payload
  ne distingue toujours pas souvenir/verrou ; parite UI/reseau non demontree.
- `rl/test_torpedo_guidance.py` : vrais ticks torpilles Sim/headless, acquisition
  puis ile bloquante, cap/profondeur stables, evitement local, reacquisition visible,
  invariance aux mouvements caches, LOS bateau/leurre/anti-torpille et tirages
  uniques par entite/passe avec nouvelles tentatives aux passes suivantes.

Fairness globale toujours incomplete : drones automatiques, degats apres tir,
comptabilite DCA, sonar allie/recu et parite reseau restent hors tranche. Les
schemas/rewards/RNG isoles existants sont preserves ; regles de trajectoire et
probabilites effectives changent, donc scores archives historiques et reevaluation
ulterieure candidats ET references necessaire. Aucun commit, deploiement,
entrainement, promotion ou evaluation de modeles lance ici.

Verification de cette tranche : suite complete via le venv existant, variables
OMP/MKL/OPENBLAS a 1, 92 tests (91 reussis, 1 ignore : fixture JavaScript sans
Node.js). Compilation Python racine/`rl` et `git diff --check` reussis.
Les tests incluent aussi l'absence de position cible sans point connu et la
conservation du pitch/pilotage filoguide manuel sans contact.

## Contacts LIVE et transport sonar avant trace

- `SonarPinged` exige le Y reel de l'emetteur ; l'unique constructeur Sim couvre
  BT synchrone et RL temporise, le dispatcher conserve XYZ et les portees en metres.
  Aucun consommateur concret ne necessite un defaut Y fictif. Les pings humains
  utilisent deja le Y serveur. Conversion JS des range/reveal recus exactement une
  fois ; local et balises inchanges. Alerte de ping recu bloquee par les iles.
- Sim retourne le dernier XYZ observe et son horodatage lorsque la cible passe
  derriere une ile, avec `tracked=false`. RL conserve sa memoire sans la rajeunir,
  et garde les tirs au point dans leur fenetre existante. Reapparition en LOS :
  suivi courant permis avant expiration, sans prolonger les 10 s.
- JS : caches sonar/radar et selection ne suivent plus les coordonnees/profondeurs
  masquees ; retour en LOS via observateur allie admissible. Les points persistent
  jusqu'au delai existant, y compris radar gele. Tir torpille sur souvenir en XZ
  sans targetId, grenades simples/salves sur snapshot XYZ ; canon par ID non permis
  sur souvenir masque. Aucune suppression globale du droit de viser un souvenir.
- Torpille selectionnee : tooltip, tir anti-torpille et mesh partagent le filtre
  radar courant ; perte de visibilite = deselection. Portee, LOS ennemie et blocage
  thermocline, exemptions propres/fullmap existantes. La trainee vieillit toujours
  mais aucun nouveau point n'est ajoute depuis une torpille invisible.
- Aucun changement de penetration/cooldown sonar, d'attenuation passive, de
  schema/reward, checkpoint ou champion. Les scores archives restent historiques.

Verification finale : 97 tests via le venv existant (OMP/MKL/OPENBLAS=1), tous
reussis, sans ignore. Node etait absent au premier passage (95 reussis, 2 ignores),
puis disponible en v18.19.1 au passage final ; aucune installation par cet agent.
Regressions Sim/RL : XYZ/horodatage figes, delai fixe, reacquisition, deux chemins
d'evenement. Contrats source Python : vrai dispatcher isole par AST, payload
humain, conversions JS, guards selection/tir et vieillissement des trainees.
`tests/test_live_contacts.js` execute les fonctions/blocs du vrai client avec
stubs DOM/capteurs pour conversion, caches, tirs et tooltip ; execution directe
reussie ainsi que `node --check static/game.js`. Compilation Python des fichiers
modifies et `git diff --check` reussis. Aucun navigateur/reseau lance.

Limites explicites : etats ennemis encore distribues aux clients, pas de redesign
des payloads ni garantie anti-client modifie. `server.spawn_torpedo` resout encore
les intentions humaines targetId sur la position live sans preuve d'observation ;
`fire_cannon_intent` conserve ses validations historiques et ses degats par ID,
sans preuve de detection partagee. Race entre selection visible et reception serveur
toujours possible. Le tir humain `fixedTarget` reste XZ (profondeur existante), pas
un nouveau guidage XYZ. Types/etats d'acquisition des torpilles, drones automatiques,
balises/partage allie et changement de point de vue restent a auditer. Pas de
parite navigateur/latence ni fairness globale etablie ; trace toujours non lancee.
Aucun commit, deploiement, entrainement ou evaluation longue dans cette tranche.

## Gardes humaines LOS et menaces BT partagees (2026-09-09)

Cette tranche corrige les resolutions live sans LOS decrites ci-dessus, sans
pretendre etablir une preuve complete de detection humaine.

- Serveur : garde exacte `Sim.bot_target_los` avant extraction XYZ visee et avant
  toute initialisation/consommation de munitions, allocation, emission ou tache
  differee. Torpilles acoustique/autonome/filoguidee, mode anti-torpille inclus ;
  canon/DCA sur bateau, drone, balises et mine de surface. ID inconnu ou masque
  refuse sans fallback vers un point qui conserverait un faux ID/une fausse alerte.
- Regle tactique explicite : le lancement manuel/memorise au point reste permis
  sans detection obligatoire de ce point. `fixedTarget` sans ID reste XZ, avec
  profondeur historique ; aucun blocage ajoute aux snapshots torpille/grenade.
- Filtre radar/CPA RL deplace dans deux helpers purs de simulation, sans import
  RL dans Sim ni dependance circulaire. Sim et BT utilisent portee locale, LOS,
  thermoclines strictes et ETA/CPA cinematiques ; verrou/type prives ne modifient
  plus inclusion, tri ou ETA. Type BT neutralise. Le combat BT utilise maintenant
  CPA <= 200 m sur 10 s au lieu du cone 15 degres ou acquisition privee.
- Les deux conditions d'activite BT passent par `_torpedoes_in_los_5km` : radar,
  LOS et thermoclines communs, rayon additionnel 5 km, sans critere CPA ; torpilles
  propres incluses si visibles. Cache BT 0.5 s conserve comme snapshot, sans
  rafraichissement cache des coordonnees. Le nom historique `torpedo_acquired`
  ne prouve plus un verrou : ETA geometrique nulle ou evasion deja engagee.

Verification : 104 tests unittest reussis dans le venv local, OMP/MKL/OPENBLAS=1.
Node : `node --check static/game.js` et `node tests/test_live_contacts.js` reussis.
Compilation Python des fichiers touches et `git diff --check` reussis.
Les tests serveur executent par AST les vrais handlers et fonctions de tir, avec
Sim reel et I/O simulees : rejets ile fine/bord/sommet sans effets, munitions
initialisees ou absentes, tirs visibles, points masques invariants aux mouvements
ennemis. Ce ne sont pas de simples assertions textuelles, mais ils ne couvrent
ni Flask/SocketIO, ni routage/authentification reels, ni execution des impacts
differes. Regressions pures Sim/BT et RL : occlusion, thermocline, limite de portee,
CPA/vitesse, neutralite des verrous/types et ordre ETA.

Restent ouverts : legalite sonar humaine complete (passif/bruit, cone/portee,
thermoclines, revelation temporisee, observateurs allies), etats ennemis toujours
distribues aux clients, parite reseau/interpolation et race selection/reception.
La LOS locale au tireur peut refuser un ID vu uniquement par un allie ; le point
reste utilisable. Identites proprietaires de torpilles, cles BT de session basees
sur tid seul, cache de menace et attaques automatiques drones restent a auditer.
Aucune fairness globale ni parite navigateur n'est etablie. Aucun changement de
schema/reward/champion, commit, deploiement, trace, entrainement ou evaluation.
Les anciens scores ne dispensent pas de reevaluation candidate ET reference.

## Correction apres premiere analyse de trace : identite sonar live

Defaut reproduit hors serveur avec la forme reelle de `server.spawn_bot` :
`bots[sid]` et `players[sid]` sont distincts, meme ID public, `is_bot` uniquement
sur le miroir joueur. L'ancien test RuntimeController sur alias headless ne
validait donc pas la parite live. Le registre deduit du flag supprimait chaque
revelation puis la recreait pendant le front, et `active_sonar_contacts` la
rejetait pour le RL. Une transition trace `active_reveal` seule ne prouve pas
que la politique a vu la cible.

Avant correction, les tests `ServerShapedActiveSonarTest` reproduisent :
- `test_runtime_and_trace_reveal_survive_wave_until_original_deadline` :
  echeance attendue 10.625, obtenue 11.0 au tick 1.0 ; controle headless reussi.
- `test_live_runtime_uses_shared_timing` : aucune torpille au tick 0.75 malgre
  acquisition attendue a 0.625.

Correction dans Sim uniquement : conserver le registre source de la cible et
verifier l'identite canonique, y compris pour `pinged_at`. Les tests couvrent les
remplacements emetteur/cible/humain avec memes ID/SID avant/apres acquisition,
retrait, reset, suivi 10 s au-dela du front, expiration stricte, memoire LOS figee
et trace temporaire acquisition 0.625 / perte 10.625. Aucun changement de regle
sonar, reward, schema/action RL, modele ou code de navigation.

Verification : suite complete 134 tests reussis (OMP/MKL/OPENBLAS=1), dont les
28 regressions sonar alias/server-shaped ; tests Node existants et syntaxe JS,
compilation Python et `git diff --check` reussis. Aucun serveur demarre/arrete,
aucune modification de la session humaine, aucun commit ni entrainement lance.

Les evaluations humaines/live precedentes ne sont pas une validation des
politiques sous ce sonar corrige ; les scores headless historiques restent des
mesures de leur environnement, pas une preuve de transfert live. Nouvelle
validation candidate ET reference a organiser par le parent/utilisateur, pas
d'entrainement ni de relance d'evaluation automatique.

Inspection ile en lecture seule : `Sim.update_bot` retourne apres le controle
externe ; le RL ne passe pas par les redirections/compteurs de blocage de
`bot_ai._drive_to_waypoint`. `update_bot_external` annule le deplacement entrant
dans une ile et remet la vitesse a zero, mais garde les commandes : une politique
qui insiste en avant peut repeter ce blocage. Le gouvernail conserve un plancher
de rotation a 0.2 ; ce n'est donc pas un verrou physique inevitable. Le BT a un
autre risque : son pilote waypoint autorise explicitement la traversee du contour
et ne constitue pas un correctif de collision reutilisable tel quel.

Prochaine experience minimale recommandee, non appliquee : reproduire le cas
RL avec pose/commandes/carte figees, puis comparer une breve marche arriere suivie
d'un virage via les commandes normales, sans cible cachee. Si cela debloque le
cas, proposer a approbation une recuperation bornee au niveau controleur, commune
live/headless, declenchee par absence de progression sous poussee et obstacle
local ; ne pas assouplir les collisions ni ajouter de teleportation/reward.
Verifier aussi arret volontaire, marche arriere, bord du monde et eau libre.
Cette lecture de code ne reproduit pas a elle seule l'episode trace. Classement
des menaces laisse au parent pour une tranche ulterieure.

## Diagnostic local de la premiere trace : blocage et tri ETA

Suivi autorise du 2026-09-09, sans serveur, entrainement, evaluation de modele,
commit ni changement de comportement. `rl/test_live_trace_diagnostics.py`
conserve une fixture issue de `logs/game_trace.jsonl`, session
`e4f954245d2f4286885ecbc4a2b60bcc`, epoch 2, bateau `bot002` ; aucune substitution
par une nouvelle session. Le mode `--trace` verifie la fixture epinglee.

430 snapshots portent exactement X=-276.1323294357245, Z=-586.9339318198893,
entre seq 10868/tick 5210 et seq 19638/tick 7354, soit 118.4198155403 s de
`stepped_seconds` entre bornes. Le premier a rotation=3.274370467384111,
Y=-16.241103768348694, vitesse=0, gouvernail=-0.36, consigne gouvernail=-1,
poussee=0.65 et profondeur cible Y=-20.25. La fixture de locomotion retient le
dernier snapshot : rotation=2.1367188922448874 rad, Y=-20.25 (202.5 m), vitesse=0,
gouvernail=-0.08395879268646246, consigne gouvernail=0, poussee=0.65.
Ne pas confondre ces deux orientations ni supposer les commandes constantes
pendant toute la trace.

Carte actuelle `maps/world.json` : SHA-256 fichier
`535e35497e79187989651209a69e19fa1720bc73383c7043a5342c6195841ab5`.
Empreinte JSON canonique `c3dd181366ad107195a953b1299dcfc5466fbcfb9f5e5febf7364709d27857af`,
identique a l'evenement world de cette epoch. Specification sous-marin actuelle :
`76441e13564456215ed398a64ddeb6dc8b7148eabbf4b1b788af154e7f7f4488`.

Experience via `HeadlessRunner.step`/`Sim` reels : dt=0.05 s, action soumise
par `apply_action` toutes les 0.25 s, sans autre acteur. Les vecteurs ci-dessous
reconstruisent les commandes de mouvement stockees, pas les decisions completes
du modele : armes et leurres desactives, profondeur maintenue a 45% de 450 m.
Ce n'est pas un replay des ticks live variables ni de la politique recurrente.

| Commandes | Duree | Resultat |
| --- | --- | --- |
| `[2,3,3,0,0]` : gouvernail 0, poussee 0.65 | 30 s | 600/600 ticks bloques, deplacement nul, vitesse finale 0 ; rotation finale 2.1347709526105643 |
| `[0,0,3,0,0]` : gouvernail -1, poussee -0.35 | 15 s | aucun blocage, deplacement net 56.4603 m, vitesse -0.4501385 u/s |
| Puis `[2,3,3,0,0]` | 30 s | aucun blocage, deplacement net de phase 230.4367 m, vitesse +0.8359715 u/s |

Position finale de cette sequence : X=-266.81779174204473,
Z=-605.0096073108454, Y=-20.25, rotation=4.006999816884515 rad.
Le virage inverse (`[4,0,3,0,0]`) pendant 15 s reussit egalement, suivi de
30 s avant sans blocage : X=-296.3897132690685, Z=-585.2225089021306.
Les essais 2, 5 et 10 s de marche arriere avec virage, dans les deux sens,
repartent mais rebloquent avant la fin des 30 s avant. Les essais 20 s reussissent.
15 s est la plus courte duree reussie **testee**, pas un minimum optimise.
Chaque tick controle le point final ET la LOS exacte du segment parcouru,
ainsi que les bornes du monde : aucune entree/traversee d'ile dans ces essais.
Cela prouve une sortie locale possible par commandes normales, pas une garantie
de navigation, d'evitement de coque complete ou de survie en combat. Aucune
recuperation automatique, teleportation ou collision assouplie n'est introduite.

### Menaces : contre-exemple synthetique historique (corrige dans le suivi)

Fixture en eau libre sans thermocline, bot immobile (0,-3,0), rotation=0.
Deux torpilles visibles, meme profondeur, vitesse=2 u/s (20 m/s), direction +X :
l'une a X=+10 s'eloigne, l'autre a X=-10 arrive dans 5 s. Ni verrou ni type prive.
La projection brute est respectivement -0.5 et +0.5 sur le segment de 10 s.
`geometry.closest_approach_on_segment` conserve ce parametre brut mais borne
la distance au segment : CPA=100 m pour la fuyante, donc sous le seuil 200 m.
`simulation.torpedo_radar_threat` borne ensuite son ETA negatif a 0 s ; le minimum
ETA de `_torpedo_observation` la choisit devant CPA=0 m/ETA=5 s de l'arrivante.
Ce contre-exemple ne depend pas d'une egalite ni de metadonnees cachees.

Observation menace historique : `(1,-0.05,0,0,0,0,0.05)` ; observation souhaitee
pour l'arrivante : `(1,0.05,0,0.5,0,0,0.05)`. Le test etait marque
`expectedFailure` lors du diagnostic ; il passe maintenant avec la correction.
Le suivi preserve les filtres existants au contact, immobile, tangentielle et
en bout d'horizon ; seuls les rangs changent, pas les dimensions d'observation.
Ce scenario est synthetique, pas la preuve du vecteur vu dans cette partie.

Verification : suite complete 138 tests, 137 reussites et 1 echec attendu (tri
ETA), `git diff --check` propre. Reproduction :
`venv/bin/python -m rl.test_live_trace_diagnostics --trace logs/game_trace.jsonl`
(omettre `--trace` apres rotation du journal pour utiliser la fixture conservee).
Les corrections sonar et autres modifications concurrentes sont preservees.
La trace par decision RL etait absente lors de ce diagnostic historique ; elle
est implementee dans le suivi en tete du document. Les anciens snapshots stockes
ne permettent pas de conclure a ce que le modele a vu.

## Prochaines etapes

1. Definir les regles communes de detection et de tir humain/bot, puis corriger
   une seule difference a la fois avec les fixtures de parite.
2. Completer les manifestes (revision, cartes, bateaux, adversaires immuables),
   valider seed/architecture a la reprise et proteger les repertoires de run.
3. Comparaison corrigee et confirmation 94000 terminees ; revue humaine et
   mesure de latence sur CPU de production avant toute decision de promotion,
   sans relancer les huit jobs deja termines ni inventer un gate retrospectif.
4. Instrumenter les refus d'action sans changer leurs penalites.
5. Seulement ensuite tester une ablation courte : learning rate, entropie ou
   curriculum, une variable a la fois. Pas de nouveau run long a ce stade.
## Autogame et auto-degats grenade (2026-09-09)

- Immunite du tireur humain supprimee ; BT/RL restent vulnerables, allies aussi.
- `GrenadeExploded.dealt` exclut l'auto-degat bot comme humain ; coefficients de
  reward et espaces observation/action inchanges, historiques non comparables.
- `autogame.json` livre vide, charge uniquement avec `--autogame` (desactive par
  defaut), au demarrage reel avant ecoute et tick,
  equipes/positions/caps explicites, validation globale et chargement strict RL
  sans fallback BT, aucun client requis. Schema et template : `TECHNIQUE.md`.
- Sans flag : aucune lecture/validation, precharge d'IA ou creation de bots du
  scenario, meme si le fichier est absent/invalide ; aucune trace `autogame`.
Exemple autorise : `./start.sh --trace --autogame --map world`.
- Attente posthume : `endCondition.waitForTorpedoes`, booleen strict, defaut false.
Le scenario local active `{"type": "anyBoatSunk", "waitForTorpedoes": true}`,
v3/v15, XYZ/caps et preparation 30 s inchanges, timeout combat 600 s. Apres condition,
attente des seules torpilles actives de tous les proprietaires initiaux coules par
BoatSunk natif, couple public ownerPlayerId/tid ; nouveaux naufrages inclus,
survivants toujours actifs, kills posthumes et draw possibles. Pas d'attente
souffle/leurres/drones ni torpilles de survivants ou nouveaux membres. Timeout
borne l'attente ; sans limite, pas de watchdog additionnel. Trace unique
autogame_settling avec declencheur et identites/comptages publics, puis bilan
definitif seulement apres resolution/timeout. Aucun changement RL ni lancement.
- Fin optionnelle : `endCondition` (`anyBoatSunk`, `anyTeamEliminated`, ou
  `teamEliminated` avec `teamId`) et/ou `maxDurationSeconds` monotone. Suivi des
  naufrages natifs des IDs initiaux, regroupement du tick, aucune victoire par
  suppression/reset. Bilan `autogame_end`, snapshot final, fermeture trace avant
  sortie normale du processus. Sans condition/duree, comportement conserve.
  Voir `TECHNIQUE.md` et `test_autogame_end.py` ; tests eventlet sans port, pas de
  partie live ni changement de modele, observation, reward ou entrainement.
- Tests sans serveur : `test_autogame.py`, `test_integrity.py`. Controleur RL
  prepare reutilise sans reset ; les tests unitaires emploient un modele factice.
- Pas de partie live, entrainement, deploiement ou remplacement de champion ;
  collecte humaine et verification navigateur/reseau restent a faire.
