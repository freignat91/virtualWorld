# Curriculum de navigation

## Etape 1 : destroyer seul

Cette etape apprend uniquement a rejoindre une destination entre les iles. Elle
n'utilise ni adversaire, ni capteur tactique, ni arme, ni leurre et ni score de
victoire. Le modele part de zero et possede une interface dediee
`navigation_v1`, incompatible volontairement avec les politiques de duel.

La carte `world` est utilisee pour ses30 iles. A chaque episode, le generateur
choisit un depart et une destination navigables separes de800 a3000 m. La ligne
droite doit toucher une ile et une route doit exister via le graphe de navigation.
Les graines d'evaluation sont disjointes de celles d'entrainement.

L'observation contient13 valeurs : vitesse, gouvernail, destination relative
avant/droite, distance au but et huit distances exactes vers les iles ou les
limites du monde. Les seules actions sont gouvernail et puissance. Le sous-marin
reutilisera plus tard le meme banc d'abord a profondeur fixe.

## Danger cotier partage

La couronne autoritaire existante de30 m autour des iles retirait1 point
d'integrite par seconde uniquement aux humains. `Sim.update_player_integrity`
applique desormais le meme dommage aux BT et aux RL, avec les evenements,
synchronisations et naufrages natifs. L'environnement transforme chaque point
de dommage cotier en penalite, sans ajouter de collision artificielle.

## Recompenses et terminaisons

- progression selon la longueur du plus court chemin navigable, pas la distance
  droite qui encouragerait a traverser une ile ;
- bonus unique a l'arrivee ;
- penalite par point de dommage cotier ;
- penalites de blocage, timeout, immobilite et temps ;
- fin sur arrivee, immobilite20 s, timeout240 s ou naufrage.

## Promotion

La selection interne utilise100 routes fixes a chaque palier100k. Un checkpoint
n'est sauvegarde sous `best/` que si tous les gates passent :

- succes >=98 % ;
- zero episode avec dommage cotier ;
- blocage <=2 % ;
- decisions immobiles <=5 % ;
- efficacite moyenne des trajets reussis <=1,2 en eau libre et <=1,3 avec ile.

La validation finale utilise500 routes inedites avec les memes gates. Aucune
victoire n'entre dans la qualite ni dans la selection.

## Commandes preparees

Premier bilan100k, sans changer le calendrier500k de la config :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 venv/bin/python \
  -m rl.train_navigation --config rl/configs/aidest_navigation_v1.json \
  --device cuda --stop-after-steps 100000
```

Validation finale d'un checkpoint promu :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 venv/bin/python \
  -m rl.evaluate_navigation MODEL.zip \
  --config rl/configs/aidest_navigation_v1.json --episodes 500 --seed 311542
```

## Premier bilan100k

Le run neuf `aidest_navigation_v1_seed11542` a termine106496 pas en19min08,
evaluation comprise, avec exit0. La recompense rollout moyenne est passee de
-21,9 au premier palier a-2,39 au dernier. Sur100 routes tenues hors
entrainement :5 % d'arrivees,44 % d'episodes avec dommage cotier,9,248 points
de dommage moyen,37 % bloques,58 % expires et3,976 % de decisions immobiles.
Les cinq trajets reussis ont une efficacite moyenne de1,245.

Les gates immobilite et efficacite passent ; arrivee, zero dommage et blocage
echouent. Aucun `best_model` n'est selectionne. Checkpoint100k SHA256
`6a134069258cdf5b3d23dcb5bf6e01db54998b6c99507c7554d7c10a684e1ad0` ; le
final106496 distinct a pour SHA256
`a7a6001805f732c195f8f13db993bebae844a6a8e038836f03669d5ada25bf8c`.
Aucune continuation n'est lancee automatiquement.

## Revision progressive apres le bilan100k

Le premier essai commencait directement par des routes bloquees de800 a3000 m.
Ses5 % d'arrivees montrent que cette distribution combine trop tot propulsion,
orientation et contournement. Le curriculum est desormais decoupe en promotions
separees :

