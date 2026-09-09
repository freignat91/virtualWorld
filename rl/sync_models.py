"""Copie tous les ZIP RL par SSH sans importer ni executer les politiques."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
from tempfile import TemporaryDirectory
from typing import List
import zipfile


REMOTE_LIST = """
import json, os, pathlib, sys
root = pathlib.Path(sys.argv[1]) / 'rl/models_rl'
if not root.is_dir():
    raise FileNotFoundError(root)
files = []
for directory, dirs, names in os.walk(root, followlinks=False):
    dirs[:] = sorted(d for d in dirs if not (pathlib.Path(directory) / d).is_symlink())
    for name in sorted(names):
        path = pathlib.Path(directory) / name
        if name.endswith('.zip'):
            if path.is_symlink() or not path.is_file():
                raise ValueError('ZIP non regulier: ' + str(path))
            files.append(path.relative_to(root).as_posix())
print(json.dumps(files))
"""


def validate_source(host: str, root: str) -> None:
    """Limite aussi les arguments interpretes par les anciens serveurs SCP."""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", host):
        raise ValueError("machine SSH invalide")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]*", root) or ".." in root.split("/"):
        raise ValueError("repertoire source absolu requis, sans espaces ni metacaracteres")


def validate_manifest(manifest: object) -> List[str]:
    """Refuse les chemins non canoniques et les sorties hors du dossier cible."""
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("aucun modele ZIP sur la source")
    paths = []
    for name in manifest:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+\.zip", name):
            raise ValueError("chemin ZIP invalide")
        path = PurePosixPath(name)
        if (path.is_absolute() or len(path.parts) < 2 or str(path) != name
                or any(part in {".", ".."} or part.startswith(".") for part in path.parts)):
            raise ValueError(f"chemin ZIP invalide: {name}")
        paths.append(name)
    if len(set(paths)) != len(paths):
        raise ValueError("ZIP duplique dans le manifeste")
    return sorted(paths)


def validate_zip(path: Path) -> None:
    """Verifie le CRC et les membres SB3, sans deserialisation pickle."""
    with zipfile.ZipFile(path) as archive:
        if not {"data", "policy.pth"}.issubset(archive.namelist()):
            raise ValueError(f"archive non SB3: {path}")
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"ZIP corrompu: {path}: {bad_member}")


def sync_models(host: str, source_root: str, target: Path) -> int:
    """Valide tout avant installation atomique par fichier, sans suppression."""
    validate_source(host, source_root)
    result = subprocess.run(
        ["ssh", "--", host, "python3 - " + shlex.quote(source_root)],
        input=REMOTE_LIST, text=True, capture_output=True, check=True,
    )
    paths = validate_manifest(json.loads(result.stdout))
    target = target.absolute()
    for name in paths:
        destination = target / name
        for part in (destination, *destination.parents):
            if part.is_symlink():
                raise ValueError(f"lien symbolique cible interdit: {part}")
        if destination.exists() and not destination.is_file():
            raise ValueError(f"cible non reguliere: {destination}")
    target.mkdir(parents=True, exist_ok=True)
    # Le staging reste sur le meme systeme de fichiers que les destinations.
    with TemporaryDirectory(prefix=".sync-", dir=target) as directory:
        staging = Path(directory)
        for index, name in enumerate(paths):
            print(f"[{index + 1}/{len(paths)}] {name}", flush=True)
            downloaded = staging / str(index)
            subprocess.run([
                "scp", "--", f"{host}:{source_root.rstrip('/')}/rl/models_rl/{name}",
                str(downloaded),
            ], check=True)
            validate_zip(downloaded)
        for index, name in enumerate(paths):
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            downloaded = staging / str(index)
            downloaded.chmod(0o644)
            os.replace(downloaded, destination)
    return len(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_host")
    parser.add_argument("source_root")
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        count = sync_models(args.source_host, args.source_root, args.target)
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Synchronisation RL annulee: {exc}\n")
    print(f"{count} modeles ZIP installes; aucun artefact cible supprime.")


if __name__ == "__main__":
    main()
