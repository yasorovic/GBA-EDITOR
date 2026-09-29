"""
ui/common/theme.py — Source unique du thème GBA Editor.

Usage :
    from ui.common.theme import C, T, QSS, GLOBAL_QSS

Couleurs via C :
    C.ACCENT   C.POWER   C.BG_INPUT   C.TEXT_DIM ...

Typographie via T — 3 familles, 3 rôles :
    T.UI    police système (Segoe UI)  → labels, menus, titres, boutons
    T.MONO  monospace                  → valeurs numériques, compteurs, chemins
    T.CODE  Consolas                   → éditeur de code, callbacks Lua
    QFont(T.UI, T.MD)      f"font-family:{T.UI_STACK}; font-size:{T.SM}px"

Espacement via S (marges/paddings standard) :
    layout.setSpacing(S.SM)   layout.setContentsMargins(S.MD, S.SM, S.MD, S.SM)

Fragments QSS via QSS :
    widget.setStyleSheet(QSS.spinbox)
    widget.setStyleSheet(QSS.checkbox)

Hiérarchie de titres (une seule grammaire pour toute l'app) :
    QSS.title_panel        en-tête de panneau/finder  (dim, uppercase par l'appelant)
    QSS.title_finder()     titre de section d'un viewer (SCENES, PREFABS…)
    QSS.title_group        intertitre dans une section de viewer (ACTORS…)
    QSS.title_section()    titre de section d'inspecteur (périwinkle par défaut)
    QSS.label_field        label de champ dans une ligne de formulaire
    QSS.empty_state        message central des écrans/panneaux vides

Stylesheet globale à appliquer une seule fois dans main.py :
    app.setStyleSheet(GLOBAL_QSS)

Bulles d'aide (`QToolTip`) : la règle `QSS.tooltip` ci-dessous NE suffit PAS —
un widget qui pose sa propre feuille de style (bouton d'icône, curseur…)
décroche sa bulle de la feuille globale, Qt retombe sur le thème natif de
l'OS. `main.py` doit AUSSI appeler `QToolTip.setPalette()` / `.setFont()` :
seul réglage que Qt applique à chaque bulle sans dépendre du widget qui la
déclenche.
"""

from ui.common import icons as _icons

# ──────────────────────────────────────────────────────────────────
#  Typographie — échelle de tailles et familles de polices
# ──────────────────────────────────────────────────────────────────

class _Typography:
    # Familles
    UI   = "Segoe UI"    # labels, menus, titres, boutons — police système
    MONO = "monospace"   # valeurs numériques, compteurs, chemins
    CODE = "Consolas"    # éditeur de code, callbacks Lua

    # Pile CSS pour les QSS : la police système de Windows 11, puis celle de 10.
    UI_STACK = "'Segoe UI Variable Text','Segoe UI',sans-serif"

    # Tailles (points pour QFont / pixels pour QSS — traitées identiquement)
    XS  = 9    # hints, sous-labels très discrets
    SM  = 10   # labels dim, boutons secondaires
    MD  = 12   # texte courant, menus, inputs
    LG  = 13   # titres section, sidebar éditeur
    XL  = 14   # titre projet, icônes larges
    XXL = 16   # très grands titres / icônes header


T = _Typography()


