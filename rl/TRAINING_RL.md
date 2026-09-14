# Entraînement des bots RL

## Mobilite runtime v16 : selections finales officielles et figees

Le14 septembre2026, les candidats v16 ont ete declares selections finales de la
phase d'entrainement aux deplacements. Les aliases publics sont maintenant
`aisub_mobility_runtime_v16` et `aidest_mobility_runtime_v16`, resolus vers
`best/best_model.zip`. Leurs poids sont des copies physiques independantes des
artefacts v15 et conservent les SHA256 suivants :

- sous-marin `7a0daa4f83a3211135c5efd05d5b68038d8b789772f7af273813f961df15ea47` ;
- destroyer `a6a53fe853cd013b8508a9f4d7b71f81179dfcd5c2ad98051a194225345fc672`.

Le runtime autonome `rl/bot_versions/v16/` fixe les rayons final et intermediaire
a500 m. Au-dela de7,5 km, il place prioritairement le nombre minimal de points
surs sur l'axe direct, chacun a plus de500 m des obstacles et avec des segments
de7,5 km maximum. La route Dijkstra demeure le repli si aucun decoupage aligne
n'existe. `route_planned` trace les points exposes, le chemin Dijkstra interne,
les distances et ratios. Le manifeste v16 est immutable ; v15 reste separee et
inchangee.

La validation finale a execute simultanement20 routes CPU deterministes avec
timeout1200 s, seeds533542 destroyer et523542 sous-marin. Le sous-marin passe
toutes les gates :100% arrivee/eau libre/obstacle,0 cotier/naufrage/blocage,
0,063% stationnaire,0 recul, vitesse0,993, rectitude0,895 et0 demande d'arme,
leurre ou sonar. Qualite diagnostique2,2879740326 ; rapport SHA256
`1c6eccba0430a602d9e233b6d4c9e6bfe3f52edca6b1b77b55aa6e407509b7e5`.

Le destroyer atteint aussi100% arrivee/eau libre/obstacle,0 naufrage/blocage,
0,089% stationnaire,0,113% recul, vitesse0,994, rectitude0,867 et0 demande.
Un episode `small_obstruction` sur20 subit3,65 points de degat cotier :5% contre
la gate maximale1%. Cette unique gate echoue ; le risque est accepte explicitement
par la decision de selection finale. Qualite diagnostique2,2352884833 ; rapport
SHA256 `b996598f4ef7270a2d1ed3d2495c0764a458742b936ef99824b3e2d588fb28a9`.

Rapports complets :

- `models_rl/aisub_mobility_runtime_v16/evaluation/segmented_runtime_v16_aligned_final500_seed523542.json` ;
- `models_rl/aidest_mobility_runtime_v16/evaluation/segmented_runtime_v16_aligned_final500_seed533542.json`.

La phase d'entrainement aux deplacements est close. V16 est officielle et en
lecture seule : ne plus entrainer, modifier, remplacer ou promouvoir son code,
ses manifests et ses poids. Le suivi de validation ecrit desormais un fichier
`*.progress.json` atomique apres chaque episode avec moyenne, temps restant et
heure de fin estimee. Aucun processus de validation ou d'entrainement ne reste.

## Mobilite runtime v8 : deux pilotes actifs

Lances simultanement le12 septembre2026 vers15:58+02, les deux runs frais
planifient100k pas : destroyer PID533844, seed77542, config SHA256
`dc67bd8ca1591295dfef0392a59e46b871ab90ff23722e2b8b4aa2a291b03827` ;
sous-marin PID533854, seed78542, config SHA256
`ba1a58f8f37eb65e319da26bab924506b5059a6dc2f886054cb75a647b921542`.
Les premiers rollouts CUDA atteignent8192 pas a429/424 FPS.

La rectitude ne cumule desormais que les segments dont la vitesse reelle est
positive. Elle vaut la norme du deplacement vectoriel avant cumule divisee par
la longueur de chemin avant ; sans segment avant, elle vaut0. Les segments en
recul restent mesures par la gate de recul mais ne peuvent plus produire une
rectitude1.0. Rewards, interfaces, architecture et gates v7 restent inchanges.
Les41 tests cibles, JSON, compilation et `git diff --check` passent.

Ne pas dupliquer, tuer ou prolonger les processus sains ; aucune promotion,
continuation, live, autogame, deploiement ou commit automatique.

## Mobilite runtime v7 : deux pilotes termines, non admissibles

Lances simultanement le12 septembre2026 vers15:20+02, les deux runs frais ont
termine106496 pas : destroyer PID529228, seed75542, config SHA256
`0374f15fde706a53c697137ac6d5c3b3aa419ed307c3717a49082f3ed326e733` ;
sous-marin PID529241, seed76542, config SHA256
`e92089138846ce3545f21166bfdf2d81d5edfb11c5d99c044cd7b742252ee371`.
Ils finissent vers15:35/15:39, sans processus restant.

La distance `movement_per_meter=0.01` est maintenant recompensee uniquement si
la vitesse reelle est positive. Hors de la zone d'exemption cotiere100 m, le
recul passe de-0.03 a-0.05 par metre ; sa recompense nette passe donc de-0.02 a
-0.05 par metre. Dans la zone d'exemption, le recul ne recoit ni bonus de distance
ni penalite. Rewards, interfaces, architecture et gates v6 restent sinon
inchanges. Les40 tests cibles, JSON, compilation et `git diff --check` passent.

Le destroyer selectionne100k :100% completion eau libre/obstacle,0 cotier,
0 naufrage/blocage,0.506% stationnaire, vitesse0.346, rectitude1.0, recul99.909%
et aucune demande d'arme/leurre/sonar. Echouent vitesse et recul. Candidat SHA256
`4a536f3ba1140e9286610cf797bb58f7d9f2cf1296f47ffbfaf8fecdc07cc2e2` ; final
distinct SHA256 `75d2a08054182fc3cbd037f4fd2355c36c97620761e9f8055b41ab012dfce767`.

Le sous-marin selectionne25k :100% completion eau libre/obstacle,1% cotier,
0 naufrage/blocage,0.415% stationnaire, vitesse0.347, rectitude1.0, recul100% et
aucune demande d'arme/leurre/sonar. Echouent vitesse et recul. Candidat SHA256
`afc90b2a2a87d841bcc0cd93c14131ee98efd02903545641f45faca805a20686` ; final
distinct SHA256 `aa1aff3c6fc7e0475c46448f2cf522fb9430dee1fa2bef98b09e7404c66339c2`.

Aucun `best/`, promotion, continuation, live, autogame, deploiement ou commit.

## Mobilite runtime v6 : deux bases terminees, non admissibles

Lances simultanement le12 septembre2026 vers14:00+02, les deux runs frais ont
termine106496 pas avec exit0. Le destroyer PID522979, seed73542, dure environ
16min34 ; le sous-marin PID522989, seed74542, dure environ9min47 car ses
evaluations bloquees se terminent apres10 s. Config SHA256
`82fb582d839141a85007be21f438249c6ce3f3c9b3bf8c62086c9cfe18fd7cf3` et
`2e0be923ddc61ccdd3c4ee5261e6504f66b2f2f620321befc29c12189e9a56aa`.

Les anciennes gates de completion globale/eau libre/obstacle et de taux de
blocage sont remplacees par deux comptes independants sur100 episodes :
`max_sunk_count=0` et `max_stuck_count=2`. La completion reste une metrique de
diagnostic et de qualite, pas une gate. La rectitude minimale passe de0.7 a0.5.
Le surcout de gouvernail sans menace revient a-0.05 pour les deux coques.

Toute demande de leurre sans torpille visible, y compris pendant le cooldown,
declenche maintenant `lure_without_threat=-0.2`, en plus de `lure_request=-0.01`.

Le destroyer selectionne100k :100% completion eau libre/obstacle,1% cotier,
0 naufrage/blocage,0.415% stationnaire, rectitude0.963, mais vitesse0.346 et recul
100%. Arme/leurre/sonar restent0. Echouent vitesse et recul. Candidat SHA256
`226c57cc3f75608299d9079baeec92237e8d16e41573c9844017ca8f7d4aca31` ; final
distinct SHA256 `28e45ae8f4723305ba7e37c6ef9c4e0d14211c8f1f8a35a619f484158cc5d6f6`.

Le sous-marin selectionne25k, identique aux quatre evaluations :0 completion,
0 naufrage mais100 blocages,100% stationnaire, vitesse/rectitude0 et aucune
demande d'arme/leurre/sonar. Echouent vitesse, rectitude, blocage et stationnaire.
Candidat SHA256 `6508d2cb15dfa8dfdd7be6d6dfb5f13bc7f032dda451cda62a998311dd42b4b0` ;
final distinct SHA256 `d2d71718dfc261769caa5117fd240990a1a72c8ed8e0cc62dc5a5dbdb3bc9822`.

Les39 tests cibles, JSON, compilation et `git diff --check` passent. Aucun
processus, `best/`, promotion, continuation, live, autogame, deploiement ou commit.

## Mobilite runtime v5 : deux pilotes termines, non admissibles

Les deux plans frais ont termine simultanement106496 pas avec exit0 en18min22
pour le destroyer et18min28 pour le sous-marin. Ils conservent interfaces,
architecture, duree100k, curriculum et gates v4. Le destroyer seul utilise
`rudder_without_threat=-0.1` au-dela de100 m sans torpille visible ; le sous-marin
conserve-0.05. Les deux ajoutent le bonus de vitesse avant par morceaux aux seuils
silencieux natifs0.4/0.8.

Le destroyer selectionne75k :71% completion,100% eau libre,42% obstacle,37%
episodes cotiers,29% bloques,5.642% stationnaire,0 recul, vitesse0.596 et
rectitude1.0. Arme/sonar restent0 ; leurre27.233%. Echouent completion, obstacle,
vitesse, cotier, bloque, stationnaire et leurre. Candidat SHA256
`dae7ff45557e5c29cdafb9a273a586eaf1916a6e1441050be11064dee0931e0a` ; final
distinct SHA256 `4ccb5a44ff80e812cdd3a76d906d1025e9287dd49c85386471975fd97000c412`.

Le sous-marin selectionne50k :99% completion,100% eau libre,98% obstacle,1%
episodes cotiers et bloques,0.562% stationnaire,0 recul, vitesse0.971, rectitude
0.087 et aucune demande d'arme/leurre/sonar. Seule la rectitude echoue. Candidat
SHA256 `c7e439a18a38329c98c5964488ed4462af689140ef7b89e441be53eec695915f` ; final
distinct SHA256 `6dc5150893433285d6d7aa2355e7e38ba7b4836bca0c0f7879710f6d76d2cb2c`.

Les16 tests cibles et319 tests complets passes avant lancement restent valides ;
les archives et `git diff --check` sont propres. Aucun processus, `best/`,
promotion, continuation, live, deploiement ou commit.

## Mobilite runtime v4 : deux pilotes termines, non admissibles

Les deux plans frais ont ete executes sequentiellement le12 septembre 2026, sans
checkpoint source et avec8 environnements CUDA. Le destroyer herite, PID508240,
a demarre a12:02:51+02 et s'est termine naturellement vers12:23:45, soit environ
20min54. Apres verification de cette fin et de l'absence du dossier de sortie, le
sous-marin PID511325 a ete lance a12:24:40 et a fini vers12:47:04 avec exit0, soit
environ22min24. Chacun atteint106496 pas whole-rollout et produit quatre
evaluations, quatre checkpoints et un `policy_final.zip` valide :

- destroyer `aidest_mobility_runtime_v4_seed69542`, config SHA256
  `d7e6c67703085aa127ec2b78ed7367b1febc1145f875a69d2ee52df662c8b190` ;
