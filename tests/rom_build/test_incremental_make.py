"""Le vrai Makefile doit recompiler après un changement d'en-tête, sans reconstruire à vide."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement


@pytest.fixture
def make_build(tmp_path):
    compiler = compilateur_hote()
    make = shutil.which("make") or shutil.which("mingw32-make")
    if compiler is None or make is None:
        message = "compilateur C hôte et make nécessaires pour tester les reconstructions"
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message)
    shutil.copyfile(Path(__file__).resolve().parents[2] / "runtime" / "Makefile", tmp_path / "Makefile")
    for directory in ("src", "grit_out", "obj"):
        (tmp_path / directory).mkdir()
    env = environnement(compiler)

    def run(target="obj/probe.o", *options):
        result = subprocess.run(
            [make, *options, target, "DEVKITPRO=unused", f"CC={compiler}", "ARCH=",
             "CFLAGS=-O0 -Isrc -Igrit_out"],
            cwd=tmp_path, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    return run, compiler, env


@pytest.mark.parametrize("directory,extension", [("src", ".c"), ("grit_out", ".c"), ("src", ".s")])
def test_header_changes_rebuild_only_when_needed(tmp_path, make_build, directory, extension):
    run, compiler, env = make_build
    source = tmp_path / directory / ("probe" + extension)
    header = source.with_name("constants.h")
    body = "int main(void) { return CONST_VALUE; }\n" if extension == ".c" else ".text\n.byte CONST_VALUE\n"
    source.write_text('#include "constants.h"\n' + body, encoding="utf-8")
    header.write_text("#define CONST_VALUE 7\n", encoding="utf-8")
    obj = tmp_path / "obj" / "probe.o"
    run()
    assert (tmp_path / "obj" / "probe.d").is_file()

    def value():
        executable = tmp_path / "probe.exe"
        linked = subprocess.run([compiler, str(obj), "-o", str(executable)], env=env,
                                capture_output=True, text=True)
        assert linked.returncode == 0, linked.stdout + linked.stderr
        return subprocess.run([str(executable)], env=env).returncode

    if extension == ".c":
        assert value() == 7
    stamp = obj.stat().st_mtime_ns
    run()
    assert obj.stat().st_mtime_ns == stamp

    header.write_text("#define CONST_VALUE 19\n", encoding="utf-8")
    os.utime(obj, ns=(stamp - 2_000_000_000, stamp - 2_000_000_000))
    assert " -c " in run()
    if extension == ".c":
        assert value() == 19

    header.unlink()
    source.write_text(body.replace("CONST_VALUE", "19"), encoding="utf-8")
    assert " -c " in run()
    assert "rom.gba" in run("all", "-n")


def test_existing_objects_without_dependency_files_are_rebuilt(tmp_path, make_build):
    run, _compiler, _env = make_build
    (tmp_path / "src" / "probe.c").write_text("int probe(void) { return 7; }\n", encoding="utf-8")
    obj = tmp_path / "obj" / "probe.o"
    obj.write_bytes(b"object from an older build")
    stamp = (tmp_path / "Makefile").stat().st_mtime_ns
    os.utime(tmp_path / "src" / "probe.c", ns=(stamp - 4_000_000_000, stamp - 4_000_000_000))
    os.utime(obj, ns=(stamp - 2_000_000_000, stamp - 2_000_000_000))

    assert " -c " in run()
    assert (tmp_path / "obj" / "probe.d").is_file()
