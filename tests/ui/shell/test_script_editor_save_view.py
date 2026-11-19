"""Enregistrer ne recadre pas la vue.

La surveillance du fichier ne distingue pas l'écriture d'un tiers de celle de
l'éditeur : chaque Ctrl+S réveillait donc la relecture, qui remplace le
document et ramène la vue sur le curseur. Ce que ces tests tiennent : notre
propre écriture ne recharge rien, et un vrai changement extérieur recharge en
gardant le défilement.
"""
from __future__ import annotations


def _ecran(qapp, tmp_path, lignes: int = 200):
    from ui.script_editor.script_editor import ScriptEditorScreen
    chemin = tmp_path / "Hero.lua"
    chemin.write_text("\n".join(f"local x{n} = {n}" for n in range(lignes)),
                      encoding="utf-8")
    ecran = ScriptEditorScreen()
    ecran.resize(900, 400)
    ecran.show()
    ecran.open_script(chemin)
    qapp.processEvents()
    return ecran, chemin


def test_enregistrer_ne_recharge_pas_et_ne_defile_pas(qapp, tmp_path):
    ecran, chemin = _ecran(qapp, tmp_path)
    editeur = ecran._editor
    editeur.verticalScrollBar().setValue(editeur.verticalScrollBar().maximum())
    position = editeur.verticalScrollBar().value()

    ecran._editor.insertPlainText("")      # rien à écrire de neuf
    ecran._save()
    ecran._reload_from_disk()              # ce que la surveillance déclenche
    qapp.processEvents()

    assert editeur.verticalScrollBar().value() == position
    assert ecran._title_lbl.text() == chemin.name


def test_un_vrai_changement_exterieur_recharge_en_gardant_le_defilement(qapp, tmp_path):
    ecran, chemin = _ecran(qapp, tmp_path)
    editeur = ecran._editor
    editeur.verticalScrollBar().setValue(40)

    chemin.write_text("\n".join(f"local y{n} = {n}" for n in range(200)),
                      encoding="utf-8")
    ecran._reload_from_disk()
    qapp.processEvents()

    assert editeur.toPlainText().startswith("local y0")
    assert editeur.verticalScrollBar().value() == 40
