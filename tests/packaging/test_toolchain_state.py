"""Les trois états de devkitPro : complet, incomplet (dossier trouvé, paquets absents),
introuvable. L'état « incomplet » est celui d'un devkitPro dont les paquets GBA n'ont
pas été téléchargés : il demande de vérifier l'installation, pas de chercher le dossier."""
from __future__ import annotations

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
