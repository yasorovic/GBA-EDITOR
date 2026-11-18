"""`data.table.<Nom>` : la nature de la donnée se lit dans le code.

Tranche 3a du chantier des cartes de valeurs peintes. Le module `data` gagne un
niveau par nature : `data.table.<Nom>` pour une table du projet,
`data.grid.<Nom>` pour une grille peinte de la scène courante (sa porte Lua
viendra avec la tranche 3b). L'ancienne forme `data.<Nom>` est refusée, avec un
message qui donne la nouvelle : une grammaire, pas deux.
"""
from __future__ import annotations

from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.parser import (
    DATA_GRID_NS, DATA_TABLE_NS, data_legacy_ref, data_table_ref, parse,
)

TABLES = {"Objets": (["prix", "nom"], 3)}


def _handler(corps: str) -> str:
    return f"function on_update()\n{corps}\nend\n"


def _erreurs(corps: str, **kwargs) -> list[str]:
    ctx = BuildContext(actor_name="Ball", data_tables=TABLES, **kwargs)
    return [e.message for e in check(parse(_handler(corps)), ctx) if e.level == "error"]


def _code(corps: str) -> str:
    code, _globals, _consts = generate(parse(_handler(corps)), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball"], data_tables=TABLES))
    return code


# ── Les reconnaisseurs, source unique ─────────────────────────────

def _valeur(corps: str):
    """La valeur du premier `local` du handler : l'expression à reconnaître."""
    return parse(_handler(corps)).functions[0].body[0].value


def test_le_reconnaisseur_voit_la_nouvelle_forme_et_pas_l_ancienne():
    """Un seul reconnaisseur, dans `parser.py` : le checker, le codegen et
    l'inférence de types le lisent là."""
    nouvelle = _valeur("local n = #data.table.Objets").operand
    ancienne = _valeur("local n = #data.Objets").operand
    assert data_table_ref(nouvelle) == "Objets"
    assert data_table_ref(ancienne) is None
    assert data_legacy_ref(ancienne) == "Objets"


def test_la_nature_n_est_pas_prise_pour_un_nom_de_table():
    """`data.table` et `data.grid` nomment la NATURE : ni l'un ni l'autre n'est
    une table dont il faudrait se plaindre."""
    for nature in (DATA_TABLE_NS, DATA_GRID_NS):
        assert data_legacy_ref(_valeur(f"local n = data.{nature}")) is None


# ── Ce que le checker accepte, et ce qu'il refuse ─────────────────

def test_la_nouvelle_forme_passe():
    assert _erreurs("local p = data.table.Objets[1].prix") == []
    assert _erreurs("local n = #data.table.Objets") == []


def test_l_ancienne_forme_est_refusee_avec_la_forme_a_ecrire():
    (msg,) = [m for m in _erreurs("local p = data.Objets[1].prix")
              if "data.Objets" in m]
    assert "data.table.Objets" in msg
    assert "data.grid.<Name>" in msg


def test_une_grille_n_est_pas_prise_pour_l_ancienne_forme_d_une_table():
    """`data.grid.<Nom>` est reconnu comme une GRILLE, pas comme l'ancienne forme
    d'une table. Ce que vaut cet accès se juge dans la scène du script : voir
    `test_grid_read.py`, qui lui donne un contexte de scène."""
    assert _erreurs("local v = data.grid.Terrain:at(0, 0)") == []


def test_une_nature_citee_seule_est_refusee():
    """`data.table` ne désigne aucune donnée : il manque le nom."""
    for forme in ("data.table", "data.grid"):
        (msg,) = _erreurs(f"local v = {forme}")
        assert f"{forme}: name the one you mean" in msg


def test_une_faute_ne_donne_qu_un_message():
    """Le nœud complet parle ; on ne redescend pas dire que la nature est nue."""
    assert len(_erreurs("local v = data.grid")) == 1
    assert len(_erreurs("local p = data.Objets[1].prix")) == 1


def test_les_messages_de_table_nomment_la_forme_reelle():
    """Une table inconnue, un rang hors bornes, une colonne absente : les trois
    messages s'écrivent comme le script doit s'écrire."""
    assert any("data.table.Nope: data table not found" in m
               for m in _erreurs("local p = data.table.Nope[1].prix"))
    assert any("data.table.Objets[9]: out of bounds" in m
               for m in _erreurs("local p = data.table.Objets[9].prix"))
    assert any("data.table.Objets[…].nope" in m
               for m in _erreurs("local p = data.table.Objets[1].nope"))
    assert any("data.table.Objets is indexed by its ROW" in m
               for m in _erreurs("local p = data.table.Objets[1][2]"))


def test_une_table_reste_impossible_a_ecrire():
    (msg,) = [m for m in _erreurs("data.table.Objets[1].prix = 2") if "cannot be written" in m]
    assert "data.table.Objets" in msg


# ── Le renommage suit la nouvelle forme ───────────────────────────

def test_renommer_une_table_reecrit_les_scripts_qui_la_citent(tmp_path):
    """Le reconnaisseur de `refactor` lit l'arbre de `luaparser`, pas celui du
    checker : s'il ratait le niveau de la nature, un renommage cesserait en
    silence de réécrire les scripts."""
    from core.models.data_table import DataColumn, DataTable
    from core.project import Project

    p = Project.create(tmp_path / "Game", "Game")
    table = DataTable(name="Objets", columns=[DataColumn(name="prix")], rows=[{"prix": 7}])
    p.data_tables.append(table)
    script = (p.user_library_dir / "scripts") / "Lecture.lua"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("function on_update()\n"
                      "    local p = data.table.Objets[1].prix\n"
                      "end\n", encoding="utf-8")
    p.save()

    assert p.rename_data_table(table, "Trésors") is False   # pas un identifiant
    assert p.rename_data_table(table, "Tresors") is True
    assert "data.table.Tresors[1].prix" in script.read_text(encoding="utf-8")

    assert p.rename_data_column(table, table.columns[0], "cout") is True
    assert "data.table.Tresors[1].cout" in script.read_text(encoding="utf-8")


# ── Ce que le codegen émet ────────────────────────────────────────

def test_le_nombre_de_lignes_reste_une_constante_de_build():
    assert "int n = 3;" in _code("local n = #data.table.Objets")


def test_une_cellule_sort_en_indexation_du_tableau_emis():
    code = _code("local p = data.table.Objets[2].prix")
    assert "g_data_Objets[1].prix" in code
