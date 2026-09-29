"""
editor/ui/icons.py — Registre centralisé des icônes.

Toutes les icônes de l'application passent par ce module.
Pour migrer vers un autre icon set (font bundlée, SVGs…),
seul ce fichier change — le reste du code appelle get() / fallback().

Backend : qtawesome — Material Design Icons (mdi.*)
Fallback : QIcon vide si qtawesome absent (pas de crash)
"""

from __future__ import annotations
import tempfile
from pathlib import Path
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

# ── Couleur neutre des icônes ─────────────────────────────────────
#
# Il n'existe plus de palette globale par famille d'asset. Actor, scène,
# script, police… restent reconnaissables PAR LA FORME de leur icône, jamais
# par une teinte qui les suivrait dans tout l'éditeur. Un écran qui a besoin
# de couleur (état actif, type de zone, rôle dans un outil) la définit dans
# son propre contexte, avec sa propre règle de lecture.
from core.interface_preferences import interface_theme as _interface_theme
_LIGHT = _interface_theme() == "light"
COLOR_DEFAULT = "#666666" if _LIGHT else "#8c8c8c"   # gris neutre
COLOR_ACTIVE  = "#3a3a3a" if _LIGHT else "#d0d0d0"   # état actif neutre
COLOR_FOLDER  = "#8a8a8a" if _LIGHT else "#6e6e6e"   # dossier — gris neutre

# Alias de compatibilité : les consommateurs existants continuent à demander
# une couleur, mais elle est volontairement neutre. Les nouveaux outils ne
# doivent pas s'en servir pour réintroduire une taxonomie globale.
COLOR_ACTOR      = COLOR_DEFAULT
COLOR_PREFAB     = COLOR_DEFAULT
COLOR_SPRITE     = COLOR_DEFAULT
COLOR_SCENE      = COLOR_DEFAULT
COLOR_BACKGROUND = COLOR_DEFAULT
COLOR_SCRIPT     = COLOR_DEFAULT
COLOR_SFX        = COLOR_DEFAULT
COLOR_MUSIC      = COLOR_DEFAULT
COLOR_EVENT    = COLOR_SCRIPT
COLOR_BEHAVIOR = COLOR_SCRIPT
COLOR_GLOBAL   = COLOR_SCRIPT
COLOR_CONST    = COLOR_SCRIPT
COLOR_UI        = COLOR_DEFAULT
COLOR_UI_LAYOUT = COLOR_DEFAULT
COLOR_UI_PANEL  = COLOR_DEFAULT
COLOR_UI_TEXT   = COLOR_DEFAULT
COLOR_UI_REGION = COLOR_DEFAULT
COLOR_FONT      = COLOR_DEFAULT

