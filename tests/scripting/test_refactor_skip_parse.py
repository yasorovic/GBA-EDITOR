"""Un script qui ne cite pas l'ancien nom n'est pas parsé (le parse Lua coûte des centaines de ms)."""
from scripting import refactor


def test_rename_in_text_skips_parse_when_old_is_absent(monkeypatch):
    monkeypatch.setattr(refactor, "iter_refs", lambda *a, **k: (_ for _ in ()).throw(AssertionError("parsed")))
    assert refactor.rename_in_text('text:draw("other")', "text", "scr_text_1", "x") == ('text:draw("other")', 0)


def test_index_refs_reparses_only_changed_scripts(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripting.api import DOMAIN_ANIM
    src = 'if self.anim == "%s" then end\n'
    (tmp_path / "a.lua").write_text(src % "k1", encoding="utf-8")
    (tmp_path / "b.lua").write_text(src % "k2", encoding="utf-8")
    project = SimpleNamespace(user_library_dir=tmp_path)
    refactor._INDEX_VALUES.clear()
    first = refactor.index_refs_in_project(project, DOMAIN_ANIM)
    assert set(first) == {"k1", "k2"}
    calls = []
    real = refactor.iter_refs
    monkeypatch.setattr(refactor, "iter_refs", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert refactor.index_refs_in_project(project, DOMAIN_ANIM) == first
    assert calls == []
    (tmp_path / "a.lua").write_text(src % "k3", encoding="utf-8")
    again = refactor.index_refs_in_project(project, DOMAIN_ANIM)
    assert len(calls) == 1 and set(again) == {"k3", "k2"}
