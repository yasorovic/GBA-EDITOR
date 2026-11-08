"""codegen/runtime_codegen/gen_affine.py : les sprites affines et leurs matrices OAM.

`affine_entry`/`compute_affine_info` rendent de la donnée ; seul `affine_oam_lines` émet du C (l'appel du moteur qui
recalcule la matrice et la prend à chaque frame).
"""
from __future__ import annotations

from core.models.components import affine_sprite_component
from core.models.field_value import FieldValue, number_c, var_names_from_project as _var_names


def affine_entry(sc, names=None) -> dict | None:
    """
    L'entrée affine d'un SpriteComponent : les valeurs de départ de son transform, ou None si le sprite n'est pas affine.

    La décision est portée par `SpriteComponent.affine_transform` : coché, le sprite est dessiné en affine (sa
    matrice, une des 32 du matériel, est prise à la frame), même si scale/rotation valent leur défaut. Sans lui, il
    est émis en OAM normale : les champs de transform gardent leur valeur, mais rien ne les affiche. Un acteur n'a ni
    rotation ni échelle : seul son sprite tourne ou change d'échelle (cf. affine_oam_lines).
    """
    if not bool(getattr(sc, "affine_transform", False)):
        return None

    return {
        # Valeurs de départ de l'entrée d'affichage, écrites à l'init. Littéral → int, variable → expression C
        # (assignation à l'init).
        "sprite_rotation":   number_c(getattr(sc, "rotation", 0), names),
        "sprite_scale_x":    number_c(getattr(sc, "scale_x", 1.0), names, q8=True),
        "sprite_scale_y":    number_c(getattr(sc, "scale_y", 1.0), names, q8=True),
        "offset_x":    _offset_value(getattr(sc, "offset_x", 0), names),
        "offset_y":    _offset_value(getattr(sc, "offset_y", 0), names),
        "pivot_x":     _offset_value(getattr(sc, "pivot_x", 0), names),
        "pivot_y":     _offset_value(getattr(sc, "pivot_y", 0), names),
    }


def _offset_value(raw, names):
    """Décalage de sprite tel qu'il s'écrit dans le C : un `int` pour un
    littéral (px/tile), l'expression `g_<nom>` pour une variable. Une
    assignation à l'init, donc une variable y est légitime. `names` =
    `var_names_from_project`."""
    fv = FieldValue.parse(raw, names)
    return fv.c_expr() if fv.is_ref else fv.px()


def compute_affine_info(actor_offset: int, scene_actors: list, names=None) -> dict:
    """
    Retourne {indice d'acteur: entry} pour tout actor POSÉ dont le SpriteComponent a `affine_transform` coché.
    L'entrée porte les valeurs de départ écrites à l'init ; aucune matrice n'est réservée, le rendu la prend à la
    frame, comme pour un né (deux sprites de même matrice partagent la sienne, cf. `oam_write_affine`).
    """
    result: dict = {}
    for j, (actor, _) in enumerate(scene_actors):
        entry = affine_entry(affine_sprite_component(actor), names=names)
        if entry:
            result[actor_offset + j] = entry
    return result


def scene_has_affine(scene_actors: list, pi: list) -> bool:
    """La scène a-t-elle un sprite affine, posé ou né (la racine ou une partie d'un modèle) ? C'est ce qui lui vaut un
    cache de calcul (`AffCache`) et la matrice dynamique."""
    owners = [actor for actor, _sprite in scene_actors]
    for m in pi:
        if m.get("shared"):
            owners += [m["prefab"], *(getattr(m["prefab"], "children", None) or [])]
    return any(affine_entry(affine_sprite_component(owner)) for owner in owners)


