"""Console de build cliquable (U3, volet A) — un `fichier.lua:ligne` du journal
saute à la bonne ligne du script.

Trois maillons : le parseur (pur), le saut de ligne de l'éditeur, et l'ouverture
à une ligne du Script Editor. Le clic souris lui-même (QMouseEvent + géométrie)
n'est pas rejoué ici — c'est `_location_at` qui porte la logique, testé via le
parseur.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ui.common.build_panel import parse_build_location, BuildConsole


# ── Le parseur (pur) ──────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("[error] Titre.lua:2 : syntax error", ("Titre.lua", 2)),
    ("[error] prefab Ball (Ball.lua):3 : ...", ("Ball.lua", 3)),
    ("[error] camera Cam (follow.lua):10 : ...", ("follow.lua", 10)),
    ("[warn]  Hero.lua: message sans ligne", None),   # pas de :ligne
    ("[build] 5 scène(s)", None),
    ("  src/main.c:42: error: foo", None),            # gcc C, pas un .lua
])
def test_parse_build_location(text, expected):
    assert parse_build_location(text) == expected


# ── Le saut de ligne de l'éditeur ─────────────────────────────────
def test_lua_editor_goto_line(qapp):
    from ui.script_editor.lua_editor import LuaEditor
    ed = LuaEditor()
    ed.setPlainText("l1\nl2\nl3\nl4\nl5")
    ed.goto_line(3)
    assert ed.textCursor().blockNumber() == 2   # 1-indexé → block 2

    ed.goto_line(999)                            # hors plage → dernière ligne
    assert ed.textCursor().blockNumber() == 4


# ── Ouverture à une ligne (Script Editor) ─────────────────────────
def test_open_script_at_line(qapp, tmp_path):
    from ui.script_editor.script_editor import ScriptEditorScreen
    sp = tmp_path / "Titre.lua"
    sp.write_text("function on_start()\n  local x = 1\n  bad line here\nend\n",
                  encoding="utf-8")
    scr = ScriptEditorScreen()
    scr.open_script(Path(sp), line=3)
    assert scr._editor.textCursor().blockNumber() == 2


# ── La console émet l'emplacement du clic ─────────────────────────
def test_console_emits_location(qapp):
    console = BuildConsole()
    console.appendPlainText("[error] Titre.lua:2 : syntax error")
    got = []
    console.location_activated.connect(lambda f, l: got.append((f, l)))
    # cursorForPosition en haut à gauche tombe sur la 1re (seule) ligne.
    from PyQt6.QtCore import QPoint
    loc = console._location_at(QPoint(4, 4))
    assert loc == ("Titre.lua", 2)
