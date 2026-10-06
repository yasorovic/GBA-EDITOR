"""L'API dit ce que l'inspecteur règle — tranche 1 : acteur, sprite, collision.

Règle (ROADMAP « L'API dit tout ce que l'inspecteur règle ») : tout champ
d'inspecteur a une porte Lua — écrite quand le runtime sait la changer, en
LECTURE SEULE quand la valeur est fixée au build.

Ce que ce fichier tient, et qu'un test de catalogue ne verrait pas :
- les portes se compilent vers le bon C (le tag de boîte devient `BOXTAG_*`) ;
- un tag inconnu est refusé À LA COMPILATION — au runtime il se lirait vide et
  s'écrirait sans effet, sans un mot ;
- les portes en lecture seule le sont vraiment ;
- le C se comporte (bornes, boîte absente, bonne boîte) — sonde native.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

REPO_DIR   = Path(__file__).resolve().parents[2]
NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
MOTEUR_DIR = REPO_DIR / "runtime" / "include"

TAGS = ["body", "hitbox"]


def _lua(src: str, tags=TAGS):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball", anim_names=["idle"],
                                        box_tag_names=tags))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"]))
    return [e.message for e in errors if e.level == "error"], code


# ── Boîtes de collision ──────────────────────────────────────────────

def test_une_boite_se_tient_dans_une_variable_et_ses_champs_sont_des_proprietes():
    errs, code = _lua(
        "function on_update(self)\n"
        "  local hb = self:collision_box(\"hitbox\")\n"
        "  hb.offset = vec2(8, -4)\n"
        "  hb.size = vec2(12, 8)\n"
        "  hb.solid = false\n"
        "  hb:activate()\n"
        "  if hb.solid then self:show() end\n"
        "  if hb.bounds.w > 0 then self:hide() end\n"
        "  if hb.tag == \"hitbox\" then self:show() end\n"
        "  if not hb then self:hide() end\n"
        "end\n")
    assert errs == []
    assert "int hb = actor_get_box(self, BOXTAG_HITBOX);" in code
    assert "collision_box_set_offset(hb, (Vec2){8, (-4)})" in code
    assert "collision_box_set_size(hb, (Vec2){12, 8})" in code
    assert "collision_box_set_solid(hb, 0)" in code
    assert "collision_box_set_active(hb, 1)" in code
    assert "collision_box_get_solid(hb)" in code
    assert "collision_box_get_bounds(hb).w" in code
    assert "collision_box_get_tag(hb) == BOXTAG_HITBOX" in code
    assert "(!hb)" in code                      # nil = 0, testable


def test_hb_tag_n_est_pas_le_tag_de_l_acteur():
    """`self.name` existe (identité de l'acteur) : `hb.tag` ne doit jamais s'y
    résoudre, sans quoi la boîte répondrait par l'acteur."""
    _, code = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n"
                   "  if hb.tag == \"body\" then self:show() end\nend\n")
    assert "collision_box_get_tag(hb)" in code
    assert "actor_get_name(hb)" not in code


def test_une_boite_d_un_autre_acteur_se_demande_aussi():
    errs, code = _lua("function on_update(self)\n"
                      " local o = actor:get(\"Ball\")\n"
                      " local hb = o:collision_box(\"body\")\n"
                      " hb.solid = false\nend\n")
    assert errs == []
    assert "actor_get_box(o, BOXTAG_BODY)" in code


def test_overlaps_prend_un_acteur_ou_une_autre_boite():
    errs, code = _lua(
        "function on_update(self)\n"
        "  local hb = self:collision_box(\"hitbox\")\n"
        "  local o = actor:get(\"Ball\")\n"
        "  local hurt = o:collision_box(\"body\")\n"
        "  if hb:overlaps(o) then self:show() end\n"
        "  if hb:overlaps(hurt) then self:show() end\n"
        "  if hb:overlaps(o:collision_box(\"body\")) then self:show() end\n"
        "end\n")
    assert errs == []
    assert "collision_box_overlaps_actor(hb, o)" in code
    assert "collision_box_overlaps_box(hb, hurt)" in code
    assert "collision_box_overlaps_box(hb, actor_get_box(o, BOXTAG_BODY))" in code


