"""runtime_codegen/main_checks.py — les contrôles bloquants de `generate_main`, avant d'écrire une ligne de C.

Ce qui ne se verrait qu'à l'exécution, chez le joueur, fait échouer le build ici : tuiles OBJ, SRAM, parenté.
L'avertissement sur l'affine d'un enfant ne bloque pas."""
from __future__ import annotations

from core.diagnostic import build_error, build_warning
from core.models.components import affine_sprite_component
from codegen.runtime_codegen.gen_affine import compute_affine_info
from codegen.runtime_codegen.gen_save import save_fatal
from codegen.runtime_codegen.gen_scene_query import parent_depths


def check_main(p, all_scene_data: list[dict], obj_alloc: dict, obj_text_tile: int, any_obj_ui: bool, emit) -> bool:
    """False si une faute bloque le build (déjà rapportée par `emit`)."""
    # Débordement : BLOQUANT, et calculé même sans `emit` — sinon la ROM se
    # construit avec des slots hors des 128 du matériel, rien à l'écran et
    # aucune erreur (le fond de conteneur en sprites rend le cas trivial : un
    # conteneur 224×48 pavé d'une frame 8×8 réclame 168 slots à lui seul).
    _fatal: list[str] = []
    # Le débordement OAM par scène (acteurs + UI + pools > 128) est la faute du
    # BUDGET, gardée en un SEUL endroit : le validateur (`_check_actor_budget`,
    # ERREUR bloquante, même source `scene_oam_layout`). `generate_main` n'est
    # atteint qu'après une validation sans erreur (cf. rom_build) — le
    # re-contrôler ici dédoublait la règle. Reste la faute des TUILES (VRAM),
    # qui n'est pas dans le budget OAM.
    # Tuiles OBJ (VRAM) : union projet, cap selon le mode bitmap le plus
    # contraint (la VRAM BG y empiète sur l'espace sprite : 512 au lieu de 1024).
    if any_obj_ui:
        _tiles_need = max((pl["tile_rel"] + pl["tiles"] for pl in obj_alloc.values()),
                          default=0)
        _cap = 512 if any(getattr(sc, "render_mode", 0) in (3, 4, 5)
                          for sc in p.scenes) else 1024
        if obj_text_tile + _tiles_need > _cap:
            _fatal.append(
                f"the text zones as sprites need {_tiles_need} OBJ tiles after "
                f"{obj_text_tile} of sprites, which is more than the {_cap} available.")
    # Débordement de la SRAM, ou deux variables persistantes indiscernables :
    # même règle que ci-dessus, ça bloque. Une sauvegarde qui déborde ne se
    # verrait qu'à l'exécution, chez le joueur.
    _fatal += save_fatal(p)
    # Parenté : un parent inconnu ou un cycle empêchent de
    # calculer une profondeur, donc d'ordonner la frame. Bloquant comme le
    # budget de tuiles, et pour la même raison — ça ne se verrait qu'en jouant.
    for _d in all_scene_data:
        _fatal += parent_depths(_d["scene_actors"])[1]
    # Un enfant hérite de la rotation et de l'échelle de son parent — mais il
    # ne peut les AFFICHER que s'il a un slot affine, le sien ou celui du
    # parent partagé. Il n'en partage pas quand il a un transform propre, et
    # il n'en réserve pas sans « Affine transform » : la composition serait
    # alors calculée puis ignorée à l'écran. Un avertissement et non une
    # erreur — le jeu tourne, c'est l'affichage qui ment.
    if emit:
        for _d in all_scene_data:
            _sa = _d["scene_actors"]
            _aff = compute_affine_info(0, _sa)
            _by = {a.name: a for a, _ in _sa}
            for _j, (_a, _sp) in enumerate(_sa):
                _par = _by.get(getattr(_a, "parent", None) or "")
                if not _par or _j in _aff or not affine_sprite_component(_a):
                    continue
                _par_sc = affine_sprite_component(_par)
                if not bool(getattr(_par_sc, "affine_transform", False)):
                    continue
                emit("diagnostic", build_warning(
                    f"its parent '{_par.name}' can rotate or scale, but "
                    f"'{_a.name}' has no affine slot — it does not share the parent's (it "
                    "has its own rotation or scale) and reserves none. Tick \"Affine "
                    f"transform\" on the sprite of '{_a.name}' to make it follow.",
                    "scene", actor=_a.name))
    if _fatal:
        for _m in _fatal:
            if emit:
                emit("diagnostic", build_error(_m, "build"))
        return False
    return True
