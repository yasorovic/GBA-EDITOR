"""Les trois états de devkitPro : complet, incomplet (dossier trouvé, paquets absents),
introuvable. L'état « incomplet » est celui d'un devkitPro dont les paquets GBA n'ont
pas été téléchargés : il demande de vérifier l'installation, pas de chercher le dossier."""
from __future__ import annotations

import pytest

from core import toolchain as tc


def _toolchain(monkeypatch, tmp_path, found, folder=True):
    monkeypatch.setattr(tc, "_WIN_DEFAULTS", [])
    monkeypatch.setattr(tc, "_UNIX_DEFAULTS", [])
    monkeypatch.setattr(tc.Toolchain, "_load_config", lambda self: {})
    monkeypatch.setattr(tc.shutil, "which", lambda name: None)
    t = tc.Toolchain()
    if folder:
        t._config["devkitpro"] = str(tmp_path)
    for name, method in (("grit", "resolve_grit"), ("make", "resolve_make"),
                         ("arm-none-eabi-gcc", "resolve_arm_gcc")):
        monkeypatch.setattr(t, method, (lambda n=name: tmp_path / n if n in found else None))
    monkeypatch.setattr(t, "resolve_mgba", lambda: None)
    return t


def test_complet(monkeypatch, tmp_path):
    t = _toolchain(monkeypatch, tmp_path, {"grit", "make", "arm-none-eabi-gcc"})
    assert t.devkitpro_state == tc.DEVKITPRO_OK and t.devkitpro_ok


def test_dossier_trouve_mais_paquets_absents_est_incomplet(monkeypatch, tmp_path):
    t = _toolchain(monkeypatch, tmp_path, {"make"})        # le cas d'un devkitPro à moitié installé
    assert t.devkitpro_state == tc.DEVKITPRO_INCOMPLETE
    assert t.devkitpro_missing_tools() == ["grit", "arm-none-eabi-gcc"]
    assert not t.devkitpro_ok


def test_dossier_present_sans_aucun_outil_est_incomplet(monkeypatch, tmp_path):
    t = _toolchain(monkeypatch, tmp_path, set())
    assert t.devkitpro_state == tc.DEVKITPRO_INCOMPLETE


def test_make_systeme_seul_ne_fait_pas_un_devkitpro_incomplet(monkeypatch, tmp_path):
    """Un Linux a `make` sans devkitPro : sans dossier ni outil propre, c'est « introuvable »."""
    t = _toolchain(monkeypatch, tmp_path, {"make"}, folder=False)
    assert t.devkitpro_state == tc.DEVKITPRO_MISSING


def test_un_outil_propre_a_devkitpro_sans_dossier_est_incomplet(monkeypatch, tmp_path):
    t = _toolchain(monkeypatch, tmp_path, {"grit"}, folder=False)
    assert t.devkitpro_state == tc.DEVKITPRO_INCOMPLETE


def test_ni_dossier_ni_outil_est_introuvable(monkeypatch, tmp_path):
    t = _toolchain(monkeypatch, tmp_path, set(), folder=False)
    assert t.devkitpro_state == tc.DEVKITPRO_MISSING


class _FakeProcess:
    def __init__(self, code, lines):
        self._code, self.stdout = code, iter(lines)

    def wait(self):
        return self._code


def _with_msys2(monkeypatch, tmp_path, codes):
    """Un MSYS2 factice sous tmp_path, et un `Popen` qui rend ces codes de sortie, un par essai."""
    found = {"make"}
    t = _toolchain(monkeypatch, tmp_path, found)
    bash = tmp_path / "msys2" / "usr" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.write_text("")
    (bash.parent / "pacman.exe").write_text("")
    launched = []
    results = iter(codes)

    def fake_popen(cmd, **kwargs):
        launched.append(cmd)
        code = next(results)
        if code == 0:
            found.update({"grit", "arm-none-eabi-gcc"})     # pacman a posé les outils
        return _FakeProcess(code, ["installing grit\n", "\n"])

    monkeypatch.setattr(tc.subprocess, "Popen", fake_popen)
    return t, launched


def test_installation_des_paquets_gba_reessaie_puis_s_arrete_au_succes(monkeypatch, tmp_path):
    t, launched = _with_msys2(monkeypatch, tmp_path, [1, 0])
    lines = []
    assert t.install_gba_packages(lines.append) is True
    assert len(launched) == 2
    assert launched[0][1:] == ["-lc", tc.GBA_PACKAGES_COMMAND]
    assert lines == ["installing grit", "Attempt 2 of 3", "installing grit"]   # lignes vides ignorées


def test_installation_des_paquets_gba_abandonne_apres_les_essais(monkeypatch, tmp_path):
    t, launched = _with_msys2(monkeypatch, tmp_path, [1, 1, 1])
    assert t.install_gba_packages(lambda line: None) is False
    assert len(launched) == 3


def test_installation_des_paquets_gba_sans_msys2_ne_lance_rien(monkeypatch, tmp_path):
    t = _toolchain(monkeypatch, tmp_path, {"make"})
    monkeypatch.setattr(tc.subprocess, "Popen", lambda *a, **k: pytest.fail("pas de processus attendu"))
    assert t.msys2_bash() is None
    assert t.install_gba_packages(lambda line: None) is False


def test_msys2_reduit_de_backstage_sans_pacman_n_offre_pas_l_installation_des_paquets(monkeypatch, tmp_path):
    """La chaîne posée par l'installateur de Backstage a bash et make, pas pacman : le bouton
    « Installer les paquets GBA » n'y réparerait rien."""
    t = _toolchain(monkeypatch, tmp_path, {"make"})
    bash = tmp_path / "msys2" / "usr" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.write_text("")
    assert t.msys2_bash() is None
    assert t.install_gba_packages(lambda line: None) is False
