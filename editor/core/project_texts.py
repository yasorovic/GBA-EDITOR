"""core/project_texts.py — la table de textes destinés au joueur.

Son I/O, son CRUD, et les règles de la CLÉ (`rename_text_key`, `resync`,
`restore`, `_apply`). La clé reste ici et non avec les renommages d'assets :
renommer un asset déplace un fichier et répare des références, alors qu'une clé
de texte est une règle d'identité de la table — la séparer de ses trois voisines
la rendrait incompréhensible.

S'y ajoutent les littéraux écrits au vol dans un script, qui deviennent des
entrées anonymes au build (`collect_literal_texts`), et `text_values`, qui donne
à l'ÉDITION les valeurs à substituer aux `$nom`.

Une TRANCHE de la classe `Project`, pas un module autonome : les méthodes
ci-dessous s'appellent `self.…` entre elles et avec le reste de `Project`. La
découpe sert la lecture — chaque responsabilité dans son fichier — sans ajouter
le moindre saut d'appel : un mixin est résolu à la construction de la classe,
`project.save_texts()` s'écrit exactement comme avant.

**Ce fichier n'importe jamais `core.project`** : ce serait un cycle immédiat,
puisque `project.py` l'importe pour composer la classe.
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

from core.resources.resource_store import atomic_write
from core.models import project_json
from core.models.ids import new_id
from core.models.text import (
    Text, key_from_path as text_key_from_path, norm_path as norm_text_path,
)


# ── Qui cite un texte ─────────────────────────────────────────────


@dataclass
class TextUsage:
    """Les citations d'une entrée de la table, par source.

    Trois sources : scripts, éléments d'interface (toutes les pages) et
    cellules de table de données de type text. En oublier une afficherait
    « orphelin » sur un texte posé dans une boîte de dialogue — et un orphelin,
    ça se supprime.
    """
    scripts: dict = field(default_factory=dict)   # {chemin du .lua: occurrences}
    regions: list = field(default_factory=list)   # [(mise en page, région)]
    tables: list = field(default_factory=list)    # [(table, ligne 1-based, colonne)]

    @property
    def count(self) -> int:
        return sum(self.scripts.values()) + len(self.regions) + len(self.tables)

    def summary(self) -> str:
        """Ce qui tient dans une cellule : « 2 scripts · 1 layout »."""
        parts = []
        if self.scripts:
            parts.append(f"{len(self.scripts)} script"
                         + ("s" if len(self.scripts) > 1 else ""))
        if self.regions:
            parts.append(f"{len(self.regions)} layout"
                         + ("s" if len(self.regions) > 1 else ""))
        if self.tables:
            parts.append(f"{len(self.tables)} table cell"
                         + ("s" if len(self.tables) > 1 else ""))
        return " · ".join(parts)

    def detail(self) -> str:
        """Le détail, pour un survol : un site par ligne."""
        lines = [f"{p.name} ×{n}" if n > 1 else p.name
                 for p, n in sorted(self.scripts.items())]
        lines += [f"{lay} › {reg}" for lay, reg in sorted(self.regions)]
        lines += [f"{table} › {row} › {col}" for table, row, col in sorted(self.tables)]
        return "\n".join(lines)


@dataclass
class TextUsageIndex:
    """Toutes les citations du projet — et ce qui a réellement pu être lu.

    `scripts_scanned` n'est pas un détail : sans luaparser, un index vide dirait
    « tout le projet est orphelin », et c'est le genre de réponse sur laquelle on
    supprime des entrées."""
    by_key: dict = field(default_factory=dict)
    scripts_scanned: bool = True

    def get(self, key: str) -> TextUsage:
        """Jamais None : une clé jamais citée a des usages vides, pas absents."""
        return self.by_key.get(key) or TextUsage()


def ui_text_build_key(layout, element, project=None) -> str:
    """Référence de build du contenu initial, sans entrée dans l'éditeur."""
    if getattr(element, "sequence_prefix", "") and project is not None:
        pages = project.textbox_pages(element)
        return pages[0].key if pages else ""
    key = getattr(element, "text_key", "") or ""
    if key or not getattr(element, "preview_text", ""):
        return key
    from hashlib import sha256
    identity = json.dumps([layout.name, element.name], ensure_ascii=True)
    return "__ui_inline_" + sha256(identity.encode("utf-8")).hexdigest()


