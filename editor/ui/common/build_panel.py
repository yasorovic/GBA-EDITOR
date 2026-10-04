"""BuildPanel, ToolchainBar."""

from ui.common.labels import label
from ui.common.tooltip import tooltip
from core.keybindings import get_keybindings
import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QPlainTextEdit, QToolButton, QTabWidget, QListWidget, QListWidgetItem,
    QSplitter,
)
from PyQt6.QtGui import QFont, QColor, QPen, QTextCharFormat, QTextCursor, QPainter, QPainterPath
from PyQt6.QtCore import pyqtSignal, pyqtProperty, Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtStateMachine import QStateMachine, QState
from PyQt6.QtSvg import QSvgRenderer

from ui.common.theme import C, T
from core.toolchain import Toolchain
from ui.common.rom_budget_bar import RomBudgetBar


# ── Mascotte du bouton Build & Run ──────────────────────────────────
# Illustrations en COULEURS PLEINES (crête et bec mauves, corps blanc…) —
# rendues telles quelles, sans reteinte par icons.py (qui ne gère que les
# glyphes qtawesome monochromes).
_MASCOT_DIR = Path(__file__).parent / "CustomIcons"
_MASCOT_FILES = {
    "idle":    "BUILD-WAIT-SUCCESS.svg",   # au repos, prêt à lancer
    "working": "BUILD-WORKING.svg",        # build en cours
    "failed":  "BUILD-FAILED.svg",         # dernier build en échec
}
_mascot_renderers: dict[str, QSvgRenderer] = {}


def mascot_renderer(state: str) -> QSvgRenderer | None:
    """Renderer SVG de la mascotte pour `state`, ou None si le fichier est
    absent/vide (cf. BUILD-WAIT-SUCCESS.svg, pas encore dessiné) — l'appelant
    se contente alors de ne rien peindre plutôt que de planter."""
    filename = _MASCOT_FILES.get(state)
    if filename is None:
        return None
    renderer = _mascot_renderers.get(state)
    if renderer is None:
        path = _MASCOT_DIR / filename
        if not path.exists():
            return None
        renderer = QSvgRenderer(str(path))
        _mascot_renderers[state] = renderer
    return renderer if renderer.isValid() else None


# Un emplacement `fichier.lua:ligne` dans une ligne de journal. Le codegen émet
# le nom du fichier tel quel (`Titre.lua:2`) ou entre parenthèses pour un prefab/
# une caméra (`prefab Ball (Ball.lua):3`) — le `\)?` couvre la parenthèse
# fermante avant le `:`. La ligne peut manquer (faute lexicale sans jeton) :
# c'est alors une simple mention sans saut, non capturée ici.
_LUA_LOCATION = re.compile(r"([\w\-.]+\.lua)\)?:(\d+)")


def parse_build_location(text: str):
    """(nom_de_fichier, ligne) du PREMIER `fichier.lua:ligne` d'une ligne de
    journal, ou None. Fonction pure — c'est elle que teste la couche UI, pas le
    widget."""
    m = _LUA_LOCATION.search(text)
    if not m:
        return None
    return m.group(1), int(m.group(2))


class BuildConsole(QPlainTextEdit):
    """La console du journal de build, rendue cliquable : une ligne qui cite un
    `fichier.lua:ligne` s'ouvre au bon endroit d'un clic (le contenu des
    messages porte déjà la position — il ne manquait que le lien).

    Le clic est traité À LA LIGNE, pas au jeton : un journal se lit vite, et
    exiger de viser les quelques caractères du nom de fichier gênerait plus que
    ça n'aiderait. Le curable main apparaît au survol d'une ligne qui a une
    cible, pour que le lien se voie."""

    location_activated = pyqtSignal(str, int)   # (nom_de_fichier, ligne)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMouseTracking(True)   # pour changer le curseur au survol

    def _location_at(self, pos):
        cursor = self.cursorForPosition(pos)
        return parse_build_location(cursor.block().text())

    def mouseMoveEvent(self, e):
        over = self._location_at(e.pos()) is not None
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            loc = self._location_at(e.pos())
            if loc:
                self.location_activated.emit(loc[0], loc[1])
                e.accept()
                return
        super().mousePressEvent(e)


