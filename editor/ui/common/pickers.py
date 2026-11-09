"""editor/ui/common/pickers.py : Slots de sélection réutilisables, tous des
`PickerSlot` (bouton « + Choisir... » quand vide, nom + × quand assigné, popup
recherche+liste au clic). Chaque fabrique ne dit que ses données : les
entrées, la description d'une valeur, ce que fait un choix.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from typing import Callable, Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QPen
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.widgets import PickerSlot, PickerPopup, PickerEntry
from ui.common.palette_swatch import bank_icon
from ui.common.theme import C, T, QSS
from ui.common import icons
from core.models.gba_color import bgr555_to_rgb888
from core.models.palette import PaletteBank

# Jeton renvoyé à on_picked quand l'utilisateur choisit « Sans palette » :
# l'appelant le mappe vers OWN_PAL_BANK (l'asset garde ses couleurs d'origine).
PALETTE_NONE = "__none__"
_NONE_LABEL = 'pick.no_palette_png_colors'


def palette_picker_slot(
    banks: list[PaletteBank],
    current_name: Optional[str],
    accent: str,
    on_picked: Callable[[str], None],
    on_cleared: Optional[Callable[[], None]] = None,
    add_label: str = None,
    parent=None,
    allow_none: bool = True,
) -> PickerSlot:
    """Slot pour choisir une PaletteBank par nom parmi `banks`. Si
    `allow_none` (défaut), une entrée « Sans palette » en tête permet de
    revenir aux couleurs d'origine du PNG : on_picked reçoit alors le jeton
    PALETTE_NONE. `current_name` None + allow_none => affiche « Sans palette ».
    Une palette posée qui n'est pas dans `banks` reste montrée, signalée."""
    if add_label is None:
        add_label = label('common.choose_palette')
    none_entry = PickerEntry(label(_NONE_LABEL), PALETTE_NONE)

    def entries():
        listed = [PickerEntry(bank.name, bank.name, bank_icon(bank)) for bank in banks]
        return ([none_entry] if allow_none else []) + listed

    def describe(name):
        if name == PALETTE_NONE:
            return none_entry
        if not name:
            return None
        bank = next((b for b in banks if b.name == name), None)
        if bank is None:
            return PickerEntry(name, name, missing=True)
        return PickerEntry(bank.name, bank.name, bank_icon(bank))

    slot = PickerSlot(add_label, accent, entries, describe, on_picked,
                      on_cleared=on_cleared, parent=parent)
    slot.set_value(current_name or (PALETTE_NONE if allow_none else None))
    return slot


def attached_script_slot(
    project: Callable[[], object],
    on_assigned: Callable[[str], None],
    on_cleared: Callable[[], None],
    open_file: Callable[[str], None],
    template: str,
    add_label: str,
    new_title: str,
    hint: str = "",
    parent=None,
) -> PickerSlot:
    """Le slot du script attaché à un acteur, une Area, une scène ou une caméra : le même geste partout.

    « + » ouvre la liste des scripts attachables (pas les behaviors) et « Nouveau script » ; un script glissé
    seul depuis l'onglet Disk s'attache aussi ; le nom ouvre le script, « × » le détache. Un script neuf naît
    comme *Create blank* (dossier affiché par l'onglet Disk, annulable, nom pris : suffixé), avec le modèle
    `template` (« actor », « scene », « camera »).

    La valeur du slot est le chemin relatif du script. L'appelant range la valeur (`on_assigned(chemin)`,
    `on_cleared()`) et repose le slot depuis son modèle (`set_value`). `project` est lu au moment du geste."""
    from pathlib import Path
    from PyQt6.QtWidgets import QInputDialog

    def entries():
        proj = project()
        if proj is None:
            return []
        return [PickerEntry(f.name, proj.asset_rel(f)) for f in proj.script_files()]

    def describe(rel):
        if not rel:
            return None
        proj = project()
        path = proj.asset_abs(rel) if proj is not None else None
        name = Path(rel).name
        if path is None or not path.exists():
            return PickerEntry(label('pick.name_missing', name=name), rel, missing=True)
        return PickerEntry(name, rel)

    def _create():
        proj = project()
        if proj is None:
            return
        name, ok = QInputDialog.getText(parent, new_title, label("common.name_without_lua"))
        if not ok or not name.strip():
            return
        from core import asset_creation
        from core.command_dispatcher import get_dispatcher
        from core.history import RefreshAfterCmd, get_history
        from ui.common.import_folder import import_folder
        folder = import_folder(proj)
        gesture = asset_creation.create_blank(proj, "script", folder, name=name.strip(), template=template)
        get_history().push(RefreshAfterCmd(gesture.command, get_dispatcher().notify_disk_changed))
        path = folder / f"{gesture.names[0]}.lua"
        slot.pick(proj.asset_rel(path))
        get_dispatcher().notify_scripts_changed()
        open_file(str(path))

    def _open():
        proj, rel = project(), slot.value()
        path = proj.asset_abs(rel) if proj is not None and rel else None
        if path is not None and path.exists():
            open_file(str(path))

    def _dropped(mime) -> Optional[str]:
        """Un seul script attachable glissé depuis l'onglet Disk : son chemin relatif, sinon None."""
        from ui.common.disk_view import dropped_paths
        proj, paths = project(), dropped_paths(mime)
        if proj is None or len(paths) != 1:
            return None
        wanted = Path(paths[0]).resolve()
        path = next((f for f in proj.script_files() if f.resolve() == wanted), None)
        return proj.asset_rel(path) if path is not None else None

    slot = PickerSlot(add_label, icons.COLOR_SCRIPT, entries, describe, on_assigned,
                      on_cleared=on_cleared, on_open=_open,
                      new_label=label('wdg.new_script'), on_new=_create, hint=hint, parent=parent)
    slot.accept_drops(_dropped)
    return slot


