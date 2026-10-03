"""core/project_paths.py — où chaque chose vit sur le disque.

Toutes les propriétés dérivent de `self.root` et rien d'autre : ce sont des
chemins CANONIQUES, la seule réponse à « où est-ce rangé ». Il n'y en a jamais
deux pour la même chose : les anciens emplacements ne sont plus lus nulle part
(cf. `core/project.py`, « Aucune migration de format »), donc ils ne se nomment
plus ici. **Une exception, le manifeste** : depuis v0.10 il s'appelle
`<Nom>.project` (cf. `find_manifest`), et l'ancien `project.json` se lit
encore une fois — le pont assumé le temps que les projets d'avant se réécrivent
à leur première sauvegarde.

Une TRANCHE de la classe `Project`, pas un module autonome : les méthodes
ci-dessous s'appellent `self.…` entre elles et avec le reste de `Project`. La
découpe sert la lecture — chaque responsabilité dans son fichier — sans ajouter
le moindre saut d'appel : un mixin est résolu à la construction de la classe,
`project.src_dir` s'écrit exactement comme avant.

**Ce fichier n'importe jamais `core.project`** : ce serait un cycle immédiat,
puisque `project.py` l'importe pour composer la classe.
"""

from __future__ import annotations

from pathlib import Path


# Le manifeste porte le nom du projet : <Nom>.project. Son extension est ce
# que Windows et Linux associent à l'éditeur — un point d'entrée sans OS, à la
# place du .bat qui ne valait que sous Windows (cf. ROADMAP v0.10).
PROJECT_EXT = ".project"

# Ancien manifeste, d'avant v0.10. Encore lu une fois par find_manifest quand
# aucun .project n'existe, puis supprimé à la première sauvegarde
# (Project.save_settings) : le projet se réécrit dans la nouvelle forme sans
# convertisseur à lancer.
LEGACY_MANIFEST_NAME = "project.json"


# Version du FORMAT des fichiers de projet, écrite dans le manifeste. Distincte
# de `version` (celle du JEU, saisie par l'auteur). Absente = projet d'avant
# son introduction. À incrémenter seulement quand une écriture devient illisible
# par l'éditeur précédent ; un projet plus récent que l'éditeur est refusé.
PROJECT_FORMAT_VERSION = 1


class ProjectManifestError(Exception):
    """Un dossier porte plusieurs `.project`. L'éditeur refuse de choisir un
    manifeste sur deux — c'est une copie manuelle, un cas anormal qu'on signale
    au lieu de deviner (cf. ROADMAP v0.10, « refus explicite »)."""


class ProjectFileError(ProjectManifestError):
    """Le projet existe mais un de ses fichiers est illisible (JSON tronqué,
    encodage invalide, champ attendu absent). Sous-classe de
    `ProjectManifestError` : tout appelant qui sait refuser un dossier ambigu
    sait aussi montrer ce message et rester sur l'écran courant."""


class ProjectNotFoundError(ProjectManifestError):
    """Le dossier n'est pas un projet : aucun manifeste. Sous-classe de
    `ProjectManifestError` pour que tout appelant qui refuse déjà un dossier
    ambigu refuse aussi un dossier vide, avec le même message à l'écran."""


def find_manifest(root: Path) -> Path | None:
    """Le manifeste d'un dossier projet, ou None si le dossier n'en est pas un.

    - Exactement un `*.project` → ce fichier (le nom du projet est son stem).
    - Aucun, mais un `project.json` (forme d'avant v0.10) → le legacy, que la
      première sauvegarde réécrira.
    - Aucun des deux → None : ce dossier n'est pas un projet.
    - Plusieurs `*.project` → `ProjectManifestError` : on ne devine pas.
    """
    manifests = sorted(root.glob(f"*{PROJECT_EXT}"))
    if len(manifests) > 1:
        names = ", ".join(m.name for m in manifests)
        raise ProjectManifestError(
            f"\"{root.name}\" contains {len(manifests)} manifests ({names}). Keep only one.")
    if manifests:
        return manifests[0]
    legacy = root / LEGACY_MANIFEST_NAME
    return legacy if legacy.exists() else None


