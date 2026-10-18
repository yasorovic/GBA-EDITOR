"""Cartridge previews. Experimental profiles never change the compilation target."""
from dataclasses import dataclass
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QSizePolicy,
)

from core import app_paths
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.common.tooltip_controller import TooltipContent, set_tooltip_provider


_IMAGES = Path(__file__).parent / "images" / "cartridges"
_LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"
_CATALOG = json.loads((_IMAGES / "photo-catalog.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class SavePreviewProfile:
    key: str
    title_key: str
    chip_key: str
    capacities: tuple[int, ...]
    battery: str = "none"
    rtc: bool = False
    release_ready: bool = False


SAVE_PREVIEW_PROFILES = (
    SavePreviewProfile("none", "cartpreview.profile_none", "", (0,)),
    SavePreviewProfile("sram", "cartpreview.profile_sram", "cartpreview.profile_sram",
                       (32768,), battery="save", release_ready=True),
    SavePreviewProfile("eeprom", "cartpreview.profile_eeprom", "cartpreview.profile_eeprom",
                       (512, 8192)),
    SavePreviewProfile("flash", "cartpreview.profile_flash", "cartpreview.profile_flash",
                       (65536, 131072)),
    SavePreviewProfile("fram", "cartpreview.profile_fram", "cartpreview.profile_fram",
                       (32768,)),
    SavePreviewProfile("flash_rtc", "cartpreview.profile_flash_rtc", "cartpreview.profile_flash",
                       (131072,), battery="rtc", rtc=True),
)


def save_preview_profiles():
    """Unimplemented profiles are available only when running from source."""
    return tuple(p for p in SAVE_PREVIEW_PROFILES if p.release_ready or not app_paths.IS_FROZEN)


def save_capacity_text(size):
    return (label('cartpreview.capacity_kib', value=size // 1024) if size >= 1024
            else label('cartpreview.capacity_bytes', value=size))


class _BoardDiagram(QWidget):
    """Illustrative layout, deliberately distinct from a photo of real hardware."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile = SAVE_PREVIEW_PROFILES[0]
        self.capacity = 0
        self.mib = 4
        self.setFixedHeight(200)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate((self.width() - min(self.width(), 340)) / 2, 0)
        painter.scale(min(self.width(), 340) / 340, 1)
        painter.setPen(QPen(QColor(C.TECH_OUTLINE), 2))
        painter.setBrush(QColor(C.TECH_BG))
        painter.drawRoundedRect(QRectF(8, 10, 324, 176), 14, 14)
        # Edge contacts suggest the cartridge without claiming a PCB revision.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C.ACCENT_WARM))
        for index in range(24):
            painter.drawRect(QRectF(25 + index * 12, 164, 7, 20))

        def chip(rect, name, detail, number):
            painter.setPen(QPen(QColor(C.TECH_OUTLINE), 1))
            for index in range(6):
                y = rect.y() + 8 + index * (rect.height() - 16) / 5
                painter.drawLine(int(rect.left() - 5), int(y), int(rect.right() + 5), int(y))
            painter.setBrush(QColor(C.BG_RAISED))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor(C.TEXT_HI))
            painter.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
            painter.drawText(rect.adjusted(3, 10, -3, -20) if detail else rect,
                             Qt.AlignmentFlag.AlignCenter, name)
            painter.setFont(QFont(T.UI, T.XS))
            painter.drawText(rect.adjusted(2, 31, -2, -3), Qt.AlignmentFlag.AlignCenter, detail)
            painter.drawText(rect.adjusted(5, 0, -2, -rect.height() + 16),
                             Qt.AlignmentFlag.AlignLeft, str(number))

        chip(QRectF(203, 27, 102, 82), label('cartpreview.chip_rom'),
             label('cartpreview.rom_capacity', mib=self.mib), 1)
        if self.profile.capacities != (0,):
            chip(QRectF(34, 27, 116, 72), label(self.profile.chip_key),
                 save_capacity_text(self.capacity), 2)
        if self.profile.rtc:
            chip(QRectF(145, 116, 67, 35), label('cartpreview.chip_rtc'), "", 4)
        if self.profile.battery != "none":
            battery = QRectF(49, 106, 45, 45)
            painter.setPen(QPen(QColor(C.ACCENT_WARM), 2))
            painter.setBrush(QColor(C.BG_RAISED))
            painter.drawEllipse(battery)
            painter.setPen(QColor(C.TEXT_HI))
            painter.drawText(battery, Qt.AlignmentFlag.AlignCenter, "3")


class _BoardPhoto(QWidget):
    """Numbered landmarks painted over the unmodified, aspect-preserved photo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.points = ()
        self.marker_tooltips = {}
        self.setMouseTracking(True)
        set_tooltip_provider(self, self._tooltip_at)
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def sizeHint(self):
        return QSize(320, 200)

    def set_board(self, filename, points, marker_tooltips=None):
        self.pixmap = QPixmap(str(_IMAGES / filename))
        self.points = points
        self.marker_tooltips = marker_tooltips or {}
        self.update()

    def _image_rect(self):
        if self.pixmap.isNull():
            return QRectF()
        size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width() - size.width()) / 2,
                      (self.height() - size.height()) / 2, size.width(), size.height())

    def _marker_rect(self, x, y):
        image = self._image_rect()
        return QRectF(image.x() + x * image.width() - 10,
                      image.y() + y * image.height() - 10, 20, 20)

    def _tooltip_at(self, position):
        if not self.pixmap.isNull():
            for number, x, y in self.points:
                marker = self._marker_rect(x, y)
                delta = marker.center() - QPointF(position)
                if delta.x() ** 2 + delta.y() ** 2 <= 10 ** 2:
                    return TooltipContent(self.marker_tooltips.get(number, ''),
                                          marker.toAlignedRect())
        # The rest of the photo has no help; do not inherit the panel's tooltip.
        return TooltipContent('', self.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.pixmap.isNull():
            painter.setPen(QColor(C.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             label('cartpreview.unavailable'))
            return
        rect = self._image_rect()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(rect, self.pixmap, QRectF(self.pixmap.rect()))
        painter.setFont(QFont(T.UI, T.SM, QFont.Weight.Bold))
        for number, x, y in self.points:
            badge = self._marker_rect(x, y)
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.setBrush(QColor("#171717"))
            painter.drawEllipse(badge)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(number))


class CartridgePreview(QFrame):
    """An example of supported hardware, never a claim about a detected cart."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(520)
        self.setObjectName("cartridgePreview")
        self.setStyleSheet(
            f"QFrame#cartridgePreview{{background:{C.BG_PANEL};"
            f"border:1px solid {C.BORDER};border-radius:6px;}}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)
        self._title = self._text(label('cartpreview.title'), emphasized=True)
        self._target = self._text("")
        self._photo = _BoardPhoto()
        layout.addWidget(self._title)
        layout.addWidget(self._target)
        views = QHBoxLayout()
        # Parent before visibility; otherwise Qt briefly opens a separate window.
        # See ARCHITECTURE.md, « Visibilité Qt et micro-fenêtres ».
        self._view_mode = QComboBox(self)
        self._view_mode.addItem(label('cartpreview.assembled'), "assembled")
        if not app_paths.IS_FROZEN:
            self._view_mode.addItem(label('cartpreview.bare'), "bare")
        self._view_mode.setAccessibleName(label('cartpreview.view_mode'))
        self._side = QComboBox(self)
        self._side.addItem(label('cartpreview.front'), "front")
        self._side.addItem(label('cartpreview.back'), "back")
        self._side.setAccessibleName(label('cartpreview.view_side'))
        views.addWidget(self._view_mode, 1)
        views.addWidget(self._side)
        layout.addLayout(views)
        self._view_mode.setVisible(not app_paths.IS_FROZEN)
        layout.addWidget(self._photo)
        self._diagram = _BoardDiagram()
        self._diagram.hide()
        layout.addWidget(self._diagram)
        self.profile_id = "sram"
        self.capacity = 32768
        self._mib = 4
        self._reference = self._text("")
        self._rom = self._text("")
        self._save = self._text(label('cartpreview.sram'))
        self._battery = self._text("")
        self._note = self._text("")
        self._credit = self._text("")
        self._credit.setTextFormat(Qt.TextFormat.RichText)
        self._credit.setOpenExternalLinks(True)
        for widget in (self._reference, self._rom, self._save, self._battery,
                       self._note, self._credit):
            layout.addWidget(widget)
        self._view_mode.currentIndexChanged.connect(self._refresh)
        self._side.currentIndexChanged.connect(self._refresh)

    @staticmethod
    def _text(text, emphasized=False):
        widget = QLabel(text)
        widget.setWordWrap(True)
        widget.setFont(QFont(T.UI, T.SM,
                            QFont.Weight.DemiBold if emphasized else QFont.Weight.Normal))
        widget.setStyleSheet(
            f"color:{C.TEXT_HI if emphasized else C.TEXT_DIM};background:transparent;")
        return widget

    def set_target(self, mib):
        self._mib = mib
        self._refresh()

    def set_profile(self, key, capacity=None):
        # Even direct callers cannot activate source-only previews in a distribution.
        profile = next((p for p in save_preview_profiles() if p.key == key),
                       SAVE_PREVIEW_PROFILES[1])
        self.profile_id = profile.key
        self.capacity = capacity if capacity in profile.capacities else profile.capacities[0]
        self._refresh()

    def _refresh(self):
        mib = self._mib
        profile = next(p for p in SAVE_PREVIEW_PROFILES if p.key == self.profile_id)
        if profile.key == "sram":
            key = "sram4" if mib == 4 else "sram8"
        elif profile.key in ("eeprom", "flash"):
            key = f"{profile.key}{self.capacity}"
        else:
            key = profile.key
        specimen = _CATALOG[key]
        board, reference_mib = specimen["board"], specimen["rom_mib"]
        bare_available = not app_paths.IS_FROZEN and "bare" in specimen
        if self._view_mode.count() > 1:
            self._view_mode.model().item(1).setEnabled(bare_available)
        if not bare_available and self._view_mode.currentData() == "bare":
            self._view_mode.blockSignals(True)
            self._view_mode.setCurrentIndex(0)
            self._view_mode.blockSignals(False)
        bare = bare_available and self._view_mode.currentData() == "bare"
        side = self._side.currentData()
        source = specimen["bare"][side] if bare else specimen["photos"][side]
        filename = (app_paths.APP_DIR / "research" / "cartridges" / source["relative_path"]
                    if bare else _IMAGES / source["file"])
        points = specimen["points"] if not bare and side == "front" else ()
        self._photo.set_board(filename, points, self._component_tooltips(profile))
        self._photo.show()
        self._diagram.hide()
        self._rom.show()
        self._save.show()
        self._battery.show()
        self._credit.show()
        if self._photo.pixmap.isNull() and not bare:
            self._set_diagram()
            self._note.setText(label('cartpreview.unavailable'))
            return
        self._target.setText(label('cartpreview.target', mib=mib) if profile.key == "sram"
                             else label('cartpreview.preview_target', mib=mib,
                                        profile=label(profile.title_key)))
        self._reference.setText(label('cartpreview.reference', board=board))
        self._rom.setText(label('cartpreview.rom', mib=reference_mib))
        self._save.setText(label('cartpreview.no_save') if not self.capacity else label(
            'cartpreview.diagram_save', kind=label(profile.chip_key),
            capacity=save_capacity_text(self.capacity)))
        if profile.key == "sram":
            self._save.setText(label('cartpreview.sram'))
            battery = label('cartpreview.battery_removed') if key == "sram4" else label(
                'cartpreview.battery_mounted')
        else:
            battery = label('cartpreview.rtc_battery') if profile.rtc else label(
                'cartpreview.no_battery')
        self._battery.setText(battery)
        note = (label('cartpreview.example') if mib not in (4, 8)
                else label('cartpreview.supported')) if profile.key == "sram" else label(
                    'cartpreview.photo_preview_only')
        if profile.key != "sram" and reference_mib != mib:
            note += " " + label('cartpreview.photo_capacity', mib=reference_mib)
        if profile.rtc:
            note += " " + label('cartpreview.rtc_removed')
        if bare:
            note = label('cartpreview.bare_note')
            self._rom.hide()
            self._save.hide()
            self._battery.hide()
        self._note.setText(note)
        self._photo.setAccessibleName(" · ".join((
            label('cartpreview.photo_accessible', board=board), self._side.currentText(),
            self._view_mode.currentText())))
        self._credit.setText(label('cartpreview.bare_credit', color=C.TEXT_DIM,
                                   source_url=source["source_page"]) if bare else label(
            'cartpreview.credit', color=C.TEXT_DIM, source_url=source["source_page"],
            author=specimen["author"], license_url=_LICENSE))

    @staticmethod
    def _component_tooltips(profile):
        def help_text(number, name, body_key):
            return tooltip(title=label('cartpreview.component_title', number=number, name=name),
                           body=label(body_key))

        tips = {1: help_text(1, label('cartpreview.chip_rom'), 'cartpreview.help_rom')}
        if profile.capacities != (0,):
            bodies = {
                'sram': 'cartpreview.help_sram',
                'eeprom': 'cartpreview.help_eeprom',
                'flash': 'cartpreview.help_flash',
                'fram': 'cartpreview.help_fram',
                'flash_rtc': 'cartpreview.help_flash',
            }
            tips[2] = help_text(2, label(profile.chip_key), bodies[profile.key])
        if profile.battery != 'none':
            tips[3] = help_text(3, label('cartpreview.chip_battery'),
                                'cartpreview.help_battery_rtc' if profile.rtc
                                else 'cartpreview.help_battery_save')
        if profile.rtc:
            tips[4] = help_text(4, label('cartpreview.chip_rtc'), 'cartpreview.help_rtc')
        return tips

    def _set_diagram(self):
        profile = next(p for p in SAVE_PREVIEW_PROFILES if p.key == self.profile_id)
        self._photo.hide()
        self._credit.hide()
        self._diagram.show()
        self._diagram.profile = profile
        self._diagram.capacity = self.capacity
        self._diagram.mib = self._mib
        self._diagram.update()
        self._target.setText(label('cartpreview.preview_target', mib=self._mib,
                                   profile=label(profile.title_key)))
        self._reference.setText(label('cartpreview.schematic'))
        self._rom.setText(label('cartpreview.diagram_rom', mib=self._mib))
        self._save.setText(label('cartpreview.no_save') if not self.capacity else label(
            'cartpreview.diagram_save', kind=label(profile.chip_key),
            capacity=save_capacity_text(self.capacity)))
        self._battery.setText(label('cartpreview.rtc_battery') if profile.rtc
                              else label('cartpreview.battery_mounted') if profile.battery == "save"
                              else label('cartpreview.no_battery'))
        self._note.setText(label('cartpreview.preview_only'))
        self._diagram.setAccessibleName("\n".join((
            self._reference.text(), self._rom.text(), self._save.text(), self._battery.text())))
