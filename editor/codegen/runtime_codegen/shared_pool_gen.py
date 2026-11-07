"""runtime_codegen/shared_pool_gen.py : le C qui parcourt le pool PARTAGÉ d'une scène.

Un emplacement du pool accueille n'importe quel modèle simple (`oam_alloc.is_plain_model`) : le build ne
peut donc plus dérouler, modèle par modèle, des boucles sur des emplacements qu'il connaît : les passes parcourent
les emplacements utilisés (`POOL_EACH` : de `g_spool_start` à `g_spool_hw`, le plus haut utilisé, en sautant les blocs
de 32 emplacements sans vivant).

Un modèle à PARTIES occupe un groupe d'emplacements contigus : `Actor.model` y est un TYPE d'emplacement, la
racine portant l'identité du modèle (`model_id`) et sa partie k cette identité + k.
Les passes communes aux posés et aux nés lisent le descripteur de modèle (`model_desc`) et ne vivent pas ici.

`pi` est la liste des pools de la scène (`gen_pool.scene_pi`) ; seuls ceux qui portent `shared`
comptent ici. Les fonctions reçoivent les générateurs de `main_gen` dont elles ont besoin plutôt que de
l'importer : ce module est sa dépendance, pas l'inverse."""
from __future__ import annotations


def shared_models(pi: list[dict]) -> list[dict]:
    """Les modèles du pool partagé, dans l'ordre de leur identité (`model_id`)."""
    return sorted((p2 for p2 in pi if p2.get("shared")), key=lambda p2: p2["model_id"])


def owners(m: dict) -> list:
    """Les porteurs d'un modèle, dans l'ordre des emplacements de son groupe : la racine, puis ses parties."""
    return [m["prefab"], *(getattr(m["prefab"], "children", None) or [])]


def trim_lines(pi: list[dict]) -> list[str]:
    """Rabat le plus haut emplacement utilisé sur le dernier occupé : après une pluie de balles, les boucles
    du tick ne parcourent plus des emplacements vides."""
    if not shared_models(pi):
        return []
    return ["    while(g_spool_hw>g_spool_start && !g_actors[g_spool_hw-1].alive) g_spool_hw--;"]
