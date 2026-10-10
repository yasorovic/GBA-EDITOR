"""Un sidecar effacé HORS de l'éditeur ne revient pas à la sauvegarde.

Le cas réel : des musiques (module + JSON) supprimées dans l'Explorateur
pendant que l'éditeur tourne. Si le watcher n'a rien vu, la ressource vit
toujours en mémoire, et `project.save()` à la fermeture réécrivait son JSON —
d'où des sidecars sans source qui revenaient au lancement suivant."""
import json

from core.project import Project


def _projet_audio(tmp_path, names):
    root = tmp_path / "jeu"
    d = root / "assets" / "music"
    d.mkdir(parents=True)
    for n in names:
        (d / f"{n}.mod").write_bytes(b"x")
        (d / f"{n}.music").write_text(
            json.dumps({"name": n, "asset": f"assets/music/{n}.mod"}), encoding="utf-8")
    p = Project(root)
    p.load()
    p.load_all_resources()
    return p, d


def test_sidecar_efface_dehors_ne_revient_pas_a_la_sauvegarde(tmp_path):
    p, d = _projet_audio(tmp_path, ["a", "b"])
    for n in ("a", "b"):
        (d / f"{n}.mod").unlink()
        (d / f"{n}.music").unlink()

    p.save()
    p.commit_all_removals()

    assert sorted(f.name for f in d.glob("*.music")) == []
    assert [m.name for m in p.music] == []


def test_une_edition_normale_est_toujours_sauvegardee(tmp_path):
    p, d = _projet_audio(tmp_path, ["a"])
    p.music[0].volume = 40

    p.save()

    assert json.loads((d / "a.music").read_text(encoding="utf-8"))["volume"] == 40


def test_drop_if_deleted_on_disk_ignore_un_sidecar_present(tmp_path):
    p, d = _projet_audio(tmp_path, ["a"])

    assert p.music.drop_if_deleted_on_disk("a") is False
    (d / "a.music").unlink()
    assert p.music.drop_if_deleted_on_disk("a") is True
    assert [m.name for m in p.music] == []
