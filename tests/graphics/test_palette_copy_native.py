"""La copie des palettes en RAM : les écrivains ne touchent plus la mémoire de palettes, `palette_commit()` y recopie la
plage modifiée juste après le VBlank.

La sonde native (`tests/native/palette_probe.c`) compile le VRAI `gba_engine.h` en substituant un tableau à la mémoire de
palettes. Sans compilateur C hôte elle se saute, comme les autres tests natifs : la CI la tient. Le second test lit le
`main.c` émis pour une vraie scène.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from codegen.runtime_codegen import main_gen
from core.project import Project
from native_toolchain import compilateur_hote, environnement

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = REPO_DIR / "tests" / "native"
INTACTE = "7777"


@pytest.fixture(scope="module")
def etapes(tmp_path_factory) -> dict:
    compilateur = compilateur_hote()
    if compilateur is None:
        message = "aucun compilateur C hôte : la copie des palettes n'est PAS vérifiée"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; elle l'est en CI")
    env = environnement(compilateur)
    binaire = tmp_path_factory.mktemp("native") / "palette_probe"
    resultat = subprocess.run(
        [compilateur, "-std=c11", "-O0", "-o", str(binaire), str(NATIVE_DIR / "palette_probe.c"),
         "-I", str(NATIVE_DIR / "libgba_shim"), "-I", str(REPO_DIR / "runtime" / "include")],
        capture_output=True, text=True, env=env)
    if resultat.returncode != 0:
        pytest.fail(f"la sonde ne compile plus contre gba_engine.h :\n{resultat.stderr[-2000:]}")
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=env).stdout
    out: dict = {}
    for ligne in sortie.splitlines():
        mots = ligne.split()
        if mots[0] == "lu":
            out.setdefault("lu", {})[mots[1]] = mots[2]
            continue
        etape, pool, index, valeur = mots
        out.setdefault(etape, {})[(int(pool), int(index))] = valeur
    return out


BANQUE_3 = range(48, 64)


def test_une_ecriture_n_atteint_pas_la_memoire_de_palettes_avant_le_vblank(etapes):
    assert all(valeur == INTACTE for valeur in etapes["ecrite"].values())


def test_le_commit_recopie_la_banque_ecrite_et_rien_d_autre(etapes):
    recopiee = etapes["recopiee"]
    assert [recopiee[(0, i)] for i in BANQUE_3] == [INTACTE] + [f"02{c:02x}" for c in range(1, 16)]
    assert recopiee[(0, 47)] == recopiee[(0, 64)] == INTACTE    # l'index 0 de la banque non plus : jamais écrit
    assert all(recopiee[(1, i)] == INTACTE for i in range(47, 65))


def test_un_commit_sans_ecriture_ne_recopie_rien(etapes):
    assert etapes["rien_a_recopier"][(0, 48)] == "1111"


def test_le_pool_obj_a_sa_propre_plage(etapes):
    obj = etapes["obj"]
    assert [obj[(1, i)] for i in BANQUE_3] == [INTACTE] + [f"01{c:02x}" for c in range(1, 16)]
    assert obj[(0, 48)] == "1111"     # le pool BG n'a pas été recopié une seconde fois


# ── Une banque tenue par un script ──────────────────────────────────────────

def test_set_color_change_une_couleur_et_get_color_la_relit_avant_l_affichage(etapes):
    assert etapes["lu"]["5"] == "001f"                     # palette:rgb(31, 0, 0), lu dans la copie
    couleur = etapes["couleur"]
    assert couleur[(0, 53)] == "001f"
    assert couleur[(0, 48)] == "1111"                      # l'index 0 n'a pas reçu 0x1234
    assert couleur[(0, 54)] == "0206"                      # les autres couleurs de la banque restent


def test_reset_rend_le_debut_de_scene_sans_toucher_l_index_0(etapes):
    reset = etapes["reset"]
    assert [reset[(0, i)] for i in range(49, 64)] == [f"05{i:02x}" for i in range(49, 64)]
    assert reset[(0, 48)] == "1111"


def test_reset_d_un_pool_sans_table_remet_a_zero(etapes):
    reset = etapes["reset_obj_sans_table"]
    assert [reset[(1, i)] for i in range(49, 64)] == ["0000"] * 15


def test_rgb_borne_chaque_canal_a_0_31(etapes):
    assert etapes["lu"]["rgb"] == "021f"                    # (31, 16, 0)


# ── Les effets de palette ────────────────────────────────────────────────────
# Banque 3 du BG (index 48 à 63) : couleur 5 (53) noire, couleur 6 (54) rouge pur, 55 = 0x0537 du début de scène.

def test_un_fondu_a_moitie_amene_chaque_canal_a_mi_chemin(etapes):
    fondu = etapes["fondu_moitie"]
    assert fondu[(0, 53)] == "3def"          # noir → (15, 15, 15)
    assert fondu[(0, 54)] == "3dff"          # rouge → (31, 15, 15)


def test_get_color_rend_la_couleur_d_origine_sous_un_effet(etapes):
    assert etapes["lu"]["fondu"] == "0000"


def test_gris_et_inversion(etapes):
    assert etapes["gris"][(0, 54)] == "2529"        # rouge pur → luminance 9 sur les trois canaux
    assert etapes["gris"][(0, 53)] == "0000"
    assert etapes["inverse"][(0, 53)] == "7fff"     # intensité 99 bornée à 16 : effet complet
    assert etapes["inverse"][(0, 54)] == "7fe0"


def test_remettre_l_effet_a_zero_rend_l_origine(etapes):
    sans = etapes["sans_effet"]
    assert (sans[(0, 53)], sans[(0, 54)], sans[(0, 55)]) == ("0000", "001f", "0537")


def test_une_banque_ou_un_pool_hors_bornes_n_a_aucun_effet(etapes):
    assert etapes["hors_bornes"] == etapes["sans_effet"]


def test_l_effet_de_la_banque_passe_avant_celui_du_pool(etapes):
    # Banque noircie, puis pool à mi-chemin du blanc : tout finit gris moyen, l'index 0 des banques compris.
    blanc = etapes["pool_blanc"]
    assert all(blanc[(0, i)] == "3def" for i in range(47, 65))
    assert all(blanc[(1, i)] == etapes["sans_effet"][(1, i)] for i in range(47, 65))   # l'autre pool n'y est pour rien


def test_retirer_l_effet_du_pool_garde_celui_de_la_banque(etapes):
    retire = etapes["pool_retire"]
    assert all(retire[(0, i)] == "0000" for i in range(48, 64))


def test_une_nouvelle_scene_part_sans_effet(etapes):
    scene = etapes["nouvelle_scene"]
    assert (scene[(0, 53)], scene[(0, 54)], scene[(0, 55)]) == ("0000", "001f", "0537")
    assert scene[(1, 55)] == "0000"          # l'inversion du pool OBJ est retirée elle aussi


# ── La rotation d'une plage ──────────────────────────────────────────────────
# Couleurs 5, 6, 7 de la banque 3 (index 53 à 55) : noir, rouge pur, 0x0537.

def _plage(etape) -> tuple:
    return tuple(etape[(0, i)] for i in (53, 54, 55))


def test_la_rotation_decale_ce_qu_on_voit_dans_la_plage_seulement(etapes):
    rotation = etapes["rotation"]
    assert _plage(rotation) == ("0537", "0000", "001f")       # un cran : la dernière passe en tête
    assert rotation[(0, 52)] == "0534" and rotation[(0, 56)] == "0538"
    assert etapes["lu"]["rotation"] == "0000"                  # get_color rend l'origine


def test_une_couleur_ecrite_pendant_la_rotation_s_affiche_a_sa_place_tournee(etapes):
    assert _plage(etapes["rotation_ecrite"]) == ("03e0", "0000", "001f")


def test_un_cran_negatif_tourne_vers_l_arriere(etapes):
    assert _plage(etapes["rotation_arriere"]) == ("001f", "03e0", "0000")


def test_une_plage_qui_toucherait_l_index_0_arrete_la_rotation(etapes):
    assert _plage(etapes["rotation_index_0"]) == ("0000", "001f", "03e0")


def test_une_nouvelle_scene_arrete_la_rotation(etapes):
    assert _plage(etapes["rotation_nouvelle_scene"]) == ("0000", "001f", "03e0")


class _Journal:
    def __call__(self, event, *args):
        pass


def test_le_main_emis_ecrit_les_palettes_par_la_copie_et_les_recopie_apres_le_vblank(tmp_path):
    p = Project.create(tmp_path / "Game", "Game")
    scene = p.active_scene
    data = [{"scene": scene, "bg_pairs": [], "scene_actors": [], "extra_sprites": [], "prefab_sprites": []}]
    assert main_gen.generate_main(p, data, None, [], [], _Journal()) is True
    main_c = (p.src_dir / "main.c").read_text(encoding="utf-8")

    assert "VBlankIntrWait();\n        palette_commit();" in main_c
    assert "palette_write(PAL_POOL_BG, 0, &backdrop, 1);" in main_c
    assert "PAL_BG_RAM" not in main_c and "PAL_OBJ_RAM" not in main_c
    assert "palette_scene_start(" in main_c