class ProjectPathsMixin:
    # ── Chemins canoniques ────────────────────────────────────────

    @property
    def assets_dir(self) -> Path:
        """Espace libre utilisateur — PNGs bruts, sons..."""
        return self.root / "assets"

    @property
    def project_dir(self) -> Path:
        """Objets moteur (scenes, actors, sprites, tilesets, backgrounds, scripts)."""
        return self.root / "project"

    @property
    def scenes_dir(self) -> Path:
        return self.project_dir / "scenes"

    @property
    def prefab_dir(self) -> Path:
        return self.project_dir / "prefab"

    @property
    def variables_file(self) -> Path:
        """Globals + constants du projet — project/variables.json (pas de dépendance externe)."""
        return self.project_dir / "variables.json"

    @property
    def texts_file(self) -> Path:
        """Table des textes du joueur — project/texts.json.

        Un seul fichier plutôt qu'un par entrée (contrairement aux palettes) :
        on parle de centaines d'entrées courtes, et un traducteur veut tout voir
        d'un coup. La v0.8 ajoutera `texts.<langue>.json` à côté."""
        return self.project_dir / "texts.json"

    @property
    def ui_layouts_dir(self) -> Path:
        """Mises en page d'UI — project/ui_layouts/*.json.

        Un fichier par mise en page (contrairement aux textes, monolithiques) :
        une mise en page est un objet qu'on renomme, duplique et partage entre
        scènes, donc qui mérite une identité de fichier — comme une palette."""
        return self.project_dir / "ui_layouts"

    @property
    def music_boxes_dir(self) -> Path:
        """MusicBox — project/music_boxes/*.json.

        Avec les données propres au projet, comme les caméras : une boîte
        sonore ne dérive d'aucun fichier importé (ROADMAP v0.8.7)."""
        return self.project_dir / "music_boxes"

    @property
    def jingle_boxes_dir(self) -> Path:
        """JingleBox — project/jingle_boxes/*.json."""
        return self.project_dir / "jingle_boxes"

    @property
    def sound_boxes_dir(self) -> Path:
        """SoundBox — project/sound_boxes/*.json."""
        return self.project_dir / "sound_boxes"

    @property
    def legacy_sound_states_dir(self) -> Path:
        """L'ancien dossier des boîtes à trois machines (avant 2026-08-18).

        Lu une seule fois, à l'ouverture, pour être découpé en trois — puis
        renommé afin que la migration ne se rejoue pas par-dessus le travail
        qui a suivi (cf. Project._migrate_sound_states)."""
        return self.project_dir / "sound_states"

    @property
    def data_tables_dir(self) -> Path:
        """Tables de données — project/data/*.json.

        Un fichier par table, avec les données propres au projet : une table ne
        dérive d'aucun fichier importé. Le dossier porte le mot que le script
        écrit (`data.Objets`) — une seule grammaire du disque au Lua."""
        return self.project_dir / "data"

    @property
    def palettes_dir(self) -> Path:
        """Catalogue de palettes unifié — sources ``.hex`` et sidecars JSON.

        Rangé dans ``assets/`` et non ``project/`` : une palette n'est plus un
        objet moteur mais une donnée d'éditeur que l'auteur importe et exporte,
        au même titre qu'un PNG ou un son."""
        return self.assets_dir / "palettes"

    @property
    def font_assets_dir(self) -> Path:
        """Polices logiques — ``project/fonts_assets/*.json``.

        Une FontAsset configure l'usage d'une ou plusieurs sources dans
        ``assets/fonts/`` ; elle vit donc avec les données du projet, jamais à
        côté d'un fichier importé.
        """
        return self.project_dir / "fonts_assets"

    @property
    def sprites_dir(self) -> Path:
        return self.assets_dir / "sprites"

    @property
    def backgrounds_dir(self) -> Path:
        """Dossier des sidecars BackgroundAsset (JSON) — co-localisé avec le PNG
        source dans assets/backgrounds/, même modèle que SpriteAsset
        (assets/sprites/)."""
        return self.assets_dir / "backgrounds"

    @property
    def background_images_dir(self) -> Path:
        """Dossier des images brutes PNG background."""
        return self.assets_dir / "backgrounds"

    @property
    def sfx_dir(self) -> Path:
        return self.assets_dir / "sfx"

    @property
    def music_dir(self) -> Path:
        return self.assets_dir / "music"

    @property
    def fonts_dir(self) -> Path:
        return self.assets_dir / "fonts"

    @property
    def scripts_dir(self) -> Path:
        return self.assets_dir / "scripts"

    @property
    def scripts_behaviors_dir(self) -> Path:
        """Le seul sous-dossier de scripts qui ait un sens : un behavior est un module
        importé par son chemin (`require("behaviors/nom")`). Tout autre script vit à plat
        dans `scripts_dir` — c'est son attache, pas son dossier, qui lui donne son contexte."""
        return self.scripts_dir / "behaviors"

    def script_files(self) -> list[Path]:
        """Les scripts qu'on peut ATTACHER à un acteur, une scène ou une caméra : tout .lua
        de `scripts_dir`, sauf les behaviors (des modules, attachés à rien)."""
        if not self.scripts_dir.is_dir():
            return []
        behaviors = self.scripts_behaviors_dir
        return sorted(f for f in self.scripts_dir.rglob("*.lua") if behaviors not in f.parents)

    @property
    def build_dir(self) -> Path:
        return self.root / "build"

    @property
    def grit_out_dir(self) -> Path:
        return self.build_dir / "grit_out"

    @property
    def src_dir(self) -> Path:
        return self.build_dir / "src"

    @property
    def obj_dir(self) -> Path:
        return self.build_dir / "obj"

    @property
    def makefile_path(self) -> Path:
        return self.build_dir / "Makefile"

    @property
    def rom_path(self) -> Path:
        return self.build_dir / "rom.gba"

    @property
    def project_file(self) -> Path:
        """Manifeste `<Nom>.project` — la cible d'ÉCRITURE, reconstruite à
        partir du nom. En lecture c'est `find_manifest()` qui le DÉCOUVRE, et le
        nom vient alors du fichier ; ici on fait le chemin inverse, le nom étant
        fixé à la création et jamais éditable ensuite."""
        return self.root / f"{self.settings.name}{PROJECT_EXT}"

    @property
    def legacy_project_file(self) -> Path:
        """Ancien manifeste `project.json`. Supprimé à la première sauvegarde
        d'un projet d'avant v0.10, une fois le `.project` écrit à sa place
        (cf. `Project.save_settings`)."""
        return self.root / LEGACY_MANIFEST_NAME