1. `open` :300-800 m, aucune ile sur le segment direct ;
2. `single_island` :400-1200 m, exactement une ile bloque la ligne droite ;
3. `multi_island` : plusieurs iles bloquent la ligne droite ;
4. `blocked` : distribution finale800-3000 m deja mesuree.

La config `configs/aidest_navigation_open_v1.json` prepare un modele neuf,
graine12542 et100k pas. Ses gates sur100 routes inedites sont98 % d'arrivees,
zero dommage cotier, <=2 % bloque, <=5 % immobile et efficacite<=1,2. Aucun
checkpoint du premier essai difficile n'est reutilise.

### Bilan du palier eau libre

Le run neuf `aidest_navigation_open_v1_seed12542` a termine106496 pas en8min17,
evaluation comprise, avec exit0. Sur100 routes inedites :15 % d'arrivees, zero
episode avec dommage cotier,4 % bloques,81 % expires,1,463 % de decisions
immobiles et efficacite1,159 sur les15 succes. La recompense rollout moyenne
termine a4,17.

Les gates dommage, immobilite et efficacite passent. Les gates arrivee>=98 % et
blocage<=2 % echouent ; aucun `best_model` n'est selectionne et le palier
`single_island` reste interdit. Checkpoint100k SHA256
`3039de405cd7b510d52210f0f353160b60635edb1b0eca769e0126c817b0b78a` ; final
distinct SHA256
`65ff48fa8e0f99f8b34cf72c181592f56873ae10bc50adb25a5e5af86aae5017`.
Aucune continuation automatique.

## Promotions eau libre des deux coques

La continuation destroyer `aidest_navigation_open_v1_continue_seed13542` passe
les100 routes internes avec99 % d'arrivees, puis500 routes independantes avec
100 % d'arrivees, zero dommage/blocage/timeout/immobilite et une efficacite
moyenne de1,069. Son `best_model` promu a pour SHA256
`3f78c228706959e626c4aeda544d2f555ff831a39e30cb1da9c4d0773f329087`.

Le sous-marin repart separement de zero dans
`aisub_navigation_open_v1_seed14542`. Il passe100 puis500 routes avec100 %
d'arrivees, zero dommage/blocage/timeout/immobilite et une efficacite finale de
1,040. Son `best_model` promu a pour SHA256
`55220ac2e1a77c92d54d2fffcd40227b60a9de17406f9accb03a3cf46b98ffaf`.
Les poids, optimiseurs, graines et environnements des deux coques ne sont jamais
partages.

## Bilan du palier a une ile

Les premiers processus100k des deux coques ont bien produit leurs checkpoints,
mais leur evaluation embarquee a expose un plafond de2000 rejets trop faible
pour certaines graines `single_island`. Le plafond propre a ce mode est passe a
20000 et les200 graines des evaluations suivantes sont couvertes par regression.
Les checkpoints ont ensuite ete evalues sans reentrainement.

| Phase | Coque | Arrivee | Episodes cotiers | Bloque | Timeout | Proche cote |
|---|---:|---:|---:|---:|---:|---:|
| une ile initiale | destroyer | 30 % | 19 % | 11 % | 59 % | non mesure |
| une ile initiale | sous-marin | 11 % | 27 % | 16 % | 73 % | non mesure |
| continuation | destroyer | 27 % | 51 % | 29 % | 44 % | non mesure |
| continuation | sous-marin | 35 % | 39 % | 24 % | 40 % | non mesure |
| detour borne <=1,3 | destroyer | 33 % | 44 % | 25 % | 42 % | non mesure |
| detour borne <=1,3 | sous-marin | 70 % | 36 % | 11 % | 17 % | non mesure |
| signal cotier100 m | destroyer | 39 % | 31 % | 21 % | 40 % | 17,370 % |
| signal cotier100 m | sous-marin | 83 % | 19 % | 11 % | 6 % | 20,550 % |
| continuation150/100 m | destroyer | 21 % | 28 % | 15 % | 64 % | 31,559 % |
| continuation150/100 m | sous-marin | 88 % | 21 % | 8 % | 4 % | 21,750 % |

