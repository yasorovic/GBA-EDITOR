"""editor/ui/common/pickers.py — Slots de sélection réutilisables, construits
sur le même modèle que le "script selector" (ScriptSlot + ScriptPickerPopup) :
bouton "+ Choisir..." quand vide, nom + Changer + × quand assigné, popup
recherche+liste au clic.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from typing import Callable, Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.widgets import ScriptSlot, ScriptPickerPopup
from ui.common.palette_swatch import bank_icon
from ui.common.theme import C, T, QSS
from ui.common import icons
from core.models.gba_color import bgr555_to_rgb888
from core.models.palette import PaletteBank

# Jeton renvoyé à on_picked quand l'utilisateur choisit « Sans palette » —
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
) -> ScriptSlot:
    """Slot pour choisir une PaletteBank par nom parmi `banks`. Si
    `allow_none` (défaut), une entrée « Sans palette » en tête permet de
    revenir aux couleurs d'origine du PNG — on_picked reçoit alors le jeton
    PALETTE_NONE. `current_name` None + allow_none => affiche « Sans palette »."""
    if add_label is None:
        add_label = label('common.choose_palette')
    slot = ScriptSlot(
        add_label=add_label, accent_color=accent,
        show_clear=on_cleared is not None,
    )

    current = next((b for b in banks if b.name == current_name), None) if current_name else None
    if current:
        slot.set_script(current.name, icon=bank_icon(current))
    elif allow_none:
        slot.set_script(label(_NONE_LABEL))

    def _open_picker():
        entries = [(bank.name, bank.name, bank_icon(bank)) for bank in banks]
        if allow_none:
            entries.insert(0, (label(_NONE_LABEL), PALETTE_NONE, None))
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(name: str):
            # Met à jour l'affichage du slot AVANT de notifier l'appelant.
            if name == PALETTE_NONE:
                slot.set_script(label(_NONE_LABEL))
            else:
                b = next((x for x in banks if x.name == name), None)
                if b:
                    slot.set_script(b.name, icon=bank_icon(b))
            on_picked(name)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker, on_clear=on_cleared)
    return slot


_UI_BANK_AUTO_LABEL = 'pick.own_palette_automatic'


def ui_pal_bank_slot(
    active: list,
    current_index: int,
    accent: str,
    on_picked: Callable[[int], None],
    project=None,
    parent=None,
) -> ScriptSlot:
    """Slot pour choisir la banque d'encre de la police PAR DÉFAUT d'une scène —
    un INDEX dans `active` (jusqu'à 16 entrées, vides comprises), pas un nom.

    Même widget que `palette_picker_slot`, mais l'entrée à choisir est un
    SLOT de la scène (`Scene.active_bg_palettes[i]`), pas une banque du
    catalogue : les slots vides sont listés quand même (« (empty) ») — la
    sélection peut se remplir après coup, et les masquer ferait disparaître
    un choix déjà posé dans le JSON.

    Deux natures de valeur : -1 = la police garde sa PROPRE palette (une banque
    lui est allouée, comme à un sprite) ; 0-15 = elle lit son encre dans cette
    palette de scène. La « banque du conteneur » N'EST PLUS un choix : un texte
    imbriqué dans un conteneur à fond la prend automatiquement (cf. le chantier
    « la police, une palette d'asset »).

    `ScriptPickerPopup.picked` est typé `str` (chemins de script, son usage
    d'origine) : l'index voyage donc en texte, comme dans `ColorIndexSlot`."""
    slot = ScriptSlot(add_label=label('pick.choose_the_ui_bank'), accent_color=accent,
                      show_clear=False)

    def _label_and_icon(i: int):
        name = active[i] if 0 <= i < len(active) else ""
        bank = project.get_palette(name) if (project and name) else None
        return f"{i} — {name or label('pick.empty')}", (bank_icon(bank) if bank else None)

    def _show(value: int):
        if value < 0:
            slot.set_script(label(_UI_BANK_AUTO_LABEL))
        else:
            lab, icon = _label_and_icon(value)
            slot.set_script(lab, icon=icon)

    _show(current_index)

    def _open_picker():
        entries = [(label(_UI_BANK_AUTO_LABEL), "-1", None)]
        for i in range(16):
            lab, icon = _label_and_icon(i)
            entries.append((lab, str(i), icon))
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(raw: str):
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return
            _show(value)
            on_picked(value)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker)
    return slot


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
) -> ScriptSlot:
    """Slot pour choisir la police par défaut d'une scène — un NOM de `Font`
    du projet parmi `fonts`, ou `""` pour « Automatic » (comme
    `Scene.font_name`, cf. `main_gen.project_fonts`).

    Deux nuances propres aux polices, absentes de `sprite_picker_slot` :
    l'entrée « Automatic » affiche la police qu'elle résoudrait ; et une police
    SANS planche exploitable reste listée, dite telle quelle — la masquer ferait
    disparaître un choix déjà posé dans le JSON.

    Ce que « Automatic » résout suit `font_emit.default_font_name` : la « Default
    Font » du projet (`project_default`) si elle est posée et utilisable, sinon la
    seule police utilisable s'il n'y en a qu'une — sinon indécidable ici."""
    if add_label is None:
        add_label = label('pick.choose_the_scene_font')
    slot = ScriptSlot(add_label=add_label, accent_color=accent, show_clear=False)
    icon = icons.get("font", C.TEXT_DIM)

    def _auto_label() -> str:
        if project_default and project_default in usable_names:
            return label('pick.automatic_project_default', project_default=project_default)
        first = sorted(usable_names)[0] if len(usable_names) == 1 else ""
        return label('pick.automatic_first', first=first) if first else label(_FONT_AUTO_LABEL_BASE)

    def _label(name: str) -> str:
        if not any(f.name == name for f in fonts):
            return label('pick.name_missing', name=name)
        return name if name in usable_names else label('pick.name_no_usable_sheet', name=name)

    def _show(name: str):
        slot.set_script(_auto_label() if not name else _label(name), icon=icon)

    _show(current_name)

    def _open_picker():
        entries = [(_auto_label(), "", icon)]
        entries += [(_label(f.name), f.name, icon) for f in fonts]
        if current_name and not any(f.name == current_name for f in fonts):
            entries.append((_label(current_name), current_name, icon))
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(name: str):
            _show(name)   # rafraîchit le label avant de notifier
            on_picked(name)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker)
    return slot


def sprite_picker_slot(
    sprite_names: list[str],
    current_name: Optional[str],
    accent: str,
    on_picked: Callable[[str], None],
    on_cleared: Optional[Callable[[], None]] = None,
    add_label: str = None,
    parent=None,
) -> ScriptSlot:
    """Slot pour choisir un SpriteAsset par nom — même modèle que
    `palette_picker_slot`, sans icône (pas d'aperçu bon marché pour un sprite)."""
    if add_label is None:
        add_label = label('pick.choose_a_sprite')
    slot = ScriptSlot(
        add_label=add_label, accent_color=accent,
        show_clear=on_cleared is not None,
    )
    if current_name:
        slot.set_script(current_name)

    def _open_picker():
        entries = [(n, n) for n in sorted(sprite_names)]
        popup = ScriptPickerPopup(entries, accent, parent=parent, new_label=None)

        def _picked(name: str):
            slot.set_script(name)   # rafraîchit le label avant de notifier
            on_picked(name)

        popup.picked.connect(_picked)
        popup.show_below(slot)

    slot.set_callbacks(on_add=_open_picker, on_open=_open_picker, on_clear=on_cleared)
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
    que quelqu'un a fait."""

    picked = pyqtSignal(int)

    def __init__(self, zero_label: str, accent: str, parent=None):
        super().__init__(parent)
        self._zero_label = zero_label
        self._accent = accent
        self._bank = None
        self._index = 0

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
        self._btn.setIcon(icons.get("palette", C.TEXT_DIM))
        self._btn.setToolTip(tooltip(
            title=label('pick.open_palette_title'), body=label('pick.pick_hint')))
        self._btn.clicked.connect(self._open)
        row.addWidget(self._btn)

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
            self._swatch.setPixmap(icons.get("font", C.TEXT_DIM).pixmap(18, 18))
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

    def _entries(self) -> list:
        """(libellé, valeur, icône) — l'index 0 nommé, puis ce que la banque
        contient RÉELLEMENT."""
        out = [(self._zero_label, "0", None)]
        n = len(self._bank.colors) if self._bank else 0
        for idx in range(1, n):
            r, g, b = bgr555_to_rgb888(self._bank.colors[idx])
            pm = QPixmap(14, 14)
            pm.fill(QColor(r, g, b))
            out.append((f"{idx}   #{r:02X}{g:02X}{b:02X}", str(idx), QIcon(pm)))
        if not self._bank:
            # Aucune banque désignée : l'index reste un choix valide (la scène
            # peut en désigner une plus tard), on ne peut simplement pas en
            # montrer la couleur.
            out += [(f"{i}", str(i), None) for i in range(1, 16)]
        return out

    def _open(self):
        popup = ScriptPickerPopup(self._entries(), self._accent,
                                  parent=self, new_label=None)
        popup.picked.connect(self._on_picked)
        popup.show_below(self)

    def _on_picked(self, value: str):
        try:
            idx = int(value)
        except (TypeError, ValueError):
            return
        if idx == self._index:
            return
        self._index = idx
        self._sync()
        self.picked.emit(idx)
