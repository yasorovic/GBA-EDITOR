"""codegen/runtime_codegen/gen_affine.py — les slots de matrice affine OAM.

Extrait de `main_gen` (A3), au-dessus de la couche de requêtes : il consomme
`parent_depths` de `gen_scene_query` (vers le bas, sans
cycle). `affine_entry`/`compute_affine_info` rendent de la donnée ; seul
`affine_oam_lines_dynamic` émet du C (la matrice recalculée chaque frame).
"""
from __future__ import annotations

from codegen.runtime_codegen.gen_scene_query import parent_depths
from core.models.components import affine_sprite_component


def affine_entry(actor, sc, slot: int, force: bool = False) -> dict | None:
    """
    Calcule l'entrée affine d'un Actor + son SpriteComponent.

    Retourne None si l'actor ne réserve pas de slot affine.

    La décision est portée par `SpriteComponent.affine_transform` (cf.
    ARCHITECTURE.md « Le modèle affine ») : coché → un des 32 slots hardware est
    réservé, même si scale/rotation valent leur défaut. Sans lui, aucun slot
    n'est alloué et le sprite est émis en OAM normale — les champs de transform
    gardent leur valeur, mais rien ne les affiche.

    Au runtime la matrice est TOUJOURS calculée à partir des champs transform de
    la struct Actor (monde + local composés, cf. actor_types_static.h) — il n'y a
    plus de chemin statique pré-calculé : le rendu lit rotation/scale/offset
    chaque frame (cf. affine_oam_lines_dynamic).
    """
    # `force` : l'enfant d'un parent affine qui PARTAGE son slot (ROADMAP
    # v0.23). Il n'a pas coché `affine_transform` — il n'en réserve aucun — mais
    # il lui faut la même entrée pour être émis en OAM affine sur le slot du
    # parent, avec SES propres décalages de sprite.
    if not force and not bool(getattr(sc, "affine_transform", False)):
        return None

    return {
        "slot": slot,
        # Valeurs de départ des champs Actor, écrites au scene_init. Monde sur
        # l'actor, local sur le sprite ; le rendu compose rotation (somme) et
        # scale (produit), l'offset étant transformé par la matrice de l'actor.
        "rotation":   int(round(getattr(actor, "rotation", 0))),
        "scale_x":    int(round(getattr(actor, "scale_x", 1.0) * 256)),
        "scale_y":    int(round(getattr(actor, "scale_y", 1.0) * 256)),
        "sprite_rotation":   int(round(getattr(sc, "rotation", 0))),
        "sprite_scale_x":    int(round(getattr(sc, "scale_x", 1.0) * 256)),
        "sprite_scale_y":    int(round(getattr(sc, "scale_y", 1.0) * 256)),
        "offset_x":    int(getattr(sc, "offset_x", 0)),
        "offset_y":    int(getattr(sc, "offset_y", 0)),
    }


