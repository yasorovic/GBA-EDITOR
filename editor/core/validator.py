"""
Validation du projet avant build.

Usage :
    from validator import validate_project
    warnings, errors = validate_project(project)

Plugins : enregistrer un validateur avec @register_validator
    from validator import register_validator, ValidationContext

    @register_validator
    def check_my_comp(ctx: ValidationContext):
        for actor in ctx.actors:
            for comp in actor.components:
                if isinstance(comp, MyComp) and comp.speed <= 0:
                    ctx.error(actor, "MyComp.speed doit être > 0")
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from core.diagnostic import (DiagnosticTarget, ValidationMessage,  # noqa: F401  (ré-exportés : API historique)
                             build_error, build_warning)
from core.models.components import sprite_components

if TYPE_CHECKING:
    from core.project import Project

_VALIDATORS: list[Callable] = []


def register_validator(fn: Callable) -> Callable:
    """Décorateur — enregistre une fonction de validation."""
    _VALIDATORS.append(fn)
    return fn


class ValidationContext:
    def __init__(self, project: "Project"):
        self.project = project
        self.scene   = project.active_scene
        self.actors  = self.scene.actors if self.scene else []
        self._msgs: list[ValidationMessage] = []
        self._focus = ""      # nom de la scène en cours de contrôle ("" hors contrôle par scène)
        self.undecodable_scripts = False   # un script n'est pas de l'UTF-8 (cf. _check_scripts_parse)
        # Les modules déjà analysés pendant CETTE validation. Trois contrôles
        # les lisent (structure de coupe, canaux du jingle, canaux du projet)
        # et un module coûte ~9 ms à analyser : sans ce cache, la démo et ses
        # 105 morceaux paient trois secondes pour trois questions.
        self._modules: dict = {}
        # Même cache que `_modules`, pour les scripts Lua analysés par
        # `_check_frame_events` — plusieurs actors peuvent partager le même
        # fichier de script, pas la peine de le reparser à chaque fois.
        self._scripts: dict = {}
        # Idem pour l'intégrité des images : un sprite cité par vingt acteurs
        # n'est vérifié qu'une fois.
        self._images: dict = {}

    def image_problem(self, path) -> Optional[str]:
        """Pourquoi l'image à ce chemin est inutilisable, ou None si elle est saine.

        `exists()` ne suffit pas : un PNG tronqué ou un fichier qui n'en est pas un
        passait la validation, puis faisait échouer le build au beau milieu de
        grit — sous forme de trace Python."""
        key = str(path)
        if key not in self._images:
            from PIL import Image
            try:
                with Image.open(path) as img:
                    img.verify()
                self._images[key] = None
            except Exception as exc:  # tolerated: stored in self._images, reported by the check that asks for it
                # Sans le chemin complet que PIL recopie : le message nomme déjà le fichier.
                self._images[key] = (f"{type(exc).__name__} : "
                                     f"{str(exc).replace(key, Path(key).name)}")
        return self._images[key]

    def module(self, path):
        """Le module lu à ce chemin, ou None s'il est illisible."""
        key = str(path)
        if key not in self._modules:
            from core.engine_emulation.module_model import load_module
            try:
                self._modules[key] = load_module(path)
            except Exception:  # tolerated: unreadable module: check_audio_file reports it
                self._modules[key] = None
        return self._modules[key]

    def script_functions(self, path) -> set:
        """Les noms de fonctions top-level déclarées dans le script Lua à ce
        chemin, ou un set vide s'il est illisible/invalide au parse — un
        script qui ne compile pas ne déclare rien de fiable, et l'échec du
        parse est déjà signalé ailleurs (`_check_lua_subset`)."""
        key = str(path)
        if key not in self._scripts:
            from scripting.parser import parse as lua_parse, LuaParseError
            try:
                script = lua_parse(path.read_text(encoding="utf-8"))
                self._scripts[key] = {fn.name for fn in script.functions}
            except (LuaParseError, OSError, UnicodeDecodeError):  # tolerated: a syntax error is reported by the script validator
                self._scripts[key] = set()
        return self._scripts[key]

    def focus(self, scene) -> None:
        """Les contrôles par scène (`ctx.scene`, `ctx.actors`) portent sur CETTE scène, et les
        messages émis ensuite la nomment. `focus(None)` revient à la scène active, sans nom."""
        self.scene = scene or self.project.active_scene
        self.actors = self.scene.actors if self.scene else []
        self._focus = scene.name if scene else ""

    def warn(self, actor_or_name, message: str, target: Optional[DiagnosticTarget] = None,
             file: str = "", line: int = 0):
        name = getattr(actor_or_name, "name", str(actor_or_name)) if actor_or_name else ""
        self._msgs.append(ValidationMessage("warning", name, message, target, source="validator",
                                            file=file, line=line, scene=self._focus))

    def error(self, actor_or_name, message: str, target: Optional[DiagnosticTarget] = None,
              file: str = "", line: int = 0):
        name = getattr(actor_or_name, "name", str(actor_or_name)) if actor_or_name else ""
        self._msgs.append(ValidationMessage("error", name, message, target, source="validator",
                                            file=file, line=line, scene=self._focus))

    @property
    def warnings(self) -> list[ValidationMessage]:
        return [m for m in self._msgs if m.level == "warning"]

    @property
    def errors(self) -> list[ValidationMessage]:
        return [m for m in self._msgs if m.level == "error"]


def validate_project(project: "Project") -> tuple[list[ValidationMessage], list[ValidationMessage]]:
    """Retourne (warnings, errors). Errors bloquent le build, warnings non."""
    # Un diagnostic est une lecture GLOBALE : il ne doit jamais conclure qu'un
    # asset est absent parce que son écran n'a pas encore été visité.
    project.load_all_resources()
    ctx = ValidationContext(project)

    # ── Validateurs built-in ─────────────────────────────────────────
    _check_unreadable_files(ctx)
    _check_translation_files(ctx)
    # Les scripts d'abord : une quinzaine de contrôles les relisent, et un fichier qui n'est
    # pas de l'UTF-8 faisait planter l'un d'eux (« internal error ») avant que ce contrôle-ci
    # puisse le dire. Dit, il suffit : les autres liraient le même fichier.
    _check_scripts_parse(ctx)
    if ctx.undecodable_scripts:
        return ctx.warnings, ctx.errors
    _check_scene(ctx)
    _check_each_scene(ctx)
    _check_prefabs(ctx)
    _check_font_sheets(ctx)
    _check_start_scene(ctx)
    # NB : pas d'avertissement quand un même sprite/prefab/layer pointant un
    # SLOT (pal_bank 0-15) résout vers des palettes différentes selon la scène.
    # C'est un comportement PRÉVISIBLE et voulu (palette-swap par slot, comme
    # le recoloring de sprites sur GB/NES) : le slot est le même partout, seul
    # le contenu du slot varie par scène. À l'utilisateur d'aligner ses
    # palettes par index en amont.
    _check_bg_text_cbb_conflict(ctx)
    _check_ui_node_slots(ctx)
    _check_ui_element_names_unique(ctx)
    _check_pal_bank_reference(ctx)
    _check_palette_bank_overflow(ctx)
    _check_api_prototypes(ctx)
    _check_api_domains(ctx)
    _check_lua_subset(ctx)
    _check_markup_fonts(ctx)
    _check_text_overflow(ctx)
    _check_font_coverage(ctx)
    _check_literal_texts(ctx)
    _check_translation_holes(ctx)
    _check_ui_text_key(ctx)
    _check_ui_image(ctx)
    _check_blend(ctx)
    _check_ui_container_fill(ctx)
    _check_scene_font(ctx)
    _check_cameras(ctx)
    _check_script_owner_families(ctx)
    _check_behaviors_without_self(ctx)
    _check_window_regions(ctx)
    _check_actor_name_collisions(ctx)
    _check_actor_budget(ctx)
    _check_data_column_types(ctx)
    _check_data_tables(ctx)
    _check_screen_space(ctx)
    _check_audio_files(ctx)
    _check_music_cut_compat(ctx)
    _check_jingle_channels(ctx)
    _check_module_channels(ctx)
    _check_sound_boxes(ctx)
    _check_sprite_appearances(ctx)

    # ── Validateurs plugins ──────────────────────────────────────────
    for fn in _VALIDATORS:
        try:
            fn(ctx)
        except Exception as exc:
            ctx.warn(None, f"Validator '{fn.__name__}' crashed: {exc}")

    return ctx.warnings, ctx.errors


# ── Validateurs built-in ──────────────────────────────────────────────

def _check_api_domains(ctx: ValidationContext):
    """Un domaine d'argument doit être connu de SES DEUX consommateurs.

    Le `domain` d'un `Param` (`scripting/api.py`) dit qu'un argument cite un
    élément nommé du projet. Trois modules en dépendent — `refactor` (suivre
    les renommages), `checker` (le nom existe-t-il ?), `codegen` (quelle
    constante C émettre ?). Le premier DÉRIVE sa table du catalogue et n'a rien
    à oublier ; les deux autres portaient une liste écrite à la main, et un
    domaine absent n'y produisait aucun signal : le checker ne validait
    simplement rien, et le codegen retombait sur « émettre la chaîne telle
    quelle », donc du texte C là où le C attend un entier — panne au `make`,
    sur la ligne générée, jamais sur la cause.

    Même famille que `_check_api_prototypes` ci-dessous, même remède : les
    listes sont comparées ici, en ERREUR bloquante, plutôt que découvertes par
    la chaîne C. Placer un nouveau domaine dans l'une des cases (validé par
    domaine, validé par appel, non validé — et pourquoi) fait partie de son
    ajout, ce n'est pas une formalité.
    """
    from scripting.api import ALL_DOMAINS
    from scripting import checker, codegen

    for role, couverts in (("checker", checker.covered_domains()),
                           ("codegen", codegen.covered_domains())):
        manquants = sorted(ALL_DOMAINS - couverts)
        if manquants:
            ctx.error(None,
                      f"Unknown argument domain(s) for {role}: {', '.join(manquants)}. Add an entry in the "
                      f"matching table (scripting/{role}.py) — without it, a name cited "
                      "in this domain is neither checked nor resolved.")
        # Un domaine listé mais qui n'existe plus est l'autre sens de la même
        # dérive : la table garde une entrée morte que rien ne peut plus
        # atteindre. Avertissement — ça ne casse pas le build.
        fantomes = sorted(couverts - ALL_DOMAINS)
        if fantomes:
            ctx.warn(None,
                     f"{role}: domain(s) declared but missing from api.py: "
                     f"{', '.join(fantomes)}.")


def _check_lua_subset(ctx: ValidationContext):
    """Tout nœud de luaparser doit être CLASSÉ — traduit, refusé, ou structurel.

    Même famille que `_check_api_domains` ci-dessus, et le même défaut réel à
    l'origine : `parser.py` rendait `None` pour tout statement non géré et
    `ExprName("__unsupported_<Type>")` pour toute expression non gérée. Un
    `repeat` ou un `for … in` disparaissait donc du jeu sans un mot, et un `..`
    n'échouait qu'au `make`. La liste des nœuds traités n'était écrite nulle
    part : elle se lisait dans un `match`, et rien ne pouvait la comparer à ce
    que luaparser sait produire.

    Ce contrôle la compare. Une mise à jour de luaparser qui ajoute un nœud
    casse le build ici, avec le nom du nœud à classer, plutôt que de rouvrir le
    trou silencieux qu'on vient de boucher.

    L'univers est DÉRIVÉ du module de luaparser (les sous-classes concrètes
    d'`Expression` — dont héritent aussi les statements) : rien à énumérer à la
    main, donc rien qui périme."""
    import inspect
    from scripting import lua_subset

    try:
        from luaparser import astnodes
    except ImportError:
        ctx.warn(None, "luaparser is missing — the Lua subset is not checked.")
        return

    # Les classes ABSTRAITES du module : elles ne sont jamais instanciées dans
    # un arbre, seulement héritées. Les nommer est le seul geste manuel ici.
    abstraites = {"Expression", "Statement", "Op", "BinaryOp", "AriOp",
                  "BitOp", "RelOp", "LoOp", "UnaryOp", "Lhs"}
    univers = frozenset(
        name for name, cls in vars(astnodes).items()
        if inspect.isclass(cls) and issubclass(cls, astnodes.Expression)
        and name not in abstraites
    )
    couverts = lua_subset.covered_nodes()

    manquants = sorted(univers - couverts)
    if manquants:
        ctx.error(None,
                  "Lua node(s) not classified in scripting/lua_subset.py: "
                  f"{', '.join(manquants)}. Each must join ACCEPTED (it is translated), REFUSED (with the"
                  " sentence saying what to write instead) or STRUCTURAL (never "
                  "dispatched) — otherwise it falls back into silence.")
    # L'autre sens : une entrée que luaparser ne produit plus. Avertissement,
    # comme pour les domaines fantômes — ça ne casse rien, ça encombre.
    fantomes = sorted(couverts - univers)
    if fantomes:
        ctx.warn(None,
                 "lua_subset.py classifies nodes that do not exist in luaparser: "
                 f"{', '.join(fantomes)}.")


