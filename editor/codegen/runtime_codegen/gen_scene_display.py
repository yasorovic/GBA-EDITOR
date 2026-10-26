"""runtime_codegen/gen_scene_display.py — les registres d'affichage qu'une scène pose dans `scene_init` : DISPCNT,
mélange de couleurs (BLDCNT, BLDALPHA, BLDY) et windows (WIN0, WIN1, fenêtre-objet).

L'ordre est une contrainte du matériel : les windows se posent APRÈS DISPCNT (cf. `scene_display_lines`)."""
from __future__ import annotations

from codegen.runtime_codegen.gen_camera import project_cameras
from codegen.window_alloc import scene_window_layout


def scene_display_lines(p, scene, dispcnt: int, cam_idx: int, emit=None) -> list[str]:
    """DISPCNT, puis le mélange, puis les windows (le cadre de la caméra compris)."""
    L: list[str] = []
    # DISPCNT
    L.append(f"    dispcnt_set(0x{dispcnt:04X});")
    # Mélange de couleurs (BLDCNT/BLDALPHA/BLDY) — rien d'émis en mode « aucun » :
    # `display_reset()` a déjà remis les trois registres à zéro, et le défaut
    # doit rester littéralement gratuit.
    L += blend_lines(scene, emit)
    # Windows (WIN0/WIN1/fenêtre-objet) — mêmes fonctions runtime que l'API Lua
    # window.* : un script peut reconfigurer/désactiver ensuite (dernier écrivain
    # gagne, pas de mécanisme séparé). Rien n'est émis si la scène n'a aucune
    # window authorée (display_reset() a déjà tout remis à « aucune window active »).
    #
    # Rang matériel décidé par l'allocateur (`window_alloc.scene_window_layout`) — ni la caméra ni un
    # WindowSlot ne nomme WIN0/WIN1 lui-même. Le validateur fait échouer le
    # build si la scène demande plus de deux intentions ; ce code suppose donc
    # `layout.overflow` vide (déjà vérifié avant d'arriver ici).
    #
    # IMPÉRATIVEMENT APRÈS dispcnt_set : window_show() pose un bit DISPCNT
    # (13=WIN0, 14=WIN1, 15=OBJWIN) dans la shadow, alors que dispcnt_set()
    # REMPLACE la shadow entière (g_dispcnt_sh = val). Émis avant, l'activation
    # des windows serait silencieusement effacée — la window resterait invisible
    # en jeu alors que tous ses autres registres sont corrects. Ça vaut aussi
    # pour le cadre de la caméra, posé une première fois par camera_switch()
    # PLUS HAUT (avant dispcnt_set) : on le repose ici, sans rappeler
    # camera_switch() en entier (ça rejouerait aussi son on_start).
    _layout = scene_window_layout(p, scene)
    if _layout.camera_slot is not None:
        _start_cam = project_cameras(p)[cam_idx]
        _fw = _start_cam.px('frame_w', p) if _start_cam else 240
        _fh = _start_cam.px('frame_h', p) if _start_cam else 160
        L.append(f"    window_set({_layout.camera_slot}, 0, 0, {_fw}, {_fh});")
        L.append(f"    window_show({_layout.camera_slot}, 1);")
    for ws in getattr(scene, "windows", []):
        # Fenêtre-objet : pas de rectangle, sa forme vient des pixels opaques
        # des sprites en obj_mode=2. Toujours WINR_OBJ (2), jamais disputée.
        # Surtout, window_set() fait `n &= 1` — l'appeler avec 2 écraserait
        # le rectangle de WIN0.
        if ws.is_obj:
            region = 2
        else:
            region = _layout.slot_for(ws.name)
            if region is None:
                continue   # en overflow — jamais censé arriver, cf. validateur
            L.append(f"    window_set({region}, {int(ws.x)}, {int(ws.y)}, {int(ws.w)}, {int(ws.h)});")
        layers = list(getattr(ws, "layers_shown", [True, True, True, True]))
        for bg in range(4):
            on = 1 if (bg < len(layers) and layers[bg]) else 0
            L.append(f"    window_set_layer({region}, {bg}, {on});")
        L.append(f"    window_set_obj({region}, {1 if ws.obj_shown else 0});")
        L.append(f"    window_show({region}, {1 if ws.visible else 0});")
    return L


