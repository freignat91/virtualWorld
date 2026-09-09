# Entraînement des bots RL

Ce document décrit le pipeline de reinforcement learning de Virtual World, de
la simulation headless au chargement d'une politique dans le serveur live.

## Principes

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

`--resume` charge les poids et réapplique les paramètres scalaires de la nouvelle
configuration. `n_steps`, `batch_size`, l'observation et l'action doivent rester
compatibles.

```bash
.venv/bin/python -m rl.train_ai --config rl/configs/aidest_v2.json \
  --stage scripted --run-name aidest_v2_scripted \
  --resume rl/models_rl/aidest_v1_scripted/best/best_model.zip --device cuda
```

Le compteur d'étapes repart de zéro dans le nouveau run. Une interface modifiée,
comme le passage de `destroyer_duel_v1` à `destroyer_duel_v2`, nécessite un
nouveau modèle.

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
