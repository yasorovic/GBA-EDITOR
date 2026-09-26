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
from dataclasses import dataclass, field
from typing import Optional

from core.resources.resource_store import atomic_write
from core.models import project_json
from core.models.text import (
    Text, key_from_path as text_key_from_path, norm_path as norm_text_path,
    new_id as new_text_id,
)


# ── Qui cite un texte ─────────────────────────────────────────────


@dataclass
class TextUsage:
    """Les citations d'une entrée de la table, par source.

    **Deux sources, jamais une seule** : un script (`text:draw("clé")`) et une
    mise en page (`UIText.text_key`). N'en compter qu'une afficherait
    « orphelin » sur un texte posé dans une boîte de dialogue — et un orphelin,
    ça se supprime.
    """
    scripts: dict = field(default_factory=dict)   # {chemin du .lua: occurrences}
    regions: list = field(default_factory=list)   # [(mise en page, région)]

    @property
    def count(self) -> int:
        return sum(self.scripts.values()) + len(self.regions)

    def summary(self) -> str:
        """Ce qui tient dans une cellule : « 2 scripts · 1 layout »."""
        parts = []
        if self.scripts:
            parts.append(f"{len(self.scripts)} script"
                         + ("s" if len(self.scripts) > 1 else ""))
        if self.regions:
            parts.append(f"{len(self.regions)} layout"
                         + ("s" if len(self.regions) > 1 else ""))
        return " · ".join(parts)

    def detail(self) -> str:
        """Le détail, pour un survol : un site par ligne."""
        lines = [f"{p.name} ×{n}" if n > 1 else p.name
                 for p, n in sorted(self.scripts.items())]
        lines += [f"{lay} › {reg}" for lay, reg in sorted(self.regions)]
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
        littéraux des scripts.

        Les entrées réelles gardent leur rang — c'est lui qui fait l'index dans
        `g_texts`, et un littéral ajouté ne doit décaler aucune clé."""
        return list(self.texts) + list(getattr(self, "_anon_texts", []))
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
        data = {"texts": [t.to_dict() for t in self.texts]}
        self.project_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.texts_file, project_json.dumps(data))

    def load_texts(self):
        self.texts = []
        if not self.texts_file.exists():
            return
        d = json.loads(self.texts_file.read_text(encoding="utf-8"))
        self.texts = [Text.from_dict(t) for t in d.get("texts", [])]
        self._repair_texts()

    def _repair_texts(self):
        """Rattrape un fichier édité à la main : id manquant ou dupliqué, clé
        manquante ou dupliquée. L'id prime — c'est lui l'identité ; une clé en
        double est celle qu'on renumérote."""
        seen_ids: set[int] = set()
        seen_keys: set[str] = set()
        for t in self.texts:
            t.path = norm_text_path(t.path)
            if not t.id or t.id in seen_ids:
                t.id = new_text_id(seen_ids)
            seen_ids.add(t.id)
            if not t.key or t.key in seen_keys:
                t.key = text_key_from_path(t.path, taken=seen_keys)
            seen_keys.add(t.key)

    # ── CRUD textes ─────────────────────────────────────────────────

    def text_keys(self) -> set[str]:
        return {t.key for t in self.texts}

    def get_text(self, key: str) -> Optional[Text]:
        """Résolution par clé — l'unique chemin de résolution côté script."""
        return next((t for t in self.texts if t.key == key), None)

    def get_text_by_id(self, tid: int) -> Optional[Text]:
        """Résolution par id — pour les références stockées dans les fichiers
        de données (inspecteurs, scènes), insensibles au renommage."""
        return next((t for t in self.texts if t.id == tid), None)

    def new_text(self, content: str = "", scene: str = "", path=None) -> Text:
        """Crée une entrée. La clé dérive du chemin de rangement, jamais du
        contenu (cf. models/text.py).

        Un texte créé depuis une scène naît sous un nœud portant son nom :
        l'arbre se remplit tout seul, et le chemin par défaut situe déjà."""
        p = norm_text_path(path if path is not None else ([scene] if scene else []))
        t = Text(
            id      = new_text_id({x.id for x in self.texts}),
            key     = text_key_from_path(p, taken=self.text_keys()),
            path    = p,
            content = content,
            scene   = scene,
        )
        self.texts.append(t)
        return t

    def text_path_key(self, text: Text) -> str:
        """Clé que le chemin actuel de `text` produirait — sans l'appliquer.
        Sa propre clé est exclue des collisions, sinon un texte déjà posé au
        bon endroit se verrait proposer un rang `_02` contre lui-même."""
        return text_key_from_path(text.path, taken=self.text_keys() - {text.key})

    def rename_text_key(self, text: Text, new_key: str) -> bool:
        """Renommage MANUEL. Retourne False si le nom est vide ou déjà pris —
        l'appelant (UI) affiche l'erreur. Les appels text:draw("clé") des
        scripts suivent (cf. rename_lua_refs).

        La clé se DÉTACHE alors du chemin (`auto_key=False`) : elle appartient
        à l'utilisateur, ranger le texte ailleurs ne la touchera plus."""
        return self._apply_text_key(text, new_key, manual=True)

    def resync_text_key(self, text: Text) -> Optional[str]:
        """Recale une clé automatique sur le chemin de rangement, et retourne
        la nouvelle clé (None si rien n'a bougé).

        No-op sur une clé nommée à la main — c'est tout l'intérêt de
        `auto_key` : le rangement reste un geste cosmétique tant que
        l'utilisateur n'a pas pris la main sur la clé."""
        if not text.auto_key:
            return None
        want = self.text_path_key(text)
        return want if (want != text.key
                        and self._apply_text_key(text, want, manual=False)) else None

    def restore_text_key(self, text: Text, key: str) -> bool:
        """Repose une clé telle quelle sans la marquer « nommée à la main ».

        Sert à l'ANNULATION d'un rangement : rejouer `resync_text_key` en sens
        inverse ne rendrait pas forcément la même clé (le rang `_NN` dépend des
        clés prises à cet instant), il faut donc remettre l'exacte ancienne."""
        return self._apply_text_key(text, key, manual=False)

    def _apply_text_key(self, text: Text, new_key: str, *, manual: bool) -> bool:
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
            text.key = new_key
            if manual:
                text.auto_key = False
        self._notify_renamed("Text", old_key, new_key, refs, n_regions=n_regions)
        return True

    def delete_text(self, text: Text):
        if text in self.texts:
            self.texts.remove(text)

    # ── Qui cite un texte ─────────────────────────────────────────

    # ── Ce qu'une zone d'interface affiche ────────────────────────

    def region_text(self, region):
        """L'entrée de la table qu'une zone d'interface montre, ou None.

        Deux sources dans cet ordre : le contenu AUTHORÉ (`text_key`, posé à
        l'init), sinon l'ÉCHANTILLON (`preview_text`) — qui n'est jamais
        compilé mais qui est, pour une zone remplie par un script, la seule
        idée que l'éditeur ait de ce qui y atterrira."""
        key = (getattr(region, "text_key", "")
               or getattr(region, "preview_text", "") or "")
        return self.get_text(key) if key else None

    def region_animated_glyphs(self, region) -> int:
        """Glyphes animés à RÉSERVER pour cette zone — dérivé, jamais déclaré.

        Le maximum sur toutes les langues, pas seulement la source : une
        traduction peut poser `[wave]` sur plus de caractères que l'original,
        et la ROM contient les deux. Sous-réserver ferait retomber l'effet en
        statique dans cette langue-là, sans que rien ne l'ait annoncé — même
        raisonnement que le contrôle de débordement du validateur.

        Plafonné à `ANIM_GLYPH_MAX` : au-delà, le runtime écrête de toute
        façon (tableaux de capture de taille fixe), et l'éditeur le signale
        plutôt que de réserver ce que le matériel refuse."""
        from core.text_markup import parse
        from core.models.ui_region import ANIM_GLYPH_MAX
        text = self.region_text(region)
        if text is None:
            return 0
        best = parse(text.content or "").animated_glyphs
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
            if region.text_key:
                idx.by_key.setdefault(region.text_key, TextUsage()).regions.append(
                    (layout.name, region.name))
        return idx
