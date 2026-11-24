"""Une grille RAM de scène, partagée par tous ses scripts via `data.grid.<Nom>`.

Tranche 3 du chantier « une grille de scène partagée en RAM ». Une grille peinte
marquée RAM se lit ET s'écrit par `data.grid.<Nom>` depuis n'importe quel script
de la scène : un script (la scène) écrit le champ de flux (`target`), un autre
(un acteur) le lit (`step_at`). Le même tampon RAM. Une grille peinte en ROM
reste en lecture seule.

Ces tests vérifient les deux gardes ouvertes : le vérificateur accepte les
méthodes d'écriture sur une grille RAM de scène (et les refuse sur une grille
ROM), et le traducteur émet le symbole du tampon partagé.
"""
from __future__ import annotations

from codegen.runtime_codegen.grids import scene_grid_access
from core.models.grid import Grid, GridValue
from core.models.scene import Scene
from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.parser import parse


def _scene() -> Scene:
    """Une scène avec une grille RAM `Flow` (partagée, inscriptible) et une grille
    peinte `Terrain` en ROM (lecture seule)."""
    flow = Grid(name="Flow", step=16, ram=True)
    flow.ensure_size(240, 160)
    return Scene(name="Arena", grids=[
        flow,
        Grid(name="Terrain", step=16,
             values=[GridValue(value=1, name="HERBE")],
             cells=[[0, 1], [1, 0]]),
    ])


def _acces() -> dict:
    return scene_grid_access(_scene())


def _handler(corps: str) -> str:
    return f"function on_update()\n{corps}\nend\n"


def _erreurs(corps: str) -> list[str]:
    ctx = BuildContext(actor_name="Chaser", scene_label="Arena", scene_grids=_acces())
    return [e.message for e in check(parse(_handler(corps)), ctx) if e.level == "error"]


def _emis(corps: str) -> str:
    code, _g, _c = generate(parse(_handler(corps)), CodegenContext(
        actor_name="Chaser", actor_sym="Chaser", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Chaser"],
        scene_sym="Arena", scene_grids=_acces()))
    return code


# ── Ce que le vérificateur accepte, et refuse ─────────────────────

def test_une_grille_ram_de_scene_s_ecrit():
    assert _erreurs("data.grid.Flow:fill(0)") == []
    assert _erreurs("data.grid.Flow:fill_rect(1, 1, 2, 2, 3)") == []
    assert _erreurs("data.grid.Flow:target(self.position)") == []


def test_une_grille_ram_de_scene_se_lit_comme_champ_de_flux():
    assert _erreurs("local d = data.grid.Flow:step_at(self.position)") == []
    assert _erreurs("local v = data.grid.Flow:at(32, 16)") == []
    assert _erreurs("local v = data.grid.Flow[2][1]") == []


def test_une_grille_peinte_en_rom_reste_en_lecture_seule():
    """L'écriture sur une grille non-RAM est refusée : seule `:at` est permise."""
    erreurs = _erreurs("data.grid.Terrain:fill(0)")
    assert erreurs and "read-only" in erreurs[0]
    assert _erreurs("local v = data.grid.Terrain:at(16, 16)") == []


def test_le_champ_de_flux_partage_borne_sa_taille_dans_target():
    """`target` d'une grille RAM de scène trop grande est refusé (scratch 1024)."""
    grande = Grid(name="Flow", step=16, ram=True)
    grande.ensure_size(2048, 2048)   # 128 x 128 = 16384 cases
    acces = scene_grid_access(Scene(name="Arena", grids=[grande]))
    ctx = BuildContext(actor_name="Chaser", scene_label="Arena", scene_grids=acces)
    erreurs = [e.message for e in check(parse(_handler("data.grid.Flow:target(self.position)")), ctx)
               if e.level == "error"]
    assert erreurs and "too large" in erreurs[0]


# ── Ce que le traducteur émet : le symbole du tampon partagé ──────

def test_l_ecriture_vise_le_tampon_ram_qualifie_par_la_scene():
    assert "grid_fill(g_grid_Arena_Flow," in _emis("data.grid.Flow:fill(0)")
    assert "grid_target(g_grid_Arena_Flow," in _emis("data.grid.Flow:target(self.position)")


def test_la_lecture_du_pas_vise_le_meme_tampon():
    """Le script de l'acteur lit le champ écrit par le script de la scène : même
    symbole `g_grid_Arena_Flow`, donc même tampon RAM."""
    assert "grid_step_at(g_grid_Arena_Flow," in _emis("local d = data.grid.Flow:step_at(self.position)")
