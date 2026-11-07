"""Liens parent-enfant des acteurs posés et des parties de prefabs spawnés."""
from __future__ import annotations

import math

from codegen.runtime_codegen.gen_scene_query import parent_depths
from core.models.field_value import number_value as _number_value


def local_transform(child, ref, ref_x: int, ref_y: int) -> tuple[int, int, int, int, int]:
    """Le transform LOCAL de `child` dans le repère de `ref` : (ox, oy Q8, rotation en degrés, sx, sy Q8).

    L'auteur pose en coordonnées MONDE ; le build en tire le local, et la composition du runtime (`slot_compose`), appliquée
    à la pose authorée du parent, redonne exactement la pose authorée de l'enfant : la scène de l'éditeur est la frame 0 du
    jeu. C'est l'inverse de la composition : on défait la rotation du parent, puis son échelle. `ref_x`, `ref_y` : la
    position du parent (0, 0 pour la racine d'un prefab, posée à l'origine du template). Tout reste en Q8 jusqu'à l'OAM :
    un arrondi par niveau ferait dériver un bras d'un pixel par cran de profondeur."""
    p_rot = float(_number_value(getattr(ref, "rotation", 0)) or 0)
    p_sx = float(_number_value(getattr(ref, "scale_x", 1.0), ref_divisor=100) or 1.0) or 1.0
    p_sy = float(_number_value(getattr(ref, "scale_y", 1.0), ref_divisor=100) or 1.0) or 1.0
    dx, dy = float(int(child.x) - ref_x), float(int(child.y) - ref_y)
    th = math.radians(-p_rot)
    ux = dx * math.cos(th) - dy * math.sin(th)
    uy = dx * math.sin(th) + dy * math.cos(th)
    rot = int(_number_value(getattr(child, "rotation", 0)) or 0) - int(round(p_rot))
    sx = int(round(float(_number_value(getattr(child, "scale_x", 1.0), ref_divisor=100) or 1.0) / p_sx * 256))
    sy = int(round(float(_number_value(getattr(child, "scale_y", 1.0), ref_divisor=100) or 1.0) / p_sy * 256))
    return int(round(ux / p_sx * 256)), int(round(uy / p_sy * 256)), rot, sx, sy


def _link_line(indent: str, slot, parent, depth: int, child, local) -> str:
    vis = 1 if getattr(child, "visible", True) else 0
    return f"{indent}actor_link_slot({slot}, {parent}, {depth}, {vis}, {', '.join(map(str, local))});"


def _part_parents(pf) -> list[tuple]:
    """Les parties d'un prefab : (rang k, partie, rang de sa partie parente (0 = la racine), profondeur)."""
    parts = list(getattr(pf, "children", []) or [])
    rank = {pt.name: k for k, pt in enumerate(parts, start=1)}
    par_of = {k: rank.get(getattr(pt, "parent", None) or "", 0) for k, pt in enumerate(parts, start=1)}
    out = []
    for k, pt in enumerate(parts, start=1):
        depth, cur = 0, k
        while cur and depth <= len(parts):       # borne : une chaîne de parties ne revient pas sur elle-même
            depth, cur = depth + 1, par_of[cur]
        out.append((k, pt, par_of[k], depth))
    return out


def part_link_lines(pf, root: str, indent: str) -> list[str]:
    """Les liens des parties d'un modèle né à l'emplacement `root` (une expression C), après leur construction : le
    parent est une autre partie, sinon la racine, et le local se tire de la pose authorée de la partie, dans le monde du
    template posé à l'origine (la racine d'un prefab n'a pas de pose : `spawn(x, y)` décide où)."""
    by_rank = {k: pt for k, pt in enumerate(pf.children, start=1)}
    L = []
    for k, part, p_off, depth in _part_parents(pf):
        ref = by_rank.get(p_off, pf)
        ref_xy = (int(ref.x), int(ref.y)) if p_off else (0, 0)
        L.append(_link_line(indent, f"group_slot({root}, {k})", f"group_slot({root}, {p_off})" if p_off else root,
                            depth, part, local_transform(part, ref, *ref_xy)))
    return L


def link_depth(scene_actors: list, pi: list[dict]) -> int:
    """La profondeur maximale de la hiérarchie d'une scène, posés et parties des modèles qui y naissent : le nombre de
    passes de `slot_compose_all` (`g_slot_depth`). 0 : aucune hiérarchie, ni composition ni cascade."""
    depths, _errs = parent_depths(scene_actors)
    d = max(depths.values(), default=0)
    for m in pi:
        if m["shared"]:
            d = max([d] + [dep for *_, dep in _part_parents(m["prefab"])])
    return d


def placed_link_lines(scene_actors: list, actor_offset: int) -> list[str]:
    """Les liens des acteurs POSÉS qui ont un parent de scène, après leur construction (`scene_init`) : le parent,
    la profondeur et le local, tiré de la pose authorée (`local_transform`). Un parent inconnu ou un cycle ont été
    refusés avant (`parent_depths`)."""
    depths, _errs = parent_depths(scene_actors)
    idx_of = {a.name: actor_offset + j for j, (a, _) in enumerate(scene_actors)}
    by_name = {a.name: a for a, _ in scene_actors}
    L = []
    for j, (a, _) in enumerate(scene_actors):
        par = by_name.get(getattr(a, "parent", None) or "")
        if par is None or a.name not in depths:
            continue
        L.append(_link_line("    ", actor_offset + j, idx_of[par.name], depths[a.name], a,
                            local_transform(a, par, int(par.x), int(par.y))))
    return L