# ── Registre : nom logique → (qta_key, unicode_fallback) ──────────
# Pour swapper l'icon set : remplacer les qta_key par les nouveaux.
_REGISTRY: dict[str, tuple[str, str]] = {
    # Outils canvas
    "tool_select":           ("mdi.cursor-default",          "↖"),
    "tool_add":              ("mdi.plus-circle-outline",     "⊕"),
    "tool_erase":            ("mdi.eraser-variant",          "⌫"),
    "tool_collision_8":      ("mdi.border-outside",          "▪"),
    "tool_collision_16":     ("mdi.border-all",              "■"),
    "tool_collision_slope":      ("mdi.trending-up",             "◥"),
    "tool_collision_slope_inv":  ("mdi.trending-down",           "◣"),
    "tool_palette":          ("mdi.palette-outline",         "◐"),
    # Zone de texte : un rectangle qui contient du texte — l'outil délimite une
    # surface, il ne saisit pas de texte (celui-ci vient de la table).
    "tool_text_region":      ("mdi.format-text-variant-outline", "⌸"),
    # Interface — types d'éléments d'une mise en page (arbre, toolbar, canvas).
    # Un type = une FORME. Le contexte qui les affiche choisit éventuellement
    # sa couleur d'état ; le registre ne leur attribue pas de couleur globale.
    "ui_layout":             ("mdi.view-dashboard-outline",  "⊞"),
    "ui_container":              ("mdi.card-outline",            "▭"),
    # Liste : un conteneur qui se PARCOURT — d'où des rangées et pas un cadre
    # vide, la forme disant ce que le type fait de plus que le conteneur.
    "ui_list":               ("mdi.format-list-bulleted",    "☰"),
    "ui_text":               ("mdi.format-text",             "T"),
    # Image : le pictogramme d'image, pas celui de sprite — c'est un ÉLÉMENT
    # d'interface qui affiche un sprite, pas le sprite lui-même.
    "ui_image":              ("mdi.image-outline",           "▣"),
    "tool_inpaint_brush":         ("mdi.brush",                   "🖌"),
    "tool_inpaint_rect":          ("mdi.select-drag",             "▭"),
    "tool_fill":                  ("mdi.format-color-fill",       "🪣"),
    # Rôle d'un layer dans le mélange de couleurs — la FORME dit le rôle :
    # hors du mélange, au-dessus (ce qui est mélangé), en dessous (ce avec quoi).
    "blend_off":             ("mdi.circle-outline",          "○"),
    "blend_top":             ("mdi.arrow-up-bold-circle-outline",   "▲"),
    "blend_bottom":          ("mdi.arrow-down-bold-circle-outline", "▼"),
    "eye":                   ("mdi.eye-outline",             "◉"),
    "eye_off":               ("mdi.eye-off-outline",         "◎"),
    # Toggles d'affichage du canvas (toolbar Scene Manager)
    "zoom":                  ("mdi.magnify",                 "⚲"),
    "zoom_in":               ("mdi.magnify-plus-outline",    "⊕"),
    "zoom_out":              ("mdi.magnify-minus-outline",   "⊖"),
    "fit_page":              ("mdi.fit-to-page-outline",     "⊡"),
    "view_grid":             ("mdi.grid",                    "▦"),
    "view_grid_large":       ("mdi.grid-large",              "▤"),
    "view_snap":             ("mdi.magnet",                  "⇲"),
    "view_boxes":            ("mdi.account-box",             "▭"),
    "view_collision":        ("mdi.wall",                    "▨"),
    "view_notes":            ("mdi.note-text-outline",       "▤"),
    "view_minimap":          ("mdi.map-outline",             "▧"),
    "warning":               ("mdi.alert",                   "⚠"),
    # Notices (ui/common/notice.py) — l'icône dit ce que le message annonce là
    # où la couleur ne suffit plus : `build` et `render` sont tous deux jaunes,
    # et ce sont l'alerte et l'œil qui les distinguent. L'ampoule est réservée
    # au niveau 3, pour qu'une astuce se reconnaisse sans être lue.
    "info":                  ("mdi.information-outline",     "ⓘ"),
    "tip":                   ("mdi.lightbulb-on-outline",    "💡"),
    "scroll_h":              ("mdi.arrow-left-right-bold",   "↔"),
    "scroll_v":              ("mdi.arrow-up-down-bold",      "↕"),
    # Project panel — types d'objets
    # Actor/Prefab/Scene se voisinent partout (arbres, menus) : les trois
    # viennent de la même famille Font Awesome 6 Solid plutôt que de mélanger
    # son trait à celui de Material Design Icons (le reste du registre). Le
    # statut « script » ne change pas le pictogramme de l'actor : il se lit
    # dans le contexte qui l'affiche, pas dans une seconde taxonomie de formes.
    "actor":                 ("fa6s.ghost",                  "◕"),
    "actor_empty":           ("fa6s.ghost",                  "◕"),
    "actor_script":          ("fa6s.ghost",                  "◕"),
    "actor_empty_script":    ("fa6s.ghost",                  "◕"),
    # Masques de théâtre : une forme réutilisable ailleurs pour tout ce qui
    # tient du gabarit/de l'archétype, pas seulement les prefabs.
    "prefab":                ("fa6s.masks-theater",          "♟"),
    # Repère d'ancrage d'un actor dans le canvas : une cible est plus explicite
    # qu'une croix dessinée à la main et réutilise le registre d'icônes.
    "actor_origin":          ("mdi.crosshairs",               "⊙"),
    "script_lua":            ("mdi.code-braces",             "λ"),
    "script_file":           ("mdi.file-outline",            "≡"),
    "scene":                 ("fa6s.clapperboard",           "◈"),
    # Groupe technique (ex. tranche OBJ de la projection Priorité) : un
    # marqueur neutre, pour ne pas laisser croire que le GROUPE est lui-même
    # un actor/prefab/scene.
    "priority_group":        ("mdi.circle-outline",          "○"),
    # Un dossier alterne plein (replié) / filet (déplié) dans les arbres —
    # cf. folder_icon() ci-dessous. "folder" seul reste l'état déplié/générique
    # (menus, filtres) pour ne pas toucher les appels qui ignorent l'état.
    "folder":                ("mdi.folder-outline",          "▸"),
    "folder_closed":         ("mdi.folder",                  "▸"),
    "sprite":                ("mdi.image-outline",           "▧"),
    "background":            ("mdi.image-multiple-outline",  "▥"),
    "palette":               ("mdi.palette-outline",         "◐"),
    "font":                  ("mdi.format-font",             "A"),
    "align_left":            ("mdi.format-align-left",       "⇤"),
    "align_center":          ("mdi.format-align-center",     "↔"),
    "align_right":           ("mdi.format-align-right",      "⇥"),
    "anim_state":            ("mdi.play-box-outline",        "▶"),
    "sfx":                   ("mdi.volume-high",             "♪"),
    "music":                 ("mdi.music-note",              "♫"),
    "data_table":            ("mdi.table",                   "▦"),
    "asset_missing":         ("mdi.circle-outline",          "○"),
    "camera":                ("mdi.video",                   "▰"),
    # Sprite Editor — directions
    "dir_n":                 ("mdi.arrow-up",                "↑"),
    "dir_ne":                ("mdi.arrow-top-right",         "↗"),
    "dir_e":                 ("mdi.arrow-right",             "→"),
    "dir_se":                ("mdi.arrow-bottom-right",      "↘"),
    "dir_s":                 ("mdi.arrow-down",               "↓"),
    "dir_sw":                ("mdi.arrow-bottom-left",       "↙"),
    "dir_w":                 ("mdi.arrow-left",              "←"),
    "dir_nw":                ("mdi.arrow-top-left",          "↖"),
    "dir_omni":              ("mdi.arrow-all",               "⊙"),
    "mirror_h":              ("mdi.flip-horizontal",         "↔"),
    "mirror_v":              ("mdi.flip-vertical",           "↕"),
    # Sprite Editor — playback
    "playback_prev":         ("mdi.skip-previous",           "⏮"),
    "playback_play":         ("mdi.play",                    "▶"),
    "playback_stop":         ("mdi.stop",                    "■"),
    "playback_loop":         ("mdi.repeat",                  "↻"),
    "playback_next":         ("mdi.skip-next",               "⏭"),
    "playback_grid":         ("mdi.grid",                    "⊞"),
    "playback_contrast":     ("mdi.contrast-circle",         "◑"),
    # Script Editor — events (EVENT_REGISTRY)
    "ev_start":              ("mdi.play",                    "▶"),
    "ev_update":             ("mdi.autorenew",                "↺"),
    "ev_late_update":        ("mdi.replay",                  "↻"),
    "ev_collide":            ("mdi.hexagon-outline",         "⬡"),
    "ev_collision_enter":    ("mdi.login-variant",           "→"),
    "ev_tile_collide":       ("mdi.grid",                    "▦"),
    "ev_collision_exit":     ("mdi.logout-variant",          "←"),
    "ev_destroy":            ("mdi.trash-can-outline",       "✕"),
    # Script Editor — boutons GBA
    "btn_a":                 ("mdi.alpha-a-circle-outline",  "🅐"),
    "btn_b":                 ("mdi.alpha-b-circle-outline",  "🅑"),
    "btn_l":                 ("mdi.alpha-l-box-outline",     "L"),
    "btn_r":                 ("mdi.alpha-r-box-outline",     "R"),
    "btn_start":             ("mdi.keyboard-return",         "⏎"),
    "btn_select":            ("mdi.menu",                    "≡"),
    "behavior_stub":         ("mdi.function-variant",        "ƒ"),
    # Text Editor — couleurs-clés d'une planche de police
    "eyedropper":            ("mdi.eyedropper",              "⚲"),
    "clear":                 ("mdi.close",                   "✕"),
    # Text Editor — barre de balisage (une par balise de core.text_markup.TAGS,
    # plus le marqueur de valeur ; « mk_ » comme markup)
    "mk_speed":              ("mdi.speedometer",             "»"),
    "mk_pause":              ("mdi.timer-sand",              "⏸"),
    "mk_icon":               ("mdi.sticker-emoji",           "☺"),
    "mk_wave":               ("mdi.waves",                   "∿"),
    "mk_shake":              ("mdi.vibrate",                 "⚡"),
    "mk_color":              ("mdi.palette-outline",         "◐"),
    "mk_value":              ("mdi.variable",                "$"),
    "mk_tag":                ("mdi.tag-outline",             "⌗"),
    # Text Editor — clé d'un texte : accrochée au rangement ou nommée à la main
    "key_auto":              ("mdi.link-variant",            "⚯"),
    "key_manual":            ("mdi.link-variant-off",        "⚮"),
    "copy":                  ("mdi.content-copy",            "⧉"),
    "copied":                ("mdi.check",                   "✓"),
    # Chrome des widgets — consommées par les QSS via qss_image()
    "spin_up":               ("mdi.menu-up",                 "▲"),
    "spin_down":             ("mdi.menu-down",               "▼"),
    # Flèches de repli/dépli des arborescences (QTreeWidget::branch) : PAS ici
    # — theme.py les rend via qss_arrow_image() (triangle vectoriel partagé,
    # cf. plus bas), pour matcher exactement la flèche de FinderSection/
    # _Section/_SubSection (icons.arrow_icon()).
    # Data Editor — bandeau TABLE : deux actions "+" distinctes côte à côte,
    # la FORME dit ce qui est ajouté (ligne vs colonne), pas juste "+".
    "add_row":                ("mdi.table-row-plus-after",    "+▭"),
    "add_column":             ("mdi.table-column-plus-after", "+▯"),
    # Édition externe — ouvrir un asset image dans le logiciel de dessin
    # configuré par l'utilisateur (cf. ui/common/external_editor.py).
    "edit_external":          ("mdi.image-edit-outline",      "✎"),
    # Préparation de la source d'un fond (Background Editor) — recadrer,
    # redimensionner, revenir à l'original.
    "prep_crop":              ("mdi.crop",                    "▣"),
    "prep_resize":            ("mdi.resize",                  "⇲"),
    "prep_reset":             ("mdi.backup-restore",          "↺"),
    # Finders — révéler le dossier RÉEL d'une famille dans l'explorateur du
    # système (cf. ui/common/reveal.py). Bouton standardisé, pas un par écran.
    "reveal_in_files":        ("mdi.folder-open-outline",     "⤢"),
    # Boutons génériques de barre d'outils (ui/common/widgets.py W.btn_add /
    # W.btn_search) — un `QIcon` recolorable au survol (cf. `_HoverIconButton`),
    # jamais un glyphe de police posé par `setText` : la feuille de style ne
    # peut recolorer que du texte, pas un pixmap déjà teinté.
    "add":                    ("mdi.plus",                    "+"),
    "search":                 ("mdi.magnify",                 "⌕"),
}