Le palier faisable utilise600-1200 m, exactement une ile, un rapport entre le
chemin du graphe et la ligne directe <=1,3 et240 s. Le signal anticipe applique
une penalite progressive sous100 m de la cote ; sa valeur par defaut reste0 afin
de ne pas changer les anciens protocoles. La derniere phase destroyer essaie
150 m, ce qui regresse fortement et est rejete. La continuation sous-marin
ameliore les arrivees a88 %, mais ne reduit pas la fraction d'episodes cotiers.

Tous les gates a une ile echouent ; aucun `best_model` n'est selectionne et le
palier `multi_island` reste interdit pour les deux coques. Les derniers
checkpoints100k ont pour SHA256 destroyer
`e7851ee988b8292763650031e5ca36e81703b517aca71911e46549507cfbb946` et
sous-marin `b1ba326fa94f43702e3ae032f147313e62f589363a149fced213dfa315d58c61`.
Les runs ont termine106496 pas en16min42 et15min45, sans processus restant.
La suite complete passe293 tests en110,180 s apres ces changements.
Aucune autre continuation n'est automatique : le prochain essai doit isoler un
changement structurel d'evitement ou de representation.

## Pilote structurel waypoint `navigation_v2`

Le choix suivant remplace, uniquement quand la route directe est bloquee, la
destination relative de l'observation par le prochain waypoint sur le plus court
chemin du graphe. Lorsque la destination redevient visible, elle redevient la
cible locale. Les13 valeurs et les deux actions gouvernail/puissance sont
conservees pour permettre le warm-start, mais la semantique est versionnee
`navigation_v2`. Le mode historique `goal` reste `navigation_v1`.

Les premiers pilotes waypoint100k produisent les resultats suivants sur100
routes inedites :

- destroyer :100 % arrivees,3 % d'episodes cotiers,0 blocage/timeout/immobilite,
  15,962 % proche cote et efficacite1,101 ; seul le gate zero dommage echoue ;
- sous-marin :97 % arrivees,8 % cotiers,3 % bloques,0 timeout,0,593 % immobile,
  17,196 % proche cote et efficacite1,062 ; arrivee, dommage et blocage echouent.

Une continuation strictement identique de100k par coque utilise de nouvelles
graines. Le destroyer obtient97 % arrivees,6 % cotiers,0 blocage,3 % timeout,
0,188 % immobile et efficacite1,092. Le sous-marin obtient92 % arrivees,17 %
cotiers,4 % bloques,4 % timeout,0,830 % immobile et efficacite1,201. Cette phase
ne confirme donc pas une convergence sur les nouvelles routes.

Les continuations terminent106496 pas en18min57/20min06. Leurs checkpoints100k
SHA256 sont destroyer
`8ea038d715cddff96d623f561e698a8e89fb6289126d589795db47619fd99831` et
sous-marin `db0c7ec262303289070e61d2a13907d033e521cdfb5758d9862256bcce5b936d` ;
les finals sont distincts. Aucun `best_model`, aucune validation500, aucun
`multi_island` et aucune continuation automatique. Les295 tests complets passent
en113,842 s et `git diff --check` est propre.

## Pilotes waypoint avec corridor côtier sûr

Le waypoint précédent pouvait devenir inutile dès que le but retrouvait une
ligne de vue géométrique, même si le segment longeait encore la côte. Le nouveau
paramètre optionnel `guidance_clearance_m`, désactivé par défaut, conserve le
waypoint jusqu'à ce que le segment vers le but respecte la marge demandée par
rapport à chaque segment d'île et aux limites du monde. Les configs
`aidest_navigation_waypoint_safe_v2.json` et
`aisub_navigation_waypoint_safe_v2.json` utilisent50 m,100k pas et des
évaluations/checkpoints tous les25k.

La sélection fréquente conserve le meilleur score de navigation dans
`candidate/`, même lorsqu'il ne passe pas les gates. Elle ne modifie pas la
promotion : seul un rapport passant tous les gates peut créer `best/`.

