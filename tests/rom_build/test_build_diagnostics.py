"""Un diagnostic, un journal conservé (chantier « La fiabilité du journal de build », tranche 2).

Ce que le build dit passe par UN objet (`ValidationMessage`), émis par l'événement
`diagnostic` : sa gravité, son fichier et sa ligne sont des champs, pas des morceaux de texte.
Le verdict se chiffre, `build.log` garde ce que le panneau a montré, et la sortie des outils
est rangée par ce qu'elle DIT (gcc écrit ses avertissements sur stderr).
"""
from __future__ import annotations

import sys

import pytest

from codegen import BuildWorker
from core.models.components import ScriptComponent
from core.models.scene import Actor
from core.project import Project
from core.toolchain import DEVKITPRO_OK, Toolchain
from core.validator import ValidationMessage, build_error, build_warning


# ── L'objet ───────────────────────────────────────────────────────


def test_la_ligne_de_console_vient_des_champs():
    erreur = ValidationMessage("error", "", "unexpected `x`", source="script",
                               file="Hit.lua", line=3)
    assert erreur.console_line() == "[error] Hit.lua:3: unexpected `x`"
    # Sans ligne : le fichier seul ; avec un propriétaire : il suit l'emplacement.
    prefab = build_warning("unused", "codegen", "Bullet.lua", actor="prefab Bullet")
    assert prefab.console_line() == "[warn]  Bullet.lua: [prefab Bullet] unused"


def test_une_etape_se_nomme_mais_pas_le_validateur():
    assert build_error("not found", "make").console_line() == "[error] make: not found"
    assert ValidationMessage("warning", "Hero", "sprite manquant").console_line() == \
        "[warn]  [Hero] sprite manquant"


# ── La sortie des outils, rangée par contenu ──────────────────────


def _worker():
    worker = BuildWorker(None, None)
    seen = {"diagnostic": [], "log_line": [], "error_line": []}
    for event, bucket in seen.items():
        worker.on(event, bucket.append)
    return worker, seen


def test_un_avertissement_de_gcc_n_est_pas_rouge():
    worker, seen = _worker()
    worker._emit_tool_line("C:\\proj\\src\\actor_A.c:12:5: warning: unused variable 'x'", "make", False)
    [d] = seen["diagnostic"]
    assert (d.level, d.file, d.line, d.source) == ("warning", "actor_A.c", 12, "make")
    assert seen["error_line"] == []


def test_une_erreur_de_gcc_est_une_erreur_avec_son_fichier():
    worker, seen = _worker()
    worker._emit_tool_line("src/actor_A.c:3:1: error: expected ';' before '}' token", "make", True)
    [d] = seen["diagnostic"]
    assert (d.level, d.file, d.line) == ("error", "actor_A.c", 3)


def test_l_editeur_de_liens_et_les_notes():
    worker, seen = _worker()
    worker._emit_tool_line("main.o: undefined reference to `foo'", "make", True)
    worker._emit_tool_line("src/a.c:3:1: note: declared here", "make", True)
    assert [d.level for d in seen["diagnostic"]] == ["error"]
    assert seen["log_line"] == ["  src/a.c:3:1: note: declared here"]


def test_le_reste_est_rouge_seulement_si_l_outil_a_echoue():
    worker, seen = _worker()
    worker._emit_tool_line("make: *** [rom] Error 1", "make", True)
    worker._emit_tool_line("grit 0.9 starting", "grit", False)
    assert seen["error_line"] == ["  make: *** [rom] Error 1"]
    assert seen["log_line"] == ["  grit 0.9 starting"]


def test_un_outil_qui_reussit_avec_un_avertissement_n_echoue_pas():
    worker, seen = _worker()
    script = "import sys; sys.stderr.write('a.c:7:1: warning: careful' + chr(10))"
    assert worker._run_cmd([sys.executable, "-c", script], "[gcc]") is True
    [d] = seen["diagnostic"]
    assert (d.level, d.file, d.line) == ("warning", "a.c", 7)
    assert seen["error_line"] == []


def test_un_outil_en_echec_compte_comme_une_erreur():
    worker, seen = _worker()
    assert worker._run_cmd([sys.executable, "-c", "import sys; sys.exit(3)"], "[gcc]") is False
    assert [d.console_line() for d in seen["diagnostic"]] == ["[error] gcc: failed (code 3)"]


# ── Le verdict et build.log ───────────────────────────────────────

# Ces trois tests lancent le vrai build : sans grit (devkitPro), il échoue pour une autre raison.
needs_devkitpro = pytest.mark.skipif(
    Toolchain().devkitpro_state != DEVKITPRO_OK,
    reason=f"devkitPro non prêt ({Toolchain().devkitpro_state}) : le build ne peut pas tourner")