class DiagnosticsView(QWidget):
    """La liste des problèmes du validateur, séparée du bruit du journal :
    chaque ligne cliquable saute à sa source. Le validateur sait déjà tout
    (`core.validator`) ; il ne manquait qu'un endroit où le lire calmement.

    Deux formes de saut, sans enrichir le modèle : un message qui cite un
    `fichier.lua:ligne` ouvre le script (comme la console), un message attaché à
    un acteur de la scène active le sélectionne. Les autres (fond, palette,
    police, global) s'affichent sans cible — la navigation viendra quand le
    modèle portera une, cf. TodoTechnique."""

    refresh_requested = pyqtSignal()
    location_activated = pyqtSignal(str, int)   # fichier.lua, ligne (comme la console)
    actor_activated = pyqtSignal(str, str)      # (scène, acteur) ; scène "" = la scène active
    element_activated = pyqtSignal(str, str)    # mise en page, nom d'élément d'UI

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar = QFrame()
        bar.setFixedHeight(26)
        bar.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 0, 8, 0)
        self._btn_refresh = QPushButton(label('build.refresh'))
        self._btn_refresh.setFont(QFont(T.UI, T.SM))
        self._btn_refresh.setFixedHeight(20)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.setToolTip(tooltip(
            title=label('build.refresh_title'), body=label('build.refresh_tip')))
        self._btn_refresh.clicked.connect(lambda: self.refresh_requested.emit())
        h.addWidget(self._btn_refresh)
        self._summary = QLabel("—")
        self._summary.setFont(QFont(T.UI, T.SM))
        self._summary.setStyleSheet(f"color:{C.TEXT_MUTED};")
        h.addWidget(self._summary)
        h.addStretch()
        v.addWidget(bar)

        self._list = QListWidget()
        self._list.setFont(QFont(T.UI, T.SM))
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_DEEP};border:none;padding:2px;}}"
            f"QListWidget::item{{padding:3px 6px;}}"
            f"QListWidget::item:hover{{background:{C.BG_HOVER};}}"
        )
        self._list.itemClicked.connect(self._on_row)
        v.addWidget(self._list, 1)

        self._msgs: list = []   # ValidationMessage, dans l'ordre affiché

    def set_diagnostics(self, warnings: list, errors: list):
        """Peuple la liste — erreurs d'abord (ce qui bloque le build), puis
        avertissements."""
        self._list.clear()
        self._msgs = list(errors) + list(warnings)
        for m in self._msgs:
            it = QListWidgetItem(str(m))
            it.setForeground(QColor(C.ACCENT_RED if m.level == "error" else C.ACCENT_YLW))
            self._list.addItem(it)
        if not self._msgs:
            self._summary.setText(label('build.no_problems'))
        else:
            self._summary.setText(
                label('build.counts', value=len(warnings), value_2=len(errors)))

    def _on_row(self, item):
        i = self._list.row(item)
        if not (0 <= i < len(self._msgs)):
            return
        m = self._msgs[i]
        # La cible structurée du message d'abord (une zone d'UI aujourd'hui) ;
        # sinon l'heuristique — un `fichier.lua:ligne` dans le texte, puis un
        # nom d'acteur. `getattr` en canard : la vue n'importe pas le validateur.
        target = getattr(m, "target", None)
        if target is not None and target.kind == "ui_element":
            self.element_activated.emit(target.layout, target.name)
            return
        # Le fichier et la ligne du diagnostic d'abord (ils sont des champs) ; le texte
        # n'est lu que pour un message du validateur qui cite encore `fichier.lua:ligne`.
        if getattr(m, "file", "").endswith(".lua") and getattr(m, "line", 0):
            self.location_activated.emit(m.file, m.line)
            return
        loc = parse_build_location(m.message)
        if loc:
            self.location_activated.emit(loc[0], loc[1])
        elif m.actor or getattr(m, "scene", ""):
            self.actor_activated.emit(getattr(m, "scene", ""), m.actor)


