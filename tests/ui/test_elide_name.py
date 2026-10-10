"""Couper un nom trop long en gardant son extension : `monnomq... .extension`."""
from pathlib import Path

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QFont, QFontMetrics, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem

from core import disk_tree
from ui.common.disk_tree_view import DiskTreeView
from ui.common.disk_view import DiskView
from ui.common.elide_name import ElidedNameDelegate, elide_name
from ui.common.theme import GLOBAL_QSS

LONG = "monnomquiestbeaucouptroplong.extension"


def _metrics(qapp) -> QFontMetrics:
    return QFontMetrics(QFont("Arial", 10))


def _all_fit(metrics: QFontMetrics, text: str, width: int) -> bool:
    return all(metrics.horizontalAdvance(line) <= width for line in text.split("\n"))


def test_a_name_that_fits_is_left_alone(qapp):
    metrics = _metrics(qapp)
    for lines in (1, 2):
        assert elide_name("GOAL.wav", metrics, 400, lines) == "GOAL.wav"
        assert elide_name(LONG, metrics, 2000, lines) == LONG
        assert isinstance(elide_name(LONG, metrics, 1, lines), str)       # aucune place : pas de plantage
        assert elide_name(LONG, metrics, 0, lines) == LONG                # pas encore de largeur : intact


def test_one_line_keeps_the_extension_and_cuts_the_start(qapp):
    metrics = _metrics(qapp)
    width = metrics.horizontalAdvance("monnomq... .extension") + 4
    shown = elide_name(LONG, metrics, width, lines=1)
    assert shown.endswith("... .extension") and shown.startswith("monn") and "\n" not in shown
    assert metrics.horizontalAdvance(shown) <= width
    kept = len(shown) - len("... .extension")                             # le plus long début qui tient :
    assert metrics.horizontalAdvance(LONG[:kept + 1] + "... .extension") > width   # un de plus ne tiendrait plus


def _width(metrics: QFontMetrics, sample: str = "monnomquiestbeau") -> int:
    return metrics.horizontalAdvance(sample) + 2                          # ~16 caractères par ligne


def test_two_lines_break_before_the_extension_when_the_name_fits_a_line(qapp):
    metrics = _metrics(qapp)
    width = _width(metrics)
    shown = elide_name("Falling Asleep.json", metrics, width, lines=2)       # une lettre seule tombait : `.jso` / `n`
    assert shown == "Falling Asleep\n.json"


def test_two_lines_break_at_a_space_never_inside_a_word(qapp):
    metrics = _metrics(qapp)
    width = _width(metrics)
    shown = elide_name("Out of Energy Game Over.json", metrics, width, lines=2)
    first, second = shown.split("\n")
    assert first + " " + second == "Out of Energy Game Over.json"          # la coupe remplace une espace
    assert "Game" in shown and _all_fit(metrics, shown, width)               # `Ga` / `me` n'existe plus


def test_two_lines_never_leave_a_lone_letter_on_the_second_line(qapp):
    metrics = _metrics(qapp)
    width = _width(metrics)
    name = "abcdefghijklmnopq"                                              # 17 caractères sans espace : le dernier tombait seul
    shown = elide_name(name, metrics, width, lines=2)
    first, second = shown.split("\n")
    assert first + second == name and len(second) >= 4 and _all_fit(metrics, shown, width)
    assert "\n" in elide_name("abcdefghijklmnopqrstuvwxyz.wav", metrics, width, lines=2)


def test_the_names_that_showed_lone_letters_in_the_jingles_folder(qapp):
    """Les noms d'une capture réelle (dossier jingles) : `.jso` / `n`, `Radical Victory.js` / `on`, `Ga` / `me`."""
    metrics = _metrics(qapp)
    expected = {
        "Falling Asleep.json": "Falling Asleep" + chr(10) + ".json",
        "Falling Asleep.mod": "Falling Asleep" + chr(10) + ".mod",
        "Radical Victory.json": "Radical Victory" + chr(10) + ".json",
        "Rascal's Ditty.mod": "Rascal's Ditty" + chr(10) + ".mod",
        "Out of Energy Game Over.json": "Out of Energy" + chr(10) + "Game Over.json",
        "Nursery Rhyme with pauses.mod": "Nursery Rhyme" + chr(10) + "with pauses.mod",
        "Short Lullaby with pauses.json": "Short Lullaby" + chr(10) + "with pauses.json",
        "GAMEOVER.json": "GAMEOVER.json",
    }
    # Une ligne juste assez large pour la plus longue ligne attendue : pas une largeur à quelques pixels
    # d'une limite, que la moindre différence de police ferait basculer d'une exécution à l'autre.
    width = max(metrics.horizontalAdvance(line) for shown in expected.values() for line in shown.split(chr(10))) + 2
    for name, shown in expected.items():
        if shown != name:
            assert metrics.horizontalAdvance(name) > width, name        # le nom ne tient pas sur une ligne
        assert elide_name(name, metrics, width, lines=2) == shown, name