# ── Backend (chargé une seule fois) ──────────────────────────────
try:
    import qtawesome as _qta
    _BACKEND = "qtawesome"
except ImportError:
    _qta = None       # type: ignore
    _BACKEND = "none"


def get(name: str,
        color: str = COLOR_DEFAULT,
        color_active: str | None = None) -> QIcon:
    """
    Retourne un QIcon pour le nom logique donné.
    color_active : couleur quand le bouton est checked (QToolButton).
    """
    entry = _REGISTRY.get(name)
    if entry is None:
        return QIcon()
    qta_key, _ = entry
    if _qta is not None:
        try:
            kw: dict = {"color": color}
            if color_active:
                kw["color_active"] = color_active
            return _qta.icon(qta_key, **kw)
        except Exception:
            pass
    return QIcon()


def folder_icon(expanded: bool, color: str = COLOR_FOLDER) -> QIcon:
    """Icône dossier des arbres : plein replié, filet déplié — la même
    alternance partout où un dossier peut se déplier (Finder d'assets, arbre
    de scène, arbre de textes)."""
    return get("folder" if expanded else "folder_closed", color)


# ── Icônes dessinées dans une vue zoomable ───────────────────────
# Un pixmap rendu une fois à N px devient flou (ou crénelé) dès que la vue
# l'agrandit. Les items de canvas passent donc par ici : ils redemandent le
# glyphe à la résolution ÉCRAN effective (zoom de la vue × devicePixelRatio)
# et le dessinent dans un rect de `size` unités de scène.

