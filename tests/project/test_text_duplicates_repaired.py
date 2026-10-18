"""Un texts.json avec un id ou une clé en double ne ferme pas le projet : il est réparé et signalé."""
import json

from core.project import Project


def _write(root, texts):
    path = root / "assets" / "texts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"texts": texts}), encoding="utf-8")


def test_doublons_d_id_et_de_cle_reparees_et_signalees(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    root = project.root
    _write(root, [{"id": "a", "key": "hello", "path": ["Hello"], "content": "one"},
                  {"id": "a", "key": "hello", "path": ["Hello"], "content": "two"}])

    reopened = Project.open(root)

    assert len({t.id for t in reopened.texts}) == 2 and len({t.key for t in reopened.texts}) == 2
    assert [t.content for t in reopened.texts] == ["one", "two"]          # l'ordre et le contenu ne bougent pas
    assert any("used twice" in w and "texts.json" in w for w in reopened.load_warnings)
    reopened.save_texts()                                                 # et la sauvegarde l'accepte


def test_une_cle_json_repetee_dans_un_objet_reste_refusee(tmp_path):
    import pytest
    from core.project import ProjectFileError

    project = Project.create(tmp_path / "Game", "Game")
    (project.root / "assets" / "texts.json").write_text(
        '{"texts": [{"id": "a", "key": "k", "key": "k2"}]}', encoding="utf-8")

    with pytest.raises(ProjectFileError, match="texts.json"):
        Project.open(project.root)