def test_get_collision_tile_est_une_methode_de_la_boite():
    errs, code = _lua("function on_update(self)\n"
                      "  local hb = self:collision_box(\"body\")\n"
                      "  local t = hb:get_collision_tile(hb.bounds.x, hb.bounds.y + hb.bounds.h)\n"
                      "end\n")
    assert errs == []
    assert "collision_box_get_collision_tile(hb, " in code


def test_l_ancienne_fonction_de_module_n_existe_plus():
    """`collision_box.get_tile` et `tile.get` sont remplacées par la méthode."""
    from scripting.api import RUNTIME_API
    assert "collision_box.get_tile" not in RUNTIME_API
    assert "tile.get" not in RUNTIME_API


def test_is_grounded_est_une_propriete_de_boite_en_lecture_seule():
    errs, code = _lua("function on_update(self)\n"
                      "  local hb = self:collision_box(\"body\")\n"
                      "  if hb.is_grounded then self:show() end\nend\n")
    assert errs == []
    assert "collision_box_get_grounded(hb)" in code
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n  hb.is_grounded = true\nend\n")
    assert errs and "read-only" in errs[0]


def test_le_tag_et_les_bounds_d_une_boite_sont_en_lecture_seule():
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n  hb.tag = \"hitbox\"\nend\n")
    assert errs and "read-only" in errs[0]
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n  hb.bounds = rect(0, 0, 1, 1)\nend\n")
    assert errs and "read-only" in errs[0]


def test_une_valeur_composee_de_la_boite_est_immuable():
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n  hb.size.x = 3\nend\n")
    assert errs and "immutable" in errs[0]


def test_un_champ_inconnu_sur_une_boite_est_refuse():
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n  hb.width = 3\nend\n")
    assert errs and "width" in errs[0] and "size" in errs[0]
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n"
                   "  if hb.width > 1 then self:show() end\nend\n")
    assert errs and "width" in errs[0]


def test_une_methode_inconnue_sur_une_boite_est_refusee():
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n  hb:touches_tile()\nend\n")
    assert errs and ":overlaps()" in errs[0]


def test_un_tag_de_boite_inconnu_est_refuse_a_la_compilation():
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"hitboks\")\nend\n")
    assert errs and "hitboks" in errs[0] and "hitbox" in errs[0]


def test_les_anciennes_portes_de_boite_n_existent_plus():
    """Supprimées à la livraison, sans alias : une fonction retirée doit être
    refusée, pas retomber sur `actor_<méthode>(...)`."""
    for appel in ('self:box_rect("body")', 'self:set_box_rect("body", rect(0, 0, 1, 1))',
                  'self:box_solid("body")', 'self:set_box_solid("body", true)'):
        errs, _ = _lua(f"function on_update(self)\n  local x = {appel}\nend\n")
        assert errs, appel


def test_un_nom_d_acteur_n_est_pas_un_tag_de_boite():
    """`tag` (identité d'un acteur) et `box_tag` (champ libre d'une boîte) sont
    deux espaces de noms."""
    errs, _ = _lua("function on_update(self)\n local s = self:collision_box(\"Ball\")\nend\n")
    assert errs


def test_box_count_est_en_lecture_seule():
    errs, code = _lua("function on_update(self)\n"
                      " if self.box_count > 1 then self:hide() end\nend\n")
    assert errs == []
    assert "actor_get_box_count(self)" in code
    errs, _ = _lua("function on_update(self)\n self.box_count = 3\nend\n")
    assert errs and "read-only" in errs[0]


# ── Réglages fixés au build : lecture seule ──────────────────────────

@pytest.mark.parametrize("champ,getter", [
    ("screen_space", "actor_get_screen_space"),
    ("affine",       "actor_get_affine"),
])
def test_les_reglages_du_build_se_lisent_sans_s_ecrire(champ, getter):
    errs, code = _lua(f"function on_update(self)\n if self.{champ} then self:show() end\nend\n")
    assert errs == []
    assert f"{getter}(self)" in code
    errs, _ = _lua(f"function on_update(self)\n self.{champ} = true\nend\n")
    assert errs and "read-only" in errs[0]


def test_un_autre_acteur_se_lit_aussi():
    errs, code = _lua("function on_update(self)\n"
                      " local o = actor:get(\"Ball\")\n"
                      " if o and o.screen_space then o:destroy() end\nend\n")
    assert errs == []
    assert "actor_get_screen_space(o)" in code


# ── Les fonctions C existent, les noms du projet suivent ────────────

