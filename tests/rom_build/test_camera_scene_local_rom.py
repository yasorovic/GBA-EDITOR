"""Le nom d'une caméra est local à sa scène : deux scènes qui ont chacune leur « Camera », scriptée et citée par
`camera:switch`, se compilent en ROM avec le vrai gcc, et chaque scène démarre sur SA caméra (avant, la première
caméra du projet portant ce nom gagnait)."""
from __future__ import annotations

import re

import pytest

from codegen import BuildWorker
from core.models.camera import Camera
from core.models.scene import Scene
from core.project import Project
from core.toolchain import DEVKITPRO_OK, Toolchain

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(Toolchain().devkitpro_state != DEVKITPRO_OK,
                       reason=f"devkitPro non prêt ({Toolchain().devkitpro_state})"),
]

SWITCH = """function on_update()
  if camera.name ~= "Camera" then
    camera:switch("Camera")
  end
end
"""
CAMERA = """function on_update()
  camera.margin = vec2(10, 10)
end
"""


def test_deux_scenes_ont_chacune_leur_camera_du_meme_nom(tmp_path):
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Switch.lua").write_text(SWITCH, encoding="utf-8")
    (scripts / "Cam.lua").write_text(CAMERA, encoding="utf-8")

    une = projet.scenes[0]
    deux = Scene(name="Scene_02")
    projet.scenes.append(deux)
    for scene, x in ((une, 11), (deux, 22)):
        scene.cameras = [Camera(name="Camera", x=x, script="assets/scripts/Cam.lua")]
        scene.camera = "Camera"
        scene.script = "assets/scripts/Switch.lua"
    projet.save()

    worker = BuildWorker(Project.open(projet.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()
    assert verdict == [True], [d.message for d in diagnostics if d.level == "error"]
    assert not any("Two cameras" in d.message for d in diagnostics)

    build = projet.root / "build"
    api_h = next(build.rglob("runtime_api.h")).read_text(encoding="utf-8")
    assert "#define CAM_SCENE_01_CAMERA 1" in api_h and "#define CAM_SCENE_02_CAMERA 2" in api_h
    main_c = next(build.rglob("main.c")).read_text(encoding="utf-8")
    # Chaque scène démarre sur sa caméra : la table garde les deux, chacune avec son x.
    assert "camera_switch(1);" in main_c and "camera_switch(2);" in main_c
    init_02 = main_c[main_c.index("static void scene_init_Scene_02(void)"):]
    assert re.search(r"camera_switch\(2\);", init_02.split("static void ", 2)[1])
    assert "Scene_01/Camera" in main_c and "Scene_02/Camera" in main_c
    # Chaque script cite la caméra de SA scène, et chaque caméra a son propre fichier.
    sources = "\n".join(c.read_text(encoding="utf-8") for c in build.rglob("*.c"))
    assert "camera_switch(CAM_SCENE_01_CAMERA)" in sources and "camera_switch(CAM_SCENE_02_CAMERA)" in sources
    assert next(build.rglob("camera_Scene_01_Camera.c"), None) is not None
    assert next(build.rglob("camera_Scene_02_Camera.c"), None) is not None
