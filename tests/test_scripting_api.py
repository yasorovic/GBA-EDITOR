"""Les trois défauts de l'API scriptée qui ne se voyaient qu'au `make`, ou pas
du tout.

Ils ont en commun de ne produire AUCUN message à l'endroit de la faute : une
API retirée qui continuait de marcher, une constante émise mais introuvable
dans l'unité de compilation, un réglage nommé retombé sur un entier nu. C'est
la définition d'un test ici (cf. `tests/` dans ARCHITECTURE) — une erreur
silencieuse, pas une exception.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent


def _lua(src: str, **ctx_kw):
    """Parse + check + génère, avec un contexte de build minimal."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball", anim_names=["idle"], **ctx_kw))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"]))
    return errors, code


def _errors(src: str, **ctx_kw) -> list[str]:
    return [e.message for e in _lua(src, **ctx_kw)[0] if e.level == "error"]


# ── T6 : actor.spawn rend un Actor* (ROADMAP v0.17) ──────────────────

def test_spawn_local_est_un_actor_pointer():
    """`local b = actor:spawn(...)` tient un `Actor*` (l'instance née), pas un
    int : `b:destroy()` doit chaîner et `if b then` tester le pool plein (NULL).
    Le local était typé `int` avant T6 — un -1 toujours vrai."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = ("function on_update(self)\n"
           "  local b = actor:spawn(\"Bullet\", vec2(10, 20))\n"
           "  if b then b:destroy() end\n"
           "end\n")
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Turret", actor_sym="Turret", scene_sym="Play",
        anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Turret"]))
    assert "Actor* b = spawn_Play_Bullet(" in code, code


# ── 1. Une API retirée doit être RETIRÉE, sur tous les récepteurs ──


def _setter_spellings() -> list[tuple[str, str]]:
    """(propriété, orthographe en méthode qui tomberait sur sa fonction C).

    `codegen._invoke` traduit une méthode inconnue en `actor_<méthode>(récepteur,
    ...)`. Pour toute propriété dont le setter C s'appelle `actor_set_<champ>`,
    l'orthographe `self:set_<champ>(v)` produit donc du C qui compile et qui
    MARCHE. Dérivé du catalogue, ce cas de test suit chaque propriété ajoutée."""
    from scripting.api import RUNTIME_PROPS

    out = []
    for name, p in RUNTIME_PROPS.items():
        if p.c_setter and p.c_setter.startswith("actor_set_"):
            out.append((name, "set_" + p.c_setter[len("actor_set_"):]))
    return out


@pytest.mark.parametrize("prop,method", _setter_spellings(),
                         ids=[m for _, m in _setter_spellings()])
def test_aucune_orthographe_en_methode_ne_double_une_propriete(prop, method):
    """Un état s'écrit d'UNE façon. `self:set_frame(0)` doit être refusé à la
    ligne fautive — sinon il traverse en simple avertissement, le repli du
    codegen tombe sur `actor_set_frame`, et l'ancienne API survit sans
    documentation à côté de `self.frame = 0`."""
    errs = _errors(f"function on_update(self)\n self:{method}(0)\nend\n")
    assert errs, (f"self:{method}() n'est pas refusé : il double {prop} "
                  f"et le C émis compile.")


def test_orthographe_retiree_bloque_sur_self():
    """Retrait sec (ROADMAP v0.16, REMOVED_API vidé) : une orthographe retirée
    est bloquée comme « méthode inconnue », sans guide de migration. Le blocage
    lui-même ne dépend pas de REMOVED_API — un « : » ne peut désigner qu'une
    méthode du catalogue."""
    errs = _errors("function on_update(self)\n self:set_frame(0)\nend\n")
    assert errs and "unknown" in errs[0].lower()


def test_orthographe_retiree_bloque_aussi_sur_un_autre_recepteur():
    """`other:set_position(p)` émettait `actor_set_position(other, p)` — du C qui
    compile et marche. Il reste bloqué sur un récepteur autre que `self`, par la
    même règle : le « : » n'a pas de méthode à traduire hors du catalogue."""
    errs = _errors("function on_collide(self, other)\n"
                   " other:set_position(vec2(1, 2))\nend\n")
    assert errs and "unknown" in errs[0].lower()