def test_toutes_les_portes_de_la_tranche_ont_leur_c():
    from scripting.api import RUNTIME_API, RUNTIME_PROPS
    facade = (MOTEUR_DIR / "runtime_api_inline.h").read_text(encoding="utf-8", errors="ignore")
    fns = [RUNTIME_API[k].c_func for k in ("actor:collision_box", "collision_box:overlaps")]
    fns += ["collision_box_overlaps_box", RUNTIME_API["collision_box:get_collision_tile"].c_func]
    fns += [RUNTIME_PROPS[k].c_getter for k in ("actor.box_count", "actor.screen_space", "actor.affine")]
    for k, prop in RUNTIME_PROPS.items():
        if k.startswith("collision_box."):
            fns.append(prop.c_getter)
            if prop.c_setter:
                fns.append(prop.c_setter)
    for fn in fns:
        assert re.search(r"\b" + re.escape(fn) + r"\s*\(", facade), f"{fn}() absent de runtime_api_inline.h"


def test_le_tag_de_boite_est_dans_les_noms_du_projet():
    """La complétion et la sidebar lisent `names_by_domain` : un domaine absent
    n'y proposerait rien."""
    from scripting.api import DOMAIN_BOX_TAG
    from scripting.project_names import names_by_domain

    class P:
        def collision_tags(self):
            return ["body", "hitbox"]

    assert names_by_domain(P())[DOMAIN_BOX_TAG] == ["body", "hitbox"]


def test_renommer_un_tag_de_boite_suit_dans_les_scripts():
    """Le renommage est dérivé de RUNTIME_API : le domaine ayant un paramètre,
    il est réécrit sans table de plus — et seulement là où il est cité comme tag."""
    from scripting.api import DOMAIN_BOX_TAG
    from scripting.refactor import rename_in_text
    src = ("function on_update(self)\n"
           "  local hb = self:collision_box(\"hitbox\")\n"
           "  local s = \"hitbox\"\nend\n")
    out, n = rename_in_text(src, DOMAIN_BOX_TAG, "hitbox", "strike")
    assert n == 1
    assert "collision_box(\"strike\")" in out and "local s = \"hitbox\"" in out


def test_renommer_un_tag_de_boite_suit_aussi_la_comparaison_de_hb_tag():
    """`hb.tag == "hitbox"` cite le tag comme `self:collision_box("hitbox")` :
    le renommage doit le suivre, sinon la comparaison ne compile plus."""
    from scripting.api import DOMAIN_BOX_TAG
    from scripting.refactor import rename_in_text
    src = ("function on_update(self)\n"
           "  local hb = self:collision_box(\"hitbox\")\n"
           "  if hb.tag == \"hitbox\" then self:show() end\nend\n")
    out, n = rename_in_text(src, DOMAIN_BOX_TAG, "hitbox", "strike")
    assert n == 2 and out.count("strike") == 2


