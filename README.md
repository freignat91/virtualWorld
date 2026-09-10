# Virtual World

## Tir De Torpille Sans Cible

Sans selection, cliquez sur une torpille puis recliquez sur le meme bouton pour
tirer dans l'axe du bateau, a sa profondeur de lancement habituelle, sans cible
acquise. Entre les deux clics, le radar permet toujours de viser un point fixe ;
ESC annule. Acoustiques et autonomes ne cherchent une cible qu'apres la distance
d'activation ; la filoguidee conserve ses commandes manuelles et sa limite d'une
torpille controlee. Les tirs restent soumis aux munitions et a la portee native.
Les actions RL peuvent maintenant consommer des torpilles sans contact : scores
historiques non directement comparables, modeles et rewards inchanges.

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

## Corrections Ciblees D'Equite (2026-09-09)

- Etape 2 canon : humains/BT/RL utilisent une parabole autoritaire vers un point
  copie, sans degats garantis par ID; mouvement, plongee et iles peuvent faire
  manquer le tir, et une autre coque (meme alliee) peut recevoir les 30 points.
  Vitesse/arc/dispersion historiques conserves, impacts natifs et trace des obus;
  DCA distincte inchangee. Voir `TECHNIQUE.md`, `test_cannon_ballistics.py` et
  `tests/test_cannon_ballistics.js` pour geometrie approximative et limites.
  Shapes RL/modeles inchanges, combat modifie : scores historiques non comparables.
  Aucun serveur live, train/eval, deploiement, modele ou commit dans cette etape.

- Le pilotage BT bloque les segments traversant/touchant une ile et les arrivees
  sur ile ou hors limites, sans deplacement horizontal et avec vitesse nulle ;
  la recuperation de waypoint existante reste presente, sans teleportation.
- Les torpilles bots acoustiques/autonomes partent dans le cap du bateau, puis
  suivent leur point observe et leurs capteurs avec le rayon de virage normal.
- Les etiquettes torpilles affichent **Point de référence**, pas une acquisition
  deduite de `tx/tz` ; les cercles restent des distances d'activation, pas de verrou.
- Etape 1 sonar BT : meme onde autoritaire que RL (portee en 5 s, revelation
  10 s apres acquisition), plus de detection/tir immediat par le seul ping.
  Coordonnees et date figees derriere une ile ; cooldowns BT 10/20 s conserves.
  Schemas/modeles inchanges, semantique modifiee ; tests `test_bt_sonar.py`.

Scores historiques non directement comparables. Equite globale non prouvee :
canonisation serveur du sonar humain et validation globale restent a traiter, ainsi que
l'offset de lancement (bots 4 m, humain 15 m) et les profondeurs de depart.
Pitch initial nul inchange. Aucun serveur, evaluation, entrainement, deploiement
ou modele lance/modifie. Details et regressions : `TECHNIQUE.md`, `rl/AUDIT_FOLLOWUP.md`.

## Torpilles Et Limites De Carte

Les torpilles acoustiques, autonomes et filoguidees sont supprimees par la
simulation lorsqu'elles sortent du rectangle centre `ground.width/depth` :
arret au premier bord franchi, sans explosion ni degats de sortie, sans rebond.
Les collisions dans la carte, bord inclus, restent actives avant suppression ;
la portee maximale peut arreter le trajet plus tot. La trace native indique
`TorpedoDead.reason = map_bounds` et le filoguidage est libere.
Changement source pour la prochaine session apres redemarrage autorise seulement :
aucun serveur en cours redemarre, aucune partie en cours mise a jour.
Les etiquettes UI sont corrigees dans la tranche distincte decrite ci-dessus.

## Observer Une Partie

Sur l'accueil, cliquer **Observer la partie**, sans choisir de bateau ni d'equipe.
Acces direct : `/?spectate=1` sur le serveur deja lance. Le spectateur ne cree
aucune unite, ne prend aucun slot humain et ne change pas le scenario autogame.

