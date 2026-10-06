"""Une erreur de gcc dans le C généré cite le SCRIPT, à sa ligne (chantier « La fiabilité du
journal de build », suite de la tranche 2).

Le générateur pose `#line N "Script.lua"` avant chaque statement et rend gcc à son `.c` en fin
de corps de fonction. Le checker est censé attraper les fautes avant gcc ; quand il a un trou, la
faute sortait sur une ligne de `actor_X.c` que personne n'a écrite. Désormais elle sort sur la
ligne du script.
"""
from __future__ import annotations

import pytest

from codegen import BuildWorker
from core.models.components import ScriptComponent
from core.models.scene import Actor
from core.project import Project
from core.toolchain import Toolchain
from scripting.codegen import CodeGen, CodegenContext, generate
from scripting.parser import parse


def _ctx(**kw) -> CodegenContext:
    return CodegenContext(anim_names=[], sfx_names=[], music_names=[], global_names=set(),
                          const_names=set(), all_actor_syms=["A"], actor_name="A",
                          actor_sym="A", scene_sym="S", **kw)


SCRIPT = "function on_update()\n  local a = 1\n  if a == 1 then\n    self.x = 2\n  end\nend\n"


# ── Le C émis ─────────────────────────────────────────────────────


def test_chaque_statement_est_precede_de_sa_ligne_de_script():
    code, _w, _n = generate(parse(SCRIPT), _ctx(lua_file="Hit.lua", c_file="actor_A.c"))
    lines = code.splitlines()
    assert lines[lines.index('#line 2 "Hit.lua"') + 1].strip() == "int a = 1;"
    assert lines[lines.index('#line 4 "Hit.lua"') + 1].strip().startswith("self.x")


def test_gcc_est_rendu_a_son_fichier_a_la_bonne_ligne():
    """Chaque `#line <n> "actor_A.c"` annonce le numéro de la ligne QUI SUIT : si le compte
    était faux, une erreur d'échafaudage citerait la mauvaise ligne."""
    code, _w, _n = generate(parse(SCRIPT), _ctx(lua_file="Hit.lua", c_file="actor_A.c"))
    lines = code.splitlines()
    resets = [i for i, text in enumerate(lines) if text.startswith('#line') and '"actor_A.c"' in text]
    assert resets, "aucune directive de retour au .c"
    for i in resets:
        assert lines[i] == f'#line {i + 2} "actor_A.c"'
    assert "/*@@line-reset@@*/" not in code


def test_sans_nom_de_script_aucune_directive():
    """Les appelants qui ne donnent pas de script (tests unitaires) gardent leur C tel quel."""
    code, _w, _n = generate(parse(SCRIPT), _ctx())
    assert "#line" not in code


# ── Le vrai gcc ───────────────────────────────────────────────────

pytestmark_toolchain = pytest.mark.skipif(
    not Toolchain().devkitpro_ok, reason="devkitPro absent : gcc ne peut pas tourner")


@pytestmark_toolchain
@pytest.mark.slow
def test_une_faute_de_c_sort_sur_la_ligne_du_script(tmp_path, monkeypatch):
    # Le checker laisse passer ce script ; on rend le C émis fautif pour imiter un trou du checker.
    monkeypatch.setattr(CodeGen, "_call_expr", lambda self, call: "bogus_undeclared_var")

    project = Project.create(tmp_path / "Game", "Game")
    project.scripts_dir.mkdir(parents=True, exist_ok=True)
    (project.scripts_dir / "Hit.lua").write_text(
        'function on_update()\n  local a = 1\n  debug:log("x")\nend\n', encoding="utf-8")
    actor = Actor(name="A")
    actor.components = [ScriptComponent(script="assets/scripts/Hit.lua")]
    project.scenes[0].actors.append(actor)
    project.save()

    worker = BuildWorker(Project.open(project.root), Toolchain())
    worker._step_launch_mgba = lambda _p: True
    diagnostics, verdict = [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", verdict.append)
    worker.run()

    assert verdict == [False]
    [hit] = [d for d in diagnostics if "bogus_undeclared_var" in d.message]
    assert (hit.level, hit.file, hit.line) == ("error", "Hit.lua", 3)
