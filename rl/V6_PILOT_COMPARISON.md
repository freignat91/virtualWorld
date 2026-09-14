# V6 : comparaison du pilote 100k / 500k

## Bilan de la continuation 500k : graines 170000-170019

La continuation `aidest_v6_continue_seed3542_review500k` s'est arretee
normalement a507904 nouveaux pas le10 septembre2026 a14:52:31+02:00, apres
1h21m43. Aucun processus d'entrainement ne reste actif. Le checkpoint source
etait le pilote500k, la graine de la nouvelle phase3542, avec LR5e-5,
entropie0.0003 et curriculum deja termine. Les regles, rewards, architecture et
adversaires sont restes inchanges.

Les selections internes divergent :

| Mode | Meilleur pas de la phase | Score interne |
|---|---:|---:|
| Deterministe | 500000 | 49,167 % |
| Echantillonne, trois graines d'actions | 100000 | 78,611 % |

Le score deterministe monte regulierement de1,667 % a49,167 %, principalement
par des nuls. Le score echantillonne vaut78,611/64,722/53,889/57,222/58,611 %
aux echeances100k a500k. Le `policy_final.zip`, sauvegarde apres le dernier
rollout d'optimisation a507904, est distinct du checkpoint500k et n'a pas servi
a la selection ou a la comparaison independante.

Une comparaison independante de400 duels utilise les graines170000-170019,
autosub/sub15 et les memes situations initiales pour chaque cellule. V4, v5,
le pilote500k et le meilleur deterministe de continuation ont une repetition
deterministe. Le pilote500k et le meilleur echantillonne de continuation ont
trois repetitions, graines d'actions seed, seed+1M et seed+2M. Premier endpoint
a300s ; torpilles posthumes des proprietaires coules resolues jusqu'a600s.

| Candidat/mode | Matchs | Score premier | Score apres continuation |
|---|---:|---:|---:|
| v4 deterministe | 40 | 67,50 % | 66,25 % |
| v5 deterministe | 40 | 80,00 % | 80,00 % |
| pilote500k deterministe | 40 | 11,25 % | 8,75 % |
| pilote500k echantillonne | 120 | 81,25 % | 81,25 % |
| continuation meilleur deterministe500k | 40 | 48,75 % | 48,75 % |
| continuation meilleur echantillonne100k | 120 | 75,417 % | 70,833 % |

IC normaux95 %, differences moyennees par adversaire et par les trois
repetitions echantillonnees avant calcul sur20 groupes de graines :

- continuation deterministe - pilote deterministe, settled : +40,00 points,
  IC [33,445 ;46,555] ;
- continuation deterministe - v4 : -17,50 [-26,972 ;-8,028] ;
- continuation deterministe - v5 : -31,25 [-42,973 ;-19,527] ;
- continuation echantillonnee - pilote echantillonne, settled :
  **-10,417 [-16,560 ;-4,274]** ;
- continuation echantillonnee - v4 : +4,583 [-6,562 ;15,729] ;
- continuation echantillonnee - v5 : -9,167 [-20,402 ;2,069].

Le meilleur echantillonne de continuation consomme en moyenne22,892 torpilles,
2,442 grenades,18,475 leurres,10,867 mines et5,55 sonars par duel avant le
premier endpoint. Il cumule3084,078 HP d'auto-degats de mines sur120 matchs,
contre851,900 pour le pilote echantillonne ;9 defaites comportent des
auto-degats de mines contre2 pour le pilote. Cette mesure n'attribue pas a elle
seule la cause finale de chaque naufrage. Aucun plafond de settling n'est atteint.

Conclusion : la phase corrige le mode deterministe catastrophique du checkpoint
source, mais le resultat reste surtout defensif et inferieur aux references.
Elle degrade significativement le candidat echantillonne par rapport au pilote
sur ce lot independant et augmente fortement ses auto-degats de mines. **Ne pas
continuer la meme phase ni promouvoir ces poids sans nouvelle decision.** La
decision suivante cree `destroyer_duel_v3` : six torpilles et six leurres sont
observes, les mines sont retirees des actions RL et un pilote v7 neuf est prepare
mais non lance. Il s'agit d'une refonte combinee demandee, pas d'une ablation
permettant d'attribuer causalement un futur ecart a un seul changement.

