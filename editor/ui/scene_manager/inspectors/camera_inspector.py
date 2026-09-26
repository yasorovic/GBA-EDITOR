"""CameraInspector — une caméra PRÉCISE, possédée par la scène sélectionnée.

Reçoit une scène et une caméra (choisie dans le scene tree, ou l'icône cliquée
dans le canvas — cf. `CameraSelection`) et édite CETTE caméra. Deux états :

- **`camera` est `None`** — la scène n'a encore aucune caméra, elle est fixe à
  l'origine, sans bornes ni suivi, sans entrée dans `scene.cameras`. Les
  réglages sont visibles mais éteints ;
- **`camera` est un objet réel** — tout est éditable. Elle n'appartient qu'à
  CETTE scène (révisé le 2026-08-24 — ce n'est plus un asset de projet
  réutilisable, cf. `changelog-archive/v0.6.md`).

Le passage du premier au second n'est pas un bouton « créer » dans CET
inspecteur : il se produit au premier réglage, y compris le déplacement du
cadre dans le canvas (`Project.ensure_scene_camera`) — la création explicite
se fait depuis le scene tree (bouton **+**).

Le combo « Starting camera » est un contrôle SÉPARÉ : il choisit laquelle des
caméras de la scène est celle de démarrage (`scene.camera`), indépendamment de
celle affichée/éditée ici.

Ce que l'inspecteur ne propose pas : rotation, zoom, projection. Un calque
régulier ne sait ni tourner ni se mettre à l'échelle (ce sont les calques
affines, v2.0) — les proposer promettrait un rendu que le matériel ne produit
pas. Le viewport, lui, EST proposé (carte Transform, `frame_w`/`frame_h`,
réglé le 2026-08-24) : WIN0 appartient désormais à la caméra active, WIN1
reste à la scène (`Scene.windows`) — cf. `core/models/camera.py`.
"""
from __future__ import annotations
from ui.common.labels import label
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea,
    QPushButton, QMessageBox, QInputDialog,
)
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtCore import pyqtSignal

from core.models.camera import Camera, CAM_FIXED, CAM_FOLLOW, CAM_SCRIPT
from core.models.scene import Scene
from core.project import Project
from ui.common.theme import C, T, QSS
from ui.common.responsive import InspectorScrollArea
from ui.common.icons import COLOR_SCRIPT
from ui.common.widgets import ScriptSlot, ScriptPickerPopup, CollapsibleCard, NotesEdit, W
from ui.common.notice import notice

_MODES = [
    (CAM_FIXED,  'caminsp.fixed'),
    (CAM_FOLLOW, 'caminsp.follow_an_actor'),
    (CAM_SCRIPT, 'caminsp.script_driven'),
]

_NO_TARGET = 'common.none_paren'
_DEFAULT_CAMERA = 'common.default_paren'


