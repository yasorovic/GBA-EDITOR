"""Le suivi déclaratif de la caméra, sur le C réellement émis pour une scène.

La marge borne le CADRE du sprite suivi, pas la position de l'acteur (son coin
haut-gauche) : les quatre bandes se lisent pareil. La sonde compile la ligne
que `camera_follow_lines` émet, avec le vrai `camera_follow` du runtime, et
promène l'acteur d'un bord à l'autre.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAME_W, FRAME_H = 32, 32
MARGIN_X, MARGIN_Y = 64, 32

SONDE = r"""
#include <stdio.h>
#define SCREEN_W 240
#define SCREEN_H 160
typedef struct { int x, y; } Vec2;
typedef struct { int x, y; } Actor;        /* la sonde ne lit que la position */
Actor g_actors[4];
int cam_x = 0, cam_y = 0;
int g_cam_margin_x = @MX@, g_cam_margin_y = @MY@;
int g_cam_active = @CAM@;
@FOLLOW@

static void suivre(void){
@LINES@
}

/* La cible est posée en (x, y) MONDE (son coin haut-gauche), la caméra suit,
   et on imprime où le cadre tombe à l'écran. */
static void pas(const char* nom, int x, int y){
    g_actors[@T@].x = x << 8; g_actors[@T@].y = y << 8;
    suivre();
    printf("%s %d %d\n", nom, (x - cam_x), (y - cam_y));
}

int main(void){
    pas("centre", 1000, 1000);     /* première image : la caméra se cale sur la cible */
    pas("gauche", 0, 1000);        /* la cible part vers la gauche du monde */
    pas("droite", 2000, 1000);
    pas("haut",   1000, 0);
    pas("bas",    1000, 2000);
    return 0;
}
"""


def _follow_source() -> str:
    """Le texte de `camera_follow`, tel que `runtime_api_inline.h` l'écrit."""
    lines = (INCLUDE / "runtime_api_inline.h").read_text(encoding="utf-8").splitlines()
    i = next(k for k, line in enumerate(lines)
             if line.startswith("static") and " camera_follow(" in line)
    j = next(k for k in range(i, len(lines)) if lines[k] == "}")
    return "\n".join(lines[i:j + 1])


def _emission(tmp_path, **scene_kwargs) -> dict:
    from codegen.runtime_codegen.gen_camera import camera_follow_lines
    from core.models.camera import Camera, CAM_FOLLOW
    from core.models.components import SpriteComponent
    from core.models.scene import Actor, Scene
    from core.models.sprite import SpriteAsset
    from core.project import Project

    project = Project(tmp_path)
    project.sprites.append(SpriteAsset(name="Hero", asset="hero.png",
                                       frame_w=FRAME_W, frame_h=FRAME_H))
    actor = Actor(name="Hero")
    actor.components.append(SpriteComponent(sprite_name="Hero"))
    cam = Camera(name="Cam", mode=CAM_FOLLOW, follow_target="Hero",
                 margin_x=MARGIN_X, margin_y=MARGIN_Y)
    scene = Scene(name="S", actors=[actor], cameras=[cam], camera="Cam",
                  **scene_kwargs)
    project.scenes.items = [scene]
    scene_actors = [(actor, project.get_sprite("Hero"))]
    lines = camera_follow_lines(project, scene, scene_actors, 0)
    assert lines, "aucun suivi émis : la sonde ne vérifierait rien"
    return {"lines": lines, "cam": 1, "target": 0}


@pytest.fixture(scope="module")
def positions(tmp_path_factory):
    """Où le coin haut-gauche du cadre suivi tombe À L'ÉCRAN, par étape."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le suivi est vérifié en CI")
    e = _emission(tmp_path_factory.mktemp("camera_follow"))
    dossier = tmp_path_factory.mktemp("camera_follow_sonde")
    source = (SONDE.replace("@FOLLOW@", _follow_source())
              .replace("@LINES@", "\n".join(e["lines"]))
              .replace("@CAM@", str(e["cam"])).replace("@T@", str(e["target"]))
              .replace("@MX@", str(MARGIN_X)).replace("@MY@", str(MARGIN_Y)))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w",
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout
    return {l.split()[0]: tuple(int(v) for v in l.split()[1:])
            for l in sortie.strip().splitlines()}


def test_le_cadre_s_arrete_a_la_marge_des_quatre_cotes(positions):
    # Bord gauche/haut : le coin du cadre s'arrête SUR la marge.
    assert positions["gauche"][0] == MARGIN_X
    assert positions["haut"][1] == MARGIN_Y
    # Bord droit/bas : c'est l'AUTRE coin du cadre qui s'arrête sur la marge.
    assert positions["droite"][0] + FRAME_W == 240 - MARGIN_X
    assert positions["bas"][1] + FRAME_H == 160 - MARGIN_Y


def test_un_axe_sans_defilement_ne_recule_pas_la_camera(tmp_path):
    """Sur un axe désactivé la cible EST la caméra : l'écart vaut 0, et une
    marge non nulle le ferait reculer d'une marge par image."""
    ligne = next(l for l in _emission(tmp_path, scroll_h=False)["lines"]
                 if "camera_follow(" in l)
    assert "(Vec2){cam_x," in ligne
    assert "camera_follow((Vec2){cam_x, ((g_actors[0].y>>8)+16)}, 0, g_cam_margin_y+16)" in ligne


def test_scene_init_pose_la_camera_apres_les_acteurs_et_leurs_on_start(tmp_path):
    """La caméra est activée tôt pour son cadrage et son on_start, puis son suivi attend que sa cible existe et que
    l'initialisation de scène ait pu la déplacer. Sinon la première image est à l'origine et le premier tick saute."""
    from codegen.runtime_codegen.gen_scene_init import gen_scene_init
    from core.models.camera import Camera, CAM_FOLLOW
    from core.models.scene import Actor, Scene
    from core.project import Project

    project = Project(tmp_path)
    hero = Actor(name="Hero")
    scene = Scene(name="S", actors=[hero], cameras=[Camera(name="Cam", mode=CAM_FOLLOW, follow_target="Hero")],
                  camera="Cam")
    project.scenes.items = [scene]
    lines = gen_scene_init(project, scene, 0, [], [(hero, None)], set(), [], {}, 0, False, None)
    source = "\n".join(lines)

    activation = source.index("camera_switch(1);")
    actor = source.index("actor_init_slot(")
    follow = source.rindex("switch(g_cam_active){")
    clamp = source.index("camera_apply_bounds();", follow)
    assert activation < actor < follow < clamp

    from codegen.runtime_codegen.gen_camera import camera_background_lines
    offsets = "\n".join(camera_background_lines([{"bg": 2}]))
    assert "BGOFS(2)" in offsets and "BGVOFS(2)" in offsets


def test_le_vide_laisse_au_bord_est_le_meme_des_deux_cotes(positions):
    """Le défaut corrigé : le coin était borné, le personnage entrait donc
    dans la bande de droite (et du bas) de toute sa largeur."""
    assert positions["gauche"][0] == 240 - (positions["droite"][0] + FRAME_W)
    assert positions["haut"][1] == 160 - (positions["bas"][1] + FRAME_H)
