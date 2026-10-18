"""`codegen/build_output.py` — le balayage supprime des fichiers : il faut savoir lesquels."""
from codegen import build_output


def test_sweep_removes_only_files_this_build_did_not_produce(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "stale.c").write_text("int old;")            # reste d'un asset retiré
    (src / "notes.txt").write_text("à garder")          # extension non compilée
    external = src / "from_grit.c"                      # produit par un outil externe
    external.write_text("int g;")

    build_output.begin_build()
    build_output.write(src / "main.c", "int main;")
    build_output.claim(external)
    removed = build_output.sweep([src])

    assert [f.name for f in removed] == ["stale.c"]
    assert sorted(f.name for f in src.iterdir()) == ["from_grit.c", "main.c", "notes.txt"]


def test_write_skips_identical_content_and_keeps_its_date(tmp_path):
    target = tmp_path / "a.c"
    build_output.begin_build()
    assert build_output.write(target, "int a;") is True
    stamp = target.stat().st_mtime_ns
    assert build_output.write(target, "int a;") is False
    assert target.stat().st_mtime_ns == stamp
    assert (build_output.written, build_output.skipped) == (1, 1)
