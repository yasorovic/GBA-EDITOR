"""Le cycle de vie s'écrit en CINQ verbes, communs à tous les types — ROADMAP v0.16,
critère 3 (décision du 2026-09-25) : `:show() :hide() :activate() :deactivate() :destroy()`.

Une seule porte d'ÉCRITURE ; l'ÉTAT (`visible`, `active`) se lit en lecture seule. Ce
fichier tient les règles du contrat, pas une liste de fonctions : un type ajouté demain
est jugé par les mêmes tests.

`_PENDING` nomme ce qui reste À MIGRER (tranches suivantes : `window`, `layer`).
Il ne peut que rétrécir — chaque tranche retire ses lignes, et un test refuse une entrée
qui a déjà disparu du catalogue.
"""

from __future__ import annotations

from scripting.api import RUNTIME_API, RUNTIME_PROPS, REF_TYPE_TABLE

VERBS = ("show", "hide", "activate", "deactivate", "destroy")
STATES = ("visible", "active")
PAIRS = (("show", "hide"), ("activate", "deactivate"))
POOL_TYPES = {"actor", "sfx"}          # `destroy` : instances de POOL seulement

# Les portes de module qui écrivent « visible » / « actif » d'une chose nommée : le
# doublon que la grammaire unique refuse. Retirées avec la tranche de leur type.
_PENDING: set[str] = set()


def _verbs_of(type_: str) -> set[str]:
    return {k.split(":")[1] for k in RUNTIME_API if k.startswith(f"{type_}:")
            and k.split(":")[1] in VERBS}


# ── Le vocabulaire ────────────────────────────────────────────────────────

def test_un_type_declare_ses_verbes_par_paires():
    """`show` sans `hide` laisserait une chose qu'on ne peut plus défaire."""
    for type_ in REF_TYPE_TABLE:
        verbs = _verbs_of(type_)
        for on, off in PAIRS:
            assert (on in verbs) == (off in verbs), (type_, verbs)


def test_destroy_ne_s_applique_qu_aux_instances_de_pool():
    for type_ in REF_TYPE_TABLE:
        if "destroy" in _verbs_of(type_):
            assert type_ in POOL_TYPES, (
                f"{type_}:destroy — un élément statique (interface, fenêtre) est défini "
                f"au build, il ne se détruit pas")


def test_l_etat_du_cycle_de_vie_est_en_lecture_seule():
    """`visible` / `active` sur n'importe quel type : jamais d'écriture — les verbes sont
    la seule porte."""
    for key, prop in RUNTIME_PROPS.items():
        if key.split(".", 1)[1] in STATES:
            assert prop.read_only and prop.c_setter is None, key


def test_aucune_porte_de_module_n_ecrit_visible_ou_actif_hors_pending():
    """Une fonction de module qui prend « une chose » + un booléen d'affichage est
    la seconde porte. Seules celles de `_PENDING` restent, le temps de leur tranche."""
    doublons = {
        key for key in RUNTIME_API
        if "." in key and not key.startswith(("self.",))
        and key.split(".", 1)[1] in {"show", "hide", "set_visible", "set_active",
                                     "activate", "deactivate"}
    }
    assert doublons == _PENDING, doublons ^ _PENDING


def test_pending_ne_garde_que_ce_qui_existe_encore():
    assert _PENDING <= set(RUNTIME_API), _PENDING - set(RUNTIME_API)


# ── Ce que chaque verbe émet ──────────────────────────────────────────────

def _errors(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = BuildContext(actor_name="Cam", actor_names=["Foe"], sfx_names=["Bip"],
                       box_tag_names=["hb"], element_names=["Menu"])
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


def _c_body(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = CodegenContext(actor_name="Cam", actor_sym="Cam", anim_names=[],
                         sfx_names=["Bip"], music_names=[], global_names=set(),
                         const_names=set(), all_actor_syms=["Foe"],
                         element_names=["Menu"])
    code, _, _ = generate(parse(src), ctx)
    start = code.find("Cam_on_update(Actor* self) {")
    return [ln.strip() for ln in code[start:].split("\n}")[0].splitlines()[1:]
            if ln.strip()]


def test_les_verbes_d_un_acteur_se_traduisent_terme_a_terme():
    body = ("self:hide()\nself:show()\nself:deactivate()\nself:activate()\n"
            'actor:get("Foe"):deactivate()')
    assert _errors(body) == []
    assert _c_body(body) == [
        "actor_set_visible(self, 0);", "actor_set_visible(self, 1);",
        "actor_set_active(self, 0);", "actor_set_active(self, 1);",
        "actor_set_active(runtime_get_actor(ACTORNAME_FOE), 0);",
    ]


def test_les_verbes_d_une_boite_et_d_un_element_se_traduisent_sans_variable():
    body = ('self:collision_box("hb"):deactivate()\n'
            'local hb = self:collision_box("hb")\nhb:activate()\n'
            'interface:get("Menu"):hide()\ninterface:get("Menu"):show()')
    assert _errors(body) == []
    assert _c_body(body) == [
        "collision_box_set_active(actor_get_box(self, BOXTAG_HB), 0);",
        "int hb = actor_get_box(self, BOXTAG_HB);",
        "collision_box_set_active(hb, 1);",
        "ui_element_show(UIELEM_MENU, 0);", "ui_element_show(UIELEM_MENU, 1);",
    ]


def test_l_etat_se_lit_sur_chaque_type():
    body = ('if self.visible and self.active then self:hide() end\n'
            'local hb = self:collision_box("hb")\nif hb.active then hb:deactivate() end\n'
            'if interface:get("Menu").visible then self:hide() end')
    assert _errors(body) == []
    c = "\n".join(_c_body(body))
    assert "actor_get_visible(self)" in c and "actor_get_active(self)" in c
    assert "collision_box_get_active(hb)" in c
    assert "ui_element_is_visible(UIELEM_MENU)" in c


# ── Ce que le checker refuse ──────────────────────────────────────────────

def test_ecrire_l_etat_est_refuse_sur_chaque_type():
    for body, prop in (("self.visible = false", "self.visible"),
                       ("self.active = true", "self.active"),
                       ('local hb = self:collision_box("hb")\nhb.active = false',
                        "hb.active"),
                       ('interface:get("Menu").visible = false', "visible")):
        (msg,) = _errors(body)
        assert "lecture seule" in msg, (body, msg)


def test_un_type_refuse_un_verbe_qu_il_ne_declare_pas():
    # Une boîte s'active sans s'afficher ; un effet n'a aucun verbe ; un élément statique
    # ne se détruit pas.
    for body, verbe in (('local hb = self:collision_box("hb")\nhb:show()', "show"),
                        ('local p = sfx:play("Bip")\np:hide()', "hide"),
                        ('interface:get("Menu"):destroy()', "destroy")):
        errors = _errors(body)
        assert errors and any(verbe in m for m in errors), (body, errors)
