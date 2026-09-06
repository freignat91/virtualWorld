#!/bin/bash
# Tue le serveur, qu'il soit lancé via python3 ou .venv/bin/python.
pkill -9 -f "python.*server\.py"
echo "Serveur arrêté"
