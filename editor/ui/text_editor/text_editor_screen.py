"""
ui/text_editor/text_editor_screen.py — écran Text Editor.

Un seul écran pour deux concepts distincts mais qui se croisent en permanence
(cf. mémoire project_text_font_screen_design) :

  • Police (`Font`)  — un asset réutilisable, importé (PNG / BMFont `.fnt`).
  • Texte (`Text`)   — une entrée référencée par clé, rangée dans un arbre.

Ils cohabitent parce que `Font.missing_chars()` et l'aperçu d'un texte ont
besoin des deux sous les yeux ; les modèles, eux, restent séparés.

Trois colonnes : polices à gauche, table des textes + atelier d'écriture au
centre, inspecteur CONTEXTUEL à droite. Le centre et l'inspecteur basculent par
la SÉLECTION, jamais par un onglet (police → contexte police, texte ou clic
dans le vide → contexte texte). Pattern du Scene Manager, mais câblé en signaux
Qt LOCAUX : le bus global est partagé avec un inspecteur qui ne connaît pas
`Font`/`Text`.

« Textes », jamais « Dialogue » : la table range, elle n'enchaîne pas. Le
séquencement reste du script — la neutralité de style est une décision de
ROADMAP v0.3.2.

Un fichier par sous-zone ; ce module n'assemble que les colonnes et arbitre le
contexte actif :

  colors.py               les deux familles de couleur (police / texte)
  glyph_paint.py          trouage des couleurs-clés + damier
  text_commands.py        commandes annulables (clé, rangement, planche)
  (colonne gauche : AssetFinder — composant partagé, cf. ui/common/asset_finder.py)
  text_panel.py           colonne centre, contexte Texte — arbitre les deux
  text_table.py           la table des textes (haut du centre)
  text_workbench.py       l'atelier d'écriture (bas du centre)
  font_screen_preview.py  aperçu écran GBA (monté par l'atelier)
  markup_toolbar.py       boutons de balisage de l'atelier (dérivés de TAGS)
  glyph_sheet.py          planche de glyphes (canvas)
  glyph_sheet_panel.py    colonne centre, contexte Police — planche + outils
  inspector_shell.py      coquille commune aux deux inspecteurs
  text_inspector.py       colonne droite, contexte Texte
  font_inspector.py       colonne droite, contexte Police
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QStackedWidget, QMessageBox,
    QFrame, QToolButton, QLabel, QButtonGroup,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.history import get_history, SetFieldCmd
from ui.common.theme import C
from ui.common.labels import label
from ui.text_editor.colors import TEXT_COLOR
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import FONTS, FONT_ASSETS
from ui.text_editor.text_panel import TextPanel
from ui.text_editor.text_finder import TextFinder
from ui.text_editor.glyph_sheet_panel import GlyphSheetPanel
from ui.text_editor.text_inspector import TextInspector
from ui.text_editor.font_inspector import FontInspector
from ui.text_editor.font_asset_preview import FontAssetPreview
from ui.text_editor.font_asset_inspector import FontAssetInspector
from core.models.font_asset import FontAsset
from ui.text_editor.text_commands import (
    SetKeyColorCmd, ResliceFontCmd, MergeGlyphsCmd, SetCharsetCmd,
)


class _TextPipelineBar(QFrame):
    """Navigation visuelle du pipeline Font → Asset → Texts."""

    context_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet(
            f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(5)

        lay.addStretch()

        self._buttons: dict[int, QToolButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for ctx, name in ((1, "Font"), (2, "FontAsset"), (0, "Texts")):
            button = QToolButton()
            button.setText(name)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            button.setStyleSheet(
                f"QToolButton{{background:{C.BG_INPUT}; color:{C.TEXT_DIM};"
                f"border:1px solid {C.BORDER}; border-radius:4px; padding:3px 12px;}}"
                f"QToolButton:hover{{color:{C.TEXT_NORM}; border-color:{C.BORDER_MID};}}"
                f"QToolButton:checked{{background:{C.BG_SEL}; color:{C.ACCENT};"
                f"border-color:{C.ACCENT};}}")
            button.clicked.connect(lambda _checked=False, c=ctx: self.context_requested.emit(c))
            group.addButton(button)
            self._buttons[ctx] = button
            lay.addWidget(button)
        lay.addStretch()

    def set_context(self, context: int):
        button = self._buttons.get(context)
        if button is not None:
            button.setChecked(True)

class TextEditorScreen(QWidget):
    """Assemble les trois colonnes et arbitre le contexte actif."""

    _CTX_TEXT = 0
    _CTX_FONT = 1
    _CTX_FONT_ASSET = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:horizontal{{width:2px;}}"
            f"QSplitter::handle:hover{{background:{TEXT_COLOR};}}"
        )

        # Le Finder est lui aussi contextuel : il ne mélange pas la source
        # bitmap, la recette FontAsset et les textes avec lesquels elles
        # travaillent. Les trois boutons sont placés ICI, pas dans une barre
        # globale, pour que la colonne de gauche dise toujours ce qu'elle
        # explore.
        self._finder_host = QWidget()
        finder_layout = QVBoxLayout(self._finder_host)
        finder_layout.setContentsMargins(0, 0, 0, 0)
        finder_layout.setSpacing(0)
        self._fonts = AssetFinder(label('txtscr.font_finder'), [FONT_ASSETS, FONTS],
                                  min_width=180, max_width=420)
        self._text_finder = TextFinder()
        self._text_finder.path_selected.connect(self._texts_set_folder_filter)
        self._text_finder.folder_renamed.connect(self._on_folder_renamed)
        self._text_finder.key_renamed.connect(
            lambda t, key: self._texts.rename_key(t, key))
        self._finder_views = QStackedWidget()
        self._finder_views.addWidget(self._fonts)
        self._finder_views.addWidget(self._text_finder)
        finder_layout.addWidget(self._finder_views, 1)

        # Le CENTRE est contextuel lui aussi : une planche fait plusieurs
        # centaines de cases, elle n'aurait pas tenu dans l'inspecteur.
        self._center = QStackedWidget()
        # Un écran empilé ne doit pas hériter de la largeur d'un aperçu à
        # pixmap fixe : seul le splitter arbitre les trois colonnes.
        self._center.setMinimumWidth(0)
        self._texts = TextPanel()
        self._sheet = GlyphSheetPanel()
        self._font_asset_preview = FontAssetPreview()
        self._center.addWidget(self._texts)   # _CTX_TEXT
        self._center.addWidget(self._sheet)   # _CTX_FONT
        self._center.addWidget(self._font_asset_preview)  # _CTX_FONT_ASSET
        self._center_host = QWidget()
        center_layout = QVBoxLayout(self._center_host)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        self._pipeline = _TextPipelineBar()
        self._pipeline.context_requested.connect(self._on_pipeline_context)
        center_layout.addWidget(self._pipeline)
        center_layout.addWidget(self._center, 1)

        self._inspectors = QStackedWidget()
        self._inspectors.setMinimumWidth(200)
        self._inspectors.setMaximumWidth(420)
        self._text_insp = TextInspector()
        self._font_insp = FontInspector()
        self._font_asset_insp = FontAssetInspector()
        self._inspectors.addWidget(self._text_insp)   # _CTX_TEXT
        self._inspectors.addWidget(self._font_insp)   # _CTX_FONT
        self._inspectors.addWidget(self._font_asset_insp)  # _CTX_FONT_ASSET

        split.addWidget(self._finder_host)
        split.addWidget(self._center_host)
        split.addWidget(self._inspectors)
        split.setSizes([240, 800, 300])
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        split.setCollapsible(1, False)
        root.addWidget(split)

        # Bascule de contexte par sélection — jamais par un onglet.
        self._fonts.selected.connect(lambda _kind, f: self._on_font_selected(f))
        self._texts.text_selected.connect(self._on_text_selected)
        self._texts.changed.connect(self._persist)
        # Clé/rangement édités au centre : l'inspecteur affiche la clé dans
        # son en-tête, il doit se relire.
        self._texts.identity_changed.connect(self._on_identity_changed)
        # Le balisage se relit à la FRAPPE, comme l'aperçu : voir ce qui cloche
        # pendant qu'on écrit, pas au build.
        self._texts.parsed.connect(self._text_insp.set_parsed)
        self._texts.preview_font_changed.connect(self._text_insp.set_font)
        self._text_insp.changed.connect(self._on_text_insp_changed)
        self._text_insp.path_rename_requested.connect(self._texts.rename_selected_path)
        self._sheet.glyph_selected.connect(self._font_insp.set_glyph)
        self._sheet.glyph_edited.connect(self._on_glyph_edited)
        self._sheet.reslice_asked.connect(self._on_reslice)
        self._sheet.merge_asked.connect(self._on_merge)
        self._sheet.selection_changed.connect(self._font_insp.set_selection)
        self._sheet.background_clicked.connect(self._on_sheet_background)
        # Pipettes : l'inspecteur DEMANDE, la planche PRÉLÈVE, l'écran DÉCIDE
        # (commande + sauvegarde) — aucune vue ne connaît l'autre.
        self._font_insp.pick_asked.connect(self._sheet.begin_pick)
        self._font_insp.key_color_cleared.connect(
            lambda role: self._set_key_color(role, None))
        self._sheet.color_picked.connect(self._set_key_color)
        # Deux chemins d'édition, une seule commande : frappe sur la planche
        # et champ de l'inspecteur passent par le même _on_glyph_edited.
        self._font_insp.glyph_char_changed.connect(self._on_glyph_edited)
        # Charset réécrit d'un bloc : assignation positionnelle sur les cases.
        self._font_insp.charset_edited.connect(self._on_charset_edited)
        self._font_asset_insp.field_changed.connect(self._on_font_asset_field_changed)
        self._font_asset_preview.field_changed.connect(self._on_font_asset_field_changed)

    def load_project(self, project):
        """Ouvre un projet — l'écran repart en contexte Texte."""
        self._project = project
        self._fonts.load_project(project)
        self._text_finder.load_project(project)
        self._texts.load_project(project)
        self._text_insp.set_font(self._texts.preview_font())
        self._text_insp.invalidate_usages()
        self._text_insp.load(None, project)
        self._set_context(self._CTX_TEXT)

    def invalidate_script_usages(self):
        """Branché sur « scripts_changed » ET « ui_text_links_changed » —
        recalcul paresseux, à la prochaine sélection (l'écran n'est peut-être
        même pas affiché).

        Deux vues montrent les usages : la colonne de la table et la section de
        l'inspecteur. Elles lisent le même index, elles se périment ensemble."""
        self._text_insp.invalidate_usages()
        self._texts.invalidate_usages()

    def _on_identity_changed(self, text):
        """Clé renommée : les scripts viennent d'être réécrits, l'index des
        utilisations et l'inspecteur sont périmés tous les deux."""
        self._text_insp.invalidate_usages()
        self._text_insp.load(text, self._project)

    def refresh(self):
        """Re-dérive à la revisite de l'écran — appelé au centre par
        `Window._show_screen` (chantier « L'écran resynchronisé à sa revisite »),
        et aussi sur fichier déposé (watcher) ou undo/redo. Un texte a pu naître
        ailleurs depuis la dernière visite (une zone créée dans le Scene Manager
        ajoute son entrée à `project.texts`). Bon marché (usages paresseux),
        conserve la sélection."""
        if not self._project:
            return
        self._fonts.refresh()
        self._text_finder.refresh()
        self._texts.reload_fonts()            # polices apparues/disparues
        self._texts.refresh()
        # L'inspecteur affiche peut-être une entrée que l'undo a changée, ou
        # qui n'existe plus.
        cur = self._text_insp._text
        if cur is not None and cur not in self._project.texts:
            cur = None
        # Un undo de renommage repasse par rename_text_key : les scripts ont
        # rebougé.
        self._text_insp.invalidate_usages()
        self._texts.invalidate_usages()
        self._text_insp.load(cur, self._project)

        # Contexte police : un undo a pu changer un caractère, une couleur-clé
        # ou la découpe — tout ça se voit.
        font = self._font_insp._font
        if font is not None:
            if font not in self._project.fonts:
                self._font_insp.load(None, self._project)
                self._sheet.load(None, self._project)
                self._set_context(self._CTX_TEXT)
            else:
                # refresh_keying et pas update() : la planche trouée peut être
                # à reconstruire.
                self._sheet.refresh_keying()
                self._font_insp.refresh_stats()
                self._font_insp.refresh_keys()

        font_asset = self._font_asset_insp._asset
        if font_asset is not None:
            if font_asset not in self._project.font_assets:
                self._font_asset_insp.load(None, self._project)
                self._font_asset_preview.load(None, self._project)
                self._set_context(self._CTX_TEXT)
            else:
                # Une source peut avoir été renommée ou apparaître à chaud :
                # le sélecteur et le résumé doivent alors se relire ensemble.
                self._font_asset_insp.load(font_asset, self._project)
                self._font_asset_preview.load(font_asset, self._project)

    # ── Contexte ──────────────────────────────────────────────────

    def _set_context(self, ctx: int):
        """Bascule centre et inspecteur d'un bloc."""
        self._center.setCurrentIndex(ctx)
        self._inspectors.setCurrentIndex(ctx)
        self._pipeline.set_context(ctx)
        if ctx == self._CTX_FONT:
            self._finder_views.setCurrentWidget(self._fonts)
            self._fonts.set_title(label('common.fonts'))
            self._fonts.show_only({FONTS.label})
        elif ctx == self._CTX_FONT_ASSET:
            self._finder_views.setCurrentWidget(self._fonts)
            self._fonts.set_title(label('akind.font_assets'))
            self._fonts.show_only({FONT_ASSETS.label})
        else:
            self._finder_views.setCurrentWidget(self._text_finder)

    def _texts_set_folder_filter(self, path) -> None:
        """Un dossier du Finder limite la table, jamais le modèle."""
        self._texts.set_folder_filter(path)

    def _on_folder_renamed(self, path, segment: str) -> None:
        """Le Finder garde le focus sur le dossier après son renommage."""
        self._texts.rename_folder(path, segment)
        new_path = tuple(path[:-1]) + (segment,)
        self._texts.set_folder_filter(new_path)
        self._text_finder.refresh()

    def _on_pipeline_context(self, ctx: int):
        """Navigation explicite, sans forcer une sélection d'asset.

        Les trois étapes peuvent être parcourues pour regarder leur espace de
        travail ; lorsqu'une police ou recette est déjà sélectionnée, elle reste
        naturellement chargée. Le canvas et la table, eux, conservent leur
        sélection courante.
        """
        if ctx == self._CTX_TEXT:
            self._fonts.clear_selection()
        self._set_context(ctx)

    def _on_font_selected(self, font):
        """Sélection à gauche : entre en contexte Police (None = retour)."""
        if font is None:
            # Règle générale « sélection vide → contexte par défaut », pas un
            # cas particulier de retour.
            self._set_context(self._CTX_TEXT)
            return
        if isinstance(font, FontAsset):
            self._texts.clear_selection()
            self._font_asset_insp.load(font, self._project)
            self._font_asset_preview.load(font, self._project)
            self._set_context(self._CTX_FONT_ASSET)
            return
        self._texts.clear_selection()
        self._font_insp.load(font, self._project)
        self._sheet.load(font, self._project)
        self._set_context(self._CTX_FONT)

    def _on_font_asset_field_changed(self, field: str, value):
        """Tous les champs de recette passent par l'historique et la même
        persistance ; l'aperçu ne peut jamais afficher une valeur non sauvée."""
        asset = self._font_asset_insp._asset
        if not asset or getattr(asset, field) == value:
            return
        get_history().push(SetFieldCmd(
            asset, field, getattr(asset, field), value,
            label=f"Set {field} of {asset.name}",
            persist_fn=lambda: self._after_font_asset_change(asset),
        ))

    def _after_font_asset_change(self, asset):
        # Le sélecteur de taille de l'aperçu et celui de l'inspecteur pilotent
        # la même recette. Relire les deux évite qu'un des deux affiche une
        # valeur transitoire après undo/redo ou après un changement dans l'autre.
        self._font_asset_insp.load(asset, self._project)
        self._font_asset_preview.refresh()
        if self._project:
            self._project.save_font_asset(asset)

    def _on_text_selected(self, text):
        """Sélection dans la table : revient au contexte Texte, même si une
        police reste surlignée à gauche."""
        self._fonts.clear_selection()
        self._text_insp.load(text, self._project)
        self._set_context(self._CTX_TEXT)

    # ── Glyphes ───────────────────────────────────────────────────

    def _on_glyph_edited(self, glyph, before: str, after: str):
        """Caractère d'une case changé, quelle que soit la vue d'origine."""
        font = self._font_insp._font
        get_history().push(SetFieldCmd(
            glyph, "char", before, after,
            label=f"Glyphe « {after} »",
            persist_fn=lambda: self._after_glyph_change(font),
        ))

    def _on_charset_edited(self, charset: str):
        """Charset réécrit d'un bloc : une seule commande réassigne les cases
        dans l'ordre de la planche (cf. SetCharsetCmd)."""
        font = self._font_insp._font
        if not font:
            return
        get_history().push(SetCharsetCmd(
            font, charset,
            persist_fn=lambda: self._after_glyph_change(font),
        ))

    def _after_glyph_change(self, font):
        """Relit tout ce qui DÉRIVE des glyphes (charset, coût en tuiles, case
        courante) et sauvegarde — sinon l'inspecteur ment après un undo."""
        self._sheet.refresh()
        self._font_insp.refresh_stats()
        self._font_insp.set_glyph(self._font_insp._glyph, self._project)
        if self._project and font:
            self._project.fonts.save(font)

    # ── Couleurs-clés de la planche ───────────────────────────────

    _KEY_FIELD = {"bg": ("bg_color", "fond"), "space": ("space_color", "espacement")}

    def _set_key_color(self, role: str, rgb):
        """Pose (ou retire, si `rgb` est None) une couleur transparente.

        Passe par l'historique : se tromper de pixel arrive, et sans undo il
        faudrait retrouver la bonne couleur à l'œil."""
        font = self._font_insp._font
        entry = self._KEY_FIELD.get(role)
        if not font or entry is None:
            return
        field_name, label = entry
        old = getattr(font, field_name)
        new = tuple(rgb) if rgb is not None else None
        if old == new:
            return
        get_history().push(SetKeyColorCmd(
            self._project, font, field_name, old, new,
            label=(f"{label} color of {font.name}" if new
                   else f"Remove {label} color of {font.name}"),
            persist_fn=lambda: self._after_key_color(font),
        ))

    def _after_key_color(self, font):
        """La transparence change ce qu'on VOIT (planche, aperçu) et ce que
        MESURE le modèle (chasse) — relire les deux, sinon l'aperçu et la ROM
        divergent."""
        self._sheet.refresh_keying()
        self._font_insp.refresh_keys()
        self._font_insp.set_glyph(self._font_insp._glyph, self._project)
        # L'aperçu écran vit dans l'autre contexte mais rend avec cette
        # police : sa planche est à retrouer même si on ne le regarde pas.
        self._texts.refresh_preview_font()
        if self._project and font:
            self._project.fonts.save(font)

    def _on_sheet_background(self):
        """Clic hors planche : sélection à zéro, retour au contexte Texte.
        Pas de bouton de retour dédié, la règle suffit."""
        self._fonts.clear_selection()
        self._font_insp.set_glyph(None)
        self._set_context(self._CTX_TEXT)

    def _on_merge(self, indices: list):
        """Fusionne les cases sélectionnées en un glyphe."""
        font = self._font_insp._font
        if not font or len(indices) < 2:
            return
        # Caractère du glyphe fusionné : celui de la 1ère case, que
        # l'utilisateur remplace ensuite (souvent par un mot).
        first = font.glyphs[min(indices)].char
        get_history().push(MergeGlyphsCmd(
            font, indices, first,
            persist_fn=lambda: self._reload_font(font),
        ))

    def _on_reslice(self, cw: int, ch: int):
        """Re-découpe la planche après confirmation (geste destructif)."""
        font = self._font_insp._font
        if not font or not self._project or not font.asset:
            return
        png = self._project.asset_abs(font.asset)
        if not png or not png.exists():
            QMessageBox.warning(self, label("txtscr.reslice_title"),
                                label("txtscr.sheet_not_found", asset=font.asset))
            return
        if QMessageBox.question(
            self, label("txtscr.reslice_confirm_title"),
            label("txtscr.reslice_confirm_msg", name=font.name, cw=cw, ch=ch),
        ) != QMessageBox.StandardButton.Yes:
            return
        from core import font_import
        try:
            # Les couleurs repiquées restent : la re-découpe change le
            # DÉCOUPAGE, pas la lecture des couleurs.
            fields = font_import.import_font_png(png, cell=(cw, ch),
                                                 keys=font.key_colors(),
                                                 space_color=font.space_color)
        except Exception as exc:
            QMessageBox.warning(self, label("txtscr.reslice_title"),
                                label("txtscr.import_failed", error=exc))
            return
        get_history().push(ResliceFontCmd(
            self._project, font, fields,
            persist_fn=lambda: self._reload_font(font),
        ))

    def _reload_font(self, font):
        """Recharge la planche et l'inspecteur après une édition lourde."""
        self._sheet.load(font, self._project)   # load reconstruit déjà le trouage
        self._font_insp.load(font, self._project)
        if self._project:
            self._project.fonts.save(font)

    # ── Persistance ───────────────────────────────────────────────

    def _persist(self):
        """Écrit texts.json."""
        if self._project:
            self._project.save_texts()

    def _on_text_insp_changed(self):
        self._persist()
        # Seule la note s'édite ici, et la table ne l'affiche pas : inutile de
        # la reconstruire.
