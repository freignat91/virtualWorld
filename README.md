# Virtual World

Virtual World est un jeu multijoueur temps réel de combat naval et sous-marin.
Un serveur Python autoritaire arbitre la navigation, les capteurs, les armes et
les dégâts, tandis qu'un client BabylonJS assure l'affichage 3D et transmet
uniquement les intentions des joueurs.
Il sert de base à la crétion de bot IA (sous-marin et destroyer) qui sont entrainés sur le jeu pour devenir des adversaires les plus redoutables possible.

Le projet prend en charge :

- les sous-marins et les destroyers ;
- les torpilles acoustiques et autonomes, le canon, les grenades, les mines et
  les leurres ;
- les sonars actifs et passifs, les balises, les drones et les thermoclines ;
- les équipes, les bots à Behavior Trees et les politiques RL récurrentes ;
- l'entraînement headless, l'évaluation reproductible et le self-play.

## Architecture

```text
Navigateur BabylonJS
        |
        | intentions Socket.IO
        v
server.py (Flask + Flask-SocketIO + eventlet)
        |
        v
simulation.py (état et règles autoritaires)
        ^
        |
  bots BT / bots RL
```

La simulation principale vit dans `simulation.py` et ne dépend ni de Flask ni
de Socket.IO. `headless.py` la réutilise directement pour les entraînements RL,
ce qui garantit que les bots apprennent avec les mêmes règles que le serveur.

## Prérequis

- Linux recommandé ;
- Python 3.10 ou plus récent ;
- OpenSSL pour générer un certificat de développement ;
- un navigateur compatible WebGL ;
- une carte NVIDIA et CUDA sont recommandées, mais facultatives pour le RL.

## Installation

```bash
git clone https://github.com/freignat91/virtualWorld.git
cd virtualWorld
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 365 \
  -subj "/CN=localhost"
```

Les certificats sont locaux et exclus de Git.

## Lancement

```bash
./start.sh
```

Le serveur écoute par défaut sur `https://localhost:7000`. Le navigateur peut
demander de confirmer le certificat auto-signé lors de la première connexion.

Options utiles :

```bash
./start.sh --map combats --port 7000 --maxPlayer 10
```

- `--map` charge `maps/world_<nom>.json` ;
- `--port` remplace le port de `config/conffile.json` ;
- `--maxPlayer` fixe le nombre maximal de joueurs humains.

Pour arrêter le serveur :

```bash
./stop.sh
```

Les journaux du serveur sont écrits dans `logs/server.log` avec rotation.

## Mise à jour d'un serveur

Le script `update_server.sh` est conçu pour être lancé depuis la machine cible.
Il met à jour la branche `main`, récupère par SSH les meilleurs modèles RL depuis
la machine d'entraînement, vérifie leurs archives et les installe dans
`models_rl/` :

```bash
./update_server.sh
```

La source par défaut est
`francois@192.168.1.20:/data/dev/opencode/virtualWorld`. La machine et le chemin
peuvent être remplacés avec
`./update_server.sh utilisateur@machine /autre/chemin`. La connexion SSH de la
cible vers la source doit être configurée. Le dépôt cible doit être sans
modification suivie. Après la copie, redémarrer le serveur pour charger le
nouveau code et vider le cache des modèles RL.

## Tests

```bash
.venv/bin/python -m unittest test_rl_pipeline.py
.venv/bin/python -m py_compile \
  server.py simulation.py headless.py rl_control.py rl_env.py train_ai.py evaluate_ai.py
```

Le dépôt ne possède pas encore de suite de tests navigateur automatisée. Les
changements graphiques doivent être vérifiés manuellement sur laptop ou desktop.

## Entraînement des bots

Le pipeline utilise Gymnasium, Stable-Baselines3 et `RecurrentPPO` de
SB3-Contrib. Les modèles peuvent affronter des Behavior Trees, une politique
gelée ou une ligue de snapshots historiques.

Consulter [TRAINING_RL.md](TRAINING_RL.md) pour :

- comprendre les observations, les actions et les récompenses ;
- lancer une phase scripted ou self-play ;
- suivre les checkpoints et TensorBoard ;
- comparer les politiques sur des graines identiques ;
- charger un bot RL dans le serveur live.

Les modèles et sorties d'entraînement vivent dans `models_rl/` et sont exclus de
Git en raison de leur taille.

## Structure du dépôt

| Chemin | Rôle |
|---|---|
| `server.py` | Réseau, sessions, intents et boucle serveur |
| `simulation.py` | Physique et règles autoritaires sans dépendance Flask |
| `events.py` | Événements typés produits par la simulation |
| `headless.py` | Adaptateur de simulation pour tests et RL |
| `bot_ai.py` | Moteur de Behavior Trees |
| `bots/ai/` | Définitions JSON des comportements |
| `rl_control.py` | Observations et actions des politiques RL |
| `rl_env.py` | Environnement Gymnasium de duel |
| `train_ai.py` | Entraînement scripted et self-play |
| `evaluate_ai.py` | Évaluation contre BT ou checkpoints RL |
| `rl_runtime.py` | Chargement des politiques dans le serveur |
| `configs/` | Configurations d'entraînement |
| `boats/` | Caractéristiques des navires |
| `maps/` | Cartes et graphes de navigation |
| `static/game.js` | Client BabylonJS |

## Documentation

- [Architecture et règles techniques](TECHNIQUE.md)
- [Entraînement des bots RL](TRAINING_RL.md)

## Licence

Aucune licence de redistribution n'est actuellement publiée dans ce dépôt.
