"""Chaîne (`Text`) et boîte de texte (`Textbox`) : deux types, un seul emplacement runtime.

La chaîne se pose en un point (jamais coupée, jamais alignée) ; la boîte coupe et aligne dans
son rectangle. Ce fichier tient la séparation : le modèle, la relecture des anciens fichiers
(où tout `text` était une boîte), le drapeau `nowrap` émis dans `g_ui_regions`, et la
référence Lua commune.
"""

from __future__ import annotations

from core.models.ui_region import (
    KIND_TEXT, KIND_TEXTBOX, KINDS_ASSEMBLY, KINDS_BRICK, UIContainer, UIList, UIText,
    UITextbox, element_from_dict, is_text,
)


def test_les_briques_et_les_assemblages_se_partagent_les_types():
    from core.models.ui_region import KINDS
    assert set(KINDS_BRICK) | set(KINDS_ASSEMBLY) == set(KINDS)
    assert not set(KINDS_BRICK) & set(KINDS_ASSEMBLY)
    assert KIND_TEXT in KINDS_BRICK and KIND_TEXTBOX in KINDS_ASSEMBLY


def test_une_chaine_et_une_boite_sont_deux_types_qui_ecrivent_des_glyphes():
    assert (UIText().kind, UITextbox().kind) == (KIND_TEXT, KIND_TEXTBOX)
    assert not UIText().wraps and UITextbox().wraps
    assert is_text(UIText()) and is_text(UITextbox()) and not is_text(UIContainer())


def test_chaque_type_se_relit_tel_quil_est_ecrit():
    for el in (UIText(name="a"), UITextbox(name="b")):
        back = element_from_dict(el.to_dict())
        assert type(back) is type(el) and back.name == el.name


def test_un_ancien_text_etait_une_boite_et_le_reste():
    old = {"kind": "text", "name": "dialogue", "w": 200, "h": 32}   # pas de `point`
    el = element_from_dict(old)
    assert isinstance(el, UITextbox) and el.wraps
    assert el.to_dict()["kind"] == KIND_TEXTBOX      # le prochain enregistrement l'écrit
    assert isinstance(element_from_dict({"kind": "region", "name": "r"}), UITextbox)


def test_le_nowrap_est_emis_pour_la_chaine_seulement():
    from codegen.font_emit import emit_ui_regions_c
    from core.models.ui_region import UILayout
    lay = UILayout(name="hud")
    string, box = UIText(name="s"), UITextbox(name="b")
    lay.elements += [string, box]
    rows = [l for l in emit_ui_regions_c([(lay, string), (lay, box)], [])
            if l.lstrip().startswith("{")]
    assert rows[0].split("}")[0].rstrip().endswith(", 1")      # chaîne : nowrap
    assert rows[1].split("}")[0].rstrip().endswith(", 0")      # boîte : coupe


def test_une_liste_accepte_les_deux_pour_rangees():
    assert set(UIList.can_contain) == {KIND_TEXT, KIND_TEXTBOX}


def test_une_boite_se_cite_comme_une_chaine_dans_un_script():
    from types import SimpleNamespace
    from scripting.project_names import ui_ref_kinds
    lay = SimpleNamespace(name="hud")
    project = SimpleNamespace(all_elements=lambda: [
        (lay, UIText(name="titre")), (lay, UITextbox(name="boite"))])
    kinds = ui_ref_kinds(project)
    assert kinds["titre"] == kinds["boite"] == "textBox"


def test_seule_la_boite_se_redimensionne():
    assert not UIText().resizable and UITextbox().resizable
