#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [utilisateur@machine-source] [repertoire-source]" >&2
    echo "Defaut: francois@192.168.1.20 /data/dev/opencode/virtualWorld" >&2
    echo "Exemple: $0 francois@192.168.1.20 /data/dev/opencode/virtualWorld" >&2
}

if [[ $# -gt 2 ]]; then
    usage
    exit 2
fi

SOURCE_HOST=${1:-francois@192.168.1.20}
SOURCE_ROOT=${2:-/data/dev/opencode/virtualWorld}
TARGET_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BRANCH=${GIT_BRANCH:-main}
RUNS=(aisub_v15_scripted aidest_v3_scripted)

if [[ $SOURCE_HOST == *:* ]]; then
    echo "La machine source ne doit pas contenir de chemin: $SOURCE_HOST" >&2
    usage
    exit 2
fi

for command_name in git scp; do
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

if ! git -C "$TARGET_ROOT" diff --quiet || ! git -C "$TARGET_ROOT" diff --cached --quiet; then
    echo "Le depot contient des modifications suivies. Mise a jour annulee." >&2
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
git -C "$TARGET_ROOT" pull --ff-only origin "$BRANCH"

TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/virtualworld-models.XXXXXX")
trap 'rm -rf "$TEMP_DIR"' EXIT

for run_name in "${RUNS[@]}"; do
    source_file="${SOURCE_ROOT%/}/rl/models_rl/$run_name/best/best_model.zip"
    downloaded_file="$TEMP_DIR/$run_name.zip"
    echo "Telechargement de $run_name..."
    scp -- "$SOURCE_HOST:$source_file" "$downloaded_file"
    "$PYTHON" -m zipfile -t "$downloaded_file" >/dev/null
done

for run_name in "${RUNS[@]}"; do
    target_dir="$TARGET_ROOT/rl/models_rl/$run_name/best"
    mkdir -p "$target_dir"
    chmod 0644 "$TEMP_DIR/$run_name.zip"
    mv -f "$TEMP_DIR/$run_name.zip" "$target_dir/best_model.zip"
done

echo "Depot et modeles mis a jour avec succes."
echo "Redemarrez le serveur pour charger le nouveau code et vider le cache RL."
