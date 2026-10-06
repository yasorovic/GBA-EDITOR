"""Renommer une clé de texte ne doit désynchroniser aucune zone d'interface.

`region.text_key` est une COPIE de chaîne, pas l'id stable du texte (cf.
`models/text.py`). Le script Lua qui cite une clé était déjà réécrit par
`rename_lua_refs` ; les zones d'interface (`UIText.text_key`), l'autre des
deux seuls référents d'une clé (cf. `TextUsage`), ne l'étaient pas — un
rangement qui recale une clé AUTO désynchronisait silencieusement l'écran de
scène. Bug réel rencontré sur le projet démo Fonts&Texts (2026-08-27).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.ui_region import UILayout, UIText

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    zone = UIText(name="bubble", w=64, h=16)
    layout = UILayout(name="hud")
    layout.elements.append(zone)
    p.ui_layouts.append(layout)
    t = p.new_text(content="Hi", path=["Dialogue", "Greeting"])
    zone.text_key = t.key
    return p, layout, zone, t


def test_renommage_manuel_repointe_la_zone(projet):
    p, _lay, zone, t = projet
    old_key = t.key

    assert p.rename_text_key(t, "salut") is True

    assert t.key == "salut"
    assert zone.text_key == "salut"
    assert zone.text_key != old_key


def test_resync_automatique_sur_rangement_repointe_la_zone(projet):
    p, _lay, zone, t = projet
    assert t.auto_key is True   # jamais renommée à la main : la clé suit le chemin

    t.path = ["Dialogue", "Farewell"]
    new_key = p.resync_text_key(t)

    assert new_key is not None
    assert t.key == new_key
    assert zone.text_key == new_key


def test_le_repointage_est_persiste_sur_le_disque(projet):
    import json
    p, layout, zone, t = projet
    p.rename_text_key(t, "salut")

    on_disk = json.loads(p.ui_layouts._path(layout.name).read_text(encoding="utf-8"))
    region = next(e for e in on_disk["elements"] if e["name"] == zone.name)
    assert region["text_key"] == "salut"


def test_une_clef_nommee_a_la_main_n_est_pas_touchee_par_un_rangement(projet):
    """`resync_text_key` est un no-op sur une clé détachée : la zone ne doit
    donc pas non plus bouger — elle suit la clé, pas le chemin."""
    p, _lay, zone, t = projet
    p.rename_text_key(t, "salut")  # détache la clé (auto_key -> False)
    assert zone.text_key == "salut"

    t.path = ["Ailleurs"]
    assert p.resync_text_key(t) is None
    assert t.key == "salut"
    assert zone.text_key == "salut"


def test_texte_cree_depuis_l_inspecteur_reste_lie_apres_rangement(projet):
    """Le geste naturel ne doit jamais laisser le canvas sur une clé morte.

    La première saisie dans l'inspecteur crée l'entrée et accroche la zone ; le
    rangement effectué ensuite dans l'écran Texte peut recalculer sa clé auto,
    mais la zone doit continuer d'afficher cette même entrée.
    """
    from ui.text_editor.text_commands import CreateTextForElementCmd, SetTextPathCmd

    p, _lay, zone, _old_text = projet
    zone.text_key = ""                 # nouvelle zone, sans entrée au départ

    create = CreateTextForElementCmd(
        p, zone, "Bienvenue", path=["HUD", "Accueil"])
    create.execute()
    text = p.get_text(zone.text_key)
    assert text is not None
    text_id = text.id

    file_away = SetTextPathCmd(
        p, [(text, list(text.path), ["Dialogue", "Accueil"])],
        label="File text")
    file_away.execute()

    assert p.region_text(zone) is text
    assert p.region_text(zone).id == text_id
    assert zone.text_key == text.key
