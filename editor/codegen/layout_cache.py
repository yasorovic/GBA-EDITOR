"""codegen/layout_cache.py — la mémoïsation des dispositions (banques de palettes, OAM, entrées), à PORTÉE DE CONTEXTE.

Éteinte par défaut : sans contexte actif, `layout_memo` recalcule à chaque appel, et aucun appelant ne peut recevoir une
disposition périmée. Deux lots de calculs l'ouvrent, sur des objets qu'ils savent figés pendant sa durée :
  - le canvas, le temps de PRÉ-CHAUFFER les régions d'une scène (cf. `GBAScene.set_ui_regions`) ;
  - le build, de la fin de la validation à `main.c` (cf. `BuildWorker.run`) : chacune de ces dispositions y était relue
    des dizaines de fois (`scene_bank_layout` 16 fois pour une scène, `scene_oam_layout` 34, `compute_input_layout` 3).

Clé par IDENTITÉ des objets (projet, scène) : le contexte ne vit jamais à travers une édition. Les objets de la clé sont
gardés avec la valeur, pour qu'un `id` ne soit pas recyclé par un objet temporaire tant que le cache vit.
"""
from __future__ import annotations

from contextlib import contextmanager

_cache: "dict | None" = None


@contextmanager
def scene_layout_cache():
    """Active la mémoïsation pour la durée du bloc. Réentrant : seul le contexte le plus externe crée et jette le cache."""
    global _cache
    outer = _cache
    if outer is None:
        _cache = {}
    try:
        yield
    finally:
        _cache = outer


def layout_memo(kind: str, objects: tuple, compute, extra: tuple = ()):
    """`compute()`, gardé sous la clé (`kind`, identités de `objects`, `extra`) tant qu'un contexte est actif."""
    if _cache is None:
        return compute()
    key = (kind, *map(id, objects), *extra)
    hit = _cache.get(key)
    if hit is None:
        hit = _cache[key] = (compute(), objects)
    return hit[0]
