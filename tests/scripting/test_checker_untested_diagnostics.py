"""Des diagnostics du checker Lua qu'aucun test ne déclenchait (la liste d'exemptions de la couverture : cf.
`tools/diagnostic_coverage_exemptions.json`). Chaque test écrit le script fautif et lit ce que le checker en dit.

Restent exemptés, avec leur raison dans le fichier d'exemptions : deux branches que leur condition rend inatteintes
(« export … not applied at build yet » : tous les types connus sont câblés ; « an actor has no such method » : un
récepteur qui rend un acteur est toujours typé, et c'est l'autre message qui parle)."""
from __future__ import annotations

from scripting.checker import BuildContext, check
from scripting.parser import parse


def _in_handler(body: str) -> str:
    return f"function on_update()\n{body}\nend\n"


def diagnostics(src: str, **context) -> list[tuple[str, str]]:
    found = check(parse(src), BuildContext(actor_name="Ball", **context))
    return [(d.level, d.message) for d in found]


def says(found, level: str, fragment: str) -> bool:
    return any(lvl == level and fragment in msg for lvl, msg in found)


# ── Fonctions privées, tableaux, tables de données ────────────────────────


def test_une_fonction_privee_declaree_deux_fois_est_une_erreur():
    src = "function helper()\n return 1\nend\nfunction helper()\n return 2\nend\n" + _in_handler("")
    assert says(diagnostics(src), "error", "Private function 'helper' declared 2 times")


def test_une_fonction_privee_ne_rend_qu_un_entier_ou_un_booleen():
    two = diagnostics("function helper()\n return 1, 2\nend\n" + _in_handler(""))
    text = diagnostics('function helper()\n return "a"\nend\n' + _in_handler(""))
    vec = diagnostics("function helper()\n return vec2(1, 2)\nend\n" + _in_handler(""))
    assert says(two, "error", "helper(): a private function returns at most one integer value")
    assert says(text, "error", "helper(): a private function only returns an integer or a boolean")
    assert says(vec, "error", "helper(): a private function only returns an integer or a boolean")


def test_un_tableau_declare_de_travers_est_une_erreur():
    record = diagnostics(_in_handler("local a = {x = 1}"))
    empty = diagnostics(_in_handler("local a = {}"))
    ragged = diagnostics(_in_handler("local a = {{1, 2}, {3}}"))
    strings = diagnostics(_in_handler('local a = {"a", "b"}'))
    assert says(record, "error", "'a' : a named entry: that is a record, not an array")
    assert says(empty, "error", "'a' : no element: an empty array has no size")
    assert says(ragged, "error", "'a' : rows of different lengths")
    assert says(strings, "error", "'a': an array only holds integers")


def test_un_indice_sur_autre_chose_qu_un_tableau_avertit_et_trop_d_indices_est_une_erreur():
    not_array = diagnostics(_in_handler("local x = 1\nx[1] = 2"))
    too_many = diagnostics(_in_handler("local a = {1, 2, 3}\nlocal v = a[1][2]"))
    assert says(not_array, "warning", "'x[…]': 'x' is not an array declared in this script")
    assert says(too_many, "error", "'a' has 1 dimension(s), 2 index(es) used")


def test_une_table_de_donnees_absente_ou_mal_indexee_est_une_erreur():
    tables = {"Items": (["price"], 3)}
    assert says(diagnostics(_in_handler("local v = data.Nope[1].price"), data_tables=tables),
                "error", "data.Nope: data table not found (Items)")
    assert says(diagnostics(_in_handler("local v = data.Items[1][2]"), data_tables=tables),
                "error", "data.Items is indexed by its ROW and nothing else")
    assert says(diagnostics(_in_handler("local v = data.Items[1].nope"), data_tables=tables),
                "error", "data.Items[…].nope: this table has no column 'nope' (price)")


def test_une_globale_indexee_inconnue_est_une_erreur():
    found = diagnostics(_in_handler("local v = global.Nope[1]"), global_names=["Score"], global_counts={"Score": 1})
    assert says(found, "error", "global.Nope: global variable not found")


# ── Écritures, calculs, attentes, appels ──────────────────────────────────


def test_assigner_un_champ_a_une_valeur_non_composite_est_une_erreur():
    found = diagnostics(_in_handler("self.priority.x = 1"))
    assert says(found, "error", "self.priority is not a composite value : it has no field 'x' to assign")


def test_un_export_d_un_type_que_les_autres_scripts_ne_lisent_pas_est_une_erreur():
    found = diagnostics(_in_handler('local a = actor:get("Hero")\nlocal v = a.tint'),
                        actor_names=["Hero"], actor_exports={"Hero": {"tint": {"type": "matrix"}}})
    assert says(found, "error", "a.tint: an export of type matrix cannot be read or written from another script")


def test_une_attente_qui_n_a_pas_exactement_un_argument_est_une_erreur():
    found = diagnostics("function on_sequence_Intro()\n wait(1, 2)\nend\n" + _in_handler(""))
    assert says(found, "error", "wait() expects exactly one argument, 2 given")