def blend_lines(scene, emit=None) -> list[str]:
    """Configuration du mélange de couleurs d'une scène.

    Les mêmes fonctions que l'API Lua `blend.*` : un script peut reconfigurer
    ensuite, dernier écrivain gagne — pas de second mécanisme.

    L'ordre suit le matériel : les CIBLES d'abord (BLDCNT bits 0-5 et 8-13),
    le MODE ensuite (bits 6-7), les coefficients en dernier. `blend_set_mode`
    n'écrase que son champ, donc l'ordre n'est pas critique — mais le lire dans
    l'ordre du registre évite de se demander s'il l'est.

    Rien n'est émis en mode « aucun » : `display_reset()` a déjà tout remis à
    zéro. Une scène sans mélange ne paie donc pas une instruction."""
    from core.models.scene import (BLEND_NONE, BLEND_ALPHA, BLEND_TOP,
                                   BLEND_BOTTOM, BLEND_NEEDS_BOTTOM,
                                   blend_role_of)
    mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
    if mode == BLEND_NONE:
        return []
    L: list[str] = []
    sides = {BLEND_TOP: 0, BLEND_BOTTOM: 1}
    for layer in getattr(scene, "background_layers", []):
        role = blend_role_of(layer)
        if role:
            L.append(f"    blend_set_layer({sides[role]}, {layer.bg_slot}, 1);"
                     f"   /* BG{layer.bg_slot} — {'dessus' if role == BLEND_TOP else 'dessous'} */")
    for attr, fn in (("blend_obj_role", "blend_set_obj"),
                     ("blend_backdrop_role", "blend_set_backdrop")):
        role = getattr(scene, attr, "")
        if role in sides:
            L.append(f"    {fn}({sides[role]}, 1);")
    L.append(f"    blend_set_mode({mode});")
    if mode == BLEND_ALPHA:
        L.append(f"    blend_set_alpha({int(scene.blend_eva)}, {int(scene.blend_evb)});")
    else:
        # Les modes 2 et 3 n'emploient QUE le dessus, et leur intensité vient de
        # BLDY — écrire BLDALPHA ici ne ferait rien du tout.
        L.append(f"    blend_set_fade({int(scene.blend_evy)});")
    if emit:
        names = {1: "alpha", 2: "lighten", 3: "assombrir"}
        tops = [f"BG{l.bg_slot}" for l in scene.blend_layers(BLEND_TOP)]
        bots = [f"BG{l.bg_slot}" for l in scene.blend_layers(BLEND_BOTTOM)]
        if getattr(scene, "blend_obj_role", "") == BLEND_TOP: tops.append("OBJ")
        if getattr(scene, "blend_obj_role", "") == BLEND_BOTTOM: bots.append("OBJ")
        if getattr(scene, "blend_backdrop_role", "") == BLEND_TOP: tops.append("backdrop")
        if getattr(scene, "blend_backdrop_role", "") == BLEND_BOTTOM: bots.append("backdrop")
        detail = f"top {', '.join(tops) or '(none)'}"
        if mode in BLEND_NEEDS_BOTTOM:
            detail += f", bottom {', '.join(bots) or '(none)'}"
        emit("log_line", f"[blend] scene '{scene.name}': {names.get(mode, mode)} — {detail}")
    return L


def scene_dispcnt(p, scene, bgi: list[dict], has_sprites: bool) -> int:
    """DISPCNT de départ : chaque slot d'UI de la scène (plusieurs possibles), chaque fond, et les sprites."""
    bg_bits = {0: 0x0100, 1: 0x0200, 2: 0x0400, 3: 0x0800}
    dispcnt = 0
    for us in p.scene_ui_bg_slots(scene):
        dispcnt |= bg_bits.get(us, 0)
    if bgi:
        for bi in bgi:
            dispcnt |= bg_bits.get(bi["bg"], 0)
    if has_sprites:
        dispcnt |= 0x1040
    return dispcnt