def _projet(tmp_path, script):
    project = Project.create(tmp_path / "Game", "Game")
    for folder in ((project.user_library_dir / "sprites"), (project.user_library_dir / "backgrounds"), (project.user_library_dir / "sfx"), (project.user_library_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    (project.user_library_dir / "scripts").mkdir(parents=True, exist_ok=True)
    ((project.user_library_dir / "scripts") / "Hit.lua").write_text(script, encoding="utf-8")
    actor = Actor(name="A")
    actor.components = [ScriptComponent(script="assets/scripts/Hit.lua")]
    project.scenes[0].actors.append(actor)
    project.save()
    return project


def _build(project):
    worker = BuildWorker(Project.open(project.root), Toolchain())
    worker._step_make = lambda _p: True
    worker._step_launch_mgba = lambda _p: True
    lines, verdict = [], []
    for event in ("log_line", "error_line"):
        worker.on(event, lines.append)
    worker.on("diagnostic", lambda d: lines.append(d.console_line()))
    worker.on("finished", verdict.append)
    worker.run()
    return verdict[-1], lines


@needs_devkitpro
@pytest.mark.slow
def test_le_verdict_chiffre_les_erreurs(tmp_path):
    # Un refus du checker, avec sa ligne : le checker est une source comme une autre.
    ok, lines = _build(_projet(tmp_path, "function on_update()\n  local f = function() return 1 end\nend\n"))
    assert ok is False
    assert any(line.startswith("[error] Hit.lua:2: ") for line in lines), lines
    assert "[build] 1 error(s), 0 warning(s)" in lines


@needs_devkitpro
@pytest.mark.slow
def test_un_projet_sain_chiffre_zero_erreur(tmp_path):
    ok, lines = _build(_projet(tmp_path, "function on_update()\nend\n"))
    assert ok is True
    assert "[build] 0 error(s), 0 warning(s)" in lines


@needs_devkitpro
@pytest.mark.slow
def test_build_log_copie_le_journal_et_se_reecrit(tmp_path):
    project = _projet(tmp_path, "function on_update()\n  local f = function() return 1 end\nend\n")
    _build(project)
    log = (project.root / "build" / "build.log").read_text(encoding="utf-8")
    assert log.splitlines()[0].endswith("build log")
    assert "project: Game" in log and "tools: " in log
    assert "[error] Hit.lua:2: " in log
    assert "[build] 1 error(s), 0 warning(s)" in log

    # Le build suivant le réécrit : rien de l'ancien ne reste.
    ((project.user_library_dir / "scripts") / "Hit.lua").write_text("function on_update()\nend\n", encoding="utf-8")
    _build(project)
    log = (project.root / "build" / "build.log").read_text(encoding="utf-8")
    assert "[error] Hit.lua" not in log
    assert "[build] 0 error(s), 0 warning(s)" in log


# ── Le démarrage de make qui échoue sans raison ─────────────────────

def _counting_tool(counter, fail_times, message):
    """Un « outil » qui échoue `fail_times` fois en écrivant `message`, puis réussit ; `counter` compte les lancements."""
    return [sys.executable, "-c",
            "import sys, pathlib\n"
            f"c = pathlib.Path({str(counter)!r})\n"
            "n = int(c.read_text()) + 1 if c.exists() else 1\n"
            "c.write_text(str(n))\n"
            f"if n <= {fail_times}:\n"
            f"    sys.stderr.write({message!r} + chr(10)); sys.exit(1)\n"]


def test_un_demarrage_de_msys2_qui_echoue_est_relance_puis_passe(tmp_path, monkeypatch):
    monkeypatch.setattr("codegen.rom_build.time.sleep", lambda _s: None)
    worker, seen = _worker()
    counter = tmp_path / "runs"

    assert worker._run_cmd(_counting_tool(counter, 2, "fatal error - add_item failed"), "[make]") is True

    assert counter.read_text() == "3"                                              # deux échecs, puis le bon
    assert seen["diagnostic"] == []                                                 # l'auteur n'a rien à lire
    assert sum("retrying" in line for line in seen["log_line"]) == 2                # mais le journal le dit


def test_un_demarrage_qui_echoue_toujours_est_une_erreur_apres_trois_essais(tmp_path, monkeypatch):
    monkeypatch.setattr("codegen.rom_build.time.sleep", lambda _s: None)
    worker, seen = _worker()
    counter = tmp_path / "runs"

    assert worker._run_cmd(_counting_tool(counter, 99, "fatal error - add_item failed"), "[make]") is False

    assert counter.read_text() == "3"                                              # un essai + deux relances, pas une boucle
    assert [d.console_line() for d in seen["diagnostic"]] == ["[error] make: failed (code 1)"]


def test_une_vraie_erreur_n_est_jamais_relancee(tmp_path, monkeypatch):
    monkeypatch.setattr("codegen.rom_build.time.sleep", lambda _s: None)
    worker, seen = _worker()
    counter = tmp_path / "runs"

    assert worker._run_cmd(_counting_tool(counter, 99, "a.c:3:1: error: expected ';'"), "[make]") is False

    assert counter.read_text() == "1"
