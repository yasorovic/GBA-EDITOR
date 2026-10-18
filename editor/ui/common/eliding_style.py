"""
ui/common/eliding_style.py — un texte trop long finit par « … », jamais coupé net.

Qt coupe sèchement le libellé d'un combo, d'un bouton, d'une case à cocher ou
d'un QLabel quand la place manque ; seules les vues (arbres, listes) ajoutent
« … ». Tous ces widgets passent par `QStyle.drawItemText` : le surcharger une
seule fois, au niveau du style de l'application, généralise le comportement à
tout l'éditeur sans toucher à aucun écran.

Un texte sur plusieurs lignes (retour à la ligne explicite ou `wordWrap`) n'est
pas tronqué : il a déjà un moyen de tenir.
"""
from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QProxyStyle, QStyle


MIN_ELIDED_LENGTH = 2

_MNEMONIC = re.compile(r"&(&?)")      # « &Yes » → « Yes », « && » → « & »


class ElidingStyle(QProxyStyle):
    """Fusion, dont tout texte d'une ligne est élidé à droite quand il déborde."""

    def __init__(self):
        super().__init__("Fusion")

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        from ui.common.tooltip import TOOLTIP_WAKEUP_MS
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return TOOLTIP_WAKEUP_MS
        if hint == QStyle.StyleHint.SH_ToolTip_FallAsleepDelay:
            return 0  # Same hover delay after closing or switching to another control.
        return super().styleHint(hint, option, widget, returnData)

    def standardIcon(self, standardIcon, option=None, widget=None):
        filename = {
            QStyle.StandardPixmap.SP_MessageBoxInformation: "BUILD-STUDY.svg",
            QStyle.StandardPixmap.SP_MessageBoxWarning: "Warning_icon.svg",
            QStyle.StandardPixmap.SP_MessageBoxQuestion: "QuestionMark_icon.svg",
            QStyle.StandardPixmap.SP_MessageBoxCritical: "BUILD-FAILED.svg",
        }.get(standardIcon)
        if filename:
            icon = QIcon(str(Path(__file__).parent / "CustomIcons" / filename))
            if not icon.isNull():
                return icon
        return super().standardIcon(standardIcon, option, widget)

    def standardPixmap(self, standardPixmap, option=None, widget=None):
        if standardPixmap in (QStyle.StandardPixmap.SP_MessageBoxInformation,
                              QStyle.StandardPixmap.SP_MessageBoxWarning,
                              QStyle.StandardPixmap.SP_MessageBoxQuestion,
                              QStyle.StandardPixmap.SP_MessageBoxCritical):
            size = self.pixelMetric(QStyle.PixelMetric.PM_MessageBoxIconSize, option, widget)
            return self.standardIcon(standardPixmap, option, widget).pixmap(size, size)
        return super().standardPixmap(standardPixmap, option, widget)

    @staticmethod
    def elided(painter, rect, flags, text: str) -> str:
        """`text` tel quel, ou tronqué avec « … » s'il déborde de `rect`."""
        multiline = bool(flags & Qt.TextFlag.TextWordWrap.value) or "\n" in text
        # Un glyphe d'icône (« 📁 », « ⚙ ») : « … » n'en dirait pas plus que lui.
        if multiline or len(text) <= MIN_ELIDED_LENGTH:
            return text
        # Le « & » d'un raccourci (« &Yes » dans une boîte de dialogue) n'est pas dessiné : on mesure ce qui l'est.
        # Mesuré avec lui, « Yes » devenait « … » dès que le bouton n'avait pas la place d'un caractère de plus.
        drawn = _MNEMONIC.sub(r"\1", text) if flags & Qt.TextFlag.TextShowMnemonic.value else text
        if painter.fontMetrics().horizontalAdvance(drawn) <= rect.width():
            return text
        return painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, rect.width())

    def drawItemText(self, painter, rect, flags, palette, enabled, text, textRole=None):
        text = self.elided(painter, rect, flags, text)
        if textRole is None:
            super().drawItemText(painter, rect, flags, palette, enabled, text)
        else:
            super().drawItemText(painter, rect, flags, palette, enabled, text, textRole)
