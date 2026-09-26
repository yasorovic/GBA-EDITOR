"""
ui/text_editor/text_inspector.py — colonne droite, contexte Texte (le défaut).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QLineEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from core.history import get_history, SetFieldCmd
from core.text_markup import parse, resolve, TAGS
from ui.common.theme import C, T
from ui.common.widgets import CollapsibleCard
from ui.common.labels import label
from ui.text_editor.colors import TEXT_COLOR
from ui.text_editor.inspector_shell import insp_scroll


class TextInspector(QWidget):
    """Contexte par défaut : ce qui identifie et situe l'entrée sélectionnée.

    Le contenu, lui, s'édite au centre — on édite là où on lit.
    """

    changed = pyqtSignal()
    path_rename_requested = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._text = None
        self._blocking = False
        # Index des citations, partagé avec la table : un seul parcours pour
        # tout le projet, luaparser étant trop lent pour être relancé à chaque
        # clic. None = à reconstruire.
        self._usage_index = None
        self._font = None       # police d'aperçu, pour les caractères manquants
        self._parsed = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        host, lay, self._name_lbl = insp_scroll(TEXT_COLOR, label("common.text"))
        root.addWidget(host)

        self._empty = QLabel(label("txtinsp.empty"))
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._empty)

        self._body = QWidget()
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)

        filing_card = CollapsibleCard(label("txttbl.h_path"))
        self._path_edits: list[QLineEdit] = []
        for level in range(6):
            edit = QLineEdit()
            edit.setPlaceholderText(label("txtwb.level", n=level + 1))
            edit.setFont(QFont(T.UI, T.SM))
            edit.setStyleSheet(
                f"QLineEdit{{background:{C.BG_INPUT}; color:{C.TEXT_NORM};"
                f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px;}}")
            edit.editingFinished.connect(
                lambda l=level, e=edit: self._commit_path(l, e.text()))
            filing_card.body_layout.addWidget(edit)
            self._path_edits.append(edit)
        filing_card.set_expanded(False)
        bl.addWidget(filing_card)

        # Ne reste ici que ce qui n'accompagne pas l'écriture : la note du
        # traducteur et l'identité machine.
        note_card = CollapsibleCard(label("txtinsp.note_card"))
        note_card.set_expanded(False)
        self._note_edit = QTextEdit()
        self._note_edit.setFont(QFont(T.UI, T.SM))
        self._note_edit.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px;}}"
        )
        self._note_edit.setFixedHeight(64)
        self._note_edit.setPlaceholderText(label("txtinsp.note_placeholder"))
        self._note_edit.setToolTip(label("txtinsp.note_tip"))
        # Commit au focus-out : une commande par frappe noierait l'historique.
        self._note_edit.focusOutEvent = self._note_focus_out
        self._note_baseline = ""
        note_card.body_layout.addWidget(self._note_edit)
        bl.addWidget(note_card)

        # ── Balisage ──────────────────────────────────────────────
        # L'atelier montre le rendu, pas ce qui l'empêche : les anomalies de
        # balisage n'ont nulle part ailleurs où apparaître avant le build.
        markup_card = CollapsibleCard(label("txtinsp.markup"))
        markup_card.set_expanded(False)
        markup_card.setToolTip("<br>".join(
            f"<b>[{s.name}{'=…' if s.value else ''}]</b> — {s.doc}"
            for s in TAGS.values()))
        self._markup = QLabel("")
        self._markup.setFont(QFont(T.UI, T.XS))
        self._markup.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._markup.setWordWrap(True)
        markup_card.body_layout.addWidget(self._markup)
        self._issues = QLabel("")
        self._issues.setFont(QFont(T.UI, T.XS))
        self._issues.setStyleSheet(f"color:{C.ACCENT_YLW};")
        self._issues.setWordWrap(True)
        self._issues.setVisible(False)
        markup_card.body_layout.addWidget(self._issues)
        # Caractères que la police d'aperçu ne sait pas rendre. C'est l'autre
        # moitié de la raison d'être de cet écran : croiser la table et la
        # police, plutôt que de découvrir le trou sur la console.
        self._missing = QLabel("")
        self._missing.setFont(QFont(T.UI, T.XS))
        self._missing.setStyleSheet(f"color:{C.ACCENT_RED};")
        self._missing.setWordWrap(True)
        self._missing.setVisible(False)
        markup_card.body_layout.addWidget(self._missing)
        bl.addWidget(markup_card)

        # Contrepartie visible du renommage automatique : il réécrit les
        # `text:draw("clé")`, encore faut-il savoir lesquels avant d'y toucher.
        usage_card = CollapsibleCard(label("txtinsp.used_by"))
        usage_card.set_expanded(False)
        self._usage = QLabel("")
        self._usage.setFont(QFont(T.UI, T.XS))
        self._usage.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._usage.setWordWrap(True)
        usage_card.body_layout.addWidget(self._usage)
        bl.addWidget(usage_card)

        info_card = CollapsibleCard(label("txtinsp.info"))
        info_card.set_expanded(False)
        self._meta = QLabel("")
        self._meta.setFont(QFont(T.UI, T.XS))
        self._meta.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._meta.setWordWrap(True)
        info_card.body_layout.addWidget(self._meta)
        bl.addWidget(info_card)

        lay.addWidget(self._body)
        lay.addStretch()
        self._body.setVisible(False)

    def set_font(self, font):
        """Police d'aperçu courante — celle contre laquelle se mesure le
        charset. Ce n'est pas une propriété du texte : il reste indépendant de
        toute police (c'est ce qui permettra les traductions)."""
        self._font = font
        self.set_parsed(self._parsed)

    def set_parsed(self, parsed):
        """Affiche l'analyse du contenu courant — appelée à chaque frappe."""
        self._parsed = parsed
        if parsed is None:
            self._markup.setText("")
            self._issues.setVisible(False)
            self._missing.setVisible(False)
            return
        bits = [label('txtinsp.length_characters_emitted', length=parsed.length)]
        effects = parsed.of_kind(*(s.name for s in TAGS.values()))
        if effects:
            bits.append(label('txtinsp.value_tag_s', value=len(effects)))
        if parsed.animated_glyphs:
            bits.append(label('txtinsp.animated_glyphs_animated_glyph_s', animated_glyphs=parsed.animated_glyphs))
        values = parsed.of_kind("value")
        if values:
            bits.append("values: " + ", ".join(f"${m.value}" for m in values))
        self._markup.setText(" · ".join(bits))

        # Dédoublonnées : une balise mal écrite est signalée à l'ouverture ET à
        # la fermeture, deux endroits à souligner mais une seule chose à dire.
        seen, msgs = set(), []
        for message in ([i.message for i in parsed.issues]
                        + self._cross_check(parsed)):
            if message not in seen:
                seen.add(message)
                msgs.append("⚠ " + message)
        self._issues.setText("\n".join(msgs))
        self._issues.setVisible(bool(msgs))

        # Sur le texte RÉSOLU : les chiffres d'une valeur interpolée demandent
        # eux aussi des glyphes, et la place réservée n'en est pas un.
        shown = resolve(parsed, self._project.text_values() if self._project else {})
        miss = self._font.missing_chars(shown) if self._font else []
        self._missing.setText(
            label('txtinsp.missing_glyphs', font=self._font.name, glyphs=' '.join((repr(c)[1:-1] for c in miss)))
            if miss else "")
        self._missing.setVisible(bool(miss))

    def _cross_check(self, parsed) -> list[str]:
        """Ce que le parseur ne peut pas savoir seul : une balise peut être
        bien écrite et désigner quelque chose qui n'existe pas. La résolution
        des références est ici, le parseur reste indépendant du projet."""
        out = []
        for m in parsed.of_kind("icon"):
            if self._font and self._font.glyph(m.value) is None:
                out.append(label('txtinsp.no_glyph', name=self._font.name, value=m.value))
        if parsed.of_kind("color") and self._font:
            from codegen.font_emit import render_composited
            if not render_composited(self._font):
                out.append(label('txtinsp.tiles_no_color', name=self._font.name))
        if self._project:
            known = {v.name for v in self._project.globals} \
                  | {c.name for c in self._project.constants}
            for m in parsed.of_kind("value"):
                if m.value not in known:
                    out.append(label('txtinsp.unknown_value', value=m.value))
        return out

    def load(self, text, project):
        """Affiche `text` (ou l'état vide si None)."""
        self._project = project
        self._text = text
        self._blocking = True
        has = text is not None
        self._body.setVisible(has)
        self._empty.setVisible(not has)
        if has:
            for level, edit in enumerate(self._path_edits):
                edit.setText(text.path[level] if level < len(text.path) else "")
                edit.setVisible(level < len(text.path))
            self._note_edit.setPlainText(text.note)
            self._note_baseline = text.note
            self._name_lbl.setText(text.key)
            self._usage.setText(self._usage_text(text.key))
            self.set_parsed(parse(text.content))
            self._meta.setText(
                label('txtinsp.id_id_folder_value', id=text.id, value=text.path_str() or label('txtinsp.root'))
                + (label('txtinsp.key_auto_note')
                   if text.auto_key else label('txtinsp.key_manual_note'))
                + (label('txtinsp.originating_scene_scene', scene=text.scene) if text.scene else "")
            )
        else:
            for edit in self._path_edits:
                edit.clear()
                edit.setVisible(False)
            self._name_lbl.setText("")
            self._usage.setText("")
            self.set_parsed(None)
        self._blocking = False

    def _commit_path(self, level: int, raw: str) -> None:
        if self._blocking or self._text is None:
            return
        value = raw.strip()
        old = self._text.path[level] if level < len(self._text.path) else ""
        if value and value != old:
            self.path_rename_requested.emit(level, value)

    # ── Utilisations ──────────────────────────────────────────────

    def invalidate_usages(self):
        """Périme l'index — dès qu'un script bouge (renommage de clé, création,
        suppression, édition dans le Script Editor). Recalcul paresseux."""
        self._usage_index = None

    def _usage_text(self, key: str) -> str:
        """Qui cite cette entrée, et où — un site par ligne.

        L'index vient du projet (`text_usage_index`), pas d'un parcours local :
        la colonne « Used » de la table pose la même question, et deux comptes
        différents pour la même clé feraient douter des deux. Il couvre aussi
        les mises en page, qu'un parcours des seuls scripts manquait — un texte
        posé dans une boîte de dialogue passait pour orphelin."""
        if self._usage_index is None and self._project is not None:
            self._usage_index = self._project.text_usage_index()
        if self._usage_index is None:
            return ""
        if not self._usage_index.scripts_scanned:
            return label('txtinsp.usage_unknown')
        use = self._usage_index.get(key)
        if not use.count:
            return label('txtinsp.no_script_no_layout')
        lines = [f"  {line}" for line in use.detail().splitlines()]
        return "\n".join([use.summary()] + lines)

    def _note_focus_out(self, e):
        """Commite la note si elle a changé."""
        QTextEdit.focusOutEvent(self._note_edit, e)
        if self._blocking or not self._text:
            return
        new = self._note_edit.toPlainText()
        if new == self._note_baseline:
            return
        old, self._note_baseline = self._note_baseline, new
        get_history().push(SetFieldCmd(
            self._text, "note", old, new,
            label=f"Note de {self._text.key}", persist_fn=self.changed.emit,
        ))
