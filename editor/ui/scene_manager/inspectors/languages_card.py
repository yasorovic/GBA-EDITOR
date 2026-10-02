"""
ui/scene_manager/inspectors/languages_card.py — la carte « Languages » de
l'inspecteur de projet (ROADMAP v0.9, phase 1).

**Déclarer, pas deviner.** C'est cette carte qui lie une langue à son fichier de
traduction et à ses polices. Rien n'est déduit d'un nom de fichier : `font_de`
peut PRÉ-REMPLIR un remplacement au moment où on ajoute la langue, mais ce qui
lie reste ce qui est écrit ici — un suffixe magique casserait au premier
renommage et ne se vérifierait nulle part.

Deux choses distinctes, donc deux zones distinctes :

  • la langue SOURCE — celle qu'on écrit dans `texts.json`. Elle n'a pas de
    fichier side (il serait une seconde copie de la même langue) et pas de
    remplacement de police (les polices du projet SONT les siennes). La
    déclarer sert à la nommer.
  • les TRADUCTIONS — une par fichier `texts_<code>.json`, chacune avec ses
    remplacements de police éventuels.

La carte ne mute rien : elle SIGNALE un geste — « ajoute », « retire »,
« ce champ vaut ça » — et l'inspecteur en fait une commande annulable. Un geste
par signal, et non la liste entière repoussée à chaque fois : deux
`SetFieldCmd` de suite sur le même champ fusionnent, et une liste entière aurait
fondu « déclarer l'allemand, le renommer, retirer le portugais » en un seul pas
d'annulation — qui ramène le projet à zéro langue.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QToolButton, QFrame,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from core.models.settings import Language, lang_code
from ui.common.theme import C, T, QSS
from ui.common.widgets import CollapsibleCard, W, BTN_ICON
from ui.common import icons


# Ce que propose le combo d'une police non remplacée.
_SAME = 'langcard.same_as_source'


class LanguagesCard(CollapsibleCard):
    """Déclaration des langues du projet."""

    # Un signal par GESTE, jamais « voici la liste entière ». Ce qui décide de
    # ça, c'est l'annulation : les `SetFieldCmd` consécutifs sur un même champ
    # FUSIONNENT (c'est ce qu'on veut en tapant un nom), si bien qu'une liste
    # repoussée en bloc réduisait « déclarer, renommer, retirer » à un seul pas
    # — dont l'annulation ramenait le projet à zéro langue.
    source_field_changed = pyqtSignal(str, str)        # (champ, valeur)
    language_added = pyqtSignal()
    language_removed = pyqtSignal(object)              # Language
    language_field_changed = pyqtSignal(object, str, object)   # (Language, champ, valeur)

    def __init__(self, parent=None):
        # Repliée d'office : un projet monolingue n'a rien à y lire, et c'est
        # le cas de tous ceux d'avant la v0.9.
        super().__init__(label('langcard.languages'), expanded=False, parent=parent)
        self._project = None
        self._blocking = False
        self._expanded: str = ""     # code de la langue dont les polices sont ouvertes
        inner = self.body_layout

        hint = QLabel(
            label('langcard.source_note'))
        hint.setFont(QFont(T.UI, T.XS))
        hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hint.setWordWrap(True)
        inner.addWidget(hint)

        # ── Source ────────────────────────────────────────────────
        src = QHBoxLayout()
        src.setContentsMargins(0, 4, 0, 0)
        src.setSpacing(4)
        lbl = QLabel(label('langcard.source'))
        lbl.setFont(QFont(T.UI, T.SM))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        src.addWidget(lbl)
        self._src_code = self._code_field("en")
        self._src_code.editingFinished.connect(self._commit_source)
        src.addWidget(self._src_code)
        self._src_name = self._name_field("English")
        self._src_name.editingFinished.connect(self._commit_source)
        src.addWidget(self._src_name, 1)
        inner.addLayout(src)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C.BORDER_DARK};")
        inner.addWidget(sep)

        # ── Traductions ───────────────────────────────────────────
        self._rows_host = QWidget()
        self._rows = QVBoxLayout(self._rows_host)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(2)
        inner.addWidget(self._rows_host)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 2, 0, 0)
        self._btn_add = W.btn_add(label('langcard.declare_a_translation'))
        self._btn_add.clicked.connect(self._add_language)
        add_row.addWidget(self._btn_add)
        self._count = QLabel("")
        self._count.setFont(QFont(T.UI, T.XS))
        self._count.setStyleSheet(f"color:{C.TEXT_MUTED};")
        add_row.addWidget(self._count, 1)
        inner.addLayout(add_row)

    # ── Fabriques de champs ───────────────────────────────────────

    def _code_field(self, placeholder: str) -> QLineEdit:
        e = QLineEdit()
        e.setFont(QFont(T.CODE, T.SM))
        e.setStyleSheet(QSS.lineedit)
        e.setFixedWidth(52)
        e.setPlaceholderText(placeholder)
        e.setToolTip(tooltip(
            title=label('langcard.code_title'), body=label('langcard.code_tip'),
            note=label('langcard.code_note')))
        return e

    def _name_field(self, placeholder: str) -> QLineEdit:
        e = QLineEdit()
        e.setFont(QFont(T.UI, T.SM))
        e.setStyleSheet(QSS.lineedit)
        e.setPlaceholderText(placeholder)
        e.setMinimumWidth(60)
        e.setToolTip(tooltip(
            title=label('langcard.name_title'), body=label('langcard.name_tip')))
        return e

    # ── Chargement ────────────────────────────────────────────────

    def load(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        self._blocking = True
        try:
            p = self._project
            enabled = p is not None
            for w in (self._src_code, self._src_name, self._btn_add):
                w.setEnabled(enabled)
            src = p.settings.source_lang if p else Language()
            self._src_code.setText(src.code)
            self._src_name.setText(src.name)
            self._rebuild_rows()
            n = len(p.settings.languages) if p else 0
            self._count.setText(
                "" if not n else label('langcard.count', n=n))
        finally:
            self._blocking = False

    def _clear_rows(self):
        while self._rows.count():
            item = self._rows.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_rows(self):
        self._clear_rows()
        if not self._project:
            return
        for i, lang in enumerate(self._project.settings.languages):
            self._rows.addWidget(self._build_row(i, lang))
            if lang.code and lang.code == self._expanded:
                self._rows.addWidget(self._build_fonts(i, lang))

    def _build_row(self, index: int, lang: Language) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        code = self._code_field("de")
        code.setText(lang.code)
        code.editingFinished.connect(
            lambda _i=index, _e=code: self._commit_code(_i, _e.text()))
        row.addWidget(code)

        name = self._name_field("Deutsch")
        name.setText(lang.name)
        name.editingFinished.connect(
            lambda _i=index, _e=name: self._commit_name(_i, _e.text()))
        row.addWidget(name, 1)

        # Le remplacement de police est l'EXCEPTION : le bouton dit s'il y en a
        # un, et n'ouvre le détail que si on le demande. Une grille de combos
        # par langue, toujours dépliée, ferait passer pour obligatoire ce qui
        # ne sert qu'aux écritures non latines.
        n = int(bool(lang.default_font))
        btn = QToolButton()
        btn.setFixedSize(22, 22)
        btn.setStyleSheet(BTN_ICON)
        btn.setIcon(icons.get("font", C.ACCENT if n else C.TEXT_DIM))
        btn.setToolTip(tooltip(
            title=label('langcard.font_title'),
            body=(label('langcard.font_replacements', n=n) if n
                  else label('langcard.no_font_replacement')),
            note=label('langcard.font_note')))
        btn.clicked.connect(lambda _c=False, _l=lang.code: self._toggle_fonts(_l))
        row.addWidget(btn)

        rm = W.btn_danger(tooltip(
            title=label('langcard.remove_title'), body=label('langcard.remove_tip')))
        rm.clicked.connect(lambda _c=False, _i=index: self._remove(_i))
        row.addWidget(rm)
        return host

    def _build_fonts(self, index: int, lang: Language) -> QWidget:
        """Sous-panneau : le remplacement de la police par défaut seulement."""
        host = QFrame()
        host.setStyleSheet(
            f"background:{C.BG_BASE}; border-left:2px solid {C.BORDER_MID};")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(8, 4, 4, 4)
        lay.setSpacing(2)
        assets = list(getattr(self._project, "font_assets", ()) or []) if self._project else []
        fonts = [f.name for f in assets] or [f.name for f in self._project.fonts]
        if not fonts:
            empty = QLabel(label('langcard.this_project_has_no_font_yet'))
            empty.setFont(QFont(T.UI, T.XS))
            empty.setStyleSheet(f"color:{C.TEXT_MUTED};")
            lay.addWidget(empty)
            return host
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        lbl = QLabel(label('projset.default_font'))
        lbl.setFont(QFont(T.UI, T.XS)); lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        row.addWidget(lbl)
        combo = QComboBox()
        combo.setFont(QFont(T.UI, T.XS)); combo.setStyleSheet(QSS.combobox)
        combo.addItem(label(_SAME), "")
        for name in fonts:
            combo.addItem(name, name)
        combo.setCurrentIndex(max(0, combo.findData(lang.default_font)))
        combo.currentIndexChanged.connect(
            lambda _i, _idx=index, _c=combo: self._commit_font(_idx, _c.currentData()))
        row.addWidget(combo, 1)
        lay.addLayout(row)
        return host

    def _toggle_fonts(self, code: str):
        self._expanded = "" if self._expanded == code else code
        self._blocking = True
        try:
            self._rebuild_rows()
        finally:
            self._blocking = False

    # ── Mutations — la carte PROPOSE, l'inspecteur décide ─────────

    def _lang_at(self, index: int):
        langs = self._project.settings.languages if self._project else []
        return langs[index] if 0 <= index < len(langs) else None

    def _commit_source(self):
        if self._blocking or not self._project:
            return
        cur = self._project.settings.source_lang
        # Les DEUX valeurs lues avant d'émettre quoi que ce soit : le premier
        # signal repasse par `refresh()`, qui repose les champs depuis le
        # modèle — relire le second après lui rendrait l'ancienne valeur, et le
        # nom saisi serait perdu à chaque fois.
        code, name = lang_code(self._src_code.text()), self._src_name.text().strip()
        if code != cur.code:
            self.source_field_changed.emit("code", code)
        if name != cur.name:
            self.source_field_changed.emit("name", name)

    def _commit_code(self, index: int, raw: str):
        if self._blocking or not self._project:
            return
        lang = self._lang_at(index)
        code = lang_code(raw)
        if lang is None or code == lang.code:
            return
        taken = {l.code for l in self._project.settings.languages if l is not lang}
        taken.add(self._project.settings.source_lang.code)
        if not code or code in taken:
            # Un code vide ou déjà pris ne peut pas nommer un fichier : on
            # repose l'ancien plutôt que d'écrire deux langues au même endroit.
            self.refresh()
            return
        self.language_field_changed.emit(lang, "code", code)

    def _commit_name(self, index: int, raw: str):
        if self._blocking or not self._project:
            return
        lang = self._lang_at(index)
        if lang is not None and lang.name != raw.strip():
            self.language_field_changed.emit(lang, "name", raw.strip())

    def _commit_font(self, index: int, replacement):
        if self._blocking or not self._project:
            return
        lang = self._lang_at(index)
        if lang is None:
            return
        replacement = replacement or ""
        if replacement != lang.default_font:
            self.language_field_changed.emit(lang, "default_font", replacement)

    def _add_language(self):
        """Ajoute une ligne éditable en place — jamais un dialogue."""
        if self._project:
            self.language_added.emit()

    def _remove(self, index: int):
        lang = self._lang_at(index)
        if lang is not None:
            self.language_removed.emit(lang)

    def free_code(self) -> str:
        """Un code encore libre, pour une langue qu'on vient d'ajouter — elle
        doit pouvoir nommer son fichier avant d'être renommée."""
        taken = {l.code for l in self._project.settings.languages}
        taken.add(self._project.settings.source_lang.code)
        n = 1
        while f"lang{n}" in taken:
            n += 1
        return f"lang{n}"
