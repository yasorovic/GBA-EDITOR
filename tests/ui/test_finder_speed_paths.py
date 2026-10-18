"""Les chemins rapides des finders rendent les mêmes arbres que les parcours qu'ils remplacent."""
from ui.common import finder_fold_state
from ui.common.asset_finder import dir_nodes


def _shape(nodes):
    return [(n.name, n.is_folder, _shape(n.children)) for n in nodes]


def test_dir_nodes_lists_folders_first_then_matching_files_alphabetically(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "z.lua").write_text("")
    (tmp_path / "a").mkdir()                       # dossier vide: gardé sans prune_empty
    (tmp_path / "Y.lua").write_text("")
    (tmp_path / "x.lua").write_text("")
    (tmp_path / "skip.png").write_text("")

    class P:
        assets = tmp_path
    assert _shape(dir_nodes("assets", (".lua",))(P)) == [
        ("a", True, []), ("b", True, [("z.lua", False, [])]), ("x.lua", False, []), ("Y.lua", False, [])]
    assert _shape(dir_nodes("assets", (".lua",), prune_empty=True)(P)) == [
        ("b", True, [("z.lua", False, [])]), ("x.lua", False, []), ("Y.lua", False, [])]


def test_fold_state_reads_through_the_cache(monkeypatch):
    monkeypatch.setattr(finder_fold_state, "_expanded", set())
    monkeypatch.setattr(finder_fold_state, "_settings",
                        lambda: type("S", (), {"setValue": lambda *a: None, "remove": lambda *a: None})())
    assert not finder_fold_state.is_expanded("folder/x")
    finder_fold_state.set_expanded("folder/x", True)
    assert finder_fold_state.is_expanded("folder/x")
    finder_fold_state.set_expanded("folder/x", False)
    assert not finder_fold_state.is_expanded("folder/x")
