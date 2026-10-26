"""L'API dit ce que l'inspecteur règle — tranche 1 : acteur, sprite, collision.

Règle : tout champ
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


def test_collision_tile_at_interroge_directement_le_monde():
    """La nouvelle porte ne demande aucune CollisionBox : la carte appartient
    à la scène, pas à l'acteur qui pose la question."""
    errs, code = _lua("function on_update(self)\n"
                      "  local t = collision:tile_at(self.position.x, self.position.y)\n"
                      "end\n")
    assert errs == []
    assert "collision_map_tile(actor_get_position(self).x, actor_get_position(self).y)" in code


def test_un_champ_d_une_valeur_composee_de_la_boite_s_ecrit():
    errs, code = _lua("function on_update(self)\n"
                      "  local hb = self:collision_box(\"body\")\n  hb.size.x = 3\nend\n")
    assert errs == []
    assert "_field.x = 3;" in code


def test_un_champ_inconnu_sur_une_boite_est_refuse():
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n  hb.width = 3\nend\n")
    assert errs and "width" in errs[0] and "size" in errs[0]
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"body\")\n"
                   "  if hb.width > 1 then self:show() end\nend\n")
    assert errs and "width" in errs[0]


def test_un_tag_de_boite_inconnu_est_refuse_a_la_compilation():
    errs, _ = _lua("function on_update(self)\n"
                   "  local hb = self:collision_box(\"hitboks\")\nend\n")
    assert errs and "hitboks" in errs[0] and "hitbox" in errs[0]


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