def _check_api_prototypes(ctx: ValidationContext):
    """Ce que l'API exposée exige des en-têtes du runtime, HORS prototypes.

    Les prototypes ne sont plus surveillés : ils sont désormais GÉNÉRÉS dans
    `runtime_api.h` à partir de `gba_engine.h`, pour le seul sous-ensemble exposé
    par le catalogue (cf. codegen/runtime_codegen/api_prototypes — le « 4e
    lecteur »). Une fonction exposée ne peut donc plus manquer de déclaration : la
    surveillance « présent dans le moteur, absent de la façade » n'a plus d'objet.

    Restent deux contrôles que la génération ne couvre pas :
      - l'ACCORD de VALEUR des énums entre `api.py` (leur source, désormais) et
        `gba_engine.h` (qui en redéfinit certaines à la main côté moteur) ;
      - l'ORDRE des arguments entre `api.py` et `gba_engine.h` : une permutation
        (mêmes noms, autre ordre) compile proprement — tout est `int` — et range
        chaque valeur dans le mauvais paramètre. Le seul désaccord de la chaîne
        qui n'échoue ni au checker ni au compilateur."""
    import re
    from core.app_paths import RUNTIME_DIR
    from scripting.api import RUNTIME_API

    engine = RUNTIME_DIR / "include" / "gba_engine.h"
    facade = RUNTIME_DIR / "include" / "runtime_api_inline.h"
    if not (engine.exists() and facade.exists()):
        ctx.warn(None, "Runtime headers not found — API not checked.")
        return
    eng = engine.read_text(encoding="utf-8", errors="ignore")
    fac = facade.read_text(encoding="utf-8", errors="ignore")

    # ── Les CONSTANTES d'énum : leur VALEUR doit s'accorder avec le moteur ──
    # Les `#define` d'énums sont désormais GÉNÉRÉS depuis `api.py`
    # (`build_enum_defines`), donc leur existence côté script n'est plus en
    # question. Reste un accord que rien ne garantissait : certaines (`BLD_MODE_*`,
    # `BLD_SIDE_*`) sont AUSSI définies à la main dans `gba_engine.h`, côté moteur.
    # Si les deux valeurs divergeaient, le codegen émettrait le symbole, les
    # scripts verraient la valeur d'api.py et `main.c` celle du moteur — un
    # décalage silencieux. On vérifie donc l'accord de VALEUR, pour les seules
    # constantes présentes des deux côtés (les autres n'ont qu'une source, api.py).
    from scripting.api import hardware_enum_defines

    def engine_value(name: str):
        m = re.search(r"^\s*#\s*define\s+" + re.escape(name) + r"\s+(-?\d+)\b", eng, re.M)
        return int(m.group(1)) if m else None

    mismatched = []
    for sym, value in hardware_enum_defines():
        ev = engine_value(sym)
        if ev is not None and ev != value:
            mismatched.append(f"{sym} (api.py={value}, gba_engine.h={ev})")
    if mismatched:
        ctx.error(None,
                  "Inconsistent enumeration values between api.py and gba_engine.h: "
                  f"{', '.join(mismatched)}. The emitted symbol would mean two different things depending "
                  "on the unit — a silent shift.")

    # ── Ordre des arguments : Lua ↔ C ─────────────────────────────
    # `codegen._emit_api_call` mappe les arguments par POSITION. Si l'ordre des
    # `params` d'api.py et celui du prototype C divergent, chaque valeur atterrit
    # dans le mauvais paramètre — et comme ils sont tous `int`, le compilateur ne
    # peut RIEN dire. C'est le seul désaccord de cette chaîne qui compile
    # proprement et rend faux à l'exécution.
    #
    # On ne signale que les PERMUTATIONS (mêmes noms, autre ordre). Un simple
    # renommage — `layer.show(n, on)` en Lua contre `layer_show(bg, on)` en C, où
    # « n » parle d'un numéro de layer côté script — est délibéré et sans effet.
    def c_params(fn: str) -> list[str] | None:
        m = re.search(r"^\s*(?:void|int)\s+" + re.escape(fn) + r"\s*\(([^)]*)\)\s*;",
                      eng, re.M)
        if not m:
            return None
        a = m.group(1).strip()
        if a in ("", "void"):
            return []
        return [p.strip().split()[-1].lstrip("*") for p in a.split(",")]

    permuted = []
    for key, f in RUNTIME_API.items():
        cp = c_params(f.c_func) if f.c_func else None
        if cp is None:
            continue
        lua = [p.name for p in f.params]
        if lua != cp and sorted(lua) == sorted(cp):
            permuted.append(f"{key} : Lua ({', '.join(lua)}) vs C ({', '.join(cp)})")
    if permuted:
        ctx.error(None,
                  "Inconsistent argument order between api.py and gba_engine.h — "
                  "values would land in the wrong parameter without the compiler "
                  f"being able to see it: {' ; '.join(permuted)}.")


def _check_scene(ctx: ValidationContext):
    if not ctx.scene:
        ctx.error(None, "No active scene — cannot build.")


def _check_each_scene(ctx: ValidationContext):
    """Les contrôles qui lisent une scène (ses acteurs, ses fonds, les événements de frame de
    leurs scripts) tournent pour CHAQUE scène : le build les compile toutes, et ne contrôler que
    la scène ouverte laissait passer, en silence, un script supprimé ou un sprite illisible dans
    une autre. Le message nomme la scène."""
    for scene in ctx.project.scenes:
        ctx.focus(scene)
        # Une scène d'interface (écran titre, victoire) n'a souvent aucun acteur : valide, pas un
        # avertissement. Elle ne fait « rien » seulement sans acteur, sans script et sans interface.
        if not (scene.actors or getattr(scene, "script", "") or getattr(scene, "ui_layouts", None)):
            ctx.warn(None, "The scene has no actor, script or interface: it will do nothing.")
        _check_actors(ctx)
        _check_backgrounds(ctx)
        _check_frame_events(ctx)
    ctx.focus(None)


def _check_font_sheets(ctx: ValidationContext):
    """Le fichier source d'une police doit exister, et une planche PNG doit se lire.

    Un fichier DISPARU est un avertissement : l'utilisateur a pu le retirer lui-même, et le
    build sait s'en passer — la police n'est pas compilée et les scènes retombent sur une autre
    (cf. `_check_scene_font`). Une planche ILLISIBLE reste une erreur : le fichier est là, mais
    la police serait émise sans glyphe."""
    p = ctx.project
    for font in getattr(p, "fonts", []):
        sheet = getattr(font, "asset", None)
        if not sheet:
            continue
        path = p.asset_abs(sheet)
        name = Path(sheet).name
        if not path or not path.exists():
            ctx.warn(None, f"Font \"{font.name}\": file {name} not found — the font is left out "
                           "of the build.")
        elif Path(sheet).suffix.lower() != ".png" or font.source_format != "png":
            continue    # .ttf / .otf / .fnt : pas une image, la rastérisation les lit à sa manière
        elif reason := ctx.image_problem(path):
            ctx.error(None, f"Font \"{font.name}\": sheet {name} is unreadable ({reason}) — "
                            "re-export the PNG.")


def _check_start_scene(ctx: ValidationContext):
    """La scène sur laquelle démarre le jeu doit exister : sinon `main_gen` retombe, sans un mot,
    sur la première scène."""
    p = ctx.project
    start = getattr(p.settings, "start_scene", "")
    names = [scene.name for scene in p.scenes]
    if start and names and start not in names:
        ctx.warn(None, f"The start scene \"{start}\" does not exist — the game will start on "
                       f"\"{names[0]}\".")


def _check_prefabs(ctx: ValidationContext):
    """Un prefab a les composants d'un acteur et se compile comme lui : mêmes contrôles. Sans
    cela, le PNG d'un sprite que seul un prefab cite n'était vu par personne."""
    for prefab in ctx.project.prefabs:
        _check_components(ctx, prefab, prefab.components)


def _check_actors(ctx: ValidationContext):
    for actor in ctx.actors:
        _check_components(ctx, actor, actor.components)


def _check_components(ctx: ValidationContext, owner, components):
    from core.models.components import component_type_name

    for comp in components:
        try:
            ctype = component_type_name(comp)
        except ValueError:
            ctx.warn(owner, "Unsupported component type ignored: "
                            f"{type(comp).__name__}")
            continue

        if ctype == "sprite":
            _check_sprite(ctx, owner, comp)
        elif ctype == "collision_box":
            _check_collision(ctx, owner, comp)
        elif ctype == "script":
            _check_script(ctx, owner, comp)


def _check_sprite(ctx, actor, comp):
    proj   = ctx.project
    sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None

    if not comp.sprite_name:
        ctx.warn(actor, "SpriteComponent without a linked SpriteAsset (no "
                        "sprite_name).")
        return
    if not sprite:
        # Le composant CITE un sprite qui n'existe plus (fichier retiré, sans doute
        # par l'utilisateur) : l'acteur se joue sans image — mais il le faut dire.
        ctx.warn(actor, f"Sprite '{comp.sprite_name}' not found — the actor names it but no "
                        "SpriteAsset has this name; it is played without a sprite.")
        return
    if not sprite.asset:
        ctx.warn(actor, f"Sprite '{sprite.name}' has no PNG assigned.")
        return
    ap = proj.asset_abs(sprite.asset)
    if not ap or not ap.exists():
        ctx.warn(actor, f"Sprite '{sprite.name}': PNG file not found ({sprite.asset}); the actor "
                        "is played without a sprite.")
    elif reason := ctx.image_problem(ap):
        ctx.error(actor, f"Sprite '{sprite.name}': image {sprite.asset} is unreadable ({reason}) — re-export the"
                         " PNG.")
    if sprite.frame_w <= 0 or sprite.frame_h <= 0:
        ctx.error(actor, f"Sprite '{sprite.name}' : invalid frame_w/h ({sprite.frame_w}×{sprite.frame_h}).")


def _check_collision(ctx, actor, comp):
    if getattr(comp, "w", 0) <= 0 or getattr(comp, "h", 0) <= 0:
        ctx.error(actor,
                  f"CollisionBox '{comp.tag}': zero width or height ({comp.w}×{comp.h}) — invisible "
                  "hitbox.")


def _check_script(ctx, actor, comp):
    proj = ctx.project
    if not comp.script:
        ctx.warn(actor, "ScriptComponent without an assigned script.")
        return
    sp = proj.asset_abs(comp.script)
    if not sp or not sp.exists():
        ctx.error(actor, f"Script not found: {comp.script}")


def _check_translation_files(ctx: ValidationContext):
    """Un fichier de traduction illisible laisse la langue sans un mot traduit : le jeu retombe sur
    la langue source. Le projet s'ouvre quand même (règle du repli), mais la perte se dit."""
    p = ctx.project
    for code, reason in getattr(p, "translation_problems", {}).items():
        ctx.warn(None, f"Translation file \"{p.translation_file(code).name}\" is unreadable "
                       f"({reason}) — language \"{code}\" falls back to the source language.")


def _check_unreadable_files(ctx: ValidationContext):
    """Un fichier de projet illisible est ABSENT du build : l'asset qu'il décrit
    n'existe ni pour l'écran ni pour la ROM. En ERREUR, comme un fichier audio
    introuvable — sinon le jeu sortirait amputé sans qu'un mot ne le dise (cf.
    `ResourceStore.unreadable`). Le fichier n'est jamais modifié."""
    for name, reason in ctx.project.unreadable_files():
        ctx.error(None, f"File \"{name}\" is unreadable ({reason}) — the asset it describes is "
                        "missing from the build; repair the file or delete it.")
    for name, backup in ctx.project.preserved_files():
        ctx.warn(None, f"File \"{name}\": the original was unreadable and has been replaced"
                       f" by a default version; it is kept in \"{backup}\".")


