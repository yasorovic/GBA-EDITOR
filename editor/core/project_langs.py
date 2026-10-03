"""core/project_langs.py — les traductions : un fichier par langue, à côté du
maître.

```
project/texts.json      le MAÎTRE — id, key, path, note, contenu SOURCE
project/texts_de.json   un SIDE   — la traduction seule, jointe par id
```

**Le maître possède la structure, le side ne porte que la traduction.** `id`,
`key`, `path` et `note` vivent dans `texts.json` et nulle part ailleurs : les
recopier dans huit fichiers donnerait huit vérités à tenir d'accord, et la
neuvième serait fausse.

**Le side se joint par `id`.** C'est ce que l'id opaque est fait pour faire —
renommer une clé ou re-ranger une entrée ne doit pas casser huit traductions.
`key` et le texte source y sont écrits À CÔTÉ de chaque entrée, pour qu'un
humain lise le fichier et qu'un diff git ait un sens ; ils sont **recalés à
chaque écriture depuis le maître**, jamais relus. Ce n'est pas un second
identifiant, c'est une annotation : en cas de désaccord, le maître a raison.

**Une entrée absente n'est pas une chaîne vide, c'est la SOURCE.** Un trou de
traduction doit se voir comme un texte de la mauvaise langue, jamais comme un
écran blanc que personne ne saura interpréter sur console. C'est aussi ce qui
garde les fichiers courts : on écrit ce qui est traduit, pas la table entière.

Une TRANCHE de la classe `Project`, comme `project_texts` — et pour la même
raison : `project.load_translations()` s'écrit comme le reste, sans saut
d'appel. **Ce fichier n'importe jamais `core.project`** : ce serait un cycle.
"""

import json
from pathlib import Path
from typing import Optional

from core.resources.resource_store import atomic_write
from core.models import project_json


class ProjectLangsMixin:

    # ── Où vivent les traductions ─────────────────────────────────

    def translation_file(self, code: str) -> Path:
        """`project/texts_<code>.json`. Le code EST le nom du fichier — d'où
        `lang_code()`, qui le rend utilisable comme tel."""
        return self.project_dir / f"texts_{code}.json"

    def is_multilingual(self) -> bool:
        """Vrai dès qu'une traduction est déclarée. Faux = le projet se
        comporte exactement comme avant la v0.9."""
        return bool(self.settings.languages)

    # ── I/O ───────────────────────────────────────────────────────

    def load_translations(self):
        """Charge tous les sides déclarés. `{code: {id du texte: contenu}}`.

        Une langue déclarée dont le fichier manque n'est pas une erreur : c'est
        une langue dont rien n'est encore traduit."""
        self.translations = {}
        self.translation_problems = {}
        for lang in self.settings.languages:
            self.translations[lang.code] = self._read_translation(lang.code)

    def _read_translation(self, code: str) -> dict:
        path = self.translation_file(code)
        if not path.exists():
            return {}
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # Un side illisible ne doit pas empêcher d'ouvrir le projet : le
            # jeu reste jouable dans sa langue source, ce qui est exactement ce
            # que dit la règle du repli. Mais la perte se dit : le validateur la relit ici.
            self.translation_problems[code] = f"{type(exc).__name__}: {exc}"
            return {}
        out = {}
        for e in d.get("texts", []):
            tid = int(e.get("id", 0) or 0)
            # `key` et `source` sont là pour l'humain : on ne les relit pas.
            if tid:
                out[tid] = str(e.get("content", ""))
        return out

    def save_translation(self, code: str):
        """Écrit un side. Les entrées vides ne sont pas écrites — une entrée
        absente vaut la source, une entrée vide voudrait dire « traduit par
        rien », ce qui n'existe pas."""
        by_id = self.translations.get(code, {})
        by_id_master = {t.id: t for t in self.texts}
        entries = []
        for t in self.texts:
            content = by_id.get(t.id, "")
            if not content:
                continue
            entries.append({
                "id": t.id,
                # Recalés depuis le maître à chaque écriture : ce sont des
                # annotations de lecture, pas des données.
                "key": t.key,
                "source": t.content,
                "content": content,
            })
        # Une traduction dont l'entrée maître a disparu n'est pas jetée en
        # silence : elle est conservée telle quelle, sans annotation possible.
        # Supprimer un texte par erreur ne doit pas détruire huit traductions.
        for tid, content in sorted(by_id.items()):
            if tid not in by_id_master and content:
                entries.append({"id": tid, "content": content})
        self.project_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.translation_file(code),
                     project_json.dumps({"lang": code, "texts": entries}))

    def ensure_translation_file(self, code: str):
        """Crée le side vide d'une langue qu'on vient de déclarer.

        Le fichier existe donc AVANT la première traduction : il est ajouté à
        git avec la déclaration, et un traducteur qui clone le dépôt trouve un
        fichier à remplir plutôt qu'un fichier à inventer."""
        # RELU quand la langue n'est pas en mémoire, et pas seulement mis à
        # vide : re-déclarer une langue — ou annuler son retrait — doit lui
        # rendre son travail, qui n'a jamais quitté le disque. Un `setdefault`
        # rendait une langue vide en la re-déclarant, ce qui fait perdre la
        # traduction à la première sauvegarde.
        if code not in self.translations:
            self.translations[code] = self._read_translation(code)
        if not self.translation_file(code).exists():
            self.save_translation(code)

    def prune_empty_translations(self, declared: set):
        """Jette les sides VIDES dont la langue n'est plus déclarée.

        Deux gestes courants en laissent derrière eux : ajouter une langue puis
        lui donner son vrai code (le fichier provisoire reste), et corriger un
        code (`de` → `deu`). Un fichier sans une seule traduction ne porte aucun
        travail — le garder ne protégerait rien et encombrerait le dépôt.

        La réciproque est la règle qui compte : **dès qu'un side contient une
        traduction, il n'est plus jamais supprimé automatiquement**, même si sa
        langue disparaît de la déclaration."""
        for path in self.project_dir.glob("texts_*.json"):
            code = path.stem[len("texts_"):]
            if code in declared:
                continue
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue          # illisible : on n'y touche pas
            if not d.get("texts"):
                path.unlink(missing_ok=True)

    def forget_translations(self, code: str):
        """Retire une langue de la MÉMOIRE, sans toucher au fichier.

        Le fichier reste sur le disque : c'est du travail humain, et le
        supprimer parce qu'on a décoché une case serait une perte qu'aucun
        undo ne rattrape. Re-déclarer la langue le relit tel quel."""
        self.translations.pop(code, None)

    # ── Lecture ───────────────────────────────────────────────────

    def text_content(self, text, code: str = "") -> str:
        """Le contenu d'une entrée dans une langue — **le point unique du
        repli**.

        Code vide, langue inconnue, ou entrée non traduite : la SOURCE. Cette
        règle ne doit exister qu'ici ; dupliquée, elle finirait par rendre une
        chaîne vide quelque part."""
        if code and code != self.settings.source_lang.code:
            got = self.translations.get(code, {}).get(text.id, "")
            if got:
                return got
        return text.content

    def translation_gaps(self, code: str) -> list:
        """Les entrées que cette langue n'a pas encore traduites.

        Sert au compte affiché par l'éditeur et au journal de build : un trou
        se répare tant qu'on sait lequel c'est."""
        by_id = self.translations.get(code, {})
        return [t for t in self.texts if not by_id.get(t.id, "")]
