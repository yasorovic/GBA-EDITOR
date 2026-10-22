"""Compile un dialogue multi-page avec accès Lua par une colonne text."""
import pytest
import os
import subprocess

from codegen import BuildWorker
from core.project import Project
from core.text_table_link import create_linked_table
from core.models.ui_region import UILayout, UITextbox, InterfaceNode
from core.models.settings import Language
from core.toolchain import Toolchain, DEVKITPRO_OK


@pytest.mark.slow
def test_textbox_pages_compile_into_one_region(tmp_path, monkeypatch):
    import core.toolchain as toolchain_module
    import core.project_starters as starters
    # Test autonome : aucune lecture/écriture des préférences utilisateur.
    monkeypatch.setattr(toolchain_module, "CONFIG_FILE", tmp_path / "toolchain.json")
    monkeypatch.setattr(toolchain_module, "_LEGACY_CONFIG_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(starters, "USER_STARTERS_DIR", tmp_path / "starters")
    toolchain = Toolchain()
    if toolchain.devkitpro_state != DEVKITPRO_OK:
        pytest.skip("devkitPro unavailable")
    p = Project.create(tmp_path / "Pages", "Pages")
    for folder in ((p.user_library_dir / "scripts"),):
        folder.mkdir(parents=True, exist_ok=True)
    scene = p.active_scene
    p.settings.default_font = "Font8x8 Latin"
    scene.font_name = "Font8x8 Latin"
    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="fr", name="French")]
    p.load_translations()
    box = UITextbox(name="Dialogue", x=8, y=8, w=160, h=32)
    layout = UILayout(name="DialogueHUD", elements=[box])
    p.ui_layouts.append(layout)
    scene.ui_layouts = [InterfaceNode(layout_name=layout.name, bg_slot=1)]
    first = p.new_text(content="FIRST PAGE", path=[scene.name, "Dialogue", "Page01"])
    second = p.new_text(content="[wave]ZEBRA[/wave]", path=[scene.name, "Dialogue", "Page02"])
    p.translations["fr"][second.id] = "[wave]ZEBRE[/wave]"
    prefix = f"{scene.name}_Dialogue"
    box.sequence_prefix = prefix
    create_linked_table(p, prefix).execute()
    table = p.data_tables[-1]
    p.rename_data_table(table, "Lines")
    p.rename_data_column(table, table.columns[0], "line")
    script = (p.user_library_dir / "scripts") / "Pages.lua"
    script.write_text('function on_update()\n'
        '    if scene.frame == 1 then\n'
        '        debug:log("TEXTBOX_INITIAL_READY")\n'
        '    end\n'
        '    if scene.frame == 30 then\n'
        '        interface:get("Dialogue"):draw(data.Lines[2].line)\n'
        '        debug:log("TEXTBOX_SECOND_PAGE_DRAWN")\n'
        '    end\nend\n', encoding="utf-8")
    scene.script = p.asset_rel(script)
    p.save()
    p.save_translation("fr")
    worker = BuildWorker(p, toolchain)
    worker._step_launch_mgba = lambda _p: True
    diagnostics, results, output = [], [], []
    worker.on("diagnostic", diagnostics.append)
    worker.on("finished", results.append)
    worker.on("error_line", output.append)
    worker.run()
    errors = [d.message for d in diagnostics if d.level == "error"]
    assert results == [True], "\n".join(errors + output[-30:])
    assert not errors
    assert p.rom_path.stat().st_size > 1024
    # Le frontend SDL permet de vérifier le script sans fenêtre ni socket de
    # débogage. Facultatif : le build reste vérifié sans émulateur installé.
    emulator = toolchain.resolve_mgba()
    sdl = emulator.with_name("mgba-sdl.exe") if emulator and os.name == "nt" else None
    if sdl is not None and sdl.is_file():
        config = tmp_path / "emulator-config"
        config.mkdir()
        env = dict(os.environ, APPDATA=str(config), LOCALAPPDATA=str(config),
                   SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
                   SDL_RENDER_DRIVER="software")
        log_path = p.build_dir / "emulator-test.log"
        with log_path.open("w") as log:
            process = subprocess.Popen([str(sdl), "-l", "8", str(p.rom_path)],
                env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        report = log_path.read_text(errors="replace")
        assert "TEXTBOX_INITIAL_READY" in report, report[:3000]
        assert "TEXTBOX_SECOND_PAGE_DRAWN" in report, report[:3000]
