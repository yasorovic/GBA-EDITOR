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


def test_les_phases_posees_se_lisent_a_l_adresse_du_binaire_lie():
    nm = ("03000100 00001c40 t scene_tick_A_render\n080001a0 00000100 t scene_tick_A_hooks\n"
          "03002000 00000020 T autre\n")
    assert ip.read_placed(nm) == {("A", "render")}


def test_un_plan_revise_au_dernier_essai_est_quand_meme_compile(tmp_path):
    from types import SimpleNamespace
    from codegen.rom_build import BuildWorker

    worker = object.__new__(BuildWorker)
    worker.toolchain = SimpleNamespace(resolve_binutil=lambda name: None)
    worker._emit = lambda event, *args: None
    worker._report_cmd = lambda proc, prefix: True
    makes = []

    def capture(cmd, prefix, cwd=None, env=None):
        makes.append(env["IWRAM_CFLAGS"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    worker._capture_cmd = capture

    # Il y a toujours une phase de plus à retirer : seul le plafond de révisions arrête la boucle.
    def plan(p, modes, proc, read_ram_use):
        victim = next(key for key, mode in modes.items() if mode != ip.ROM)
        return ip.Plan({**modes, victim: ip.ROM}, 0, 0, [victim])
    worker._iwram_plan = plan

    src, build = tmp_path / "src", tmp_path / "build"
    (build / "obj").mkdir(parents=True), src.mkdir()
    (src / "main.c").write_text("".join(f"#define BS_IWRAM_{s}_render 2\n" for s in "ABCDE"), encoding="utf-8")

    worker._make_fitting_iwram(SimpleNamespace(src_dir=src, build_dir=build, grit_out_dir=tmp_path / "grit"), "make", 1, {})

    revisions = BuildWorker._IWRAM_FIT_REVISIONS
    assert len(makes) == revisions + 1                                  # chaque révision a son make
    assert makes[-1].count("-D") == revisions                           # le dernier make porte toutes les révisions


def test_l_empreinte_change_avec_le_c_et_avec_les_options(tmp_path):
    (tmp_path / "a.c").write_text("int a;", encoding="utf-8")
    before = ip.fingerprint([tmp_path], "-DX")
    assert ip.fingerprint([tmp_path], "-DX") == before
    assert ip.fingerprint([tmp_path], "-DY") != before
    (tmp_path / "a.c").write_text("int b;", encoding="utf-8")
    assert ip.fingerprint([tmp_path], "-DX") != before


def test_le_plan_memorise_ne_vaut_que_pour_son_empreinte(tmp_path):
    memo = tmp_path / "iwram_plan.json"
    ip.save_memo(memo, "abc", [("A", "render")])
    assert ip.load_memo(memo, "abc") == [("A", "render")]
    assert ip.load_memo(memo, "autre") is None
    assert ip.load_memo(tmp_path / "absent.json", "abc") is None


def test_un_second_build_du_meme_c_reprend_le_plan_et_ne_compile_qu_une_fois(tmp_path):
    from types import SimpleNamespace
    from codegen.rom_build import BuildWorker

    worker = object.__new__(BuildWorker)
    worker.toolchain = SimpleNamespace(resolve_binutil=lambda name: None)
    worker._emit = lambda event, *args: None
    worker._report_cmd = lambda proc, prefix: True
    makes = []

    def capture(cmd, prefix, cwd=None, env=None):
        makes.append(env["IWRAM_CFLAGS"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    worker._capture_cmd = capture

    def plan(p, modes, proc, read_ram_use):        # ne tient que si ("A", "render") est en ROM
        if modes[("A", "render")] == ip.ROM:
            return None
        return ip.Plan({**modes, ("A", "render"): ip.ROM}, 0, 0, [("A", "render")])
    worker._iwram_plan = plan

    src, build = tmp_path / "src", tmp_path / "build"
    (build / "obj").mkdir(parents=True), src.mkdir()
    (src / "main.c").write_text("#define BS_IWRAM_A_render 2\n#define BS_IWRAM_B_render 2\n", encoding="utf-8")
    project = SimpleNamespace(src_dir=src, build_dir=build, grit_out_dir=tmp_path / "grit")

    worker._make_fitting_iwram(project, "make", 1, {})
    assert len(makes) == 2                                              # départ, puis le plan révisé
    makes.clear()
    worker._make_fitting_iwram(project, "make", 1, {})
    assert makes == ["-DBS_IWRAM_A_render=0"]                           # le plan mesuré sert de départ

    (src / "main.c").write_text("#define BS_IWRAM_A_render 2\n", encoding="utf-8")   # le C change : on recommence
    makes.clear()
    worker._make_fitting_iwram(project, "make", 1, {})
    assert makes[0] == ""
