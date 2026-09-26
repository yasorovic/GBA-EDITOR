"""
ui/text_editor/text_commands.py — commandes annulables de l'écran Texte.

Regroupées ici : ce sont les seules à connaître les effets de bord d'une
édition (réécriture des `text.draw` des scripts, remesure des chasses), que les
vues n'ont pas à porter.
"""
from __future__ import annotations

from core.history import Command


class RenameTextKeyCmd(Command):
    """Renomme une clé de texte.

    L'undo repasse par `Project.rename_text_key` en sens inverse : elle réécrit
    aussi les `text:draw("clé")` des scripts, remettre le champ ne suffirait pas.
    """

    def __init__(self, project, text, old_key: str, new_key: str,
                 old_auto: bool, persist_fn=None):
        self._project = project
        self._text = text
        self._old = old_key
        self._new = new_key
        # Passé par l'appelant : le renommage a déjà eu lieu et a mis auto_key
        # à False, le lire ici restaurerait la nouvelle valeur.
        self._old_auto = old_auto
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
        self._text.auto_key = self._old_auto   # garde le badge « auto » cohérent
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


class CreateTextForElementCmd(Command):
    """Crée une entrée de table ET l'accroche à un élément d'UI, d'un seul geste.

    Écrire dans un élément de texte sans entrée est UNE intention, pas deux :
    la commande porte les deux effets, une seule annulation les défait.

    Le chemin de rangement est PROPOSÉ par l'appelant, jamais imposé : la clé
    qui en dérive reste `auto_key`, donc ranger l'entrée ailleurs la recalera
    (contrat de `models/text.py`).
    """

    def __init__(self, project, element, content: str, path,
                 scene: str = "", persist_fn=None):
        self._project = project
        self._element = element
        self._content = content
        self._path = list(path)
        self._scene = scene
        self._text = None                       # créé au premier execute()
        self._old_key = getattr(element, "text_key", "")
        self.label = "New text"
        self._persist = persist_fn

    def execute(self):
        if self._text is None:
            self._text = self._project.new_text(
                self._content, scene=self._scene, path=self._path)
        elif self._text not in self._project.texts:
            self._project.texts.append(self._text)   # redo : on rend la MÊME entrée
        self._text.content = self._content
        self._element.text_key = self._text.key
        self.label = f"New text {self._text.key}"
        self._notify_link_changed()
        if self._persist:
            self._persist()

    def undo(self):
        if self._text is not None and self._text in self._project.texts:
            self._project.texts.remove(self._text)
        self._element.text_key = self._old_key
        self._notify_link_changed()
        if self._persist:
            self._persist()

    def _notify_link_changed(self):
        # L'écran Texte cache qui cite quoi (`text_usage_index`) : ce geste
        # accroche l'élément à une entrée sans passer par un script, il doit
        # périmer ce cache lui aussi (cf. command_dispatcher).
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().notify_ui_text_links_changed()

    def merge(self, newer: "Command") -> bool:
        """Absorbe la frappe qui SUIT la création.

        Sans ça, écrire « PRESS START » dans un élément neuf laisserait deux
        entrées d'historique — créer le texte, puis l'écrire — pour un seul
        geste. On lit les champs internes de `SetFieldCmd` comme elle-même le
        fait dans sa propre fusion."""
        from core.history import SetFieldCmd
        if (self._text is not None
                and isinstance(newer, SetFieldCmd)
                and newer._obj is self._text
                and newer._field == "content"):
            self._content = newer._new
            return True
        return False


class SetTextPathCmd(Command):
    """Range un ou plusieurs textes (déplacer une entrée = renommer un nœud, à
    l'échelle près).

    Les clés AUTO se recalent derrière — donc les scripts sont réécrits ; les
    clés nommées à la main ne bougent pas (contrat de `auto_key`).

    `order` : la liste plate telle qu'elle doit être APRÈS le geste. Un
    glisser-déposer range ET place — lâcher une entrée entre deux autres dit
    aussi où elle va. Deux commandes auraient demandé deux annulations pour un
    seul geste, d'où le paramètre plutôt qu'une commande de plus.
    """

    def __init__(self, project, entries, label: str, persist_fn=None, order=None):
        self._project = project
        # (texte, ancien chemin, nouveau chemin, ancienne clé) — la clé est
        # capturée MAINTENANT, avant le premier execute().
        self._entries = [(t, list(old), list(new), t.key) for t, old, new in entries]
        self._order_after = list(order) if order is not None else None
        self._order_before = list(project.texts) if order is not None else None
        self.label = label
        self._persist = persist_fn

    def _set_order(self, order):
        # En place : `AddListItemCmd` et le projet gardent une référence sur
        # CETTE liste, la remplacer les laisserait sur l'ancienne.
        if order is not None:
            self._project.texts[:] = order

    def execute(self):
        self._set_order(self._order_after)
        for t, _old, new, _key in self._entries:
            t.path = list(new)
            self._project.resync_text_key(t)
        if self._persist:
            self._persist()

    def undo(self):
        self._set_order(self._order_before)
        for t, old, _new, key in self._entries:
            t.path = list(old)
            # `restore` et non `resync` : le rang `_NN` d'une clé dérivée dépend
            # des clés prises à l'instant du calcul, la rejouer ne rendrait pas
            # forcément la même.
            if t.auto_key:
                self._project.restore_text_key(t, key)
        if self._persist:
            self._persist()


class RelinkTextKeyCmd(Command):
    """Ré-accroche une clé nommée à la main à son chemin de rangement — exact
    inverse du renommage manuel : elle redevient dérivée."""

    def __init__(self, project, text, persist_fn=None):
        self._project = project
        self._text = text
        self._old_key = text.key
        self.label = f"Ré-accrocher {text.key} au rangement"
        self._persist = persist_fn

    def execute(self):
        self._text.auto_key = True
        self._project.resync_text_key(self._text)
        if self._persist:
            self._persist()

    def undo(self):
        self._project.restore_text_key(self._text, self._old_key)
        self._text.auto_key = False
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
