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

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal

from core.models.text import MAX_DEPTH, SEP, norm_path, repath_segment
from core.history import (
    get_history, SetFieldCmd, AddListItemCmd, RemoveListItemsCmd,
)
from ui.common.theme import QSS
from ui.common.labels import label
from ui.text_editor.text_table import TextTable
from ui.text_editor.text_workbench import TextWorkbench
from ui.text_editor.text_commands import (
    RenameTextKeyCmd, SetTextPathCmd, RelinkTextKeyCmd, SetTranslationCmd,
)


class TextPanel(QWidget):
    """Table des `Text` + éditeur du contenu sélectionné."""

    text_selected = pyqtSignal(object)      # Text | None (l'inspecteur en suit un)
    changed = pyqtSignal()                  # contenu modifié → persistance
    identity_changed = pyqtSignal(object)   # clé/chemin modifiés
    parsed = pyqtSignal(object)             # ParsedText de l'entrée courante
    preview_font_changed = pyqtSignal(object)   # Font | None

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

        split = QSplitter(Qt.Orientation.Vertical)
        split.setStyleSheet(QSS.splitter)
        split.setChildrenCollapsible(False)
        self._table = TextTable()
        self._bench = TextWorkbench()
        split.addWidget(self._table)
        split.addWidget(self._bench)
        split.setSizes([300, 300])
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        root.addWidget(split, 1)

        self._table.selection_changed.connect(self._on_selection)
        self._table.key_edited.connect(self._on_table_key)
        self._table.group_renamed.connect(self._on_group_renamed)
        self._table.add_asked.connect(self._add_text)
        self._table.delete_asked.connect(self._delete_texts)

        self._bench.content_committed.connect(self._on_content_committed)
        self._bench.active_lang_changed.connect(self._on_lang_changed)
        self._bench.key_committed.connect(self._on_bench_key)
        self._bench.path_committed.connect(
            lambda lvl, seg: self._repath(self._selection, lvl, seg))
        self._bench.relink_asked.connect(self._relink_key)
        self._bench.parsed.connect(self._on_parsed)
        self._bench.preview_font_changed.connect(self.preview_font_changed.emit)

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
        """Relais du Finder de textes vers la table centrale."""
        self._table.set_folder_filter(path)

    def rename_selected_path(self, level: int, segment: str) -> None:
        """Renommage d'un niveau depuis l'inspecteur de texte."""
        if self._selection:
            self._repath(self._selection, level, segment)

    def rename_folder(self, path, segment: str) -> None:
        """Relais du renommage en place demandé depuis le Finder."""
        self._on_group_renamed(path, segment)

    def rename_key(self, t, typed: str) -> None:
        """Renommage de clé demandé depuis le Finder."""
        if self._rename_key(t, typed):
            self._table.refresh()

    # ── Sélection ─────────────────────────────────────────────────

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

    def _on_bench_key(self, typed: str):
        if len(self._selection) != 1:
            return
        if not self._rename_key(self._selection[0], typed):
            self._bench.reset_key_field()

    def _rename_key(self, t, raw: str) -> bool:
        """Renomme la clé — refuse le vide et les doublons.

        Point unique du renommage MANUEL : la cellule de la table et le champ
        de l'atelier écrivent la même chose (la clé se détache du rangement),
        il ne doit pas y avoir deux versions de cette règle."""
        new = (raw or "").strip()
        if not self._project or not new or new == t.key:
            return False
        old, old_auto = t.key, t.auto_key
        if not self._project.rename_text_key(t, new):
            QMessageBox.warning(
                self, label("txtpnl.invalid_key_title"),
                label("txtpnl.invalid_key_msg", name=new))
            return False
        get_history().push(RenameTextKeyCmd(
            self._project, t, old, new, old_auto,
            persist_fn=self._after_identity_change,
        ))
        return True

    def _relink_key(self):
        """Ré-accroche une clé nommée à la main à son rangement."""
        if len(self._selection) != 1 or not self._project:
            return
        get_history().push(RelinkTextKeyCmd(
            self._project, self._selection[0],
            persist_fn=self._after_identity_change))

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
        self._table.refresh()
        self._bench.set_texts(self._selection)
        self.identity_changed.emit(self._current)

    # ── CRUD ──────────────────────────────────────────────────────

    def _add_text(self):
        """Crée un texte DANS le rangement courant — seul moyen de créer une
        catégorie, et évite de re-ranger chaque entrée après coup."""
        if not self._project:
            return
        t = self._project.new_text(content="", path=self._table.selected_path())

        def _after():
            self.changed.emit()
            self._table.refresh(
                select_ids=[t.id] if t in self._project.texts else [])

        # new_text a déjà ajouté l'entrée : execute() est un no-op au premier
        # passage, undo la retire, redo la remet.
        get_history().push(AddListItemCmd(
            self._project.texts, t, persist_fn=_after,
            label=f"New text {t.key}",
        ))

    def _delete_texts(self):
        """Supprime la sélection, après confirmation."""
        texts = list(self._selection)
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
            alive = [t.id for t in texts if t in self._project.texts]
            self._selection = [t for t in texts if t in self._project.texts]
            self._table.refresh(select_ids=alive)
            if not alive:
                self._current = None
                self.text_selected.emit(None)

        get_history().push(RemoveListItemsCmd(
            self._project.texts, texts, persist_fn=_after,
            label=f"Delete {what}",
        ))
