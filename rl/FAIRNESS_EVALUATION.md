# Reevaluation sous regles corrigees

STEP4 termine le 2026-09-10 sous les regles STEP1/2/3 et HP 200/100/10 :
1200 matchs frais, v3 67,00 %, v4 300k 75,50 %, v4 2M 66,50 %.
Voir la nouvelle section finale ; les evaluations ci-dessous restent historiques,
non fusionnees avec ce nouveau regime. Aucune promotion.

Confirmation 94000 terminee le 2026-09-09 : 400 nouveaux matchs valides,
v3 55,25 %, v4 300k 58,00 %. Gain frais +2,75 points, IC 95 % groupe par
graine [-3,073 ; 8,573]. Pas de promotion ; detail et cumul en fin de document.

## Resultats initiaux du 2026-09-09 (92000/93000)

Les six jobs sont termines avec code zero, sans stderr, en environ 6,5 minutes.
Les 1200 issues sont validees et archivees, aucun job restant a relancer.
V4 300k depasse v3 sur cette suite ; v4 2M regresse. Aucun modele promu.

W/L/D = victoires/defaites/nuls. Chaque cellule adversaire cumule 200 matchs.

| Modele | Autosub W/L/D | Score | V15 W/L/D | Score | Score 50/50 | Ecart v3, IC 95 % (points) |
|---|---|---|---|---|---|---|
| v3 champion | 67/11/122 | 64,00 % | 79/103/18 | 44,00 % | 54,000 % | reference |
| v4 300k | 93/18/89 | 68,75 % | 100/88/12 | 53,00 % | 60,875 % | +6,875 [2,447 ; 11,303] |
| v4 2M | 60/61/79 | 49,75 % | 76/113/11 | 40,75 % | 45,250 % | -8,750 [-13,708 ; -3,792] |

### Detail par serie

100 matchs par ligne ; ecarts apparies au v3 du meme adversaire et de la meme graine.

| Modele | Adversaire | Serie | W/L/D | Score | Ecart v3, IC 95 % (points) |
|---|---|---|---|---|---|
| v3 | autosub | 92000 | 33/6/61 | 63,5 % | reference |
| v3 | autosub | 93000 | 34/5/61 | 64,5 % | reference |
| v3 | v15 | 92000 | 35/58/7 | 38,5 % | reference |
| v3 | v15 | 93000 | 44/45/11 | 49,5 % | reference |
| v4 300k | autosub | 92000 | 52/9/39 | 71,5 % | +8,0 [0,16 ; 15,84] |
| v4 300k | autosub | 93000 | 41/9/50 | 66,0 % | +1,5 [-7,25 ; 10,25] |
| v4 300k | v15 | 92000 | 53/43/4 | 55,0 % | +16,5 [6,16 ; 26,84] |
| v4 300k | v15 | 93000 | 47/45/8 | 51,0 % | +1,5 [-6,79 ; 9,79] |
| v4 2M | autosub | 92000 | 23/36/41 | 43,5 % | -20,0 [-29,13 ; -10,87] |
| v4 2M | autosub | 93000 | 37/25/38 | 56,0 % | -8,5 [-17,64 ; 0,64] |
| v4 2M | v15 | 92000 | 42/53/5 | 44,5 % | +6,0 [-6,09 ; 18,09] |
| v4 2M | v15 | 93000 | 34/60/6 | 37,0 % | -12,5 [-21,46 ; -3,54] |

Ecarts par adversaire sur les deux series : v4 300k/autosub +4,75
[-1,13 ; 10,63], v4 300k/v15 +9,00 [2,37 ; 15,63] ;
v4 2M/autosub -14,25 [-20,71 ; -7,79], v4 2M/v15 -3,25 [-10,77 ; 4,27].

## Protocole

- Trois ZIP demandes, sans apprentissage ni modification des champions.
- `testCombats`, `autosub` et seul ZIP du repertoire gele sous-marin v15 `best`.
- `--report --config rl/configs/aidest_v4.json --device cpu --episodes 100`.
- `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`.
- Graines 92000-92099 et 93000-93099 pour chaque modele/adversaire.
- Six jobs, 200 matchs chacun, soit 1200 matchs realises, 400 par modele.
- 200 valeurs de graines distinctes, reutilisees entre modeles et adversaires ;
  400 paires de matchs par comparaison a v3, pas 1200 graines independantes.
- Regles courantes : profondeur canon corrigee, radar torpilles strict,
  sonar actif RL differe. Le contrat BT existant reste inchange.
