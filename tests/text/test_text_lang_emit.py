"""`emit_texts_c` gagne une dimension langue (ROADMAP v0.9, phase 3.1).

Ce que ces tests protègent :

- un projet MONOLINGUE (`lang_codes = [""]`) émet des tables C identiques en
  COMPORTEMENT à celles d'avant la phase 3 — une seule langue, `g_lang` posé
  à 0 ;
- un projet multilingue émet une case par langue déclarée, dans l'ordre
  reçu, chacune avec ses PROPRES codepoints (résolus par `content_fn`) ;
- les événements de balisage (`[wave]`, `$score`…) sont recalculés par
  langue — une traduction plus longue ou qui réordonne ses marqueurs ne doit
  pas hériter des index de la source ;
- `g_text_values` (les globals interpolés) est dédupliqué PAR LANGUE, jamais
  partagé entre langues.

Cf. `codegen/font_emit.emit_texts_c` et le design posé dans ROADMAP.md.
"""
from __future__ import annotations

import re


def _text(key: str, content: str, tid: int = 0):
    from core.models.text import Text
    return Text(id=tid, key=key, content=content)


def _array(src: str, name: str) -> list[int]:
    """Le contenu d'un `static const unsigned short NAME[...] = {...};`."""
    m = re.search(re.escape(name) + r"\[[^\]]*\]\s*=\s*\{([^}]*)\}", src)
    assert m, f"{name} introuvable dans :\n{src}"
    body = m.group(1).strip()
    return [int(x) for x in body.split(",")] if body else []


def test_projet_monolingue_une_seule_langue(capsys=None):
    from codegen.font_emit import emit_texts_c
    t = _text("intro", "PONG")
    lines = emit_texts_c([t], [""], lambda txt, code: txt.content)
    src = "\n".join(lines)

    assert "int g_lang = 0;" in src
    # Une seule case de langue.
    assert re.search(r"g_texts\[1\]\s*=\s*\{g_texts_0\}", src)
    assert _array(src, "g_text_0_0") == [ord(c) for c in "PONG"]


def test_deux_langues_codepoints_distincts():
    from codegen.font_emit import emit_texts_c
    t = _text("greet", "Hi", tid=1)
    contents = {"": "Hi", "fr": "Salut"}
    lines = emit_texts_c([t], ["", "fr"], lambda txt, code: contents[code])
    src = "\n".join(lines)

    assert re.search(r"g_texts\[2\]\s*=\s*\{g_texts_0,g_texts_1\}", src)
    assert _array(src, "g_text_0_0") == [ord(c) for c in "Hi"]
    assert _array(src, "g_text_1_0") == [ord(c) for c in "Salut"]


def test_evenements_recalcules_par_langue():
    """`[wave]` sur toute la source, absent de la traduction : les tables
    d'événements ne doivent pas être partagées entre langues."""
    from codegen.font_emit import emit_texts_c
    t = _text("title", "[wave]Bartender[/wave]", tid=2)
    contents = {"": "[wave]Bartender[/wave]", "fr": "Tenancier"}
    lines = emit_texts_c([t], ["", "fr"], lambda txt, code: contents[code])
    src = "\n".join(lines)

    assert "g_text_ev_0_0" in src        # la source a un événement WAVE
    assert "g_text_ev_1_0" not in src    # la traduction, aucun balisage : pas de table


def test_la_portee_font_devient_un_evenement_avec_l_index_de_la_police():
    from codegen.font_emit import emit_texts_c
    t = _text("title", "A[font=Titre]B[/font]")
    fonts = [type("Font", (), {"name": "Corps"})(),
             type("Font", (), {"name": "Titre"})()]

    src = "\n".join(emit_texts_c([t], [""], lambda txt, code: txt.content,
                                   fonts=fonts))

    assert "TEXT_EV_FONT" in src
    assert re.search(r"\{ 1, 2, 1, TEXT_EV_FONT, 0 \}", src)


def test_g_text_values_deduplique_par_langue():
    """Un global cité dans une langue et pas l'autre : chaque langue tient sa
    PROPRE table de sources, jamais une partagée (une langue peut réordonner
    ou omettre ses `$nom`, ROADMAP v0.9)."""
    from codegen.font_emit import emit_texts_c
    t = _text("score", "Score: $score", tid=3)
    contents = {"": "Score: $score", "fr": "Score"}   # FR ne cite pas $score
    globals_ = [type("G", (), {"name": "score"})()]
    lines = emit_texts_c([t], ["", "fr"], lambda txt, code: contents[code],
                         globals_=globals_)
    src = "\n".join(lines)

    assert "GLOBAL_SCORE" in re.search(r"g_text_values_0\[\d+\] = \{([^}]*)\}", src).group(1)
    values_1 = re.search(r"g_text_values_1\[\d+\] = \{([^}]*)\}", src).group(1)
    assert "GLOBAL_SCORE" not in values_1


def test_langue_source_reste_le_repli_par_defaut():
    """`content_fn` est appelée avec le CODE de la langue — c'est elle (pas
    `emit_texts_c`) qui décide le repli ; ici on vérifie juste qu'un code
    absent du dict lève plutôt que de retomber en silence sur du faux."""
    from codegen.font_emit import emit_texts_c
    t = _text("x", "X", tid=4)
    calls = []

    def content_fn(txt, code):
        calls.append(code)
        return txt.content

    emit_texts_c([t], ["", "de", "ja"], content_fn)
    assert calls == ["", "de", "ja"]
