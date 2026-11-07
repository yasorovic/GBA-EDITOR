"""La passe de contacts émise par scène : qui y entre, et la taille de sa liste. Le cycle de vie d'un contact (enter,
collide, exit, désactivé, détruit, emplacement réoccupé) est exécuté par la sonde `tests/native/actor_box_probe.c`, la
parité posé / spawné par `test_parity_contacts.py`."""
from __future__ import annotations

import re

from core.models.components import CollisionShapeComponent
from core.models.scene import Actor


def _lignes(tmp_path, acteurs, scripts, reagit):
    """La passe émise pour une vraie scène de ces acteurs posés (types 1, 2, ...), `scripts` alignés sur eux."""
    from codegen.runtime_codegen.physics.contacts import contact_tick_lines
    from core.models.scene import Scene
    from core.project import Project
    scene = Scene(name="S", actors=list(acteurs))
    p = Project(tmp_path)
    p.scenes.items = [scene]
    return "\n".join(contact_tick_lines(p, scene, [(a, None) for a in acteurs], [], None, scripts,
                                        lambda s, ev: s in reagit and ev == "on_collision_enter"))


def _acteur(nom, tag="body"):
    return Actor(name=nom, components=[CollisionShapeComponent(w=8, h=8, tag=tag)])


def test_sans_script_qui_reponde_aucune_passe(tmp_path):
    assert _lignes(tmp_path, [_acteur("A"), _acteur("B")], [None, None], set()) == ""


def test_un_couple_n_entre_que_si_un_des_deux_types_reagit(tmp_path):
    # Types 1 (A, scripté), 2 (B) et 3 (C) : A rencontre ses propres copies, B et C ; B et C, aucun script, ne se testent
    # pas entre eux.
    code = _lignes(tmp_path, [_acteur("A"), _acteur("B"), _acteur("C")], ["A", None, None], {"A"})
    allowed = re.search(r"_ct_allowed\[3\]\[3\][^=]*=\{(.*)\};", code)[1]
    assert allowed == "{1,1,1},{1,0,0},{1,0,0}"
    assert "_ct_ki[4]" in code and "={255,0,1,2};" in code


def test_la_liste_des_contacts_est_bornee_par_les_paires_possibles(tmp_path):
    from codegen.runtime_codegen.physics.contacts import CONTACT_CAPACITY
    petit = _lignes(tmp_path / "petit", [_acteur("A"), _acteur("B"), _acteur("C")], ["A", None, None], {"A"})
    assert "static Contact _ct_prev[3] EWRAM_BSS, _ct_cur[3] EWRAM_BSS;" in petit      # 3 acteurs : 3 paires au plus
    beaucoup = [_acteur(f"A{i}") for i in range(20)]                                     # 190 paires possibles
    grand = _lignes(tmp_path / "grand", beaucoup, [a.name for a in beaucoup], {a.name for a in beaucoup})
    assert f"static Contact _ct_prev[{CONTACT_CAPACITY}] EWRAM_BSS" in grand


def test_la_matrice_des_tags_retire_un_couple(tmp_path):
    from codegen.runtime_codegen.physics.contacts import contact_tick_lines
    from core.models.scene import Scene
    from core.models.settings import pair_key
    from core.project import Project
    a, b = _acteur("A", tag="hero"), _acteur("B", tag="ghost")
    scene = Scene(name="S", actors=[a, b])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.settings.collision_disabled_pairs = [pair_key("hero", "ghost")]
    code = "\n".join(contact_tick_lines(p, scene, [(a, None), (b, None)], [], None, ["A", None],
                                       lambda s, ev: s == "A"))
    # A (hero) rencontre ses copies ; le couple hero / ghost est retiré par la matrice.
    assert re.search(r"_ct_allowed\[1\]\[1\][^=]*=\{\{1\}\};", code)