| Pas | Coque | Arrivée | Côtiers | Bloqué | Timeout | Proche côte | Efficacité | Qualité |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 25k | destroyer | 90 % | 5 % | 4 % | 6 % | 14,553 % | 1,108 | 0,7383 |
| 50k | destroyer | 96 % | 4 % | 4 % | 0 % | 11,308 % | 1,068 | 0,8722 |
| 75k | destroyer | 90 % | 4 % | 4 % | 6 % | 9,622 % | 1,071 | 0,7521 |
| 100k | destroyer | 97 % | 5 % | 3 % | 0 % | 8,188 % | 1,067 | 0,8826 |
| 25k | sous-marin | 99 % | 5 % | 1 % | 0 % | 8,878 % | 1,061 | 0,9237 |
| 50k | sous-marin | 98 % | 3 % | 1 % | 1 % | 9,125 % | 1,067 | 0,9231 |
| 75k | sous-marin | 98 % | 4 % | 2 % | 0 % | 9,683 % | 1,041 | 0,9153 |
| 100k | sous-marin | 98 % | 3 % | 2 % | 0 % | 10,392 % | 1,017 | 0,9279 |

Le meilleur candidat est le checkpoint100k pour les deux coques. Leurs SHA256
sont destroyer
`4fd1040efdcbf6684ee616de84b428416507dcbd7467d759abe33407065d7b62` et
sous-marin
`2447a9a01b49a0c2852e6af4755312d0eb7e40bf7835377b2783ffd320ab26aa`.
Le sous-marin termine106496 pas en51min11 ; son final est distinct. Le destroyer
atteint son checkpoint100k, puis l'enveloppe externe expire à une heure pendant
l'évaluation embarquée. Le rapport100k est récupéré par une évaluation autonome
et le candidat est restauré depuis le checkpoint ; aucun processus ne reste.

Les validations indépendantes sur100 routes fraîches donnent :

- destroyer, seed502542 :97 % arrivées,4 % côtiers,2 % bloqués,1 % timeout,
  0,470 % immobile,7,214 % proche côte, efficacité1,089, qualité0,8906 ;
- sous-marin, seed512542 :97 % arrivées,3 % côtiers,3 % bloqués,0 timeout,
  0,638 % immobile,10,474 % proche côte, efficacité1,003, qualité0,9091.

Le destroyer échoue les gates arrivée et zéro dommage ; le sous-marin échoue
arrivée, zéro dommage et blocage. Aucun `best/`, test500, `multi_island` ou
nouvelle continuation n'est lancé. Les rapports frais sont archivés sous
`evaluation/fresh_502542/` et `evaluation/fresh_512542/`. La suite complète
passe298 tests en138,049 s et `git diff --check` est propre. Aucun serveur,
entraînement ou évaluateur ne reste actif ; aucun live, déploiement ou commit.

## Expérience terminée : marge de guidage100 m

Le prochain essai autorisé porte uniquement `guidance_clearance_m` de50 à100 m.
Tout le reste reste identique aux pilotes corridor50 : `navigation_v2`,13
observations,2 actions, routes `single_island`600-1200 m/détour<=1,3/240 s,
récompenses, gates,100k pas et sélection/checkpoints tous les25k. Les graines de
phase sont33542/34542 et celles d'évaluation422542/432542.

Les deux runs ont démarré séparément le11 septembre2026 à18:50:35+02 :

- destroyer `aidest_navigation_waypoint_clearance100_v2_seed33542`, parent
  PID411084, warm-start candidat50 SHA256 `4fd1040e...` ;
- sous-marin `aisub_navigation_waypoint_clearance100_v2_seed34542`, parent
  PID411089, warm-start candidat50 SHA256 `2447a9a0...`.

Chaque parent possédait huit workers et a chargé son propre optimiseur. Les runs
terminent106496 pas en1h26min31 et1h23min15, sans processus restant.

| Palier sélectionné | Coque | Arrivée | Côtiers | Bloqué | Timeout | Immobile | Proche côte | Efficacité | Qualité |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 75k | destroyer | 96 % | 9 % | 4 % | 0 % | 0,971 % | 7,845 % | 1,086 | 0,8204 |
| 50k | sous-marin | 97 % | 6 % | 3 % | 0 % | 0,601 % | 6,284 % | 1,049 | 0,8745 |

