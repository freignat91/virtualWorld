# Suivi de l'audit RL

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
CPA <= 200 m, ETA bornee a [0,10] s. Minimum ETA parmi les candidats visibles,
ordre d'insertion stable en cas d'egalite ; torpilles propres toujours exclues.
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

### Sonar actif RL : correction temporelle approuvee

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