- Score : victoire=1, nul=0,5, defaite=0 ; poids fixes 50/50 des adversaires.

Les resultats historiques ne doivent pas etre fusionnes avec cette experience.
Les differences avant/apres ne permettent pas d'attribuer un effet causal a
une correction particuliere : regles et series de graines ont change.

## Tracabilite

Artefacts locaux sous `rl/models_rl/aidest_v4_scripted/evaluation/fairness_corrected/` :
`run_manifest.json`, `initial.diff`, `source_inputs.tar.gz`,
`fairness_corrected_inputs.sha256`, revision HEAD, statut initial, dependances,
captures de tests et processus, les six `fairness_corrected_v*.json` complets et
`fairness_corrected_analysis.json`. Ce repertoire est un artefact local ignore par Git.

Le HEAD seul ne represente pas le code execute : les corrections etaient non
committees, dont des modules non suivis. Le diff initial SHA-256 est
`c412c65e467ca932e30189de578fdf6d2a9efdc98785a7ab5ca22fc68bd45b0a`.
L'archive contient aussi les sources Python non suivies et les cartes/bateaux/BT.
Les hashes des quatre ZIP et de la config sont captures avant execution.
Pas de verrou filesystem ; les 38 hashes ont ete recontroles apres completion,
tous inchanges. Les six rapports identifient les memes ZIP/config/BT attendus.
Les ajouts de documentation et d'analyse apres l'archive ne changent pas Sim.

Verification actuelle : 57 tests passes (simulation, rapports, fairness, sonar,
RNG, pipeline et analyse), compilation des nouveaux scripts et `git diff --check`
OK ; 38 empreintes d'entrees inchangees. Les smoke tests utilisent des modeles
temporaires, pas les checkpoints evalues. Tous les changements preexistants sont
preserves ; aucune regle, reward, configuration ou politique n'a ete modifiee.

## Validation Et Analyse

Controle effectue sur chacun des 12 groupes : exactement 100 issues et graines
consecutives attendues, W/L/D et reward moyenne coherents, identite adversaire
par episode et hash de l'unique ZIP/BT selectionnable. Options effectives verifiees :
reward v4 exacte, frame_skip=5, max_physics_steps=6000, spawn=600-2000 m,
curriculum_decisions=0, destroyer_duel_v2, adversaire sous-marin, aucun self-play.
Chaque processus observe avait un seul thread. Rapports copies seulement apres
validation ; aucun rapport historique ecrase.

```bash
venv/bin/python -m rl.analyze_evaluation_reports \
  --baseline 103481713271ed04cf03007f1468898e6b4c928214c12f28ecd90fabfc5066c2 \
  --episodes 100 rl/models_rl/aidest_v4_scripted/evaluation/fairness_corrected/fairness_corrected_v*.json
```

L'analyseur rejette les fichiers incomplets, les graines incorrectes, W/L/D
incoherents, hashes modifies, doublons et strates/environnements non apparies.
Il ne remplace pas le controle des codes de sortie et du manifeste de lancement.

Pour chaque strate adversaire x serie, apparier le score candidat a v3 par graine.
Difference agregee = moyenne des quatre moyennes de differences ;
SE = sqrt(sum(s_h^2/n_h))/4, IC normal = difference +/- 1,96 SE.
Les poids restent fixes : pas de variance artificielle due au melange d'adversaires.
Les IC sont marginaux, sous hypothese d'echantillonnage des graines et de strates
independantes, sans correction de multiplicite ni garantie de generalisation.
Une graine partagee apparie les conditions initiales, pas les trajectoires ou les
tirages de combat apres divergence des actions. Il ne faut donc pas pretendre
a un couplage aleatoire parfait. Un IC incluant zero ne prouve pas l'equivalence.

## Conclusion Et Suite

V4 300k passe les seuils ponctuels existants (+3 points agreges, pas de regression
adversaire >5 points), mais la borne basse de son IC agrege reste sous +3 points.
Le gain varie fortement entre series ; les nuls restent nombreux contre autosub.
V4 2M echoue, avec une regression nette surtout contre autosub ; cette experience
ne demontre pas la cause de la degradation tardive ni une parite reseau complete.
Validation humaine et latence restent absentes : pas de promotion automatique.