Archive :
`rl/models_rl/aidest_v6_continue_seed3542_review500k/evaluation/independent_170000/`.
Dix jobs CPU mono-thread exit0,107/108 empreintes inchangees par job,400 matchs
et traces valides,36MiB. `summary.json`, neuf rapports `verified_v4_*.json` et
`analyze_independent.py` conservent l'analyse. Aucun gameplay, reward, runtime,
poids de production, deploiement ou commit modifie.

Suite preparee : selection de checkpoints independante par mode dans
`train_ai.py`, activee uniquement par `sampled_action_seed_offsets`. Nouvelle
configuration `configs/aidest_v6_dual_eval.json`,500k comme le pilote, sans
modifier les anciennes configurations. Deterministe dans `best/`, echantillonne
dans `sampled/best/`; chaque mode garde son historique et ses graines.267 tests
passes, uniquement petits modeles temporaires ; aucun prolongement ou changement
du runtime lance. Voir TRAINING_RL.md pour les240 matchs par echeance et limites.

## Comparaison aux references : graines 160000-160019

200 duels termines : v4 BEST300k et v5 BEST2M en inference deterministe,
v6 checkpoint500k en inference echantillonnee avec trois repetitions des actions.
Chaque cellule affronte autosub/sub15 sur les memes20 graines de scenario.
La graine Torch des actions vaut seed, seed+1000000 ou seed+2000000 ; les
conditions initiales restent identiques. L'adversaire sub15 reste deterministe.
Les mines sont autorisees dans toutes les cellules : aucune ablation ici.

| Candidat/mode | Nombre matchs | Score premier endpoint | Score apres continuation |
|---|---:|---:|---:|
| v4 deterministe | 40 | 82,50 % | 81,25 % |
| v5 deterministe | 40 | 81,25 % | 82,50 % |
| v6 echantillonne repetition0 | 40 | 82,50 % | 81,25 % |
| v6 echantillonne repetition1 | 40 | 80,00 % | 80,00 % |
| v6 echantillonne repetition2 | 40 | 85,00 % | 82,50 % |
| v6 moyenne des trois repetitions | 120 | 82,50 % | 81,25 % |

Resultats apres continuation par adversaire :

| Candidat | Autosub V/D/N | Score | Sub15 V/D/N | Score |
|---|---|---:|---|---:|
| v4 | 14/0/6 | 85,00 % | 12/1/7 | 77,50 % |
| v5 | 14/0/6 | 85,00 % | 13/1/6 | 80,00 % |
| v6 (trois repetitions cumulees) | 41/0/19 | 84,167 % | 36/2/22 | 78,333 % |

Comparaison appariee : pour chaque graine de scenario, moyenne des trois
repetitions v6 puis moyenne des deux adversaires, avant comparaison a la
reference. IC normal95 % sur20 groupes, pas120 observations independantes.

- V6 - v4 apres continuation : 0,00 point, IC [-9,627 ;9,627].
- V6 - v5 apres continuation : -1,25 point, IC [-9,817 ;7,317].
- Avant continuation : 0,00 [-9,627 ;9,627] et +1,25 [-7,796 ;10,296].

Il s'agit de comparer des combinaisons modele/mode d'inference, pas seulement
les poids : v4/v5 ne sont pas echantillonnes dans cette experience. Les graines
apparient les situations initiales, pas les trajectoires apres divergence des
actions. Petit lot exploratoire, une seule carte et20 situations par adversaire :
pas de preuve d'equivalence, de superiorite, ni de robustesse globale. Aucune
comparaison directe avec les scores historiques sur d'autres graines.

Moyennes par duel agent avant le premier endpoint :

| Mesure | v4 | v5 | v6 echantillonne |
|---|---:|---:|---:|
| Torpilles tirees | 12,025 | 17,050 | 27,033 |
| Grenades tirees | 4,525 | 3,425 | 2,308 |
| Leurres consommes | 15,050 | 16,950 | 18,808 |
| Refus d'arme penalises | 171,600 | 74,600 | 52,275 |
| Stock acoustique epuise | 5/40 | 14/40 | 44/120 |
| Stock autonome epuise | 0/40 | 0/40 | 60/120 |
| Stock de leurres epuise | 17/40 | 24/40 | 92/120 |

V6 ne subit aucun naufrage auto-attribue avant le premier endpoint sur ses120
matchs. Il subit neanmoins896,568 HP d'auto-degats par mines cumules ; ne pas
conclure a une disparition definitive du probleme. La forte consommation
de leurres ne prouve pas une defense optimale, ni un gaspillage de chaque tir.
Les details de degats et des continuations restent dans le rapport JSON.

