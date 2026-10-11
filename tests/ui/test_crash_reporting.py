"""Le crash log et la fenêtre d'erreur : une erreur répétée s'écrit une fois, et la fenêtre ne s'ouvre
jamais depuis l'exception elle-même."""
from __future__ import annotations

import pytest

from core import crash_log


@pytest.fixture
def journal(tmp_path, monkeypatch):
    log = tmp_path / "crash.log"
    monkeypatch.setattr(crash_log, "LOG_FILE", log)
    monkeypatch.setattr(crash_log, "_repeats", {})
    monkeypatch.setattr(crash_log, "_shown_summaries", set())
    monkeypatch.setattr(crash_log, "_reporter", None)
    return log


def _raise_same_error():
    try:
        raise ValueError("boom")
    except ValueError as error:
        return type(error), error, error.__traceback__


def test_an_error_that_repeats_is_written_in_full_once(journal, capsys):
    hook_args = _raise_same_error()
    for _ in range(9):
        crash_log._excepthook(*hook_args)

    text = journal.read_text(encoding="utf-8")
    assert text.count("ValueError: boom") == 1 and text.count("Traceback") == 1
    assert capsys.readouterr().err.count("Traceback") == 1       # stderr aussi : pas d'inondation


def test_a_repeated_error_is_recalled_at_each_power_of_ten(journal):
    hook_args = _raise_same_error()
    for _ in range(100):
        crash_log._excepthook(*hook_args)

    text = journal.read_text(encoding="utf-8")
    assert "now happened 10 times" in text and "now happened 100 times" in text
    assert "now happened 11 times" not in text and text.count("Traceback") == 1


def test_a_different_error_is_written_in_full_too(journal):
    crash_log._excepthook(*_raise_same_error())
    try:
        raise KeyError("other")
    except KeyError as error:
        crash_log._excepthook(type(error), error, error.__traceback__)

    text = journal.read_text(encoding="utf-8")
    assert "ValueError: boom" in text and "KeyError: 'other'" in text


def test_the_crash_window_opens_after_the_exception_not_during_it(qapp, monkeypatch):
    from ui.common import crash_dialog

    opened = []
    monkeypatch.setattr(crash_dialog, "_exec_dialog", lambda *args: opened.append(args))

    crash_dialog.show_crash_dialog("ValueError: boom", "trace", None)
    assert opened == []                         # pas dans la pile de l'exception (ni d'un paintEvent)
    qapp.processEvents()
    qapp.processEvents()

    assert len(opened) == 1


def test_only_one_crash_window_at_a_time(qapp, monkeypatch):
    from ui.common import crash_dialog

    created = []

    class _Fake:
        def __init__(self, *args):
            created.append(args)

        def exec(self):
            crash_dialog._exec_dialog("second", "trace", None)         # une erreur pendant que la fenêtre est ouverte

    monkeypatch.setattr(crash_dialog, "CrashDialog", _Fake)
    crash_dialog._exec_dialog("first", "trace", None)

    assert [args[0] for args in created] == ["first"]
    assert crash_dialog._dialog_open is False                          # rendu une fois la fenêtre fermée


def test_the_test_suite_does_not_write_into_the_authors_crash_log(tmp_path):
    """Garde du filet de `tests/conftest.py` : le journal de chaque test est dans son dossier temporaire."""
    from core.toolchain import config_dir
    assert crash_log.LOG_FILE.parent == tmp_path
    assert config_dir() not in crash_log.LOG_FILE.parents
    assert crash_log.NATIVE_LOG_FILE.parent == tmp_path
