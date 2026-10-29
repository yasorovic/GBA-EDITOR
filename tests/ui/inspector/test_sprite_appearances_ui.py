"""Marche 3b : l'inspecteur applique la règle « activer une apparence désactive
l'autre » — en UNE entrée d'historique — et n'active jamais une apparence ajoutée."""
import pytest

from core.history import get_history
from core.models.components import SpriteComponent, displayed_sprite_component
from core.models.scene import Actor
from core.models.sprite import SpriteAsset
from core.project import Project
from ui.scene_manager.inspectors.actor_inspector import ActorInspector


@pytest.fixture
def history():
    h = get_history()
    h.clear()
    yield h
    h.clear()


def _acteur():
    a = Actor(name="Hero")
    a.components.append(SpriteComponent(id="normal", sprite_name="A", active=True))
    a.components.append(SpriteComponent(id="blesse", sprite_name="B", active=False))
    return a


def _charge(actor, tmp_path):
    """L'éditeur d'un composant sprite lit le projet : sans lui, PyQt6 abandonne le
    processus sur l'exception d'un slot (pas de traceback, code 127)."""
    projet = Project(tmp_path)
    for nom in ("A", "B"):
        projet.sprites.append(SpriteAsset(name=nom, asset=f"{nom}.png"))
    insp = ActorInspector()
    insp.load(actor, project=projet, scene=None)
    return insp


def test_activer_une_apparence_desactive_la_precedente(qapp, history, tmp_path):
    a = _acteur()
    normal, blesse = a.components
    _charge(a, tmp_path)._set_comp(blesse, "active", True)
    assert (normal.active, blesse.active) == (False, True)
    assert displayed_sprite_component(a) is blesse


def test_un_seul_annuler_rend_les_deux_etats(qapp, history, tmp_path):
    a = _acteur()
    normal, blesse = a.components
    _charge(a, tmp_path)._set_comp(blesse, "active", True)
    history.undo()
    assert (normal.active, blesse.active) == (True, False)
    history.redo()
    assert (normal.active, blesse.active) == (False, True)


def test_desactiver_une_apparence_ne_touche_pas_les_autres(qapp, history, tmp_path):
    a = _acteur()
    normal, blesse = a.components
    _charge(a, tmp_path)._set_comp(normal, "active", False)
    assert (normal.active, blesse.active) == (False, False)
    assert displayed_sprite_component(a) is None


def test_une_apparence_ajoutee_naît_inactive(qapp, history, tmp_path):
    a = _acteur()
    insp = _charge(a, tmp_path)
    insp._add_component("sprite")
    assert len(a.components) == 3 and a.components[2].active is False
    assert displayed_sprite_component(a) is a.components[0]      # rien n'a changé à l'écran


def test_la_premiere_apparence_ajoutee_est_active(qapp, history, tmp_path):
    a = Actor(name="Hero")
    _charge(a, tmp_path)._add_component("sprite")
    assert a.components[0].active is True


def _avec_script(tmp_path):
    from core.models.components import ScriptComponent
    a = _acteur()
    a.components[1].id = "blesse"
    (tmp_path / "assets" / "scripts" / "actors").mkdir(parents=True)
    rel = "assets/scripts/actors/hero.lua"
    (tmp_path / rel).write_text('function on_update(self)\n  self:activate_sprite("blesse")\nend\n',
                                encoding="utf-8")
    a.components.append(ScriptComponent(script=rel))
    return a, tmp_path / rel


def test_renommer_un_id_reecrit_le_script_et_s_annule_avec(qapp, history, tmp_path):
    a, script = _avec_script(tmp_path)
    blesse = a.components[1]
    insp = _charge(a, tmp_path)
    insp._set_comp(blesse, "id", "touche")
    assert blesse.id == "touche" and 'activate_sprite("touche")' in script.read_text(encoding="utf-8")
    history.undo()
    assert blesse.id == "blesse" and 'activate_sprite("blesse")' in script.read_text(encoding="utf-8")
    # L'annulation reconstruit l'éditeur du composant : sans ce nettoyage, le widget
    # survit jusqu'à la fermeture de l'interpréteur et Qt plante en le détruisant
    # (tous les tests passent, le processus sort en 139).
    insp.deleteLater()
    qapp.processEvents()


def test_un_id_deja_pris_ou_vide_est_refuse(qapp, history, tmp_path):
    a, script = _avec_script(tmp_path)
    blesse = a.components[1]
    insp = _charge(a, tmp_path)
    insp._set_comp(blesse, "id", "normal")          # déjà pris par l'autre apparence
    insp._set_comp(blesse, "id", "  ")
    assert blesse.id == "blesse" and not history.can_undo
