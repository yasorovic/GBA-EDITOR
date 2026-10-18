"""Compatibilité des emplacements entre ROMs, exécutée par le vrai pilote C."""
import os
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from codegen.runtime_codegen.gen_save import save_fatal, save_lines, save_slot_size, save_total_bytes
from core.models.settings import GlobalVar
from native_toolchain import compilateur_hote, environnement

SRAM_SIZE = 32768
SCORE = GlobalVar(name="score", id="000000000001", persist=True)
LEVEL = GlobalVar(name="level", id="000000000002", persist=True, default=7)


def _project(variables, slots=3):
    return SimpleNamespace(globals=list(variables), settings=SimpleNamespace(save_slots=slots))


def _legacy(slots, records=1, payload_bytes=4, version=2):
    memory = bytearray(SRAM_SIZE)
    for slot in slots:
        data = b"".join(struct.pack("<IIi", i + 1, payload_bytes, 40 + slot + i)
                        + bytes(payload_bytes - 4) for i in range(records))
        checksum = slot if version == 3 else 0
        for byte in data:
            checksum = (checksum * 31 + byte) & 0xFFFFFFFF
        block = struct.pack("<4sHHI", b"GBSV", version, records, checksum)
        block += struct.pack("<I", slot) if version == 3 else b""
        block += data
        base = slot * (((SRAM_SIZE // 3) & ~3) if version == 3 else len(block))
        memory[base:base + len(block)] = block
    assert len(memory) == SRAM_SIZE
    return bytes(memory)


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    compiler = compilateur_hote()
    if compiler is None:
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail("compilateur C hôte nécessaire pour tester la SRAM")
        pytest.skip("compilateur C hôte absent")
    root = tmp_path_factory.mktemp("save-probe")
    repo = Path(__file__).resolve().parents[2]
    env = environnement(compiler)
    builds = {}
    calls = 0

    def run(memory, commands, variables=(SCORE, LEVEL), slots=3, no_memory=False):
        nonlocal calls
        project = _project(variables, slots)
        tables = "\n".join(save_lines(project))
        key = tables, no_memory
        if key not in builds:
            folder = root / str(len(builds))
            folder.mkdir(exist_ok=True)
            (folder / "save_tables.h").write_text(tables, encoding="utf-8")
            executable = folder / "probe.exe"
            result = subprocess.run(
                [compiler, "-std=c11", "-O0", "-ffunction-sections", "-fdata-sections",
                 "-Wl,--gc-sections", *(["-DPROBE_NO_MEMORY"] if no_memory else []),
                 "-I", str(repo / "tests/native/libgba_shim"), "-I", str(repo / "runtime/include"),
                 "-I", str(folder), str(repo / "tests/native/save_probe.c"), "-o", str(executable)],
                env=env, capture_output=True, text=True)
            assert result.returncode == 0, result.stdout + result.stderr
            builds[key] = executable
        calls += 1
        source, target = root / f"input{calls}.sav", root / f"output{calls}.sav"
        source.write_bytes(memory)
        result = subprocess.run([str(builds[key]), str(source), str(target)], input=commands,
                                env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return [list(map(int, line.split())) for line in result.stdout.splitlines()], target.read_bytes()

    return run


def test_new_slots_survive_adding_variables_and_writing_one_slot(probe):
    commands = "S 0 40\nW 0\nS 0 41\nW 1\nS 0 42\nW 2\n"
    result, old = probe(bytes(SRAM_SIZE), commands, variables=(SCORE,))
    assert result == [[1], [1], [1]]
    result, unchanged = probe(old, "R 0\nR 1\nR 2\nP 2 0\nP 2 1\n")
    assert result == [[1, 40, 7], [1, 41, 7], [1, 42, 7], [42], [7]]
    assert unchanged == old
    result, saved = probe(old, "S 0 90\nS 1 8\nW 0\nR 1\nR 2\n")
    assert result == [[1], [1, 41, 7], [1, 42, 7]]
    result, _ = probe(saved, "R 0\nR 1\nR 2\n")
    assert result == [[1, 90, 8], [1, 41, 7], [1, 42, 7]]


@pytest.mark.parametrize("slots", [(0, 1, 2), (2,)])
@pytest.mark.parametrize("version", [2, 3])
def test_legacy_slots_are_read_without_changing_sram(probe, slots, version):
    old = _legacy(slots, version=version)
    result, unchanged = probe(old, "R 2\nP 2 0\nP 2 1\nX 1\n")
    assert result == [[1, 42, 7], [42], [7], [int(1 in slots)]]
    assert unchanged == old


@pytest.mark.parametrize("operation", ["S 0 90\nS 1 8\nW 0\n", "E 0\n"])
@pytest.mark.parametrize("version", [2, 3])
def test_first_write_or_erase_preserves_neighbouring_legacy_slots(probe, operation, version):
    result, migrated = probe(_legacy((0, 1, 2), version=version), operation + "R 1\nR 2\n")
    assert result == [[1], [1, 41, 7], [1, 42, 7]]
    result, _ = probe(migrated, "R 1\nR 2\nX 0\n")
    assert result == [[1, 41, 7], [1, 42, 7], [int("W" in operation)]]
    room = (SRAM_SIZE // 3) & ~3
    base = next(b for b in (2 * room, 2 * room + (room // 2 & ~3)) if migrated[b:b + 4] == b"GBSV" and migrated[b + 4] == 4)
    assert struct.unpack_from("<I", migrated, base + 24)[0] == 0  # Old count and type remain unknown.


@pytest.mark.parametrize("legacy", [False, True])
def test_removing_and_reordering_variables_keeps_their_ids(probe, legacy):
    if legacy:
        old = _legacy((0, 1, 2), records=2)
    else:
        _, old = probe(bytes(SRAM_SIZE), "S 0 42\nS 1 43\nW 2\n")
    result, _ = probe(old, "R 2\n", variables=(LEVEL,))
    assert result == [[1, 43]]
    result, _ = probe(old, "R 2\n", variables=(LEVEL, SCORE))
    assert result == [[1, 43, 42]]


def test_slot_count_change_keeps_existing_slots(probe):
    _, old = probe(bytes(SRAM_SIZE), "S 0 40\nW 0\nS 0 41\nW 1\n", variables=(SCORE,), slots=2)
    result, saved = probe(old, "R 0\nR 1\nS 0 42\nW 2\nR 1\n", variables=(SCORE,))
    assert result == [[1, 40], [1, 41], [1], [1, 41]]
    result, _ = probe(saved, "R 0\nR 1\nR 2\n", variables=(SCORE,))
    assert result == [[1, 40], [1, 41], [1, 42]]


def test_reading_one_variable_does_not_replace_the_running_game(probe):
    result, _ = probe(_legacy((2,)), "S 0 99\nS 1 88\nP 2 0\nR -1\n")
    assert result == [[42], [0, 99, 88]]


def test_slot_number_is_protected_by_the_checksum(probe):
    _, saved = probe(bytes(SRAM_SIZE), "S 0 42\nW 2\n", variables=(SCORE,))
    saved = bytearray(saved)
    saved[2 * ((SRAM_SIZE // 3) & ~3) + 12] = 1
    result, unchanged = probe(saved, "X 1\nX 2\n")
    assert result == [[0], [0]]
    assert unchanged == saved


def test_game_without_persistent_variables_does_not_touch_sram(probe):
    old = _legacy((0, 1, 2))
    result, unchanged = probe(old, "W 0\nE 0\nX 0\nR 0\n", variables=())
    assert result == [[0], [0], [0], [0]]
    assert unchanged == old


@pytest.mark.parametrize("failure", ["memory", "capacity", "hidden_slot"])
def test_failed_migration_changes_no_sram_bytes(probe, failure):
    # "memory": deux gros blocs v2 qui se recouvrent les places libres : seule la réécriture en RAM passerait.
    old = (_legacy((0,), payload_bytes=16384) if failure == "capacity"
           else _legacy((0, 1), payload_bytes=4000) if failure == "memory" else _legacy((0, 1)))
    result, unchanged = probe(old, "W 0\n", slots=1 if failure == "hidden_slot" else 3,
                              no_memory=failure == "memory")
    assert result == [[0]]
    assert unchanged == old


@pytest.mark.parametrize("damage", ["checksum", "size", "count", "version"])
def test_invalid_save_records_are_refused(probe, damage):
    old = bytearray(_legacy((0,)))
    if damage == "checksum":
        old[8] ^= 1
    elif damage == "size":
        old[16:20] = struct.pack("<I", 0xFFFFFFFF)
    elif damage == "count":
        old[6:8] = b"\xff\xff"
    else:
        old[4] = 99
    result, unchanged = probe(old, "X 0\nR 0\nP 0 1\nW -1\nE 2147483647\n")
    assert result == [[0], [0, 0, 0], [7], [0], [0]]
    assert unchanged == old


def test_codegen_counts_the_new_header_and_blocks_sram_overflow():
    project = _project((SCORE, LEVEL))
    assert save_slot_size(project) == 16 + 2 * 16
    assert save_total_bytes(project) == 3 * 2 * 48   # deux copies par emplacement
    assert not save_fatal(project)
    project.globals = [GlobalVar(name="large", id=SCORE.id, persist=True, count=8192)]
    assert any("SRAM" in problem for problem in save_fatal(project))


@pytest.mark.parametrize("kind,default,values,grown", [
    ("bool", 1, [0], 2),
    ("bool", 1, [0, 1, 0], 5),
    ("bool", 1, [0] * 31, 33),
    ("u8", 7, [9], 2),
    ("u8", 7, [9, 0, 255], 6),
    ("s8", -7, [-9, 0, 127], 6),
    ("u16", 7, [65535], 3),
    ("s16", -7, [-32768], 3),
    ("int", 7, [-123, 0], 4),
])
def test_array_growth_keeps_new_cells_at_their_defaults(probe, kind, default, values, grown):
    old_var = GlobalVar(name="array", id=SCORE.id, persist=True, type=kind, default=default, count=len(values))
    new_var = GlobalVar(name="array", id=SCORE.id, persist=True, type=kind, default=default, count=grown)
    commands = "".join(f"A 0 {i} {value}\n" for i, value in enumerate(values)) + "W 1\n"
    result, old = probe(bytes(SRAM_SIZE), commands, variables=(old_var, LEVEL))
    assert result == [[1]]
    commands = "R 1\n" + "".join(f"G 0 {i}\n" for i in range(grown))
    result, unchanged = probe(old, commands, variables=(new_var, LEVEL))
    expected = values + [default] * (grown - len(values))
    assert result == [[1, values[0], 0]] + [[value] for value in expected]
    assert unchanged == old
    result, saved = probe(old, commands + "W 1\n", variables=(new_var, LEVEL))
    assert result[-1] == [1]
    result, _ = probe(saved, commands, variables=(new_var, LEVEL))
    assert result == [[1, values[0], 0]] + [[value] for value in expected]


@pytest.mark.parametrize("kind,value", [("u8", 255), ("s8", -128), ("u16", 65535), ("s16", -32768)])
def test_saved_element_width_and_sign_survive_type_changes(probe, kind, value):
    old_var = GlobalVar(name="array", id=SCORE.id, persist=True, type=kind, count=1)
    new_var = GlobalVar(name="array", id=SCORE.id, persist=True, type="int", default=7, count=2)
    _, saved = probe(bytes(SRAM_SIZE), f"A 0 0 {value}\nW 0\n", variables=(old_var,))
    result, _ = probe(saved, "R 0\nG 0 1\nP 0 0\n", variables=(new_var,))
    assert result == [[1, value], [7], [value]]


def test_shorter_array_does_not_overwrite_the_next_variable(probe):
    old_var = GlobalVar(name="array", id=SCORE.id, persist=True, type="u8", count=5)
    new_var = GlobalVar(name="array", id=SCORE.id, persist=True, type="u8", count=2)
    _, saved = probe(bytes(SRAM_SIZE), "A 0 0 9\nA 0 1 8\nA 0 4 99\nS 1 42\nW 2\n",
                     variables=(old_var, LEVEL))
    result, _ = probe(saved, "R 2\nG 0 1\nG 0 2\n", variables=(new_var, LEVEL))
    assert result == [[1, 9, 42], [8], [0]]


@pytest.mark.parametrize("meta", [8 << 24, (7 << 24) | 1, (32 << 24) | 2,
                                 (0x81 << 24) | 1, (8 << 24) | 65536])
def test_invalid_array_metadata_is_rejected_even_with_a_valid_checksum(probe, meta):
    _, saved = probe(bytes(SRAM_SIZE), "W 0\n", variables=(LEVEL,))
    saved = bytearray(saved)
    struct.pack_into("<I", saved, 24, meta)
    checksum = 0
    for byte in saved[16:32]:
        checksum = (checksum * 31 + byte) & 0xFFFFFFFF
    struct.pack_into("<I", saved, 8, checksum)
    result, unchanged = probe(saved, "X 0\nR 0\nP 0 0\n", variables=(LEVEL,))
    assert result == [[0], [0, 0], [7]]
    assert unchanged == saved


def test_boolean_arrays_keep_their_packed_size():
    array = GlobalVar(name="flags", id=SCORE.id, persist=True, type="bool", count=400)
    assert save_slot_size(_project((array,))) == 16 + 12 + 52


# ── Une coupure en pleine écriture épargne la sauvegarde précédente ───────────

def _copies(slots=3, slot=0):
    room = (SRAM_SIZE // slots) & ~3
    return slot * room, slot * room + (room // 2 & ~3)


def test_a_second_write_goes_to_the_other_copy_and_keeps_the_first(probe):
    first, second = _copies()
    _, once = probe(bytes(SRAM_SIZE), "S 0 40\nW 0\n", variables=(SCORE,))
    _, twice = probe(once, "S 0 41\nW 0\n", variables=(SCORE,))
    assert twice[first:first + 16] == once[first:first + 16]          # la première copie n'a pas bougé
    assert twice[second:second + 4] == b"GBSV"
    result, _ = probe(twice, "R 0\n", variables=(SCORE,))
    assert result == [[1, 41]]


@pytest.mark.parametrize("damage", ["checksum", "payload", "header"])
def test_a_write_cut_midway_leaves_the_previous_save_readable(probe, damage):
    first, second = _copies()
    _, once = probe(bytes(SRAM_SIZE), "S 0 40\nW 0\n", variables=(SCORE,))
    _, twice = probe(once, "S 0 41\nW 0\n", variables=(SCORE,))
    cut = bytearray(twice)
    offset = {"checksum": second + 8, "payload": second + 16 + 12, "header": second}[damage]
    cut[offset] ^= 0xFF        # la copie la plus récente est abîmée, comme par une coupure
    result, _ = probe(bytes(cut), "R 0\nX 0\n", variables=(SCORE,))
    assert result == [[1, 40], [1]]
    result, healed = probe(bytes(cut), "S 0 42\nW 0\nR 0\n", variables=(SCORE,))
    assert result == [[1], [1, 42]]
    assert healed[first:first + 4] == b"GBSV"


def test_erase_clears_both_copies(probe):
    _, once = probe(bytes(SRAM_SIZE), "S 0 40\nW 0\n", variables=(SCORE,))
    _, twice = probe(once, "S 0 41\nW 0\nE 0\n", variables=(SCORE,))
    result, _ = probe(twice, "X 0\n", variables=(SCORE,))
    assert result == [[0]]


def test_generation_wraps_around_without_losing_the_latest(probe):
    memory = bytes(SRAM_SIZE)
    for value in range(300):
        _, memory = probe(memory, f"S 0 {value}\nW 0\n", variables=(SCORE,))
    result, _ = probe(memory, "R 0\n", variables=(SCORE,))
    assert result == [[1, 299]]


# ── Une coupure en pleine migration ne perd aucun emplacement ─────────────────

@pytest.mark.parametrize("version", [2, 3])
def test_migration_keeps_every_slot_readable_and_leaves_nothing_to_migrate(probe, version):
    result, migrated = probe(_legacy((0, 1, 2), version=version), "W 1\n")
    assert result == [[1]]
    for slot, value in ((0, 40), (1, 0), (2, 42)):
        result, _ = probe(migrated, f"R {slot}\n")
        assert result[0][:2] == [1, value]
    # Plus aucun ancien bloc : une écriture de plus n'a rien à migrer et ne perd rien.
    result, _ = probe(migrated, "R 2\nW 2\nR 0\nR 2\n")
    assert result == [[1, 42, 7], [1], [1, 40, 7], [1, 42, 7]]


def test_old_and_new_block_both_present_resolves_to_the_new_one(probe):
    """État laissé par une coupure juste avant l'effacement de l'ancien bloc : l'ancien est périmé, le nouveau gagne,
    et la migration suivante efface l'ancien."""
    _, migrated = probe(_legacy((0, 1, 2), version=2), "W 1\n")
    assert migrated[:4] != b"GBSV"                       # l'ancien bloc de l'emplacement 0 est effacé
    cut = bytearray(migrated)
    cut[:12] = _legacy((0,), version=2)[:12]             # l'en-tête de l'ancien est revenu : les deux sont lisibles
    result, healed = probe(bytes(cut), "R 0\nW 2\nR 0\n")
    assert result == [[1, 40, 7], [1], [1, 40, 7]]
    assert healed[:4] != b"GBSV"                         # le doublon périmé a été effacé