def _check_backgrounds(ctx: ValidationContext):
    proj = ctx.project
    if not ctx.scene:
        return

    for layer in ctx.scene.background_layers:
        if not layer.background_name:
            continue
        ba = proj.get_background(layer.background_name)
        if not ba:
            ctx.warn(None, f"Background BG{layer.bg_slot}: image '{layer.background_name}' not found — layer ignored.")
            continue
        png = ba.asset if ba.asset else f"{layer.background_name}.png"
        if not (proj.background_images_dir / png).exists():
            ctx.warn(None, f"Background BG{layer.bg_slot}: PNG not found ({png}) — layer ignored.")
        elif reason := ctx.image_problem(proj.background_images_dir / png):
            ctx.error(None, f"Background BG{layer.bg_slot}: image {png} is unreadable ({reason}) — "
                            "re-export the PNG.")


def _check_bg_text_cbb_conflict(ctx: ValidationContext):
    """`scene_init` configure le BGxCNT de CHAQUE slot d'UI (v0.12) et y loge la
    police : le slot d'une interface est donc censé ne porter AUCUN décor. Si un
    vrai layer BG occupe ce même slot, ses tuiles ET son registre BGxCNT sont
    écrasés au build — corruption garantie (même sévérité que _check_bg_tile_
    budget), donc bloquant. Vaut pour tous les slots d'UI, pas le seul primaire."""
    p = ctx.project
    for scene in p.scenes:
        ui_slots = {s for s in p.scene_ui_bg_slots(scene) if s in (0, 1, 2, 3)}
        for layer in scene.background_layers:
            if layer.background_name and layer.bg_slot in ui_slots:
                ctx.error(None,
                    f"Scene '{scene.name}': layer BG{layer.bg_slot} ('{layer.background_name}') shares its slot with an "
                    f"interface (BG{layer.bg_slot}) — its charblock is overwritten by the font "
                    "tiles at build. Change the interface's BG slot or empty this "
                    "layer's image.")


def _check_ui_node_slots(ctx: ValidationContext):
    """Slots BG des nœuds `Interface` (v0.12).

    • Un nœud rendu en Background doit viser un slot que le MODE VIDÉO expose
      (mode 1 n'a pas de BG3, les bitmaps n'ont que BG2…) — sinon rien ne
      s'affiche au bon endroit.
    • Un même layout ne peut être posé DEUX fois dans une scène : ses éléments
      porteraient les mêmes noms, or `REGION_*`/`IMAGE_*` sont indexés par nom
      unique au projet — collision d'ABI (cf. ROADMAP v0.12)."""
    from core.models.scene import BG_SLOTS_BY_MODE
    from core.models.ui_region import TARGET_BG
    p = ctx.project
    for scene in p.scenes:
        rm = int(getattr(scene, "render_mode", 0) or 0)
        valid = BG_SLOTS_BY_MODE.get(rm, BG_SLOTS_BY_MODE[0])
        seen: set[str] = set()
        for node in p.scene_ui_layouts(scene):
            name = node.layout_name
            if name in seen:
                ctx.error(None,
                    f"Scene '{scene.name}': interface '{name}' is placed twice — its elements "
                    "would share the same names (REGION_*/IMAGE_*). A layout can only"
                    " be placed once per scene.")
            seen.add(name)
            if node.resolved_target(None, rm) == TARGET_BG and node.bg_slot not in valid:
                ctx.error(None,
                    f"Scene '{scene.name}': interface '{name}' targets slot BG{node.bg_slot}, which is "
                    f"unavailable in video mode {rm} (allowed slots: {list(valid)}). Choose a "
                    "valid slot in the node inspector.")


def _check_ui_element_names_unique(ctx: ValidationContext):
    """Un nom d'élément d'interface est UNIQUE dans tout le projet.

    `REGION_*`, `IMAGE_*` et `UIELEM_*` sont indexés par NOM, pour l'ensemble des
    mises en page (cf. `Project.ui_element_names`) : deux éléments homonymes, même
    dans deux layouts posés sur deux scènes différentes, émettent la même macro avec
    deux valeurs. Le compilateur n'en dit qu'un avertissement, et la dernière
    définition gagne — `interface:get("nom")` vise alors l'élément de l'AUTRE
    interface. Le contrôle ci-dessus ne voit que le cas « un layout posé deux fois
    dans une scène » ; celui-ci voit les homonymes entre layouts différents."""
    owners: dict[str, list[str]] = {}
    for layout, element in ctx.project.all_elements():
        if element.name:
            owners.setdefault(element.name, []).append(layout.name)
    for name, layouts in sorted(owners.items()):
        if len(layouts) > 1:
            where = ", ".join(f"'{lay}'" for lay in sorted(set(layouts)))
            ctx.error(None,
                f"Interface element \"{name}\" duplicated ({where}): its REGION_/IMAGE_/UIELEM_"
                " constants collide and a script would target the wrong element. "
                "Rename one of them: the name is unique across the whole project.")


def _text_variants(p, text, globals_names: set) -> list:
    """[(étiquette de langue, source, ParsedText)] à mesurer pour une entrée.

    **La source seule ne suffit plus dès qu'une langue est déclarée**
    (ROADMAP v0.9) : une traduction plus longue déborde une zone que la
    source remplissait tout juste, et rien ne le dirait avant la ROM en jeu.
    Une langue non encore traduite montre la source — la revérifier
    produirait le même avertissement une seconde fois, donc elle est exclue
    par le test d'égalité de contenu, pas par un `if` sur `auto_key` ou autre
    état qui pourrait diverger de ce que `text_content()` rend réellement."""
    from core.text_markup import parse, KIND_VALUE
    source = text.content or ""
    out = [("", source, parse(source))]
    seen = {text.content or ""}
    for lang in getattr(p.settings, "languages", []):
        raw = p.translations.get(lang.code, {}).get(text.id, "")
        if not raw or raw in seen:
            continue
        seen.add(raw)
        out.append((lang.code, raw, parse(raw)))
    # Un `$global` a une largeur qui ne se connaît qu'en jeu, quelle que soit
    # la langue — même filtre qu'avant, appliqué à chaque variante.
    return [(lbl, source, parsed) for lbl, source, parsed in out
            if not any(m.kind == KIND_VALUE and m.value in globals_names
                      for m in parsed.markers)]


def _check_markup_fonts(ctx: ValidationContext):
    """Une portée ``[font=nom]`` doit viser une police réellement disponible.

    Le parseur valide la forme de la balise ; lui seul ne connaît pas le projet.
    Sans ce contrôle, l'encodeur ne pourrait pas convertir le nom en index de
    ``g_fonts`` et l'erreur apparaîtrait trop tard, dans le C généré.
    """
    p = ctx.project
    from core.text_markup import parse
    from codegen.font_emit import encodable_project_fonts
    known = {font.name for font in (encodable_project_fonts(p) or list(getattr(p, "fonts", [])))}
    seen: set[tuple[str, str, str]] = set()
    for text in getattr(p, "texts", []):
        variants = [("", getattr(text, "content", "") or "")]
        for lang in getattr(getattr(p, "settings", None), "languages", []):
            content = getattr(p, "translations", {}).get(lang.code, {}).get(text.id, "")
            if content:
                variants.append((lang.code, content))
        for code, content in variants:
            for marker in parse(content).of_kind("font"):
                name = str(marker.value)
                key = (text.key, code, name)
                if name not in known and key not in seen:
                    seen.add(key)
                    ctx.error(None,
                        f"Text '{text.key}'"
                        + (f" (language \"{code}\")" if code else "")
                        + f" cites the unknown font '{name}' in [font={name}].")


def _check_text_overflow(ctx: ValidationContext):
    """Un texte qui ne tient pas dans sa zone est TRONQUÉ au dernier glyphe qui
    tient (cf. runtime `text_glyph_fits`), sans un mot en jeu.

    Ne juge que le DÉCIDABLE : la paire (zone, clé) doit être littérale dans le
    script — repérage par DOMAINE (`iter_call_sites`), donc toute future
    primitive « zone + contenu » est couverte sans rien déclarer — et le texte
    ne doit citer aucun global, `$score` faisant 1 ou 3 caractères selon la
    partie. Une constante, cuite au build, reste mesurable après substitution.
    Le reste appartient à la coupe au runtime : avertir sur une supposition
    apprendrait à ignorer les avertissements.

    Mesuré contre TOUTES les langues traduites, pas seulement la source —
    cf. `_text_variants`."""
    p = ctx.project
    if not getattr(p, "texts", None) or not getattr(p, "fonts", None):
        return
    from scripting.refactor import find_call_sites_in_project
    from scripting.api import DOMAIN_UI_ELEMENT, DOMAIN_TEXT
    from core.text_markup import parse, resolve, KIND_VALUE
    from core.engine_emulation.text_layout import layout_marked_text

    regions = {r.name: r for _lay, r in p.all_regions()}
    from codegen.font_emit import encodable_project_fonts
    built_fonts = encodable_project_fonts(p) or list(p.fonts)
    fonts   = {f.name: f for f in built_fonts}
    globals_names = {g.name for g in getattr(p, "globals", [])}
    consts = {c.name: c.value for c in getattr(p, "constants", [])}

    # Une zone qui ne nomme pas sa police prend celle de la scène (cf.
    # font_emit.scene_default_font). Or une mise en page est PARTAGÉE : deux
    # scènes peuvent l'afficher avec deux polices par défaut différentes, donc
    # deux largeurs. On mesure contre chacune plutôt que d'en élire une —
    # choisir, ici, ce serait taire un débordement réel dans l'autre scène.
    from codegen.font_emit import scene_default_font
    first = built_fonts[0] if built_fonts else None
    lay_defaults: dict[str, list] = {}
    for _scene in p.scenes:
        _f = fonts.get(scene_default_font(p, _scene)[1]) or first
        # La police par défaut de la scène s'applique à CHACUN de ses nœuds
        # `Interface` (v0.25 : une scène en référence plusieurs).
        for _node in (getattr(_scene, "ui_layouts", []) or []):
            _seen_f = lay_defaults.setdefault(_node.layout_name, [])
            if not any(x is _f for x in _seen_f):
                _seen_f.append(_f)
    region_layout = {r.name: lay.name for lay, r in p.all_regions()}

    def _fonts_for(el) -> list:
        """Polices contre lesquelles mesurer `el` : la sienne si elle est
        nommée, sinon tous les défauts de scène qui peuvent lui échoir."""
        if getattr(el, "font_name", "") in fonts:
            return [fonts[el.font_name]]
        return lay_defaults.get(region_layout.get(el.name, ""), None) or ([first] if first else [])

    seen: set = set()
    for site in find_call_sites_in_project(p, DOMAIN_UI_ELEMENT, DOMAIN_TEXT):
        region = regions.get(site.values[DOMAIN_UI_ELEMENT])
        text   = p.get_text(site.values[DOMAIN_TEXT])
        if region is None or text is None:
            continue          # le checker le dit déjà, et mieux
        for lbl, source, _parsed in _text_variants(p, text, globals_names):
            for font in _fonts_for(region):
                # La police ET la langue entrent dans la clé de dédup : la
                # même paire mesurée contre deux défauts de scène — ou deux
                # traductions — donne deux verdicts distincts.
                quad = (region.name, text.key, font.name, lbl)
                if quad in seen:
                    continue   # la même paire dans dix scripts, un seul message
                seen.add(quad)
                _placed, over = layout_marked_text(
                    font, source, fonts, consts, region.w, region.h)
                if over:
                    ctx.warn(None,
                        f"Text '{text.key}'"
                        + (f" (language \"{lbl}\")" if lbl else "")
                        + f" overflows the zone '{region.name}' ({region.w}×{region.h} px, font '{font.name}') — it "
                          "will be cut at the last glyph that fits. Enlarge the zone,"
                          " shorten the text, or split it into two entries.")

    # Textes AUTHORÉS : le couple (élément, contenu) est connu sans lire un
    # script, et plus sûr que le cas script — c'est `scene_init` qui l'écrit,
    # rien ne peut changer le texte avant l'affichage.
    from core.models.ui_region import KIND_TEXT
    for _lay, el in p.all_regions():
        if getattr(el, "kind", "") != KIND_TEXT:
            continue
        text = p.get_text(getattr(el, "text_key", "") or "")
        if text is None:
            continue          # clé vide ou cassée : _check_ui_text_key le dit
        for lbl, source, _parsed in _text_variants(p, text, globals_names):
            for font in _fonts_for(el):
                _placed, over = layout_marked_text(
                    font, source, fonts, consts, el.w, el.h)
                if over:
                    ctx.warn(None,
                        f"Text '{text.key}'"
                        + (f" (language \"{lbl}\")" if lbl else "")
                        + f" overflows the element '{el.name}' ({el.w}×{el.h} px, font "
                          f"'{font.name}') — it will be cut at the last glyph that fits. "
                          "Enlarge the element in the canvas, or shorten the text.")


