"""
CommandDispatcher — point unique pour toutes les mutations du projet.

Règle absolue :
  - TOUT appel à save_scene/save/save_prefab passe par ici.
  - Le watcher est toujours suspendu pendant une mutation.
  - Les panels appellent get_dispatcher().xxx() pour muter.
  - window.py s'abonne via .on() aux événements du dispatcher.

Usage :
    from core.command_dispatcher import get_dispatcher
    get_dispatcher().delete_actor(actor)
    get_dispatcher().on("actors_list_changed", panel.refresh)

Événements émis :
    "scene_sprites_changed"        — recréer les sprites canvas
    "actors_list_changed"          — rafraîchir la liste actors
    "bg_slot_changed"  (int slot)  — rafraîchir un BG slot précis
    "inpaint_layer_changed" (int slot)      — layer BG peint actif
    "bg_layer_visibility"    (int, bool)     — visibilité viewport d'un layer BG
    "status_message"   (str msg)   — afficher dans la barre de statut
    "scripts_changed"              — rafraîchir la liste des scripts
    "ui_text_links_changed"        — un élément de mise en page a changé de
                                     `text_key` (créé ou rebranché) : l'écran
                                     Texte doit relire qui cite quoi
    "flush_script_edits"           — le Script Editor doit persister sa frappe
                                     en cours (avant réécriture de scripts)
    "palettes_changed"             — rafraîchir le catalogue de palettes
    "project_tree_changed"         — un élément a été renommé/créé, ou le lien
                                     prefab d'un actor a changé (Relink/Expose/
                                     Unlink) : repeupler les arbres du panneau
                                     projet (cf. Project._notify_renamed)
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from contextlib import contextmanager

import copy

from core.resources import asset_reconciliation
from core.events import EventEmitter
from core.models.scene import Actor, Prefab, Scene
from core.history import get_history, AddActorCmd
from core.selection_bus import get_bus

if TYPE_CHECKING:
    from core.project import Project
    from core.project_watcher import ProjectWatcher


def unique_name(base: str, existing) -> str:
    """Nom unique dérivé de `base` : `base`, puis `base_2`, `base_3`… en évitant
    les noms déjà présents dans `existing`. Sert au nommage automatique lors de
    la création d'assets (pas de pop-up — cf. feedback inline over dialogs)."""
    existing = set(existing)
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


def _copy_name(base: str, taken) -> str:
    """`base_copy`, puis `base_copy2`, `base_copy3`… — nommage des duplicatas
    d'actor. Distinct de `unique_name` (suffixe `_2`), qui sert à la CRÉATION :
    le suffixe dit lequel des deux gestes a produit l'objet."""
    name = f"{base}_copy"
    i = 1
    while name in taken:
        i += 1
        name = f"{base}_copy{i}"
    return name


