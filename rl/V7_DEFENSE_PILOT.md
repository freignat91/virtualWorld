# Pilote V7 defense

## Bilan final phase4/phase5

Le cinquieme palier est termine a106496 nouveaux pas en15min14, le10 septembre
2026 a22:15:46+02:00. L'entrainement planifie v7 est acheve et aucun processus
ne reste. Selection interne phase5 : deterministe34,167 % (0V/19D/41N), sampled
76,944 % (118V/21D/41N),7657 tentatives d'arme invalides et zero mine.

La comparaison finale utilise320 duels, graines fraiches200000-200019, avec le
meme protocole apparie que les comparaisons precedentes.

| Candidat/mode | Matchs | Score premier | Score apres settling |
|---|---:|---:|---:|
| Phase4 deterministe |40|46,25 %|42,50 %|
| Phase5 deterministe |40|32,50 %|32,50 %|
| Phase4 echantillonne |120|80,00 %|75,833 %|
| Phase5 echantillonne |120|80,417 %|76,667 %|

Ecarts phase5-phase4, IC normaux95 % sur20 groupes :

- deterministe first : -13,75 points [-22,068 ;-5,432] ;
- deterministe settled : **-10,00 [-15,507 ;-4,493]** ;
- sampled first : +0,417 [-4,537 ;5,370] ;
- sampled settled : +0,833 [-4,318 ;5,985].

Phase5 degrade donc le mode deterministe de facon nette, sans gain sampled
etabli. Elle reduit toutefois les tentatives invalides sampled : armes44,333->
39,917/duel et leurres164,708->78,125/duel, avec des tirs stables28,942->28,967.
Zero mine, aucun plafond de settling et158 continuations.

Huit jobs CPU mono-thread exit0,124 empreintes inchangees chacun,320 traces et
sept validations croisees reussies. Archive68MiB :
`models_rl/aidest_v7_defense_continue4_seed8542_final100k/evaluation/independent_200000/`.

Le runtime standard utilise `deterministic=True`. Le checkpoint final recommande
pour d'eventuelles evaluations supplementaires est donc **phase4-100k**, SHA256
`9a513b31a9237fa2a67be9f2aa65a93beabf2e3a6bfd5d20fe60b4f6df35ad4d`.
Il n'est pas promu : sur ce dernier lot deterministe, il finit0V/6D/34N apres
settling et reste principalement defensif. Aucune copie vers la production,
continuation, execution live, deployment ou commit n'a ete effectuee.

Checkpoint/best/best-sampled phase5 partagent le meme payload de poids ; son
`policy_final.zip` a106496 est distinct et non evalue.293 entrees hors cinq docs
de statut et les196 ZIP preexistants sont inchanges apres completion.

## Cinquieme palier final actif

Le run `aidest_v7_defense_continue4_seed8542_final100k` est actif depuis le10
septembre2026 a22:00:12+02:00, PID304338, workers304358-304365, CUDA. Il charge
le checkpoint phase4 selectionne/evalue, SHA256 ZIP `9a513b31...`, avec poids et
optimiseur a100k.

Cette phase utilise la graine8542 et les100k pas restants.106496 nouveaux pas
sont attendus par rollouts complets. Entropie reprise a0.000975 puis achevee a
0.0003 ; curriculum termine/desactive. Double evaluation interne a100k.

Verification a24576 pas :548 FPS cumules, optimiseur fini, KL0.0075392537,
loss0.00464, value_loss0.497 et explained_variance0.29 finies. Les298 entrees,
dont196 ZIP, restent inchangees apres lancement avant docs.15 tests cibles et la
comparaison independante precedente320 duels sont valides. Log :
`/tmp/virtualWorld_aidest_v7_defense_continue4_seed8542_final100k.log`.
Ne pas dupliquer/tuer. Aucune phase supplementaire, reevaluation independante ou
promotion n'est automatique apres la fin.

## Comparaison independante phase3/phase4

La comparaison sur320 duels, graines fraiches190000-190019, reprend exactement
le protocole precedent : autosub/sub15,40 matchs deterministes et120 sampled par
checkpoint, trois graines d'actions, situations initiales appariees, premier
endpoint300s et settling des torpilles jusqu'a600s.