Archive :
`rl/models_rl/aidest_v6_scripted_seed2542_pilot500k/evaluation/references_160000/`.
Cinq jobs exit0, durees182/193/255/260/246 s ;102 hashes inchanges pour chaque
reference et103 pour chaque repetition v6. Les manifestes incluent toutes les
sources/configs/poids necessaires et les diffs non committes. `summary.json`,
quatre rapports `verified_v4_*.json` et le script `analyze_v6_references.py`
reconcilient les200 duels uniques et leurs traces. Les rapports apparient
plusieurs fois v4 pour verification, sans augmenter artificiellement le nombre
de matchs ou de groupes statistiques. Aucun plafond de continuation atteint.

Le runner diagnostique accepte maintenant `--action-seed-offset` uniquement
avec `--stochastic` ; sa valeur et les graines effectives sont archivees.
Le test verifie des situations identiques avec des actions differentes,
la repetition exacte d'une graine, et les valeurs invalides. 262 tests passes.
Le runtime standard, les regles, rewards et checkpoints restent inchanges.

Conclusion : le depart de zero produit deja une politique echantillonnee
competitive sur ce petit lot, mais aucune promotion n'est justifiee. Avant
prolongement, fixer explicitement un protocole de selection qui suit les deux
modes et plusieurs graines d'actions ; ne pas selectionner exclusivement sur
le score deterministe ni basculer silencieusement le serveur en echantillonnage.
Pas de nouvel entrainement, de serveur, de deploiement ou de commit lance.

## Dernier resultat : ablation des mines, graines 150000-150019

Sur autorisation explicite, 80 nouveaux duels comparent le meme checkpoint
500k deterministe avec et sans pose de mines de l'agent. Chaque condition
affronte autosub et sub15 gele sur 20 graines communes ; toutes les autres
composantes de l'action sont appliquees telles que proposees a chaque decision.
Les trajectoires, observations et futures propositions divergent naturellement
apres l'intervention. Aucun entrainement ni changement des regles du jeu.

| Condition | Autosub V/D/N premier | Sub15 V/D/N premier | Score premier | Score apres continuation |
|---|---|---|---|---|
| Controle, mines autorisees | 0/20/0 | 2/18/0 | 5,00 % | 2,50 % |
| Pose de mines neutralisee | 0/4/16 | 4/8/8 | 40,00 % | 40,00 % |

Apres continuation : controle sub15 0/18/2 ; ablation sub15 3/7/10.
Les autres cellules sont inchangees. Gain apparie apres continuation :
37,50 points, IC normal95 % [27,765 ; 47,235], 20 groupes de graines avec
covariance entre adversaires conservee. Avant continuation : +35,00
[24,101 ; 45,899]. 33 continuations, aucun plafond de 600 secondes atteint.

Les 40 controles confirment 32 naufrages auto-attribues avant continuation et
5860,019 points de degats auto-infliges par mines. Avec l'intervention, aucune
mine agent n'est posee et aucun auto-degat par mine n'existe dans les traces.
Les 40 duels sans mines donnent 4 victoires, 12 defaites et 24 nuls au premier
endpoint ; apres continuation, 3 victoires, 11 defaites et 26 nuls.

La survie ne suffit pas : aucune des deux conditions n'emet de sonar ou ne tire
de grenade/canon. Sans mines, 220 acoustiques tirees contre 173 pour le controle,
110 leurres contre71 ; aucune autonome. Les demandes proposees de mines restent
presentes dans toutes les 37939 decisions agent avant le premier endpoint de
l'ablation. Elles sont neutralisees, pas desapprises.

Conclusion : supprimer la pose de mines de cette politique a un effet positif
net sur cette suite et elimine sa source majeure d'auto-degats. Ce n'est pas
une correction d'apprentissage ni la preuve d'un bon bot ; la plupart des gains
deviennent des nuls. Le resultat motive l'analyse du choix deterministe et de
la distribution apprise plutot qu'une suppression des mines en production.
Ne pas fusionner avec les graines140000 ou comparer numeriquement le40 % aux
77,5 % echantillonnes comme si les conditions initiales etaient identiques.

Archive locale :
`rl/models_rl/aidest_v6_scripted_seed2542_pilot500k/evaluation/mine_ablation_150000/`.
Deux jobs exit0 (103,04 / 134,81 s),103 empreintes d'entree identiques entre
jobs et inchangees apres chacun. L'analyseur reconcilie les80 traces et leurs
issues/degats/stocks ; `intervention_verified.json` verifie chaque action proposee
et appliquee, y compris adversaire inchange, ainsi que le stock de mines intact
jusqu'a la fin. Script de verification conserve dans l'archive.

