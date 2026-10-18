"""Séquences de textes : DÉRIVÉES des clés, jamais stockées.

Les textes dont la clé finit par un segment numérique (`Dialogue_1`, `Dialogue_Page01`,
`Shop_007`) et qui partagent le même préfixe forment une séquence dès deux textes.
L'ordre est la valeur du numéro. Une séquence est LIÉE dès qu'un consommateur la cite
— une table (`DataTable.text_link`) ou une TextBox (`UITextbox.sequence_prefix`) —,
LIBRE sinon. Les consommateurs la suivent d'eux-mêmes (cf. `sync_consumers`).
"""
import re

# Le suffixe est le dernier segment après `_` qui finit par des chiffres.
# shortcut: `A_Page1` et `A_Line1` partagent le préfixe `A` et se fondent en une seule
# séquence ; à revoir si un projet nomme deux séquences distinctes sous le même préfixe.
_SUFFIX = re.compile(r"(.+)_[^_]*?([0-9]+)")


def sequence_of(key):
    """(préfixe, numéro) si la clé porte un suffixe numérique, sinon None."""
    m = _SUFFIX.fullmatch(key)
    return (m[1], int(m[2])) if m else None


def sequences(project) -> dict[str, list[str]]:
    """préfixe -> clés triées par numéro, deux textes au moins."""
    found: dict[str, list] = {}
    for t in project.texts:
        if (seq := sequence_of(t.key)):
            found.setdefault(seq[0], []).append((seq[1], t.key))
    return {prefix: [key for _, key in sorted(pages)]
            for prefix, pages in sorted(found.items()) if len(pages) >= 2}


def group_texts(project, prefix) -> list:
    """Les textes du préfixe dans l'ordre des numéros, même moins de deux.

    `startswith` d'abord : cette fonction est lue à chaque repaint du canvas, la regex
    ne tourne que sur les rares clés du préfixe."""
    head = prefix + "_"
    pages = [(seq[1], t.key, t) for t in project.texts
             if t.key.startswith(head) and (seq := sequence_of(t.key)) and seq[0] == prefix]
    return [t for _n, _k, t in sorted(pages, key=lambda page: page[:2])]


def group_keys(project, prefix) -> list[str]:
    return [t.key for t in group_texts(project, prefix)]


def renumbered_keys(project, prefix) -> list:
    """[(texte, clé)] pour rendre la numérotation continue (1, 2, 3…), en gardant la forme
    et la largeur du premier suffixe (`Page01`, `Page02`…). Vide si elle l'est déjà."""
    texts = group_texts(project, prefix)
    if not texts:
        return []
    m = re.fullmatch(r"(.*?)([0-9]+)", texts[0].key.rsplit("_", 1)[1])
    stem, width = m[1], len(m[2])
    wanted = [f"{prefix}_{stem}{n:0{width}d}" for n in range(1, len(texts) + 1)]
    return [(t, key) for t, key in zip(texts, wanted) if t.key != key]


def reordered_keys(texts, source: int, target: int) -> list:
    """[(texte, clé)] pour déplacer `texts[source]` en position `target` : les textes, dans leur nouvel
    ordre, reprennent les clés actuelles (triées). Réordonner, c'est échanger des numéros."""
    keys = [t.key for t in texts]
    order = list(texts)
    order.insert(target, order.pop(source))
    return [(text, key) for text, key in zip(order, keys) if text.key != key]


def promotion(project, base) -> list:
    """[(texte, clé)] : le texte seul qui porte la clé `base` devient `base_1`, pour que `base`
    ne désigne plus qu'une séquence (jamais une entrée ET un conteneur). Vide s'il n'y en a pas,
    ou si la séquence existe déjà."""
    leaf = project.get_text(base)
    return [(leaf, f"{base}_1")] if leaf is not None and not group_texts(project, base) else []


def would_empty_linked(project, text, new_key) -> bool:
    """Renommer `text` en `new_key` viderait-il une séquence lue par une table ou une boîte ?
    Vrai si c'est son seul texte et que la nouvelle clé sort du préfixe."""
    old = sequence_of(text.key)
    new = sequence_of(new_key)
    if not old or (new and new[0] == old[0]):
        return False
    return group_keys(project, old[0]) == [text.key] and bool(consumers(project, old[0]))


def next_key(project, prefix) -> str:
    """La clé du prochain texte de la séquence : numéro max + 1, largeur du dernier."""
    keys = group_keys(project, prefix)
    if not keys:
        return f"{prefix}_1"
    last = keys[-1].rsplit("_", 1)[-1]
    width = len(re.search(r"[0-9]+$", last)[0])
    return f"{prefix}_{last[:len(last) - width]}{sequence_of(keys[-1])[1] + 1:0{width}d}"


def consumers(project, prefix) -> list:
    """Tables et TextBox qui lisent cette séquence : liée si la liste n'est pas vide."""
    tables = [t for t in project.data_tables if t.text_link.get("prefix") == prefix]
    boxes = [box for _layout, box in project.all_regions()
             if getattr(box, "sequence_prefix", "") == prefix]
    return tables + boxes


def snapshot_groups(project, texts) -> dict[str, list[str]]:
    """Avant un renommage : pour chaque préfixe touché, les ids de TOUT son groupe."""
    prefixes = {s[0] for t in texts if (s := sequence_of(t.key))}
    return {p: [t.id for t in project.texts if (s := sequence_of(t.key)) and s[0] == p]
            for p in prefixes}


def follow_groups(project, before) -> None:
    """Après un renommage : un groupe entier passé sous un même nouveau préfixe
    emporte ses consommateurs ; un groupe éclaté les laisse (la synchro retire les lignes)."""
    for old, ids in before.items():
        new = {(s[0] if (s := sequence_of(t.key)) else None)
               for i in ids if (t := project.get_text_by_id(i))}
        if len(new) == 1 and (target := new.pop()) and target != old:
            _retarget(project, old, target)


def _retarget(project, old, new) -> None:
    for table in project.data_tables:
        if table.text_link.get("prefix") == old:
            table.text_link = {**table.text_link, "prefix": new}
            project.data_tables.save(table)
    saved = []
    for layout, box in project.all_regions():
        if getattr(box, "sequence_prefix", "") == old:
            box.sequence_prefix = new
            if not any(layout is other for other in saved):
                saved.append(layout)
    for layout in saved:
        project.ui_layouts.save(layout)


def editor_rows(project):
    """(texte, chemin affiché, préfixe de sa séquence ou None) pour tout le projet."""
    from collections import Counter
    sizes = Counter(s[0] for t in project.texts if (s := sequence_of(t.key)))
    return [(t, tuple(t.path),
             s[0] if (s := sequence_of(t.key)) and sizes[s[0]] >= 2 else None)
            for t in project.texts]