def _check_font_coverage(ctx: ValidationContext):
    """Un texte qui cite un caractère ABSENT de sa police est sauté en
    silence à l'affichage (`text_glyph_slot` rend -1, cf. gba_engine.h) — le
    pendant `_check_text_overflow` côté GLYPHE plutôt que côté LARGEUR de
    zone. Bug réel rencontré en jouant la démo Fonts&Texts : une traduction
    japonaise citait un kanji (友) absent des 3831 glyphes de la police du
    projet, invisible jusqu'à ce que quelqu'un joue la ROM dans cette
    langue-là.

    La police jugée est l'EFFECTIVE, pas la déclarée : une langue peut remplacer
    la Default Font du projet. Les FontAsset explicitement nommées ne reçoivent
    pas de repli global ; leur chaîne de sources porte leur couverture.

    Même reprise que `_check_text_overflow` : DEUX sources (script + textes
    authorés), TOUTES les langues déclarées (`_text_variants`), dédupliqué
    par (zone, clé, police EFFECTIVE, langue)."""
    p = ctx.project
    if not getattr(p, "texts", None) or not getattr(p, "fonts", None):
        return
    from scripting.refactor import find_call_sites_in_project
    from scripting.api import DOMAIN_UI_ELEMENT, DOMAIN_TEXT
    from core.text_markup import KIND_VALUE, SENTINEL

    regions = {r.name: r for _lay, r in p.all_regions()}
    from codegen.font_emit import encodable_project_fonts
    built_fonts = encodable_project_fonts(p) or list(p.fonts)
    fonts   = {f.name: f for f in built_fonts}
    globals_names = {g.name for g in getattr(p, "globals", [])}
    consts = {c.name: c.value for c in getattr(p, "constants", [])}
    lang_by_code = {l.code: l for l in getattr(p.settings, "languages", [])}
    # Un jeu de caractères par police, calculé une fois — relire les glyphes
    # à chaque texte serait quadratique sur un projet qui en a beaucoup.
    coverage = {f.name: {g.char for g in f.glyphs if g.char} for f in built_fonts}

    from codegen.font_emit import scene_default_font
    first = built_fonts[0] if built_fonts else None
    lay_defaults: dict[str, list] = {}
    for _scene in p.scenes:
        _f = fonts.get(scene_default_font(p, _scene)[1]) or first
        # La police par défaut de la scène s'applique à CHACUN de ses nœuds
        # `Interface` (v0.25 : une scène en référence plusieurs).
        for _node in (getattr(_scene, "ui_layouts", []) or []):
            _seen_f = lay_defaults.setdefault(_node.layout_name, [])
            if not any(x is _f for x in _seen_f):
                _seen_f.append(_f)
    region_layout = {r.name: lay.name for lay, r in p.all_regions()}

    def _fonts_for(el) -> list:
        if getattr(el, "font_name", "") in fonts:
            return [fonts[el.font_name]]
        return lay_defaults.get(region_layout.get(el.name, ""), None) or ([first] if first else [])

    def _effective(lbl: str, font):
        """La langue ne remplace que la Default Font du projet."""
        if not lbl:
            return font
        lang = lang_by_code.get(lbl)
        default = getattr(p.settings, "default_font", "") or ""
        target = getattr(lang, "default_font", "") if lang and font.name == default else ""
        return fonts.get(target or "", font)

    def _missing(parsed, base_font) -> list[tuple[str, str]]:
        """(police active, caractère absent), segment par segment.

        Les bornes d'une portée sont exprimées dans ``parsed.display``. Un
        `$const` y occupe une seule place mais se développe à l'affichage : ses
        chiffres héritent donc tous de la police active à cette position.
        """
        values = {m.at: str(consts[m.value])[:m.limit or None]
                  for m in parsed.markers
                  if m.kind == KIND_VALUE and m.value in consts}
        font_markers = parsed.of_kind("font")
        missing: set[tuple[str, str]] = set()
        for i, char in enumerate(parsed.display):
            active = base_font
            for marker in font_markers:
                if marker.at <= i < marker.end:
                    active = fonts.get(str(marker.value), active)
            shown = values.get(i, f"${next((m.value for m in parsed.markers if m.at == i), '')}") \
                    if char == SENTINEL else char
            for shown_char in shown:
                if shown_char != "\n" and shown_char not in coverage.get(active.name, set()):
                    missing.add((active.name, shown_char))
        return sorted(missing)

    def _warn(key: str, lbl: str, region_kind: str, region_name: str,
              missing: list[tuple[str, str]]):
        by_font: dict[str, list[str]] = {}
        for font_name, char in missing:
            by_font.setdefault(font_name, []).append(char)
        details = "; ".join(f"{font_name} : {' '.join(chars)}"
                            for font_name, chars in by_font.items())
        ctx.warn(None,
            f"Text '{key}'"
            + (f" (language \"{lbl}\")" if lbl else "")
            + f" cites a character missing from the active font ({region_kind} '{region_name}'): "
              f"{details}. The missing glyph will be skipped at display, without a word in "
              "game. Add it to a font, or change the translation.")

    seen: set = set()
    for site in find_call_sites_in_project(p, DOMAIN_UI_ELEMENT, DOMAIN_TEXT):
        region = regions.get(site.values[DOMAIN_UI_ELEMENT])
        text   = p.get_text(site.values[DOMAIN_TEXT])
        if region is None or text is None:
            continue
        for lbl, _source, parsed in _text_variants(p, text, globals_names):
            for font in _fonts_for(region):
                eff = _effective(lbl, font)
                quad = (region.name, text.key, eff.name, lbl, parsed.display)
                if quad in seen:
                    continue
                seen.add(quad)
                missing = _missing(parsed, eff)
                if missing:
                    _warn(text.key, lbl, "the zone", region.name, missing)

    from core.models.ui_region import KIND_TEXT
    for _lay, el in p.all_regions():
        if getattr(el, "kind", "") != KIND_TEXT:
            continue
        text = p.get_text(getattr(el, "text_key", "") or "")
        if text is None:
            continue
        for lbl, _source, parsed in _text_variants(p, text, globals_names):
            for font in _fonts_for(el):
                eff = _effective(lbl, font)
                quad = (el.name, text.key, eff.name, lbl, parsed.display)
                if quad in seen:
                    continue
                seen.add(quad)
                missing = _missing(parsed, eff)
                if missing:
                    _warn(text.key, lbl, "the element", el.name, missing)


def _check_literal_texts(ctx: ValidationContext):
    """Un littéral passé à `text:draw("Bonjour")` reste compilable — une
    entrée ANONYME de la table, comme depuis la v0.3.2, un raccourci hors
    interface ASSUMÉ au prix de la traduction. Mais dès qu'une langue est
    déclarée, c'est un trou de traduction GARANTI (ROADMAP v0.9, décision 6) :
    l'entrée n'a pas de clé dans `texts.json`, donc rien qu'un side puisse
    joindre par id — aucune langue ne pourra jamais le traduire.

    Silencieux tant que le projet est MONOLINGUE : c'était un prix que
    personne n'a encore demandé de payer, pas une faute à signaler dans le
    vide. Un littéral qui référence une clé RÉELLE (`by_key`, cf.
    `Project.collect_literal_texts`) n'en est pas un — il est déjà couvert."""
    p = ctx.project
    if not hasattr(p, "is_multilingual") or not p.is_multilingual():
        return
    from scripting.refactor import iter_refs, script_paths
    from scripting.api import DOMAIN_TEXT, LITERAL_TEXT_CALLS
    keys = {t.key for t in getattr(p, "texts", [])}
    for path in script_paths(p):
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # tolerated: _check_scripts_parse reports it
            continue
        for ref in iter_refs(src, path=path, domain=DOMAIN_TEXT):
            if ref.api_key not in LITERAL_TEXT_CALLS or ref.value in keys:
                continue
            ctx.warn(None,
                f"{path.name}:{ref.line}: the literal text \"{ref.value}\" passed to {ref.api_key}(...) is not "
                "translatable — it is an ANONYMOUS entry (v0.3.2), invisible to every"
                " declared language. Create it in the Text screen to be able to "
                "translate it.")


def _check_translation_holes(ctx: ValidationContext):
    """Ce qu'une langue déclarée n'a pas traduit (ROADMAP v0.9, phase 5.3).

    Décision verrouillée à l'ouverture du jalon — « le build compte les trous
    et les nomme » — et restée sans implémentation jusqu'ici : le compte
    existait dans l'ÉDITEUR (le badge par onglet de l'atelier, phase 2), pas
    là où quelqu'un fabrique une cartouche.

    Un trou n'est pas une erreur : une entrée absente d'un side rend la SOURCE
    (`project_langs.py`), donc le jeu affiche un texte de la mauvaise langue
    plutôt qu'un écran blanc — c'est délibéré, et c'est ce qui laisse traduire
    un jeu par étapes. Ce qui manquait, c'est de le SAVOIR avant de graver.

    Silencieux en projet monolingue, même contrat que `_check_literal_texts` :
    sans langue déclarée, il n'y a pas de trou, il y a un jeu dans sa langue.
    Les entrées ANONYMES (littéraux de script) ne sont pas comptées ici — elles
    n'ont pas d'id qu'un side puisse joindre, et `_check_literal_texts` les
    nomme déjà une par une, avec leur fichier et leur ligne."""
    p = ctx.project
    if not hasattr(p, "is_multilingual") or not p.is_multilingual():
        return
    textes = [t for t in getattr(p, "texts", []) if (t.content or "").strip()]
    if not textes:
        return
    for lang in p.settings.languages:
        side = p.translations.get(lang.code, {})
        trous = [t for t in textes if not (side.get(t.id) or "").strip()]
        if not trous:
            continue
        # Les clés, pas les ids : c'est ce que l'auteur lit dans l'écran Texte
        # et ce que ses scripts citent. Trois, parce qu'un message qui déroule
        # deux cents clés ne se lit pas — le compte porte l'ampleur, l'écran
        # porte la liste.
        apercu = ", ".join(t.key for t in trous[:3])
        reste = f", and {len(trous) - 3} more" if len(trous) > 3 else ""
        ctx.warn(None,
            f"Language \"{lang.name or lang.code}\": {len(trous)} of {len(textes)} entries are not translated — they will "
            f"display in the source language ({apercu}{reste}).")


def _check_ui_text_key(ctx: ValidationContext):
    """Un texte qui pointe une clé DISPARUE ne dessine rien.

    Erreur silencieuse par excellence : l'élément reste visible dans le canvas,
    le build n'émet aucun appel, et la ROM affiche un vide sans que rien n'ait
    échoué.

    Une clé VIDE, elle, ne se signale plus : depuis la fusion des deux types de
    texte, c'est un choix d'authoring normal — l'élément est un emplacement
    qu'un script remplira (`interface.draw_text`). Le signaler ferait crier le
    validateur sur chaque boîte de dialogue d'un projet qui pilote son texte au
    script, c'est-à-dire sur le cas le plus courant."""
    p = ctx.project
    for lay, el in p.all_regions():
        key = getattr(el, "text_key", "") or ""
        if key and p.get_text(key) is None:
            ctx.error(None,
                f"Text '{el.name}' (layout '{lay.name}') points to key '{key}', which no longer "
                "exists in the text table.",
                DiagnosticTarget("ui_element", el.name, lay.name))