- Vue joueur sur le premier bateau de la liste initiale : suivi 3D, bouton **Zoom** pour la vue embarquee, profondeur/eau/visibilite du bateau observe.
- **Changer unite** (bouton Unites existant), Tab / Shift-Tab : parcourir tous les bateaux presents, humains et bots, allies et ennemis ; `movebot` reste un raccourci local.
- Radar normal par defaut : capteurs et equipe du bateau observe, gel en plongee, visibilite/LOS/thermoclines habituelles. Taper `allmap` active/desactive localement la carte complete de diagnostic.
- Sur la carte : molette pour zoomer (x1 a x100), glisser pour deplacer ; dezoomer a x1 retrouve le monde entier.
- Glisser dans la vue 3D pour regarder, molette pour zoomer ; cliquer un contact radar visible ou une etiquette 3D pour suivre, sans cibler ni teleporter.
- Naufrage/depart : bateau survivant suivant, sinon vue neutre sans ecran de mort ; la premiere arrivee est suivie automatiquement.
- Integrite en pourcentage, vitesse/cap/profondeur en lecture seule. Stocks de munitions distants non transmis : indication explicite, pas de faux compteurs ni d'arsenal actif.
- Aucun tir, pilotage, ajout d'unite, cheat serveur ou commande admin ; quitter l'observation revient a l'accueil via une nouvelle connexion.

Ce mode public reutilise la perception du client joueur, mais ne reconstitue pas
ses detections privees ou son historique avant connexion/changement de vue ; ce
n'est pas une preuve de parite capteur BT/RL ou navigateur. Avec `--trace`, le spectateur n'est pas une troisieme unite dans
les snapshots. Une fin autogame configuree arrete toujours le serveur, meme si
un spectateur est connecte. Aucun demarrage serveur n'est implique par ce mode.

## Trace Serveur Opt-In

Equilibrage approuve le 2026-09-09 : coques destroyer **200 points**, sous-marin
**100 points**, leurres acoustiques **10 points**, configures dans `boats/*.json`.
Les degats sont absolus, le HUD affiche le pourcentage courant/maximum; les leurres
peuvent survivre aux explosions attenuees en 3D. Autres destructibles inchanges,
HP differes. Memes capacites humaines/BT/RL/headless, schemas RL inchanges mais
scores historiques non directement comparables. Champions conserves; aucune
promotion, nouvelle session humaine ou entrainement implique. Voir `TECHNIQUE.md`.

`./start.sh --trace --map world` active la trace des sessions normales (humains,
bots BT/RL, sous-marins et destroyers). Sans `--trace`, aucun fichier de trace
n'est ouvert ; pas de commande distante ni de changement de configuration requis.

- Fichier : `logs/game_trace.jsonl`, JSON par ligne, flush apres chaque ligne.
- Rotation : 20 MiB par fichier, cinq sauvegardes `.1` a `.5`, soit 120 MiB maximum.
- Snapshots a 4 Hz maximum en temps reel : bateaux, torpilles, drones, grenades,
  mines, balises actives/passives et leurres ; compteurs et commandes stockees inclus.
- Evenements de combat au drainage Sim ou a l'emission legacy, transitions de
  verrou/contact serveur a chaque pas, disparitions deduites entre snapshots.
- Aucune dependance ML ajoutee. Aucune IP, conversation, SID, credential ou nom
  de joueur collecte ; uniquement les identifiants publics utiles au gameplay.
- Les lignes `sample` indiquent les nombres d'objets, lignes et octets ecrits
  depuis le debut du processus. Voir `TECHNIQUE.md` pour le schema et les limites.

La trace contient l'etat autoritaire stocke, pas une preuve de visibilite legale
ni un replay deterministe. Garder les fichiers sur le serveur, hors diffusion
aux joueurs. Pas de nouvel entrainement long avant analyse de traces humaines
autorisees ; aucun audit global de fairness n'est declare termine.

Pour placer les bots d'une session de trace : taper `allmap` si necessaire,
selectionner un bot allie ou ennemi sur le radar (ou en 3D), taper `telebot`
hors champ de saisie, puis cliquer la destination sur la carte radar.
`Echap` annule ; apres un refus, retaper `telebot` pour reessayer.
`move` deplace son bateau ; `movebot` (ou `bot`) passe en vue bot,
et `self` revient a son bateau, sans teleporter le bot.
La profondeur est conservee, la vitesse remise a zero ; l'IA reprend ensuite.
Les joueurs humains ne sont jamais des cibles valides. Comme les cheats existants,
il suffit d'avoir rejoint le jeu (aucun role administrateur distinct).
Avec `--trace`, chaque placement accepte produit un evenement `BotTeleported`.

