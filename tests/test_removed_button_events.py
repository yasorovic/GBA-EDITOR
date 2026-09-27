"""La tranche finale du chantier « Les inputs personnalisés » (2026-09-27) :
les dix events `on_button_*` sont retirés — un script qui en définit encore un
est refusé au build avec un message de migration vers `input:pressed(nom)` —
et `SoundFxComponent.trigger` vise désormais un NOM (bouton ou action
déclarée), migré depuis l'ancien `on_button_*` à la lecture du projet.
"""
from __future__ import annotations

import pytest


def _errors(src: str):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    return [e.message for e in check(parse(src), BuildContext(actor_name="Ball"))
            if e.level == "error"]


@pytest.mark.parametrize("name, btn", [
    ("on_button_a", "a"), ("on_button_up", "up"), ("on_button_select", "select"),
])
def test_on_button_refuse_avec_message_de_migration(name, btn):
    errs = _errors(f"function {name}()\nend\n")
    assert errs, f"{name}() devrait être refusé"
    assert f'input:pressed("{btn}")' in errs[0], errs


def test_on_update_avec_pressed_reste_valide():
    errs = _errors('function on_update()\n  if input:pressed("a") then end\nend\n')
    assert errs == []


def test_soundfx_component_migre_le_trigger_a_la_lecture():
    from core.models.components import components_from_list
    comps = components_from_list([
        {"component_type": "sound_fx", "sfx_name": "Boop", "trigger": "on_button_a"},
    ])
    assert comps[0].trigger == "a"


def test_soundfx_component_conserve_manual_et_on_spawn():
    from core.models.components import components_from_list
    comps = components_from_list([
        {"component_type": "sound_fx", "sfx_name": "Boop", "trigger": "on_spawn"},
    ])
    assert comps[0].trigger == "on_spawn"


def test_sfx_auto_triggers_ne_contient_plus_les_boutons():
    from core.models.components import SFX_AUTO_TRIGGERS
    assert SFX_AUTO_TRIGGERS == ("on_spawn", "on_destroy")


def test_removed_events_couvre_les_dix_noms():
    from scripting.api import REMOVED_EVENTS, KNOWN_EVENTS
    assert len(REMOVED_EVENTS) == 10
    assert not (set(REMOVED_EVENTS) & set(KNOWN_EVENTS)), \
        "un event retiré ne doit plus être un event connu"