class CommandDispatcher(EventEmitter):
    """
    Dispatcher centralisé — singleton, initialiser via setup() après chaque chargement projet.
    """

    def __init__(self):
        super().__init__()
        self._project: Optional["Project"] = None
        self._watcher: Optional["ProjectWatcher"] = None

    @property
    def project(self) -> Optional["Project"]:
        return self._project

    def setup(self, project, watcher):
        """Appelé par MainWindow à chaque chargement/création de projet."""
        self._project = project
        self._watcher = watcher
        # Le projet énonce des faits, l'application les met en mots et
        # rafraîchit les vues. C'est ce branchement-ci qui remplace l'import du
        # dispatcher que `Project` faisait autrefois : la dépendance ne va plus
        # que dans un sens, et un projet ouvert sans interface reste muet de
        # lui-même. `off` d'abord : rebrancher deux fois le même projet
        # doublerait chaque message.
        project.events.off("renamed", self._on_project_renamed)
        project.events.off("status", self._on_project_status)
        project.events.on("renamed", self._on_project_renamed)
        project.events.on("status", self._on_project_status)
        project.rename_scope = self._rename_scope

    # ── Ce que le projet annonce ──────────────────────────────────

    @contextmanager
    def _rename_scope(self):
        """La portée dans laquelle `Project` déroule un renommage : frappe en
        cours persistée avant de lire les scripts sur disque, surveillant
        suspendu pendant nos propres écritures."""
        self.flush_script_edits()
        with self.suspended():
            yield

    def _on_project_status(self, msg: str):
        self._emit("status_message", msg)

    def _on_project_renamed(self, label: str, old: str, new: str,
                            refs: dict, n_texts: int, n_regions: int = 0):
        """Met en mots un renommage et rafraîchit ce qui affiche le nom."""
        msg = f"{label} renamed: “{old}” → “{new}”"
        if refs:
            n_refs = sum(refs.values())
            files  = ", ".join(sorted(p.name for p in refs))
            msg += (f" — {n_refs} reference(s) updated in "
                    f"{len(refs)} script(s): {files}")
        if n_texts:
            msg += f" — {n_texts} text(s) updated"
        if n_regions:
            msg += f" — {n_regions} UI zone(s) relinked"
        self._emit("project_tree_changed")
        if refs:
            self.notify_scripts_changed()
        # En dernier : les rafraîchissements ci-dessus peuvent poster leur
        # propre message de statut, celui du renommage doit rester visible.
        self._emit("status_message", msg)

    @contextmanager
    def suspended(self):
        """Suspend le watcher de fichiers pendant une écriture directe sur disque
        (ex. réécriture d'un PNG indexé par le Sprite Editor) — évite que le
        watcher recharge tout l'écran et réinitialise l'UI (palette de preview…).
        No-op si aucun watcher n'est branché (ex. tests headless)."""
        if self._watcher:
            with self._watcher.suspended():
                yield
        else:
            yield

    # ── Helpers ───────────────────────────────────────────────────

    # `self.suspended()` et non `self._watcher.suspended()` : sans watcher
    # (build headless, test), l'accès direct lève une AttributeError au fond
    # d'un slot Qt, donc un abandon de processus sans trace.
    def _save_scene(self):
        if not self._project or not self._project.active_scene:
            return
        with self.suspended():
            self._project.save_scene(self._project.active_scene)

    def _save_all(self):
        if not self._project:
            return
        with self.suspended():
            self._project.save()

    # ── Actor ─────────────────────────────────────────────────────

    def add_actor(self, name: str, x: int = 0, y: int = 0) -> Optional[Actor]:
        """Ajoute un actor vide à la scène active aux coordonnées données (avec historique)."""
        if not self._project or not self._project.active_scene:
            return None
        scene = self._project.active_scene
        actor = Actor(name=name, x=x, y=y)

        def persist():
            self._save_scene()
            self._emit("actors_list_changed")
            self._emit("scene_sprites_changed")

        get_history().push(AddActorCmd(scene, actor, persist_fn=persist))
        get_bus().select(actor)
        self._emit("status_message", f"Actor created: {name}")
        return actor

    def status(self, msg: str):
        """Affiche un message dans la barre de statut.

        Exposé parce que des écrans en émettent aussi (une zone de texte créée
        au canvas, par exemple) : sans ce point d'entrée, ils appelleraient
        `_emit` depuis l'extérieur du dispatcher."""
        self._emit("status_message", msg)

    def delete_actor(self, actor: Actor):
        """Supprime un actor de la scène active (avec historique)."""
        self.delete_actors([actor])

    def delete_actors(self, actors: list):
        """Supprime un LOT d'actors de la scène active en UNE entrée
        d'historique — supprimer une sélection est un seul geste, l'annuler
        doit l'être aussi (même règle que `duplicate_actors`)."""
        from core.history import RemoveListItemsCmd
        if not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        victims = [a for a in actors if any(x is a for x in scene.actors)]
        if not victims:
            return

        def persist():
            get_bus().clear()
            self._save_scene()
            self._emit("actors_list_changed")
            self._emit("scene_sprites_changed")

        n = len(victims)
        get_history().push(RemoveListItemsCmd(
            scene.actors, victims, persist_fn=persist,
            label=f"Deleted {n} actor{'s' if n > 1 else ''}"))
        self._emit("status_message",
                   f"Deleted actor: {victims[0].name}" if n == 1
                   else f"Deleted {n} actors")

    def duplicate_actor(self, actor: Actor, dx: int = 8, dy: int = 8) -> Optional[Actor]:
        """Duplique un actor (copie profonde des composants) dans la scène active,
        décalé de (dx, dy) et renommé de façon unique. Undoable."""
        new = self.duplicate_actors([actor], dx, dy)
        return new[0] if new else None

    def duplicate_actors(self, actors: list, dx: int = 8, dy: int = 8) -> list:
        """Duplique un LOT d'actors de la scène active en UNE entrée d'historique.

        Les sources doivent appartenir à la scène — c'est ce qui distingue le
        dupliquer du coller, dont les sources viennent du presse-papier (et
        peut-être d'une autre scène)."""
        if not self._project or not self._project.active_scene:
            return []
        scene = self._project.active_scene
        sources = [a for a in actors if any(x is a for x in scene.actors)]
        return self._add_actor_copies(sources, dx, dy, "Duplicated")

    def paste_actors(self, actors: list, dx: int = 0, dy: int = 0) -> list:
        """Colle des actors venus du presse-papier du canvas dans la scène active.

        Mêmes copies et même unicité de nom que `duplicate_actors` ; seule
        l'appartenance à la scène n'est pas exigée, la source ayant pu être
        copiée ailleurs (voire supprimée depuis)."""
        return self._add_actor_copies(list(actors), dx, dy, "Pasted")

    def _add_actor_copies(self, sources: list, dx: int, dy: int, verb: str) -> list:
        """Cœur commun du dupliquer / coller : copie profonde, nom unique,
        position résolue puis décalée, et UNE commande d'historique pour le lot."""
        from core.history import AddListItemsCmd
        if not self._project or not self._project.active_scene or not sources:
            return []
        scene = self._project.active_scene
        # La position peut être un littéral px/tile ou une réf de variable :
        # on la résout en pixels avant d'appliquer le décalage (la copie devient
        # un placement littéral distinct).
        from core.models.field_value import (FieldValue, make_resolver,
                                             var_names_from_project)
        r = make_resolver(self._project)
        _vn = var_names_from_project(self._project)
        taken = {a.name for a in scene.actors}
        copies: list[Actor] = []
        for src in sources:
            new = copy.deepcopy(src)
            new.name = _copy_name(src.name, taken)
            taken.add(new.name)
            new.x = FieldValue.parse(src.x, _vn).px(r) + dx
            new.y = FieldValue.parse(src.y, _vn).px(r) + dy
            copies.append(new)

        def persist():
            self._save_scene()
            self._emit("actors_list_changed")
            self._emit("scene_sprites_changed")

        n = len(copies)
        get_history().push(AddListItemsCmd(
            scene.actors, copies, persist_fn=persist,
            label=f"{verb} {n} actor{'s' if n > 1 else ''}"))
        get_bus().select(copies[0])
        self._emit("status_message",
                   f"{verb} actor: {copies[0].name}" if n == 1
                   else f"{verb} {n} actors")
        return copies

    def instantiate_prefab(self, prefab_name: str, x: int, y: int) -> Optional[Actor]:
        """Instancie un prefab dans la scène active aux coordonnées données."""
        if not self._project or not self._project.active_scene:
            return None
        prefab = self._project.get_prefab(prefab_name)
        if not prefab:
            return None
        existing = {a.name for a in self._project.active_scene.actors}
        name = prefab.name
        counter = 1
        while name in existing:
            name = f"{prefab.name}_{counter}"
            counter += 1
        actor = self._project.instantiate_actor_from_prefab(prefab, name, x=x, y=y)
        self._project.active_scene.actors.append(actor)
        self._save_scene()
        self._emit("actors_list_changed")
        self._emit("scene_sprites_changed")
        get_bus().select(actor)
        return actor

    # ── Scene ─────────────────────────────────────────────────────

    def add_scene(self, name: str) -> Optional[Scene]:
        """Crée une nouvelle scène vide et la persiste."""
        if not self._project:
            return None
        # Une scène NEUVE naît en budget AUTO (ROADMAP v0.17, révision
        # 2026-09-19) : le budget est dérivé, `128 − acteurs_posés − OBJ_UI`,
        # rien à réserver d'avance. `actor_slots` reste à 0 (override réservé à
        # plus tard) ; l'ancien seeding 96/32 a disparu avec `DEFAULT_ACTOR_SLOTS`.
        scene = Scene(name=name)
        self._project.seed_default_ui_palette(scene)
        self._project.scenes.append(scene)
        with self._watcher.suspended():
            self._project.save_scene(scene)
        # Une scène de plus change l'arbre projet : les vues qui en dérivent
        # (project viewer, graphe des scènes) doivent l'apprendre tout de suite,
        # pas au prochain aller-retour d'écran.
        self._emit("project_tree_changed")
        self._emit("status_message",f"Scene created: {name}")
        return scene

    # ── Camera ────────────────────────────────────────────────────

    def add_camera(self, name: Optional[str] = None) -> Optional["Camera"]:
        """Ajoute une caméra à la scène active (avec historique). Nom unique
        à l'échelle du PROJET (cf. `Project.camera_names` — `camera.switch`
        n'est pas qualifié par scène)."""
        from core.history import AddListItemCmd
        from core.models.camera import Camera
        from core.selection_bus import CameraSelection
        if not self._project or not self._project.active_scene:
            return None
        scene = self._project.active_scene
        cam = Camera(name=unique_name(name or "Camera", self._project.camera_names()))

        def persist():
            self._save_scene()
            self._emit("cameras_list_changed")

        get_history().push(AddListItemCmd(scene.cameras, cam, persist_fn=persist,
                                          label=f"Add camera {cam.name}"))
        get_bus().select(CameraSelection(scene, cam))
        self._emit("status_message", f"Camera created: {cam.name}")
        return cam

    def delete_camera(self, camera):
        """Supprime une caméra de la scène active (avec historique)."""
        from core.history import RemoveListItemsCmd
        from core.selection_bus import CameraSelection
        if not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        if not any(c is camera for c in scene.cameras):
            return

        def persist():
            get_bus().clear()
            self._save_scene()
            self._emit("cameras_list_changed")

        get_history().push(RemoveListItemsCmd(
            scene.cameras, [camera], persist_fn=persist,
            label=f"Deleted camera {camera.name}"))
        self._emit("status_message", f"Deleted camera: {camera.name}")

    # ── Prefab ────────────────────────────────────────────────────

    def add_prefab(self, name: str) -> Optional[Prefab]:
        """Crée un nouveau prefab vide et le persiste."""
        if not self._project:
            return None
        prefab = Prefab(name=name)
        self._project.prefabs.append(prefab)
        with self._watcher.suspended():
            self._project.save_prefab(prefab)
        self._emit("status_message",f"Prefab created: {name}")
        return prefab

    # ── Sprite ────────────────────────────────────────────────────

    def save_sprite(self, sprite) -> None:
        """
        Persiste un SpriteAsset et notifie les canvas scène ouverts —
        sinon un acteur affiché dans le Scene Manager continue de montrer
        les anciennes frames après une édition dans le Sprite Editor.
        """
        if not self._project:
            return
        with self._watcher.suspended():
            self._project.save_sprite(sprite)
        self._emit("scene_sprites_changed")

    def rename_sprite(self, sprite, new_name: str) -> None:
        """Renomme un SpriteAsset (PNG + sidecar) et répare les SpriteComponent
        qui le référencent par nom, sur tous les Actors (scènes) et Prefabs —
        cf. Project.rename_sprite. Notifie les canvas scène ouverts."""
        if not self._project:
            return
        with self._watcher.suspended():
            self._project.rename_sprite(sprite, new_name)
        self._emit("scene_sprites_changed")

    # ── Palette ───────────────────────────────────────────────────

    def save_palette(self, bank) -> None:
        """Persiste une PaletteBank (l'ajoute au catalogue si nouvelle) et
        notifie les écrans affichant le catalogue — ex. une palette extraite
        depuis le Sprite Editor doit apparaître dans le Palette Finder sans
        recharger le projet."""
        if not self._project:
            return
        if self._project.palettes.get(bank.name) is None:
            self._project.palettes.append(bank)
        with self._watcher.suspended():
            self._project.palettes.save(bank)
        self._emit("palettes_changed")

    # ── Background ────────────────────────────────────────────────

    def notify_background_changed(self, ba) -> None:
        """Émet bg_slot_changed pour chaque layer de la scène active référençant
        ce BackgroundAsset — pour que le Scene Manager rafraîchisse son canvas
        immédiatement après une mutation depuis le Background Editor (palette,
        inpainting, recompression). N'affecte pas la sauvegarde elle-même."""
        if not self._project or not self._project.active_scene:
            return
        for layer in self._project.active_scene.background_layers:
            if layer.background_name == ba.name:
                self._emit("bg_slot_changed", layer.bg_slot)

    def import_background_png(self, path_str: str):
        """Importe un PNG dans assets/backgrounds/ et crée le BackgroundAsset associé."""
        if not self._project or not path_str:
            return
        ap = Path(path_str)
        dst = self._project.import_asset(ap, "backgrounds")
        with self._watcher.suspended():
            warning = asset_reconciliation.sync_background_png(self._project, dst)
        msg = f"Background imported: {dst.stem}"
        if warning:
            msg += f" — {warning}"
        self._emit("status_message", msg)
        self._emit("bg_slot_changed", 0)

    # ── Sprite ────────────────────────────────────────────────────

    def import_sprite_png(self, path_str: str):
        """Importe un PNG dans assets/sprites/ et crée le SpriteAsset associé, via
        le pipeline aligné sur les backgrounds : Validator → Encodage → asset.
        Miroir de import_background_png."""
        if not self._project or not path_str:
            return
        ap = Path(path_str)
        dst = self._project.import_asset(ap, "sprites")
        with self._watcher.suspended():
            warning = asset_reconciliation.sync_sprite_png(self._project, dst)
        msg = f"Sprite imported: {dst.stem}"
        if warning:
            msg += f" — {warning}"
        self._emit("status_message", msg)
        self._emit("scene_sprites_changed")

    # ── Prefab avec propagation ───────────────────────────────────

    def save_prefab(self, prefab: Prefab):
        """
        Sauvegarde le prefab ET propage ses components à toutes les instances
        liées (actor.prefab_name == prefab.name) dans toutes les scènes.
        La position/transform de chaque instance reste inchangée.
        """
        if not self._project:
            return
        with self._watcher.suspended():
            self._project.save_prefab(prefab)

        # Propagation cross-scène
        scenes_updated: list[Scene] = []
        for scene in self._project.scenes:
            changed = False
            for actor in scene.actors:
                if actor.prefab_name == prefab.name:
                    actor.components = copy.deepcopy(prefab.components)
                    changed = True
            if changed:
                with self._watcher.suspended():
                    self._project.save_scene(scene)
                scenes_updated.append(scene)

        if scenes_updated:
            self._emit("scene_sprites_changed")
            self._emit("actors_list_changed")

        n = len(scenes_updated)
        msg = f"Prefab '{prefab.name}' saved"
        if n:
            msg += f" — {n} scene{'s' if n > 1 else ''} updated"
        self._emit("status_message",msg)

    def relink_actor_to_prefab(self, actor: Actor) -> bool:
        """« Relink to prefab » : recharge `actor` depuis son prefab —
        composants, palette et notes reviennent à l'état du template
        (« remettre les valeurs par défaut »). La réservation affine suit dans
        les composants : elle vit sur le SpriteComponent. La POSE
        (x/y/rotation/scale/parent/priorité/...) reste celle de l'instance :
        elle n'a jamais appartenu au prefab (cf. core/models/scene.Prefab)."""
        if not self._project or not actor.prefab_name:
            return False
        prefab = self._project.get_prefab(actor.prefab_name)
        if not prefab:
            return False
        actor.components = copy.deepcopy(prefab.actor.components)
        actor.pal_bank = prefab.actor.pal_bank
        actor.notes = prefab.actor.notes
        self._save_scene()
        self._emit("scene_sprites_changed")
        self._emit("actors_list_changed")
        # Le project viewer (AssetsFinderPanel) et l'arbre de scène montrent
        # tous deux cet acteur comme instance d'un prefab (icône, badge) —
        # une action lancée depuis ce même badge doit les tenir à jour.
        self._emit("project_tree_changed")
        self._emit("status_message", f"{actor.name} relinked to '{prefab.name}'")
        return True

    def expose_actor_to_prefab(self, actor: Actor) -> bool:
        """« Expose to prefab » : pousse les composants/palette/notes de CETTE
        instance vers son prefab — l'inverse de Relink (la réservation affine
        voyage avec le SpriteComponent).
        Passe par `save_prefab()`, qui persiste ET propage à toutes les
        autres instances liées (même comportement qu'éditer le prefab
        directement — Expose ne fait qu'y injecter l'état de l'instance
        d'abord)."""
        if not self._project or not actor.prefab_name:
            return False
        prefab = self._project.get_prefab(actor.prefab_name)
        if not prefab:
            return False
        prefab.actor.components = copy.deepcopy(actor.components)
        prefab.actor.pal_bank = actor.pal_bank
        prefab.actor.notes = actor.notes
        self.save_prefab(prefab)
        # cf. relink_actor_to_prefab — même badge, même besoin de tenir à
        # jour le project viewer et l'arbre de scène.
        self._emit("project_tree_changed")
        return True

    def create_prefab_from_actor(self, actor: Actor) -> Optional[Prefab]:
        """« Expose to prefab » depuis un acteur QUI N'EST PAS déjà une
        instance : crée un nouveau Prefab à partir de son état actuel
        (composants/palette/réservation affine/notes — la POSE ne fait
        jamais partie d'un prefab, cf. core/models/scene.Prefab) et fait de
        cet acteur sa première instance liée."""
        if not self._project:
            return None
        existing = {pf.name for pf in self._project.prefabs}
        name = unique_name(actor.name, existing)
        new_actor = copy.deepcopy(actor)
        new_actor.name = name
        prefab = Prefab(name=name, actor=new_actor)
        self._project.prefabs.append(prefab)
        with self._watcher.suspended():
            self._project.save_prefab(prefab)
        actor.prefab_name = name
        self._save_scene()
        self._emit("actors_list_changed")
        # Nouveau prefab : le project viewer doit le lister sans qu'il faille
        # rouvrir le projet.
        self._emit("project_tree_changed")
        self._emit("status_message", f"Prefab created from {actor.name}: '{name}'")
        return prefab

    # ── Saves ─────────────────────────────────────────────────────

    def save_scene(self):
        """Sauvegarde la scène active (après drag actor, déplacement caméra)."""
        self._save_scene()

    def save_all(self):
        """Sauvegarde globale différée (après changements inspector)."""
        self._save_all()

    def notify_scripts_changed(self):
        """Notifie que la liste des scripts a changé (création, suppression)."""
        self._emit("scripts_changed")

    def notify_ui_text_links_changed(self):
        """Notifie qu'un élément de mise en page vient de changer de
        `text_key` — l'écran Texte cache qui cite quoi (`text_usage_index`) et
        doit l'oublier, sous peine d'afficher « unused » sur une entrée qu'on
        vient pourtant de brancher."""
        self._emit("ui_text_links_changed")

    def flush_script_edits(self):
        """Demande au Script Editor de persister sa frappe en cours.

        Émis AVANT toute réécriture de scripts sur disque (renommage) : sans ça
        la réécriture part de la version disque, ignore les lignes non sauvées,
        et l'éditeur se retrouve avec un buffer en conflit dont la sauvegarde
        rétablirait l'ancien nom — le lien serait cassé en silence."""
        self._emit("flush_script_edits")


_dispatcher = CommandDispatcher()


def get_dispatcher() -> CommandDispatcher:
    return _dispatcher