# ── Le C se comporte ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sortie_sonde(tmp_path_factory):
    import os
    compilateur = compilateur_hote()
    if compilateur is None:
        message = "aucun compilateur C hôte — le comportement C des boîtes n'est PAS vérifié"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; il l'est en CI")

    from codegen.runtime_codegen.api_prototypes import build_enum_defines
    dossier = tmp_path_factory.mktemp("box_probe")
    (dossier / "enums.h").write_text("\n".join(build_enum_defines()) + "\n")
    binaire = dossier / "actor_box_probe"
    env = environnement(compilateur)
    r = subprocess.run(
        [compilateur, "-std=c11", "-w", "-O0", "-include", str(dossier / "enums.h"),
         "-I", str(NATIVE_DIR / "libgba_shim"), "-I", str(MOTEUR_DIR),
         str(NATIVE_DIR / "actor_box_probe.c"), "-o", str(binaire)],
        capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    return {l.split()[0]: [int(v) for v in l.split()[1:]] for l in run.stdout.splitlines()}


def test_c_la_bonne_boite_repond(sortie_sonde):
    """La référence est un rang (acteur × MAX_BOXES + boîte + 1), 0 = absente."""
    assert sortie_sonde["refs"] == [1, 2, 0, 5]
    assert sortie_sonde["tags"] == [0, 1]
    assert sortie_sonde["offset_body"] == [0, 0]
    assert sortie_sonde["offset_hit"] == [2, -3]
    assert sortie_sonde["size_hit"] == [8, 8]


def test_c_une_ecriture_hors_bornes_est_serree_et_ne_deborde_pas(sortie_sonde):
    assert sortie_sonde["offset_borne"] == [127, -128]
    assert sortie_sonde["size_borne"] == [255, 0]
    assert sortie_sonde["voisine_offset"] == [0, 0]
    assert sortie_sonde["voisine_size"] == [16, 16]
    assert sortie_sonde["offset_normal"] == [4, 5]
    assert sortie_sonde["size_normal"] == [6, 7]


def test_c_solid_et_active_se_lisent_s_ecrivent_et_ne_touchent_que_leur_boite(sortie_sonde):
    assert sortie_sonde["solid_avant"] == [1, 0]
    assert sortie_sonde["solid_apres"] == [0, 1]
    assert sortie_sonde["active_avant"] == [1, 1]
    assert sortie_sonde["active_apres"] == [1, 0]


def test_c_une_boite_absente_se_lit_vide_et_s_ecrit_sans_effet(sortie_sonde):
    assert sortie_sonde["absente_offset"] == [0, 0]
    assert sortie_sonde["absente_bounds"] == [0, 0, 0, 0]
    assert sortie_sonde["absente_solid"] == [0]
    assert sortie_sonde["box_count"] == [2]


def test_c_bounds_est_le_rectangle_monde_en_pixels(sortie_sonde):
    """La position d'un acteur est en Q8 : 100 << 8 doit donner x = 100."""
    assert sortie_sonde["bounds_body"] == [100, 50, 16, 16]
    assert sortie_sonde["bounds_hit"] == [102, 47, 8, 8]


def test_c_le_chevauchement_compare_des_pixels_pas_du_q8(sortie_sonde):
    """Régression : `box_overlap` recevait les positions en Q8 et les comparait
    à des offsets en pixels — deux boîtes à 5 px ne se voyaient plus. Vaut pour
    la référence ET pour la détection acteur-contre-acteur (`on_collide`)."""
    assert sortie_sonde["overlap_5px"] == [1, 1]
    assert sortie_sonde["overlap_20px"] == [0, 0]
    assert sortie_sonde["actors_overlap"] == [1]


def test_c_is_grounded_se_lit_par_boite_et_une_boite_absente_est_fausse(sortie_sonde):
    assert sortie_sonde["grounded"] == [1, 0, 0]


def test_c_get_collision_tile_traverse_la_boite_et_une_boite_absente_rend_0(sortie_sonde):
    """Le stub de la sonde répond x*10 + y : la valeur prouve que les coordonnées
    passent telles quelles, la boîte absente que la porte est fermée."""
    assert sortie_sonde["collision_tile"] == [37, 0]


def test_c_une_boite_inactive_ne_touche_personne(sortie_sonde):
    assert sortie_sonde["overlap_inactive_autre"] == [0, 0, 0]
    assert sortie_sonde["overlap_inactive_moi"] == [0]
    assert sortie_sonde["overlap_absente"] == [0]


def test_c_les_drapeaux_du_build(sortie_sonde):
    assert sortie_sonde["affine_sans_slot"] == [0]
    assert sortie_sonde["affine_slot_zero"] == [1]       # le slot 0 EST un slot
    assert sortie_sonde["screen_space"] == [1]


def test_activer_une_apparence_repose_les_constantes_du_sprite_d_arrivee(sortie_sonde):
    """(apparence, état, frame, largeur, hauteur, banque, auto_dir, timer) : ligne
    `base + 1` de la table, animation à zéro."""
    assert sortie_sonde["appearance_set"] == [1, 0, 0, 8, 8, 2, 1, 0]


def test_un_acteur_sans_entree_ignore_le_changement_d_apparence(sortie_sonde):
    assert sortie_sonde["appearance_sans_entree"] == [0]


def test_play_anim_ignore_un_etat_absent_et_repart_de_zero_sinon(sortie_sonde):
    assert sortie_sonde["anim_absente"] == [2, 6]
    assert sortie_sonde["anim_reelle"] == [1, 0]


def test_un_porteur_mono_apparence_ne_lit_jamais_la_ligne_d_un_autre(sortie_sonde):
    assert sortie_sonde["appearance_mono"] == [55]           # inchangé


# ── Tranche 2 : caméra, scène, fond ──────────────────────────────────

def _lua_scene(src: str):
    """Compile un script de scène (le récepteur `self` est absent) avec une caméra « Boss »."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball", anim_names=["idle"],
                                        camera_names=["Boss"]))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"]))
    return [e.message for e in errors if e.level == "error"], code


def test_camera_margin_et_frame_se_lisent_et_s_ecrivent_en_vec2():
    errs, code = _lua_scene(
        "function on_update(self)\n"
        "  camera.margin = vec2(60, 30)\n"
        "  camera.frame = vec2(240, 120)\n"
        "  if camera.margin.x > 0 and camera.frame.y < 160 then self:show() end\n"
        "end\n")
    assert errs == []
    assert "camera_set_margin((Vec2){60, 30})" in code
    assert "camera_set_frame((Vec2){240, 120})" in code
    assert "camera_get_margin().x" in code
    assert "camera_get_frame().y" in code


def test_camera_name_se_compare_par_son_nom_et_ne_s_ecrit_pas():
    errs, code = _lua_scene(
        "function on_update(self)\n"
        "  if camera.name == \"Boss\" then self:show() end\n"
        "end\n")
    assert errs == []
    assert "(camera_get_active() == CAM_BOSS)" in code
    errs, _ = _lua_scene("function on_update(self)\n  camera.name = \"Boss\"\nend\n")
    assert errs, "camera.name est en lecture seule"


def test_une_camera_inconnue_est_refusee_a_la_comparaison():
    errs, _ = _lua_scene("function on_update(self)\n"
                         "  if camera.name == \"Nulle\" then self:show() end\nend\n")
    assert errs, "une caméra qui n'existe pas doit être refusée à la compilation"


def test_scene_scroll_h_v_sont_en_lecture_seule():
    errs, code = _lua_scene(
        "function on_update(self)\n"
        "  if scene.scroll_h and not scene.scroll_v then self:show() end\n"
        "end\n")
    assert errs == []
    assert "g_scene_scroll_h" in code and "g_scene_scroll_v" in code
    errs, _ = _lua_scene("function on_update(self)\n  scene.scroll_h = false\nend\n")
    assert errs, "scene.scroll_h est en lecture seule"


def test_layer_scroll_speed_se_lit_et_s_ecrit_en_pourcent():
    errs, code = _lua_scene(
        "function on_update(self)\n"
        "  layer:get(1).scroll_speed = 50\n"
        "  if layer:get(1).scroll_speed > 0 then self:show() end\n"
        "end\n")
    assert errs == []
    assert "layer_set_scroll_speed(1, 50)" in code
    assert "layer_get_scroll_speed(1)" in code


def test_c_la_camera_serre_sa_marge_et_son_cadre(sortie_sonde):
    assert sortie_sonde["cam_active"] == [3]
    assert sortie_sonde["cam_margin"] == [60, 0]
    assert sortie_sonde["cam_frame_borne"] == [240, 1]
    assert sortie_sonde["cam_frame_reduit"] == [240, 100]
    assert sortie_sonde["cam_frame_plein"] == [240, 160]


def test_c_la_vitesse_de_parallax_est_en_pourcent_et_avance_pas_a_pas(sortie_sonde):
    assert sortie_sonde["speed_50"] == [50, 128]                 # 50 % = 128 en Q8
    assert sortie_sonde["speed_incrementale"] == [1, 110]        # aucun pas perdu par l'arrondi
    assert sortie_sonde["speed_negative"] == [-20]               # un parallax inversé se relit
    assert sortie_sonde["speed_voisin"] == [0]                   # l'écriture ne déborde pas


def test_scene_collision_layer_est_un_numero_de_fond_en_lecture_seule():
    errs, code = _lua_scene(
        "function on_update()\n  layer:get(scene.collision_layer):hide()\nend\n")
    assert errs == []
    assert "layer_show(g_scene_collision_layer, 0)" in code
    errs, _ = _lua_scene("function on_update()\n  scene.collision_layer = 1\nend\n")
    assert errs


def test_layer_pal_bank_se_lit_pour_recolorer_et_ne_s_ecrit_pas():
    _, code = _lua_scene(
        "function on_update()\n  palette:set_bg(layer:get(1).pal_bank, \"Nuit\")\nend\n")
    assert "layer_get_pal_bank(1)" in code
    errs, _ = _lua_scene("function on_update()\n  layer:get(1).pal_bank = 2\nend\n")
    assert errs, "layer.pal_bank est en lecture seule"
