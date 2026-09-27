"""core/project_renames.py — renommer un élément et réparer ce qui le cite.

Un renommage n'est jamais une simple écriture de champ : il déplace le fichier
sidecar, réécrit les scripts Lua qui citent l'ancien nom, met à jour les `$nom`
des textes, et annonce ce qu'il a touché. `_renaming` entoure tout ça de la
portée que l'application a posée (frappe en cours persistée, surveillant de
fichiers suspendu).

Ce qui est annoncé, ce sont des FAITS : `_notify_renamed` émet quoi, d'où vers
où et combien de références réécrites. La phrase affichée à l'utilisateur est
rédigée par `CommandDispatcher`, pas ici. Le projet ne connaît pas l'interface.

Une TRANCHE de la classe `Project`, pas un module autonome : les méthodes
ci-dessous s'appellent `self.…` entre elles et avec le reste de `Project`. La
découpe sert la lecture — chaque responsabilité dans son fichier — sans ajouter
le moindre saut d'appel : un mixin est résolu à la construction de la classe,
`project.rename_scene(…)` s'écrit exactement comme avant.

**Ce fichier n'importe jamais `core.project`** : ce serait un cycle immédiat,
puisque `project.py` l'importe pour composer la classe.
"""

from contextlib import contextmanager
from typing import Optional

from core.models.audio import Music
from core.models.background import BackgroundAsset
from core.models.components import SpriteComponent, ScriptComponent
from core.models.palette import PaletteBank, PaletteUsage, OWN_PAL_BANK
from core.models.scene import Scene
from core.models.sprite import SpriteAsset
from scripting.api import (
    DOMAIN_SCENE, DOMAIN_CAMERA, DOMAIN_PREFAB, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_FONT,
    DOMAIN_ACTOR, DOMAIN_UI_ELEMENT, DOMAIN_WIN_REGION,
)


