# Diagnostic Des 80 Duels

## Statut Et Autorisation

Campagne explicitement autorisee et terminee le 2026-09-10 : **80/80 matchs**,
deux processus exit 0, aucun entrainement lance par cet agent. L'autorisation
recente remplace les anciennes mentions interdisant cette evaluation et le
training ulterieur ; le parent reste responsable de ce dernier. Aucun serveur,
commit, deploiement, promotion ou remplacement de modele.

Sources ajoutees : `rl/diagnose_duels.py`, `rl/analyze_duel_diagnostics.py` et
leurs regressions. Aucun fichier Sim, controleur, reward, configuration ou
checkpoint modifie. Les changements sales STEP1/2/3 et autres sont preserves.

## Protocole

- V3 best et v4 best 300k, chacun contre autosub et le seul ZIP sub15 best gele.
- Exactement 20 graines 98000-98019 dans chacune des quatre cellules ; 80 matchs,
  40 paires modele/reference, mais seulement **20 graines distinctes**.
- `testCombats`, `aidest_v4.json`, rewards exactes, HP coque 200/100 et leurre 10.
- Spawn final 600-2000 m, sans curriculum, aucun self-play ; physique 0,05 s,
  frame_skip 5, politique recurrente deterministe CPU, etat recurrent par duel.
- Premier endpoint : premier tick contenant un naufrage natif, ou 6000 ticks
  (300 s). Un timeout sans mort reste nul : pas de combat supplementaire a 600 s.
- Si mort, continuation jusqu'a disparition des torpilles de TOUS les
  proprietaires initiaux coules, y compris les naufrages suivants ; plafond
  absolu 12000 ticks/600 s. Identite `(ownerPlayerId, tid)`, pas tid seul.
- Survivants conservant leurs controleurs natifs, aucune inference ni action
  pour les morts ; Sim continue aussi sans bateau vivant si une torpille attendue
  reste active. Pas d'attente specifique des grenades, obus, mines ou leurres.
- Initialisation via `SubmarineDuelEnv.reset`, puis vrais `build_observation`,
  `apply_action`, `HeadlessRunner.step` et Sim. Aucun moteur physique distinct,
  aucun appel `env.step` ou `_predict_opponent` apres disparition d'un acteur.
- Les semantiques de fin Gym/evaluation standard et les flags de penalite sont
  inchanges. Le runner diagnostique ne calcule pas une nouvelle reward.

## Resultats

W/L/D = victoires/defaites/nuls, 20 matchs par ligne ; score = W + 0,5 D.

| Modele | Adversaire | Premier W/L/D | Score | Apres settling W/L/D | Score |
|---|---|---:|---:|---:|---:|
| v3 | autosub | 9/0/11 | 72,50 % | 9/0/11 | 72,50 % |
| v3 | sub15 | 6/1/13 | 62,50 % | 4/1/15 | 57,50 % |
| v4 300k | autosub | 9/0/11 | 72,50 % | 9/0/11 | 72,50 % |
| v4 300k | sub15 | 12/0/8 | 80,00 % | 10/0/10 | 75,00 % |

Scores agreges 50/50 : **v3 67,50 -> 65,00 %**, **v4 76,25 -> 73,75 %**.
Gain apparie v4-v3 : **+8,75 points** aux deux endpoints ; IC normal 95 %
groupe par graine, covariance entre adversaires conservee :
premier `[-0,838 ; 18,338]`, settling `[-1,476 ; 18,976]` points.
Moyenner les deux differences adversaires par graine, puis utiliser
`mean(z) +/- 1,96 * stdev(z)/sqrt(20)`. Petit diagnostic post hoc, IC incluant
zero ; ni preuve autonome de superiorite ni nouveau gate de promotion.
Ne pas fusionner ces issues avec les anciennes regles ou les 1200 matchs STEP4.

**34 continuations**, aucune atteignant le plafond ; 3047,75 s simulees ajoutees.
Maximum : +387,15 s, fin a 461,40 s. Quatre W deviennent D, tous contre sub15 :
v3 graines 98001/98015, v4 98009/98016. Cela represente 4/36 victoires au premier
endpoint (11,11 %), pas 4 inversions W->L. Aucun changement d'issue autosub,
aucun changement de l'ecart agrege v4-v3 ; chaque modele perd 2,50 points.

## Armes Et Refus

Totaux AVANT le premier endpoint, 40 matchs par modele ; les refus incluent
les cooldowns sans flag `weapon_invalid` du destroyer.

| Mesure agent | v3 | v4 300k |
|---|---:|---:|
| Decisions | 31966 | 29826 |
| Demandes d'arme principale | 3837 | 11403 |
| Tirs effectifs | 106 | 550 |
| Refus effectifs | 3731 | 10853 |
| Flag penalise `weapon_invalid` | 2315 | 7383 |
| Refus cooldown, non penalises | 1416 | 3470 |
| Refus faute de contact canon/grenade | 2293 | 7076 |
| Refus cible immergee, canon | 22 | 212 |
| Refus stock vide, torpille acoustique | 0 | 95 |
| Refus portee | 0 | 0 |
| Torpilles acoustiques/autonomes | 1/8 | 373/59 |
| Torpilles blind/fresh/memory | 9/0/0 | 354/68/10 |
| Grenades fresh/memory | 90/7 | 108/10 |
| Canon | 0 | 0 |
| Mines suspendues | 2 | 1 |
| Leurres depenses | 280 | 594 |

