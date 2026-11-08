"""Données passées au constructeur C d'un acteur, à l'entrée de scène ou au spawn."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.runtime_codegen.gen_affine import affine_init_fields
from codegen.runtime_codegen.gen_appearance import appearance_init_fields
from codegen.runtime_codegen.gen_sprite import initial_state_rank, resolve_initial_appearance
from codegen.runtime_codegen.interact_gen import owner_boxes
from core.models.field_value import FieldValue, number_c, var_names_from_project
from core.models.palette import OWN_PAL_BANK


def _initial_values(fields: dict) -> str:
    return "{" + ", ".join(f".{key} = {value}" for key, value in fields.items()) + "}"


def actor_init_lines(p, owner, obj_layout, *, slot, entry, name, type_id, position, active,
                     appearance_base, affine, indent) -> list[str]:
    """Émet une commande d'initialisation."""
    component, sprite = resolve_initial_appearance(p, owner)
    names = var_names_from_project(p)
    dx, dy = getattr(owner, "dir_x", 0), getattr(owner, "dir_y", 0)
    x, y = position
    actor = {
        "name": name,
        "type_id": type_id,
        "x": f"({x}) * 256",
        "y": f"({y}) * 256",
        "active": int(active),
        "dir_x": dx,
        "dir_y": dy,
        "facing_x": dx,
        "facing_y": dy,
    }
    boxes = []
    for box in owner_boxes(owner, sprite):
        fields = {key: FieldValue.parse(getattr(box, key), names).c_expr()
                  for key in ("x", "y", "w", "h")}
        fields.update(solid=int(box.solid), active=int(box.active),
                      tag="BOXTAG_" + c_sym(box.tag or "body").upper())
        boxes.append(_initial_values(fields))
    if boxes:
        actor["collision"] = _initial_values({
            "box_count": len(boxes), "boxes": "{" + ", ".join(boxes) + "}",
        })
    # Le littéral peut dépendre des variables du jeu. Son bloc borne la durée
    # de vie du temporaire pour que le compilateur réutilise la pile entre appels.
    out = [f"{indent}{{", f"{indent}    actor_init_slot({slot}, {entry},",
           f"{indent}        &(const Actor){_initial_values(actor)},"]
    if entry == -1:
        return [*out, f"{indent}        0);", f"{indent}}}"]

    own = list(sprite.own_palette) if sprite and sprite.own_palette else []
    pal = obj_layout.bank_index(getattr(owner, "pal_bank", OWN_PAL_BANK), own) if obj_layout else 0
    display = {
        "visible": int(getattr(owner, "visible", True)),
        "flip_h": int(getattr(owner, "flip_h", False)),
        "flip_v": int(getattr(owner, "flip_v", False)),
        "screen_space": int(getattr(owner, "screen_space", False)),
        "pal_bank": pal or 0,
        "obj_mode": int(getattr(owner, "obj_mode", 0)) & 3,
        "priority": number_c(getattr(owner, "priority", 0), names, mask=3),
        "facing_auto": int(getattr(component, "facing_auto", True)),
        "anim_state": initial_state_rank(component, sprite),
        "frame_w": sprite.frame_w if sprite else 0,
        "frame_h": sprite.frame_h if sprite else 0,
        **affine_init_fields(affine),
    }
    display.update(appearance_init_fields(p, owner, appearance_base))
    return [*out, f"{indent}        &(const OamEntry){_initial_values(display)});", f"{indent}}}"]
