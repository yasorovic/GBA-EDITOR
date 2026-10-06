"""Les séquences — ce qui ne se verrait ni au `make`, ni en lisant le Lua.

Une séquence est réécrite en machine à états au build. Chaque défaut couvert
ici produit du C qui **compile parfaitement** et se trompe en jeu :

- une variable relue après une attente laissée en local C → elle repart de sa
  valeur d'initialisation à la tranche suivante, sans un mot ;
- le pompage absent d'`on_update` → la séquence démarre et n'avance jamais ;
- l'état posé en statique de fichier dans un prefab poolé → les vingt copies
  jouent la même étape ;
- la dernière tranche qui ne remet pas l'étape à zéro → `sequence.running`
  reste vrai pour toujours.

Cf. ROADMAP v0.7.7.
"""
from __future__ import annotations

import pytest


def _gen(src: str, pooled: bool = False, pool_size: int = 8):
    """Parse + check + génère, pour un acteur nommé Hero."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = [e.message for e in check(script, BuildContext(actor_name="Hero",
                                                           anim_names=["idle"]))
              if e.level == "error"]
    code, _warnings, state_bytes = generate(script, CodegenContext(
        actor_name="Hero", actor_sym="Hero", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Hero"], is_pooled=pooled, pool_size=pool_size))
    return errors, code, state_bytes


_DEUX_ATTENTES = """
function on_sequence_intro()
    self:hide()
    wait(30)
    self:show()
    wait_until(self.position.x >= 100)
    self:play_anim("idle")
end
"""


# ── Le découpage ──────────────────────────────────────────────────


def test_une_tranche_par_attente_dans_l_ordre_de_la_source():
    errs, code, _n = _gen(_DEUX_ATTENTES)
    assert errs == []
    corps = code.split("static void Hero_sequence_intro(Actor* self) {")[1]
    # Quatre tranches : le code d'avant, l'attente, le code d'après, l'attente,
    # puis la dernière ligne — soit cinq `case`.
    assert [l.strip() for l in corps.splitlines() if l.strip().startswith("case ")] == [
        "case 1: {", "case 2: {   /* wait(30) */", "case 3: {",
        "case 4: {   /* wait_until */", "case 5: {",
    ]


def test_la_derniere_tranche_arrete_la_sequence():
    """Sans ce retour à zéro, `sequence.running` resterait vrai pour toujours
    et le pompage rappellerait une séquence terminée à chaque frame."""
    _errs, code, _n = _gen(_DEUX_ATTENTES)
    corps = code.split("static void Hero_sequence_intro(Actor* self) {")[1]
    assert "Hero_seq_intro_step = 0;" in corps


def test_le_switch_n_a_pas_de_boucle_autour():
    """Une tranche par frame : c'est ce qui rend un cycle sans attente
    structurellement impossible à faire tourner en rond dans une frame."""
    _errs, code, _n = _gen(_DEUX_ATTENTES)
    corps = code.split("static void Hero_sequence_intro(Actor* self) {")[1].split("\n}")[0]
    assert "for (;;)" not in corps and "while" not in corps


def test_un_wait_sans_duree_n_a_pas_de_compteur():
    """Le compteur est partagé par séquence, et n'existe que s'il y a une durée
    à décompter."""
    _errs, code, _n = _gen("""
function on_sequence_a()
    self:hide()
    wait_until(self.position.x >= 10)
    self:show()
end
""")
    assert "Hero_seq_a_step" in code
    assert "Hero_seq_a_timer" not in code


# ── Ce qui survit à l'attente ─────────────────────────────────────


def test_une_variable_relue_apres_une_attente_survit():
    """Le défaut visé : `depart` laissé en `int depart = …` dans la tranche 1
    n'existerait plus dans la tranche 3. Le C compilerait — une autre variable
    du même nom, à zéro."""
    _errs, code, _n = _gen("""
function on_sequence_a()
    local depart = self.position.x
    wait(10)
    self.position = vec2(depart, 0)
end
""")
    assert "int depart" not in code
    assert "Hero_seq_a_depart = actor_get_position(self).x;" in code
    assert "Hero_seq_a_depart" in code.split("case 3")[1]


def test_une_variable_qui_ne_traverse_rien_reste_locale():
    """L'inverse doit tenir aussi : hisser tout ferait payer de l'état pour une
    variable de travail, et mentirait sur ce que la séquence coûte."""
    _errs, code, _n = _gen("""
function on_sequence_a()
    local n = self.position.x
    self.position = vec2(n, 0)
    wait(10)
    self:show()
end
""")
    assert "int n = actor_get_position(self).x;" in code
    assert "Hero_seq_a_n" not in code


# ── Le pompage ────────────────────────────────────────────────────


def test_le_pompage_est_en_fin_de_on_update():
    _errs, code, _n = _gen("""
function on_update()
    self:show()