Plus petit experiment recommande a cette etape, depuis termine ci-dessous : v3 contre
v4 300k seulement, nouvelle serie 94000-94099, 100 matchs par adversaire/modele
(400 matchs, CPU mono-thread, memes regles/rewards, aucun entrainement).
Hypothese : gain positif reproductible, pas seulement effet de la serie 92000.
Conserver les seuils existants et publier l'IC apparie ; suspendre toute promotion
en cas de regression ou d'incertitude persistante. Ne pas ajuster les rewards
apres lecture de ces resultats ; completer ensuite revue humaine et latence.

## Confirmation 94000 Terminee

Deux jobs seulement, v3 champion et v4 best 300k, termines avec code zero en
282,675 s et 262,586 s respectivement, stderr vide et aucun processus restant.
100 episodes par adversaire/modele, exactement 94000-94099 : 400 matchs,
200 paires candidat/reference mais seulement 100 graines distinctes.
Meme `testCombats`, `--report --config rl/configs/aidest_v4.json`, CPU,
`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1` ; les deux
processus observes avaient NLWP=1. Aucun job v4 2M ni entrainement experimental.

### Nouvelle serie seule

| Modele | Autosub W/L/D | Score | V15 W/L/D | Score | Score 50/50 |
|---|---|---|---|---|---|
| v3 champion | 43/6/51 | 68,50 % | 38/54/8 | 42,00 % | 55,25 % |
| v4 300k | 53/8/39 | 72,50 % | 41/54/5 | 43,50 % | 58,00 % |

Ecarts apparies v4-v3, IC normal 95 % en points : autosub +4,000
[-3,328 ; 11,328], v15 +1,500 [-6,187 ; 9,187]. Agrege groupe par graine :
**+2,750 [-3,073 ; 8,573]**. Le gain ponctuel frais est inferieur a +3 points,
sans regression ponctuelle par adversaire ; son IC inclut zero. Cela ne prouve
ni un gain positif reproductible sur cette serie seule, ni l'equivalence.

### Cumul sous les seules regles corrigees

92000/93000/94000, uniquement v3 et v4 300k : 300 matchs par cellule adversaire,
600 par modele, 1200 au total, 600 paires et 300 graines distinctes.
Les 400 matchs v4 2M initiaux ne font pas partie de ce cumul, ni aucun rapport
historique sous anciennes regles. Les 38 hashes initiaux etaient tous encore
identiques avant lancement ; l'analyse controle aussi les environnements entre series.

| Modele | Autosub W/L/D | Score | V15 W/L/D | Score | Score 50/50 |
|---|---|---|---|---|---|
| v3 champion | 110/17/173 | 65,500 % | 117/157/26 | 43,333333 % | 54,416667 % |
| v4 300k | 146/26/128 | 70,000 % | 141/142/17 | 49,833333 % | 59,916667 % |

Ecarts par adversaire : autosub +4,500 [-0,116 ; 9,116], v15 +6,500
[1,393 ; 11,607]. Agrege groupe par graine : **+5,500 [2,016 ; 8,984]**.
Les gains agreges par serie sont +12,25, +1,50 et +2,75 points : le signal
reste fortement porte par 92000. Les nuls autosub restent nombreux.

### Covariance et statut statistique

L'analyseur existant est reutilise sans modification pour valider les rapports,
scores et IC par adversaire. Ses IC agreges supposent les strates adversaires
independantes, ce que la reutilisation des memes graines ne garantit pas.
La reanalyse locale conserve explicitement cette covariance : pour chaque
serie h et graine i, z_hi = (d_autosub_hi + d_v15_hi) / 2 ; delta = mean_h(mean_i z_hi),
SE = sqrt(sum_h(var(z_h)/100)) / H, IC = delta +/- 1,96 SE.
Les poids adversaires restent 50/50 et les H series disjointes ont poids egaux.

Covariances empiriques des differences de score entre adversaires :
92000 -0,03353535 ; 93000 +0,01744949 ; 94000 +0,02969697.
La covariance positive de 94000 elargit son IC ; l'ignorer n'est pas justifie.

| Series | Ecart (points) | IC analyseur, independance | IC groupe par graine retenu |
|---|---|---|---|
| 94000 seule | +2,750 | [-2,560 ; 8,060] | [-3,073 ; 8,573] |
| 92000/93000 | +6,875 | [2,447 ; 11,303] | [2,535 ; 11,215] |
| Trois series | +5,500 | [2,058 ; 8,942] | [2,016 ; 8,984] |

