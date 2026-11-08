"""Le script d'une Area : une famille de propriétaire à part (« area »), où `self` est la référence de l'Area et où les contacts
des acteurs qui la touchent arrivent par `on_actor_enter/collide/exit(other, other_box)`."""
from __future__ import annotations

from scripting.api import KNOWN_AREA_EVENTS, KNOWN_EVENTS
from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.completion import _member_candidates
from scripting.parser import parse


def _errors(src: str, owner_kind: str = "area") -> list[str]:
    ctx = BuildContext(actor_name="Door", owner_kind=owner_kind, actor_names=[], box_tag_names=["body"])
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


def _c(src: str) -> str:
    ctx = CodegenContext(actor_name="Door", actor_sym="Sc_Door", anim_names=[], sfx_names=[], music_names=[],
                         global_names=set(), const_names=set(), all_actor_syms=[], scene_sym="Sc",
                         owner_kind="area", area_ref=3)
    return generate(parse(src), ctx)[0]


def test_les_evenements_d_une_area():
    assert KNOWN_AREA_EVENTS == ["on_start", "on_update", "on_actor_enter", "on_actor_collide", "on_actor_exit"]
    assert not any(ev.startswith("on_actor_") for ev in KNOWN_EVENTS)    # un acteur ne les reçoit pas


def test_self_est_l_area_et_ses_membres_sont_ceux_du_type_area():
    src = ("function on_update()\n  if self.active then self.position = vec2(1, 2) end\n"
           "  local n = self.name\n  self:deactivate()\nend\n")
    assert _errors(src) == []
    code = _c(src)
    assert "static const int self __attribute__((unused)) = 3;" in code     # la référence de CETTE Area : rang + 1
    assert "area_get_active(self)" in code and "area_set_position(self, (Vec2){1, 2});" in code
    assert "area_set_active(self, 0);" in code
    assert "void Sc_Door_area_on_update(void) {" in code


def test_une_methode_d_acteur_sur_self_est_refusee():
    assert _errors("function on_update()\n  self:play_anim(\"idle\")\nend\n")


def test_les_contacts_recoivent_l_acteur_et_sa_boite():
    src = ("function on_actor_enter(other, other_box)\n  if other_box.tag == \"body\" then other:destroy() end\n"
           "  if self:overlaps(other) then other.velocity = vec2(0, 0) end\nend\n")
    assert _errors(src) == []
    code = _c(src)
    assert ("void Sc_Door_area_on_actor_enter(Actor* other __attribute__((unused)), "
            "u8 other_box_tag __attribute__((unused))) {") in code
    assert "int other_box __attribute__((unused)) = actor_get_box(other, other_box_tag);" in code
    assert "area_overlaps_actor(self, other)" in code


def test_les_points_d_entree_non_ecrits_ont_un_corps_vide():
    code = _c("function on_start()\nend\n")
    assert "void Sc_Door_area_on_update(void) {}" in code
    assert "void Sc_Door_area_on_actor_exit(Actor* other" in code


def test_un_parametre_que_le_moteur_ne_passe_pas_est_refuse():
    assert any("does not pass" in e for e in _errors("function on_actor_enter(other, my_box)\nend\n"))


def test_un_acteur_ne_peut_pas_ecrire_on_actor_enter():
    assert any("not available for a actor script" in e
               for e in _errors("function on_actor_enter(other)\nend\n", owner_kind="actor"))


def test_une_area_ne_peut_pas_ecrire_un_evenement_d_acteur():
    assert any("not available for a Area script" in e for e in _errors("function on_area_enter(area)\nend\n"))


def test_la_completion_de_self_propose_les_membres_de_l_area():
    assert {c.insert for c in _member_candidates("self", ":", None, "area")} == {"activate", "deactivate", "overlaps"}
    fields = {c.insert for c in _member_candidates("self", ".", None, "area")}
    assert {"name", "tag", "active", "position", "bounds"} <= fields
    assert "velocity" not in fields


def test_le_validateur_avertit_d_un_script_d_area_sans_declencheur(tmp_path):
    from core import validator
    from core.models.components import ScriptComponent, TriggerComponent
    from core.models.scene import Area
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Door.lua").write_text("function on_actor_enter(other)\nend\n", encoding="utf-8")
    porte = Area(name="Door")
    porte.components.append(ScriptComponent(script="assets/scripts/Door.lua"))
    scene = projet.scenes[0]
    scene.areas.append(porte)

    def messages():
        ctx = validator.ValidationContext(projet)
        validator._check_area_handlers(ctx, scene)
        return [m.message for m in ctx._msgs]

    assert messages() == []                                       # déclencheur actif : le script entendra les contacts
    porte.components = [c for c in porte.components if not isinstance(c, TriggerComponent)]
    assert any("on_actor_enter will never be called" in m and "Door" in m for m in messages())