_SCALE_STEP = 0.5     # quantification du facteur — borne le nombre d'entrées
_SCALE_MAX = 16.0     # au-delà, le glyphe est déjà largement sur-échantillonné
_scaled_cache: dict[tuple[str, str, int, float], QPixmap] = {}


def scaled_pixmap(name: str,
                  color: str = COLOR_DEFAULT,
                  size: int = 16,
                  scale: float = 1.0) -> QPixmap:
    """
    Pixmap de l'icône rendue à `size × scale` pixels réels, mise en cache.
    L'appelant dessine dans un rect de `size` unités (rect cible + rect source
    complet) : le résultat est net à tout niveau de zoom.
    """
    q = min(max(round(scale / _SCALE_STEP) * _SCALE_STEP, _SCALE_STEP), _SCALE_MAX)
    key = (name, color, size, q)
    px = _scaled_cache.get(key)
    if px is None:
        n = max(1, int(round(size * q)))
        px = get(name, color).pixmap(QSize(n, n))
        _scaled_cache[key] = px
    return px


def fallback(name: str) -> str:
    """Caractère Unicode de repli pour les widgets qui ne supportent pas QIcon."""
    entry = _REGISTRY.get(name)
    return entry[1] if entry else "?"


# ── Icônes pour les QSS ───────────────────────────────────────────
# `image: url(...)` ne sait lire qu'un fichier ou une ressource Qt : pas de
# police d'icônes, pas de data-URI. On matérialise donc l'icône en PNG dans
# un cache disque. Le CHEMIN est déterministe (clé + couleur + taille), donc
# calculable à l'import de theme.py — alors que le RENDU exige une
# QApplication vivante et n'arrive qu'ensuite (ensure_qss_assets).