def test_c_un_contact_par_couple_de_tags_le_premier_ne_masque_pas_le_suivant(sortie_sonde):
    """Régression : `on_collision_enter` ne rapportait que la PREMIÈRE paire de
    boîtes d'un couple d'acteurs. Un joueur qui retombe sur une pièce la touche
    d'abord des pieds : le contact « corps » arrivait ensuite sans événement.
    Bit (i*MAX_BOXES + j) ; ici MAX_BOXES = 4, corps = tag 0, pieds = tag 1."""
    assert sortie_sonde["mask_pieds"] == [1 << (1 * 4 + 0)]
    assert sortie_sonde["mask_les_deux"] == [(1 << (0 * 4 + 0)) | (1 << (1 * 4 + 0))]
    assert sortie_sonde["mask_loin"] == [0]
    assert sortie_sonde["mask_meme_tag"] == [1]         # un seul contact, pas deux
    assert sortie_sonde["mask_inactive"] == [1]         # seul le corps touche encore


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
    """(apparence, état, frame, largeur, hauteur, banque, facing_auto, timer) : ligne
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


def test_layer_pal_bank_se_lit_pour_recolorer_et_ne_s_ecrit_pas():
    _, code = _lua_scene(
        "function on_update()\n  palette:set_bg(layer:get(1).pal_bank, \"Nuit\")\nend\n")
    assert "layer_get_pal_bank(1)" in code
    errs, _ = _lua_scene("function on_update()\n  layer:get(1).pal_bank = 2\nend\n")
    assert errs, "layer.pal_bank est en lecture seule"

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


def test_c_la_camera_reste_dans_un_monde_plus_etroit_que_l_ecran(sortie_sonde):
    """Régression : bornes < écran => `hi < lo`, et le second clamp poussait la
    caméra à gauche/au-dessus du monde."""
    assert sortie_sonde["cam_large"] == [170, 20]       # 10+400-240, y borné à 20
    assert sortie_sonde["cam_etroit_haut"] == [10, 20]  # collée au bord
    assert sortie_sonde["cam_etroit_bas"] == [10, 20]


def test_c_une_division_par_zero_donne_zero_et_move_to_ignore_une_vitesse_negative(sortie_sonde):
    assert sortie_sonde["div2"] == [0, 3]
    assert sortie_sonde["div3"] == [3, 0, 0]
    assert sortie_sonde["move_sur_cible"] == [5, 5]
    assert sortie_sonde["move_vitesse_negative"] == [5, 5]


def test_c_atan2_arrondit_au_degre_le_plus_proche(sortie_sonde):
    """Régression : la dichotomie rendait le degré passant, donc 1 pour 0,06°."""
    assert sortie_sonde["atan2"] == [0, 45, 90, 180, 225, 271]


def test_c_les_courbes_ont_leurs_bornes_et_leur_milieu(sortie_sonde):
    assert sortie_sonde["ease_bornes"] == [10, 90, 10, 7]
    assert sortie_sonde["ease_milieu"] == [20, 80, 50]


def test_c_le_sinus_replie_la_table_sur_les_quatre_quadrants(sortie_sonde):
    assert sortie_sonde["sin"] == [0, 128, 256, 128, -128, -256, -4, -128]
    assert sortie_sonde["cos"] == [256, -256, 0]


def test_c_wobble_demarre_a_moins_amount_finit_a_zero_et_survit_a_une_duree_nulle(sortie_sonde):
    assert sortie_sonde["wobble"] == [350, 0, 0]


def test_c_la_marge_de_suivi_est_bornee_a_la_moitie_de_l_ecran(sortie_sonde):
    assert sortie_sonde["marge"] == [120, 0]
    assert sortie_sonde["marge_y"] == [7, 80]


# ── Une référence d'acteur ne désigne plus rien quand l'emplacement change de main ─────────

def test_c_une_reference_resout_tant_que_l_emplacement_n_a_pas_change_de_main(sortie_sonde):
    assert sortie_sonde["ref_make"] == [1, 0]        # non nulle ; nil -> 0
    assert sortie_sonde["ref_get"] == [1, 1]
    assert sortie_sonde["ref_inactif"] == [1]        # désactivé : toujours adressable
    assert sortie_sonde["ref_indice"] == [1]


def test_c_une_reference_perimee_rend_nil_apres_destruction_et_apres_reoccupation(sortie_sonde):
    assert sortie_sonde["ref_detruit"] == [1]
    assert sortie_sonde["ref_reoccupe"] == [1]       # ne désigne pas l'occupant suivant
    assert sortie_sonde["ref_neuve"] == [1, 1]


# ── Détruit libère l'emplacement, désactivé le garde ──────────────────────────────────────

def test_c_detruit_libere_l_emplacement_desactive_le_garde(sortie_sonde):
    assert sortie_sonde["vie_occupes"] == [2, 1]
    assert sortie_sonde["vie_desactive"] == [1, 2]           # toujours adressable, toujours occupé
    assert sortie_sonde["vie_detruit"] == [1, 0, 1]          # nil, alive = 0, un de moins


def test_c_les_instances_d_un_modele_se_parcourent_par_rang_vivant(sortie_sonde):
    assert sortie_sonde["vie_nth"] == [1, 1, 1, 1]           # la 1re vivante, puis rien
    assert sortie_sonde["vie_nth_ordre"] == [1, 1]           # l'ordre est celui des emplacements
    assert sortie_sonde["vie_groupe"] == [1]                 # la table dit où sont les racines
    assert sortie_sonde["vie_eclate"] == [1, 1]              # ni contiguës, ni dans l'ordre des emplacements


def test_c_le_pool_partage_se_parcourt_par_le_modele_de_chaque_emplacement(sortie_sonde):
    assert sortie_sonde["pool_modele"] == [1, 1, 0]
    assert sortie_sonde["pool_nth"] == [1, 1]
    assert sortie_sonde["pool_mixte"] == [2, 1, 1]       # les posés (la table), puis le pool
    assert sortie_sonde["pool_hw"] == [0]                # au-delà du plus haut emplacement utilisé : rien
    assert sortie_sonde["pool_etat"] == [1]              # un bloc d'état par `inst`


def test_c_un_groupe_garde_sa_partie_detruite_et_rend_tout_avec_sa_racine(sortie_sonde):
    assert sortie_sonde["grp_occupe"] == [0, 0, 0, 1]      # le groupe est occupé, l'emplacement suivant libre
    assert sortie_sonde["grp_partie"] == [0, 0, 3]         # la partie détruite n'est PAS libre ; le curseur recule jusqu'à elle
    assert sortie_sonde["grp_racine"] == [1, 1, 1, 0, 0]   # la racine détruite rend le groupe, parties effacées
    assert sortie_sonde["grp_acces"] == [2, 2, 2, 5, 1, 1]   # racine d'une partie 1, d'une partie 2, d'une racine, d'un plat ; partie k
    assert sortie_sonde["grp_sans_table"] == [3]
    assert sortie_sonde["pose_parent"] == [1, 1, 1, 1, 1]       # enfant, petit-enfant, sommet (aucun), autre chaîne, nil
    assert sortie_sonde["pose_racine"] == [1, 1, 1, 1, 1]
    assert sortie_sonde["pose_enfant"] == [1, 1]
    assert sortie_sonde["pose_milieu_mort"] == [1, 1, 1]        # parent mort : nil ; mais le sommet reste la racine ; l'enfant mort se lit nil
    assert sortie_sonde["pose_sommet_mort"] == [1, 1]
    assert sortie_sonde["pose_sans_table"] == [1, 1]
    assert sortie_sonde["nth_fuzz"] == [0, 1]         # 0 écart avec un parcours complet, sur plus de 1000 vérifications
    assert sortie_sonde["nth_curseur"] == [1]         # et le curseur a bien suivi les boucles qui avancent de 1
    assert sortie_sonde["grp_racine_de"] == [1, 1, 1, 1]   # partie, partie de partie, racine (elle-même), nil
    assert sortie_sonde["grp_parent_de"] == [1, 1, 1, 1]   # la racine, la partie 1, aucun pour une racine, nil
    assert sortie_sonde["grp_apres_perte"] == [1, 1, 1]    # parent détruit : nil ; la racine reste ; l'acteur détruit n'a pas de racine
    assert sortie_sonde["grp_curseur"] == [2]
    assert sortie_sonde["ref_signe"] == [1, 1]        # génération 0x8000 : handle négatif, résolu
    assert sortie_sonde["ref_300"] == [1]             # au-delà des 256 d'un octet, toujours périmée
    assert sortie_sonde["ref_boucle"] == [1, 1]       # le compteur boucle : la référence meurt, sans devenir nil
    assert sortie_sonde["ref_zero"] == [1, 1]         # génération 0, emplacement 0 : ce n'est pas « aucun acteur »
    assert sortie_sonde["grp_bits_partie"] == [(1 << 2) | (1 << 4)]   # emplacements 2 et 4 vivants, 3 détruit
    assert sortie_sonde["grp_bits_racine"] == [0]