| Candidat/mode | Matchs | Score premier | Score apres settling |
|---|---:|---:|---:|
| Phase3 deterministe |40|36,25 %|36,25 %|
| Phase4 deterministe |40|47,50 %|45,00 %|
| Phase3 echantillonne |120|77,083 %|74,167 %|
| Phase4 echantillonne |120|72,917 %|70,417 %|

Ecarts phase4-phase3, IC normaux95 % sur20 groupes de graines :

- deterministe first : +11,25 points [2,932 ;19,568] ;
- deterministe settled : +8,75 [3,388 ;14,112] ;
- sampled first : -4,167 [-9,263 ;0,930] ;
- sampled settled : -3,75 [-8,843 ;1,343].

La baisse d'entropie a donc nettement renforce la sortie deterministe, avec
phase4 settled1V/5D/34N contre phase3 0V/11D/29N. Le sampled baisse, mais son IC
recouvre zero : aucune degradation demontree sur ce lot. Ses tentatives d'arme
invalides montent legerement37,467->40,45/duel, les tirs baissent30->27,967 et les
leurres invalides baissent169,7->161,167. Zero mine et aucun plafond de settling ;
165 continuations.

Huit jobs CPU mono-thread exit0,121 empreintes inchangees chacun,320 traces et
sept validations croisees reussies. Archive71MiB :
`models_rl/aidest_v7_defense_continue3_seed7542_review100k/evaluation/independent_190000/`.

Conclusion : phase4 est le meilleur checkpoint deterministe v7 teste, mais reste
surtout defensif. Le dernier palier planifie de100k est defensable pour achever
la decroissance d'entropie ; il exige encore une autorisation explicite.

## Quatrieme palier termine

Phase4 terminee a106496 nouveaux pas en14min29 le10 septembre2026 a21:40:29,
sans processus restant. Selection interne : deterministe41,667 % (2V/12D/46N),
sampled79,722 % (124V/17D/39N),7907 tentatives d'arme invalides, zero mine.
Checkpoint/best/best-sampled partagent le meme payload ; final106496 distinct et
non evalue.288 entrees hors cinq docs et les192 ZIP preexistants sont inchanges.

## Quatrieme palier actif

Le run `aidest_v7_defense_continue3_seed7542_review100k` est actif depuis le10
septembre2026 a21:25:41+02:00, PID300707, workers300727-300734, CUDA. Il charge
le checkpoint phase3 selectionne/evalue, SHA256 ZIP `3a0438b...`, avec poids et
optimiseur a100k.

La phase utilise la graine7542 et represente les200k pas restants. Elle s'arrete
pour revue apres100k demandes/106496 reels attendus. Entropie reprise a0.00165
vers0.0003 sur200k ; curriculum acheve et desactive. Double evaluation a100k.

Verification a24576 nouveaux pas :558 FPS cumules, optimiseur fini, KL0.008496623,
loss-0.0082, value_loss0.306 et explained_variance0.922 finies. Les293 entrees
archivees, dont192 ZIP, restent inchangees apres lancement avant docs.15 tests
cibles passent ; comparaison independante precedente320 duels validee. Log :
`/tmp/virtualWorld_aidest_v7_defense_continue3_seed7542_review100k.log`.
Ne pas dupliquer/tuer ou continuer automatiquement apres revue.

## Comparaison independante phase2/phase3

La comparaison demandee est terminee sur320 duels uniques, graines de scenario
fraiches180000-180019, autosub/sub15, conditions initiales appariees. Pour chaque
checkpoint :40 matchs deterministes et120 echantillonnes avec graines d'action
`seed`, `seed+1M`, `seed+2M`. Le premier endpoint est a300s ; les torpilles des
proprietaires coules sont reglees jusqu'a600s.

| Candidat/mode | Matchs | Score premier | Score apres settling |
|---|---:|---:|---:|
| Phase2 deterministe |40|27,50 %|27,50 %|
| Phase3 deterministe |40|35,00 %|35,00 %|
| Phase2 echantillonne |120|75,833 %|72,50 %|
| Phase3 echantillonne |120|77,917 %|78,333 %|

Ecarts phase3-phase2, IC normaux95 % calcules sur20 groupes de graines apres
moyenne des adversaires et, en mode echantillonne, des trois repetitions :