def test_calculer_sur_un_rect_est_une_erreur():
    found = diagnostics(_in_handler("local r = rect(1, 2, 3, 4)\nlocal v = r + 1"))
    assert says(found, "error", "a rect is not a number: '+' is not defined on it")


def test_la_longueur_d_autre_chose_qu_un_tableau_est_une_erreur():
    found = diagnostics(_in_handler("local n = #x"))
    assert says(found, "error", "'#' only applies to an array declared in this script or to a data table")


def test_un_son_joue_sans_composant_son_avertit():
    found = diagnostics(_in_handler("self:play_sfx()"))
    assert says(found, "warning", "self:play_sfx(): this actor has no SoundFX component")


def test_une_methode_d_acteur_inconnue_est_une_erreur():
    found = diagnostics(_in_handler("self:nope()"))
    assert says(found, "error", "Unknown method: self:nope()")


def test_un_constructeur_vectoriel_au_mauvais_nombre_d_arguments_est_une_erreur():
    found = diagnostics(_in_handler("local v = vec2(1)"))
    assert says(found, "error", "vec2() expects 2 numbers (x, y), 1 given")


# ── Références aux ressources du projet ───────────────────────────────────


def test_un_etat_ou_un_declencheur_de_boite_inconnu_est_dit():
    sound = diagnostics(_in_handler('sound_box:set_state("x")'), sound_box_state_names=["a"])
    jingle = diagnostics(_in_handler('jingle_box:set_state("x")'), jingle_box_state_names=[])
    trigger = diagnostics(_in_handler('music_box:trigger("x")'), music_box_trigger_names=["a"])
    assert says(sound, "error", "sound_box:set_state('x'): no state with this name in this box. Available states: a")
    assert says(jingle, "error", "jingle_box:set_state('x'): no state with this name in this box. Available states: none")
    assert says(trigger, "warning", "music_box:trigger('x'): no music transition listens to this trigger")


def test_une_cle_de_texte_inconnue_est_dite_selon_que_le_litteral_est_permis():
    typo = diagnostics(_in_handler('text:draw(8, 8, "village_guard_01")'), text_keys=["intro"])
    missing = diagnostics(_in_handler('local n = text:length("NoKey")'), text_keys=["intro"])
    assert says(typo, "warning", "text:draw('village_guard_01'): no entry with this name in the table")
    assert says(missing, "error", "text:length('NoKey'): text 'NoKey' not found in the project table (intro)")


def test_une_police_ou_une_palette_inconnue_est_une_erreur():
    font = diagnostics(_in_handler('text:set_font("Nope")'), font_names=["Pixel"])
    palette = diagnostics(_in_handler('palette:set_bg(1, "Nope")'), palette_names=["Day"])
    assert says(font, "error", "text:set_font('Nope'): font 'Nope' not found or without glyphs (Pixel)")
    assert says(palette, "error", "palette:set_bg('Nope'): palette 'Nope' not found in the colour catalogue (Day)")


def test_une_globale_non_declaree_avertit():
    found = diagnostics(_in_handler('local v = save:read(0, "Nope")'), global_names=["Score"], save_slots=1)
    assert says(found, "warning", "save:read('Nope'): global variable 'Nope' is not declared in the project")


def test_une_sauvegarde_sans_variable_persistante_avertit():
    found = diagnostics(_in_handler("save:write(0)"), has_persistent=False, save_slots=1)
    assert says(found, "warning", "save:write(): no global variable is marked persistent in this project")


def test_lire_une_globale_non_persistante_avertit():
    found = diagnostics(_in_handler('local v = save:read(0, "Score")'),
                        global_persist={"Score": False}, global_names=["Score"], save_slots=1)
    assert says(found, "warning", "save:read(..., 'Score'): 'Score' is not ticked \"persist\"")


def test_la_table_de_valeurs_d_un_spawn_est_refusee_de_trois_facons():
    context = dict(prefab_names=["Bullet"], spawn_exports={"Bullet": {"speed": {"type": "int"}}})
    not_a_table = diagnostics(_in_handler('actor:spawn("Bullet", vec2(0, 0), 5)'), **context)
    unnamed = diagnostics(_in_handler('actor:spawn("Bullet", vec2(0, 0), {5})'), **context)
    computed = diagnostics(_in_handler('local x = 3\nactor:spawn("Bullet", vec2(0, 0), {speed = x})'), **context)
    assert says(not_a_table, "error", "actor.spawn: the 3rd argument is a table of values")
    assert says(unnamed, "error", "actor.spawn: the table of values only accepts named entries")
    assert says(computed, "error", 'actor.spawn: the value of "speed" must be a literal')


def test_un_acteur_absent_de_la_scene_avertit():
    found = diagnostics(_in_handler('local a = actor:get("Nope")'), actor_names=["Hero"])
    assert says(found, "warning", "actor:get('Nope'): no actor named 'Nope' in the scene (Hero)")
