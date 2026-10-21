import pytest

from core.update_check import version_key


def test_version_order():
    assert version_key("1.0.0-alpha") < version_key("1.0.0-beta") < version_key("1.0.0-stable")
    assert version_key("1.0.0-stable") < version_key("1.0.1-alpha")
    assert version_key("1.2.0-alpha") > version_key("1.1.9-stable")
    assert version_key("v1.0.0-alpha") == version_key("1.0.0-alpha")


def test_unknown_form_is_refused():
    with pytest.raises(ValueError):
        version_key("1.0-rc1")


def test_check_delay():
    from core.update_check import CHECK_INTERVAL_SECONDS, is_due
    assert is_due(0, 1_000_000)
    assert not is_due(1_000_000, 1_000_000 + CHECK_INTERVAL_SECONDS - 1)
    assert is_due(1_000_000, 1_000_000 + CHECK_INTERVAL_SECONDS)


def test_update_json():
    from core.update_check import parse_importance
    assert parse_importance({"importance": "normal"}) is False
    assert parse_importance({"importance": "major", "reasons": ["api"]}) is True
    for bad in ({}, {"importance": "major"}, {"importance": "major", "reasons": ["x"]},
                {"importance": "normal", "reasons": "api"}):
        with pytest.raises(ValueError):
            parse_importance(bad)


def test_sha256sums_parsing():
    from core.update_install import parse_sums
    assert parse_sums("AB  a.exe\nCD *b.zip\n\n") == {"a.exe": "ab", "b.zip": "cd"}