def ui_font(size: int = T.MD, *, bold: bool = False, family: str | None = None):
    """QFont dont la taille est en PIXELS — la même unité que les fragments QSS.

    `QFont(T.UI, T.MD)` crée un 12 *points* (≈16 px à 96 dpi) : posé sur une
    ligne d'arbre stylée `font-size:12px`, il donne deux corps différents pour
    un même niveau de hiérarchie. ui_font() garde les deux mondes d'accord."""
    from PyQt6.QtGui import QFont
    f = QFont(family or T.UI)
    f.setPixelSize(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


# ──────────────────────────────────────────────────────────────────
#  Espacement — échelle unique pour marges, paddings et spacing
# ──────────────────────────────────────────────────────────────────

class _Spacing:
    XS  = 2    # interlignes serrés (rangées de formulaire)
    SM  = 4    # spacing par défaut d'un layout dense
    MD  = 8    # marge interne de panneau, écart label/widget
    LG  = 12   # marge de section, gouttières de panneau
    XL  = 16   # respiration entre sections d'inspecteur
    XXL = 24   # marges d'écran / d'état vide

    # Gouttière gauche commune à TOUS les viewers : titre de panneau, titre de
    # section et première colonne d'arbre s'alignent dessus — c'est la ligne
    # verticale unique qu'on lit du haut en bas d'un finder.
    GUTTER = 10

    # Retrait du CONTENU d'une section (intertitres, lignes de variables) :
    # gouttière + chevron + colonne d'icône, soit là où un QTreeWidget de finder
    # pose ses items de premier niveau. Sans lui, les listes qui ne sont pas des
    # arbres décrochent de deux ou trois pixels.
    CONTENT = GUTTER + LG + MD

    # Hauteur d'une ligne d'arbre / de liste dans les finders. Centralisée parce
    # que certains arbres la calculent à la main (assets_finder_panel._Tree._fit).
    ROW = 24


S = _Spacing()


# ──────────────────────────────────────────────────────────────────
#  Palette de couleurs
# ──────────────────────────────────────────────────────────────────

_DARK = dict(
    # Fonds — ramp sombre NEUTRE (gris purs, aucune teinte), du plus profond au plus clair
    BG_DEEP="#0b0b0b",     # barre statut, séparateurs forts
    BG_BASE="#111111",     # fond panels principaux
    BG_PANEL="#171717",    # fond widgets, inspector
    BG_RAISED="#1e1e1e",   # menus, toolbars
    BG_INPUT="#262626",    # inputs (spinbox, lineedit, combobox)
    BG_HOVER="#303030",    # survol boutons
    BG_SEL="#2c2c2c",      # fond sélection
    BORDER="#2b2b2b", BORDER_MID="#383838", BORDER_DARK="#222222",
    ACCENT="#d0d0d0",      # accent PRIMAIRE structurel (sélection, focus, onglet actif)
    ACCENT_HOVER="#e6e6e6", ACCENT_PRESSED="#a8a8a8",
    ON_ACCENT="#000000",   # texte posé sur un fond ACCENT
    # État qui demande l'attention, sans signer l'interface d'un vert « power ».
    # Les succès ordinaires restent neutres ; le jaune porte l'alerte simple.
    POWER="#e8c547",
    ACCENT_RED="#e05050", ACCENT_YLW="#e8c547",
    ACCENT_WARM="#c48b3c", ACCENT_COOL="#82aaff",
    TEXT_HI="#ececec", TEXT_NORM="#ababab", TEXT_DIM="#6e6e6e", TEXT_MUTED="#4a4a4a",
    TEXT_BASE="#d4d4d4",   # texte de la palette Qt
    AXIS_X="#c07070", AXIS_Y="#7090c0", AXIS_Z="#7aab7a",
    SEL_BG="#2c2c2c", SEL_BORDER="#d0d0d0", SEL_TEXT="#f2f2f2",
    BTN_PRIMARY="#3a3a3a", BTN_PRIMARY_HOVER="#4a4a4a", BTN_PRIMARY_PRESSED="#2a2a2a",
    BTN_PRIMARY_DISABLED="#232323", BTN_PRIMARY_TEXT="#f2f2f2",
    SCROLL_HANDLE="#3a3a3a", SCROLL_HANDLE_HOVER="#4c4c4c",
    CANVAS_BG="#1a1a1a", CHECKER_A="#222222", CHECKER_B="#2a2a2a",
    SYNTAX_KEYWORD="#c586c0", SYNTAX_API="#4ec9b0", SYNTAX_NUMBER="#b5cea8",
    SYNTAX_STRING="#ce9178", SYNTAX_COMMENT="#6a9955",
    CONSOLE_TEXT="#c8ffc8",   # texte de la console de build
    # Instrument « technique » (barre ROM) : pavés noirs, quadrillage, filet acier.
    TECH_BG="#040a06", TECH_TEXT="#b9f5c9", TECH_GRID="#0d1a11", TECH_OK="#5be08b",
    TECH_OUTLINE="#2f6a44", TECH_BLOCK_BORDER="#1b3a27",
    HEADER_BG_VALUE=22,    # luminosité (0-255) du fond d'en-tête d'asset
)

_LIGHT = dict(
    BG_DEEP="#d2d2d2", BG_BASE="#e4e4e4", BG_PANEL="#f1f1f1", BG_RAISED="#fafafa",
    BG_INPUT="#ffffff", BG_HOVER="#dadada", BG_SEL="#cdcdcd",
    BORDER="#c4c4c4", BORDER_MID="#acacac", BORDER_DARK="#d4d4d4",
    ACCENT="#3a3a3a", ACCENT_HOVER="#555555", ACCENT_PRESSED="#222222",
    ON_ACCENT="#ffffff",
    POWER="#b8860b", ACCENT_RED="#c62828", ACCENT_YLW="#b8860b",
    ACCENT_WARM="#a86a10", ACCENT_COOL="#2f5fc4",
    TEXT_HI="#0d0d0d", TEXT_NORM="#2e2e2e", TEXT_DIM="#575757", TEXT_MUTED="#828282",
    TEXT_BASE="#262626",
    AXIS_X="#b04040", AXIS_Y="#3f68b0", AXIS_Z="#3f8a3f",
    SEL_BG="#cdcdcd", SEL_BORDER="#3a3a3a", SEL_TEXT="#0d0d0d",
    BTN_PRIMARY="#3a3a3a", BTN_PRIMARY_HOVER="#555555", BTN_PRIMARY_PRESSED="#222222",
    BTN_PRIMARY_DISABLED="#c4c4c4", BTN_PRIMARY_TEXT="#ffffff",
    SCROLL_HANDLE="#b0b0b0", SCROLL_HANDLE_HOVER="#909090",
    CANVAS_BG="#dcdcdc", CHECKER_A="#b4b4b4", CHECKER_B="#9e9e9e",
    CONSOLE_TEXT="#1f6b3a",
    TECH_BG="#f3fbf5", TECH_TEXT="#0e4023", TECH_GRID="#d3e9da", TECH_OK="#1f9d55",
    TECH_OUTLINE="#3f8a5c", TECH_BLOCK_BORDER="#93c6a5",
    SYNTAX_KEYWORD="#9c2f9a", SYNTAX_API="#0b7a6a", SYNTAX_NUMBER="#2a7a2a",
    SYNTAX_STRING="#a8482a", SYNTAX_COMMENT="#5a8a3a",
    HEADER_BG_VALUE=240,
)


class _Colors:
    """Les constantes de couleur du thème ACTIF (voir interface_theme()).
    Lues une fois à l'import : un changement de thème prend effet au redémarrage."""

    def __init__(self, palette: dict, light: bool):
        self.IS_LIGHT = light
        for name, value in palette.items():
            setattr(self, name, value)


from core.interface_preferences import interface_theme

_LIGHT_MODE = interface_theme() == "light"
C = _Colors(_LIGHT if _LIGHT_MODE else _DARK, _LIGHT_MODE)


def tint(hex_color: str, alpha: float) -> str:
    """`#d0d0d0` + 0.3 → `rgba(208,208,208,0.30)`, pour poser une couleur de
    rôle en fond ou en filet sans inventer une seconde constante par opacité.
    Les QSS de Qt lisent `rgba()`, pas le `#rrggbbaa` du CSS moderne."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ──────────────────────────────────────────────────────────────────
#  Petites flèches ▲▼ des QSpinBox / QComboBox — comme le reste de
#  l'application, elles viennent de l'icon set (ui.common.icons).
#  icons.qss_image() les matérialise dans un cache disque
#  parce que le loader url() des QSS ne sait lire qu'un
#  fichier : ni police d'icônes, ni data-URI.
#  Rendues en 2× puis affichées à _ARROW_PX pour rester nettes en HiDPI.
# ──────────────────────────────────────────────────────────────────

_ARROW_PX = 9
_ARROW_SCALE = 2.5   # remplit la boîte MDI, sinon le triangle est minuscule


def _arrow_rule(selectors: str, name: str, color: str) -> str:
    """Règle `image:` pour une flèche, ou "" si l'icon set est indisponible
    — auquel cas Qt garde sa flèche native plutôt qu'une case vide."""
    path = _icons.qss_image(name, color, _ARROW_PX * 2, _ARROW_SCALE)
    if not path:
        return ""
    return (f"{selectors} {{\n"
            f"    image: url({path}); "
            f"width: {_ARROW_PX}px; height: {_ARROW_PX}px;\n"
            f"}}")


# Flèche ▾/▸ de repli des QTreeWidget — le MÊME triangle vectoriel partagé
# (icons.arrow_icon() / qss_arrow_image(), voir leur commentaire) que
# FinderSection/_Section utilisent pour LEUR flèche, à la même taille de
# boîte (ARROW_BOX_PX = T.MD, importé par widgets.py/sidebar_widgets.py) :
# sinon les flèches de l'appli (en-tête de section vs branche d'arbre) ne se
# lisent ni comme la même forme ni comme la même taille.
ARROW_BOX_PX = T.MD


def _tree_arrow_rule(selectors: str, direction: str, color: str) -> str:
    path = _icons.qss_arrow_image(direction, color)
    if not path:
        return ""
    return (f"{selectors} {{\n"
            f"    image: url({path}); "
            f"width: {ARROW_BOX_PX}px; height: {ARROW_BOX_PX}px;\n"
            f"}}")


# ──────────────────────────────────────────────────────────────────
#  Fragments QSS réutilisables widget par widget
#
#  Anatomie d'un fragment (mêmes 4 leviers partout) :
#    background  → fond du widget       border      → cadre (souvent BORDER_MID)
#    color       → couleur du texte     :focus/:hover→ état actif = bascule ACCENT
#  Pour reteinter tout l'app, change les constantes C.* plus haut ;
#  pour retoucher UN widget, édite son fragment ci-dessous.
# ──────────────────────────────────────────────────────────────────

class _QSS:

    # Champs numériques ▲▼ (position, taille, offsets inspecteur)
    @property
    def spinbox(self) -> str:
        return f"""
QSpinBox, QDoubleSpinBox {{
    background: {C.BG_INPUT};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 4px;
    padding: 3px 6px;
    font-family: monospace;
    font-size: {T.MD}px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 15px; border: none; background: transparent;
    border-top-right-radius: 4px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 15px; border: none; background: transparent;
    border-bottom-right-radius: 4px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {C.BG_HOVER};
}}
{_arrow_rule("QSpinBox::up-arrow, QDoubleSpinBox::up-arrow",
             "spin_up", C.TEXT_NORM)}
{_arrow_rule("QSpinBox::down-arrow, QDoubleSpinBox::down-arrow",
             "spin_down", C.TEXT_NORM)}
{_arrow_rule("QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover",
             "spin_up", C.TEXT_HI)}
{_arrow_rule("QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover",
             "spin_down", C.TEXT_HI)}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {C.ACCENT};
}}
"""

    # Champs texte (noms d'assets, chemins, valeurs éditables)
    @property
    def lineedit(self) -> str:
        return f"""
QLineEdit {{
    background: {C.BG_INPUT};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 4px;
    padding: 3px 6px;
    font-family: monospace;
    font-size: {T.MD}px;
}}
QLineEdit:focus {{
    border: 1px solid {C.ACCENT};
}}
QLineEdit:read-only {{
    color: {C.TEXT_DIM};
    background: {C.BG_PANEL};
}}
"""

    # Cases à cocher (options booléennes) — la coche remplie prend ACCENT
    @property
    def checkbox(self) -> str:
        return f"""
QCheckBox {{
    color: {C.TEXT_NORM};
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
    spacing: 5px;
}}
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid {C.BORDER_MID};
    border-radius: 2px;
    background: {C.BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {C.ACCENT};
    border-color: {C.ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {C.ACCENT};
}}
"""

    # Menus déroulants (choix de mode, sélecteurs) + leur liste ouverte
    @property
    def combobox(self) -> str:
        return f"""
QComboBox {{
    background: {C.BG_INPUT};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 4px;
    padding: 3px 8px;
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
}}
QComboBox:focus {{
    border: 1px solid {C.ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
/* Sans cette flèche, un QComboBox stylé est indiscernable d'un QLineEdit —
   on réutilise l'icône des QSpinBox pour garder une seule forme de chevron. */
{_arrow_rule("QComboBox::down-arrow", "spin_down", C.TEXT_NORM)}
{_arrow_rule("QComboBox::down-arrow:hover, QComboBox::down-arrow:on",
             "spin_down", C.TEXT_HI)}
QComboBox QAbstractItemView {{
    background: {C.BG_RAISED};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 0;
    selection-background-color: {C.BG_SEL};
    selection-color: {C.ACCENT};
    outline: none;
}}
"""

    # Bouton d'action mis en avant, plein gris clair (Ouvrir, Créer, Valider)
    @property
    def button_primary(self) -> str:
        # Action primaire « ordinaire » (Ouvrir, Créer…) → gris clair.
        # Le vert POWER est réservé au Build / process actif, pas ici.
        return f"""
QPushButton {{
    background: {C.BTN_PRIMARY};
    color: {C.BTN_PRIMARY_TEXT};
    border: none;
    border-radius: 3px;
    padding: 4px 12px;
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
    font-weight: 600;
}}
QPushButton:hover  {{ background: {C.BTN_PRIMARY_HOVER}; }}
QPushButton:pressed {{ background: {C.BTN_PRIMARY_PRESSED}; }}
QPushButton:disabled {{ background: {C.BTN_PRIMARY_DISABLED}; color: {C.TEXT_MUTED}; }}
"""

    # Bouton discret transparent, texte seul + cadre (actions secondaires)
    @property
    def button_ghost(self) -> str:
        return f"""
QPushButton {{
    color: {C.TEXT_DIM};
    background: transparent;
    border: 1px solid {C.BORDER};
    border-radius: 3px;
    padding: 2px 8px;
    font-family: {T.UI_STACK};
    font-size: {T.SM}px;
}}
QPushButton:hover {{ color: {C.TEXT_HI}; background: {C.BG_HOVER}; border-color: {C.BORDER_MID}; }}
QPushButton:disabled {{ color: {C.TEXT_MUTED}; border-color: {C.BORDER_DARK}; }}
"""

    # Variante accent du bouton discret : contour périwinkle, se remplit au survol
    # (Ouvrir/Choisir secondaire — entre button_ghost et button_primary)
    @property
    def button_accent_outline(self) -> str:
        return f"""
QPushButton {{
    color: {C.ACCENT};
    background: transparent;
    border: 1px solid {C.ACCENT};
    border-radius: 3px;
    padding: 2px 6px;
    font-family: {T.UI_STACK};
    font-size: {T.SM}px;
}}
QPushButton:hover {{ color: {C.BG_DEEP}; background: {C.ACCENT}; }}
QPushButton:disabled {{ color: {C.TEXT_MUTED}; border-color: {C.BORDER_DARK}; }}
"""

    # Petit bouton carré à icône (toolbar compacte, +/-, actions rapides)
    @property
    def button_icon(self) -> str:
        return f"""
QPushButton {{
    color: {C.TEXT_DIM};
    background: {C.BG_INPUT};
    border: 1px solid {C.BORDER_MID};
    border-radius: 3px;
    font-family: monospace;
    font-size: {T.XL}px;
}}
QPushButton:hover {{ color: {C.TEXT_HI}; background: {C.BG_HOVER}; border-color: {C.BORDER_MID}; }}
"""

    # Bouton icône SANS cadre (QToolButton) — + ajout, ⌕ recherche : survol = ACCENT
    @property
    def toolbutton_icon(self) -> str:
        return f"""
QToolButton {{
    color: {C.TEXT_DIM};
    background: transparent;
    border: none;
    font-size: {T.XXL}px;
    padding: 0 3px;
}}
QToolButton:hover {{ color: {C.ACCENT}; }}
QToolButton:pressed {{ color: {C.ACCENT}; opacity: 0.7; }}
"""

    # Bouton icône SANS cadre pour action destructive (× supprimer) : survol = rouge
    @property
    def toolbutton_danger(self) -> str:
        return f"""
QToolButton {{
    color: {C.TEXT_NORM};
    background: transparent;
    border: none;
    font-family: monospace;
    font-size: {T.XL}px;
    padding: 0;
}}
QToolButton:hover {{ color: {C.ACCENT_RED}; }}
QToolButton:pressed {{ color: #ff3030; }}
"""

    # Listes (assets, scènes, palettes) — ligne sélectionnée = barre ACCENT à gauche
    @property
    def list_widget(self) -> str:
        return f"""
QListWidget {{
    background: {C.BG_BASE};
    color: {C.TEXT_NORM};
    border: 1px solid {C.BORDER};
    border-radius: 3px;
    outline: none;
}}
QListWidget::item {{
    /* Pas de filet entre les lignes : à 20+ items ça fait une grille. La
       hauteur de ligne suffit à les séparer (cf. QSS.tree_widget). */
    padding: 4px 6px;
    min-height: {S.XL}px;
    border: none;
    border-left: 2px solid transparent;
}}
QListWidget::item:selected {{
    background: {C.BG_SEL};
    color: {C.ACCENT};
    border-left: 2px solid {C.ACCENT};
}}
QListWidget::item:hover:!selected {{
    background: {C.BG_PANEL};
}}
"""

    # Liste plate d'un viewer (polices, fonds) — pendant de tree_widget pour
    # les finders sans hiérarchie : même retrait gauche, même hauteur de ligne,
    # même sélection. `accent` teinte la ligne sélectionnée à la couleur de la
    # contexte d'un finder, si cet écran en a réellement besoin.
    def finder_list(self, accent: str | None = None) -> str:
        accent = accent or C.ACCENT
        return f"""
QListWidget {{
    background: {C.BG_BASE};
    color: {C.TEXT_NORM};
    border: none;
    outline: none;
    font-family: {T.UI_STACK};
    font-size: {T.LG}px;
    padding-left: {S.LG}px;
    padding-right: {S.SM}px;
}}
QListWidget::item {{
    padding: 3px 6px;
    min-height: {S.XL}px;
    border: none;
    border-left: 2px solid transparent;
}}
QListWidget::item:selected {{
    background: {C.BG_SEL};
    color: {accent};
    border-left: 2px solid {accent};
}}
QListWidget::item:hover:!selected {{
    background: {C.BG_PANEL};
}}
"""

    # Barres de défilement fines (verticale + horizontale), poignée grise
    # Arborescences (finder projet, palettes, sons, textes, sprites)
    @property
    def tree_widget(self) -> str:
        return f"""
QTreeWidget {{
    background: {C.BG_BASE};
    color: {C.TEXT_NORM};
    border: none;
    font-family: {T.UI_STACK};
    /* T.LG = corps « sidebar » : les viewers sont des colonnes qu'on balaie
       du regard, 12 px y sont trop serrés. Les items qui posent leur propre
       QFont doivent utiliser ui_font(T.LG) pour rester d'accord. */
    font-size: {T.LG}px;
    outline: none;
    show-decoration-selected: 1;
    /* Retrait gauche : les lignes se rangent SOUS le titre de section, et la
       surbrillance de sélection démarre en retrait, ce qui l'allège. */
    padding-left: {S.LG}px;
    padding-right: {S.SM}px;
}}
QTreeWidget::item {{
    height: {S.ROW}px;
    padding-left: 2px;
    border: none;
    /* liseré transparent au repos : la ligne ne se décale pas de 2 px
       quand elle passe en sélection */
    border-left: 2px solid transparent;
}}
QTreeWidget::item:selected {{
    background: {C.BG_SEL};
    color: {C.ACCENT};
    /* Le bord gauche est RÉSERVÉ à l'état « actif » (barre peinte par
       RowSelectionDelegate) — la sélection ne dessine plus de liseré gauche,
       sinon les deux notions (sélection vs actif) se confondent. */
    border-left: 2px solid transparent;
}}
QTreeWidget::item:hover:!selected {{
    background: {C.BG_PANEL};
}}
QTreeWidget::branch {{
    background: {C.BG_BASE};
}}
{_tree_arrow_rule("QTreeWidget::branch:has-children:closed", "right", C.TEXT_DIM)}
{_tree_arrow_rule("QTreeWidget::branch:has-children:open", "down", C.TEXT_DIM)}
"""

    @property
    def scrollbar(self) -> str:
        return f"""
QScrollBar:vertical {{
    background: {C.BG_BASE};
    width: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C.SCROLL_HANDLE};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {C.SCROLL_HANDLE_HOVER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: {C.BG_BASE};
    height: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {C.SCROLL_HANDLE};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C.SCROLL_HANDLE_HOVER}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
"""

    # Zone défilante sans cadre propre (contenu qui doit se fondre dans son parent)
    @property
    def scroll_area(self) -> str:
        return "QScrollArea { border: none; background: transparent; }"

    # Carte élevée d'un inspecteur (fond BG_RAISED, coins arrondis) — l'object_name
    # isole chaque carte pour ne pas teinter les QFrame/QLabel enfants transparents
    def card(self, object_name: str) -> str:
        return f"""
QFrame#{object_name} {{
    background: {C.BG_RAISED};
    border: none;
    border-radius: 6px;
}}
QFrame#{object_name} QFrame {{
    background: transparent;
    border: none;
}}
QFrame#{object_name} QLabel {{
    background: transparent;
    border: none;
}}
"""

    # Encadré de notice (ui/common/notice.py) — niveau 2 quand la gravité
    # l'impose, et tout le niveau 3. La teinte du ton porte le cadre ET le
    # fond, à deux opacités : c'est ce qui le fait lire comme un bloc à part
    # sans lui donner un aplat opaque de plus dans une carte déjà sombre.
    def notice_box(self, color: str) -> str:
        return f"""
QFrame#noticeBox {{
    background: {tint(color, 0.07)};
    border: 1px solid {tint(color, 0.30)};
    border-radius: 4px;
}}
QFrame#noticeBox QLabel {{
    background: transparent;
    border: none;
}}
"""

    # Fond de fenêtre modale (project picker, dialogues de confirmation)
    @property
    def dialog(self) -> str:
        return f"QDialog {{ background: {C.BG_BASE}; }}"

    # Poignée entre panneaux redimensionnables (survol = ACCENT)
    @property
    def splitter(self) -> str:
        return f"""
QSplitter::handle {{
    background: {C.BORDER};
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:vertical {{
    height: 3px;
}}
QSplitter::handle:hover {{
    background: {C.ACCENT};
}}
"""

    # Bulles d'aide au survol
    @property
    def tooltip(self) -> str:
        return f"""
QToolTip {{
    background: {C.BG_RAISED};
    color: {C.TEXT_NORM};
    border: 1px solid {C.BORDER_MID};
    padding: 5px 8px;
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
}}
"""
    # PAS de `border-radius` ici : avec un arrondi, Qt rend la bulle dans une fenêtre
    # translucide, et sur Windows le fond n'est alors pas peint — un rectangle noir
    # sous le texte, à la place du fond du thème.

    # Menus contextuels et déroulants (clic droit, menus de la barre)
    @property
    def menu(self) -> str:
        return f"""
QMenu {{
    background: {C.BG_RAISED};
    color: {C.TEXT_NORM};
    border: 1px solid {C.BORDER_MID};
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
    padding: 2px;
}}
QMenu::item {{
    padding: 4px 20px 4px 12px;
    border-radius: 2px;
}}
QMenu::item:selected {{
    background: {C.BG_SEL};
    color: {C.ACCENT};
}}
QMenu::separator {{
    height: 1px;
    background: {C.BORDER};
    margin: 3px 6px;
}}
"""

    # Barre d'outils sous le menu (boutons ; actif coché = fond ACCENT)
    @property
    def toolbar(self) -> str:
        return f"""
QToolBar {{
    background: {C.BG_RAISED};
    border-bottom: 1px solid {C.BORDER};
    spacing: 4px;
    padding: 2px 8px;
}}
QToolButton {{
    color: {C.TEXT_NORM};
    border: none;
    padding: 4px 8px;
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
    border-radius: 3px;
}}
QToolButton:hover {{
    background: {C.BG_HOVER};
    color: {C.TEXT_HI};
}}
QToolButton:checked {{
    background: {C.BG_SEL};
    color: {C.ACCENT};
}}
"""

    # Barre de menus tout en haut (Fichier, Édition…)
    @property
    def menubar(self) -> str:
        return f"""
QMenuBar {{
    background: {C.BG_RAISED};
    color: {C.TEXT_NORM};
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
    border-bottom: 1px solid {C.BORDER};
}}
QMenuBar::item:selected {{ background: {C.BG_HOVER}; }}
QMenuBar::item:pressed  {{ background: {C.BG_SEL}; color: {C.ACCENT}; }}
"""

    # Barre d'état tout en bas (fond le plus sombre, texte discret)
    @property
    def statusbar(self) -> str:
        return f"""
QStatusBar {{
    background: {C.BG_DEEP};
    color: {C.TEXT_DIM};
    font-family: {T.UI_STACK};
    font-size: {T.SM}px;
    border-top: 1px solid {C.BORDER};
}}
"""

    # Onglets (bascule entre vues) — onglet actif = liseré ACCENT en haut
    @property
    def tab(self) -> str:
        return f"""
QTabWidget::pane {{
    border: 1px solid {C.BORDER};
    background: {C.BG_PANEL};
}}
QTabBar::tab {{
    background: {C.BG_RAISED};
    color: {C.TEXT_DIM};
    border: 1px solid {C.BORDER};
    border-bottom: none;
    padding: 4px 12px;
    font-family: {T.UI_STACK};
    font-size: {T.MD}px;
}}
QTabBar::tab:selected {{
    background: {C.BG_PANEL};
    color: {C.ACCENT};
    border-top: 2px solid {C.ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {C.BG_HOVER};
    color: {C.TEXT_NORM};
}}
"""

    # ──────────────────────────────────────────────────────────────
    #  Hiérarchie de titres — LA grammaire commune à toute l'app.
    #  3 niveaux + l'état vide ; aucun panneau ne définit son propre
    #  style de titre en dehors de ces briques.
    # ──────────────────────────────────────────────────────────────

    # Niveau 1 — en-tête de panneau/finder (« PROJECT VIEWER », « SFX »).
    # Discret : le contenu prime, l'en-tête ne fait que ranger.
    @property
    def title_panel(self) -> str:
        return (f"color: {C.TEXT_DIM}; background: transparent; border: none;"
                f"font-family: {T.UI_STACK}; font-size: {T.SM}px;"
                f"font-weight: 600; letter-spacing: 1px;")

    # Niveau 1b — titre de section d'un finder (« SCENES », « PREFABS »).
    # Un cran au-dessus de title_panel : dans un viewer, ce sont les sections
    # qui portent la structure. Ni fond ni cadre — la hiérarchie tient à
    # l'espace et à la casse, pas à des bandeaux empilés.
    def title_finder(self, color: str | None = None) -> str:
        return (f"color: {color or C.TEXT_NORM}; background: transparent; border: none;"
                f"font-family: {T.UI_STACK}; font-size: {T.LG}px;"
                f"font-weight: 600; letter-spacing: 1.2px;")

    # Niveau 1c — intertitre DANS une section de finder (« ACTORS » sous
    # SCRIPTS). Le plus discret : il range, il ne s'annonce pas.
    @property
    def title_group(self) -> str:
        return (f"color: {C.TEXT_MUTED}; background: transparent; border: none;"
                f"font-family: {T.UI_STACK}; font-size: {T.XS}px;"
                f"font-weight: 700; letter-spacing: 1.2px;")

    # Niveau 2 — titre de section d'inspecteur (« SCENE MODE », « PALETTE »).
    # Périwinkle par défaut ; `color` ne sert qu'aux en-têtes pilotés par la
    # contexte local (AssetHeaderBar, par exemple), pas une couleur globale
    # attachée au type d'asset.
    def title_section(self, color: str | None = None) -> str:
        return (f"color: {color or C.ACCENT}; background: transparent; border: none;"
                f"font-family: {T.UI_STACK}; font-size: {T.LG}px;"
                f"font-weight: 600; letter-spacing: 1px;")

    # Niveau 3 — label de champ d'une ligne de formulaire (« Frame », « Speed »)
    @property
    def label_field(self) -> str:
        return (f"color: {C.TEXT_DIM}; background: transparent; border: none;"
                f"font-family: {T.UI_STACK}; font-size: {T.SM}px;")

    # Message central d'un écran/panneau vide (sélection absente, à venir…)
    @property
    def empty_state(self) -> str:
        return (f"color: {C.TEXT_MUTED}; background: transparent; border: none;"
                f"font-family: {T.UI_STACK}; font-size: {T.LG}px;")


QSS = _QSS()


# ──────────────────────────────────────────────────────────────────
#  Stylesheet globale — à passer UNE SEULE FOIS à app.setStyleSheet()
#  Couvre tous les widgets standard sans setStyleSheet() individuel.
# ──────────────────────────────────────────────────────────────────

GLOBAL_QSS = (
    QSS.tooltip
    + QSS.menu
    + QSS.menubar
    + QSS.toolbar
    + QSS.statusbar
    + QSS.scrollbar
    + QSS.splitter
    + QSS.spinbox
    + QSS.lineedit
    + QSS.checkbox
    + QSS.combobox
    + QSS.list_widget
)
