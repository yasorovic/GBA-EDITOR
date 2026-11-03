"""Émission des contacts entre colliders."""
from __future__ import annotations


def box_contact_lines(a_expr: str, b_expr: str, active: str, prev: str,
                      events_a: list, events_b: list, indent: str, allowed: int = 0xFFFF) -> list[str]:
    """Les contacts d'UNE paire d'acteurs, un par couple de tags de colliders.

    `actors_overlap_mask` rend un bit par couple de tags en contact ; `prev` en
    garde le souvenir d'une frame à l'autre. Un contact qui naît appelle
    `on_collision_enter`, un contact qui dure `on_collide`, un contact qui se
    défait `on_collision_exit` — chacun avec les tags de CE couple. Une paire
    d'acteurs porte donc plusieurs contacts à la fois (pieds contre tête ET corps
    contre corps) sans que le premier masque les suivants.

    `events_a` / `events_b` : (événement, fonction C) que reçoit chaque côté ;
    `my_box` d'un côté est la `other_box` de l'autre."""
    def calls(events: list, event: str, self_expr: str, other_expr: str,
              self_tag: str, other_tag: str) -> list[str]:
        return [f"{fn}({self_expr},{other_expr},{self_tag},{other_tag});"
                for ev, fn in events if ev == event]

    i = indent
    lines = [
        f"{i}if({active}) debug_physics_contact_test();",
        f"{i}{{ u16 _cur=({active})?actors_overlap_mask({a_expr},{b_expr},{allowed}):0; u16 _prv={prev};",
        f"{i}  if(_cur|_prv)",
        f"{i}  for(u8 _bi=0;_bi<MAX_BOXES;_bi++) for(u8 _bj=0;_bj<MAX_BOXES;_bj++){{",
        f"{i}      u16 _m=(u16)(1u<<(_bi*MAX_BOXES+_bj));",
        f"{i}      u8 _c=(_cur&_m)!=0, _p=(_prv&_m)!=0;",
        f"{i}      if(!_c&&!_p) continue;",
        f"{i}      u8 _ta=({a_expr})->collision.boxes[_bi].tag, _tb=({b_expr})->collision.boxes[_bj].tag;",
        f"{i}      (void)_ta; (void)_tb;",
    ]
    for cond, event in (("_c&&!_p", "on_collision_enter"),
                        ("_c&&_p", "on_collide")):
        calls_a = calls(events_a, event, a_expr, b_expr, "_ta", "_tb")
        calls_b = calls(events_b, event, b_expr, a_expr, "_tb", "_ta")
        if calls_a or calls_b:
            lines.append(f"{i}      if({cond}){{ " + " ".join(calls_a + calls_b) + " }")

    exit_a = calls(events_a, "on_collision_exit", a_expr, b_expr, "_ta", "_tb")
    exit_b = calls(events_b, "on_collision_exit", b_expr, a_expr, "_tb", "_ta")
    if exit_a or exit_b:
        lines.append(f"{i}      if(!_c&&_p){{")
        # Détruire est terminal : aucun des deux scripts n'apprend un `exit`.
        # Désactiver ne l'est pas : seul le partenaire encore actif est averti.
        if exit_a:
            lines.append(f"{i}        if(({a_expr})->active&&({a_expr})->alive&&({b_expr})->alive){{ "
                         + " ".join(exit_a) + " }")
        if exit_b:
            lines.append(f"{i}        if(({b_expr})->active&&({b_expr})->alive&&({a_expr})->alive){{ "
                         + " ".join(exit_b) + " }")
        lines.append(f"{i}      }}")
    lines += [f"{i}  }}", f"{i}  {prev}=_cur; }}"]
    return lines