class CameraInspector(QWidget):
    """Édite une caméra précise, possédée par la scène sélectionnée."""
    changed = pyqtSignal()
    # Position ou frame édités ICI (pas par drag canvas) — le canvas doit
    # suivre. Symétrique de `update_position`, qui fait le chemin inverse.
    camera_moved = pyqtSignal(object)   # Camera

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene: Optional[Scene] = None
        self._camera: Optional[Camera] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self._script_open_fn = None

        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        scroll.setWidget(inner)

        # ── Quelle caméra démarre la scène ────────────────────────
        # Renommer CETTE caméra se fait dans l'en-tête partagé (AssetHeaderBar,
        # cf. DynamicInspector._on_header_rename) — même contrat que
        # Scene/Actor/Prefab, pas de second champ « name » ici.
        camera_card = CollapsibleCard(label('caminsp.this_camera'))
        start_row = QHBoxLayout()
        start_row.setSpacing(6)
        start_lbl = QLabel(label('caminsp.starting_camera'))
        start_lbl.setFont(QFont(T.UI, T.XS))
        start_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        start_row.addWidget(start_lbl)
        self._combo_camera = QComboBox()
        self._combo_camera.setFont(QFont(T.UI, T.MD))
        self._combo_camera.setStyleSheet(QSS.combobox)
        self._combo_camera.setToolTip(
            label('caminsp.starting_camera_tip')
        )
        self._combo_camera.currentIndexChanged.connect(self._on_camera_picked)
        start_row.addWidget(self._combo_camera, 1)
        camera_card.body_layout.addLayout(start_row)

        self._lbl_users = QLabel("")
        self._lbl_users.setFont(QFont(T.UI, T.XS))
        self._lbl_users.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._lbl_users.setWordWrap(True)
        camera_card.body_layout.addWidget(self._lbl_users)
        layout.addWidget(camera_card)

        # ── Note libre — même carte partagée qu'Actor/Scène ───────
        notes_card = CollapsibleCard(label('common.note'))
        self._notes_edit = NotesEdit()
        self._notes_edit.committed.connect(self._on_notes_changed)
        notes_card.body_layout.addWidget(self._notes_edit)
        layout.addWidget(notes_card)

        # ── Mode ──────────────────────────────────────────────────
        mode_card = CollapsibleCard(label('common.mode'))
        self._mode_combo = QComboBox()
        self._mode_combo.setFont(QFont(T.UI, T.MD))
        self._mode_combo.setStyleSheet(QSS.combobox)
        for _, lbl_key in _MODES:
            self._mode_combo.addItem(label(lbl_key))
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_card.body_layout.addWidget(self._mode_combo)
        notice("camera.mode", self._mode_combo, mode_card.body_layout)
        layout.addWidget(mode_card)

        # Largeur de colonne des libellés, mesurée sur le plus long du panneau —
        # même approche que l'ActorInspector (une valeur fixe tronquerait selon
        # la fonte de la machine).
        _lbl_w = max(
            QFontMetrics(QFont(T.UI, T.SM)).horizontalAdvance(t)
            for t in (label('common.position'), label('caminsp.origin'), label('caminsp.margin'), label('common.frame'), label('common.size'))
        ) + 4

        # ── Transform : position (canvas ↔ inspecteur) + frame écran ──
        transform_card = CollapsibleCard(label('caminsp.transform'))
        # Position — plage 0..32767 (s16, comme les bornes du monde), pas de 8 px.
        self._pos_x = W.spinbox(0, min_v=0, max_v=32767, step=8)
        self._pos_y = W.spinbox(0, min_v=0, max_v=32767, step=8)
        W.pair(label('common.position'), "X", C.AXIS_X, self._pos_x, "Y", C.AXIS_Y, self._pos_y,
               transform_card.body_layout, label_width=_lbl_w)
        notice("camera.position", self._pos_x, transform_card.body_layout)

        self._frame_w = W.spinbox(240, min_v=1, max_v=240)
        self._frame_h = W.spinbox(160, min_v=1, max_v=160)
        W.pair(label('common.frame'), "W", C.AXIS_X, self._frame_w, "H", C.AXIS_Y, self._frame_h,
               transform_card.body_layout, label_width=_lbl_w)

        self._lbl_win_budget = QLabel("")
        self._lbl_win_budget.setFont(QFont(T.UI, T.XS))
        self._lbl_win_budget.setWordWrap(True)
        transform_card.body_layout.addWidget(self._lbl_win_budget)

        notice("camera.frame", self._frame_w, transform_card.body_layout)
        layout.addWidget(transform_card)

        # ── Suivi (visible en mode follow) ────────────────────────
        self._follow_group = CollapsibleCard(label('caminsp.follow_an_actor'))
        fg = self._follow_group.body_layout

        self._follow_combo = QComboBox()
        self._follow_combo.setFont(QFont(T.UI, T.MD))
        self._follow_combo.setStyleSheet(QSS.combobox)
        self._follow_combo.setToolTip(
            label('caminsp.actor_local_note'))
        self._follow_combo.currentTextChanged.connect(self._on_follow_changed)
        fg.addWidget(self._follow_combo)

        self._margin_x = W.spinbox(0, min_v=0, max_v=120)
        self._margin_y = W.spinbox(0, min_v=0, max_v=120)
        W.pair(label('caminsp.margin'), "X", C.AXIS_X, self._margin_x, "Y", C.AXIS_Y, self._margin_y,
               fg, label_width=_lbl_w)
        self._margin_x.valueChanged.connect(self._on_margins_changed)
        self._margin_y.valueChanged.connect(self._on_margins_changed)
        notice("camera.margin", self._margin_x, fg)

        layout.addWidget(self._follow_group)

        # ── Bornes du monde (rect : origine + taille) ──────────────
        bounds_card = CollapsibleCard(label('caminsp.world_bounds_0_unlimited'))
        # Taille — bornes monde jusqu'à 32767 (s16) → scroll caméra max = 32767 -
        # screen.width (32527 en X, 32607 en Y).
        self._bounds_w = W.spinbox(0, min_v=0, max_v=32767, step=8)
        self._bounds_h = W.spinbox(0, min_v=0, max_v=32767, step=8)
        W.pair(label('common.size'), "W", C.AXIS_X, self._bounds_w, "H", C.AXIS_Y, self._bounds_h,
               bounds_card.body_layout, label_width=_lbl_w)
        # Origine de la zone scrollable — 0 = le monde commence au bord de l'écran.
        # Presque toujours 0, exposé pour rester cohérent avec le rect camera.bound.
        self._bounds_x = W.spinbox(0, min_v=0, max_v=32767, step=8)
        self._bounds_y = W.spinbox(0, min_v=0, max_v=32767, step=8)
        W.pair(label('caminsp.origin'), "X", C.AXIS_X, self._bounds_x, "Y", C.AXIS_Y, self._bounds_y,
               bounds_card.body_layout, label_width=_lbl_w)
        self._bounds_w.valueChanged.connect(self._on_bounds_changed)
        self._bounds_h.valueChanged.connect(self._on_bounds_changed)
        self._bounds_x.valueChanged.connect(self._on_bounds_changed)
        self._bounds_y.valueChanged.connect(self._on_bounds_changed)

        self._btn_recalc = QPushButton(label('caminsp.recompute_from_backgrounds'))
        self._btn_recalc.setFont(QFont(T.UI, T.SM))
        self._btn_recalc.setStyleSheet(QSS.button_ghost)
        self._btn_recalc.setToolTip(
            label('caminsp.prefill_tip')
        )
        self._btn_recalc.clicked.connect(self._recalc_bounds)
        bounds_card.body_layout.addWidget(self._btn_recalc)

        notice("camera.bounds", self._bounds_w, bounds_card.body_layout)
        layout.addWidget(bounds_card)

        # ── Script de caméra ──────────────────────────────────────
        script_card = CollapsibleCard(label('caminsp.camera_script'))
        self._script_slot = ScriptSlot(
            add_label    = label('caminsp.add_a_camera_script'),
            accent_color = COLOR_SCRIPT,
            hint         = "on_start · on_update",
        )
        self._script_slot.set_callbacks(
            on_add   = self._script_new,
            on_open  = self._script_open,
            on_clear = self._script_clear,
        )
        script_card.body_layout.addWidget(self._script_slot)
        notice("camera.script", self._script_slot, script_card.body_layout)
        layout.addWidget(script_card)

        layout.addStretch()

        # Tout ce qui n'a de sens qu'avec une caméra RÉELLE.
        self._editors = (
            self._mode_combo, self._follow_group, self._margin_x, self._margin_y,
            self._bounds_w, self._bounds_h, self._bounds_x, self._bounds_y,
            self._btn_recalc, self._script_slot,
            self._pos_x, self._pos_y, self._frame_w, self._frame_h,
            self._notes_edit,
        )
        self._pos_x.valueChanged.connect(self._on_transform_changed)
        self._pos_y.valueChanged.connect(self._on_transform_changed)
        self._frame_w.valueChanged.connect(self._on_transform_changed)
        self._frame_h.valueChanged.connect(self._on_transform_changed)

    def set_script_open_fn(self, fn):
        self._script_open_fn = fn

    # ── Chargement ────────────────────────────────────────────────

    def load(self, scene: Scene, camera: Optional[Camera], project: Project):
        self._scene = scene
        self._camera = camera
        self._project = project
        self._refresh()

    def _refresh(self):
        self._blocking = True
        try:
            cam = self._camera
            scene = self._scene

            self._combo_camera.clear()
            self._combo_camera.addItem(label(_DEFAULT_CAMERA), "")
            for c in (scene.cameras if scene else []):
                self._combo_camera.addItem(c.name, c.name)
            idx = self._combo_camera.findData(getattr(scene, "camera", "") or "")
            self._combo_camera.setCurrentIndex(max(0, idx))

            for w in self._editors:
                w.setEnabled(cam is not None)

            self._lbl_users.setText(
                "" if cam is not None else
                label('caminsp.no_camera_yet'))

            mode = cam.mode if cam else CAM_FIXED
            self._mode_combo.setCurrentIndex(
                next((i for i, (m, _) in enumerate(_MODES) if m == mode), 0))
            self._follow_group.setVisible(mode == CAM_FOLLOW)

            self._follow_combo.clear()
            self._follow_combo.addItem(label(_NO_TARGET), "")
            for actor in (self._scene.actors if self._scene else []):
                self._follow_combo.addItem(actor.name, actor.name)
            target = cam.follow_target if cam else ""
            if target and self._follow_combo.findData(target) < 0:
                # Cible introuvable dans cette scène (acteur supprimé/renommé
                # sans passer par ici) : la garder visible plutôt que de la
                # réécrire en silence — le validateur le signale déjà.
                self._follow_combo.addItem(label('caminsp.target_not_in_this_scene', target=target), target)
                self._follow_combo.setCurrentIndex(self._follow_combo.count() - 1)
            else:
                self._follow_combo.setCurrentIndex(
                    max(0, self._follow_combo.findData(target)))

            self._margin_x.setValue(cam.margin_x if cam else 40)
            self._margin_y.setValue(cam.margin_y if cam else 20)
            self._bounds_w.setValue((cam.bounds_w if cam else 0) or 0)
            self._bounds_h.setValue((cam.bounds_h if cam else 0) or 0)
            self._bounds_x.setValue((cam.bounds_x if cam else 0) or 0)
            self._bounds_y.setValue((cam.bounds_y if cam else 0) or 0)
            self._notes_edit.set_text_silent(cam.notes if cam else "")
            self._pos_x.setValue(cam.x if cam else 0)
            self._pos_y.setValue(cam.y if cam else 0)
            self._frame_w.setValue(cam.frame_w if cam else 240)
            self._frame_h.setValue(cam.frame_h if cam else 160)
            self._refresh_window_budget()

            script = (cam.script if cam else "") or ""
            if script:
                self._script_slot.set_script(script.rsplit("/", 1)[-1])
            else:
                self._script_slot.clear_script()
        finally:
            self._blocking = False

    def _refresh_window_budget(self):
        """Même chiffre que la carte Windows du Scene inspector — une seule
        fonction (`window_alloc.scene_window_budget`), pour que l'auteur voie
        le coût AVANT de réduire le cadre, pas seulement après un warning."""
        if not self._scene:
            self._lbl_win_budget.setText("")
            return
        from codegen.window_alloc import scene_window_budget
        used, total = scene_window_budget(self._scene)
        over = used > total
        self._lbl_win_budget.setStyleSheet(
            f"color:{C.ACCENT_RED if over else C.TEXT_MUTED};")
        msg = label('caminsp.windows_used', used=used, total=total)
        if over:
            msg = label('caminsp.windows_over_budget', used=used, total=total)
        self._lbl_win_budget.setText(msg)

    def update_position(self, camera, x: int, y: int):
        """Appelé en direct par le canvas pendant un drag (cf. SceneEditor,
        même rôle que ActorInspector.update_position) : pas de `_refresh()`
        complet, juste les deux spinboxes concernées — et seulement si la
        caméra déplacée est bien celle affichée ici."""
        if self._blocking or camera is not self._camera:
            return
        self._blocking = True
        self._pos_x.setValue(x)
        self._pos_y.setValue(y)
        self._blocking = False

    # ── Mutations ─────────────────────────────────────────────────

    def _mutable(self) -> Optional[Camera]:
        """La caméra à éditer, matérialisée si la scène n'en avait encore
        aucune (état implicite, `self._camera is None`). Une fois réelle, la
        référence tenue par l'inspecteur devient cette caméra-là.

        Seule la MATÉRIALISATION exige un projet (elle passe par
        `ensure_scene_camera`) : une caméra déjà réelle s'édite sans, ce qui
        garde l'édition symétrique des autres inspecteurs (la persistance, elle,
        est déjà gardée dans `_save`)."""
        if self._camera is not None:
            return self._camera
        if not self._scene or not self._project:
            return None
        self._camera = self._project.ensure_scene_camera(self._scene)
        return self._camera

    def _save(self):
        """Persiste la scène — la caméra vit dans SON JSON (plus de fichier
        séparé). Donné en `persist_fn` aux commandes : c'est leur `execute`/`undo`
        qui sauve, pour que l'écriture disque suive fidèlement l'état."""
        if self._project and self._scene:
            self._project.save_scene(self._scene)

    def _edit(self, fields, label: str, refresh: bool = True) -> bool:
        """Applique un GROUPE de champs comme UNE entrée d'historique annulable.

        `fields` = [(obj, nom, valeur), …]. Seuls les champs qui CHANGENT
        réellement produisent une commande (garde no-op, comme `_set` des autres
        inspecteurs). Un seul champ modifié → `SetFieldCmd` (les frappes du même
        champ fusionnent) ; plusieurs → `MacroCmd` atomique (un geste = un
        Ctrl+Z). Rend True si quelque chose a changé.

        C'est ce qui rend la caméra ANNULABLE : l'édition ne mute plus l'objet
        en direct, elle passe par l'historique comme l'actor et l'UIRegion."""
        from core.history import get_history, SetFieldCmd, MacroCmd
        cmds = [SetFieldCmd(o, f, getattr(o, f, None), v, label=label)
                for o, f, v in fields if getattr(o, f, None) != v]
        if not cmds:
            return False
        cmds[-1]._persist = self._save          # un seul save, en fin de groupe
        get_history().push(cmds[0] if len(cmds) == 1 else MacroCmd(cmds, label))
        self.changed.emit()
        if refresh:
            self._refresh()
        return True

    def _on_camera_picked(self, idx: int):
        """Choix de la caméra de DÉMARRAGE de la scène — indépendant de la
        caméra affichée/éditée par le reste de ce panneau."""
        if self._blocking or not self._scene:
            return
        self._edit([(self._scene, "camera", self._combo_camera.itemData(idx) or "")],
                   "Startup camera")

    def _on_notes_changed(self, text: str):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is not None:
            self._edit([(cam, "notes", text)], "Camera note", refresh=False)

    def _on_mode_changed(self, idx: int):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is not None:
            self._edit([(cam, "mode", _MODES[idx][0])], "Camera mode")

    def _on_follow_changed(self, text: str):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is not None:
            self._edit([(cam, "follow_target",
                         self._follow_combo.currentData() or "")],
                       "Camera target", refresh=False)

    def _on_margins_changed(self):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is not None:
            self._edit([(cam, "margin_x", self._margin_x.value()),
                        (cam, "margin_y", self._margin_y.value())],
                       "Camera margins", refresh=False)

    def _on_bounds_changed(self):
        if self._blocking:
            return
        cam = self._mutable()
        if cam is not None:
            self._edit([(cam, "bounds_w", self._bounds_w.value() or None),
                        (cam, "bounds_h", self._bounds_h.value() or None),
                        (cam, "bounds_x", self._bounds_x.value() or None),
                        (cam, "bounds_y", self._bounds_y.value() or None)],
                       "Camera bounds", refresh=False)

    def _on_transform_changed(self):
        """Position et frame : édition faite ICI (pas par drag canvas), donc
        `camera_moved` est émis en plus — c'est ce qui fait suivre le rectangle
        du canvas (cf. SceneEditor.move_camera_item)."""
        if self._blocking:
            return
        cam = self._mutable()
        if cam is None:
            return
        if self._edit([(cam, "x", self._pos_x.value()),
                       (cam, "y", self._pos_y.value()),
                       (cam, "frame_w", self._frame_w.value()),
                       (cam, "frame_h", self._frame_h.value())],
                      "Camera transform", refresh=False):
            self.camera_moved.emit(cam)

    def _recalc_bounds(self):
        """Pré-remplit depuis le fond le plus proche d'une vitesse de 1.0 dans
        la scène SÉLECTIONNÉE — une caméra partagée n'a pas de fond à elle."""
        if not self._scene or not self._project:
            return
        layers = [L for L in self._scene.background_layers if L.background_name]
        if not layers:
            QMessageBox.information(self, label('caminsp.world_bounds'), label('caminsp.no_background'))
            return
        ref = min(layers, key=lambda L: abs(L.scroll_speed - 1.0))
        size = self._bg_pixel_size(ref)
        if size is None:
            QMessageBox.warning(self, label('caminsp.world_bounds'), label('caminsp.bg_read_failed', background_name=ref.background_name))
            return
        w, h = size
        # Poser les quatre valeurs SANS déclencher le handler par champ (sinon
        # quatre entrées d'historique pour un clic), puis committer le groupe en
        # UNE entrée via `_on_bounds_changed` → `_edit` (MacroCmd).
        for sp, v in ((self._bounds_x, 0), (self._bounds_y, 0),
                      (self._bounds_w, w), (self._bounds_h, h)):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self._on_bounds_changed()

    def _bg_pixel_size(self, layer) -> Optional[tuple[int, int]]:
        ba = self._project.get_background(layer.background_name)
        if ba is None:
            return None
        if getattr(ba, "tileset", None):
            return ba.tiles_w * 8, ba.tiles_h * 8
        png = self._project.background_images_dir / (
            ba.asset if getattr(ba, "asset", None) else f"{layer.background_name}.png"
        )
        try:
            from PIL import Image
            with Image.open(png) as img:
                return img.size
        except Exception:
            return None

    # ── Script ────────────────────────────────────────────────────

    def _script_new(self):
        if not self._project:
            return
        scripts = [(f.name, str(f.relative_to(self._project.root)).replace("\\", "/"))
                   for f in self._project.script_files()]
        popup = ScriptPickerPopup(scripts, COLOR_SCRIPT, parent=self)
        popup.picked.connect(self._script_assign)
        popup.new_requested.connect(self._script_create_new)
        popup.show_below(self._script_slot)

    def _script_assign(self, rel: str):
        cam = self._mutable()
        if cam is not None:
            self._edit([(cam, "script", rel)], "Camera script")

    def _script_create_new(self):
        cam = self._mutable()
        if cam is None:
            return
        name, ok = QInputDialog.getText(self, label('caminsp.new_camera_script'), label('common.name_without_lua'))
        if not ok or not name.strip():
            return
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        d = self._project.scripts_dir
        d.mkdir(parents=True, exist_ok=True)
        sp = d / f"{name.strip()}.lua"
        if not sp.exists():
            ctx = ScriptTemplateContext(kind="camera", name=name.strip(), camera_name=cam.name)
            sp.write_text(generate_script_template(ctx), encoding="utf-8")
        rel = str(sp.relative_to(self._project.root)).replace("\\", "/")
        self._edit([(cam, "script", rel)], "Camera script")
        if self._script_open_fn:
            self._script_open_fn(str(sp))

    def _script_open(self):
        cam = self._camera
        if cam is None or not self._project or not cam.script:
            return
        sp = self._project.asset_abs(cam.script)
        if sp and sp.exists() and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _script_clear(self):
        cam = self._camera
        if cam is not None:
            self._edit([(cam, "script", "")], "Camera script")
