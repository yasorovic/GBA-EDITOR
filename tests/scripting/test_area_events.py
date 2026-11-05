"""Les événements d'Area : `on_area_enter/collide/exit(area, my_box)`, reçus par l'acteur qui touche une Area à déclencheur.

`area` est une RÉFÉRENCE d'Area (le rang dans `g_areas`, plus un), `my_box` une référence de boîte de `self` : le C passe un
`Area*` et un tag, le script reçoit les deux références, posées en tête de la fonction."""
from __future__ import annotations

from core.models.components import CollisionShapeComponent, ScriptComponent, TriggerComponent
from core.models.scene import Actor, Area, Scene
from scripting.api import AREA_EVENTS, EVENT_REGISTRY, KNOWN_EVENTS, RUNTIME_PROPS

TAGS = ["body", "door"]


def _lua(src: str, tags=TAGS):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Hero", anim_names=["idle"], box_tag_names=tags))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Hero", actor_sym="Hero", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Hero"]))
    return [e.message for e in errors if e.level == "error"], code


def test_les_trois_evenements_sont_connus_et_portent_area_puis_my_box():
    for ev in AREA_EVENTS:
        assert ev in KNOWN_EVENTS
        assert [p["name"] for p in EVENT_REGISTRY[ev]["params"]] == ["area", "my_box"]
        assert "Area* area, u8 my_box" in EVENT_REGISTRY[ev]["c_sig"]


def test_un_handler_se_compile_avec_les_deux_references_en_tete():
    errs, code = _lua(
        "function on_area_enter(area, my_box)\n"
        "  if area.tag == \"door\" and my_box.tag == \"body\" then\n"
        "    self:destroy()\n"
        "  end\n"
        "end\n")
    assert errs == []
    assert "void Hero_on_area_enter(Actor* self, Area* area_ptr, u8 my_box_tag)" in code
    assert "int area __attribute__((unused)) = area_ref(area_ptr);" in code
    assert "int my_box __attribute__((unused)) = actor_get_box(self, my_box_tag);" in code
    # Les tags se comparent à des constantes, comme pour une boîte d'acteur.
    assert "area_get_tag(area)" in code and "BOXTAG_DOOR" in code


def test_un_handler_peut_declarer_moins_de_parametres():
    errs, code = _lua("function on_area_exit(area)\n  self:hide()\nend\n")
    assert errs == []
    assert "area_ref(area_ptr)" in code
    errs, code = _lua("function on_area_collide()\n  self:hide()\nend\n")
    assert errs == [] and "Area* area" in code


def test_un_parametre_que_le_moteur_ne_passe_pas_est_refuse():
    errs, _code = _lua("function on_area_enter(area, my_box, other)\nend\n")
    assert any("does not pass" in e for e in errs)


def test_les_proprietes_de_l_area_sont_en_lecture_seule_et_inconnues_refusees():
    assert RUNTIME_PROPS["area.tag"].read_only and RUNTIME_PROPS["area.active"].read_only
    errs, _code = _lua("function on_area_enter(area, my_box)\n  area.active = false\nend\n")
    assert errs, "écrire une propriété en lecture seule doit être refusé"
    errs, _code = _lua("function on_area_enter(area, my_box)\n  local n = area.nope\nend\n")
    assert errs, "une propriété inconnue doit être refusée"


def test_un_tag_d_area_inconnu_est_refuse_a_la_compilation():
    errs, _code = _lua("function on_area_enter(area, my_box)\n  if area.tag == \"ghost\" then self:hide() end\nend\n")
    assert errs


def test_le_nom_area_n_est_pas_une_reference_dans_une_autre_fonction():
    """Le type `area` n'est tenu que le temps du handler : un `area` d'une autre fonction n'en hérite pas."""
    errs, code = _lua(
        "function on_area_enter(area, my_box)\n  self:hide()\nend\n"
        "function on_update()\n  local area = 3\n  if area > 1 then self:hide() end\nend\n")
    assert errs == []
    assert code.count("area_ref(area_ptr)") == 1       # posé dans le handler seulement
    assert "area = 3" in code


# ── Le validateur ────────────────────────────────────────────────────────

def test_un_handler_sans_area_a_declencheur_dans_la_scene_avertit(tmp_path):
    from core import validator
    from core.project import Project
    projet = Project.create(tmp_path / "Game", "Game")
    scripts = projet.user_library_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "Hero.lua").write_text("function on_area_enter(area, my_box)\nend\n", encoding="utf-8")
    hero = Actor(name="Hero", components=[CollisionShapeComponent(id="body", tag="body"),
                                          ScriptComponent(script="assets/scripts/Hero.lua")])
    scene = projet.scenes[0]
    scene.actors.append(hero)

    def messages():
        ctx = validator.ValidationContext(projet)
        validator._check_area_handlers(ctx, scene)
        return [m.message for m in ctx._msgs]

    assert any("on_area_enter will never be called" in m for m in messages())
    area = Area(name="Door")
    scene.areas.append(area)
    assert messages() == []                                                      # un déclencheur actif : rien à dire
    area.components = [c for c in area.components if not isinstance(c, TriggerComponent)]
    assert any("never be called" in m for m in messages())                      # une Area muette ne compte pas