def oam_window_open(box_w: int, box_h: int) -> list[str]:
    """Ouvre le bloc qui écrit UN sprite dans l'OAM : seulement s'il touche l'écran, et tant qu'il
    reste un emplacement. `sx`/`sy` (le coin haut-gauche de sa boîte OAM) et `_oamn` (le prochain
    emplacement libre de la frame) sont déjà posés par l'appelant ; le sprite écrit en
    `shadow_oam[_o]`. Le test est EXACT, sans marge : l'OAM boucle sur 256 en Y, un sprite posé
    hors écran de plus de (256 - 160) pixels reviendrait s'afficher de l'autre côté."""
    return [
        f"        if(sx+{box_w}>0&&sx<240&&sy+{box_h}>0&&sy<160){{",
        "          if(_oamn>=128){ g_oam_dropped++; } else {",
        "            int _o=_oamn++;",
    ]


def oam_window_close() -> list[str]:
    return ["          }", "        }"]


def affine_oam_lines(idx, sprite, bt: int, screen_space: bool = False, entry=None) -> list[str]:
    """Lignes C (intérieur du if actif) pour un sprite affine : PA/PB/PC/PD et
    position recalculés CHAQUE FRAME depuis le transform du sprite
    (`OamEntry.rotation/scale_x/scale_y`, self.sprite_*) via gba_sincos (cf. runtime_api_inline.h), même formule que la
    matrice GBA 8.8 (PA=cos/scale_x, PB=sin/scale_x, PC=-sin/scale_y,
    PD=cos/scale_y, évaluée en C avec des Q8).

    Un acteur n'a ni rotation ni échelle : le centre du cadre est `actor.position + offset + demi-cadre`, l'offset
    décalant le cadre du sprite depuis la position de l'acteur (il ne s'inverse pas avec le flip du sprite ; le sprite
    n'a pas de position monde).

    Rotation, échelle et flip (échelle -1, ici le signe de pa/pb/pc/pd)
    s'exercent autour du POINT DE PIVOT (`sprite.pivot_x/y`, depuis le centre
    du cadre ; (0,0) = le centre, comme sur GBA native).

    `screen_space` retire la soustraction de caméra (cf. Actor.screen_space).

    Aucune matrice n'est réservée au build, pour un acteur posé comme pour un né : le sprite prend sa matrice à la
    frame, quand il est dessiné, comme il prend le prochain emplacement d'OAM. Une matrice IDENTIQUE déjà écrite dans
    cette frame est reprise (dix pièces qui tournent pareil coûtent une matrice, pas dix) ; sinon la suivante (`_affn`)
    est prise. `OamEntry.affine_slot` retient celle de cette frame.
    L'appelant a déjà vérifié qu'il en reste (cf. `gen_sprite._oam_body_lines`).

    Le calcul vit dans le runtime (`oam_write_affine`, `runtime_api_inline.h`), en un seul exemplaire en IWRAM : ces
    lignes ne font que l'appeler avec les constantes du sprite. Déroulé dans chaque cas du rendu, il coûtait près de
    3 Ko par type affine."""
    e = idx if entry is None else entry   # entrée OAM ; `idx` reste l'acteur
    cam = "0,0" if screen_space else "cam_x,cam_y"
    return [f"        _oamn=oam_write_affine(&g_actors[{idx}],&g_oam_entries[{e}],&g_aff_cache[{e}],_oamn,&_affn,{cam},"
            f"{sprite.frame_w},{sprite.frame_h},{bt},{sprite.tiles_per_frame},{sprite.oam_shape},{sprite.oam_size});"]


def pool_affine(p, owner):
    """L'entrée affine d'un porteur (la racine ou une partie) d'un modèle NÉ, ou None : comme pour un posé, il est
    affine si SON sprite a la case cochée, sa matrice prise à la frame (cf. `affine_oam_lines`)."""
    return affine_entry(affine_sprite_component(owner), names=_var_names(p))


def affine_init_fields(entry: dict | None) -> dict:
    """Transform local du sprite. Le numéro de matrice est attribué au rendu."""
    if entry is None:
        return {"affine_slot": -1}
    return {
        "affine_slot": 0,
        "rotation": entry["sprite_rotation"],
        "scale_x": entry["sprite_scale_x"],
        "scale_y": entry["sprite_scale_y"],
        **{field: entry[field] for field in ("offset_x", "offset_y", "pivot_x", "pivot_y")},
    }
