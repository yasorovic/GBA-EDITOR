"""La palette d'interface par défaut : « Microsoft Windows 16 », activée dans toute scène neuve
et lue par son texte libre tant que l'auteur n'a pas choisi autre chose."""
from __future__ import annotations

from core.models.palette import DEFAULT_UI_PALETTE, PaletteBank
from core.models.scene import Scene
from core.project import Project


def test_un_projet_neuf_active_la_palette_par_defaut_dans_sa_premiere_scene(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")

    scene = project.scenes[0]

    assert project.get_palette(DEFAULT_UI_PALETTE) is not None      # fournie par le Starter
    assert scene.active_bg_palettes == [DEFAULT_UI_PALETTE]
    assert scene.font_pal_banks == {"": 0}                          # le texte libre la lit


def test_une_scene_avec_une_selection_n_est_jamais_modifiee(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    scene = Scene(name="Level", active_bg_palettes=["_Commodore 64"])

    assert project.seed_default_ui_palette(scene) is False
    assert scene.active_bg_palettes == ["_Commodore 64"]
    assert scene.font_pal_banks == {}


def test_sans_la_palette_dans_le_catalogue_rien_n_est_pose(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    project.palettes.remove(project.get_palette(DEFAULT_UI_PALETTE))
    scene = Scene(name="Level")

    assert project.seed_default_ui_palette(scene) is False
    assert scene.active_bg_palettes == []


def test_une_scene_vide_recoit_le_defaut_une_seule_fois(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    scene = Scene(name="Level")

    assert project.seed_default_ui_palette(scene) is True
    assert project.seed_default_ui_palette(scene) is False
    assert scene.active_bg_palettes == [DEFAULT_UI_PALETTE]


def test_le_suffixe_d_une_palette_est_son_vrai_nombre_de_couleurs():
    from ui.common.asset_kinds import PALETTES

    bank = PaletteBank(name="Tiny", colors=[0, 1, 2, 3, 4])

    assert PALETTES.suffix_of(bank) == "5"