def test_two_lines_cut_only_when_still_too_long_and_the_extension_stays_alone(qapp):
    metrics = _metrics(qapp)
    width = metrics.horizontalAdvance("monnomquiestbeau") + 2
    shown = elide_name(LONG, metrics, width, lines=2)
    first, second = shown.split("\n")
    assert second == ".extension" and first.endswith("...") and first.startswith("monn")
    assert _all_fit(metrics, shown, width)


def test_without_an_extension_the_end_of_the_second_line_is_cut(qapp):
    metrics = _metrics(qapp)
    width = metrics.horizontalAdvance("monnomquiestbeau") + 2
    shown = elide_name("monnomquiestbeaucouptroplongvraimentbeaucouptroplong", metrics, width, lines=2)
    assert "\n" in shown and shown.endswith("...") and _all_fit(metrics, shown, width)
    narrow = metrics.horizontalAdvance("monnomqu...") + 2
    one = elide_name("monnomquiestbeaucouptroplong", metrics, narrow, lines=1)
    assert one.endswith("...") and ".." not in one[:-3]


def test_an_extension_too_long_for_the_room_falls_back_to_a_middle_cut(qapp):
    metrics = _metrics(qapp)
    width = metrics.horizontalAdvance("ab...")
    for lines in (1, 2):
        shown = elide_name("a." + "x" * 40, metrics, width, lines)
        assert shown and _all_fit(metrics, shown, width)


def test_the_delegate_shortens_only_what_is_displayed(qapp):
    delegate = ElidedNameDelegate(lines=1)
    model = QStandardItemModel()
    model.appendRow(QStandardItem(LONG))
    index = model.index(0, 0)
    # `initStyleOption` reprend la police de l'application : on mesure donc avec elle.
    room = QFontMetrics(qapp.font()).horizontalAdvance("monnomq... .extension") + 40
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, room, 20)
    delegate.initStyleOption(option, index)
    assert option.text.endswith(".extension") and option.text != LONG
    assert index.data() == LONG                              # le modèle garde le nom entier


NAMES = ["Swing into Victory.json", "Swing into Victory.mod", "The Sad Truth.json", "Victory Fanfare.json",
         "Victory Fanfare.mod", LONG, "GAMEOVER.json", "another_extremely_long_file_name_without_end"]


def _qt_would_elide(view, delegate, index) -> bool:
    """Qt abrège de son côté un texte plus large que la place qu'il réserve : c'est CE test qui
    avait manqué — le texte du délégué tenait dans la largeur qu'il avait devinée, pas dans la vraie."""
    option = QStyleOptionViewItem()
    view.initViewItemOption(option)
    option.rect = view.visualRect(index)
    option.widget = view
    delegate.initStyleOption(option, index)
    style = view.style()
    margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, option, view) + 1
    available = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, view).width() - 2 * margin
    return any(option.fontMetrics.horizontalAdvance(line) > available for line in option.text.split("\n"))


def _jingles_tree() -> disk_tree.DiskNode:
    base = Path("assets")
    return disk_tree.DiskNode("assets", base, disk_tree.FOLDER, children=[
        disk_tree.DiskNode(name, base / name, disk_tree.ASSET if row % 2 == 0 else disk_tree.LINKED_SOURCE,
                           "x", "jingles")
        for row, name in enumerate(NAMES)])


def test_in_the_real_tree_qt_never_elides_what_the_delegate_already_cut(qapp):
    """Le vrai arbre de l'onglet Disk, avec la feuille de style de l'application : c'est elle (marges
    des items, icônes) qui faisait que la largeur devinée était trop grande — `Vi... .mod` devenait
    `Vi... .m…`. Une vue nue n'aurait jamais montré le défaut."""
    qapp.setStyleSheet(GLOBAL_QSS)
    try:
        for width in range(150, 331, 20):
            view = DiskTreeView()
            view.resize(width, 500)
            view.set_tree(_jingles_tree())
            view.show()
            qapp.processEvents()
            top = view._tree.topLevelItem(0)
            for row in range(top.childCount()):
                index = view._tree.indexFromItem(top.child(row))
                assert not _qt_would_elide(view._tree, view._tree.itemDelegate(), index), (width, NAMES[row])
            view.close()
    finally:
        qapp.setStyleSheet("")


def test_in_the_real_flat_view_qt_never_elides_what_the_delegate_already_cut(qapp):
    qapp.setStyleSheet(GLOBAL_QSS)
    try:
        view = DiskView()
        view.resize(700, 300)
        view.set_tree(_jingles_tree())
        view.show()
        qapp.processEvents()
        assert view._list.count() > len(NAMES)
        for row in range(view._list.count()):
            index = view._list.indexFromItem(view._list.item(row))
            assert not _qt_would_elide(view._list, view._list.itemDelegate(), index), view._list.item(row).text()
    finally:
        qapp.setStyleSheet("")
