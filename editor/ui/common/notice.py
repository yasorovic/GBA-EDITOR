"""
ui/common/notice.py — le contenu informatif de l'éditeur : trois niveaux,
quatre tons, et pas une phrase écrite dans le code d'interface.

    from ui.common.notice import note, notice, tip, text

    self._cost = note(card.body_layout, "ui.text.footprint_bg")
    ...
    self._cost.show_text(w=tw, h=th, n=tw * th)      # affiche
    self._cost.clear()                               # se tait

Le NIVEAU dit à quel point le message s'impose ; c'est l'appelant qui le
choisit, parce que c'est une question de place dans l'écran :

    note(layout, clé="")          1 — une ligne sans cadre, en sous-brillance
    notice(clé, ancre, layout)    2 — la GRAVITÉ tranche la forme (voir plus bas)
    tip(clé, layout)              3 — un encadré (icône du TON), coupable par
                                     réglage ET par une croix au coup par coup

Le TON dit ce que le message annonce ; il est écrit dans le catalogue, parce
que c'est une propriété du message et non du lieu où il s'affiche :

    info      constat — une empreinte, un compte, une provenance
    accent    complément qui renvoie ailleurs (autre écran, notion de l'éditeur)
    build     ça compile, mais le build va écarter ou rogner ce qui est là
    render    ça s'émet, mais la console n'affichera pas ce qui est authoré

`build` et `render` sont tous deux JAUNES : une seule couleur d'alerte, et
c'est la forme de l'icône qui les distingue — la même règle que les familles
d'icônes. Le rouge n'entre pas dans ce gabarit : il reste aux erreurs
bloquantes du validateur, et un inspecteur qui parle rouge banalise la seule
couleur qui devait arrêter quelqu'un.

**Le niveau 2 n'a qu'un appel.** Un message de niveau 2 est toujours À PROPOS
de quelque chose (l'ancre) et vit toujours QUELQUE PART (la carte) ; la forme
en découle : `info`/`accent` deviennent une bulle au survol de l'ancre,
`build`/`render` un encadré permanent dans la carte. S'il n'a pas d'ancre,
c'est qu'il parle du panneau entier — donc ce n'est pas un niveau 2.

**Le niveau 3 est le seul endroit où l'éditeur a le droit d'EXPLIQUER** (un
concept, une optimisation, une règle). Les niveaux 1 et 2 disent ce qui est
actionnable et probablement non voulu, ils ne commentent pas le matériel.
C'est l'interrupteur — `core/interface_preferences.py`, un réglage
d'APPLICATION et non de projet — qui rend le niveau 3 acceptable : il ne peut
pas noyer les deux autres puisqu'il est optionnel. Chaque astuce porte en plus
sa propre croix (`NoticeBox._dismiss`) : fermée au coup par coup, en session,
sans toucher au réglage qui gouverne toutes les autres.

── Le catalogue ──────────────────────────────────────────────────

    notices/notices.json        le MAÎTRE — clé, ton, texte SOURCE
    notices/notices_fr.json     un SIDE   — la traduction seule, jointe par clé

Même grammaire que la table de textes du JEU (core/project_langs.py), pour la
même raison : le maître possède la structure, le side ne porte que la
traduction, et **une entrée absente vaut la SOURCE, jamais une chaîne vide**.
Une seule différence : ici la clé EST la jointure, là où le jeu utilise un id
opaque. La clé est écrite dans du Python versionné — un id opaque y serait
illisible, et la renommer est un changement de code, donc les sides suivent
dans le même commit.

Le Python passe des VALEURS, jamais des morceaux de phrase : c'est la
concaténation qui rend un message intraduisible, l'ordre des mots n'étant pas
le même d'une langue à l'autre. Le pluriel se déclare (`one`/`other`, choisi
par l'argument `n`) au lieu de s'écrire `"s" if n > 1`.

`tools/check_architecture.py` vérifie les deux sens : toute clé citée existe,
toute entrée est citée. Sans lui l'extraction se déferait seule — une clé mal
tapée donne un message vide, et un message vide ne se plaint jamais.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import QSize, Qt

from ui.common import icons
from ui.common.theme import C, S, T, QSS, ui_font
from ui.common.catalog import Catalog
from ui.common import catalog


NOTICES_DIR = Path(__file__).parent / "notices"

# Ton → (couleur, nom d'icône). Le nom vide = pas d'icône : une ligne de
# niveau 1 porte son ton par sa seule couleur, comme aujourd'hui.
TONES: dict[str, tuple[str, str]] = {
    "info":   (C.TEXT_MUTED, ""),
    "accent": (C.ACCENT,     "info"),
    "build":  (C.ACCENT_YLW, "warning"),
    "render": (C.ACCENT_YLW, "eye"),
}


# ── Le catalogue ──────────────────────────────────────────────────
# La mécanique (maître + side, repli, pluriel, format, set_language) vit dans
# ui/common/catalog.py, partagée avec les libellés (ui/common/labels.py). Ici ne
# reste que ce qui est PROPRE aux notices : le ton, et le rich text des bulles.

_CAT = Catalog("notices", NOTICES_DIR)


def set_language(code: str):
    """Bascule la langue de TOUS les catalogues d'interface (notices ET
    libellés) — un changement de langue est global. Sous ce nom parce que c'est
    l'API que la suite de la v0.11 branche sur le réglage de langue ; le cœur
    partagé (`catalog.set_language`) fait le travail."""
    catalog.set_language(code)


def text(key: str, **args) -> str:
    """Le message résolu, prêt à afficher — traduction, pluriel et valeurs.

    Public parce qu'un message COMPOSÉ injecte un autre message : chaque
    morceau reste une phrase entière pour le traducteur (`text("…where_obj",
    n=tiles)` passé en argument de l'entrée qui l'accueille)."""
    return _CAT.text(key, **args)


def tone_of(key: str) -> str:
    """Le ton déclaré par le catalogue, `info` s'il ne dit rien."""
    t = str(_CAT.raw(key).get("tone", "info"))
    return t if t in TONES else "info"


