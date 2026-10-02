"""
ui/text_editor/markup_toolbar.py — barre de balisage de l'atelier d'écriture.

Écrire `[wave]…[/wave]` à la main marche, mais demande de connaître le
catalogue par cœur et de ne pas se tromper de fermeture. Cette barre pose les
balises sur la SÉLECTION, comme n'importe quel éditeur BBCode.

Elle ne redit pas la grammaire : les boutons sont dérivés de
`core.text_markup.TAGS` — une balise ajoutée au catalogue apparaît ici sans
qu'on y touche (avec une icône de repli si personne ne lui en a choisi une).
Seule la PRÉSENTATION (icône, valeur pré-remplie) vit dans ce module.

Deux règles, qui suivent la nature de la balise :
  • de PORTÉE (`wave`, `shake`, `color`, `font`) → elle enveloppe la sélection, et
    re-cliquer sur une sélection déjà enveloppée la déshabille ;
  • PONCTUELLE (`speed`, `pause`, `icon`) → elle marque un instant, donc elle
    se pose DEVANT la sélection sans jamais la remplacer.

Quand la balise attend une valeur, la valeur insérée est laissée SÉLECTIONNÉE :
on la corrige en tapant, sans boîte de dialogue ni aller-retour à la souris.
Quand cette valeur désigne quelque chose que le projet connaît déjà (un glyphe
nommé de la police, un global ou une constante), le bouton propose la liste —
mieux vaut choisir que retaper un nom que l'inspecteur signalera ensuite.
"""
from __future__ import annotations

import re
from typing import Optional

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QToolButton
from PyQt6.QtGui import QTextCursor
from PyQt6.QtCore import Qt, QSize

from core.text_markup import TAGS, KIND_VALUE, VALUE_NONE
from ui.common import icons
from ui.common.theme import C
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.widgets import ScriptPickerPopup


# Présentation d'une balise : (icône, valeur pré-remplie). Les valeurs par
# défaut sont des points de départ PLAUSIBLES, pas des neutres : `[pause=0]` ou
# `[color=]` obligerait à taper avant de pouvoir juger du rendu.
_LOOK: dict[str, tuple[str, str]] = {
    "speed": ("mk_speed", "2"),
    "pause": ("mk_pause", "30"),
    "icon":  ("mk_icon",  "name"),
    "wave":  ("mk_wave",  ""),
    "shake": ("mk_shake", ""),
    "color": ("mk_color", "1"),
    "font":  ("mk_tag",   "name"),
}
_FALLBACK_ICON = "mk_tag"


