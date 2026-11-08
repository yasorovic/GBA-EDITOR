"""codegen/runtime_codegen/gen_affine.py : les sprites affines et leurs matrices OAM.

Extrait de `main_gen` (A3), au-dessus de la couche de requêtes : il consomme
`parent_depths` de `gen_scene_query` (vers le bas, sans
cycle). `affine_entry`/`compute_affine_info` rendent de la donnée ; seul
`affine_oam_lines` émet du C (la matrice recalculée et prise à chaque frame).
"""
from __future__ import annotations

from codegen.runtime_codegen.gen_scene_query import parent_depths
from core.models.components import affine_sprite_component
from core.models.field_value import FieldValue, number_c, number_value, var_names_from_project as _var_names


def affine_entry(actor, sc, force: bool = False, names=None) -> dict | None:
    """
    Calcule l'entrée affine d'un Actor + son SpriteComponent.

    Retourne None si le sprite de l'actor n'est pas affine.

    La décision est portée par `SpriteComponent.affine_transform` : coché, le sprite est dessiné en affine (sa
    matrice, une des 32 du matériel, est prise à la frame), même si scale/rotation valent leur défaut. Sans lui, il
    est émis en OAM normale : les champs de transform gardent leur valeur, mais rien ne les affiche.

    Au runtime la matrice est TOUJOURS calculée à partir des champs transform de
    la struct Actor (monde + local composés, cf. actor_types_static.h) — il n'y a
    plus de chemin statique pré-calculé : le rendu lit rotation/scale/offset
    chaque frame (cf. affine_oam_lines).
    """
    # `force` : l'enfant d'un parent affine qui tourne avec lui sans avoir coché `affine_transform`, ou une partie
    # d'un modèle né affine. Il est dessiné en affine avec SES propres décalages de sprite ; sa matrice, identique à
    # celle de son parent, est reprise à la frame (cf. `affine_oam_lines`).
    if not force and not bool(getattr(sc, "affine_transform", False)):
        return None

    return {
        # Valeurs de départ des champs Actor, écrites au scene_init. Monde sur
        # l'actor, local sur le sprite ; le rendu compose rotation (somme) et
        # scale (produit), l'offset étant transformé par la matrice de l'actor.
        # Littéral → int, variable → expression C (assignation à l'init).
        "rotation":   number_c(getattr(actor, "rotation", 0), names),
        "scale_x":    number_c(getattr(actor, "scale_x", 1.0), names, q8=True),
        "scale_y":    number_c(getattr(actor, "scale_y", 1.0), names, q8=True),
        "sprite_rotation":   number_c(getattr(sc, "rotation", 0), names),
        "sprite_scale_x":    number_c(getattr(sc, "scale_x", 1.0), names, q8=True),
        "sprite_scale_y":    number_c(getattr(sc, "scale_y", 1.0), names, q8=True),
        "offset_x":    _offset_value(getattr(sc, "offset_x", 0), names),
        "offset_y":    _offset_value(getattr(sc, "offset_y", 0), names),
        "pivot_x":     _offset_value(getattr(sc, "pivot_x", 0), names),
        "pivot_y":     _offset_value(getattr(sc, "pivot_y", 0), names),
    }


def _is_set(obj, name: str, neutral) -> bool:
    """Le champ s'écarte-t-il de sa valeur neutre ? Une VARIABLE compte comme
    écart : sa valeur n'est pas connue au build, et le rendu affine doit
    pouvoir la recevoir."""
    raw = getattr(obj, name, neutral)
    return isinstance(raw, dict) or number_value(raw, default=neutral) != neutral


def _offset_value(raw, names):
    """Décalage de sprite tel qu'il s'écrit dans le C : un `int` pour un
    littéral (px/tile), l'expression `g_<nom>` pour une variable. Une
    assignation à l'init, donc une variable y est légitime. `names` =
    `var_names_from_project`."""
    fv = FieldValue.parse(raw, names)
    return fv.c_expr() if fv.is_ref else fv.px()


def compute_affine_info(actor_offset: int, scene_actors: list, names=None) -> dict:
    """
    Retourne {indice d'acteur: entry} pour tout actor POSÉ dessiné en affine : son SpriteComponent a
    `affine_transform` coché, ou il tourne avec un parent affine (ci-dessous). L'entrée porte les valeurs de
    départ écrites à l'init ; aucune matrice n'est réservée, le rendu la prend à la frame, comme pour un né.
    """
    result: dict = {}

    idx_of = {a.name: actor_offset + j for j, (a, _) in enumerate(scene_actors)}
    for j, (actor, _) in enumerate(scene_actors):
        sc = affine_sprite_component(actor)
        if not sc:
            continue
        entry = affine_entry(actor, sc, names=names)
        if entry:
            result[actor_offset + j] = entry

    # ── Enfants sans transform propre : ils tournent AVEC le parent ──
    # Une matrice ne contient que pa/pb/pc/pd — la position n'y est pour rien —
    # donc deux OBJ de même rotation et de même échelle peuvent pointer la
    # même. Un enfant qui n'a ni rotation ni échelle propres
    # hérite EXACTEMENT du transform de son parent : sa matrice est la même, et
    # le rendu la reprend au lieu d'en prendre une autre (`affine_oam_lines`).
    # Un boss à six parties qui tourne d'un bloc coûte donc UNE matrice sur 32,
    # pas sept.
    #
    # Sans cela, ces enfants seraient émis en OAM normale et ne
    # tourneraient pas avec leur parent — la composition serait calculée puis
    # ignorée à l'affichage.
    #
    # Deuxième passe : le parent doit déjà être affine, et il peut être déclaré
    # APRÈS l'enfant dans la scène.
    depths, _errs = parent_depths(scene_actors)
    for _pass in range(max(depths.values(), default=0)):
        for j, (actor, _) in enumerate(scene_actors):
            oam = actor_offset + j
            par = getattr(actor, "parent", None)
            if oam in result or not par or par not in idx_of:
                continue
            base = result.get(idx_of[par])
            sc = affine_sprite_component(actor)
            if not base or not sc:
                continue
            if getattr(sc, "affine_transform", False):
                continue          # il est affine de lui-même
            if (_is_set(actor, "rotation", 0)
                    or _is_set(actor, "scale_x", 1.0)
                    or _is_set(actor, "scale_y", 1.0)):
                continue          # transform propre → matrice différente
            # Le transform LOCAL du sprite entre AUSSI dans la matrice
            # (`angle_eff = rotation + sprite_rot`, `scale_eff = scale ×
            # sprite_scale`) : un enfant dont le sprite a sa propre rotation
            # n'a pas la même matrice que son parent, malgré un transform
            # d'acteur neutre.
            if (_is_set(sc, "rotation", 0)
                    or _is_set(sc, "scale_x", 1.0)
                    or _is_set(sc, "scale_y", 1.0)):
                continue
            # Ses PROPRES décalages de sprite : la matrice est partagée, pas la pose.
            entry = affine_entry(actor, sc, force=True, names=names)
            if entry:
                result[oam] = entry

    return result


