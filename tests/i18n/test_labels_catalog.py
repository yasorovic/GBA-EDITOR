"""Le cœur partagé des catalogues d'interface (ui/common/catalog.py) et le
catalogue de libellés (ui/common/labels.py), ROADMAP v0.11.

Garde ce que le refactor des notices ne devait PAS changer (repli sur la source,
pluriel, format, une clé absente = la clé), et ce que le catalogue frère ajoute
(un `set_language` qui bascule TOUS les catalogues d'un coup).
"""
from __future__ import annotations

import json

import pytest

from ui.common import catalog
from ui.common.catalog import Catalog
from ui.common.labels import label


def _write(directory, name: str, code: str, entries: dict) -> None:
    fn = f"{name}.json" if not code else f"{name}_{code}.json"
    (directory / fn).write_text(
        json.dumps({name: entries}, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def demo(tmp_path):
    """Un catalogue jetable : maître + side `fr` incomplet (n_items non traduit)."""
    _write(tmp_path, "demo", "", {
        "hi": {"text": "Hello"},
        "n_items": {"singular": "{n} item", "plural": "{n} items"},
        "greet": {"text": "Hi {who}"},
    })
    _write(tmp_path, "demo", "fr", {
        "hi": {"text": "Bonjour"},
        "greet": {"text": "Salut {who}"},
    })
    cat = Catalog("demo", tmp_path)
    yield cat
    catalog.set_language("")     # ne pas polluer les autres tests


def test_source_when_no_language(demo):
    catalog.set_language("")
    assert demo.text("hi") == "Hello"


def test_missing_key_returns_key(demo):
    assert demo.text("nope") == "nope"


def test_side_translation(demo):
    catalog.set_language("fr")
    assert demo.text("hi") == "Bonjour"


def test_absent_side_entry_falls_back_to_source(demo):
    catalog.set_language("fr")               # n_items absent du side
    assert demo.text("n_items", n=3) == "3 items"


def test_plural_source(demo):
    catalog.set_language("")
    assert demo.text("n_items", n=1) == "1 item"
    assert demo.text("n_items", n=7) == "7 items"


def test_format_values(demo):
    catalog.set_language("fr")
    assert demo.text("greet", who="Ada") == "Salut Ada"


def test_set_language_is_global(demo):
    """`catalog.set_language` bascule TOUS les catalogues enregistrés, pas
    seulement `demo` : c'est ce qui fait qu'un changement de langue touche
    notices ET libellés d'un seul appel."""
    catalog.set_language("fr")
    assert demo.text("hi") == "Bonjour"
    assert label("common.close") == "Fermer"
    catalog.set_language("")


def test_delivered_french_labels_and_fallback():
    """Le premier side livré traduit ses clés et laisse le reste en source."""
    catalog.set_language("fr")
    assert label("common.close") == "Fermer"
    # Ce libellé n'est pas encore dans labels_fr.json : le repli reste anglais.
    assert label("actorinsp.active") == "Active on start"
    catalog.set_language("")


def test_french_settings_catalogue_is_complete():
    """Le premier écran livré dans une langue ne mélange pas ses libellés."""
    from ui.common.labels import LABELS_DIR
    master = json.loads(
        (LABELS_DIR / "labels.json").read_text(encoding="utf-8"))["labels"]
    french = json.loads(
        (LABELS_DIR / "labels_fr.json").read_text(encoding="utf-8"))["labels"]
    settings_keys = {key for key in master if key.startswith("settings.")}
    assert settings_keys <= set(french)


def test_french_home_catalogue_is_complete():
    """L'accueil est le second écran livré sans mélange de langues."""
    from ui.common.labels import LABELS_DIR
    master = json.loads(
        (LABELS_DIR / "labels.json").read_text(encoding="utf-8"))["labels"]
    french = json.loads(
        (LABELS_DIR / "labels_fr.json").read_text(encoding="utf-8"))["labels"]
    home_keys = {key for key in master if key.startswith("home.")}
    assert home_keys <= set(french)


def test_available_languages_lists_delivered_sides():
    codes = dict(catalog.available_languages())
    assert codes[""] == "English (source)"
    assert codes["fr"] == "Français"


def test_labels_seed_reads_settings_keys():
    catalog.set_language("")
    assert label("common.close") == "Close"
    assert label("settings.shortcuts.reset_to", default="Ctrl+Z") == "Reset to Ctrl+Z"
    assert label("settings.__absent__") == "settings.__absent__"


def test_notices_not_regressed():
    """Le refactor de notice.py vers le cœur partagé n'a pas cassé la
    résolution : la PREMIÈRE clé réelle du catalogue de notices rend toujours un
    texte, ni vide ni la clé brute."""
    from ui.common import notice
    from ui.common.notice import NOTICES_DIR
    catalog.set_language("")
    master = json.loads(
        (NOTICES_DIR / "notices.json").read_text(encoding="utf-8"))["notices"]
    key = next(iter(master))
    assert notice.text(key) not in ("", key)