def test_methode_inconnue_signalee_sur_tout_recepteur():
    """Un `:` ne peut désigner qu'une méthode du catalogue : hors de lui, il n'y
    a rien à traduire, et `_invoke` inventerait un `actor_nawak(other, 1)`."""
    errs = _errors("function on_collide(self, other)\n other:nawak(1)\nend\n")
    assert errs and "other:nawak" in errs[0]


def test_methode_valide_sur_un_autre_recepteur_reste_valide():
    """La validation ne doit pas devenir un refus : une méthode du catalogue
    s'appelle sur n'importe quel Actor* nommé."""
    errs, code = _lua("function on_collide(self, other)\n"
                      " other:move(vec2(1, 0), 2)\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_move(other," in code


def test_nom_de_ressource_du_recepteur_refuse():
    """`other:play_anim("idle")` : le nom est résolu contre le SpriteAsset de
    l'acteur qui EXÉCUTE (`anim_constant(ctx.actor_sym, ...)`), donc le C émis
    citerait l'animation d'un autre acteur — crédible et faux."""
    errs = _errors("function on_collide(self, other)\n"
                   " other:play_anim('idle')\nend\n")
    assert errs and "self" in errs[0]


# ── 2. Les constantes vivent dans les DEUX en-têtes ────────────────


def test_constantes_denumeration_generees_pour_les_unites_script():
    """Les unités de scène et d'acteur voient les `#define` d'énums GÉNÉRÉS dans
    `runtime_api.h` (plus redéclarés à la main dans `runtime_api_inline.h`). Le
    contrat : chaque constante du catalogue est reprise par la génération —
    sinon le codegen l'émettrait et le `make` échouerait sur un identifiant
    inconnu."""
    from scripting.api import HARDWARE_ENUMS
    from codegen.runtime_codegen.api_prototypes import build_enum_defines

    generated = {l.split()[1] for l in build_enum_defines()}
    missing = sorted({
        c for table in HARDWARE_ENUMS.values() for c in table.values()
        if c not in generated
    })
    assert missing == [], f"constantes non générées : {missing}"


def test_les_valeurs_denum_saccordent_avec_le_moteur():
    """api.py tient désormais la valeur de chaque énum ; `gba_engine.h` en
    redéfinit certaines à la main côté moteur. main.c voit les deux — une valeur
    divergente serait une redéfinition bruyante ET un décalage silencieux côté
    script. Ce test la nomme avant le compilateur (miroir du garde-fou de
    `validator._check_api_prototypes`)."""
    from scripting.api import hardware_enum_defines

    engine = (REPO_DIR / "runtime" / "include" / "gba_engine.h").read_text(
        encoding="utf-8", errors="ignore")

    def engine_value(name: str):
        m = re.search(r"^\s*#\s*define\s+" + re.escape(name) + r"\s+(-?\d+)\b", engine, re.M)
        return int(m.group(1)) if m else None

    for sym, value in hardware_enum_defines():
        ev = engine_value(sym)
        if ev is not None:
            assert ev == value, f"{sym} vaut {value} dans api.py et {ev} dans le moteur"


def test_le_c_emis_cite_la_constante_pas_le_nombre():
    _, code = _lua("function on_update(self)\n"
                   " window:get('HudFrame'):set_layer(1, true)\n"
                   " blend:set_layer('top', 2, true)\nend\n",
                   window_names=["HudFrame"])
    assert "window_set_layer(WIN_HUDFRAME," in code
    assert "blend_set_layer(BLD_SIDE_TOP," in code


# ── 3. Une propriété d'énumération s'écrit et se compare par son NOM ─


def test_propriete_denumeration_ecrite_par_son_nom():
    errs, code = _lua("function on_update(self)\n"
                      " self.obj_mode = 'window'\n"
                      " blend.mode = 'alpha'\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_set_obj_mode(self, OBJ_MODE_WINDOW)" in code
    assert "blend_set_mode(BLD_MODE_ALPHA)" in code


def test_propriete_denumeration_comparee_par_son_nom():
    """Sans traduction, la comparaison partirait sur une chaîne C là où le getter
    rend un entier : gcc accepte, et le test est toujours faux."""
    errs, code = _lua("function on_update(self)\n"
                      " if blend.mode == 'alpha' then blend.mode = 'none' end\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "blend_get_mode() == BLD_MODE_ALPHA" in code


def test_entier_nu_refuse_sur_une_propriete_denumeration():
    errs = _errors("function on_update(self)\n self.obj_mode = 2\nend\n")
    assert errs and "name" in errs[0]


def test_valeur_inconnue_refusee():
    errs = _errors("function on_update(self)\n blend.mode = 'alfa'\nend\n")
    assert errs and "alfa" in errs[0]


def test_aucune_enumeration_materielle_nest_orpheline():
    """Une table de `HARDWARE_ENUMS` que plus aucun paramètre ni propriété ne cite
    est du vocabulaire mort — et son domaine oblige quand même checker et codegen
    à garder une entrée. C'est ce qui est arrivé à OBJ_MODES et BLEND_MODES le
    jour où leurs réglages sont devenus des propriétés."""
    from scripting.api import RUNTIME_API, RUNTIME_PROPS, HARDWARE_ENUMS

    cites = {p.domain for f in RUNTIME_API.values() for p in f.params}
    cites |= {p.domain for p in RUNTIME_PROPS.values()}
    orphelins = sorted(set(HARDWARE_ENUMS) - cites)
    assert orphelins == [], f"énumérations citées par personne : {orphelins}"


def test_aucune_fonction_de_module_ne_contourne_lacquisition():
    """Garde-fou critère 5 (ROADMAP v0.16, amendement « module fabrique, type
    opère ») : une fonction de MODULE (`module.fonction`, PAS `type:méthode`)
    ne doit jamais agir sur une chose nommée en la recevant en argument
    (`list.index("Menu")`, avant migration) ni recevoir une référence déjà
    acquise (`interface.move(element, ...)`) — les deux détours qui
    contournaient `module.get("Nom")` puis `ref:méthode()` / `ref.propriété`.

    Sans ce test, la règle retombe en trois versions dès la prochaine
    fonction ajoutée au catalogue : rien d'autre ne l'empêche.

    `ALLOWED` liste les verbes établis qui GÈRENT, CRÉENT ou ACQUIÈRENT un
    système singleton ou un pool (cf. ARCHITECTURE, « Module, type,
    instance ») — le seul cas où un module reçoit légitimement un nom.
    Ajouter une entrée y est une décision consciente, jamais un oubli."""
    from scripting.api import RUNTIME_API, REF_TYPES

    NAMED_INSTANCE_DOMAINS = {
        "actor", "sfx", "music", "scene", "camera", "ui_element",
        "prefab", "font", "palette", "win_region",
    }
    ALLOWED = {
        "actor.spawn", "actor.get", "interface.get", "sfx.play",
        "music.play", "music.jingle", "music.fade_to", "music.cut_to",
        "scene.switch", "camera.switch", "text.set_font", "window.get",
        "palette.set_bg", "palette.set_obj",
    }
    ref_types = set(REF_TYPES)

    violations = []
    for key, f in RUNTIME_API.items():
        if ":" in key or key in ALLOWED:
            continue   # méthode sur un type, ou verbe établi
        for p in f.params:
            if p.domain in NAMED_INSTANCE_DOMAINS or p.ptype in ref_types:
                violations.append(f"{key} (param {p.name})")
                break

    assert violations == [], (
        "fonction(s) de module qui agissent sur une chose nommée sans passer "
        f"par l'acquisition : {violations} — router par une référence "
        "(module.get(...) puis ref:méthode()/ref.propriété), ou ajouter "
        "l'entrée à ALLOWED si c'est un verbe de gestion/création légitime.")


# ── 4. Un état, une orthographe ────────────────────────────────────
# La direction s'écrivait trois fois pour un seul couple `dir_x`/`dir_y` : un
# vec2, une boussole nommée, et un entier 0-8 en lecture — qu'on POSAIT par un
# nom et qu'on RELISAIT en nombre.


def test_la_direction_secrit_des_deux_facons_sur_une_seule_propriete():
    errs, code = _lua("function on_update(self)\n"
                      " self.direction = \"north_east\"\n"
                      " self.direction = vec2(1, -1)\n"
                      " self.flip_h = self.direction.x < 0\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    # Deux portes C pour un seul état : l'index de boussole, et le vecteur.
    assert "actor_set_dir(self, DIR_NORTH_EAST)" in code
    assert "actor_set_direction(self, (Vec2){1, (-1)})" in code
    assert "actor_get_direction(self).x" in code


def test_la_direction_se_compare_par_son_nom():
    """Le getter ordinaire rend un `Vec2`, que le C ne sait pas comparer : sans
    la porte nommée, `self.direction == "west"` produirait du C invalide."""
    errs, code = _lua('function on_update(self)\n'
                      ' if self.direction == "west" then self.frame = 0 end\nend\n')
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_get_dir(self) == DIR_WEST" in code


@pytest.mark.parametrize("old", [
    'self:set_dir("north")',
    "self:get_dir()",
    "self:set_auto_dir(true)",
    "self:on_ground()",
])
def test_les_anciennes_orthographes_sont_bloquees(old):
    """Retrait sec (ROADMAP v0.16, REMOVED_API vidé) : une orthographe retirée
    reste refusée — comme « méthode inconnue » — mais ne guide plus vers la
    propriété. Le blocage tient au « : », pas à REMOVED_API."""
    errs = _errors(f"function on_update(self)\n local x = {old}\nend\n")
    assert errs and "unknown" in errs[0].lower()


def test_auto_dir_se_lit_maintenant():
    """L'ancien `set_auto_dir` n'avait pas de getter : un script qui voulait le
    basculer devait tenir son propre drapeau à côté de celui du moteur."""
    errs, code = _lua("function on_update(self)\n"
                      " if self.auto_dir then self.auto_dir = false end\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_get_auto_dir(self)" in code and "actor_set_auto_dir(self, 0)" in code


def test_grounded_est_en_lecture_seule():
    errs = _errors("function on_update(self)\n self.grounded = true\nend\n")
    assert errs and "read-only" in errs[0]


def test_le_getter_dauto_dir_existe_en_c():
    """Une propriété sans lecture n'en est pas une — et le garde-fou des
    prototypes ne voit que ce qui est déjà dans `gba_engine.h`, donc il n'aurait
    pas signalé l'absence de celle-ci."""
    from scripting.api import RUNTIME_PROPS

    facade = (REPO_DIR / "runtime" / "include" / "runtime_api_inline.h").read_text(
        encoding="utf-8", errors="ignore")
    for name, p in RUNTIME_PROPS.items():
        for fn in (p.c_getter, p.c_setter, p.c_getter_named, p.c_setter_named):
            if fn and fn.startswith("actor_"):
                assert re.search(r"\b" + re.escape(fn) + r"\s*\(", facade), (
                    f"{name} : {fn}() n'existe pas dans runtime_api_inline.h")


# ── 5. L'état d'une image se vérifie DANS son sprite ───────────────


def _ui_errors(src: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    ctx = BuildContext(actor_name="HUD", element_names=["coeur_1", "curseur"],
                       ref_kinds={"coeur_1": "image", "curseur": "image"},
                       image_states={"coeur_1": ["plein", "vide"],
                                     "curseur": ["on", "off"]})
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


def test_etat_dimage_valide():
    assert _ui_errors('function on_update(self)\n'
                      ' interface:get("coeur_1").state = "vide"\nend\n') == []


def test_l_etat_se_nomme_aussi_par_un_local_et_se_compare():
    assert _ui_errors('function on_update(self)\n'
                      ' local c = interface:get("coeur_1")\n'
                      ' c.state = "plein"\n'
                      ' if c.state == "vide" then c.state = "plein" end\nend\n') == []


def test_un_etat_d_image_ecrit_sur_une_image_inconnue_du_build_est_refuse():
    """Un paramètre, un local réaffecté : on ne sait pas dans quel sprite chercher l'état,
    et deviner la constante écrirait l'état d'une autre image."""
    errs = _ui_errors('function on_update(self)\n'
                      ' local c = interface:get("coeur_1")\n'
                      ' local c = interface:get("curseur")\n'
                      ' c.state = "on"\nend\n')
    assert len(errs) == 1 and "does not know which image" in errs[0]


def test_etat_dimage_inconnu_refuse_avec_les_etats_du_bon_sprite():
    """« vide » est valide sur coeur_1 et pas sur curseur : l'ensemble valide se
    lit sur l'IMAGE citée, jamais sur le projet entier."""
    errs = _ui_errors('function on_update(self)\n'
                      ' interface:get("curseur").state = "vide"\nend\n')
    assert errs and "on, off" in errs[0]


def test_image_inconnue_ne_produit_quune_seule_erreur():
    errs = _ui_errors('function on_update(self)\n'
                      ' interface:get("nawak").state = "vide"\nend\n')
    assert len(errs) == 1 and "not found" in errs[0]


# ── 6. L'écran de référence décrit l'API qui existe ────────────────


def test_le_json_de_reference_ne_decrit_que_lapi_vivante():
    """`api_reference.json` a décrit pendant des mois `display.print` et
    `text.draw_box`. La réconciliation les cachait ; le fichier mentait quand
    même, et personne ne le relisait."""
    from scripting import api_reference

    api_reference.get_categories()
    assert sorted(set(api_reference.STALE)) == []


def test_toute_entree_du_catalogue_est_rangee_et_aucune_ne_finit_en_vrac():
    """`doc_anchor` (pas `label`) identifie une entrée : les propriétés
    l'affichent désormais sous une forme COURTE (`position(Vec2)`, sans son
    préfixe `self.`), donc parser le libellé ne retrouverait plus le nom
    complet du catalogue — l'ancre, dérivée du nom complet, si."""
    from scripting import api_reference
    from scripting.api import RUNTIME_API, RUNTIME_PROPS

    cats = api_reference.get_categories()
    anchors = {e["doc_anchor"] for c in cats for e in c["entries"]}
    catalogue = {name: name.replace(":", "-").replace(".", "-")
                 for name in (*RUNTIME_API, *RUNTIME_PROPS)}
    manquants = {name for name, anchor in catalogue.items() if anchor not in anchors}
    assert manquants == set(), f"absents de l'écran : {sorted(manquants)}"
    assert not any(c["name"] == "Other" for c in cats), (
        "une entrée est tombée dans le fourre-tout : donne-lui une catégorie "
        "dans api_reference.json ou dans _PROP_HOME")
    assert all(c["entries"] for c in cats), "catégorie sans entrée"


def test_lordre_du_json_gouverne_lecran():
    """Une catégorie vidée par le filtre gardait son en-tête mais perdait sa
    place : « Transform », première du fichier, se recréait en dernier une fois
    ses cinq entrées retirées."""
    import json

    from scripting import api_reference

    brut = json.loads((REPO_DIR / "editor" / "scripting" / "api_reference.json")
                      .read_text(encoding="utf-8"))
    attendu = [c["name"] for c in brut["categories"]]
    rendu   = [c["name"] for c in api_reference.get_categories()]
    assert rendu == [n for n in attendu if n in rendu]
    assert rendu[0] == "Transform"


def test_les_huit_sections_ne_perdent_aucune_entree():
    """Le rangement (ROADMAP v0.16) regroupe les 24 catégories en 8 sections
    sans rien perdre : chaque entrée du catalogue atterrit dans une section, et
    aucune section « orpheline » (un nom de catégorie brut) n'apparaît — signe
    qu'une catégorie a échappé à `SECTIONS`."""
    from scripting import api_reference

    secs = api_reference.get_sections()
    assert [s["label"] for s in secs] == [k for k, _ in api_reference.SECTIONS], (
        "8 sections attendues, dans l'ordre de SECTIONS — une section orpheline "
        "signale une catégorie hors de SECTIONS")

    n_sec = sum(len(g["entries"])
                for s in secs for side in ("iteration", "engine") for g in s[side])
    n_cat = sum(len(c["entries"]) for c in api_reference.get_categories())
    assert n_sec == n_cat, f"{n_cat - n_sec} entrées perdues au rangement"


def test_la_couche_moteur_se_replie_la_bonne():
    """Le drapeau moteur (« Aller plus loin ») est per-entrée, plus fin que la
    catégorie : `sfx.play` reste itération quand `sound_box.set_state` est
    moteur, tous deux dans « Le son »."""
    from scripting import api_reference

    secs = {s["label"]: s for s in api_reference.get_sections()}
    def keys(groups):
        return {e["label"].split("(")[0].strip() for g in groups for e in g["entries"]}

    son = secs["scrsb.sec.sound"]
    assert "sfx:play" in keys(son["iteration"])
    assert "sound_box:set_state" in keys(son["engine"])


    # Le décor a une face itération ET une face moteur pour le MÊME calque.
    decor = secs["scrsb.sec.scenery"]
    assert "background_layer:show" in keys(decor["iteration"])
    assert "map" in keys(decor["engine"])      # propriété `background_layer.map`, libellé court



# ── 7. L'identité d'un acteur se cite par son nom ──────────────────
# `self.tag` rendait un entier opaque qu'aucune écriture Lua ne permettait de
# nommer : sa doc disait « utile pour identifier other » sans dire comment.


def _tag_lua(src: str):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball",
                                        actor_names=["PADDLE_PL"],
                                        prefab_names=["Bullet"]))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball", "PADDLE_PL"]))
    return [e.message for e in errors if e.level == "error"], code


def test_le_tag_se_compare_par_le_nom_de_lacteur():
    errs, code = _tag_lua('function on_collide(self, other)\n'
                          ' if other.name == "PADDLE_PL" then self:destroy() end\nend\n')
    assert errs == []
    assert "actor_get_name(other) == ACTOR_PADDLE_PL" in code


def test_le_tag_accepte_aussi_un_prefab():
    """`headers.py` émet un ACTOR_* par acteur de scène ET par prefab poolé."""
    errs, code = _tag_lua('function on_collide(self, other)\n'
                          ' if other.name == "Bullet" then self:destroy() end\nend\n')
    assert errs == []
    assert "ACTOR_BULLET" in code


def test_identite_inconnue_refusee():
    """Sans `#define`, le C généré cite un identifiant qui n'existe pas — même
    sévérité que pour une scène ou un prefab inconnus."""
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' if other.name == "Nawak" then end\nend\n')
    assert errs and "no actor or prefab" in errs[0]


def test_le_tag_ne_se_compare_pas_a_un_nombre():
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' if other.name == 0 then end\nend\n')
    assert errs and "by its name" in errs[0]


def test_les_messages_nomment_le_recepteur_ecrit():
    """Le catalogue range les propriétés d'actor sous `self.<champ>` : une clé,
    pas une restriction. Un message qui reprendrait la clé citerait à l'auteur
    une ligne qu'il n'a pas écrite."""
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' other.name = "Bullet"\nend\n')
    assert errs and errs[0].startswith("other.name")


def test_aucun_domaine_declare_nest_orphelin():
    """Un `DOMAIN_*` que ni un paramètre ni une propriété ne cite est du
    vocabulaire mort — et il oblige quand même checker et codegen à garder une
    entrée pour satisfaire `validator._check_api_domains`. C'était le cas de
    `tag`, gardé au motif faux que `ACTOR_*` serait un espace ouvert (c'est
    `BOXTAG_*` qui l'est)."""
    from scripting.api import ALL_DOMAINS, RUNTIME_API, RUNTIME_PROPS

    cites = {p.domain for f in RUNTIME_API.values() for p in f.params if p.domain}
    cites |= {p.domain for p in RUNTIME_PROPS.values() if p.domain}
    assert sorted(ALL_DOMAINS - cites) == []


def test_les_deux_consommateurs_couvrent_tous_les_domaines():
    """Pendant Python de `validator._check_api_domains`, qui ne tourne qu'au
    build d'un projet : un domaine inconnu du checker n'est pas vérifié, et
    inconnu du codegen il part en littéral C."""
    from scripting.api import ALL_DOMAINS
    from scripting import checker, codegen

    assert sorted(ALL_DOMAINS - checker.covered_domains()) == []
    assert sorted(ALL_DOMAINS - codegen.covered_domains()) == []
    assert sorted(checker.covered_domains() - ALL_DOMAINS) == []
    assert sorted(codegen.covered_domains() - ALL_DOMAINS) == []


# ── 8. Les helpers de « juiciness » ne composent que l'API existante ──
# squash/stretch/bounce/shake/flash/blink/pulse/pop/wobble : neuf `self:`
# stateless (t, duration, amount) qui n'écrivent que sprite_scale/
# sprite_offset/sprite_rotation/pal/visible — donc reproductibles à la main.

JUICE_METHODS = [
    "squash", "stretch", "bounce", "shake",
    "flash", "blink", "pulse", "pop", "wobble",
]


def test_les_neuf_helpers_de_juiciness_compilent():
    errs, code = _lua(
        "function on_update(self)\n"
        + "\n".join(f" self:{m}(3, 8, 10)" for m in JUICE_METHODS)
        + "\nend\n",
        affine_transform=True,
    )
    assert errs == []
    for m in JUICE_METHODS:
        assert f"actor_{m}(self, 3, 8, 10)" in code


def test_les_neuf_helpers_existent_en_c():
    """Même garde-fou que `test_le_getter_dauto_dir_existe_en_c` : le checker
    ne voit que le catalogue Python, jamais l'en-tête C — un `c_func` sans
    implémentation compilerait en `undefined reference` seulement au `make`."""
    from scripting.api import RUNTIME_API

    facade = (REPO_DIR / "runtime" / "include" / "runtime_api_inline.h").read_text(
        encoding="utf-8", errors="ignore")
    for m in JUICE_METHODS:
        fn = RUNTIME_API[f"actor:{m}"].c_func
        assert re.search(r"\b" + re.escape(fn) + r"\s*\(", facade), (
            f"self:{m} : {fn}() n'existe pas dans runtime_api_inline.h")



# ── 9. Les portes du son : une référence, et les graduations ──────────
# ROADMAP v0.8.6. Deux erreurs silencieuses possibles ici : un `pas:set_volume`
# traduit en `actor_set_volume(pas, …)` — le repli des méthodes d'actor, qui ne
# compile pas mais ne dit rien avant le `make` —, et un pourcentage envoyé tel
# quel dans un registre qui compte en 0–255, en 0–1024 ou en facteur 6.10. Le
# second ne fait jamais échouer le build : il règle juste au mauvais niveau,
# comme la musique qui jouait à 25 % avant la v0.8.5.


def _lua_sfx(src: str):
    """Comme `_lua`, mais avec un Sfx dans le contexte des DEUX côtés."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball", anim_names=["idle"],
                                        sfx_names=["Pas"]))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=["Pas"],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"],
        sfx_volumes={"Pas": 100}))
    return [e.message for e in errors if e.level == "error"], code


CINQ_METHODES = '''function on_update(self)
  local pas = sfx:play("Pas")
  pas:set_volume(80)
  pas:set_pitch(120)
  pas:set_panning(-40)
  if pas:playing() then pas:stop() end
end
'''


def test_la_reference_deffet_porte_son_type_et_ses_cinq_methodes():
    errs, code = _lua_sfx(CINQ_METHODES)
    assert errs == []
    # `hold = 1` : la référence est tenue, donc le canal est protégé.
    assert "mm_sfxhand pas = sfx_play(SFX_PAS, 255, 1);" in code
    for appel in ("sfx_set_volume(pas,", "sfx_set_pitch(pas,", "sfx_set_panning(pas,",
                  "sfx_is_playing(pas)", "sfx_stop(pas)"):
        assert appel in code, appel
    # Le repli des méthodes d'actor ne doit surtout pas s'appliquer ici.
    assert "actor_set_volume" not in code


def test_chaque_pourcentage_part_dans_la_graduation_de_son_registre():
    """Quatre registres, quatre échelles — et un pourcentage n'appartient à
    aucune. 80 % vaut 204 par effet (0–255), 60 % vaut 614 pour un module
    (0–1024), 120 % vaut 1229 en hauteur (facteur 6.10), et −40 vaut 77 en
    panning (0–255, centré sur 128)."""
    errs, code = _lua_sfx(CINQ_METHODES.replace(
        "  if pas:playing() then pas:stop() end\n",
        "  music:set_volume(60)\n"
        "  sound_box:set_volume(60)\n"
        "  jingle_box:set_volume(60)\n"))
    assert errs == []
    assert "sfx_set_volume(pas, 204)" in code
    assert "sfx_set_pitch(pas, 1229)" in code
    assert "sfx_set_panning(pas, 77)" in code
    assert "music_set_volume(614)" in code
    assert "sfx_set_effects_volume(614)" in code
    assert "music_jingle_volume(614)" in code


def test_un_pourcentage_calcule_se_convertit_a_lexecution():
    """Un niveau peut venir d'une variable : la conversion ne peut alors pas
    être pliée au build, mais elle doit avoir lieu quand même."""
    errs, code = _lua_sfx('function on_update(self)\n'
                          '  local pas = sfx:play("Pas")\n'
                          '  pas:set_volume(niveau)\n'
                          'end\n')
    assert errs == []
    assert "sfx_set_volume(pas, ((niveau) * 255 / 100))" in code


def test_une_methode_inconnue_sur_une_reference_est_refusee():
    errs, _ = _lua_sfx('function on_update(self)\n'
                       '  local pas = sfx:play("Pas")\n'
                       '  pas:set_speed(2)\n'
                       'end\n')
    assert len(errs) == 1
    assert "sfx reference" in errs[0]
    assert ":set_pitch()" in errs[0]


def test_une_reference_qui_traverse_une_attente_garde_son_champ_detat():
    """Une variable de séquence vit dans l'état, pas sous son nom : émettre le
    nom nu produisait un identifiant que le C ne connaît pas — et le `make`
    échouait loin de la ligne fautive."""
    errs, code = _lua_sfx('function on_sequence_intro(self)\n'
                          '  local pas = sfx:play("Pas")\n'
                          '  wait(10)\n'
                          '  pas:stop()\n'
                          'end\n')
    assert errs == []
    assert "sfx_stop(Ball_seq_intro_pas)" in code
    assert "sfx_stop(pas)" not in code


def test_les_portes_du_son_existent_dans_le_c_emis():
    """Même garde-fou que pour les helpers de juiciness, côté audio : ces
    fonctions-là ne vivent pas dans `runtime_api_inline.h` mais dans l'en-tête
    ÉMIS par `headers.py`, et un `c_func` sans implémentation ne se verrait
    qu'au `make`."""
    from scripting.api import RUNTIME_API

    src = (REPO_DIR / "editor" / "codegen" / "runtime_codegen" / "headers.py").read_text(
        encoding="utf-8", errors="ignore")
    prefixes = ("sfx:", "sfx.", "music.", "sound_box.", "jingle_box.", "music_box.")
    portes = [k for k in RUNTIME_API if k.startswith(prefixes)]
    assert portes, "aucune porte audio dans le catalogue"
    for key in portes:
        fn = RUNTIME_API[key].c_func
        assert re.search(r"\b" + re.escape(fn) + r"\s*\(", src), (
            f"{key} : {fn}() n'est émis nulle part par headers.py")


DEUX_LECTURES = '''function on_update(self)
  sfx:play("Pas")
  local tenu = sfx:play("Pas")
end
'''


def test_un_effet_pose_seul_laisse_son_canal_volable():
    """La règle de la v0.8.8 : `sfx:play(…)` posé seul n'a pas de référence à
    protéger, donc son canal reste volable (`hold = 0`) ; celui qu'on retient
    est protégé (`hold = 1`). C'est la seule décision du générateur qui dépend
    de la POSITION de l'appel — sans elle, huit bruitages intouchables
    faisaient perdre le neuvième en silence."""
    errs, code = _lua_sfx(DEUX_LECTURES)
    assert errs == []
    assert "sfx_play(SFX_PAS, 255, 0);" in code
    assert "mm_sfxhand tenu = sfx_play(SFX_PAS, 255, 1);" in code


# ── Un `local a, b, c` déclare bien les TROIS, dans un corps de handler ──
# Le défaut, silencieux et daté : en corps de fonction, seul le premier nom
# était retenu (`StmtLocalAssign` ne lisait que `targets[0]`). `heightspeed` et
# `runspeed` disparaissaient du C, et les référencer partait en identifiant C
# inconnu — au `make`, jamais sur sa cause. Le top-level, lui, les gardait déjà :
# c'est cette asymétrie que le correctif « multi-local » supprime.

MULTI_LOCAL = '''function on_update()
    local speed, heightspeed, runspeed = 1, 2, 3
    self:move(vec2(speed, 0), runspeed + heightspeed)
end
'''


def test_multi_local_en_corps_declare_tous_les_noms():
    errs, code = _lua(MULTI_LOCAL)
    assert [e.message for e in errs if e.level in ("error", "warning")] == []
    assert "int speed = 1;" in code
    assert "int heightspeed = 2;" in code
    assert "int runspeed = 3;" in code


def test_multi_local_valeurs_manquantes_valent_zero():
    # `local a, b, c = 1` : b et c sont nil, donc 0 dans le C entier — jamais
    # laissés non initialisés.
    _errs, code = _lua("function on_start()\n    local a, b, c = 1\nend\n")
    assert "int a = 1;" in code
    assert "int b = 0;" in code and "int c = 0;" in code


def test_tag_d_un_acteur_guide_vers_name():
    """`other.tag` était l'identité de l'acteur ; `tag` est désormais réservé aux boîtes."""
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' if other.tag == "Ball" then end\nend\n')
    assert any("other.name" in e for e in errs)


def test_collision_box_n_est_pas_un_champ_d_acteur():
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' if other.collision_box.tag == "Player" then end\nend\n')
    assert any("other_box.tag" in e for e in errs)
