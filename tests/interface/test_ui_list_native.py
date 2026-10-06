"""La NAVIGATION d'une liste, exécutée par le vrai moteur C.

`ui_list_step` / `ui_list_reveal` sont de l'arithmétique entière sans sortie
visible avant qu'une ROM tourne sur une console : exactement le genre de module
que ce dépôt fait vérifier en C plutôt qu'à la relecture (cf. la sonde
d'équivalence de `text_layout`). Ce qui est tenu ici :

- le pas simple et le rebouclage, avec et sans `wrap` ;
- **la garde du pas transverse** — une liste à une colonne ne doit PAS répondre
  à gauche/droite, sous peine de confisquer au jeu l'autre axe de la croix ;
- le pas en grille, dans les deux sens de lecture (Z et W) ;
- le défilement **à la ligne** : dans une grille, la fenêtre avance de
  `nav_columns` items, sans quoi les colonnes glisseraient d'un cran à chaque
  pas et la grille dessinée ne serait plus celle que l'auteur a posée ;
- `active`, qui coupe la sélection sans rien effacer.

La FORME de la liste est posée à la compilation (cf. l'en-tête de la sonde :
gcc replie la lecture d'un objet `const` sur son initialiseur, même à `-O0`).
Une sonde est donc compilée par forme, et mise en cache pour la session.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Les mêmes helpers que la sonde de mise en page : un seul endroit sait trouver
# un compilateur hôte et lui donner son PATH. Les dupliquer ferait diverger le
# jour où l'un des deux apprend un compilateur de plus.
from native_toolchain import compilateur_hote, environnement

NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
SONDE_C    = NATIVE_DIR / "ui_list_probe.c"
SHIM_DIR   = NATIVE_DIR / "libgba_shim"
MOTEUR_DIR = Path(__file__).resolve().parents[2] / "runtime" / "include"

# Ce que la sonde lit sur son entrée, en clair.
HAUT, BAS, GAUCHE, DROITE = 1, 2, 3, 4
RELACHE, RENDRE_LA_MAIN, REPRENDRE = 0, 5, 6


@pytest.fixture(scope="session")
def sonde(tmp_path_factory):
    """Rend `compile(rows, columns, major, wrap) -> (binaire, env)`, une
    compilation par forme, gardée pour la session."""
    compilateur = compilateur_hote()
    if compilateur is None:
        import os
        message = ("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) — "
                   "la navigation de liste n'est PAS vérifiée")
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; elle l'est en CI")

    env = environnement(compilateur)
    dossier = tmp_path_factory.mktemp("ui_list_native")
    cache: dict[tuple, Path] = {}

    def compiler(rows: int, columns: int = 1, major: int = 0, wrap: int = 1):
        cle = (rows, columns, major, wrap)
        if cle not in cache:
            binaire = dossier / ("probe_%d_%d_%d_%d" % cle)
            resultat = subprocess.run(
                [compilateur, "-std=c11", "-O0", "-Wall",
                 f"-DPROBE_ROWS={rows}", f"-DPROBE_COLUMNS={columns}",
                 f"-DPROBE_MAJOR={major}", f"-DPROBE_WRAP={wrap}",
                 "-o", str(binaire), str(SONDE_C),
                 "-I", str(SHIM_DIR), "-I", str(MOTEUR_DIR)],
                capture_output=True, text=True, env=env)
            if resultat.returncode != 0:
                pytest.fail(f"la sonde ne compile plus contre gba_engine.h "
                            f"(code {resultat.returncode}) :\n{resultat.stderr}")
            cache[cle] = binaire
        return cache[cle], env

    return compiler


def _parcourir(sonde, touches: list[int], *, total: int, rows: int,
               columns: int = 1, major: int = 0, wrap: int = 1):
    """Joue `touches` (une par frame) et rend [(index, premier visible)].

    Un appui suivi d'un relâchement = UN pas : la cadence de répétition de la
    sonde est neutre, mais une touche TENUE répète, ce qui est justement le
    comportement qu'on ne veut pas mesurer ici."""
    binaire, env = sonde(rows, columns, major, wrap)
    frames: list[int] = []
    for t in touches:
        frames += [t, RELACHE]
    entree = f"{total} {len(frames)} " + " ".join(str(t) for t in frames)
    resultat = subprocess.run([str(binaire)], input=entree,
                              capture_output=True, text=True, env=env)
    assert resultat.returncode == 0, f"la sonde a échoué : {resultat.stderr}"
    mots = resultat.stdout.split()
    assert mots[0] == "STEP"
    n = int(mots[1])
    paires = [(int(mots[2 + 2 * k]), int(mots[3 + 2 * k])) for k in range(n)]
    # Une frame sur deux est le relâchement : elle ne bouge rien, on la jette.
    return paires[::2]


# ── Le pas simple ─────────────────────────────────────────────────

def test_une_liste_verticale_descend_puis_reboucle(sonde):
    pas = _parcourir(sonde, [BAS] * 4, total=4, rows=4)
    assert [i for i, _f in pas] == [2, 3, 4, 1]