def compute_affine_info(actor_offset: int, scene_actors: list, pi: list) -> dict:
    """
    Retourne {oam_idx: entry} pour tout actor dont le SpriteComponent a
    `affine_transform` coché.
    Limité à 32 slots (contrainte hardware GBA OAM).
    """
    result: dict = {}
    slot = 0

    idx_of = {a.name: actor_offset + j for j, (a, _) in enumerate(scene_actors)}
    for j, (actor, _) in enumerate(scene_actors):
        if slot >= 32:
            break
        sc = affine_sprite_component(actor)
        if not sc:
            continue
        entry = affine_entry(actor, sc, slot)
        if entry:
            result[actor_offset + j] = entry
            slot += 1

    # ── Enfants sans transform propre : ils PARTAGENT le slot du parent ──
    # Un slot ne contient que pa/pb/pc/pd — la position n'y est pour rien —
    # donc deux OBJ de même rotation et de même échelle peuvent pointer le
    # même (ROADMAP v0.23). Un enfant qui n'a ni rotation ni échelle propres
    # hérite EXACTEMENT du transform de son parent : sa matrice est la même.
    # Un boss à six parties qui tourne d'un bloc coûte donc UN slot sur 32,
    # pas sept.
    #
    # Sans ce partage, ces enfants seraient émis en OAM normale et ne
    # tourneraient pas avec leur parent — la composition serait calculée puis
    # ignorée à l'affichage.
    #
    # Deuxième passe, après l'attribution : le parent doit déjà avoir le sien,
    # et il peut être déclaré APRÈS l'enfant dans la scène.
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
                continue          # il a demandé le sien, il l'a eu (ou pas : 32)
            if (int(getattr(actor, "rotation", 0) or 0) != 0
                    or float(getattr(actor, "scale_x", 1.0) or 1.0) != 1.0
                    or float(getattr(actor, "scale_y", 1.0) or 1.0) != 1.0):
                continue          # transform propre → matrice différente
            # Le transform LOCAL du sprite entre AUSSI dans la matrice
            # (`angle_eff = rotation + sprite_rot`, `scale_eff = scale ×
            # sprite_scale`) : un enfant dont le sprite a sa propre rotation
            # n'a pas la même matrice que son parent, malgré un transform
            # d'acteur neutre. Il paie alors son slot comme les autres.
            if (int(round(getattr(sc, "rotation", 0) or 0)) != 0
                    or float(getattr(sc, "scale_x", 1.0) or 1.0) != 1.0
                    or float(getattr(sc, "scale_y", 1.0) or 1.0) != 1.0):
                continue
            # Ses PROPRES décalages de sprite, sur le slot du parent : la
            # matrice est partagée, pas la pose.
            entry = affine_entry(actor, sc, base["slot"], force=True)
            if entry:
                result[oam] = entry

    for p2 in pi:
        pf = p2["prefab"]
        sc = affine_sprite_component(pf)
        if not sc:
            continue
        for oam_idx in range(p2["start"], p2["start"] + p2["size"]):
            if slot >= 32:
                break
            entry = affine_entry(pf, sc, slot)
            if entry:
                result[oam_idx] = entry
                slot += 1

    return result


