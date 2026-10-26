"""Le plan du code chaud en IWRAM : quelles phases du tick y vont, et lesquelles repartent en ROM quand la place manque."""
from __future__ import annotations

from codegen import iwram_plan as ip

K = 1024


def test_les_modes_sont_lus_dans_le_main_genere():
    texte = ("#ifndef BS_IWRAM_Level_render\n#define BS_IWRAM_Level_render 2   /* 2 = ARM in IWRAM, 0 = ROM */\n#endif\n"
             "#ifndef BS_IWRAM_Level_physics\n#define BS_IWRAM_Level_physics 0   /* 2 = ARM in IWRAM, 0 = ROM */\n#endif\n")
    assert ip.read_modes(texte) == {("Level", "render"): 2, ("Level", "physics"): 0}


def test_les_tailles_sont_lues_dans_la_liste_des_symboles():
    nm = ("00000000 00001c40 t scene_tick_Level_render\n00001c40 00000100 t scene_tick_Level_hooks\n"
          "00000000 0000002c t scene_tick_Level\n00000000 00000010 T autre\n")
    assert ip.read_sizes(nm) == {("Level", "render"): 0x1c40, ("Level", "hooks"): 0x100}


def test_tout_ce_qui_tient_reste_en_iwram():
    modes = {("A", "render"): 2, ("A", "hooks"): 2}
    plan = ip.make_plan(modes, {("A", "render"): 6 * K, ("A", "hooks"): 400}, static_bytes=6 * K)
    assert not plan.changed and plan.modes == modes and plan.placed == 6 * K + 400


def test_la_physique_enorme_part_avant_l_affichage_et_les_petites_boucles_restent():
    modes = {("A", "render"): 2, ("A", "physics"): 2, ("A", "hooks"): 2, ("A", "late"): 2}
    sizes = {("A", "render"): 7 * K, ("A", "physics"): 23 * K, ("A", "hooks"): 300, ("A", "late"): 700}
    plan = ip.make_plan(modes, sizes, static_bytes=6 * K)
    assert plan.dropped == [("A", "physics")]
    assert plan.modes[("A", "render")] == plan.modes[("A", "hooks")] == plan.modes[("A", "late")] == ip.ARM
    assert plan.placed <= plan.budget


def test_la_pile_garde_sa_reserve():
    # 32 Ko - 4 Ko de pile - 6 Ko de données = 22 Ko pour le code placé
    plan = ip.make_plan({("A", "render"): 2}, {("A", "render"): 23 * K}, static_bytes=6 * K)
    assert plan.budget == 22 * K and plan.dropped == [("A", "render")] and plan.placed == 0


def test_toutes_les_scenes_comptent_car_le_code_place_y_reste():
    modes = {("A", "render"): 2, ("B", "render"): 2}
    plan = ip.make_plan(modes, {("A", "render"): 12 * K, ("B", "render"): 12 * K}, static_bytes=6 * K)
    assert len(plan.dropped) == 1 and plan.placed == 12 * K          # une seule des deux tient


def test_les_defines_n_imposent_que_les_phases_renvoyees_en_rom():
    plan = ip.make_plan({("A", "render"): 2, ("A", "physics"): 2},
                        {("A", "render"): 4 * K, ("A", "physics"): 30 * K}, static_bytes=6 * K)
    assert ip.cflags(plan) == "-DBS_IWRAM_A_physics=0"


def test_la_place_sans_lien_se_compte_dans_les_objets_moins_le_code_deja_place():
    objets = [".bss 1000 0\n.data 200 0\n.iwram 5000 0\n.text 9999 0\n", ".bss 300 0\n"]
    assert ip.static_from_objects(objets, placed=5000) == 1500 + ip.LIBRARIES_IWRAM_ESTIMATE


def test_un_lien_qui_deborde_de_l_iwram_se_reconnait():
    assert ip.overflowed("ld.exe: region `iwram' overflowed by 120 bytes")
    assert ip.overflowed("ld.exe: address 0x300968c of rom.elf section `.init_array' is not within region `iwram'")
    assert not ip.overflowed("undefined reference to `foo'")
