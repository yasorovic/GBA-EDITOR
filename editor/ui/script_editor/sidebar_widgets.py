"""ui/script_editor/sidebar_widgets.py — briques réutilisables de la sidebar (section, sous-section, bouton d'entrée)."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QSizePolicy
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, QSize

from ui.common.theme import C, T
from ui.common.labels import label
from .colors import _BG, _BG_HDR, _BG_HOVER, _BORDER, _TEXT_DIM, _TEXT_HI, _TEXT_NORM, _C_API, _C_REF, _C_SUB, _C_EVENT, _C_BEHAVIOR, _BG_SEL_REF

_BTN_BASE = (
    f"QPushButton{{color:{_TEXT_DIM};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_FILE = (
    f"QPushButton{{color:{_TEXT_DIM};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.MD}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_FILE_SEL = (
    f"QPushButton{{color:{_C_REF};background:{_BG_SEL_REF};border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.MD}px;}}"
    f"QPushButton:hover{{color:{_C_REF};background:{_BG_SEL_REF};}}"
)
_BTN_EVENT_DEFINED = (
    f"QPushButton{{color:{_C_EVENT};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;font-weight:bold;}}"
    f"QPushButton:hover{{background:{_BG_HOVER};}}"
)
_BTN_API = (
    f"QPushButton{{color:{_C_API};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_REF = (
    f"QPushButton{{color:{_C_REF};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_BEHAVIOR = (
    f"QPushButton{{color:{_C_BEHAVIOR};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)


from scripting.api import EVENT_REGISTRY as _EVENT_META


def _event_tooltip(name: str) -> str:
    meta = _EVENT_META.get(name, {})
    desc = meta.get("desc", "")
    params = meta.get("params", [])
    stub_sig = f"function {name}(" + ", ".join(p["name"] for p in params) + ")"

    lines = [
        f"<b style='font-family:Consolas,monospace;color:{_C_EVENT}'>{stub_sig}</b>",
        f"<p style='color:{_TEXT_NORM};margin:4px 0'>{desc}</p>",
    ]
    if params:
        lines.append("<table cellspacing='2' style='margin-top:4px'>")
        for p in params:
            lines.append(
                f"<tr>"
                f"<td style='font-family:Consolas,monospace;color:{_C_API}'>{p['name']}</td>"
                f"<td style='color:{_TEXT_DIM};padding:0 6px'>{p['type']}</td>"
                f"<td style='color:{_TEXT_DIM}'>{p['description']}</td>"
                f"</tr>"
            )
        lines.append("</table>")
    lines.append(f"<p style='color:{_C_SUB};margin-top:6px;font-size:9px'>{label('scrsb.doc_soon')}</p>")
    return "".join(lines)


def _group_label(text: str) -> QLabel:
    """Intertitre non cliquable À L'INTÉRIEUR d'une sous-section.

    Distinct de `_Section.sub_label` (qui coiffe une sous-section) : sert à
    séparer des paquets dans une liste déjà repliable — les dossiers de textes,
    par exemple — sans ajouter un troisième niveau de dépliage dans une colonne
    de 200 px."""
    lbl = QLabel(text)
    f = QFont(T.UI, T.XS)
    # Italique et non gras, indenté au-delà du header de sous-section : un
    # intertitre doit se lire comme une ANNOTATION, pas comme un contrôle. En
    # gras et aligné sur le header, un dossier de textes passait pour une
    # sous-section frère de « Textes » au lieu d'une subdivision.
    f.setItalic(True)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color:{_C_SUB};background:{_BG};padding:4px 0 1px 22px;")
    lbl.setFixedHeight(18)
    return lbl


class _Section(QWidget):
    """Section collapsible avec header cliquable."""

    def __init__(self, title: str, color: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._pre_filter_expanded: bool | None = None   # état d'avant la recherche
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(26)
        hdr.setStyleSheet(
            f"background:{_BG_HDR};border-top:1px solid {_BORDER};"
            f"border-bottom:1px solid {_BORDER};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)

        self._toggle = QPushButton()
        self._toggle.setStyleSheet(
            f"QPushButton{{color:{color};border:none;background:transparent;"
            f"font-family:{T.UI_STACK};font-size:{T.SM}pt;font-weight:bold;"
            f"text-align:left;padding:0 4px 0 4px;}}"
            f"QPushButton:hover{{background:{_BG_HOVER};}}"
        )
        self._toggle.setIconSize(QSize(T.MD, T.MD))
        self._toggle.setText(f"  {title}")
        self._toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._do_toggle)
        self._color = color
        self._title = title
        self._set_arrow("down")
        hl.addWidget(self._toggle)
        root.addWidget(hdr)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{_BG};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 2, 0, 4)
        self._body_layout.setSpacing(0)

        if not expanded:
            self._do_toggle()

    def _set_arrow(self, direction: str):
        """direction: "down" (dépliée) ou "right" (repliée) — même triangle
        vectoriel partagé que FinderSection/QTreeWidget (cf. icons.arrow_icon)."""
        from ui.common import icons
        self._toggle.setIcon(icons.arrow_icon(direction, self._color))

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._set_arrow("down" if self._expanded else "right")

    def set_title_and_color(self, title: str, color: str):
        """Change le titre et la couleur d'accent du header (ex: EVENTS ↔
        MODULE selon le contexte du script). Passe par le même chemin que
        __init__ pour que titre, couleur et flèche restent toujours cohérents
        — pas de poke direct sur `_toggle` depuis l'extérieur."""
        self._title = title
        self._color = color
        self._toggle.setStyleSheet(
            f"QPushButton{{color:{color};border:none;background:transparent;"
            f"font-family:{T.UI_STACK};font-size:{T.SM}pt;font-weight:bold;"
            f"text-align:left;padding:0 4px 0 4px;}}"
            f"QPushButton:hover{{background:{_BG_HOVER};}}"
        )
        self._toggle.setText(f"  {title}")
        self._set_arrow("down" if self._expanded else "right")

    def add_widget(self, w: QWidget):
        self._body_layout.addWidget(w)

    def clear_body(self):
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def sub_label(self, text: str) -> QLabel:
        """Sous-label statique (utilisé pour RÉFÉRENCES)."""
        lbl = QLabel(f"  {text}")
        lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        lbl.setStyleSheet(
            f"color:{_C_SUB};background:{_BG_HDR};"
            f"border-bottom:1px solid {_BORDER};padding:3px 0;"
        )
        lbl.setFixedHeight(18)
        self._body_layout.addWidget(lbl)
        return lbl

    def sub_section(self, text: str) -> "_SubSection":
        """Sous-section collapsible (utilisé pour les catégories API)."""
        ss = _SubSection(text)
        self._body_layout.addWidget(ss)
        return ss

    def apply_filter(self, query: str):
        """Filtre par nom : le titre de la section, celui d'une sous-section ou
        le libellé d'une entrée. Un titre qui correspond montre TOUT son
        contenu (« actor » rend la catégorie entière) ; sinon seules les
        entrées qui correspondent restent. Requête vide : tout revient, replié
        ou déplié comme avant la recherche."""
        if not query:
            if self._pre_filter_expanded is not None:
                self._set_expanded(self._pre_filter_expanded)
                self._pre_filter_expanded = None
            self.setVisible(True)
            for w in self._body_children():
                if isinstance(w, _SubSection):
                    w.apply_filter("", False)
                else:
                    w.setVisible(True)
            return
        if self._pre_filter_expanded is None:
            self._pre_filter_expanded = self._expanded
        section_hit = query in self._title.lower()
        any_hit = section_hit
        for w in self._body_children():
            if isinstance(w, _SubSection):
                hit = w.apply_filter(query, section_hit)
            elif isinstance(w, _EntryButton):
                hit = section_hit or query in w.search_text
                w.setVisible(hit)
            else:                       # intertitre : suit le titre seul
                hit = False
                w.setVisible(section_hit)
            any_hit = any_hit or hit
        self.setVisible(any_hit)
        if any_hit:
            self._set_expanded(True)

    def _body_children(self):
        return [self._body_layout.itemAt(i).widget()
                for i in range(self._body_layout.count())
                if self._body_layout.itemAt(i).widget()]

    def _set_expanded(self, expanded: bool):
        if self._expanded != expanded:
            self._do_toggle()