def _check_blend(ctx: ValidationContext):
    """Les deux pannes MUETTES du mélange de couleurs.

    Le matériel n'échoue pas : il n'applique simplement rien, et rien ne le dit.
    Les deux cas se ressemblent à l'écran (« mon effet ne marche pas ») et se
    diagnostiquent dans deux registres différents.

    Avertissement et non erreur : la ROM tourne, elle est juste moins jolie que
    prévu — et un auteur peut très bien régler le mode d'abord et les cibles
    ensuite sans qu'on lui bloque un build entre les deux."""
    from core.models.scene import (BLEND_NONE, BLEND_TOP, BLEND_BOTTOM,
                                   BLEND_NEEDS_BOTTOM, blend_role_of)
    for scene in ctx.project.scenes:
        mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
        if mode == BLEND_NONE:
            continue
        if not scene.blend_has_target(BLEND_TOP):
            ctx.warn(None,
                f"Scene '{scene.name}': a blend mode is set but no first target is designated —"
                " nothing is blended, the effect has no effect. Set a layer (or the "
                "sprites) to \"top\".")
        elif mode in BLEND_NEEDS_BOTTOM and not scene.blend_has_target(BLEND_BOTTOM):
            ctx.warn(None,
                f"Scene '{scene.name}': alpha without a second target — blending only happens "
                "where a pixel of the top has a pixel of the bottom behind it. Set "
                "the layer behind, or the backdrop, to \"bottom\".")
        # Un rôle « dessous » sous un mode qui ne l'emploie pas ne fait rien.
        if mode not in BLEND_NEEDS_BOTTOM:
            idle = [f"BG{L.bg_slot}" for L in scene.background_layers
                    if blend_role_of(L) == BLEND_BOTTOM]
            if idle:
                ctx.warn(None,
                    f"Scene '{scene.name}': {', '.join(idle)} set to \"bottom\", but this mode only uses the "
                    "top — this role does nothing.")


def _check_ui_image(ctx: ValidationContext):
    """Une image sans sprite résoluble ne dessine rien.

    Même famille de panne silencieuse que la clé de texte disparue : l'élément
    est bien là dans le canvas, la table est bien émise, et la ROM ne montre
    rien à cet endroit. La distinction vide / cassé est reprise telle quelle —
    on ne réclame pas un sprite à une image fraîchement dessinée, on signale
    seulement une référence qui ne résout plus.

    L'état, lui, n'a pas besoin d'être vérifié : un `state_name` qui ne résout
    plus retombe sur l'état 0 (`UIImage.state_index`), ce qui affiche quelque
    chose plutôt que rien."""
    p = ctx.project
    if not hasattr(p, "all_images"):
        return
    from core.models.ui_region import can_fill
    for lay, im in p.all_images():
        # `all_images` porte aussi les conteneurs à fond sprite : même table, même
        # panne, seul le mot change pour que le message désigne le bon objet.
        what = ("the container background" if can_fill(im)
                else "the image")
        name = getattr(im, "sprite_name", "") or ""
        if not name:
            continue
        if p.get_sprite(name) is None:
            ctx.error(None,
                f"{what.capitalize()} '{im.name}' (layout '{lay.name}') points to sprite '{name}', which no longer "
                "exists in the project.",
                DiagnosticTarget("ui_element", im.name, lay.name))
        elif im.state_name and not any(
                s.name == im.state_name
                for s in getattr(p.get_sprite(name), "states", []) or []):
            ctx.warn(None,
                f"{what.capitalize()} '{im.name}' asks for state '{im.state_name}', missing from sprite '{name}' — it will "
                "display the first state.",
                DiagnosticTarget("ui_element", im.name, lay.name))


def _check_ui_container_fill(ctx: ValidationContext):
    """Le canvas peint le fond d'un conteneur d'UI quoi qu'il arrive ; le build,
    lui, n'en émet qu'une partie. Un conteneur hors de ce cadre disparaît entre
    l'éditeur et la ROM, sans une ligne de log.

    Deux chemins depuis que les fonds OBJ existent, et le mode DIT lequel :
    couleur / nine-slice / background posent des tuiles et une carte, donc BG
    (`scene_color_fills` / `scene_image_fills`, root ancré ÉCRAN) ; sprite pave
    des OBJ, donc OBJ (`g_ui_images`). `fill_allowed` interdit les croisements —
    ce qui reste ici, ce sont les cas qui PASSENT le modèle et tombent quand
    même au build.

    Avertissement et non erreur : le texte de la zone s'affiche quand même, il
    lui manque son fond."""
    p = ctx.project
    from core.models.ui_region import (can_fill, FILL_NONE, FILL_COLOR,
                                       FILL_SPRITE, ANCHOR_SCREEN, TARGET_BG,
                                       fill_allowed)
    for scene in p.scenes:
        rm = int(getattr(scene, "render_mode", 0) or 0)
        active = list(getattr(scene, "active_bg_palettes", []) or [])
        for lay, el in p.scene_ui_elements(scene):
            if not can_fill(el):
                continue
            fk = getattr(el, "fill_kind", FILL_NONE)
            if fk == FILL_NONE:
                continue
            target = lay.resolved_target(el, rm)
            # ① Mode incompatible avec la cible. Le cas le plus courant est un
            # fond posé quand le root était ancré à l'écran, puis le root est
            # passé sur un acteur — la cible bascule en OBJ et emporte tout le
            # sous-arbre, sans que le fond ait été retouché.
            if not fill_allowed(fk, target):
                quoi = ("a sprite background" if target != TARGET_BG
                        else "a colour, a nine-slice or a background")
                ctx.warn(None,
                    f"Scene '{scene.name}': the background of container '{el.name}' is in mode "
                    f"\"{fk}\", which does not exist on target {target.upper()} — nothing will be "
                    f"drawn. On this target, choose {quoi}.",
                    DiagnosticTarget("ui_element", el.name, lay.name))
                continue
            why = []
            if fk == FILL_SPRITE:
                # ② Chemin OBJ. La résolution du sprite est dite par
                # `_check_ui_image` (même table) : ici, ce qui lui est propre.
                if not getattr(el, "fill_sprite", ""):
                    why.append("no sprite is chosen")
            else:
                # ③ Chemin BG.
                if p.scene_ui_bg_slot(scene) not in (0, 1, 2, 3):
                    why.append("the scene has no UI layer (no Interface node on "
                               "Background)")
                anchor = lay.effective_anchor(el)[0]
                if anchor != ANCHOR_SCREEN:
                    why.append(f"its anchor is \"{anchor}\" (only the screen is emitted)")
                if fk == FILL_COLOR and getattr(el, "fill_palette", "") not in active:
                    why.append("its palette "
                               f"\"{getattr(el, 'fill_palette', '') or '(none)'}\" is not among the scene's active BG palettes")
            if why:
                ctx.warn(None,
                    f"Scene '{scene.name}': the background of container '{el.name}' will NOT be in "
                    f"the ROM — {' ; '.join(why)}. The canvas shows it anyway: the editor promises "
                    "more than the build delivers.",
                    DiagnosticTarget("ui_element", el.name, lay.name))


def _check_data_column_types(ctx: ValidationContext):
    """Les trois listes qui décrivent un type de colonne doivent s'accorder.

    Une colonne de RÉFÉRENCE porte le nom de son domaine de script, et ce nom
    doit exister des deux autres côtés : dans `api.ALL_DOMAINS` (sinon le
    checker et le codegen n'en savent rien) et dans `project.DATA_COLUMN_SOURCES`
    (sinon la cellule n'offre aucun choix). `core.models.data_table` ne peut pas
    importer les deux — c'est une couche en dessous — donc l'accord se vérifie
    ICI, comme celui des prototypes du moteur et celui des domaines d'argument.

    Erreur bloquante et non avertissement : un type sans domaine émettrait un 0
    silencieux dans la ROM, et un type sans source rendrait la colonne
    inéditable sans que rien ne le dise."""
    from core.models.data_table import COLUMN_REFERENCES
    from core.project import DATA_COLUMN_SOURCES
    from scripting.api import ALL_DOMAINS, REF_TYPE_TABLE

    # Une colonne cite un DOMAINE (un nom d'asset : `text`, `sfx`…) ou une RÉFÉRENCE typée
    # (une zone de texte, une image : leur index EST le handle du type, `RefType.column`).
    # Le nom d'un élément d'interface ne se cite plus dans un argument — `interface.get` est
    # la seule porte —, mais sa colonne reste une donnée valide.
    citables = ALL_DOMAINS | {t.column for t in REF_TYPE_TABLE.values() if t.column}
    inconnus = sorted(set(COLUMN_REFERENCES) - citables)
    if inconnus:
        ctx.error(None,
                  "Column type(s) without a matching script domain: "
                  f"{', '.join(inconnus)}. A reference column carries the name of its domain "
                  "(scripting/api.py, DOMAIN_*) or declares `column` on the reference"
                  " type that carries it (RefType).")
    sans_source = sorted(set(COLUMN_REFERENCES) - set(DATA_COLUMN_SOURCES))
    if sans_source:
        ctx.error(None,
                  "Column type(s) without a list of citable names: "
                  f"{', '.join(sans_source)}. Complete DATA_COLUMN_SOURCES (core/project.py).")
    fantomes = sorted(set(DATA_COLUMN_SOURCES) - set(COLUMN_REFERENCES))
    if fantomes:
        ctx.warn(None,
                 "DATA_COLUMN_SOURCES describes a column type that no longer exists: "
                 f"{', '.join(fantomes)}.")


def _check_data_tables(ctx: ValidationContext):
    """Ce qu'une table de données doit respecter pour être émise.

    Le nom d'une table et celui de ses colonnes s'écrivent comme du CODE dans
    un script (`data.Objets[i].prix`) : ce sont des identifiants, pas des
    libellés. Et une référence qui ne résout pas serait émise en 0 — c'est-à-dire
    la PREMIÈRE entrée de la table citée, une valeur plausible et fausse. La
    dégradation silencieuse est refusée ici comme partout ailleurs."""
    from core.models.data_table import COLUMN_TYPES, COLUMN_REFERENCES, IDENTIFIER

    p = ctx.project
    for table in getattr(p, "data_tables", []):
        if not IDENTIFIER.match(table.name):
            ctx.error(None,
                      f"Table \"{table.name}\": a script writes it without quotes "
                      f"(data.{table.name}), so its name must be an identifier — letters, "
                      "digits and _, not starting with a digit.")
        vus = set()
        for col in table.columns:
            if not IDENTIFIER.match(col.name):
                ctx.error(None,
                          f"Table \"{table.name}\", column \"{col.name}\": same rule as the table name, it"
                          " is an identifier.")
            if col.name in vus:
                ctx.error(None,
                          f"Table \"{table.name}\": two columns named \"{col.name}\".")
            vus.add(col.name)
            if col.type not in COLUMN_TYPES:
                ctx.error(None,
                          f"Table \"{table.name}\", column \"{col.name}\": unknown type '{col.type}' "
                          f"({', '.join(COLUMN_TYPES)}).")
        for n, row in enumerate(table.rows, start=1):
            for key in row:
                if key not in vus:
                    ctx.warn(None,
                             f"Table \"{table.name}\", row {n}: key \"{key}\" matches no column — it "
                             "is not emitted.")
            for col in table.columns:
                if col.type not in COLUMN_REFERENCES:
                    continue
                name = str(table.value(row, col) or "").strip()
                if name and name not in p.data_column_choices(col.type):
                    ctx.error(None,
                              f"Table \"{table.name}\", row {n}, column \"{col.name}\": no {col.type} named "
                              f"\"{name}\" in the project.")