## Architecture Du Jeu

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
de Socket.IO. `rl/headless.py` la réutilise directement pour les entraînements RL,
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
```

Au premier lancement, `start.sh` génère automatiquement un certificat HTTPS
auto-signé valable dix ans si `certs/cert.pem` et `certs/key.pem` sont absents.
Les certificats restent locaux et exclus de Git. Une paire existante n'est
jamais remplacée automatiquement.

La clé Flask n'est pas stockée dans le dépôt. La variable d'environnement
`VIRTUALWORLD_SECRET_KEY` peut fournir une valeur stable d'au moins 32
caractères. Si elle est absente, le serveur génère une clé aléatoire temporaire
à chaque démarrage ; cela suffit tant qu'aucune session Flask persistante n'est
utilisée.

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
Il met à jour la branche `main`, récupère par SSH tous les modèles ZIP RL depuis
la machine d'entraînement, vérifie leurs archives et les installe dans
`rl/models_rl/` :

```bash
./update_server.sh
```

La source par défaut est
`francois@192.168.1.20:/data/dev/opencode/virtualWorld`. La machine et le chemin
peuvent être remplacés avec
`./update_server.sh utilisateur@machine /autre/chemin`. La connexion SSH de la
cible vers la source doit être configurée. Les modifications locales non
commitées sont autorisées ; Git refuse le pull si elles risquent d'être écrasées.
Si la version distante de `config/conffile.json` diffère,
le script refuse la mise à jour : réconcilier explicitement la configuration,
sans perdre les choix locaux, avant de relancer. Aucun stash ni écrasement
automatique de la configuration n'est effectué.

La copie conserve tous les runs et sous-répertoires contenant des ZIP : `best`,
`checkpoints`, modèles finaux, `league`, `archive`, y compris les versions non
promues. Elle exclut les logs, TensorBoard et rapports JSON. Aucun fichier cible
absent de la source n'est supprimé. Les ZIP sont tous téléchargés et vérifiés
(CRC et membres SB3, sans exécuter les modèles) avant installation atomique par
fichier sur le même système de fichiers. Un échec de transfert ou validation
laisse les modèles installés intacts ; l'ensemble n'est pas une transaction
atomique si une erreur survient pendant l'installation. Prévoir l'espace pour
une copie complète et utiliser une source de confiance sans entraînement en
cours d'écriture. Prérequis : `git`, `ssh`, `scp`, Python 3 local et distant,
sans `rsync` ; chemin source absolu sans espaces. `./update_server.sh --help`
ne contacte aucune machine. Après la copie, redémarrer le serveur pour charger le
nouveau code et vider le cache des modèles RL.

## Sélection des bots IA

Les boutons **Sub IA** et **Destroyer IA** lisent ces clés à la racine de
`config/conffile.json` (orthographe `bub` intentionnelle) :

```json
{
  "bot_rl_sub": "aisub_v15_scripted",
  "bot_rl_destroyer": "aidest_v3_scripted",
  "server": { "port": 7000 },
  "world": { "dayDurationSeconds": 1800 }
}
```

Ces valeurs sont les défauts si les clés sont absentes. Utiliser le nom complet
du run, sans préfixe `rl_` ; aucune sélection automatique d'une version récente.
Un run charge `best/best_model.zip`, sinon `policy_final.zip`. Pour tester un
checkpoint existant, utiliser par exemple
`"bot_rl_destroyer": "aidest_v4_scripted:policy_250000_steps"` : recherche à la
racine du run puis dans `checkpoints/`, extension `.zip` facultative. Les ZIP
`league`/`archive` sont copiés pour les évaluations, sans nouveau sélecteur UI.
Redémarrer le serveur et reconnecter le client après modification.

Seuls ces deux identifiants sont ajoutés au bootstrap socket `init`, jamais le
fichier de configuration complet. Un identifiant invalide bloque le démarrage ;
un modèle absent ou incompatible avec le bateau utilise le repli BT existant
(`autosub`/`autodest`) avec erreur dans les logs. La copie ne promeut aucun modèle.

## Tests

```bash
.venv/bin/python -m unittest -v rl.test_rl_pipeline
.venv/bin/python -m py_compile \
  server.py simulation.py rl/headless.py rl/rl_control.py rl/rl_env.py \
  rl/rl_runtime.py rl/train_ai.py rl/evaluate_ai.py