_CACHE_DIR = Path(tempfile.gettempdir()) / "gba_editor_icons"
_pending: dict[Path, tuple[str, str, int, float]] = {}


def _render(path: Path) -> None:
    """Écrit le PNG si possible ; silencieux tant que Qt n'est pas prêt."""
    if QApplication.instance() is None or path.exists():
        return
    name, color, size, scale = _pending[path]
    try:
        if _qta is None:
            return
        entry = _REGISTRY.get(name)
        if entry is None:
            return
        icon = _qta.icon(entry[0], color=color, scale_factor=scale)
        path.parent.mkdir(parents=True, exist_ok=True)
        icon.pixmap(size, size).save(str(path), "PNG")
    except Exception:
        pass


def qss_image(name: str, color: str = COLOR_DEFAULT,
              size: int = 16, scale: float = 1.0) -> str:
    """
    Chemin POSIX (QSS n'aime pas les `\\`) d'un PNG rendu depuis l'icon set.
    `scale` grossit le glyphe dans sa boîte — les icônes MDI laissent une
    marge généreuse, trop discrète pour du petit chrome de widget.
    Retourne "" si l'icône est inconnue ou aucun backend disponible : l'appelant
    omet alors la règle `image:` au lieu de pointer un fichier fantôme.
    """
    if _REGISTRY.get(name) is None or _qta is None:
        return ""
    slug = f"{name}_{color.lstrip('#')}_{size}_{scale:g}"
    path = _CACHE_DIR / f"{slug}.png"
    _pending[path] = (name, color, size, scale)
    _render(path)
    return path.as_posix()