_UI_BANK_AUTO_LABEL = 'pick.own_palette_automatic'


def ui_pal_bank_slot(
    active: list,
    current_index: int,
    accent: str,
    on_picked: Callable[[int], None],
    project=None,
    parent=None,
    compact: bool = False,
) -> PickerSlot | QToolButton:
    """Slot pour choisir la banque d'encre de la police PAR DÉFAUT d'une scène :
    un INDEX dans `active` (jusqu'à 16 entrées, vides comprises), pas un nom.

    Même widget que `palette_picker_slot`, mais l'entrée à choisir est un
    SLOT de la scène (`Scene.active_bg_palettes[i]`), pas une banque du
    catalogue : les slots vides sont listés quand même (« (empty) »), la
    sélection peut se remplir après coup, et les masquer ferait disparaître
    un choix déjà posé dans le JSON.

    Deux natures de valeur : -1 = la police garde sa PROPRE palette (une banque
    lui est allouée, comme à un sprite) ; 0-15 = elle lit son encre dans cette
    palette de scène. La « banque du conteneur » N'EST PLUS un choix : un texte
    imbriqué dans un conteneur à fond la prend automatiquement (cf. le chantier
    « la police, une palette d'asset »).

    `compact` conserve le même choix derrière un bouton de barre d'outils, qui
    ouvre le même popup."""

    def describe(i: int) -> PickerEntry:
        if i < 0:
            return PickerEntry(label(_UI_BANK_AUTO_LABEL), -1)
        name = active[i] if i < len(active) else ""
        bank = project.get_palette(name) if (project and name) else None
        return PickerEntry(f"{i} — {name or label('pick.empty')}", i,
                           bank_icon(bank) if bank else None)

    def entries():
        return [describe(i) for i in range(-1, 16)]

    if not compact:
        slot = PickerSlot(label('pick.choose_the_ui_bank'), accent, entries, describe, on_picked,
                          parent=parent)
        slot.set_value(current_index)
        return slot

    button = QToolButton(parent)
    button.setFixedSize(32, 32)
    button.setIconSize(QSize(20, 20))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setStyleSheet(QSS.toolbutton_icon)

    def _show(value: int):
        entry = describe(value)
        button.setIcon(entry.icon or icons.toolbar_icon('bank', C.TEXT_DIM))
        button.setIconSize(QSize(18, 18) if entry.icon is not None else QSize(26, 26))
        button.setToolTip(tooltip(
            title=label('uiinsp.text.bank_title'),
            body=entry.label, note=label('uiinsp.text.bank_tip')))
        button.setAccessibleName(f"{label('uiinsp.text.bank')}: {entry.label}")

    def _picked(value: int):
        _show(value)
        on_picked(value)

    def _open_picker():
        popup = PickerPopup(entries(), accent, parent=button)
        popup.picked.connect(_picked)
        popup.show_below(button)

    _show(current_index)
    button.clicked.connect(_open_picker)
    return button


