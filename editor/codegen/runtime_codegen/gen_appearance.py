"""codegen/runtime_codegen/gen_appearance.py — les constantes d'ACTIVATION des apparences.

Un porteur (acteur, partie de prefab) peut avoir plusieurs apparences ; une seule est
affichée (`OamEntry.appearance`). Activer l'une pose sur l'entrée OAM ce qui dépend du
sprite d'arrivée — tailles de frame, banque de palette, direction auto — et que
l'init n'a posé que pour l'apparence de DÉPART (cf. `main_gen._appearance_init_lines`).

Ces constantes vivent dans une table ROM PAR SCÈNE (`g_appearance_init`, cf.
`AppearanceInit` dans actor_types_static.h) : la banque de palette est un fait de la
scène, pas de l'acteur. Seuls les porteurs à PLUSIEURS apparences y ont des lignes —
un porteur mono-apparence n'a rien à activer, et sa géométrie reste celle d'avant.

Le calcul est PARTAGÉ : `scene_init` (qui émet la table et pose les bases des acteurs
posés) et le spawn des pools (qui pose la base d'une instance) appellent la même
fonction, donc ne peuvent pas diverger sur les numéros de ligne."""
from __future__ import annotations

from dataclasses import dataclass, field

from codegen.c_names import sym as c_sym
from codegen.oam_alloc import owner_appearances
from core.models.palette import OWN_PAL_BANK


@dataclass
class AppearanceLayout:
    """Les lignes de la table d'une scène, et où commence chaque porteur."""
    rows: list[tuple] = field(default_factory=list)          # (frame_w, frame_h, pal, auto_dir)
    actor_base: dict[int, int] = field(default_factory=dict)   # indice d'acteur posé → 1re ligne
    member_base: dict[tuple, int] = field(default_factory=dict)  # (sym du pool, membre) → 1re ligne


def _rows_of(p, owner, obj_layout) -> list[tuple]:
    """Une ligne par apparence du porteur, dans l'ordre de ses composants."""
    out = []
    for comp, sprite in owner_appearances(p, owner):
        own = list(sprite.own_palette) if getattr(sprite, "own_palette", None) else []
        pal = obj_layout.bank_index(getattr(owner, "pal_bank", OWN_PAL_BANK), own) if obj_layout else 0
        out.append((sprite.frame_w, sprite.frame_h, pal or 0, 1 if getattr(comp, "auto_dir", True) else 0))
    return out


def appearance_layout(p, scene_actors: list, pool_info: list, obj_layout) -> AppearanceLayout:
    """La table d'une scène : les membres de ses pools PUIS ses acteurs posés, à
    plusieurs apparences seulement. Les pools d'abord : le spawn n'a pas les
    acteurs posés sous la main, et `appearance_layout(p, [], pool_info, …)` doit
    lui rendre les mêmes numéros que `scene_init`."""
    lay = AppearanceLayout()
    for pi in pool_info:
        pf = pi["prefab"]
        for k, member in enumerate([pf] + list(getattr(pf, "children", []) or [])):
            rows = _rows_of(p, member, obj_layout)
            if len(rows) > 1:
                lay.member_base[(pi["sym"], k)] = len(lay.rows)
                lay.rows += rows
    for j, (actor, _sprite) in enumerate(scene_actors):
        rows = _rows_of(p, actor, obj_layout)
        if len(rows) > 1:
            lay.actor_base[j] = len(lay.rows)
            lay.rows += rows
    return lay


def appearance_table_lines(scene_sym: str, lay: AppearanceLayout) -> list[str]:
    """Le tableau ROM de la scène, ou rien si aucun porteur n'a plusieurs apparences."""
    if not lay.rows:
        return []
    body = ",".join(f"{{{w},{h},{pal},{ad}}}" for w, h, pal, ad in lay.rows)
    return [f"static const AppearanceInit {c_sym(scene_sym)}_appearance_init[{len(lay.rows)}] = {{{body}}};"]
