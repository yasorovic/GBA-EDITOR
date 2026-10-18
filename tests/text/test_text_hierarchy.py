from core.models.text import Text, key_from_path


def test_each_underscore_is_one_level_and_the_path_is_derived_from_the_key():
    text = Text.from_dict({"key": "scr_arena_score_cpu", "path": ["Libellé", "ignoré"]})

    assert text.path == ["scr", "arena", "score", "cpu"]
    assert "path" not in text.to_dict()


def test_a_legacy_entry_without_key_gets_one_from_its_old_path():
    text = Text.from_dict({"path": ["SCR", "La forêt", "Entrée"]})

    assert text.key == key_from_path(["SCR", "La forêt", "Entrée"]) == "SCR_LaForet_Entree"
    assert text.path == ["SCR", "LaForet", "Entree"]


def test_filing_a_text_renames_its_key(tmp_path):
    from core.project import Project
    from ui.text_editor.text_commands import SetTextPathCmd

    project = Project(tmp_path / "game")
    text = project.new_text(path=["SCR", "La forêt"])
    assert text.key == "SCR_LaForet"

    command = SetTextPathCmd(project, [(text, text.path, ["Écran", "Forêt sombre"])], "move")
    command.execute()
    assert text.key == "Ecran_ForetSombre" and text.path == ["Ecran", "ForetSombre"]

    command.undo()
    assert text.key == "SCR_LaForet"
