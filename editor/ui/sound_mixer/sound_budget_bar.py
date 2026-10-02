"""
ui/sound_mixer/sound_budget_bar.py — le bandeau de canaux de l'écran Son.

`window.py` porte déjà UNE barre de budget matériel (`GbaStatusBar`) : OAM,
cycles/ligne, VRAM, palettes — fixée en bas de la FENÊTRE, et rattachée à la
scène active quel que soit l'écran ouvert. Sur l'écran Son, elle continue de
montrer ces quatre chiffres-là — exacts, mais sur le mauvais sujet (ROADMAP
v0.8.5 : « un écran de son qui affiche le budget des sprites ment par
déplacement »). Ce module ne l'étend pas : il lui donne un jumeau LOCAL, pour
la ressource rare de CET écran-ci.

    La ressource rare, ici, ce sont les huit canaux logiciels de maxmod
    (réglables depuis la v0.8.8), partagés entre la musique et le jingle —
    les deux seules couches CONTINUES du système.

Les effets (SoundBox) n'entrent pas dans ce compte : ce sont des déclenchements
PONCTUELS, pilotés par le gameplay, et aucune analyse statique ne borne combien
en jouent à la fois. C'est précisément pour ça que maxmod porte sa propre
politique de pénurie (désassemblée en v0.8.6/v0.8.8) — ce bandeau ne couvre
que ce qui EST prévisible au build : le pire état de chaque couche continue.

Le coût de `mmFrame` dans la frame, cité dans la même phrase du jalon, n'est
PAS affiché : il n'est pas mesuré, et ce projet n'affiche pas de nombre deviné.
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from typing import Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtGui import QFont

from ui.common.theme import C, T
from core.models.sound_box import MusicBox, JingleBox

# Même seuil d'alerte que GbaStatusBar (window.py) : ~75 % du plafond, pas
# un pourcentage arbitraire choisi ici — c'est la marge à laquelle le jalon
# du son a lui-même buté (huit canaux tenus, le neuvième perdu en silence).
_WARN_RATIO = 0.75


def _module_channels(project, cache: dict, asset_name: str) -> int:
    """Le nombre de voies du module cité par `asset_name`, ou 0.

    0 couvre trois cas à la fois — aucun nom, ressource introuvable, fichier
    illisible — et c'est le bon repli : un module absent ne PÈSE rien sur le
    budget, il est signalé ailleurs (le validateur audio, pas cette jauge).
    """
    if not asset_name:
        return 0
    if asset_name in cache:
        return cache[asset_name]
    from core.engine_emulation.module_model import load_module

    n = 0
    music = next((m for m in getattr(project, "music", []) if m.name == asset_name), None)
    ap = project.asset_abs(music.asset) if music and music.asset else None
    if ap and ap.exists():
        try:
            n = load_module(ap).num_channels
        except Exception:
            n = 0
    cache[asset_name] = n
    return n


def worst_case_channels(project, music_box: Optional[MusicBox],
                        jingle_box: Optional[JingleBox]) -> tuple[int, int]:
    """(canaux musique, canaux jingle) — le pire état de CHAQUE couche, prise
    séparément, dans les deux boîtes données.

    Les deux couches ne se coordonnent pas (ROADMAP v0.8.7, « TROIS ASSETS
    indépendants ») : n'importe quel état de musique peut se superposer à
    n'importe quel état de jingle. Le pire total possible est donc la SOMME
    des deux pires pris séparément — pas le pire d'une paire d'états précise,
    qui supposerait une coordination que le matériel n'offre pas.

    Une SEULE boîte est active par famille en jeu (v0.8.7), mais ce bandeau
    lit les boîtes EN COURS D'ÉDITION : c'est celles-là que l'auteur règle,
    donc celles sur lesquelles il attend un retour — même principe que
    `GbaStatusBar`, rattachée à la scène ouverte et non à une scène « qui
    compte » entre plusieurs.
    """
    cache: dict = {}
    music_ch = 0
    if music_box is not None:
        music_ch = max(
            (_module_channels(project, cache, s.music) for s in music_box.states),
            default=0)
    jingle_ch = 0
    if jingle_box is not None:
        jingle_ch = max(
            (_module_channels(project, cache, name)
             for st in jingle_box.states for name in st.mapping.values()),
            default=0)
    return music_ch, jingle_ch


class SoundBudgetBar(QWidget):
    """Bandeau fixe en bas de l'écran Son : UN compteur, « canaux ».

    Même langage visuel que `GbaStatusBar` (nom en gris, valeur en gras,
    trois couleurs, tooltip qui explique la règle) — mais un widget à part,
    pas une extension : la barre de fenêtre reste sprite/BG, celle-ci reste
    son, et aucune des deux ne montre le budget de l'autre.
    """
    _STYLE_OK   = f"color:{C.TEXT_NORM};"
    _STYLE_WARN = f"color:{C.ACCENT_YLW};"
    _STYLE_CRIT = f"color:{C.ACCENT_RED};"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setStyleSheet(f"background:{C.BG_DEEP}; border-top:1px solid {C.BORDER};")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(0)

        lbl_name = QLabel(label('sndbar.channels'))
        lbl_name.setFont(QFont(T.MONO, T.XS))
        lbl_name.setStyleSheet(f"color:{C.TEXT_MUTED};")
        lay.addWidget(lbl_name)

        self._value = QLabel("0/8")
        self._value.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        self._value.setStyleSheet(self._STYLE_OK)
        lay.addWidget(self._value)

        self._detail = QLabel("")
        self._detail.setFont(QFont(T.MONO, T.XS))
        self._detail.setStyleSheet(f"color:{C.TEXT_MUTED};")
        lay.addWidget(self._detail)

        lay.addStretch()

        for w in (lbl_name, self._value, self._detail):
            w.setToolTip(tooltip(
                title=label("sndbar.channels_title"),
                body=label("sndbar.channels_tip"),
                note=label("sndbar.channels_note"),
            ))

    def update_boxes(self, project, music_box: Optional[MusicBox],
                     jingle_box: Optional[JingleBox], limit: int):
        music_ch, jingle_ch = worst_case_channels(project, music_box, jingle_box)
        total = music_ch + jingle_ch
        self._value.setText(f"{total}/{limit}")
        self._detail.setText(label('sndbar.channels_detail', music_ch=music_ch, jingle_ch=jingle_ch))
        warn = round(limit * _WARN_RATIO)
        # `>=`, pas `>` : même règle que GbaStatusBar (window.py) — atteindre
        # PILE le plafond veut dire qu'il ne reste plus rien pour les effets,
        # qui ne sont pas comptés ici mais partagent le même pool.
        if total >= limit:
            self._value.setStyleSheet(self._STYLE_CRIT)
        elif total >= warn:
            self._value.setStyleSheet(self._STYLE_WARN)
        else:
            self._value.setStyleSheet(self._STYLE_OK)