def scene_has_affine(scene_actors: list, pi: list) -> bool:
    """La scène a-t-elle un sprite affine, posé (`SpriteComponent.affine_transform`) ou né (un modèle dont la racine
    l'est) ? C'est ce qui lui vaut un cache de calcul (`AffCache`) et la matrice dynamique."""
    for actor, _sprite in scene_actors:
        sc = affine_sprite_component(actor)
        if sc and sc.affine_transform:
            return True
    for m in pi:
        sc = affine_sprite_component(m["prefab"])
        if m.get("shared") and sc and sc.affine_transform:
            return True
    return False


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
    position recalculés CHAQUE FRAME depuis les champs transform de la struct
    Actor via gba_sin/gba_cos (cf. runtime_api_inline.h), même formule que la
    matrice GBA 8.8 (PA=cos/scale_x, PB=sin/scale_x, PC=-sin/scale_y,
    PD=cos/scale_y, évaluée en C avec des Q8).

    Composition du transform MONDE de l'actor (self.rotation/self.scale) et du
    transform LOCAL du sprite (self.sprite_*) :
        angle_eff     = rotation + sprite_rot            (somme)
        scale_eff     = scale_x * sprite_scale_x / 256   (produit, Q8)
        centre_eff    = actor.position + R(rotation)·S(scale)·(offset + demi-cadre)
    L'offset vit dans le repère local de l'actor : le cadre entier (son coin
    haut-gauche ET son centre) tourne et scale avec lui, comme un corps rigide
    (mais l'offset ne s'inverse pas avec le flip du sprite). C'est lui qui décale
    le cadre du sprite par rapport à la position monde (l'actor n'a pas l'offset ;
    le sprite n'a pas de position monde).

    Rotation, échelle et flip (échelle -1, ici le signe de pa/pb/pc/pd)
    s'exercent autour du POINT DE PIVOT (`sprite.pivot_x/y`, depuis le centre
    du cadre ; (0,0) = le centre, comme sur GBA native).

    `screen_space` retire la soustraction de caméra (cf. Actor.screen_space).

    Aucune matrice n'est réservée au build, pour un acteur posé comme pour un né : le sprite prend sa matrice à la
    frame, quand il est dessiné, comme il prend le prochain emplacement d'OAM. Une matrice IDENTIQUE déjà écrite dans
    cette frame est reprise (un enfant sans transform propre tourne avec son parent : un boss à six parties coûte une
    matrice, pas sept) ; sinon la suivante (`_affn`) est prise. `OamEntry.affine_slot` retient celle de cette frame.
    L'appelant a déjà vérifié qu'il en reste (cf. `gen_sprite._oam_body_lines`).

    Le calcul vit dans le runtime (`oam_write_affine`, `runtime_api_inline.h`), en un seul exemplaire en IWRAM : ces
    lignes ne font que l'appeler avec les constantes du sprite. Déroulé dans chaque cas du rendu, il coûtait près de
    3 Ko par type affine."""
    e = idx if entry is None else entry   # entrée OAM ; `idx` reste l'acteur
    cam = "0,0" if screen_space else "cam_x,cam_y"
    return [f"        _oamn=oam_write_affine(&g_actors[{idx}],&g_oam_entries[{e}],&g_aff_cache[{e}],_oamn,&_affn,{cam},"
            f"{sprite.frame_w},{sprite.frame_h},{bt},{sprite.tiles_per_frame},{sprite.oam_shape},{sprite.oam_size});"]


def pool_affine(p, root, owner):
    """L'entrée affine d'un porteur (la racine ou une partie) d'un modèle NÉ, ou None.

    Un modèle est affine quand sa racine l'est ; chaque porteur de son groupe qui affiche un sprite est alors
    dessiné en affine, sa matrice prise à la frame (cf. `affine_oam_lines`). Les valeurs de départ sont celles du
    sprite PROPRE du porteur (décalages, pivot, rotation et échelle locales)."""
    sc_root = affine_sprite_component(root)
    if not (sc_root and sc_root.affine_transform):
        return None
    sc = affine_sprite_component(owner)
    if sc is None:
        return None
    return affine_entry(owner, sc, force=True, names=_var_names(p))


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
