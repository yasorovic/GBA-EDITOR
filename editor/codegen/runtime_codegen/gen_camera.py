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

    Une caméra appartient à sa scène (révisé 2026-08-24, cf.
    `changelog/archives/v0.6.md`) : cette table APLATIT toutes les scènes, dans
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
        # cam_x/cam_y restent en pixels (ROADMAP v0.19 : « la caméra arrondit
        # après avoir suivi, jamais avant » — un seul arrondi, ICI, à la
        # frontière acteur→caméra ; tout le reste du suivi/scroll/streaming
        # continue en pixels, inchangé).
        tx = f"(g_actors[{t}].x>>8)" if scene.scroll_h else "cam_x"
        ty = f"(g_actors[{t}].y>>8)" if scene.scroll_v else "cam_y"
        cases.append(f"        case {i}: camera_follow((Vec2){{{tx}, {ty}}}, "
                     f"g_cam_margin_x, g_cam_margin_y); break;"
                     f"   /* {cam.name} → {cam.follow_target} */")
    if not cases:
        return []
    return ["    switch(g_cam_active){"] + cases + ["        default: break;", "    }"]