class _SubSection(QWidget):
    """Sous-section collapsible (catégories API, ou dossiers du file tree si icon_key donné)."""

    def __init__(self, title: str, expanded: bool = False, icon_key: str | None = None, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._pre_filter_expanded: bool | None = None   # état d'avant la recherche
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # En-tête cliquable en une pièce (arrow + icône + titre) — même
        # grammaire que FinderSection (widgets.py) : un conteneur qui porte le
        # survol/le clic, pas un QPushButton dont l'icône serait disputée
        # entre le dossier et la flèche.
        hdr = QWidget()
        hdr.setObjectName("subToggle")
        hdr.setFixedHeight(20)
        hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        hdr.setStyleSheet(
            f"QWidget#subToggle{{background:{_BG_HDR};}}"
            f"QWidget#subToggle:hover{{background:{_BG_HOVER};}}"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(4, 0, 4, 0)
        hl.setSpacing(4)

        self._arrow_lbl = QLabel()
        self._arrow_lbl.setFixedWidth(T.MD)
        self._arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(self._arrow_lbl)

        if icon_key:
            from ui.common.icons import get as _ico, COLOR_FOLDER
            icon_lbl = QLabel()
            icon_lbl.setPixmap(_ico(icon_key, COLOR_FOLDER).pixmap(QSize(13, 13)))
            hl.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color:{_C_SUB};background:transparent;"
            f"font-family:{T.UI_STACK};font-size:{T.SM}pt;font-weight:bold;"
        )
        hl.addWidget(title_lbl, 1)

        # Sans ça, survoler l'icône/le titre enverrait un Leave au conteneur :
        # survol clignotant (cf. FinderSection, même remarque).
        for lbl in (self._arrow_lbl, title_lbl):
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        hdr.mousePressEvent = lambda e: self._do_toggle()

        self._title = title
        self._set_arrow("down")
        root.addWidget(hdr)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{_BG};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)

        if not expanded:
            self._do_toggle()

    def _set_arrow(self, direction: str):
        """direction: "down" (dépliée) ou "right" (repliée) — même triangle
        vectoriel partagé que FinderSection/QTreeWidget (cf. icons.arrow_icon)."""
        from ui.common import icons
        icon = icons.arrow_icon(direction, _C_SUB)
        self._arrow_lbl.setPixmap(icon.pixmap(QSize(T.MD, T.MD)))

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._set_arrow("down" if self._expanded else "right")

    def add_widget(self, w: QWidget):
        self._body_layout.addWidget(w)

    def apply_filter(self, query: str, parent_hit: bool) -> bool:
        """Cf. `_Section.apply_filter`. Rend True si la sous-section reste visible."""
        children = [self._body_layout.itemAt(i).widget()
                    for i in range(self._body_layout.count())
                    if self._body_layout.itemAt(i).widget()]
        if not query:
            for w in children:
                w.setVisible(True)
            self.setVisible(True)
            if self._pre_filter_expanded is not None:
                self._set_expanded(self._pre_filter_expanded)
                self._pre_filter_expanded = None
            return True
        if self._pre_filter_expanded is None:
            self._pre_filter_expanded = self._expanded
        all_hit = parent_hit or query in self._title.lower()
        any_hit = all_hit
        for w in children:
            hit = all_hit or (isinstance(w, _EntryButton) and query in w.search_text)
            w.setVisible(hit)
            any_hit = any_hit or hit
        self.setVisible(any_hit)
        if any_hit:
            self._set_expanded(True)
        return any_hit

    def _set_expanded(self, expanded: bool):
        if self._expanded != expanded:
            self._do_toggle()


class _EntryButton(QPushButton):
    """Bouton d'entrée sidebar avec tooltip riche, icône optionnelle (ui/icons.py)."""

    def __init__(self, label: str, style: str, tooltip_html: str,
                 icon_key: str | None = None, icon_color: str | None = None, parent=None):
        super().__init__(label, parent)
        self.search_text = label.strip().lower()    # ce que la recherche compare
        self.setFont(QFont(T.CODE, T.MD))
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(style)
        self.setToolTip(tooltip_html)
        self._icon_key = icon_key
        if icon_key:
            self.setIconSize(QSize(15, 15))
            self.set_icon_color(icon_color or _TEXT_DIM)

    def set_icon_color(self, color: str):
        """Recolore l'icône — QSS ne peut pas teinter un QIcon, contrairement au texte."""
        if self._icon_key:
            from ui.common.icons import get as _ico
            self.setIcon(_ico(self._icon_key, color))

