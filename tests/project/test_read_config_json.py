"""Un fichier de réglages illisible est conservé, pas écrasé en silence."""
from core.resources.resource_store import read_config_json


def test_missing_file_is_empty_and_valid_file_is_read(tmp_path):
    path = tmp_path / "config.json"
    assert read_config_json(path) == {}
    path.write_text('{"a": 1}', encoding="utf-8")
    assert read_config_json(path) == {"a": 1}


def test_corrupt_file_is_kept_aside_and_reads_empty(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_config_json(path) == {}
    assert (tmp_path / "config.json.corrupt").read_text(encoding="utf-8") == "{not json"
