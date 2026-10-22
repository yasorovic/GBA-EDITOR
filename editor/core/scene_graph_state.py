"""État d'éditeur du Graphe des scènes — positions des nœuds.

Le graphe reste DÉRIVÉ des appels `scene.switch` (cf. `scripting/scene_graph.py`) ;
ce sidecar ne porte QUE de la présentation : où un nœud est posé. Le **rangement**
des scènes en groupes n'est pas ici — c'est un dossier d'assets de la famille
`scenes`, capacité générale partagée avec la Scene library (cf.
`core/asset_folder_store.py`). Deux mécanismes de dossiers concurrents seraient
une seconde source de vérité ; il n'y en a qu'un.

Frère de `scene-tree.json` : sidecar atomique sous `project/editor/`, clé = nom
de scène, orphelins purgés à l'appel de `prune`. Aucun marqueur de cible absente
n'est jamais mémorisé : son identité est un littéral volatil, replacé à chaque
rendu.
"""
from __future__ import annotations

from pathlib import Path
import json

from core.resources.resource_store import atomic_write
from core.models import project_json


class SceneGraphState:
    """Lit et écrit le sidecar du graphe : positions des scènes, indexées par nom.

    Une position sans scène existante est purgée à `prune` : le sidecar ne
    garantit jamais une scène morte.
    """

    _VERSION = 3

    def __init__(self, project_root: Path):
        self._path = Path(project_root) / "project" / "editor" / "scene-graph.json"
        self._data: dict = {"version": self._VERSION, "scene_positions": {},
                            "missing_positions": {}, "scene_previews": {}, "edge_styles": {}, "edge_notes": {},
                            "groups": {}, "notes": {}}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        positions = raw.get("scene_positions") if isinstance(raw, dict) else None
        missing_positions = raw.get("missing_positions") if isinstance(raw, dict) else None
        previews = raw.get("scene_previews") if isinstance(raw, dict) else None
        edge_styles = raw.get("edge_styles") if isinstance(raw, dict) else None
        edge_notes = raw.get("edge_notes") if isinstance(raw, dict) else None
        groups = raw.get("groups") if isinstance(raw, dict) else None
        notes = raw.get("notes") if isinstance(raw, dict) else None
        self._data = {"version": self._VERSION,
                      "scene_positions": positions if isinstance(positions, dict) else {},
                      "missing_positions": missing_positions if isinstance(missing_positions, dict) else {},
                      "scene_previews": previews if isinstance(previews, dict) else {},
                      "edge_styles": edge_styles if isinstance(edge_styles, dict) else {},
                      "edge_notes": edge_notes if isinstance(edge_notes, dict) else {},
                      "groups": groups if isinstance(groups, dict) else {},
                      "notes": notes if isinstance(notes, dict) else {}}

    def scene_position(self, name: str) -> tuple[float, float] | None:
        raw = self._data["scene_positions"].get(name)
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            return (float(raw[0]), float(raw[1]))
        return None

    def positions(self) -> dict[str, tuple[float, float]]:
        """Toutes les positions de scènes connues, nom → (x, y)."""
        out: dict[str, tuple[float, float]] = {}
        for name, raw in self._data["scene_positions"].items():
            if isinstance(raw, (list, tuple)) and len(raw) == 2:
                out[str(name)] = (float(raw[0]), float(raw[1]))
        return out

    def set_scene_position(self, name: str, x: float, y: float) -> bool:
        current = self._data["scene_positions"].get(name)
        new = [float(x), float(y)]
        if isinstance(current, list) and current == new:
            return False
        self._data["scene_positions"][name] = new
        self.save()
        return True

    def replace_scene_positions(self, mapping: dict[str, tuple[float, float]]) -> None:
        """Réécrit TOUTES les positions — geste « Re-arrange ». Écrase l'existant :
        c'est le seul geste qui re-flue la carte et efface les placements manuels."""
        self._data["scene_positions"] = {
            str(name): [float(pos[0]), float(pos[1])] for name, pos in mapping.items()}
        self.save()

    def missing_position(self, name: str) -> tuple[float, float] | None:
        raw = self._data["missing_positions"].get(name)
        return (float(raw[0]), float(raw[1])) if isinstance(raw, (list, tuple)) and len(raw) == 2 else None

    def set_missing_position(self, name: str, x: float, y: float) -> bool:
        new = [float(x), float(y)]
        if self._data["missing_positions"].get(name) == new:
            return False
        self._data["missing_positions"][name] = new
        self.save()
        return True

    def prune_missing_positions(self, names: set[str]) -> None:
        table = self._data["missing_positions"]
        stale = [name for name in table if name not in names]
        if stale:
            for name in stale:
                del table[name]
            self.save()

    def rename_scene(self, before: str, after: str) -> None:
        """Migre la position ET l'aperçu — appelé par le choke point
        `Project.rename_scene`."""
        if before == after:
            return
        changed = False
        for key in ("scene_positions", "scene_previews"):
            table = self._data[key]
            if before in table:
                table[after] = table.pop(before)
                changed = True
        styles = self._data["edge_styles"]
        for key, style in list(styles.items()):
            source, separator, target = key.partition("\x1f")
            if not separator or (source != before and target != before):
                continue
            styles.pop(key)
            styles[self._edge_key(after if source == before else source,
                                  after if target == before else target)] = style
            changed = True
        notes = self._data["edge_notes"]
        for key, note in list(notes.items()):
            source, separator, target = key.partition("\x1f")
            if not separator or (source != before and target != before):
                continue
            notes.pop(key)
            notes[self._edge_key(after if source == before else source,
                                 after if target == before else target)] = note
            changed = True
        if changed:
            self.save()

    # ── Mode de rendu d'un nœud : condensé (défaut) ou aperçu du fond ──
    #
    # Choix PAR SCÈNE, piloté par la pastille du nœud. Présentation pure : ne
    # touche ni au jeu ni au build. Seules les scènes en aperçu sont mémorisées ;
    # une scène absente est condensée.

    def scene_preview(self, name: str) -> bool:
        return bool(self._data["scene_previews"].get(name, False))

    def set_scene_preview(self, name: str, on: bool) -> bool:
        previews = self._data["scene_previews"]
        if bool(previews.get(name, False)) == bool(on):
            return False
        if on:
            previews[name] = True
        else:
            previews.pop(name, None)   # défaut = condensé : on ne stocke pas les False
        self.save()
        return True

    # ── Tracé des arêtes ─────────────────────────────────────────────
    #
    # Une arête représente une transition dérivée du script ; seul son tracé
    # (droit ou courbe) est éditorial. La clé reste interne et non ambiguë même
    # si un nom de scène contient un séparateur visuel habituel.

    @staticmethod
    def _edge_key(source: str, target: str) -> str:
        return f"{source}\x1f{target}"

    def edge_style(self, source: str, target: str) -> str:
        """Style forcé : ``auto`` (défaut), ``straight`` ou ``curve``."""
        value = self._data["edge_styles"].get(self._edge_key(source, target))
        return value if value in {"straight", "curve"} else "auto"

    def set_edge_style(self, source: str, target: str, style: str) -> bool:
        if style not in {"auto", "straight", "curve"}:
            raise ValueError(f"Unknown edge style: {style}")
        styles = self._data["edge_styles"]
        key = self._edge_key(source, target)
        old = self.edge_style(source, target)
        if old == style:
            return False
        if style == "auto":
            styles.pop(key, None)
        else:
            styles[key] = style
        self.save()
        return True

    def edge_note(self, source: str, target: str) -> str:
        value = self._data["edge_notes"].get(self._edge_key(source, target), "")
        return value if isinstance(value, str) else ""

    def set_edge_note(self, source: str, target: str, note: str) -> bool:
        notes = self._data["edge_notes"]
        key, note = self._edge_key(source, target), str(note or "")
        if self.edge_note(source, target) == note:
            return False
        if note:
            notes[key] = note
        else:
            notes.pop(key, None)
        self.save()
        return True

    # ── Présentation d'un groupe dans le canvas du Graphe ──────────
    #
    # Indexée par ID de groupe (le dossier de `AssetFolderStore`). C'est de la
    # présentation du GRAPHE — repli et position de la boîte quand elle est
    # repliée ; l'appartenance des scènes, elle, vit dans le store de dossiers.

    def _group(self, group_id: str) -> dict:
        return self._data["groups"].setdefault(group_id, {})

    def group_collapsed(self, group_id: str) -> bool:
        """Une boîte est repliée par défaut — condenser est l'état d'accueil."""
        return bool(self._data["groups"].get(group_id, {}).get("collapsed", True))

    def set_group_collapsed(self, group_id: str, collapsed: bool) -> bool:
        if self.group_collapsed(group_id) == collapsed:
            return False
        self._group(group_id)["collapsed"] = bool(collapsed)
        self.save()
        return True

    def group_note(self, group_id: str) -> str:
        value = self._data["groups"].get(group_id, {}).get("note", "")
        return value if isinstance(value, str) else ""

    def set_group_note(self, group_id: str, note: str) -> bool:
        group, value = self._group(group_id), str(note or "")
        if self.group_note(group_id) == value:
            return False
        if value:
            group["note"] = value
        else:
            group.pop("note", None)
        self.save()
        return True

    def group_box_position(self, group_id: str) -> tuple[float, float] | None:
        raw = self._data["groups"].get(group_id, {}).get("box")
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            return (float(raw[0]), float(raw[1]))
        return None

    def set_group_box_position(self, group_id: str, x: float, y: float) -> bool:
        current = self._data["groups"].get(group_id, {}).get("box")
        new = [float(x), float(y)]
        if isinstance(current, list) and current == new:
            return False
        self._group(group_id)["box"] = new
        self.save()
        return True

    # Géométrie du CADRE déplié (x, y, largeur, hauteur) — distincte de `box`
    # (position de la boîte repliée). Déplié, le groupe est un rectangle que
    # l'auteur pose et dimensionne à la main ; il ne suit plus ses membres.

    def group_frame(self, group_id: str) -> tuple[float, float, float, float] | None:
        raw = self._data["groups"].get(group_id, {}).get("frame")
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            return tuple(float(v) for v in raw)  # type: ignore[return-value]
        return None

    def set_group_frame(self, group_id: str, x: float, y: float,
                        w: float, h: float) -> bool:
        current = self._data["groups"].get(group_id, {}).get("frame")
        new = [float(x), float(y), float(w), float(h)]
        if isinstance(current, list) and current == new:
            return False
        self._group(group_id)["frame"] = new
        self.save()
        return True

    # ── Notes libres du Graphe ───────────────────────────────────────
    #
    # Les notes ne représentent rien dans le jeu : elles vivent uniquement dans
    # le sidecar du graphe, avec leur géométrie et leur apparence éditoriales.

    def notes(self) -> dict[str, dict]:
        """Notes valides, indexées par identifiant stable."""
        out: dict[str, dict] = {}
        for note_id, value in self._data["notes"].items():
            if isinstance(value, dict):
                out[str(note_id)] = value.copy()
        return out

    def create_note(self, note_id: str, x: float, y: float) -> bool:
        if note_id in self._data["notes"]:
            return False
        self._data["notes"][note_id] = {"title": "Note", "text": "",
                                        "color": "#FFFFFF", "collapsed": False,
                                        "position": [float(x), float(y)]}
        self.save()
        return True

    def update_note(self, note_id: str, **values) -> bool:
        note = self._data["notes"].get(note_id)
        if not isinstance(note, dict):
            return False
        changed = False
        for key in ("title", "text", "color", "collapsed"):
            if key not in values:
                continue
            value = values[key]
            value = bool(value) if key == "collapsed" else str(value or "")
            if note.get(key) != value:
                note[key] = value
                changed = True
        if changed:
            self.save()
        return changed

    def note_position(self, note_id: str) -> tuple[float, float] | None:
        note = self._data["notes"].get(note_id, {})
        raw = note.get("position") if isinstance(note, dict) else None
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            return float(raw[0]), float(raw[1])
        return None

    def set_note_position(self, note_id: str, x: float, y: float) -> bool:
        note = self._data["notes"].get(note_id)
        value = [float(x), float(y)]
        if not isinstance(note, dict) or note.get("position") == value:
            return False
        note["position"] = value
        self.save()
        return True

    def delete_note(self, note_id: str) -> bool:
        if note_id not in self._data["notes"]:
            return False
        del self._data["notes"][note_id]
        self.save()
        return True

    def prune(self, valid_scene_names: set[str], valid_group_ids: set[str] | None = None) -> None:
        """Oublie les positions des scènes disparues, et — si `valid_group_ids`
        est fourni — la présentation des groupes disparus."""
        changed = False
        for key in ("scene_positions", "scene_previews"):
            table = self._data[key]
            for name in [n for n in table if n not in valid_scene_names]:
                del table[name]
                changed = True
        for table in (self._data["edge_styles"], self._data["edge_notes"]):
            for key in list(table):
                source, separator, target = key.partition("\x1f")
                if not separator or source not in valid_scene_names or target not in valid_scene_names:
                    del table[key]
                    changed = True
        if valid_group_ids is not None:
            groups = self._data["groups"]
            for gid in [g for g in groups if g not in valid_group_ids]:
                del groups[gid]
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self._path, project_json.dumps(self._data))
