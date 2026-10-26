"""editor/codegen/pool_model.py — le modèle d'un prefab : ce qui le fait compter pour un seul code.

Un modèle est compilé une fois ; ses instances (posées ou nées) n'ont que leurs valeurs propres.
Ce module dit QUELS acteurs posés rejoignent le modèle de leur prefab, et combien d'emplacements
d'acteurs occupe une instance. La géométrie qui en découle vit dans `oam_alloc`."""
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