- sous-marin `aisub_mobility_runtime_v4_seed70542`, config SHA256
  `450e47957dcf5a4f4a09caabcbd635f2cb720497dbdb81fe0b89f7bd2fb71e48`.

Le changement par rapport a v3 releve la gate maximale d'episodes avec degat
cotier de0 a0.01, borne incluse, et porte le surcout de gouvernail sans torpille
visible de-0.01 a-0.05 fois le ratio absolu au-dela de100 m. Avec le cout normal
de-0.01, le cout total maximal devient-0.06 ; a100 m ou moins, les deux restent
suspendus. Interfaces, architecture, duree et autres rewards/gates restent v3.

Les evaluations destroyer25k/50k/75k/100k ont les qualites1.1639533074,
-0.9275417370,1.1816445937 et1.1816445937. Le premier maximum strict selectionne
75k :100% completion/eau libre/obstacle,0 episode cotier,0 bloque,0.415%
stationnaire,0 marche arriere, vitesse0.968, rectitude0.084,0 demande de torpille
ou sonar, mais100% de demandes de leurre. Echouent les gates de rectitude et de
leurre. Candidat SHA256
`ef28666f76cbaf5b6b1a84aa210c45dc5966fafab752f14314ecffa5abb879e3` ; final
106496 distinct SHA256
`b52a7a43fe7f7a70f19504ef2b9d049b8fc0c354177ad38720334bec0e13a7eb`.

Les evaluations sous-marin25k/50k/75k/100k ont les qualites1.1067306608,
1.1067306608,1.1768240692 et1.1360799382. Le checkpoint75k est selectionne :100%
completion/eau libre/obstacle,0 episode cotier,0 bloque,0.415% stationnaire,
0 marche arriere, vitesse0.639, rectitude0.494 et aucune demande de torpille,
leurre ou sonar. Echouent uniquement les gates de vitesse et rectitude. Candidat
SHA256 `6430d2f7f99fb8812466372f22e54510fcc5f9ff52583ccaf00adfec5acb9be3` ;
final106496 distinct SHA256
`bc160e74921f5e25de69654e31325cee68f48e9504fdfc5ae47f29d46094f13e`.

Aucune evaluation ne passe tous les gates, donc aucun `best/`. Les319 tests Python
passes avant lancement n'ont pas ete relances ; les deux archives finales passent
`unzip -t`, leurs metadonnees indiquent106496 pas et `git diff --check` est propre.
Aucun processus, continuation, promotion, autogame, live, deploiement ou commit.

## Mobilite runtime v3 : deux pilotes termines, non admissibles

Lances simultanement le 12 septembre 2026 a11:21+02, les deux runs frais, sans
checkpoint source et avec8 environnements CUDA distincts chacun, ont termine
106496 pas avec exit0 en19min44/19min27 :

- destroyer `aidest_mobility_runtime_v3_seed67542`, PID503758,
  `destroyer_duel_v4`, config SHA256 `033146f6287760d499042abdb7b8c76a38a68ebc08f49b0098ac5ec7a171aed3` ;
- sous-marin `aisub_mobility_runtime_v3_seed68542`, PID503768, `sub_duel_v2`,
  config SHA256 `f573b357d3c9d0bf182493f7992d6216abbbd997649dc5bf92760089039911ad`.

Ils ajoutent aux regles v2 la penalite `lure_without_threat=-0.1` et, uniquement
au-dela de100 m des cotes, `rudder_without_threat=-0.01` fois le ratio absolu.
A100 m ou moins, les deux couts de gouvernail restent suspendus.

Le destroyer selectionne le checkpoint100k :98% completion,100% eau libre,96%
obstacle,2% episodes cotiers,2% bloques,0.747% stationnaire, vitesse0.961 et
rectitude0.173. Les demandes de torpille restent a0, mais les leurres reviennent
a100% apres avoir ete nuls a25k. Echouent obstacle, rectitude, zero-cotier et
leurre. Candidat SHA256 `7866069df085099e3a2a739858d18f63c2ae2c0f76401cfea894a37a152eb259` ;
final distinct SHA256 `206624cbaa90a33744cfd8d930b5edea3f034df6fc22304b5d5f14f9ea5a78c4`.

Le sous-marin selectionne le checkpoint25k :100% completion eau libre/obstacle,
0 degat cotier,0 bloque,0.415% stationnaire, vitesse0.639, rectitude0.092 et
aucune demande de torpille, leurre ou sonar. Seules vitesse et rectitude echouent.
Le checkpoint100k atteint99% completion,1% cotier/bloque, vitesse0.638 et
rectitude0.328, mais sa qualite est inferieure. Candidat25k SHA256
`9bc636c180009bfcab81b40e39724a73763c85447f643b562fe5d0b9decbe0c0` ; final
106496 distinct SHA256 `b00fd1b1b276c7d0f9560bf093e15071274e8f01ff82a8392f2d2ea10390c7a9`.

Les61 tests cibles anterieurs et14 tests finaux de mobilite passent ; les JSON et
`git diff --check` sont valides. Aucun processus, `best/`, continuation, promotion,
autogame, live, deploiement ou commit.

## Mobilite runtime v2 : deux pilotes termines, non admissibles

Lances simultanement le 12 septembre 2026 a10:30+02, les deux pilotes frais,
sans checkpoint source et avec8 environnements CUDA distincts chacun, ont termine
106496 pas avec exit0 en19min34 pour le destroyer et17min10 pour le sous-marin :

- destroyer `aidest_mobility_runtime_v2_seed65542`, PID498593,
  `destroyer_duel_v4`, config SHA256 `01cbdb8d937fb44009c724f15c4f8ae239945036bb918c41fd5338380556f23f` ;
- sous-marin `aisub_mobility_runtime_v2_seed66542`, PID498603, `sub_duel_v2`,
  config SHA256 `739087dc3094bea45b7c9a0b4d0b434db1a3ed8d941b70f2270d0c7a13587bbb`.

Chaque tentative de torpille sans cible est refusee et cumule maintenant le cout
de demande `-0.02` et la penalite sans acquisition `-0.1` dans `MobilityEnv`.
Les sorties v1 restent intactes. L'evaluation finale100 routes du destroyer donne
100% completion en eau libre et obstacle,0 degat cotier,0 bloque,0.415%
stationnaire,0 marche arriere, vitesse0.637 et rectitude0.084. Les demandes de
torpille tombent de100% a0, mais les demandes de leurre restent a100%. Echouent
les gates vitesse, rectitude et leurre. Candidat100k SHA256
`78943ec7f02543796fed0fe197420048a4be97c9b796049a0e19b077b51138ef` ; final
106496 distinct SHA256 `e2609d1be6bdb1f943bd5c68f36246a601b7fa211ec30a8e22b78804412284bc`.

Le sous-marin donne99% completion,100% eau libre,98% obstacle,2% episodes avec
degat cotier,1% bloque,0.714% stationnaire,0 marche arriere, vitesse0.967 et
rectitude0.100. Les demandes de torpille tombent aussi a0, mais les leurres restent
a100%. Echouent les gates rectitude, zero degat cotier et leurre. Candidat100k
SHA256 `d3c8c4ec079d6d709d75091b5a3af92ac278f73131384cd6933f3e8703bd8677` ; final
106496 distinct SHA256 `9358480089687d9582a29f9cb09edc1c5ef031767268ca4f21d6d8a070c0a5d9`.

Les315 tests complets anterieurs et38 tests cibles apres branchement de la
recompense passent ; les JSON et `git diff --check` sont valides. Aucun processus,
`best/`, continuation, promotion, autogame, live, deploiement ou commit.

Apres la fin de ces runs, une nouvelle penalite non entrainee a ete ajoutee : un
leurre effectivement largue sans torpille visible coute `-0.1` supplementaire.
Dans `MobilityEnv`, le gouvernail sans menace coute aussi `-0.01` supplementaire
fois son ratio uniquement au-dela de100 m des cotes ; les deux couts de gouvernail
restent nuls a100 m ou moins. Le signal vient du radar deja utilise par
l'observation, sans nouveau capteur. Les61 tests cibles passent. Les poids v2
restent historiques et non promotables ; mesurer ces changements exige un nouveau
run frais et une nouvelle sortie.

## Mobilite runtime neuve : pilotes100k termines, non admissibles

Deux politiques recurrentes neuves ont ete entrainees simultanement, sans
adversaire et dans des processus/environnements distincts. Elles conservent des
le depart les actions completes et les interfaces finales `destroyer_duel_v4`
(173 observations) et `sub_duel_v2` (169 observations). Les propres projectiles
de l'agent ne remplissent jamais ses slots de menace ; aucune action n'est
masquee ou remplacee.

Les deux runs terminent106496 pas avec exit0, en24m30 pour le destroyer et24m15
pour le sous-marin :

- `aidest_mobility_runtime_v1_seed63542` : evaluation finale100 routes,98 % de
  completion,100 % eau libre,96 % obstacle,2 % de degats cotiers,2 % bloques,
  vitesse moyenne normalisee0,632 et rectitude0,105 ; demandes d'arme100 % et de
  leurre100 %. Final SHA256 `d2160e3e9567580ddc5806aaa18738317836730b539a4269084520db631053f6`.
- `aisub_mobility_runtime_v1_seed64542` :98 % de completion,100 % eau libre,
  96 % obstacle,2 % de degats cotiers,2 % bloques, vitesse0,965 et rectitude0,171 ;
  demandes d'arme100 %. Final SHA256
  `92fd95c2a60e4008d96cc0589521030dff5d6e2a8e6941ea02266ec12fedd8d0`.

Les evaluations25/50/75/100k ne montrent aucune amelioration deterministe de la
trajectoire. Les meilleurs candidats internes restent ceux de25k, mais tous les
gates echouent ; aucun `best/`, promotion, autogame, continuation, deploiement ou
commit. Les deux finals se chargent par `rl_runtime` et les latences CPU smoke
sont inferieures a1 ms. Apres les runs, le slot de contact des seules nouvelles
interfaces accepte aussi un contact visuel si et seulement si les deux bateaux
sont en surface selon le seuil natif de flottaison et que la LOS geometrique est
libre ; toute coque immergee reste exclusivement detectee au sonar.
Les313 tests passent en155,485 s apres cette correction ; `git diff --check` est
propre et aucun processus d'entrainement ne reste.

Depuis le 12 septembre, toute torpille exige une cible selectionnee pour les
humains, BT et RL. Les pilotes ci-dessus ont ete produits avant cette restauration
et ne doivent pas etre continues ou compares comme si leur regle de tir etait
identique. Une tentative RL sans cible est refusee et recoit la penalite dediee
`weapon_without_acquisition=-0.1` par defaut, en plus de `weapon_invalid` ; aucun
modele n'a ete modifie ou reentraine par cette correction.

L'objectif terminal de combat existe deja dans `SubmarineDuelEnv` : couler
l'adversaire tout en restant en vie verse `win=+10` par defaut aux interfaces
`sub_duel_v2` et `destroyer_duel_v4`. `MobilityEnv` ne verse pas cette recompense,
car ses episodes actuels ne creent aucun adversaire ; elle s'appliquera lors du
passage de ces interfaces au curriculum de duel.

## Navigation : bouclier orienté waypoint rejeté

Sur les mêmes50 routes, classer les actions sûres par progression projetée vers
le waypoint conserve zéro dégât côtier mais régresse face à la variante sûre la
plus proche : destroyer94 % d'arrivées,4 % bloqués,2 % timeout et1,256 %
d'interventions ; sous-marin92 % d'arrivées,8 % bloqués,0 timeout et2,431 %
d'interventions. Les rapports SHA256 sont `a7fa133d...`/`f5d5c9db...`.

Le critère préalable échoue pour les deux coques : aucune adaptation50k ni
promotion. Le bouclier optionnel, désactivé par défaut, est restauré à la
meilleure variante `closest-safe`, code SHA256 `2e17c9c5...`. La suite complète
antérieure de302 tests et2 tests ciblés après restauration passent ;
`git diff --check` est propre et aucun processus ne reste.

