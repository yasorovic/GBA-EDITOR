"""Empreintes de conversion des assets de build.

Le cache ne conserve aucune copie parallèle des sorties : `build/` EST le
cache. Il mémorise seulement quelle empreinte a produit quels fichiers ; une
entrée n'est utilisable que si tous ces fichiers existent encore. Ainsi un
nettoyage de build, un changement de branche ou une sortie supprimée retombe
naturellement sur une conversion complète.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from functools import lru_cache
from pathlib import Path

from core.app_info import APP_VERSION

import codegen.build_output as build_output


def file_digest(path: Path) -> str:
    """Empreinte du contenu, indépendante de toute date de fichier."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return f"{path.stat().st_size}:{digest.hexdigest()}"


def tool_signature(path: Path | None) -> str:
    """Identifie l'outil sans hacher son exécutable à chaque asset."""
    if not path:
        return "absent"
    try:
        stat = path.stat()
        return f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        return str(path)


# Les modules dont le CODE décide de ce que produit une conversion (quantification,
# recomposition des feuilles, découpe des modules audio).
_CONVERSION_MODULES = ("codegen.grit_conversion", "core.models.gba_color",
                       "core.module_trim", "core.music_structure", "core.wav_module")


@lru_cache(maxsize=1)
def pipeline_signature() -> str:
    """Empreinte du code de conversion : la version de l'application, plus le contenu
    des modules ci-dessus quand leurs sources existent (checkout de développement).

    Sans elle, l'empreinte d'un asset ne dit rien du code qui l'a converti : après
    une mise à jour, ou une retouche de `quantize_asset`, le cache resservait les
    anciennes sorties. Une distribution Nuitka n'a pas les `.py` : la version suffit,
    le code n'y change qu'avec elle."""
    digest = hashlib.sha256(APP_VERSION.encode("utf-8"))
    for name in _CONVERSION_MODULES:
        source = Path(getattr(importlib.import_module(name), "__file__", "") or "")
        if source.suffix == ".py" and source.is_file():
            digest.update(source.read_bytes())
    return digest.hexdigest()


class AssetBuildCache:
    """Index persistant `{entrée: empreinte}` des sorties déjà dans build/."""

    def __init__(self, build_dir: Path):
        self.path = build_dir / ".asset-cache.json"
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = value.get("entries", {}) if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            self._entries = {}
        self._dirty = False

    @staticmethod
    def fingerprint(value: object) -> str:
        encoded = json.dumps({"pipeline": pipeline_signature(), "value": value}, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def hit(self, key: str, fingerprint: str, outputs: list[Path]) -> bool:
        entry = self._entries.get(key)
        if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint:
            return False
        if not all(path.is_file() for path in outputs):
            return False
        for path in outputs:
            build_output.claim(path)
        return True

    def store(self, key: str, fingerprint: str) -> None:
        self._entries[key] = {"fingerprint": fingerprint}
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        text = json.dumps({"version": 1, "entries": self._entries},
                          ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        build_output.write(self.path, text)
        self._dirty = False
