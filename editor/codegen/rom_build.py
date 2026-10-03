"""
Backstage — pipeline de build
Prend la scène active du projet et génère la ROM.

Flux :
  scène active → résolution des backgrounds + actors
  → grit BG    → grit_out/tileset.h
  → grit Actor → grit_out/actor_{name}.h
  → main.c     → src/main.c (+ scripts C copiés)
  → make       → obj/*.o → rom.elf → rom.gba
  → mgba
"""

import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from core import crash_log
from core.events import EventEmitter
from core.toolchain import Toolchain
from codegen.grit_conversion import (
    GritBackground, GritSprites, MmutilAudio,
    resolve_sound_assets, png_size,
    bg_layer_sym, bg_layer_sym_for, bg_map_geometry, bg_map_sbb_count,
    resolve_palette_bank,
)
from codegen.palette_alloc import (
    scene_bank_layout, effective_palette_colors, ui_image_sprite_pools,
)
from codegen.actor_budget import prefab_pool_instances
from codegen.oam_alloc import scene_pool_instances, owner_appearances
from core.models.components import displayed_sprite_component
from core.app_paths import RUNTIME_DIR
from codegen.runtime_codegen.headers import generate_actor_types, generate_runtime_api
from codegen.runtime_codegen.lua_compiler import transpile_all
from codegen.runtime_codegen.main_gen import generate_main
from codegen.runtime_codegen.gen_scene_query import ui_image_sprites
from core.models.palette import OWN_PAL_BANK
from core.models.components import SpriteComponent
from core.models.sprite import SpriteAsset
from core.models.scene import Actor
from core.project import Project
from core.validator import validate_project, build_error, build_warning
import codegen.build_output as build_output

# Pipeline scripting (Lua → C) : importée localement dans les méthodes, d'où
# l'ajout du dossier au sys.path ici pour que `from scripting.…` se résolve.
sys.path.insert(0, str(Path(__file__).parent))


# grit, gcc et make sont des exécutables Windows sans prise en charge des chemins
# longs : au-delà de 260 caractères ils échouent, et Python lève un `WinError 267`
# dès qu'il leur donne un dossier de travail trop long.
WINDOWS_PATH_LIMIT = 260
# Partie fixe, au-delà de `build_dir`, du plus long chemin que le build écrit ;
# le reste dépend des noms d'assets. CALIBRÉE sur une mesure (2026-10-02, projet
# à noms ≤ 8 caractères) : le build passe avec une racine de 214 caractères et
# casse à 218. Une marge de 2 en plus, donc un refus légèrement précoce plutôt
# que tardif.
_BUILD_PATH_OVERHEAD = 24


# `chemin:ligne:col: error: message` — la forme de gcc (et de make qui la relaie).
_TOOL_DIAGNOSTIC = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)(?::\d+)?:\s*(?P<kind>fatal error|error|warning|note):\s*"
    r"(?P<message>.*)$")


def path_too_long_message(p: Project) -> Optional[str]:
    """Un message si le projet est trop profond pour les outils de build Windows,
    None sinon. Contrôlé AVANT de générer quoi que ce soit : la même panne sortait
    sinon sous forme d'`erreur inattendue` et de trace Python, au milieu du build.

    L'estimation prend le plus long nom d'asset DEUX fois : `actor_<Scène>_<Prefab>.c`
    assemble deux noms, et un sprite se retrouve dans plusieurs fichiers."""
    if os.name != "nt":
        return None
    names = [x.name for coll in (p.sprites, p.backgrounds, p.scenes, p.prefabs) for x in coll]
    longest = max((len(n) for n in names), default=0)
    estimate = len(str(p.build_dir)) + _BUILD_PATH_OVERHEAD + 2 * longest
    if estimate < WINDOWS_PATH_LIMIT:
        return None
    return (f"project path too long: the build writes files up to ~{estimate} "
            "characters, and the Windows tools (grit, gcc) refuse beyond "
            f"{WINDOWS_PATH_LIMIT}. Move the project to a shallower folder (e.g. "
            f"C:\\Games\\{p.settings.name}).")


class _PalKey:
    """Porteur de palette pour interroger `SceneBankLayout.bg_block_offset`.

    Celui-ci prend un asset et lit `.palettes` ; une sous-palette synthétisée par
    la fusion d'un animé avec son décor n'appartient à aucun asset (cf.
    codegen/bg_anim). L'allocation étant dédupliquée par CONTENU, ce porteur
    minimal suffit à retrouver la banque."""
    __slots__ = ("palettes", "bpp")

    def __init__(self, pal):
        self.palettes, self.bpp = [pal], 4


