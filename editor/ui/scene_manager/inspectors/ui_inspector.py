"""UIInspector — édition de N'IMPORTE QUEL élément d'une mise en page UI
(texte, conteneur, image), sélectionné dans l'arbre ou le canvas.

UN inspecteur adaptatif, pas un par type : ancrage et géométrie sont les mêmes
champs pour les trois kinds — les dupliquer dans deux classes (l'état d'avant)
garantissait leur divergence. Les sections spécifiques (contenu et police d'un
texte, fond d'un conteneur, sprite et état d'une image) se montrent ou se
cachent au chargement, comme les MODE_INFO du SceneInspector.

**Le nom se change dans l'EN-TÊTE**, pas dans un champ. C'est là qu'il est déjà
affiché en gros, et c'est là que scène, acteur, prefab et script se renomment
(`AssetHeaderBar`, cf. DynamicInspector) : un champ « Name » de plus faisait de
l'interface le seul écran à en avoir deux, l'un montrant le nom et l'autre
seul capable de le changer.

Écrit dans la grammaire `W` (labels à gauche, paires d'axes colorées) — la même
que tous les autres inspecteurs, pour que l'UI ne soit pas un écran étranger.

**L'ancrage et la cible ne sont PLUS ici (v0.25)** : ils appartiennent au nœud
`Interface`, édités dans `UINodeInspector` (clic sur la racine « Interface » de
l'arbre). L'inspecteur d'élément ne fait que LIRE la cible héritée
(`layout.resolved_target`) pour adapter le fond et le pas de grille — il n'offre
aucun menu qui la changerait.

Les invariants métier restent ceux des modèles (models/ui_region.py) :
  • l'élément porte la GÉOMÉTRIE, jamais l'enchaînement (pas d'éditeur de dialogue) ;
  • la taille d'une image n'est pas libre — c'est la frame de son sprite.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QButtonGroup,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QScrollArea, QSpinBox, QLineEdit, QTextEdit, QToolButton,
)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter, QPen, QColor
from PyQt6.QtCore import pyqtSignal, QTimer, Qt

from core.project import Project
from core.text_markup import display_text
from core.models.gba_color import bgr555_to_rgb888
from core.models.ui_region import (
    ANCHOR_ACTOR, ALIGNS, TARGET_BG, TARGET_OBJ, PRIORITY_INHERIT,
    KIND_LIST, KIND_TEXT, KIND_IMAGE, can_fill,
    NAV_ROW, NAV_COLUMN, CURSOR_SNAP, CURSOR_SLIDE,
    FILL_NONE, FILL_COLOR, FILL_NINE, FILL_BG, FILL_SPRITE, fill_allowed,
    sprite_grid,
    image_geometry,
    preset_rect, H_LEFT, H_CENTER, H_RIGHT, V_TOP, V_MIDDLE, V_BOTTOM,
)
from ui.common import icons
from ui.common.theme import C, T, QSS
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import W, CollapsibleCard
from ui.common.notice import note, notice, text
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.pickers import ColorIndexSlot
from ui.text_editor.colors import TEXT_COLOR as TEXT_ACCENT

# Clés de libellé (infobulles) ; le choix se DESSINE, cf. `_ALIGN_ICONS`.
_ALIGN_TIP_KEYS = ("uiinsp.align.left", "uiinsp.align.centered", "uiinsp.align.right")
# Le même choix, dessiné : un alignement se reconnaît à sa forme.
_ALIGN_ICONS = ("align_left", "align_center", "align_right")

# Style SEGMENTÉ — `QSS.toolbutton_icon` n'a pas d'état `:checked`, et trois
# boutons dont aucun ne paraît enfoncé ne disent pas quel alignement est posé.
_SEGMENTED = f"""
QToolButton {{
    background: {C.BG_INPUT};
    border: 1px solid {C.BORDER_MID};
    border-radius: 3px;
    padding: 0;
}}
QToolButton:hover {{ background: {C.BG_HOVER}; }}
QToolButton:checked {{
    background: {C.BG_SEL};
    border-color: {C.ACCENT};
}}
"""
_FILL_LABEL_KEYS = [
    (FILL_NONE,   "uiinsp.fill.none"),
    (FILL_COLOR,  "uiinsp.fill.color"),
    (FILL_NINE,   "uiinsp.fill.nine"),
    (FILL_BG,     "common.background"),
    (FILL_SPRITE, "uiinsp.fill.sprite_opt"),
]

# ── Presets de placement ──────────────────────────────────────────
_H_POS = (H_LEFT, H_CENTER, H_RIGHT)
_V_POS = (V_TOP, V_MIDDLE, V_BOTTOM)
_POS_WORD = {H_LEFT: 'uiinsp.left', H_CENTER: 'uiinsp.center', H_RIGHT: 'uiinsp.right',
             V_TOP: 'uiinsp.top', V_MIDDLE: 'uiinsp.middle', V_BOTTOM: 'uiinsp.bottom'}


def _preset_tip(hpos: str, vpos: str, sh: bool, sv: bool) -> str:
    if sh and sv:
        return label('uiinsp.fill_the_frame')
    if sh:
        return label('uiinsp.full_width_value', value=label(_POS_WORD[vpos]))
    if sv:
        return label('uiinsp.full_height_value', value=label(_POS_WORD[hpos]))
    return label('uiinsp.placement', vertical=label(_POS_WORD[vpos]), horizontal=label(_POS_WORD[hpos]))


def _preset_icon(hpos: str, vpos: str, sh: bool, sv: bool) -> QIcon:
    """Le cadre, et dedans la boîte à sa place — dessiné plutôt que nommé.

    Neuf libellés « haut-gauche / haut-centre / … » se lisent moins vite qu'un
    dessin. Générée plutôt que douze fichiers, pour suivre le thème."""
    S, M = 32, 3                      # taille de rendu, marge du cadre
    fw = fh = S - 2 * M
    # ~40 % du cadre : assez pour que la POSITION saute aux yeux.
    bw = fw if sh else int(fw * 0.42)
    bh = fh if sv else int(fh * 0.42)
    bx = {H_LEFT: 0, H_CENTER: (fw - bw) // 2}.get(hpos, fw - bw)
    by = {V_TOP: 0, V_MIDDLE: (fh - bh) // 2}.get(vpos, fh - bh)

    px = QPixmap(S, S)
    px.fill(Qt.GlobalColor.transparent)
    q = QPainter(px)
    q.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    q.setPen(QPen(QColor(C.TEXT_MUTED), 1))
    q.setBrush(Qt.BrushStyle.NoBrush)
    q.drawRect(M, M, fw - 1, fh - 1)
    q.setPen(Qt.PenStyle.NoPen)
    q.setBrush(QColor(icons.COLOR_UI))
    q.drawRect(M + bx, M + by, bw, bh)
    q.end()
    return QIcon(px)


class UIInspector(QWidget):
    changed = pyqtSignal()
    # Le nom a changé sous nos pieds (collision d'unicité résolue par le
    # modèle) : l'en-tête, qui l'affiche, doit se remettre d'accord. Émis par
    # `rename` — la seule porte d'entrée du renommage, cf. la docstring.
    renamed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._layout_asset = None
        self._element = None
        self._scene = None
        self._blocking = False
        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        inner = QWidget()
        L = QVBoxLayout(inner)
        L.setContentsMargins(8, 8, 8, 8)
        L.setSpacing(4)
        scroll.setWidget(inner)

        # ── Appartenance ──────────────────────────────────────────
        # La mise en page est un ASSET partagé : modifier ici touche N scènes,
        # et ça se dit en couleur, pas en silence.
        self._layout_lbl = note(L, "ui.layout.name")
        # Le partage est une INFO de portée, pas un risque : il passe en
        # périwinkle sur sa propre ligne, au lieu de teinter en jaune la
        # ligne du nom. Le jaune reste à ce que le build ou l'écran feront.
        self._layout_shared = note(L, "ui.layout.shared")

        # L'ancrage et la cible ne vivent plus sur l'élément (v0.25) : ils sont
        # portés par le NŒUD `Interface`, édités dans `UINodeInspector` (clic sur
        # la racine « Interface » de l'arbre). L'inspecteur d'élément ne fait plus
        # que LIRE la cible héritée (`layout.resolved_target`) pour adapter le fond
        # et l'empreinte — il n'offre aucun menu qui la changerait.

        # ── Géométrie ─────────────────────────────────────────────
        geom_card = CollapsibleCard(label("uiinsp.card.geometry"))
        self._geom_lbl = geom_card

        # Presets de placement — la grille de Godot, adaptée au matériel : poser
        # une boîte basse sans taper quatre nombres. Les champs restent là pour
        # l'ajustement fin (icône plutôt que libellé, cf. `_preset_icon`).
        self._presets = QWidget()
        self._presets.setStyleSheet("background:transparent;")
        pg = QGridLayout(self._presets)
        pg.setContentsMargins(0, 2, 0, 2)
        pg.setSpacing(2)
        for r_i, vpos in enumerate(_V_POS):
            for c_i, hpos in enumerate(_H_POS):
                pg.addWidget(self._preset_btn(hpos, vpos), r_i, c_i)
        # 4e colonne : les étirements, qui eux CHANGENT la taille — séparés des
        # neuf placements pour que la différence se voie avant le clic.
        pg.addWidget(self._preset_btn(H_LEFT, V_TOP, sh=True), 0, 3)
        pg.addWidget(self._preset_btn(H_LEFT, V_TOP, sv=True), 1, 3)
        pg.addWidget(self._preset_btn(H_LEFT, V_TOP, sh=True, sv=True), 2, 3)
        pg.setColumnMinimumWidth(3, 34)     # respire : c'est un autre groupe
        # Colonne fantôme qui absorbe la largeur restante : sinon la grille
        # s'étire et les neuf cases se dispersent, or leur disposition EST
        # l'information — elles doivent rester serrées et carrées.
        pg.setColumnStretch(4, 1)
        W.row(label("uiinsp.geom.place"), self._presets, geom_card.body_layout)
        self._sp = {}
        for key in ("x", "y", "w", "h"):
            s = QSpinBox()
            s.setFont(QFont(T.MONO, T.MD))
            s.setStyleSheet(QSS.spinbox)
            # Sans ça, taper « 120 » vaut trois valeurs (1, 12, 120) : trois
            # écritures disque et trois redessins du canvas pour un seul geste.
            s.setKeyboardTracking(False)
            s.valueChanged.connect(lambda v, k=key: self._on_geom(k, v))
            self._sp[key] = s
        self._sp["x"].setRange(-512, 512)
        self._sp["y"].setRange(-512, 512)
        self._sp["w"].setRange(8, 512)
        self._sp["h"].setRange(8, 512)
        W.pair(label("common.position"), "X", C.AXIS_X, self._sp["x"],
               "Y", C.AXIS_Y, self._sp["y"], geom_card.body_layout)
        W.pair(label("common.size"), "W", C.AXIS_X, self._sp["w"],
               "H", C.AXIS_Y, self._sp["h"], geom_card.body_layout)
        L.addWidget(geom_card)

        # ── Visibilité (commune aux trois types) ──────────────────
        # État AUTHORÉ de départ, pas l'état effectif : un enfant sous un parent
        # caché reste coché ici (rien ne lui est arrivé), `_visible_why` dit
        # pourquoi il ne s'affiche quand même pas. Un script bascule cette même
        # valeur au runtime via `ui.show(nom, on)` — cf. models/ui_region.py.
        visible_card = CollapsibleCard(label("uiinsp.card.visibility"))
        self._visible = W.checkbox_row(label("uiinsp.visible.label"),
                                       label("uiinsp.visible.sub"), visible_card.body_layout)
        self._visible.toggled.connect(self._on_visible)
        self._visible_why = note(visible_card.body_layout, "ui.visible.hidden_parent")
        # Priorité OBJ — portée par CHAQUE élément (texte, image, fond de
        # conteneur), surchargeable, héritée par défaut. -1 = « Auto » : la
        # profondeur de l'acteur ancré, en direct. Sa place est ici, avec la
        # visibilité : les deux disent OÙ et SI l'élément se voit, pas sa forme.
        # N'a d'effet qu'en cible OBJ ; en BG la profondeur est celle du layer,
        # d'où la note conditionnelle plutôt qu'un champ qu'on croirait sans effet.
        self._prio = QSpinBox()
        self._prio.setFont(QFont(T.MONO, T.MD))
        self._prio.setStyleSheet(QSS.spinbox)
        self._prio.setRange(-1, 3)
        self._prio.setSpecialValueText(label("uiinsp.priority.auto"))
        self._prio.setKeyboardTracking(False)
        self._prio.setToolTip(tooltip(
            title=label("uiinsp.priority.title"), body=label("uiinsp.priority.tip"), note=label("uiinsp.priority.note")))
        self._prio.valueChanged.connect(self._on_prio)
        self._prio_row = W.row(label("uiinsp.priority.label"), self._prio,
                               visible_card.body_layout).parentWidget()
        self._prio_why = note(visible_card.body_layout)
        L.addWidget(visible_card)

        # ── Section TEXTE (zone runtime ET texte authoré) ─────────
        self._text_card = CollapsibleCard(label("common.text"))

        # Contenu ÉDITABLE SUR PLACE d'un texte authoré, pour ne pas avoir à
        # créer l'entrée dans l'écran Texte puis revenir la choisir ici.
        #
        # Le contenu n'est PAS stocké dans l'élément : ce widget édite l'entrée
        # de la table pointée par `text_key` (créée à la volée à la première
        # frappe). Le dupliquer ici le sortirait de l'édition centralisée, donc
        # de la traduction et de l'interpolation `$nom`.
        self._content = QTextEdit()
        self._content.setFont(QFont(T.MONO, T.MD))
        self._content.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px;}}")
        self._content.setFixedHeight(72)
        self._content.setPlaceholderText(label("uiinsp.text.content_placeholder"))
        self._content.setToolTip(tooltip(
            title=label("uiinsp.text.content_title"), body=label("uiinsp.text.content_tip"), note=label("uiinsp.text.content_note")))
        # Même coloration que l'atelier Texte, sinon on tape les balises à
        # l'aveugle ici.
        from ui.text_editor.markup_highlighter import MarkupHighlighter
        self._hl = MarkupHighlighter(self._content.document())
        W.section(label("uiinsp.text.content_section"), self._text_card.body_layout)

        # L'entrée AVANT le champ de saisie : c'est elle qui nomme ce que ce
        # champ édite. Sous le champ, comme avant, on lisait le nom de la chose
        # après l'avoir modifiée.
        self._text_key = QComboBox()
        self._text_key.setFont(QFont(T.UI, T.SM))
        self._text_key.setStyleSheet(QSS.combobox)
        self._text_key.setToolTip(tooltip(
            title=label("uiinsp.text.entry_title"), body=label("uiinsp.text.entry_tip")))
        self._text_key.currentIndexChanged.connect(self._on_text_key)
        self._text_key_row = W.row(label("uiinsp.text.entry"), self._text_key,
                                   self._text_card.body_layout).parentWidget()

        self._content.textChanged.connect(self._on_content_typed)
        self._content.focusOutEvent = self._content_focus_out
        # Commit DIFFÉRÉ : `_persist` sauve le projet et redessine le canvas, ce
        # qui à chaque frappe ferait onze sauvegardes pour « PRESS START ».
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(600)
        self._commit_timer.timeout.connect(self._commit_content)
        self._content_baseline = None   # None = rien en cours d'édition
        self._text_card.body_layout.addWidget(self._content)

        self._key_lbl = note(self._text_card.body_layout)
        self._key_shared = note(self._text_card.body_layout, "ui.text.key_shared")

        # L'ÉCHANTILLON ne sert qu'à une zone SANS entrée — c'est écrit dans son
        # propre tooltip depuis toujours : « editor only, never compiled ». Il
        # ne s'affiche donc que dans ce cas (cf. `_sync_text_rows`). Les deux
        # combos étaient jusqu'ici côte à côte, avec la même allure et la même
        # liste, alors qu'un seul des deux compte à la fois : c'était la
        # première chose incompréhensible de cette carte.
        self._preview = QComboBox()
        self._preview.setFont(QFont(T.UI, T.MD))
        self._preview.setStyleSheet(QSS.combobox)
        self._preview.setToolTip(tooltip(
            title=label("uiinsp.text.sample_title"), body=label("uiinsp.text.sample_tip")))
        self._preview.currentIndexChanged.connect(self._on_preview)
        self._preview_row = W.row(label("uiinsp.text.sample"), self._preview,
                                  self._text_card.body_layout).parentWidget()
        self._preview_why = note(self._text_card.body_layout, "ui.text.sample_only")

        W.section(label("uiinsp.text.typography"), self._text_card.body_layout)

        from ui.common.font_asset_selector import FontAssetSelector
        self._font = FontAssetSelector()
        self._font.changed.connect(self._on_font)
        self._font_row = W.row(label("uiinsp.text.font"), self._font,
                               self._text_card.body_layout).parentWidget()

        # Trois boutons plutôt qu'un menu déroulant : le choix est court, fermé,
        # et se DESSINE — l'icône dit le résultat mieux que le mot « Centered ».
        self._align_group = QButtonGroup(self)
        self._align_group.setExclusive(True)
        align_box = QWidget()
        ab = QHBoxLayout(align_box)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(2)
        for i, (key, tip_key) in enumerate(zip(_ALIGN_ICONS, _ALIGN_TIP_KEYS)):
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedHeight(24)
            b.setStyleSheet(_SEGMENTED)
            b.setIcon(icons.get(key, C.TEXT_DIM, TEXT_ACCENT))
            b.setToolTip(label(tip_key))
            ab.addWidget(b, 1)
            self._align_group.addButton(b, i)
        self._align_group.idToggled.connect(self._on_align_toggled)
        self._align_row = W.row(label("uiinsp.text.alignment"), align_box,
                                self._text_card.body_layout).parentWidget()

        # Couleur du texte : un INDEX dans la banque d'UI de la scène, pas un
        # RGB — le matériel n'offre que des index. 0 = encre d'origine (seul
        # moyen de garder une police à contour) ; sinon l'encre est APLATIE,
        # comme avec `[color=n]`.
        W.section(label("uiinsp.text.colors"), self._text_card.body_layout)

        # LA MÊME liste que le fond du conteneur (les banques ACTIVES de la
        # scène) — mais un texte n'en choisit qu'UNE pour toute la scène, là où
        # un fond choisit librement PAR élément. Ce n'est pas un manque : le
        # matériel sélectionne la banque d'un fond tuile par tuile (gratuit),
        # alors qu'un glyphe est RECOLORÉ en VRAM au chargement, une copie par
        # INDEX employé — si deux zones choisissaient deux banques, « couleur
        # 3 » désignerait deux RGB différents pour une seule copie de glyphes.
        # Réglage de SCÈNE donc (même champ que l'inspecteur de Scène), posé
        # ici pour qu'il n'y ait plus à changer d'écran pour le voir ou le
        # poser — l'écart qui rendait Ink/Highlight incompréhensibles à côté
        # du picker de fond, qui lui semble tout choisir sur place.
        # Ceci vaut pour un texte LIBRE. Un texte imbriqué dans un conteneur à
        # fond ne choisit pas : il prend la banque de son conteneur (cf.
        # `_ink_bank`), et l'hôte porte alors une étiquette en lecture seule à
        # la place du slot — la banque de scène ne le régit pas.
        #
        # Même widget que le picker de fond (`_fill_pal_slot`) — un hôte vide
        # ici, le slot RECONSTRUIT à chaque `_reload_color` : il capture sa
        # liste de slots à la construction, et cette liste appartient à la
        # scène (cf. `_reload_fill_palette`, même raison).
        self._ui_pal_host = QWidget()
        self._ui_pal_host.setStyleSheet("background:transparent;")
        self._ui_pal_box = QVBoxLayout(self._ui_pal_host)
        self._ui_pal_box.setContentsMargins(0, 0, 0, 0)
        self._ui_pal_slot = None
        self._ui_pal_row = W.row(label("uiinsp.text.bank"), self._ui_pal_host,
                                 self._text_card.body_layout).parentWidget()
        self._ui_pal_host.setToolTip(tooltip(
            title=label("uiinsp.text.bank_title"), body=label("uiinsp.text.bank_tip"), note=label("uiinsp.text.bank_note")))

        self._color = ColorIndexSlot(label("uiinsp.text.ink_default"), TEXT_ACCENT)
        self._color.picked.connect(self._on_color)
        self._color.setToolTip(tooltip(
            title=label("uiinsp.text.ink_title"), body=label("uiinsp.text.ink_tip"), note=label("uiinsp.text.ink_note")))
        self._color_row = W.row(label("uiinsp.text.ink"), self._color,
                                self._text_card.body_layout).parentWidget()

        # Surlignement — la couleur posée SOUS le texte. Même banque et même
        # plage que l'encre : la tuile où le texte se compose ne porte qu'UNE
        # banque de palette, le matériel n'en offre pas deux.
        self._highlight = ColorIndexSlot(label("uiinsp.text.highlight_none"), TEXT_ACCENT)
        self._highlight.picked.connect(self._on_highlight)
        self._highlight.setToolTip(tooltip(
            title=label("uiinsp.text.highlight_title"), body=label("uiinsp.text.highlight_tip"), note=label("uiinsp.text.highlight_note")))
        self._highlight_row = W.row(label("uiinsp.text.highlight"), self._highlight,
                                    self._text_card.body_layout).parentWidget()
        self._bank_why = note(self._text_card.body_layout)

        # Ce que la zone COÛTE, sous les réglages qui le font bouger. La ligne
        # d'empreinte vivait dans la carte Geometry : le contrôle était ici, sa
        # conséquence deux cartes plus haut.
        #
        # Il n'y a plus de champ « glyphes animés » : leur nombre se DÉDUIT du
        # texte affiché (cf. `Project.region_animated_glyphs`) au lieu d'être
        # recompté à la main par l'auteur. Il se lit ici, avec le reste du coût.
        W.section(label("uiinsp.text.costs"), self._text_card.body_layout)
        self._size_lbl = note(self._text_card.body_layout)
        self._anim_lbl = note(self._text_card.body_layout)
        L.addWidget(self._text_card)

        # ── Section FOND (conteneur) ──────────────────────────────
        self._fill_card = CollapsibleCard(label("common.background"))

        self._fill_kind = QComboBox()
        self._fill_kind.setFont(QFont(T.UI, T.MD))
        self._fill_kind.setStyleSheet(QSS.combobox)
        for k, key in _FILL_LABEL_KEYS:
            self._fill_kind.addItem(label(key), k)
        self._fill_kind.currentIndexChanged.connect(self._on_fill_kind)
        self._fill_kind_row = W.row(label("common.mode"), self._fill_kind,
                                    self._fill_card.body_layout).parentWidget()

        # Couleur : palette ACTIVE de la scène + index + pastille de rendu.
        #
        # Le slot de sélection partagé (`pickers.palette_picker_slot`) et non
        # une liste de tout le catalogue : `scene_color_fills` écarte du build
        # un fond dont la palette n'est pas dans les palettes BG actives de la
        # scène — il lui faut une banque matérielle. Proposer les autres, c'est
        # promettre un fond que la ROM n'aura pas.
        #
        # Le slot est RECONSTRUIT à chaque chargement (`_reload_fill_palette`) :
        # il capture sa liste à la construction, et cette liste appartient à la
        # scène. D'où l'hôte vide posé ici, qui lui, ne bouge pas.
        color_box = QWidget()
        color_box.setStyleSheet("background:transparent;")
        cc = QHBoxLayout(color_box)
        cc.setContentsMargins(0, 0, 0, 0)
        cc.setSpacing(6)
        self._fill_pal_host = QWidget()
        self._fill_pal_host.setStyleSheet("background:transparent;")
        self._fill_pal_box = QVBoxLayout(self._fill_pal_host)
        self._fill_pal_box.setContentsMargins(0, 0, 0, 0)
        self._fill_pal_slot = None
        cc.addWidget(self._fill_pal_host, 1)
        self._fill_index = QSpinBox()
        self._fill_index.setFont(QFont(T.MONO, T.MD))
        self._fill_index.setStyleSheet(QSS.spinbox)
        self._fill_index.setRange(0, 15)
        self._fill_index.setKeyboardTracking(False)
        self._fill_index.valueChanged.connect(self._on_fill_index)
        cc.addWidget(self._fill_index)
        self._fill_swatch = QLabel()
        self._fill_swatch.setFixedSize(22, 22)
        cc.addWidget(self._fill_swatch)
        self._fill_color_row = W.row(label("uiinsp.fill.color_row"), color_box,
                                     self._fill_card.body_layout).parentWidget()

        self._fill_asset = QComboBox()
        self._fill_asset.setFont(QFont(T.UI, T.SM))
        self._fill_asset.setStyleSheet(QSS.combobox)
        self._fill_asset.currentIndexChanged.connect(self._on_fill_asset)
        self._fill_asset_row = W.row(label("uiinsp.fill.asset"), self._fill_asset,
                                     self._fill_card.body_layout).parentWidget()

        # ── Fond SPRITE (cible OBJ) ───────────────────────────────
        # Mêmes trois questions que pour une image — quel sprite, quel état —
        # plus la seule chose qu'un fond ajoute : sa cadence propre.
        self._fill_sprite = QComboBox()
        self._fill_sprite.setFont(QFont(T.UI, T.SM))
        self._fill_sprite.setStyleSheet(QSS.combobox)
        self._fill_sprite.setToolTip(tooltip(
            title=label("uiinsp.fill.sprite_title"), body=label("uiinsp.fill.sprite_tip"), note=label("uiinsp.fill.sprite_note")))
        self._fill_sprite.currentIndexChanged.connect(self._on_fill_sprite)
        self._fill_sprite_row = W.row(label("common.sprite"), self._fill_sprite,
                                      self._fill_card.body_layout).parentWidget()

        self._fill_state = QComboBox()
        self._fill_state.setFont(QFont(T.UI, T.SM))
        self._fill_state.setStyleSheet(QSS.combobox)
        self._fill_state.setToolTip(tooltip(
            title=label("uiinsp.fill.state_title"), body=label("uiinsp.fill.state_tip"), note=label("uiinsp.fill.state_note")))
        self._fill_state.currentIndexChanged.connect(self._on_fill_state)
        self._fill_state_row = W.row(label("uiinsp.fill.state"), self._fill_state,
                                     self._fill_card.body_layout).parentWidget()

        self._fill_speed = QSpinBox()
        self._fill_speed.setFont(QFont(T.MONO, T.MD))
        self._fill_speed.setStyleSheet(QSS.spinbox)
        self._fill_speed.setRange(0, 255)
        self._fill_speed.setSpecialValueText(label("uiinsp.fill.speed_from"))
        self._fill_speed.setSuffix(label("uiinsp.fill.speed_suffix"))
        self._fill_speed.setKeyboardTracking(False)
        self._fill_speed.setToolTip(tooltip(
            title=label("uiinsp.fill.speed_title"), body=label("uiinsp.fill.speed_tip"), note=label("uiinsp.fill.speed_note")))
        self._fill_speed.valueChanged.connect(self._on_fill_speed)
        self._fill_speed_row = W.row(label("common.speed"), self._fill_speed,
                                     self._fill_card.body_layout).parentWidget()

        # Marges de coupe du cadre sélectionné. Elles vivent sur le FOND
        # D'INTERFACE lui-même (`BackgroundAsset.slice_*`), asset PARTAGÉ entre
        # tous les panels qui le citent — d'où le persist projet. Pas de champ
        # « source » ici : le fond cité EST l'image. Pas de bouton « créer un
        # cadre » non plus — un cadre s'importe dans le Background Editor, comme
        # toute autre image, et c'est là que le canvas montre où passe la coupe.
        ns_margins = QWidget()
        ns_margins.setStyleSheet("background:transparent;")
        mrow = QHBoxLayout(ns_margins)
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.setSpacing(4)
        self._ns_m = {}
        for key, lab in (("slice_left", "L"), ("slice_right", "R"),
                         ("slice_top", "T"), ("slice_bottom", "B")):
            t = QLabel(lab)
            t.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
            t.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
            t.setFixedWidth(14)
            sp = QSpinBox()
            sp.setFont(QFont(T.MONO, T.SM))
            sp.setStyleSheet(QSS.spinbox)
            sp.setRange(0, 64)
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda v, k=key: self._on_ns_margin(k, v))
            mrow.addWidget(t)
            mrow.addWidget(sp, 1)
            self._ns_m[key] = sp
        self._ns_margins_row = W.row(label("uiinsp.fill.margins"), ns_margins,
                                     self._fill_card.body_layout).parentWidget()

        self._fill_why = note(self._fill_card.body_layout)
        self._fill_overflow = note(self._fill_card.body_layout,
                                   "ui.fill.sprite_overflow")
        # Niveau 2 : la palette citée est un RISQUE AU BUILD, et il porte
        # sur un champ précis — l'encadré se pose donc contre lui, au lieu
        # de se perdre au milieu du paragraphe qui décrit le mode.
        self._fill_pal_why = notice("ui.fill.color_inactive",
                                    self._fill_color_row,
                                    self._fill_card.body_layout)
        L.addWidget(self._fill_card)

        # ── Section LISTE (ROADMAP v0.22) ─────────────────────────
        # L'inspecteur d'un TYPE depuis le 2026-09-02, et non plus une case à
        # cocher posée sur chaque conteneur : le moteur prend toujours la
        # navigation et pas la mise en page, mais la navigation a un
        # propriétaire. Les rangées restent les zones de texte posées DANS la
        # liste — rien à déclarer de plus.
        self._list_card = CollapsibleCard(label("common.list"))
        W.section(label("uiinsp.list.navigation"), self._list_card.body_layout)

        self._list_active = W.checkbox_row(
            label("uiinsp.list.selection"), label("uiinsp.list.selection_sub"),
            self._list_card.body_layout)
        self._list_active.setToolTip(tooltip(
            title=label("uiinsp.list.selection_title"), body=label("uiinsp.list.selection_tip"), note=label("uiinsp.list.selection_note")))
        self._list_active.toggled.connect(
            lambda v: self._set("active", bool(v), "List selection"))

        # La GRILLE en deux nombres : sans compte de colonnes, un parcours en Z
        # ou en W ne se calcule pas — le moteur ne saurait pas de combien
        # sauter en changeant de ligne. Cf. `NAV_ROW`/`NAV_COLUMN`.
        self._list_cols = QSpinBox()
        self._list_cols.setFont(QFont(T.MONO, T.SM))
        self._list_cols.setStyleSheet(QSS.spinbox)
        self._list_cols.setRange(1, 64)
        self._list_cols.setKeyboardTracking(False)
        self._list_cols.setToolTip(tooltip(
            title=label("uiinsp.list.columns_title"), body=label("uiinsp.list.columns_tip"), note=label("uiinsp.list.columns_note")))
        self._list_cols.valueChanged.connect(
            lambda v: (self._set("nav_columns", int(v), "List columns"),
                       self._sync_list_rows()))
        W.row(label("uiinsp.list.columns"), self._list_cols, self._list_card.body_layout)

        self._list_major = W.combobox([label("uiinsp.list.order_col"),
                                       label("uiinsp.list.order_row")])
        self._list_major.setToolTip(tooltip(
            title=label("uiinsp.list.order_title"), body=label("uiinsp.list.order_tip"), note=label("uiinsp.list.order_note")))
        self._list_major.currentIndexChanged.connect(
            lambda i: (self._set("nav_major", NAV_ROW if i == 1 else NAV_COLUMN,
                                 "List order"),
                       self._sync_list_rows()))
        W.row(label("uiinsp.list.order"), self._list_major, self._list_card.body_layout)

        self._list_wrap = W.checkbox_row(
            label("uiinsp.list.wrap"), label("uiinsp.list.wrap_sub"),
            self._list_card.body_layout)
        self._list_wrap.toggled.connect(
            lambda v: self._set("wrap", bool(v), "List wrap"))
        self._list_why = note(self._list_card.body_layout)
        self._list_shape = note(self._list_card.body_layout)

        # ── Curseur — la liste le POSSÈDE ─────────────────────────
        # Elle NOMME une image de la même mise en page ; le moteur la déplace
        # par le chemin de `interface.image_move`, un décalage relatif à la position
        # authorée. L'auteur pose donc son curseur en face de la PREMIÈRE
        # rangée, et n'a rien à écrire pour qu'il suive la sélection.
        W.section(label("uiinsp.list.cursor_section"), self._list_card.body_layout)
        self._list_cursor = W.combobox([])
        self._list_cursor.setToolTip(tooltip(
            title=label("uiinsp.list.cursor_title"), body=label("uiinsp.list.cursor_tip"), note=label("uiinsp.list.cursor_note")))
        self._list_cursor.currentIndexChanged.connect(self._on_list_cursor)
        W.row(label("common.image"), self._list_cursor, self._list_card.body_layout)

        self._list_cursor_mode = W.combobox([label("uiinsp.list.motion_snap"),
                                             label("uiinsp.list.motion_slide")])
        self._list_cursor_mode.setToolTip(tooltip(
            title=label("uiinsp.list.motion_title"), body=label("uiinsp.list.motion_tip")))
        self._list_cursor_mode.currentIndexChanged.connect(
            lambda i: (self._set("cursor_mode",
                                 CURSOR_SLIDE if i == 1 else CURSOR_SNAP,
                                 "Cursor motion"),
                       self._sync_list_cursor()))
        W.row(label("uiinsp.list.motion"), self._list_cursor_mode, self._list_card.body_layout)

        self._list_cursor_speed = QSpinBox()
        self._list_cursor_speed.setFont(QFont(T.MONO, T.SM))
        self._list_cursor_speed.setStyleSheet(QSS.spinbox)
        self._list_cursor_speed.setRange(1, 64)
        self._list_cursor_speed.setSuffix(label("uiinsp.list.speed_suffix"))
        self._list_cursor_speed.setKeyboardTracking(False)
        self._list_cursor_speed.valueChanged.connect(
            lambda v: self._set("cursor_speed", int(v), "Cursor speed"))
        self._list_cursor_speed_row = W.row(
            label("common.speed"), self._list_cursor_speed,
            self._list_card.body_layout).parentWidget()
        self._list_cursor_why = note(self._list_card.body_layout,
                                     "ui.list.cursor_missing")

        # ── Style de la rangée choisie ────────────────────────────
        # Les deux réglages qu'une zone porte déjà, appliqués par le moteur en
        # suivant l'index : même banque, même plage, même zéro. Une ANIMATION
        # n'est pas offerte — sur cible BG elle réécrirait des tuiles à chaque
        # frame, et ce coût se mesure avant de se promettre.
        W.section(label("uiinsp.list.selrow"), self._list_card.body_layout)
        self._list_ink = ColorIndexSlot(label("uiinsp.list.ink_default"), TEXT_ACCENT)
        self._list_ink.picked.connect(
            lambda i: self._set("selected_text_color", int(i), "Selected ink"))
        self._list_ink.setToolTip(tooltip(
            title=label("uiinsp.list.ink_title"), body=label("uiinsp.list.ink_tip"), note=label("uiinsp.list.ink_note")))
        W.row(label("uiinsp.list.ink"), self._list_ink, self._list_card.body_layout)

        self._list_hl = ColorIndexSlot(label("uiinsp.list.highlight_none"), TEXT_ACCENT)
        self._list_hl.picked.connect(
            lambda i: self._set("selected_highlight_color", int(i),
                                "Selected highlight"))
        self._list_hl.setToolTip(tooltip(
            title=label("uiinsp.list.highlight_title"), body=label("uiinsp.list.highlight_tip")))
        W.row(label("uiinsp.list.highlight"), self._list_hl, self._list_card.body_layout)
        L.addWidget(self._list_card)

        # ── Section IMAGE (sprite à état) ─────────────────────────
        # L'élément DÉSIGNE, il ne redéfinit pas : ni vitesse, ni liste de
        # frames, ni direction ici — tout ça vit dans le SpriteAsset et s'édite
        # dans le Sprite Editor. Recopier une vitesse donnerait deux vérités
        # pour un même dessin (cf. models/ui_region.UIImage).
        self._img_card = CollapsibleCard(label("common.image"))

        self._img_sprite = QComboBox()
        self._img_sprite.setFont(QFont(T.UI, T.MD))
        self._img_sprite.setStyleSheet(QSS.combobox)
        self._img_sprite.setToolTip(tooltip(
            title=label("uiinsp.img.sprite_title"), body=label("uiinsp.img.sprite_tip"), note=label("uiinsp.img.sprite_note")))
        self._img_sprite.currentIndexChanged.connect(self._on_img_sprite)
        self._img_sprite_row = W.row(label("common.sprite"), self._img_sprite,
                                     self._img_card.body_layout).parentWidget()

        self._img_state = QComboBox()
        self._img_state.setFont(QFont(T.UI, T.MD))
        self._img_state.setStyleSheet(QSS.combobox)
        self._img_state.setToolTip(tooltip(
            title=label("uiinsp.img.state_title"), body=label("uiinsp.img.state_tip"), note=label("uiinsp.img.state_note")))
        self._img_state.currentIndexChanged.connect(self._on_img_state)
        self._img_state_row = W.row(label("uiinsp.img.state"), self._img_state,
                                    self._img_card.body_layout).parentWidget()

        self._img_play = QComboBox()
        self._img_play.setFont(QFont(T.UI, T.MD))
        self._img_play.setStyleSheet(QSS.combobox)
        self._img_play.addItem(label("uiinsp.img.playing"), True)
        self._img_play.addItem(label("uiinsp.img.frozen"), False)
        self._img_play.setToolTip(tooltip(
            title=label("uiinsp.img.play_title"), body=label("uiinsp.img.play_tip")))
        self._img_play.currentIndexChanged.connect(self._on_img_play)
        self._img_play_row = W.row(label("uiinsp.img.frames"), self._img_play,
                                   self._img_card.body_layout).parentWidget()

        # La priorité n'est plus ici : elle vit dans la carte Geometry
        # (`self._prio`), portée par chaque élément d'UI, pas seulement l'image.

        self._img_why = note(self._img_card.body_layout)
        self._img_missing = notice("ui.image.missing", self._img_sprite,
                                   self._img_card.body_layout)
        self._img_none = notice("ui.image.none", self._img_sprite,
                                self._img_card.body_layout)
        L.addWidget(self._img_card)

        # ── Suppression ───────────────────────────────────────────
        # Il n'y a plus de label d'avertissement ICI : chaque message est posé
        # sous le réglage qui le cause (empreinte sous le texte, fond sous le
        # fond) plutôt que dans un bac commun au pied de l'inspecteur.
        W.separator(L)
        self._del = W.btn_ghost(label("uiinsp.delete"))
        self._del.setFont(QFont(T.UI, T.SM))
        self._del.clicked.connect(self._on_delete)
        L.addWidget(self._del)
        L.addStretch()

    # ── Presets de placement ──────────────────────────────────────
    def _preset_btn(self, hpos: str, vpos: str,
                    sh: bool = False, sv: bool = False) -> QToolButton:
        b = QToolButton()
        b.setFixedSize(24, 24)
        b.setStyleSheet(QSS.toolbutton_icon)
        b.setIcon(_preset_icon(hpos, vpos, sh, sv))
        b.setIconSize(b.size() * 0.8)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(_preset_tip(hpos, vpos, sh, sv))
        b.clicked.connect(lambda _=False: self._apply_preset(hpos, vpos, sh, sv))
        return b

    def _apply_preset(self, hpos: str, vpos: str, sh: bool, sv: bool):
        """Repose l'élément dans son cadre. UNE commande pour les quatre champs
        (`ResizeUIRegionCmd`, celle des poignées du canvas) : quatre
        `SetFieldCmd` donneraient quatre annulations pour un clic."""
        el, lay = self._element, self._layout_asset
        if el is None or lay is None:
            return
        fw, fh = lay.frame_size(el)
        tile = lay.resolved_target(el, self._render_mode()) == TARGET_BG
        old = (el.x, el.y, el.w, el.h)
        new = preset_rect(el.w, el.h, fw, fh, hpos, vpos, sh, sv, tile)
        if tuple(new) == old:
            return
        from core.history import get_history, ResizeUIRegionCmd
        cmd = ResizeUIRegionCmd(el, old, new, persist_fn=self._persist)
        cmd.label = f"Place {el.name} — {_preset_tip(hpos, vpos, sh, sv)}"
        get_history().push(cmd)
        self._blocking = True
        try:
            for k in ("x", "y", "w", "h"):
                self._sp[k].setValue(int(getattr(el, k)))
        finally:
            self._blocking = False
        self._refresh_diagnostics()

    # ── Chargement ────────────────────────────────────────────────
    def load(self, layout_asset, element, project: Project, scene):
        # Une frappe en attente appartient à l'élément PRÉCÉDENT : la commiter
        # avant de changer de contexte, sinon le timer tirera sur le nouveau.
        self._commit_content()
        self._layout_asset, self._element = layout_asset, element
        self._project, self._scene = project, scene
        self._blocking = True
        try:
            kind = self._kind()

            users = project.ui_layout_users(layout_asset.name) if project else []
            self._layout_lbl.show_text(name=layout_asset.name)
            if len(users) > 1:
                self._layout_shared.show_text(n=len(users))
            else:
                self._layout_shared.clear()

            for k in ("x", "y", "w", "h"):
                self._sp[k].setValue(int(getattr(element, k, 0)))
            self._prio.setValue(int(getattr(element, "priority", PRIORITY_INHERIT)))
            # La priorité OBJ n'agit qu'en cible OBJ : sous un nœud écran/monde
            # (BG), la profondeur est celle du layer. On le DIT plutôt que de
            # cacher un champ que l'auteur a demandé sur chaque élément.
            if self._layout_asset.resolved_target(element, self._render_mode()) != TARGET_BG:
                self._prio_why.clear()
            else:
                self._prio_why.show_text("ui.priority.bg")
            self._visible.setChecked(bool(getattr(element, "visible", True)))
            self._sync_visible_hint()

            # Sections par type — tout se montre/cache ICI, une seule fois.
            is_text  = kind == KIND_TEXT
            is_list  = kind == KIND_LIST
            is_image = kind == KIND_IMAGE
            # Le FOND suit la capacité et non le type : les deux conteneurs en
            # dessinent un (cf. `FillMixin`), et demander le type ici ferait
            # disparaître la carte de la liste sans que rien ne le dise.
            has_fill = can_fill(element)
            self._text_card.setVisible(is_text)
            self._fill_card.setVisible(has_fill)
            self._list_card.setVisible(is_list)
            self._img_card.setVisible(is_image)
            # La taille d'une image est celle de la frame de son sprite : la
            # laisser éditable inviterait à un étirement que le matériel ne sait
            # pas faire. Les presets de PLACEMENT restent actifs (ils ne
            # redimensionnent pas sans `stretch_*`).
            for k in ("w", "h"):
                self._sp[k].setEnabled(not is_image)
            self._del.setText(label("uiinsp.delete"))

            if is_text:
                self._reload_fonts()
                btn = self._align_group.button(
                    ALIGNS.index(element.align) if element.align in ALIGNS else 0)
                if btn is not None:
                    btn.setChecked(True)
                self._reload_color()
                self._reload_previews()
                self._reload_text_key()
                self._reload_content()
                self._sync_text_rows()
            if has_fill:
                self._reload_fill()
            if is_list:
                self._reload_list()
            if is_image:
                self._reload_image()

            self._sync_geom()
            self._refresh_diagnostics()
        finally:
            self._blocking = False

    # ── Contexte ──────────────────────────────────────────────────
    def _kind(self) -> str:
        return getattr(self._element, "kind", KIND_TEXT)

    def _render_mode(self) -> int:
        return int(getattr(self._scene, "render_mode", 0) or 0)

    # ── Rechargements de combos ───────────────────────────────────
    def _reload_fonts(self):
        self._font.set_project(self._project)
        legacy_name = getattr(self._element, "font_name", "") or ""
        legacy_font = self._project.fonts.get(legacy_name) if self._project and legacy_name else None
        weight = getattr(self._element, "font_weight", None)
        italic = getattr(self._element, "font_italic", None)
        self._font.set_value(legacy_name, int(weight if weight is not None else
                                               getattr(legacy_font, "weight", 400)),
                             bool(italic if italic is not None else
                                  getattr(legacy_font, "italic", False)))

    def _reload_previews(self):
        self._preview.clear()
        self._preview.addItem(label("common.none_paren"), "")
        values = self._project.text_values() if self._project else {}
        for t in (self._project.texts if self._project else []):
            self._preview.addItem(
                f"{t.key} — {display_text(t.content, values)[:24]}", t.key)
        i = self._preview.findData(getattr(self._element, "preview_text", "") or "")
        self._preview.setCurrentIndex(i if i >= 0 else 0)

    def _reload_text_key(self):
        self._text_key.clear()
        self._text_key.addItem(label("uiinsp.text.entry_new"), "")
        for t in (self._project.texts if self._project else []):
            self._text_key.addItem(t.key, t.key)
        i = self._text_key.findData(getattr(self._element, "text_key", "") or "")
        self._text_key.setCurrentIndex(i if i >= 0 else 0)

    # ── Image (désigne un sprite et l'un de ses états) ────────────
    def _current_sprite(self):
        """Le SpriteAsset que cette image affiche, ou None (nom vide/cassé)."""
        name = getattr(self._element, "sprite_name", "") or ""
        if not (self._project and name):
            return None
        return next((s for s in getattr(self._project, "sprites", [])
                     if s.name == name), None)

    def _reload_image(self):
        prev, self._blocking = self._blocking, True
        try:
            self._img_sprite.clear()
            self._img_sprite.addItem(label("uiinsp.img.sprite_none"), "")
            for s in (getattr(self._project, "sprites", []) if self._project else []):
                self._img_sprite.addItem(s.name, s.name)
            i = self._img_sprite.findData(getattr(self._element, "sprite_name", "") or "")
            self._img_sprite.setCurrentIndex(i if i >= 0 else 0)
            self._reload_image_states()
            j = self._img_play.findData(bool(getattr(self._element, "playing", True)))
            self._img_play.setCurrentIndex(j if j >= 0 else 0)
        finally:
            self._blocking = prev
        self._sync_image_note()

    def _reload_image_states(self):
        """Les états du sprite courant. « (first state) » plutôt qu'un premier
        état nommé en dur : un `state_name` vide suit le sprite quand on en
        réordonne les états, un nom figé désignerait l'ancien."""
        self._img_state.blockSignals(True)
        self._img_state.clear()
        sprite = self._current_sprite()
        self._img_state.addItem(label("uiinsp.img.state_first"), "")
        for st in (getattr(sprite, "states", []) if sprite else []):
            self._img_state.addItem(st.name, st.name)
        self._img_state.setEnabled(sprite is not None)
        k = self._img_state.findData(getattr(self._element, "state_name", "") or "")
        self._img_state.setCurrentIndex(k if k >= 0 else 0)
        self._img_state.blockSignals(False)

    def _sprite_frame_count(self, sprite) -> int:
        """Frames que le build chargera pour ce sprite.

        `count_frames`, celle du build, et pas un comptage maison : elle DÉDUPLIQUE
        (deux états qui partagent une pose ne coûtent qu'une frame), et annoncer
        ici un chiffre plus gros que celui réservé ferait douter de la jauge à
        chaque fois que les deux ne tombent pas d'accord."""
        if sprite is None or self._project is None:
            return 1
        from codegen.grit_conversion import count_frames
        return count_frames(self._project, sprite)

    def _sync_image_note(self):
        """Ce que l'image coûte, dit avant le build. Un sprite manquant est un
        trou visible à l'écran, pas une erreur de compilation : on le nomme."""
        el = self._element
        if el is None or self._kind() != KIND_IMAGE:
            return
        sprite = self._current_sprite()
        bound = str(getattr(el, "sprite_name", "") or "")
        if sprite is None:
            # Deux messages, pas un ternaire : « rien de choisi » et « le nom
            # ne répond plus » n'appellent pas le même geste, et un traducteur
            # ne peut pas deviner qu'une phrase en cache deux.
            self._img_why.clear()
            if bound:
                self._img_missing.show_text(sprite=bound)
                self._img_none.clear()
            else:
                self._img_none.show_text()
                self._img_missing.clear()
            return
        self._img_missing.clear()
        self._img_none.clear()
        frames = self._sprite_frame_count(sprite)
        g = image_geometry(el, frames)
        target = self._layout_asset.resolved_target(el, self._render_mode())
        # Une image OBJ ne réserve RIEN : ses tuiles sont celles du sprite, déjà
        # résidentes. Annoncer un coût VRAM là serait compter deux fois le même
        # dessin (cf. models/ui_region.layout_obj_budget).
        where = text("ui.image.where_obj" if target == TARGET_OBJ
                     else "ui.image.where_bg", n=g["tiles"])
        self._img_why.show_text("ui.image.cost", w=el.w, h=el.h,
                                n=frames, where=where)

    def _on_img_sprite(self, i):
        """Choisir un sprite REDIMENSIONNE l'élément sur sa frame — une seule
        entrée d'historique pour les deux, sinon annuler laisserait un rectangle
        qui ne correspond à aucun dessin."""
        if self._blocking or not self._element or i < 0:
            return
        name = self._img_sprite.currentData() or ""
        self._set("sprite_name", name, "Image sprite")
        # `state_name` pointe un état de l'ANCIEN sprite : le remettre au défaut
        # plutôt que de garder une ref qui ne résout plus (elle retomberait
        # silencieusement sur l'état 0 au build).
        self._set("state_name", "", "Image state")
        sprite = self._current_sprite()
        if sprite is not None and self._element.sync_size_from(sprite):
            self._blocking = True
            try:
                for k in ("w", "h"):
                    self._sp[k].setValue(int(getattr(self._element, k)))
            finally:
                self._blocking = False
        self._blocking = True
        try:
            self._reload_image_states()
        finally:
            self._blocking = False
        self._persist()
        self._sync_image_note()

    def _on_img_state(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("state_name", self._img_state.currentData() or "", "Image state")

    def _on_img_play(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("playing", bool(self._img_play.currentData()), "Image playback")
        self._sync_image_note()

    def _on_prio(self, v):
        """Priorité OBJ de N'IMPORTE quel élément d'UI (texte, image, fond de
        conteneur) — le champ vit dans Geometry. -1 = héritée."""
        if self._blocking or not self._element:
            return
        self._set("priority", int(v), "Priority")

    # ── Contenu (édite l'entrée de table, pas l'élément) ──────────
    def _current_text(self):
        """L'entrée de table que cet élément affiche, ou None s'il n'en a pas
        encore (elle naîtra à la première frappe)."""
        key = getattr(self._element, "text_key", "") or ""
        return self._project.get_text(key) if (self._project and key) else None

    def _reload_content(self):
        """Repose le contenu et le badge de clé. Sous `_blocking` : setPlainText
        déclenche `textChanged`, qui prendrait un rechargement pour une frappe."""
        t = self._current_text()
        self._content.setPlainText(t.content if t else "")
        self._content_baseline = None
        self._sync_key_badge()

    def _sync_text_rows(self):
        """L'échantillon n'apparaît QUE pour une zone sans entrée.

        Une zone qui a son entrée a déjà un contenu réel à mesurer et à
        montrer dans le canvas ; lui proposer en plus un « échantillon » tiré
        de la même liste posait deux fois la même question, dont une seule
        comptait. Vide, l'échantillon est la seule idée que l'éditeur ait de
        ce que le script y écrira — et la mesure de débordement s'appuie
        dessus."""
        has_entry = bool(getattr(self._element, "text_key", "") or "")
        self._preview_row.setVisible(not has_entry)
        if has_entry:
            self._preview_why.clear()
        else:
            self._preview_why.show_text()

    def _sync_key_badge(self):
        """Le badge sous l'éditeur : quelle entrée, dérivée ou nommée, partagée
        ou non. Séparé du rechargement du contenu — le reposer pendant que
        l'utilisateur écrit lui remettrait le curseur au début."""
        t = self._current_text()
        if t is None:
            self._key_lbl.show_text("ui.text.key_none")
            self._key_shared.clear()
            return
        users = self._text_users(t.key)
        # La clé n'est PLUS répétée ici : le combo « Entry », juste au-dessus du
        # champ, la porte déjà. Son origine (dérivée ou nommée) n'apprenait rien
        # d'exploitable non plus : seul reste ce qui appelle un geste — l'entrée
        # absente, ou partagée avec d'autres éléments.
        self._key_lbl.clear()
        # Une entrée partagée se corrige en un endroit — mais se casse aussi en
        # un endroit. Même règle que le badge « mise en page partagée » : c'est
        # une portée, donc du périwinkle sur sa propre ligne.
        if users:
            self._key_shared.show_text(n=users)
        else:
            self._key_shared.clear()

    def _text_users(self, key: str) -> int:
        """Autres éléments d'UI du projet qui affichent la même entrée."""
        if not self._project:
            return 0
        return sum(1 for _l, e in self._project.all_regions()
                   if e is not self._element
                   and getattr(e, "text_key", "") == key)

    def _on_content_typed(self):
        """Frappe : on écrit dans le modèle TOUT DE SUITE — c'est ce qui fait
        vivre l'aperçu du canvas — mais on ne sauve ni ne pousse d'historique
        avant la fin de la salve."""
        if self._blocking or not self._element or self._kind() != KIND_TEXT:
            return
        new = self._content.toPlainText()
        t = self._current_text()
        if t is None:
            if not new.strip():
                return          # frappe vide : pas de quoi créer une entrée
            self._create_text_entry(new)
            self.changed.emit()
            self._commit_timer.start()
            return
        if self._content_baseline is None:
            self._content_baseline = t.content      # début de salve
        t.content = new
        self.changed.emit()     # redessin du canvas, sans écriture disque
        self._commit_timer.start()

    def _content_focus_out(self, e):
        QTextEdit.focusOutEvent(self._content, e)
        self._commit_content()

    def _commit_content(self):
        """Fin de salve : une commande d'historique et une sauvegarde.

        La valeur est DÉJÀ dans le modèle (posée à la frappe) : la commande la
        repose à l'identique, elle n'existe que pour rendre le geste annulable.
        `SetFieldCmd.merge` fusionne la salve en une entrée d'historique."""
        self._commit_timer.stop()
        if self._content_baseline is None:
            return
        old, self._content_baseline = self._content_baseline, None
        t = self._current_text()
        if t is None or t.content == old:
            return
        from core.history import get_history, SetFieldCmd
        get_history().push(SetFieldCmd(
            t, "content", old, t.content,
            label=f"Edit text {t.key}", persist_fn=self._persist))

    def _create_text_entry(self, content: str):
        """Crée l'entrée de table qui manquait et l'accroche à l'élément.

        Le chemin PROPOSE la clé : mise en page puis nom de l'élément, ce qui
        situe sans jamais posséder (`auto_key` reste vrai, ranger l'entrée
        ailleurs la recalera). Cf. models/text.py."""
        from ui.text_editor.text_commands import CreateTextForElementCmd
        from core.history import get_history
        get_history().push(CreateTextForElementCmd(
            self._project, self._element, content,
            path=[self._layout_asset.name, self._element.name],
            scene=getattr(self._scene, "name", "") or "",
            persist_fn=self._persist))
        self._blocking = True
        try:
            self._reload_text_key()     # l'entrée neuve entre dans la liste
            self._sync_key_badge()
        finally:
            self._blocking = False

    # ── Géométrie : pas de grille selon la cible HÉRITÉE du nœud ───
    def _sync_geom(self):
        """Adapte le pas des spinbox et le titre à la cible héritée du nœud
        `Interface` (v0.25) — l'élément ne CHOISIT plus sa cible, il la subit :
        un BG ne se pose pas hors grille (pas de 8), un enfant se place relativement
        à son parent. Aucun contrôle d'ancrage/cible ici, ils sont sur le nœud."""
        e, rm = self._element, self._render_mode()
        lay = self._layout_asset
        is_child = bool(e.parent) and lay.get(e.parent) is not None
        eff_anchor, _ = lay.effective_anchor(e)
        eff = lay.resolved_target(e, rm)

        step = 8 if eff == TARGET_BG else 1
        for k in ("x", "y", "w", "h"):
            self._sp[k].setSingleStep(step)
        self._geom_lbl.set_title(
            label("uiinsp.card.geometry_child") if is_child
            else label("uiinsp.card.geometry_bg") if eff == TARGET_BG
            else label("uiinsp.card.geometry_actor") if eff_anchor == ANCHOR_ACTOR
            else label("uiinsp.card.geometry"))

    def _actor_pos(self, name: str):
        """(x, y) de l'acteur nommé, ou None — même contrat que
        `SceneRegionItem._actor_pos` dans scene_canvas.py : passé aux helpers
        d'ancrage du modèle, qui eux ne connaissent pas la scène."""
        for a in getattr(self._scene, "actors", []):
            if a.name == name:
                return (a.x, a.y)
        return None

    def _sync_visible_hint(self):
        """Dit pourquoi l'élément ne s'affiche pas quand la case est cochée :
        un ancêtre caché l'emporte sans jamais toucher à cette case (cf.
        `UILayout.is_visible`, qui remonte la chaîne au lieu de la propager)."""
        e, lay = self._element, self._layout_asset
        if e is None or lay is None or not self._visible.isChecked():
            self._visible_why.clear()
            return
        hidden_ancestor = next(
            (a for a in lay.ancestors(e.name)
             if not getattr(lay.get(a), "visible", True)), None)
        if hidden_ancestor:
            self._visible_why.show_text(parent=hidden_ancestor)
        else:
            self._visible_why.clear()

    def _refresh_diagnostics(self):
        """Empreinte + avertissements d'un élément de TEXTE.

        L'empreinte va sous le texte ; l'alerte « ancré sur un acteur sans acteur
        choisi » vit désormais sur le NŒUD (`UINodeInspector`), l'ancrage n'étant
        plus un réglage de l'élément (v0.25). Une image a sa propre note
        (`_sync_image_note`) : son empreinte se lit dans le sprite, pas dans le
        rectangle. Un conteneur n'en a aucune."""
        if self._kind() == KIND_IMAGE:
            self._size_lbl.clear()
            self._anim_lbl.clear()
            self._sync_image_note()
            return
        if self._kind() != KIND_TEXT:
            self._size_lbl.clear()
            self._anim_lbl.clear()
            return
        r, rm = self._element, self._render_mode()
        lay = self._layout_asset
        target = lay.resolved_target(r, rm)
        tx, ty, tw, th = r.tile_rect()
        # DÉDUIT du texte affiché, plus déclaré à la main : c'est le parseur qui
        # compte les portées `[wave]`/`[shake]`, sur toutes les langues.
        anim = (self._project.region_animated_glyphs(r) if self._project else 0)
        if target == TARGET_OBJ:
            from core.models.ui_region import strip_geometry
            g = strip_geometry(r, anim)
            self._size_lbl.show_text("ui.text.footprint_obj", w=tw, h=th,
                                     oam=g["oam"], tiles=g["tiles"])
        else:
            self._size_lbl.show_text("ui.text.footprint_bg", w=tw, h=th, n=tw * th)
        self._sync_anim_note(anim, target)

    def _sync_anim_note(self, anim: int, target: str):
        """Ce que les effets animés réservent — CONSTAT, jamais une question.

        Muet quand il n'y a rien à animer : la ligne n'apparaît que si le texte
        porte `[wave]` ou `[shake]`. On prévient dans les deux cas où le
        matériel ne suivra pas — une cible BG, qui n'a pas de sprite pour sortir
        un glyphe de la bande, et le plafond de capture du runtime."""
        from core.models.ui_region import ANIM_GLYPH_MAX
        if not anim:
            self._anim_lbl.clear()
            return
        if target != TARGET_OBJ:
            self._anim_lbl.show_text("ui.text.anim_bg", n=anim)
        elif anim >= ANIM_GLYPH_MAX:
            self._anim_lbl.show_text("ui.text.anim_capped",
                                     n=anim, max=ANIM_GLYPH_MAX)
        else:
            self._anim_lbl.show_text("ui.text.anim_reserved", n=anim)

    # ── Fond (conteneur) ──────────────────────────────────────────
    def _reload_fill(self):
        """Peuple la section fond et grise les modes incompatibles avec la cible
        (dérivée du root) : un background n'est pas un sprite."""
        el, rm = self._element, self._render_mode()
        target = self._layout_asset.resolved_target(el, rm)
        for i in range(self._fill_kind.count()):
            item = self._fill_kind.model().item(i)
            if item is not None:
                item.setEnabled(fill_allowed(self._fill_kind.itemData(i), target))
        fi = self._fill_kind.findData(getattr(el, "fill_kind", FILL_NONE))
        self._fill_kind.setCurrentIndex(fi if fi >= 0 else 0)
        self._reload_fill_palette()
        self._fill_index.setValue(int(getattr(el, "fill_index", 0) or 0))
        self._reload_fill_asset()
        self._reload_fill_sprite()
        self._sync_fill()

    def _active_bg_palettes(self) -> list[str]:
        """Noms des palettes BG actives de la scène — celles qui ont une banque
        matérielle, donc les seules qu'un fond couleur puisse citer."""
        return list(getattr(self._scene, "active_bg_palettes", []) or [])

    def _reload_fill_palette(self):
        """(Re)construit le slot de palette du fond, filtré aux palettes BG
        ACTIVES. Reconstruit et non repeuplé : `palette_picker_slot` capture sa
        liste à la construction, et cette liste change avec la scène.

        Une palette DÉJÀ posée mais devenue inactive reste AFFICHÉE — l'effacer
        du slot cacherait la valeur qui est dans le fichier au lieu de dire
        qu'elle ne sera pas émise ; c'est la note de la carte qui le dit."""
        from ui.common.pickers import palette_picker_slot
        from ui.common import icons as _icons
        actifs = self._active_bg_palettes()
        banks = [b for n in actifs
                 if (b := (self._project.get_palette(n) if self._project else None))]
        cur = getattr(self._element, "fill_palette", "") or ""
        if self._fill_pal_slot is not None:
            self._fill_pal_box.removeWidget(self._fill_pal_slot)
            self._fill_pal_slot.deleteLater()
        self._fill_pal_slot = palette_picker_slot(
            banks, cur or None, _icons.COLOR_UI,
            on_picked=self._on_fill_palette,
            add_label=label("common.choose_palette"), parent=self, allow_none=False)
        if cur and cur not in actifs:
            self._fill_pal_slot.set_script(cur)
        self._fill_pal_box.addWidget(self._fill_pal_slot)

    def _reload_fill_sprite(self):
        """Peuple sprite/état/vitesse du fond sprite. blockSignals : repeupler
        un combo émet `currentIndexChanged`, qui écrirait dans le modèle."""
        el = self._element
        self._fill_sprite.blockSignals(True)
        self._fill_sprite.clear()
        self._fill_sprite.addItem(label("uiinsp.fill.sprite_none"), "")
        for s in (getattr(self._project, "sprites", []) if self._project else []):
            self._fill_sprite.addItem(s.name, s.name)
        i = self._fill_sprite.findData(getattr(el, "fill_sprite", "") or "")
        self._fill_sprite.setCurrentIndex(i if i >= 0 else 0)
        self._fill_sprite.blockSignals(False)
        self._reload_fill_states()
        self._fill_speed.blockSignals(True)
        self._fill_speed.setValue(int(getattr(el, "fill_speed", 0) or 0))
        self._fill_speed.blockSignals(False)

    def _reload_fill_states(self):
        """États du sprite de fond. « (first state) » plutôt qu'un premier état
        nommé en dur — même raison que pour une image : un nom vide suit le
        sprite quand on en réordonne les états, un nom figé désigne l'ancien."""
        self._fill_state.blockSignals(True)
        self._fill_state.clear()
        sprite = (self._project.get_sprite(getattr(self._element, "fill_sprite", "") or "")
                  if self._project else None)
        self._fill_state.addItem(label("uiinsp.fill.state_first"), "")
        for st in (getattr(sprite, "states", []) if sprite else []):
            self._fill_state.addItem(st.name, st.name)
        self._fill_state.setEnabled(sprite is not None)
        k = self._fill_state.findData(getattr(self._element, "fill_state", "") or "")
        self._fill_state.setCurrentIndex(k if k >= 0 else 0)
        self._fill_state.blockSignals(False)

    def _reload_fill_asset(self):
        """Peuple le combo d'asset selon le mode. blockSignals pour ne pas
        écraser `fill_asset` pendant le repeuplement.

        En nine-slice, seuls les fonds d'INTERFACE de rôle « nine-slice » sont
        proposés : eux seuls portent des marges de coupe, et citer une image qui
        n'en a pas donnerait un cadre sans coins. En mode background, toute
        image reste citable — poser un décor derrière un panneau est légitime,
        et rien dans les données ne s'y oppose."""
        fk = self._fill_kind.currentData()
        self._fill_asset.blockSignals(True)
        self._fill_asset.clear()
        self._fill_asset.addItem(label("uiinsp.fill.asset_none"), "")
        if fk == FILL_NINE:
            from core.models.background import UI_ROLE_NINE
            ui_bgs = (self._project.ui_backgrounds(UI_ROLE_NINE)
                      if self._project else [])
            for n in ui_bgs:
                self._fill_asset.addItem(n.name, n.name)
        elif fk == FILL_BG:
            for b in (getattr(self._project, "backgrounds", []) if self._project else []):
                self._fill_asset.addItem(b.name, b.name)
        ai = self._fill_asset.findData(getattr(self._element, "fill_asset", "") or "")
        self._fill_asset.setCurrentIndex(ai if ai >= 0 else 0)
        self._fill_asset.blockSignals(False)

    def _sync_fill(self):
        """Montre les champs du mode courant + une note ; met à jour la pastille."""
        if not can_fill(self._element):
            return
        fk = self._fill_kind.currentData()
        self._fill_color_row.setVisible(fk == FILL_COLOR)
        self._fill_asset_row.setVisible(fk in (FILL_NINE, FILL_BG))
        self._ns_margins_row.setVisible(fk == FILL_NINE)
        for w in (self._fill_sprite_row, self._fill_state_row,
                  self._fill_speed_row):
            w.setVisible(fk == FILL_SPRITE)
        if fk == FILL_NINE:
            self._reload_ns()
        if fk == FILL_COLOR:
            self._sync_color_fill()
        elif fk == FILL_NINE:
            self._fill_why.show_text("ui.fill.nine")
        elif fk == FILL_BG:
            self._fill_why.show_text("ui.fill.bg")
        elif fk == FILL_SPRITE:
            self._sync_sprite_fill()
        else:
            self._fill_why.clear()
        if fk != FILL_COLOR:
            self._fill_pal_why.clear()
        if fk != FILL_SPRITE:
            self._fill_overflow.clear()
        self._update_swatch()

    def _sync_color_fill(self):
        """Ce que le build fera de la palette citée. Une palette hors des BG
        actives de la scène est ÉCARTÉE à l'émission — c'est le défaut qui a
        fait qu'un conteneur ne colorait qu'une partie de sa zone, et il ne se
        voyait nulle part avant le Build. Ce qu'est un aplat se dit toujours
        (niveau 1) ; le risque, lui, s'encadre contre le champ (niveau 2)."""
        pal = getattr(self._element, "fill_palette", "") or ""
        self._fill_why.show_text("ui.fill.color")
        if pal and pal not in self._active_bg_palettes():
            self._fill_pal_why.show_text(palette=pal)
        else:
            self._fill_pal_why.clear()

    def _sync_sprite_fill(self):
        """Ce que le pavage coûte VRAIMENT, chiffré sur le sprite choisi.

        Le nombre de slots OAM est la seule information que l'auteur ne peut pas
        deviner en regardant le canvas, et c'est celle qui fait échouer un build
        (128 slots pour toute la scène, acteurs compris)."""
        sprite = (self._project.get_sprite(getattr(self._element, "fill_sprite", "") or "")
                  if self._project else None)
        if sprite is None:
            self._fill_why.show_text("ui.fill.sprite")
            self._fill_overflow.clear()
            return
        fw = int(getattr(sprite, "frame_w", 0) or 0)
        fh = int(getattr(sprite, "frame_h", 0) or 0)
        cols, rows = sprite_grid(self._element, fw, fh)
        n = cols * rows
        over = (cols * fw - int(self._element.w), rows * fh - int(self._element.h))
        self._fill_why.show_text("ui.fill.sprite_cost", w=fw, h=fh,
                                 cols=cols, rows=rows, n=n)
        if over[0] or over[1]:
            self._fill_overflow.show_text(dx=over[0], dy=over[1])
        else:
            self._fill_overflow.clear()

    def _current_ns(self):
        """Le fond d'interface cité comme cadre — c'est lui qui porte l'image
        ET les marges."""
        if not self._project:
            return None
        return self._project.get_background(getattr(self._element, "fill_asset", "") or "")

    def _reload_ns(self):
        """Charge les marges du cadre sélectionné ; grise si aucun."""
        prev, self._blocking = self._blocking, True
        try:
            ns = self._current_ns()
            has = ns is not None
            for sp in self._ns_m.values():
                sp.setEnabled(has)
            if has:
                for k, sp in self._ns_m.items():
                    sp.setValue(int(getattr(ns, k, 0)))
        finally:
            self._blocking = prev

    def _update_swatch(self):
        css = f"background:transparent; border:1px solid {C.BORDER};"
        if self._fill_kind.currentData() == FILL_COLOR and self._project is not None:
            bank = self._project.get_palette(getattr(self._element, "fill_palette", "") or "")
            idx = self._fill_index.value()
            if bank and 0 <= idx < len(bank.colors):
                r, g, b = bgr555_to_rgb888(bank.colors[idx])
                css = f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER};"
        self._fill_swatch.setStyleSheet(css)

    # ── Édition (toutes les écritures passent par l'historique) ────
    def _persist(self):
        # Par le dispatcher, jamais `project.save()` en direct : il suspend le
        # watcher de fichiers le temps de l'écriture. Sans ça le watcher voit le
        # JSON changer, croit à une édition externe et fait recharger la scène —
        # ce qui rebascule l'inspecteur sur la scène et fait perdre l'élément en
        # cours d'édition à chaque champ modifié.
        if self._project:
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().save_all()
        self.changed.emit()

    def _reload_list(self):
        """Repose les réglages de navigation, le curseur et le style de la
        rangée choisie."""
        el = self._element
        self._list_active.setChecked(bool(getattr(el, "active", True)))
        self._list_cols.setValue(max(1, int(getattr(el, "nav_columns", 1) or 1)))
        self._list_major.setCurrentIndex(
            1 if getattr(el, "nav_major", NAV_COLUMN) == NAV_ROW else 0)
        self._list_wrap.setChecked(bool(getattr(el, "wrap", True)))
        self._reload_list_cursor()
        # Le style de sélection vit dans la MÊME banque que l'encre d'une zone
        # (`Scene.ui_pal_bank`) : le matériel ne charge qu'une banque d'UI par
        # scène, et deux banques feraient dire deux couleurs au même index.
        bank = self._ui_bank()
        self._list_ink.set_value(
            bank, int(getattr(el, "selected_text_color", 0) or 0))
        self._list_hl.set_value(
            bank, int(getattr(el, "selected_highlight_color", 0) or 0))
        self._sync_list_rows()

    def _reload_list_cursor(self):
        """(Re)peuple le choix de curseur avec les IMAGES de cette mise en page.

        Seulement celles-ci : une liste qui déplacerait l'image d'une autre page
        bougerait quelque chose que l'auteur ne voit pas à côté d'elle. Un nom
        posé qui n'y est plus reste montré et signalé, jamais effacé en
        silence — même règle que `ColorIndexSlot` pour un index hors banque."""
        from core.models.ui_region import KIND_IMAGE
        el, lay = self._element, self._layout_asset
        cur = str(getattr(el, "cursor_image", "") or "")
        names = [x.name for x in (lay.elements if lay else [])
                 if getattr(x, "kind", "") == KIND_IMAGE]
        if cur and cur not in names:
            names.append(cur)
        was = self._blocking
        self._blocking = True
        try:
            self._list_cursor.clear()
            self._list_cursor.addItem(label("uiinsp.list.cursor_none"), "")
            for n in names:
                self._list_cursor.addItem(n, n)
            i = self._list_cursor.findData(cur)
            self._list_cursor.setCurrentIndex(i if i >= 0 else 0)
        finally:
            self._blocking = was
        self._sync_list_cursor()

    def _on_list_cursor(self, _i: int):
        if self._blocking or self._element is None:
            return
        self._set("cursor_image", str(self._list_cursor.currentData() or ""),
                  "List cursor")
        self._sync_list_cursor()

    def _sync_list_cursor(self):
        """La vitesse ne compte qu'en mode glissant, et un curseur introuvable
        se dit ici plutôt qu'au Build."""
        from core.models.ui_region import KIND_IMAGE
        el, lay = self._element, self._layout_asset
        if el is None:
            return
        cur = str(getattr(el, "cursor_image", "") or "")
        self._list_cursor_speed_row.setVisible(
            getattr(el, "cursor_mode", CURSOR_SNAP) == CURSOR_SLIDE)
        self._list_cursor_speed.setValue(
            max(1, int(getattr(el, "cursor_speed", 2) or 2)))
        target = lay.get(cur) if (lay and cur) else None
        if cur and getattr(target, "kind", "") != KIND_IMAGE:
            self._list_cursor_why.show_text("ui.list.cursor_missing", name=cur)
        else:
            self._list_cursor_why.clear()

    def _sync_list_rows(self):
        """Dit combien de rangées la liste porte et quelle grille elles font —
        une liste sans zone de texte enfant n'afficherait rien, et c'est le
        genre de chose qu'on veut lire ici plutôt que découvrir au Build."""
        e = self._element
        if e is None or self._kind() != KIND_LIST:
            return
        from core.models.ui_region import KIND_TEXT
        lay = self._layout_asset
        rows = [x for x in (lay.elements if lay else [])
                if getattr(x, "parent", "") == e.name
                and getattr(x, "kind", "") == KIND_TEXT]
        if rows:
            self._list_why.show_text("ui.list.rows", n=len(rows),
                                     names=", ".join(r.name for r in rows))
        else:
            self._list_why.show_text("ui.list.empty")
        # La forme obtenue, dite en clair : deux nombres se lisent moins bien
        # qu'un « 2 × 3 », et c'est la grille que l'auteur a en tête.
        cols = max(1, int(getattr(e, "nav_columns", 1) or 1))
        n = len(rows)
        lines = max(1, n // cols) if n else 0
        row_first = getattr(e, "nav_major", NAV_COLUMN) == NAV_ROW
        if not n:
            self._list_shape.clear()
            return
        if cols == 1:
            shape, order = label('uiinsp.n_rows_one_column', n=n), label('uiinsp.top_to_bottom')
        elif lines <= 1:
            shape, order = label('uiinsp.n_columns_one_line', n=n), label('uiinsp.left_to_right')
        else:
            shape = label('uiinsp.lines_cols_grid', lines=lines, cols=cols)
            order = (label('uiinsp.left_to_right_then_the_line_below') if row_first
                     else label('uiinsp.top_to_bottom_then_the_next_column'))
        self._list_shape.show_text("ui.list.grid", shape=shape, order=order)

    def _set(self, field: str, value, label: str):
        from core.history import get_history, SetFieldCmd
        old = getattr(self._element, field)
        if old == value:
            return
        get_history().push(SetFieldCmd(self._element, field, old, value,
                                       label=label, persist_fn=self._persist))

    def rename(self, new_name: str) -> str:
        """Renomme l'élément courant — appelé par l'EN-TÊTE, seule porte d'entrée.

        Tout le travail (unicité projet, rebranchement des enfants sur le
        nouveau nom, réécriture des scripts qui citent la constante) est déjà
        dans `Project.rename_ui_element` : le refaire ici en donnerait une
        seconde version, et c'est toujours la seconde qui oublie un cas.

        Retourne le nom RÉELLEMENT appliqué — il peut différer de la demande si
        une collision a été résolue, et l'en-tête doit afficher celui-là."""
        el, lay = self._element, self._layout_asset
        if el is None or lay is None or not self._project:
            return ""
        old = el.name
        applied = self._project.rename_ui_element(lay, el, new_name)
        if applied != old:
            self._persist()
            self.renamed.emit(applied)
        return applied

    def _on_geom(self, key: str, val: int):
        if self._blocking or not self._element:
            return
        self._set(key, int(val), "Geometry")
        self._refresh_diagnostics()

    def _on_visible(self, on: bool):
        if self._blocking or not self._element:
            return
        self._set("visible", bool(on), "Visibility")
        self._sync_visible_hint()

    def _on_align_toggled(self, i: int, checked: bool):
        """`idToggled` tire DEUX fois par changement — le bouton qui se relève
        et celui qui s'enfonce. Seul le second dit le choix."""
        if not checked or self._blocking or not self._element or not 0 <= i < len(ALIGNS):
            return
        self._set("align", ALIGNS[i], "Alignment")

    def _on_font(self, name: str, weight: int, italic: bool):
        if self._blocking or not self._element:
            return
        if name != getattr(self._element, "font_name", ""):
            self._set("font_name", name, "Font")
        if weight != getattr(self._element, "font_weight", 400):
            self._set("font_weight", weight, "Font weight")
        if italic != getattr(self._element, "font_italic", False):
            self._set("font_italic", italic, "Font italic")

    def _on_color(self, index: int):
        if self._blocking or not self._element:
            return
        self._set("text_color", int(index), "Text ink")

    def _on_highlight(self, index: int):
        if self._blocking or not self._element:
            return
        self._set("highlight_color", int(index), "Text highlight")

    def _ui_bank(self):
        """PaletteBank où CE texte libre lit ses couleurs, ou None.

        None en mode automatique (la police impose sa propre palette) ou si le
        slot désigné est vide : pas de pastilles à montrer dans ces cas."""
        if not (self._project and self._scene):
            return None
        from core.models.scene import scene_font_pal_bank
        from codegen.font_emit import scene_default_font

        # Le champ historique ``ui_pal_bank`` n'est plus sérialisé.  Le picker
        # d'une zone doit donc lire exactement la même entrée de
        # ``font_pal_banks`` que l'allocateur et le codegen, sinon une valeur
        # pourtant enregistrée réapparaît à tort comme « own palette » après
        # rechargement.
        _index, default_font = scene_default_font(self._project, self._scene)
        selected_font = getattr(self._element, "font_name", "") or default_font
        slot = scene_font_pal_bank(self._scene, selected_font, default_font)
        active = list(getattr(self._scene, "active_bg_palettes", []) or [])
        if not 0 <= slot < len(active):
            return None
        return self._project.get_palette(active[slot])

    def _ink_bank(self):
        """La banque où l'encre et le surlignement du texte s'indexent VRAIMENT
        quand il est imbriqué dans un conteneur à FOND — ou None quand il lit la
        banque de scène (`ui_pal_bank`), le cas du texte libre.

        Un texte enfant d'un conteneur à fond PREND la banque de ce conteneur
        (RegionFill.bank au runtime), pas le `ui_pal_bank` de la scène. Plutôt
        que de reconstruire ici les conditions d'émission (cible BG, ancrage
        écran, palette active, 8bpp, débordement de zone), on DEMANDE au codegen
        ce qu'il émet pour CETTE zone : `scene_region_colors` /
        `scene_region_backdrops` ne l'y listent que si le build la lie vraiment à
        un conteneur, et à quelle banque. C'est la même vérité que la ROM, pas
        une copie qui divergera.

        Renvoie `(banque, nom_de_banque, nom_du_conteneur)` ou None — `banque`
        porte `.colors`, ce qu'attend `ColorIndexSlot`."""
        from core.models.ui_region import KIND_TEXT
        if not (self._project and self._scene and self._element):
            return None
        if getattr(self._element, "kind", "") != KIND_TEXT:
            return None
        from codegen.runtime_codegen.gen_text import region_ink_bank
        resolved = region_ink_bank(self._project, self._scene, self._element)
        if resolved is None:
            return None      # le build ne lie pas cette zone : texte → police
        bank_off, container = resolved

        # Les couleurs réellement chargées dans cette banque HW — même calcul que
        # l'émission (`slot_colors[bank]`).
        from codegen.palette_alloc import scene_bank_layout
        from types import SimpleNamespace
        layout = scene_bank_layout(self._project, self._scene, "bg")
        if not 0 <= bank_off < len(layout.slot_colors):
            return None
        cols = layout.slot_colors[bank_off]
        if not cols:
            return None
        cont_el = self._layout_asset.get(container)
        label = (getattr(cont_el, "fill_palette", "")
                 or getattr(cont_el, "fill_asset", "") or container)
        return (SimpleNamespace(colors=list(cols)), label, container)

    def _clear_ui_pal_host(self):
        """Vide la ligne « Bank » — elle porte tantôt le slot ÉDITABLE (texte
        libre), tantôt une étiquette en LECTURE SEULE (banque héritée d'un
        conteneur). Un seul hôte, deux contenus selon le contexte."""
        while self._ui_pal_box.count():
            w = self._ui_pal_box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self._ui_pal_slot = None

    def _reload_ui_pal_slot(self):
        """(Re)construit le slot de banque ÉDITABLE — LA MÊME liste, dans le
        même ordre, que `SceneInspector._reload_ui_pal` : c'est le même choix
        pour une police donnée, il ne doit pas se présenter différemment selon
        l'écran d'où on le change.
        Reconstruit et non repeuplé, pour la même raison que
        `_reload_fill_palette` : le picker capture sa liste à la construction."""
        from ui.common.pickers import ui_pal_bank_slot
        from ui.common import icons as _icons
        active = list(getattr(self._scene, "active_bg_palettes", []) or []) if self._scene else []
        cur = -1
        if self._scene and self._project:
            from core.models.scene import scene_font_pal_bank
            from codegen.font_emit import scene_default_font
            _index, default_font = scene_default_font(self._project, self._scene)
            selected_font = getattr(self._element, "font_name", "") or default_font
            cur = scene_font_pal_bank(self._scene, selected_font, default_font)
        self._clear_ui_pal_host()
        self._ui_pal_slot = ui_pal_bank_slot(
            active, cur, _icons.COLOR_UI, on_picked=self._on_ui_pal_bank,
            project=self._project, parent=self)
        self._ui_pal_box.addWidget(self._ui_pal_slot)

    def _show_inherited_bank(self, name: str):
        """Remplace le slot éditable par le nom de la banque HÉRITÉE, en lecture
        seule : un texte imbriqué ne CHOISIT pas sa banque, il la prend de son
        conteneur (cf. `_ink_bank`). Le « pourquoi » va dans la note en dessous
        (`ui.text.bank_inherited`), la couleur des pastilles vient de cette
        banque-là."""
        self._clear_ui_pal_host()
        lbl = QLabel(name)
        lbl.setFont(QFont(T.MONO, T.MD))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        lbl.setToolTip(tooltip(
            title=label("uiinsp.bank_inherited_title"),
            body=label("uiinsp.bank_inherited_tip"),
            note=label("uiinsp.bank_inherited_note")))
        self._ui_pal_box.addWidget(lbl)

    def _on_ui_pal_bank(self, new: int):
        """Enregistre l'override de la police effective dans la scène.

        L'inspecteur est ouvert depuis une zone, mais cette banque appartient
        à la police dans cette scène.  Un dictionnaire neuf est indispensable
        pour que l'historique puisse restaurer fidèlement avant/après."""
        if not (self._scene and self._project):
            return
        from core.history import get_history, SetFieldCmd
        from core.models.scene import font_pal_key, scene_font_pal_bank
        from codegen.font_emit import scene_default_font

        _index, default_font = scene_default_font(self._project, self._scene)
        selected_font = getattr(self._element, "font_name", "") or default_font
        old = scene_font_pal_bank(self._scene, selected_font, default_font)
        new = int(new)
        if old == new:
            return
        banks = dict(getattr(self._scene, "font_pal_banks", {}) or {})
        key = font_pal_key(selected_font, default_font)
        if 0 <= new < 16:
            banks[key] = new
        else:
            banks.pop(key, None)
        get_history().push(SetFieldCmd(
            self._scene, "font_pal_banks",
            dict(getattr(self._scene, "font_pal_banks", {}) or {}), banks,
            label="Text palette bank", persist_fn=self._persist))
        # Changer de banque sans toucher à l'encre ne se voit pas : l'index 0
        # (« défaut ») ne peint rien de la banque. On pose donc la première
        # couleur réelle de la nouvelle banque (index 1, le 0 étant réservé).
        bank = self._ui_bank()
        if bank and len(bank.colors) > 1:
            self._set("text_color", 1, "Text ink")
        self._reload_color()   # les deux pickers lisent une autre banque désormais

    def _reload_color(self):
        """Repose la banque, l'encre et le surlignement — deux couleurs, une
        seule banque.

        La liste proposée aux deux pickers est FILTRÉE sur les couleurs que la
        banque contient vraiment. Les seize index étaient offerts d'office, au
        motif qu'un index reste valide même sans banque : c'est vrai du
        STOCKAGE, pas du CHOIX — proposer un index qui ne peint rien fait
        poser un réglage sans effet, et rien ne le dit ensuite. Un index déjà
        posé qui sort de la banque, lui, reste montré et signalé
        (`ColorIndexSlot`) : c'est un choix de quelqu'un, on ne l'efface pas
        en silence.

        Le surlignement est masqué en cible OBJ : une bande de sprites ne passe
        pas par la surface BG, rien ne l'y émettrait — on ne propose pas une
        action impossible (même règle que `_FILL_TARGETS`).

        **Une banque HÉRITÉE prend le pas sur celle de scène.** Un texte imbriqué
        dans un conteneur à fond lit son encre dans la banque du CONTENEUR
        (cf. `_ink_bank`), pas dans `ui_pal_bank` : le champ passe alors en
        lecture seule et les deux pastilles montrent les couleurs de cette
        banque-là. Le texte libre, lui, garde le réglage de scène, éditable."""
        inherited = self._ink_bank()
        if inherited is not None:
            bank, bank_name, container = inherited
            self._show_inherited_bank(bank_name)
            self._bank_why.show_text("ui.text.bank_inherited", container=container)
        else:
            self._reload_ui_pal_slot()
            bank = self._ui_bank()
            # Le combo au-dessus dit déjà QUELLE banque ; ce qui reste à dire,
            # c'est pourquoi les pickers n'ont que des numéros à montrer tant
            # qu'aucune n'est choisie.
            if bank:
                self._bank_why.clear()
            else:
                self._bank_why.show_text("ui.text.bank_none")
        self._color.set_value(
            bank, int(getattr(self._element, "text_color", 0) or 0))
        self._highlight.set_value(
            bank, int(getattr(self._element, "highlight_color", 0) or 0))
        target = self._layout_asset.resolved_target(self._element, self._render_mode())
        self._highlight_row.setVisible(target == TARGET_BG)

    def _on_preview(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("preview_text", self._preview.currentData() or "", "Zone preview")

    def _on_text_key(self, i):
        """Ré-accroche l'élément à une AUTRE entrée existante. La salve en cours
        appartient à l'ancienne : la commiter avant de basculer."""
        if self._blocking or not self._element or i < 0:
            return
        self._commit_content()
        self._set("text_key", self._text_key.currentData() or "", "Element text")
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().notify_ui_text_links_changed()
        self._blocking = True
        try:
            self._reload_content()
            self._sync_text_rows()
        finally:
            self._blocking = False
        self._refresh_diagnostics()

    # ── Fond : écritures ──────────────────────────────────────────
    def _fill_editable(self) -> bool:
        # La CAPACITÉ, pas le type : les deux conteneurs dessinent un fond, et
        # tester le seul panneau ici rendrait la carte de la liste inerte —
        # visible, éditable en apparence, sans rien écrire.
        return bool(self._element) and can_fill(self._element)

    def _on_fill_kind(self, i):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_kind", self._fill_kind.currentData() or FILL_NONE, "Container background")
        self._blocking = True
        try:
            self._reload_fill_asset()
            self._sync_fill()
        finally:
            self._blocking = False

    def _on_fill_palette(self, name: str):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_palette", name or "", "Background palette")
        self._sync_fill()

    def _on_fill_index(self, v):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_index", int(v), "Background index")
        self._update_swatch()

    def _on_fill_asset(self, i):
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_asset", self._fill_asset.currentData() or "", "Background asset")
        self._reload_ns()

    # ── Fond sprite (cible OBJ) ───────────────────────────────────
    def _on_fill_sprite(self, i):
        """Changer de sprite REMET l'état au défaut — `fill_state` pointe un état
        de l'ANCIEN sprite, et le garder retomberait silencieusement sur l'état 0
        au build. Même règle que pour une image.

        Le panneau, lui, n'est PAS redimensionné : sa taille est celle du
        conteneur, c'est le fond qui s'y adapte en se pavant."""
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_sprite", self._fill_sprite.currentData() or "", "Panel sprite")
        self._set("fill_state", "", "Panel sprite state")
        self._reload_fill_states()
        self._sync_fill()

    def _on_fill_state(self, i):
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_state", self._fill_state.currentData() or "",
                  "Panel sprite state")

    def _on_fill_speed(self, v):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_speed", int(v), "Panel sprite speed")

    # ── Nine-slice (asset partagé) ────────────────────────────────
    def _persist_ns(self):
        """Le cadre est un asset PARTAGÉ : sauver le projet + redessiner."""
        if self._project:
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().save_all()
        self.changed.emit()

    def _set_ns(self, ns, field, value, label):
        from core.history import get_history, SetFieldCmd
        old = getattr(ns, field)
        if old == value:
            return
        get_history().push(SetFieldCmd(ns, field, old, value,
                                       label=label, persist_fn=self._persist_ns))

    def _on_ns_margin(self, key, v):
        if self._blocking:
            return
        ns = self._current_ns()
        if ns is not None:
            self._set_ns(ns, key, int(v), "Frame margin")

    # ── Suppression ───────────────────────────────────────────────
    def _on_delete(self):
        """Supprime l'élément ET son sous-arbre — même règle qu'au canvas
        (Suppr) : la position d'un enfant étant relative à son conteneur, les
        orphelins ne resteraient pas en place, ils sauteraient ailleurs."""
        if not self._element or not self._layout_asset:
            return
        from core.history import get_history, RemoveListItemsCmd
        from core.selection_bus import get_bus
        lay = self._layout_asset
        victims = [self._element] + lay.descendants(self._element.name)
        n = len(victims)
        get_bus().clear()     # avant la persistance, qui réémet la sélection
        get_history().push(RemoveListItemsCmd(
            lay.elements, victims, persist_fn=self._persist,
            label=f"Delete {self._element.name}"
                  + (f" (+{n - 1} children)" if n > 1 else "")))
