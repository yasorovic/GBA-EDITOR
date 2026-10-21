"""
ui/text_editor/text_commands.py — commandes annulables de l'écran Texte.

Regroupées ici : ce sont les seules à connaître les effets de bord d'une
édition (réécriture des `text.draw` des scripts, remesure des chasses), que les
vues n'ont pas à porter.
"""
from __future__ import annotations

from copy import deepcopy

from core.history import Command
from core.text_sequences import sequence_of


class DeleteTextsCmd(Command):
    """Supprime des textes, leurs traductions et les `text_key` qui les affichaient.

    Les tables et boîtes liées à une séquence suivent d'elles-mêmes (synchro de l'historique)."""

    def __init__(self, project, texts, persist_fn=None, label="Delete texts"):
        self.project = project
        self.texts = list({id(text): text for text in texts}.values())
        self.label = label
        self._persist = persist_fn
        self._text_order = list(project.texts)
        self._translations = deepcopy(project.translations)
        self._regions = [(region, getattr(region, "text_key", ""))
                         for _layout, region in project.all_regions()]
        ids = {text.id for text in self.texts}
        self.translation_langs = {
            code for code, values in project.translations.items() if ids & values.keys()
        }
        keys = {text.key for text in self.texts}
        self.touched_layouts = list({id(layout): layout for layout, region in project.all_regions()
                                     if getattr(region, "text_key", "") in keys}.values())
        # Les séquences touchées : si une table ou une boîte les lit, leur numérotation reste continue.
        self._prefixes = sorted({seq[0] for t in self.texts if (seq := sequence_of(t.key))})
        self._renamed = []
        self._table_restore = None

    def execute(self):
        ids = {text.id for text in self.texts}
        keys = {text.key for text in self.texts}
        self.project.texts[:] = [text for text in self.project.texts if text.id not in ids]
        for values in self.project.translations.values():
            for text_id in ids:
                values.pop(text_id, None)
        for region, _key in self._regions:
            if getattr(region, "text_key", "") in keys:
                region.text_key = ""
        self._renumber_linked()
        if self._persist:
            self._persist()

    def _renumber_linked(self):
        """Une séquence liée garde une numérotation continue : les pages suivantes remontent.

        Les lignes des tables liées d'abord (celle de la page supprimée part), puis les clés :
        le renommage réécrit les cellules, chaque ligne garde donc ses autres colonnes."""
        from core.text_sequences import consumers, renumbered_keys
        from core.text_table_link import sync_linked_tables
        self._renamed, self._table_restore = [], None
        linked = [p for p in self._prefixes if consumers(self.project, p)]
        if not linked:
            return
        self._table_restore = sync_linked_tables(self.project)
        for prefix in linked:
            pairs = renumbered_keys(self.project, prefix)
            before = [(text, text.key) for text, _key in pairs]
            try:
                self.project.rename_text_keys(pairs)
            except ValueError:
                continue                  # clé déjà prise : on laisse la numérotation telle quelle
            self._renamed += before
        self._notify_tables()

    def _notify_tables(self):
        if self._renamed or self._table_restore:
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().notify_data_tables_changed()

    def undo(self):
        # Avant de rendre les textes supprimés : leurs anciennes clés sont encore libres.
        if self._renamed:
            self.project.rename_text_keys([(text, old) for text, old in self._renamed])
        if self._table_restore:
            self._table_restore()
        self._notify_tables()
        self.project.texts[:] = self._text_order
        self.project.translations.clear()
        self.project.translations.update(deepcopy(self._translations))
        for region, key in self._regions:
            region.text_key = key
        if self._persist:
            self._persist()


class RenameTextKeyCmd(Command):
    """Renomme une clé de texte.

    L'undo repasse par `Project.rename_text_key` en sens inverse : elle réécrit
    aussi les `text:draw("clé")` des scripts, remettre le champ ne suffirait pas.
    """

    def __init__(self, project, text, old_key: str, new_key: str, persist_fn=None):
        self._project = project
        self._text = text
        self._old = old_key
        self._new = new_key
        self.label = f"Rename text → {new_key}"
        self._persist = persist_fn
        self._first = True   # le renommage a déjà été appliqué par l'appelant

    def execute(self):
        if self._first:
            self._first = False        # premier passage : déjà fait
        else:
            self._project.rename_text_key(self._text, self._new)
        if self._persist:
            self._persist()

    def undo(self):
        self._project.rename_text_key(self._text, self._old)
        if self._persist:
            self._persist()