class BuildWorker(EventEmitter, threading.Thread):
    """
    Worker de build GBA — Python pur, sans dépendance GUI.

    Événements émis (depuis le thread de build) :
        "log_line"   (str)   — ligne de log normale
        "error_line" (str)   — ligne de contexte d'un échec (sortie d'un outil qui a échoué)
        "diagnostic" (ValidationMessage) — un avertissement ou une erreur, avec son fichier
                              et sa ligne ; c'est la SEULE forme d'un problème de build
        "finished"   (bool)  — succès/échec en fin de build, précédé du décompte

    Tout ce qui est émis est aussi copié dans `<projet>/build/build.log`, réécrit à chaque
    build : c'est le journal qu'on joint à un rapport de bug, et il survit à la fenêtre.

    La GUI est responsable de marshaller ces callbacks vers son propre
    thread principal (ex. queue + QTimer pour PyQt6).
    """

    # processus mGBA en cours (partagé entre toutes les instances)
    _mgba_proc: "subprocess.Popen | None" = None

    def __init__(self, project: Project, toolchain: Toolchain):
        EventEmitter.__init__(self)
        threading.Thread.__init__(self, daemon=True)
        self.project   = project
        self.toolchain = toolchain
        self._build_log = None
        self._counts = {"error": 0, "warning": 0}

    # ── Émission, décompte et build.log ───────────────────────────────

    def _emit(self, event: str, *args) -> None:
        """Seul point par où passe le journal : compte les diagnostics, ajoute le décompte
        devant `finished`, et copie chaque ligne dans `build.log`."""
        if event == "diagnostic":
            self._counts[args[0].level] += 1
        elif event == "finished":
            errors, warnings = self._counts["error"], self._counts["warning"]
            self._emit("error_line" if errors else "log_line",
                       f"[build] {errors} error(s), {warnings} warning(s)")
        self._write_build_log(event, args)
        super()._emit(event, *args)
        if event == "finished":
            self._close_build_log()

    def _open_build_log(self, p: Project) -> None:
        import datetime
        from core.app_info import APP_NAME, APP_VERSION
        self._counts = {"error": 0, "warning": 0}
        tc = self.toolchain
        tools = ({"make": tc.resolve_make(), "grit": tc.resolve_grit(),
                  "mmutil": tc.resolve_mmutil(), "arm-gcc": tc.resolve_arm_gcc(),
                  "mgba": tc.resolve_mgba()} if tc else {})
        try:
            p.build_dir.mkdir(parents=True, exist_ok=True)
            self._build_log = open(p.build_dir / "build.log", "w", encoding="utf-8")
        except OSError as exc:
            self._build_log = None
            self._emit("log_line", f"[build] build.log could not be written: {exc}")
            return
        header = [f"{APP_NAME} {APP_VERSION} — build log",
                  f"project: {p.settings.name} ({p.root})",
                  f"started: {datetime.datetime.now().isoformat(timespec='seconds')}",
                  "tools: " + ", ".join(f"{k}={v or 'NOT FOUND'}" for k, v in tools.items()),
                  "legend: `! ` = output of a tool that failed; [error]/[warn] = diagnostics",
                  ""]
        self._build_log.write("\n".join(header) + "\n")

    def _write_build_log(self, event: str, args: tuple) -> None:
        if self._build_log is None:
            return
        if event == "log_line":
            text = args[0]
        elif event == "error_line":
            text = "! " + args[0]
        elif event == "diagnostic":
            text = args[0].console_line()
        else:
            return
        try:
            self._build_log.write(text + "\n")
            self._build_log.flush()
        except OSError:  # tolerated: build.log is a copy of what the panel shows, the build goes on
            self._build_log = None

    def _close_build_log(self) -> None:
        if self._build_log is not None:
            self._build_log.close()
            self._build_log = None

    def run(self):
        try:
            # Ferme mGBA si encore ouvert (sinon objcopy ne peut pas écraser rom.gba)
            if BuildWorker._mgba_proc and BuildWorker._mgba_proc.poll() is None:
                BuildWorker._mgba_proc.terminate()
                try:
                    BuildWorker._mgba_proc.wait(timeout=3)
                except Exception:  # tolerated: wait() timed out: the process is killed instead
                    BuildWorker._mgba_proc.kill()
            BuildWorker._mgba_proc = None

            p = self.project
            self._open_build_log(p)

            if not p.scenes:
                self._emit("diagnostic", build_error("no scene in the project", "build"))
                self._emit("finished",False)
                return

            # ── Validation ────────────────────────────────────────
            warns, errors = validate_project(p)
            for w in warns:
                self._emit("diagnostic", w)
            for e in errors:
                self._emit("diagnostic", e)
            if errors:
                self._emit("log_line", "[build] build cancelled: the project has blocking errors.")
                self._emit("finished", False)
                return

            if too_long := path_too_long_message(p):
                self._emit("diagnostic", build_error(too_long, "build"))
                self._emit("finished", False)
                return

            self._emit("progress", 0.03)

            all_scenes = p.scenes
            scene_names = [s.name for s in all_scenes]
            self._emit("log_line", f"[build] {p.settings.name}")
            self._emit("log_line", f"[build] {len(all_scenes)} scene(s): {', '.join(scene_names)}")

            p.prepare_build()
            build_output.begin_build()
            # Le cache n'est qu'un index : les sorties restent dans build/ et
            # sont validées par leur présence avant tout réemploi.
            from codegen.asset_cache import AssetBuildCache
            asset_cache = AssetBuildCache(p.build_dir)
            # Le scan des `text.set_font` est mémoïsé pour la durée d'un build
            # seulement (cf. font_emit) : les scripts changent entre deux builds.
            from codegen.font_emit import clear_font_scan_cache
            clear_font_scan_cache()
            sound_assets = self._resolve_sound_assets(p)

            # ── Résolution par scène ───────────────────────────────
            all_scene_data: list[dict] = []
            all_bg_pairs_flat: list = []
            all_actor_sprites_flat: list = []

            for scene in all_scenes:
                # BG layers = ceux de la SCÈNE (chacun référence une image dont
                # la compression vit dans un BackgroundAsset sidecar keyé par nom).
                bg_pairs = list(getattr(scene, "background_layers", []))

                # Actors
                scene_actors: list[tuple[Actor, Optional[SpriteAsset]]] = []
                # Les sprites des apparences AUTRES que celle de `scene_actors` : ils
                # sont résidents en VRAM (marche 3, « tout résident ») sans être
                # « le » sprite de l'acteur, donc hors de `scene_actors` (dont
                # l'indice EST l'acteur) — d'où une liste à part.
                extra_sprites: list[tuple[Actor, SpriteAsset]] = []
                for actor in scene.actors:
                    if actor.active:
                        # Le sprite AFFICHÉ au départ ; à défaut d'apparence active,
                        # la première (l'entrée existe, cachée).
                        shown = displayed_sprite_component(actor)
                        sprite = p.get_sprite(shown.sprite_name) if shown else None
                        apps = owner_appearances(p, actor)
                        if sprite is None and apps:
                            sprite = apps[0][1]
                        scene_actors.append((actor, sprite))
                        extra_sprites += [(actor, sp) for _c, sp in apps if sp is not sprite]

                all_scene_data.append({
                    "scene": scene,
                    "bg_pairs": bg_pairs,
                    "scene_actors": scene_actors,
                    "extra_sprites": extra_sprites,
                })
                all_bg_pairs_flat += bg_pairs
                all_actor_sprites_flat += scene_actors + extra_sprites

            # Prefab sprites (communs à toutes les scènes)
            prefab_actor_sprites: list[tuple[Actor, Optional[SpriteAsset]]] = []
            for pf in self.project.prefabs:
                if prefab_pool_instances(self.project, pf) <= 0:
                    continue
                # Toutes les apparences de la racine sont résidentes (marche 3).
                for _c, _pf_sprite in owner_appearances(p, pf):
                    prefab_actor_sprites.append((pf, _pf_sprite))
                # Les PARTIES d'un prefab segmenté (ROADMAP v0.23) : chacune a
                # son propre sprite, qui doit être chargé en VRAM comme celui de
                # la racine. Sans ça, un bras serait émis en OAM sur des tuiles
                # qui n'ont jamais été copiées. Une partie sans sprite est un
                # marqueur : rien à charger.
                for _part in (getattr(pf, "children", []) or []):
                    for _c, _p_sprite in owner_appearances(p, _part):
                        prefab_actor_sprites.append((_part, _p_sprite))

            ok = True

            # Chaque layer de scène référence une image ; sa compression vit dans
            # un BackgroundAsset sidecar (keyé par nom). Fond compressé -> émission
            # directe (pas grit) ; sinon grit (legacy, rare car tout est compressé).
            # Dédup globale par (image, bg_slot).
            seen_bg_layers: set = set()
            unique_bg_layers: list = []
            seen_encoded: set = set()
            for d in all_scene_data:
                scene = d["scene"]
                bg_layout = scene_bank_layout(p, scene, "bg")
                for layer in d["bg_pairs"]:
                    if not layer.background_name:
                        continue
                    ba = p.get_background(layer.background_name)
                    # Fond bitmap (Mode 4) : non supporté au build (increment 2) —
                    # ignoré (sinon traité comme un fond tuilé/grit → données invalides).
                    if ba is not None and getattr(ba, "mode", "tiled") == "bitmap":
                        self._emit("log_line",
                                   f"[bg] '{ba.name}' bitmap (Mode 4) — not supported by the"
                                   " build (increment 2) → ignored")
                        continue
                    if ba and ba.tileset:
                        has_ov = bool(getattr(layer, "tile_palette_overrides", None))
                        sym = bg_layer_sym_for(scene, layer)
                        # Map PROPRE À LA SCÈNE si overrides (scène = source de
                        # vérité), sinon partagée entre scènes (dédup ROM).
                        key = (scene.name, sym) if has_ov else (ba.name, layer.bg_slot)
                        if key not in seen_encoded:
                            seen_encoded.add(key)
                            # Garde-fou 8bpp → 4bpp (transitoire) : aucun tileset
                            # 8bpp ne doit atteindre bg_emit (il serait interprété
                            # en 4bpp = corrompu).
                            build_ba = self._bg_build_asset(p, ba)
                            if build_ba is None:
                                continue   # bitmap (Mode 4) — non émis (increment 2)
                            # 8bpp = palette 256 sur TOUTE la PAL_BG_RAM : incompatible
                            # avec un 2e calque de fond dans la même scène.
                            if (getattr(build_ba, "bpp", 4) == 8
                                    and sum(1 for L in d["bg_pairs"] if L.background_name) > 1):
                                self._emit("diagnostic", build_warning(
                                    f"'{build_ba.name}' 8bpp takes the whole BG "
                                    "palette — the other background layers of "
                                    f"scene '{scene.name}' will have wrong colours", "bg"))
                            pal_offset = bg_layout.bg_block_offset(build_ba) or 0
                            final_map = self._bg_final_tilemap(
                                p, scene, build_ba, layer, pal_offset)
                            self._emit_encoded_bg(p, build_ba, sym, final_map)
                        continue
                    key = (layer.background_name, layer.bg_slot)
                    if key in seen_bg_layers:
                        continue
                    seen_bg_layers.add(key)

                    png = p.background_images_dir / (ba.asset if ba and ba.asset else f"{layer.background_name}.png")
                    colors = effective_palette_colors(
                        p, layer.pal_bank, png, scene.active_bg_palettes)
                    mp_slot = bg_layout.bank_index(layer.pal_bank, colors)
                    unique_bg_layers.append((ba, layer, colors, mp_slot))
                # Tables des animés posés — après les calques, dont elles
                # dépendent (tuiles de l'hôte pour le décalage, bloc de banques
                # pour les couleurs).
                ok = self._emit_scene_animations(p, scene, bg_layout) and ok
            if ok and unique_bg_layers:
                ok = ok and self._step_grit_bg(p, unique_bg_layers, asset_cache)
            if ok and unique_bg_layers:
                ok = ok and self._check_bg_tile_budget(p, unique_bg_layers)
            if ok:
                ok = ok and self._check_encoded_tile_budget(p)
            if ok: self._emit("progress", 0.20)

            # grit Sprites : union de toutes scènes + prefabs (dédupliqués par
            # nom — 1er rencontré gagne). Les couleurs effectives sont résolues
            # via la scène propriétaire de l'actor ; pour un prefab poolé, via
            # la 1ère scène du projet — cohérence inter-scènes vérifiée par le
            # validateur (avertissement, pas un blocage).
            seen_sprites: set[str] = set()
            unique_sprites: list = []
            for d in all_scene_data:
                scene = d["scene"]
                for actor, sprite in d["scene_actors"] + d["extra_sprites"]:
                    if sprite and sprite.asset and sprite.name not in seen_sprites:
                        seen_sprites.add(sprite.name)
                        colors = effective_palette_colors(
                            p, actor.pal_bank, p.asset_abs(sprite.asset),
                            scene.active_obj_palettes, own_pal=sprite.own_palette)
                        unique_sprites.append((actor, sprite, colors))
            anchor_scene = all_scenes[0] if all_scenes else None
            anchor_obj = anchor_scene.active_obj_palettes if anchor_scene else []
            for pf, sprite in prefab_actor_sprites:
                if sprite and sprite.asset and sprite.name not in seen_sprites:
                    seen_sprites.add(sprite.name)
                    colors = effective_palette_colors(
                        p, getattr(pf, "pal_bank", OWN_PAL_BANK), p.asset_abs(sprite.asset),
                        anchor_obj, own_pal=sprite.own_palette)
                    unique_sprites.append((pf, sprite, colors))
            # Sprites des IMAGES d'interface : ni acteur ni prefab ne les
            # porte, mais `main_gen` leur donne une base en VRAM OBJ et émet
            # leur copie de tuiles comme pour un acteur (cf.
            # `ui_image_sprites`). Sans ce passage, grit ne produit pas leur
            # `sprite_X.c/.h` et le C ne trouve pas `sprite_XTiles`. La banque
            # est celle du SPRITE (une image n'a pas de `pal_bank` propre), et
            # elle se résout sur la scène ancre comme pour un prefab.
            anchor_bg = anchor_scene.active_bg_palettes if anchor_scene else []
            ui_pools = ui_image_sprite_pools(p)
            for _, sprite in ui_image_sprites(p):
                if sprite and sprite.asset and sprite.name not in seen_sprites:
                    seen_sprites.add(sprite.name)
                    pool = ui_pools.get(sprite.name, "obj")
                    colors = effective_palette_colors(
                        p, getattr(sprite, "pal_bank", OWN_PAL_BANK),
                        p.asset_abs(sprite.asset),
                        anchor_bg if pool == "bg" else anchor_obj,
                        own_pal=sprite.own_palette)
                    unique_sprites.append((None, sprite, colors))
            if ok and unique_sprites:
                ok = ok and self._step_grit_actors(p, unique_sprites, asset_cache)
            if ok: self._emit("progress", 0.35)

            if ok and sound_assets:
                ok = ok and self._step_mmutil(p, sound_assets, asset_cache)
            if ok: self._emit("progress", 0.45)

            # Headers : tous les actors de toutes les scènes
            if ok:
                # `generate_runtime_api` a encore besoin de l'union (ANIM_* par
                # SpriteAsset) ; la taille de `g_actors` et les TAG_/POOL_, eux,
                # sont dérivés par scène de `scene_oam_layout` (ROADMAP v0.17).
                all_sa = [(a, s) for d in all_scene_data for a, s in d["scene_actors"]]
                ok = self._step_generate_actor_headers(
                    p, all_sa, sound_assets, all_scenes=all_scenes,
                )
            if ok: self._emit("progress", 0.55)

            # Collecte des events définis + écriture globals.h/c depuis project.globals
            actor_defined_events: dict[str, set[str]] = {}
            global_names: list[str] = []
            if ok:
                global_names = self._write_project_globals(p, all_scene_data, actor_defined_events)
            if ok: self._emit("progress", 0.60)

            # Écriture constants.h depuis project.constants
            const_names: list[str] = []
            if ok:
                const_names = self._write_project_constants(p)
            if ok: self._emit("progress", 0.65)

            # Tables de données — AVANT la transpilation : chaque unité d'acteur
            # inclut `data_tables.h`, il doit donc exister quand gcc y arrive.
            if ok:
                self._write_project_data_tables(p)

            # Transpilation Lua → C pour chaque scène. Les caméras sont des
            # assets PARTAGÉS (compilés une fois). Les prefabs, eux, sont
            # RECOMPILÉS par scène depuis le pool par scène (ROADMAP v0.17, T1) :
            # chaque scène émet `actor_<Scène>_<Prefab>.c` contre SA géométrie
            # (POOL_<Scène>_<Prefab>_*), donc plus de garde `compiled_prefabs`.
            compiled_cameras: set[str] = set()
            if ok:
                for d in all_scene_data:
                    if not ok:
                        break
                    ok = self._step_transpile_scripts(
                        p, d["scene"], d["scene_actors"], scene_names=scene_names,
                        precomputed_global_names=global_names,
                        precomputed_const_names=const_names,
                        compiled_cameras=compiled_cameras,
                        # Les #define SFX_*/MUSIC_* sont des rangs dans ce que
                        # mmutil a reçu, pas dans le catalogue du projet.
                        sound_assets=sound_assets,
                    )
            if ok: self._emit("progress", 0.80)

            if ok:
                ok = self._step_gen_main(
                    p, all_scene_data, sound_assets,
                    prefab_actor_sprites=prefab_actor_sprites,
                    actor_defined_events=actor_defined_events,
                )
            if ok: self._emit("progress", 0.88)
            # Le balayage remplace le rmtree que `prepare_build` faisait en tête
            # de build (ROADMAP v0.24) : ce que CE build n'a pas produit n'a plus
            # lieu d'être compilé. Il doit passer avant `make`, qui ramasse
            # `src/*.c` et `grit_out/*.c` au glob.
            if ok:
                stale = build_output.sweep((p.src_dir, p.grit_out_dir))
                for f in stale:
                    self._emit("log_line", f"[gen] stale, removed: {f.name}")
                self._emit("log_line",
                           f"[gen] {build_output.written} file(s) written, {build_output.skipped} unchanged")
                asset_cache.save()
            if ok:
                ok = self._step_make(p)
            if ok: self._emit("progress", 0.97)
            # Le rapport de poids vient APRÈS le make : il se lit sur la ROM et
            # sur l'ELF, pas sur le projet. Et avant mGBA, pour que les chiffres
            # soient la dernière chose lisible du journal.
            if ok:
                self._step_rom_report(p, sound_assets)
            if ok:
                ok = self._step_launch_mgba(p)
            if ok: self._emit("progress", 1.0)

            self._emit("finished", ok)

        except OSError as e:
            # Le système de fichiers refuse (un dossier qui est un fichier, un disque plein,
            # un droit manquant) : un cas courant, pas un bogue. On le dit comme tel, avec le
            # chemin que l'OS donne ; la trace reste dans `crash.log` pour qui la cherche.
            crash_log.log_current_exception(
                f"Build of {getattr(getattr(self, 'project', None), 'root', '?')}")
            self._emit("diagnostic", build_error(f"file system error: {e}", "build"))
            self._emit("finished", False)

        except Exception as e:
            # Une panne que personne n'a prévue : un message lisible dans le
            # journal de build, et la trace complète dans `crash.log` (là où le
            # menu Aide → « Ouvrir le dossier du journal » mène). Jamais une trace
            # Python brute devant l'utilisateur.
            crash_log.log_current_exception(
                f"Build of {getattr(getattr(self, 'project', None), 'root', '?')}")
            self._emit("diagnostic", build_error(
                f"internal error: {type(e).__name__}: {e}", "build"))
            self._emit("log_line", f"[build] details are in {crash_log.LOG_FILE} (Help → Open the log"
                                   " folder)")
            self._emit("finished", False)

    # ── Utilitaires ───────────────────────────────────────────────

    @staticmethod
    def _actor_script(actor: Actor) -> Optional[str]:
        comp = actor.get_component("script")
        return comp.script if comp and comp.active else None

    def _emit_tool_line(self, line: str, source: str, failed: bool) -> None:
        """Une ligne du stderr d'un outil, rangée par ce qu'elle DIT et non par le flux
        qui la porte : gcc écrit ses avertissements sur stderr, et une compilation réussie
        se remplissait de lignes rouges. Seul le code de retour juge de l'échec.

        - `fichier:ligne:col: error|warning:` (gcc) : un diagnostic, avec son fichier ;
        - `undefined reference` (l'éditeur de liens) : une erreur ;
        - `note:` : de l'information ;
        - le reste : du contexte, rouge si l'outil a échoué, ordinaire sinon."""
        m = _TOOL_DIAGNOSTIC.match(line)
        if m and m["kind"] in ("error", "fatal error", "warning"):
            make = build_warning if m["kind"] == "warning" else build_error
            self._emit("diagnostic", make(m["message"], source,
                                          Path(m["file"]).name, int(m["line"])))
        elif "undefined reference" in line:
            self._emit("diagnostic", build_error(line.strip(), source))
        elif failed and not (m and m["kind"] == "note"):
            self._emit("error_line", f"  {line}")
        else:
            self._emit("log_line", f"  {line}")

    def _run_cmd(self, cmd, prefix, cwd=None, env=None) -> bool:
        self._emit("log_line",f"{prefix} {' '.join(str(c) for c in cmd)}")
        try:
            # `errors="replace"` : les outils écrivent des chemins dans leur
            # page de code (accents d'un dossier de projet) ; un octet que le
            # décodeur refuse tuait le thread de lecture de `subprocess` et le
            # build perdait toute la sortie de l'outil, erreurs comprises.
            proc = subprocess.run(
                cmd, capture_output=True, text=True, errors="replace",
                cwd=str(cwd) if cwd else None, env=env
            )
            failed = proc.returncode != 0
            for line in proc.stdout.splitlines():
                self._emit("log_line", f"  {line}")
            for line in proc.stderr.splitlines():
                self._emit_tool_line(line, prefix.strip("[]"), failed)
            if failed:
                # La sortie des outils est longue ; la ligne qui dit QUELLE étape
                # a échoué, et avec quel code, ferme le bloc.
                self._emit("diagnostic", build_error(
                    f"failed (code {proc.returncode})", prefix.strip("[]")))
            return not failed
        except FileNotFoundError as e:
            self._emit("diagnostic", build_error(f"not found: {e}", prefix.strip("[]")))
            return False
        except OSError as e:
            # L'outil n'a pas pu démarrer (dossier de travail refusé, chemin trop
            # long : WinError 267…). Un message, pas une trace de « erreur
            # inattendue » (cf. `path_too_long_message` pour le cas prévisible).
            self._emit("diagnostic", build_error(f"could not start the tool: {e}",
                                                  prefix.strip("[]")))
            return False

    def _make_env(self) -> dict:
        env = os.environ.copy()
        dkp = self.toolchain.devkitpro_path or Path("C:/devkitPro")
        arm = self.toolchain.resolve_arm_gcc()
        env["DEVKITPRO"] = str(dkp).replace("\\", "/")
        env["DEVKITARM"] = str(dkp / "devkitARM").replace("\\", "/")
        extras = [
            str(dkp / "devkitARM" / "bin"),
            str(dkp / "tools" / "bin"),
            str(dkp / "msys2" / "usr" / "bin"),
        ]
        if arm:
            extras.insert(0, str(arm.parent))
        sep = ";" if os.name == "nt" else ":"
        env["PATH"] = sep.join(extras) + sep + env.get("PATH", "")
        return env

    # ── Étape 1 : grit BG ─────────────────────────────────────────

    def _step_grit_bg(self, p, layers, asset_cache=None):
        return GritBackground(
            self.toolchain.resolve_grit(), self._emit, self._run_cmd, asset_cache
        ).run(p, layers)

    def _bg_final_tilemap(self, p, scene, ba, layer, pal_offset: int) -> list:
        """SE finale par cellule du layer (pal_offset DÉJÀ appliqué) :
        - tuile PEINTE (`layer.tile_palette_overrides`) -> SE_PALBANK = banque HW de la
          banque de scène choisie (slot dans active_bg_palettes == index HW, cf.
          scene_bank_layout qui place chaque banque active à son slot). La scène
          est la source de vérité : l'asset (`ba.tilemap`) reste intact.
        - tuile normale -> pal_bank local + pal_offset (bloc de l'asset)."""
        from core.models.tile_codec import unpack_se, pack_se
        tp = getattr(layer, "tile_palette_overrides", None) or {}
        tw = ba.tiles_w or 1
        out = []
        # effective_tilemap() = baseline + overrides d'inpainting ASSET
        # (BackgroundInpainting, partagé). Les overrides de SCÈNE (`tp`) se
        # superposent par-dessus ci-dessous.
        for cell, se in enumerate(ba.effective_tilemap()):
            tid, pb, fh, fv = unpack_se(se)
            col, row = cell % tw, cell // tw
            slot = tp.get((col, row))
            # Override valide seulement si la banque de scène résout des couleurs
            # (sinon rien à afficher — on garde la palette d'origine).
            if slot is not None and 0 <= slot < 16:
                bank = resolve_palette_bank(p, scene.active_bg_palettes, slot)
                if bank and bank.colors:
                    out.append(pack_se(tid, slot, fh, fv))
                    continue
            out.append(pack_se(tid, pb + pal_offset, fh, fv))
        # Animés en mode `shared` : leur rectangle pointe sur le bloc réservé, une
        # fois pour toutes. Cuit ici et non posé à l'init parce que la carte ne
        # changera plus — au runtime il ne restera que des pixels à recopier.
        from codegen.bg_anim import bake_shared_map, host_palettes
        lay = scene_bank_layout(p, scene, "bg")
        offsets = {tuple(pal): (lay.bg_block_offset(_PalKey(pal)) or 0)
                   for pal in host_palettes(p, ba)}
        return bake_shared_map(p, ba, out, offsets)

    def _bg_build_asset(self, p, ba):
        """Filtre les fonds non émissibles au build. Un fond BITMAP (Mode 4) est
        ignoré (retourne None — support ROM = increment 2). Les fonds tuilés,
        4bpp comme 8bpp, sont émis nativement (retournés tels quels)."""
        if getattr(ba, "mode", "tiled") == "bitmap":
            self._emit("log_line",
                       f"[bg] '{ba.name}' bitmap background (Mode 4) — not supported by the "
                       "build (increment 2) → ignored")
            return None
        return ba

    def _emit_encoded_bg(self, p, ba, sym, final_tilemap):
        """Émet un fond COMPRESSÉ (métadonnées) en C compatible grit — pas de
        grit. `sym` = symbole du layer (partagé, ou propre à la scène si peint,
        cf. bg_layer_sym_for). `final_tilemap` = SE avec pal_offset + overrides
        déjà appliqués (cf. _bg_final_tilemap) — donc pal_offset=0 ici. cf.
        codegen/bg_emit.

        Le tileset émis est celui du CHARBLOCK, pas celui du seul fond : les
        tuiles des animés posés dessus le suivent (cf. codegen/bg_anim). La carte
        de l'hôte reste valable telle quelle, ses tuiles venant en premier."""
        from codegen.bg_emit import emit_bg_c
        from codegen.bg_anim import merged_tileset
        bpp = getattr(ba, "bpp", 4)
        tileset = merged_tileset(p, ba)
        c, h = emit_bg_c(sym, tileset, final_tilemap, pal_offset=0, bpp=bpp)
        p.grit_out_dir.mkdir(parents=True, exist_ok=True)
        build_output.write(p.grit_out_dir / f"{sym}.c", c)
        build_output.write(p.grit_out_dir / f"{sym}.h", h)
        extra = len(tileset) - len(ba.tileset)
        self._emit("log_line",
                   f"[bg] {ba.name} compressed ({bpp}bpp) -> {sym} ({len(tileset)} tiles"
                   + (f", including {extra} from placed animated backgrounds" if extra else "")
                   + f", {len(ba.palettes)} palettes)")

    def _emit_scene_animations(self, p, scene, bg_layout) -> bool:
        """Écrit les tables des fonds animés de la scène — entrées de carte pour
        le mode `instance`, pixels pour le mode `shared`.

        Un fichier par scène : la banque de palette d'un animé est allouée PAR
        SCÈNE, alors que le C d'un calque est partagé entre les scènes qui le
        posent — les mêler ferait imposer ses couleurs par la première scène
        compilée."""
        from codegen.bg_emit import emit_bg_anim_c, emit_bg_tileanim_c
        from codegen.bg_anim import (scene_animations, scene_anim_tables,
                                     scene_anim_sym, anim_table_sym, frame_table,
                                     shared_anim_sym, shared_table_sym,
                                     shared_frame_tiles)

        def _skip(name, why):
            self._emit("log_line",
                       f"[bg] animated '{name}' on scene '{scene.name}' — {why} → ignored")

        ok = True

        def _err(name, geom, why):
            nonlocal ok
            self._emit("diagnostic", build_error(
                f"'{name}' placed at ({geom.col}, {geom.row}) tiles on '{geom.host_name}': {why}. An animated "
                "background is MERGED with the scenery underneath — its sub-palette "
                "therefore holds the colours of both. Move the placement onto a "
                "plainer scenery, or reduce the number of colours of the animation or"
                " of the background.", "bg"))
            ok = False

        placements = scene_animations(p, scene, _skip, _err)
        p.grit_out_dir.mkdir(parents=True, exist_ok=True)

        def _bank(a) -> int:
            """Banque allouée à la sous-palette SYNTHÉTISÉE de cette fusion."""
            pal = a["block"].composed.palette
            return bg_layout.bg_block_offset(_PalKey(pal)) or 0

        # `instance` — une table par fusion distincte, pas par placement : deux
        # copies au-dessus du même décor lisent la même.
        tables = []
        for a in scene_anim_tables(p, scene, shared=False):
            tables.append((anim_table_sym(scene, a["table_index"]),
                           frame_table(a, _bank(a))))
        sym = scene_anim_sym(scene)
        c, h = emit_bg_anim_c(sym, tables)
        build_output.write(p.grit_out_dir / f"{sym}.c", c)
        build_output.write(p.grit_out_dir / f"{sym}.h", h)

        # `shared` — une table de pixels par fusion (toutes ses copies lisent le
        # même bloc, c'est la définition du mode).
        stables = []
        for a in scene_anim_tables(p, scene, shared=True):
            stables.append((shared_table_sym(scene, a["table_index"]),
                            shared_frame_tiles(a)))
        ssym = shared_anim_sym(scene)
        c, h = emit_bg_tileanim_c(ssym, stables, 4)
        build_output.write(p.grit_out_dir / f"{ssym}.c", c)
        build_output.write(p.grit_out_dir / f"{ssym}.h", h)

        if placements:
            n_sh = sum(1 for a in placements if a["shared"])
            total = sum(a["geom"].frames for a in placements)
            self._emit("log_line",
                       f"[bg] scene '{scene.name}': {len(placements)} animated background(s) placed "
                       f"({len(placements) - n_sh} per instance, {n_sh} shared), {total} images")
        return ok

    def _check_bg_tile_budget(self, p, layers) -> bool:
        """Garde-fou VRAM : un layer dont les tuiles débordent sur ce qui est
        alloué juste au-dessus (une map, le bloc du texte, un autre layer)
        écraserait silencieusement cette zone au runtime — on bloque le build
        plutôt que de laisser la corruption passer inaperçue (contrairement au
        conflit de palette OBJ/BG entre scènes, qui n'est qu'un avertissement :
        ici c'est de la mémoire écrasée, pas juste une mauvaise couleur).

        Le budget vient de l'ALLOCATEUR (codegen/vram_alloc.py), plus d'un
        plafond fixe : il dépend de ce que la scène range réellement au-dessus
        du layer, et vaut jusqu'à 1024 tuiles quand le charblock suivant est
        libre (portée d'un index de map sur 10 bits)."""
        ok = True
        budgets = self._scene_tile_budgets(p)
        for asset, layer, *_rest in layers:
            if not layer.background_name:
                continue
            png_name = asset.asset if asset and asset.asset else f"{layer.background_name}.png"
            w, h = png_size(p.background_images_dir / png_name)
            _, _, ms = bg_map_geometry(w, h)
            map_sbb_count = bg_map_sbb_count(ms)
            # Le budget le plus SERRÉ parmi les scènes qui utilisent ce layer :
            # les tuiles sont partagées, l'allocation ne l'est pas.
            tile_budget = budgets.get((asset.name, layer.bg_slot),
                                      (8 - map_sbb_count) * 64)
            sym = bg_layer_sym(asset.name, layer.bg_slot)
            header = p.grit_out_dir / f"{sym}.h"
            m = re.search(rf"{sym}TilesLen\s+(\d+)", header.read_text()) if header.exists() else None
            if not m:
                self._emit("diagnostic", build_error(
                    f"{sym}.h not found/unreadable — build cancelled", "grit"))
                ok = False
                continue
            tiles_used = int(m.group(1)) // 32
            if tiles_used > tile_budget:
                self._emit("diagnostic", build_error(
                    f"'{asset.name}' BG{layer.bg_slot}: {tiles_used} tiles generated, {tile_budget} tiles available "
                    f"from the base of charblock {layer.bg_slot} — reduce the number of unique "
                    "tiles of this layer (fewer colours/patterns), its map size, or "
                    "move another layer of this scene.", "grit"))
                ok = False
        return ok

    def _check_encoded_tile_budget(self, p) -> bool:
        """Garde-fou VRAM des fonds COMPRESSÉS — le pendant de
        `_check_bg_tile_budget`, qui ne couvre que le chemin grit (fonds legacy).

        Il manquait : rien ne bloquait un fond compressé dont les tuiles
        dépassent ce que l'allocateur lui laisse. C'était supportable tant qu'un
        calque ne portait que ses propres tuiles ; un animé posé dessus en ajoute
        sans que l'auteur les ait dessinées dans l'image, et un dépassement
        n'écrit pas un mauvais pixel — il écrase la zone du voisin, sans erreur
        avant l'exécution."""
        from codegen.bg_anim import layer_tile_count as bg_anim_tile_count
        ok = True
        budgets = self._scene_tile_budgets(p)
        seen: set[tuple] = set()
        for scene in p.scenes:
            for layer in getattr(scene, "background_layers", []):
                if not getattr(layer, "background_name", ""):
                    continue
                ba = p.get_background(layer.background_name)
                if not (ba and getattr(ba, "tileset", None)):
                    continue
                if getattr(ba, "mode", "tiled") == "bitmap":
                    continue
                key = (ba.name, layer.bg_slot)
                if key in seen:
                    continue
                seen.add(key)
                used = bg_anim_tile_count(p, ba)
                budget = budgets.get(key)
                if budget is None or used <= budget:
                    continue
                own = len(ba.tileset)
                extra = used - own
                self._emit("diagnostic", build_error(
                    f"'{ba.name}' BG{layer.bg_slot}: {used} tiles to load ({own} for the background"
                    + (f" + {extra} for the animated backgrounds placed on it" if extra else "")
                    + f"), {budget} tiles available from the base of charblock "
                      f"{layer.bg_slot} — remove a placed animation, reduce the number of unique "
                      "tiles, or move another layer of the scene.", "bg"))
                ok = False
        return ok

    def _scene_tile_budgets(self, p) -> dict:
        """{(nom du fond, bg_slot): budget en tuiles} — le MINIMUM sur toutes
        les scènes qui posent ce fond sur ce slot.

        Un même fond peut servir dans plusieurs scènes, avec des voisins
        différents donc des budgets différents. Ses tuiles, elles, sont générées
        une fois : c'est la scène la plus contrainte qui commande."""
        from codegen.vram_alloc import scene_layout
        from codegen.bg_anim import layer_tile_count as bg_anim_tile_count
        from codegen.runtime_codegen.gen_text import scene_text_reservation
        # Réservation prise au MÊME calcul que le placement réel, sinon le
        # budget validé ici n'est plus celui que la scène tient.
        out: dict = {}
        for scene in p.scenes:
            slots, maps, names = {}, {}, {}
            for layer in getattr(scene, "background_layers", []):
                if not layer.background_name:
                    continue
                ba = p.get_background(layer.background_name)
                if ba is not None and getattr(ba, "mode", "tiled") == "bitmap":
                    continue
                png = p.background_images_dir / (
                    ba.asset if ba and ba.asset else f"{layer.background_name}.png")
                w, h = png_size(png)
                _, _, ms = bg_map_geometry(w, h)
                # Nombre de tuiles inconnu ici pour un fond legacy (grit n'a pas
                # encore tourné) : on prend le pire, l'allocateur reste correct
                # — il donnera juste un budget prudent. Pour un fond compressé,
                # les animés posés dessus comptent (ils partagent le charblock).
                slots[layer.bg_slot] = (bg_anim_tile_count(p, ba)
                                        if (ba and ba.tileset) else 512)
                maps[layer.bg_slot] = bg_map_sbb_count(ms)
                names[layer.bg_slot] = layer.background_name
            if not slots:
                continue
            text_tiles = scene_text_reservation(p, scene)["total"]
            lay = scene_layout(slots, maps, p.scene_ui_bg_slot(scene), text_tiles,
                               ui_slots=p.scene_ui_bg_slots(scene))
            for slot, name in names.items():
                key = (name, slot)
                b = lay.budget[slot]
                out[key] = min(out[key], b) if key in out else b
        return out

    # ── Étape 2 : grit Actors ─────────────────────────────────────

    def _step_grit_actors(self, p, sprites, asset_cache=None):
        return GritSprites(
            self.toolchain.resolve_grit(), self._emit, self._run_cmd, asset_cache
        ).run(p, sprites)

    # ── Étape 3 : audio ───────────────────────────────────────────

    def _resolve_sound_assets(self, p):
        return resolve_sound_assets(p)

    def _step_mmutil(self, p, sound_assets, asset_cache=None):
        return MmutilAudio(
            self.toolchain.resolve_mmutil(),
            self.toolchain.resolve_bin2s(),
            self._emit, self._run_cmd, asset_cache,
        ).run(p, sound_assets)

    # ── Génération des headers C ─────────────────────────────────────

    def _step_generate_actor_headers(self, p, scene_actors, sound_assets,
                                      all_scenes=None):
        has_sound = bool(sound_assets and (sound_assets.get('sfx') or sound_assets.get('music')))
        generate_actor_types(p)
        generate_runtime_api(
            p, scene_actors, self.project.prefabs, has_sound,
            all_scenes=all_scenes,
        )
        self._emit('log_line', '[gen] actor_types.h + actor_api.h')
        return True

    # ── Globals projet + collecte des events définis ──────────────────

    def _write_project_globals(self, p, all_scene_data,
                                actor_defined_events: dict | None = None) -> list[str]:
        """
        Génère globals.h/c depuis project.globals (source de vérité explicite).
        Parse aussi les scripts pour collecter actor_defined_events (events implémentés).
        """
        from scripting.parser import parse as _parse, LuaParseError
        from scripting.globals import write_globals as _write_globals
        from codegen.c_names import sym as c_sym, scene_actor_sym

        # Écriture globals.h/c depuis la liste déclarée dans le projet
        names = _write_globals(p.src_dir, p.globals)
        if names:
            self._emit("log_line", f"[lua] globals: {', '.join('g_' + n for n in names)}")

        # Parse léger pour collecter les events définis par chaque acteur/prefab
        if actor_defined_events is None:
            return names

        from scripting.parser import sequence_name as _sequence_name

        def _collect_events(sym, sp):
            if sp and sp.exists() and sp.suffix.lower() == ".lua":
                try:
                    ast = _parse(sp.read_text(encoding="utf-8"))
                    events = {fn.name for fn in ast.functions}
                    # Une séquence avance à la fin d'`on_update` : un script qui
                    # n'en écrit pas mais déclare une séquence a quand même
                    # quelque chose à faire à chaque frame, et `main.c` ne
                    # l'appellerait pas (cf. ROADMAP v0.7.7).
                    if any(_sequence_name(n) is not None for n in events):
                        events.add("on_update")
                    actor_defined_events[sym] = events
                except LuaParseError:  # tolerated: a syntax error is reported by the script validator
                    pass

        for d in all_scene_data:
            scene = d["scene"]
            for actor, _ in d["scene_actors"]:
                comp = actor.get_component("script")
                if comp and comp.active and comp.script:
                    _collect_events(scene_actor_sym(scene.name, actor.name), p.asset_abs(comp.script))
            scene_script = getattr(scene, "script", "")
            if scene_script:
                _collect_events(c_sym(scene.name) + "_scene", p.asset_abs(scene_script))

        # Prefabs poolés : les fonctions émises sont PER-SCÈNE (`<Scène>_<Prefab>`,
        # ROADMAP v0.17, T1), donc les events se collectent sous cette même clé,
        # pour chaque scène qui déclare le prefab — c'est ce que `main_gen`
        # interroge (`_def(p2["sym"], …)`).
        from core.models.components import ScriptComponent
        for d in all_scene_data:
            scene_sym = c_sym(d["scene"].name)
            for pf in self.project.prefabs:
                if scene_pool_instances(d["scene"], pf) <= 0:
                    continue
                sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
                if sc and sc.script:
                    _collect_events(f"{scene_sym}_{c_sym(pf.name)}",
                                    p.asset_abs(sc.script))

        return names

    # ── Constants projet ────────────────────────────────────────────────

    def _write_project_constants(self, p) -> list[str]:
        """Génère constants.h depuis project.constants (source de vérité explicite)."""
        from scripting.constants import write_constants as _write_constants

        names = _write_constants(p.src_dir, p.constants)
        if names:
            self._emit("log_line", f"[lua] constants: {', '.join('CONST_' + n.upper() for n in names)}")
        return names

    # ── Tables de données projet ────────────────────────────────────────

    def _write_project_data_tables(self, p) -> list[str]:
        """Génère data_tables.h/.c depuis project.data_tables."""
        from codegen.runtime_codegen.data_tables import write_data_tables
        return write_data_tables(p.src_dir, p, self._emit)

    # ── Transpilation Lua → C ─────────────────────────────────────────

    def _step_transpile_scripts(self, p, scene, scene_actors, scene_names=None,
                                 precomputed_global_names=None, precomputed_const_names=None,
                                 compiled_cameras=None,
                                 sound_assets=None):
        return transpile_all(
            p, scene, scene_actors, self.project.prefabs, self._emit,
            scene_names=scene_names,
            precomputed_global_names=precomputed_global_names,
            precomputed_const_names=precomputed_const_names,
            compiled_cameras=compiled_cameras,
            sound_assets=sound_assets,
        )

    # ── Génération de main.c ──────────────────────────────────────────

    def _step_gen_main(self, p, all_scene_data,
                       sound_assets=None, prefab_actor_sprites=None,
                       actor_defined_events=None):
        return generate_main(
            p, all_scene_data, sound_assets,
            prefab_actor_sprites or [], self.project.prefabs, self._emit,
            actor_defined_events=actor_defined_events,
        )

    # ── Étape 4 : make ────────────────────────────────────────────

    def _step_make(self, p: Project) -> bool:
        make = self.toolchain.resolve_make()
        if not make:
            self._emit("diagnostic", build_error("not found", "make")); return False
        src = RUNTIME_DIR / "Makefile"
        if not src.exists():
            self._emit("diagnostic", build_error(f"Makefile missing: {src}", "make")); return False
        build_output.copy(src, p.makefile_path)
        # Une ROM tenue ouverte par un autre programme (un émulateur lancé hors de
        # l'éditeur) fait échouer `objcopy` avec « Permission denied » — sans dire
        # pourquoi. On le dit AVANT de compiler pour rien.
        if p.rom_path.exists():
            try:
                with open(p.rom_path, "ab"):
                    pass
            except PermissionError:
                self._emit("diagnostic", build_error(
                    f"{p.rom_path.name} is locked: opened by another program (an "
                    "emulator?) or read-only. Close it, then run the build "
                    "again.", "make"))
                return False
        env = self._make_env()
        # ROADMAP v0.14 : `debug.*` n'existe dans la ROM que build DEBUG. Le
        # define passe par l'environnement de make (EXTRA_CFLAGS, cf.
        # runtime/Makefile) plutôt que par un flag d'exécution — retiré à la
        # compilation, pas testé à chaque frame.
        if getattr(p.settings, "debug_build", True):
            env["EXTRA_CFLAGS"] = (env.get("EXTRA_CFLAGS", "") + " -DGBA_DEBUG_BUILD").strip()
        # ROADMAP v0.24 : `-j` n'est pas un réglage. Le nombre de cœurs se lit,
        # le build en profite — une case de plus à expliquer n'achèterait rien.
        # `make` était appelé sériel, et il pèse la moitié du temps de build
        # (6,1 s sur 12,3 pour Pong, mesuré le 2026-08-20) : c'est le seul
        # poste où la parallélisation change quelque chose.
        # Repli à 1 si la plateforme ne sait pas dire combien de cœurs elle a —
        # `-j` sans nombre lancerait un job par cible, sans aucune borne.
        jobs = os.cpu_count() or 1
        return self._run_cmd(
            [str(make), f"-j{jobs}"], "[make]", cwd=p.build_dir, env=env
        )

    # ── Étape 4b : ce que la ROM pèse ─────────────────────────────

    def _step_rom_report(self, p, sound_assets) -> None:
        """Affiche la répartition du poids en fin de build.

        Ne renvoie rien et n'interrompt jamais : c'est un rapport, et une ROM
        correctement construite ne doit pas échouer parce que `nm` manque. Le
        seul cas bloquant est le dépassement de capacité, et il est signalé en
        erreur sans annuler un build déjà terminé — la ROM existe, elle ne
        tient simplement pas sur la cartouche visée.
        """
        from codegen.rom_report import measure, format_report
        try:
            report = measure(
                p, self.toolchain,
                [s.name for s, _ in (sound_assets or {}).get("sfx", [])],
                [m.name for m, _ in (sound_assets or {}).get("music", [])],
                cartridge_mib=getattr(p.settings, "cartridge_mib", 4),
            )
        except Exception as e:
            self._emit("diagnostic", build_warning(f"report unavailable: {e}", "weight"))
            return
        if report is None:
            self._emit("log_line", "[weight] report unavailable (ELF or binutils "
                                   "missing)")
            return
        for line in format_report(report):
            self._emit("log_line", line)
        # Le bandeau du panneau Build (RomBudgetBar) reçoit l'objet mesuré tel
        # quel, pas les lignes de texte — le rendu graphique ne réanalyse rien.
        self._emit("rom_report", report)
        if report.over_capacity:
            self._emit("diagnostic", build_warning(
                "the ROM exceeds the declared cartridge capacity.", "weight"))

    # ── Étape 5 : mgba ────────────────────────────────────────────

    def _step_launch_mgba(self, p: Project) -> bool:
        if not p.rom_path.exists():
            self._emit("diagnostic", build_error(f"ROM missing: {p.rom_path}", "mgba"))
            return False
        mgba = self.toolchain.resolve_mgba()
        if not mgba:
            self._emit("diagnostic", build_error("not found", "mgba")); return False
        BuildWorker._mgba_proc = subprocess.Popen([str(mgba), str(p.rom_path)])
        self._emit("log_line","[mgba] launched")
        return True