- deterministe first/settled : +7,50 points [0,302 ;14,698] ;
- echantillonne first : +2,083 [-3,827 ;7,993] ;
- echantillonne settled : +5,833 [0,016 ;11,650].

Le resultat settled echantillonne soutient un gain sur ce lot independant, mais
la borne basse est presque nulle. Le deterministe reduit les defaites sans gagner
un seul match : phase2 0V/18D/22N, phase3 0V/12D/28N. Il reste impropre a une
promotion deterministe.

En echantillonne avant le premier endpoint, les tentatives d'arme invalides
baissent de93,817 a33,05 par duel (-64,8 %), pour un nombre de tirs presque stable
29,525 contre28,883. Les leurres invalides baissent de196,217 a161,667 par duel.
Aucune mine, aucun plafond de settling ;198 matchs ont une continuation.

Huit jobs CPU mono-thread terminent avec code0,40 matchs et118 empreintes
inchangees chacun. Les320 traces sont validees integralement par sept analyses
croisees. Archive80MiB :
`models_rl/aidest_v7_defense_continue2_seed6542_review100k/evaluation/independent_180000/`.

Conclusion : l'evaluation interne phase3 a sous-estime le checkpoint sur ses
graines. La comparaison independante favorise phase3 et la forte baisse des
actions invalides rend un nouveau palier100k defensable, mais aucune promotion
ou continuation n'est automatique.

## Troisieme palier termine

Le troisieme palier s'est termine a106496 nouveaux pas en16min41 le10 septembre
2026 a21:06:11+02:00. Aucun processus ne reste. Selection interne100k :
deterministe34,167 % (0V/19D/41N), echantillonnee73,056 % (104V/21D/55N),8389
tentatives d'arme invalides et zero mine. Checkpoint/best/best-sampled ont le
meme payload de poids ; final106496 distinct et non evalue.283 entrees hors cinq
docs de statut et les188 ZIP preexistants sont inchanges apres completion.

## Troisieme palier actif

Le run `aidest_v7_defense_continue2_seed6542_review100k` est actif depuis le10
septembre2026 a20:49:11+02:00, PID296452, workers296472-296479, CUDA. Il charge
le checkpoint selectionne a100k du deuxieme palier, SHA256 ZIP
`f3148eab8df6b57c05363a08cbbf5fab5881a70c1d99d423693e24c371a0a3e1`, avec
poids et optimiseur.

La nouvelle phase utilise la graine6542 et represente les300k pas restants. Elle
s'arrete pour revue apres100k demandes, soit106496 nouveaux pas attendus. Pour
ne pas recommencer les calendriers, l'entropie part de0.002325 vers0.0003 sur
300k et le curriculum deja acheve reste desactive. Evaluation double a100k.

Verification a16384 nouveaux pas :575 FPS cumules, premier optimiseur fini,
KL0.005891783, loss0.0658, value_loss0.748 et explained_variance0.733 finies.
Les288 entrees archivees, dont188 ZIP, sont inchangees apres lancement avant ces
docs ;15 tests cibles passent. Log :
`/tmp/virtualWorld_aidest_v7_defense_continue2_seed6542_review100k.log`.
Ne pas dupliquer/tuer ou continuer automatiquement apres revue.

## Deuxieme palier termine

Le deuxieme palier a termine106496 nouveaux pas en15min20, sans processus
restant. Selection interne100k : deterministe33,333 % (0V/20D/40N,60) et
echantillonnee81,389 % (130V/17D/33N,180). Le mode echantillonne compte5150 tirs,
16721 tentatives d'arme invalides et3256 leurres ; aucune mine. Les tentatives
invalides baissent de43,1 % face au premier palier, mais le deterministe reste
faible et sans leurre. Checkpoint et deux best ont le meme payload de poids ;
final106496 distinct/non evalue.278 entrees hors5 docs de statut et les184 ZIP
preexistants sont inchanges. Ces scores restent internes et non promotionnels.

## Deuxieme palier actif

Continuation explicitement autorisee sous forme de nouvelle phase warm-start.
Le run `aidest_v7_defense_continue_seed5542_review100k` a demarre le10 septembre
2026 a20:28:54+02:00, PID294428, avec huit workers294449-294456 et CUDA.

