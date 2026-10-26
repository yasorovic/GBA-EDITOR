"""runtime_codegen/gen_declarations.py — l'en-tête de main.c : les includes (union de toutes les scènes) et les
`extern` des fonctions de script que main.c appelle."""
from __future__ import annotations

from codegen.c_names import sym as c_sym, scene_actor_sym
from codegen.runtime_codegen.gen_scene_query import actor_script, ui_image_sprites


def include_lines(p, all_scene_data: list[dict], scene_bgi: list[list[dict]], prefab_actor_sprites: list,
                  has_sound: bool, soundbank_h) -> list[str]:
    """Les `#include` de main.c, sans doublon, dans l'ordre : moteur, son, puis fonds et sprites par scène."""
    L: list[str] = []
    seen_incs: set[str] = set()

    def _add_inc(line: str):
        if line not in seen_incs:
            seen_incs.add(line)
            L.append(line)

    _add_inc('#define GBA_ENGINE_IMPL')
    _add_inc('#include "gba_engine.h"')
    _add_inc('#include "runtime_api.h"')
    _add_inc('#include "globals.h"')
    _add_inc('#include "constants.h"')
    _add_inc('#include "gba_debug.h"')   # mesure de budget par frame
    if has_sound and soundbank_h.exists():
        _add_inc('#include <maxmod.h>')
        _add_inc(f'#include "{soundbank_h.name}"')
        _add_inc('#include "soundbank.bin.h"')

    for d, bgi_d in zip(all_scene_data, scene_bgi):
        for bi in bgi_d:
            _add_inc(f'#include "{bi["sym"]}.h"')
        # Tables d'images des fonds animés — un header par scène, toujours émis
        # (vide si la scène n'en pose aucun), pour que l'include ne dépende pas
        # d'un état que le générateur devrait deviner.
        from codegen.bg_anim import scene_anim_sym, shared_anim_sym
        _add_inc(f'#include "{scene_anim_sym(d["scene"])}.h"')
        _add_inc(f'#include "{shared_anim_sym(d["scene"])}.h"')
        for _, sprite in d["scene_actors"]:
            if sprite and sprite.asset:
                _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')

    for _, sprite in prefab_actor_sprites:
        if sprite and sprite.asset:
            _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')

    # Les sprites des IMAGES d'interface ne sont portés par aucun acteur ni
    # prefab, mais leurs tuiles partent en VRAM OBJ par le même chemin (cf.
    # `ui_image_sprites`) : leur header grit doit être inclus au même titre.
    # Sans ça, un sprite utilisé UNIQUEMENT par une image d'UI compilait sur
    # « 'sprite_XTiles' undeclared » — le cas restait masqué tant qu'un acteur
    # partageait le sprite et amenait l'include avec lui.
    for _, sprite in ui_image_sprites(p):
        if sprite and sprite.asset:
            _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')
    return L


def extern_lines(p, all_scene_data: list[dict], scene_pis: list, actor_defined_events: dict[str, set[str]] | None
                 ) -> list[str]:
    """Externs actors + scènes (filtrés sur les events réellement implémentés)."""
    L: list[str] = []
    def _def(sym, ev):
        """True si l'event est défini dans le script Lua de cet actor."""
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    for d, _spi in zip(all_scene_data, scene_pis):
        sc = d["scene"]
        sc_sym = c_sym(sc.name)
        # Une instance posée d'un modèle n'a pas de code à elle : ses appels vont au modèle.
        _members = {d["scene_actors"][j][0].name for pl in _spi for j in pl["members"]}
        for actor, _ in d["scene_actors"]:
            if actor.name in _members:
                continue
            s = scene_actor_sym(sc.name, actor.name)
            script_path = actor_script(actor)
            if script_path:
                abs_sp = p.asset_abs(script_path)
                if abs_sp and abs_sp.suffix.lower() == ".lua":
                    for ev in ("on_start", "on_update", "on_late_update", "on_tile_collide",
                               "on_collision_enter", "on_collide", "on_collision_exit", "on_interact"):
                        if _def(s, ev):
                            if ev == "on_tile_collide":
                                L.append(f"extern void {s}_{ev}(Actor*,int,int);")
                            elif ev == "on_interact":
                                L.append(f"extern void {s}_{ev}(Actor*,Actor*);")
                            elif ev in ("on_collision_enter", "on_collide", "on_collision_exit"):
                                L.append(f"extern void {s}_{ev}(Actor*,Actor*,u8,u8);")
                            else:
                                L.append(f"extern void {s}_{ev}(Actor*);")
        if getattr(sc, "script", ""):
            L += [
                f"extern void {sc_sym}_scene_on_start(void);",
                f"extern void {sc_sym}_scene_on_update(void);",
                f"extern void {sc_sym}_scene_on_late_update(void);",
            ]
    L.append("")
    return L
