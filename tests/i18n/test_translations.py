"""Les fichiers de traduction — ce que ni le `make` ni l'écran ne diraient.

Chaque règle couverte ici décide du sort d'un travail HUMAIN. Elles se
trompent en silence : un projet s'ouvre, l'écran s'affiche, et la perte ne se
voit qu'au moment où quelqu'un rouvre sa traduction.

- une entrée non traduite doit rendre la SOURCE, jamais une chaîne vide — sur
  console, un texte de la mauvaise langue s'interprète, un écran blanc non ;
- le side se joint par `id` : renommer une clé ne casse rien ;
- `key` et `source` y sont des ANNOTATIONS — le maître les recale, ne les relit
  jamais ;
- une traduction dont l'entrée maître a disparu est CONSERVÉE ;
- un side vide et non déclaré est jetable, un side qui porte une traduction ne
  l'est jamais.

Cf. ROADMAP v0.9, temps 2, phase 1.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def projet(tmp_path):
    """Un projet neuf avec trois textes et une langue déclarée."""
    from core.project import Project
    from core.models.settings import Language

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    for key, content in (("intro", "PONG"), ("win", "YOU WIN"), ("lose", "")):
        t = p.new_text(content=content)
        t.key = key
    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="de", name="Deutsch")]
    p.load_translations()
    return p


def test_une_entree_non_traduite_rend_la_source(projet):
    intro, win = projet.texts[0], projet.texts[1]
    projet.translations["de"][intro.id] = "PONG!"

    assert projet.text_content(intro, "de") == "PONG!"
    # Non traduite : la source, et surtout pas "".
    assert projet.text_content(win, "de") == "YOU WIN"
    # Langue inconnue ou absente : la source aussi, sans condition.
    assert projet.text_content(intro, "xx") == "PONG"
    assert projet.text_content(intro, "") == "PONG"
    assert projet.text_content(intro, "en") == "PONG"


def test_le_side_se_joint_par_id_pas_par_cle(projet):
    intro = projet.texts[0]
    projet.translations["de"][intro.id] = "PONG!"
    projet.save_translation("de")

    # Renommer la clé ne doit RIEN casser : c'est ce pour quoi l'id existe.
    intro.key = "intro_renommee"
    projet.translations = {}
    projet.load_translations()
    assert projet.text_content(intro, "de") == "PONG!"


def test_key_et_source_sont_des_annotations_recalees(projet, tmp_path):
    intro = projet.texts[0]
    projet.translations["de"][intro.id] = "PONG!"
    projet.save_translation("de")

    d = json.loads(projet.translation_file("de").read_text(encoding="utf-8"))
    entry = d["texts"][0]
    assert (entry["key"], entry["source"]) == ("intro", "PONG")

    # Un side dont les annotations mentent : elles sont IGNORÉES à la lecture,
    # et réécrites depuis le maître à la sauvegarde suivante.
    entry["key"], entry["source"] = "mensonge", "faux"
    projet.translation_file("de").write_text(json.dumps(d), encoding="utf-8")
    projet.load_translations()
    assert projet.text_content(intro, "de") == "PONG!"
    projet.save_translation("de")
    again = json.loads(projet.translation_file("de").read_text(encoding="utf-8"))
    assert (again["texts"][0]["key"], again["texts"][0]["source"]) == ("intro", "PONG")


def test_une_traduction_vide_n_est_pas_ecrite(projet):
    projet.translations["de"][projet.texts[0].id] = ""
    projet.save_translation("de")
    d = json.loads(projet.translation_file("de").read_text(encoding="utf-8"))
    # « Traduit par rien » n'existe pas : c'est une entrée absente.
    assert d["texts"] == []
    assert len(projet.translation_gaps("de")) == len(projet.texts)


def test_une_traduction_orpheline_est_conservee(projet):
    """Supprimer une entrée du maître ne doit pas détruire sa traduction.

    Une suppression s'annule ; une traduction effacée du disque, non."""
    intro = projet.texts[0]
    projet.translations["de"][intro.id] = "PONG!"
    projet.save_translation("de")

    projet.delete_text(intro)
    projet.save_translation("de")
    d = json.loads(projet.translation_file("de").read_text(encoding="utf-8"))
    orphan = [e for e in d["texts"] if e["id"] == intro.id]
    assert orphan and orphan[0]["content"] == "PONG!"
    # Sans entrée maître, pas d'annotation possible — et c'est tout.
    assert "key" not in orphan[0]


def test_re_declarer_une_langue_relit_son_travail(projet):
    projet.translations["de"][projet.texts[0].id] = "PONG!"
    projet.save_translation("de")

    projet.forget_translations("de")
    assert "de" not in projet.translations
    projet.ensure_translation_file("de")
    # Le fichier n'a jamais quitté le disque : le re-déclarer le RELIT, il ne
    # le remet pas à vide (sans quoi la sauvegarde suivante l'écraserait).
    assert projet.translations["de"] == {projet.texts[0].id: "PONG!"}


def test_seul_un_side_vide_et_non_declare_est_jete(projet):
    projet.ensure_translation_file("de")
    projet.translations["ja"] = {projet.texts[0].id: "ポン"}
    projet.save_translation("ja")
    projet.translations["lang1"] = {}
    projet.save_translation("lang1")

    projet.prune_empty_translations({"de"})
    assert projet.translation_file("de").exists()        # déclaré
    assert projet.translation_file("ja").exists()        # porte du travail
    assert not projet.translation_file("lang1").exists()  # vide et non déclaré


def test_le_code_de_langue_nomme_un_fichier(projet):
    from core.models.settings import lang_code
    assert lang_code("pt-BR") == "pt_br"
    assert lang_code("  ES  ") == "es"
    assert lang_code("Français") == "francais"
    assert projet.translation_file("pt_br").name == "texts_pt_br.json"


def test_un_projet_sans_langue_declaree_ne_change_pas(tmp_path):
    from core.project import Project
    p = Project(tmp_path / "mono")
    assert p.settings.languages == []
    assert p.settings.all_languages() == []
    assert p.is_multilingual() is False
    t = p.new_text(content="PONG")
    # Le repli marche même sans la moindre déclaration : c'est ce qui permet
    # au reste de l'éditeur d'appeler `text_content` sans se demander si le
    # projet est traduit.
    assert p.text_content(t) == "PONG"
