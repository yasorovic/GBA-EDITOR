"""Les scripts Lua s'écrivent par fichier temporaire puis rename : une écriture interrompue laisse l'ancien contenu."""
from pathlib import Path

import pytest

from scripting.refactor import rename_in_files
from scripting.script_notes import write_note


class SimulatedCrash(Exception):
    pass


@pytest.fixture
def crash_on_temporary(monkeypatch):
    real = Path.write_text

    def write_text(self, *args, **kwargs):
        if self.suffix == ".tmp":
            raise SimulatedCrash
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text)


def test_un_renommage_interrompu_laisse_le_script_intact(tmp_path, crash_on_temporary):
    script = tmp_path / "a.lua"
    script.write_bytes(b'scene.switch("Arena")\n')

    with pytest.raises(SimulatedCrash):
        rename_in_files([script], "scene", "Arena", "Pong")

    assert script.read_bytes() == b'scene.switch("Arena")\n'


def test_une_note_interrompue_laisse_le_script_intact(tmp_path, crash_on_temporary):
    script = tmp_path / "a.lua"
    script.write_bytes(b"local x = 1\n")

    with pytest.raises(SimulatedCrash):
        write_note(script, "hello")

    assert script.read_bytes() == b"local x = 1\n"