# ── Flèche ▾/▸ de repli, PARTAGÉE par tout le chrome de l'appli ─────
# Un glyphe (MDI ou caractère Unicode ▾/▸) dépend de ce que la police en
# cours contient et de QUEL moteur Qt le dessine (QLabel texte via
# QTextLayout ≠ QPainter.drawText hors widget) : deux rendus qui ne se
# ressemblent jamais vraiment, et le second peut même rester blanc si le
# fallback de police ne s'y applique pas hors contexte de widget. On dessine
# donc la flèche nous-mêmes — un simple triangle plein vectoriel — et
# arrow_icon() / qss_arrow_image() sont les DEUX SEULS points d'entrée pour
# cette forme dans toute l'appli : FinderSection, _Section, _SubSection
# (widgets.py / sidebar_widgets.py) et le QSS de QTreeWidget::branch
# (theme.py) y passent tous, donc un dessin strictement identique partout,
# sans dépendre d'aucune police.
_ARROW_NATIVE_PX = 64   # résolution native, mise à l'échelle par l'appelant
                        # (QSS width/height, ou QIcon + setIconSize)
_ARROW_FILL = 0.6       # le triangle occupe 60% du côté de sa boîte


def _arrow_polygon(direction: str):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF
    n = _ARROW_NATIVE_PX
    w = n * _ARROW_FILL          # base du triangle
    h = w * 0.87                 # hauteur ~ équilatérale
    cx = cy = n / 2
    if direction == "right":
        return QPolygonF([QPointF(cx - h / 2, cy - w / 2),
                           QPointF(cx - h / 2, cy + w / 2),
                           QPointF(cx + h / 2, cy)])
    return QPolygonF([QPointF(cx - w / 2, cy - h / 2),
                       QPointF(cx + w / 2, cy - h / 2),
                       QPointF(cx, cy + h / 2)])


def _paint_arrow(direction: str, color: str) -> QPixmap:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QColor, QPainter
    n = _ARROW_NATIVE_PX
    px = QPixmap(n, n)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(color)))
    painter.drawPolygon(_arrow_polygon(direction))
    painter.end()
    return px


_pending_arrow: dict[Path, tuple[str, str]] = {}


def _render_arrow(path: Path) -> None:
    """Écrit le PNG de la flèche si possible ; silencieux tant que Qt n'est pas prêt."""
    if QApplication.instance() is None or path.exists():
        return
    direction, color = _pending_arrow[path]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _paint_arrow(direction, color).save(str(path), "PNG")
    except Exception:
        pass


def qss_arrow_image(direction: str, color: str = COLOR_DEFAULT) -> str:
    """
    Chemin POSIX du PNG de la flèche pleine partagée ("right" = repliée,
    "down" = dépliée), pour la règle `image:` d'une QSS
    (QTreeWidget::branch) — l'appelant fixe `width`/`height` pour la taille
    d'affichage, le rendu natif est en 64px pour rester net à l'échelle.
    """
    slug = f"arrow_{direction}_{color.lstrip('#')}"
    path = _CACHE_DIR / f"{slug}.png"
    _pending_arrow[path] = (direction, color)
    _render_arrow(path)
    return path.as_posix()


def arrow_icon(direction: str, color: str = COLOR_DEFAULT) -> QIcon:
    """
    QIcon de la même flèche pleine partagée, pour un usage direct sur un
    QLabel/QPushButton (FinderSection, _Section, _SubSection) — exactement le
    même dessin que qss_arrow_image(), sans passer par le cache disque QSS.
    L'appelant choisit la taille d'affichage via setIconSize()/pixmap(size).
    """
    if QApplication.instance() is None:
        return QIcon()
    return QIcon(_paint_arrow(direction, color))


def ensure_qss_assets() -> None:
    """
    Rend les PNG demandés par les QSS. À appeler une fois après la création
    de la QApplication et avant `setStyleSheet`.
    """
    for path in list(_pending):
        _render(path)
    for path in list(_pending_arrow):
        _render_arrow(path)
