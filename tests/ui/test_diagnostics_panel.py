"""DiagnosticsView (U3, volet B) — la liste du validateur, cliquable.

Sans enrichir `ValidationMessage` : un message qui cite `fichier.lua:ligne` route
vers le script, un message d'acteur route vers sa sélection, le reste s'affiche
sans cible.
"""
from __future__ import annotations

from core.validator import ValidationMessage, DiagnosticTarget
from ui.common.build_panel import DiagnosticsView, BuildPanel


def _view(qapp) -> DiagnosticsView:
    return DiagnosticsView()


def test_set_diagnostics_erreurs_dabord(qapp):
    d = _view(qapp)
    warns = [ValidationMessage("warning", "Hero", "sprite manquant")]
    errs = [ValidationMessage("error", "", "Titre.lua:2 : syntax error")]
    d.set_diagnostics(warns, errs)
    assert d._list.count() == 2
    assert d._msgs[0].level == "error"          # ce qui bloque le build en tête
    assert "1 warning(s)" in d._summary.text() and "1 error(s)" in d._summary.text()


def test_liste_vide(qapp):
    d = _view(qapp)
    d.set_diagnostics([], [])
    assert d._list.count() == 0
    assert d._summary.text() == "No problems"


def test_routage_script_acteur_et_global(qapp):
    d = _view(qapp)
    d.set_diagnostics(
        warnings=[ValidationMessage("warning", "Hero", "sprite manquant"),
                  ValidationMessage("warning", "", "font X ne couvre pas « é »")],
        errors=[ValidationMessage("error", "", "Titre.lua:2 : syntax error")],
    )
    loc, act = [], []
    d.location_activated.connect(lambda f, l: loc.append((f, l)))
    d.actor_activated.connect(lambda scene, n: act.append((scene, n)))

    d._on_row(d._list.item(0))   # erreur script → fichier:ligne
    d._on_row(d._list.item(1))   # warning acteur → nom
    d._on_row(d._list.item(2))   # warning global → aucune cible

    assert loc == [("Titre.lua", 2)]
    assert act == [("", "Hero")]


def test_routage_cible_ui_element_prioritaire(qapp):
    """Une cible structurée `ui_element` route vers l'élément — avant même
    l'heuristique (le message pourrait aussi citer un acteur/un fichier)."""
    d = _view(qapp)
    d.set_diagnostics(
        warnings=[ValidationMessage("warning", "", "le fond du conteneur ne sera pas émis",
                                    DiagnosticTarget("ui_element", "Cursor", "HUD"))],
        errors=[],
    )
    el = []
    d.element_activated.connect(lambda lay, n: el.append((lay, n)))
    d._on_row(d._list.item(0))
    assert el == [("HUD", "Cursor")]


def test_build_panel_a_les_deux_onglets(qapp):
    bp = BuildPanel()
    assert hasattr(bp, "console") and hasattr(bp, "diagnostics")


# ── Les diagnostics d'un build (tranche 2 de « La fiabilité du journal de build ») ──


def test_un_diagnostic_de_build_va_dans_la_console_et_l_onglet(qapp):
    from core.validator import build_error, build_warning
    bp = BuildPanel()
    bp.start_build_diagnostics()
    bp.log_diagnostic(build_warning("unused", "codegen", "Hit.lua"))
    bp.log_diagnostic(build_error("unexpected `x`", "script", "Hit.lua", 3))
    assert "[error] Hit.lua:3: unexpected `x`" in bp.console.toPlainText()

    bp.show_build_diagnostics()
    assert bp.diagnostics._list.count() == 2
    assert bp.diagnostics._msgs[0].level == "error"       # erreurs d'abord


def test_le_clic_lit_le_fichier_et_la_ligne_du_diagnostic(qapp):
    """Les champs, pas une regex sur le texte : un message sans « Hit.lua:3 » dedans route
    quand même vers la bonne ligne."""
    from core.validator import build_error
    view = DiagnosticsView()
    view.set_diagnostics([], [build_error("unexpected token", "script", "Hit.lua", 3)])
    got = []
    view.location_activated.connect(lambda f, l: got.append((f, l)))
    view._on_row(view._list.item(0))
    assert got == [("Hit.lua", 3)]


def test_un_nouveau_build_repart_d_une_liste_vide(qapp):
    from core.validator import build_error
    bp = BuildPanel()
    bp.start_build_diagnostics()
    bp.log_diagnostic(build_error("old", "make"))
    bp.start_build_diagnostics()
    bp.show_build_diagnostics()
    assert bp.diagnostics._list.count() == 0


# ── Un diagnostic d'une autre scène ouvre cette scène ─────────────


def test_le_clic_porte_la_scene_du_diagnostic(qapp):
    view = DiagnosticsView()
    view.set_diagnostics([], [ValidationMessage("error", "Hero", "script missing", scene="Level2"),
                              ValidationMessage("warning", "", "does nothing", scene="Level3")])
    got = []
    view.actor_activated.connect(lambda scene, actor: got.append((scene, actor)))
    view._on_row(view._list.item(0))
    view._on_row(view._list.item(1))
    assert got == [("Level2", "Hero"), ("Level3", "")]       # une scène seule se clique aussi


def _window_stub(scenes, active):
    """Le seul morceau de MainWindow que le clic utilise, sans construire l'interface."""
    from types import SimpleNamespace
    state = SimpleNamespace(active=active, opened=[], selected=[], status=[])
    project = SimpleNamespace(scenes=scenes, active_scene=active)

    def on_scene_selected(index, refresh_diagnostics=True):
        project.active_scene = scenes[index]
        state.opened.append((index, refresh_diagnostics))

    stub = SimpleNamespace(
        project=project, _on_scene_selected=on_scene_selected,
        _bus=SimpleNamespace(select=state.selected.append),
        _status=SimpleNamespace(showMessage=lambda text, *_: state.status.append(text)))
    return stub, state


def test_cliquer_un_acteur_d_une_autre_scene_bascule_puis_le_selectionne():
    from types import SimpleNamespace
    from window import MainWindow
    hero = SimpleNamespace(name="Hero")
    scenes = [SimpleNamespace(name="Level1", actors=[]),
              SimpleNamespace(name="Level2", actors=[hero])]
    stub, state = _window_stub(scenes, scenes[0])

    MainWindow._select_actor_by_name(stub, "Level2", "Hero")

    # La scène change SANS relancer la validation : la liste du build reste affichée.
    assert state.opened == [(1, False)]
    assert state.selected == [hero]


def test_cliquer_dans_la_scene_active_ne_bascule_pas():
    from types import SimpleNamespace
    from window import MainWindow
    hero = SimpleNamespace(name="Hero")
    scenes = [SimpleNamespace(name="Level1", actors=[hero])]
    stub, state = _window_stub(scenes, scenes[0])

    MainWindow._select_actor_by_name(stub, "Level1", "Hero")
    MainWindow._select_actor_by_name(stub, "", "Hero")        # sans scène : l'active

    assert state.opened == []
    assert state.selected == [hero, hero]


def test_cliquer_une_scene_sans_acteur_ouvre_seulement_la_scene():
    from types import SimpleNamespace
    from window import MainWindow
    scenes = [SimpleNamespace(name="Level1", actors=[]), SimpleNamespace(name="Level2", actors=[])]
    stub, state = _window_stub(scenes, scenes[0])

    MainWindow._select_actor_by_name(stub, "Level2", "")

    assert state.opened == [(1, False)]
    assert state.selected == [] and state.status == []
