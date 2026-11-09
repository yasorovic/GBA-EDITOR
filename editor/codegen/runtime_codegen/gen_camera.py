"""codegen/runtime_codegen/gen_camera.py : la table des caméras et le suivi.

Extrait de `main_gen` (A3). `scene_cameras_indexed` est l'ordre de vérité de la
table runtime : la table, `headers.py` (les `#define CAM_*`) et les colonnes de
données en dérivent, sinon `camera.switch` viserait la mauvaise caméra.
`project_cameras` en est la vue à plat, entrée 0 comprise.
"""
from __future__ import annotations

from codegen.c_names import sym as c_sym


def camera_sym(scene_name: str, name: str) -> str:
    """Symbole C d'une caméra : préfixé, les caméras et les acteurs partageant
    le même espace de noms C, et qualifié par sa scène, le nom d'une caméra
    étant local à sa scène (deux scènes peuvent chacune avoir sa « Camera »)."""
    return f"camera_{c_sym(scene_name)}_{c_sym(name)}"


def scene_cameras_indexed(p) -> list:
    """(index dans la table runtime, scène, caméra) pour chaque caméra du projet : les scènes dans leur ordre, puis
    `Scene.cameras`. L'index 0 est réservé à la caméra par défaut. Ce qui a besoin de la scène d'une caméra (sa
    constante, son symbole) la lit ici plutôt que de refaire l'ordre."""
    out = []
    for s in p.scenes:
        for c in s.cameras:
            out.append((len(out) + 1, s, c))
    return out


def project_cameras(p) -> list:
    """Les caméras du projet dans l'ordre de la TABLE runtime, `None` en tête.

    Ce `None` est la caméra par défaut : fixe à l'origine, sans bornes ni
    suivi, et sans entrée dans aucune scène — une scène qui n'en désigne
    aucune tombe dessus. La donner comme entrée 0 plutôt que comme cas
    particulier évite un `if` à chaque endroit qui active une caméra.

    Même ordre que `scene_cameras_indexed`, dont elle dérive."""
    return [None] + [c for _i, _s, c in scene_cameras_indexed(p)]


def scene_camera_index(p, scene) -> int:
    """Index de la caméra de démarrage d'une scène dans la table runtime.

    Cherchée parmi les caméras de CETTE scène seulement : une autre scène peut
    avoir une caméra du même nom. Un nom qui ne résout pas retombe sur 0 (la
    caméra par défaut) plutôt que de faire échouer le build : le validateur
    signale la référence cassée, et un jeu qui compile encore reste débuggable."""
    name = getattr(scene, "camera", "")
    if not name:
        return 0
    return next((i for i, s, c in scene_cameras_indexed(p) if s is scene and c.name == name), 0)


def camera_target_index(camera, scene_actors: list, actor_offset: int) -> int:
    """Index dans `g_actors` de l'acteur suivi par cette caméra, ou -1.

    Simplifié le 2026-08-24 : une caméra n'appartient plus qu'à UNE scène, sa
    cible se résout donc toujours dans les acteurs de CETTE scène — plus de
    couple (scène, caméra) à lever, `scene_actors` est déjà la bonne liste."""
    if camera is None or camera.mode != "follow" or not camera.follow_target:
        return -1
    local = next((j for j, (a, _) in enumerate(scene_actors)
                  if a.name == camera.follow_target), None)
    return -1 if local is None else actor_offset + local


def camera_follow_lines(p, scene, scene_actors: list, actor_offset: int) -> list[str]:
    """Le suivi déclaratif de la frame, pour la caméra ACTIVE.

    Un `switch` plutôt qu'une table de cibles lue au runtime : la cible et la
    zone morte deviennent des constantes. Un seul cas par caméra DE CETTE
    SCÈNE (une caméra n'en possède qu'une, cf. `camera_target_index`) ; une
    scène où aucune caméra n'a de cible n'émet rien du tout."""
    index_of = {id(c): i for i, c in enumerate(project_cameras(p)) if c is not None}
    cases: list[str] = []
    for cam in scene.cameras:
        t = camera_target_index(cam, scene_actors, actor_offset)
        if t < 0:
            continue
        i = index_of[id(cam)]
        # Axe désactivé (scroll_h/scroll_v) : la cible sur cet axe devient
        # cam_x/cam_y lui-même → écart nul → camera_follow ne le bouge pas.
        # cam_x/cam_y restent en pixels.
        tx = f"(g_actors[{t}].x>>8)" if scene.scroll_h else "cam_x"
        ty = f"(g_actors[{t}].y>>8)" if scene.scroll_v else "cam_y"
        cases.append(f"        case {i}: camera_follow((Vec2){{{tx}, {ty}}}, "
                     f"g_cam_margin_x, g_cam_margin_y); break;"
                     f"   /* {cam.name} → {cam.follow_target} */")
    if not cases:
        return []
    return ["    switch(g_cam_active){"] + cases + ["        default: break;", "    }"]


def camera_table_lines(p) -> list[str]:
    """Les `extern` des scripts de caméra et la table `g_cam_table` du projet."""
    L: list[str] = []
    # ── Caméras du projet ────────────────────────────────────────
    # Une caméra est une DONNÉE : la table ci-dessous en est la forme runtime,
    # l'entrée 0 étant toujours la caméra par défaut (fixe à l'origine, sans
    # bornes) — celle qu'obtient une scène qui n'en désigne aucune, sans
    # qu'aucun fichier n'ait à exister.
    cams = scene_cameras_indexed(p)
    for _i, scene, cam in cams:
        if getattr(cam, "script", ""):
            cs = camera_sym(scene.name, cam.name)
            L += [
                f"extern void {cs}_camera_on_start(void);",
                f"extern void {cs}_camera_on_update(void);",
            ]
    L.append(f"const Camera g_cam_table[{len(cams) + 1}] = {{")
    # 240,160 = plein écran = WIN0 éteinte (frame_w/h), pas 0,0 qui
    # donnerait un cadre nul — cf. Camera.frame_w/h.
    L.append("    { 0, 40, 20, 0, 0, 0, 0, 0, 0, 240, 160, NULL, NULL },   /* (default) */")
    for _i, scene, cam in cams:
        cs = camera_sym(scene.name, cam.name)
        hooks = (f"{cs}_camera_on_start, {cs}_camera_on_update"
                 if getattr(cam, "script", "") else "NULL, NULL")
        L.append(f"    {{ {cam.mode_id()}, {cam.px('margin_x', p)}, {cam.px('margin_y', p)}, "
                 f"{cam.px('x', p)}, {cam.px('y', p)}, "
                 f"{cam.px('bounds_x', p)}, {cam.px('bounds_y', p)}, "
                 f"{cam.px('bounds_w', p)}, {cam.px('bounds_h', p)}, "
                 f"{cam.px('frame_w', p)}, {cam.px('frame_h', p)}, {hooks} }},"
                 f"   /* {scene.name}/{cam.name}, {cam.mode} */")
    L += ["};", ""]
    return L