class RenameTextGroupKeysCmd(Command):
    """Renomme le préfixe d'une séquence en un seul pas d'historique.

    Ses consommateurs (tables, boîtes) suivent le nouveau préfixe (`rename_text_keys`)."""

    def __init__(self, project, texts, prefix, persist_fn=None):
        self._project = project
        texts = list({text.id: text for text in texts}.values())
        self._entries = [(text, text.key, f"{prefix}_{text.key.rsplit('_', 1)[1]}")
                         for text in texts]
        self._persist = persist_fn
        self.label = f"Rename text group → {prefix}"

    def execute(self):
        members = {id(text) for text, *_ in self._entries}
        occupied = {text.key for text in self._project.texts if id(text) not in members}
        targets = [new for _, _, new in self._entries]
        if len(set(targets)) != len(targets) or any(new in occupied for new in targets):
            raise ValueError("Text key already exists")
        self._project.rename_text_keys([(t, new) for t, _, new in self._entries])
        if self._persist:
            self._persist()

    def undo(self):
        self._project.rename_text_keys([(text, old) for text, old, _ in self._entries])
        if self._persist:
            self._persist()


class SetTranslationCmd(Command):
    """Écrit une entrée dans un fichier de traduction (ROADMAP v0.9, phase 2).

    Symétrique de `SetFieldCmd`, mais le champ n'est pas un attribut d'objet :
    c'est `project.translations[code][text.id]`. « » (chaîne vide) ET
    « absent » sont la MÊME chose pour cette commande — une entrée jamais
    traduite lit "" via `dict.get`, et une traduction vidée par l'utilisateur y
    redevient "" plutôt que d'être retirée du dict. C'est `text_content()` qui
    décide qu'une chaîne vide vaut la source ; cette commande n'a pas à
    connaître cette règle, seulement à la stocker fidèlement.
    """

    def __init__(self, project, code: str, text, old: str, new: str,
                 label: str = "", persist_fn=None):
        self._project = project
        self._code = code
        self._text = text
        self._old = old
        self._new = new
        self.label = label or f"Translate {text.key} ({code})"
        self._persist = persist_fn

    def _write(self, value: str):
        self._project.translations.setdefault(self._code, {})[self._text.id] = value
        if self._persist:
            self._persist()

    def execute(self):
        self._write(self._new)

    def undo(self):
        self._write(self._old)

    def merge(self, newer: "Command") -> bool:
        if (not isinstance(newer, SetTranslationCmd) or self._code != newer._code
                or self._text is not newer._text):
            return False
        self._new = newer._new
        self._persist = newer._persist
        return True


class DeleteSequenceCmd(Command):
    """Détruit toute une séquence : ses textes (et traductions), les lignes des tables liées, et
    vide les TextBox qui la suivaient (déliées, sans page). Un seul pas d'historique.

    Les textes passent par `DeleteTextsCmd` : la synchro retire les lignes de table et les références
    `text_key` tombent. Les boîtes sont déliées d'abord, pour ne pas rester sur une séquence disparue."""

    def __init__(self, project, prefix: str, persist_fn=None):
        from core.text_sequences import group_texts
        self.project, self.prefix, self._persist = project, prefix, persist_fn
        self._boxes = [(layout, box) for layout, box in project.all_regions()
                       if getattr(box, "sequence_prefix", "") == prefix]
        self._inner = DeleteTextsCmd(project, group_texts(project, prefix))
        self.label = f"Delete sequence {prefix}"

    @property
    def translation_langs(self):
        return self._inner.translation_langs

    def _save_layouts(self):
        layouts = {id(layout): layout for layout, _box in self._boxes}
        layouts.update({id(layout): layout for layout in self._inner.touched_layouts})
        for layout in layouts.values():
            self.project.ui_layouts.save(layout)

    def execute(self):
        for _layout, box in self._boxes:
            box.sequence_prefix = ""
        self._inner.execute()
        self._save_layouts()
        if self._persist:
            self._persist()

    def undo(self):
        self._inner.undo()
        for _layout, box in self._boxes:
            box.sequence_prefix = self.prefix
        self._save_layouts()
        if self._persist:
            self._persist()


class RenameTextKeysCmd(Command):
    """Renomme un lot de clés d'un coup (réordonner des pages = échanger leurs numéros).

    Scripts, cellules de table, boîtes et séquences liées suivent (`Project.rename_text_keys`) ;
    l'undo repose les clés exactes d'avant."""

    def __init__(self, project, pairs, label: str, persist_fn=None):
        self._project = project
        self._pairs = list(pairs)
        self._before = [(t, t.key) for t, _key in pairs]
        self.label = label
        self._persist = persist_fn

    def execute(self):
        self._apply(self._pairs)

    def undo(self):
        self._apply(self._before)

    def _apply(self, pairs):
        # Un seul parcours d'`assets/` pour le renommage ET le rafraîchissement qui suit (index d'usage).
        from core.lua_scripts import lua_files_cached
        with lua_files_cached(self._project):
            self._project.rename_text_keys(pairs)
            if self._persist:
                self._persist()