Les candidats SHA256 sont `2a251964...` et `b0f66ba3...`. Les métriques100k
régressent encore à93 % d'arrivées/7 % côtiers/5 % bloqués/2 % timeout pour le
destroyer et97 %/6 %/3 %/0 % pour le sous-marin. Tous les gates échouent ; la
marge100 m n'établit pas d'amélioration sur50 m et aucune validation fraîche
n'est justifiée automatiquement. Les SHA256 des configs sont
`89c3e013...`/`5794a557...`. Trois tests ciblés passent, les298 tests complets
précédents restent la dernière suite globale et `git diff --check` est propre.
Aucun `best/`, test500, `multi_island`, continuation, promotion, live,
déploiement ou commit.

## Expérience terminée : progression alignée sur le guidage

La progression historique utilisait la simple ligne de vue alors que la cible
locale conservait le waypoint jusqu'à un corridor libre de50 m. Dans la zone de
transition, le signal pouvait donc récompenser une coupe de virage et pénaliser
le détour demandé. Le calcul de distance accepte désormais le segment direct
uniquement s'il respecte la marge lorsqu'il sert la récompense. Distance
initiale, progression et efficacité partagent alors la route du guidage. Le
filtre `max_detour_ratio` continue d'utiliser la distance géométrique afin de ne
pas modifier volontairement la distribution du palier.

Les deux pilotes warm-start gardent marge50, observation13, actions2,
récompenses, gates et évaluation/checkpoint tous les25k. Ils planifient75k,
arrondis au rollout complet81920 :

- destroyer `aidest_navigation_waypoint_aligned_v2_seed35542`, parent419692,
  seed35542, évaluation442542, source safe50 SHA256 `4fd1040e...` ;
- sous-marin `aisub_navigation_waypoint_aligned_v2_seed36542`, parent419704,
  seed36542, évaluation452542, source safe50 SHA256 `2447a9a0...`.

Les processus ont démarré le11 septembre2026 à20:35:02+02 avec huit workers
chacun et leurs optimiseurs propres. Ils terminent81920 pas en1h00min48 et
53min59, sans processus restant.

| Pas | Coque | Arrivée | Côtiers | Bloqué | Timeout | Immobile | Proche côte | Efficacité | Qualité |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 25k | destroyer | 91 % | 6 % | 4 % | 5 % | 0,884 % | 9,580 % | 1,070 | 0,7521 |
| 50k | destroyer | 89 % | 5 % | 4 % | 7 % | 0,856 % | 11,353 % | 1,049 | 0,7243 |
| 75k | destroyer | 85 % | 4 % | 4 % | 11 % | 0,788 % | 9,149 % | 1,087 | 0,6505 |
| 25k | sous-marin | 98 % | 2 % | 2 % | 0 % | 0,417 % | 12,018 % | 0,991 | 0,9396 |
| 50k | sous-marin | 98 % | 3 % | 2 % | 0 % | 0,413 % | 11,638 % | 0,999 | 0,9296 |
| 75k | sous-marin | 98 % | 3 % | 2 % | 0 % | 0,429 % | 10,773 % | 0,994 | 0,9296 |

Les meilleurs candidats sont donc les deux checkpoints25k, SHA256
`b3c0be56...` et `627b147a...`. Le destroyer régresse avec l'entraînement. Le
sous-marin atteint exactement les gates arrivée et blocage mais conserve2 %
d'épisodes côtiers ; il échoue donc encore la promotion stricte. Aucun `best/`
ne peut être créé.

La validation autorisée du candidat sous-marin25k sur100 routes fraîches,
seed552542, obtient98 % d'arrivées,3 % côtiers,2 % bloqués,0 timeout,0,413 %
immobile,13,908 % proche côte et efficacité1,032. Elle confirme arrivée,
blocage, immobilité et efficacité, mais échoue encore uniquement le gate zéro
côtier. Le rapport archivé sous `evaluation/fresh_552542/report.json` a pour
SHA256 `5db07271...`.

