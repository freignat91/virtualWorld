# Repository Guidelines

## Overview

`virtualWorld` is a real-time multiplayer naval/submarine combat game. An authoritative Python server (Flask + Flask-SocketIO over eventlet) arbitrates all gameplay, while a monolithic BabylonJS client (`static/game.js`) renders and sends *intents*. Optional AI bots run as behavior trees or reinforcement-learning agents. Read `TECHNIQUE.md` for the full architecture.

## Project Structure & Module Organization

- `server.py` — entry point: network, tick loop, authoritative arbitration.
- `simulation.py` — pure game logic (`Sim` class, `step(dt)`); no I/O or Flask deps.
- `events.py` — dataclass events dispatched to sockets/logs/replay.
- `geometry.py`, `nav_graph.py` — pure geometry helpers and bot navigation graph.
- `bot_ai.py` — behavior-tree engine; tree definitions live in `bots/ai/*.json`.
- `boats/` — ship specs (`destroyer.json`, `submarine.json`).
- `maps/` — world maps; `config/conffile.json` — port and day length.
- `configs/` — RL training configs (`aisub_v*.json`).
- `models/`, `static/textures/` — 3D assets; `templates/` — HTML pages.

## Build, Test, and Development Commands

```bash
python3 -m venv .venv                      # create virtualenv
.venv/bin/pip install -r requirements.txt  # install dependencies
./start.sh                                 # run server (HTTPS, default port 7000)
./stop.sh                                  # stop server
python migrate_nav_graph.py                # one-shot: rebuild nav graphs in maps/
```

## Coding Style & Naming Conventions

- Python: 4-space indentation, `snake_case`, full type hints (`typing`), dataclasses for events.
- Docstrings and inline comments are written in **French** — keep this convention.
- JSON specs use `camelCase` keys (`radarRangeMeters`, `dayDurationSeconds`).
- `server.py` and `static/game.js` are large; make surgical edits and put new game state in `simulation.py` (never I/O-coupled).

## Testing Guidelines

There is no automated test suite or coverage config. Verify changes manually: run `./start.sh`, connect the client, and inspect `logs/server.log`. Toggle `debug_log.py` categories at runtime via the in-game `debug <cat>` cheat.

## Commit & Pull Request Guidelines

No Git history is currently present, so conventions are not yet established. Keep commits small and focused, reference the module touched, and update `TECHNIQUE.md` for any gameplay or network-behavior change.
