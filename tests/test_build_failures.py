"""Un build qui échoue le dit en clair : jamais une trace Python brute, toujours
l'étape en cause, et le détail dans le journal.

Pas de devkitPro ici : les pannes sont provoquées sur des projets minimaux ou des
doublures. Le build de bout en bout avec pannes réelles (compilation C en erreur,
PNG corrompu, ROM verrouillée) est rejoué à la main — cf. ALPHA_CHECKLIST.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from codegen.rom_build import BuildWorker
from core import crash_log
from core.models.components import SpriteComponent
from core.models.scene import Actor, BackgroundLayer
from core.project import Project
from core.validator import validate_project

windows_only = pytest.mark.skipif(os.name != "nt", reason="verrou exclusif Windows")


def _projet(tmp_path) -> Project:
    root = tmp_path / "Jeu"
    p = Project.create(root, "Jeu")
    Image.new("RGB", (16, 16), (200, 30, 30)).save(p.sprites_dir / "hero.png")
    Image.new("RGB", (32, 32), (30, 30, 200)).save(p.backgrounds_dir / "sky.png")
    p = Project.open(root)
    p.load_all_resources()
    hero = Actor(name="Hero")
    hero.components.append(SpriteComponent(sprite_name="hero"))
    p.scenes[0].actors.append(hero)
    p.scenes[0].background_layers.append(BackgroundLayer(background_name="sky", bg_slot=0))
    p.save()
    return Project.open(root)


def _erreurs(project) -> list[str]:
    return [str(m) for m in validate_project(project)[1]]


# ── Images illisibles : refusées AVANT le build ───────────────────────

def test_projet_sain_n_a_pas_d_erreur_d_image(tmp_path):
    assert not any("illisible" in e for e in _erreurs(_projet(tmp_path)))


def test_png_de_sprite_corrompu_est_refuse_en_validation(tmp_path):
    p = _projet(tmp_path)
    (p.sprites_dir / "hero.png").write_bytes(b"ceci n'est pas un PNG" * 20)

    errors = _erreurs(p)

    assert any("hero.png" in e and "unreadable" in e for e in errors)
    assert not any(str(tmp_path) in e for e in errors)        # pas de chemin complet recopié


def test_png_de_fond_corrompu_est_refuse_en_validation(tmp_path):
    p = _projet(tmp_path)
    (p.backgrounds_dir / "sky.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"tronque")

    assert any("sky.png" in e and "unreadable" in e for e in _erreurs(p))


# ── Panne imprévue : message lisible, trace dans le journal ───────────

class _ProjetQuiPlante:
    root = Path("projet-qui-plante")

    @property
    def scenes(self):
        raise RuntimeError("boom interne")


def test_une_panne_imprevue_ne_montre_pas_de_trace_python(tmp_path, monkeypatch):
    journal = tmp_path / "crash.log"
    monkeypatch.setattr(crash_log, "LOG_FILE", journal)
    projet = _ProjetQuiPlante()
    projet.build_dir = tmp_path / "build"
    projet.settings = SimpleNamespace(name="projet-qui-plante")
    worker = BuildWorker(projet, None)
    lines, finished = [], []
    worker.on("error_line", lines.append)
    worker.on("diagnostic", lambda d: lines.append(d.console_line()))
    worker.on("log_line", lines.append)
    worker.on("finished", finished.append)

    worker.run()

    assert finished == [False]
    texte = "\n".join(lines)
    assert "Traceback" not in texte
    assert "internal error" in texte and "boom interne" in texte
    assert str(journal) in texte                                # dit où est le détail
    assert "RuntimeError" in journal.read_text(encoding="utf-8")   # …et il y est


# ── Un outil qui échoue : l'étape et le code ──────────────────────────

def test_un_outil_en_echec_dit_quelle_etape_et_quel_code():
    worker = BuildWorker(None, None)
    lines = []
    worker.on("error_line", lines.append)
    worker.on("diagnostic", lambda d: lines.append(d.console_line()))
    worker.on("log_line", lines.append)

    ok = worker._run_cmd([sys.executable, "-c", "import sys; sys.exit(3)"], "[outil]")

    assert ok is False
    assert "[error] outil: failed (code 3)" in lines


def test_un_outil_qui_reussit_n_ajoute_pas_de_ligne_d_echec():
    worker = BuildWorker(None, None)
    lines = []
    worker.on("error_line", lines.append)
    worker.on("diagnostic", lambda d: lines.append(d.console_line()))

    assert worker._run_cmd([sys.executable, "-c", "pass"], "[outil]") is True
    assert not any("a échoué" in line for line in lines)


# ── ROM verrouillée : dite avant de compiler pour rien ────────────────

@windows_only
def test_rom_verrouillee_par_un_autre_programme_est_dite_clairement(tmp_path):
    rom = tmp_path / "rom.gba"
    rom.write_bytes(b"\x00" * 16)
    projet = SimpleNamespace(rom_path=rom, makefile_path=tmp_path / "Makefile")
    worker = BuildWorker(None, SimpleNamespace(resolve_make=lambda: Path("make")))
    errors = []
    worker.on("error_line", errors.append)
    worker.on("diagnostic", lambda d: errors.append(d.console_line()))

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = ctypes.c_void_p
    # GENERIC_READ, partage 0 : verrou exclusif, comme un émulateur qui a la ROM ouverte.
    handle = kernel32.CreateFileW(str(rom), 0x80000000, 0, None, 3, 0, None)
    try:
        assert worker._step_make(projet) is False
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))

    assert any("rom.gba" in e and "locked" in e for e in errors)
