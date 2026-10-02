"""ui/script_editor/sidebar_panel.py — panneau gauche : sections EVENTS / API / RÉFÉRENCES."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QToolButton, QLineEdit
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from scripting.api import (KNOWN_EVENTS, KNOWN_SCENE_EVENTS, KNOWN_EVENTS_BY_KIND,
                           EVENT_REGISTRY as _EVENT_META,
                           DOMAIN_SCENE, DOMAIN_ACTOR, DOMAIN_PREFAB, DOMAIN_SFX, DOMAIN_FONT)
from scripting import api_snippets
from scripting.project_names import names_by_domain
from core.models.text import SEP
from core.text_markup import display_text
from ui.common.theme import C, T
from ui.common.labels import label
from ui.common.tooltip import tooltip
from .colors import _BG, _BG_HDR, _BORDER, _TEXT_DIM, _TEXT_NORM, _C_API, _C_REF, _C_EVENT, _C_BEHAVIOR
from .sidebar_widgets import (
    _Section, _EntryButton, _group_label,
    _BTN_BASE, _BTN_API, _BTN_REF, _BTN_BEHAVIOR, _BTN_EVENT_DEFINED, _event_tooltip,
)

class SidebarPanel(QWidget):
    """
    Panneau gauche du script editor avec 3 sections collapsibles :
    EVENTS / API / RÉFÉRENCES. Émet snippet_requested(str) à chaque clic.
    """

    snippet_requested = pyqtSignal(str)     # snippet à insérer dans l'éditeur
    stub_requested    = pyqtSignal(str)     # event name → insérer stub ou jumper

    def __init__(self, parent=None):
        super().__init__(parent)
        # Bornes larges = colonne « étirable » dans le QSplitter du Script Editor
        # (même esprit que les finders du Sprite Editor : min/max, pas de fixe).
        self.setMinimumWidth(190)
        self.setMaximumWidth(400)
        self.setStyleSheet(f"background:{_BG};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Filtre par nom — section, sous-section ou entrée (cf. _apply_filter).
        self._filter = QLineEdit()
        self._filter.setClearButtonEnabled(True)
        self._filter.setPlaceholderText(label("scrsb.filter_placeholder"))
        self._filter.setToolTip(tooltip(title=label("scrsb.filter_title"), body=label("scrsb.filter_tip")))
        self._filter.setStyleSheet(
            f"QLineEdit{{background:{_BG_HDR};color:{_TEXT_NORM};"
            f"border:none;border-bottom:1px solid {_BORDER};padding:4px 8px;}}")
        self._filter.textChanged.connect(self._apply_filter)
        outer.addWidget(self._filter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{_BG};border:none;")

        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        self._cl = QVBoxLayout(container)
        self._cl.setContentsMargins(0, 0, 0, 0)
        self._cl.setSpacing(0)

        # ── Section EVENTS ─────────────────────────────────────────
        self._sec_events = _Section(label("scrsb.events"), _C_EVENT)
        self._event_btns: dict[str, _EntryButton] = {}
        for ev in KNOWN_EVENTS:
            meta  = _EVENT_META.get(ev, {})
            btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                 icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
            btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
            self._sec_events.add_widget(btn)
            self._event_btns[ev] = btn
        self._cl.addWidget(self._sec_events)

        # ── Sections API — 8 sections, une par chose qu'on tient ──────
        # ROADMAP v0.16 : le rangement remplace les 3 grosses parties
        # (Gameplay/Scripting/Hardware) par une navigation unique par NOM. Les
        # anciennes catégories deviennent des sous-titres ; le moteur se replie
        # sous « Aller plus loin » — cf. api_reference.get_sections().
        self._api_sections: list[_Section] = []
        self._build_api_sections()
        for sec in self._api_sections:
            self._cl.addWidget(sec)

        # ── Section RÉFÉRENCES ──────────────────────────────────────
        self._sec_refs = _Section(label("scrsb.references"), _C_REF, expanded=False)
        self._cl.addWidget(self._sec_refs)

        self._cl.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _apply_filter(self, text: str = ""):
        query = text.strip().lower()
        for sec in (self._sec_events, *self._api_sections, self._sec_refs):
            sec.apply_filter(query)

    # ── Sections API (statiques, depuis api_reference.json) ───────────
    # Huit sections — une par CHOSE qu'on tient (ROADMAP v0.16). Les anciennes
    # catégories deviennent des SOUS-SECTIONS repliables, plus des
    # portes : la seule navigation est la section. Dans chacune, l'itération se
    # montre, le moteur suit sous « Go further ».

    def _api_button(self, entry: dict):
        from scripting.api_reference import make_tooltip
        # La sidebar montre le VERBE (`get("name")`) ; le clic insère la forme
        # complète (`actor:get("name")`), gardée dans le snippet.
        # Même règle pour `:` (méthode) et `.` (module, propriété).
        raw = entry['label']
        head = raw.split("(")[0]
        cut = max(head.rfind(":"), head.rfind("."))
        display = raw[cut + 1:] if cut >= 0 else raw
        snippet = entry.get("snippet", entry.get("label", ""))
        btn = _EntryButton(f"  {display}", _BTN_API, make_tooltip(entry))
        btn.search_text = raw.lower()      # la forme complète : « spawn » ou « actor » trouvent
        btn.clicked.connect(lambda _, s=snippet: self.snippet_requested.emit(s))
        return btn

    def _build_api_sections(self):
        from scripting.api_reference import get_sections
        for section in get_sections():
            sec = _Section(label(section["label"]), _C_API, expanded=False)
            # Une sous-section repliable par ancienne catégorie ; le moteur se
            # range dans la sienne, sous l'annotation « Go further » — pas un
            # troisième niveau de dépliage dans une colonne de 200 px.
            iteration = {grp["name"]: grp["entries"] for grp in section["iteration"]}
            engine = {grp["name"]: grp["entries"] for grp in section["engine"]}
            for name in [*iteration, *(n for n in engine if n not in iteration)]:
                sub = sec.sub_section(name)
                for entry in iteration.get(name, []):
                    sub.add_widget(self._api_button(entry))
                if name in engine:
                    sub.add_widget(_group_label(label("scrsb.go_further")))
                    for entry in engine[name]:
                        sub.add_widget(self._api_button(entry))
            self._api_sections.append(sec)

    # ── Références (dynamique, depuis le projet) ─────────────────────

    def set_project(self, project):
        """Recharge les sections dynamiques (RÉFÉRENCES) depuis le projet.

        Les snippets viennent d'`api_snippets.call()`, jamais d'une chaîne
        écrite ici : c'est ce qui empêche un bouton de survivre à la fonction
        qu'il appelle (`scene_goto`, `instantiate` — deux noms proposés ici
        pendant des mois alors qu'aucun n'existait dans le catalogue)."""
        self._sec_refs.clear_body()
        if not project:
            return
        # La sidebar liste TOUS les sprites et fonds : matérialise ces catalogues
        # différés (v0.24). On est ici à l'ouverture du Script Editor — un écran
        # dédié, pas l'ouverture du projet.
        project.load_sprites()
        project.load_backgrounds()

        # Les noms par domaine viennent de la source unique (`names_by_domain`),
        # celle que lit aussi l'autocomplétion — plus de liste dressée ici à côté
        # d'elle (ROADMAP v0.27, phase 3). Les sections riches (textes, zones)
        # gardent leur parcours propre : elles ont besoin des OBJETS, pas des
        # seuls noms.
        nbd = names_by_domain(project)

        def _ref_btn(label: str, snippet: str, tip: str) -> _EntryButton:
            btn = _EntryButton(f"  {label}", _BTN_REF, tip)
            btn.clicked.connect(lambda _, s=snippet: self.snippet_requested.emit(s))
            return btn

        def _tip(sig: str, desc: str, note: str = "") -> str:
            return tooltip(title=sig, body=desc, note=note)

        def _api_tip(api_name: str, snippet: str, extra: str = "") -> str:
            """Tooltip d'un bouton d'asset : l'appel tel qu'il sera inséré, la
            description de la fonction telle qu'elle vit dans `api.py`, puis ce
            que l'éditeur seul sait de l'asset."""
            return _tip(snippet, api_snippets.description(api_name), extra)

        def _add(sub, label: str, api_name: str, extra: str = "", **domains):
            sn = api_snippets.call(api_name, **domains)
            sub.add_widget(_ref_btn(label, sn, _api_tip(api_name, sn, extra)))

        # Scènes
        if nbd.get(DOMAIN_SCENE):
            sub = self._sec_refs.sub_section(label("scrsb.scenes"))
            for name in nbd[DOMAIN_SCENE]:
                _add(sub, name, "scene.switch", scene=name)

        # Actors — ceux de la scène active (cf. names_by_domain)
        if nbd.get(DOMAIN_ACTOR):
            sub = self._sec_refs.sub_section(label("scrsb.actors"))
            for name in nbd[DOMAIN_ACTOR]:
                _add(sub, name, "actor.get", label("scrsb.active_scene"), actor=name)

        # Prefabs
        if nbd.get(DOMAIN_PREFAB):
            sub = self._sec_refs.sub_section(label("common.prefabs"))
            for name in nbd[DOMAIN_PREFAB]:
                _add(sub, name, "actor.spawn", prefab=name)

        # Sprites
        sprites = list(project.sprites)
        if sprites:
            sub = self._sec_refs.sub_section(label("common.sprites"))
            for sp in sprites:
                _add(sub, sp.name, "self:play_anim", anim=sp.name)

        # Backgrounds — aucune API ne prend un nom de fond en argument (un fond
        # se pose dans la scène, pas dans un script) : la référence reste un
        # commentaire, et le dire évite de chercher la fonction manquante.
        bgs = list(project.backgrounds)
        if bgs:
            sub = self._sec_refs.sub_section(label("common.backgrounds"))
            for bg in bgs:
                sub.add_widget(_ref_btn(bg.name, f"-- BG: {bg.name}",
                    _tip(bg.name, label("scrsb.bg_ref"))))

        # ── Textes ─────────────────────────────────────────────────
        # Rangés par premier niveau de chemin : c'est l'arbre de l'écran Texte,
        # aplati à un niveau. Aller plus profond ici ferait des sous-sections de
        # deux entrées dans une colonne de 200 px — la recherche fine reste le
        # métier de l'écran Texte, la sidebar sert à INSÉRER.
        texts = list(getattr(project, "texts", []))
        if texts:
            sub = self._sec_refs.sub_section(label("common.texts"))
            _UNFILED = label('scrsb.unfiled')
            values = project.text_values()
            groups: dict[str, list] = {}
            for t in texts:
                groups.setdefault(t.path[0] if t.path else _UNFILED, []).append(t)
            for folder in sorted(groups):
                if len(groups) > 1:
                    sub.add_widget(_group_label(folder))
                for t in groups[folder]:
                    where = SEP.join(t.path) if t.path else _UNFILED
                    excerpt = display_text(t.content, values).replace("\n", " ⏎ ")[:60]
                    _add(sub, t.key, "text.draw", f"{where} · « {excerpt} »", text=t.key)

        # ── Zones de texte ─────────────────────────────────────────
        # Celles des nœuds `Interface` de la scène active (v0.25) — comme les
        # Actors, et pour la même raison : une zone d'une autre scène a des
        # coordonnées réelles mais aucune surface réservée là où on écrirait.
        slots = (project.scene_ui_slots(project.active_scene)
                 if project.active_scene and hasattr(project, "scene_ui_slots")
                 else [])
        if slots:
            sub = self._sec_refs.sub_section(label("scrsb.text_zones"))
            for layout, r in slots:
                # Une zone propose son texte d'aperçu ; un texte AUTHORÉ porte
                # directement sa clé, et reste adressable (cf. KIND_SLOTS) pour
                # être remplacé en cours de jeu.
                key = getattr(r, "preview_text", "") or getattr(r, "text_key", "") or ""
                doms = {"text": key} if key else {}
                # La zone s'écrit sur SON acquisition : interface:get("zone"):draw(...).
                sn = api_snippets.element_call(r.name, "text_region:draw", **doms)
                extra = (label('scrsb.interface_name', name=layout.name)
                         + (label('scrsb.preview_value', value=key) if key else ""))
                sub.add_widget(_ref_btn(r.name, sn, _api_tip("text_region:draw", sn, extra)))

        # ── Polices ────────────────────────────────────────────────
        if nbd.get(DOMAIN_FONT):
            sub = self._sec_refs.sub_section(label("common.fonts"))
            for name in nbd[DOMAIN_FONT]:
                _add(sub, name, "text.set_font", font=name)

        # SFX
        if nbd.get(DOMAIN_SFX):
            sub = self._sec_refs.sub_section(label("common.sfx"))
            for name in nbd[DOMAIN_SFX]:
                _add(sub, name, "sfx.play", sfx=name)

        # Scripts behaviors
        behaviors_dir = project.scripts_behaviors_dir
        scripts = sorted(behaviors_dir.glob("*.lua")) if behaviors_dir.exists() else []
        if scripts:
            sub = self._sec_refs.sub_section(label("scrsb.scripts"))
            for sp in scripts:
                rel = f"behaviors/{sp.stem}"
                sn  = f"local {sp.stem} = require(\"{rel}\")"
                sub.add_widget(_ref_btn(sp.name, sn,
                    _tip(f"require(\"{rel}\")",
                         label("scrsb.require_desc", name=sp.stem))))

        self._apply_filter(self._filter.text())

    # ── Mise à jour état events ───────────────────────────────────────

    def update_defined_events(self, defined: set[str]):
        for ev, btn in self._event_btns.items():
            btn.setText(f"  {ev}")
            if ev in defined:
                btn.setStyleSheet(_BTN_EVENT_DEFINED)
                btn.set_icon_color(_C_EVENT)
            else:
                btn.setStyleSheet(_BTN_BASE)
                btn.set_icon_color(_TEXT_DIM)

    # ── Adaptation contextuelle ───────────────────────────────────────

    def set_context(self, context: str):
        """Adapte les sections selon le type de script (actor/scene/behavior/unknown)."""
        self._event_btns.clear()
        self._sec_events.clear_body()

        if context == "behavior":
            # Remplace EVENTS par MODULE
            self._sec_events.set_title_and_color(label("scrsb.module"), _C_BEHAVIOR)

            hint = QLabel(label("scrsb.no_handlers"))
            hint.setFont(QFont(T.UI, T.XS))
            hint.setStyleSheet(f"color:{_TEXT_DIM};background:{_BG};padding:4px 8px;")
            hint.setWordWrap(True)
            self._sec_events.add_widget(hint)

            stub_text = "function M.name(actor, ...)"
            stub_btn = _EntryButton(f"  {stub_text}", _BTN_BEHAVIOR,
                tooltip(title=stub_text, body=label("scrsb.behavior_stub_tip")),
                icon_key="behavior_stub", icon_color=_C_BEHAVIOR)
            stub_btn.clicked.connect(
                lambda: self.snippet_requested.emit("function M.name(actor, ...)\n    \nend\n"))
            self._sec_events.add_widget(stub_btn)

            self._sec_refs.setVisible(False)
        else:
            # Restore EVENTS header style
            self._sec_events.set_title_and_color(label("scrsb.events"), _C_EVENT)
            self._sec_refs.setVisible(True)

            # Un script sans `self` (scène ou caméra) a ses propres points
            # d'entrée — une caméra n'a pas d'on_late_update.
            events_to_show = KNOWN_EVENTS_BY_KIND.get(context, KNOWN_EVENTS)
            for ev in events_to_show:
                meta  = _EVENT_META.get(ev, {})
                btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                     icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
                btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
                self._sec_events.add_widget(btn)
                self._event_btns[ev] = btn