def _check_cameras(ctx: ValidationContext):
    """Trois choses peuvent mentir sans faire échouer le build — d'où des
    avertissements plutôt qu'un silence.

    ① Une caméra en suivi cite un acteur par nom ; comme elle appartient
      désormais à UNE scène, ce nom doit être un acteur de CETTE scène.
    ② La scène désigne une caméra qui n'existe plus (dans sa propre liste) :
      elle retombe sur la caméra par défaut, donc un cadrage à l'origine sans
      bornes.
    ③ Deux caméras du projet portent le même nom : `camera:switch("Nom")`
      n'est pas qualifié par scène, un doublon viserait la mauvaise caméra."""
    p = ctx.project
    seen: dict[str, str] = {}   # nom → scène qui l'a vu en premier
    for scene in p.scenes:
        for cam in scene.cameras:
            if cam.mode == "follow" and not cam.follow_target:
                ctx.warn(None,
                    f"Camera \"{cam.name}\" (scene '{scene.name}'): follow mode without a target actor —"
                    " it will behave like a fixed camera.")
            elif cam.mode == "follow" and not any(
                    a.name == cam.follow_target for a in scene.actors):
                ctx.warn(None,
                    f"Scene '{scene.name}': camera \"{cam.name}\" follows \"{cam.follow_target}\", which is not an actor "
                    "of this scene — the camera will stay still.")
            if cam.name in seen and seen[cam.name] != scene.name:
                ctx.warn(None,
                    f"Two cameras named \"{cam.name}\" (scenes '{seen[cam.name]}' and '{scene.name}') — "
                    f"camera:switch(\"{cam.name}\") would target either one, depending on the "
                    "build.")
            seen.setdefault(cam.name, scene.name)
        if not scene.cameras:
            # Sans caméra, la vue reste fixe à (0,0) : sans conséquence pour un
            # écran d'un seul tenant (menu, titre), mais tout ce qui dépasse
            # 240×160 est alors inatteignable.
            for layer in scene.background_layers:
                ba = p.get_background(layer.background_name) if layer.background_name else None
                bw, bh = ba.pixel_size() if ba else (0, 0)
                if bw > 240 or bh > 160:
                    ctx.warn(None,
                        f"Scene '{scene.name}' has no camera but its background \"{layer.background_name}\""
                        f" ({bw}×{bh}) is larger than the screen — the view stays fixed at the origin,"
                        " the rest of the scene is never shown. Add a camera to scroll.")
                    break
        want = getattr(scene, "camera", "") or ""
        if want and not any(c.name == want for c in scene.cameras):
            ctx.warn(None,
                f"Scene '{scene.name}': camera \"{want}\" no longer exists — the scene restarts from"
                " the default camera (fixed at the origin, without bounds).")


def _check_script_owner_families(ctx: ValidationContext):
    """Un fichier de script a UNE famille de propriétaire : acteur/prefab, scène ou caméra.

    C'est l'attache qui donne son contexte au script (ses événements, l'existence de
    `self`). Un même fichier attaché à deux familles aurait deux contextes à la fois :
    `self` y désignerait une instance dans un cas et rien dans l'autre. On le refuse
    plutôt que de le tolérer — un fichier, un contexte. Plusieurs acteurs qui partagent
    le même script, eux, restent permis : c'est la même famille."""
    from core.script_owners import script_attachments, FAMILY_LABELS

    for path, familles in script_attachments(ctx.project).items():
        if len(familles) < 2:
            continue
        detail = " ; ".join(f"{FAMILY_LABELS[fam]} : {', '.join(owners[:3])}"
                            f"{'…' if len(owners) > 3 else ''}"
                            for fam, owners in familles.items())
        ctx.error(None,
            f"Script \"{path}\" is attached to several families of owners ({detail}). A script "
            "has a single context: `self` and the available events depend on what it "
            "is attached to. Write one script per family, and put the shared code in "
            "a behavior.")


def _check_scripts_parse(ctx: ValidationContext):
    """Chaque `.lua` de `scripts/` est lu, utilisé ou non (chantier « La fiabilité du
    journal de build »). Le build ne parse que ce qu'il compile : un behavior inliné
    n'était qu'un avertissement, un prefab sans instance dans la scène était sauté, un
    fichier attaché à rien n'était jamais ouvert.

    Une faute de syntaxe, ou une instruction hors fonction qui ne s'exécuterait jamais, est
    une ERREUR pour un script attaché (acteur, scène, caméra, prefab) et pour un behavior ;
    pour un fichier attaché à rien, un avertissement : un brouillon ne bloque pas le build."""
    from scripting.parser import parse as lua_parse, LuaParseError
    from core.script_owners import script_attachments

    p = ctx.project
    attached = set()
    for rel in script_attachments(p):
        ap = p.asset_abs(rel)
        if ap is not None and Path(ap).suffix.lower() == ".lua":
            attached.add(Path(ap).resolve())
    behaviors = (sorted(p.scripts_behaviors_dir.glob("*.lua"))
                 if p.scripts_behaviors_dir.is_dir() else [])
    files = {f.resolve(): f for f in (*p.script_files(), *behaviors)}
    files.update({a: a for a in attached if a.exists()})

    for resolved, path in sorted(files.items(), key=lambda kv: str(kv[0])):
        blocking = resolved in attached or p.scripts_behaviors_dir in path.parents
        report = ctx.error if blocking else ctx.warn
        suffix = "" if blocking else " (attached to nothing)"
        try:
            script = lua_parse(path.read_text(encoding="utf-8"))
        except LuaParseError as exc:
            report(None, f"{exc}{suffix}", file=path.name, line=exc.line or 0)
            continue
        except UnicodeDecodeError as exc:
            ctx.undecodable_scripts = True
            report(None, f"not valid UTF-8 (byte {exc.object[exc.start]:#04x} at position "
                         f"{exc.start}): save the script as UTF-8{suffix}", file=path.name)
            continue
        except OSError as exc:
            report(None, f"cannot be read ({exc}){suffix}", file=path.name)
            continue
        for _node, line in script.stray_statements:
            report(None, f"this statement is outside any function, so it would never "
                         f"run{suffix}", file=path.name, line=line)
        if blocking and not script.functions:
            # Un script vide (ou réduit à des commentaires) est valide, mais l'acteur qui le porte
            # perd tout son comportement : un avertissement, pas une erreur.
            ctx.warn(None, "defines no function: the script does nothing.", file=path.name)


def _check_behaviors_without_self(ctx: ValidationContext):
    """`self` désigne l'instance à laquelle le script est attaché ; un behavior n'est
    attaché à rien, il REÇOIT un acteur en paramètre. Lui laisser le mot `self` le
    rendrait ambigu (l'instance attachée ? le paramètre ?) — on le refuse, en
    bloquant le build : les erreurs du checker sur un behavior ne sont que des
    avertissements, ce qui ne suffit pas ici."""
    from scripting.parser import parse as lua_parse, LuaParseError
    from scripting.checker import uses_self

    behaviors_dir = ctx.project.scripts_behaviors_dir
    if not behaviors_dir.is_dir():
        return
    for path in sorted(behaviors_dir.glob("*.lua")):
        try:
            script = lua_parse(path.read_text(encoding="utf-8"))
        except (LuaParseError, OSError, UnicodeDecodeError):  # tolerated: _check_scripts_parse reports it
            continue
        if uses_self(script):
            ctx.error(None,
                f"Behavior \"{path.stem}\": `self` is reserved for the instance a script is "
                "attached to. A behavior receives its actor as first parameter: name "
                "it something else, `function M.update(actor)`.")


def _check_actor_budget(ctx: ValidationContext):
    """Le budget OAM d'une scène — la SEULE faute possible, et elle est BLOQUANTE
    (ROADMAP v0.17 T7).

    Source unique : `scene_oam_layout` (la même que le build lit pour dimensionner
    `g_actors` et placer les pools). Acteurs actifs + OBJ d'interface + pools
    doivent tenir dans les 128 entrées de l'OAM. Le validateur et le build ne
    peuvent donc plus diverger — c'est le sens de « budget unifié ».

    ERREUR et non avertissement, depuis que les trois postes atterrissent sur des
    entrées OAM RÉELLES : le rendu écrit `shadow_oam[<index>]` avec l'index de
    `g_actors` (cf. main_gen / `oam_update`), et `shadow_oam` n'a que 128 entrées.
    Au-delà, ce n'est plus « le surplus ne s'affiche pas » mais un débordement de
    tableau qui corrompt la mémoire voisine. L'ancienne mesure « avertissement »
    (v0.7.6) valait quand le pool était une tranche à part ; il partage désormais
    la fenêtre OAM des acteurs.

    N.B. — l'inspecteur, lui, affiche la RÉSERVATION de l'auteur (override
    `Scene.actor_slots`, via `actor_budget.scene_actor_budget`) : une vue
    d'intention, distincte de l'empreinte matérielle mesurée ici."""
    from codegen.oam_alloc import scene_oam_layout, OAM_LIMIT
    p = ctx.project
    for scene in p.scenes:
        lay = scene_oam_layout(p, scene)
        if lay.over_budget:
            ctx.error(None,
                f"Scene '{scene.name}': {lay.used} OAM entries requested ({lay.placed_entries} sprite actors + {lay.ui} "
                f"interface + {lay.pool_entries} pool) for {OAM_LIMIT} available — reduce a background "
                "tiling, move a zone to a BG target, or shrink the pool.")


def _check_window_regions(ctx: ValidationContext):
    """Réglé le 2026-08-25 : WIN0/WIN1 sont allouées par intention
    (`codegen/window_alloc.py`), pas choisies par l'auteur — cf.
    ARCHITECTURE.md « Windows — le pochoir ».

    ① Une scène qui demande plus de deux intentions (cadre de caméra +
      `WindowSlot` nommés) fait échouer le build — ERREUR bloquante, pas un
      warning : il n'existe pas de repli sûr, une région non allouée
      s'affiche partout au lieu d'être découpée (bug visuel silencieux).
    ② Un `WindowSlot` sans nom ne peut être ni alloué ni adressé depuis Lua.
    ③ Deux `WindowSlot` (toutes scènes) partageant un nom : `window.set_layer`
      n'est pas qualifié par scène, un doublon viserait la mauvaise window —
      même check que les caméras (`_check_cameras`)."""
    from codegen.window_alloc import scene_window_layout
    seen: dict[str, str] = {}   # nom → scène qui l'a vu en premier
    for scene in ctx.project.scenes:
        layout = scene_window_layout(ctx.project, scene)
        if layout.overflow:
            names = ", ".join(f"\"{n}\"" for n in layout.overflow)
            ctx.error(None,
                f"Scene '{scene.name}': {names} do(es) not fit — only two rectangle windows are "
                "possible per scene (camera frame included). Reduce the number of "
                "WindowSlots or enlarge the frame of a reduced camera.")
        for ws in scene.windows:
            if ws.is_obj:
                continue
            if not ws.name:
                ctx.error(None,
                    f"Scene '{scene.name}': a rectangle window has no name — it can be neither "
                    "allocated nor cited from a script.")
                continue
            if ws.name in seen and seen[ws.name] != scene.name:
                ctx.warn(None,
                    f"Two windows named \"{ws.name}\" (scenes '{seen[ws.name]}' and '{scene.name}') — "
                    f"window.set_layer(\"{ws.name}\") would target either one, depending on "
                    "the build.")
            seen.setdefault(ws.name, scene.name)


def _check_actor_name_collisions(ctx: ValidationContext):
    """Deux acteurs d'une MÊME scène portant le même symbole C se marchent
    dessus au build (ROADMAP « L'acteur appartient à sa scène », décision B).

    Un acteur appartient à sa scène : son nom est LOCAL à la scène, donc
    réutilisable librement d'une scène à l'autre — deux « Cursor » dans deux
    scènes ne collisionnent plus, parce que le symbole C émis est qualifié par
    la scène (`<Scène>_<Acteur>`, cf. `codegen.c_names.scene_actor_sym`), comme
    l'est déjà un prefab poolé. L'unicité n'est donc exigée que DANS une même
    scène — deux « Cursor » de la MÊME scène partagent alors le TAG et le
    fichier `actor_<Scène>_<Acteur>.c`, donc le même comportement.

    Avertissement et non erreur : le build aboutit, la ROM tourne — c'est le
    comportement qui ment. Comparé sur le SYMBOLE C, pas sur le nom :
    « Player 1 » et « Player-1 » donnent le même symbole."""
    from codegen.c_names import sym as c_sym
    for scene in ctx.project.scenes:
        seen: dict[str, str] = {}   # symbole → premier nom vu DANS cette scène
        for actor in scene.actors:
            s = c_sym(actor.name)
            if s in seen:
                first = seen[s]
                same = first == actor.name
                quoi = (f"Two actors named \"{actor.name}\"" if same else
                        f"Actors \"{first}\" and \"{actor.name}\"")
                ctx.warn(None,
                    f"{quoi} in scene '{scene.name}' share the C symbol `{s}` — same TAG and same "
                    f"file actor_{c_sym(scene.name)}_{s}.c, hence the same behaviour. Rename one of "
                    "them.")
            seen.setdefault(s, actor.name)