## Navigation : lookahead et bouclier diagnostiqués, sans entraînement

`navigation_v3` conserve13 observations et2 actions mais permet de montrer le
segment suivant avant le rayon d'arrivée :150 m pour le destroyer,100 m pour le
sous-marin. Le mode de progression devient également explicite. Ces options ne
modifient pas `navigation_v1/v2` lorsqu'elles ne sont pas configurées.

Une comparaison appariée de50 routes applique les mêmes modèles et graines au
contrôle et au lookahead. Les résultats d'épisode sont identiques : destroyer
96 % d'arrivées,6 % côtiers,2 % bloqués et2 % timeout ; sous-marin96 %,10 %,4 %
et0 %. Le lookahead ne satisfait donc pas le critère préalable et aucun
entraînement50k n'est lancé. Rapports sous `evaluation/lookahead_diag_562542/`
et `evaluation/lookahead_diag_572542/`.

Le second diagnostic ajoute un bouclier limité à l'environnement de navigation,
désactivé par défaut. Il projette la cinématique native sur5 s lorsqu'une coque
peut atteindre la marge50 m, teste les25 actions, puis choisit la commande sûre
la plus proche de la demande RL. Sur les mêmes routes, il supprime tous les
dégâts côtiers mais obtient :

- destroyer :96 % arrivées,0 côtier,0 bloqué,4 % timeout,3,112 % interventions ;
- sous-marin :94 % arrivées,0 côtier,6 % bloqués,0 timeout,3,542 % interventions.

Le bouclier maximal antérieur était plus mauvais encore à92 % d'arrivées pour
les deux coques. La variante proche ne passe toujours pas les gates arrivée et,
pour le sous-marin, blocage ; aucune adaptation n'est lancée. Rapports
`closest_safe.json` SHA256 `ce1f9119...`/`5c42bf79...` sous `shield_diag_*`.
Les302 tests passent en156,185 s, `git diff --check` est propre et aucun processus
ne reste. Aucun gameplay/runtime, best, promotion, live, déploiement ou commit.

## Navigation V2 : progression alignée terminée

Le défaut isolé était une incohérence : le waypoint restait soumis au corridor
de50 m, mais la progression repassait à la distance directe dès la simple ligne
de vue. `_shortest_distance_u(..., guidance=True)` utilise maintenant le même
test de marge et la même recherche de route que le guidage. La distance initiale,
la progression par pas et l'efficacité emploient ce chemin ; le filtre de
difficulté et l'échantillonnage des routes conservent leur distance géométrique
historique. Observation13, actions2, marge50, coefficients, gates et cadence25k
ne changent pas.

Les pilotes `aidest_navigation_waypoint_aligned_v2_seed35542` et
`aisub_navigation_waypoint_aligned_v2_seed36542` ont démarré le11 septembre2026
à20:35:02+02, parents419692/419704 et huit workers chacun. Ils chargent les
candidats safe50 SHA256 `4fd1040e...`/`2447a9a0...` avec leurs optimiseurs.
Chaque plan s'arrête après75k, soit81920 pas entiers attendus, avec graines
35542/36542 et évaluations442542/452542.

Les runs terminent81920 pas en1h00min48 et53min59, sans processus restant. Les
deux meilleurs candidats sont les checkpoints25k. Le destroyer obtient91 %
d'arrivées,6 % côtiers,4 % bloqués,5 % timeout,0,884 % immobile, efficacité1,070
et qualité0,7521. Le sous-marin obtient98 % d'arrivées,2 % côtiers,2 % bloqués,
0 timeout,0,417 % immobile, efficacité0,991 et qualité0,9396. Les candidats
SHA256 sont `b3c0be56...`/`627b147a...`; les finals81920 sont distincts.

Le destroyer régresse et échoue trois gates. Le sous-marin passe arrivée,
blocage, immobilité et efficacité, mais échoue encore le gate zéro épisode
côtier. Une validation autorisée sur100 nouvelles routes, seed552542, confirme
98 % d'arrivées,3 % côtiers,2 % bloqués,0 timeout,0,413 % immobile,13,908 %
proche côte et efficacité1,032. Elle échoue donc encore uniquement le gate
zéro côtier ; rapport SHA256 `5db07271...`. Aucun `best/` n'est produit. Configs
SHA256 `89ae4b8f...`/`9de7ba3c...`, code `rl/navigation_env.py` SHA256 `e2d1f0f6...`.
Les299 tests passent en146,065 s et `git diff --check` est propre. Logs dans
`/tmp/virtualWorld_aidest_navigation_waypoint_aligned_v2_seed35542.log`
et `/tmp/virtualWorld_aisub_navigation_waypoint_aligned_v2_seed36542.log`. Ne pas
lancer automatiquement continuation, autre évaluation, promotion, live,
déploiement ou commit.

## Navigation V2 : corridor100 terminé et rejeté

L'expérience autorisée suivante isole une seule variable :
`guidance_clearance_m` passe de50 à100 m. Les observations13, actions2,
récompenses, routes à une île, hyperparamètres, gates et évaluations/checkpoints
tous les25k restent identiques. Les configs sont
`aidest_navigation_waypoint_clearance100_v2.json` et
`aisub_navigation_waypoint_clearance100_v2.json`, SHA256 `89c3e013...` et
`5794a557...`.

Les deux nouvelles phases100k ont démarré le11 septembre2026 à18:50:35+02 avec
les parents411084/411089 et huit workers chacune. Elles ont chargé séparément les
candidats50 m destroyer `4fd1040e...` et sous-marin `2447a9a0...`, optimiseurs
inclus, puis remettent le compteur de phase à zéro avec les graines33542/34542
et les graines d'évaluation422542/432542. La provenance effective est écrite
dans chaque nouveau répertoire de run.

Les runs terminent106496 pas en1h26min31 et1h23min15, sans processus restant.
Le meilleur candidat destroyer est le palier75k :96 % d'arrivées,9 % côtiers,
4 % bloqués,0 timeout,0,971 % immobile, efficacité1,086 et qualité0,8204. Le
meilleur sous-marin est le palier50k :97 % d'arrivées,6 % côtiers,3 % bloqués,
0 timeout,0,601 % immobile, efficacité1,049 et qualité0,8745. Leurs SHA256 sont
`2a251964...` et `b0f66ba3...`; les finals106496 sont distincts.

Tous les gates échouent et cette marge n'établit aucune amélioration sur50 m.
Les logs sont
`/tmp/virtualWorld_aidest_navigation_waypoint_clearance100_v2_seed33542.log` et
`/tmp/virtualWorld_aisub_navigation_waypoint_clearance100_v2_seed34542.log`.
Trois tests ciblés passent, après les298 tests complets précédents, et
`git diff --check` est propre. Aucun test frais100/500, `best/`, `multi_island`,
continuation, promotion, exécution live, déploiement ou commit automatique.

## Navigation V2 : corridor côtier terminé et rejeté

Le guidage garde désormais le waypoint du graphe tant que le segment direct
vers le but ne respecte pas une marge générique de50 m par rapport aux polygones
des îles et aux limites du monde. `guidance_clearance_m` vaut0 par défaut ; les
deux nouvelles configs utilisent50 m. Les observations restent de taille13 et
les actions gouvernail/puissance. La sélection évalue tous les25k et conserve le
meilleur score dans `candidate/`, tandis que `best/` exige toujours tous les
gates.

Les candidats internes100k obtiennent97 % d'arrivées/5 % côtiers/3 % bloqués
pour le destroyer et98 %/3 %/2 % pour le sous-marin. Sur100 routes fraîches,
seed502542/512542, le destroyer obtient97 % d'arrivées,4 % côtiers,2 % bloqués,
1 % timeout et1,089 d'efficacité ; le sous-marin97 %,3 %,3 %,0 % et1,003. Les
deux validations échouent donc et aucun `best/` ni test500 n'est créé.

Les candidats SHA256 sont `4fd1040e...` et `2447a9a0...`. Le sous-marin termine
106496 pas en51min11. Le checkpoint destroyer100k est complet, mais l'enveloppe
externe atteint son timeout pendant l'évaluation finale ; celle-ci est récupérée
indépendamment sans processus restant. Les298 tests passent en138,049 s et
`git diff --check` est propre. Aucun `multi_island`, continuation, live,
déploiement ou commit ; détails dans `NAVIGATION_CURRICULUM.md`.

## Navigation V2 waypoint : pilote et continuation terminés

Le changement structurel choisi expose comme cible relative le prochain waypoint
sûr du graphe tant que la destination est masquée par une île. L'observation
reste de taille13 et les actions restent gouvernail/puissance, mais la nouvelle
sémantique est `navigation_v2`; `navigation_v1` reste disponible par défaut.

Le premier100k améliore fortement les résultats : destroyer100 % d'arrivées,
3 % d'épisodes côtiers et aucun autre échec ; sous-marin97 % d'arrivées,8 %
côtiers et3 % bloqués. Les gates stricts échouent toutefois et aucun best n'est
créé. Une continuation identique sur de nouvelles graines obtient destroyer
97 %/6 % côtiers et sous-marin92 %/17 % côtiers ; elle ne confirme pas la
convergence.

Les runs `aidest_navigation_waypoint_v2_continue_seed27542` et
`aisub_navigation_waypoint_v2_continue_seed28542` terminent106496 pas en
18min57/20min06, sans processus. Checkpoints100k SHA256 `8ea038d7...` et
`db0c7ec2...`, finals distincts, aucun best. Aucun500 final, `multi_island`,
continuation, live, déploiement ou commit. Les295 tests passent en113,842 s ;
voir `NAVIGATION_CURRICULUM.md`.

## Navigation V1 : eau libre promue, une île bloquée

Les navigateurs eau libre sont promus séparément après validation indépendante
sur500 routes : destroyer et sous-marin atteignent100 % d'arrivées, zéro dégât,
blocage, timeout ou immobilité, avec une efficacité de1,069 et1,040. Les best
SHA256 sont respectivement `3f78c228...` et `55220ac2...`.

Le palier à exactement une île reste bloqué après plusieurs phases100k parallèles
et séparées. Le meilleur résultat observé du destroyer est39 % d'arrivées avec
31 % d'épisodes côtiers ; celui du sous-marin est88 % avec21 % côtiers. Borner
le détour à1,3 et porter le timeout à240 s améliore surtout le sous-marin. Une
pénalité anticipée sous100 m réduit certains échecs, mais une marge destroyer de
150 m régresse à21 % d'arrivées/64 % de timeouts.

Le générateur `single_island` dispose maintenant de20000 essais et les200 graines
des derniers protocoles sont couvertes. `max_detour_ratio` borne la difficulté ;
`coastal_proximity` est désactivée par défaut et `near_coast_fraction` mesure le
signal sans devenir un gate. Les derniers runs
`aidest_navigation_single_island_safe_v1_continue_seed23542` et
`aisub_navigation_single_island_safe_v1_continue_seed24542` ont terminé106496
pas en16min42/15min45, sans best ni processus. Aucun passage à `multi_island`,
continuation automatique, live, déploiement ou commit. Les293 tests complets
passent en110,180 s. Voir
`NAVIGATION_CURRICULUM.md` pour le tableau complet et les hashes.

## Navigation V1 : premier bilan100k termine

Le premier curriculum repart de zero avec un destroyer seul sur `world`, sans
adversaire ni arme. `navigation_v1` expose destination relative et8 rayons ; la
politique ne commande que gouvernail/puissance. Les routes directes sont bloquees
par une ile et validees accessibles. La selection exige98 % d'arrivees, zero
dommage cotier, <=2 % blocages, <=5 % immobilite et efficacite<=1,5 sur100 routes,
puis500 routes finales. Les bots recoivent maintenant le meme dommage cotier
natif que les humains. Config `configs/aidest_navigation_v1.json`, protocole dans
NAVIGATION_CURRICULUM.md.

