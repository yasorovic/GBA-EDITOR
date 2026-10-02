"""
ui/common/rom_budget_bar.py — bandeau fixe du panneau Build/debug : ce que la
ROM pèse RÉELLEMENT, mesuré sur le dernier build (codegen/rom_report.py).

Même langage visuel que `GbaStatusBar`/`SoundBudgetBar` (window.py,
sound_budget_bar.py) : label gris, valeur en gras, tooltip qui porte le
détail. Deux différences volontaires :

  - la jauge propose deux lectures : remplissage de la cartouche ou
    répartition entre catégories ; chaque segment (Audio, Fonds, Sprites…)
    garde SA couleur — l'exception à « une teinte par
    famille, la forme distingue le détail » (icons.py) que ce widget ne peut
    pas suivre : une icône a une forme, un pixel de barre n'en a pas, la
    teinte est ici la SEULE chose qui distingue un segment de son voisin ;
  - le mot « ROM » est cliquable : il choisit la cartouche visée
    (`Project.settings.cartridge_mib`), le dénominateur de cette jauge.

Rien n'est estimé : `RomReport` vient de `codegen/rom_report.py`, lu sur
l'ELF et le `.gba` d'un build réel. Tant qu'aucun build n'a eu lieu, le
bandeau le dit plutôt que d'annoncer un chiffre deviné.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from typing import Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy, QToolTip, QMenu
from PyQt6.QtGui import QFont, QPainter, QColor, QCursor
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.icons import COLOR_DEFAULT
from codegen.rom_report import RomReport, CARTRIDGE_SIZES_MIB

_WARN_RATIO = 0.75  # même seuil que GbaStatusBar / SoundBudgetBar

# Une couleur par catégorie de `rom_report.CATEGORY_ORDER`. Propres à CETTE barre
# (icons.py refuse toute teinte globale par famille d'asset) : en mode
# répartition, des segments gris ne se distingueraient pas. L'accent et le rouge
# sont laissés à l'état de remplissage (OK / dépassement), les catégories les
# évitent. Code/Reste ne sont pas des assets : les deux gris du thème.
_HUES_DARK = {
    "Audio": "#e0a050", "Polices": "#b48ce8", "Fonds": "#4fb3d9", "Sprites": "#4fd9c0",
    "Palettes": "#e07aa8", "Textes": "#e8e8e8", "Interface": "#5b8fe8",
    "Tables de données": "#d98a5b", "Collision": "#8a8ae8",
}
_HUES_LIGHT = {
    "Audio": "#b8741c", "Polices": "#7a4fc0", "Fonds": "#1f86ad", "Sprites": "#1f9d8a",
    "Palettes": "#c04a80", "Textes": "#555555", "Interface": "#2f5fc4",
    "Tables de données": "#b5602a", "Collision": "#5a5ac0",
}
_CATEGORY_COLORS: dict[str, str] = {
    **(_HUES_LIGHT if C.IS_LIGHT else _HUES_DARK),
    "Code":  C.TEXT_DIM,
    "Reste": C.TEXT_MUTED,
}


_CATEGORY_KEYS = {'Audio': 'rombar.audio', 'Polices': 'common.fonts', 'Fonds': 'common.backgrounds', 'Sprites': 'common.sprites', 'Palettes': 'common.palettes', 'Textes': 'common.texts', 'Interface': 'common.interface', 'Tables de données': 'rombar.data_tables', 'Collision': 'rombar.collision', 'Code': 'rombar.code', 'Reste': 'rombar.other'}


def _color_of(category: str) -> str:
    return _CATEGORY_COLORS.get(category, COLOR_DEFAULT)


class _Gauge(QWidget):
    """Jauge de ROM dans deux lectures complémentaires.

    ``fill`` mesure chaque segment contre la cartouche : la zone sombre est
    vraiment libre. ``breakdown`` remplit toute la largeur : les proportions
    entre consommateurs deviennent faciles à comparer.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        # [(catégorie, octets, couleur)], et le total (octets de la cartouche
        # visée) sur lequel la largeur de chaque segment se calcule.
        self._segments: list[tuple[str, int, str]] = []
        self._total = 0
        self._rom_bytes = 0
        self._mode = "fill"
        # Couleur du remplissage : accent / jaune / rouge selon l'état, posée par
        # la barre (elle seule connaît le seuil d'alerte).
        self.fill_color = C.ACCENT

    def set_data(self, categories: dict[str, int], rom_bytes: int, cartridge_bytes: int):
        """`cartridge_bytes` est le dénominateur ACTUEL, pas forcément celui
        du dernier build : choisir une autre cartouche redessine tout de
        suite, sur les mêmes octets mesurés — rien n'est remesuré."""
        self._segments = [(cat, size, _color_of(cat))
                          for cat, size in categories.items() if size > 0]
        self._total = max(1, cartridge_bytes)
        self._rom_bytes = rom_bytes
        self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def _segment_at(self, x: int) -> Optional[tuple[str, int]]:
        """Catégorie sous le pixel `x`, ou None (zone vide au-delà du poids
        réel — la cartouche a de la place libre, ce n'est pas un asset)."""
        w = self.width()
        pos = 0.0
        denominator = self._rom_bytes if self._mode == "breakdown" else self._total
        for cat, size, _color in self._segments:
            seg_w = w * size / max(1, denominator)
            if pos <= x < pos + seg_w:
                return cat, size
            pos += seg_w
        return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.BG_BASE))
        p.drawRect(0, 0, w, h)

        # Le quadrillage très discret donne une présence à l'espace libre :
        # il reste lisible sans concurrencer les segments de ressources.
        if self._mode == "fill":
            p.setPen(QColor(C.BORDER_DARK))
            for grid_x in range(16, w, 16):
                p.drawLine(grid_x, 2, grid_x, h - 3)
        p.setPen(Qt.PenStyle.NoPen)

        if self._mode == "fill":
            # Une seule information est utile ici : la capacité consommée.
            # Les catégories sont toujours retrouvées par `_segment_at` pour
            # le tooltip, sans fragmenter visuellement la progression.
            fill_w = round(w * self._rom_bytes / max(1, self._total))
            p.setBrush(QColor(self.fill_color))
            p.drawRect(0, 0, min(w, fill_w), h)
        else:
            x = 0.0
            for _cat, size, color in self._segments:
                seg_w = w * size / max(1, self._rom_bytes)
                p.setBrush(QColor(color))
                left, right = round(x), round(x + seg_w)
                # Un interstice noir d'un pixel garde chaque catégorie lisible.
                p.drawRect(left, 0, max(1, right - left - 1), h)
                x += seg_w

        # Même contour que les champs et boutons de l'application.
        p.setPen(QColor(C.BORDER_MID))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, max(0, w - 1), max(0, h - 1))
        p.end()

    def mouseMoveEvent(self, event):
        hit = self._segment_at(int(event.position().x()))
        if hit is None:
            if self._mode == "fill" and self._rom_bytes < self._total:
                free_kib = (self._total - self._rom_bytes) / 1024
                QToolTip.showText(event.globalPosition().toPoint(),
                                  label('rombar.free_space', size=free_kib), self)
            else:
                QToolTip.hideText()
            return
        cat, size = hit
        pct = 100 * size / max(1, self._rom_bytes)
        category = label(_CATEGORY_KEYS[cat]) if cat in _CATEGORY_KEYS else cat
        QToolTip.showText(event.globalPosition().toPoint(),
                          label('rombar.category_usage', category=category, size=size / 1024, percent=pct), self)

    def leaveEvent(self, event):
        QToolTip.hideText()


