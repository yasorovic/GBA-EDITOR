"""On-demand Disk metadata and previews. Never imports or re-encodes an asset."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from math import ceil
from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QTextOption
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from core import disk_tree
from core.models.gba_color import bgr555_to_hex, bgr555_to_rgb888
from core.models.palette import PaletteBank
from core.models.sprite import IMAGE_FILE_EXTS
from core.interface_preferences import disk_preview_collapsed, set_disk_preview_collapsed
from ui.common import icons
from ui.common.labels import label
from ui.common.theme import C, T


@dataclass
class DiskPreview:
    lines: list[str] = field(default_factory=list)
    image: QImage = field(default_factory=QImage)
    note: str = ""
    metadata: list[tuple[str, str]] = field(default_factory=list)
    text: str | None = None
    audio_path: Path | None = None


def _metadata_html(name, value):
    """Structure only: captions and values have already been localized."""
    return f'<span style="color:{C.TEXT_MUTED}">{escape(name)} :</span> {escape(value)}'


def _metadata(project, node):
    """Detailed human-readable fields, without dumping tile/pixel buffers."""
    rows = []

    def add(key, value):
        if value is not None and value != '':
            if isinstance(value, bool):
                value = label('disk.meta_yes' if value else 'disk.meta_no')
            rows.append((label(key), str(value)))

    def file_info(path, source=False):
        path = Path(path)
        add('disk.meta_source' if source else 'disk.meta_path', path)
        try:
            add('disk.meta_source_bytes' if source else 'disk.meta_bytes', f'{path.stat().st_size:,} B')
        except OSError:
            add('disk.meta_status', label('disk.preview_missing_source') if source else label('disk.preview_unavailable'))
            return
        if path.suffix.lower() in IMAGE_FILE_EXTS:
            reader = QImageReader(str(path))
            size = reader.size()
            if size.isValid():
                add('disk.meta_source_dimensions' if source else 'disk.meta_dimensions',
                    f'{size.width()} × {size.height()} px')
                add('disk.meta_format', bytes(reader.format()).decode('ascii', errors='replace').upper())
                from PIL import Image
                with Image.open(path) as image:
                    add('disk.meta_pixel_mode', image.mode)
                    add('disk.meta_transparency', 'A' in image.getbands() or 'transparency' in image.info)

    file_info(node.path)
    if node.kind == disk_tree.LINKED_SOURCE:
        add('disk.meta_linked_assets', node.owner)
    elif node.kind == disk_tree.FREE_SOURCE:
        add('disk.meta_status', label('disk.free_source'))
    if node.kind != disk_tree.ASSET:
        return rows
    getter = {'sprites': 'get_sprite', 'backgrounds': 'get_background', 'palettes': 'get_palette'}.get(node.family)
    obj = getattr(project, getter)(node.owner) if getter and project is not None else None
    if obj is None:
        return rows
    add('disk.meta_name', obj.name)
    if obj.asset:
        source = project.asset_abs(obj.asset)
        if source is not None:
            file_info(source, True)
    if node.family == 'palettes':
        add('disk.meta_capacity', obj.size)
        for index, color in enumerate(obj.colors):
            rows.append((label('disk.meta_color', index=index), bgr555_to_hex(color)))
        return rows
    add('disk.meta_quantization', obj.quantize_method)
    add('disk.meta_palette_overrides', ', '.join(f'{index}: {name}' for index, name in obj.palette_overrides.items()))
    if node.family == 'sprites':
        add('disk.meta_tiles_per_frame', obj.tiles_per_frame)
        for state in obj.states:
            rows.append((label('disk.meta_animation', name=state.name),
                         label('disk.meta_animation_details', directions=len(state.directions),
                               frames=sum(len(d.frames) for d in state.directions if d.mirror_of is None),
                               speed=state.speed,
                               loop=label('disk.meta_yes' if state.loop else 'disk.meta_no'))))
    else:
        add('disk.meta_kind', obj.kind)
        add('disk.meta_dither', obj.dither)
        if obj.mode == 'tiled':
            add('disk.meta_tile_grid', f'{obj.tiles_w} × {obj.tiles_h}')
            add('disk.meta_tile_count', len(obj.effective_tileset()))
            add('disk.meta_map_cells', len(obj.effective_tilemap()))
            add('disk.meta_painted_cells', len(obj.tile_paint))
        else:
            add('disk.meta_bitmap_bytes', len(obj.bitmap) // 2)
        for key, value in (
            ('disk.meta_canvas', obj.canvas_size), ('disk.meta_image_position', obj.image_pos),
            ('disk.meta_image_size', obj.image_size), ('disk.meta_added_palettes', ', '.join(obj.added_palettes)),
            ('disk.meta_placed_animations', len(obj.animations)),
        ):
            add(key, value)
        add('disk.meta_adjustments', label('disk.meta_adjustment_values', hue=obj.adjust.hue,
                                         saturation=obj.adjust.saturation, brightness=obj.adjust.brightness,
                                         contrast=obj.adjust.contrast))
        add('disk.meta_compression', label('disk.meta_compression_values',
            palettes=obj.compression.palettes_max, colors=obj.compression.colors_per_palette,
            global_colors=obj.compression.global_colors, tiles=obj.compression.tile_target,
            palette_colors=obj.compression.palette_colors))
        if obj.frame_w and obj.frame_h:
            add('disk.meta_frame_size', f'{obj.frame_w} × {obj.frame_h} px')
            add('disk.meta_frame_ticks', obj.speed)
            add('disk.meta_loop', obj.loop)
    return rows


def _qimage(image):
    image = image.convert("RGBA")
    # Bound retained preview memory, including unusually large source sheets.
    image.thumbnail((4096, 4096))
    return QImage(image.tobytes(), image.width, image.height,
                  QImage.Format.Format_RGBA8888).copy()


def _read_image(path, render, result):
    reader = QImageReader(str(path))
    size = reader.size()
    if not size.isValid():
        raise ValueError(reader.errorString())
    result.lines.append(label('disk.preview_image', width=size.width(), height=size.height(),
                              format=bytes(reader.format()).decode('ascii', errors='replace').upper()))
    if render:
        if max(size.width(), size.height()) > 4096:
            reader.setScaledSize(size.scaled(4096, 4096, Qt.AspectRatioMode.KeepAspectRatio))
            result.note = label('disk.preview_reduced')
        result.image = reader.read()
        if result.image.isNull():
            raise ValueError(reader.errorString())


def _palette_image(colors):
    columns = min(16, len(colors))
    if not columns:
        return QImage()
    image = QImage(columns * 24, ((len(colors) + columns - 1) // columns) * 24,
                   QImage.Format.Format_RGB32)
    image.fill(QColor(C.BG_DEEP))
    painter = QPainter(image)
    for i, color in enumerate(colors):
        painter.fillRect((i % columns) * 24, (i // columns) * 24, 23, 23,
                         QColor(*bgr555_to_rgb888(color)))
    painter.end()
    return image


def resource_preview(project, node, render=False):
    """Return None for other families. Metadata-only calls do not decode pixels.

    Read live project models so unsaved edits appear too. A source uses its own
    format even when linked to a different family (e.g. a PNG used as a font).
    """
    if node.kind == disk_tree.FOLDER:
        return None
    from ui.common.disk_audio_preview import read_audio_preview, supports_audio
    if supports_audio(node):
        result = DiskPreview()
        read_audio_preview(project, node, result, render)
        if render:
            result.metadata = _metadata(project, node) + result.metadata
        return result
    from ui.common.disk_text_preview import read_text_preview, supports_text
    if supports_text(node.path):
        result = DiskPreview()
        read_text_preview(node, result, render)
        if render:
            result.metadata = _metadata(project, node) + result.metadata
        return result
    source = node.kind != disk_tree.ASSET
    is_image = source and node.path.suffix.lower() in IMAGE_FILE_EXTS
    is_hex = source and node.path.suffix.lower() == '.hex'
    if not (is_image or is_hex or node.family in ('sprites', 'backgrounds', 'palettes')):
        return None
    result = DiskPreview()
    try:
        if is_image:
            _read_image(node.path, render, result)
        elif is_hex or node.family == 'palettes':
            palette = (PaletteBank.from_hex(node.path.stem, node.path.read_text(encoding='utf-8-sig'))
                       if is_hex else project.get_palette(node.owner))
            if palette is None:
                raise ValueError('palette')
            result.lines.append(label('disk.preview_colors', count=len(palette.colors), capacity=palette.size))
            if render:
                result.image = _palette_image(palette.colors)
        elif node.family == 'sprites':
            sprite = project.get_sprite(node.owner)
            if sprite is None:
                raise ValueError('sprite')
            result.lines.extend([
                label('disk.preview_frame', width=sprite.frame_w, height=sprite.frame_h),
                label('disk.preview_states', count=len(sprite.states)),
                label('disk.preview_frames', count=sum(len(d.frames) for s in sprite.states
                                                       for d in s.directions if d.mirror_of is None)),
                label('disk.preview_palettes', count=len(sprite.palettes)),
            ])
            path = project.asset_abs(sprite.asset)
            if path is None or not path.is_file():
                result.note = label('disk.preview_missing_source')
            elif render:
                from core.sprite_compose import compose_frame_image
                frame = next((f for s in sprite.states for d in s.directions
                              if d.mirror_of is None for f in d.frames if f.tiles), None)
                if frame is not None:
                    result.image = _qimage(compose_frame_image(path, frame, sprite.frame_w, sprite.frame_h))
                    result.note = label('disk.preview_first_frame')
                else:
                    result.note = label('disk.preview_empty_frame')
        elif node.family == 'backgrounds':
            from core.bg_bake import render_rgba
            bg = project.get_background(node.owner)
            if bg is None:
                raise ValueError('background')
            width, height = ((bg.out_w, bg.out_h) if bg.mode == 'bitmap'
                             else (bg.tiles_w * 8, bg.tiles_h * 8))
            result.lines.extend([
                label('disk.preview_background', mode=label('disk.preview_bitmap' if bg.mode == 'bitmap'
                                                           else 'disk.preview_tiled'), bpp=bg.bpp),
                label('disk.preview_dimensions', width=width, height=height),
                label('disk.preview_palettes', count=len(bg.palettes)),
            ])
            if render:
                if width * height > 16_777_216:
                    result.note = label('disk.preview_too_large')
                elif (bg.bitmap if bg.mode == 'bitmap' else bg.tilemap) and width and height:
                    result.image = _qimage(render_rgba(bg))
                    result.note = label('disk.preview_encoded')
                else:
                    path = project.asset_abs(bg.asset)
                    if path is not None and path.is_file():
                        _read_image(path, True, result)
                        result.note = label('disk.preview_source_fallback')
                    else:
                        result.note = label('disk.preview_missing_source')
    except (OSError, ValueError, TypeError, IndexError, KeyError, OverflowError):
        result.note = label('disk.preview_unavailable')
    if render:
        try:
            result.metadata = _metadata(project, node)
        except (OSError, ValueError, TypeError, IndexError, KeyError, OverflowError):
            result.metadata.append((label('disk.meta_status'), label('disk.preview_unavailable')))
    return result


class PreviewImage(QLabel):
    """Fit preview over a checkerboard, with crisp nearest-neighbour scaling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.setMinimumSize(80, 60)

    def paintEvent(self, event):
        painter = QPainter(self)
        visible = event.rect()
        for y in range(visible.top() // 12 * 12, visible.bottom() + 1, 12):
            for x in range(visible.left() // 12 * 12, visible.right() + 1, 12):
                painter.fillRect(x, y, 12, 12, QColor('#303030' if (x // 12 + y // 12) % 2 else '#242424'))
        if not self.image.isNull():
            size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            # Draw directly into the clipped viewport; zoom must not allocate a
            # full-size pixmap of a potentially 32768 x 32768 scroll widget.
            painter.drawImage(QRect((self.width() - size.width()) // 2,
                                    (self.height() - size.height()) // 2,
                                    size.width(), size.height()), self.image)
        painter.end()


class _MetadataPath(QTextEdit):
    """Selectable paths wrap anywhere and occupy only their actual line count."""
    def __init__(self, value):
        super().__init__()
        self.setReadOnly(True)
        self.setPlainText(value)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.setStyleSheet(f'QTextEdit{{background:{C.BG_BASE};color:{C.TEXT_NORM};border:none;padding:0;}}')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(self.viewport().width())
        height = ceil(self.document().size().height()) + 2
        if self.height() != height:
            self.setFixedHeight(height)


class DiskPreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('diskPreviewPanel')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f'QWidget#diskPreviewPanel{{background:{C.BG_BASE};}}'
                           f'QLabel{{color:{C.TEXT_NORM};}}')
        self._result = None
        self._collapsed = disk_preview_collapsed()
        # Vertical handle, always visible: it is the whole collapse control.
        self._chevron = QToolButton()
        self._chevron.setFixedWidth(16)
        self._chevron.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._chevron.setIconSize(QSize(12, 12))
        self._chevron.setStyleSheet(f'QToolButton{{border:none;background:{C.BG_DEEP};padding:0;}}'
                                    f'QToolButton:hover{{background:{C.BG_SEL};}}')
        self._chevron.clicked.connect(self._toggle)
        self._content = QWidget()
        layout = QVBoxLayout(self._content)
        self._empty = QLabel(label('disk.preview_empty'))
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(f'color:{C.TEXT_MUTED};')
        self._title = QLabel()
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setWordWrap(True)
        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        self._image = PreviewImage()
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setFont(QFont(T.CODE, T.SM))
        self._text.setStyleSheet(f'QPlainTextEdit{{background:{C.BG_DEEP};color:{C.TEXT_NORM};border:none;}}')
        self._text.hide()
        from ui.common.disk_audio_preview import DiskAudioPlayer
        self._audio = DiskAudioPlayer()
        self._audio.hide()
        self._details = QLabel()
        self._details.setTextFormat(Qt.TextFormat.PlainText)
        self._details.setWordWrap(True)
        self._enlarge = QPushButton(label('disk.preview_enlarge'))
        self._enlarge.clicked.connect(self._open)
        body.addWidget(self._image, 1)
        body.addWidget(self._text, 1)
        body.addWidget(self._audio)
        body.addWidget(self._details)
        body.addWidget(self._enlarge)
        layout.addWidget(self._empty, 1)
        layout.addWidget(self._title)
        layout.addWidget(self._body, 1)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._chevron)
        root.addWidget(self._content, 1)
        self._sync_collapsed()

    def _toggle(self):
        self._collapsed = not self._collapsed
        set_disk_preview_collapsed(self._collapsed)
        self._sync_collapsed()

    def _sync_collapsed(self):
        """The panel stays in place (header + chevron) so selecting never reflows the list."""
        self._chevron.setIcon(icons.get('panel_expand_left' if self._collapsed else 'panel_collapse_right', C.TEXT_NORM))
        self._content.setVisible(not self._collapsed)
        self._body.setVisible(self._result is not None)
        self._empty.setVisible(self._result is None)
        self._title.setVisible(self._result is not None)
        self.setFixedWidth(16 if self._collapsed else 280)

    def show_preview(self, name, result):
        self._audio.set_path(result.audio_path if result else None)
        self._audio.setVisible(result is not None and result.audio_path is not None)
        self._result = result
        if result is None:
            self._title.clear()
            self._image.image = QImage()
            self._text.clear()
            self._sync_collapsed()
            return
        self._title.setText(name)
        self._image.image = result.image
        self._image.update()
        is_text = result.text is not None
        self._image.setVisible(not is_text and not result.image.isNull())
        self._text.setVisible(is_text)
        self._text.setPlainText(''.join(result.text.splitlines(keepends=True)[:60]) if is_text else '')
        self._details.setText('\n'.join(result.lines + ([result.note] if result.note else [])))
        self._enlarge.setEnabled(is_text or result.audio_path is not None or not result.image.isNull())
        self._sync_collapsed()

    def _open(self):
        dialog = QDialog(self)
        dialog.setStyleSheet(f'QDialog{{background:{C.BG_BASE};}}'
                             f'QLabel{{color:{C.TEXT_NORM};}}'
                             f'QWidget#diskPreviewMetadata{{background:{C.BG_BASE};}}')
        dialog.setWindowTitle(self._title.text())
        dialog.resize(1100, 700)
        layout = QVBoxLayout(dialog)
        row = QHBoxLayout()
        is_text = self._result.text is not None
        is_audio = self._result.audio_path is not None
        scroll = QPlainTextEdit() if is_text else QScrollArea()
        scroll.setObjectName('diskPreviewImageScroll')
        scroll.viewport().setStyleSheet(f'background:{C.BG_DEEP};')
        image = PreviewImage()
        image.image = self._image.image
        if is_text:
            scroll.setObjectName('diskPreviewText')
            scroll.setReadOnly(True)
            scroll.setPlainText(self._result.text)
            scroll.setFont(QFont(T.CODE, T.SM))
            scroll.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            scroll.setStyleSheet(f'QPlainTextEdit{{background:{C.BG_DEEP};color:{C.TEXT_NORM};}}')
        else:
            scroll.setWidget(image)
            scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom = [1.0]

        def resize_image(factor):
            zoom[0] = max(0.05, min(8.0, factor))
            if is_text:
                font = scroll.font()
                font.setPointSizeF(max(6, T.SM * zoom[0]))
                scroll.setFont(font)
            else:
                image.resize(image.image.size() * zoom[0])
                image.update()

        for text, action in (
            (label('disk.text_wrap') if is_text else label('disk.preview_fit'),
             (lambda: scroll.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth
                      if scroll.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
                      else QPlainTextEdit.LineWrapMode.NoWrap)) if is_text else lambda: resize_image(min(
                scroll.viewport().width() / image.image.width(),
                scroll.viewport().height() / image.image.height()))),
            ('−', lambda: resize_image(zoom[0] / 1.5)),
            ('+', lambda: resize_image(zoom[0] * 1.5)),
            ('100 %', lambda: resize_image(1.0)),
        ):
            if is_audio:
                continue
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, fn=action: fn())
            row.addWidget(button)
        layout.addLayout(row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        audio_player = None
        if is_audio:
            from ui.common.disk_audio_preview import DiskAudioPlayer
            self._audio.stop()
            audio_player = DiskAudioPlayer()
            audio_player.set_path(self._result.audio_path)
            area = QWidget()
            audio_layout = QVBoxLayout(area)
            if self._result.image.isNull():
                placeholder = QLabel('\n'.join(self._result.lines))
                placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                placeholder.setTextFormat(Qt.TextFormat.PlainText)
                audio_layout.addWidget(placeholder, 1)
                scroll.hide()
                scroll.setParent(area)
            else:
                audio_layout.addWidget(scroll, 1)
            audio_layout.addWidget(audio_player)
            splitter.addWidget(area)
        else:
            splitter.addWidget(scroll)
        details_scroll = QScrollArea()
        details_scroll.setObjectName('diskPreviewMetadataScroll')
        details_scroll.setWidgetResizable(True)
        details_scroll.setMinimumWidth(240)
        details = QWidget()
        details.setObjectName('diskPreviewMetadata')
        details.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        form = QVBoxLayout(details)
        form.setContentsMargins(10, 8, 10, 8)
        form.setSpacing(4)
        heading = QLabel(label('disk.meta_title'))
        heading.setStyleSheet(f'font-weight:bold;color:{C.TEXT_HI};')
        form.addWidget(heading)
        summary = QLabel(self._details.text())
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addWidget(summary)
        for name, value in self._result.metadata:
            if name in (label('disk.meta_path'), label('disk.meta_source')):
                caption = QLabel(name)
                caption.setTextFormat(Qt.TextFormat.PlainText)
                caption.setStyleSheet(f'color:{C.TEXT_MUTED};')
                form.addWidget(caption)
                text = _MetadataPath(value)
            else:
                text = QLabel(_metadata_html(name, value))
                text.setTextFormat(Qt.TextFormat.RichText)
                text.setWordWrap(True)
                text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            form.addWidget(text)
        form.addStretch()
        details_scroll.setWidget(details)
        splitter.addWidget(details_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([760, 300])
        layout.addWidget(splitter, 1)
        dialog.show()
        if not is_text and not image.image.isNull():
            resize_image(min(scroll.viewport().width() / image.image.width(),
                             scroll.viewport().height() / image.image.height()))
        dialog.exec()
        if audio_player is not None:
            audio_player.stop()
        dialog.deleteLater()
