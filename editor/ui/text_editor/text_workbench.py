"""
ui/text_editor/text_workbench.py — colonne centre (contexte Texte), partie
BASSE : l'atelier d'écriture.

Identité en haut (clé, fil d'Ariane), source à gauche, aperçu écran à droite —
côte à côte, jamais empilés : l'aperçu suit la frappe, il doit rester visible
pendant qu'on écrit.

Sous l'identité, des ONGLETS DE LANGUE (ROADMAP v0.9, un par langue déclarée,
source comprise) — cachés entiers tant qu'aucune traduction n'existe. C'est
LÀ, et nulle part ailleurs, que se choisit ce qu'on écrit : ni la table ni le
panneau ne portent leur propre notion de langue active, ils suivent celle-ci
via `active_lang_changed`. Cliquer un onglet de traduction fait apparaître la
source en lecture seule au-dessus du champ, qui lui reste vide tant que rien
n'est écrit — jamais pré-rempli avec elle (cf. `_content_of`).

L'atelier édite la SOURCE ou une TRADUCTION selon l'onglet actif (balises
comprises dans les deux cas) ; la table, au-dessus, montre le RENDU de cette
même langue. C'est la même règle que partout ailleurs dans l'éditeur : on
écrit ce que la ROM contiendra, on regarde ce que le joueur verra.

Il connaît trois états, et la sélection multiple n'est pas un cas dégénéré :
  • rien de sélectionné — tout est éteint ;
  • une entrée — clé, rangement, contenu, aperçu ;
  • plusieurs — le contenu s'éteint (il n'y a pas de texte « commun »), le
    RANGEMENT reste vivant. Ranger vingt entrées d'un coup est ce qui remplace
    le glisser-déposer de l'ancien arbre, et c'est un geste que le
    glisser-déposer ne savait pas faire.

L'atelier ne modifie rien lui-même : il signale une saisie validée, le panneau
en tire une commande annulable.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTextEdit, QLineEdit, QComboBox, QToolButton, QButtonGroup, QApplication,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from core.models.text import MAX_DEPTH, SEP
from core.text_markup import parse, resolve
from ui.common.theme import C, T, QSS
from ui.common.widgets import BTN_ICON
from ui.common import icons
from ui.common.labels import label
from ui.text_editor.colors import TEXT_COLOR
from ui.text_editor.font_screen_preview import FontScreenPreview
from ui.text_editor.markup_toolbar import MarkupToolbar


class _LangTabs(QWidget):
    """Le contexte de langue de l'atelier — un onglet par langue déclarée,
    source comprise.

    **Caché ENTIER tant qu'il n'y a rien à choisir** (moins de deux langues) :
    un projet monolingue ne voit aucun chrome de plus, exactement comme avant
    la v0.9. Une traduction porte son compte de trous entre parenthèses — la
    source n'en a pas, elle n'est traduite de rien.

    Le CODE de l'onglet source est son vrai code de langue (`en`, jamais "") :
    toutes les règles qui décident « source ou traduction ? » ailleurs dans
    l'écran comparent au code source du projet, pas à une chaîne vide — les
    onglets suivent la même convention plutôt que d'en inventer une seconde.
    """

    picked = pyqtSignal(str)   # code de langue cliqué

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        self._active = ""
        self._buttons: dict[str, QToolButton] = {}
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(8, 0, 8, 0)
        self._lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.setVisible(False)

    def populate(self, project, active: str) -> str:
        """Reconstruit les onglets depuis le projet. Rend le code
        EFFECTIVEMENT actif — celui demandé s'il existe encore, sinon la
        source (jamais une langue au hasard)."""
        for b in list(self._buttons.values()):
            self._group.removeButton(b)
            b.deleteLater()
        self._buttons.clear()
        while self._lay.count():
            self._lay.takeAt(0)

        langs = project.settings.all_languages() if project else []
        self.setVisible(len(langs) > 1)
        if len(langs) <= 1:
            self._active = ""
            return ""

        source_code = project.settings.source_lang.code
        for lang in langs:
            is_source = lang.code == source_code
            disp = lang.name or lang.code or "?"
            if not is_source:
                n = len(project.translation_gaps(lang.code))
                if n:
                    disp = f"{disp} ({n})"
            b = QToolButton()
            b.setText(disp)
            b.setCheckable(True)
            b.setFont(QFont(T.UI, T.XS))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(label("txtwb.source_tab", name=disp) if is_source
                         else label("txtwb.translation_tab", name=disp))
            b.setStyleSheet(
                f"QToolButton{{background:transparent; color:{C.TEXT_DIM};"
                f"border:none; border-bottom:2px solid transparent;"
                f"padding:4px 8px;}}"
                f"QToolButton:hover{{color:{C.TEXT_NORM};}}"
                f"QToolButton:checked{{color:{TEXT_COLOR};"
                f"border-bottom-color:{TEXT_COLOR};}}"
            )
            b.clicked.connect(lambda _c=False, _code=lang.code: self._on_click(_code))
            self._group.addButton(b)
            self._lay.addWidget(b)
            self._buttons[lang.code] = b
        self._lay.addStretch(1)

        resolved = active if active in self._buttons else source_code
        self._active = resolved
        self._buttons[resolved].setChecked(True)
        return resolved

    def _on_click(self, code: str):
        if code != self._active:
            self._active = code
            self.picked.emit(code)


class _PillEdit(QLineEdit):
    """Un niveau de rangement, en PASTILLE — même langage visuel que la
    colonne Category de la table (`_CategoryDelegate`). Reste un QLineEdit
    ordinaire, sans bascule lecture/édition à part : cliquer dessus édite
    tout de suite (cf. mémoire feedback_inline_over_dialogs)."""

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setFont(QFont(T.MONO, T.SM))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"QLineEdit{{background:{C.BG_RAISED}; color:{C.TEXT_DIM};"
            f"border:1px solid {C.BORDER_MID}; border-radius:9px; padding:2px 4px;}}"
            f"QLineEdit:focus{{color:{C.TEXT_HI}; border-color:{TEXT_COLOR};}}"
        )
        self.textChanged.connect(self._autosize)
        self.setPlaceholderText(placeholder)

    def setPlaceholderText(self, text: str):
        super().setPlaceholderText(text)
        self._autosize()

    def _autosize(self):
        text = self.text() or self.placeholderText()
        w = self.fontMetrics().horizontalAdvance(text) + 22
        self.setFixedWidth(max(50, min(w, 200)))


class TextWorkbench(QWidget):
    """Identité, source et aperçu de ce que la table a sélectionné."""

    content_committed = pyqtSignal(str, str)   # (avant, après — langue ACTIVE)
    key_committed = pyqtSignal(str)            # clé saisie
    path_committed = pyqtSignal(int, str)      # (niveau, segment)
    relink_asked = pyqtSignal()                # clé manuelle ré-accrochée
    parsed = pyqtSignal(object)                # ParsedText de l'entrée courante
    preview_font_changed = pyqtSignal(object)  # Font | None
    active_lang_changed = pyqtSignal(str)      # code cliqué dans les onglets

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._texts: list = []
        self._values: dict = {}
        self._blocking = False
        # "" = source. Décide CE QUE l'éditeur montre et commite — le panneau
        # est le seul à savoir dans quel fichier ça atterrit (`texts.json` ou
        # un side), l'atelier n'a besoin que de savoir QUOI afficher.
        self._active_lang = ""
        # Un seul niveau de rangement à la création ; les suivants se révèlent
        # sur demande, jusqu'au plafond du modèle.
        self._path_depth = 1
        # Cadenas ouvert : le champ est éditable, mais `auto_key` ne tombera
        # qu'au commit d'un nom réellement différent.
        self._key_unlocked = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_editor())
        self.set_texts([], None)

    # ── Construction ──────────────────────────────────────────────

    def _build_editor(self) -> QWidget:
        pane = QWidget()
        pane.setStyleSheet(f"background:{C.BG_BASE};")
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Identité sur une ligne, contenu dessous : éditer là où on lit. La clé
        # est en mono — c'est du code, elle part telle quelle dans les Lua.
        hdr = QFrame()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet(
            f"background:{C.BG_PANEL}; border-top:1px solid {C.BORDER_DARK};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 2, 8, 2)
        hl.setSpacing(4)

        self._key_edit = QLineEdit()
        self._key_edit.setFont(QFont(T.CODE, T.SM))
        self._key_edit.setFixedWidth(180)
        self._key_edit.setPlaceholderText(label("txtwb.key_ph"))
        self._key_edit.editingFinished.connect(self._commit_key)
        hl.addWidget(self._key_edit)

        # Cadenas : la clé est en lecture seule tant qu'elle DÉRIVE du
        # rangement. La nommer à la main l'en détache définitivement.
        self._btn_lock = QToolButton()
        self._btn_lock.setFixedSize(22, 22)
        self._btn_lock.setStyleSheet(BTN_ICON)
        self._btn_lock.clicked.connect(self._toggle_key_lock)
        hl.addWidget(self._btn_lock)

        self._btn_copy = QToolButton()
        self._btn_copy.setFixedSize(22, 22)
        self._btn_copy.setStyleSheet(BTN_ICON)
        self._btn_copy.setIcon(icons.get("copy", C.TEXT_DIM))
        self._btn_copy.setToolTip(label("txtwb.copy_tip"))
        self._btn_copy.clicked.connect(self._copy_key)
        hl.addWidget(self._btn_copy)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{C.BORDER};")
        hl.addSpacing(4)
        hl.addWidget(sep)
        hl.addSpacing(4)

        # Un FIL D'ARIANE, pas trois champs à séparateur nu : chaque niveau est
        # une pastille éditable en place — même geste que renommer une
        # catégorie dans la table, jamais de dialogue. Chaque pastille commite
        # SON niveau et lui seul, ce qui rend le rangement d'une sélection
        # multiple sans danger pour les niveaux qu'elle ne partage pas.
        self._path_edits: list[_PillEdit] = []
        self._path_seps: list[QLabel] = []
        for lvl in range(MAX_DEPTH):
            if lvl:
                arrow = QLabel(SEP.strip())
                arrow.setFont(QFont(T.UI, T.SM))
                arrow.setStyleSheet(f"color:{C.TEXT_MUTED};")
                hl.addWidget(arrow)
                self._path_seps.append(arrow)
            e = _PillEdit(label("txtwb.level", n=lvl + 1))
            e.setToolTip(label("txtwb.filing_tip"))
            e.editingFinished.connect(lambda _l=lvl: self._commit_path(_l))
            hl.addWidget(e)
            self._path_edits.append(e)
        self._btn_add_path = QToolButton()
        self._btn_add_path.setIcon(icons.get("add", C.TEXT_DIM))
        self._btn_add_path.setToolTip(label("txtwb.add_level_tip"))
        self._btn_add_path.setStyleSheet(BTN_ICON)
        self._btn_add_path.clicked.connect(self._add_path_level)
        hl.addWidget(self._btn_add_path)
        hl.addStretch(1)
        self._sync_path_fields()
        lay.addWidget(hdr)

        # Le contexte de LANGUE — un onglet par langue déclarée, source
        # comprise. Caché entier tant qu'il n'y a rien à choisir.
        self._lang_tabs = _LangTabs()
        self._lang_tabs.picked.connect(self._on_tab_picked)
        lay.addWidget(self._lang_tabs)

        # Référence de la SOURCE — visible seulement en train de traduire.
        # Lecture seule et hauteur bornée à dessein : c'est un repère, pas un
        # second champ à remplir. « Éditer là où on lit » ne s'applique qu'à
        # la langue qu'on écrit ; l'original reste à côté, jamais mélangé.
        # Texte posé plus tard par `_reload_content` (SOURCE — <langue>) ; jamais
        # affiché tant que rien n'est chargé.
        self._source_hdr = QLabel("")
        self._source_hdr.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._source_hdr.setStyleSheet(
            f"background:{C.BG_PANEL}; color:{C.TEXT_MUTED};"
            f"padding:2px 8px; letter-spacing:1px;")
        self._source_view = QTextEdit()
        self._source_view.setReadOnly(True)
        self._source_view.setFont(QFont(T.CODE, T.SM))
        self._source_view.setFixedHeight(52)
        self._source_view.setStyleSheet(
            f"QTextEdit{{background:{C.BG_DEEP}; color:{C.TEXT_DIM}; border:none;"
            f"border-bottom:1px solid {C.BORDER_DARK}; padding:4px 6px;}}")
        self._source_hdr.setVisible(False)
        self._source_view.setVisible(False)
        lay.addWidget(self._source_hdr)
        lay.addWidget(self._source_view)

        # La surface GBA EST désormais l'éditeur. Elle conserve une source
        # BBCode et expose le petit contrat consommé par MarkupToolbar.
        self._preview = FontScreenPreview()
        self._preview.set_editable(True)
        self._preview.edited.connect(self._on_edited)
        self._preview.committed.connect(self.content_committed.emit)
        self._markup_bar = MarkupToolbar(self._preview)
        self._btn_markup = QToolButton()
        self._btn_markup.setCheckable(True)
        self._btn_markup.setIcon(icons.get("mk_tag", C.TEXT_DIM))
        self._btn_markup.setToolTip(label("txtwb.show_markup_tip"))
        self._btn_markup.setStyleSheet(BTN_ICON)
        self._btn_markup.toggled.connect(self._preview.set_markup_visible)
        self._markup_bar.add_trailing_widget(self._btn_markup)
        self._preview_font = QComboBox()
        self._preview_font.setFont(QFont(T.UI, T.XS))
        self._preview_font.setStyleSheet(QSS.combobox)
        self._preview_font.setToolTip(label("txtwb.preview_font_tip"))
        self._preview_font.currentIndexChanged.connect(self._on_preview_font)
        self._markup_bar.add_trailing_widget(self._preview_font)
        lay.addWidget(self._markup_bar)
        lay.addWidget(self._build_preview(), 1)
        return pane

    def _build_preview(self) -> QWidget:
        pane = QWidget()
        pane.setStyleSheet(f"background:{C.BG_DEEP};")
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Pas de QScrollArea : l'aperçu est son PROPRE viewport (molette = zoom,
        # clic-central = pan), deux défilements superposés se voleraient la
        # molette.
        lay.addWidget(self._preview, 1)
        return pane

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project):
        self._project = project
        # Valeurs initiales des globals et constantes, relues à l'ouverture :
        # l'aperçu montre des chiffres, pas des places réservées.
        self._values = project.text_values() if project else {}
        self._markup_bar.set_project(project)
        self.reload_fonts()
        self._active_lang = ""
        self.refresh_languages()

    def refresh_languages(self):
        """Repeuple les onglets depuis les langues déclarées.

        Appelé au chargement ET par tout refresh venant d'ailleurs (watcher,
        undo, retour d'une déclaration faite dans l'inspecteur de projet — un
        autre écran, avec lequel cet atelier ne partage aucun signal)."""
        resolved = self._lang_tabs.populate(self._project, self._active_lang)
        if resolved != self._active_lang:
            # La langue qu'on éditait a disparu (retirée ailleurs) : repli sur
            # la source, et la TABLE doit le savoir — elle affiche encore
            # l'ancienne tant qu'on ne le lui dit pas.
            self.set_active_lang(resolved)
            self.active_lang_changed.emit(resolved)

    def _on_tab_picked(self, code: str):
        self.set_active_lang(code)
        self.active_lang_changed.emit(code)

    def reload_fonts(self):
        """Peuple le sélecteur avec les Font Assets du projet.

        Le texte reste indépendant de toute police ; cet aperçu doit toutefois
        suivre la même recette (sources de repli, taille et rasterisation) que
        celle qu'une TextBox sélectionnera dans une scène.
        """
        self._blocking = True
        cur = self._preview_font.currentText()
        self._preview_font.clear()
        for asset in (list(self._project.font_assets) if self._project else []):
            self._preview_font.addItem(asset.name, asset)
        idx = self._preview_font.findText(cur)
        self._preview_font.setCurrentIndex(idx if idx >= 0 else 0)
        self._blocking = False
        self._apply_preview_font()

    def preview_font(self):
        """Source primaire, maintenue pour les outils bitmap existants.

        L'écran lui-même reçoit la FontAsset complète dans
        :meth:`_apply_preview_font`; l'inspecteur et le menu d'icônes n'ont pas
        encore de modèle de ligatures multi-sources.
        """
        asset = self._preview_font.currentData()
        return (self._project.fonts.get(asset.primary_source_name())
                if asset and self._project else None)

    def refresh_preview_font(self):
        """Reconstruit le rendu après une modification de recette ou source."""
        self._apply_preview_font()

    def _apply_preview_font(self):
        """Passe la police choisie à l'aperçu — et à qui veut la confronter au
        texte (l'inspecteur, pour les caractères manquants)."""
        asset = self._preview_font.currentData()
        self._preview.set_font_asset(asset, self._project)
        # La même police décide de ce que `[icon=…]` peut désigner : les cases
        # fusionnées n'existent que dans une planche précise. Les outils
        # historiques attendent encore une source bitmap ; la FontAsset est
        # bien celle affichée par l'écran, sa première source sert seulement à
        # cette liste de ligatures.
        source = (self._project.fonts.get(asset.primary_source_name())
                  if asset and self._project else None)
        self._markup_bar.set_font(source)
        self.preview_font_changed.emit(source)

    def _on_preview_font(self, _i):
        if not self._blocking:
            self._apply_preview_font()

    # ── Sélection ─────────────────────────────────────────────────

    def commit_pending(self):
        """Force le commit du contenu en cours de frappe.

        Appelé AVANT tout changement de sélection : sans ça, la frappe non
        validée serait attribuée à l'entrée suivante."""
        self._preview.commit()

    def set_texts(self, texts: list, project=None):
        """Recharge l'atelier — zéro, une ou plusieurs entrées."""
        if project is not None:
            self._project = project
        self._texts = list(texts)
        one = self._texts[0] if len(self._texts) == 1 else None
        multi = len(self._texts) > 1
        self._key_unlocked = False      # le cadenas se referme d'une entrée à l'autre

        self._blocking = True
        self._key_edit.setText(one.key if one else "")
        self._key_edit.setPlaceholderText(
            label("txtwb.n_selected", n=len(self._texts)) if multi
            else label("txtwb.key_ph"))
        for lvl, e in enumerate(self._path_edits):
            e.setText(self._common_segment(lvl))
            e.setPlaceholderText(
                label("txtwb.mixed") if multi and not e.text() and self._differs(lvl)
                else label("txtwb.level", n=lvl + 1))
        self._path_depth = max(
            1, min(MAX_DEPTH, max((len(t.path) for t in self._texts), default=1)))
        self._sync_path_fields()
        self._sync_key_lock()
        self._blocking = False

        self._set_enabled(one is not None, multi)
        self._reload_content()

    def set_active_lang(self, code: str):
        """La langue qu'on ÉDITE change — cliquée dans les onglets.

        Commite ce qui est en cours AVANT de basculer, ici et pas chez
        l'appelant : c'est l'invariant qui protège la frappe, il doit tenir
        quel que soit le chemin qui mène à cet appel, pas seulement celui
        d'aujourd'hui (le clic d'onglet). Ne touche ni à la sélection ni à
        l'identité (clé, rangement) : ils ne dépendent pas de la langue. Seul
        le contenu — et donc l'aperçu et la référence source — a une raison de
        bouger."""
        if code == self._active_lang:
            return
        self._preview.commit()
        self._active_lang = code
        self._reload_content()

    def _is_translating(self) -> bool:
        return bool(self._active_lang and self._project
                    and self._active_lang != self._project.settings.source_lang.code)

    def _content_of(self, t) -> str:
        """Ce que l'éditeur doit REMPLIR pour cette entrée.

        **Pas de repli sur la source ici, volontairement.** `Project.
        text_content()` — celui de la table, celui du build — rend la source
        tant qu'une traduction manque ; c'est juste pour ça qu'`_reload_content`
        affiche la source à PART, dans `_source_view`. Pré-remplir aussi le
        champ éditable avec elle ferait deux dégâts d'un coup : laisser le
        champ tel quel (rien tapé) ressemblerait à une traduction qui vaut la
        source, et la moindre retouche d'un mot commiterait TOUT le reste de la
        source comme si c'était traduit — un `SetTranslationCmd` dont `old` est
        la source, jamais "", casse aussi le statut Missing/Translated d'un
        undo. Le champ montre ce qui est VRAIMENT écrit, "" si rien ne l'est."""
        if t is None:
            return ""
        if self._is_translating():
            return (self._project.translations.get(self._active_lang, {})
                    .get(t.id, "") if self._project else "")
        return t.content

    def _reload_content(self):
        """(Re)pose la référence source, le contenu éditable et l'aperçu.

        Factorisé hors de `set_texts` : changer de SÉLECTION et changer de
        LANGUE recalent tous les deux ce trio, sans que l'un ait besoin de
        rejouer l'autre."""
        one = self._texts[0] if len(self._texts) == 1 else None
        multi = len(self._texts) > 1
        translating = self._is_translating()

        show_ref = translating and one is not None
        self._source_hdr.setVisible(show_ref)
        self._source_view.setVisible(show_ref)
        if show_ref:
            src = self._project.settings.source_lang
            self._source_hdr.setText(
                label("txtwb.source_ref", name=src.name or src.code or "source"))
            self._source_view.setPlainText(one.content)

        content = self._content_of(one)
        self._preview.set_text_silent(content)
        self._push_parsed(content)

    def _common_segment(self, lvl: int) -> str:
        """Le segment que TOUTE la sélection partage à ce niveau, ou "" si elle
        ne s'accorde pas — un champ ne doit jamais afficher la valeur d'une
        entrée comme si c'était celle des autres."""
        segs = {(t.path[lvl] if lvl < len(t.path) else "") for t in self._texts}
        return segs.pop() if len(segs) == 1 else ""

    def _add_path_level(self):
        if self._path_depth < MAX_DEPTH:
            self._path_depth += 1
            self._sync_path_fields()
            self._path_edits[self._path_depth - 1].setFocus()

    def _sync_path_fields(self):
        """Ne montre que les niveaux réellement choisis pour le rangement."""
        for lvl, edit in enumerate(getattr(self, "_path_edits", ())):
            edit.setVisible(lvl < self._path_depth)
        for lvl, sep in enumerate(getattr(self, "_path_seps", ()), start=1):
            sep.setVisible(lvl < self._path_depth)
        if hasattr(self, "_btn_add_path"):
            self._btn_add_path.setVisible(self._path_depth < MAX_DEPTH)

    def _differs(self, lvl: int) -> bool:
        return len({(t.path[lvl] if lvl < len(t.path) else "")
                    for t in self._texts}) > 1

    def _set_enabled(self, single: bool, multi: bool):
        """Le contenu n'a de sens que sur UNE entrée ; le rangement en accepte
        plusieurs."""
        self._preview.setEnabled(single)
        self._preview.set_editable(single)
        self._markup_bar.setEnabled(single)
        self._key_edit.setEnabled(single)
        self._btn_lock.setEnabled(single)
        self._btn_copy.setEnabled(single)
        self._btn_add_path.setEnabled(single or multi)
        for e in self._path_edits:
            e.setEnabled(single or multi)

    # ── Contenu ───────────────────────────────────────────────────

    def _on_edited(self, source: str):
        """Frappe en cours : analyse et diffusion, aucune écriture au modèle
        (elle arrive au commit)."""
        if not self._blocking and self._texts:
            self._push_parsed(source)

    def _push_parsed(self, source: str):
        """Analyse une fois et diffuse : l'aperçu dessine le texte affiché,
        l'inspecteur montre balises et anomalies, la table montre le rendu. Un
        seul parcours par frappe."""
        parsed = parse(source)
        # L'aperçu reçoit la SOURCE, pas seulement le texte résolu : `[font]`
        # porte le choix typographique et disparaît justement de `resolve()`.
        self._preview.set_text(source, self._values)
        self.parsed.emit(parsed)
        return parsed

    def display_of(self, source: str) -> str:
        """Le texte tel qu'on le LIT, pour la ligne de table correspondante."""
        return resolve(parse(source), self._values).replace("\n", " ⏎ ")

    # ── Identité ──────────────────────────────────────────────────

    def _commit_key(self):
        if not self._blocking and len(self._texts) == 1:
            typed = self._key_edit.text().strip()
            if typed and typed != self._texts[0].key:
                self.key_committed.emit(typed)

    def _commit_path(self, lvl: int):
        if self._blocking or not self._texts:
            return
        typed = self._path_edits[lvl].text().strip()
        if typed != self._common_segment(lvl):
            self.path_committed.emit(lvl, typed)

    def reset_key_field(self):
        """Repose la clé du modèle — le renommage a été refusé."""
        self._blocking = True
        self._key_edit.setText(self._texts[0].key if self._texts else "")
        self._blocking = False

    def _toggle_key_lock(self):
        """Ouvre le champ clé, ou ré-accroche une clé manuelle au rangement."""
        if len(self._texts) != 1:
            return
        t = self._texts[0]
        if not t.auto_key:
            self._key_unlocked = False
            self.relink_asked.emit()
            return
        # Le cadenas n'ouvre que le champ : cliquer par curiosité ne doit rien
        # casser, `auto_key` ne tombe qu'au commit.
        self._key_unlocked = not self._key_unlocked
        self._blocking = True
        self._key_edit.setText(t.key)
        self._sync_key_lock()
        self._blocking = False
        if self._key_unlocked:
            self._key_edit.setFocus()
            self._key_edit.selectAll()

    def _sync_key_lock(self):
        """Reflète l'état de la clé : dérivée (verrouillée), dérivée mais
        déverrouillée le temps de l'édition, ou nommée à la main."""
        t = self._texts[0] if len(self._texts) == 1 else None
        auto = bool(t and t.auto_key)
        editable = t is not None and (not auto or self._key_unlocked)
        self._key_edit.setReadOnly(not editable)
        self._key_edit.setStyleSheet(
            QSS.lineedit if editable else
            QSS.lineedit + f"QLineEdit{{color:{C.TEXT_MUTED}; background:{C.BG_PANEL};}}"
        )
        self._key_edit.setToolTip(
            label("txtwb.key_tip_head")
            + (label("txtwb.key_tip_auto") if auto
               else label("txtwb.key_tip_hand"))
        )
        self._btn_lock.setIcon(icons.get(
            "key_auto" if auto else "key_manual",
            C.TEXT_DIM if auto else TEXT_COLOR))
        self._btn_lock.setToolTip(
            (label("txtwb.lock_attached")
             if not self._key_unlocked else
             label("txtwb.lock_reattach"))
            if auto else
            label("txtwb.lock_hand"))

    def _copy_key(self):
        """Copie la clé dans le presse-papier (à coller dans un script)."""
        if len(self._texts) != 1:
            return
        QApplication.clipboard().setText(self._texts[0].key)
        self._btn_copy.setIcon(icons.get("copied", C.ACCENT))
        QTimer.singleShot(
            900, lambda: self._btn_copy.setIcon(icons.get("copy", C.TEXT_DIM)))