V4 : **81,94 %** des 432 torpilles sont blind, soit 10,8 torpilles/episode
contre 0,225 pour v3. `blind` signifie aucun contact admissible au tir, pas
absence absolue d'historique sensoriel ; `fresh` utilise le flag de suivi natif,
pas l'egalite stricte du timestamp avec le tick courant. L'age du contact est trace.
Le tir blind reste legal avec activation/capteurs natifs : ce n'est pas un bug.

Apres settling, torpilles agent v3 **15**, v4 **501** ; grenades **98/118** ;
leurres **329/667** ; mines **3/1** ; toujours aucun canon. V4 ajoute 69 tirs
blind alors que l'adversaire est deja coule : activite tactiquement inutile pour
le duel, mais commande native du survivant, non neutralisee artificiellement.

### Adversaires Et Epuisement

| Adversaire face a | Torpilles acoustiques/autonomes | Leurres | Episodes stock acoustique/autonome vide |
|---|---:|---:|---:|
| autosub / v3 | 2/52 | 0 | 0/1 |
| autosub / v4 | 0/74 | 8 | 0/1 |
| sub15 / v3 | 259/112 | 77 | 7/6 |
| sub15 / v4 | 273/151 | 53 | 5/8 |

Ces stocks adverses ne changent pas pendant les continuations de cette campagne.
Sub15 fait respectivement **10226/9058 demandes**, **371/424 tirs**,
**9855/8634 refus**, dont **5168/5469 cooldowns** et **4687/3165 stocks vides**.
Ses torpilles blind/fresh/memory : **21/350/0** face a v3, **20/403/1** face a v4.
Autosub emet 51/72 autonomes fresh, 1/2 autonomes memory, plus 2/0 acoustiques
fresh. Les gates internes BT ne sont pas assimiles a des demandes RL : seuls
ses appels natifs de lancement sont traces, avec resultat et motif si rejet.

Agent v3 : aucun stock torpille vide ; leurres vides 1/40 aux deux endpoints.
Agent v4 : acoustiques vides **3/40 -> 4/40**, autonomes jamais ; leurres
vides **15/40 -> 20/40**. Grenades et mines jamais epuisees. Les stocks sont
captures AVANT leur suppression au naufrage : disparition de l'inventaire ne
compte jamais comme depense. Les nombres par type peuvent concerner le meme duel.

## Degats Reels

Sommes de pertes HP effectivement appliquees, limitees aux HP restants, pas
puissance nominale d'explosion ni simple variation nette de HP par decision.
Les enveloppes diagnostiques entourent les vraies explosions et collisions,
puis enregistrent `Sim.bot_apply_damage` sans changer arguments ou resultat.

| Degats agent -> ennemi, premier endpoint | v3 | v4 300k |
|---|---:|---:|
| Grenade | 1932,060 | 2177,084 |
| Torpille | 0 | 144,111 |
| Canon / mine | 0 / 0 | 0 / 0 |
| Total | 1932,060 | 2321,195 |

Ces totaux offensifs sont inchanges apres settling. **93,79 %** des degats
ennemis de v4 viennent des grenades, malgre ses nombreux tirs de torpilles.
Cela ne prouve pas que chaque tir blind est inutile : pas d'ablation causale,
ni attribution des degats par contexte blind/fresh, ni mesure d'effet dissuasif.
Les degats de leurres ne sont pas comptes comme degats de coque adverse.

Torpilles ennemies -> agent, premier puis settling :
v3 **949,762 -> 1435,487 HP**, v4 **952,152 -> 1323,897 HP**.
Auto-degats grenade v4 **39,513 -> 73,849 HP**, tous contre sub15 ; v3 zero.
Les evenements natifs et l'appel de degats distinguent explicitement ces
auto-degats des degats infliges a l'ennemi ; aucune attribution inconnue.

## Diagnostic Et Suite Unique

**Aucun nouveau blocage de justesse du gameplay confirme.** Le probleme de
cycle de vie d'un `env.step` apres fin est evite dans le runner dedie, pas
"corrige" en modifiant les terminaisons standard. Les flags destroyer ignorent
les refus cooldown alors que ceux du sous-marin les penalisent : asymetrie
existante maintenant mesuree, conservee pour respecter la semantique demandee.
Il serait incorrect d'appeler le seul compteur `weapon_invalid` tous les refus.

Les tirs blind massifs, demandes de grenades sans contact, consommation de
leurres et tirs apres mort adverse sont des comportements appris sous regles
changees, pas une preuve de contournement physique. La majorite des degats
restent dus aux grenades ; pas de justification mesuree pour une nouvelle
penalite speculative de torpille ou un masquage d'action.

