"""Compilateur C de la machine hôte, partagé par les tests qui compilent une sonde native.

Les sondes (`tests/native/*.c`) font tourner le VRAI code C du moteur : sans compilateur,
le test saute (et la CI, qui en a un, le joue)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


def compilateur_hote() -> str | None:
    """Un compilateur C qui produit un exécutable pour CETTE machine.

    `arm-none-eabi-gcc` est écarté volontairement, y compris s'il est sur le
    PATH : il compile, mais ce qu'il produit ne s'exécute pas ici.

    `CC` l'emporte sur le PATH — c'est la variable conventionnelle, et sous
    Windows elle évite d'avoir à mettre msys2 dans le PATH de la session :

        CC=C:/msys64/ucrt64/bin/gcc.exe python -m pytest tests
    """
    declare = os.environ.get("CC")
    if declare:
        resolu = shutil.which(declare)
        if resolu is None:
            # Un `CC` posé mais introuvable est une erreur de configuration, pas
            # une absence de compilateur : le taire ferait sauter le test en
            # laissant croire que la machine n'en a pas.
            pytest.fail(f"CC={declare!r} est introuvable")
        return resolu
    for nom in ("cc", "gcc", "clang"):
        chemin = shutil.which(nom)
        if chemin:
            return chemin
    return None


def environnement(compilateur: str) -> dict:
    """Le PATH, avec le répertoire du compilateur devant.

    Sans ça, un `gcc.exe` msys2 désigné par un chemin absolu ne trouve pas ses
    propres DLL : il ne démarre pas, ne dit rien sur sa sortie d'erreur, et rend
    un code non nul. L'exécutable qu'il produit a le même besoin — d'où le même
    environnement pour la compilation ET pour la sonde."""
    env = dict(os.environ)
    dossier = str(Path(compilateur).parent)
    env["PATH"] = dossier + os.pathsep + env.get("PATH", "")
    return env
