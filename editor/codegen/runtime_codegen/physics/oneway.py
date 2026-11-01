"""La condition de traversée d'une face à sens unique, écrite UNE fois pour tous ses lecteurs C.

La carte de collision (`resolve_actor_tiles`) et les acteurs (`block_push_one_way`) décident de la même chose :
une boîte qui franchit une face contre sa normale est arrêtée, une boîte qui vient de l'autre côté passe. Les deux
lisent cette fonction ; elle ne dépend que de la normale, jamais de l'axe Y.
"""
from __future__ import annotations


def oneway_common_lines() -> list[str]:
    """Aide C partagée. Gardée par une macro : la carte et les acteurs l'émettent chacun, dans le même fichier."""
    return [
        "#ifndef BS_ONEWAY_COMMON",
        "#define BS_ONEWAY_COMMON",
        "/* Face à sens unique : `dir` est sa NORMALE (1 haut, 2 bas, 3 gauche, 4 droite), le côté d'où l'on vient se",
        "   poser. Le bord d'une boîte qui regarde la face est son bas (1), son haut (2), son bord droit (3) ou son",
        "   bord gauche (4), en pixels et exclusif en bas et à droite : (t+h), t, (l+w), l. La face est à la coordonnée",
        "   `face` sur le même axe.",
        "   La face n'arrête que la boîte qui était, AVANT le déplacement, entièrement du côté ouvert : bord <= face",
        "   pour un haut ou un gauche, bord >= face pour un bas ou un droite. Une boîte déjà au-delà la traverse. */",
        "static int __attribute__((unused)) oneway_open(u8 dir,int edge,int face){",
        "    return (dir&1) ? edge<=face : edge>=face;",
        "}",
        "static int __attribute__((unused)) oneway_edge(u8 dir,int l,int t,int r,int b){",
        "    return dir==1 ? b : dir==2 ? t : dir==3 ? r : l;",
        "}",
        "static int __attribute__((unused)) oneway_face(u8 dir,int l,int t,int r,int b){",
        "    return dir==1 ? t : dir==2 ? b : dir==3 ? l : r;",
        "}",
        "#endif",
    ]
