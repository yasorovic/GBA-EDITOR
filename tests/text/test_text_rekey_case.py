from core.models.text import Text, key_from_path


def test_a_key_rebuilt_from_its_own_path_is_unchanged():
    labels = Text(key="scr_arena_score").path

    assert labels == ["scr", "arena", "score"]
    assert key_from_path(labels) == "scr_arena_score"


def test_a_moved_text_takes_the_new_folder_and_keeps_the_case_of_its_own_levels():
    assert key_from_path(["B", "Scr", "Arena"], like="scr_arena") == "B_scr_arena"


def test_authored_labels_still_decide_the_key_when_they_differ_from_it():
    assert key_from_path(["Scene B", "Line"], like="custom_key") == "SceneB_Line"


def test_dropping_a_folder_does_not_recase_the_keys_inside(tmp_path):
    from core.project import Project
    from ui.text_editor.text_commands import SetTextPathCmd

    project = Project(tmp_path / "game")
    text = project.new_text(path=["Scr", "Arena"])
    project.rename_text_key(text, "scr_arena")

    SetTextPathCmd(project, [(text, list(text.path), ["Scr", "Arena"])], "same place").execute()
    assert text.key == "scr_arena"

    SetTextPathCmd(project, [(text, list(text.path), ["Acte", "Scr", "Arena"])], "move").execute()
    assert text.key == "Acte_scr_arena"


def test_a_move_that_swaps_two_keys_is_exact_and_undo_gives_them_back(tmp_path):
    from core.project import Project
    from ui.text_editor.text_commands import SetTextPathCmd

    project = Project(tmp_path / "game")
    first = project.new_text(path=["A", "Line"])
    second = project.new_text(path=["B", "Line"])
    assert (first.key, second.key) == ("A_Line", "B_Line")

    command = SetTextPathCmd(project, [(first, ["A", "Line"], ["B", "Line"]),
                                       (second, ["B", "Line"], ["A", "Line"])], "swap")
    command.execute()
    assert (first.key, second.key) == ("B_Line", "A_Line")

    command.undo()
    assert (first.key, second.key) == ("A_Line", "B_Line")
    assert (first.path, second.path) == (["A", "Line"], ["B", "Line"])