class RomBudgetBar(QWidget):
    """Bandeau fixe : occupation de la cartouche, en segments colorés par
    catégorie d'asset. Reste sur le DERNIER build tant qu'aucun nouveau
    rapport n'arrive — changer d'écran ou vider la console ne l'efface pas."""

    cartridge_mib_changed = pyqtSignal(int)

    _BLOCK_BG = C.BG_BASE
    _BLOCK_TEXT = C.TEXT_DIM
    _STYLE_OK   = f"color:{C.ACCENT};"
    _STYLE_WARN = f"color:{C.ACCENT_YLW};"
    _STYLE_CRIT = f"color:{C.ACCENT_RED};"

    @classmethod
    def _theme_block(cls, color: str | None = None) -> str:
        """Pavé compact qui suit les couleurs de champ du thème actif."""
        return (f"background:{cls._BLOCK_BG}; color:{color or cls._BLOCK_TEXT}; "
                f"border:1px solid {C.BORDER_MID}; padding:0 8px;")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"background:{C.BG_DEEP}; border-top:1px solid {C.BORDER};")
        self._cartridge_mib = 4
        # Dernier rapport mesuré — conservé à part de la cartouche choisie :
        # changer de cartouche sans rebuilder redessine sur les MÊMES octets,
        # rien n'est remesuré (cf. `_refresh`).
        self._report: Optional[RomReport] = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 5)
        lay.setSpacing(6)

        self._lbl_rom = QLabel()
        self._lbl_rom.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._lbl_rom.setFixedHeight(24)
        self._lbl_rom.setStyleSheet(self._theme_block())
        self._lbl_rom.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_rom.mousePressEvent = lambda e: self._open_cartridge_menu()
        lay.addWidget(self._lbl_rom)

        self._value = QLabel("—")
        self._value.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        self._value.setFixedHeight(24)
        self._value.setStyleSheet(self._theme_block())

        self._percent = QLabel()
        self._percent.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._percent.setFixedHeight(24)
        self._percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._percent.setStyleSheet(self._theme_block())

        self._gauge = _Gauge()
        lay.addWidget(self._gauge, 1)

        # Les chiffres viennent après la jauge : lecture gauche → droite,
        # capacité visuelle puis valeur mesurée et pourcentage exact.
        lay.addWidget(self._value)
        lay.addWidget(self._percent)

        self._mode = "fill"
        self._mode_button = QLabel()
        self._mode_button.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._mode_button.setFixedHeight(24)
        self._mode_button.setStyleSheet(self._theme_block())
        self._mode_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_button.mousePressEvent = lambda e: self._open_mode_menu()
        lay.addWidget(self._mode_button)

        self._refresh()

    def _open_cartridge_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        for mib in CARTRIDGE_SIZES_MIB:
            act = menu.addAction(f"{mib} MiB")
            act.setCheckable(True)
            act.setChecked(mib == self._cartridge_mib)
            act.triggered.connect(lambda _checked, m=mib: self._pick_cartridge(m))
        menu.exec(QCursor.pos())

    def _open_mode_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        for mode, key in (("fill", "rombar.mode_fill"),
                          ("breakdown", "rombar.mode_breakdown")):
            act = menu.addAction(label(key))
            act.setCheckable(True)
            act.setChecked(mode == self._mode)
            act.triggered.connect(lambda _checked, m=mode: self._set_mode(m))
        menu.exec(QCursor.pos())

    def _set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        self._gauge.set_mode(mode)
        self._refresh_mode_label()

    def _refresh_mode_label(self):
        key = "rombar.mode_fill" if self._mode == "fill" else "rombar.mode_breakdown"
        self._mode_button.setText(f"{label(key).upper()} ▾")
        self._mode_button.setToolTip(tooltip(
            title=label('rombar.mode_title'), body=label('rombar.mode_tip')))

    def _pick_cartridge(self, mib: int):
        if mib == self._cartridge_mib:
            return
        self.cartridge_mib_changed.emit(mib)

    def set_cartridge_mib(self, mib: int):
        """Reflète la cartouche RÉELLEMENT réglée dans le projet — appelé au
        chargement du projet et après tout changement, pas seulement celui
        fait ici (l'inspecteur de projet a le même réglage). Le mot ROM et la
        jauge se mettent à jour tout de suite, même sans nouveau build."""
        self._cartridge_mib = mib
        self._refresh()

    @staticmethod
    def _kio(n: int) -> str:
        return f"{n / 1024:,.1f} KiB".replace(",", " ")

    def update_report(self, report: Optional[RomReport]):
        """Reçoit le `RomReport` mesuré à la fin d'un build (rom_build.py,
        événement `rom_report`) — jamais recalculé ici."""
        if report is None:
            return
        self._report = report
        self._cartridge_mib = report.cartridge_bytes // (1024 * 1024)
        self._refresh()

    def _refresh(self):
        """Seul endroit qui écrit le libellé ROM, la valeur et la jauge —
        appelé aussi bien par un nouveau build que par un simple changement
        de cartouche, pour que les deux chemins ne divergent jamais."""
        self._lbl_rom.setText(label('rombar.target', _cartridge_mib=self._cartridge_mib))
        self._refresh_mode_label()
        self._lbl_rom.setToolTip(tooltip(title=label('rombar.target_title')))

        cartridge_bytes = self._cartridge_mib * 1024 * 1024
        report = self._report
        if report is None:
            self._value.setText("—")
            self._percent.setText("—")
            self._value.setStyleSheet(self._theme_block())
            self._percent.setStyleSheet(self._theme_block())
            self._gauge.set_data({}, 0, cartridge_bytes)
            return

        fill_ratio = report.rom_bytes / cartridge_bytes if cartridge_bytes else 0.0
        pct = 100 * fill_ratio
        self._value.setText(self._kio(report.rom_bytes))
        self._percent.setText(f"{pct:.1f}%")
        if report.rom_bytes > cartridge_bytes:
            style = self._STYLE_CRIT
        elif fill_ratio >= _WARN_RATIO:
            style = self._STYLE_WARN
        else:
            style = self._STYLE_OK
        color = style.removeprefix("color:").removesuffix(";")
        self._gauge.fill_color = (C.ACCENT_RED if style == self._STYLE_CRIT
                                  else C.ACCENT_YLW if style == self._STYLE_WARN
                                  else C.ACCENT)
        self._value.setStyleSheet(self._theme_block(color))
        self._percent.setStyleSheet(self._theme_block(color))
        self._gauge.set_data(report.categories, report.rom_bytes, cartridge_bytes)