def affine_oam_lines_dynamic(idx: int, aff: dict, sprite, bt: int, priority_expr: str,
                             screen_space: bool = False,
                             entry: int | None = None) -> list[str]:
    """Lignes C (intérieur du if actif) pour un sprite affine : PA/PB/PC/PD et
    position recalculés CHAQUE FRAME depuis les champs transform de la struct
    Actor via gba_sin/gba_cos (cf. runtime_api_inline.h), même formule que la
    matrice GBA 8.8 (PA=cos/scale_x, PB=sin/scale_x, PC=-sin/scale_y,
    PD=cos/scale_y, évaluée en C avec des Q8).

    Composition du transform MONDE de l'actor (self.rotation/self.scale) et du
    transform LOCAL du sprite (self.sprite_*), cf. ARCHITECTURE.md « Le modèle
    affine » :
        angle_eff     = rotation + sprite_rot            (somme)
        scale_eff     = scale_x * sprite_scale_x / 256   (produit, Q8)
        position_eff  = actor.position + R(rotation)·S(scale)·offset
    L'offset vit dans le repère local de l'actor : il tourne ET scale avec lui.
    C'est lui qui décale le sprite par rapport à la position monde (l'actor n'a
    pas l'offset ; le sprite n'a pas de position monde).

    `screen_space` retire la soustraction de caméra (cf. Actor.screen_space)."""
    aslot = aff["slot"]
    W, H   = sprite.frame_w, sprite.frame_h
    sh, sz = sprite.oam_shape, sprite.oam_size
    tpf    = sprite.tiles_per_frame
    dx, dy = -(W // 2), -(H // 2)

    # ROADMAP v0.19 : x/y sont en Q8 en interne (256 = 1 px) ; l'émission OAM
    # est UN des deux seuls points d'arrondi du chantier (l'autre est l'entrée
    # de la collision, cf. resolve_actor_tiles). >>8 tronque vers -inf sur un
    # entier signé avec ce compilateur (ARM/GCC, décalage arithmétique) —
    # cohérent, pas de saut à la traversée de 0.
    e = idx if entry is None else entry   # entrée OAM ; `idx` reste l'acteur
    base_x = f"(g_actors[{idx}].x>>8)" + ("" if screen_space else "-cam_x")
    base_y = f"(g_actors[{idx}].y>>8)" + ("" if screen_space else "-cam_y")

    return [
        # Transform monde + local composés
        f"        int _arot=g_actors[{idx}].rotation;",
        f"        int _srot=g_oam_entries[{e}].rotation;",
        f"        int _ang=_arot+_srot; int _cosA=gba_cos(_ang); int _sinA=gba_sin(_ang);",
        f"        int _asx=g_actors[{idx}].scale_x; int _asy=g_actors[{idx}].scale_y;",
        f"        int _ssx=g_oam_entries[{e}].scale_x; int _ssy=g_oam_entries[{e}].scale_y;",
        f"        int _sxq=_asx*_ssx/256; int _syq=_asy*_ssy/256;",
        f"        int _fh=g_oam_entries[{e}].flip_h; int _fv=g_oam_entries[{e}].flip_v;",
        f"        int _sxs=_fh?-_sxq:_sxq; int _sys=_fv?-_syq:_syq;",
        # Matrice 8.8 (base, sans flip)
        f"        int _pa=_sxq?_cosA*256/_sxq:0; int _pb=_sxq?_sinA*256/_sxq:0;",
        f"        int _pc=_syq?-_sinA*256/_syq:0; int _pd=_syq?_cosA*256/_syq:0;",
        f"        if(!_pa&&!_pb){{_pa=1;}}",
        f"        if(!_pc&&!_pd){{_pd=1;}}",
        # Offset local transformé par la matrice de l'ACTOR (hérarchie) :
        #   ox = R(rotation)·S(scale)·offset, avec le flip déjà dans le signe.
        f"        int _acos=gba_cos(_arot); int _asin=gba_sin(_arot);",
        f"        int _asxs=_fh?-_asx:_asx; int _asys=_fv?-_asy:_asy;",
        f"        int _ofx=(_acos*_asxs*g_oam_entries[{e}].offset_x - _asin*_asys*g_oam_entries[{e}].offset_y)/65536;",
        f"        int _ofy=(_asin*_asxs*g_oam_entries[{e}].offset_x + _acos*_asys*g_oam_entries[{e}].offset_y)/65536;",
        # Position : pivot de rotation au centre texture ; l'offset s'ajoute au monde.
        f"        int _ocx=({base_x})+_ofx; int _ocy=({base_y})+_ofy;",
        f"        int _u=(_cosA*_sxs*({dx}))/65536-(_sinA*_sys*({dy}))/65536;",
        f"        int _v=(_sinA*_sxs*({dx}))/65536+(_cosA*_sys*({dy}))/65536;",
        f"        int sx=_ocx+(-{W}-_u); int sy=_ocy+(-{H}-_v);",
        f"        u16 ti=(u16)({bt}+g_oam_entries[{e}].frame*{tpf});",
        f"        shadow_oam[{aslot*4+0}].dummy=(u16)(s16)(_fh?-_pa:_pa);",
        f"        shadow_oam[{aslot*4+1}].dummy=(u16)(s16)(_fh?-_pb:_pb);",
        f"        shadow_oam[{aslot*4+2}].dummy=(u16)(s16)(_fv?-_pc:_pc);",
        f"        shadow_oam[{aslot*4+3}].dummy=(u16)(s16)(_fv?-_pd:_pd);",
        f"        shadow_oam[{e}].attr0=(sy&0xFF)|(1<<8)|(1<<9)|(g_oam_entries[{e}].obj_mode<<10)|({sh}<<14);",
        f"        shadow_oam[{e}].attr1=(sx&0x1FF)|({aslot}<<9)|({sz}<<14);",
        f"        shadow_oam[{e}].attr2=(ti&0x3FF)|({priority_expr}<<10)|(g_oam_entries[{e}].pal_bank<<12);",
    ]