class ProjectTextsMixin:
    # ── Littéraux de script → entrées anonymes ────────────────────
    # `text.draw` et `interface.draw_text` acceptent un littéral en plus d'une clé :
    # un accès rapide au prix assumé de la traduction. À la compilation il
    # devient une entrée ANONYME de la table, donc le runtime ne connaît qu'un
    # seul chemin (mêmes codepoints, même balisage, mêmes interpolations).

    def collect_literal_texts(self) -> list:
        """Entrées anonymes à ajouter à la table pour ce build.

        Le repérage est celui du renommage (`iter_refs`, par DOMAINE) : une
        chaîne qui matche une clé existante n'en est pas un, c'est la référence
        à cette entrée."""
        from core.models.text import Text
        from scripting.refactor import iter_refs, script_paths
        from scripting.api import DOMAIN_TEXT, LITERAL_TEXT_CALLS, anon_text_key
        keys = {t.key for t in self.texts}
        found: dict[str, str] = {}
        for path in script_paths(self):
            try:
                src = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for ref in iter_refs(src, path=path, domain=DOMAIN_TEXT):
                if ref.api_key in LITERAL_TEXT_CALLS and ref.value not in keys:
                    found.setdefault(anon_text_key(ref.value), ref.value)

        # Exports de type `string` (chantier « Les exports de script ») : leur
        # défaut ET chaque valeur d'instance (exports_values) suivent le MÊME
        # chemin qu'un littéral de text.draw — une entrée ANONYME, résolue en
        # index TEXT_* au build (le moteur est entièrement entier, une string
        # n'est qu'un index de la table). Les défauts couvrent tous les scripts
        # (y compris scène/caméra) ; les overrides ne vivent que sur un owner.
        from scripting.exports_parser import parse_exports
        from core.models.components import ScriptComponent

        def _add(value) -> None:
            if isinstance(value, str) and value and value not in keys:
                found.setdefault(anon_text_key(value), value)

        for path in script_paths(self):
            for e in parse_exports(path):
                if e.get("type") == "string":
                    _add(e.get("default"))

        # Variables et constantes de type `string` : même chemin, une entrée
        # anonyme par valeur non vide (une clé réelle du projet garde la sienne).
        for var in list(self.globals) + list(self.constants):
            if var.type == "string":
                _add(var.default if hasattr(var, "default") else var.value)

        # `global.titre = "Bonjour"` sur une globale string : le littéral écrit
        # dans un script est une entrée anonyme lui aussi.
        string_globals = {g.name for g in self.globals if g.type == "string"}
        if string_globals:
            import re
            assign = re.compile(r'\bglobal\.(\w+)\s*=\s*"([^"\n]*)"')
            for path in script_paths(self):
                try:
                    src = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                for name, literal in assign.findall(src):
                    if name in string_globals:
                        _add(literal)

        owners = [a for sc in self.scenes for a in sc.actors] + list(self.prefabs)
        for owner in owners:
            comp = next((c for c in getattr(owner, "components", [])
                         if isinstance(c, ScriptComponent)), None)
            if not comp or not getattr(comp, "script", None):
                continue
            sp = self.asset_abs(comp.script)
            if not sp or not sp.exists() or sp.suffix.lower() != ".lua":
                continue
            str_names = {e["name"] for e in parse_exports(sp)
                         if e.get("type") == "string"}
            for k, v in (getattr(comp, "exports_values", None) or {}).items():
                if k in str_names:
                    _add(v)

        return [Text(key=k, content=v) for k, v in sorted(found.items())]
    def build_texts(self) -> list:
        """La table de textes VUE PAR LE BUILD : les entrées du projet, puis les
        littéraux des scripts et les contenus locaux de l'interface.

        Les entrées réelles gardent leur rang — c'est lui qui fait l'index dans
        `g_texts`, et un littéral ajouté ne doit décaler aucune clé."""
        return (list(self.texts) + list(getattr(self, "_anon_texts", []))
                + self.inline_ui_texts())

    def inline_ui_texts(self) -> list:
        """Contenus locaux éphémères, jamais ajoutés à la table de l'éditeur.

        L'identité dépend de l'élément, pas du contenu ; les textes identiques
        de deux éléments restent indépendants.
        """
        out = []
        for lay, el in self.all_regions():
            if getattr(el, "text_key", "") or not getattr(el, "preview_text", ""):
                continue
            text = self.region_text(el)
            if text is not None:
                key = ui_text_build_key(lay, el)
                out.append(Text(id=key, key=key, content=text.content))
        return out
    def text_values(self) -> dict:
        """Valeurs à substituer aux marqueurs `$nom` d'un texte, à l'ÉDITION.

        Un global n'a de valeur courante qu'en jeu : l'éditeur montre sa valeur
        INITIALE, la seule qu'il connaisse et celle que la ROM affichera avant
        que quoi que ce soit ne l'ait changée. Une constante, elle, ne bouge
        jamais — l'aperçu montre exactement ce que l'encodeur cuira."""
        out = {g.name: g.default for g in self.globals}
        out.update({c.name: c.value for c in self.constants})
        return out
    # ── I/O textes (table de chaînes destinées au joueur) ───────────

    def save_texts(self):
        self._validate_texts(self.texts)
        data = {"texts": [t.to_dict() for t in self.texts]}
        self.texts_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.texts_file, project_json.dumps(data))

    def load_texts(self):
        self._text_repairs = []
        if not self.texts_file.exists():
            self.texts = []
            return
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f'Duplicate JSON key in texts.json: {key}')
                result[key] = value
            return result
        d = json.loads(self.texts_file.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        self.texts = [Text.from_dict(t) for t in d.get("texts", [])]
        # Un doublon (une fusion git, une édition à la main) ne ferme pas le projet : il est réparé et dit à l'ouverture.
        self._text_repairs = self._repair_texts()

    @staticmethod
    def _validate_texts(texts):
        for field in ('id', 'key'):
            seen = set()
            for text in texts:
                value = getattr(text, field)
                if value and value in seen:
                    raise ValueError(f'Duplicate text {field}: {value}')
                seen.add(value)

    def _repair_texts(self) -> list[str]:
        """Complète les identités manquantes des anciens fichiers et renumérote les doublons (l'id prime, c'est lui
        l'identité ; une clé en double est celle qu'on renumérote). Une phrase par doublon, pour `load_warnings`."""
        seen_ids: set[str] = set()
        seen_keys: set[str] = set()
        notes: list[str] = []
        for t in self.texts:
            if not t.id or t.id in seen_ids:
                if t.id:
                    notes.append(f"texts.json: id \"{t.id}\" was used twice; one entry got a new id")
                t.id = new_id(seen_ids)
            seen_ids.add(t.id)
            if not t.key or t.key in seen_keys:
                old = t.key
                t.key = text_key_from_path(t.path, taken=seen_keys, like=old)
                if old:
                    notes.append(f"texts.json: key \"{old}\" was used twice; the second entry is now \"{t.key}\"")
            seen_keys.add(t.key)
        return notes

    # ── CRUD textes ─────────────────────────────────────────────────

    def text_keys(self) -> set[str]:
        return {t.key for t in self.texts}

    def get_text(self, key: str) -> Optional[Text]:
        """Résolution par clé — l'unique chemin de résolution côté script."""
        return next((t for t in self.texts if t.key == key), None)

    def get_text_by_id(self, tid: str) -> Optional[Text]:
        """Résolution par id — pour les références stockées dans les fichiers
        de données (inspecteurs, scènes), insensibles au renommage."""
        # Index id → rang, vérifié à chaque lecture : la liste est modifiée de partout (ajout, suppression, restauration
        # d'un undo), donc un rang périmé se détecte (`texts[i].id` ne correspond plus) et l'index se refait.
        position = getattr(self, "_text_positions", {}).get(tid)
        texts = self.texts
        if position is None or position >= len(texts) or texts[position].id != tid:
            self._text_positions = {t.id: i for i, t in enumerate(texts)}
            position = self._text_positions.get(tid)
            if position is None:
                return None
        return texts[position]

    def migrate_legacy_pages(self) -> None:
        """Les anciennes `page_ids` d'une boîte deviennent une séquence ou un `text_key`.

        En mémoire seulement : le fichier n'est réécrit qu'à la prochaine sauvegarde du
        layout. Si les pages sont exactement une séquence, la boîte la suit ; sinon elle
        garde sa première page (les autres ne sont pas une séquence, rien à relier)."""
        from core.text_sequences import sequence_of
        for _layout, box in self.all_regions():
            ids = box.__dict__.pop("_legacy_page_ids", None)
            if not ids or getattr(box, "sequence_prefix", ""):
                continue
            pages = [t for tid in ids if (t := self.get_text_by_id(tid)) is not None]
            prefixes = {s[0] for t in pages if (s := sequence_of(t.key))}
            if len(pages) >= 2 and len(prefixes) == 1:
                from core.text_sequences import group_keys
                prefix = prefixes.pop()
                if group_keys(self, prefix) == [t.key for t in pages]:
                    box.sequence_prefix = prefix
                    continue
            if pages and not box.text_key:
                box.text_key = pages[0].key

    def textbox_pages(self, box) -> list:
        """Les textes qu'une boîte lit, dans l'ordre : sa séquence entière si elle
        en suit une, sinon son seul `text_key`. Dérivé à chaque lecture."""
        if getattr(box, "sequence_prefix", ""):
            from core.text_sequences import group_texts
            return group_texts(self, box.sequence_prefix)
        entry = self.get_text(box.text_key) if getattr(box, "text_key", "") else None
        return [entry] if entry is not None else []

    def new_text(self, content: str = "", scene: str = "", path=None) -> Text:
        """Crée une entrée. La clé dérive du chemin de rangement, jamais du
        contenu (cf. models/text.py).

        Un texte créé depuis une scène naît sous un nœud portant son nom :
        l'arbre se remplit tout seul, et le chemin par défaut situe déjà."""
        p = norm_text_path(path if path is not None else ([scene] if scene else []))
        t = Text(
            id      = new_id({x.id for x in self.texts}),
            key     = text_key_from_path(p, taken=self.text_keys()),
            content = content,
            scene   = scene,
        )
        self.texts.append(t)
        return t

    def text_path_keys(self, entries) -> list:
        """[(texte, clé)] que de nouveaux chemins produiraient, sans rien appliquer.

        `entries` : [(texte, nouveau chemin)]. Les clés du lot ne comptent pas comme prises (elles
        changent ensemble) mais chaque clé choisie l'est pour la suivante ; le résultat convient à
        `rename_text_keys`, échanges compris. Ranger un texte, c'est renommer sa clé."""
        members = {text.id for text, _path in entries}
        taken = {t.key for t in self.texts if t.id not in members}
        out = []
        for text, path in entries:
            key = text_key_from_path(path, taken=taken, like=text.key)
            taken.add(key)
            out.append((text, key))
        return out

    def rename_text_key(self, text: Text, new_key: str) -> bool:
        """Renomme la clé. Retourne False si le nom est vide ou déjà pris —
        l'appelant (UI) affiche l'erreur. Les appels text:draw("clé") des
        scripts suivent (cf. rename_lua_refs).

        Les libellés de `path` se réalignent sur la nouvelle clé."""
        with self.consumers_follow([text]):
            return self._apply_text_key(text, new_key)

    @contextmanager
    def consumers_follow(self, texts):
        """Un groupe renommé d'un bloc emporte les tables et boîtes qui le lisent.
        Seul l'appel le plus extérieur agit : les clés temporaires d'un échange n'en sont pas."""
        from core.text_sequences import snapshot_groups, follow_groups
        if getattr(self, "_following", False):
            yield
            return
        self._following = True
        try:
            before = snapshot_groups(self, texts)
            yield
            follow_groups(self, before)
        finally:
            self._following = False

    def rename_text_keys(self, entries) -> None:
        """Rename a complete set, including swaps, without merging references."""
        entries = [(text, key) for text, key in entries if text.key != key]
        with self.consumers_follow([text for text, _ in entries]):
            self._rename_text_keys(entries)

    def _rename_text_keys(self, entries) -> None:
        members = {text.id for text, _ in entries}
        targets = [key for _, key in entries]
        if (len(members) != len(entries) or len(set(targets)) != len(targets)
                or any(not key or self.get_text_by_id(text.id) is not text for text, key in entries)
                or any(t.key in targets for t in self.texts if t.id not in members)):
            raise ValueError('Text key already exists')
        from core.models.unique_name import unique_name
        taken = self.text_keys() | set(targets)
        temporary = []
        for text, key in entries:
            temp = unique_name('__text_rename_' + text.id, taken)
            taken.add(temp)
            temporary.append((text, temp, key))
        applied = []
        with self._renaming():
            from scripting.refactor import script_paths
            files = set(script_paths(self))
            files.update(self.ui_layouts.path_of(layout) for layout in self.ui_layouts)
            files.update(self.data_tables.path_of(table) for table in self.data_tables)
            disk = {path: path.read_text(encoding='utf-8') if path.exists() else None for path in files}
            original = [(t, t.key) for t, _ in entries]
            regions = [(r, r.text_key) for _, r in self.all_regions()]
            cells = [(row, col.name, col.name in row, row.get(col.name))
                     for table in self.data_tables for row in table.rows for col in table.columns
                     if col.type == 'text']
            try:
                for text, key in ([(t, temp) for t, temp, _ in temporary] + entries):
                    old = text.key
                    if not self.rename_text_key(text, key):
                        raise ValueError('Cannot rename text key')
                    applied.append((text, old))
            except Exception:
                for text, key in original:
                    text.key = key
                for region, key in regions:
                    region.text_key = key
                for row, name, present, value in cells:
                    if present:
                        row[name] = value
                    else:
                        row.pop(name, None)
                for path, content in disk.items():
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(path, content)
                raise

    def _apply_text_key(self, text: Text, new_key: str) -> bool:
        new_key = (new_key or "").strip()
        if not new_key or any(t.key == new_key and t is not text for t in self.texts):
            return False
        old_key = text.key
        if new_key == old_key:
            return True
        # Import LOCAL, comme partout dans ce fichier : `scripting` importe le
        # projet, le remonter en tête du module ferait un cycle.
        from scripting.api import DOMAIN_TEXT
        with self._renaming():
            refs = self.rename_lua_refs(DOMAIN_TEXT, old_key, new_key)
            # `region.text_key` est une COPIE de chaîne, pas l'id stable du
            # texte (cf. models/text.py) : sans ce rattrapage, ranger une
            # entrée ailleurs recale sa clé auto SANS suivre les zones
            # d'interface qui la citaient, et l'écran de scène affiche
            # silencieusement le mauvais texte (ou plus rien). Même geste que
            # `rename_lua_refs` juste au-dessus, pour l'autre des deux seuls
            # référents d'une clé de texte (cf. TextUsage).
            touched_layouts = []   # dédupliqué par IDENTITÉ : UILayout n'est pas hashable
            n_regions = 0
            for layout, region in self.all_regions():
                if region.text_key == old_key:
                    region.text_key = new_key
                    if not any(layout is L for L in touched_layouts):
                        touched_layouts.append(layout)
                    n_regions += 1
            for layout in touched_layouts:
                self.ui_layouts.save(layout)
            # Les cellules text contiennent des clés lisibles ; les pages,
            # elles, gardent leurs ids et n'ont aucune réécriture à subir.
            for table in getattr(self, "data_tables", []):
                changed = False
                for col in table.columns:
                    if col.type != "text":
                        continue
                    for row in table.rows:
                        if str(table.value(row, col) or "").strip() == old_key:
                            row[col.name] = new_key
                            changed = True
                if changed:
                    self.data_tables.save(table)
            text.key = new_key
        self._notify_renamed("Text", old_key, new_key, refs, n_regions=n_regions)
        return True

    def delete_text(self, text: Text):
        if text in self.texts:
            self.texts.remove(text)

    # ── Qui cite un texte ─────────────────────────────────────────

    # ── Ce qu'une zone d'interface affiche ────────────────────────

    def region_text(self, region):
        """L'entrée de la table qu'une zone d'interface montre, ou None.

        La première page par id, sinon le contenu AUTHORÉ (`text_key`, posé à
        l'init), sinon le contenu local (`preview_text`), également posé à
        l'init. Ce dernier ne devient jamais une entrée du projet ; le build
        lui attribue une référence interne.

        Une ancienne valeur de `preview_text` qui est une clé reste comprise :
        les projets enregistrés avant le littéral conservent leur aperçu."""
        if getattr(region, "sequence_prefix", ""):
            pages = self.textbox_pages(region)
            return pages[0] if pages else None
        key = getattr(region, "text_key", "") or ""
        if key:
            return self.get_text(key)
        preview = getattr(region, "preview_text", "") or ""
        if not preview:
            return None
        if not getattr(region, "preview_is_literal", True):
            legacy = self.get_text(preview)
            if legacy is not None:
                return legacy
        from core.models.text import Text
        return Text(content=preview)

    def region_texts(self, region) -> list:
        """Tous les contenus possibles d'un élément, sans dépendre de l'aperçu.
        Les références absentes sont diagnostiquées séparément au build.
        """
        if getattr(region, "sequence_prefix", ""):
            return self.textbox_pages(region)
        initial = self.region_text(region)
        return [initial] if initial is not None else []

    def region_animated_glyphs(self, region) -> int:
        """Glyphes animés à RÉSERVER pour cette zone — dérivé, jamais déclaré.

        Le maximum sur toutes les pages et langues, pas seulement la source : une
        traduction peut poser `[wave]` sur plus de caractères que l'original,
        et la ROM contient les deux. Sous-réserver ferait retomber l'effet en
        statique dans cette langue-là, sans que rien ne l'ait annoncé — même
        raisonnement que le contrôle de débordement du validateur.

        Plafonné à `ANIM_GLYPH_MAX` : au-delà, le runtime écrête de toute
        façon (tableaux de capture de taille fixe), et l'éditeur le signale
        plutôt que de réserver ce que le matériel refuse."""
        from core.text_markup import parse
        from core.models.ui_region import ANIM_GLYPH_MAX
        best = 0
        for text in self.region_texts(region):
            best = max(best, parse(text.content or "").animated_glyphs)
            for lang in getattr(self.settings, "languages", []):
                raw = self.translations.get(lang.code, {}).get(text.id, "")
                if raw:
                    best = max(best, parse(raw).animated_glyphs)
        return min(ANIM_GLYPH_MAX, best)

    def layout_animated_glyphs(self, layout) -> dict:
        """{nom de zone: glyphes animés} — la forme qu'attend
        `layout_obj_budget`, qui ne résout pas la table lui-même."""
        return {r.name: self.region_animated_glyphs(r) for r in layout.slots}

    def text_usage_index(self) -> TextUsageIndex:
        """{clé: TextUsage} pour tout le projet, en un seul parcours.

        Point UNIQUE de la question « qui utilise ce texte ? ». Elle se posait à
        deux endroits — la table et l'inspecteur — et l'inspecteur ne regardait
        que les scripts : une même question, deux réponses.

        Un seul parcours des scripts, parce que luaparser est trop lent pour
        être relancé à chaque sélection : l'appelant garde l'index et
        l'invalide sur `scripts_changed` ET `ui_text_links_changed` — un
        `region.text_key` rebranché périme l'index tout autant qu'un script
        réécrit."""
        idx = TextUsageIndex()
        try:
            from scripting.refactor import index_refs_in_project
            from scripting.api import DOMAIN_TEXT
            for key, per_script in index_refs_in_project(self, DOMAIN_TEXT).items():
                idx.by_key.setdefault(key, TextUsage()).scripts.update(per_script)
        except Exception:
            # luaparser absent ou scripts illisibles : l'index le DIT. Rendre
            # zéro ferait passer tout le projet pour orphelin.
            idx.scripts_scanned = False
        for layout, region in self.all_regions():
            keys = ([t.key for t in self.textbox_pages(region)]
                    if getattr(region, "sequence_prefix", "") else [region.text_key])
            for key in dict.fromkeys(keys):
                if not key:
                    continue
                idx.by_key.setdefault(key, TextUsage()).regions.append(
                    (layout.name, region.name))
        for table in getattr(self, "data_tables", []):
            for col in table.columns:
                if col.type == "text":
                    for n, row in enumerate(table.rows, 1):
                        key = str(table.value(row, col) or "").strip()
                        if key:
                            idx.by_key.setdefault(key, TextUsage()).tables.append(
                                (table.name, n, col.name))
        return idx
