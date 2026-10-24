"""
ui/text_editor/text_panel.py — colonne centre, contexte Texte : la table des
textes en haut, l'atelier d'écriture en bas.

Ce module ARBITRE. La table (`text_table.py`) et l'atelier
(`text_workbench.py`) sont deux vues qui signalent ce qu'on a édité ; c'est ici
qu'une saisie devient une commande annulable, et ici seulement. Une vue qui
écrirait dans le modèle le ferait hors historique — et le rangement, lui,
recale les clés automatiques et réécrit les scripts qui les citent : ce n'est
pas un geste qu'on veut voir partir de deux endroits.

D'où le point unique `_repath` : ranger UNE entrée depuis une cellule de la
table et ranger VINGT entrées depuis le champ de niveau de l'atelier sont le
même geste à l'échelle près, exactement comme renommer une catégorie.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from ui.common.popup import MessageBox as QMessageBox
from PyQt6.QtCore import pyqtSignal

from core.models.text import MAX_DEPTH, SEP, norm_path, repath_segment, moved_text_paths
from core.text_markup import parse
from core.history import get_history, SetFieldCmd, AddListItemCmd
from ui.common.labels import label
from ui.text_editor.text_table import TextTable
from ui.text_editor.text_workbench import TextWorkbench
from ui.text_editor.text_commands import (
    DeleteTextsCmd, RenameTextKeyCmd, RenameTextGroupKeysCmd, SetTextPathCmd,
    SetTranslationCmd,
)


class TextPanel(QWidget):
    """Table des `Text` + éditeur du contenu sélectionné."""

    text_selected = pyqtSignal(object)      # Text | None (l'inspecteur en suit un)
    changed = pyqtSignal()                  # contenu modifié → persistance
    identity_changed = pyqtSignal(object)   # clé/chemin modifiés
    parsed = pyqtSignal(object)             # ParsedText de l'entrée courante
    preview_font_changed = pyqtSignal(object)   # Font | None
    filing_moved = pyqtSignal(object)       # Chemin à sélectionner après move/undo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._current: Optional[object] = None
        self._selection: list = []
        # "" = source — la langue que L'ATELIER a effectivement chargée. Suit
        # `TextTable._active_lang` avec un tour de retard EXPRÈS : le commit
        # d'une frappe en cours doit encore voir l'ANCIENNE langue au moment
        # où le sélecteur change (cf. `_on_lang_changed`), le même principe
        # que `self._current` pendant un changement de sélection.
        self._editing_lang = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._table = TextTable()
        # Garder l'atelier pour ses relais internes, sans l'exposer à l'écran
        # ni laisser une poignée de séparation permettre de le rouvrir.
        self._bench = TextWorkbench(self)
        self._bench.setEnabled(False)
        self._bench.hide()
        # Réemployer aussi les onglets de langue de l'atelier ; le reste de
        # l'ancien panneau et son aperçu demeurent masqués.
        root.addWidget(self._bench._lang_tabs)
        root.addWidget(self._table, 1)

        self._table.selection_changed.connect(self._on_selection)
        self._table.key_edited.connect(self._on_table_key)
        self._table.group_key_edited.connect(self._on_group_key)
        self._table.entry_structure.connect(self._edit_sequence_entry)
        self._table.group_renamed.connect(self._on_group_renamed)
        self._table.delete_asked.connect(self._delete_texts)
        self._table.sequence_delete_asked.connect(self._delete_sequence)
        self._table.entry_reorder_asked.connect(self._reorder_entry)
        self._table.content_edited.connect(self._on_inline_content)

        self._bench.content_committed.connect(self._on_content_committed)
        self._bench.active_lang_changed.connect(self._on_lang_changed)
        self._bench.key_committed.connect(self._on_bench_key)
        self._bench.path_committed.connect(
            lambda lvl, seg: self._repath(self._selection, lvl, seg))
        self._bench.parsed.connect(self._on_parsed)
        self._bench.preview_font_changed.connect(self.preview_font_changed.emit)
        self._bench.preview_font_changed.connect(self._table.set_markup_font)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project):
        self._project = project
        self._editing_lang = ""
        self._bench.load_project(project)
        self._table.load_project(project)

    def refresh(self, select_ids: Optional[list[int]] = None):
        """Recharge depuis le projet — fichier déposé (watcher) ou undo/redo.

        Repeuple aussi les onglets de langue : ce `refresh` est le même que
        celui que le watcher et l'undo déclenchent depuis n'importe où, y
        compris après une déclaration de langue faite dans l'inspecteur de
        projet — un autre écran, avec lequel cette table ne partage aucun
        signal. Bon marché (une poignée d'onglets), pas la peine d'en créer un."""
        self._bench.refresh_languages()
        self._table.refresh(select_ids)

    def reload_fonts(self):
        """Polices apparues ou disparues."""
        self._bench.reload_fonts()

    def refresh_preview_font(self):
        self._bench.refresh_preview_font()

    def preview_font(self):
        return self._bench.preview_font()

    def invalidate_usages(self):
        """Les scripts ont changé : la colonne « Used » est périmée."""
        self._table.invalidate_usages()

    def clear_selection(self):
        """Vide la sélection et l'atelier, sans émettre."""
        self._table.clear_selection()
        self._selection = []
        self._current = None
        self._bench.set_texts([])

    def set_folder_filter(self, path) -> None:
        """Relais du Library de textes vers la table centrale."""
        self._table.set_folder_filter(path)

    def rename_selected_path(self, level: int, segment: str) -> None:
        """Renommage d'un niveau depuis l'inspecteur de texte."""
        if self._selection:
            self._repath(self._selection, level, segment)

    def rename_folder(self, path, segment: str) -> None:
        """Relais du renommage en place demandé depuis le Library."""
        self._on_group_renamed(path, segment)

    def move_path(self, source, destination):
        """Le drop suit le nouveau rangement, y compris pour une clé manuelle."""
        if self._project is None:
            return
        source, destination = tuple(source), tuple(destination)
        entries = moved_text_paths(self._project.texts, source, destination)
        if not entries:
            return
        new_root = destination + (source[-1],)

        def persist():
            moved = tuple(entries[0][0].path) == tuple(entries[0][2])
            path = new_root if moved else source
            self._after_identity_change()
            self.set_folder_filter(path)
            self._table.refresh(select_ids=[text.id for text, _old, _new in entries])
            self.filing_moved.emit(path)

        get_history().push(SetTextPathCmd(
            self._project, entries, label=f"Move text filing {SEP.join(source)}",
            persist_fn=persist))

    def rename_key(self, t, typed: str) -> None:
        """Renommage de clé par le code (les cellules et le champ de l'atelier passent par `_rename_key`)."""
        if self._rename_key(t, typed):
            self._table.refresh()

    # ── Sélection ─────────────────────────────────────────────────

    def _edit_sequence_entry(self, prefix, tid, operation):
        """+ ajoute le texte suivant de la séquence (numéro max + 1) ; − supprime l'entrée."""
        if not self._project:
            return
        text = self._project.get_text_by_id(tid) if tid else None
        if operation == 'remove':
            if text is not None:
                self._table.select_by_ids([tid])
                self._on_selection([text])
                self._delete_texts()
            return
        anchor = text.path if text is not None else self._table.selected_path()
        # Un texte seul n'a pas de préfixe : son + le promeut en séquence (sa clé sert de base).
        added, promoted = self._new_text_after(prefix or text.key, list(anchor))
        self._push_new_text(added, promoted)

    def show_text(self, text) -> None:
        """Navigation entrante : sélectionne `text` malgré les filtres, sans prendre le curseur.
        `select_by_ids` ne signale rien, d'où l'appel explicite de la sélection."""
        self._table.focus_entry(text.id, edit=False)
        self._on_selection([text])

    def _on_selection(self, texts: list):
        # Commiter AVANT de changer d'entrée, sinon la frappe non validée
        # serait attribuée au texte suivant.
        self._bench.commit_pending()
        self._selection = list(texts)
        # L'inspecteur montre UNE entrée : sur une sélection multiple, c'est
        # celle par laquelle elle a commencé.
        current = texts[0] if len(texts) == 1 else None
        # AVANT `set_texts` : ce rechargement ré-analyse le contenu de `current`
        # et le signale via `parsed` → `_on_parsed`, qui écrit dans la table au
        # nom de `self._current`. Le mettre à jour après aurait fait recevoir
        # à l'ANCIENNE ligne le contenu de la NOUVELLE (et l'inverse au clic
        # suivant) — sans qu'une seule touche n'ait été tapée.
        emit_change = current is not self._current
        self._current = current
        self._bench.set_texts(texts)
        if emit_change:
            self.text_selected.emit(current)

    def _on_parsed(self, parsed):
        """Frappe en cours : la ligne de table montre le rendu, l'inspecteur
        les balises. Aucune écriture au modèle — elle arrive au commit."""
        self.parsed.emit(parsed)
        if self._current is None:
            return
        display = parsed.display.replace("\n", " ⏎ ")
        source_code = self._project.settings.source_lang.code if self._project else ""
        if not display and self._editing_lang and self._editing_lang != source_code:
            # Rien encore tapé pour CETTE traduction : la cellule doit
            # continuer de montrer ce qui SERAIT lu — la source, exactement la
            # règle de `Project.text_content()`. Sans ce repli, ouvrir une
            # entrée non traduite la ferait passer à vide sous les yeux, juste
            # parce qu'on l'a sélectionnée.
            display = self._bench.display_of(self._current.content)
        self._table.update_content(self._current, display)

    def _on_lang_changed(self, code: str):
        """Un onglet de langue de l'atelier a été cliqué.

        L'atelier a déjà commité la frappe en cours SOUS L'ANCIENNE langue
        avant d'émettre ce signal (`TextWorkbench.set_active_lang`) — donc
        `self._editing_lang` peut être mis à jour tout de suite : le commit
        qui vient de partir, s'il y en a eu un, l'a lu à sa valeur d'avant."""
        self._editing_lang = code
        self._table.set_active_lang(code)

    # ── Contenu ───────────────────────────────────────────────────

    def _on_inline_content(self, text, before: str, after: str, lang: str):
        if self._project is None or before == after:
            return
        translating = bool(lang and lang != self._project.settings.source_lang.code)

        def persist():
            if translating:
                self._project.save_translation(lang)
            self._table.sync_entry(text)
            if self._current is text:
                self._bench.set_texts([text])
                self.parsed.emit(parse(self._table._editable_content(text)))
            self.changed.emit()

        if translating:
            command = SetTranslationCmd(
                self._project, lang, text, before, after,
                label=f"Translate {text.key} ({lang})", persist_fn=persist)
        else:
            command = SetFieldCmd(text, "content", before, after,
                                  label=f"Content of {text.key}", persist_fn=persist)
        get_history().push(command)

    def _on_content_committed(self, before: str, after: str):
        t = self._current
        if t is None:
            return
        source_code = self._project.settings.source_lang.code if self._project else ""
        if self._editing_lang and self._editing_lang != source_code:
            code = self._editing_lang
            get_history().push(SetTranslationCmd(
                self._project, code, t, before, after,
                label=f"Translate {t.key} ({code})",
                persist_fn=lambda: self._after_translation(code),
            ))
        else:
            get_history().push(SetFieldCmd(
                t, "content", before, after,
                label=f"Content of {t.key}", persist_fn=self._after_content,
            ))

    def _after_content(self):
        """Le contenu décide de deux choses que la table affiche : ce qu'on lit,
        et si l'entrée est encore vide."""
        self.changed.emit()
        self._table.refresh()

    def _after_translation(self, code: str):
        """Même effets que `_after_content`, plus l'écriture du SIDE — le
        maître n'a pas bougé, `save_texts()` n'a donc rien à faire ici."""
        if self._project:
            self._project.save_translation(code)
        self.changed.emit()
        self._table.refresh()

    # ── Clé ───────────────────────────────────────────────────────

    def _on_table_key(self, t, typed: str):
        if not self._rename_key(t, typed):
            self._table.refresh()       # repose la clé du modèle dans la cellule

    def _on_group_key(self, texts, prefix: str):
        prefix = prefix.strip()
        if (not self._project or not prefix or
                any(not any(text is current for current in self._project.texts)
                    for text in texts)):
            self._table.refresh()
            return
        try:
            get_history().push(RenameTextGroupKeysCmd(
                self._project, texts, prefix, persist_fn=self._after_identity_change))
        except ValueError:
            QMessageBox.warning(
                self, label("txtpnl.invalid_key_title"),
                label("txtpnl.invalid_key_msg", name=prefix))
            self._table.refresh()

    def _on_bench_key(self, typed: str):
        if len(self._selection) != 1:
            return
        if not self._rename_key(self._selection[0], typed):
            self._bench.reset_key_field()

    def _rename_key(self, t, raw: str) -> bool:
        """Renomme la clé — refuse le vide et les doublons.

        Point unique du renommage : la cellule de la table et le champ de
        l'atelier écrivent la même chose, il ne doit pas y avoir deux versions
        de cette règle."""
        new = (raw or "").strip()
        if not self._project or not new or new == t.key:
            return False
        from core.text_sequences import would_empty_linked
        if would_empty_linked(self._project, t, new) and QMessageBox.question(
                self, label("txtpnl.empty_sequence_title"),
                label("txtpnl.empty_sequence_msg", page=t.key, name=new),
        ) != QMessageBox.StandardButton.Yes:
            return False
        old = t.key
        if not self._project.rename_text_key(t, new):
            QMessageBox.warning(
                self, label("txtpnl.invalid_key_title"),
                label("txtpnl.invalid_key_msg", name=new))
            return False
        get_history().push(RenameTextKeyCmd(
            self._project, t, old, new,
            persist_fn=self._after_identity_change,
        ))
        return True

    # ── Rangement ─────────────────────────────────────────────────

    def _repath(self, texts: list, lvl: int, seg: str):
        """Change UN niveau de rangement, sur une entrée ou sur vingt.

        Un niveau à la fois, et pas le chemin entier : sur une sélection
        multiple, réécrire les trois niveaux écraserait ceux que la sélection
        ne partage pas — l'utilisateur en a changé un, il n'a rien dit des
        autres."""
        if not self._project or not texts:
            return
        entries = []
        for t in texts:
            path = list(t.path) + [""] * (MAX_DEPTH - len(t.path))
            path[lvl] = seg
            new = norm_path(path)
            if new != list(t.path):
                entries.append((t, list(t.path), new))
        if not entries:
            return
        where = SEP.join(entries[0][2]) or label('txtpnl.root')
        cmd_label = (f"File {len(entries)} texts under {where}" if len(entries) > 1
                     else f"File {entries[0][0].key} under {where}")
        get_history().push(SetTextPathCmd(
            self._project, entries, label=cmd_label,
            persist_fn=self._after_identity_change))

    def _on_group_renamed(self, path, new_seg: str):
        """Renommer un nœud renomme le rangement de tout son sous-arbre."""
        if not self._project:
            return
        path = tuple(path)
        entries = repath_segment(self._project.texts, path, new_seg)
        if not entries:
            return
        self._table.retitle_group(path, new_seg)
        get_history().push(SetTextPathCmd(
            self._project, entries,
            label=f"Rename text filing {' › '.join(path)} → {new_seg}",
            persist_fn=self._after_identity_change))

    def _after_identity_change(self):
        """Persiste, reconstruit la table et prévient l'inspecteur."""
        self.changed.emit()
        self._table.invalidate_usages()
        self._table.refresh()
        self._bench.set_texts(self._selection)
        self.identity_changed.emit(self._current)

    # ── CRUD ──────────────────────────────────────────────────────

    def _add_text(self, path=None):
        """Crée un texte DANS le rangement courant — seul moyen de créer une
        catégorie, et évite de re-ranger chaque entrée après coup.

        Le texte est une feuille nommée `text` sous le dossier (`scr_text`, puis `scr_text_2`…) :
        sans ce nom, sa clé serait celle du dossier lui-même (`scr`)."""
        if not self._project:
            return
        from core.models.text import key_from_path
        folder = list(self._table.selected_path() if path is None else path)
        leaf_path = folder + ["text"]
        added, promoted = self._new_text_after(key_from_path(leaf_path), leaf_path)
        self._push_new_text(added, promoted)

    def _new_text_after(self, base, path, content="", scene=""):
        """Crée un texte sous la clé `base`, sans que `base` soit à la fois entrée et séquence.

        (texte, promotions) : si `base` est déjà un texte seul, il sera renommé `base_1` et le
        nouveau prend `base_2` ; si la séquence existe, il prend le numéro suivant ; sinon il
        porte `base`. Les promotions ne sont appliquées que par la commande qu'on pousse."""
        from core.text_sequences import group_texts, next_key, promotion
        project = self._project
        promoted = promotion(project, base)
        added = project.new_text(content, scene=scene, path=path)
        if promoted:
            project.rename_text_key(added, f"{base}_2")
        elif group_texts(project, base):
            project.rename_text_key(added, next_key(project, base))
        return added, promoted

    def _promoting(self, command, promoted, label):
        """`command` précédée de la promotion, en UNE entrée d'historique."""
        if not promoted:
            return command
        from core.history import MacroCmd
        from ui.text_editor.text_commands import RenameTextKeysCmd
        return MacroCmd([RenameTextKeysCmd(self._project, promoted, label), command], label)

    def _push_new_text(self, t, promoted=()):
        def _after():
            self.changed.emit()
            self._table.refresh(
                select_ids=[t.id] if t in self._project.texts else [])
            if t in self._project.texts:
                self._table.focus_entry(t.id)
            self.identity_changed.emit(t if t in self._project.texts else None)

        # new_text a déjà ajouté l'entrée : execute() est un no-op au premier
        # passage, undo la retire, redo la remet.
        label_ = f"New text {t.key}"
        get_history().push(self._promoting(
            AddListItemCmd(self._project.texts, t, persist_fn=_after, label=label_),
            promoted, label_))

    def _delete_texts(self, texts=None):
        """Supprime la sélection, après confirmation."""
        texts = list(self._selection if texts is None else texts)
        if not texts or not self._project:
            return
        what = (f"“{texts[0].key}”" if len(texts) == 1
                else label("txtpnl.n_texts", n=len(texts)))
        if QMessageBox.question(
            self, label("txtpnl.delete_title"),
            label("txtpnl.delete_msg", what=what),
        ) != QMessageBox.StandardButton.Yes:
            return

        def _after():
            self.changed.emit()
            for code in command.translation_langs:
                self._project.save_translation(code)
            for layout in command.touched_layouts:
                self._project.ui_layouts.save(layout)
            alive = [t.id for t in texts if t in self._project.texts]
            self._selection = [t for t in texts if t in self._project.texts]
            self._table.refresh(select_ids=alive)
            if not alive:
                self._current = None
                self.text_selected.emit(None)
            self.identity_changed.emit(self._current)

        command = DeleteTextsCmd(self._project, texts,
                                 persist_fn=_after, label=f"Delete {what}")
        get_history().push(command)

    def _reorder_entry(self, prefix: str, source_id: str, target_id: str):
        """Poignée d'une page : la déplace, ce qui échange les numéros de clé (annulable)."""
        from core.text_sequences import group_texts, reordered_keys
        from ui.text_editor.text_commands import RenameTextKeysCmd
        if not self._project:
            return
        pages = group_texts(self._project, prefix)
        ids = [t.id for t in pages]
        if source_id not in ids or target_id not in ids:
            return
        pairs = reordered_keys(pages, ids.index(source_id), ids.index(target_id))
        if pairs:
            get_history().push(RenameTextKeysCmd(
                self._project, pairs, "Reorder pages", persist_fn=self._after_identity_change))

    def _delete_sequence(self, prefix: str):
        """Poubelle de l'en-tête : détruit la séquence, vide ses tables et ses boîtes (après confirmation)."""
        from core.text_sequences import consumers, group_texts
        from ui.text_editor.text_commands import DeleteSequenceCmd
        project = self._project
        texts = group_texts(project, prefix) if project else []
        if not texts:
            return
        users = ", ".join(c.name for c in consumers(project, prefix))
        if QMessageBox.question(
            self, label("txtpnl.delete_sequence_title"),
            label("txtpnl.delete_sequence_msg", name=prefix, n=len(texts), users=users or "—"),
        ) != QMessageBox.StandardButton.Yes:
            return

        def _after():
            self.changed.emit()
            for code in command.translation_langs:
                project.save_translation(code)
            self._selection = [t for t in self._selection if t in project.texts]
            self._table.refresh(select_ids=[t.id for t in self._selection])
            if not self._selection:
                self._current = None
                self.text_selected.emit(None)
            self.identity_changed.emit(self._current)

        command = DeleteSequenceCmd(project, prefix, persist_fn=_after)
        get_history().push(command)

    def create_at_path(self, path):
        self._add_text(list(path))

    def delete_from_library(self, texts):
        self._delete_texts(texts)

    def duplicate_text(self, source):
        if not self._project or source not in self._project.texts:
            return
        from core.text_sequences import sequence_of
        seq = sequence_of(source.key)
        duplicate, promoted = self._new_text_after(
            seq[0] if seq else source.key, source.path, source.content, source.scene)
        duplicate.note = source.note
        copied_translations = {}
        for code, values in self._project.translations.items():
            if source.id in values:
                values[duplicate.id] = values[source.id]
                copied_translations[code] = values[source.id]

        def _after():
            present = duplicate in self._project.texts
            for code, content in copied_translations.items():
                values = self._project.translations.setdefault(code, {})
                if present:
                    values[duplicate.id] = content
                else:
                    values.pop(duplicate.id, None)
                self._project.save_translation(code)
            self.changed.emit()
            self._table.refresh(select_ids=[duplicate.id] if present else [])
            if present:
                self._table.focus_entry(duplicate.id)
            self.identity_changed.emit(duplicate if present else None)

        label_ = f"Duplicate {source.key}"
        get_history().push(self._promoting(
            AddListItemCmd(self._project.texts, duplicate, persist_fn=_after, label=label_),
            promoted, label_))