```

Le dépôt ne possède pas encore de suite de tests navigateur automatisée. Les
changements graphiques doivent être vérifiés manuellement sur laptop ou desktop.

## Entraînement des bots

Le pipeline utilise Gymnasium, Stable-Baselines3 et `RecurrentPPO` de
SB3-Contrib. Les modèles peuvent affronter des Behavior Trees, une politique
gelée ou une ligue de snapshots historiques.

Consulter [rl/TRAINING_RL.md](rl/TRAINING_RL.md) pour :

- comprendre les observations, les actions et les récompenses ;
- lancer une phase scripted ou self-play ;
- suivre les checkpoints et TensorBoard ;
- comparer les politiques sur des graines identiques ;
- charger un bot RL dans le serveur live.

Les modèles et sorties d'entraînement vivent dans `rl/models_rl/` et sont exclus de
Git en raison de leur taille.

## Structure du dépôt

| Chemin | Rôle |
|---|---|
| `server.py` | Réseau, sessions, intents et boucle serveur |
| `simulation.py` | Physique et règles autoritaires sans dépendance Flask |
| `events.py` | Événements typés produits par la simulation |
| `bot_ai.py` | Moteur de Behavior Trees |
| `bots/ai/` | Définitions JSON des comportements |
| `rl/` | Pipeline RL : environnement, contrôle, entraînement, évaluation et modèles |
| `rl/configs/` | Configurations d'entraînement RL |
| `boats/` | Caractéristiques des navires |
| `maps/` | Cartes et graphes de navigation |
| `static/game.js` | Client BabylonJS |

## Documentation

- [Architecture et règles techniques](TECHNIQUE.md)
- [Entraînement des bots RL](rl/TRAINING_RL.md)

## Licence

Aucune licence de redistribution n'est actuellement publiée dans ce dépôt.
## Scenarios Au Demarrage

`autogame.json` a la racine est charge uniquement avec `--autogame`, au demarrage
du serveur avant toute connexion ; `{"boats": []}` permet un scenario vide.
Le fichier local autorise contient actuellement le duel destroyer v3 / sous-marin v15,
avec 30 s de preparation, premier naufrage puis attente des torpilles des bateaux
coules, et limite de combat de 600 s.
Sans ce flag (defaut), aucune lecture, validation, precharge d'IA ni creation de
bots du scenario, meme si le fichier est absent ou invalide. Exemple de lancement
autorise : `./start.sh --trace --autogame --map world`. Il permet de fixer
type de bateau, IA BT/RL, equipe, XYZ en unites monde (10 m/u) et cap en radians.
Le champ `map` optionnel doit correspondre a `--map` ; erreurs de scenario ou
modeles absents/incompatibles refusent le demarrage avec `--autogame`, sans repli RL silencieux.
Schema complet et exemple de duel RL a 2 km : section "Scenario automatique et
grenades" de `TECHNIQUE.md`. Aucun serveur lance pour cette modification.
Les grenades peuvent maintenant endommager leur tireur humain comme les bots.

Fin automatique optionnelle, a ajouter a un scenario contenant des bateaux :

```json
"endCondition": {"type": "anyBoatSunk", "waitForTorpedoes": true},
"maxDurationSeconds": 600
```

Preparation optionnelle : `"startDelaySeconds": 30` (defaut 0, nombre fini >= 0,
booleens refuses ; une valeur positive exige des bateaux). Apres prechargement
et spawn immediat, HTTPS et **Observer** restent accessibles pendant l'attente :
positions initiales visibles, aucun pas de physique, decision BT/RL ou tick sonar.
Les intents de jeu, dont le spawn humain, retournent `autogame_preparing` jusqu'au
depart ; il faut les reessayer ensuite. Le chrono de 600 s commence au depart,
pas au spawn. Avec `--trace`, `autogame_ready` et `autogame_started` distinguent
preparation et combat. Aucun lancement n'est effectue par cette modification.

Autres conditions : `{"type": "anyBoatSunk"}` ou
`{"type": "teamEliminated", "teamId": "red"}`. Le timeout est optionnel et peut
etre utilise seul. Sans ces champs, aucun arret automatique. Seuls les naufrages
des bots initiaux comptent, pas les suppressions manuelles ni les nouveaux joueurs.
Naufrages simultanes regroupes, bilan `autogame_end`, trace finale fermee puis
sortie normale du processus (code 0). Les clients sont deconnectes ; reception du
dernier evenement non garantie. Voir `TECHNIQUE.md` pour le schema et les limites.

`endCondition.waitForTorpedoes` accepte uniquement un booleen (defaut `false`,
arret immediat conserve), pour les trois types. Avec `true`, une condition atteinte
attend la disparition de toutes les torpilles en vol des membres initiaux coules.
Les survivants continuent de jouer ; tout nouveau naufrage initial ajoute ses
torpilles a l'attente, permettant un kill posthume et un match nul. Pas d'attente
des torpilles de survivants, humains/bots ajoutes, explosions persistantes,
leurres ou drones. La limite de duree interrompt aussi cette attente ; sans limite,
aucun watchdog supplementaire. `--trace` emet une seule entree `autogame_settling`,
puis le bilan definitif seulement a la fin. Le scenario local active cette option.
