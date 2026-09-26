"""Trois trous du checker, fermés en AVERTISSEMENT (2026-09-02).

Les trois ont la même signature : le script traverse le checker sans un mot,
le codegen émet du C, et gcc parle d'un fichier que l'auteur n'a jamais écrit.
C'est le piège que ARCHITECTURE.md nomme le plus coûteux de cette chaîne.

1. **Un nom NU non déclaré.** `curpos = curpos + 1` émettait
   `curpos = (curpos + 1);` — un identifiant qui n'existe pas. Ce langage n'a
   pas de variable de script implicite : une valeur qui traverse les frames est
   un `local` de tête, une valeur partagée est `global.nom`.
2. **Un membre inconnu sur une référence d'élément d'interface.** `ui_element`
   est déclaré comme type de retour mais absent de `REF_TYPES` (qui ne contient
   que `sfx`), donc AUCUN membre n'y était validé : `.y`, `.foo`, `:bouge()`
   passaient tous. `interface:get("Cursor").y` produisait `UIELEM_CURSOR.y` — `.y` sur
   un `#define` entier.
3. **Les arguments d'un appel utilisé comme RÉCEPTEUR.** `interface:get("Cusor"):show()`
   ne validait rien : `_check_call_expr` s'arrête à un récepteur `ExprName` et
   personne ne descendait dans le reste. La même expression posée seule était
   pourtant refusée.

**Avertissement et non erreur** pour 1 et 2 : ces deux contrôles s'appliquent à
tous les scripts de tous les projets, et un cas légitime oublié bloquerait un
build qui marche aujourd'hui. À durcir une fois éprouvés. Le 3, lui, ne fait que
laisser passer les contrôles EXISTANTS — ils gardent donc leur sévérité, et
aucun build qui marche n'en pâtit : un nom d'élément inconnu ne produit pas de
`#define`, donc ce build-là échouait déjà au `make`.

La moitié la plus importante de ce fichier est la seconde : ce que ces contrôles
ne doivent PAS refuser.
"""
from __future__ import annotations

import pytest


def _msgs(src: str, **kw):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    kw.setdefault("element_names", ["Cursor"])
    kw.setdefault("ref_kinds", {"Cursor": "image"})
    kw.setdefault("actor_names", ["paddle"])
    kw.setdefault("global_counts", {"score": 1})
    return check(parse(src), BuildContext(actor_name="T", **kw))


def _warnings(src: str, **kw) -> list[str]:
    return [m.message for m in _msgs(src, **kw) if m.level == "warning"]


def _errors(src: str, **kw) -> list[str]:
    return [m.message for m in _msgs(src, **kw) if m.level == "error"]


def _body(*lines: str) -> str:
    return "function on_update()\n" + "".join(f"    {l}\n" for l in lines) + "end\n"


# ── 1. Un nom nu qui ne désigne rien ──────────────────────────────


def test_ecrire_un_nom_nu_non_declare_avertit():
    warns = _warnings(_body("curpos = 1"))
    assert len(warns) == 1
    assert "curpos" in warns[0]
    # Le message donne les DEUX façons légitimes, pas seulement un refus.
    assert "local curpos" in warns[0] and "global.curpos" in warns[0]


def test_lire_un_nom_nu_non_declare_avertit_aussi():
    assert len(_warnings(_body("local v = curpos + 1"))) == 1


def test_un_nom_inconnu_se_dit_une_seule_fois():
    """`curpos = curpos + 1` rencontre le nom trois fois — la cible, la cible
    relue comme expression, l'opérande. Trois lignes identiques donneraient à
    chercher trois fautes."""
    assert len(_warnings(_body("curpos = curpos + 1", "curpos = curpos - 1"))) == 1


def test_deux_noms_inconnus_font_deux_messages():
    assert len(_warnings(_body("a = 1", "b = 2"))) == 2


def test_cest_un_avertissement_pas_une_erreur():
    """Le build ne doit pas s'arrêter tant que ce contrôle n'a pas tourné sur
    de vrais projets."""
    assert _errors(_body("curpos = 1")) == []


