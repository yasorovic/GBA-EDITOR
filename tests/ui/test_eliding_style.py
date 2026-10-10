"""ElidingStyle : un texte d'une ligne qui déborde est élidé, un texte multiligne non."""
from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QComboBox, QLabel

from ui.common.eliding_style import ElidingStyle


def _elide(text: str, width: int, flags: int = 0) -> str:
    image = QImage(200, 30, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        return ElidingStyle.elided(painter, QRect(0, 0, width, 20), flags, text)
    finally:
        painter.end()


def test_overflowing_text_gets_ellipsis(qapp):
    assert _elide("From project (Cut (no transition))", 60).endswith("…")


def test_fitting_text_untouched(qapp):
    assert _elide("OK", 150) == "OK"


def test_icon_glyph_never_elided(qapp):
    assert _elide("📁", 1) == "📁"


def test_wrapped_or_multiline_text_untouched(qapp):
    long = "a long sentence that wraps"
    assert _elide(long, 40, Qt.TextFlag.TextWordWrap.value) == long
    assert _elide("a\nb", 1) == "a\nb"


def test_widgets_render_with_the_style(qapp):
    style = ElidingStyle()
    for widget in (QComboBox(), QLabel("some text")):
        widget.setStyle(style)
        widget.resize(40, 28)
        widget.render(QImage(40, 28, QImage.Format.Format_ARGB32))


def _width(text: str) -> int:
    image = QImage(200, 30, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        return painter.fontMetrics().horizontalAdvance(text)
    finally:
        painter.end()


def test_the_ampersand_of_a_mnemonic_takes_no_room(qapp):
    """`&Yes` d'une boîte de dialogue : le « & » n'est pas dessiné. Mesuré avec lui, « Yes » devenait « … » dès que le
    bouton n'avait pas la place d'un caractère de plus (les boutons « ... » d'une fenêtre de confirmation)."""
    fits = _width("Yes") + 1
    assert _elide("&Yes", fits, Qt.TextFlag.TextShowMnemonic.value) == "&Yes"
    assert _elide("&No", _width("No") + 1, Qt.TextFlag.TextShowMnemonic.value) == "&No"


def test_a_mnemonic_text_that_really_overflows_is_still_elided(qapp):
    assert _elide("&Yes, delete everything", _width("Yes") + 1, Qt.TextFlag.TextShowMnemonic.value).endswith("…")


def test_an_ampersand_without_the_mnemonic_flag_is_a_character_like_any_other(qapp):
    assert _elide("&Yes", _width("Yes") + 1, 0).endswith("…")                       # sans le drapeau, « & » est dessiné


def test_a_confirmation_box_keeps_its_button_labels(qapp):
    from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
    from ui.common.theme import GLOBAL_QSS
    old_style, old_sheet = QApplication.style().objectName(), qapp.styleSheet()
    qapp.setStyle(ElidingStyle())
    qapp.setStyleSheet(GLOBAL_QSS)
    try:
        box = QMessageBox(QMessageBox.Icon.Question, "Delete", "Delete?",
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        shown = []
        original = ElidingStyle.elided
        ElidingStyle.elided = staticmethod(lambda p, r, f, text: shown.append((text, original(p, r, f, text))) or original(p, r, f, text))
        try:
            box.show()
            qapp.processEvents()
            box.grab()
        finally:
            ElidingStyle.elided = staticmethod(original)
        labels = [(text, out) for text, out in shown if text in ("&Yes", "&No")]
        assert labels and all(text == out for text, out in labels)                  # aucun bouton n'est devenu « … »
        assert [b.text() for b in box.findChildren(QPushButton)] == ["&Yes", "&No"]
    finally:
        qapp.setStyle(old_style)
        qapp.setStyleSheet(old_sheet)
