"""Disposition des images de sprites, commune aux budgets, à grit et aux animations C."""
from __future__ import annotations

from core.models.sprite import AnimFrame, SpriteAsset, StateDirection
from core.project import Project


def count_frames(p: Project, sprite: SpriteAsset) -> int:
    """Nombre de frames uniques (dédupliquées) que grit convertit réellement pour ce sprite."""
    _, ordered = sprite_unique_frames(sprite)
    return max(1, len(ordered))


def _frame_key(frame: "AnimFrame") -> tuple:
    """Clé hashable identifiant la composition d'une frame (tuiles + positions
    + flip par tuile — deux frames identiques sauf pour une tuile retournée
    doivent être traitées comme distinctes)."""
    return tuple(sorted(
        (t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
        for t in frame.tiles
    ))


def seq_key(src_sd: "StateDirection", flip_h: bool, flip_v: bool) -> tuple:
    """Clé hashable d'une séquence d'animation : compositions de ses frames
    (dans l'ordre) + flip appliqué. Deux directions produisant exactement la
    même suite de frames retournées de la même façon partagent un bloc."""
    return (tuple(_frame_key(f) for f in src_sd.frames), flip_h, flip_v)


def sprite_unique_frames(sprite: SpriteAsset) -> tuple[dict, list]:
    """Layout du sheet reconstruit : chaque séquence (state,direction) occupe un
    bloc CONTIGU de frames. C'est impératif — le runtime joue une direction via
    `frame = start + k` (k = 0..count-1) sur une plage contiguë ; dédupliquer au
    niveau frame casserait cette contiguïté (séquences non séquentielles →
    frames erronées / hors limites dans la loop). On déduplique donc au niveau
    séquence entière : deux directions identiques (mêmes frames + même flip,
    ex. une source et son omni) partagent le même bloc, mais une frame répétée
    dans une même séquence (ping-pong A,B,C,B) est stockée telle quelle pour
    rester contiguë.

    Fait autorité sur l'ordre des frames pour le sheet reconstruit
    (build_sprite_sheet_indexed) ET les tables d'animation C
    (gen_sprite.anim_tables_for) — les deux partagent ce layout.

    Retourne (seq_starts, ordered) où seq_starts[seq_key] = offset de départ du
    bloc dans ordered, et ordered = [(AnimFrame, flip_h, flip_v), ...] dans
    l'ordre du sheet."""
    seq_starts: dict[tuple, int] = {}
    ordered: list = []
    for state in sprite.states:
        dir_map = {sd.dir: sd for sd in state.directions}
        for sd in state.directions:
            src_sd = dir_map.get(sd.mirror_of, sd) if sd.mirror_of is not None else sd
            key = seq_key(src_sd, sd.flip_h, sd.flip_v)
            if key not in seq_starts:
                seq_starts[key] = len(ordered)
                for f in src_sd.frames:
                    ordered.append((f, sd.flip_h, sd.flip_v))
    return seq_starts, ordered
