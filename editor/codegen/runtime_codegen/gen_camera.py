"""codegen/runtime_codegen/gen_camera.py — la table des caméras et le suivi.

Extrait de `main_gen` (A3). `project_cameras` est l'ordre de vérité de la table
runtime : `headers.py` (les `#define CAM_*`) et `lua_compiler.py` en dérivent la
même liste, sinon `camera.switch` viserait la mauvaise caméra. La façade
`main_gen` ré-exporte `project_cameras` pour ces consommateurs.
"""
from __future__ import annotations

from codegen.c_names import sym as c_sym


def camera_sym(name: str) -> str:
    """Symbole C d'une caméra — préfixé, les caméras et les acteurs partageant
    le même espace de noms C."""
    return f"camera_{c_sym(name)}"


def project_cameras(p) -> list:
    """Les caméras du projet dans l'ordre de la TABLE runtime, `None` en tête.

    Ce `None` est la caméra par défaut : fixe à l'origine, sans bornes ni
    suivi, et sans entrée dans aucune scène — une scène qui n'en désigne
    aucune tombe dessus. La donner comme entrée 0 plutôt que comme cas
    particulier évite un `if` à chaque endroit qui active une caméra.

    Une caméra appartient à sa scène (révisé 2026-08-24) : cette table APLATIT toutes les scènes, dans
    leur ordre puis celui de `Scene.cameras` — ordre déterministe, condition
    pour que `headers.py` (les `#define CAM_*`) et `lua_compiler.py` en
    dérivent la MÊME liste que celle-ci (sinon `camera.switch` viserait la
    mauvaise caméra)."""
    return [None] + [c for s in p.scenes for c in s.cameras]


def scene_camera_index(p, scene) -> int:
    """Index de la caméra de démarrage d'une scène dans la table runtime.

    Un nom qui ne résout pas retombe sur 0 (la caméra par défaut) plutôt que de
    faire échouer le build : le validateur signale la référence cassée, et un
    jeu qui compile encore reste débuggable."""
    name = getattr(scene, "camera", "")
    if not name:
        return 0
    cams = project_cameras(p)
    return next((i for i, c in enumerate(cams) if c is not None and c.name == name), 0)


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
    cams = project_cameras(p)
    for cam in cams[1:]:
        if getattr(cam, "script", ""):
            cs = camera_sym(cam.name)
            L += [
                f"extern void {cs}_camera_on_start(void);",
                f"extern void {cs}_camera_on_update(void);",
            ]
    L.append(f"const Camera g_cam_table[{len(cams)}] = {{")
    for cam in cams:
        if cam is None:
            # 240,160 = plein écran = WIN0 éteinte (frame_w/h), pas 0,0 qui
            # donnerait un cadre nul — cf. Camera.frame_w/h.
            L.append("    { 0, 40, 20, 0, 0, 0, 0, 0, 0, 240, 160, NULL, NULL },   /* (default) */")
            continue
        cs = camera_sym(cam.name)
        hooks = (f"{cs}_camera_on_start, {cs}_camera_on_update"
                 if getattr(cam, "script", "") else "NULL, NULL")
        L.append(f"    {{ {cam.mode_id()}, {cam.px('margin_x', p)}, {cam.px('margin_y', p)}, "
                 f"{cam.px('x', p)}, {cam.px('y', p)}, "
                 f"{cam.px('bounds_x', p)}, {cam.px('bounds_y', p)}, "
                 f"{cam.px('bounds_w', p)}, {cam.px('bounds_h', p)}, "
                 f"{cam.px('frame_w', p)}, {cam.px('frame_h', p)}, {hooks} }},"
                 f"   /* {cam.name} — {cam.mode} */")
    L += ["};", ""]
    return L