def test_sans_rebouclage_le_curseur_bute_sur_la_fin(sonde):
    pas = _parcourir(sonde, [BAS] * 4, total=4, rows=4, wrap=0)
    assert [i for i, _f in pas] == [2, 3, 4, 4]


def test_remonter_depuis_le_premier_va_au_dernier(sonde):
    pas = _parcourir(sonde, [HAUT], total=4, rows=4)
    assert [i for i, _f in pas] == [4]


# ── La garde du pas transverse ────────────────────────────────────

def test_une_liste_a_une_colonne_ignore_gauche_droite(sonde):
    """Sans cette garde, le pas transverse vaut ±1 quand il n'y a qu'une
    colonne : la croix ENTIÈRE piloterait un menu qui n'a qu'un axe, et le jeu
    ne pourrait plus se servir de l'autre (changer une valeur, tourner une
    page)."""
    pas = _parcourir(sonde, [DROITE, GAUCHE, DROITE], total=4, rows=4)
    assert [i for i, _f in pas] == [1, 1, 1]


def test_une_grille_dune_seule_ligne_ignore_l_autre_axe(sonde):
    """Une rangée d'onglets : trois items sur trois colonnes. Haut/bas n'a nulle
    part où aller, et un pas de ±3 sur trois items ferait un tour complet — un
    mouvement invisible mais bien réel, qui rendrait la répétition erratique."""
    pas = _parcourir(sonde, [DROITE, BAS, HAUT], total=3, rows=3,
                     columns=3, major=1)
    assert [i for i, _f in pas] == [2, 2, 2]


# ── La grille ─────────────────────────────────────────────────────

def test_en_z_droite_avance_dun_et_bas_dune_ligne(sonde):
    """Parcours en Z : les index suivent la RANGÉE (gauche→droite), donc bas
    saute d'une ligne entière — `nav_columns` items."""
    pas = _parcourir(sonde, [DROITE, BAS, GAUCHE, HAUT], total=6, rows=6,
                     columns=2, major=1)
    assert [i for i, _f in pas] == [2, 4, 3, 1]


def test_en_w_bas_avance_dun_et_droite_dune_colonne(sonde):
    """Parcours en W : les index descendent la COLONNE, donc c'est droite qui
    saute de `nav_columns`. Le symétrique exact du cas précédent."""
    pas = _parcourir(sonde, [BAS, DROITE, HAUT, GAUCHE], total=6, rows=6,
                     columns=2, major=0)
    assert [i for i, _f in pas] == [2, 4, 3, 1]


def test_le_pas_transverse_reboucle_sur_la_suite_plate(sonde):
    """Six items, deux colonnes, pas de bord magique : monter depuis la première
    ligne repart de la fin. Le rebouclage porte sur l'index PLAT — les items
    sont une suite, la grille n'est que la façon dont elle est posée."""
    pas = _parcourir(sonde, [HAUT], total=6, rows=6, columns=2, major=1)
    assert [i for i, _f in pas] == [5]


# ── Le défilement ─────────────────────────────────────────────────

def test_la_fenetre_suit_le_curseur_ligne_par_ligne(sonde):
    """Deux rangées visibles, cinq items : la fenêtre ne bouge qu'une fois le
    curseur sorti par le bas."""
    pas = _parcourir(sonde, [BAS] * 4, total=5, rows=2)
    assert pas == [(2, 1), (3, 2), (4, 3), (5, 4)]


def test_dans_une_grille_la_fenetre_avance_dune_LIGNE(sonde):
    """Quatre cases sur deux colonnes = deux lignes visibles, huit items. La
    fenêtre s'aligne sur les lignes (1, 3, 5…) : avancer d'un ITEM décalerait
    les colonnes d'un cran à chaque pas, et la grille affichée ne serait plus
    celle qui a été dessinée."""
    pas = _parcourir(sonde, [BAS, BAS, BAS], total=8, rows=4,
                     columns=2, major=1)
    assert pas == [(3, 1), (5, 3), (7, 5)]


def test_remonter_ramene_la_fenetre(sonde):
    pas = _parcourir(sonde, [BAS, BAS, BAS, HAUT, HAUT], total=5, rows=2)
    assert pas[-2:] == [(3, 3), (2, 2)]


# ── La main ───────────────────────────────────────────────────────

def test_une_liste_inactive_ne_bouge_plus_et_garde_son_index(sonde):
    """`active` coupe la SÉLECTION, pas l'affichage : l'index survit à la
    parenthèse, et la liste repart d'où elle était. C'est ce qui permet un menu
    et son sous-menu à l'écran en même temps."""
    pas = _parcourir(sonde, [BAS, RENDRE_LA_MAIN, BAS, BAS, REPRENDRE, BAS],
                     total=5, rows=5)
    assert [i for i, _f in pas] == [2, 2, 2, 2, 2, 3]
