"""
ui/sound_mixer/state_machines.py — Les trois boîtes de l'écran Son.

L'écran édite TROIS assets indépendants (ROADMAP v0.8.7), qui ne se
ressemblent pas et ne s'affichent donc pas pareil :

    MusicBox   états + ARÊTES  → un graphe déplaçable + un inspecteur
    SoundBox   actions       → une TABLE actions × états
    JingleBox  idem

Une boîte d'actions n'a pas d'arêtes : un graphe y dessinerait des nœuds
sans liens. La table répond en revanche à la question qu'on se pose réellement
en tenant un pas de course — « et sur les cailloux, ça donne quoi ? » — parce
qu'elle se lit sur une ligne.

La MusicBox, elle, EN A — d'où le graphe déplaçable de `music_graph.py`. Ce
fichier n'en porte que l'hôte (`MusicMachinePanel`) et l'inspecteur qui règle
le nœud sélectionné (`MusicStateInspector`).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QCheckBox,
    QTableWidget, QHeaderView, QFrame,
    QLineEdit, QInputDialog, QMessageBox, QAbstractItemView,
)

from core.history import get_history, AddListItemCmd, RemoveListItemCmd, SetFieldCmd
from core.keybindings import get_keybindings
from ui.common.theme import C, T, QSS
from ui.common.widgets import W
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.sound_mixer.music_graph import MusicGraphView
from ui.sound_mixer.sound_commands import (
    RenameMusicStateCmd, AddBoxStateCmd, RemoveActionStateCmd,
    SetActionTargetCmd,
)
from core.models.sound_box import (
    MusicBox, MusicState, MusicTransition, ActionState,
    KIND_SOUND, TRANSITION_FADE, TRANSITION_CUT, INTENSITY_TARGETS,
)


# ══════════════════════════════════════════════════════════════════
#  Une machine d'EMPLACEMENTS — la table
# ══════════════════════════════════════════════════════════════════

class ActionMatrix(QWidget):
    """Actions en LIGNES, états en COLONNES — SoundBox et JingleBox.

    Une ACTION est ce qu'une frame d'animation cite (« PlayerWalk ») ; l'état
    courant dit vers quel échantillon elle pointe. L'orientation n'est pas
    indifférente : on ajoute des états bien plus souvent que des actions (un
    sol de plus, une ambiance de plus), et un tableau grandit mieux en largeur
    qu'en hauteur dans un panneau central.
    """
    changed = pyqtSignal()

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._machine = None
        self._assets: list[str] = []
        self._blocking = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        bar = QHBoxLayout(); bar.setSpacing(6)
        self._btn_action = W.btn_ghost(label("sndmix.add_action"))
        self._btn_action.setToolTip(tooltip(title=label("sndmix.add_action_title"), body=label("sndmix.add_action_tip")))
        self._btn_action.clicked.connect(self._add_action)
        self._btn_state = W.btn_ghost(label("sndmix.add_state"))
        self._btn_state.setToolTip(tooltip(title=label("sndmix.add_state_title"), body=label("sndmix.add_state_tip")))
        self._btn_state.clicked.connect(self._add_state)
        self._btn_del = W.btn_ghost(label("sndmix.del_column"))
        self._btn_del.setToolTip(tooltip(title=label("sndmix.remove_state_title"), body=label("sndmix.remove_state_tip")))
        self._btn_del.clicked.connect(self._del_state)
        bar.addWidget(self._btn_action); bar.addWidget(self._btn_state)
        bar.addWidget(self._btn_del); bar.addStretch()
        lbl_start = QLabel(label("sndmix.start"))
        lbl_start.setFont(QFont(T.UI, T.SM))
        lbl_start.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._combo_start = QComboBox()
        self._combo_start.setFont(QFont(T.UI, T.SM))
        self._combo_start.setStyleSheet(QSS.combobox)
        self._combo_start.setToolTip(tooltip(title=label("sndmix.start_title")))
        self._combo_start.currentIndexChanged.connect(self._on_start)
        bar.addWidget(lbl_start); bar.addWidget(self._combo_start)
        root.addLayout(bar)

        self._table = QTableWidget()
        self._table.setStyleSheet(QSS.tree_widget)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectColumns)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table, 1)

        self._hint = QLabel()
        self._hint.setFont(QFont(T.UI, T.SM))
        self._hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

    # ── Chargement ────────────────────────────────────────────────

    def load(self, box, assets: list[str]):
        self._machine, self._assets = box, list(assets)
        self._rebuild()

    def _rebuild(self):
        m = self._machine
        self._blocking = True
        actions = list(getattr(m, "actions", []) or [])
        states = list(getattr(m, "states", []) or [])
        self._table.clear()
        self._table.setRowCount(len(actions))
        self._table.setColumnCount(len(states))
        self._table.setHorizontalHeaderLabels([s.name for s in states])
        self._table.setVerticalHeaderLabels(actions)

        for r, action in enumerate(actions):
            for c, st in enumerate(states):
                combo = QComboBox()
                combo.setFont(QFont(T.UI, T.SM))
                combo.setStyleSheet(QSS.combobox)
                combo.setToolTip(tooltip(
                    title=label("sndmix.matrix_target_title"),
                    body=label("sndmix.matrix_target_tip", action=action, state=st.name),
                ))
                combo.addItem(label("common.none_dash"), "")
                for a in self._assets:
                    combo.addItem(a, a)
                cur = st.mapping.get(action, "") or ""
                idx = combo.findData(cur)
                if idx < 0 and cur:
                    # L'asset a disparu : on le GARDE visible plutôt que de
                    # retomber sur « rien », ce qui ferait mentir la case.
                    combo.addItem(label("common.missing_name", name=cur), cur)
                    idx = combo.count() - 1
                combo.setCurrentIndex(max(0, idx))
                combo.currentIndexChanged.connect(
                    lambda _i, rr=r, cc=c, cb=combo: self._on_cell(rr, cc, cb))
                self._table.setCellWidget(r, c, combo)

        self._combo_start.clear()
        for st in states:
            self._combo_start.addItem(st.name, st.name)
        i = self._combo_start.findData(getattr(m, "start", ""))
        self._combo_start.setCurrentIndex(i if i >= 0 else 0)
        self._blocking = False

        kind_word = label("sndmix.kind_sound" if self._kind == KIND_SOUND
                          else "sndmix.kind_jingle")
        self._hint.setText(
            label("sndmix.matrix_hint", kind=kind_word) if actions
            else label("sndmix.matrix_hint_empty")
        )

    # ── Édition ───────────────────────────────────────────────────

    def _after_edit(self):
        """Écriture STRUCTURELLE : une ligne ou une colonne en plus ou en moins."""
        self._rebuild()
        self.changed.emit()

    def _after_value(self):
        """Écriture SCALAIRE : la même grille, d'autres cibles.

        Ne reconstruit RIEN — une case est un QComboBox, et le détruire depuis
        son propre signal ferait tomber Qt. Un `resync` suffit à remonter ce
        qu'un undo a rétabli.
        """
        self._resync()
        self.changed.emit()

    def _resync(self):
        """Relit le modèle dans les widgets déjà en place."""
        m = self._machine
        if m is None:
            return
        self._blocking = True
        for r, action in enumerate(m.actions):
            for c, st in enumerate(m.states):
                combo = self._table.cellWidget(r, c)
                if combo is None:
                    continue
                i = combo.findData(st.mapping.get(action, "") or "")
                if i >= 0:
                    combo.setCurrentIndex(i)
        i = self._combo_start.findData(getattr(m, "start", ""))
        if i >= 0:
            self._combo_start.setCurrentIndex(i)
        self._blocking = False

    def _on_cell(self, row: int, col: int, combo: QComboBox):
        if self._blocking or not self._machine:
            return
        actions = self._machine.actions
        states = self._machine.states
        if row >= len(actions) or col >= len(states):
            return
        value = combo.currentData() or ""
        st, action = states[col], actions[row]
        old = st.mapping.get(action, "") or ""
        if old == value:
            return
        get_history().push(SetActionTargetCmd(st, action, old, value,
                                              self._after_value))

    def _add_action(self):
        if not self._machine:
            return
        name, ok = QInputDialog.getText(self, label("sndmix.new_action_title"),
                                        label("sndmix.new_action_prompt"))
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in self._machine.actions:
            QMessageBox.information(self, label("sndmix.dup_action_title"),
                                    label("sndmix.dup_action_text", name=name))
            return
        get_history().push(AddListItemCmd(
            self._machine.actions, name, self._after_edit,
            label=f"Ajouter l'action {name}"))

    def _add_state(self):
        if not self._machine:
            return
        name, ok = QInputDialog.getText(self, label("sndmix.new_state_title"),
                                        label("common.name_colon"))
        name = (name or "").strip()
        if not ok or not name:
            return
        if any(s.name == name for s in self._machine.states):
            QMessageBox.information(self, label("sndmix.dup_state_title"),
                                    label("sndmix.dup_state_text", name=name))
            return
        get_history().push(AddBoxStateCmd(
            self._machine, ActionState(name=name, mapping={}),
            self._after_edit))

    def _del_state(self):
        if not self._machine or not self._machine.states:
            return
        col = self._table.currentColumn()
        if col < 0 or col >= len(self._machine.states):
            QMessageBox.information(self, label("sndmix.no_column_title"),
                                    label("sndmix.no_column_text"))
            return
        get_history().push(RemoveActionStateCmd(
            self._machine, self._machine.states[col], self._after_edit))

    def _on_start(self, _i: int):
        if self._blocking or not self._machine:
            return
        new = self._combo_start.currentData() or ""
        if new == self._machine.start:
            return
        get_history().push(SetFieldCmd(
            self._machine, "start", self._machine.start, new,
            f"État de départ : {new}", self._after_value))




# ══════════════════════════════════════════════════════════════════
#  La machine MUSIQUE — le graphe
# ══════════════════════════════════════════════════════════════════

class MusicMachinePanel(QWidget):
    """Le graphe et sa barre d'outils. Rien d'autre.

    Les réglages d'un état vivent dans `MusicStateInspector`, colonne de
    droite : les mettre dans les nœuds demanderait un champ de saisie par
    réglage, donc un nœud dont la taille dépend de son contenu.
    """
    changed = pyqtSignal()
    # L'état sélectionné dans le graphe, ou None — l'écran le relaie à
    # l'inspecteur de droite.
    state_selected = pyqtSignal(object)
    # Un état vient d'être CRÉÉ : son nom auto attend d'être corrigé, et c'est
    # le seul cas où le focus doit partir dans l'inspecteur.
    state_created = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        bar = QHBoxLayout(); bar.setSpacing(4)
        b_add = W.btn_ghost(label("sndmix.add_state"))
        b_add.setToolTip(tooltip(title=label("sndmix.add_state_title"), body=label("sndmix.add_state_tip")))
        b_add.clicked.connect(self._add_state)
        b_del = W.btn_ghost("−")
        b_del.setToolTip(tooltip(title=label("sndmix.delete_selection_title"), shortcut=get_keybindings().resolve("common.delete")))
        b_del.clicked.connect(lambda: self.view.delete_selected())
        b_auto = W.btn_ghost(label("sndmix.auto_layout"))
        b_auto.setToolTip(tooltip(title=label("sndmix.auto_layout"), body=label("sndmix.auto_layout_tip")))
        b_auto.clicked.connect(lambda: self.view.auto_layout())
        bar.addWidget(b_add); bar.addWidget(b_del); bar.addWidget(b_auto)
        bar.addStretch()

        b_out = W.btn_ghost("−")
        b_out.setToolTip(tooltip(title=label("sndmix.zoom_out")))
        b_out.clicked.connect(lambda: self.view.zoom_by(1 / 1.15))
        self._zoom_lbl = QLabel("100 %")
        self._zoom_lbl.setFont(QFont(T.MONO, T.SM))
        self._zoom_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._zoom_lbl.setFixedWidth(44)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_in = W.btn_ghost("+")
        b_in.setToolTip(tooltip(title=label("sndmix.zoom_in")))
        b_in.clicked.connect(lambda: self.view.zoom_by(1.15))
        b_fit = W.btn_ghost("⤢")
        b_fit.setToolTip(tooltip(title=label("sndmix.fit_title"), shortcut=get_keybindings().resolve("common.fit")))
        b_fit.clicked.connect(lambda: self.view.fit())
        bar.addWidget(b_out); bar.addWidget(self._zoom_lbl)
        bar.addWidget(b_in); bar.addWidget(b_fit)
        root.addLayout(bar)

        self.view = MusicGraphView()
        self.view.changed.connect(self.changed)
        self.view.changed.connect(self._update_hint)
        self.view.selected.connect(self.state_selected)
        self.view.zoomed.connect(lambda z: self._zoom_lbl.setText(f"{z} %"))
        root.addWidget(self.view, 1)

        self._hint = QLabel()
        self._hint.setFont(QFont(T.UI, T.SM))
        self._hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

    def load(self, box: MusicBox):
        self.view.load(box)
        self._update_hint()

    def refresh(self):
        """Le modèle a été édité depuis l'inspecteur."""
        self.view.rebuild()
        self._update_hint()

    def _update_hint(self):
        """Le geste qui manque, et lui seul — il disparaît une fois fait."""
        g = self.view.graph
        if g is None or not g.states:
            self._hint.setText(label("sndmix.graph_hint_empty"))
        elif not g.transitions:
            self._hint.setText(label("sndmix.graph_hint_no_trans"))
        else:
            self._hint.clear()
        self._hint.setVisible(bool(self._hint.text()))

    def _add_state(self):
        if self.view.add_state() is not None:
            self._update_hint()
            self.state_created.emit()


