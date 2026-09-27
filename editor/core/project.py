"""
GBA Editor — gestion de projet

Structure de projet :

  assets/              ← géré par l'utilisateur
    sprites/           ← PNG + JSON sidecar (auto-créé au dépôt)
    backgrounds/       ← PNG + JSON sidecar
    sounds/            ← WAV, MOD
    sfx/               ← effets sonores
    music/             ← musiques
    fonts/             ← polices
    scripts/           ← Lua (pas de sidecar)
      actors/
      scenes/
      cameras/
      behaviors/

  project/             ← géré exclusivement par l'éditeur
    scenes/            ← une scène par JSON (actors ET caméras inline)
    prefab/            ← templates d'actors (jamais compilés directement)

  <Nom>.gba-project    ← manifeste : settings globaux (scène de démarrage,
                         auteur…) ET point d'entrée double-clic. Le nom du
                         projet EST le nom du fichier. Remplace project.json,
                         encore relu une fois pour les projets d'avant v0.10.
  build/               ← 100 % jetable (regénéré à chaque build)

Ce module porte la classe `Project` : ses registres d'assets, la scène active,
les recherches, et l'orchestration save/load. Quatre responsabilités
volumineuses en sont des TRANCHES, chacune dans son fichier — `project_paths`,
`project_variables`, `project_texts`, `project_renames` (cf. la classe).

Autour : le modèle de domaine dans `core.models.*`, l'I/O générique de
collection dans `core.resources.resource_store`, l'orchestration d'encodage
d'assets dans `core.resources.asset_reconciliation`.

**Une seule forme ÉCRITE, deux formes LUES — et seulement pour la v0.24.**
La règle est longtemps restée « on ne lit qu'UNE forme de chaque fichier, celle
d'aujourd'hui » : sans version diffusée, un changement de format se propageait
en cassant, et un `core/project_migrations.py` a été retiré avec les anciennes
formes qu'il absorbait.

Ce qui a changé (ROADMAP v0.24) : à plusieurs, l'ancienne forme n'est pas dans
le passé, elle est **dans la branche d'à côté**. Un coéquipier qui rebase sur
un fichier écrit avant la bascule doit pouvoir l'ouvrir. Les trois formes
touchées par ce chantier se relisent donc dans les deux écritures, pour de
bon — les couleurs (`#RRGGBB` ou entier BGR555, cf. `core/gba_color.py`) et
les grilles (en rangées ou à plat, cf. `core/project_json.py`). L'écriture,
elle, n'a jamais qu'UNE forme : la nouvelle. Aucun convertisseur à lancer, le
premier enregistrement d'un fichier le réécrit.

Ce n'est pas une porte ouverte à un système de migration : c'est une paire de
lecteurs tolérants, à l'endroit précis où le travail à plusieurs l'exige.

**Ce module ne ré-exporte plus le modèle.** Chaque nom s'importe du fichier qui
le définit — `from core.models.scene import Scene`, jamais à travers ce
module-ci.
"""

import json
import shutil
import copy
from contextlib import nullcontext
from pathlib import Path
from typing import Optional

from core.events import EventEmitter
from core.models import project_json
from core.resources import asset_reconciliation
from core.reconcile_manifest import ReconcileManifest
from core.resources.resource_store import ResourceStore, atomic_write
from core.resources.palette_store import PaletteStore
from core.project_starters import copy_starter, get_starter
from core.project_paths import ProjectPathsMixin, PROJECT_EXT, find_manifest
from core.project_variables import ProjectVariablesMixin
from core.project_texts import ProjectTextsMixin
from core.project_langs import ProjectLangsMixin
from core.project_renames import ProjectRenameMixin

# ── Le modèle, importé pour l'usage de CE fichier ────────────────────────
# Rien de plus. Ce bloc a longtemps ré-exporté tout le domaine, si bien que
# trente fichiers écrivaient `from core.project import Scene` pour une classe
# définie dans `core/models/scene.py` : deux adresses valides pour un même nom,
# et un lecteur qui ouvrait ce fichier pour trouver `Scene` n'y voyait qu'une
# ligne d'import. **Chaque nom s'importe désormais du module où il est
# DÉFINI** — y compris quand un module voisin se trouve l'avoir sous la main
# (`core.models.scene` importe `OWN_PAL_BANK` pour son propre usage ; il ne
# faut pas le lui emprunter).
from core.models.settings import (ProjectSettings, GlobalVar, Constant,
                                  Language, InputBinding, InputSequence, InputAxis, InputMovement)
from core.models.text import Text
from core.models.palette import PaletteBank, OWN_PAL_BANK
from core.models.sprite import SpriteAsset
from core.models.components import sprite_components
from core.models.background import BackgroundAsset
from core.models.audio import Sfx, Music
from core.models.font import Font
from core.models.font_asset import FontAsset
from core.models.ui_region import UILayout
from core.models.camera import Camera
from core.models.sound_box import MusicBox, JingleBox, SoundBox
from core.models.data_table import DataTable
from core.models.scene import Prefab, Actor, Scene


# ── Ce qu'une colonne de RÉFÉRENCE peut citer ─────────────────────────────
# Une entrée par type de colonne de `core.models.data_table.COLUMN_REFERENCES`.
# Une table plutôt qu'une suite de `if` : le build compare les deux listes
# (`validator._check_data_column_types`), ce qu'une chaîne de conditions ne
# permet pas. Elle ne dit QUE les noms citables — l'index de chacun en ROM
# appartient à l'émetteur, qui seul connaît l'ordre de ses tables.
DATA_COLUMN_SOURCES = {
    "text":    lambda p: [t.key for t in p.texts],
    "sfx":     lambda p: [s.name for s in p.sfx],
    "music":   lambda p: [m.name for m in p.music],
    "scene":   lambda p: [s.name for s in p.scenes],
    "camera":  lambda p: sorted(p.camera_names()),
    "font":    lambda p: [a.name for a in p.font_assets],
    "palette": lambda p: [b.name for b in p.palettes],
    "region":  lambda p: p.region_names(),
    "image":   lambda p: p.image_names(),
}


# ──────────────────────────────────────────────────────────────────
#  Project — conteneur principal
# ──────────────────────────────────────────────────────────────────