Les IC initiaux v4 2M restent ceux de l'analyse initiale, non recalcules ici.
Les nouveaux IC supposent encore des graines/series independantes, un
echantillonnage representatif et une approximation normale ; pas de correction
de multiplicite ni de couplage parfait des tirages de combat. Cette experience
est une **confirmation post hoc** apres selection de v4 300k, pas un nouveau
gate statistique preregistre. Le cumul est descriptif et ne supprime pas ce biais
de selection. Aucun nouveau seuil n'est invente : les seuils ponctuels existants
restent +3 points agreges et aucune regression adversaire >5 points ; une borne
basse d'IC au-dessus de +3 n'est pas ajoutee comme exigence retrospective.

### Archive et verifications

Nouveau repertoire local ignore, cree sans ecrasement :
`rl/models_rl/aidest_v4_scripted/evaluation/fairness_corrected/confirmation_94000/`.
`launch_manifest.json`, manifests par job et de completion, `initial.diff`,
`staged.diff`, statut/HEAD, dependances/CPU, `source_inputs.tar.gz`,
`inputs.sha256` et captures de processus/tests preservent le code sale execute.
Les deux `confirmation_*.json` ont ete archives seulement apres validation :
issues/graines exactes, W/L/D, reward moyenne, identite par episode et seul ZIP
v15, hashes modeles/config/BT et environnement identique a 93000, reward v4
exacte. Les 40 hashes d'entrees sont inchanges apres completion ; ils incluent
aussi le ZIP 2M a titre de protection, sans l'evaluer. Pas de verrou filesystem.

`fresh_*`, `previous_*`, `combined_*` conservent les deux methodes d'analyse.
Le README local donne la reproduction sans ecriture via
`analyze_confirmation.py --stdout-only` et les trois tests de covariance.
57 regressions existantes et 3 tests analytiques passes ; `compileall` et
`git diff --check` OK. Les smoke tests existants utilisent uniquement des modeles
temporaires, jamais les checkpoints evalues. Aucun fichier de gameplay, reward,
config, runtime, champion ou analyseur existant modifie par cette confirmation.

### Decision et prochaine action

**Aucune promotion.** Le cumul passe les seuils ponctuels existants mais la
confirmation fraiche reste incertaine et la revue humaine n'a pas ete faite.
Au terme de cette confirmation, latence non mesuree : la documentation de deploiement identifie la source
d'entrainement, pas une cible de production accessible ; aucun benchmark du
poste local n'est presente comme une mesure de production. Aucun p50/p95/p99/max
n'est donc revendique, aucun script de benchmark ni changement runtime ajoute.