# ── 2. Les membres d'une référence d'élément d'interface ──────────


@pytest.mark.parametrize("src", ['interface:get("Cursor").y = 4',
                                 'local y = interface:get("Cursor").y'])
def test_un_champ_sur_une_reference_delement_est_une_erreur(src):
    """Une ERREUR et non un avertissement : le C émis (`UIELEM_CURSOR.y`) ne compile
    pas, donc laisser le build continuer ne fait que déplacer la faute vers gcc."""
    errs = _errors(_body(src))
    assert len(errs) == 1
    assert "propres membres" in errs[0]           # le message dit où chercher
    assert _warnings(_body(src)) == []


def test_une_methode_inconnue_sur_une_reference_delement_est_une_erreur():
    """Une ERREUR : le C émis (`actor_bouge(UIELEM_CURSOR)`) ne compile pas."""
    errs = _errors(_body('interface:get("Cursor"):bouge()'))
    assert len(errs) == 1
    assert ":show()" in errs[0] and ":hide()" in errs[0]
    assert _warnings(_body('interface:get("Cursor"):bouge()')) == []


@pytest.mark.parametrize("m", ["show", "hide"])
def test_les_deux_methodes_reelles_restent_muettes(m):
    assert _warnings(_body(f'interface:get("Cursor"):{m}()')) == []


# ── 3. Le récepteur d'un `:méthode()` quand c'est un appel ────────


def test_largument_du_recepteur_est_enfin_verifie():
    """La même expression posée seule était refusée depuis toujours ; en
    récepteur, elle ne l'était pas."""
    errs = _errors(_body('interface:get("Cusor"):show()'))
    assert len(errs) == 1
    assert "Cusor" in errs[0] and "Cursor" in errs[0]


def test_le_meme_nom_pose_seul_dit_la_meme_chose():
    """Les deux formes doivent parler pareil — c'est l'incohérence qui faisait
    le trou."""
    seul = _errors(_body('interface:get("Cusor")'))
    recepteur = _errors(_body('interface:get("Cusor"):show()'))
    assert seul == recepteur


# ── Ce que les trois contrôles ne doivent PAS refuser ─────────────


@pytest.mark.parametrize("src", [
    # Un `local` de tête, puis son écriture — l'état d'un script.
    "local v = 2\nfunction on_update()\n    v = v + 1\nend\n",
    # Un `local` déclaré dans une branche : le parcours est à plat, assumé.
    'function on_update()\n    if true then local a = 1\n        a = a + 1 end\nend\n',
    # Une variable de boucle.
    "function on_update()\n    for i = 1, 3 do local z = i * 2 end\nend\n",
    # Les espaces de noms — atteints par le `_check_expr(e.obj)` qui clôt la
    # branche ExprIndex, donc le vrai risque de faux positif.
    "function on_update()\n    global.score = 1\n    local w = screen.width\nend\n",
    "function on_update()\n    local m = math.floor(3)\n    text:clear(0, 0, 4, 4)\nend\n",
    # Un acteur nommé du projet, en récepteur de propriété.
    "function on_update()\n    local p = paddle.position\nend\n",
    # L'alias d'un behavior importé.
    'local AI = require("behaviors/ai")\nfunction on_update()\n    AI.update(self)\nend\n',
    # Les deux formes légitimes sur une référence d'élément.
    'function on_update()\n    interface:get("Cursor"):show()\nend\n',
    # Et la façon de déplacer une image.
    'function on_update()\n    interface:get("Cursor").offset = vec2(0, 8)\nend\n',
])
def test_aucun_faux_positif(src):
    assert _warnings(src) == []


def test_un_parametre_de_fonction_est_un_nom_legitime():
    """Un behavior reçoit son acteur en paramètre. `check_event_names=False`
    parce que ses fonctions top-level sont des noms de méthode, pas des
    handlers (cf. `lua_compiler._compile_script`)."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = "function aide(actor, n)\n    n = n + 1\n    return n\nend\n"
    msgs = check(parse(src), BuildContext(actor_name="T"), check_event_names=False)
    assert [m.message for m in msgs if m.level == "warning"] == []