def _check_audio_files(ctx: ValidationContext):
    """Second filet derrière le refus à l'import : le ProjectWatcher crée aussi
    des ressources pour les fichiers déposés à la main dans assets/sfx/ et
    assets/music/, qui n'ont donc traversé aucun dialogue.

    En ERREUR et non en avertissement, contrairement à la plupart des contrôles
    d'ici, parce que mmutil ne bronchera pas : un wav 24 bits produit une ROM
    complète, avec sa constante `SFX_*` bien définie et un effet muet. Laisser
    passer, c'est livrer un jeu dont un son manque sans que rien ne l'ait dit —
    et ça ne s'entend qu'en jouant."""
    from core.resources.asset_reconciliation import check_audio_file
    p = ctx.project
    for kind, assets in (("SFX", getattr(p, "sfx", [])),
                         ("Music", getattr(p, "music", []))):
        for a in assets or []:
            if not a.asset:
                ctx.warn(None, f"{kind} \"{a.name}\": no associated file.")
                continue
            path = p.asset_abs(a.asset)
            if not path or not path.exists():
                ctx.warn(None, f"{kind} \"{a.name}\": file not found ({a.asset}); it is not played.")
                continue
            if reason := check_audio_file(path):
                ctx.error(None, f"{kind} \"{a.name}\" ({path.name}): {reason}")

    # `Scene.music` nomme une piste sans qu'aucun script ne la cite : c'est une
    # référence de plus à vérifier. En AVERTISSEMENT — le codegen sait ne pas
    # émettre l'appel, donc la scène est muette au lieu de casser le build.
    from core.models.scene import MUSIC_INHERIT, MUSIC_NONE
    known = {m.name for m in getattr(p, "music", [])}
    for scene in p.scenes:
        want = getattr(scene, "music", MUSIC_INHERIT) or MUSIC_INHERIT
        if want in (MUSIC_INHERIT, MUSIC_NONE) or want in known:
            continue
        ctx.warn(None,
            f"Scene '{scene.name}': music \"{want}\" does not exist — the scene will start none "
            "(what already plays continues).")

    # `MUSIC_NONE` est le mot réservé qui déclare le silence. Une piste qui
    # porterait ce nom deviendrait inatteignable par une scène, sans que rien
    # ne le dise.
    if MUSIC_NONE in known:
        ctx.error(None,
            f"A music is named \"{MUSIC_NONE}\", which is the reserved word for silence in "
            "Scene.music — rename it.")


def _check_music_cut_compat(ctx: ValidationContext):
    """`music.cut_to` reprend l'autre module au MÊME index d'ordre. Deux
    modules dont la table d'ordre n'a pas la même longueur ne peuvent donc pas
    se relayer : la reprise tomberait ailleurs dans le morceau.

    Sans ce contrôle, l'auteur entend un saut sans savoir d'où il vient — et
    c'est le genre de défaut qu'on ne rattache jamais à sa cause. En
    AVERTISSEMENT : la ROM se construit et joue, c'est le résultat musical qui
    est douteux, et une structure volontairement différente reste un choix
    défendable.

    On compare chaque piste citée par `cut_to` à celles que le script peut
    avoir en cours — c'est-à-dire toutes les autres du même script. Grossier,
    mais du bon côté : on préfère un avertissement de trop qu'un saut muet."""
    from scripting.api import DOMAIN_MUSIC
    from scripting.refactor import iter_refs, script_paths
    p = ctx.project
    by_name = {m.name: m for m in getattr(p, "music", [])}
    orders: dict[str, int] = {}

    def order_len(name: str) -> Optional[int]:
        if name in orders:
            return orders[name]
        m = by_name.get(name)
        ap = p.asset_abs(m.asset) if m and m.asset else None
        n = None
        if ap and ap.exists():
            mod = ctx.module(ap)
            n = len(mod.order) if mod is not None else None
        orders[name] = n
        return n

    for path in script_paths(p):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # tolerated: _check_scripts_parse reports it
            continue
        if "cut_to" not in text:            # évite de parser pour rien
            continue
        cited = {r.value for r in iter_refs(text, path=path, domain=DOMAIN_MUSIC)}
        targets = {r.value for r in iter_refs(text, path=path, domain=DOMAIN_MUSIC)
                   if r.api_key == "music.cut_to"}
        for target in sorted(targets):
            n_t = order_len(target)
            if n_t is None:
                continue
            for other in sorted(cited - {target}):
                n_o = order_len(other)
                if n_o is not None and n_o != n_t:
                    ctx.warn(None,
                        f"{path.name}: music:cut_to(\"{target}\") resumes at the current position, "
                        f"but \"{other}\" does not have the same structure ({n_o} patterns "
                        f"against {n_t}) — the resume would land elsewhere in the song.")


def _check_jingle_channels(ctx: ValidationContext):
    """Un jingle est plafonné à 4 canaux par maxmod (doc `mmJingle`).

    Un module qui en demande plus sera joué tronqué — et un morceau tronqué ne
    s'entend pas comme une erreur, il s'entend comme un morceau raté. Le nombre
    de canaux est écrit dans l'en-tête du MOD et `mod_file.py` le lit déjà : ça
    se vérifie sans rien construire."""
    from scripting.api import DOMAIN_MUSIC
    from scripting.refactor import iter_refs, script_paths
    p = ctx.project
    by_name = {m.name: m for m in getattr(p, "music", [])}
    seen: set[str] = set()
    for path in script_paths(p):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # tolerated: _check_scripts_parse reports it
            continue
        if "jingle" not in text:
            continue
        for ref in iter_refs(text, path=path, domain=DOMAIN_MUSIC):
            if ref.api_key != "music.jingle" or ref.value in seen:
                continue
            seen.add(ref.value)
            m = by_name.get(ref.value)
            ap = p.asset_abs(m.asset) if m and m.asset else None
            if not (ap and ap.exists()):
                continue
            mod = ctx.module(ap)
            if mod is None:
                continue
            ch = mod.num_channels
            if ch > 4:
                ctx.warn(None,
                    f"{path.name}: \"{ref.value}\" is played as a jingle but uses {ch} channels — maxmod "
                    "only gives 4 to a jingle, the others will be silent.")


def _check_module_channels(ctx: ValidationContext):
    """Un module qui demande plus de voies que le projet n'a de canaux.

    `mmInitDefault(bank, n)` fixe le nombre de canaux logiciels — un réglage de
    projet depuis la v0.8.8 — et musique et effets s'y partagent. Un module de
    16 voies dans un projet à 8 canaux ne joue pas « un peu moins fort » : les
    notes en trop n'ont nulle part où sonner, et il manque des instruments sans
    que rien ne le dise. Même contrôle que les 4 canaux du jingle, avec l'autre
    plafond.

    En AVERTISSEMENT : la ROM se construit et joue. Et volontairement large —
    on regarde toutes les musiques du projet, pas seulement celles qu'un script
    cite, parce que le coût du contrôle est nul et qu'un morceau importé pour
    plus tard vaut mieux d'être signalé maintenant.
    """
    p = ctx.project
    channels = int(getattr(p.settings, "sound_channels", 8))
    for m in getattr(p, "music", []):
        ap = p.asset_abs(m.asset) if getattr(m, "asset", None) else None
        if not (ap and ap.exists()):
            continue
        mod = ctx.module(ap)
        if mod is None:
            continue
        ch = mod.num_channels
        if ch > channels:
            ctx.warn(None,
                f"\"{m.name}\" uses {ch} voices, the project only has {channels} channels — the extra"
                " voices will stay silent. The number of channels is set in the "
                "project inspector.")


def _check_sound_boxes(ctx: ValidationContext):
    """Les trois boîtes sonores (ROADMAP v0.8.7).

    Depuis qu'elles sont trois assets, chaque boîte a son propre espace de
    noms : un même nom d'état dans une SoundBox et dans une JingleBox n'est
    plus ambigu, puisque l'appel Lua nomme la boîte. Ce qui reste refusé, c'est
    un doublon DANS une boîte — là, le build choisirait à la place de l'auteur.
    """
    p = ctx.project
    sfx_names = {s.name for s in getattr(p, "sfx", [])}
    music_names = {m.name for m in getattr(p, "music", [])}

    # Une boîte active par famille — la première par ordre de nom (v0.8.7).
    # Les autres existent dans le projet mais ne sonneront jamais.
    for store, label in ((getattr(p, "music_boxes", []), "MusicBox"),
                         (getattr(p, "jingle_boxes", []), "JingleBox"),
                         (getattr(p, "sound_boxes", []), "SoundBox")):
        boxes = sorted(store, key=lambda b: b.name)
        for extra in boxes[1:]:
            ctx.warn(None,
                f"{label} \"{extra.name}\": the game only loads one, \"{boxes[0].name}\" (the first by name order)."
                " This one will not be played.")
        for box in boxes:
            for dup in box.duplicate_state_names():
                ctx.error(None,
                    f"{label} \"{box.name}\": two states are named \"{dup}\" — the call would be "
                    "ambiguous. Rename one.")

    for box in getattr(p, "music_boxes", []):
        for st in box.states:
            if st.music and st.music not in music_names:
                ctx.warn(None,
                    f"MusicBox \"{box.name}\", state \"{st.name}\": music \"{st.music}\" does not exist — the "
                    "state will be silent.")

    for store, known, label, target in (
            (getattr(p, "sound_boxes", []), sfx_names, "SoundBox", "sound effect"),
            (getattr(p, "jingle_boxes", []), music_names, "JingleBox", "music")):
        for box in store:
            for st in box.states:
                for action, name in st.mapping.items():
                    if name and name not in known:
                        ctx.warn(None,
                            f"{label} \"{box.name}\", state \"{st.name}\": action \"{action}\" points to {target} "
                            f"\"{name}\", which does not exist.")

    # Une action posée sur une frame mais qu'aucune SoundBox ne déclare ne
    # résout vers rien : la frame est silencieuse, et rien ne le dirait.
    # Même chose pour un Sfx direct (`sfx_name`) qui ne correspond à aucun Sfx
    # du projet — les deux emplacements sont indépendants (ROADMAP v0.8.9).
    from core.models.sound_box import KIND_SOUND
    declared = set(p.sound_action_names(KIND_SOUND))
    for spr in getattr(p, "sprites", []):
        for stt in getattr(spr, "states", []) or []:
            for sd in getattr(stt, "directions", []) or []:
                _warned_action = _warned_sfx = False
                for fr in getattr(sd, "frames", []) or []:
                    action = getattr(fr, "action_name", "") or ""
                    if action and action not in declared and not _warned_action:
                        ctx.warn(None,
                            f"Sprite \"{spr.name}\", state \"{stt.name}\": the frame cites action "
                            f"\"{action}\", which no SoundBox declares — it will play "
                            "nothing.")
                        _warned_action = True
                    sfx_name = getattr(fr, "direct_sfx_name", "") or ""
                    if sfx_name and sfx_name not in sfx_names and not _warned_sfx:
                        ctx.warn(None,
                            f"Sprite \"{spr.name}\", state \"{stt.name}\": the frame cites Sfx "
                            f"\"{sfx_name}\", which does not exist — it will play nothing.")
                        _warned_sfx = True


def _check_frame_events(ctx: ValidationContext):
    """EventCall (`AnimFrame.event_name`) : le sprite est un asset PARTAGÉ, il
    ne sait pas quel actor l'anime — donc le nom ne se vérifie qu'ICI, contre
    le script de CHAQUE actor qui utilise ce sprite. Même philosophie que
    `action_name`/`sfx_name` : un nom qui ne résout vers rien est silencieux,
    pas une erreur bloquante (ROADMAP v0.8.9)."""
    p = ctx.project
    for actor in ctx.actors:
        script_comp = actor.get_component("script")
        if not script_comp or not script_comp.active or not script_comp.script:
            continue
        # Chaque apparence de l'acteur : un sprite inactif au départ s'animera
        # quand on l'activera, ses événements de frame appellent donc le même script.
        for sprite_comp in sprite_components(actor):
          sprite = p.get_sprite(getattr(sprite_comp, "sprite_name", "") or "")
          if not sprite:
            continue
          events = {
              getattr(fr, "event_name", "") or ""
              for stt in getattr(sprite, "states", []) or []
              for sd in getattr(stt, "directions", []) or []
              for fr in getattr(sd, "frames", []) or []
          } - {""}
          if not events:
            continue
          sp = p.asset_abs(script_comp.script)
          declared = ctx.script_functions(sp) if sp and sp.exists() else set()
          for ev in sorted(events):
            if ev not in declared:
                ctx.warn(actor,
                    f"Sprite \"{sprite.name}\" cites event \"{ev}\" on a frame, but the script of "
                    f"\"{actor.name}\" declares no function \"{ev}\" — the call will play nothing. "
                    f"Add `function {ev}(self) ... end` to the script, or remove the "
                    "call.")