# ══════════════════════════════════════════════════════════════════
#  L'inspecteur d'un état musical
# ══════════════════════════════════════════════════════════════════

class _TransitionRow(QFrame):
    """Une arête sortante, éditable en place.

    Une transition « depuis n'importe quel état » apparaît dans la liste de
    CHAQUE état : elle en sort réellement. Les cacher aurait rendu
    inéditables celles qu'on vient de basculer en globales.
    """
    removed = pyqtSignal(object)

    def __init__(self, tr: MusicTransition, owner: str, states: list[str],
                 commit, parent=None):
        super().__init__(parent)
        self.tr = tr
        self._owner = owner
        # La ligne n'écrit pas dans le modèle : elle DEMANDE l'écriture, et
        # l'inspecteur la passe par l'historique. Sans ça, régler une durée
        # échapperait à Ctrl+Z alors que la supprimer non.
        self._commit = commit
        self._blocking = True
        self.setObjectName("transition_row")
        self.setStyleSheet(
            f"QFrame#transition_row{{background:{C.BG_BASE};"
            f"border:1px solid {C.BORDER}; border-radius:4px;}}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        head = QHBoxLayout(); head.setSpacing(6)
        arrow = QLabel("→"); arrow.setFont(QFont(T.UI, T.MD))
        arrow.setStyleSheet(f"color:{C.ACCENT};")
        self._dst = QComboBox(); self._dst.setStyleSheet(QSS.combobox)
        for n in states:
            self._dst.addItem(n, n)
        self._dst.setCurrentIndex(max(0, self._dst.findData(tr.dst)))
        self._dst.setToolTip(tooltip(title=label("sndmix.destination_title")))
        self._dst.currentIndexChanged.connect(
            lambda _i: self._set("dst", self._dst.currentData() or ""))
        btn_del = W.btn_danger()
        btn_del.setToolTip(tooltip(title=label("sndmix.delete_transition_title")))
        btn_del.clicked.connect(lambda: self.removed.emit(self.tr))
        head.addWidget(arrow); head.addWidget(self._dst, 1); head.addWidget(btn_del)
        lay.addLayout(head)

        self._src = QComboBox(); self._src.setStyleSheet(QSS.combobox)
        self._src.addItem(label("sndmix.src_this", owner=owner), owner)
        self._src.addItem(label("sndmix.src_any"), "")
        self._src.setCurrentIndex(0 if tr.src else 1)
        self._src.setToolTip(tooltip(title=label("sndmix.source_title"), body=label("sndmix.source_tip")))
        self._src.currentIndexChanged.connect(
            lambda _i: self._set("src", self._src.currentData() or ""))
        W.row(label("sndmix.from"), self._src, lay, label_width=78)

        self._trigger = QLineEdit(tr.trigger)
        self._trigger.setStyleSheet(QSS.lineedit)
        self._trigger.setToolTip(tooltip(title=label("sndmix.trigger_title"), body=label("sndmix.trigger_tip")))
        self._trigger.editingFinished.connect(
            lambda: self._set("trigger", self._trigger.text().strip()))
        W.row(label("sndmix.trigger"), self._trigger, lay, label_width=78)

        self._kind = QComboBox(); self._kind.setStyleSheet(QSS.combobox)
        self._kind.addItem(label("sndmix.fade"), TRANSITION_FADE)
        self._kind.addItem(label("sndmix.cut"), TRANSITION_CUT)
        self._kind.setCurrentIndex(max(0, self._kind.findData(tr.kind)))
        self._kind.setToolTip(tooltip(title=label("sndmix.transition_kind_title"), body=label("sndmix.kind_tip")))
        self._kind.currentIndexChanged.connect(self._on_kind)
        W.row(label("sndmix.transition"), self._kind, lay, label_width=78)

        self._frames = QSpinBox(); self._frames.setRange(2, 255)
        self._frames.setValue(tr.frames); self._frames.setSuffix(label("sndmix.frames_suffix"))
        self._frames.setStyleSheet(QSS.spinbox)
        # En frames et non en ms : c'est l'unité du runtime et celle des
        # transitions de scène (v0.6.2). Une durée ne s'écrit pas de deux façons.
        self._frames.setToolTip(tooltip(title=label("sndmix.duration_title"), body=label("sndmix.frames_tip")))
        self._frames.valueChanged.connect(
            lambda v: self._set("frames", int(v)))
        W.row(label("sndmix.duration"), self._frames, lay, label_width=78)

        self._sync_frames()
        self._blocking = False

    def _on_kind(self, _i: int):
        self._set("kind", self._kind.currentData())
        self._sync_frames()

    def _sync_frames(self):
        # Une coupe attend la fin du motif : sa durée n'est pas réglable, et un
        # champ actif laisserait croire le contraire.
        self._frames.setEnabled(self.tr.kind != TRANSITION_CUT)

    def _set(self, attr: str, value):
        if self._blocking or getattr(self.tr, attr) == value:
            return
        self._commit(self.tr, attr, getattr(self.tr, attr), value,
                     f"Transition : {attr}")

    def resync(self):
        """Relit le modèle sans reconstruire — après un undo, typiquement."""
        self._blocking = True
        self._dst.setCurrentIndex(max(0, self._dst.findData(self.tr.dst)))
        self._src.setCurrentIndex(0 if self.tr.src else 1)
        self._trigger.setText(self.tr.trigger)
        self._kind.setCurrentIndex(max(0, self._kind.findData(self.tr.kind)))
        self._frames.setValue(self.tr.frames)
        self._sync_frames()
        self._blocking = False


class MusicStateInspector(QWidget):
    """Ce que règle l'état sélectionné dans le graphe."""
    changed = pyqtSignal()          # une valeur a changé — sauvegarder
    restructured = pyqtSignal()     # le graphe est à redessiner

    def __init__(self, parent=None):
        super().__init__(parent)
        self._graph: Optional[MusicBox] = None
        self._state: Optional[MusicState] = None
        self._musics: list[str] = []
        self._rows: list[_TransitionRow] = []
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        W.section(label("sndmix.sec_state"), root)
        self._name = QLineEdit(); self._name.setStyleSheet(QSS.lineedit)
        self._name.editingFinished.connect(self._on_rename)
        W.row(label("sndmix.name"), self._name, root)

        self._start = QCheckBox(label("sndmix.start_state"))
        self._start.setStyleSheet(QSS.checkbox)
        self._start.setToolTip(tooltip(title=label("sndmix.start_state_title"), body=label("sndmix.start_state_tip")))
        self._start.toggled.connect(self._on_start)
        root.addWidget(self._start)

        W.section(label("sndmix.sec_music"), root)
        self._music = QComboBox(); self._music.setStyleSheet(QSS.combobox)
        self._music.currentIndexChanged.connect(
            lambda _i: self._set("music", self._music.currentData() or ""))
        W.row(label("sndmix.track"), self._music, root)

        self._loop = QCheckBox(label("common.loop")); self._loop.setStyleSheet(QSS.checkbox)
        self._loop.setToolTip(tooltip(title=label("sndmix.loop_title"), body=label("sndmix.loop_tip")))
        self._loop.toggled.connect(lambda v: self._set("loop", bool(v)))
        root.addWidget(self._loop)

        self._level = QSpinBox(); self._level.setRange(0, 100)
        self._level.setSuffix(" %"); self._level.setStyleSheet(QSS.spinbox)
        self._level.setToolTip(tooltip(title=label("sndmix.level_title")))
        self._level.valueChanged.connect(lambda v: self._set("level", int(v)))
        W.row(label("sndmix.level"), self._level, root)

        self._itarget = QComboBox(); self._itarget.setStyleSheet(QSS.combobox)
        for t in INTENSITY_TARGETS:
            self._itarget.addItem(t, t)
        self._itarget.setToolTip(tooltip(title=label("sndmix.intensity_title"), body=label("sndmix.intensity_tip")))
        self._itarget.currentIndexChanged.connect(
            lambda _i: self._set("intensity_target", self._itarget.currentData()))
        W.row(label("sndmix.intensity"), self._itarget, root)

        self._ivalue = QSpinBox(); self._ivalue.setRange(50, 200)
        self._ivalue.setSuffix(" %"); self._ivalue.setStyleSheet(QSS.spinbox)
        self._ivalue.setToolTip(tooltip(title=label("sndmix.intensity_value_title"), body=label("sndmix.ivalue_tip")))
        self._ivalue.valueChanged.connect(
            lambda v: self._set("intensity", int(v)))
        W.row(label("sndmix.value"), self._ivalue, root)

        W.section(label("sndmix.sec_transitions"), root)
        self._trs_box = QWidget()
        self._trs_box.setStyleSheet("background:transparent;")
        self._trs_lay = QVBoxLayout(self._trs_box)
        self._trs_lay.setContentsMargins(0, 0, 0, 0)
        self._trs_lay.setSpacing(6)
        root.addWidget(self._trs_box)

        self._btn_tr = W.btn_ghost(label("sndmix.add_transition"))
        self._btn_tr.setToolTip(tooltip(title=label("sndmix.add_transition_title"), body=label("sndmix.add_transition_tip")))
        self._btn_tr.clicked.connect(self._add_tr)
        root.addWidget(self._btn_tr)
        root.addStretch()

        for w in (self._name, self._start, self._music, self._loop,
                  self._level, self._itarget, self._ivalue, self._btn_tr):
            w.setEnabled(False)

    # ── Chargement ────────────────────────────────────────────────

    def set_musics(self, musics: list[str]):
        self._musics = list(musics)

    def load(self, box: Optional[MusicBox],
             state: Optional[MusicState]):
        """Recharge SEULEMENT si l'état montré change.

        Le graphe se redessine à chaque édition ; sans ce garde-fou, un
        spinbox se rechargerait sous les doigts de celui qui le règle.
        """
        if box is self._graph and state is self._state:
            return
        self._graph, self._state = box, state
        self._blocking = True
        for w in (self._name, self._start, self._music, self._loop,
                  self._level, self._itarget, self._ivalue, self._btn_tr):
            w.setEnabled(state is not None)
        if state is not None:
            self._name.setText(state.name)
            self._start.setChecked(box is not None
                                   and box.start == state.name)
            self._music.clear()
            self._music.addItem(label("common.none_dash"), "")
            for m in self._musics:
                self._music.addItem(m, m)
            i = self._music.findData(state.music)
            if i < 0 and state.music:
                # La piste a disparu : on la GARDE visible plutôt que de
                # retomber sur « rien », ce qui ferait mentir le champ.
                self._music.addItem(label("common.missing_name", name=state.music), state.music)
                i = self._music.count() - 1
            self._music.setCurrentIndex(max(0, i))
            self._loop.setChecked(state.loop)
            self._level.setValue(state.level)
            j = self._itarget.findData(state.intensity_target)
            self._itarget.setCurrentIndex(j if j >= 0 else 0)
            self._ivalue.setValue(max(50, min(200, state.intensity)))
        else:
            self._name.clear()
        self._blocking = False
        self._rebuild_trs()

    def focus_name(self):
        """Après une création : le nom auto est sélectionné, prêt à corriger."""
        self._name.setFocus()
        self._name.selectAll()

    # ── Transitions ───────────────────────────────────────────────

    def _after_edit(self):
        """Écriture STRUCTURELLE : la liste des arêtes ou un nom a changé."""
        self._rebuild_trs()
        self.changed.emit()
        self.restructured.emit()

    def _after_value(self):
        """Écriture SCALAIRE : les mêmes lignes, d'autres valeurs.

        Ne reconstruit RIEN — un widget détruit pendant qu'on le règle ferait
        tomber Qt, et un `resync` suffit à remonter ce qu'un undo a rétabli.
        """
        self.resync()
        self.changed.emit()
        self.restructured.emit()

    def resync(self):
        """Relit le modèle dans les widgets, sans en détruire aucun."""
        st = self._state
        if st is None:
            return
        self._blocking = True
        self._name.setText(st.name)
        self._start.setChecked(self._graph is not None
                               and self._graph.start == st.name)
        i = self._music.findData(st.music)
        if i >= 0:
            self._music.setCurrentIndex(i)
        self._loop.setChecked(st.loop)
        self._level.setValue(st.level)
        j = self._itarget.findData(st.intensity_target)
        self._itarget.setCurrentIndex(j if j >= 0 else 0)
        self._ivalue.setValue(max(50, min(200, st.intensity)))
        self._blocking = False
        for row in self._rows:
            row.resync()

    def _commit_tr(self, tr, attr: str, old, new, label: str):
        get_history().push(SetFieldCmd(tr, attr, old, new, label,
                                       self._after_value))

    def _rebuild_trs(self):
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        g, st = self._graph, self._state
        if g is None or st is None:
            return
        names = [s.name for s in g.states]
        for tr in g.transitions:
            if tr.src not in ("", st.name):
                continue
            row = _TransitionRow(tr, st.name, names, self._commit_tr)
            row.removed.connect(self._del_tr)
            self._trs_lay.addWidget(row)
            self._rows.append(row)

    def _add_tr(self):
        g, st = self._graph, self._state
        if g is None or st is None:
            return
        from core.command_dispatcher import unique_name
        taken = [t.trigger for t in g.transitions if t.trigger]
        # Vers un AUTRE état par défaut : une transition d'un état vers
        # lui-même ne changerait rien à ce qui joue.
        dst = next((s.name for s in g.states if s.name != st.name), st.name)
        tr = MusicTransition(src=st.name, dst=dst,
                             trigger=unique_name("trigger", taken))
        get_history().push(AddListItemCmd(g.transitions, tr, self._after_edit,
                                          label="Ajouter une transition"))

    def _del_tr(self, tr: MusicTransition):
        g = self._graph
        if g is None or tr not in g.transitions:
            return
        get_history().push(RemoveListItemCmd(
            g.transitions, tr, self._after_edit,
            label="Supprimer une transition"))

    # ── Édition de l'état ─────────────────────────────────────────

    def _set(self, attr: str, value):
        if self._blocking or self._state is None:
            return
        old = getattr(self._state, attr)
        if old == value:
            return
        # Les commandes consécutives sur le même champ fusionnent : maintenir
        # la flèche d'un spinbox ne doit pas remplir l'historique.
        get_history().push(SetFieldCmd(self._state, attr, old, value,
                                       f"État : {attr}", self._after_value))

    def _on_rename(self):
        g, st = self._graph, self._state
        if self._blocking or g is None or st is None:
            return
        new = self._name.text().strip()
        if not new or new == st.name:
            self._name.setText(st.name)
            return
        if g.state(new) is not None:
            # Deux états homonymes DANS une boîte rendraient l'appel ambigu.
            # Revert silencieux, pas de pop-up.
            self._name.setText(st.name)
            return
        # Composée : le nom est cité par les arêtes et par l'état de départ.
        get_history().push(RenameMusicStateCmd(g, st, new, self._after_edit))

    def _on_start(self, checked: bool):
        g, st = self._graph, self._state
        if self._blocking or g is None or st is None:
            return
        if checked:
            get_history().push(SetFieldCmd(
                g, "start", g.start, st.name,
                f"État de départ : {st.name}", self._after_value))
            return
        if g.start == st.name:
            # Décocher laisserait la machine sans état initial : le seul geste
            # possible est de désigner un AUTRE état.
            self._blocking = True
            self._start.setChecked(True)
            self._blocking = False
