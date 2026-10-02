"""
ui/text_editor/font_inspector.py — colonne droite, contexte Police.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QLineEdit,
    QPushButton,
)
from PyQt6.QtGui import QFont, QPixmap, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QRect

from codegen.font_emit import advance_source, glyph_advance_px
from core.models.font import TILES_PER_CHARBLOCK, rect_tiles
from ui.common.theme import C, T, QSS
from ui.common.widgets import CollapsibleCard
from ui.common import icons
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.text_editor.colors import FONT_COLOR
from ui.text_editor.glyph_paint import key_out
from ui.text_editor.glyph_sheet import GlyphSheet
from ui.text_editor.inspector_shell import insp_scroll


class _CharsetEdit(QTextEdit):
    """QTextEdit qui signale la fin d'édition à la perte du focus, comme le fait
    `QLineEdit.editingFinished` — le charset n'est validé qu'en quittant la
    zone, jamais à chaque frappe (une frappe intermédiaire n'est pas un charset
    valide)."""

    editing_finished = pyqtSignal()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.editing_finished.emit()


class FontInspector(QWidget):
    """Contexte « police » : compteurs, couleurs-clés, charset et case courante.

    Le coût en tuiles est en tête parce que ces tuiles sont en concurrence
    directe avec le décor.
    """

    glyph_char_changed = pyqtSignal(object, str, str)   # (glyph, avant, après)
    charset_edited     = pyqtSignal(str)                # charset réécrit d'un bloc
    pick_asked         = pyqtSignal(str, str)           # (rôle, libellé)
    key_color_cleared  = pyqtSignal(str)                # rôle

    # (role, model field, label key, tooltip key).
    _KEY_ROLES = (
        ("bg", "bg_color", "common.background", "fontinsp.bg_tip"),
        ("space", "space_color", "fontinsp.space", "fontinsp.space_tip"),
    )

    # Libellés des sources de chasse nommées par `font_emit.advance_source`.
    # Diagnostic composé (source de chasse) — laissé littéral (fragments), cf.
    # politique de différé des blocs de stats interpolés.
    _ADV_ORIGIN = {
        "fnt":     'fontinsp.fnt_descriptor',
        "spacing": 'fontinsp.declared_by_spacing',
        "mono":    'fontinsp.mono',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._project = None
        self._glyph = None
        self._blocking = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        host, lay, self._name_lbl = insp_scroll(FONT_COLOR, label("fontinsp.title"))
        root.addWidget(host)

        info_card = CollapsibleCard(label("fontinsp.info"))
        self._info = QLabel("")
        self._info.setFont(QFont(T.UI, T.SM))
        self._info.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._info.setWordWrap(True)
        info_card.body_layout.addWidget(self._info)
        lay.addWidget(info_card)

        # ── Transparence ──────────────────────────────────────────
        # Pipettes plutôt que sélecteur de couleur : la couleur voulue est
        # sous les yeux, dans la planche.
        transparency_card = CollapsibleCard(label("fontinsp.transparency"))
        self._swatches: dict[str, QLabel] = {}
        for role, _field, lbl_key, tip_key in self._KEY_ROLES:
            transparency_card.body_layout.addLayout(self._key_row(role, lbl_key, tip_key))

        self._key_hint = QLabel("")
        self._key_hint.setFont(QFont(T.UI, T.XS))
        self._key_hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._key_hint.setWordWrap(True)
        transparency_card.body_layout.addWidget(self._key_hint)
        lay.addWidget(transparency_card)

        charset_card = CollapsibleCard(label("fontinsp.charset"))
        self._charset = _CharsetEdit()
        self._charset.setFont(QFont(T.CODE, T.MD))
        self._charset.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px;}}"
        )
        self._charset.setFixedHeight(80)
        self._charset.setToolTip(tooltip(
            title=label("fontinsp.charset_title"), body=label("fontinsp.charset_tip"),
        ))
        self._charset.editing_finished.connect(self._commit_charset)
        charset_card.body_layout.addWidget(self._charset)

        charset_hint = QLabel(label("fontinsp.charset_hint"))
        charset_hint.setFont(QFont(T.UI, T.XS))
        charset_hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        charset_hint.setWordWrap(True)
        charset_card.body_layout.addWidget(charset_hint)
        lay.addWidget(charset_card)

        glyph_card = CollapsibleCard(label("fontinsp.selected_glyph"))

        # La case seule, agrandie : c'est ce qu'on regarde pour décider quel
        # caractère lui assigner.
        self._glyph_preview = QLabel()
        self._glyph_preview.setFixedHeight(72)
        self._glyph_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._glyph_preview.setStyleSheet(
            f"background:{C.BG_INPUT}; border:1px solid {C.BORDER_MID};"
            f"border-radius:3px;")
        glyph_card.body_layout.addWidget(self._glyph_preview)

        # Case par case plutôt que le charset entier : corriger celle qu'on a
        # sous les yeux ne décale pas le reste.
        self._char_edit = QLineEdit()
        self._char_edit.setStyleSheet(QSS.lineedit)
        self._char_edit.setFont(QFont(T.CODE, T.LG))
        self._char_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._char_edit.setPlaceholderText(label("fontinsp.char_placeholder"))
        self._char_edit.setToolTip(tooltip(
            title=label("fontinsp.char_title"), body=label("fontinsp.char_tip"),
        ))
        self._char_edit.editingFinished.connect(self._commit_char)
        glyph_card.body_layout.addWidget(self._char_edit)

        self._glyph_info = QLabel(label("fontinsp.no_cell"))
        self._glyph_info.setFont(QFont(T.UI, T.XS))
        self._glyph_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._glyph_info.setWordWrap(True)
        glyph_card.body_layout.addWidget(self._glyph_info)

        self._hint = QLabel(label("fontinsp.glyph_hint"))
        self._hint.setFont(QFont(T.UI, T.XS))
        self._hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._hint.setWordWrap(True)
        glyph_card.body_layout.addWidget(self._hint)
        lay.addWidget(glyph_card)

        lay.addStretch()

    # ── Couleurs-clés ─────────────────────────────────────────────

    def _key_row(self, role: str, lbl_key: str, tip_key: str) -> QHBoxLayout:
        """Une ligne de couleur-clé : nom, pastille, pipette, effacement."""
        disp = label(lbl_key)
        tip = tooltip(title=disp, body=label(tip_key))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        name = QLabel(disp)
        name.setFont(QFont(T.UI, T.SM))
        name.setStyleSheet(f"color:{C.TEXT_NORM};")
        name.setToolTip(tip)
        name.setFixedWidth(84)
        row.addWidget(name)

        swatch = QLabel()
        swatch.setFixedSize(28, 20)
        swatch.setToolTip(tip)
        self._swatches[role] = swatch
        row.addWidget(swatch)
        row.addStretch()

        pick = QPushButton()
        pick.setIcon(icons.get("eyedropper", C.TEXT_NORM))
        pick.setFixedSize(24, 22)
        pick.setToolTip(tooltip(title=label("fontinsp.pick_title", name=disp)))
        pick.setStyleSheet(QSS.button_icon)
        pick.clicked.connect(lambda _=False, r=role, l=disp: self.pick_asked.emit(r, l))
        row.addWidget(pick)

        clear = QPushButton()
        clear.setIcon(icons.get("clear", C.TEXT_MUTED))
        clear.setFixedSize(24, 22)
        clear.setToolTip(tooltip(title=label("fontinsp.clear_title", name=disp),
                                 body=label("fontinsp.clear_tip", name=disp)))
        clear.setStyleSheet(QSS.button_icon)
        clear.clicked.connect(lambda _=False, r=role: self.key_color_cleared.emit(r))
        row.addWidget(clear)
        return row

    def refresh_keys(self):
        """Relit les pastilles et le libellé de chasse depuis le modèle —
        après un prélèvement, un effacement ou un undo."""
        f = self._font
        for role, field_name, _label, _tip in self._KEY_ROLES:
            rgb = getattr(f, field_name, None) if f else None
            sw = self._swatches[role]
            if rgb is None:
                sw.setStyleSheet(
                    f"background:{C.BG_INPUT}; border:1px dashed {C.BORDER_MID};"
                    f"border-radius:3px;")
                sw.setText("")
            else:
                r, g, b = rgb
                sw.setStyleSheet(
                    f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER_MID};"
                    f"border-radius:3px;")
                sw.setText("")
        n = len(f.key_colors()) if f else 0
        # L'espacement fait DEUX choses : il disparaît, et il déclare la
        # chasse. La seconde est invisible sur la planche, donc annoncée ici.
        mode = ""
        if f and f.source_format == "png":
            mode = (label("fontinsp.adv_spacing") if f.space_color
                    else label("fontinsp.adv_mono"))
        self._key_hint.setText(
            (label("fontinsp.key_none") if n == 0
             else label("fontinsp.key_count", n=n))
            + mode
        )

    def load(self, font, project=None):
        """Affiche `font` (ou l'état vide si None)."""
        self._font = font
        if project is not None:
            self._project = project
        if not font:
            self._name_lbl.setText("")
            self._info.setText("")
            self._charset.setPlainText("")
            self.refresh_keys()
            self.set_glyph(None)
            return
        self._name_lbl.setText(font.name)
        self.refresh_stats()
        self.refresh_keys()
        self.set_glyph(None)

    def refresh_stats(self):
        """Recalcule compteurs et charset — dérivés des glyphes, donc à relire
        après chaque édition."""
        f = self._font
        if not f:
            return
        # Le chiffre seul ne parle pas, la limite si : ces tuiles sont en
        # concurrence directe avec le décor.
        warn = label('fontinsp.exceeds_a_charblock') if f.exceeds_charblock() else ""
        self._info.setText(
            label('fontinsp.stats', value=len(f.glyphs), cell_w=f.cell_w, cell_h=f.cell_h, line_height=f.line_height, value_2=f.tile_count(), TILES_PER_CHARBLOCK=TILES_PER_CHARBLOCK, warn=warn, source_format=f.source_format)
        )
        self._charset.setPlainText(f.charset)

    def set_glyph(self, glyph, project=None):
        """Affiche la case courante : aperçu, caractère, rect et chasse."""
        if project is not None:
            self._project = project
        self._glyph = glyph
        self._blocking = True
        if not glyph:
            self._glyph_info.setText(label("fontinsp.no_cell"))
            self._glyph_preview.clear()
            self._char_edit.clear()
            self._char_edit.setEnabled(False)
            self._blocking = False
            return
        self._char_edit.setEnabled(True)
        self._char_edit.setText(glyph.char)
        self._glyph_preview.setPixmap(self._crop(glyph))
        extra = label('fontinsp.ligature') if len(glyph.char) > 1 else ""
        # D'OÙ vient la chasse, pas seulement sa valeur : « 5 px » ne dit pas si
        # c'est une décision de l'auteur ou le mono par défaut. La source est
        # nommée par l'émetteur, pas re-déduite ici.
        f = self._font
        origin = label(self._ADV_ORIGIN[advance_source(f)]) if f else "—"
        # Chasse EFFECTIVE, pas celle stockée : sans couleur d'espacement la
        # police est mono quoi que porte le champ (vieux sidecars).
        adv = glyph_advance_px(glyph, f) if f else glyph.advance
        self._glyph_info.setText(
            label('fontinsp.rect_w_h_at_x_y_advance_adv', w=glyph.w, h=glyph.h, x=glyph.x, y=glyph.y, adv=adv, origin=origin, extra=extra)
        )
        self._blocking = False

    def set_selection(self, count: int, rect):
        """Sélection multiple : l'aperçu montre le rectangle visé, donc le futur
        glyphe fusionné — pas seulement sa première case."""
        if count <= 1 or rect is None:
            return          # cas simple : set_glyph a déjà fait le travail
        self._glyph_preview.setPixmap(self._crop_rect(rect))
        self._char_edit.setEnabled(False)
        tw, th = rect_tiles(rect.width(), rect.height())
        self._glyph_info.setText(
            label('fontinsp.merge_stats', count=count, value=rect.width(), value_2=rect.height(), tw=tw, th=th)
        )

    def _crop(self, glyph) -> QPixmap:
        """Aperçu agrandi d'une case."""
        return self._crop_rect(QRect(glyph.x, glyph.y, glyph.w, glyph.h))

    def _crop_rect(self, r: QRect) -> QPixmap:
        """Découpe une région de la planche, la troue et l'agrandit au plus
        grand zoom entier qui tient (8×8 est illisible à taille réelle)."""
        f, p = self._font, self._project
        if not (f and p and f.asset):
            return QPixmap()
        path = p.asset_abs(f.asset)
        if not path or not path.exists():
            return QPixmap()
        sheet = QPixmap(str(path))
        if sheet.isNull():
            return QPixmap()
        cell = sheet.copy(r)
        z = max(1, min(64 // max(1, r.height()), 64 // max(1, r.width())))
        cell = cell.scaled(cell.width() * z, cell.height() * z,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.FastTransformation)
        # Troué comme la planche : c'est sur une case isolée qu'on juge si
        # l'espacement a bien été désigné.
        keys = f.key_colors()
        if not keys:
            return cell
        holed = key_out(cell, keys)
        out = QPixmap(holed.size())
        out.fill(Qt.GlobalColor.transparent)
        q = QPainter(out)
        q.fillRect(out.rect(), GlyphSheet._checker_brush())
        q.drawPixmap(0, 0, holed)
        q.end()
        return out

    def _commit_char(self):
        """Valide le caractère saisi — l'écran en fera une commande."""
        if self._blocking or not self._glyph:
            return
        new = self._char_edit.text()
        if new == self._glyph.char:
            return
        if not new:
            self._char_edit.setText(self._glyph.char)
            return
        self.glyph_char_changed.emit(self._glyph, self._glyph.char, new)

    def _commit_charset(self):
        """Valide le charset réécrit d'un bloc — l'écran en fera une commande.

        Les retours à la ligne ne sont pas des glyphes (cf. `Font`) : on les
        retire pour qu'un saut de ligne tapé par mégarde ne décale pas
        l'assignation."""
        if self._blocking or not self._font:
            return
        new = self._charset.toPlainText().replace("\n", "").replace("\r", "")
        if new == self._font.charset:
            return
        self.charset_edited.emit(new)