class MarkupToolbar(QFrame):
    """Boutons de balisage agissant sur une surface d'édition.

    La surface historique est un ``QTextEdit``. L'atelier unifié expose le
    même petit contrat sans dépendre de Qt : ``source()``, ``selection()`` et
    ``replace_source(edits, selection)``. La barre garde donc ses règles de
    balisage et ses menus, quel que soit le rendu situé dessous.
    """

    def __init__(self, edit, parent=None):
        super().__init__(parent)
        self._edit = edit
        self._project = None
        self._font = None
        self.setFixedHeight(32)
        self.setStyleSheet(
            f"QFrame{{background:{C.BG_PANEL}; "
            f"border-top:1px solid {C.BORDER_DARK};}}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(3)

        for name, spec in TAGS.items():
            icon, default = _LOOK.get(name, (_FALLBACK_ICON, ""))
            syntax = (f"[{name}{'=…' if spec.value else ''}]"
                      + (f"…[/{name}]" if spec.scoped else ""))
            lay.addWidget(self._button(
                icon,
                tooltip(
                    title=syntax,
                    body=spec.doc,
                    note=(label("mktool.wraps") if spec.scoped
                          else label("mktool.dropped")),
                ),
                lambda _c=False, n=name, d=default: self._on_click(n, d),
            ))

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{C.BORDER};")
        lay.addSpacing(4)
        lay.addWidget(sep)
        lay.addSpacing(4)

        # Le marqueur de valeur n'est PAS une balise (il ne met rien en forme,
        # il substitue) — d'où le séparateur, et sa place en bout de barre.
        lay.addWidget(self._button(
            "mk_value",
            tooltip(title="$name", body=label("mktool.value_tip")),
            lambda _c=False: self._on_click(KIND_VALUE, "name"),
        ))
        lay.addStretch()

    def add_trailing_widget(self, widget):
        """Ajoute un contrôle de contexte à droite de la barre existante.

        L'atelier Texte y place la bascule de balisage et le choix de police :
        ce sont des réglages du même geste d'écriture, pas un second bandeau.
        """
        self.layout().addWidget(widget)

    def _button(self, icon: str, tooltip: str, slot) -> QToolButton:
        # Même bouton que les barres de canvas (28×24, icône 18, cadre discret) :
        # une barre d'outils se reconnaît d'un écran à l'autre.
        b = QToolButton(self)
        b.setFixedSize(28, 24)
        b.setIconSize(QSize(18, 18))
        b.setIcon(icons.get(icon, C.TEXT_NORM))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER}; background:{C.BG_INPUT};"
            f"border-radius:4px; padding:0px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER}; border-color:{C.ACCENT};}}"
            f"QToolButton:disabled{{background:transparent; border-color:{C.BORDER_DARK};}}"
        )
        b.setToolTip(tooltip)
        # Sans focus : cliquer un bouton ne doit ni voler le curseur au texte,
        # ni défaire la sélection sur laquelle on vient d'appuyer.
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(slot)
        return b

    # ── Contexte projet ───────────────────────────────────────────

    def set_project(self, project):
        self._project = project

    def set_font(self, font):
        """Police d'aperçu — la seule qui puisse dire quels glyphes NOMMÉS
        existent, donc ce que `[icon=…]` peut désigner."""
        self._font = font

    # ── Application ───────────────────────────────────────────────

    def _on_click(self, name: str, default: str):
        """Un clic : soit la liste de ce que la valeur peut désigner, soit la
        balise posée directement."""
        choices = self._choices(name)
        if not choices:
            self._insert(name, default or None, preselect=bool(default))
            return
        # Même explorateur filtrable que les sélecteurs d'assets : une liste
        # qui grossit reste lisible et le clavier y trouve naturellement sa
        # place. Le footer garde la saisie libre, utile avant de créer l'asset
        # ou la variable que le texte va citer.
        entries = [(choice, choice,
                    icons.get("font", C.ACCENT) if name == "font" else None)
                   for choice in choices]
        popup = ScriptPickerPopup(entries, C.ACCENT, parent=self,
                                  new_label=label("mktool.type_by_hand"))
        popup.picked.connect(lambda value:
                             self._insert(name, value, preselect=False))
        popup.new_requested.connect(
            lambda: self._insert(name, default or None,
                                 preselect=bool(default)))
        btn = self.sender()
        popup.show_below(btn)

    def _choices(self, name: str) -> list[str]:
        """Ce que la valeur peut désigner, quand le projet le sait. Vide = rien
        à proposer, on insère alors un gabarit à corriger sur place."""
        if name == KIND_VALUE and self._project:
            return sorted({v.name for v in self._project.globals}
                          | {c.name for c in self._project.constants})
        if name == "icon" and self._font:
            # Les glyphes MULTI-caractères seuls : une case qui porte « A » se
            # tape au clavier, `[icon=…]` n'existe que pour les cases fusionnées
            # (pictogrammes, ligatures) qu'aucune touche ne produit.
            # Un nom à crochets est écarté : la valeur d'une balise s'arrête au
            # premier « ] », `[icon=[X]]` ne voudrait pas dire ce qu'il montre.
            return sorted({g.char for g in self._font.glyphs
                           if len(g.char) > 1 and "[" not in g.char
                           and "]" not in g.char})
        if name == "font" and self._project:
            # Seuls les FontAsset sont sélectionnables : c'est ce qu'une TextBox
            # nomme et ce que le build matérialise (`project_build_fonts`). Les
            # Font brutes ne sont que des sources — proposer leur nom mènerait à
            # une police introuvable à l'émission. La réconciliation garantit
            # qu'un asset existe pour toute planche autonome.
            names = {getattr(asset, "name", "") for asset in
                     (getattr(self._project, "font_assets", None) or [])}
            return sorted(name for name in names if name and "[" not in name
                          and "]" not in name)
        return []

    def _insert(self, name: str, value: Optional[str], *, preselect: bool):
        """Pose la balise et laisse le curseur là où l'écriture continue."""
        a, b = self._selection()
        src = self._source()

        if name == KIND_VALUE:
            token = "$" + (value or "name")
            self._apply([(a, a, token)],
                        (a + 1, len(token) - 1) if preselect else (a + len(token), 0))
            return

        spec = TAGS[name]
        open_tag = f"[{name}]" if spec.value == VALUE_NONE else f"[{name}={value}]"
        val_at = a + len(name) + 2      # après « [nom= »
        val_len = len(value or "")

        if not spec.scoped:
            # Ponctuelle : elle marque un instant, elle ne recouvre rien. Posée
            # au DÉBUT de la sélection — « à partir d'ici », pas « après ».
            self._apply([(a, a, open_tag)],
                        (val_at, val_len) if preselect and val_len
                        else (a + len(open_tag), 0))
            return

        already = self._wrapping(src, a, b, name)
        if already:
            # Déjà enveloppée : le bouton la retire. Sans ça, re-cliquer
            # empilerait `[wave][wave]…` sans que rien ne change à l'écran.
            (o0, o1), (c0, c1) = already
            self._apply([(o0, o1, ""), (c0, c1, "")], (o0, c0 - o1))
            return

        close_tag = f"[/{name}]"
        # La sélection reste sélectionnée : on peut enchaîner une seconde
        # balise dessus (`[wave]` puis `[color=3]`) sans la reprendre.
        self._apply([(b, b, close_tag), (a, a, open_tag)],
                    (val_at, val_len) if preselect and val_len
                    else (a + len(open_tag), b - a))

    @staticmethod
    def _wrapping(src: str, a: int, b: int, name: str):
        """Les deux bornes de la balise `name` qui enveloppe déjà [a, b[, ou
        None. La paire est reconnue qu'elle soit JUSTE AUTOUR de la sélection ou
        DEDANS : on a sélectionné le texte, ou le texte et ses balises."""
        close = f"[/{name}]"
        opener = re.compile(rf"\[{name}(?:=[^\]]*)?\]")

        m = re.search(opener.pattern + r"$", src[:a])
        if m and src[b:].startswith(close):
            return (m.start(), a), (b, b + len(close))

        inner = src[a:b]
        m = opener.match(inner)
        if m and inner.endswith(close) and b - len(close) >= a + m.end():
            return (a, a + m.end()), (b - len(close), b)
        return None

    def _apply(self, edits: list[tuple[int, int, str]],
               select: tuple[int, int]):
        """Applique les remplacements en UN pas d'annulation, puis pose la
        sélection (`(début, longueur)`) demandée.

        De la fin vers le début : chaque remplacement décale ce qui le suit,
        pas ce qui le précède — les positions calculées restent donc justes."""
        if hasattr(self._edit, "replace_source"):
            self._edit.replace_source(edits, select)
            return
        cur = self._edit.textCursor()
        cur.beginEditBlock()
        for a, b, text in sorted(edits, reverse=True):
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            cur.insertText(text)
        cur.endEditBlock()
        start, length = select
        cur.setPosition(start)
        if length:
            cur.setPosition(start + length, QTextCursor.MoveMode.KeepAnchor)
        self._edit.setTextCursor(cur)

    def _source(self) -> str:
        return self._edit.source() if hasattr(self._edit, "source") else self._edit.toPlainText()

    def _selection(self) -> tuple[int, int]:
        if hasattr(self._edit, "selection"):
            return self._edit.selection()
        cur = self._edit.textCursor()
        return cur.selectionStart(), cur.selectionEnd()
        self._edit.setFocus()