class ProjectRenameMixin:
    # ── Renommage (supprime l'ancien fichier + répare les références) ──
    # ResourceStore.rename() seul ne suffit pas : il faut aussi mettre à
    # jour tout ce qui référence l'ancien nom ailleurs dans le projet.

    def rename_background(self, bg: BackgroundAsset, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == bg.name:
            return
        old_name = bg.name
        # Renommer aussi le PNG source : un BackgroundAsset est keyé par le stem
        # de son PNG (name == stem(source)). Sans ça, la réconciliation des fonds
        # recréerait un asset orphelin depuis l'ancien PNG au prochain chargement.
        old_png = (self.background_images_dir / bg.asset) if bg.asset else None
        if old_png and old_png.exists():
            new_png = old_png.with_name(f"{new_name}{old_png.suffix}")
            if not new_png.exists():
                old_png.rename(new_png)
                bg.asset = new_png.name
        self.backgrounds.rename(bg, new_name)
        # Met à jour les layers des scènes qui référencent ce fond par nom.
        for scene in self.scenes:
            touched = False
            for L in scene.background_layers:
                if L.background_name == old_name:
                    L.background_name = new_name
                    touched = True
            if touched:
                self.save_scene(scene)
        self._notify_renamed("Background", old_name, new_name)

    def rename_sprite(self, sprite: SpriteAsset, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == sprite.name:
            return
        old_name = sprite.name
        # Renommer aussi le PNG source : un SpriteAsset est keyé par le stem
        # de son PNG (comme BackgroundAsset). Sans ça, la réconciliation des
        # sprites recréerait un asset orphelin depuis l'ancien PNG au prochain
        # chargement.
        old_png = self.asset_abs(sprite.asset) if sprite.asset else None
        if old_png and old_png.exists():
            new_png = old_png.with_name(f"{new_name}{old_png.suffix}")
            if not new_png.exists():
                old_png.rename(new_png)
                sprite.asset = self.asset_rel(new_png)
        self.sprites.rename(sprite, new_name)
        # Met à jour les SpriteComponent (Actors inline dans les scènes, et
        # Prefabs) qui référencent ce sprite par nom.
        for scene in self.scenes:
            touched = False
            for actor in scene.actors:
                for comp in actor.components:
                    if isinstance(comp, SpriteComponent) and comp.sprite_name == old_name:
                        comp.sprite_name = new_name
                        touched = True
            if touched:
                self.save_scene(scene)
        for prefab in self.prefabs:
            touched = False
            for comp in prefab.components:
                if isinstance(comp, SpriteComponent) and comp.sprite_name == old_name:
                    comp.sprite_name = new_name
                    touched = True
            if touched:
                self.save_prefab(prefab)
        # Aucun domaine Lua : un sprite se référence par son composant, pas
        # depuis un script (les animations, elles, ont DOMAIN_ANIM).
        self._notify_renamed("Sprite", old_name, new_name)

    def rename_scene(self, scene: Scene, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == scene.name:
            return
        old_name = scene.name
        with self._renaming():
            self.scenes.rename(scene, new_name)
            touched = False
            for field in ("start_scene", "last_scene"):
                if getattr(self.settings, field) == old_name:
                    setattr(self.settings, field, new_name)
                    touched = True
            if touched:
                self.save_settings()
            refs = self.rename_lua_refs(DOMAIN_SCENE, old_name, new_name)
        self._notify_renamed("Scene", old_name, new_name, refs)

    def rename_camera(self, scene: Scene, camera, new_name: str):
        """Renomme une caméra POSSÉDÉE par `scene` et répare ce qui la cite :
        le pointeur `scene.camera` s'il la désignait, et les `camera:switch(…)`
        des scripts — non qualifiés par scène, donc potentiellement n'importe
        où dans le projet (cf. models/camera.py). Refuse en silence une
        collision avec une autre caméra du projet — même contrainte que la
        constante C `CAM_<NOM>` qu'elle recevra."""
        new_name = new_name.strip()
        old_name = camera.name
        if (not new_name or new_name == old_name or camera not in scene.cameras
                or new_name in (self.camera_names() - {old_name})):
            return
        with self._renaming():
            camera.name = new_name
            if getattr(scene, "camera", "") == old_name:
                scene.camera = new_name
            self.save_scene(scene)
            refs = self.rename_lua_refs(DOMAIN_CAMERA, old_name, new_name)
        self._notify_renamed("Camera", old_name, new_name, refs)

    def rename_window(self, scene: Scene, window, new_name: str):
        """Renomme un `WindowSlot` rectangle POSSÉDÉ par `scene` et répare les
        `window.*("…")` des scripts — non qualifiés par scène (cf.
        models/scene.py, WindowSlot). Refuse en silence une collision avec
        une autre window du projet OU avec un mot-clé fixe ("object"/
        "outside") — même contrainte que la constante C `WIN_<NOM>`."""
        new_name = new_name.strip()
        old_name = window.name
        if (not new_name or new_name == old_name or window not in scene.windows
                or window.is_obj or new_name.lower() in ("object", "outside")
                or new_name in (self.window_names() - {old_name})):
            return
        with self._renaming():
            window.name = new_name
            self.save_scene(scene)
            refs = self.rename_lua_refs(DOMAIN_WIN_REGION, old_name, new_name)
        self._notify_renamed("Window", old_name, new_name, refs)

    def rename_prefab(self, prefab, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == prefab.name:
            return
        old_name = prefab.name
        with self._renaming():
            self.prefabs.rename(prefab, new_name)
            # Instances placées dans les scènes : elles pointent le template par nom.
            for scene in self.scenes:
                touched = False
                for actor in scene.actors:
                    if getattr(actor, "prefab_name", "") == old_name:
                        actor.prefab_name = new_name
                        touched = True
                if touched:
                    self.save_scene(scene)
            refs = self.rename_lua_refs(DOMAIN_PREFAB, old_name, new_name)
        self._notify_renamed("Prefab", old_name, new_name, refs)

    def rename_actor(self, actor, new_name: str, scene: Optional[Scene] = None):
        """Actor placé dans une scène (pas un template de prefab — cf.
        rename_prefab). `scene` est sauvegardée si fournie."""
        new_name = new_name.strip()
        if not new_name or new_name == actor.name:
            return
        old_name = actor.name
        with self._renaming():
            refs = self.rename_lua_refs(DOMAIN_ACTOR, old_name, new_name)
            for path, n in self._rename_actor_ref_exports(old_name, new_name).items():
                refs[path] = refs.get(path, 0) + n
            actor.name = new_name
            if scene is not None:
                self.save_scene(scene)
        self._notify_renamed("Actor", old_name, new_name, refs)

    def _rename_actor_ref_exports(self, old_name: str, new_name: str) -> dict:
        """Un export `actor_ref` choisi dans l'inspecteur (menu déroulant, cf.
        `component_editors/script.py`) stocke le NOM de l'acteur visé dans
        `ScriptComponent.exports_values` — pas une référence vivante. Sans ce
        suivi, renommer l'acteur visé laissait la valeur pointer dans le vide :
        le même trou que celui déjà refermé pour l'`id` d'un composant sprite
        (`rename_sprite_id_refs`). Retourne `{script: nombre de valeurs
        corrigées}`, dans le même format que `rename_lua_refs`."""
        from scripting.exports_parser import parse_exports
        touched: dict = {}
        export_types_by_script: dict = {}   # cache : un .lua peut être partagé par N instances

        def actor_ref_names(script_rel: str) -> set[str]:
            if script_rel not in export_types_by_script:
                path = self.asset_abs(script_rel)
                exports = parse_exports(path) if path else []
                export_types_by_script[script_rel] = {
                    e["name"] for e in exports if e["type"] == "actor_ref"
                }
            return export_types_by_script[script_rel]

        def fix_component(comp) -> bool:
            if not isinstance(comp, ScriptComponent) or not comp.script or not comp.exports_values:
                return False
            changed = False
            for key in actor_ref_names(comp.script) & comp.exports_values.keys():
                if comp.exports_values[key] == old_name:
                    comp.exports_values[key] = new_name
                    changed = True
                    path = self.asset_abs(comp.script)
                    touched[path] = touched.get(path, 0) + 1
            return changed

        for scn in self.scenes:
            scn_touched = any([fix_component(c) for a in scn.actors for c in a.components])
            if scn_touched:
                self.save_scene(scn)
        for pf in self.prefabs:
            if any([fix_component(c) for c in pf.components]):
                self.save_prefab(pf)
        return touched

    def rename_ui_element(self, layout, element, new_name: str) -> str:
        """Renomme un élément d'une mise en page UI (texte, conteneur, image).

        **Unicité sur TOUT le projet, quel que soit le type** (cf.
        `ui_element_names`) : un texte se résout en `REGION_*` et une image en
        `IMAGE_*`, deux constantes C projet-globales, et le conteneur partage
        l'espace des refs `parent`. Chercher au plus large évite d'avoir à
        expliquer pourquoi deux éléments homonymes coexistent parfois.

        Les enfants pointant le parent par NOM, on les rebranche
        (`retarget_parent`) AVANT de figer le nouveau nom. Le nom se cite dans les
        scripts par `interface:get("Nom")`, pour TOUS les types — c'est un seul
        domaine, y compris pour un conteneur. Retourne le nom RÉELLEMENT appliqué
        (peut différer si collision)."""
        from core.models.ui_region import (
            KIND_TEXT, KIND_IMAGE, KIND_LIST, unique_element_name)
        new_name = new_name.strip()
        if not new_name or new_name == element.name:
            return element.name
        taken = set(self.ui_element_names()) - {element.name}
        if new_name in taken:
            new_name = unique_element_name(taken, new_name)
        kind = getattr(element, "kind", KIND_TEXT)
        # Un élément ne se cite que par `interface:get("Nom")`, quelle que soit sa nature :
        # UN domaine, donc un conteneur — qu'aucun domaine ne couvrait — est réécrit aussi.
        domain = DOMAIN_UI_ELEMENT
        label = {KIND_TEXT: "Text", KIND_IMAGE: "Image",
                 KIND_LIST: "List"}.get(kind, "UI element")
        old_name = element.name
        with self._renaming():
            layout.retarget_parent(old_name, new_name)
            # Le curseur d'une liste DÉSIGNE une image par son nom, comme un
            # enfant désigne son parent : renommer l'image sans rebrancher
            # laisserait la liste pointer dans le vide, et le build se
            # contenterait d'un avertissement.
            if kind == KIND_IMAGE:
                for el in layout.elements:
                    if getattr(el, "cursor_image", "") == old_name:
                        el.cursor_image = new_name
            element.name = new_name
            refs = self.rename_lua_refs(domain, old_name, new_name) if domain else {}
            self.ui_layouts.save_all()
        self._notify_renamed(label, old_name, new_name, refs)
        return new_name

    def rename_ui_layout(self, layout, new_name: str) -> str:
        """Renomme un nœud `Interface` (l'asset `UILayout`, `project/ui_layouts/
        <nom>.json`) et répare les scènes qui le citent.

        Une scène référence ses nœuds par NOM (`Scene.ui_layouts`, v0.25) : le
        renommage remplace le nom EN PLACE dans chaque liste, pour ne pas changer
        l'ordre des nœuds d'une scène. Aucun domaine Lua — un nœud ne se cite pas
        depuis un script (seuls ses éléments le font, via `REGION_*`/`IMAGE_*`).
        Retourne le nom RÉELLEMENT appliqué (peut différer si collision)."""
        new_name = new_name.strip()
        if not new_name or new_name == layout.name:
            return layout.name
        taken = {l.name for l in self.ui_layouts} - {layout.name}
        if new_name in taken:
            base, n = new_name, 2
            while new_name in taken:
                new_name = f"{base}_{n:02d}"
                n += 1
        old_name = layout.name
        with self._renaming():
            self.ui_layouts.rename(layout, new_name)
            for scene in self.scenes:
                nodes = getattr(scene, "ui_layouts", None) or []
                touched = False
                for node in nodes:
                    if node.layout_name == old_name:
                        node.layout_name = new_name
                        touched = True
                if touched:
                    self.save_scene(scene)
        self._notify_renamed("Interface", old_name, new_name)
        return new_name

    def rename_sound(self, asset, new_name: str):
        """Sfx ou Music — même chemin, seul le domaine Lua diffère."""
        new_name = new_name.strip()
        if not new_name or new_name == asset.name:
            return
        old_name = asset.name
        is_music = isinstance(asset, Music)
        with self._renaming():
            (self.music if is_music else self.sfx).rename(asset, new_name)
            refs = self.rename_lua_refs(DOMAIN_MUSIC if is_music else DOMAIN_SFX,
                                        old_name, new_name)
        self._notify_renamed("Music" if is_music else "SFX",
                             old_name, new_name, refs)

    def palette_usages(self, name: str) -> list[PaletteUsage]:
        """Tout ce qui utilise la banque `name` — alimente la carte « USAGE »
        du Palette Editor.

        MÊMES référents que `rename_palette` : les deux doivent connaître
        exactement la même liste, sinon on répare un lien qu'on n'affiche pas
        (ou l'inverse).
          - sprites / fonds : override de sous-palette (`palette_overrides`) ;
          - scènes          : sélection active OBJ/BG (l'index EST la banque
            hardware, d'où l'affichage du slot) ;
          - prefabs         : `pal_bank` résolu via la scène d'ancrage (la 1re
            scène), exactement comme au build (cf. codegen/palette_alloc.py).
        Les Actors n'ont pas de ligne propre : un actor ne peut viser qu'un slot
        DÉJÀ dans la sélection active de sa scène — la ligne de la scène couvre
        le lien."""
        usages: list[PaletteUsage] = []
        if not name:
            return usages

        for assets, kind in ((self.sprites, "sprite"), (self.backgrounds, "background")):
            for asset in assets:
                overrides = getattr(asset, "palette_overrides", None) or {}
                slots = sorted(i for i, n in overrides.items() if n == name)
                if slots:
                    usages.append(PaletteUsage(
                        kind, asset.name,
                        "sous-palette " + ", ".join(str(i) for i in slots)))

        for scene in self.scenes:
            slots = []
            for pool, attr in (("OBJ", "active_obj_palettes"), ("BG", "active_bg_palettes")):
                for i, n in enumerate(getattr(scene, attr, None) or []):
                    if n == name:
                        slots.append(f"{pool} {i}")
            if slots:
                usages.append(PaletteUsage("scene", scene.name, "banque " + ", ".join(slots)))

        anchor = self.scenes[0] if len(self.scenes) else None
        anchor_active = list(getattr(anchor, "active_obj_palettes", None) or []) if anchor else []
        for prefab in self.prefabs:
            pb = getattr(prefab, "pal_bank", OWN_PAL_BANK)
            if pb != OWN_PAL_BANK and 0 <= pb < len(anchor_active) and anchor_active[pb] == name:
                usages.append(PaletteUsage("prefab", prefab.name,
                                           f"banque OBJ {pb} via « {anchor.name} »"))
        return usages

    def rename_palette(self, bank: PaletteBank, new_name: str):
        """Renomme une PaletteBank du catalogue et répare TOUT ce qui la cite par
        nom :
          - la sélection active des scènes (`active_obj_palettes` /
            `active_bg_palettes`) — remplacement EN PLACE : l'index dans la liste
            est la banque hardware, il ne doit jamais bouger ;
          - les overrides de sous-palette des sprites et des fonds
            (`palette_overrides` = {idx dérivé -> nom de banque}).
        Sans cette réparation, `palettes.rename()` seul laisse les scènes pointer
        un nom mort : le slot devient vide au build (garde-fou du validateur) et
        l'asset s'affiche avec le contenu par défaut de la banque.
        Aucun domaine Lua : une palette ne se cite pas depuis un script."""
        new_name = new_name.strip()
        if not new_name or new_name == bank.name:
            return
        old_name = bank.name
        with self._renaming():
            self.palettes.rename(bank, new_name)
            for scene in self.scenes:
                touched = False
                for attr in ("active_obj_palettes", "active_bg_palettes"):
                    names = getattr(scene, attr, None) or []
                    for i, n in enumerate(names):
                        if n == old_name:
                            names[i] = new_name
                            touched = True
                if touched:
                    self.save_scene(scene)
            for assets, save in ((self.sprites, self.save_sprite),
                                 (self.backgrounds, self.save_background)):
                for asset in assets:
                    overrides = getattr(asset, "palette_overrides", None) or {}
                    hits = [i for i, n in overrides.items() if n == old_name]
                    for i in hits:
                        overrides[i] = new_name
                    if hits:
                        save(asset)
        self._notify_renamed("Palette", old_name, new_name)

    def rename_font(self, font, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == font.name:
            return
        old_name = font.name
        with self._renaming():
            self.fonts.rename(font, new_name)
            refs = self.rename_lua_refs(DOMAIN_FONT, old_name, new_name)
            # FontAsset est le seul consommateur qui cite une SOURCE de police
            # à ce stade. Le garder ici, avec les scènes et les scripts, évite
            # de laisser une chaîne de couverture devenir silencieusement morte.
            for font_asset in self.font_assets:
                changed = False
                for sources in font_asset.sources.values():
                    for i, source_name in enumerate(sources):
                        if source_name == old_name:
                            sources[i] = new_name
                            changed = True
                if any(face.source_name == old_name for face in font_asset.faces):
                    from core.models.font_asset import FontFace
                    font_asset.faces = [
                        FontFace(new_name if face.source_name == old_name else face.source_name,
                                 face.weight, face.italic)
                        for face in font_asset.faces
                    ]
                    changed = True
                if changed:
                    self.save_font_asset(font_asset)
            # `Scene.font_pal_banks` est keyé par NOM de police (cf.
            # `core/models/scene.font_pal_key`) : l'override de banque d'une
            # police NON-défaut vivrait sinon sous le nom mort, et retomberait en
            # silence sur la palette propre. La police PAR DÉFAUT passe par la clé
            # "" — stable, jamais old_name, donc épargnée. Même geste que
            # `rename_palette` pour `active_*_palettes`.
            for scene in self.scenes:
                banks = getattr(scene, "font_pal_banks", None) or {}
                if old_name in banks:
                    banks[new_name] = banks.pop(old_name)
                    self.save_scene(scene)
        self._notify_renamed("Font", old_name, new_name, refs)

    def rename_font_asset(self, font_asset, new_name: str):
        """Renomme une police logique.

        Le tag `[font=…]` et les colonnes de données typées `font` citent
        désormais un FontAsset par son nom (cf. `DATA_COLUMN_SOURCES`), mais leur
        propagation sur renommage suit le même régime que les autres références de
        cellule et de balisage : non câblée pour l'instant, à traiter d'un bloc
        avec la bascule des scènes et des layouts vers cette couche. Garder le
        renommage ici évite que le finder contourne Project et crée une seconde
        règle le jour où cette propagation arrive.
        """
        new_name = new_name.strip()
        if not new_name or new_name == font_asset.name:
            return
        old_name = font_asset.name
        with self._renaming():
            self.font_assets.rename(font_asset, new_name)
        self._notify_renamed("FontAsset", old_name, new_name)

    # ── Références Lua ───────────────────────────────────────────────
    # Un script cite un élément du projet par son NOM, mais ce nom n'est
    # qu'une étiquette d'auteur : au build il est déjà résolu en index
    # physique (SCENE_IDX_*, SFX_*, g_<var>…). Renommer côté éditeur doit
    # donc mettre les scripts à jour tout seul — le lien survit, l'écriture
    # reste lisible. Repérage structurel via scripting/refactor.py : seuls
    # les arguments déclarés comme références bougent (jamais un commentaire
    # ni une string sans rapport).

    def rename_sprite_id_refs(self, owner, old: str, new: str) -> dict:
        """Propage le renommage de l'`id` d'un composant sprite dans le script de
        SON propriétaire seulement. Deux acteurs peuvent avoir chacun un « normal » :
        renommer celui de l'un ne doit pas toucher le script de l'autre (contrairement
        à un nom d'asset, unique dans le projet). Un behavior partagé n'est pas
        réécrit : le checker signalera l'id devenu inconnu au build."""
        from core.models.components import ScriptComponent
        from scripting.api import DOMAIN_SPRITE_ID
        from scripting.refactor import rename_in_files
        scripts = [self.asset_abs(c.script) for c in getattr(owner, "components", [])
                   if isinstance(c, ScriptComponent) and c.active and c.script]
        return rename_in_files([s for s in scripts if s and s.exists()],
                               DOMAIN_SPRITE_ID, old, new)

    def rename_lua_refs(self, domain: str, old: str, new: str) -> dict:
        """Propage un renommage dans les scripts. Retourne {script: n} —
        vide si aucun script ne citait l'ancien nom."""
        from scripting.refactor import rename_in_project
        return rename_in_project(self, domain, old, new)

    # ── Tables de données ────────────────────────────────────────────
    # Une table et ses colonnes sont citées comme du CODE dans les scripts
    # (`data.Objets[i].prix`), pas comme des chaînes d'arguments : elles ne
    # passent donc pas par `rename_lua_refs` mais par le second type de site de
    # `scripting/refactor.py`. Le nom sur le disque, lui, se renomme comme
    # n'importe quelle ressource.

    def rename_data_table(self, table, new_name: str) -> bool:
        """Renomme une table et réécrit les scripts qui la citent.

        Refuse (sans rien faire) un nom vide, inchangé, déjà pris, ou qui n'est
        pas un identifiant : le script l'écrit sans guillemets, donc « Objets
        rares » ne s'écrirait pas."""
        from core.models.data_table import IDENTIFIER
        from scripting.refactor import rename_data_table_in_project
        new_name = new_name.strip()
        if (not new_name or new_name == table.name
                or not IDENTIFIER.match(new_name)
                or self.data_tables.get(new_name)):
            return False
        old_name = table.name
        with self._renaming():
            refs = rename_data_table_in_project(self, old_name, new_name)
            self.data_tables.rename(table, new_name)
        self._notify_renamed("Table", old_name, new_name, refs)
        return True

    def rename_data_column(self, table, column, new_name: str) -> bool:
        """Renomme une colonne : le schéma, la CLÉ de chaque ligne, et les
        scripts. Les trois ou aucun — une ligne dont la clé garderait l'ancien
        nom perdrait sa valeur au prochain chargement, sans un mot."""
        from core.models.data_table import IDENTIFIER
        from scripting.refactor import rename_data_column_in_project
        new_name = new_name.strip()
        if (not new_name or new_name == column.name
                or not IDENTIFIER.match(new_name)
                or table.column(new_name)):
            return False
        old_name = column.name
        with self._renaming():
            refs = rename_data_column_in_project(self, table.name, old_name, new_name)
            for row in table.rows:
                if old_name in row:
                    row[new_name] = row.pop(old_name)
            column.name = new_name
            self.data_tables.save(table)
        self._notify_renamed(f"Colonne de {table.name}", old_name, new_name, refs)
        return True
    # ── Renommage — plomberie commune ────────────────────────────────

    @contextmanager
    def _renaming(self):
        """Déroule un renommage dans la portée que l'application a posée.

        Ce qu'elle y met, quand il y en a une : la frappe en cours du Script
        Editor persistée AVANT de commencer (la réécriture lit les scripts sur
        disque, une ligne encore dans le buffer ne serait pas mise à jour), et le
        surveillant de fichiers suspendu pendant l'opération (les fichiers
        déplacés et réécrits sont NOS écritures ; sans ça il les rapporte comme
        modifiées à l'extérieur et l'éditeur recharge tout).

        Ici on ne sait rien de tout cela — juste qu'un renommage a une portée."""
        with self.rename_scope():
            yield

    def _notify_renamed(self, label: str, old: str, new: str,
                        refs: Optional[dict] = None, n_texts: int = 0,
                        n_regions: int = 0) -> None:
        """Annonce un renommage et son ampleur : quoi, d'où vers où, quelles
        références réécrites (`{chemin: nombre}`), combien de textes touchés
        (marqueurs `$nom`) et combien de zones d'interface repointées
        (`region.text_key`, cf. `rename_text_key`).

        Émis pour TOUT renommage, même celui qui n'a rien réécrit — sinon
        l'utilisateur n'a aucun retour quand rien ne référençait l'élément.
        Les FAITS seulement : la phrase affichée et les vues à rafraîchir
        regardent l'application, pas le projet."""
        self.events._emit("renamed", label, old, new, refs or {}, n_texts, n_regions)
