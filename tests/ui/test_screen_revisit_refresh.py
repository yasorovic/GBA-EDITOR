"""Un écran se resynchronise à sa REVISITE, via `refresh()` (chantier « L'écran resynchronisé à sa
revisite »).

`Window._load_screen_for_project` ne charge un écran qu'à sa PREMIÈRE visite. Tout ce qu'un écran
capture alors (la table des textes, les catalogues d'autocomplétion, le catalogue de palettes) reste
figé tant que rien ne le relit : un nom né ensuite dans un autre écran n'apparaissait jamais, en
silence. Le correctif : `Window._show_screen` appelle `refresh()` à chaque revisite — bon marché,
sélection conservée.

Deux niveaux, dans ce fichier :
  · le gating de `_show_screen` (refresh en revisite, jamais à la première visite, jamais sans projet) ;
  · pour chaque écran concerné, qu'une entrée née hors de lui apparaît au prochain `refresh()`.
"""
from __future__ import annotations

from types import SimpleNamespace


# ── Le gating de `_show_screen` ───────────────────────────────────────────


class _FakeScreen:
    """Satisfait le contrat `ProjectScreen` (a `load_project`) et compte ses appels ; `refresh` est
    le crochet optionnel de revisite."""
    def __init__(self):
        self.loaded = 0
        self.refreshed = 0

    def load_project(self, project):
        self.loaded += 1

    def refresh(self):
        self.refreshed += 1


class _Recorder:
    def __init__(self):
        self.calls = 0

    def clear(self):
        self.calls += 1

    def setCurrentIndex(self, index):
        self.calls += 1


def _make_window(screen):
    """Un stub portant exactement ce que les méthodes touchent, avec les deux méthodes auxiliaires
    RÉELLES liées dessus : c'est la logique de gating de `_show_screen` qu'on exerce, pas une
    réimplémentation. Pas de widget Qt construit."""
    from window import MainWindow

    win = SimpleNamespace(
        project=object(),
        _project_loaded_screen_indices=set(),
        _screen_widgets=[screen],
        _screens=[SimpleNamespace(name="TestScreen", plugin=False)],
        _screen_stack=_Recorder(),
        _history=_Recorder(),
        _bus=_Recorder(),
    )
    win._ensure_screen = lambda index: screen
    win._load_screen_for_project = MainWindow._load_screen_for_project.__get__(win)
    win._refresh_screen_for_project = MainWindow._refresh_screen_for_project.__get__(win)
    return win


def test_refresh_appele_en_revisite_pas_a_la_premiere_visite():
    from window import MainWindow

    screen = _FakeScreen()
    win = _make_window(screen)

    MainWindow._show_screen(win, 0)             # première visite : load_project peuple, pas de refresh
    assert (screen.loaded, screen.refreshed) == (1, 0)

    MainWindow._show_screen(win, 0)             # revisite : load court-circuité, refresh appelé
    assert (screen.loaded, screen.refreshed) == (1, 1)

    MainWindow._show_screen(win, 0)
    assert (screen.loaded, screen.refreshed) == (1, 2)


def test_pas_de_refresh_sans_projet():
    from window import MainWindow

    screen = _FakeScreen()
    win = _make_window(screen)
    win.project = None

    MainWindow._show_screen(win, 0)
    MainWindow._show_screen(win, 0)
    assert (screen.loaded, screen.refreshed) == (0, 0)


# ── Ce que `refresh()` relit, écran par écran ─────────────────────────────


def _text_rows(screen):
    from ui.text_editor.text_table import _ROLE_TEXT
    table = screen._texts._table
    return [it for it in table._iter_rows() if it.data(0, _ROLE_TEXT) is not None]


def test_ecran_texte_voit_une_entree_nee_ailleurs(qapp, tmp_path):
    """Une zone de texte créée dans le Scene Manager ajoute son entrée à `project.texts` ; la table
    de l'écran Texte restait figée (« 1 of 8 shown » alors qu'une seule ligne était construite)."""
    from core.project import Project
    from ui.text_editor.text_editor_screen import TextEditorScreen

    p = Project(tmp_path)
    p.new_text(content="HUB", path=["Hub", "text"])

    screen = TextEditorScreen()
    screen.load_project(p)
    assert len(_text_rows(screen)) == 1

    p.new_text(content="", path=["Menu", "text"])
    p.new_text(content="", path=["Boss", "text"])
    screen.refresh()

    assert len(_text_rows(screen)) == 3


def test_ecran_scripts_voit_un_global_ne_ailleurs(qapp, tmp_path):
    """L'autocomplétion capture les catalogues du projet à la première visite : un global déclaré
    ensuite n'y entrait jamais, sans erreur."""
    from core.project import Project
    from core.models.settings import GlobalVar
    from ui.script_editor.script_editor import ScriptEditorScreen

    def names(screen):
        return (screen._editor._completer._project_names or {}).get("global", [])

    p = Project(tmp_path)
    screen = ScriptEditorScreen()
    screen.load_project(p)
    assert "score" not in names(screen)

    p.globals.append(GlobalVar(name="score"))
    screen.refresh()

    assert "score" in names(screen)


def _new_palette(name):
    from core.models.palette import PaletteBank
    return PaletteBank(name=name, colors=[0] * 16)


def test_ecran_fonds_relit_le_catalogue_de_palettes(qapp, tmp_path):
    """La grille « + du catalogue » lit `project.palettes` à la première visite ; une palette
    ajoutée ensuite dans l'écran Palettes n'y apparaissait jamais. Les tests appellent `refresh()`
    directement : un vrai `show()` réveille le canvas, qui ne survit pas au mode offscreen."""
    from core.project import Project
    from ui.background_editor.background_editor_screen import BackgroundEditorScreen

    p = Project(tmp_path)
    screen = BackgroundEditorScreen()
    screen.load_project(p)
    screen._props._project = p                 # ce que fait `_props.load(ba, project)` à la sélection
    screen._props.refresh_palette_catalog()
    assert screen._props._pal_grid._catalog == []

    p.palettes.append(_new_palette("hero_pal"))
    screen.refresh()

    assert [b.name for b in screen._props._pal_grid._catalog] == ["hero_pal"]


def test_ecran_animations_relit_le_catalogue_de_palettes(qapp, tmp_path):
    from core.project import Project
    from core.models.sprite import SpriteAsset
    from ui.sprite_editor.sprite_editor_screen import SpriteEditorScreen

    p = Project(tmp_path)
    screen = SpriteEditorScreen()
    screen.load_project(p)
    screen._right.load_sprite(SpriteAsset(name="hero"), p)   # le panneau ne tient son projet qu'après
    assert screen._right._pal_grid._catalog == []

    p.palettes.append(_new_palette("hero_pal"))
    screen.refresh()

    assert [b.name for b in screen._right._pal_grid._catalog] == ["hero_pal"]