_FONT_AUTO_LABEL_BASE = 'pick.automatic_first_font'


def font_picker_slot(
    fonts: list,
    usable_names: set,
    current_name: str,
    accent: str,
    on_picked: Callable[[str], None],
    add_label: str = None,
    parent=None,
    project_default: str = "",
) -> PickerSlot:
    """Slot pour choisir la police par défaut d'une scène : un NOM de `Font`
    du projet parmi `fonts`, ou `""` pour « Automatic » (comme
    `Scene.font_name`, cf. `main_gen.project_fonts`).

    Deux nuances propres aux polices : l'entrée « Automatic » affiche la police
    qu'elle résoudrait ; et une police SANS planche exploitable reste listée,
    dite telle quelle, la masquer ferait disparaître un choix déjà posé dans le JSON.

    Ce que « Automatic » résout suit `font_emit.default_font_name` : la « Default
    Font » du projet (`project_default`) si elle est posée et utilisable, sinon la
    seule police utilisable s'il n'y en a qu'une, sinon indécidable ici."""
    if add_label is None:
        add_label = label('pick.choose_the_scene_font')
    icon = icons.get("font", C.TEXT_DIM)

    def _auto_label() -> str:
        if project_default and project_default in usable_names:
            return label('pick.automatic_project_default', project_default=project_default)
        first = sorted(usable_names)[0] if len(usable_names) == 1 else ""
        return label('pick.automatic_first', first=first) if first else label(_FONT_AUTO_LABEL_BASE)

    def describe(name: str) -> PickerEntry:
        if not name:
            return PickerEntry(_auto_label(), "", icon)
        if not any(f.name == name for f in fonts):
            return PickerEntry(label('pick.name_missing', name=name), name, missing=True)
        shown = name if name in usable_names else label('pick.name_no_usable_sheet', name=name)
        return PickerEntry(shown, name, icon)

    def entries():
        return [describe("")] + [describe(f.name) for f in fonts]

    slot = PickerSlot(add_label, accent, entries, describe, on_picked, parent=parent)
    slot.set_value(current_name or "")
    return slot


def collision_tag_slot(
    tags: list[str],
    current_tag: str,
    accent: str,
    on_picked: Callable[[str], None],
    on_created: Callable[[str], None],
    parent=None,
) -> PickerSlot:
    """Slot pour choisir le tag de collision d'une boîte, avec la CRÉATION en
    plus : le texte tapé dans la recherche devient un nouveau tag (`on_created`).
    Le slot ne déclare rien lui-même ; l'appelant possède la déclaration au
    niveau projet."""
    icon = icons.get("view_collision", C.TEXT_DIM)

    def describe(tag: str) -> PickerEntry:
        return PickerEntry(tag, tag, icon)

    slot = PickerSlot(label('pick.choose_a_tag'), accent,
                      lambda: [describe(t) for t in tags], describe, on_picked,
                      new_label=label('pick.create_tag_named', name='{name}'),
                      on_new=on_created, create_named=True, parent=parent)
    slot.set_value(current_tag)
    return slot


def name_picker_slot(
    names: Callable[[], list[str]],
    current: Optional[str],
    accent: str,
    on_picked: Callable[[str], None],
    *,
    add_label: str,
    icon: QIcon | None = None,
    none_label: str | None = None,
    on_cleared: Optional[Callable[[], None]] = None,
    parent=None,
) -> PickerSlot:
    """Slot pour choisir un NOM parmi `names()`, lue à chaque ouverture : un
    sprite, un son, une scène, une caméra, un acteur, une boîte.

    `none_label` fait de l'absence de choix une entrée nommée en tête (valeur
    `""`), au lieu du « + ». Un nom posé qui n'est plus dans la liste reste
    montré, signalé « (missing) »."""

    def describe(name):
        if not name:
            return PickerEntry(none_label, "") if none_label else None
        if name not in names():
            return PickerEntry(label('pick.name_missing', name=name), name, missing=True)
        return PickerEntry(name, name, icon)

    def entries():
        head = [PickerEntry(none_label, "")] if none_label else []
        return head + [PickerEntry(n, n, icon) for n in names()]

    slot = PickerSlot(add_label, accent, entries, describe, on_picked,
                      on_cleared=on_cleared, parent=parent)
    slot.set_value(current)
    return slot