Le runner diagnostique seul accepte `--disable-agent-mines` (defaut false).
Les deux nouvelles regressions testent la seule composante modifiee, la
preservation du tableau de la policy, les stocks et le rejet d'un schema
incompatible. 261 tests passent ; aucun serveur/entrainement actif, aucun
poids, runtime de production, reward, deploiement ou commit modifie.

Prochaine verification proposee, non lancee : confronter v6 echantillonne aux
references v4/v5 sur les memes conditions, avec plusieurs graines d'actions,
avant de choisir un protocole de selection et une continuation d'apprentissage.

## Etat

Le pilote depuis zero est termine : 507904 transitions, environ 31 min 30 s.
Le callback retient 100000 (score interne 51,667 %), contre 8,333 % a 500000.
Ces scores internes ne mesurent que l'inference deterministe.

Comparaison independante terminee : 160 duels, quatre jobs CPU mono-thread,
sorties 0, aucun changement de poids, de reward, de physique ou de runtime live.
Aucun prolongement du pilote ou promotion n'est lance.

## Protocole

- Checkpoints : BEST100k et `checkpoints/policy_500000_steps.zip`, pas le final
  a 507904 transitions.
- Deux modes : actions deterministes ou echantillonnees de l'agent seulement.
  L'adversaire RL sub15 reste deterministe dans tous les cas.
- `testCombats`, adversaires autosub et sub15 gele, configuration aidest_v6
  complete, sans curriculum en evaluation, HP 200/100/10.
- 20 graines communes 140000-140019 par adversaire et cellule, soit 40 duels
  par cellule. Le RNG Torch de l'agent echantillonne est initialise par graine
  et restaure a la sortie ; l'isolation existante Python/NumPy est conservee.
- Premier endpoint : premier deces ou 300 secondes. Continuation avec les
  controles natifs survivants tant que des torpilles des proprietaires coules
  restent actives, plafond 600 secondes. Les grenades encore actives peuvent
  produire des degats pendant cette continuation.

Le mode echantillonne utilise la distribution apprise, pas des actions uniformes
ajoutees apres coup. Il reproduit le choix stochastique de PPO, mais pas toute
la distribution d'entrainement (carte, curriculum et sequences differentes).

## Resultats

Scores = victoires + 0,5 * nuls, ponderation egale des adversaires.

| Checkpoint / mode | Autosub V/D/N premier | Sub15 V/D/N premier | Score premier | Score apres continuation |
|---|---|---|---|---|
| 100k deterministe | 0/2/18 | 5/2/13 | 51,25 % | 53,75 % |
| 500k deterministe | 0/20/0 | 4/16/0 | 10,00 % | 6,25 % |
| 100k echantillonne | 16/2/2 | 14/3/3 | 81,25 % | 77,50 % |
| 500k echantillonne | 12/0/8 | 12/3/5 | 76,25 % | 77,50 % |

Apres continuation : sub15 100k deterministe 5/0/15, 500k deterministe 0/15/5 ;
100k echantillonne 13/2/5 contre chacun ; 500k echantillonne autosub 12/0/8,
sub15 12/2/6. Aucune continuation n'atteint le plafond de 600 secondes.

IC normaux apparies a 95 %, regroupes sur les 20 graines (moyenne des deux
adversaires dans chaque groupe, covariance conservee) :

| Comparaison | Ecart premier, points | Ecart apres continuation, points |
|---|---|---|
| 500k - 100k, deterministe | -41,25 [-50,15 ; -32,35] | -47,50 [-53,55 ; -41,45] |
| 500k - 100k, echantillonne | -5,00 [-12,62 ; 2,62] | 0,00 [-9,41 ; 9,41] |
| Echantillonne - deterministe, 100k | 30,00 [17,38 ; 42,62] | 23,75 [12,81 ; 34,69] |
| Echantillonne - deterministe, 500k | 66,25 [51,91 ; 80,59] | 71,25 [58,80 ; 83,70] |

IC marginaux exploratoires, sans correction de multiplicite. Une seule graine
d'actions echantillonnees par condition initiale : pas de preuve de robustesse
generale, pas d'equivalence entre checkpoints. Ne pas comparer ces scores
directement aux anciennes evaluations v4/v5 sur d'autres graines.

