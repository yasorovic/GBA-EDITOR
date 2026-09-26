"""core/project_variables.py — globals et constantes du projet.

Leur I/O, leur identité et leur CRUD. Le renommage d'une variable vit ICI et non
avec les renommages d'assets : il partage `_variable_list` et la vérification
d'unicité avec la création, alors qu'il n'a ni fichier à déplacer ni sidecar à
réparer.

L'`id` opaque est la clé de tout : c'est lui que citent les références de champ
et les fichiers de sauvegarde, et c'est pour ça qu'un renommage ne le touche pas.

Une TRANCHE de la classe `Project`, pas un module autonome : les méthodes
ci-dessous s'appellent `self.…` entre elles et avec le reste de `Project`. La
découpe sert la lecture — chaque responsabilité dans son fichier — sans ajouter
le moindre saut d'appel : un mixin est résolu à la construction de la classe,
`project.add_variable()` s'écrit exactement comme avant.

**Ce fichier n'importe jamais `core.project`** : ce serait un cycle immédiat,
puisque `project.py` l'importe pour composer la classe.
"""

import json

from core.resources.resource_store import atomic_write
from core.models import project_json
from core.models.ids import new_id
from core.models.settings import GlobalVar, Constant
from scripting.api import DOMAIN_GLOBAL


class ProjectVariablesMixin:
    # ── I/O variables (globals + constants) ─────────────────────────
    # Assets côté éditeur sans dépendance externe -> project/variables.json,
    # pas project.json (config racine uniquement, cf. ARCHITECTURE.md).

    def save_variables(self):
        data = {
            "globals": [
                {"id": g.id, "name": g.name, "type": g.type,
                 "default": g.default, "desc": g.desc, "persist": g.persist,
                 # Écrit seulement s'il y a quelque chose à dire : un scalaire
                 # (le cas de toutes les variables d'avant la v0.20) ne gagne
                 # pas une clé dans le fichier de projet.
                 **({"count": g.count} if g.count > 1 else {})}
                for g in self.globals
            ],
            "constants": [
                {"id": c.id, "name": c.name, "type": c.type,
                 "value": c.value, "desc": c.desc}
                for c in self.constants
            ],
        }
        self.project_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.variables_file, project_json.dumps(data))

    def load_variables(self):
        self.globals = []
        self.constants = []
        if not self.variables_file.exists():
            return
        d = json.loads(self.variables_file.read_text(encoding="utf-8"))
        self.globals = [
            GlobalVar(
                name    = g.get("name", "var"),
                type    = g.get("type", "int"),
                default = g.get("default", 0),
                desc    = g.get("desc", ""),
                id      = int(g.get("id", 0)),
                persist = bool(g.get("persist", False)),
                # Absent = scalaire : c'est ce qu'était toute variable avant la
                # v0.20, donc un projet existant se relit à l'identique.
                count   = max(1, int(g.get("count", 1) or 1)),
            )
            for g in d.get("globals", [])
        ]
        self.constants = [
            Constant(
                name  = c.get("name", "const"),
                type  = c.get("type", "int"),
                value = c.get("value", 0),
                desc  = c.get("desc", ""),
                id    = int(c.get("id", 0)),
            )
            for c in d.get("constants", [])
        ]

    # ── Identité des variables ──────────────────────────────────────

    def all_variables(self) -> list:
        """Globals puis constantes — l'ordre d'affichage, pas un ordre de C."""
        return list(self.globals) + list(self.constants)

    def assign_variable_ids(self) -> int:
        """Donne un id aux variables qui n'en ont pas.

        C'est ce qui rend `variables.json` éditable à la main : un id est un
        entier opaque, personne ne peut en inventer un, donc une variable
        ajoutée au clavier n'en a pas et le reçoit ici. Idempotent — une
        variable qui en a déjà un n'est jamais renumérotée, sans quoi tout ce
        qui la référence casserait à l'ouverture suivante."""
        taken = {v.id for v in self.all_variables() if v.id}
        n = 0
        for v in self.all_variables():
            if not v.id:
                v.id = new_id(taken)
                taken.add(v.id)
                n += 1
        return n
    # ── CRUD variables (globals / constants) ────────────────────────
    # Unicité vérifiée PAR TYPE uniquement : un global et une constante
    # peuvent partager un nom (préfixes C distincts : g_<nom> / CONST_<NOM>).

    def _variable_list(self, kind: str) -> list:
        """kind: "global" | "const" """
        return self.constants if kind == "const" else self.globals

    def variable_name_taken(self, kind: str, name: str, *, exclude=None) -> bool:
        return any(e is not exclude and e.name == name for e in self._variable_list(kind))

    def add_variable(self, kind: str, name: str):
        """Ajoute un global ou une constante. Retourne None si le nom est vide ou déjà pris (par type)."""
        name = name.strip()
        if not name or self.variable_name_taken(kind, name):
            return None
        entry = Constant(name=name) if kind == "const" else GlobalVar(name=name)
        # Id tout de suite, et pas au prochain chargement du projet : c'est lui
        # qui identifie la variable dans une référence de champ comme dans un
        # fichier de sauvegarde. Une variable sans id est une variable sans
        # identité, y compris pendant la session qui vient de la créer.
        entry.id = new_id({v.id for v in self.all_variables() if v.id})
        self._variable_list(kind).append(entry)
        self.save_variables()
        return entry

    def rename_variable(self, kind: str, entry, new_name: str) -> bool:
        """Renomme en place. Retourne False (no-op) si le nom est vide/inchangé/déjà pris."""
        new_name = new_name.strip()
        if not new_name or new_name == entry.name:
            return False
        if self.variable_name_taken(kind, new_name, exclude=entry):
            return False
        old_name = entry.name
        with self._renaming():
            # `global.nom` / `const.nom` (chantier global/const) se citent par
            # IDENTIFIANT, pas par chaîne littérale — `rename_var_in_project`
            # couvre les DEUX. `rename_lua_refs`/DOMAIN_GLOBAL, en plus, pour
            # `save:read(slot, "nom")` : seul site qui garde un nom entre
            # guillemets (une CONSTANTE n'a plus aucun site littéral).
            from scripting.refactor import rename_var_in_project
            ns = "const" if kind == "const" else "global"
            refs = (self.rename_lua_refs(DOMAIN_GLOBAL, old_name, new_name)
                   if kind == "global" else {})
            for path, n in rename_var_in_project(self, ns, old_name, new_name).items():
                refs[path] = refs.get(path, 0) + n
            n_texts = self.rename_var_in_texts(old_name, new_name)
            entry.name = new_name
            self.save_variables()
        self._notify_renamed("Constant" if kind == "const" else "Global",
                             old_name, new_name, refs,
                             n_texts=n_texts)
        return True

    def rename_var_in_texts(self, old_name: str, new_name: str) -> int:
        """Réécrit les `$nom` des entrées de texte. Retourne le nombre d'entrées
        touchées.

        Un `$nom` est du texte ÉCRIT À LA MAIN, comme un script : il cite la
        variable par son nom, pas par son id, donc c'est au renommage de le
        suivre. Les références stockées dans des fichiers de données, elles,
        citent l'id et n'ont rien à faire ici."""
        from core.text_markup import rename_value
        n = 0
        for t in self.texts:
            content = rename_value(t.content, old_name, new_name)
            if content != t.content:
                t.content = content
                n += 1
        if n:
            self.save_texts()
        return n
