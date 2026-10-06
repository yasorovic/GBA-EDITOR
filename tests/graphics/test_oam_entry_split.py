"""Marche 0a de « La struct Actor allégée » : l'état d'affichage vit dans
`OamEntry` (`g_oam_entries[]`), l'acteur ne garde que son identité, sa position,
sa collision et le lien `oam_entry`.

Le partage se lit dans le header lui-même : c'est la source de vérité du layout C,
et ce qu'un second lecteur (le writer OAM, les accesseurs) doit suivre."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = (ROOT / "runtime" / "include" / "actor_types_static.h").read_text(encoding="utf-8")
CODEGEN = ROOT / "editor" / "codegen" / "runtime_codegen"

# Les registres OAM et l'animation : à l'entrée OAM, jamais à l'acteur.
AFFICHAGE = ("frame", "anim_state", "timer", "anim_speed", "anim_length", "anim_loop",
             "anim_finished", "frame_w", "frame_h", "auto_dir", "visible", "flip_h",
             "flip_v", "pal_bank", "obj_mode", "priority", "screen_space",
             "offset_x", "offset_y", "pivot_x", "pivot_y", "affine_slot")


def _champs(struct_nom: str) -> set[str]:
    """Les noms de champs de premier niveau d'un `typedef struct <nom> {…} <nom>;`."""
    debut = HEADER.index(f"typedef struct {struct_nom} {{")
    fin = HEADER.index(f"}} {struct_nom};", debut)
    corps = re.sub(r"/\*.*?\*/", "", HEADER[debut:fin], flags=re.S)
    corps = re.sub(r"struct\s*\{.*?\}\s*\w+;", "", corps, flags=re.S)   # bloc `collision`
    noms: set[str] = set()
    for decl in corps.split(";"):
        decl = decl.split("{", 1)[-1].strip()
        if not decl:
            continue
        for morceau in decl.split(","):
            m = re.search(r"(\w+)(?:\[[^\]]*\])?\s*$", morceau.strip())
            if m:
                noms.add(m.group(1))
    return noms


def test_l_entree_oam_porte_tout_l_affichage():
    assert set(AFFICHAGE) <= _champs("OamEntry")


def test_l_acteur_ne_porte_plus_aucun_champ_d_affichage():
    actor = _champs("Actor")
    assert not actor & set(AFFICHAGE), sorted(actor & set(AFFICHAGE))


def test_l_acteur_garde_son_socle_et_le_lien():
    actor = _champs("Actor")
    assert {"x", "y", "vx", "vy", "name", "active", "dir_x", "dir_y",
            "oam_entry"} <= actor
    # Le transform MONDE reste à l'acteur (état de jeu, lisible sans affichage) ;
    # le LOCAL (`rotation`, `scale_*` de l'entrée) est un autre champ, d'un autre struct.
    assert {"rotation", "scale_x", "scale_y"} <= actor
    assert "} collision;" in HEADER


def test_aucun_emetteur_n_ecrit_l_affichage_sur_g_actors():
    """Un `g_actors[i].frame` émis compilerait encore si le champ revenait à
    l'acteur : on interdit donc l'écriture elle-même, pas seulement le résultat."""
    motif = re.compile(
        r"g_actors\[[^\]]+\]\.(sprite\b|" + "|".join(AFFICHAGE) + r")\b")
    for nom in ("main_gen.py", "gen_affine.py", "gen_sprite.py"):
        source = (CODEGEN / nom).read_text(encoding="utf-8")
        trouves = motif.findall(source)
        assert not trouves, f"{nom} : g_actors[..].{trouves[0]}"


def test_les_accesseurs_de_script_passent_par_le_lien():
    api = (ROOT / "runtime" / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    assert "actor_oam_entry(const Actor* s)" in api
    assert "g_oam_entries[s->oam_entry]" in api
    # Plus aucun accès direct à l'affichage par un `Actor*` : `s->frame`,
    # `s->sprite.frame`, `s->visible`… doivent tous passer par l'accesseur.
    directs = re.findall(r"\bs->(?:sprite\.)?(" + "|".join(AFFICHAGE) + r")\b", api)
    assert not directs, directs


def test_la_table_est_declaree_et_initialisee_avec_son_lien():
    source = (CODEGEN / "main_gen.py").read_text(encoding="utf-8")
    assert 'OamEntry g_oam_entries[{n_oam_entries}] EWRAM_DATA;' in source
    # scene_init remet TOUT acteur à -1 (sans entrée) : le lien se pose ensuite,
    # pour les seuls acteurs qui affichent un sprite…
    assert "g_actors[_i].oam_entry=-1" in source
    # …et le spawn le repose, puisqu'il remet l'acteur à zéro.
    assert "g_actors[_i] = (Actor){{0}}; g_actors[_i].oam_entry = {_e0 or -1};" in source


def test_l_acteur_sans_sprite_a_des_accesseurs_neutres():
    """Lien -1 : lecture = 0, écriture sans effet, jamais d'accès hors tableau."""
    api = (ROOT / "runtime" / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    corps = api[api.index("static inline OamEntry* actor_oam_entry"):]
    corps = corps.split("return &none;")[0]   # tout le corps, jusqu'au dernier return
    assert "if (s->oam_entry >= 0) return &g_oam_entries[s->oam_entry];" in corps
    assert "none = (OamEntry){0};" in corps and "none.affine_slot = -1;" in corps


# ── Types étroits ─────────────────────────────────────────────────────

def test_l_entree_oam_n_a_plus_aucun_int():
    """Une entrée par slot OAM, jusqu'à 128 : un drapeau sur 32 bits est du gaspillage."""
    debut = HEADER.index("typedef struct OamEntry {")
    corps = re.sub(r"/\*.*?\*/", "", HEADER[debut:HEADER.index("} OamEntry;")], flags=re.S)
    assert not re.search(r"\bint\b", corps), "OamEntry : un champ est resté en int"


def test_les_tailles_des_structs_ne_regressent_pas(tmp_path):
    """Mesuré par le compilateur hôte : `int` fait 4 octets sur les deux cibles, et
    le remplissage est le même — la taille GBA suit. Plafonds au 2026-09-25 :
    OamEntry 38 (92 avant ; 32 + `appearance` + `appearance_base`, marches 3a-3c, puis
    `pivot_x/y` sur 8 bits le 2026-10-04), Actor 68 (96 avant)."""
    import os, shutil, subprocess
    import pytest
    cc = os.environ.get("CC") or shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")
    if not cc:
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail("aucun compilateur C hôte — les tailles de structs ne sont PAS mesurées")
        pytest.skip("aucun compilateur C hôte")
    source = tmp_path / "taille.c"
    source.write_text(
        "#include <stdio.h>\n"
        "typedef unsigned char u8; typedef signed char s8;\n"
        "typedef unsigned short u16; typedef short s16; typedef unsigned int u32;\n"
        '#include "actor_types_static.h"\n'
        'int main(void){printf("%d %d ",(int)sizeof(OamEntry),(int)sizeof(Actor));return 0;}\n',
        encoding="utf-8")
    exe = tmp_path / "taille.exe"
    env = dict(os.environ)
    env["PATH"] = str(Path(cc).parent) + os.pathsep + env.get("PATH", "")
    r = subprocess.run([cc, "-I", str(ROOT / "runtime" / "include"), str(source), "-o", str(exe)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    oam, actor = map(int, subprocess.run([str(exe)], capture_output=True, text=True,
                                         env=env).stdout.split())
    assert oam <= 38 and actor <= 68, (oam, actor)