# ── Une COULEUR d'une banque, par son index ───────────────────────
# Même modèle que les slots ci-dessus — popup de recherche + liste — mais pour
# un INDEX dans une banque, pas pour un asset nommé.
#
# Le code hexadécimal est AFFICHÉ et jamais SAISI : sur cette machine une
# couleur d'interface est un index dans une banque de 16, pas un RGB libre.
# Un champ où l'on taperait « #93B478 » promettrait une couleur que le matériel
# ne sait pas produire — et il faudrait alors soit la refuser après coup, soit
# l'arrondir en silence. On montre donc ce que l'index VAUT (lisible, copiable)
# et on ne se choisit que dans ce qui existe.

class ColorIndexSlot(QWidget):
    """Choix d'une couleur par son index dans une banque de palettes.

    `picked(int)` porte l'index retenu. La liste est FILTRÉE sur les couleurs
    réellement présentes dans la banque : proposer les seize d'office ferait
    choisir des index qui ne peignent rien.

    Un index déjà posé qui sort de la banque (banque changée depuis) reste
    montré, signalé comme pendant — l'effacer sans le dire perdrait un choix
    que quelqu'un a fait. `compact_label` active le bouton sans libellé : son
    nom accessible et son infobulle portent le rôle et la valeur, tandis que
    `role` choisit l'icône commune d'encre ou de surlignement."""

    picked = pyqtSignal(int)

    def __init__(self, zero_label: str, accent: str, parent=None,
                 compact_label: str = "", role: str = "ink"):
        super().__init__(parent)
        self._zero_label = zero_label
        self._accent = accent
        self._bank = None
        self._index = 0
        self._compact_label = compact_label
        self._role = role

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._swatch = QLabel()
        self._swatch.setFixedSize(22, 22)
        self._swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._swatch)

        # Lecture seule, mais SÉLECTIONNABLE : on vient souvent ici pour relire
        # une couleur et la reporter ailleurs (un fond, une autre zone).
        self._code = QLabel()
        self._code.setFont(QFont(T.MONO, T.SM))
        self._code.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._code.setStyleSheet(f"color:{C.TEXT_NORM};")
        row.addWidget(self._code, 1)

        self._btn = QToolButton()
        self._btn.setFixedSize(24, 24)
        self._btn.setStyleSheet(QSS.toolbutton_icon)
        self._btn.setIcon(icons.get(role, C.TEXT_DIM))
        self._btn.setToolTip(tooltip(
            title=label('pick.open_palette_title'), body=label('pick.pick_hint')))
        self._btn.clicked.connect(self._open)
        row.addWidget(self._btn)
        if compact_label:
            self._swatch.hide()
            self._code.hide()
            self._btn.setFixedSize(32, 32)
            self._btn.setIconSize(QSize(26, 26))
            self._btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.setFixedSize(32, 32)
            row.setSpacing(0)
            self._sync()

    # ── Lecture ───────────────────────────────────────────────────

    def set_value(self, bank, index: int):
        """Repose la banque courante et l'index choisi."""
        self._bank, self._index = bank, max(0, int(index or 0))
        self._sync()

    def _color_at(self, idx: int):
        """(r, g, b) de l'index dans la banque, ou None s'il n'y est pas."""
        if not self._bank or not (0 <= idx < len(self._bank.colors)):
            return None
        return bgr555_to_rgb888(self._bank.colors[idx])

    def _sync(self):
        self._sync_details()
        if self._compact_label:
            # Le symbole occupe toute la place ; la couleur vit dans une
            # pastille en coin, sans réduire l'icône pour loger une barre.
            rgb = self._color_at(self._index)
            missing = bool(self._index and rgb is None)
            color = C.ACCENT_YLW if missing else C.TEXT_DIM
            pixmap = QPixmap(52, 52)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            icons.toolbar_icon(self._role, color).paint(painter, 0, 0, 52, 52)
            if self._index:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QColor("#000000"), 2))
                painter.setBrush(QColor(*rgb) if rgb is not None else QColor(color))
                painter.drawEllipse(30, 30, 20, 20)
            painter.end()
            self._btn.setIcon(QIcon(pixmap))
            value = self._code.text()
            if self._index:
                value = f"{self._index} · {value}"
            self._btn.setToolTip(tooltip(
                title=self._compact_label, body=value,
                note=label('pick.pick_hint')))
            self._btn.setAccessibleName(f"{self._compact_label}: {self._code.text()}")

    def _sync_details(self):
        """Le swatch est un aplat SEULEMENT quand il montre une vraie couleur.

        Les deux autres états ne SONT pas des couleurs — un rectangle en
        pointillés transparents (l'ancien rendu de « pas de couleur ») se lit
        comme un swatch cassé, et un rectangle bordé de jaune sur fond neutre
        (l'ancien rendu de « index absent de la banque ») se lit d'un coup
        d'œil comme un aplat de plus, pas comme une alerte. Une icône —
        police pour l'un, avertissement pour l'autre — ne peut pas être prise
        pour une couleur."""
        rgb = self._color_at(self._index)
        if self._index == 0:
            self._swatch.setPixmap(icons.get(self._role, C.TEXT_DIM).pixmap(18, 18))
            self._swatch.setStyleSheet(
                f"background:{C.BG_INPUT}; border:1px solid {C.BORDER_MID};"
                f"border-radius:3px;")
            self._code.setText(self._zero_label)
            self._code.setStyleSheet(f"color:{C.TEXT_DIM};")
            self._code.setToolTip("")
            return
        if rgb is None:
            # Index posé, couleur introuvable : on le DIT plutôt que de le
            # remettre à zéro dans le dos de l'auteur.
            self._swatch.setPixmap(icons.get("warning", C.ACCENT_YLW).pixmap(18, 18))
            self._swatch.setStyleSheet(
                f"background:{C.BG_INPUT}; border:1px solid {C.ACCENT_YLW};"
                f"border-radius:3px;")
            self._code.setText(label('pick.index_index_not_in_the_bank', _index=self._index))
            self._code.setStyleSheet(f"color:{C.ACCENT_YLW};")
            self._code.setToolTip(tooltip(
                title=label('pick.unavailable_color_title'),
                body=label('pick.stale_index_tip')))
            return
        r, g, b = rgb
        self._swatch.setPixmap(QPixmap())   # efface une icône posée au tour précédent
        self._swatch.setStyleSheet(
            f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER_MID};"
            f"border-radius:3px;")
        self._code.setText(f"#{r:02X}{g:02X}{b:02X}")
        self._code.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._code.setToolTip(tooltip(
            title=label('pick.color_index_title', _index=self._index),
            body=label('pick.index_tip', _index=self._index)))

    # ── Choix ─────────────────────────────────────────────────────

    def _entries(self) -> list[PickerEntry]:
        """L'index 0 nommé, puis ce que la banque contient RÉELLEMENT."""
        out = [PickerEntry(self._zero_label, 0)]
        n = len(self._bank.colors) if self._bank else 0
        for idx in range(1, n):
            r, g, b = bgr555_to_rgb888(self._bank.colors[idx])
            pm = QPixmap(14, 14)
            pm.fill(QColor(r, g, b))
            out.append(PickerEntry(f"{idx}   #{r:02X}{g:02X}{b:02X}", idx, QIcon(pm)))
        if not n:
            # Aucune banque désignée : l'index reste un choix valide (la scène
            # peut en désigner une plus tard), on ne peut simplement pas en
            # montrer la couleur.
            out += [PickerEntry(f"{i} — {label('pick.empty')}", i)
                    for i in range(1, 16)]
        return out

    def _open(self):
        popup = PickerPopup(self._entries(), self._accent, parent=self)
        popup.picked.connect(self._on_picked)
        popup.show_below(self)

    def _on_picked(self, idx: int):
        if idx == self._index:
            return
        self._index = idx
        self._sync()
        self.picked.emit(idx)