Le premier run neuf `aidest_navigation_v1_seed11542` a termine106496 pas en
19min08, exit0. Sur100 routes tenues hors entrainement :5 % arrivees,44 % avec
dommage cotier,37 % blocages,58 % timeouts,3,976 % immobilite et efficacite
1,245 sur les cinq succes. Les gates arrivee/dommage/blocage echouent ; aucun
best n'est selectionne et aucune continuation n'est automatique.

Le curriculum revise ne continue pas ce checkpoint. Il repart de zero sur le
palier `open` de300-800 m sans ile sur le segment direct, puis exigera une
promotion avant `single_island`, `multi_island` et la distribution `blocked`.
Config : `configs/aidest_navigation_open_v1.json`, graine12542,100k pas.

Ce palier eau libre a termine106496 pas/8min17, exit0. Evaluation100 routes :
15 % arrivees,0 dommage cotier,4 % bloques,81 % timeouts,1,463 % immobilite et
efficacite1,159 sur les succes. Arrivee et blocage echouent ; aucun best, aucune
transition vers `single_island` ni continuation automatique.

## Pilotes v16/v16b acquisition termines, v8 non lance

Le pilote warm-start v15 `aisub_v16_acquisition_seed9542_pilot100k` a termine
106496 pas/11min00 avec exit0. Sa penalite isolee de tir sans acquisition reduit
ce taux de28,081 a25,028 % sur les memes180 situations, mais reste loin du gate
5 % ; le desalignement empire89,067->93,321 % et les demandes invalides
93,143->94,684 %. Score pondere v15/v16 33,542/33,958 %, sans inference paire.
Les gates echouent, aucun best n'est selectionne et le pilote v8 mobilite reste
prepare mais non lance. A la demande du user, v16b a conserve exactement le meme
protocole et renforce seulement la penalite de-0.1 a-0.5. Il reduit les tirs non
acquis a15,759 %, mais baisse le score a32,083 % ; desalignement90,381 % et
demandes invalides93,839 % echouent encore. Aucun best v16b.278 tests complets
et les smokes config passent. Voir BEHAVIOR_PILOTS.md ; aucune continuation/
promotion/live/deploiement/commit automatique.

## V7 defense : entrainement et comparaison finale termines

Phase5 terminee106496 pas/15min14, aucun processus. Interne det34,167 %, sampled
76,944 %. Comparaison independante phase4/phase5 :320 duels graines200000-19.
Settled det42,5/32,5 %, sampled75,833/76,667 %. Phase5-phase4 det -10
[-15,507 ;-4,493]pp ; sampled +0,833 [-4,318 ;5,985]pp, IC95 normaux/20 clusters.
Phase5 degrade donc significativement le runtime deterministe sans gain sampled
etabli.

Phase5 reduit les invalides sampled, armes44,333->39,917/duel et leurres164,708->
78,125, mais cela ne compense pas le recul deterministe.8 jobs exit0,124 hashes
inchanges/job,320 traces validees, zero mine/cap. Archive :
`models_rl/aidest_v7_defense_continue4_seed8542_final100k/evaluation/independent_200000/`.

Recommandation sans promotion : conserver phase4 checkpoint100k SHA9a513b31...
comme candidat v7, car le runtime standard est deterministe. Il reste0V/6D/34N
settled sur le dernier lot et n'est donc pas pret a remplacer la production.
L'entrainement planifie est acheve ; aucune continuation/live/promotion/deploiement/
commit. Voir V7_DEFENSE_PILOT.md.

## V7 defense : cinquieme palier final actif

Run `aidest_v7_defense_continue4_seed8542_final100k` actif depuis2026-09-10
22:00:12+02, PID304338, workers304358-304365/CUDA. Warm-start du checkpoint
phase4-100k SHA `9a513b31...`, poids+optimiseur, graine8542. Derniers100k demandes,
106496 reels attendus. Entropie0.000975->0.0003 sur cette phase ; curriculum0.

Verifie24576 pas/548FPS et optimiseur fini, metriques finies.298 entrees/196 ZIP
inchangees apres lancement avant docs ;15 tests cibles, comparaison precedente
320 duels validee. Log :
`/tmp/virtualWorld_aidest_v7_defense_continue4_seed8542_final100k.log`.
Ne pas dupliquer/tuer ; aucune suite/promotion automatique apres fin.

## V7 defense : phase4 comparee independamment

Phase4 terminee106496 pas/14min29, aucun processus. Selection interne det41,667 %
(2V/12D/46N), sampled79,722 % (124V/17D/39N),7907 invalid weapons, zero mine.

Comparaison independante phase3/phase4 :320 duels graines190000-19. Scores
settled det36,25/45 %, sampled74,167/70,417 %. Phase4-phase3 det +8,75
[3,388 ;14,112]pp ; sampled -3,75 [-8,843 ;1,343]pp, IC95 normaux/20 clusters.
Le gain deterministe est soutenu ; la baisse sampled n'est pas etablie. Zero
mine/cap.8 jobs exit0,121 hashes inchanges/job,320 traces validees. Archive :
`models_rl/aidest_v7_defense_continue3_seed7542_review100k/evaluation/independent_190000/`.

Phase4 est le meilleur checkpoint deterministe v7 teste, encore principalement
defensif. Un dernier palier100k achevant le calendrier d'entropie est defensable,
mais aucune continuation/promotion n'est automatique. Voir V7_DEFENSE_PILOT.md.

## V7 defense : quatrieme palier100k actif

Run `aidest_v7_defense_continue3_seed7542_review100k` actif depuis2026-09-10
21:25:41+02, PID300707, workers300727-300734/CUDA. Warm-start du checkpoint
phase3-100k SHA `3a0438b...`, poids+optimiseur, nouvelle graine7542. Phase
restante200k mais arret revue100k/106496 reels attendus. Entropie poursuivie
0.00165->0.0003 sur200k ; curriculum termine0.

Verifie24576 pas/558FPS et optimiseur fini avec metriques finies.293 entrees/
192 ZIP inchangees apres lancement avant docs ;15 tests cibles, comparaison
independante precedente320 duels validee. Log :
`/tmp/virtualWorld_aidest_v7_defense_continue3_seed7542_review100k.log`.
Ne pas dupliquer/tuer ou auto-continuer apres bilan.

## V7 defense : comparaison independante phase2/phase3 terminee