Configs SHA256 `89ae4b8f...`/`9de7ba3c...`, code SHA256 `e2d1f0f6...`. Les299
tests passent en146,065 s et `git diff --check` est propre. Ne pas lancer
automatiquement autre évaluation, continuation, `multi_island`, promotion,
live, déploiement ou commit.

## Diagnostics lookahead et bouclier côtier

Le mode optionnel `lookahead_waypoint` versionne l'observation en
`navigation_v3`, sans changer sa taille13 ni les2 actions. Il remplace le rayon
de bascule implicite50 m par `waypoint_lookahead_m` :150 m destroyer et100 m
sous-marin. `progress_mode` rend simultanément explicite le choix entre distance
géométrique et distance de guidage. Les anciens modes restent inchangés sans ces
options.

Les modèles sont d'abord comparés sans apprentissage sur les mêmes50 routes :

| Coque | Variante | Arrivée | Côtiers | Bloqué | Timeout | Dégât moyen |
|---|---|---:|---:|---:|---:|---:|
| destroyer | contrôle v2 | 96 % | 6 % | 2 % | 2 % | 1,003 |
| destroyer | lookahead v3 | 96 % | 6 % | 2 % | 2 % | 1,003 |
| sous-marin | contrôle v2 | 96 % | 10 % | 4 % | 0 % | 1,705 |
| sous-marin | lookahead v3 | 96 % | 10 % | 4 % | 0 % | 1,705 |

Le lookahead ne change aucun résultat d'épisode et aucun entraînement50k n'est
lancé. Les rapports sont archivés sous `lookahead_diag_562542/` et
`lookahead_diag_572542/`.

Un bouclier prédictif optionnel, strictement limité à `NavigationEnv` et
désactivé par défaut, projette la commande sur5 s lorsqu'une marge50 m peut être
atteinte. Il teste les25 actions discrètes. La première variante maximisait la
garde et réduisait les deux coques à92 % d'arrivées. La variante finale choisit
plutôt la commande sûre la plus proche de la demande RL :

| Coque | Arrivée | Côtiers | Bloqué | Timeout | Interventions | Efficacité |
|---|---:|---:|---:|---:|---:|---:|
| destroyer | 96 % | 0 % | 0 % | 4 % | 3,112 % | 1,126 |
| sous-marin | 94 % | 0 % | 6 % | 0 % | 3,542 % | 1,042 |

La contrainte élimine donc les dégâts mais déplace les échecs vers timeout ou
blocage. Les critères de lancement échouent et aucune adaptation n'est lancée.
Les rapports finaux `closest_safe.json` ont pour SHA256 `ce1f9119...` et
`5c42bf79...`. Les302 tests passent en156,185 s, `git diff --check` est propre
et aucun processus ne reste. Aucun changement gameplay/runtime, `best/`,
promotion, live, déploiement ou commit.

## Diagnostic bouclier orienté waypoint

La variante suivante remplace le critère « commande sûre la plus proche » par
la meilleure progression projetée vers le waypoint, puis rejoue exactement les
mêmes50 routes et modèles. Elle garde zéro épisode côtier mais obtient :

| Coque | Arrivée | Côtiers | Bloqué | Timeout | Interventions |
|---|---:|---:|---:|---:|---:|
| destroyer | 94 % | 0 % | 4 % | 2 % | 1,256 % |
| sous-marin | 92 % | 0 % | 8 % | 0 % | 2,431 % |

Ces résultats régressent face à `closest-safe` malgré moins d'interventions.
Les rapports `goal_oriented.json` ont pour SHA256 `a7fa133d...` et
`f5d5c9db...`. Aucune adaptation50k n'est lancée et le code optionnel revient à
la variante `closest-safe`, SHA256 `2e17c9c5...`, toujours désactivée par défaut.
La suite complète précédente de302 tests et2 tests ciblés après restauration
passent ; `git diff --check` est propre et aucun processus ne reste. Aucun
`best/`, promotion, live, déploiement ou commit.
