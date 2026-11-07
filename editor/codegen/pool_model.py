"""editor/codegen/pool_model.py : le modèle d'un prefab : ce qui le fait compter pour un seul code.

Un modèle est compilé une fois ; ses instances (posées ou nées) n'ont que leurs valeurs propres.
Ce module dit QUELS acteurs posés rejoignent le modèle de leur prefab, combien d'emplacements
d'acteurs occupe une instance, et quel type d'emplacement reçoit chaque posé. La géométrie qui en découle vit
dans `oam_alloc`."""
from __future__ import annotations

from codegen.actor_appearance import sprite_key
from core.models.scene import actor_prefab_linked


def prefab_group(prefab) -> int:
    """Entrées de `g_actors` qu'occupe UNE instance : la racine plus ses
    parties. Un prefab plat vaut 1.

    C'est ICI que le calcul vit."""
    return 1 + len(getattr(prefab, "children", []) or [])


def _sfx_key(owner) -> tuple:
    comp = owner.get_component("sound_fx")
    return (bool(comp and comp.active), getattr(comp, "sfx_name", "") if comp else "")


def model_members(project, posed: list) -> dict:
    """Quels acteurs POSÉS rejoignent le modèle de leur prefab : nom de prefab -> indices dans
    `posed`. Un membre PARTAGE le code du modèle (compilé une fois) et n'a que ses valeurs
    d'instance. Il doit donc être sur le même chemin de compilation que lui :

      - le prefab est plat (l'instanciation d'un sous-arbre en scène n'existe pas) ;
      - l'acteur est « lié » (`actor_prefab_linked` : mêmes composants, même `.lua`) ET affiche les
        mêmes sprites, même Sfx (les noms d'état se résolvent dans le sprite) ;
      - il n'est le parent d'aucun autre acteur posé (`self.Enfant` se résout au build, dans l'acteur) ;
      - son script est du Lua (un script C natif se copie tel quel).

    Les autres acteurs, dérivés du prefab ou non, restent des singletons : chacun son code."""
    by_name = {pf.name: pf for pf in project.prefabs}
    parents = {getattr(a, "parent", None) for a in posed} - {None, ""}
    out: dict = {}
    for i, a in enumerate(posed):
        pf = by_name.get(getattr(a, "prefab_name", None) or "")
        if pf is None or getattr(pf, "children", None) or a.name in parents:
            continue
        if not actor_prefab_linked(a, pf):
            continue
        if sprite_key(a) != sprite_key(pf) or _sfx_key(a) != _sfx_key(pf):
            continue
        script = pf.get_component("script")
        if script and script.active and script.script and not script.script.lower().endswith(".lua"):
            continue
        out.setdefault(pf.name, []).append(i)
    return out


# Les champs de composant qui vivent dans l'EMPLACEMENT (`Actor`, `OamEntry`, état du script) : deux instances qui ne
# diffèrent que par eux restent le même type. Tout autre champ est lu au modèle (descripteur) et sépare deux types.
# Le tag d'une boîte est au modèle : les tables de paires (blocage, appui, transport, impulsions) appliquent la
# matrice des tags au build, par couple de types.
_SLOT_FIELDS = {
    "collision_shape": {"x", "y", "w", "h", "solid", "active"},
    "sprite": {"initial_state", "affine_transform", "scale_x", "scale_y", "rotation",
               "offset_x", "offset_y", "pivot_x", "pivot_y"},
    "script": {"exports_values"},
}


def _box_roles(actor) -> tuple:
    """Les rôles de boîtes que le build tire de `solid` et `active` (champs d'emplacement) : le mode du corps, ses boîtes
    de corps, ses boîtes bloquantes. Deux copies dont les rôles diffèrent sont deux types, sinon une table de paires par
    type donnerait à l'une les boîtes de l'autre."""
    from codegen.runtime_codegen.physics.body import (
        physics_blocker_entries, physics_body_mode, physics_collider_mask,
    )
    return (physics_body_mode(actor), physics_collider_mask(actor),
            tuple(rank for rank, _box in physics_blocker_entries(actor)))


def _variant_key(prefab_name: str, actor) -> tuple:
    from core.models.components import components_to_list
    comps = []
    for c in components_to_list(actor.components):
        drop = _SLOT_FIELDS.get(c.get("component_type"), set())
        comps.append(tuple(sorted((k, repr(v)) for k, v in c.items() if k not in drop)))
    return (prefab_name, tuple(comps), bool(getattr(actor, "screen_space", False)),
            bool(getattr(actor, "is_player", False)), _box_roles(actor))


def placed_types(posed: list, members: dict, first: int, spawned: dict | None = None) -> list[int]:
    """Le type d'emplacement (`Actor.type_id`) de chaque acteur POSÉ.

    Un membre dont les valeurs lues au modèle sont celles de son prefab, quand la scène fait aussi naître ce prefab
    (`spawned` : nom -> (prefab, `root_type_id`)), prend le `root_type_id` du prefab : posé ou né, le même type, la même ligne de
    descripteur. Les autres types commencent à `first` (après ceux du pool partagé) : un membre qui diffère de son
    prefab partage le sien avec les membres de mêmes valeurs (une variante), un acteur qui n'est membre de rien est un
    modèle à lui seul."""
    member_of = {i: name for name, idx in members.items() for i in idx}
    ids: dict = {_variant_key(name, prefab.actor): root_type_id for name, (prefab, root_type_id) in (spawned or {}).items()}
    fresh = 0
    out = []
    for i, a in enumerate(posed):
        key = _variant_key(member_of[i], a) if i in member_of else ("singleton", i)
        if key not in ids:
            ids[key] = first + fresh
            fresh += 1
        out.append(ids[key])
    return out
