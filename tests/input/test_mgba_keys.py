"""Les touches transmises à mGBA : seule la section clavier du config.ini change."""
from core.mgba_keys import DEFAULT_KEYS, SECTION, write_keys

_EXISTING = (
    "[gba.input.SDLB]\nkeyA=-1\n\n"
    f"[{SECTION}]\nkeyA=88\nkeyB=90\n\n"
    "[ports.qt]\nfps=1\n"
)


def test_only_the_keyboard_section_changes(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text(_EXISTING, encoding="utf-8")
    write_keys(ini, {"A": 65, "Up": 87})
    text = ini.read_text(encoding="utf-8")
    assert "[gba.input.SDLB]\nkeyA=-1\n" in text and "[ports.qt]\nfps=1\n" in text
    section = text.split(f"[{SECTION}]")[1].split("[ports.qt]")[0]
    assert "keyA=65" in section and "keyB=90" in section and "keyUp=87" in section
    assert "keyA=88" not in text


def test_a_missing_file_or_section_is_created(tmp_path):
    ini = tmp_path / "sub" / "config.ini"
    write_keys(ini, DEFAULT_KEYS)
    assert ini.read_text(encoding="utf-8").startswith(f"[{SECTION}]\n")
    assert "keyStart=16777220" in ini.read_text(encoding="utf-8")


def test_crlf_is_kept(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_bytes(_EXISTING.replace("\n", "\r\n").encode())
    write_keys(ini, {"A": 65})
    raw = ini.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