Prochaine action : identifier la machine CPU de production et organiser la revue
humaine v3/v4 (passivite/nuls, tirs invalides, sonar, absence d'omniscience), puis
mesurer le vrai `RuntimeController.model.predict` des deux ZIP : CPU et threads
documentes, warmup complet, au moins 100 echantillons mesures, p50/p95/p99/max.
Cette mesure exclura simulation, reseau et charge multi-bots ; elle ne suffira
pas seule a valider tout le budget de decision de 250 ms. Aucun nouveau run long,
ajustement de reward ou relancement automatique de ces evaluations.

## Latence CPU Locale Friatech

Benchmark autorise et execute le 2026-09-09 sur **friatech**, pas sur une cible
etablie representative de production. Intel Core i9-12900F, 24 CPU logiques,
affinite 0-23 sans epinglage, Linux 7.0.0-30-generic x86_64 / glibc 2.39,
Python 3.12.3, Torch 2.11.0, SB3/SB3-Contrib 2.8.0, NumPy 2.4.4, Gymnasium 1.2.3.
Un seul processus, modeles mesures successivement, sans test de charge concurrente.

`rl/benchmark_inference.py` utilise le vrai `load_model` CPU puis
`RuntimeController.model.predict`, sans changement du runtime. Pour chaque modele,
64 observations float32 legales viennent d'un reset headless et d'une courte
trajectoire pilotee par ce modele sur `testCombats`, graine 95000, contre `autosub`.
Preparation, simulation et chargement sont hors chronometrage. Deux relectures
distinctes : 100 predictions de warmup puis 1000 mesures. Etat LSTM retourne
conserve entre decisions ; nouveau controleur (`state=None`, `episode_start=True`)
aux debuts d'episode et de corpus, y compris au debut de la phase mesuree.
Ce corpus court repete ne couvre pas la diversite d'un match complet.

`deterministic=True`, algorithmes Torch deterministes, graines Python/NumPy/Torch
fixees ; `PYTHONHASHSEED=95000`. Threads Torch intra-op=1 et inter-op=1, uniquement
dans le processus CLI ; OMP/MKL/OpenBLAS=1. Avant les options CLI, Torch annonce
intra-op=1 sous cet environnement et inter-op=16. Aucun defaut global de production
modifie ; aucun benchmark distinct des defauts natifs n'a ete execute.

| Modele | p50 ms | p95 ms | p99 ms | Max ms | Moyenne ms | Predictions/s |
|---|---|---|---|---|---|---|
| v3 champion | 0,442635 | 0,460407 | 0,482280 | 0,553090 | 0,443825 | 2253,14 |
| v4 best 300k | 0,440122 | 0,461595 | 0,484843 | 0,509959 | 0,442058 | 2262,15 |

Debit = 1000 / moyenne en ms, uniquement temps cumule de `predict`, pas debit
de simulation ni capacite serveur. Percentiles : interpolation lineaire NumPy.
Exclusions : construction des observations, application des actions, simulation,
reseau, ordonnancement 4 Hz et charge multi-bots. La creation du tableau
`episode_start` et l'affectation de l'etat retourne sont incluses, comme au runtime.
Ces chiffres ne valident **ni le budget complet de 250 ms ni la production**.

Archive locale ignoree, nouveau chemin sans ecrasement :
`rl/models_rl/aidest_v4_scripted/evaluation/latency_friatech/20260909_threads1/results.json`.
Elle contient les 2000 latences brutes, options, environnement, hashes du corpus,
marqueurs de reset et SHA-256 des sources/entrees verifies inchanges en fin de run.
SHA-256 des ZIP verifies avant/apres chaque mesure :

- v3 : `103481713271ed04cf03007f1468898e6b4c928214c12f28ecd90fabfc5066c2`.
- v4 300k : `90c08a62b551f77f23a90194bb7876841df7cf7a9c50987141c3257aa16ca8e2`,
  conforme a `best/selection.json` (300000 pas).

Commande executee depuis la racine (choisir une nouvelle sortie pour refaire) :

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONHASHSEED=95000 \
venv/bin/python -m rl.benchmark_inference \
  rl_aidest_v3_scripted rl_aidest_v4_scripted \
  --threads 1 --interop-threads 1 --warmup 100 --samples 1000 \
  --trajectory-steps 64 --seed 95000 --map testCombats \
  --output rl/models_rl/aidest_v4_scripted/evaluation/latency_friatech/20260909_threads1/results.json
```

Le smoke CLI a charge les deux vrais ZIP avec warmup=2, samples=5 et corpus=4
(sortie `/tmp/latency_friatech_smoke_20260909.json`) ; ces nombres ne sont pas les
resultats retenus. Les petits comptes sont acceptes pour les smoke tests seulement,
les valeurs par defaut restent 100/1000. Tests dedies : validation des arguments,
refus de sortie existante/modele absent et transport/reset recurrent chronometre.
Verification finale : 56 tests RL (dont 3 nouveaux) et 4 tests simulation passes,
compilation des deux nouveaux modules et `git diff --check` OK. Les travaux
non committes preexistants sont preserves ; `rl/AGENTS.md` reste un fichier local ignore.

**Aucune promotion.** Inspection humaine toujours manquante, machine de production
toujours non etablie. Pour le test local que le parent prepare : comparer v3 et
v4 par leurs noms runtime ci-dessus, sans remplacer le champion ; observer
passivite/nuls, tirs invalides, sonar et absence d'omniscience. Aucun serveur lance
par ce benchmark ; demarrage et inspection restent au parent/utilisateur.

## STEP4 Termine : Regles STEP1/2/3 (2026-09-10)

Autorisation explicite de reevaluation uniquement. Six jobs lances le
2026-09-09 vers 23:53 +02:00, termines le 2026-09-10 vers 00:03 +02:00,
tous exit 0, stderr vide, aucun timeout ni processus d'evaluation restant.
Exactement 100 episodes dans chacune des 12 strates, graines consecutives
96000-96099 et 97000-97099 : 1200 matchs, 400 par candidat, 200 graines
distinctes reutilisees entre candidats et adversaires.

### Nouveau protocole et perimetre

- Trois ZIP : champion destroyer v3, v4 best selectionne a 300k, checkpoint v4 2M.
- Carte `testCombats`, adversaires `submarine/autosub` et unique ZIP sous-marin
  v15 `best`, poids fixes 50/50 ; aucune politique adverse tiree d'un autre pool.
- `--report --config rl/configs/aidest_v4.json --episodes 100 --device cpu` ;
  `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, NLWP observe = 1.
- Reward v4 exacte inchangee, controle `destroyer_duel_v2`, frame_skip 5,
  dt 0,05 s, 6000 ticks maximum, spawn final 600-2000 m, curriculum/self-play nuls.
- Regles actuelles : sonar BT differe STEP1, canon partage sur trajectoire STEP2,
  torpilles sans contact STEP3, HP destroyer/sous-marin/leurre = 200/100/10,
  plus corrections precedentes de LOS, menaces, mouvement et guidage.
- Fin d'evaluation **au premier bateau mort**, ou 300 s ; aucun changement de
  terminaison. L'autogame local attend les torpilles des proprietaires coules et
  a un plafond de 600 s : ces scores ne mesurent PAS cette condition de victoire.
- Sous-marin v15 gele en poids, pas en comportement : observations, torpilles et
  environnement courants l'affectent aussi. Aucun score ancien ajoute au cumul.

### Resultats frais

W/L/D = victoires/defaites/nuls ; 200 matchs par cellule adversaire.
Score = victoire + 0,5 nul. Ecarts en points de pourcentage contre v3.

| Modele | Autosub W/L/D | Score | V15 W/L/D | Score | Score 50/50 | Ecart v3, IC 95 % groupe par graine |
|---|---|---|---|---|---|---|
| v3 champion | 70/0/130 | 67,50 % | 96/30/74 | 66,50 % | 67,00 % | reference |
| v4 300k | 111/0/89 | 77,75 % | 114/21/65 | 73,25 % | 75,50 % | +8,50 [4,727 ; 12,273] |
| v4 2M | 68/5/127 | 65,75 % | 97/28/75 | 67,25 % | 66,50 % | -0,50 [-4,481 ; 3,481] |

Ecarts par adversaire : v4 300k/autosub +10,25 [5,840 ; 14,660],
v4 300k/v15 +6,75 [0,912 ; 12,588] ; v4 2M/autosub -1,75
[-6,435 ; 2,935], v4 2M/v15 +0,75 [-4,885 ; 6,385].

| Modele | Adversaire | Serie | W/L/D | Score % | Ecart v3, IC 95 % |
|---|---|---|---|---|---|
| v3 | autosub | 96000 | 31/0/69 | 65,5 | reference |
| v3 | autosub | 97000 | 39/0/61 | 69,5 | reference |
| v3 | v15 | 96000 | 50/14/36 | 68,0 | reference |
| v3 | v15 | 97000 | 46/16/38 | 65,0 | reference |
| v4 300k | autosub | 96000 | 56/0/44 | 78,0 | +12,50 [5,483 ; 19,517] |
| v4 300k | autosub | 97000 | 55/0/45 | 77,5 | +8,00 [2,656 ; 13,344] |
| v4 300k | v15 | 96000 | 56/13/31 | 71,5 | +3,50 [-5,115 ; 12,115] |
| v4 300k | v15 | 97000 | 58/8/34 | 75,0 | +10,00 [2,121 ; 17,879] |
| v4 2M | autosub | 96000 | 34/3/63 | 65,5 | 0,00 [-6,824 ; 6,824] |
| v4 2M | autosub | 97000 | 34/2/64 | 66,0 | -3,50 [-9,922 ; 2,922] |
| v4 2M | v15 | 96000 | 56/17/27 | 69,5 | +1,50 [-6,435 ; 9,435] |
| v4 2M | v15 | 97000 | 41/11/48 | 65,0 | 0,00 [-8,002 ; 8,002] |

L'analyseur reutilisable conserve maintenant la covariance entre adversaires :
pour chaque serie h et graine i, z_hi = (d_autosub_hi + d_v15_hi)/2 ;
delta = moyenne_h(moyenne_i z_hi), SE = sqrt(sum_h(var(z_h)/100))/2,
IC normal = delta +/- 1,96 SE. Chaque comparaison a 400 paires de matchs
mais **200 groupes de graines**, pas 400 paires independantes. Les IC par
adversaire gardent les deux series disjointes a poids egaux. Les diagnostics
sous independance des strates sont archives, non retenus pour les conclusions
agregees : v4 300k [4,842 ; 12,158], v4 2M [-4,164 ; 3,164].

Hypotheses restantes : echantillonnage representatif, independance entre graines
et series, approximation normale ; IC marginaux sans correction de multiplicite.
Les graines apparient les conditions, pas tous les tirages apres divergence des
actions. Selection historique du checkpoint connue ; pas de nouveau gate post hoc.
V4 300k progresse dans les deux series (+8 et +9 points agreges), passe les
seuils ponctuels existants (+3 agreges, aucune regression adverse >5), sans
etablir une robustesse globale ni autoriser une promotion. V4 2M ne demontre
ni gain ni equivalence a v3 ; ne pas recycler la conclusion historique de regression.

### Munitions et comportement

Moyennes **par episode de l'agent** ; toutes les colonnes sont des comptes
de succes/rejets reels, pas des intentions supposees ni des taux de degats.

| Modele/adversaire | Torp. acoust. | Torp. auton. | Grenades | Armes invalides | Leurres | Contacts | Duree sim. s |
|---|---|---|---|---|---|---|---|
| v3/autosub | 0,015 | 0,155 | 1,170 | 28,875 | 4,825 | 0,470 | 224,217 |
| v3/v15 | 0,000 | 0,515 | 4,905 | 55,615 | 8,835 | 5,950 | 156,834 |
| v4 300k/autosub | 8,780 | 0,825 | 2,045 | 165,465 | 13,740 | 0,695 | 194,282 |
| v4 300k/v15 | 9,655 | 1,365 | 3,850 | 128,535 | 14,980 | 3,510 | 155,377 |
| v4 2M/autosub | 0,755 | 0,200 | 1,280 | 20,615 | 4,580 | 0,760 | 239,490 |
| v4 2M/v15 | 2,895 | 0,205 | 4,535 | 40,345 | 10,095 | 4,180 | 168,968 |

Agregat 50/50 : v3/v4 300k/v4 2M tirent respectivement 0,3425/10,3125/2,0275
torpilles et 3,380/13,260/4,935 armes par episode ; demandes invalides
42,245/147,000/30,480 (0,222/0,841/0,149 par seconde simulee).
V4 300k utilise environ 30 fois plus de torpilles que v3 et fait 3,48 fois plus
de demandes invalides, malgre des parties plus courtes (174,829 contre 190,525 s).
Ce signal ne vient donc pas simplement d'une duree d'exposition plus longue.
La fraction de demandes d'armes rejetees vaut 92,59/91,73/86,07 % : une fraction
legerement moindre pour v4 300k ne signifie pas moins de spam en volume.

Sur 400 episodes/modele, epuisement des 20 torpilles acoustiques : 0/23/0 ;
des 16 autonomes : 0/0/0 ; des 20 leurres : 22/122/32.
Episodes sans aucun tir de torpille : 328/6/162. Aucun tir de canon reussi dans
les 1200 matchs ; les compteurs ne distinguent pas un canon demande puis rejete.
Mines/episode : 0,025/0,030/0,055, aucune demande de mine invalide.
Sonars/episode : 6,5725/6,0800/7,0175, aucune demande sonar invalide.
Les nuls restent importants : 204/154/202, dont 203/154/202 timeouts et
un double naufrage simultane pour v3. Les contacts comptent des transitions
vers une detection, pas du temps de contact ni des ennemis distincts.

**Limites d'instrumentation :** pas d'etiquette tir aveugle/avec contact, pas
de raison de rejet, pas de consommation adverse, pas de hits ni de degats en
points attribues aux armes. Les HP terminaux sont archives mais ne remplacent
pas ces compteurs ; le reward ne permet pas de reconstruire les degats.
La consommation elevee de v4 300k est mesuree sous STEP3, mais ni son gaspillage
exact ni un effet causal propre aux tirs sans cible ne sont identifies ici.
Ne pas comparer ces volumes a une ancienne baseline sous d'autres regles.

### Tracabilite et ressources

Nouvelle archive locale ignoree, sans ecrasement :
`rl/models_rl/aidest_v4_scripted/evaluation/rules_steps123/`.
Elle contient manifests de lancement/completion, commandes exactes, stdout/stderr,
six rapports JSON, `analysis.json`, `metrics.json`, scripts de lancement/resume,
dependances/CPU, statut Git, diffs initial/index, 125 hashes et archive source
incluant sources non suivies, client, tests, cartes, specs et arbres BT.
Les 125 empreintes ont toutes ete recontrolees identiques apres les six jobs,
avant les ajouts documentaires de completion. Aucun verrou filesystem.

HEAD `a237504f9cb362588848d5dcb77a31e6a9e501a6` ne suffit pas a identifier
le code sale execute. SHA-256 :

| Artefact | SHA-256 |
|---|---|
| v3 champion | `103481713271ed04cf03007f1468898e6b4c928214c12f28ecd90fabfc5066c2` |
| v4 best 300k | `90c08a62b551f77f23a90194bb7876841df7cf7a9c50987141c3257aa16ca8e2` |
| v4 checkpoint 2M | `473f08d02b34ac5f6e9eacbfe04b65500cbf3cd743a0fc98331b326312655a77` |
| sous-marin v15 best | `2849f0c79a15fced51a249720bd25bd4210ee1bafc4c71f79aa942dfaab421c5` |
| config aidest_v4 | `38e16186ca860bc589209ac9051ef212b50b0c284b82d29a1570ec907a7c7fdc` |
| source_inputs.tar.gz | `d37c4496750ff4a427de2a087cf79930ca84236ea8c67703bf6558d487f1d1e9` |
| initial.diff | `fd0c27642dd1748b2feaf56bc652a71411ef9195ffec61e8ea872e1dea9e1eb0` |

| Job | Duree murale s | CPU utilisateur s | CPU systeme s | Pic RSS KiB | Exit |
|---|---|---|---|---|---|
| v3/96000 | 472,429 | 472,125 | 0,236 | 829820 | 0 |
| v3/97000 | 466,483 | 466,218 | 0,245 | 826120 | 0 |
| v4 300k/96000 | 597,544 | 597,283 | 0,238 | 826244 | 0 |
| v4 300k/97000 | 575,707 | 575,437 | 0,216 | 831216 | 0 |
| v4 2M/96000 | 482,320 | 482,062 | 0,232 | 830928 | 0 |
| v4 2M/97000 | 522,995 | 522,688 | 0,264 | 831488 | 0 |

Ressources via `getrusage(RUSAGE_CHILDREN)` du processus d'evaluation ; environ
10 minutes murales en parallele, sans epinglage CPU. Timeout interne 3500 s,
outil 3600 s ; pas de coupe arbitraire a 600 s. Ce n'est pas une mesure de
latence de production, ni une comparaison de cout `predict` isole.

Validation : 247 tests Python passes (dont les 5 tests de l'analyseur), compilation
des scripts et `git diff --check` passes. Tests analytiques couvrant covariance
positive/negative, poids fixes et rejet de series chevauchantes/non appariees.
Le test pipeline utilise son modele temporaire habituel, jamais les ZIP evalues.
Aucun gameplay/reward/config/observation/action/modele modifie ; seuls analyseur,
tests, documentation et artefacts ont ete ajoutes/modifies pour STEP4.
Aucun entrainement long, promotion, deploiement, serveur live ou commit.

### Prochaine experience avant tout run RL long

**Priorite : diagnostic instrumente apparie, pas davantage de PPO.** Proposer,
sur nouvelle autorisation, v3 et v4 300k seulement, 20 graines nouvelles
98000-98019 par adversaire, soit 80 trajectoires, CPU mono-thread et memes
conditions initiales. Enregistrer tirs avec/sans contact legal, raisons des
rejets, ammo restante, impacts/degats et torpilles encore actives au premier mort.
Avant execution, choisir explicitement le contrat de fin a mesurer ; si une
continuation de settling est autorisee, conserver les deux classifications sur
chaque meme trajectoire, sans modifier retroactivement les rapports STEP4.

Hypotheses : le surplus de torpilles/leurres est-il tactiquement utile ou depense
aveugle, et la coupure au premier mort masque-t-elle des kills posthumes capables
de changer le classement ? Budget propose : 80 trajectoires, plafond simule
600 s seulement si settling autorise, un plafond mural d'une heure, zero update
de poids. Critere diagnostique : rapport apparie complet, compteurs reconcilies
aux munitions, revue humaine des rejets/epuisements et changements d'issue ;
80 matchs ne sont pas un nouveau gate de promotion. Suspendre le plan long en
cas de source modifiee, mismatch inexplique ou sensibilite de classement au
contrat de fin ; conserver champions/configs, aucun ajustement opportuniste des
rewards. Restent aussi validation live humaine/navigateur/reseau et charge CPU
de production, qui ne sont pas remplacees par cette robustesse de suite.
