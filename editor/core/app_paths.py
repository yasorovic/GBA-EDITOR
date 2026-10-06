"""
app_paths.py — « où tourne-t-on ? ».

Source de vérité pour les chemins qui changent entre l'exécution
depuis les sources et l'exécution depuis une distribution compilée. Tout
le reste du code importe d'ici plutôt que de refaire le calcul dans son
coin : c'est précisément la duplication de ce calcul qui avait laissé
deux modules de codegen chercher runtime/ hors du bundle.

Ce module ne doit importer que la stdlib — il est chargé très tôt et par
des modules de bas niveau (codegen/c_names.py notamment).
"""

import sys
from pathlib import Path


# Nuitka injecte `__compiled__` dans les globals de chaque module compilé.
# C'est le marqueur documenté, et le seul fiable : `sys.frozen` est posé
# par certains modes seulement. On teste quand même les deux, pour rester
# correct si la distribution change encore de forme.
IS_FROZEN = "__compiled__" in globals() or getattr(sys, "frozen", False)

# Le système d'exploitation, lu ici et nulle part ailleurs : un écran qui
# s'affiche autrement sous Linux, un chemin de config, un drapeau de processus
# importent ces deux constantes plutôt que de tester `sys.platform` dans leur coin.
IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")


def _app_dir() -> Path:
    """
    Dossier qui contient les données embarquées (runtime/, plugins/, …).

    Build Nuitka standalone : l'exe et les dossiers de données sont côte à
    côte dans le dossier de distribution, d'où sys.executable.

    Depuis les sources : la racine du repo, où vit runtime/.
    """
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_DIR = _app_dir()

# runtime/ — sources C du moteur, copiées dans le projet à chaque build ROM.
RUNTIME_DIR = APP_DIR / "runtime"