## Cause observee de l'echec deterministe tardif

Sur 40 duels, le 500k deterministe subit 36 defaites au premier endpoint :
32 naufrages sont attribues nativement a son propre identifiant, et quatre a
l'adversaire. Les traces de degats identifient 5886,111 HP auto-infliges par
ses propres mines. Contre autosub seul : 3562,217 HP auto-infliges, contre
437,783 HP infliges par l'adversaire. Les quatre victoires initiales restantes
deviennent ensuite des nuls, avec quatre autres naufrages auto-attribues.

Il ne tire ni grenade ni canon et n'emet aucun sonar. La tete d'action mine
demande majoritairement des mines de surface (18971 decisions sur 21947),
avec une commande de barre +0,5 tres frequente (19205 decisions).
Ce constat justifie une ablation des mines ; il ne prouve pas a lui seul
qu'une trajectoire particuliere est la cause de chaque explosion.

Le 100k deterministe demande exclusivement des mines de fond, n'utilise
ni leurre ni sonar, et obtient surtout des nuls. Il n'est donc pas un
champion defensif malgre son score superieur.

## Comportement avec echantillonnage

Totaux agents avant le premier endpoint, sur 40 duels :

| Mesure | 100k deterministe | 500k deterministe | 100k echantillonne | 500k echantillonne |
|---|---:|---:|---:|---:|
| Torpilles tirees | 611 | 185 | 918 | 1111 |
| Grenades tirees | 0 | 0 | 156 | 73 |
| Leurres consommes | 0 | 79 | 720 | 763 |
| Pings sonar emis | 0 | 0 | 184 | 250 |
| Mines posees | 708 | 375 | 354 | 493 |
| HP auto-infliges par mines | 0 | 5886,111 | 1651,241 | 73,818 |
| HP adverses infliges par torpilles | 1111,124 | 544,097 | 735,012 | 1461,349 |
| HP adverses infliges par grenades | 0 | 0 | 2545,752 | 1408,952 |

L'echantillonnage produit un comportement beaucoup plus efficace sur cette
suite, mais reste tres consommateur de leurres (18 puis 19,075 par duel).
Il ne demontre pas encore une bonne defense contre une salve, ni que v6
surpasse v4/v5 sous le meme protocole.

## Tracabilite et verifications

Archive locale :
`rl/models_rl/aidest_v6_scripted_seed2542_pilot500k/evaluation/comparison_140000/`.
Quatre sous-dossiers avec manifestes, source archivee, configuration, revisions
et diffs, 160 traces JSONL gzip, resultats et empreintes. Les scripts descriptifs
sont copies dans l'archive avec `behavior_summary.json` et les deux analyses
de verification completes `verified_deterministic.json` / `verified_sampled.json`.

Chaque job controle les hashes avant/apres : 102 entrees pour les jobs BEST,
103 pour les jobs 500k (checkpoint supplementaire). Les deux analyses existantes
ont reconcilie les issues, graines, stocks, decisions, refus, evenements et degats
des 160 traces. Durees : 174,11 / 101,67 / 167,51 / 220,30 secondes pour
BEST deterministe / 500k deterministe / BEST echantillonne / 500k echantillonne.

SHA-256 :
- BEST100k : `102adde7843694c1deb23a98b08810b9143ec396c111b19a4a1f91486ad84086`
- checkpoint500k : `53a0104bfb284b01007de90400ae99d12fa54f66e4c0a9fc0f444c2cec1ac6fc`

Seul le runner diagnostique ajoute `--stochastic`, par defaut desactive ; la
policy gelee adverse, l'evaluation standard et le runtime live restent inchanges.
Test de reproductibilite d'actions et restauration du RNG ajoute.
259 tests passes ; aucun nouveau long entrainement, deploiement ou commit.

## Hypothese initiale du test suivant (executee ci-dessus)

V6-500k gele, inference deterministe, une seule intervention diagnostique :
forcer l'action mine a zero. Comparer au meme checkpoint non modifie sur de
nouvelles graines, avec resultats apparies, auto-degats, contacts, armes et
survie aux torpilles. Cela teste l'hypothese precise des auto-destructions,
sans changer le jeu ni supprimer les mines de l'apprentissage.

Avant une continuation longue, confronter aussi le mode echantillonne aux
references v4/v5 sur les memes graines et plusieurs graines de politique.
Ne pas basculer silencieusement la production vers un mode stochastique ni
retoucher la reward apres lecture de ce seul lot.
