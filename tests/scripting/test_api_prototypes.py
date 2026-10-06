"""L'extracteur de prototypes d'API — le « 4e lecteur » (A2).

Les prototypes que voient les unités de scène/acteur sont GÉNÉRÉS depuis
`gba_engine.h` pour le sous-ensemble exposé par `api.py`, au lieu d'être
redéclarés à la main dans `runtime_api_inline.h`. Ces tests tiennent l'extracteur
(le maillon fragile) ; les deux projets démo compilés en CI tiennent le reste.
"""
from __future__ import annotations

from codegen.runtime_codegen.api_prototypes import (
    extract_prototype, build_prototype_block, exposed_engine_names,
    build_enum_defines, build_window_region_defines,
)


def test_extract_signature_simple():
    src = "int  foo (int a, int b);"
    assert extract_prototype(src, "foo") == "int foo(int a, int b)"


def test_extract_static_inline_definition():
    src = "static inline void bar(int x){ do_thing(x); }"
    assert extract_prototype(src, "bar") == "void bar(int x)"


def test_ignore_un_appel_dans_un_corps():
    # Un APPEL au milieu de code n'est pas une déclaration : l'extracteur passe
    # au suivant jusqu'à la vraie signature. (Entrée déjà sans commentaires —
    # c'est `build_prototype_block` qui les retire, cf. test suivant.)
    src = "void other(void){ baz(1); }\nint baz(int n);\n"
    assert extract_prototype(src, "baz") == "int baz(int n)"


def test_block_ignore_les_commentaires():
    # `build_prototype_block` retire les commentaires AVANT d'extraire : un nom
    # cité dans un commentaire ne doit pas produire un prototype bidon.
    src = "/* qux(int) fait ceci */\nint qux(int n);\n"
    decls, unparsed = build_prototype_block(src, {"qux"})
    assert decls == ["extern int qux(int n);"]
    assert unparsed == []


def test_absent_rend_none():
    assert extract_prototype("int foo(void);", "absent") is None


def test_block_from_real_engine_is_complete():
    """Sur le vrai `gba_engine.h` + le vrai catalogue : chaque nom exposé PRÉSENT
    dans le moteur doit être extractible (sinon le header d'API serait incomplet
    et le build casserait). L'invariant que la génération exige."""
    from core.app_paths import RUNTIME_DIR
    eng = (RUNTIME_DIR / "include" / "gba_engine.h").read_text(
        encoding="utf-8", errors="ignore")
    decls, unparsed = build_prototype_block(eng, exposed_engine_names())
    assert unparsed == [], f"noms présents mais illisibles : {unparsed}"
    assert decls, "aucun prototype extrait — catalogue ou moteur introuvable ?"
    # Toutes des redéclarations externes, une par ligne.
    assert all(d.startswith("extern ") and d.endswith(");") for d in decls)


# ── Les #define d'énums, générés depuis api.py ────────────────────
def test_enum_defines_couvrent_le_catalogue():
    from scripting.api import hardware_enum_defines
    lines = build_enum_defines()
    # Une ligne #define par (constante, valeur) du catalogue, valeur comprise.
    assert len(lines) == len(hardware_enum_defines())
    emitted = {tuple(l.split()[1:3]) for l in lines}   # {(constante, valeur)}
    assert all((sym, str(v)) in emitted for sym, v in hardware_enum_defines())


def test_enum_defines_nexpose_pas_winr():
    # WINR_* n'est pas une énumération du catalogue : il a sa propre voie
    # (build_window_region_defines, extraite de gba_engine.h), pas build_enum_defines.
    assert not any("WINR_" in l for l in build_enum_defines())


# ── Les régions de window, extraites de gba_engine.h ──────────────
def test_window_region_defines_extraits_du_moteur():
    from core.app_paths import RUNTIME_DIR
    eng = (RUNTIME_DIR / "include" / "gba_engine.h").read_text(
        encoding="utf-8", errors="ignore")
    lines = build_window_region_defines(eng)
    syms = {l.split()[1] for l in lines}
    # Les quatre régions matérielles, telles que le moteur les définit et les
    # utilise (case WINR_0: …).
    assert {"WINR_0", "WINR_1", "WINR_OBJ", "WINR_OUT"} <= syms
    assert all(l.startswith("#define WINR_") for l in lines)


def test_window_region_defines_valeurs():
    src = "#define WINR_0 0\n#define WINR_OBJ   2\n/* pas #define: WINR_X */\n"
    assert build_window_region_defines(src) == ["#define WINR_0   0", "#define WINR_OBJ 2"]