class SetTextPathCmd(Command):
    """Range un ou plusieurs textes : déplacer une entrée ou renommer un dossier, c'est renommer
    les clés (le chemin n'est que leurs segments, cf. models/text.py).

    `entries` : [(texte, ancien chemin, nouveau chemin)]. Tout le lot change d'un coup — une clé
    qui prend la place d'une autre ne s'y heurte pas — et scripts, cellules de table, boîtes et
    séquences liées suivent. L'undo repose les anciennes clés exactes : rejouer la dérivation ne les
    rendrait pas forcément (le rang `_NN` dépend des clés prises)."""

    def __init__(self, project, entries, label: str, persist_fn=None):
        self._project = project
        self._targets = [(t, list(new)) for t, _old, new in entries]
        self._before = [(t, t.key) for t, _old, _new in entries]
        self.label = label
        self._persist = persist_fn

    def execute(self):
        pairs = self._project.text_path_keys(self._targets)
        self._project.rename_text_keys(pairs)
        if self._persist:
            self._persist()

    def undo(self):
        self._project.rename_text_keys(self._before)
        if self._persist:
            self._persist()


class SetKeyColorCmd(Command):
    """Désigne (ou retire) une couleur-clé.

    La couleur d'espacement gouverne la chasse : les `Glyph.advance` de toute la
    planche sont relus derrière, et l'undo doit rendre les deux.
    """

    def __init__(self, project, font, field: str, old, new,
                 label: str, persist_fn=None):
        self._project = project
        self._font = font
        self._field = field
        self._old, self._new = old, new
        self._advances_before = [g.advance for g in font.glyphs]
        self.label = label
        self._persist = persist_fn

    def _apply(self, value, advances=None):
        setattr(self._font, self._field, value)
        if advances is not None:
            for g, a in zip(self._font.glyphs, advances):
                g.advance = a
        else:
            self._remeasure()
        if self._persist:
            self._persist()

    def _remeasure(self):
        """Relit les chasses sur la planche (la règle d'autorité est dans
        `font_import.remeasure_advances`)."""
        f = self._font
        if not f.asset or not self._project:
            return
        from core.font_import import remeasure_advances
        remeasure_advances(f, self._project.asset_abs(f.asset))

    def execute(self):
        self._apply(self._new)

    def undo(self):
        self._apply(self._old, self._advances_before)


class ResliceFontCmd(Command):
    """Re-découpe la planche à une autre taille de cellule.

    Destructive : la liste de glyphes est remplacée, les corrections de
    caractères sont perdues — d'où l'instantané complet.
    """

    def __init__(self, project, font, fields: dict, persist_fn=None):
        self._project = project
        self._font = font
        self._fields = fields
        self._before = {
            "cell_w": font.cell_w, "cell_h": font.cell_h,
            "line_height": font.line_height, "glyphs": list(font.glyphs),
        }
        self.label = f"Re-découper {font.name} en {fields.get('cell_w')}×{fields.get('cell_h')}"
        self._persist = persist_fn

    def execute(self):
        from core.font_import import apply_font_import
        apply_font_import(self._font, self._fields)
        if self._persist:
            self._persist()

    def undo(self):
        for k, v in self._before.items():
            setattr(self._font, k, list(v) if k == "glyphs" else v)
        if self._persist:
            self._persist()


class MergeGlyphsCmd(Command):
    """Rend annulable la fusion calculée par `Font.merged_glyphs`.

    Instantané complet de la liste : la fusion remplace des glyphes, elle n'en
    modifie aucun.
    """

    def __init__(self, font, indices: list, char: str, persist_fn=None):
        self._font = font
        self._before = list(font.glyphs)
        self._after, self.merged = font.merged_glyphs(indices, char)
        self.label = f"Fusionner {len(indices)} cases"
        self._persist = persist_fn

    def execute(self):
        self._font.glyphs = list(self._after)
        if self._persist:
            self._persist()

    def undo(self):
        self._font.glyphs = list(self._before)
        if self._persist:
            self._persist()


class SetCharsetCmd(Command):
    """Réécrit tout le charset d'un bloc, par assignation POSITIONNELLE.

    Le charset n'est pas stocké (cf. `Font`) : l'éditer revient à réécrire les
    `Glyph.char` un à un, dans l'ordre de la planche — caractère i → case i.
    Une case reçoit exactement un caractère, donc une ligature existante est
    aplatie (elle se répare case par case). Les cases au-delà de la chaîne
    gardent leur caractère, les caractères au-delà des cases sont ignorés.
    """

    def __init__(self, font, charset: str, persist_fn=None):
        self._font = font
        self._before = [g.char for g in font.glyphs]
        self._after = list(self._before)
        for i in range(min(len(self._after), len(charset))):
            self._after[i] = charset[i]
        self.label = "Éditer le charset"
        self._persist = persist_fn

    def execute(self):
        for g, ch in zip(self._font.glyphs, self._after):
            g.char = ch
        if self._persist:
            self._persist()

    def undo(self):
        for g, ch in zip(self._font.glyphs, self._before):
            g.char = ch
        if self._persist:
            self._persist()
