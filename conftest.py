# Tout le cache et le temporaire des tests vit dans le dossier .tmp/ du dépôt,
# git-ignoré, et nulle part ailleurs (règle révisée le 2026-11-28, voir
# .claude/CLAUDE.md « Tests et build »). Raison : le bac à sable de Codex ne
# peut écrire que dans le workspace ; %TEMP% et les caches épars hors dépôt lui
# sont refusés. Les redirections restées dans pyproject.toml : cache_dir de
# pytest et cache-dir de ruff.

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(__file__).parent / ".tmp"

# Bytecode : redirigé dès l'import du conftest (donc avant le gros des imports
# de collecte). PYTHONPYCACHEPREFIX dans la commande de test couvre le reste
# (démarrage de l'interpréteur, sous-processus).
_PYCACHE = _TMP / "pycache"
_PYCACHE.mkdir(parents=True, exist_ok=True)
sys.pycache_prefix = str(_PYCACHE)
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(_PYCACHE))


def pytest_configure(config):
    basetemp = _TMP / "pytest-basetemp"
    basetemp.mkdir(parents=True, exist_ok=True)
    tmp_str = str(basetemp)

    # tempfile et les sous-processus (gcc des sondes C) écrivent dans .tmp/.
    for var in ("TMP", "TEMP", "TMPDIR"):
        os.environ[var] = tmp_str
    tempfile.tempdir = tmp_str

    # Fixtures tmp_path / tmp_path_factory de pytest.
    if not config.option.basetemp:
        config.option.basetemp = tmp_str