def _check_sprite_appearances(ctx: ValidationContext):
    """Un porteur affiche UN sprite : ses `SpriteComponent` sont des apparences dont
    au plus une est active (marche 3 de « La struct Actor allégée »). Deux actives
    seraient ambiguës — le build en afficherait une seule, sans le dire. Vaut pour
    les acteurs de chaque scène, les prefabs poolés et leurs parties."""
    p = ctx.project

    def _check(owner, label):
        # Les `id` deviennent des constantes C (SPRITE_<ACTEUR>_<ID>) : deux ids
        # qui donnent le même identifiant ne se distingueraient plus à la compile.
        from codegen.c_names import c_ident
        seen: dict[str, str] = {}
        for c in sprite_components(owner):
            ident = c_ident(c.id)
            if ident in seen and seen[ident] != c.id:
                ctx.error(owner,
                    f"\"{label}\": ids \"{seen[ident]}\" and \"{c.id}\" give the same C constant "
                    f"(SPRITE_…_{ident}) — rename one of them.")
            seen.setdefault(ident, c.id)
        actives = [c for c in sprite_components(owner) if c.active and c.sprite_name]
        if len(actives) > 1:
            ctx.error(owner,
                f"\"{label}\" has {len(actives)} active appearances (sprite components) "
                f"({', '.join(c.id for c in actives)}): only one can be. Activating one deactivates the other — "
                "untick the others.")

    for scene in p.scenes:
        for actor in scene.actors:
            _check(actor, actor.name)
    for pf in p.prefabs:
        _check(pf, pf.name)
        for part in getattr(pf, "children", []) or []:
            _check(part, f"{pf.name}/{part.name}")


def _check_scene_font(ctx: ValidationContext):
    """`Scene.font_name` désigne la police que `scene_init` charge. Un nom qui
    ne répond pas retombe sur la police par défaut du projet (« Default Font »),
    ou la première police encodable à défaut — il FAUT charger quelque chose,
    sinon la scène n'affiche plus une lettre.

    Deux causes, deux messages : la police n'existe plus (renommée, supprimée),
    ou elle existe mais n'est pas encodable — sa planche manque, donc
    `project_fonts` la saute et le `#define FONT_*` n'existe pas non plus.
    Distinguer les deux évite de faire chercher un fichier pour un nom mort."""
    p = ctx.project
    from codegen.font_emit import project_fonts
    from codegen.font_emit import scene_default_font
    encodable = {f.name for f in project_fonts(p)}
    known = {f.name for f in getattr(p, "fonts", [])}
    project_default = getattr(getattr(p, "settings", None), "default_font", "") or ""
    if project_default and project_default not in encodable:
        ctx.warn(None,
            f"Project: the Default Font \"{project_default}\" is missing or unusable; the game will "
            "fall back to the first available font.")
    for lang in getattr(getattr(p, "settings", None), "languages", []):
        replacement = getattr(lang, "default_font", "") or ""
        if replacement and replacement not in encodable:
            ctx.warn(None,
                f"Language \"{lang.code}\": the Default Font \"{replacement}\" is missing or unusable; the "
                "game will keep the project's.")
    for scene in p.scenes:
        want = getattr(scene, "font_name", "") or ""
        if not want or want in encodable:
            continue           # vide = défaut du projet, choix légitime
        # Ce sur quoi la scène retombe VRAIMENT — même résolution que le build
        # (Default Font du projet, sinon première police).
        resolved = scene_default_font(p, scene)[1]
        repli = (f" — the scene falls back to \"{resolved}\"" if resolved
                 else " — the scene falls back to the first font of the project")
        if want in known:
            ctx.warn(None,
                f"Scene '{scene.name}': the default font \"{want}\" has no usable sheet (missing PNG"
                f" or no glyph), so it is not compiled{repli}.")
        else:
            ctx.warn(None,
                f"Scene '{scene.name}': the default font \"{want}\" does not exist in the "
                f"project{repli}.")


def _check_screen_space(ctx: ValidationContext):
    """Un acteur ancré à l'écran (`Actor.screen_space`) lit ses x/y en pixels
    d'ÉCRAN. Trois systèmes continuent, eux, de les lire comme des coordonnées
    de MONDE — sans rien casser au build, donc sans rien dire.

    On n'avertit que sur ces trois-là : chacun a une correction évidente, ce qui
    est la seule raison d'écrire un avertissement (cf. la règle de verbosité —
    l'éditeur rend le matériel, il ne le commente pas).

    Toutes les scènes, pas seulement l'active : le build les compile toutes."""
    p = ctx.project
    from core.models.ui_region import ANCHOR_ACTOR
    for scene in p.scenes:
        layouts = p.scene_ui_layouts(scene)
        for actor in getattr(scene, "actors", []) or []:
            if not getattr(actor, "screen_space", False):
                continue
            # ① Collision — la carte de collision est en pixels de monde. Une
            # hitbox posée à des coordonnées d'écran teste donc la mauvaise case.
            if any(type(c).__name__ == "CollisionBoxComponent"
                   for c in getattr(actor, "components", []) or []):
                ctx.warn(actor,
                    f"Scene '{scene.name}': '{actor.name}' is anchored to the screen but carries a "
                    "CollisionBox — the collision map is in WORLD pixels, so the "
                    "hitbox will test a different tile than the one you see. Remove "
                    "the CollisionBox, or the screen anchor.")
            # ② Caméra — suivre une position d'écran fige la caméra sur place.
            _cam = p.scene_camera(scene) if hasattr(p, "scene_camera") else None
            if (_cam is not None and _cam.mode == "follow"
                    and _cam.follow_target == actor.name):
                ctx.warn(actor,
                    f"Scene '{scene.name}': camera '{_cam.name}' follows '{actor.name}', which is anchored to "
                    "the screen — its position does not move with the world, so the "
                    "camera will stay still. Target a world actor.")
            # ③ Nœud Interface ancré SUR cet acteur — `text_region_origin()`
            # retranche la caméra pour une ancre acteur (elle la suppose dans le
            # monde) ; sur un acteur d'écran ça décale le nœud du scroll courant.
            # L'ancrage est celui du NŒUD (v0.25) : un avertissement par nœud, plus
            # par élément racine.
            for lay in layouts:
                if (getattr(lay, "anchor", "") == ANCHOR_ACTOR
                        and getattr(lay, "anchor_actor", "") == actor.name):
                    ctx.warn(actor,
                        f"Scene '{scene.name}': interface node '{lay.name}' is anchored on "
                        f"'{actor.name}', itself anchored to the screen — actor anchoring "
                        "assumes a world position and will subtract the scroll a "
                        "second time. Anchor the node to the SCREEN: both are already"
                        " in the same frame of reference.")


def _check_pal_bank_reference(ctx: ValidationContext):
    """Un asset (actor / prefab / layer BG) peut pointer une palette RÉFÉRENCÉE
    (pal_bank 0-15) dont le slot est hors de active_*_palettes, vide, ou dont la
    palette a été supprimée du catalogue. Ce n'est PAS bloquant — ça peut être
    délibéré (banque destinée à être remplie plus tard, palette-swap par slot) —
    mais l'asset s'affichera alors avec le contenu du slot tel quel en PAL RAM
    (souvent la palette de secours de la banque 0), donc de mauvaises couleurs.
    On avertit en nommant le type et le nom de l'asset concerné.

    Résolution des slots identique au build :
    - actors  -> active_obj_palettes de LEUR scène ;
    - prefabs -> active_obj_palettes de CHAQUE scène qui les poole (ROADMAP v0.17
      T7 : le spawn est per-scène, plus de « scène d'ancrage ») ;
    - layers  -> active_bg_palettes de chaque scène utilisant le background."""
    from core.models.palette import OWN_PAL_BANK
    from codegen.oam_alloc import scene_pool_instances
    p = ctx.project

    def _slot_missing(active: list, slot: int) -> bool:
        if not (0 <= slot < len(active)):
            return True
        name = active[slot]
        return not (name and p.get_palette(name))

    def _sprite_of(entity):
        # Le sprite CONSTRUIT d'une des apparences : la banque référencée vaut pour
        # toutes (elle est à l'acteur, pas à l'apparence).
        sprites = (p.get_sprite(c.sprite_name) for c in sprite_components(entity) if c.sprite_name)
        return next((sp for sp in sprites if sp and sp.asset), None)

    # ── Actors (par scène) ───────────────────────────────────────────
    for scene in p.scenes:
        active = getattr(scene, "active_obj_palettes", [])
        for actor in scene.actors:
            if not actor.active:
                continue
            pb = getattr(actor, "pal_bank", OWN_PAL_BANK)
            if pb == OWN_PAL_BANK:
                continue
            sp = _sprite_of(actor)
            if not (sp and sp.asset):
                continue  # pas de sprite construit -> pal_bank sans effet
            if _slot_missing(active, pb):
                ctx.warn(actor,
                    f"Actor '{actor.name}' points to OBJ bank {pb} of scene '{scene.name}', empty or "
                    "outside the active selection — the sprite will display with the "
                    "default content of that slot.")

    # ── Prefabs poolés : dans CHAQUE scène qui les spawne ────────────
    # Le spawn est per-scène (T1) : un prefab à palette référencée lit la banque
    # de LA scène qui le poole, pas d'une scène d'ancrage. Une banque manquante
    # dans une scène et présente dans une autre est donc un avertissement CIBLÉ
    # sur la scène fautive.
    for scene in p.scenes:
        active = getattr(scene, "active_obj_palettes", [])
        for pf in p.prefabs:
            if scene_pool_instances(scene, pf) <= 0:
                continue
            pb = getattr(pf, "pal_bank", OWN_PAL_BANK)
            if pb == OWN_PAL_BANK:
                continue
            sp = _sprite_of(pf)
            if not (sp and sp.asset):
                continue
            if _slot_missing(active, pb):
                ctx.warn(None,
                    f"Prefab '{pf.name}' points to OBJ bank {pb} of scene '{scene.name}' (which spawns"
                    " it), empty or outside the active selection — its instances will"
                    " display there with the default content of that slot.")

    # ── Layers BG (portés par la scène) ──────────────────────────────
    for scene in p.scenes:
        active = getattr(scene, "active_bg_palettes", [])
        for layer in scene.background_layers:
            if not layer.background_name:
                continue
            pb = getattr(layer, "pal_bank", OWN_PAL_BANK)
            if pb == OWN_PAL_BANK:
                continue
            if _slot_missing(active, pb):
                ctx.warn(None,
                    f"Background '{layer.background_name}' BG{layer.bg_slot} (scene '{scene.name}') points to BG bank {pb}, "
                    "empty or outside the active selection — the layer will display "
                    "with the default content of that slot.")


def _check_palette_bank_overflow(ctx: ValidationContext):
    """Chaque scene ne dispose que de 16 banques materielles par pool (OBJ /
    BG). Palettes referencees + palettes propres distinctes (assets en mode
    OWN) sont auto-allouees par palette_alloc ; si le total depasse 16, une
    ou plusieurs palettes propres ne trouvent pas de slot -> avertissement
    (non bloquant : ces assets retombent sur la banque 0 au build)."""
    from codegen.palette_alloc import scene_bank_layout
    p = ctx.project
    for scene in p.scenes:
        for pool, label in (("obj", "OBJ (sprites)"), ("bg", "BG (backgrounds)")):
            layout = scene_bank_layout(p, scene, pool)
            if layout.overflow():
                ctx.warn(None,
                    f"Scene '{scene.name}': more than 16 {label} palettes needed (referenced + own "
                    "palettes of assets without an assigned palette). Some assets "
                    "will fall back to bank 0 and display wrong colours — reduce the "
                    "number of distinct palettes or share referenced palettes.")