def _escape(s: str) -> str:
    """Texte brut → rich text Qt, retours à la ligne compris."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace("\n", "<br>"))


# ── Niveau 3 — l'interrupteur ─────────────────────────────────────

def tips_enabled() -> bool:
    """Réglage d'APPLICATION (`core/interface_preferences.py`), pas de projet :
    couper les astuces ne doit pas les couper pour l'équipe entière par le
    project.json versionné, ni entrer dans l'historique d'annulation."""
    from core.interface_preferences import tips_shown
    return tips_shown()


def refresh_tips():
    """Applique l'interrupteur aux astuces DÉJÀ construites.

    Pas de registre d'instances : les astuces vivantes sont exactement les
    widgets vivants, et `allWidgets()` les connaît déjà. Dupliquer cette liste
    dans un module serait un second état à tenir d'accord, pour une action que
    l'utilisateur fait deux fois par projet."""
    for w in QApplication.allWidgets():
        if isinstance(w, NoticeBox) and w.is_tip:
            w.refresh()


# ── Niveau 1 — la ligne ───────────────────────────────────────────

class NoteLine(QLabel):
    """Une ligne sans cadre, sous un `W.section()`. Se retire du layout quand
    elle n'a rien à dire, au lieu d'y laisser un blanc.

    **Sa clé peut changer à chaque rafraîchissement**, et c'est la raison
    d'être du niveau 1 : une ligne d'inspecteur dit tantôt une empreinte,
    tantôt pourquoi elle est vide. La COULEUR suit la clé sans que l'appelant
    ait son mot à dire — c'est exactement le jugement à la main qui posait du
    jaune sur des messages de gravité opposée."""

    def __init__(self, key: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.setFont(ui_font(T.SM))
        self.setWordWrap(True)
        self.setVisible(False)

    def show_text(self, key: str | None = None, **args):
        self.key = key or self.key
        body = text(self.key, **args) if self.key else ""
        self.setStyleSheet(f"color:{TONES[tone_of(self.key)][0]}; "
                           f"background:transparent; border:none;")
        self.setText(body)
        self.setVisible(bool(body))

    def clear(self):
        self.setText("")
        self.setVisible(False)


def note(layout: QVBoxLayout, key: str = "") -> NoteLine:
    """Niveau 1 — information secondaire, posée sous un séparateur.

    `key` est facultative : une ligne qui dit toujours la même chose la déclare
    ici, une ligne qui alterne la passe à chaque `show_text()`."""
    lbl = NoteLine(key)
    layout.addWidget(lbl)
    return lbl


# ── Niveaux 2 et 3 — l'encadré ────────────────────────────────────

class NoticeBox(QFrame):
    """L'encadré : icône du ton + texte. Sert au niveau 2 quand la gravité
    l'impose (`build`/`render`), et à TOUT le niveau 3 — une astuce est
    toujours encadrée, c'est ce qui la rend reconnaissable d'un coup d'œil, et
    donc ignorable par qui n'en veut pas.

    **L'icône vient du TON, jamais du niveau** : une astuce `build`/`render`
    montre le même avertissement (⚠/👁) qu'un niveau 2 — c'en est un, en plus
    pédagogique — et une astuce `info`/`accent` n'en réclame aucune de plus
    qu'un niveau 2 du même ton. Pas d'ampoule à part : une troisième forme
    d'icône pour ce qui reste par ailleurs le même vocabulaire."""

    def __init__(self, key: str, is_tip: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.is_tip = is_tip
        self._dismissed = False
        color, icon_name = TONES[tone_of(key)]
        self.setObjectName("noticeBox")
        self.setStyleSheet(QSS.notice_box(color))

        row = QHBoxLayout(self)
        row.setContentsMargins(S.MD, S.MD, S.MD, S.MD)
        row.setSpacing(S.MD)

        if icon_name:
            ico = QLabel()
            ico.setPixmap(icons.get(icon_name, color).pixmap(QSize(14, 14)))
            ico.setAlignment(Qt.AlignmentFlag.AlignTop)
            ico.setFixedWidth(14)
            row.addWidget(ico)

        # SANS cadre, la couleur est portée par le texte ; AVEC cadre, par le
        # cadre et l'icône. Un encadré dont le corps reprendrait la teinte du
        # ton serait illisible dans les deux cas qui comptent : un `info` en
        # gris très discret (le ton est déjà dit par le cadre), et un risque en
        # jaune sur trois lignes, qu'on finit par ne plus lire.
        self._body = QLabel()
        self._body.setFont(ui_font(T.SM))
        self._body.setWordWrap(True)
        self._body.setStyleSheet(
            f"color:{C.TEXT_NORM}; background:transparent; border:none;")
        row.addWidget(self._body, 1)

        # Une astuce se ferme au coup par coup — l'interrupteur d'application
        # (Settings ▸ Interface) reste le seul geste qui les coupe TOUTES.
        # Un niveau 2 ne porte pas cette croix : il rend compte d'un état
        # (le build va rogner ceci), le fermer laisserait croire que l'état a
        # changé alors que seul l'affichage s'est tu.
        if is_tip:
            close = QToolButton()
            close.setIcon(icons.get("clear", C.TEXT_MUTED))
            close.setIconSize(QSize(11, 11))
            close.setFixedSize(16, 16)
            close.setAutoRaise(True)
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.setToolTip(tooltip(title=label('noticeui.dismiss_title')))
            close.setStyleSheet(
                "QToolButton{border:none; background:transparent;}"
                f"QToolButton:hover{{background:{C.BG_HOVER};border-radius:3px;}}")
            close.clicked.connect(self._dismiss)
            row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)

        self.setVisible(False)

    def show_text(self, **args):
        self._body.setText(text(self.key, **args))
        self.refresh()

    def clear(self):
        self._body.setText("")
        self.refresh()

    def _dismiss(self):
        self._dismissed = True
        self.refresh()

    def refresh(self):
        """Visible si elle a quelque chose à dire, si le projet en veut, et si
        elle n'a pas été fermée. `refresh_tips()` rappelle cette méthode sans
        connaître les deux premiers termes, d'où la relecture plutôt qu'un
        booléen passé."""
        self.setVisible(bool(self._body.text())
                        and not self._dismissed
                        and (tips_enabled() if self.is_tip else True))


class HoverNotice:
    """La forme discrète du niveau 2 : le message vit dans l'infobulle de son
    ancre. Pas un widget — il n'occupe aucune place, c'est tout son intérêt."""

    def __init__(self, key: str, anchor: QWidget):
        self.key = key
        self._anchor = anchor
        self._color = TONES[tone_of(key)][0]
        self.show_text()

    def show_text(self, **args):
        body = text(self.key, **args)
        # Rich text : sans balise, Qt rendrait les retours à la ligne comme des
        # espaces. La largeur est imposée parce qu'une infobulle en rich text
        # ne se replie pas toute seule, contrairement au texte brut.
        html = _escape(body)
        # `code` — l'expression Lua que ce champ MIROITE. Elle vit dans le
        # maître et jamais dans un side : une expression d'API ne se traduit
        # pas, la traduire casserait le script qu'elle donne à recopier.
        expr = str(_CAT.raw(self.key).get("code", ""))
        if expr:
            html = (f"<b style='color:{C.ACCENT}'>{_escape(expr)}</b>"
                    f"<br><br>{html}")
        self._anchor.setToolTip(
            f'<div style="color:{self._color}; width:280px;">{html}</div>'
            if body else "")

    def clear(self):
        self._anchor.setToolTip("")


def notice(key: str, anchor: QWidget, layout: QVBoxLayout):
    """Niveau 2 — la gravité tranche la forme.

    `info`/`accent` → infobulle sur `anchor` (on va la chercher).
    `build`/`render` → encadré permanent dans `layout` (un risque ne se cache
    pas). L'appelant fournit les deux et ne choisit pas : c'est le ton du
    catalogue qui décide, sinon deux messages de même gravité finiraient sous
    deux formes selon l'humeur du jour."""
    if tone_of(key) in ("build", "render"):
        box = NoticeBox(key, is_tip=False)
        layout.addWidget(box)
        return box
    return HoverNotice(key, anchor)


def tip(key: str, layout: QVBoxLayout, **args) -> NoticeBox:
    """Niveau 3 — astuce, explication d'un concept, piste d'optimisation.
    Coupée en bloc par les réglages d'application (Settings ▸ Interface).

    S'affiche immédiatement, contrairement aux deux autres niveaux : une
    astuce explique une NOTION, elle ne rend pas compte d'un état — il n'y a
    donc rien à attendre pour savoir quoi dire."""
    box = NoticeBox(key, is_tip=True)
    layout.addWidget(box)
    box.show_text(**args)
    return box
