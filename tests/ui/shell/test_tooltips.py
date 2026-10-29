"""Exercise the same application-level path as the running editor."""
import pytest

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QHelpEvent, QMouseEvent, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QApplication, QGraphicsScene, QGraphicsView, QLabel, QListWidget,
    QListWidgetItem, QTabBar, QTableView, QToolTip, QVBoxLayout, QWidget,
)

from ui.common.tooltip import TOOLTIP_DURATION_MS, TOOLTIP_WAKEUP_MS, tooltip, tooltip_html
from ui.common.tooltip_controller import (
    TooltipContent, install_tooltips, resolve_tooltip, set_tooltip_provider,
)


@pytest.fixture
def tips(qapp):
    controller = install_tooltips(qapp)
    yield controller
    controller.shutdown()


def hover(widget, position=None):
    position = position or widget.rect().center()
    event = QHelpEvent(QEvent.Type.ToolTip, position, widget.mapToGlobal(position))
    QApplication.sendEvent(widget, event)


def test_widget_plain_rich_and_local_styles_use_one_bubble(qapp, tips):
    host = QWidget()
    layout = QVBoxLayout(host)
    first, second = QLabel(), QLabel()
    first.setToolTip('Line one\nLine two & <filename>')
    second.setToolTip(tooltip(title='Title', body='Body', shortcut='Ctrl+K'))
    second.setStyleSheet('background:red;color:yellow;')
    layout.addWidget(first)
    layout.addWidget(second)
    host.show()
    qapp.processEvents()
    try:
        hover(first)
        bubble = tips._bubble
        assert bubble.isVisible()
        assert bubble._text.text() == 'Line one<br>Line two &amp; &lt;filename&gt;'
        hover(second)
        assert tips._bubble is bubble
        assert bubble._text.text() == second.toolTip()
        assert not QToolTip.isVisible()
        assert bubble.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert bubble.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert tips._expiry.interval() == TOOLTIP_DURATION_MS
    finally:
        host.close()


def test_item_roles_restore_list_and_table_tooltips(qapp, tips):
    view = QListWidget()
    for title in ('First', 'Second'):
        item = QListWidgetItem(title)
        item.setToolTip(f'{title}\nDetail')
        view.addItem(item)
    view.show()
    qapp.processEvents()
    try:
        first = view.visualItemRect(view.item(0)).center()
        hover(view.viewport(), first)
        assert tips._bubble._text.text() == 'First<br>Detail'
        second = view.visualItemRect(view.item(1)).center()
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(second),
                            QPointF(view.viewport().mapToGlobal(second)),
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), event)
        assert tips._bubble.isHidden()
        hover(view.viewport(), second)
        assert tips._bubble._text.text() == 'Second<br>Detail'
    finally:
        view.close()

    table = QTableView()
    model = QStandardItemModel(1, 1, table)
    item = QStandardItem('Value')
    item.setData('Cell detail', Qt.ItemDataRole.ToolTipRole)
    model.setItem(0, 0, item)
    model.setHeaderData(0, Qt.Orientation.Horizontal, 'Column detail', Qt.ItemDataRole.ToolTipRole)
    table.setModel(model)
    table.show()
    qapp.processEvents()
    try:
        hover(table.viewport(), table.visualRect(model.index(0, 0)).center())
        assert tips._bubble._text.text() == 'Cell detail'
        header = table.horizontalHeader()
        hover(header.viewport(), QPoint(5, 5))
        assert tips._bubble._text.text() == 'Column detail'
    finally:
        table.close()


def test_tabs_canvas_and_inherited_widget_tips(qapp, tips):
    tabs = QTabBar()
    tabs.addTab('Tab')
    tabs.setTabToolTip(0, 'Tab detail')
    tabs.show()
    try:
        hover(tabs, tabs.tabRect(0).center())
        assert tips._bubble._text.text() == 'Tab detail'
    finally:
        tabs.close()
    scene = QGraphicsScene()
    item = scene.addRect(0, 0, 80, 80)
    item.setToolTip('Note\n\nHardware detail')
    child = scene.addRect(5, 5, 10, 10)
    child.setParentItem(item)
    view = QGraphicsView(scene)
    view.show()
    qapp.processEvents()
    try:
        hover(view.viewport(), view.mapFromScene(10, 10))
        assert tips._bubble._text.text() == 'Note<br><br>Hardware detail'
    finally:
        view.close()
    parent = QWidget()
    parent.setToolTip('Inherited')
    child = QLabel(parent)
    assert resolve_tooltip(child, QPoint()).text == 'Inherited'


@pytest.mark.parametrize('kind', [QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.Close,
                                QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress,
                                QEvent.Type.Wheel, QEvent.Type.ApplicationDeactivate])