end
""" + _DEUX_ATTENTES)
    corps = code.split("void Hero_on_update(Actor* self) {")[1].split("\n}")[0]
    lignes = [l.strip() for l in corps.strip().splitlines()]
    assert lignes[0] == "actor_set_visible(self, 1);"
    assert lignes[-1] == "if (Hero_seq_intro_step) Hero_sequence_intro(self);"


def test_un_script_sans_on_update_en_recoit_un():
    """Le défaut visé : sans `on_update`, `main.c` n'appelle rien et la
    séquence démarre pour ne jamais avancer. Rien ne le dirait."""
    _errs, code, _n = _gen(_DEUX_ATTENTES)
    assert "void Hero_on_update(Actor* self) {" in code
    assert "if (Hero_seq_intro_step) Hero_sequence_intro(self);" in code


def test_le_handler_de_sequence_n_est_pas_emis_en_double():
    """`on_sequence_intro` est découpé, pas transpilé tel quel : un
    `static void Hero_on_sequence_intro` en plus serait du code mort."""
    _errs, code, _n = _gen(_DEUX_ATTENTES)
    assert "Hero_on_sequence_intro" not in code


def test_les_sequences_avancent_dans_l_ordre_de_declaration():
    _errs, code, _n = _gen("""
function on_sequence_un()
    wait(1)
end
function on_sequence_deux()
    wait(1)
end
""")
    corps = code.split("void Hero_on_update(Actor* self) {")[1].split("\n}")[0]
    assert corps.index("Hero_sequence_un") < corps.index("Hero_sequence_deux")


# ── Les trois portes ──────────────────────────────────────────────


def test_les_trois_portes_ne_touchent_qu_un_entier():
    _errs, code, _n = _gen("""
function on_sequence_intro()
    wait(1)
end
function on_start()
    sequence:start("intro")
end
function on_update()
    if sequence:running("intro") then
        sequence:stop("intro")
    end
end
""")
    assert "Hero_seq_intro_step = 1;" in code
    assert "Hero_seq_intro_step = 0;" in code
    assert "(Hero_seq_intro_step != 0)" in code


# ── Un prefab poolé ───────────────────────────────────────────────


def test_dans_un_prefab_poole_l_etat_est_par_instance():
    """Le défaut visé : une statique de fichier ferait jouer la même étape aux
    vingt copies, et le C compilerait sans broncher."""
    _errs, code, state_bytes = _gen("""
function on_sequence_a()
    local depart = self.position.x
    wait(10)
    self.position = vec2(depart, 0)
end
""", pooled=True, pool_size=8)
    assert "static int Hero_seq_a_step" not in code
    assert "int seq_a_step;" in code
    assert "int seq_a_timer;" in code
    assert "int seq_a_depart;" in code
    assert "_st->seq_a_step" in code
    assert "HeroState* _st = &g_state_Hero[Hero_pool_slot(self)];" in code
    # trois entiers d'état, aucune variable de tête
    assert state_bytes == 12


def test_pool_init_remet_les_sequences_a_l_arret():
    """Une instance respawnée doit repartir avec ses séquences arrêtées, pas
    au milieu de celle de l'occupant précédent du slot."""
    _errs, code, _n = _gen("""
function on_sequence_a()
    wait(10)
end
""", pooled=True)
    assert ".seq_a_step = 0" in code
    assert "*_st = (HeroState){" in code


# ── Les refus ─────────────────────────────────────────────────────


@pytest.mark.parametrize("src,attendu", [
    # Le même refus dans les deux cas : une attente s'écrit au premier niveau
    # d'une séquence. La v0.23 a ouvert la boucle BORNÉE et reformulé le
    # message autour d'elle — d'où ce marqueur, et non l'ancien « PREMIER
    # NIVEAU » qui n'y figure plus.
    ("function on_sequence_a()\n if self.visible then\n wait(10)\n end\nend\n",
     "at the top level or in a BOUNDED loop"),
    ("function on_update()\n wait(10)\nend\n",
     "at the top level or in a BOUNDED loop"),
    ("function on_sequence_a()\n local n = wait(3)\nend\n", "returns no value"),
    ("function on_sequence_a()\n wait_until(false)\nend\n", "cannot change"),
    ("local S = 10\nfunction on_sequence_a()\n wait_until(S > 20)\nend\n",
     "cannot change"),
    ("function on_sequence_a()\n wait(-1)\nend\n", "plain positive number"),
    ("function on_sequence_a()\n wait(1)\nend\nfunction on_start()\n"
     " sequence:start(\"autre\")\nend\n", "does not declare a sequence"),
])
def test_les_refus(src, attendu):
    errs, _code, _n = _gen(src)
    assert any(attendu in e for e in errs), errs


@pytest.mark.parametrize("cond", [
    "self.position.x >= 100",     # une propriété change d'une frame à l'autre
    "n > 20",                     # un local que le script assigne
])
def test_une_condition_qui_peut_changer_passe(cond):
    """L'autre sens du refus : le contrôle ne doit jamais accuser à tort."""
    errs, _code, _n = _gen(
        f"local n = 0\nfunction on_update()\n n = n + 1\nend\n"
        f"function on_sequence_a()\n wait_until({cond})\nend\n")
    assert errs == []
