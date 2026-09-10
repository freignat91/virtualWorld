#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [utilisateur@machine-source] [repertoire-source]" >&2
    echo "Defaut: francois@192.168.1.20 /data/dev/opencode/virtualWorld" >&2
    echo "Exemple: $0 francois@192.168.1.20 /data/dev/opencode/virtualWorld" >&2
    echo "Depuis la cible: git pull puis tous les ZIP RL (sans logs ni suppression)." >&2
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    usage
    exit 0
fi

if [[ $# -gt 2 ]]; then
    usage
    exit 2
fi

SOURCE_HOST=${1:-francois@192.168.1.20}
SOURCE_ROOT=${2:-/data/dev/opencode/virtualWorld}
TARGET_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BRANCH=${GIT_BRANCH:-main}
if [[ ! $SOURCE_HOST =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.@-]*$ ]] ||
   [[ ! $SOURCE_ROOT =~ ^/[a-zA-Z0-9_./-]*$ ]] ||
   [[ /${SOURCE_ROOT#/}/ == */../* ]]; then
    echo "Source invalide: hote SSH simple et chemin absolu sans espaces requis." >&2
    usage
    exit 2
fi

for command_name in git ssh scp; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Commande absente: $command_name" >&2
        exit 1
    fi
done

if ! git -C "$TARGET_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Le script doit se trouver dans le depot virtualWorld." >&2
    exit 1
fi

current_branch=$(git -C "$TARGET_ROOT" branch --show-current)
if [[ $current_branch != "$BRANCH" ]]; then
    echo "Branche courante '$current_branch', branche attendue '$BRANCH'." >&2
    exit 1
fi

if [[ -x "$TARGET_ROOT/.venv/bin/python" ]]; then
    PYTHON=$TARGET_ROOT/.venv/bin/python
elif [[ -x "$TARGET_ROOT/venv/bin/python" ]]; then
    PYTHON=$TARGET_ROOT/venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=$(command -v python3)
else
    echo "Python 3 est requis pour verifier les archives de modeles." >&2
    exit 1
fi

echo "Mise a jour du depot ($BRANCH)..."
git -C "$TARGET_ROOT" fetch origin "$BRANCH"
revision=$(git -C "$TARGET_ROOT" rev-parse FETCH_HEAD)
if ! git -C "$TARGET_ROOT" diff --quiet HEAD "$revision" -- config/conffile.json; then
    echo "La configuration distante differe: reconciliez config/conffile.json explicitement avant la mise a jour." >&2
    exit 1
fi
# Tire la revision deja verifiee, sans nouvelle requete distante.
git -C "$TARGET_ROOT" pull --ff-only --no-rebase . "$revision"

"$PYTHON" "$TARGET_ROOT/rl/sync_models.py" "$SOURCE_HOST" "$SOURCE_ROOT" "$TARGET_ROOT/rl/models_rl"

echo "Depot et modeles mis a jour avec succes."
echo "Redemarrez le serveur pour charger le nouveau code et vider le cache RL."
