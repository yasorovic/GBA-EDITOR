"""Le champ de couleur commun : couleur web 24 bits ou couleur de la console (BGR555)."""
from PyQt6.QtCore import QPointF

from core.models.gba_color import bgr555_to_rgb888
from ui.common.color_field import ColorField


def _type(field, text):
    """Saisie dans le champ hexa du sélecteur, puis Entrée."""
    field._open()
    field._popup._hex.setText(text)
    field._popup._hex.editingFinished.emit()


def test_mode_gba_affiche_le_bgr555_et_quantifie(qapp):
    field = ColorField(gba=True)
    commits = []
    field.committed.connect(commits.append)
    field.set_value(0x4210)
    assert field._bgr555.text() == "0x4210" and commits == []

    _type(field, "#ff0001")
    assert commits == [0x001F]             # rouge plein, le bleu 1/255 disparaît
    assert field._bgr555.text() == "0x001F"
    assert field._popup._hex.text() == "#f80000"   # la conversion du projet : 31 << 3

    square = field._popup._square
    square._pick(QPointF(square.width() / 3, square.height() / 3))
    square.released.emit()
    value = commits[-1]
    assert isinstance(value, int) and 0 <= value <= 0x7FFF
    # La pastille montre la couleur quantifiée, celle que la console affichera.
    r, g, b = bgr555_to_rgb888(value)
    assert f"#{r:02x}{g:02x}{b:02x}" in field._swatch.styleSheet()
    field._popup.close()


def test_mode_web_garde_les_24_bits_sans_valeur_a_cote(qapp):
    field = ColorField()
    commits = []
    field.committed.connect(commits.append)
    assert field._bgr555 is None
    _type(field, "#FF0001")
    assert commits == ["#ff0001"]
    _type(field, "rouge")                  # invalide : revient à la couleur retenue
    assert commits == ["#ff0001"] and field._popup._hex.text() == "#ff0001"
    field._popup.close()


def test_le_selecteur_suit_le_glisse(qapp):
    field = ColorField()
    field.set_value("#aa50b4")
    field._open()
    popup = field._popup
    assert popup._hex.text() == "#aa50b4"
    square = popup._square
    square._pick(QPointF(0, square.height()))       # noir, aperçu
    assert popup._hex.text() == "#000000"
    popup.close()