320 duels sur graines180000-19, autosub/sub15 : par checkpoint40 deterministes
et120 echantillonnes (trois graines d'action), situations appariees. Scores
first/settled phase2-det27,5/27,5 %, phase3-det35/35 %, phase2-sampled75,833/
72,5 %, phase3-sampled77,917/78,333 %. Phase3-phase2 settled : deterministe
+7,5 [0,302 ;14,698] points ; sampled +5,833 [0,016 ;11,650], IC95 normaux sur
20 groupes de graines. La borne sampled est presque nulle, donc pas de conclusion
globale ni promotion.

Tentatives d'arme invalides sampled avant endpoint :93,817->33,05/duel (-64,8 %),
tirs29,525->28,883. Zero mine et aucun plafond de settling. Huit jobs exit0,
118 empreintes inchangees/job,320 traces validees. Archive :
`models_rl/aidest_v7_defense_continue2_seed6542_review100k/evaluation/independent_180000/`.

Phase3 elle-meme est terminee106496 pas/16min41 ; selection interne det34,167 %,
sampled73,056 %. Aucun processus ne reste. Un autre palier100k est defensable,
mais requiert une decision explicite ; aucun live/promotion/deploiement/commit.

## V7 defense : troisieme palier100k actif

Run `aidest_v7_defense_continue2_seed6542_review100k` actif depuis2026-09-10
20:49:11+02, PID296452, huit workers296472-296479/CUDA. Warm-start du checkpoint
selectionne du deuxieme palier, SHA `f3148eab...`, poids+optimiseur a100k.
Graine6542, phase restante300k et arret de revue100k/106496 reels attendus.
Calendrier preserve manuellement : entropie0.002325 vers0.0003 sur300k,
curriculum termine (`curriculum_fraction=0`). Verifie16384 pas/575FPS et premier
optimiseur fini avec metriques finies.288 entrees/188 ZIP inchangees apres
lancement avant docs ;15 tests cibles. Log :
`/tmp/virtualWorld_aidest_v7_defense_continue2_seed6542_review100k.log`.

Le deuxieme palier est termine a106496 pas/15min20 : deterministe33,333 %
(0V/20D/40N), sampled81,389 % (130V/17D/33N),16721 invalides contre29373 au
premier palier, zero mine. Aucun processus phase2 ne reste. Voir
`V7_DEFENSE_PILOT.md`. Ne pas dupliquer/tuer ou auto-continuer apres phase3.

## V7 defense : deuxieme palier100k actif

Le run `aidest_v7_defense_continue_seed5542_review100k` est actif depuis
2026-09-10 20:28:54+02, PID294428, workers294449-294456, CUDA. Nouvelle phase
warm-start depuis le checkpoint canonique100k du premier pilote, SHA256
`41c5fa5d0f260130ad6edcf66559706f2303ee38829b98505e83e5abcf5ac2e5`.
Graine5542, phase planifiee400k, stop apres100k demandes/106496 nouveaux pas
attendus. La CLI remet les calendriers curriculum/entropie au debut de cette
phase ; ce n'est pas une continuation exacte du compteur precedent.

Verification a24576 pas :559 FPS cumules et premier optimiseur fini avec
metriques finies.283 entrees/184 ZIP inchanges apres demarrage avant docs ;15
tests cibles passent,275 tests complets restent la derniere suite large. Log
`/tmp/virtualWorld_aidest_v7_defense_continue_seed5542_review100k.log`. Ne pas
dupliquer, tuer ou poursuivre automatiquement apres le bilan. Voir
`V7_DEFENSE_PILOT.md`.

## V7 defense : palier100k termine

Le run `aidest_v7_defense_seed4542_review100k` est termine a106496 pas reels,
sans processus restant. Temps affiche16min14s. Evaluation interne a100k :
deterministe35 % sur60 matchs (1V/19D/40N), echantillonnee75 % sur180 matchs
(108V/18D/54N), dont autosub80 % et aisub_v15 fige70 %. Zero mine dans les240
matchs. Le mode echantillonne totalise5391 tirs mais29373 tentatives d'arme
invalides ; le deterministe ne tire que11 fois et ne depose aucun leurre. La
politique reste immature et n'est pas promotable sur cette seule selection.

Les trois archives a100k checkpoint/best/best-sampled contiennent les memes
poids. `policy_final.zip`, apres l'optimisation finale a106496, est distinct et
non evalue.273/277 entrees restent inchangees apres fin, les quatre exceptions
etant les docs de statut modifies apres lancement ; les180 ZIP preexistants sont
inchanges. Voir `V7_DEFENSE_PILOT.md` et `completion_verified.json` dans le
manifeste de lancement. Aucune continuation ou evaluation independante lancee ;
decision explicite requise.

## V7 defense : premier palier100k actif

Lancement explicitement autorise le10 septembre2026 a19:59:34+02:00 : run
`aidest_v7_defense_seed4542_review100k`, PID291249, huit workers291267-291274,
CUDA. Modele neuf, aucune source et aucun warm-start ; graine4542, interface
`destroyer_duel_v3` 101 observations/actions5 sans mine.

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
venv/bin/python -u -m rl.train_ai \
  --config rl/configs/aidest_v7_defense.json --stage scripted \
  --run-name aidest_v7_defense_seed4542_review100k \
  --device cuda --stop-after-steps 100000
```

Commande deja lancee, ne pas la dupliquer. Le budget configure reste500k pour
les calendriers, mais cette invocation s'arrete apres100k demandes, soit106496
pas attendus par rollouts complets. Curriculum20 % termine a ce palier ; entropie
lineaire seulement avancee de20 % vers0.0003. Double evaluation a100k :60 matchs
deterministes et180 echantillonnes. Aucun prolongement automatique apres bilan.

Verification a16384 pas : premier optimiseur fini,492 FPS cumules, KL0.00552852,
loss0.109, value_loss1.43 et explained_variance-0.0258 finies. Provenance
`new_model`, source nulle, architecture256x256/LSTM256 et device CUDA confirmes.
275 tests complets puis7 cibles v3 passent avant lancement. Archive sous
`models_rl/launch_manifests/aidest_v7_defense_seed4542_review100k/` ;277 entrees,
dont180 ZIP preexistants, verifiees inchangees apres demarrage avant ces mises a
jour documentaires. Log :
`/tmp/virtualWorld_aidest_v7_defense_seed4542_review100k.log`.
Pas de serveur live, promotion, deploiement, commit ou sous-agent.

## V7 defense preparee, aucun entrainement lance

Decision utilisateur apres le bilan v6 : corriger d'abord le manque
d'information d'evitement. La nouvelle interface `destroyer_duel_v3` expose six
torpilles et six leurres actifs et retire entierement les mines de l'espace
d'action RL. Les anciennes interfaces et tous leurs checkpoints restent
reconnus, mais v3 est incompatible avec leurs espaces et exige un modele neuf.

Configuration preparee : `configs/aidest_v7_defense.json`, graine4542, pilote
500k, architecture et hyperparametres frais du pilote v6, double selection tous
les100k et checkpoint a chaque echeance. Aucun processus n'est lance. La valeur
`mine_placed=-1.0` reste une defense en profondeur sans effet attendu : l'action
de mine n'existe plus et les stocks/cooldown de mines ne sont pas observes.

Les101 valeurs sont :14 etats/munitions/cooldowns historiques,7 valeurs du
contact,6x7 valeurs de torpilles,6x5 valeurs de leurres, puis8 rayons. Chaque
torpille fournit presence, position avant/droite relative, vitesse relative
avant/droite, CPA et ETA sur10s. Les menaces a CPA<=200m sont prioritaires,
puis les autres trajectoires visibles et les torpilles recedantes proches.
Type, verrou et cible restent caches ; les torpilles propres sont exclues.
Chaque leurre fournit presence, position relative, duree restante et indicateur
propre/etranger. Un leurre propre reste connu ; un leurre etranger exige portee
radar, LOS et absence de thermocline, et un leurre expire est exclu.

Ne pas utiliser `--resume` avec un destroyer v1/v2 : le chargeur doit refuser
les espaces36/40 contre101 et les actions6 contre5. Aucun changement de modele
de production, runtime deterministe, serveur ou regles des mines humaines/BT.
Verification :275 tests de la suite complete passent, puis7 tests v3 cibles
passent apres l'ajout final de la regression de warm-start incompatible.

## Bilan continuation v6 500k : termine, ne pas prolonger automatiquement

Le run `aidest_v6_continue_seed3542_review500k` a termine normalement a507904
nouveaux pas le10 septembre2026 a14:52:31+02:00, en1h21m43. Aucun processus
d'entrainement ne reste actif. Artefacts valides : `policy_final.zip`, checkpoints
250k/500k, meilleur deterministe a500k (49,167 % interne) et meilleur
echantillonne a100k (78,611 % interne). Le final507904 est distinct et non evalue.

La comparaison independante400 duels/graines170000-170019 donne, apres settling :
pilote500k echantillonne81,25 %, continuation echantillonnee70,833 %, v4 66,25 %,
v5 80 %, continuation deterministe48,75 % et source deterministe8,75 %.
La continuation echantillonnee perd10,417 points contre le pilote, IC95 %
groupe sur20 graines [-16,560 ;-4,274], et cumule3084,078 HP d'auto-degats de
mines contre851,900. Ne pas relancer la tranche restante des2M, promouvoir ou
modifier le runtime. Voir `V6_PILOT_COMPARISON.md` et l'archive
`models_rl/aidest_v6_continue_seed3542_review500k/evaluation/independent_170000/`.
La prochaine experience exige une nouvelle decision et une dimension isolee.

## Continuation v6 autorisee, tranche de bilan en cours

Lancee le10 septembre2026 a13:30:32+02:00 sur friatech, PID262667,
workers262687-262694. Run `aidest_v6_continue_seed3542_review500k` depuis
le checkpoint500k du pilote, SHA
`53a0104bfb284b01007de90400ae99d12fa54f66e4c0a9fc0f444c2cec1ac6fc`.
Nouvelle graine3542 et phase de reprise, pas continuation exacte des RNG/rollouts.

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
venv/bin/python -u -m rl.train_ai --config rl/configs/aidest_v6_continue.json \
  --stage scripted --run-name aidest_v6_continue_seed3542_review500k \
  --resume rl/models_rl/aidest_v6_scripted_seed2542_pilot500k/checkpoints/policy_500000_steps.zip \
  --device cuda --stop-after-steps 500000
```

Commande deja lancee, ne pas la dupliquer. Log :
`/tmp/virtualWorld_aidest_v6_continue_seed3542_review500k.log`.

Budget planifie2M nouveaux pas, execution limitee a500k pour bilan, soit507904
avec les rollouts complets. `--stop-after-steps` ne modifie pas l'horizon des
calendriers configure ; la provenance et `effective_config.json` enregistrent
separement budget planifie et pas demandes. Aucune reprise automatique apres
l'arret. Un futur appel `--resume` serait encore une nouvelle phase, pas un
redemarrage exact de la collecte interrompue.

Calendriers explicites : LR constant5e-5 ; entropie constante0.0003 (valeur finale
du pilote) ; curriculum termine, distance complete600-2000m des le depart.
Architecture, observations, actions, rewards et distribution autosub/sub15
restent identiques. Mines conservees, aucune ablation appliquee a l'apprentissage.
Evaluation tous100k :60 matchs deterministes et180 echantillonnes, trois graines
d'actions, selections separees. Compteurs et noms de checkpoints locaux a la
nouvelle phase, premiere evaluation100k supplementaires, checkpoints250k/500k.

Verification a24576 nouveaux pas : CUDA,421 FPS cumules, n_updates504 (inclut
les updates du checkpoint), KL0.010056967, loss-0.00583, value_loss0.745 finies.
13 tests cibles reprise/double selection passent ; pas de suite generale rerun.
Archive exacte sources/docs/configs/diff/revision et manifeste sous
`rl/models_rl/launch_manifests/aidest_v6_continue_seed3542_review500k/`.
270 hashes inchanges apres demarrage dont175 fichiers ZIP preexistants, avant
ces mises a jour de statut documentaire. Aucun gameplay/runtime live change,
aucune promotion/deploiement/commit. Travail direct sans sous-agent.

## Selection a deux modes (description du protocole)

Le protocole optionnel `evaluation.sampled_action_seed_offsets` active une
seconde selection independante. Exemple dans
`rl/configs/aidest_v6_dual_eval.json` :

```json
"sampled_action_seed_offsets": [0, 1000000, 2000000]
```

Les fichiers historiques v5/v6 et leurs artefacts restent inchanges. Cette
nouvelle configuration conserve le budget pilote de500k et ses autres
hyperparametres ; elle ne constitue pas encore un choix de budget ou de
checkpoint de reprise pour une continuation longue.

- A chaque echeance, evaluation deterministe, puis evaluation echantillonnee
  sur les memes graines de scenario, avec les trois decalages Torch ci-dessus.
- Adversaire gele toujours deterministe ; les autres dimensions du jeu restent
  identiques. Les RNG globaux sont restaures apres chaque evaluation.
- Moyenne des repetitions, avec les poids configures des adversaires conserves.
  Pas de moyenne entre les scores deterministe et echantillonne.
- Maximum strict conserve independamment dans chaque mode (egalite = conserver
  le checkpoint existant). Les evaluations restent premier deces/300s ici,
  pas le settling diagnostique des torpilles.

Sous `rl/models_rl/<nouveau_run>/` :

| Artefact | Mode |
|---|---|
| `best/best_model.zip`, `best/selection.json` | Deterministe, convention historique |
| `evaluation/match_scores.jsonl` | Historique deterministe |
| `sampled/best/best_model.zip`, `sampled/best/selection.json` | Echantillonne |
| `sampled/evaluation/match_scores.jsonl` | Historique echantillonne |

Chaque selection indique `inference_mode`, les decalages des graines, le SHA du
modele et une signature de protocole. Changer les graines invalide la reprise
de l'ancien score. Avec le protocole double, les details incluent aussi chaque
episode, sa graine de scenario/d'action, ses resultats et options d'environnement.
Les details et poids de chaque repetition permettent une analyse appariee,
en regroupant les repetitions par scenario plutot qu'en les comptant comme
des situations independantes. Les pools doivent rester immuables : la signature
historique repose encore sur leurs chemins, les empreintes detaillees sont
enregistrees pour verification mais ne verrouillent pas les fichiers.

TensorBoard separe `eval/match_score` et `eval_sampled/match_score`.
Les lignes `eval_sampled/opponent_<index>_match_score` enumerent successivement
les adversaires de chaque repetition, dans l'ordre des decalages configures.

Cout actuel :30 episodes x2 adversaires x(1 deterministe +3 repetitions) =
240 matchs par echeance de100k, contre60 auparavant. La frequence n'est pas
modifiee automatiquement. Sans la cle optionnelle, le comportement reste
deterministe seul. L'API `evaluate()` expose le mode optionnel ; sa CLI et le
runtime en jeu restent deterministes. Un ZIP selectionne en echantillonnage
ne suffit donc pas a changer son mode d'execution en production.

Validation : modeles temporaires, save/reload, conservation independante des
meilleurs checkpoints, poids inegaux des adversaires, repetabilite et absence
de modification des poids/RNG ;267 tests passent. Aucun nouveau run long,
modification de reward, de modele historique ou de serveur, ni promotion.

Dernier etat v6 : pilote termine a 507904 pas. La comparaison instrumentee
100k/500k en inference deterministe et echantillonnee est terminee ; voir
`V6_PILOT_COMPARISON.md`. L'echec tardif deterministe est fortement associe
aux auto-destructions par mines, absentes ou rares en echantillonnage. Aucun
prolongement long automatique n'a ete lance.

Ce document décrit le pipeline de reinforcement learning de Virtual World, de
la simulation headless au chargement d'une politique dans le serveur live.

## Principes

### Pilote V6 Actif (2026-09-10)

Nouvelle autorisation utilisateur limitee au pilote frais v6 : aucune reprise
v5 ni continuation automatique3-5M. `configs/aidest_v6.json` reprend exactement
v5 sauf nom, description, seed2542 et total_steps500000 ; architecture,
observations, regles, rewards, melange autosub/sub15 et evaluation100k avec
30 episodes/adversaire restent inchanges. Les258 tests passent, dont deux
regressions de conformite v6 et de creation sans chargement de checkpoint.

Attention : les fractions restent identiques, pas leurs durees. Curriculum
12500 decisions/worker (100k agregees), contre50000 en v5 ; entropie0.003 vers
0.0003 sur500k au lieu de2M. Ce pilote n'isole donc pas causalement l'effet
de l'initialisation et ne prouve ni convergence ni superiorite. Les rollouts
8192 peuvent porter la fin normale a507904 decisions. Graines internes
102542-102571, distinctes des series independantes110000/120000/130000.

**ACTIF**, lancement `2026-09-10T09:08:39+02:00`, controle effectif
`2026-09-10T09:09:31+02:00`, PID **244030**. L'acces admin configure
exterieurement a resolu le blocage historique ; aucune politique modifiee par
l'agent. Aucun job training/evaluation/serveur avant lancement, sortie et log
absents ; suite actuelle **258 tests OK** en5,387s, OMP/MKL/OPENBLAS1,
`git diff --check` passe. Commande reellement executee depuis la racine :

```bash
nohup env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 venv/bin/python -u -m rl.train_ai --config rl/configs/aidest_v6.json --stage scripted --run-name aidest_v6_scripted_seed2542_pilot500k --device cuda > /tmp/virtualWorld_aidest_v6_scripted_seed2542_pilot500k.log 2>&1 &
```

Preuves du demarrage :

- `effective_config.json` : `resume=null`, seed2542,total_steps500000,n_envs8,
  curriculum12500 decisions/worker ; `provenance.json` : `phase=new_model`,
  checkpoint_source/sha256 null,checkpoint_timesteps0,seed2542,device cuda,
  MLP256x256/LSTM256x1. Configuration source inchangee et conformite v5 verifiee.
- Premier rollout8192 puis **16384 steps**, **470 FPS cumules** apres optimiseur,
  n_updates8,loss0,0489,value_loss2,4,KL0,005169966,clip_fraction0,0141,
  entropy_loss-7,6,explained_variance0,0123,policy_gradient_loss-0,00164.
  Toutes les valeurs journalisees controlees sont finies, aucun traceback.
- Huit workers forkserver **244048-244055**, parent forkserver244047 ; chacun
  un thread. OMP/MKL/OPENBLAS1 verifies dans l'environnement du PID244030.
  Parent9 threads natifs ; `nvidia-smi` confirme PID244030 en calcul,434MiB GPU.
- `check_training_device.py` execute : vrai produit matriciel CUDA valide,
  RTX5080,torch2.11.0/CUDA13.0,SB3/contrib2.8.0,Python3.12.3.
- Prochaine evaluation interne100000,30 episodes/adversaire ; checkpoint250000.
  Pilote non termine et non evalue au releve ; ne pas dupliquer/arreter le job sain.

Archive neuve, distincte de la sortie :
`models_rl/launch_manifests/aidest_v6_scripted_seed2542_pilot500k/`.
`source.tar.gz` contient **99 fichiers** : Python racine/RL suivis et non suivis,
configurations/cartes/coques/BT, exigences et documents. Git diff binaire HEAD,
statut exhaustif/revision, SHA individuels et preuves startup/tests conserves en
fichiers non inscriptibles. Les six references historiques v3/v4/v5/sub15
(dont selection v4 et final v5) concordent ; **99 entrees et58 fichiers modeles**
du baseline complet correspondent encore apres lancement, avant ces mises a jour
documentaires. Comparaison du contenu tar avec les sources reussie.

- Archive SHA256 : `650f22d13523dea2b67a8fa160de648a466c4c9d7f8b2d28f162b87d5579711c`.
- Config v6 SHA256 : `d99811da797fe5cc3036e942e518a52f39ebc7fbae64ec32a2aadc3d576960e2`.
- Log actif : `/tmp/virtualWorld_aidest_v6_scripted_seed2542_pilot500k.log`.
- Releve conserve : `startup_checks.json`, `startup.log`, `startup_processes.txt`,
  `startup_cuda.txt`, `effective_config.json`, `provenance.json`, `tests.log`.

Pas de continuation automatique3-5M avant rapport/evaluation du pilote, serveur,
promotion, deploiement, commit, ancien modele ecrase ou surveillance promise.

### Run V5 Termine Et Evalue (2026-09-10)

Le run `aidest_v5_scripted_seed1542` est **termine**, pas a relancer.
Derniere ecriture du log a `2026-09-10T03:11:25+02:00`, puis du ZIP final
a la meme seconde : barre100%,245 rollouts,**2 007 040 nouvelles etapes**,
7320 s affichees,274 FPS cumules avec evaluations. Aucun processus training
restant au controle du matin. Le code de sortie historique du processus detache
n'a pas ete capture : la completion est etablie par le log complet et les
metadonnees ZIP, pas par un exit0 invente.

| Artefact | Etapes de phase | Updates cumulees | SHA-256 |
|---|---:|---:|---|
| `best/best_model.zip` | 2000000 | 5752 | `1af86f9b3f1be7235be4a8994ebbfd8e538d0935c078358dfd1ea8374fe8e9de` |
| `policy_final.zip` | 2007040 | 5760 | `8b4e9f5a5bf7ea2e79a3ae8ebc9b59326a82d7d70687751b5164c67bc69eb052` |

`selection.json` confirme le BEST a2M, score interne**0,7916666666666667**,
contre autosub78,333% et sub15 80%,30 episodes chacun, graines101542-101571.
BEST ecrit a03:11:10+02:00 pendant le dernier rollout, avant son optimisation ;
`policy_final` contient aussi cette derniere mise a jour, pas seulement7040
etapes de compteur en plus. L'evaluation independante utilise **BEST seulement**.
La provenance confirme le warm-start v4best300k intact, seed1542 effective,
MLP256x256/LSTM256x1 ; v5 reste exactement v4 sauf identite/description/seed.

#### Tendances Observees

Moyennes des valeurs console existantes, sans nouvelle experience ; fenetres
ouvertes a gauche, fermees a droite. 60/61/61/62 lignes de pertes exploitables
(premier rollout sans pertes),20 evaluations internes sur les memes30 graines.

| Fenetre | Score interne moyen | Entropy loss | KL | Clip fraction | Explained variance | Value loss |
|---|---:|---:|---:|---:|---:|---:|
| 0-500k | 67,833% | -2,4267 | 0,01403 | 0,1381 | 0,8594 | 0,4305 |
| 500k-1M | 64,500% | -2,4039 | 0,01574 | 0,1485 | 0,9143 | 0,3747 |
| 1M-1,5M | 70,667% | -2,2162 | 0,01719 | 0,1596 | 0,9069 | 0,4227 |
| 1,5M-2007040 | 75,000% | -1,9921 | 0,01697 | 0,1509 | 0,9071 | 0,5811 |

Entropie en baisse, progression interne non monotone (55,833% a1M puis79,167%
a2M). Reward moyenne glissante console4,462 ->5,508 entre premiere/derniere
fenetre ; pas une mesure independante. Pertes tardives plus dispersees :
`loss` moyenne0,473,mediane0,00724,max10,1 ; `value_loss` max1,86.
Les valeurs numeriques des245 rollouts parses sont finies, aucun traceback ;
deux avertissements de deprecation SB3 au demarrage. Cela ne prouve ni la
finitude de tous les tenseurs non journalises ni l'absence de surapprentissage.

#### Comparaison Independante Terminee

Six jobs CPU mono-thread,1200 matchs frais,series110000/120000,100 par adversaire
et serie, autosub/sub15 gele, testCombats/reward v5 exacte. **v3 69,500%,
v4best300k 80,500%,v5best 80,375%**. V5-v4 **-0,125[-3,624;3,374]** points ;
v5-v3 **+10,875[7,036;14,714]**, IC95% apparies groupes par graine.
Le gate incremental +3 points face a v4 n'est pas atteint. Aucun gain demontre
sur v4, aucune promotion ni relance automatique ; ne pas substituer le gain
contre v3 au gain contre la reference la plus forte. Details et prochaine
proposition diagnostique dans `FAIRNESS_EVALUATION.md`.

Archive neuve `models_rl/aidest_v5_scripted_seed1542/evaluation/independent_110000_120000/` :
log copie, selection/provenance/config et sources archivees, SHA pre/post123
entrees, metadonnees ZIP, tendances JSON,6 rapports, analyses vs v3 ET v4,
metriques et256 tests passes. Les98 entrees du lancement training ont aussi
ete recontrolees : seules quatre notes de statut avaient change ; les sources
executables et les quatre empreintes du manifeste modeles sont inchangees.
Les cinq documents de suivi sont actualises apres verification des evaluations.
Aucune regle/reward/config/politique modifiee, aucun serveur/commit/deploiement.

### Historique Du Lancement V5 (2026-09-10)

Le releve ci-dessous decrit uniquement01:10:30, remplace par la completion et
la comparaison independante ci-dessus ; il ne decrit plus un job actif.

Autorisation explicite du lancement long executee, remplacant les anciennes
mentions de preparation/non-lancement des agents. Demarrage local
`2026-09-10T01:09:11+02:00` (`2026-09-09T23:09:11Z`), PID **210501** ; etat
actif verifie a `2026-09-10T01:10:30+02:00`. Commande exacte, depuis la racine :

```bash
nohup env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 venv/bin/python -u -m rl.train_ai --config rl/configs/aidest_v5.json --stage scripted --run-name aidest_v5_scripted_seed1542 --resume rl/models_rl/aidest_v4_scripted/best/best_model.zip --device cuda > /tmp/virtualWorld_aidest_v5_scripted_seed1542.log 2>&1 &
```

- Aucun job training/evaluation/serveur concurrent avant lancement ; sortie absente.
- Configuration inchangee : 2M nouvelles decisions, huit workers forkserver
  `210519-210526` (parent forkserver `210518`), seed effective1542.
- `models_rl/aidest_v5_scripted_seed1542/provenance.json` confirme source300000
  steps, CUDA, MLP `[256,256]`, LSTM256/1 couche ; nouvelle phase, pas reprise exacte.
- Source v4 SHA256 : `90c08a62b551f77f23a90194bb7876841df7cf7a9c50987141c3257aa16ca8e2`.
- Adversaire sub15 SHA256 : `2849f0c79a15fced51a249720bd25bd4210ee1bafc4c71f79aa942dfaab421c5`.
- Baseline v3 SHA256 : `103481713271ed04cf03007f1468898e6b4c928214c12f28ecd90fabfc5066c2`.
- Premier rollout **8192** complet : iterations1,8s,992FPS avant optimisation ;
  ce chiffre n'est pas le debit d'entrainement complet.
- Apres optimisation : iterations3,**24576** steps,46s,**523FPS** cumules ;
  loss=-0.0287,value_loss=0.251,KL=0.013700104,explained_variance=0.794.
  `n_updates`3808 puis3816 inclut le compteur historique du checkpoint.
- RTX5080/16Go, torch2.11.0/CUDA13.0, SB3/contrib2.8.0 ; GPU22%,1083MiB
  totaux/16303MiB,42C au relevement. Parent RSS~2GiB, huit workers~0.66GiB
  chacun (RSS non deduplique),49GiB RAM disponible,swap inutilisee.
- OMP/MKL/OPENBLAS1 verifies dans `/proc/210501/environ` ; chaque worker1 thread,
  parent9 threads natifs incluant les auxiliaires CUDA.
- Quatre tests warm-start passes avant lancement ; check_env initial passe,
  metriques affichees finies, aucune erreur observee. Pas de capture exhaustive
  des observations du run ni de garantie de finitude future.
- Premiere evaluation a100000 nouvelles decisions,30 episodes/adversaire ;
  checkpoint periodique a250000. Rien n'est promu/deploye, aucun ancien ZIP ecrase.

Capture avant lancement : `models_rl/launch_manifests/aidest_v5_scripted_seed1542/`.
`source.tar.gz` contient98 fichiers, dont tous les Python racine/RL presents
(suivis et non suivis), configurations, cartes, coques, BT et documentation.
Pas de credentials, noms de joueurs, logs live ou certificats dans cette selection.
Git diff binaire HEAD, statut incluant les non-suivis, revision, versions materiel,
SHA individuels des98 entrees et des modeles sont conserves hors sortie du run.
Archive SHA256 : `329cb3084a3a1a254e2f824e23681f6c7573b43d310c3f880fe68b4fcb5ca217`.
`rl/train_ai.py` SHA256 : `26d74b6c5df3446e52451d3001b43bf1a27ed63ffaf497ac9fa960e09328fb46`.
Comparaison tar/source et98 SHA passes ; v3/v4/sub15 et selection v4 inchanges
apres lancement. Fichiers de capture rendus non inscriptibles ; les notes de
statut presentes ont ete ajoutees ensuite, sans changer les entrees executables.
`startup.log` conserve les premiers rollouts, le log `/tmp` continue d'evoluer.

Au releve initial, entrainement non termine et premiere evaluation attendue.
Pas d'ETA extrapolee avant les evaluations ; pas de promesse de surveillance
automatique ulterieure. Le job est desormais termine, ne pas le relancer.

Le client n'est jamais utilisé pendant l'entraînement. `headless.py` instancie
directement `simulation.Sim`, la même simulation autoritaire que `server.py`.
Les règles de navigation, détection, munitions, projectiles, dégâts et naufrage
sont donc communes au jeu et au RL.

Chaque duel contient deux bateaux :

- l'agent à entraîner, toujours contrôlé par une politique externe ;
- un adversaire contrôlé par un Behavior Tree ou une politique RL gelée.

La physique avance à 20 Hz avec un pas de 0,05 seconde. Une action RL est
appliquée toutes les cinq étapes physiques, soit à 4 Hz. Le serveur live utilise
la même fréquence de décision.

Le modèle est un `RecurrentPPO` avec une politique `MlpLstmPolicy`. Le LSTM
permet à l'agent d'exploiter les contacts sonar mémorisés et l'évolution des
menaces sans accéder à l'état caché réel de l'adversaire.

## Modules

| Module | Responsabilité |
|---|---|
| `simulation.py` | Règles autoritaires et horloge de simulation |
| `headless.py` | Monde sans Flask, Socket.IO ni rendu |
| `rl_control.py` | Version des observations et application des actions |
| `rl_env.py` | Environnement Gymnasium, récompenses et adversaires |
| `train_ai.py` | Vectorisation, PPO, callbacks, checkpoints et ligue |
| `evaluate_ai.py` | Évaluation déterministe et télémétrie |
| `rl_runtime.py` | Validation et exécution des modèles dans le jeu |
| `rl/configs/*.json` | Hyperparamètres et composition des duels |
| `rl/configs/archive/` | Anciennes configurations incompatibles avec le chargeur actuel |

## Interfaces de contrôle

Une interface est identifiée par sa version, sa dimension d'observation et son
espace d'action. Un checkpoint n'est chargeable que si ces espaces correspondent
à la coque demandée.

| Coque | Version | Observation | Action |
|---|---|---:|---|
| Sous-marin | `sub_duel_v1` | 32 | `MultiDiscrete([5, 5, 5, 3, 2])` |
| Destroyer historique | `destroyer_duel_v1` | 36 | `MultiDiscrete([5, 5, 5, 2, 2])` |
| Destroyer avec mines | `destroyer_duel_v2` | 40 | `MultiDiscrete([5, 5, 5, 2, 2, 4])` |
| Destroyer défense multi-objets | `destroyer_duel_v3` | 101 | `MultiDiscrete([5, 5, 5, 2, 2])` |

Les versions historiques restent reconnues par `rl_runtime.py` et
`evaluate_ai.py`. En revanche, elles ne peuvent pas servir de checkpoint de
départ à un entraînement dont les espaces ont changé.

### Sous-marin `sub_duel_v1`

L'observation contient :

- vitesse, profondeur, gouvernail, intégrité et bruit émis ;
- stocks de torpilles acoustiques, autonomes et de leurres ;
- disponibilité des torpilles et des leurres ;
- dernier contact sonar connu, âge, position relative, profondeur et bruit ;
- torpille menaçante, position relative, distance, type et temps d'impact ;
- huit rayons anticollision autour du bateau.

L'action contrôle :

1. le gouvernail : fort bâbord, bâbord, neutre, tribord, fort tribord ;
2. la vitesse : arrière, arrêt, lente, croisière, maximale ;
3. la profondeur parmi cinq niveaux normalisés ;
4. l'arme : aucune, torpille acoustique ou autonome ;
5. le largage d'un leurre.

### Destroyer `destroyer_duel_v1`

L'observation contient la navigation, l'intégrité, le bruit, les munitions et
cooldowns des torpilles, du canon, des grenades, des leurres et du sonar actif,
le dernier contact, la menace de torpille et huit rayons anticollision.

L'action contrôle le gouvernail, la vitesse, une arme parmi aucune, torpille
acoustique, torpille autonome, canon ou grenade, puis le leurre et le sonar.

Une commande maintenue pendant son cooldown est une attente silencieuse. Elle
n'est pas comptée comme une erreur à chaque décision.

### Destroyer `destroyer_duel_v2`

La version v2 ajoute les stocks de mines de surface, de fond et suspendues ainsi
que leur cooldown. La sixième composante de l'action choisit le type de mine.

Règles de priorité :

- une grenade demandée est toujours prioritaire et bloque la pose d'une mine
  dans la même décision, même pendant son cooldown ;
- une mine ne peut être posée que toutes les 15 secondes ;
- une mine suspendue reprend la profondeur du dernier contact connu ;
- le délai d'armement et les dégâts proviennent des caractéristiques du bateau ;
- dans `aidest_v3`, poser une mine coûte quatre fois plus qu'effectuer un tir.

Cette pondération laisse les mines disponibles comme outil tactique sans
remplacer les grenades anti-sous-marines.

### Destroyer `destroyer_duel_v3`

La version v3 repart de v1 pour l'etat propre, le contact et les commandes, puis
remplace la menace unique par six trajectoires de torpilles et six positions de
leurres. Les positions et vitesses sont relatives au cap du destroyer. Les slots
sont fixes, bornes et tries afin de conserver un espace PPO constant lorsque le
nombre d'objets du monde varie.

La policy ne peut plus poser de mine : la sixieme composante v2 est supprimee,
ainsi que les stocks et le cooldown de mines. Les mines du jeu, des humains et
des BT ne changent pas. Cette suppression evite qu'un bot sans strategie de pose
consomme son apprentissage et son integrite sur une capacite mal maitrisee.

## Information accessible

Une politique n'est pas omnisciente. `build_observation()` appelle les capteurs
de la simulation et ne lit pas directement la position d'un ennemi caché.

- Un contact détecté met à jour une mémoire locale.
- La position mémorisée expire après 30 secondes.
- Une arme guidée vers une cible exige un contact datant de moins d'une seconde.
- Le sonar actif peut rafraîchir le contact mais révèle également le tireur selon
  les règles du jeu.
- Les rayons anticollision ne décrivent que les côtes et les limites du monde.

## Adversaires

Trois sources d'adversaires peuvent être combinées.

### Behavior Trees

La liste `env.opponents` contient des entrées pondérées :

```json
"opponents": [
  {"boat_type": "submarine", "ai": "autosub", "weight": 1.0},
  {"boat_type": "destroyer", "ai": "autodest", "weight": 1.0}
]
```

### Politique gelée

`fixed_opponent_policy` désigne un répertoire contenant un ou plusieurs
checkpoints compatibles avec la coque déclarée :

```json
"fixed_opponent_policy": {
  "boat_type": "submarine",
  "pool_dir": "models_rl/aisub_v14_selfplay/best",
  "probability": 0.5
}
```

La politique gelée est utile pour entraîner un destroyer contre un sous-marin
RL, puis un sous-marin contre un destroyer RL, sans rendre les deux côtés
non stationnaires en même temps.

### Ligue self-play

Pendant une phase `selfplay`, `train_ai.py` copie le checkpoint initial dans
`league/policy_bootstrap.zip`, puis publie régulièrement des snapshots. À chaque
épisode, l'environnement peut choisir l'un de ces adversaires historiques de la
même coque.

```json
"league": {
  "self_play_probability": 0.7,
  "snapshot_every_steps": 250000,
  "keep_last": 12
}
```

La sélection de ligue est effectuée en premier. Avec une probabilité self-play
de 0,7 et une politique gelée à 0,5, la distribution effective est :

- 70 % contre la ligue historique ;
- 15 % contre la politique gelée ;
- 15 % contre le groupe de Behavior Trees.

## Configuration

Chaque configuration active de `rl/configs/` contient six sections obligatoires.
Les versions historiques v4 à v12 sont conservées sous `rl/configs/archive/`
pour l'analyse, mais ne doivent pas être relancées avec le chargeur actuel.

| Section | Contenu |
|---|---|
| `model` | Architecture MLP et LSTM |
| `training` | Nombre d'étapes, workers et hyperparamètres PPO |
| `env` | Coque, interface, carte, adversaires et curriculum |
| `reward` | Récompenses terminales et intermédiaires |
| `evaluation` | Carte, adversaires, fréquence et épisodes par adversaire |
| `league` | Probabilité self-play et conservation des snapshots |

Configurations principales :

| Configuration | Usage |
|---|---|
| `aisub_v14.json` | Sous-marin contre BT mixtes, puis self-play |
| `aidest_v1.json` | Premier destroyer contre BT et sous-marin gelé |
| `aidest_v2.json` | Raffinement du destroyer historique contre sous-marins |
| `aidest_v3.json` | Nouvelle politique destroyer avec mines et télémétrie |

`curriculum_start_min_m`, `curriculum_start_max_m` et
`curriculum_fraction` rapprochent initialement les adversaires avant de rejoindre
la plage finale `spawn_min_m` à `spawn_max_m`. L'évaluation n'applique jamais le
curriculum.

## Préparation

Créer l'environnement et installer les dépendances :

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Vérifier CUDA :

```bash
.venv/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

Exécuter les tests avant un run long :

```bash
.venv/bin/python -m unittest -v rl.test_rl_pipeline
```

## Phase scripted

Une phase scripted entraîne l'agent contre les Behavior Trees et, si elle est
configurée, une politique gelée. Aucun snapshot de ligue n'est utilisé.

Sous-marin :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
.venv/bin/python -m rl.train_ai --config rl/configs/aisub_v14.json \
  --stage scripted --run-name aisub_v14_scripted --device cuda
```

Destroyer avec mines :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
.venv/bin/python -m rl.train_ai --config rl/configs/aidest_v3.json \
  --stage scripted --run-name aidest_v3_scripted --device cuda
```

Raffinement alterné du sous-marin contre le destroyer RL sélectionné :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
.venv/bin/python -m rl.train_ai --config rl/configs/aisub_v15.json \
  --stage scripted --run-name aisub_v15_scripted \
  --resume rl/models_rl/aisub_v14_selfplay/best/best_model.zip --device cuda
```

`aisub_v15` conserve l'interface `sub_duel_v1`. La moitié des épisodes utilise
le meilleur `aidest_v3_scripted` comme adversaire gelé ; l'autre moitié utilise
un mélange équilibré de `autosub` et `autodest` pour limiter l'oubli des
comportements déjà acquis.

Raffinement alterné du destroyer contre le sous-marin v15 sélectionné :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
.venv/bin/python -m rl.train_ai --config rl/configs/aidest_v4.json \
  --stage scripted --run-name aidest_v4_scripted \
  --resume rl/models_rl/aidest_v3_scripted/best/best_model.zip --device cuda
```

Utiliser `--device cpu` sur une machine sans CUDA. La limitation des threads CPU
évite que les huit workers chargés d'exécuter les adversaires RL ne se disputent
inutilement tous les cœurs.

## Reprise d'un checkpoint

`--resume` demarre une **nouvelle phase warm-start**, pas une continuation exacte :
les poids et l'etat de l'optimiseur sont charges, les parametres scalaires sont
reappliques (dont gamma/lambda dans le buffer). La seed de la nouvelle config est
passee au chargement avant le setup ; les workers recoivent seed + index au reset.
`policy_kwargs` doit correspondre exactement au checkpoint : toute difference
d'architecture est refusee, sans adaptation des poids. `n_steps`, `batch_size`,
l'observation et l'action doivent aussi rester compatibles.

Le repertoire de sortie doit etre absent ou vide, meme avec `--resume` : la CLI
refuse un repertoire non vide avant toute ecriture de configuration. Choisir un
nouveau nom, jamais effacer un run pour le reutiliser. Le rechargement historique
du meilleur score reste disponible dans le callback, mais pas via cette CLI.

```bash
.venv/bin/python -m rl.train_ai --config rl/configs/aidest_v2.json \
  --stage scripted --run-name aidest_v2_scripted \
  --resume rl/models_rl/aidest_v1_scripted/best/best_model.zip --device cuda
```

Le compteur d'étapes repart de zéro dans le nouveau run. Une interface modifiée,
comme le passage de `destroyer_duel_v1` à `destroyer_duel_v2`, nécessite un
nouveau modèle.

### Historique De Preparation V5

Preparation historique, executee ensuite ; voir completion en tete de document.

Apres diagnostic80 et autorisation explicite du run long, `aidest_v5.json` reprend
exactement v4 sauf nom, description et seed1542. Source : v4 best300k, 2M nouvelles
decisions RL demandees, huit workers `forkserver`, memes recompenses, adversaires,
LR, entropie et cadence d'evaluation. PPO finit ses rollouts : avec 8 x 1024,
le compteur final attendu est 2 007 040, pas exactement 2 000 000.

Commande pour le parent, **non executee pendant cette preparation** :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
venv/bin/python -m rl.train_ai --config rl/configs/aidest_v5.json \
  --stage scripted --run-name aidest_v5_scripted_seed1542 \
  --resume rl/models_rl/aidest_v4_scripted/best/best_model.zip --device cuda
```

Le fichier source reste inchange, SHA256
`90c08a62b551f77f23a90194bb7876841df7cf7a9c50987141c3257aa16ca8e2`.
Il contient 300000 etapes, architecture [256,256]/LSTM256/1 et seed historique342
(pas la seed542 demandee dans v4). La nouvelle phase applique effectivement1542.
Les compteurs de phase, curriculum, evaluation et schedule d'entropie repartent ;
ce n'est ni une restauration du RNG historique ni une reprise d'episode.

`provenance.json` est ecrit une seule fois avant `learn`, depuis le modele charge :
source absolue/SHA256 controle avant et apres chargement, compteur source, seed,
classe/policy_kwargs/architecture reels, device et versions des dependances.
Ce manifeste ne remplace pas l'archive de code et d'entrees : le parent doit
archiver commit, empreinte du worktree sale, configs/cartes/specs et adversaire
gele avant son lancement, sans modifier les checkpoints de reference.

Verification locale avec `venv/bin/python -m rl.check_training_device` et les trois
variables de threads ci-dessus : Python3.12.3, torch2.11.0/CUDA13.0,
stable-baselines3 et sb3-contrib2.8.0, Gymnasium1.2.3, NumPy2.4.4 ; RTX5080
disponible et petit calcul CUDA valide. `forkserver` est disponible. Cela ne mesure
pas le debit d'entrainement : simulation et adversaires restent sur CPU ; un petit
LSTM peut etre limite par les transferts/latences GPU. CUDA est une option valide,
pas une preuve de gain face a `--device cpu`. Aucun benchmark long effectue ici.

Validation de preparation : 256 tests passent avec OMP/MKL/OPENBLAS=1, compilation
des trois scripts Python et `git diff --check` OK. Le test recurrent reel charge
un petit checkpoint temporaire puis apprend 32 pas avec huit workers forkserver :
poids identiques avant apprentissage, seeds1542-1549 observees au reset, manifeste
verifie, trois differences d'architecture refusees et sortie non vide preservee.
La source v4 conserve son SHA256 ; aucun run long, commit ou deploiement effectue.

## Phase self-play

Ne démarrer le self-play qu'après une évaluation séparée concluante contre les
adversaires fixes. Exemple sous-marin :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
.venv/bin/python -m rl.train_ai --config rl/configs/aisub_v14.json \
  --stage selfplay --run-name aisub_v14_selfplay \
  --resume rl/models_rl/aisub_v14_scripted/best/best_model.zip --device cuda
```

Pour améliorer les deux coques, préférer des phases alternées :

1. entraîner le destroyer contre un sous-marin gelé ;
2. sélectionner le meilleur destroyer par évaluation ;
3. entraîner le sous-marin contre ce destroyer gelé ;
4. sélectionner le meilleur sous-marin ;
5. répéter avec les nouveaux checkpoints.

Il faut éviter de mettre à jour simultanément les deux politiques dans le même
duel : l'adversaire changerait en permanence et déstabiliserait l'apprentissage.

## Exécution en arrière-plan

```bash
mkdir -p rl/logs
nohup env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
.venv/bin/python -m rl.train_ai --config rl/configs/aidest_v3.json \
  --stage scripted --run-name aidest_v3_scripted --device cuda \
  > rl/logs/aidest_v3_scripted.log 2>&1 &
```

Suivre la progression :

```bash
tail -f rl/logs/aidest_v3_scripted.log
pgrep -af "rl.train_ai"
```

TensorBoard :

```bash
.venv/bin/tensorboard --logdir rl/models_rl
```

## Fichiers produits

Un run `rl/models_rl/<run_name>/` contient :

| Chemin | Contenu |
|---|---|
| `effective_config.json` | Configuration effective et version d'observation |
| `provenance.json` | Source/SHA256, seed et architecture chargees, device et versions avant apprentissage |
| `monitor.csv` | Résultats des épisodes d'entraînement |
| `tensorboard/` | Métriques TensorBoard |
| `checkpoints/` | Sauvegardes périodiques |
| `evaluation/match_scores.jsonl` | Score de match détaillé à chaque évaluation |
| `best/best_model.zip` | Meilleur score `victoire + 0,5 × nul` pondéré |
| `best/selection.json` | Étape, score et résultats du modèle sélectionné |
| `league/` | Bootstrap et snapshots self-play |
| `policy_final.zip` | Politique à la dernière étape |

Les anciens runs créés avec `EvalCallback` possèdent encore un fichier
`evaluation/evaluations.npz`. `best_model.zip` et `policy_final.zip` ne sont pas
nécessairement identiques : une politique peut régresser en fin d'entraînement.
Une évaluation indépendante sur davantage d'épisodes reste requise avant la
promotion dans le jeu.

## Interprétation des métriques

- `rollout/success_rate` mesure les derniers épisodes d'entraînement, avec le
  curriculum et le mélange courant d'adversaires.
- `eval/match_score` agrège les évaluations déterministes selon les poids réels
  des adversaires, sans curriculum.
- `eval/opponent_<n>_match_score` expose chaque adversaire séparément.
- `ep_rew_mean` combine victoire, dégâts, coût temporel et actions.
- `explained_variance` indique la qualité de la fonction de valeur.
- `entropy_loss` reflète la diversité restante des actions.

Les rollouts et l'évaluation ne sont pas directement comparables. Une hausse du
taux de victoire accompagnée de nombreuses actions invalides peut également
cacher une politique inefficace.

## Évaluation séparée

Toujours utiliser les mêmes graines pour comparer deux checkpoints.

Contre des Behavior Trees :

```bash
.venv/bin/python -m rl.evaluate_ai \
  rl/models_rl/aidest_v3_scripted/best/best_model.zip \
  --agent-boat-type destroyer --maps testCombats \
  --opponents submarine/autosub,destroyer/autodest \
  --episodes 100 --seed 60000 --device cuda
```

Contre une politique RL gelée :

```bash
.venv/bin/python -m rl.evaluate_ai \
  rl/models_rl/aidest_v3_scripted/best/best_model.zip \
  --agent-boat-type destroyer --maps testCombats --opponents "" \
  --opponent-pools rl/models_rl/aisub_v14_selfplay/best \
  --opponent-pool-boat-type submarine \
  --episodes 100 --seed 60000 --device cuda
```

La sortie JSON contient les victoires, défaites, matchs nuls, récompenses,
contacts, leurres et sonars. Pour les destroyers, elle détaille aussi :

- torpilles acoustiques et autonomes ;
- coups de canon ;
- grenades ;
- mines de surface, de fond et suspendues ;
- actions invalides.

Une évaluation robuste doit séparer chaque adversaire. Une moyenne agrégée peut
masquer une faiblesse importante contre une coque précise.

### Rapport traçable opt-in

Ajouter `--report` pour remplacer la liste JSON historique par un objet contenant
`report_version`, `seed`, `deterministic`, les manifestes SHA-256 `model` et
`config`, et la liste `results`. Sans ce drapeau, la sortie agrégée reste inchangée.
Chaque résultat détaillé ajoute les paramètres effectifs `env`, le manifeste des
adversaires `opponent_manifest` (BT ou checkpoints visibles du pool), et
`episode_results` : graine, issue, récompense, HP finaux, statistiques terminales,
identité adverse, `terminated`, `truncated` et `length` en décisions RL ;
`physics_steps` compte séparément les pas physiques.

`--config rl/configs/aidest_v4.json` reprend la coque, la version de contrôle,
les récompenses, `frame_skip`, `max_physics_steps`, `spawn_min_m` et `spawn_max_m`.
Le curriculum reste désactivé, comme pendant l'évaluation d'entraînement ; les
cartes et adversaires restent définis par les options CLI, pas par la config.
Une coque CLI contradictoire ou des espaces de modèle incompatibles avec la
coque/version configurée provoquent une erreur. Les récompenses omises sont
complétées par les valeurs par défaut et consignées dans `env.reward`.

Rediriger stdout avec `--report > rapport.json` pour conserver le rapport.
Garder les artefacts et pools gelés pendant toute l'évaluation : les empreintes
sont calculées avant les épisodes, sans copie ni verrouillage des fichiers.
Pour l'API Python, utiliser `evaluate(..., include_episodes=True)` ; le manifeste
du modèle chargé appartient au rapport CLI, car l'API reçoit un modèle en mémoire.

## Chargement dans le jeu

Sans checkpoint explicite, `rl_runtime.py` cherche d'abord
`best/best_model.zip`, puis `policy_final.zip`.

Dans la console du navigateur :

```javascript
spawnRlBot("aisub_v15_scripted");
spawnRlBot("aidest_v3_scripted", false, "", "destroyer");
```

Pour charger un checkpoint nommé :

```javascript
spawnRlBot("aidest_v3_scripted", false, "policy_2500000_steps", "destroyer");
```

Le serveur vérifie les espaces du modèle avant de l'attacher. En cas
d'incompatibilité, il journalise l'erreur et replie le bot sur `autosub` ou
`autodest` selon sa coque.

## Reproductibilité et conservation

- Chaque environnement reçoit une graine distincte dérivée de `training.seed`.
- Les évaluations utilisent une plage de graines séparée.
- Les positions initiales et la simulation headless sont réinitialisées à chaque
  épisode.
- `effective_config.json` conserve les paramètres réellement employés.
- `rl/models_rl/` et `rl/logs/` sont exclus de Git : sauvegarder les checkpoints
  importants sur un stockage adapté avant de nettoyer une machine.

## Diagnostic

Si un run ne démarre pas :

1. vérifier que le pool gelé contient au moins un fichier `.zip` ;
2. vérifier la coque et la version de contrôle du checkpoint ;
3. exécuter `.venv/bin/python -m unittest -v rl.test_rl_pipeline` ;
4. confirmer que CUDA est visible ou utiliser `--device cpu` ;
5. lire la fin du journal et `rl/models_rl/<run>/effective_config.json`.

Les avertissements SB3 concernant `get_schedule_fn()` ou `constant_fn()` sont
des dépréciations de bibliothèque et n'interrompent pas l'entraînement actuel.
