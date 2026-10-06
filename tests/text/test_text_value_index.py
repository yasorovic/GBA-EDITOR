"""Chaque texte qui cite un global lit son PROPRE rang dans `g_text_values_<langue>`."""
import re

from codegen.font_emit import emit_texts_c
from core.models.settings import GlobalVar
from core.models.text import Text


def test_second_text_reads_its_own_global():
    texts = [Text(id=1, key="a", content="$score_player"),
             Text(id=2, key="b", content="$score_cpu"),
             Text(id=3, key="c", content="$score_player")]
    c = "\n".join(emit_texts_c(
        texts, [""], lambda t, code: t.content,
        globals_=[GlobalVar(name="score_player", id=1), GlobalVar(name="score_cpu", id=2)]))

    assert "g_text_values_0[2] = {GLOBAL_SCORE_PLAYER,GLOBAL_SCORE_CPU}" in c
    # L'argument du TextEvent VALUE est le rang dans cette table : 0, 1, puis 0 (dédoublonné).
    ranks = [int(m) for m in re.findall(r"\{ \d+, \d+, (\d+), TEXT_EV_VALUE", c)]
    assert ranks == [0, 1, 0]
