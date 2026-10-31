"""La mémoïsation des dispositions : éteinte hors contexte, partagée dans un contexte, jetée à sa sortie."""
from codegen.layout_cache import layout_memo, scene_layout_cache


class _Obj:
    pass


def _counter():
    calls = []

    def compute():
        calls.append(1)
        return object()
    return calls, compute


def test_without_context_every_call_recomputes():
    a, calls_compute = _Obj(), _counter()
    calls, compute = calls_compute
    first = layout_memo("k", (a,), compute)
    second = layout_memo("k", (a,), compute)
    assert first is not second
    assert len(calls) == 2


def test_inside_context_the_value_is_shared():
    a = _Obj()
    calls, compute = _counter()
    with scene_layout_cache():
        assert layout_memo("k", (a,), compute) is layout_memo("k", (a,), compute)
    assert len(calls) == 1


def test_key_separates_kind_object_and_extra():
    a, b = _Obj(), _Obj()
    with scene_layout_cache():
        calls, compute = _counter()
        values = {layout_memo("k", (a,), compute), layout_memo("j", (a,), compute), layout_memo("k", (b,), compute),
                  layout_memo("k", (a,), compute, ("x",))}
    assert len(values) == 4 and len(calls) == 4


def test_cache_is_dropped_on_exit_and_nested_contexts_share_it():
    a = _Obj()
    calls, compute = _counter()
    with scene_layout_cache():
        outer = layout_memo("k", (a,), compute)
        with scene_layout_cache():
            assert layout_memo("k", (a,), compute) is outer      # le contexte interne reprend celui de l'extérieur
        assert layout_memo("k", (a,), compute) is outer          # et ne le jette pas en sortant
    assert layout_memo("k", (a,), compute) is not outer          # sorti du contexte externe : plus rien n'est gardé


def test_objects_of_the_key_are_kept_alive_so_ids_cannot_be_reused():
    calls, compute = _counter()
    with scene_layout_cache():
        layout_memo("k", (_Obj(),), compute)     # l'objet n'a plus d'autre référence que le cache
        layout_memo("k", (_Obj(),), compute)     # un id recyclé ferait un faux succès : 1 appel au lieu de 2
    assert len(calls) == 2