**Recommandation au parent : seule dimension majeure = warm-start v4 best
300k plutot que v3 pour une adaptation aux regles courantes.** Le signal +8,75
points est coherent avec STEP4 (+8,50), sans gain autosub sur ces 20 graines ;
le settling ne change pas la preference. Ce choix n'est pas une promotion.

Proposition de run neuf `aidest_v5_rules_scripted`, **~2M nouvelles decisions**,
seed **1542**, depuis le ZIP v4 hash ci-dessous. Garder exactement les rewards,
architectures, LR 0,00005, entropie 0,003 -> 0,0003, timing premier mort/300 s,
spawn/curriculum et melange autosub/sub15 50/50 du v4 scripted. Aucun self-play
nouveau, aucun changement simultane de settling, LR, capteurs ou balance.
Le seed neuf et le budget sont des parametres d'execution ; un seul run ne
permettra pas d'estimer causalement l'effet du warm-start.

Evaluer avant apprentissage pour conserver la baseline initiale ; conserver
checkpoints 250k et evaluations 100k, references v3 et v4 intouchables, sortie
neuve uniquement. Examiner aussi le settling dans les controles diagnostiques,
sans le confondre avec le score de selection standard. Le parent choisira des
graines de validation disjointes de 96000/97000/98000 ; ne pas recycler ces 20
graines comme gate independant. Entrainement ulterieur autorise au parent,
**non lance ici** ; pas de promotion automatique ni d'ecrasement du best initial.

## Tracabilite Et Verification

Archive ignoree :
`rl/models_rl/aidest_v4_scripted/evaluation/diagnostic80_98000/` (6,4 Mio).
Deux sous-repertoires v3/v4 : `launch.json`, `results.json`, 40 JSONL gzip chacun,
`sources.tar.gz`, diff sale/stage, statut, HEAD, dependances. `analysis.json`
reconcilie les **101801 decisions RL**, tous les evenements et les degats des
80 traces avec les resultats ; valide les graines, issues, limites, absence
d'inference apres naufrage et egalite exacte des spawns/rotations/HP apparies.

**79 entrees SHA-256 par job inchangees** au terme du job et lors de l'analyse :
code racine/RL, cartes, bateaux, BT, configs et tous les ZIP best presents.
Pas de verrou filesystem. Le hash de HEAD seul ne represente pas le code sale.
Les scripts d'analyse et le test de parite ajoutes apres lancement n'ont pas
modifie les sources de simulation archivees.

| Entree | SHA-256 |
|---|---|
| v3 best | `103481713271ed04cf03007f1468898e6b4c928214c12f28ecd90fabfc5066c2` |
| v4 best 300k | `90c08a62b551f77f23a90194bb7876841df7cf7a9c50987141c3257aa16ca8e2` |
| sub15 best | `2849f0c79a15fced51a249720bd25bd4210ee1bafc4c71f79aa942dfaab421c5` |
| aidest_v4.json | `38e16186ca860bc589209ac9051ef212b50b0c284b82d29a1570ec907a7c7fdc` |
| testCombats | `78a7875d165691c81cdaae565308ec5f30924a745dae73bc2a9dd3eeb8c7ae9a` |
| destroyer | `067c0f7dd08660ee854c2804aef6ffe9f7d044c484aeb426668aae9d623f87d2` |
| submarine | `3f2bc0842dab848dcfa91edac6cb6d8b6d021c9998abcf0ff8ff293c17aec370` |
| autosub | `e247ab2be8624b01ceb9471d1a95eec7340a60c16f233a8a33c234acbd8db85d` |

CPU : `OMP_NUM_THREADS=MKL_NUM_THREADS=OPENBLAS_NUM_THREADS=1`, deux jobs
paralleles seulement, NLWP observe **1** pour chacun ; RSS observe 697768/696512
Kio, ~99 % CPU chacun. Durees v3 **104,209 s**, v4 **141,721 s**, sorties 0.
Python dynamique reseme par duel via HeadlessRunner ; RNG prive de spawn,
Python/NumPy/Torch preserves autour du duel et des chargements de modeles.
Politiques deterministes, pas de CUDA ; meme graine n'implique pas memes tirages
de combat apres divergence des actions. Pas de parite navigateur/reseau prouvee.

Trace serveur existante lue, sans serveur lance : `logs/game_trace.jsonl`,
session `151295e7462e4705b8c05ef162de8cfe`, metadata seq2, premiere RLDecision
seq379/tick1. Meme triplet observation/action/result et evenements natifs ; le
format hors ligne est explicitement distinct du schema serveur 1.

Regressions : **252 tests passes** lors de la verification finale, dont le test
de parite observation/action/stock/endpoint avec `env.step` standard. Compilation
Python ciblee et `git diff --check` passes. Tests de continuation
posthume, nul, compte exact de degats, stock au naufrage et timeout inclus.
Reproduction de l'analyse, sans rejouer les duels ni modifier les artefacts :

```bash
venv/bin/python -m rl.analyze_duel_diagnostics \
  rl/models_rl/aidest_v4_scripted/evaluation/diagnostic80_98000
```
