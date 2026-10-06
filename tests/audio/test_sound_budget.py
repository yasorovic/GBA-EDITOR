"""Le bandeau de canaux de l'écran Son — `ui/sound_mixer/sound_budget_bar.py`.

Purement la fonction de calcul : c'est elle qui décide, le widget ne fait que
l'afficher (même partage que partout dans ce dépôt entre logique et Qt). Le
piège qu'un test doit attraper ici est celui que la ROADMAP nomme : les DEUX
couches (musique, jingle) sont indépendantes, donc le pire total est une
SOMME de deux maximums séparés — pas le pire état d'une seule boîte, ni le
maximum d'un état combiné qui n'existe nulle part dans le modèle.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F          # noqa: E402
from core.models.audio import Music  # noqa: E402
from core.models.sound_box import (  # noqa: E402
    MusicBox, MusicState, JingleBox, ActionState,
)
from core.project import Project     # noqa: E402
from ui.sound_mixer.sound_budget_bar import worst_case_channels  # noqa: E402


def _projet(tmp_path) -> Project:
    """Un projet en mémoire, comme test_palette_alloc.py : aucun sidecar
    n'est lu, les registres se remplissent à la main."""
    return Project(tmp_path)


def _ajouter_musique(p: Project, nom: str, data: bytes, ext: str) -> Music:
    """Une Music dont l'asset EXISTE sur disque — `worst_case_channels` lit
    le fichier pour connaître son nombre de voies, comme le fera l'auteur."""
    path = p.root / "assets" / "music" / f"{nom}{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    m = Music(name=nom, asset=p.asset_rel(path))
    p.music.append(m)
    return m


def test_le_pire_total_est_la_somme_de_deux_maximums_separes(tmp_path):
    """Le MOD de fixture a 4 canaux, le XM en a 1 (cf. module_fixtures.py).
    Une MusicBox à deux états (4 et 1 canal) et une JingleBox à un état
    (1 canal) doivent donner 4 + 1 — le pire état de chaque couche, pas le
    pire état d'une seule."""
    p = _projet(tmp_path)
    quatre = _ajouter_musique(p, "Quatre", F.make_mod(), ".mod")
    un = _ajouter_musique(p, "Un", F.make_xm(), ".xm")

    box = MusicBox(name="musics", states=[
        MusicState(name="calme", music=un.name),
        MusicState(name="combat", music=quatre.name),
    ])
    jingle = JingleBox(name="jingles", actions=["victoire"], states=[
        ActionState(name="s", mapping={"victoire": un.name}),
    ])

    music_ch, jingle_ch = worst_case_channels(p, box, jingle)
    assert (music_ch, jingle_ch) == (4, 1)


def test_un_etat_sans_musique_ne_pese_rien():
    """`MusicState.music == ""` est un silence explicite (ROADMAP v0.8.2) —
    il ne doit ni faire planter le calcul, ni compter comme un canal."""
    p = Project(Path("."))
    box = MusicBox(name="m", states=[MusicState(name="silence", music="")])
    music_ch, jingle_ch = worst_case_channels(p, box, None)
    assert (music_ch, jingle_ch) == (0, 0)


def test_une_boite_absente_ne_pese_rien():
    """Aucune JingleBox choisie dans l'onglet (`None`) : la couche jingle ne
    contribue rien, elle ne fait pas planter le calcul."""
    p = Project(Path("."))
    box = MusicBox(name="m", states=[])
    music_ch, jingle_ch = worst_case_channels(p, box, None)
    assert (music_ch, jingle_ch) == (0, 0)


def test_une_reference_musicale_disparue_ne_pese_rien():
    """Une ressource Music dont le fichier n'existe plus sur le disque —
    déplacé, supprimé à la main — ne doit pas faire planter le bandeau. Le
    validateur audio la signale ailleurs ; cette jauge se contente de ne pas
    la compter."""
    p = Project(Path("."))
    p.music.append(Music(name="Fantôme", asset="assets/music/introuvable.mod"))
    box = MusicBox(name="m", states=[MusicState(name="s", music="Fantôme")])
    music_ch, _ = worst_case_channels(p, box, None)
    assert music_ch == 0


def test_jingle_prend_le_pire_de_toutes_les_actions_dun_meme_etat(tmp_path):
    """Un état de JingleBox mappe PLUSIEURS actions à des modules différents ;
    une seule joue à la fois au runtime, mais on ne sait pas laquelle à
    l'édition — le pire de l'état est donc le max sur ses actions, pas la
    somme."""
    p = _projet(tmp_path)
    quatre = _ajouter_musique(p, "Quatre", F.make_mod(), ".mod")
    un = _ajouter_musique(p, "Un", F.make_xm(), ".xm")
    jingle = JingleBox(name="j", actions=["a", "b"], states=[
        ActionState(name="s", mapping={"a": un.name, "b": quatre.name}),
    ])
    _music_ch, jingle_ch = worst_case_channels(p, None, jingle)
    assert jingle_ch == 4