class AnimatedBuildButton(QToolButton):
    """Bouton toolbar Build & Run : la mascotte de l'éditeur, plaquée sur une
    pilule colorée qui se transforme en jauge pendant le build, pilotée par
    QStateMachine.

    États (mascotte + couleur de la pilule) :
      idle     — mascotte au repos, pilule mauve, libellé « Run ».
      building — mascotte affairée, pilule jaune qui se remplit ; le
                 remplissage suit la progression réelle via `set_progress()`.
      done     — succès : retour direct à idle après un court délai. Échec :
                 mascotte assommée et pilule rouge « XXX », qui reste affichée
                 jusqu'à ce qu'un nouveau build soit lancé (pas de retour
                 automatique — un échec ne doit pas disparaître tout seul).
    """

    build_started = pyqtSignal()
    build_finished = pyqtSignal(bool)
    _settle = pyqtSignal()

    # La mascotte occupe la partie gauche et empiète sur la pilule (comme la
    # maquette) : la pilule commence avant la fin de sa boîte.
    _WIDTH, _HEIGHT = 96, 64
    # ── Réglages de coupe de la mascotte ────────────────────────────
    # Ce que peint _mascot_rect() est toujours plus grand que le bouton :
    # SCALE agrandit le dessin, X/Y_SHIFT le déplacent — le bouton (largeur
    # fixe _WIDTH/_HEIGHT) agit comme un cadre qui rogne le reste. Ajuster
    # ces 4 constantes suffit à recadrer la mascotte sans toucher au code.
    _MASCOT_SCALE = .82   # 1.0 = hauteur de la mascotte == hauteur du bouton
    _MASCOT_BOX_W = 48     # plafond de largeur rendue pour la mascotte
    _MASCOT_X_SHIFT = 0    # décale le dessin horizontalement (+ = vers la droite)
    # Décale le DESSIN de la mascotte vers le haut (valeur négative) sans
    # toucher à la pilule : la tête sort du cadre en haut, et c'est un point
    # plus bas de l'illustration (ventre plutôt que buste) qui se retrouve
    # au niveau de la pilule — donc la pilule paraît plus basse sur l'oiseau.
    _MASCOT_Y_SHIFT = -10
    _PILL_X = 15
    _PILL_MARGIN_R = 3   # même marge que _PILL_X côté droit — sinon le contour
                          # touche le bord du bouton et se retrouve à moitié rogné
    _PILL_H = 27   # réduite avec l'icône (même rapport) — sinon la pilule
                   # paraît trop grande par rapport à une mascotte plus petite
    _PILL_RADIUS = 4   # coins arrondis d'une barre carrée, pas une pilule ovale

    _PURPLE = "#aa50b4"   # mauve de la mascotte (crête/bec) — couleur de repos
    _SETTLE_OK_MS = 700   # retour à idle après un succès

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self._fill = 0.0
        self._success = True
        self._bar_mode = False

        self._progress_anim = QPropertyAnimation(self, b"fill", self)
        self._progress_anim.setDuration(220)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._settle)

        self.build_finished.connect(lambda ok: setattr(self, "_success", ok))

        self._machine = QStateMachine(self)
        st_idle = QState()
        st_building = QState()
        st_done = QState()

        st_idle.addTransition(self.build_started, st_building)
        st_building.addTransition(self.build_finished, st_done)
        st_done.addTransition(self._settle, st_idle)
        # Retenter pendant un échec affiché relance directement la jauge —
        # sans ça, "done" ignore build_started (transition propre à st_idle)
        # et le clic ne fait rien voir tant que le timer n'a pas expiré.
        st_done.addTransition(self.build_started, st_building)

        st_idle.entered.connect(self._enter_idle)
        st_building.entered.connect(self._enter_building)
        st_done.entered.connect(self._enter_done)

        for st in (st_idle, st_building, st_done):
            self._machine.addState(st)
        self._machine.setInitialState(st_idle)
        self._machine.start()

    # ── transitions d'état ───────────────────────────────────────
    def _enter_idle(self):
        self._bar_mode = False
        self._fill = 0.0
        self.update()

    def _enter_building(self):
        self._success = True
        self._bar_mode = True
        self._fill = 0.0
        self.update()

    def _enter_done(self):
        # Un succès efface l'écran de fin tout seul, vite. Un échec reste
        # affiché tant que l'utilisateur ne relance pas un build (transition
        # st_done → st_building ci-dessus) : pas de retour "Run" tout seul,
        # ce qui laisserait croire que l'erreur est réglée sans action.
        if self._success:
            self._settle_timer.start(self._SETTLE_OK_MS)
        self.update()

    def set_progress(self, fraction: float):
        """Avance la jauge vers `fraction` (0..1) — reflète l'état réel du build."""
        fraction = max(0.0, min(1.0, fraction))
        self._progress_anim.stop()
        self._progress_anim.setStartValue(self._fill)
        self._progress_anim.setEndValue(fraction)
        self._progress_anim.start()

    # ── propriété animable ──────────────────────────────────────
    def _get_fill(self): return self._fill
    def _set_fill(self, v):
        self._fill = v
        self.update()
    fill = pyqtProperty(float, _get_fill, _set_fill)

    def _mascot_state(self) -> str:
        if not self._bar_mode:
            return "idle"
        return "working" if self._success else "failed"

    # ── peinture ─────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        pill_x, pill_w = self._PILL_X, self.width() - self._PILL_X - self._PILL_MARGIN_R
        pill_y = (h - self._PILL_H) // 2

        # Géométrie de la mascotte calculée UNE FOIS, réutilisée par
        # _paint_mascot() tout à la fin (par-dessus la pilule).
        icon_rect = self._mascot_rect(h)
        text_rect = QRectF(pill_x, pill_y, pill_w, self._PILL_H)
        text_align = Qt.AlignmentFlag.AlignCenter

        r = self._PILL_RADIUS
        if not self._bar_mode:
            pill_color = QColor(self._PURPLE)
            if not self.isEnabled():
                pill_color = QColor(C.BTN_PRIMARY_DISABLED)
            elif self.underMouse():
                pill_color = pill_color.lighter(112)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pill_color)
            p.drawRoundedRect(pill_x, pill_y, pill_w, self._PILL_H, r, r)

            p.setPen(QColor("#000000") if self.isEnabled() else QColor(C.TEXT_MUTED))
            p.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
            p.drawText(text_rect, text_align, label("common.run"))
        elif not self._success:
            # échec figé : pilule pleine rouge, pas de jauge à faire lire.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.ACCENT_RED))
            p.drawRoundedRect(pill_x, pill_y, pill_w, self._PILL_H, r, r)
            p.setPen(QColor("#000000"))
            p.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
            p.drawText(text_rect, text_align, label("build.failed_mark"))
        else:
            # en cours : la pilule devient la jauge, remplissage réel du build.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.BG_INPUT))
            p.drawRoundedRect(pill_x, pill_y, pill_w, self._PILL_H, r, r)
            fw = round(pill_w * self._fill)
            if fw > 0:
                p.save()
                p.setBrush(QColor(C.ACCENT_YLW))
                p.setClipPath(self._rounded_path(pill_x, pill_y, pill_w, self._PILL_H, r))
                p.drawRect(pill_x, pill_y, fw, self._PILL_H)
                p.restore()   # sans ça le clip reste actif et masque la mascotte

        # Contour noir, cohérent avec le trait de la mascotte — par-dessus le
        # remplissage, quel que soit l'état.
        p.setPen(QPen(QColor("#000000"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, self._PILL_H), r, r)

        self._paint_mascot(p, icon_rect)
        p.end()

    def _mascot_rect(self, h: int) -> QRectF | None:
        """Boîte de la mascotte pour l'état courant, ancrée en bas-gauche du
        bouton — None si aucun dessin n'est disponible pour cet état."""
        renderer = mascot_renderer(self._mascot_state())
        if renderer is None:
            return None
        vb = renderer.viewBox()
        icon_h = float(h) * self._MASCOT_SCALE
        icon_w = min(icon_h * (vb.width() / vb.height()), self._MASCOT_BOX_W)
        x = self._MASCOT_X_SHIFT
        y = h - icon_h + self._MASCOT_Y_SHIFT
        return QRectF(x, y, icon_w, icon_h)

    def _paint_mascot(self, p: QPainter, icon_rect: "QRectF | None"):
        if icon_rect is None:
            return
        renderer = mascot_renderer(self._mascot_state())
        renderer.render(p, icon_rect)

    @staticmethod
    def _rounded_path(x, y, w, h, r):
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), r, r)
        return path

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class BuildPanel(QWidget):
    # Relais du même signal du bandeau ROM — window.py est seul à connaître
    # le projet, ce panneau n'en garde jamais de référence.
    cartridge_mib_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(28)
        header.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 8, 0)
        lbl = QLabel(label('build.build_debug'))
        lbl.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        lbl.setStyleSheet(f"color:{C.TEXT_NORM};")
        hl.addWidget(lbl)
        hl.addStretch()
        btn_clear = QPushButton(label('build.clear'))
        btn_clear.setFont(QFont(T.UI, T.SM))
        btn_clear.setFixedHeight(20)
        btn_clear.setToolTip(tooltip(title=label('build.clear_title')))
        btn_clear.clicked.connect(lambda: self.console.clear())
        hl.addWidget(btn_clear)
        layout.addWidget(header)

        self.console = BuildConsole()
        self.console.setFont(QFont(T.MONO, T.SM))
        self.console.setStyleSheet(
            f"background:{C.BG_DEEP}; color:{C.CONSOLE_TEXT}; border:none; padding:4px;"
        )
        # Plafond haut : un dump gcc verbeux ne doit pas pousser la VRAIE cause
        # (souvent la première erreur) hors du tampon.
        self.console.setMaximumBlockCount(5000)

        # Console (le journal) et Diagnostics (la liste du validateur) partagent
        # l'emplacement : deux onglets, le budget ROM reste dessous.
        self.diagnostics = DiagnosticsView()
        self._build_diagnostics: list = []   # ceux du build en cours (cf. log_diagnostic)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setStyleSheet(
            f"QTabBar::tab{{background:{C.BG_RAISED};color:{C.TEXT_MUTED};"
            f"padding:3px 10px;border:none;font-family:{T.UI_STACK};font-size:{T.SM}px;}}"
            f"QTabBar::tab:selected{{color:{C.TEXT_NORM};border-bottom:2px solid {C.ACCENT};}}"
            f"QTabWidget::pane{{border:none;}}"
        )
        tabs.addTab(self.console, label('build.console'))
        tabs.addTab(self.diagnostics, label('build.diagnostics'))
        layout.addWidget(tabs, 1)

        # Séparé verticalement du journal, et FERRÉ en bas : contrairement au
        # texte de la console (qui défile et se vide au Clear), ce bandeau
        # garde le dernier poids mesuré en permanence visible.
        self.rom_bar = RomBudgetBar()
        self.rom_bar.cartridge_mib_changed.connect(self.cartridge_mib_changed)
        layout.addWidget(self.rom_bar, 0)

        self.btn_build = QPushButton(label('build.build_run'))
        self.btn_build.setToolTip(tooltip(
            title=label('win.build_run_title'), shortcut=get_keybindings().resolve("game.build"), body=label('win.build_run_tip')))
        self.btn_build.setEnabled(False)
        self.btn_build.setVisible(False)

    def log(self, text, color=C.CONSOLE_TEXT):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(("\n" if self.console.toPlainText() else "") + text, fmt)
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def log_error(self, t): self.log(t, C.ACCENT_RED)
    def log_info(self, t):  self.log(t, C.ACCENT_COOL)

    def start_build_diagnostics(self):
        """Un nouveau build : la liste des diagnostics repart de zéro."""
        self._build_diagnostics = []

    def log_diagnostic(self, diagnostic):
        """Une ligne de console colorée selon la gravité DU DIAGNOSTIC (et non du canal qui
        l'a porté), gardée pour l'onglet Diagnostics à la fin du build."""
        self.log(diagnostic.console_line(),
                 C.ACCENT_RED if diagnostic.level == "error" else C.ACCENT_YLW)
        self._build_diagnostics.append(diagnostic)

    def show_build_diagnostics(self):
        """Fin de build : l'onglet Diagnostics montre ce que le build a dit, y compris ce que
        le checker, le codegen et les outils ont reproché — pas seulement le validateur."""
        warnings = [d for d in self._build_diagnostics if d.level == "warning"]
        errors = [d for d in self._build_diagnostics if d.level == "error"]
        self.diagnostics.set_diagnostics(warnings, errors)

    def reveal(self):
        """Rouvre le panneau s'il a été replié à zéro dans son QSplitter
        (poignée tirée jusqu'au bord). Sans effet s'il est déjà visible."""
        splitter = self.parentWidget()
        if not isinstance(splitter, QSplitter):
            return
        index = splitter.indexOf(self)
        sizes = splitter.sizes()
        if sizes[index] > 0:
            return
        wanted = max(self.minimumHeight(), 160)
        sizes[index] = wanted
        # Le volume est pris sur le widget le plus grand (l'éditeur/canvas).
        donor = max(range(len(sizes)), key=lambda i: sizes[i])
        sizes[donor] = max(sizes[donor] - wanted, 0)
        splitter.setSizes(sizes)

    def set_building(self, b):
        self.btn_build.setEnabled(not b)
        self.btn_build.setText(label('build.building') if b else label('build.build_run'))

    def update_rom_report(self, report):
        """Reçoit le `RomReport` du dernier build (window.py, événement
        `rom_report`) et le passe au bandeau — ce panneau ne mesure rien."""
        self.rom_bar.update_report(report)

    def set_cartridge_mib(self, mib: int):
        """Resynchronise le bandeau ROM sur le réglage RÉEL du projet — au
        chargement, et après un changement fait ici ou dans l'inspecteur."""
        self.rom_bar.set_cartridge_mib(mib)