class Project(ProjectPathsMixin, ProjectVariablesMixin, ProjectTextsMixin,
              ProjectLangsMixin, ProjectRenameMixin):
    """
    Représente un projet GBA ouvert.

    Reste ici ce qui fait de `Project` un tout : ses registres d'assets, la
    scène active, la résolution des chemins d'assets, les recherches, et
    l'orchestration `save`/`load`/`create`/`open`. Cinq responsabilités
    volumineuses vivent dans leur propre fichier, sous forme de TRANCHES de
    cette classe et non de collaborateurs :

      - `core.project_paths`     — où chaque chose vit sur le disque
      - `core.project_variables` — globals et constantes
      - `core.project_texts`     — la table de textes du joueur
      - `core.project_langs`     — ses traductions, un fichier par langue
      - `core.project_renames`   — renommer et réparer ce qui cite

    Des mixins plutôt que des objets délégués : `project.rename_scene(...)`
    s'écrit exactement comme avant chez ses vingt-deux appelants, et rien n'a
    gagné un saut d'appel — la résolution se fait une fois, à la construction de
    la classe. Le prix assumé : ces fichiers ne sont pas autonomes, ils
    supposent le reste de `Project`.
    """

    def __init__(self, root: Path | str):
        # Point d'entrée unique (construction directe ET `open`) : on coerce ici
        # une fois pour toutes, comme le fait `pathlib`. Un appelant qui passe une
        # chaîne obtient un projet valide, pas un `AttributeError` opaque.
        root = Path(root)
        self.root = root.resolve()
        self.settings = ProjectSettings(name=root.name)
        # {code de langue: {id du texte: contenu}} — cf. core/project_langs.
        # Vide tant qu'aucune traduction n'est déclarée.
        self.translations: dict = {}

        # Ce que le projet ANNONCE, et à quoi il se laisse ENTOURER.
        #
        # Un projet ne connaît pas l'application : il ne sait ni écrire dans une
        # barre de statut, ni suspendre un surveillant de fichiers. Il énonce
        # donc des faits — « ceci a été renommé, tant de références réécrites » —
        # et c'est l'application qui décide de la formulation et du
        # rafraîchissement. Sans abonné (build en ligne de commande, test), tout
        # est silencieux, sans qu'aucun repli n'ait à être écrit.
        #
        # `rename_scope` est l'exception qui ne peut pas être un événement : un
        # renommage doit se dérouler ENTOURÉ de quelque chose (la frappe en cours
        # persistée, le surveillant suspendu), pas suivi d'une notification. Un
        # appelable rendant un gestionnaire de contexte, que l'application
        # remplace ; par défaut il n'entoure rien.
        self.events = EventEmitter()
        self.rename_scope = nullcontext

        self.backgrounds: ResourceStore[BackgroundAsset] = ResourceStore(self.backgrounds_dir, BackgroundAsset)
        self.sprites:     ResourceStore[SpriteAsset]     = ResourceStore(self.sprites_dir, SpriteAsset)
        self.prefabs:     ResourceStore[Prefab]      = ResourceStore(self.prefab_dir, Prefab)
        # Avertissements du dernier load() — rempli par la réconciliation
        # des assets. Toujours présent : un projet fraîchement créé n'a pas
        # encore chargé, et l'appelant ne doit pas avoir à le vérifier.
        self.load_warnings: list[str] = []
        self.scenes:      ResourceStore[Scene]       = ResourceStore(self.scenes_dir, Scene)
        self.sfx:         ResourceStore[Sfx]         = ResourceStore(self.sfx_dir, Sfx)
        self.music:       ResourceStore[Music]       = ResourceStore(self.music_dir, Music)
        self.fonts:       ResourceStore[Font]        = ResourceStore(self.fonts_dir, Font)
        self.font_assets: ResourceStore[FontAsset]   = ResourceStore(self.font_assets_dir, FontAsset)
        self.palettes: PaletteStore = PaletteStore(self.palettes_dir)
        self.ui_layouts: ResourceStore[UILayout] = ResourceStore(self.ui_layouts_dir, UILayout)
        # Pas de ResourceStore pour Camera : une caméra appartient à sa scène
        # (Scene.cameras), elle se charge/sauve avec elle (cf. camera_names()
        # ci-dessous pour la vue à plat sur tout le projet).
        # Trois registres et non un : les trois couches du matériel ne se
        # coordonnent pas, et un appel Lua nomme la boîte à qui il parle.
        self.music_boxes: ResourceStore[MusicBox] = ResourceStore(
            self.music_boxes_dir, MusicBox)
        self.jingle_boxes: ResourceStore[JingleBox] = ResourceStore(
            self.jingle_boxes_dir, JingleBox)
        self.sound_boxes: ResourceStore[SoundBox] = ResourceStore(
            self.sound_boxes_dir, SoundBox)
        self.data_tables: ResourceStore[DataTable] = ResourceStore(self.data_tables_dir, DataTable)
        # Ces familles sont nombreuses et une scène ne cite qu'une petite
        # partie d'entre elles. ``load`` les indexe ; leur écran ou une
        # opération globale les matérialise explicitement (v0.24).
        self._deferred_resource_collections: set[str] = set()
        # La porte de la réconciliation incrémentale : l'empreinte des dossiers
        # source au dernier rattrapage. Sidecar d'éditeur, jamais livré en ROM
        # (cf. core/reconcile_manifest.py).
        self.reconcile_manifest = ReconcileManifest(self.root)

        # Variables globales déclarées explicitement dans le projet
        self.globals:     list[GlobalVar] = []

        # Constantes déclarées explicitement dans le projet (lecture seule)
        self.constants:   list[Constant] = []

        # Table des textes destinés au joueur (traduisibles, cf. models/text.py)
        self.texts:       list[Text] = []

        # Scène active (index dans self.scenes)
        self._active_scene_idx: int = 0


    # ── Scène active ──────────────────────────────────────────────

    @property
    def active_scene(self) -> Optional[Scene]:
        if not self.scenes:
            return None
        idx = max(0, min(self._active_scene_idx, len(self.scenes) - 1))
        return self.scenes[idx]

    def set_active_scene(self, index: int):
        self._active_scene_idx = max(0, min(index, len(self.scenes) - 1))
        if self.active_scene and self.settings.last_scene != self.active_scene.name:
            # Mémorise la scène ouverte pour la prochaine session — surtout PAS
            # start_scene, qui est le point de départ du jeu choisi par l'auteur
            # (cf. ProjectInspector).
            self.settings.last_scene = self.active_scene.name
            self.save_settings()

    # ── Résolution des assets ─────────────────────────────────────

    def asset_abs(self, rel: Optional[str]) -> Optional[Path]:
        if not rel:
            return None
        p = Path(rel)
        return (self.root / p).resolve() if not p.is_absolute() else p

    def asset_rel(self, abs_path: Path) -> str:
        try:
            return str(abs_path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return f"assets/{abs_path.name}"

    def import_asset(self, src: Path, subdir: str = "") -> Path:
        """
        Copie un fichier dans assets/{subdir}/.
        Retourne le chemin absolu dans le projet.
        """
        dst_dir = self.assets_dir / subdir if subdir else self.assets_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst

    # ── Encodage d'assets ───────────────────────────────────────────
    # L'orchestration vit dans `core/resources/asset_reconciliation.py`, et ses
    # appelants s'y adressent directement.
    # Treize méthodes qui ne faisaient que rappeler ce module vivaient ici, au
    # motif qu'elles servaient « depuis plusieurs écrans et le ProjectWatcher » :
    # dix n'avaient aucun appelant et le watcher n'en appelait aucune. Un
    # passe-plat ne rend pas un appel plus lisible, il ajoute un endroit où
    # chercher.

    def commit_all_removals(self):
        """Rend définitives les suppressions différées (appeler à la fermeture).

        Pour les familles adossées à un fichier source, on efface AUSSI ce
        fichier, pas seulement le sidecar JSON : sinon `reconcile_*` retrouverait
        le PNG / `.fnt` / module au prochain lancement et recréerait la ressource
        (cf. asset_reconciliation). C'est ce qui manquait pour qu'une suppression depuis
        le finder tienne au rechargement, et non un défaut du soft_delete lui-même.

        La source n'est touchée qu'ICI, à la fermeture — pendant la session elle
        reste en place, et le Ctrl+Z (restore) suffit à ramener la ressource."""
        for store, source_paths in (
            (self.sprites,     asset_reconciliation.sprite_source_paths),
            (self.backgrounds, asset_reconciliation.background_source_paths),
            (self.sfx,         asset_reconciliation.sound_source_paths),
            (self.music,       asset_reconciliation.sound_source_paths),
            (self.fonts,       asset_reconciliation.font_source_paths),
        ):
            for item in store.pending_deletes():
                for path in source_paths(self, item):
                    try:
                        Path(path).unlink(missing_ok=True)
                    except OSError:
                        pass   # fichier verrouillé (indexeur, AV) : le reste passe
        for mgr in (self.sprites, self.backgrounds, self.sfx, self.music,
                    self.fonts, self.font_assets, self.scenes, self.prefabs, self.ui_layouts,
                    self.palettes, self.music_boxes,
                    self.jingle_boxes, self.sound_boxes):
            mgr.commit_deletes()

    # ── Helpers de lookup ────────────────────────────────────────

    def get_background(self, name: str) -> Optional[BackgroundAsset]:
        return self.backgrounds.get(name)

    def get_sprite(self, name: str) -> Optional[SpriteAsset]:
        return self.sprites.get(name)

    # ── Ressources différées ─────────────────────────────────────

    def load_sprites(self) -> None:
        """Matérialise les sprites et rattrape les PNG ajoutés hors éditeur."""
        if "sprites" not in self._deferred_resource_collections:
            return
        self.sprites.load()
        asset_reconciliation.reconcile_sprites(self)
        self._deferred_resource_collections.discard("sprites")

    def load_backgrounds(self) -> None:
        """Matérialise les fonds et rattrape leurs sources PNG."""
        if "backgrounds" not in self._deferred_resource_collections:
            return
        self.backgrounds.load()
        asset_reconciliation.reconcile_backgrounds(self)
        self._deferred_resource_collections.discard("backgrounds")

    def load_audio(self) -> None:
        """Matérialise effets et musiques, avec le rattrapage des sources."""
        pending = {"sfx", "music"} & self._deferred_resource_collections
        if not pending:
            return
        self.sfx.load()
        self.music.load()
        asset_reconciliation.reconcile_sfx_and_music(self)
        self._deferred_resource_collections.difference_update(pending)

    def load_all_resources(self) -> None:
        """Matérialise les familles différées pour un geste global.

        Le build, la validation et les renommages transversaux doivent voir le
        projet entier. Les écrans, eux, appellent seulement leur méthode
        ``load_*`` dédiée.
        """
        self.load_sprites()
        self.load_backgrounds()
        self.load_audio()

    def load_active_scene_resources(self) -> None:
        """Précharge les assets cités par la scène active, et rien d'autre.

        Le Scene Editor est la première vue d'un projet : lui imposer une
        lecture disque au milieu de la construction du canvas rendait son
        ouverture perceptiblement moins fluide. On prépare donc ses références
        directes pendant l'ouverture du projet, sans matérialiser les catalogues
        complets ni lancer leur réconciliation globale.

        Ce que la scène RÉCLAME, c'est tout ce qu'elle rend : ses layers de
        fond, les sprites de ses acteurs, ET les images/fonds de ses nœuds
        Interface — oublier ces derniers laissait une zone d'UI blanche à
        l'ouverture tant que l'écran Interface n'avait pas tourné. Chaque asset
        chargé passe ensuite par la réparation par-asset (`reconcile_*`) : un
        catalogue différé ne repasse pas la passe globale, donc un encodage
        manquant ou une planche retouchée hors éditeur laisserait sinon l'asset
        vide jusqu'à l'ouverture de son écran (`load_sprites`/`load_backgrounds`).
        """
        scene = self.active_scene
        if scene is None:
            return

        bg_names = {
            layer.background_name
            for layer in scene.background_layers
            if layer.background_name
        }
        sprite_names: set[str] = set()
        for actor in scene.actors:
            # Toutes les apparences : tout résident, donc tout chargé (marche 3).
            for component in sprite_components(actor):
                if component.sprite_name:
                    sprite_names.add(component.sprite_name)
        # Nœuds Interface : sprites posés par leurs images, fonds de remplissage
        # (nine-slice / background). Les mises en page, elles, sont déjà chargées.
        from core.models.ui_region import FILL_BG, FILL_NINE
        for node in getattr(scene, "ui_layouts", []):
            layout = self.ui_layouts.get(node.layout_name)
            if layout is None:
                continue
            sprite_names |= layout.sprite_names()
            bg_names |= {
                el.fill_asset for el in layout.elements
                if getattr(el, "fill_asset", "")
                and getattr(el, "fill_kind", "") in (FILL_BG, FILL_NINE)
            }

        for name in bg_names:
            ba = self.backgrounds.ensure_loaded(name)
            if ba is not None:
                asset_reconciliation.reconcile_background(self, ba)
        for name in sprite_names:
            sp = self.sprites.ensure_loaded(name)
            if sp is not None:
                asset_reconciliation.reconcile_sprite(self, sp)

    def get_font_asset(self, name: str) -> Optional[FontAsset]:
        """La police logique nommée, distincte de sa source ``Font``."""
        return self.font_assets.get(name)

    def get_prefab(self, name: str) -> Optional[Prefab]:
        return self.prefabs.get(name)

    def get_palette(self, name: str) -> Optional[PaletteBank]:
        return self.palettes.get(name)

    def get_ui_layout(self, name: str) -> Optional[UILayout]:
        return self.ui_layouts.get(name)

    def get_data_table(self, name: str) -> Optional[DataTable]:
        return self.data_tables.get(name)

    def data_column_choices(self, column_type: str) -> list[str]:
        """Les noms qu'une colonne de RÉFÉRENCE peut citer, pour ce projet.

        Ce que cette méthode NE dit pas : à quel index chacun se résout en ROM.
        Ce sont deux questions distinctes — l'éditeur a besoin de la liste à
        proposer, le build de la position dans SA table — et les confondre
        ferait dépendre l'éditeur des ordres d'émission.

        `DATA_COLUMN_SOURCES` couvre exactement `COLUMN_REFERENCES` (vérifié au
        build par `validator._check_data_column_types`) : un type de colonne
        ajouté sans source n'offrirait aucun choix, en silence."""
        source = DATA_COLUMN_SOURCES.get(column_type)
        return list(source(self)) if source else []

    def camera_names(self) -> set[str]:
        """Noms de TOUTES les caméras du projet, toutes scènes confondues.

        Une caméra n'appartient qu'à une scène (`Scene.cameras`), mais son nom
        doit rester unique au projet : `camera:switch("Nom")` n'est pas
        qualifié par scène côté Lua, et chaque caméra reçoit une constante C
        globale `CAM_<NOM>` (cf. models/camera.py)."""
        return {c.name for s in self.scenes for c in s.cameras}

    def window_names(self) -> set[str]:
        """Noms de tous les `WindowSlot` rectangle (non-OBJ) du projet, toutes
        scènes confondues — même contrainte d'unicité que les caméras :
        `window.set_layer("Nom", …)` n'est pas qualifié par scène, chaque
        window reçoit une constante C globale `WIN_<NOM>` (cf.
        codegen/window_alloc.py)."""
        return {ws.name for s in self.scenes for ws in s.windows if not ws.is_obj}

    def scene_camera(self, scene) -> Optional[Camera]:
        """Caméra de démarrage d'une scène, ou None si elle emploie la caméra
        par défaut (nom vide) — ou si la référence est cassée, auquel cas le
        validateur le dit et la scène retombe sur le défaut."""
        name = getattr(scene, "camera", "")
        if not name:
            return None
        return next((c for c in scene.cameras if c.name == name), None)

    def ensure_scene_camera(self, scene) -> Camera:
        """La caméra de cette scène, MATÉRIALISÉE si elle emploie encore le
        défaut implicite.

        C'est le geste « je veux autre chose que l'origine » : personne ne crée
        de caméra d'avance, elle apparaît au premier réglage (cadrage déplacé
        dans le canvas, mode changé dans l'inspecteur). Sans ça, il faudrait
        soit créer une caméra par scène à la création — une liste remplie
        d'entrées jamais touchées — soit demander à l'auteur d'en créer une
        avant de pouvoir bouger le cadre."""
        cam = self.scene_camera(scene)
        if cam is not None:
            return cam
        taken = self.camera_names()
        base = (getattr(scene, "name", "") or "Camera").strip()
        name, n = base, 2
        while name in taken:
            name, n = f"{base} {n}", n + 1
        cam = Camera(name=name)
        scene.cameras.append(cam)
        scene.camera = name
        return cam

    def ui_backgrounds(self, role: str = "") -> list[BackgroundAsset]:
        """Fonds d'INTERFACE du projet, éventuellement filtrés sur leur rôle
        (`UI_ROLE_NINE` / `UI_ROLE_BG`). C'est ce que propose le menu de fond
        d'un `UIContainer` — d'où le filtre : un cadre étirable et une image posée
        ne s'étalent pas pareil, les mélanger dans une liste unique laisserait
        choisir un cadre sans marges."""
        from core.models.background import KIND_UI
        self.load_backgrounds()
        return [b for b in self.backgrounds
                if b.kind == KIND_UI and (not role or b.ui_role == role)]

    def animated_backgrounds(self) -> list[BackgroundAsset]:
        from core.models.background import KIND_ANIMATED
        self.load_backgrounds()
        return [b for b in self.backgrounds if b.kind == KIND_ANIMATED]

    def scene_ui_layouts(self, scene) -> list:
        """Les nœuds `Interface` d'une scène (v0.12), résolus en `BoundInterface`
        (nœud + asset composé), dans l'ordre où la scène les référence. Les refs
        cassées sont sautées — un nom qui ne résout plus ne doit pas faire tomber
        le chargement, le validateur le signalera.

        L'ancrage et la cible BG/OBJ restent portés par l'asset à ce stade
        (cf. `BoundInterface`) ; seul `bg_slot` est par nœud. Aucune migration de
        cible n'a donc lieu ici — les refs cassées sont sautées."""
        from core.models.ui_region import BoundInterface
        out = []
        for node in getattr(scene, "ui_layouts", []) or []:
            lay = self.ui_layouts.get(node.layout_name)
            if lay is not None:
                out.append(BoundInterface(node, lay))
        return out

    # Slot BG d'UI par DÉFAUT quand une scène n'a aucun nœud rendu en Background —
    # le comportement historique de `Scene.text_bg` (défaut 1). Sert au texte
    # scripté/libre (`text.draw` aux coordonnées) d'une scène sans Interface
    # authorée. Une couverture explicite (avertir si un script écrit du texte sans
    # nœud) reste à faire côté validateur.
    UI_BG_SLOT_DEFAULT = 1

    def scene_ui_bg_slot(self, scene) -> int:
        """Slot BG d'UI de la scène (v0.12), remplace l'ancien `Scene.text_bg`
        comme entrée UNIQUE de la réservation VRAM et de la config d'affichage :
        le slot du premier nœud `Interface` rendu en Background, sinon le défaut.

        Le ROUTAGE par zone (`scene_route_region`) utilise, lui, le `bg_slot` de
        CHAQUE nœud — c'est ce qui permet à un layout partagé d'être sur deux slots
        selon la scène. Ce helper ne rend qu'un slot (réservation mono-slot de la
        tranche 2 ; le multi-slot par scène est une étape distincte)."""
        from core.models.ui_region import TARGET_BG
        rm = int(getattr(scene, "render_mode", 0) or 0)
        for node in self.scene_ui_layouts(scene):
            if node.resolved_target(None, rm) == TARGET_BG:
                return int(node.bg_slot)
        return self.UI_BG_SLOT_DEFAULT

    def scene_ui_bg_slots(self, scene) -> list:
        """TOUS les slots BG distincts que les nœuds `Interface` de la scène
        occupent, triés. Un layout partagé posé sur BG0 et un HUD sur BG2 dans la
        MÊME scène en rendent deux : chacun réclame sa propre map (screenblock),
        les glyphes restant partagés dans un seul charblock. Vide → le défaut
        (`scene_ui_bg_slot`) est utilisé seul, comme avant."""
        from core.models.ui_region import TARGET_BG
        rm = int(getattr(scene, "render_mode", 0) or 0)
        slots = {int(node.bg_slot) for node in self.scene_ui_layouts(scene)
                 if node.resolved_target(None, rm) == TARGET_BG}
        return sorted(slots) if slots else [self.scene_ui_bg_slot(scene)]

    def scene_ui_layout(self, scene) -> Optional[UILayout]:
        """Le nœud `Interface` PRIMAIRE de la scène (le premier référencé), ou
        None. Réponse volontairement singulière pour le seul cas où « un défaut »
        suffit. L'outil widget du canvas, lui, préfère désormais le DERNIER nœud
        sélectionné et ne retombe sur le premier qu'à défaut (cf.
        `scene_canvas._ensure_layout`). Tout ce qui doit couvrir TOUS les nœuds
        passe par `scene_ui_layouts` (ou `scene_ui_slots`/`_images`/`_elements`)."""
        layouts = self.scene_ui_layouts(scene)
        return layouts[0] if layouts else None

    def scene_ui_slots(self, scene) -> list:
        """[(UILayout, slot de texte)] de TOUS les nœuds `Interface` d'une scène
        (v0.25), dans l'ordre des nœuds puis des slots. Le pendant par-scène de
        `all_regions`, pour les émetteurs qui réservent/initialisent PAR scène —
        et qui itéraient jusqu'ici l'unique `scene_ui_layout`."""
        return [(lay, r) for lay in self.scene_ui_layouts(scene) for r in lay.slots]

    def scene_ui_images(self, scene) -> list:
        """[(UILayout, UIImage)] de tous les nœuds `Interface` d'une scène."""
        return [(lay, im) for lay in self.scene_ui_layouts(scene) for im in lay.images]

    def scene_ui_elements(self, scene) -> list:
        """[(UILayout, élément)] de tous les nœuds `Interface` d'une scène, tous
        types confondus."""
        return [(lay, e) for lay in self.scene_ui_layouts(scene) for e in lay.elements]

    def all_regions(self) -> list:
        """[(UILayout, élément de texte)] de tout le projet, ordre STABLE.

        C'est cet ordre qui devient l'index dans la table C `g_ui_regions` —
        même convention que les textes et les polices. Ordre des mises en page,
        puis des slots dans chacune."""
        return [(lay, r) for lay in self.ui_layouts for r in lay.slots]

    def all_images(self) -> list:
        """[(UILayout, UIImage)] de tout le projet — l'index de `g_ui_images`.

        Table séparée de `all_regions`, exactement comme les deux propriétés du
        modèle : un script qui vise une image et un script qui vise un texte ne
        parlent pas de la même chose, et un index partagé obligerait le runtime
        à trier."""
        return [(lay, im) for lay in self.ui_layouts for im in lay.images]

    def all_elements(self) -> list:
        """[(UILayout, élément)] de tout le projet, TOUS types confondus, ordre
        STABLE — l'index de la table de visibilité plate (`UIELEM_*`), la seule
        à couvrir aussi les panels-groupes purs (ni `REGION_*` ni `IMAGE_*`).
        Même convention que `all_regions`/`all_images` : ordre des mises en
        page, puis des éléments dans chacune."""
        return [(lay, e) for lay in self.ui_layouts for e in lay.elements]

    def region_names(self) -> list[str]:
        """Noms de slot de texte du projet entier — l'espace de nommage des
        constantes `REGION_*`, donc ce contre quoi vérifier l'unicité."""
        return [r.name for _, r in self.all_regions()]

    def image_names(self) -> list[str]:
        """Noms d'image du projet entier — l'espace des constantes `IMAGE_*`."""
        return [im.name for _, im in self.all_images()]

    def ui_element_names(self) -> list[str]:
        """TOUS les noms d'élément d'UI du projet. L'unicité se cherche ici et
        pas par type : les deux espaces de constantes (`REGION_*`, `IMAGE_*`)
        sont distincts côté C, mais l'auteur, lui, ne devrait jamais avoir à
        savoir que deux éléments homonymes de types différents sont légaux —
        il les verrait côte à côte dans l'arbre sans pouvoir les distinguer."""
        return [e.name for _lay, e in self.all_elements()]

    def _action_boxes(self, kind: str):
        """Le registre d'actions d'une famille, trié par nom."""
        from core.models.sound_box import KIND_JINGLE
        store = self.jingle_boxes if kind == KIND_JINGLE else self.sound_boxes
        return sorted(store, key=lambda b: b.name)

    def sound_action_names(self, kind: str) -> list[str]:
        """Les actions d'une famille, dans un ordre stable.

        L'espace est COMMUN au projet et non propre à une boîte : une frame
        d'animation cite une action par son nom (« pas »), et elle ne sait pas
        quelle boîte sera active quand elle se jouera. Deux boîtes qui
        déclarent `pas` doivent donc viser la même action — sinon la même
        animation sonnerait ou non selon la boîte, sans que rien ne le dise.

        L'ordre — boîtes par nom, puis l'ordre d'écriture de l'auteur dans
        chacune — devient l'index émis en C. Il est recalculé à chaque build et
        n'est jamais sérialisé : un index rangé dans un fichier est un index à
        tenir d'accord avec sa source (même règle que l'arbre de `UILayout`).
        """
        names: list[str] = []
        for box in self._action_boxes(kind):
            for action in box.actions:
                if action and action not in names:
                    names.append(action)
        return names

    def sound_state_names(self, kind: str) -> list[str]:
        """Les états d'une famille, dans un ordre stable.

        UN espace par famille, et non un espace commun : depuis que les trois
        boîtes sont trois assets, `sound_box:set_state("sable")` dit à qui il
        parle. Deux familles peuvent donc porter le même nom d'état sans que
        rien ne devienne ambigu — ce que le fichier unique interdisait.
        """
        from core.models.sound_box import KIND_MUSIC
        boxes = (sorted(self.music_boxes, key=lambda b: b.name)
                 if kind == KIND_MUSIC else self._action_boxes(kind))
        names: list[str] = []
        for box in boxes:
            for st in box.states:
                if st.name and st.name not in names:
                    names.append(st.name)
        return names

    def sound_trigger_names(self) -> list[str]:
        """Les déclencheurs cités par les arêtes musicales, dans un ordre stable.

        L'ordre devient l'entier que `music_box:trigger(...)` passe au runtime,
        et il est recalculé à chaque build : jamais sérialisé, donc jamais à
        tenir d'accord avec autre chose.
        """
        names: list[str] = []
        for box in sorted(self.music_boxes, key=lambda b: b.name):
            for tr in box.transitions:
                if tr.trigger and tr.trigger not in names:
                    names.append(tr.trigger)
        return names

    def _migrate_box_dirs(self):
        """Renomme les trois dossiers de boîtes vers leur nom au SINGULIER.

        Le pluriel (`musics_boxes`) est tombé avec la v0.8.6, qui aligne le nom
        de la boîte sur celui de l'appel Lua (`music_box.trigger`). Le CONTENU
        des fichiers ne change pas : seul le dossier est renommé, donc rien à
        relire ni à réécrire.

        Le dossier neuf ne l'est jamais avant ce passage — `load()` crée les
        sous-dossiers manquants juste après. S'il existe déjà avec du contenu,
        on ne touche à rien : deux dossiers pleins veulent dire que quelqu'un a
        déjà migré, et écraser serait choisir à sa place.
        """
        for old, new_dir in (("musics_boxes", self.music_boxes_dir),
                             ("jingles_boxes", self.jingle_boxes_dir),
                             ("sounds_boxes", self.sound_boxes_dir)):
            old_dir = self.project_dir / old
            if not old_dir.is_dir():
                continue
            if new_dir.exists() and any(new_dir.iterdir()):
                continue
            try:
                if new_dir.exists():
                    new_dir.rmdir()
                old_dir.rename(new_dir)
            except OSError:
                continue

    def _migrate_sound_states(self):
        """Découpe les anciennes boîtes à trois machines en trois assets.

        Un fichier `project/sound_states/X.json` d'avant le 2026-08-18 portait
        musique, effets et jingles ensemble. Il devient jusqu'à trois fichiers
        du même nom, un par famille — et seulement pour les familles qui
        avaient du contenu : une boîte vide créée par la migration serait un
        asset que personne n'a voulu.

        Le dossier d'origine est ensuite RENOMMÉ, pas effacé : la donnée de
        l'auteur reste sur le disque, et la migration ne se rejoue pas
        par-dessus le travail qui a suivi.
        """
        import json
        import time
        from core.models.sound_box import (
            MusicBox, JingleBox, SoundBox, MusicState, MusicTransition,
            ActionState,
        )
        old_dir = self.legacy_sound_states_dir
        if not old_dir.is_dir():
            return
        files = sorted(old_dir.glob("*.json"))
        for path in files:
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            name = d.get("name", path.stem)
            made = False
            if d.get("music_states"):
                box = MusicBox(
                    name=name, start=d.get("music_start", ""),
                    states=[MusicState(
                        name=s.get("name", "state"), music=s.get("music", ""),
                        loop=s.get("loop", True), level=int(s.get("level", 100)),
                        intensity_target=s.get("intensity_target", "volume"),
                        intensity=int(s.get("intensity", 100)),
                        x=int(s.get("x", 0)), y=int(s.get("y", 0)))
                        for s in d["music_states"]],
                    transitions=[MusicTransition(
                        src=t.get("src", ""), dst=t.get("dst", ""),
                        trigger=t.get("trigger", ""), kind=t.get("kind", "fade"),
                        frames=int(t.get("frames", 30)))
                        for t in d.get("music_transitions", [])])
                self.music_boxes.save(box)
                made = True
            for key, cls, store in (("sfx", SoundBox, self.sound_boxes),
                                    ("jingle", JingleBox, self.jingle_boxes)):
                m = d.get(key) or {}
                if not (m.get("slots") or m.get("states")):
                    continue
                made = True
                store.save(cls(
                    name=name, actions=list(m.get("slots", [])),
                    start=m.get("start", ""),
                    states=[ActionState(name=s.get("name", "state"),
                                        mapping=dict(s.get("mapping", {})))
                            for s in m.get("states", [])]))
            if not made:
                # Une boîte encore vide reste une boîte que l'auteur a créée et
                # NOMMÉE. La perdre en silence serait perdre une intention.
                self.music_boxes.save(MusicBox(name=name))
        if files:
            # Le projet énonce le fait ; c'est l'application qui décide de la
            # formulation et de l'endroit où elle s'affiche.
            self.events._emit(
                "status",
                f"{len(files)} boîte(s) à état découpée(s) en MusicBox / "
                f"JingleBox / SoundBox — ancien dossier conservé sous "
                f"« sound_states.migre »")
        target = old_dir.with_name("sound_states.migre")
        if target.exists():
            target = old_dir.with_name(f"sound_states.migre.{int(time.time())}")
        try:
            old_dir.rename(target)
        except OSError:
            pass

    def ui_layout_users(self, name: str) -> list:
        """Scènes qui référencent ce nœud `Interface`. Alimente le badge
        « partagée — N scènes » : éditer un élément depuis le canvas modifie un
        objet commun, et le taire casserait N scènes en un geste."""
        return [s for s in self.scenes
                if any(n.layout_name == name
                       for n in (getattr(s, "ui_layouts", []) or []))]

    def instantiate_actor_from_prefab(self, prefab: Prefab, name: str,
                                       x: int = 112, y: int = 72) -> Actor:
        """Crée un Actor inline depuis un Prefab — copie complète de son actor
        racine (composants, palette, réservation affine, notes ; aucun lien
        vivant après la création), reposé aux coordonnées données.

        Un prefab EST son actor racine (cf. core/models/scene.Prefab) :
        copier CET objet plutôt que de relister champ par champ, c'est ce qui
        évite l'ancien bug — `pal_bank`/`notes` du prefab n'étaient pas reportés
        sur l'instance, faute d'avoir pensé à les ajouter à cette liste."""
        actor = copy.deepcopy(prefab.actor)
        actor.name = name
        actor.prefab_name = prefab.name
        actor.active = True
        actor.x, actor.y = x, y
        return actor

    # ── Build ─────────────────────────────────────────────────────

    def prepare_build(self):
        # Les deux répertoires générés ne sont PLUS effacés ici (ROADMAP
        # v0.24). Le rmtree répondait au bon risque — le Makefile ramasse
        # `src/*.c` au glob, donc un asset retiré du projet laissait un `.c`
        # qui continuait d'être compilé — mais il datait à neuf 32 fichiers
        # identiques d'un build à l'autre, et `make` recompilait tout à chaque
        # itération. Le même risque est couvert en fin de génération par
        # `codegen.build_output.sweep`, qui retire ce que ce build-ci n'a pas
        # produit.
        for d in (self.grit_out_dir, self.src_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.obj_dir.mkdir(parents=True, exist_ok=True)
        self._anon_texts = self.collect_literal_texts()


    def scene_scripts(self, scene) -> tuple[list, bool]:
        """(scripts Lua qu'une scène peut exécuter, en reste-t-il d'opaques ?).

        Le script de la scène, celui de chacun de ses actors, et ceux de TOUS
        les prefabs : un prefab est poolé au niveau projet et `actor:spawn()`
        s'appelle de n'importe où, donc rien ne dit qu'il ne tournera pas ici.

        Le second booléen dit qu'un script échappe à l'analyse : introuvable sur
        disque, ou écrit en C natif (lequel peut appeler n'importe quelle
        fonction du moteur hors catalogue Lua). L'appelant doit en tirer « je ne
        sais pas », jamais « il n'y a rien »."""
        out, opaque = [], False

        def add(rel):
            nonlocal opaque
            if not rel:
                return
            ap = self.asset_abs(rel)
            if ap is None:
                return
            if ap.suffix.lower() == ".lua":
                if ap.exists():
                    out.append(ap)
                else:
                    opaque = True
            else:
                opaque = True      # .c natif : hors de portée de l'analyse

        add(getattr(scene, "script", ""))
        owners = list(getattr(scene, "actors", [])) + list(getattr(self, "prefabs", []))
        for owner in owners:
            comp = owner.get_component("script") if hasattr(owner, "get_component") else None
            if comp and getattr(comp, "active", True):
                add(getattr(comp, "script", ""))
        return out, opaque


    # ── I/O settings globaux ──────────────────────────────────────

    def save_settings(self):
        # Pas de clé `name` : le nom du projet EST le nom du fichier
        # (<Nom>.gba-project). L'écrire aussi dans le JSON en ferait un second
        # porteur, à re-synchroniser — exactement ce que « source de vérité
        # unique » interdit (cf. ROADMAP v0.10).
        data = {
            "start_scene": self.settings.start_scene,
            "last_scene":  self.settings.last_scene,
            "author":      self.settings.author,
            "version":     self.settings.version,
            "backdrop_color": self.settings.backdrop_color,
            "save_slots":  self.settings.save_slots,
            "transition_kind":   self.settings.transition_kind,
            "transition_frames": self.settings.transition_frames,
            "cartridge_mib":     self.settings.cartridge_mib,
            "sfx_sample_rate":   self.settings.sfx_sample_rate,
            "sound_channels":    self.settings.sound_channels,
            "debug_build":       self.settings.debug_build,
            "list_repeat_delay": self.settings.list_repeat_delay,
            "list_repeat_rate":  self.settings.list_repeat_rate,
            # Écrite seulement s'il y a des exceptions : un projet où tout se
            # heurte — le cas de tous ceux d'avant la v0.23 — ne gagne pas une clé.
            **({"collision_disabled_pairs": sorted(self.settings.collision_disabled_pairs)}
               if self.settings.collision_disabled_pairs else {}),
            **({"collision_tags": sorted(self.settings.collision_tags)}
               if self.settings.collision_tags else {}),
            # Mêmes égards qu'au-dessus : un projet monolingue — tous ceux
            # d'avant la v0.9 — ne gagne pas deux clés vides.
            **({"source_lang": self.settings.source_lang.to_dict()}
               if self.settings.source_lang.code else {}),
            **({"languages": [l.to_dict() for l in self.settings.languages]}
               if self.settings.languages else {}),
            **({"default_font": self.settings.default_font}
               if self.settings.default_font else {}),
            # Placeholder (cf. InputBinding) : un projet sans input déclaré ne
            # gagne pas de clé, même politique que languages/collisions.
            **({"inputs": [i.to_dict() for i in self.settings.inputs]}
               if self.settings.inputs else {}),
            **({"input_sequences": [s.to_dict() for s in self.settings.sequences]}
               if self.settings.sequences else {}),
            **({"input_axes": [a.to_dict() for a in self.settings.axes]}
               if self.settings.axes else {}),
            **({"input_movements": [m.to_dict() for m in self.settings.movements]}
               if self.settings.movements else {}),
        }
        atomic_write(self.project_file, project_json.dumps(data))
        # Projet d'avant v0.10 : le .gba-project vient d'être écrit, l'ancien
        # project.json n'a plus de raison d'être. Sa suppression ici est la
        # deuxième moitié du pont de find_manifest — sans elle, le dossier
        # porterait deux manifestes et l'ouverture suivante serait refusée.
        if self.legacy_project_file.exists():
            self.legacy_project_file.unlink()

    def load_settings(self):
        manifest = find_manifest(self.root)
        if manifest is None:
            return
        d = json.loads(manifest.read_text(encoding="utf-8"))
        # Le nom vient du FICHIER : <Nom>.gba-project → le stem. Un manifeste
        # legacy (project.json) ne le porte pas dans son intitulé — on retombe
        # alors sur sa clé `name`, puis sur le dossier.
        if manifest.suffix == PROJECT_EXT:
            self.settings.name = manifest.stem
        else:
            self.settings.name = d.get("name", self.root.name)
        self.settings.start_scene = d.get("start_scene", "")
        # Projets antérieurs à la séparation start_scene/last_scene : start_scene
        # y servait aussi de « dernière scène ouverte ».
        self.settings.last_scene  = d.get("last_scene", self.settings.start_scene)
        self.settings.author      = d.get("author", "")
        self.settings.version     = d.get("version", "0.1")
        # `palette_auto_import_enabled` des anciens project.json est ignoré :
        # le réservoir auto-import est abandonné (cf. ROADMAP.md v0.2), la clé
        # disparaît du fichier à la prochaine sauvegarde.
        self.settings.backdrop_color = d.get("backdrop_color", 0)
        # Un projet antérieur à la v0.5 n'a pas d'emplacement déclaré : il en
        # reçoit un, comme un projet neuf. Sans variable persistante, aucun ne
        # sera émis de toute façon.
        self.settings.save_slots = max(1, int(d.get("save_slots", 1)))
        # Un projet antérieur à la v0.6.2 n'a pas de transition : coupure franche,
        # exactement ce qu'il avait avant. Le fondu se demande, il ne s'impose pas.
        self.settings.transition_kind   = d.get("transition_kind", "none") or "none"
        self.settings.transition_frames = max(1, int(d.get("transition_frames", 16)))
        # Un projet antérieur à la v0.8.4 vise la plus petite cartouche et ne
        # ré-échantillonne rien : les deux défauts ne changent RIEN à ce qui
        # était construit avant.
        from codegen.rom_report import CARTRIDGE_SIZES_MIB, DEFAULT_CARTRIDGE_MIB
        cart = int(d.get("cartridge_mib", DEFAULT_CARTRIDGE_MIB))
        self.settings.cartridge_mib = cart if cart in CARTRIDGE_SIZES_MIB else DEFAULT_CARTRIDGE_MIB
        self.settings.sfx_sample_rate = max(0, int(d.get("sfx_sample_rate", 0)))
        # Antérieur à la v0.8.8 : les 8 canaux qui étaient en dur dans le
        # codegen. Borné par le matériel — le masque de canaux de maxmod est un
        # mot de 32 bits, et sous 4 canaux un module ordinaire ne tient pas.
        from core.models.audio import SOUND_CHANNELS_MIN, SOUND_CHANNELS_MAX
        self.settings.sound_channels = max(
            SOUND_CHANNELS_MIN,
            min(SOUND_CHANNELS_MAX, int(d.get("sound_channels", 8))))
        # Antérieur à la v0.14 : `debug.*` n'existait pas encore, donc rien ne
        # change de comportement pour un projet ancien — défaut à True.
        self.settings.debug_build = bool(d.get("debug_build", True))
        # `show_tips` des project.json écrits pendant la première passe de la
        # v0.11 est ignoré : l'affichage des astuces est un réglage
        # d'APPLICATION (core/interface_preferences.py). Même traitement que
        # `palette_auto_import_enabled` plus haut — la clé disparaît du fichier
        # à la prochaine sauvegarde, sans migration.
        # Antérieur à la v0.22 : les valeurs qui étaient en dur dans
        # l'émetteur, donc aucun changement de comportement.
        self.settings.list_repeat_delay = max(0, int(d.get("list_repeat_delay", 10)))
        self.settings.list_repeat_rate  = max(0, int(d.get("list_repeat_rate", 4)))
        # Absente = aucune exception, donc tout se heurte : le comportement
        # d'avant la v0.23, à l'identique.
        self.settings.collision_disabled_pairs = list(
            d.get("collision_disabled_pairs") or [])
        # Absents = aucun tag réservé, le cas de tout projet avant que la
        # déclaration explicite n'existe — la matrice continue de tout
        # découvrir depuis les composants, comme avant.
        self.settings.collision_tags = list(d.get("collision_tags") or [])
        # Absentes = projet monolingue, le cas de tous ceux d'avant la v0.9 :
        # le maître EST la seule langue et rien ne change.
        self.settings.source_lang = Language.from_dict(d.get("source_lang") or {})
        self.settings.languages = [Language.from_dict(x)
                                   for x in (d.get("languages") or [])
                                   if (x or {}).get("code")]
        # `fallback_font` était le nom historique, alors ambigu : il désignait
        # à la fois le défaut et un repli de couverture global. Il devient le
        # défaut du projet lors de la première relecture ; la prochaine
        # sauvegarde écrit uniquement `default_font`.
        self.settings.default_font = d.get("default_font", d.get("fallback_font", ""))
        # Les anciens remaps généraux deviennent le remplacement de la police
        # par défaut seulement. Les remaps d'autres polices disparaissent : leur
        # couverture appartient désormais à leurs FontAsset.
        for raw, language in zip(d.get("languages") or [], self.settings.languages):
            legacy = (raw or {}).get("fonts") or {}
            if not language.default_font and self.settings.default_font:
                language.default_font = str(legacy.get(self.settings.default_font, "") or "")
        # Absents = aucun input déclaré, le cas de tout projet avant que ce
        # placeholder n'existe.
        self.settings.inputs = [InputBinding.from_dict(x)
                                for x in (d.get("inputs") or [])
                                if (x or {}).get("name")]
        self.settings.sequences = [InputSequence.from_dict(x)
                                   for x in (d.get("input_sequences") or [])
                                   if (x or {}).get("name")]
        self.settings.axes = [InputAxis.from_dict(x)
                              for x in (d.get("input_axes") or [])
                              if (x or {}).get("name")]
        self.settings.movements = [InputMovement.from_dict(x)
                                   for x in (d.get("input_movements") or [])
                                   if (x or {}).get("name")]

    def collision_tags(self) -> list:
        """Tags de collision du projet, DÉCLARÉS d'abord (dans leur ordre —
        celui que Project Settings > Collisions laisse glisser-déposer),
        puis ceux seulement TROUVÉS sur un CollisionBoxComponent (actif ou non : un script peut l'allumer)
        (scènes, prefabs, ET parties de prefabs), triés, à la suite.

        Source unique pour ses TROIS lecteurs : le sélecteur de tag du
        CollisionEditor (ui/.../component_editors/collision.py), la matrice de
        Project Settings, et les `#define BOXTAG_*` de `actor_types.h`
        (codegen/runtime_codegen/headers.py). Le codegen refaisait sa propre
        collecte, limitée aux acteurs de SCÈNE : un tag porté seulement par un
        prefab poolé n'avait pas de constante, et `spawn_<Prefab>()` — qui
        l'écrit dans `boxes[].tag` — ne compilait pas."""
        from core.models.components import CollisionBoxComponent
        owners = [a for sc in self.scenes for a in sc.actors] + list(self.prefabs)
        owners += [ch for pf in self.prefabs for ch in (getattr(pf, "children", []) or [])]
        discovered = {c.tag or "body" for o in owners for c in getattr(o, "components", [])
                     if isinstance(c, CollisionBoxComponent)}
        declared = list(self.settings.collision_tags)
        seen = set(declared)
        extra = sorted(t for t in discovered if t not in seen)
        return declared + extra




    # ── Raccourcis de sauvegarde par objet (delegue au ResourceStore) ──

    def save_scene(self, scene: Scene):                    self.scenes.save(scene)
    def save_prefab(self, prefab: Prefab):                 self.prefabs.save(prefab)
    def save_sprite(self, sprite: SpriteAsset):           self.sprites.save(sprite)
    def save_background(self, bg: BackgroundAsset):       self.backgrounds.save(bg)
    def save_sfx(self, sfx: Sfx):                         self.sfx.save(sfx)
    def save_music(self, music: Music):                   self.music.save(music)
    def save_font_asset(self, font_asset: FontAsset):     self.font_assets.save(font_asset)

    # ── Sauvegarde / chargement global ────────────────────────────

    def save(self):
        self.save_settings()
        self.save_variables()
        self.save_texts()
        self.sprites.save_all()
        self.sfx.save_all()
        self.music.save_all()
        self.fonts.save_all()
        self.font_assets.save_all()
        self.ui_layouts.save_all()
        self.music_boxes.save_all()
        self.jingle_boxes.save_all()
        self.sound_boxes.save_all()
        self.data_tables.save_all()
        # `palettes` manquait ici — seule des quatorze collections. Sans
        # conséquence au quotidien (l'éditeur de palettes écrit chaque banque
        # dès l'édition, cf. palette_grid_panel), mais un « enregistrer le
        # projet » qui saute une collection est un piège à l'échelle d'une
        # équipe, et c'est ce qui a laissé les fichiers de palettes dans
        # l'ancienne forme écrite quand tout le reste avait basculé (v0.24).
        self.palettes.save_all()
        self.backgrounds.save_all()
        self.prefabs.save_all()
        self.scenes.save_all()

    def load_scenes(self):
        """Charge les scènes, puis rouvre sur la dernière éditée.

        Repli : la scène de démarrage du jeu, qui tenait ce rôle avant la
        séparation des deux champs."""
        self.scenes.load()
        restore = self.settings.last_scene or self.settings.start_scene
        if restore:
            for i, s in enumerate(self.scenes):
                if s.name == restore:
                    self._active_scene_idx = i
                    break

    def load(self):
        # S'assurer que tous les sous-dossiers existent
        for sub in ("project/scenes", "project/prefab",
                    "project/fonts_assets", "project/ui_layouts",
                    "project/music_boxes",
                    "project/jingle_boxes",
                    "project/sound_boxes",
                    "assets/palettes",
                    "assets/sprites", "assets/backgrounds",
                    "assets/scripts", "assets/scripts/behaviors",
                    "assets/sfx", "assets/music", "assets/fonts"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        # Chaque registre est suivi de son rattrapage (cf. asset_reconciliation,
        # section « Rattrapage à l'ouverture ») : un fichier déposé éditeur
        # fermé n'a été vu par aucun watcher, on repasse une fois ici.
        self.load_settings()
        self.load_variables()
        # Une variable ajoutée à la main dans variables.json n'a pas d'id, et
        # tout ce qui référence une variable en a besoin : attribution AVANT
        # que quoi que ce soit ne tente de résoudre.
        if self.assign_variable_ids():
            self.save_variables()
        self.load_texts()
        # Après les textes : un side se joint aux entrées du maître.
        self.load_translations()
        self.palettes.load()
        # Les trois catalogues lourds ne lisent ici que leurs noms et chemins.
        # Leur contenu et le rattrapage des sources sont demandés par l'écran
        # concerné, ou par ``load_all_resources`` avant une opération globale.
        self._deferred_resource_collections = {"sprites", "backgrounds", "sfx", "music"}
        self.sprites.scan_index()
        self.backgrounds.scan_index()
        self.sfx.scan_index()
        self.music.scan_index()
        self.fonts.load()
        self.font_assets.load()
        # Ce que la réconciliation n'a PAS pu importer. Gardé sur le projet
        # plutôt que jeté : sans ça, une police refusée à l'import laisse un
        # panneau vide et aucune explication (cf. reconcile_fonts).
        self.load_warnings = list(asset_reconciliation.reconcile_fonts(self) or [])
        asset_reconciliation.reconcile_font_assets(self)
        # Avant les scènes : une scène référence sa mise en page et ses prefabs
        # par nom, et doit les trouver déjà chargés.
        self.ui_layouts.load()
        self._migrate_box_dirs()
        self._migrate_sound_states()
        self.music_boxes.load()
        self.jingle_boxes.load()
        self.sound_boxes.load()
        self.data_tables.load()
        self.prefabs.load()
        self.load_scenes()
        self.load_active_scene_resources()

    # ── Création / ouverture ──────────────────────────────────────

    @classmethod
    def create(cls, root: Path, name: str, starter_id: str = "Basic") -> "Project":
        """Crée un projet depuis le starter ``Basic`` intégré à l'éditeur."""
        root.mkdir(parents=True, exist_ok=True)
        for sub in (
            "assets/sprites",
            "assets/backgrounds",
            "assets/sounds",
            "assets/sfx",
            "assets/music",
            "assets/fonts",
            "project/fonts_assets",
            "assets/scripts",
            "assets/scripts/behaviors",
            "project/scenes",
            "project/prefab",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)

        copy_starter(get_starter(starter_id), root)

        proj = cls(root)
        proj.settings.name = name

        # Les assets initiaux (dont les palettes .hex et les polices de base)
        # viennent du starter. Un projet neuf reste en mémoire juste après sa
        # création : charger les fonts ici les rend donc visibles tout de suite,
        # et non seulement après sa première réouverture.
        proj.palettes.load()
        proj.fonts.load()
        proj.font_assets.load()
        proj.load_warnings = list(asset_reconciliation.reconcile_fonts(proj) or [])
        asset_reconciliation.reconcile_font_assets(proj)

        # Créer une scène de démarrage par défaut
        # Budget AUTO comme toute scène créée ensuite (v0.17, révision
        # 2026-09-19) : dérivé, rien à réserver — la première scène d'un projet
        # n'est pas un cas particulier.
        default_scene = Scene(name="Scene_01")
        proj.scenes.append(default_scene)
        proj.settings.start_scene = "Scene_01"
        proj.settings.last_scene  = "Scene_01"

        # save() écrit le manifeste <Nom>.gba-project : c'est LUI qu'on
        # double-clique, associé à l'éditeur sur les deux OS (packaging/). Il a
        # remplacé le launcher .bat, qui ne valait que sous Windows.
        proj.save()

        return proj

    @classmethod
    def open(cls, root: Path) -> "Project":
        """Ouvre un projet existant."""
        proj = cls(root)
        proj.load()
        return proj
