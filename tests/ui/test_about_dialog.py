"""La fenêtre « À propos » : nom, version, auteur et licences.

Ces tests vivent ici et non dans `tests/test_app_info.py` : ils instancient des widgets, donc
utilisent la fixture `qapp` de la session. En créant leur propre `QApplication` puis en le
lâchant, ils le détruisaient, et les tests UI suivants trouvaient un `CommandHistory` supprimé.
"""
from __future__ import annotations

from core.app_info import APP_AUTHOR, APP_VERSION


def test_la_fenetre_a_propos_donne_nom_version_et_auteur(qapp):
    from PyQt6.QtWidgets import QLabel
    from ui.common.about_dialog import AboutDialog

    dialog = AboutDialog()
    text = "\n".join(lbl.text() for lbl in dialog.findChildren(QLabel))

    assert APP_VERSION in text and APP_AUTHOR in text


def test_la_fenetre_a_propos_ouvre_licences_et_notices_tierces(qapp):
    from PyQt6.QtWidgets import QTabWidget, QTextBrowser
    from ui.common.about_dialog import LicensesDialog

    dialog = LicensesDialog()
    tabs = dialog.findChild(QTabWidget)

    assert tabs.count() == 3          # éditeur, moteur, notices tierces
    notices = tabs.widget(2)
    assert isinstance(notices, QTextBrowser)
    assert "PyQt6" in notices.toPlainText()