- source immuable : `checkpoints/policy_100000_steps.zip` du premier pilote ;
- SHA256 source : `41c5fa5d0f260130ad6edcf66559706f2303ee38829b98505e83e5abcf5ac2e5` ;
- poids et optimiseur charges a100000 pas, nouvelle graine5542 ;
- horizon de nouvelle phase400000, mais arret de revue apres100000 demandes ;
-106496 nouveaux pas attendus par rollouts complets ;
- curriculum et entropie repartent au debut de leur nouvelle phase ;
- double evaluation interne a100000 nouveaux pas.

Verification a24576 nouveaux pas :559 FPS cumules, premier optimiseur fini,
KL0.0056987912, loss0.15, value_loss0.828 et explained_variance0.294 finies.
Les283 entrees archivees, dont184 ZIP, sont inchangees apres le demarrage avant
la mise a jour de ces documents.15 tests cibles passent ; les275 tests complets
du premier palier restent la derniere verification large. Log :
`/tmp/virtualWorld_aidest_v7_defense_continue_seed5542_review100k.log`.

Ne pas dupliquer ou interrompre le processus sain. Aucune continuation apres ce
nouveau seuil, evaluation independante, promotion, execution live, deployment
ou commit n'est automatiquement autorise.

## Statut

Le premier palier du run `aidest_v7_defense_seed4542_review100k` est termine.
Il a commence le10 septembre2026 a19:59:34+02:00 et produit son artefact final
a20:16:10. Aucun processus d'entrainement ne reste actif.

- modele neuf, sans checkpoint source ;
- graine4542, CUDA, huit environnements ;
- `destroyer_duel_v3`,101 observations et5 composantes d'action sans mine ;
-106496 pas reels pour100000 demandes, par rollouts complets ;
- temps affiche par l'entraineur :16min14s.

## Evaluation interne a100k

La selection deterministe couvre60 matchs :

-1 victoire,19 defaites et40 nuls ;
- score35 % ;
- autosub38,333 %, aisub_v15 fige31,667 % ;
-11 armes tirees, aucune tentative d'arme invalide, aucun leurre et un sonar ;
- aucune mine.

La selection echantillonnee couvre180 matchs, soit30 situations pour chacun des
deux adversaires et des offsets d'action0,1000000 et2000000 :

-108 victoires,18 defaites et54 nuls ;
- score75 % ;
- autosub80 %, aisub_v15 fige70 % ;
-5391 armes tirees,29373 tentatives d'arme invalides,3294 leurres et1116 sonars ;
- aucune mine.

Le contraste35/75 % indique que la politique deterministe s'est presque figee
sur l'inaction tandis que l'echantillonnage exploite deja des actions utiles. Le
taux tres eleve de tentatives invalides montre toutefois que la politique reste
immature. Ces scores de selection internes ne constituent ni une comparaison
independante, ni une preuve de robustesse, ni un motif de promotion.

## Artefacts et integrite

`checkpoints/policy_100000_steps.zip`, `best/best_model.zip` et
`sampled/best/best_model.zip` ont le meme contenu de poids et d'optimiseur ;
leurs SHA ZIP different seulement a cause de l'emballage. Le SHA256 du payload
`policy.pth` selectionne est
`98879f0437aa8b1a26c2ab81de20894d8c3bc83e547e649b34e11c7be6722d81`.

`policy_final.zip` est distinct apres la derniere optimisation a106496 pas et
n'a pas ete evalue. Son SHA256 ZIP est
`1dba37d41da4331bdbb7f2d8d622f36a3bbee7ed424d7e18c8ba074ba51a532e`.
L'archive ZIP est valide.

Apres la fin,273 des277 entrees de lancement sont verifiees inchangees. Les
quatre exceptions sont uniquement les documents de statut modifies apres le
demarrage. Les180 ZIP de modeles preexistants font partie des entrees inchangees.

## Decision requise

Aucune continuation, comparaison independante, promotion, modification de
recompense, execution live, deployment ou commit n'a ete lance. Le prochain
choix doit etre explicite : prolonger le meme run vers le prochain palier, ou
figer ce pilote et mener d'abord une evaluation independante ciblee.