class ToolchainBar(QFrame):
    configure_requested = pyqtSignal()

    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self.toolchain = toolchain
        self.setFixedHeight(28)
        self.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:{C.SPLITTER_WIDTH}px solid {C.SPLITTER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(12)
        font = QFont(T.UI, T.SM)

        lbl = QLabel(label('build.toolchain'))
        lbl.setFont(font); lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        layout.addWidget(lbl)

        self._dkp  = QLabel(); self._dkp.setFont(font)
        self._mgba = QLabel(); self._mgba.setFont(font)
        layout.addWidget(self._dkp)
        layout.addWidget(self._mgba)
        layout.addStretch()

        btn = QPushButton(label('build.configure'))
        btn.setFixedHeight(20); btn.setFont(font)
        btn.setToolTip(tooltip(
            title=label('build.configure_title'), body=label('build.configure_tip')))
        btn.setStyleSheet(
            f"background:{C.BORDER}; color:{C.TEXT_NORM}; border:1px solid {C.TEXT_MUTED};"
            "border-radius:3px; padding:0 6px;"
        )
        btn.clicked.connect(self.configure_requested)
        layout.addWidget(btn)
        self.refresh()

    def refresh(self):
        ok = self.toolchain.devkitpro_ok
        self._dkp.setText("devkitPro ✓" if ok else "devkitPro ✗")
        self._dkp.setStyleSheet(f"color:{C.TEXT_NORM};" if ok else f"color:{C.ACCENT_RED};")
        ok2 = self.toolchain.mgba_ok
        self._mgba.setText("mgba ✓" if ok2 else "mgba ✗")
        self._mgba.setStyleSheet(f"color:{C.TEXT_NORM};" if ok2 else f"color:{C.ACCENT_RED};")


## L'ancien ToolchainDialog (OK/Cancel, devkitPro + mgba) vit maintenant comme
## la catégorie « Toolchains » de ui/common/settings_dialog.py — un seul
## endroit qui configure le logiciel, plutôt qu'un dialogue par réglage.
