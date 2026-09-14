# Pilotes de comportement RL

## Etat au 11 septembre 2026

Le pipeline mesure maintenant, sans modifier les regles de jeu, le contexte au
moment d'un tir RL : acquisition exploitable, age du contact, erreur angulaire,
tir sans acquisition et tir acquis hors cone. Les rapports ajoutent les taux de
tirs sans acquisition, de tirs desalignes, de demandes d'arme invalides,
d'immobilite et d'episodes sans tir. Des `behavior_gates` optionnels peuvent
empecher la selection `best` meme si le score de match augmente. Les anciennes
configs restent neutres : les trois nouvelles recompenses valent `0.0` par
defaut.

Deux configs isolees sont preparees :

- `configs/aisub_v16_acquisition.json` ajoute seulement une recompense de
  `-0.1` par tir sans acquisition exploitable, warm-start v15 ;
- `configs/aidest_v8_mobility.json` ajoute seulement `-0.002` par decision a
  vitesse nulle sans contact frais ni menace, warm-start v7 phase4.

Depuis le 12 septembre, le runtime humain, BT et RL exige une cible selectionnee
pour lancer une torpille ; les resultats ci-dessous conservent l'ancienne regle.
Les schemas d'observation et d'action restent inchanges.

## Pilote v16 termine

Run `aisub_v16_acquisition_seed9542_pilot100k`, warm-start de
`models_rl/aisub_v15_scripted/best/best_model.zip`, SHA256
`2849f0c79a15fced51a249720bd25bd4210ee1bafc4c71f79aa942dfaab421c5`.
Graine9542, CUDA,8 environnements, entropie v15 conservee a0.001,106496 pas
reels en11min00. Le processus a termine avec exit0 ; aucun processus
d'entrainement ou d'evaluation ne reste.

Evaluation interne deterministe :180 combats,60 contre autosub,60 contre
autodest et60 contre le pool fige aidest-v3, graine109542. Score pondere
33,958 %, tirs non acquis25,028 %, tirs acquis desalignes93,321 %, demandes
d'arme invalides94,684 %,11,679 tirs acquis/episode et15,833 % d'episodes sans
tir. Les gates acquisition5 %, desalignement25 % et invalides50 % echouent ;
aucun `best_model` n'a ete selectionne.

Checkpoint100k SHA256
`4a7919c0d2f99dbd1d4eb766368d66854f8bdcb9eccafea1fd78aad989f295cd` ;
`policy_final.zip` est distinct, SHA256
`4d8e63365f5bf287bc9041a1f470da35be091875781312231a459f426908371d`.

## Comparaison v15 sur les memes situations

Le checkpoint source v15 a ete rejoue avec les memes cartes, adversaires,
60 episodes par groupe et graine109542. Score pondere33,542 %, tirs non acquis
28,081 %, tirs acquis desalignes89,067 %, demandes invalides93,143 %,11,929
tirs acquis/episode et17,083 % d'episodes sans tir.

Le pilote v16 change donc le score de seulement +0,417 point et les tirs non
acquis de -3,053 points, mais degrade le desalignement de +4,254 points, les
demandes invalides de +1,541 point et les tirs acquis de -0,25/episode. Les
resultats candidat ne contiennent pas les episodes individuels : cette lecture
agregee sur memes graines ne fournit ni IC paire ni preuve d'amelioration.

Les rapports source sont archives sous
`models_rl/aisub_v16_acquisition_seed9542_pilot100k/evaluation/`.

## Decision

Apres l'echec v16, le user a choisi un renforcement isole de la meme recompense.
`configs/aisub_v16b_acquisition_strong.json` conserve source, graine,
hyperparametres, protocole et gates de v16 ; seule la penalite passe de-0.1 a
-0.5.

Le run `aisub_v16b_acquisition_strong_seed9542_pilot100k` a termine106496 pas
en10min57 avec exit0. Sur les memes180 situations, son score est32,083 %, ses
tirs non acquis15,759 %, ses tirs acquis desalignes90,381 %, ses demandes
invalides93,839 %, ses tirs acquis12,088/episode et ses episodes sans tir
18,333 %. Face a v15, cela donne -1,458 point de score et -12,322 points de tirs
non acquis, mais encore +1,315 point de desalignement et +0,696 point de demandes
invalides. Les gates5/25/50 % echouent encore et aucun `best_model` n'est cree.

Checkpoint100k v16b SHA256
`a4c426bf27aa4066e408222a4d63329579d69a4ea088993a9e366817a9902344` ; final
distinct SHA256
`705006628e10d4a7df4919fe26acbd7f53f5d9a5ef85ab49fbf7705e621a034f`.

v16 et v16b echouent les criteres de comportement et ne doivent etre ni promus
ni continues automatiquement. Le pilote v8 est prepare mais n'a pas ete lance,
car le plan impose de valider le premier axe avant d'engager le suivant. Une
nouvelle iteration doit etre explicitement choisie ; augmenter encore la meme
penalite n'est pas soutenu par le compromis comportement/score observe.

Verification :47 tests cibles, puis278 tests complets, puis le test de creation
des deux environnements pilotes passent. `git diff --check` passe. Aucun serveur,
live, deploiement, promotion, commit ou sous-agent.
