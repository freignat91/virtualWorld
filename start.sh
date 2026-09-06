#!/bin/bash
cd "$(dirname "$0")"
# Utilise le venv si présent (apporte SB3 + torch pour les bots RL).
PY=python3
if [ -x ".venv/bin/python" ]; then
    PY=.venv/bin/python
elif [ -x "venv/bin/python" ]; then
    PY=venv/bin/python
fi
$PY server.py "$@" 2>&1 | $PY logfilter.py
