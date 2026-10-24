"""Le backdrop d'un projet NEUF est le gris foncé (50, 50, 50) ; un projet qui a déjà sa couleur la garde."""
from core.models.gba_color import rgb888_to_bgr555
from core.models.settings import ProjectSettings
from core.project import Project


def test_le_backdrop_par_defaut_est_un_gris_fonce():
    assert ProjectSettings().backdrop_color == rgb888_to_bgr555(50, 50, 50) == 0x18C6


def test_un_projet_neuf_l_ecrit_et_un_projet_existant_garde_sa_couleur(tmp_path):
    neuf = Project.create(tmp_path / "Game", "Game")
    assert neuf.settings.backdrop_color == 0x18C6

    neuf.settings.backdrop_color = 0x1234
    neuf.save_settings()
    neuf.load_settings()
    assert neuf.settings.backdrop_color == 0x1234
