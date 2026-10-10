"""elide_name — couper un nom de fichier trop long sans perdre son extension.

La règle : le nom passe à la ligne tant que la place le permet — de préférence avant
l'extension, sinon à une espace, jamais en laissant une lettre seule ; s'il est ENCORE trop
long, on garde son extension et on coupe le début :

    monnomquiestbeaucouptroplong.extension  →  monnomq... .extension

Sur une ligne (l'arbre vertical) l'espace avant l'extension évite quatre points d'affilée
(`....extension`) ; sur deux lignes (la vue à plat) c'est un saut de ligne : l'extension
se retrouve seule sur la seconde.

Le retour à la ligne est fait ICI, par un saut de ligne explicite, et non laissé à Qt : en
mode icônes Qt ne coupe qu'aux espaces, donc un nom sans espace n'est jamais replié — il est
abrégé par un « … » qui mange l'extension.

Une seule règle pour la vue à plat et l'arbre vertical de l'onglet Disk : `ElidedNameDelegate`
l'applique à l'affichage, le texte de l'item reste le nom entier.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem


def _longest_prefix(text: str, metrics: QFontMetrics, width: int, tail: str = "") -> int:
    """Le plus grand `k` tel que `text[:k] + tail` tienne en `width` pixels (0 si aucun)."""
    low, high, best = 1, len(text), 0
    while low <= high:
        middle = (low + high) // 2
        if metrics.horizontalAdvance(text[:middle] + tail) <= width:
            best, low = middle, middle + 1
        else:
            high = middle - 1
    return best


def _one_line(name: str, metrics: QFontMetrics, width: int) -> str:
    if metrics.horizontalAdvance(name) <= width:
        return name
    stem, dot, extension = name.rpartition(".")
    if dot and stem and extension:
        tail = f"... .{extension}"
        kept = _longest_prefix(stem, metrics, width, tail)
        if kept:
            return stem[:kept] + tail
    else:
        kept = _longest_prefix(name, metrics, width, "...")
        if kept:
            return name[:kept] + "..."
    # Même l'extension seule ne tient pas : une coupe au milieu, faute de mieux.
    return metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, width)


# Une seconde ligne plus courte que ça ressemble à un accident (`.jso` / `n`) : on recule la coupe.
_MIN_SECOND_LINE = 4


def _two_lines(name: str, metrics: QFontMetrics, width: int) -> str:
    """Passe à la ligne, dans cet ordre de préférence — la première qui convient gagne :
    1. juste avant l'extension : le nom d'un côté, `.ext` seule de l'autre ;
    2. à une espace, la dernière qui laisse tenir les deux lignes (jamais au milieu d'un mot) ;
    3. en pleine lettre, sans laisser une ou deux lettres seules sur la seconde ligne ;
    4. sinon le nom est coupé (début conservé, extension gardée), cf. `elide_name`."""
    def fits(text: str) -> bool:
        return metrics.horizontalAdvance(text) <= width

    if fits(name):
        return name
    stem, dot, extension = name.rpartition(".")
    has_extension = bool(dot and stem and extension)
    if has_extension and fits(stem) and fits(f".{extension}"):
        return f"{stem}\n.{extension}"
    best = None
    for position, character in enumerate(name):
        if character == " " and name[:position] and fits(name[:position]) and fits(name[position + 1:]):
            best = (name[:position], name[position + 1:])
    if best:
        return "\n".join(best)
    first = _longest_prefix(name, metrics, width)
    if first == 0:
        return metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, width)
    if len(name) - first < _MIN_SECOND_LINE:
        first = max(1, len(name) - _MIN_SECOND_LINE)
    rest = name[first:]
    if fits(rest):
        return f"{name[:first]}\n{rest}"
    # Encore trop long : le début est coupé, l'extension passe seule sur la seconde ligne.
    if has_extension and fits(f".{extension}"):
        kept = _longest_prefix(stem, metrics, width, "...")
        if kept:
            return f"{stem[:kept]}...\n.{extension}"
    # Sans extension (ou une extension trop large) : la fin de la seconde ligne est coupée.
    kept = _longest_prefix(rest, metrics, width, "...")
    return f"{name[:first]}\n{rest[:kept]}..." if kept else name[:first]


def elide_name(name: str, metrics: QFontMetrics, width: int, lines: int = 1) -> str:
    """`name` s'il tient en `width` pixels, sinon sa forme repliée ou coupée. `lines` : 1 ou 2."""
    if width <= 0:
        return name
    return _one_line(name, metrics, width) if lines <= 1 else _two_lines(name, metrics, width)


class ElidedNameDelegate(QStyledItemDelegate):
    """Affiche le nom d'un item selon `elide_name`, dans `lines` lignes."""

    def __init__(self, lines: int = 1, parent=None):
        super().__init__(parent)
        self._lines = lines

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        option.text = elide_name(option.text, option.fontMetrics, self._text_width(option), self._lines)

    @staticmethod
    def _text_width(option: QStyleOptionViewItem) -> int:
        """La largeur dont le texte DISPOSE vraiment : celle que le style de Qt lui réserve (l'icône
        et ses marges retirées), moins les deux marges de texte qu'il retire encore au dessin. Une
        largeur devinée un peu trop grande, et Qt abrège de nouveau le nom déjà coupé — l'extension
        disparaissait derrière son « … »."""
        widget = option.widget
        style = widget.style() if widget is not None else QApplication.style()
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, widget)
        margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, option, widget) + 1
        return text_rect.width() - 2 * margin - 1