def test_tooltip_closes_on_interaction(qapp, tips, kind):
    widget = QLabel()
    widget.setToolTip('Detail')
    hover(widget)
    assert tips._bubble.isVisible()
    # Invoke the filter directly for typed input events to avoid fabricating
    # invalid QMouseEvent/QKeyEvent objects for a widget's native event handler.
    tips.eventFilter(widget, QEvent(kind))
    assert tips._bubble.isHidden()
    assert tips._anchor is None
    assert not tips._expiry.isActive()


def test_empty_tips_expiry_and_owner_destruction(qapp, tips):
    from PyQt6 import sip
    widget = QLabel()
    widget.setToolTip('Detail')
    hover(widget)
    tips._expiry.timeout.emit()
    assert tips._bubble.isHidden()
    hover(widget)
    sip.delete(widget)
    assert tips._bubble.isHidden()
    assert tips._anchor is None
    empty = QLabel()
    hover(empty)
    assert tips._bubble.isHidden()


def test_lazy_provider_wins_and_empty_provider_suppresses_fallback(qapp, tips):
    calls = []
    widget = QLabel()
    widget.setToolTip('Fallback')
    def provider(point):
        calls.append(point)
        return TooltipContent('Lazy metadata', widget.rect())
    set_tooltip_provider(widget, provider)
    assert calls == []
    hover(widget)
    assert len(calls) == 1
    assert tips._bubble._text.text() == 'Lazy metadata'
    set_tooltip_provider(widget, lambda point: TooltipContent('', widget.rect()))
    hover(widget)
    assert tips._bubble.isHidden()


def test_gauge_shares_tooltip_path_and_segment_bounds(qapp, tips):
    from ui.common.rom_budget_bar import _Gauge
    gauge = _Gauge()
    gauge.resize(200, 16)
    gauge.set_data({'Code': 1024, 'Audio': 1024}, 2048, 4096)
    first = resolve_tooltip(gauge, QPoint(10, 8))
    free = resolve_tooltip(gauge, QPoint(150, 8))
    assert first.text and free.text and first.text != free.text
    assert not first.rect.contains(QPoint(60, 8))
    hover(gauge, QPoint(150, 8))
    assert tips._bubble._text.text() == tooltip_html(free.text)
    assert not QToolTip.isVisible()


def test_install_is_lazy_idempotent_and_delay_is_platform_independent(qapp, tips):
    from PyQt6.QtWidgets import QStyle
    from ui.common.eliding_style import ElidingStyle
    assert install_tooltips(qapp) is tips
    assert tips._bubble is None
    style = ElidingStyle()
    assert style.styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay) == TOOLTIP_WAKEUP_MS
    assert style.styleHint(QStyle.StyleHint.SH_ToolTip_FallAsleepDelay) == 0


def test_shutdown_releases_the_bubble_before_application_destruction(qapp, tips):
    widget = QLabel()
    widget.setToolTip('Detail')
    hover(widget)
    bubble = tips._bubble
    tips.shutdown()
    assert tips._bubble is None
    assert bubble.isHidden()
    assert not tips._expiry.isActive()
    assert qapp._tooltip_controller is None
    tips.shutdown()  # The normal shutdown path may run after a cancelled picker.


def test_bubble_stays_within_screen_and_shrinks_after_long_content(qapp, tips):
    widget = QLabel()
    widget.setToolTip(tooltip(title='Long help', body='A readable detail. ' * 40))
    area = qapp.primaryScreen().availableGeometry()
    QApplication.sendEvent(widget, QHelpEvent(QEvent.Type.ToolTip, QPoint(), area.bottomRight()))
    qapp.processEvents()
    bubble = tips._bubble
    assert area.contains(bubble.geometry())
    width = bubble.width()
    widget.setToolTip('Short')
    hover(widget)
    qapp.processEvents()
    assert bubble.width() < width


def test_unbroken_paths_wrap_and_oversized_notes_are_bounded(qapp, tips):
    from PyQt6.QtGui import QTextDocument
    widget = QLabel()
    widget.setToolTip('a' * 500)
    hover(widget)
    assert tips._bubble._text.height() > tips._bubble._text.fontMetrics().height() * 2
    widget.setToolTip('A long note\n' * 200)
    area = qapp.primaryScreen().availableGeometry()
    QApplication.sendEvent(widget, QHelpEvent(QEvent.Type.ToolTip, QPoint(), area.bottomRight()))
    assert area.contains(tips._bubble.geometry())
    rendered = QTextDocument()
    rendered.setHtml(tips._bubble._text.text())
    assert rendered.toPlainText().endswith('…')
