"""Le service d'encodage unique : le dernier réglage gagne, le seuil de coût, le cache, les rappels, l'échec.

Un FAUX exécuteur tient les calculs en main : un test décide quand chacun finit, donc quand un réglage plus récent
arrive « pendant le calcul ».
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import os

import pytest

from core.models.background import BackgroundAsset, BackgroundCompression
from ui.background_editor.background_encoding import BackgroundEncodingService, EncodingJob, EncodingState


class ManualExecutor:
    """Garde les travaux ; `finish(result, seconds)` termine le plus ancien, `fail(message)` le fait échouer."""

    def __init__(self):
        self.jobs: list = []

    def run(self, work, on_done, on_failed):
        self.jobs.append((work, on_done, on_failed))

    def finish(self, result=None, seconds: float = 0.1):
        work, on_done, _ = self.jobs.pop(0)
        on_done(result if result is not None else {"tag": len(self.jobs)}, seconds)

    def fail(self, message: str = "boom"):
        _work, _done, on_failed = self.jobs.pop(0)
        on_failed(message)


def _fond(name="x"):
    ba = BackgroundAsset(name=name, asset=f"{name}.png")
    ba.id = f"id-{name}"
    return ba


def _job(ba, palettes_max=16, token="tiled4"):
    return EncodingJob(ba=ba, path=Path(f"{ba.name}.png"), token=token, method="median_cut", dither=False,
                       prep={"canvas": None, "pos": None, "size": None, "mirror": (None, None, False, False),
                             "adjust": ba.adjust},
                       compression=BackgroundCompression(palettes_max=palettes_max))


def _service(auto_seconds=4.0):
    committed, executor = [], ManualExecutor()
    service = BackgroundEncodingService(commit=lambda job, result: committed.append((job, result)),
                                        executor=executor, auto_seconds=auto_seconds)
    return service, executor, committed


# ── Le cas simple ─────────────────────────────────────────────────────────────

def test_une_demande_bon_marche_part_toute_seule_et_se_valide_a_la_fin(qapp):
    service, executor, committed = _service()
    ba = _fond()
    states = []
    service.state_changed.connect(lambda b: states.append(service.state(b)))

    service.request(_job(ba))
    assert service.state(ba) == EncodingState.COMPUTING and len(executor.jobs) == 1

    executor.finish({"tag": "a"})

    assert [r for _j, r in committed] == [{"tag": "a"}]
    assert service.state(ba) in (EncodingState.UP_TO_DATE, EncodingState.PENDING)    # le faux résultat ne pose pas d'empreinte
    assert states[:2] == [EncodingState.PENDING, EncodingState.COMPUTING]


def test_la_validation_appelle_les_rappels_et_signale(qapp):
    service, executor, _committed = _service()
    ba = _fond()
    seen, signalled = [], []
    service.committed.connect(lambda b, j: signalled.append(b))

    service.request(_job(ba), then=lambda: seen.append("then"))
    executor.finish()

    assert seen == ["then"] and signalled == [ba]


# ── Le dernier gagne ──────────────────────────────────────────────────────────

def test_un_reglage_plus_recent_remplace_le_precedent_et_le_perime_n_est_jamais_valide(qapp):
    service, executor, committed = _service()
    ba = _fond()
    service.request(_job(ba, palettes_max=4))                    # part
    service.request(_job(ba, palettes_max=8))                    # arrive PENDANT le calcul : il remplace le voulu
    service.request(_job(ba, palettes_max=12))                   # et lui aussi est remplacé

    executor.finish({"tag": "4"})                                # le premier finit, périmé
    assert committed == [] and len(executor.jobs) == 1           # rien de validé ; le dernier voulu repart

    executor.finish({"tag": "12"})
    assert [r["tag"] for _j, r in committed] == ["12"]
    assert committed[0][0].compression.palettes_max == 12


def test_les_rappels_d_un_reglage_remplace_survivent_a_la_validation_finale(qapp):
    service, executor, _committed = _service()
    ba = _fond()
    seen = []
    service.request(_job(ba, palettes_max=4), then=lambda: seen.append("premier"))
    service.request(_job(ba, palettes_max=8), then=lambda: seen.append("second"))

    executor.finish()
    executor.finish()

    assert seen == ["premier", "second"]


def test_un_seul_calcul_a_la_fois_tous_fonds_confondus(qapp):
    service, executor, committed = _service()
    a, b = _fond("a"), _fond("b")
    service.request(_job(a))
    service.request(_job(b))

    assert len(executor.jobs) == 1 and service.state(b) == EncodingState.PENDING   # b attend son tour
    executor.finish({"tag": "a"})
    assert len(executor.jobs) == 1                                                 # b est parti
    executor.finish({"tag": "b"})
    assert [j.ba.name for j, _r in committed] == ["a", "b"]


# ── Le seuil de coût ──────────────────────────────────────────────────────────

def test_un_fond_dont_le_dernier_encodage_a_ete_cher_attend_le_bouton(qapp):
    service, executor, committed = _service(auto_seconds=4.0)
    ba = _fond()
    service.request(_job(ba, palettes_max=4))
    executor.finish({"tag": "lent"}, seconds=9.0)                # un encodage de 9 s

    service.request(_job(ba, palettes_max=8))

    assert service.last_seconds(ba) == 9.0
    assert executor.jobs == [] and service.state(ba) == EncodingState.PENDING   # trop cher pour partir tout seul

    service.run_now(ba)                                          # « Run encoding »
    assert len(executor.jobs) == 1 and service.state(ba) == EncodingState.COMPUTING
    executor.finish({"tag": "fait"}, seconds=9.0)
    assert [r["tag"] for _j, r in committed][-1] == "fait"


def test_un_geste_part_toujours_meme_sur_un_fond_cher(qapp):
    service, executor, _committed = _service(auto_seconds=4.0)
    ba = _fond()
    service.request(_job(ba, palettes_max=4))
    executor.finish(seconds=9.0)

    service.request(_job(ba, palettes_max=8), immediate=True)

    assert len(executor.jobs) == 1                               # le canvas, l'import : l'auteur l'a demandé


def test_un_fond_bon_marche_repart_tout_seul(qapp):
    service, executor, _committed = _service(auto_seconds=4.0)
    ba = _fond()
    service.request(_job(ba, palettes_max=4))
    executor.finish(seconds=1.0)

    service.request(_job(ba, palettes_max=8))

    assert len(executor.jobs) == 1


def test_un_reglage_remplace_pendant_un_calcul_cher_retombe_en_attente(qapp):
    service, executor, committed = _service(auto_seconds=4.0)
    ba = _fond()
    service.request(_job(ba, palettes_max=4))                    # part (jamais mesuré)
    service.request(_job(ba, palettes_max=8))                    # remplace pendant le calcul

    executor.finish({"tag": "4"}, seconds=9.0)                   # le premier était cher : le suivant attend

    assert executor.jobs == [] and committed == [] and service.state(ba) == EncodingState.PENDING
    service.run_now(ba)
    executor.finish({"tag": "8"}, seconds=9.0)
    assert [r["tag"] for _j, r in committed] == ["8"]


# ── Le cache ──────────────────────────────────────────────────────────────────

def test_un_resultat_deja_vu_se_valide_sans_calcul(qapp):
    service, executor, committed = _service()
    ba = _fond()
    service.request(_job(ba, palettes_max=4))
    executor.finish({"tag": "4"})
    service.request(_job(ba, palettes_max=8))
    executor.finish({"tag": "8"})
    committed.clear()

    service.request(_job(ba, palettes_max=4))                    # déjà vu

    assert executor.jobs == [] and [r["tag"] for _j, r in committed] == ["4"]


def test_le_cache_est_borne(qapp):
    service, executor, _committed = _service()
    ba = _fond()
    for n in range(1, 13):
        service.request(_job(ba, palettes_max=n))
        executor.finish({"tag": str(n)})

    assert len(service._cache) == BackgroundEncodingService.CACHE_SIZE


# ── L'échec ───────────────────────────────────────────────────────────────────

def test_un_echec_est_un_etat_et_un_signal_et_le_bouton_le_rejoue(qapp):
    service, executor, committed = _service()
    ba = _fond()
    messages = []
    service.failed.connect(lambda b, m: messages.append((b, m)))
    service.request(_job(ba))

    executor.fail("PNG illisible")

    assert service.state(ba) == EncodingState.FAILED and messages == [(ba, "PNG illisible")]
    assert executor.jobs == []                                   # on ne boucle pas sur l'échec

    service.run_now(ba)                                          # le réglage reste voulu : on le rejoue
    assert len(executor.jobs) == 1
    executor.finish({"tag": "ok"})
    assert [r["tag"] for _j, r in committed] == ["ok"]


def test_un_echec_perime_est_ignore(qapp):
    service, executor, _committed = _service()
    ba = _fond()
    messages = []
    service.failed.connect(lambda b, m: messages.append(m))
    service.request(_job(ba, palettes_max=4))
    service.request(_job(ba, palettes_max=8))                    # remplace pendant le calcul

    executor.fail("ancien")

    assert messages == [] and len(executor.jobs) == 1            # le réglage actuel repart, rien n'est signalé


# ── La clé ────────────────────────────────────────────────────────────────────

def test_la_cle_d_un_travail_change_avec_chaque_reglage_et_pas_avec_le_fond():
    a = _job(_fond())
    assert a.key() == _job(_fond("autre")).key() or a.key()[0] != _job(_fond("autre")).key()[0]   # le chemin y est
    assert _job(_fond(), palettes_max=4).key() != _job(_fond(), palettes_max=5).key()
    assert _job(_fond(), token="tiled8").key() != _job(_fond(), token="tiled4").key()


# ── L'annulation ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("request_again", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_changed_source_rejects_running_result_and_retries_without_losing_callbacks(
        qapp, tmp_path, request_again, failure):
    service, executor, committed = _service()
    source = tmp_path / "source.png"
    source.write_bytes(b"old")
    job = replace(_job(_fond()), path=source)
    callbacks, errors = [], []
    service.failed.connect(lambda ba, message: errors.append(message))
    service.request(job, then=lambda: callbacks.append("first"))
    stamp = source.stat().st_mtime_ns
    source.write_bytes(b"new")
    os.utime(source, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))
    if request_again:
        service.request(replace(job), then=lambda: callbacks.append("second"))
    if failure:
        executor.fail("old source failed")
    else:
        executor.finish({"tag": "old"})

    assert committed == callbacks == errors == []
    assert len(executor.jobs) == 1
    assert service.state(job.ba) == EncodingState.COMPUTING
    executor.finish({"tag": "new"})
    assert [r["tag"] for _j, r in committed] == ["new"]
    assert callbacks == (["first", "second"] if request_again else ["first"])
    service.request(replace(job))
    assert executor.jobs == []
    assert [r["tag"] for _j, r in committed] == ["new", "new"]


def test_source_size_alone_invalidates_the_result(qapp, tmp_path):
    service, executor, committed = _service()
    source = tmp_path / "source.png"
    source.write_bytes(b"old")
    job = replace(_job(_fond()), path=source)
    service.request(job)
    stamp = source.stat().st_mtime_ns
    source.write_bytes(b"larger replacement")
    os.utime(source, ns=(stamp, stamp))
    executor.finish({"tag": "old"})
    assert committed == [] and len(executor.jobs) == 1


def test_source_deleted_during_encoding_is_retried_and_failure_does_not_loop(qapp, tmp_path):
    service, executor, committed = _service()
    source = tmp_path / "source.png"
    source.write_bytes(b"old")
    job = replace(_job(_fond()), path=source)
    service.request(job)
    source.unlink()
    executor.finish({"tag": "old"})
    assert committed == [] and len(executor.jobs) == 1
    executor.fail("source missing")
    assert executor.jobs == [] and service.state(job.ba) == EncodingState.FAILED

def test_annuler_une_demande_en_attente_remet_le_fond_a_jour_et_un_calcul_en_cours_ne_valide_rien(qapp):
    service, executor, committed = _service(auto_seconds=4.0)
    ba = _fond()
    service.request(_job(ba, palettes_max=4))
    executor.finish(seconds=9.0)                                 # le fond est cher : la suite attend le bouton
    service.request(_job(ba, palettes_max=8))
    assert service.state(ba) == EncodingState.PENDING

    service.cancel(ba)

    assert service.wanted(ba) is None and service._states[service._id(ba)] == EncodingState.UP_TO_DATE

    service.request(_job(ba, palettes_max=12), immediate=True)   # part ; puis l'auteur revient en arrière pendant le calcul
    committed.clear()
    service.cancel(ba)
    executor.finish({"tag": "12"})

    assert committed == [] and service._states[service._id(ba)] == EncodingState.UP_TO_DATE


@pytest.mark.parametrize("failure", [False, True])
def test_cancel_all_discards_running_and_queued_callbacks(qapp, failure):
    service, executor, committed = _service()
    callbacks, errors = [], []
    service.failed.connect(lambda ba, message: errors.append(message))
    old, queued, new = _fond("old"), _fond("queued"), _fond("new")
    service.request(_job(old), then=lambda: callbacks.append("old"))
    service.request(_job(queued), then=lambda: callbacks.append("queued"))

    service.cancel_all()
    service.request(_job(new), then=lambda: callbacks.append("new"))
    if failure:
        executor.fail("old project failed")
    else:
        executor.finish({"tag": "old"})

    assert committed == callbacks == errors == []
    assert service.wanted(old) is None and service.wanted(queued) is None
    assert len(executor.jobs) == 1
    executor.finish({"tag": "new"})
    assert [job.ba for job, _result in committed] == [new]
    assert callbacks == ["new"]


def test_project_switch_does_not_save_an_old_encoding_into_the_new_project(qapp, tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from PIL import Image
    from core.project import Project
    from ui.background_editor import background_editor_screen

    projects, backgrounds = [], []
    for name, color in (("old", "red"), ("new", "blue")):
        project = Project(tmp_path / name)
        (project.assets_dir / "backgrounds").mkdir(parents=True)
        Image.new("RGB", (8, 8), color).save((project.assets_dir / "backgrounds") / "sky.png")
        ba = BackgroundAsset(name="sky", asset="assets/backgrounds/sky.png")
        project.backgrounds.append(ba)
        project.backgrounds.save(ba)
        projects.append(project)
        backgrounds.append(ba)
    old, new = projects
    old_ba, new_ba = backgrounds
    callbacks = []
    dispatcher = SimpleNamespace(suspended=nullcontext, notify_background_changed=lambda ba: None)
    monkeypatch.setattr(background_editor_screen, "get_dispatcher", lambda: dispatcher)
    screen = background_editor_screen.BackgroundEditorScreen()
    executor = ManualExecutor()
    screen._encoding._executor = executor
    screen.load_project(old)
    screen._compress_async(old_ba, old.background_image_path(old_ba), "tiled4", "median_cut", False,
                           then=lambda: callbacks.append("old"))
    old_result = executor.jobs[0][0]()

    screen.load_project(new)
    screen._compress_async(new_ba, new.background_image_path(new_ba), "tiled4", "median_cut", False,
                           then=lambda: callbacks.append("new"))
    before = [project.backgrounds.path_of(ba).read_bytes() for project, ba in zip(projects, backgrounds)]
    executor.finish(old_result)

    assert callbacks == []
    assert [project.backgrounds.path_of(ba).read_bytes() for project, ba in zip(projects, backgrounds)] == before
    assert len(executor.jobs) == 1
    executor.finish(executor.jobs[0][0]())
    assert callbacks == ["new"] and new_ba.encoding_is_current()
    assert new.backgrounds.path_of(new_ba).read_bytes() != before[1]
    assert old.backgrounds.path_of(old_ba).read_bytes() == before[0]


# ── Une validation qui plante ne bloque pas la file ──────────────────────────

def test_une_validation_qui_leve_est_un_echec_et_la_file_continue(qapp):
    executor, calls, failures = ManualExecutor(), [], []

    def commit(job, result):
        calls.append(job.ba.name)
        if job.ba.name == "a":
            raise OSError("disque plein")

    service = BackgroundEncodingService(commit=commit, executor=executor, auto_seconds=4.0)
    service.failed.connect(lambda b, message: failures.append((b.name, message)))
    first, second = _fond("a"), _fond("b")
    service.request(_job(first))
    service.request(_job(second))

    executor.finish({"tag": "a"})

    assert failures == [("a", "disque plein")]
    assert service.state(first) == EncodingState.FAILED
    assert len(executor.jobs) == 1                       # le fond suivant est parti
    executor.finish({"tag": "b"})
    assert calls == ["a", "b"]


def test_un_rappel_qui_leve_ne_bloque_pas_la_file(qapp):
    service, executor, committed = _service()
    first, second = _fond("a"), _fond("b")
    service.request(_job(first), then=lambda: 1 / 0)
    service.request(_job(second))

    with pytest.raises(ZeroDivisionError):
        executor.finish({"tag": "a"})

    assert len(executor.jobs) == 1                       # `_pump` a tourné malgré l'exception



def test_cancel_all_forgets_states_and_durations(qapp):
    service, executor, _committed = _service()
    ba = _fond()
    service.request(_job(ba))
    executor.finish({"tag": "a"}, seconds=3.0)
    assert service.last_seconds(ba) == 3.0
    service.cancel_all()
    assert service.last_seconds(ba) is None


# ── Un geste n'est pas retiré par l'inspecteur ────────────────────────────────

def test_l_inspecteur_qui_ne_veut_plus_rien_ne_retire_pas_la_demande_d_un_geste(qapp):
    service, executor, committed = _service()
    ba = _fond()
    called = []

    service.request(_job(ba), immediate=True, then=lambda: called.append("apres import"))
    service.withdraw(ba)                      # la minuterie de l'inspecteur : rien n'est « en attente » chez lui
    executor.finish({"tag": "import"})

    assert [r for _j, r in committed] == [{"tag": "import"}] and called == ["apres import"]


def test_withdraw_retire_la_demande_de_l_inspecteur(qapp):
    service, executor, committed = _service()
    ba = _fond()

    service.request(_job(ba, palettes_max=8))     # un curseur, pas un geste
    service.withdraw(ba)
    executor.finish({"tag": "curseur"})

    assert committed == []


# ── Rappels de même clé, adresses réutilisées ─────────────────────────────────

def test_un_rappel_de_meme_cle_n_est_appele_qu_une_fois(qapp):
    service, executor, _committed = _service()
    ba = _fond()
    called = []

    for palettes in (16, 12, 8):                      # un curseur tiré : une demande par pause
        service.request(_job(ba, palettes_max=palettes), then=lambda: called.append("resync"), then_key="resync")
    executor.finish({"tag": "a"})
    while executor.jobs:
        executor.finish({"tag": "b"})

    assert called == ["resync"]


def test_un_fond_qui_reprend_l_adresse_d_un_autre_n_herite_pas_de_son_etat(qapp):
    import weakref

    service, _executor, _committed = _service()
    gone, ba = _fond("gone"), _fond("new")
    service._owners[id(ba)] = weakref.ref(gone)       # l'adresse de `ba` était celle de `gone`
    service._states[id(ba)] = EncodingState.FAILED
    service._seconds[id(ba)] = 99.0

    assert service.state(ba) != EncodingState.FAILED and service.last_seconds(ba) is None
