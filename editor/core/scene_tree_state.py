"""Métadonnées d'organisation du contexte Content du Scene Tree.

Ces données ne vivent volontairement pas dans `Scene.to_dict()` : elles ne
changent ni le jeu, ni le build, ni la hiérarchie runtime des acteurs. Le
fichier est un sidecar du projet, partageable avec le projet si souhaité, mais
sans aucune incidence sur la ROM.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from core.models.ids import new_id
from core.resources.resource_store import atomic_write
from core.models import project_json


@dataclass(frozen=True)
class ContentFolder:
    id: str
    name: str
    members: tuple[str, ...]
    color: str = ""


class SceneTreeState:
    """Lit et écrit les dossiers virtuels, indexés par scène et par clé durable.

    Une clé est descriptive (``actor:Hero``, ``camera:Main``, ``ui:HUD``),
    jamais un chemin dans le QTreeWidget ; les renommages portés par l'arbre
    sont migrés au moment du geste. Les sous-arbres d'acteurs et d'UI
    restent donc déterminés par le modèle de jeu ; un dossier ne fait que
    choisir le parent visuel de leur racine.
    """

    _VERSION = 1

    def __init__(self, project_root: Path):
        self._path = Path(project_root) / "project" / "editor" / "scene-tree.json"
        self._data = {"version": self._VERSION, "scenes": {}}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        scenes = raw.get("scenes") if isinstance(raw, dict) else None
        if isinstance(scenes, dict):
            self._data = {"version": self._VERSION, "scenes": scenes}

    def _folder_ids(self) -> set[str]:
        """Tous les ids de dossier du fichier, toutes scènes confondues : un id
        tiré n'en recouvre aucun."""
        return {str(f.get("id")) for entry in self._data["scenes"].values()
                if isinstance(entry, dict) and isinstance(entry.get("folders"), list)
                for f in entry["folders"] if isinstance(f, dict)}

    def _scene_data(self, scene_name: str) -> dict:
        scenes = self._data["scenes"]
        entry = scenes.setdefault(scene_name, {})
        if not isinstance(entry.get("folders"), list):
            entry["folders"] = []
        if not isinstance(entry.get("hidden_members"), list):
            entry["hidden_members"] = []
        if not isinstance(entry.get("hidden_folders"), list):
            entry["hidden_folders"] = []
        return entry

    def folders(self, scene_name: str) -> list[ContentFolder]:
        folders = []
        for raw in self._scene_data(scene_name)["folders"]:
            if not isinstance(raw, dict):
                continue
            folder_id = str(raw.get("id") or "")
            name = str(raw.get("name") or "")
            members = raw.get("members") or []
            if folder_id and name and isinstance(members, list):
                folders.append(ContentFolder(folder_id, name, tuple(map(str, members)),
                                             str(raw.get("color") or "")))
        return folders

    def create_folder(self, scene_name: str, name: str) -> ContentFolder:
        clean = name.strip() or "Folder"
        raw = {"id": new_id(self._folder_ids()), "name": clean, "members": [], "color": ""}
        self._scene_data(scene_name)["folders"].append(raw)
        self.save()
        return ContentFolder(raw["id"], clean, (), "")

    def rename_folder(self, scene_name: str, folder_id: str, name: str) -> bool:
        clean = name.strip()
        if not clean:
            return False
        raw = self._folder(scene_name, folder_id)
        if raw is None or raw.get("name") == clean:
            return False
        raw["name"] = clean
        self.save()
        return True

    def delete_folder(self, scene_name: str, folder_id: str) -> bool:
        folders = self._scene_data(scene_name)["folders"]
        before = len(folders)
        folders[:] = [f for f in folders if not isinstance(f, dict) or f.get("id") != folder_id]
        if len(folders) == before:
            return False
        entry = self._scene_data(scene_name)
        entry["hidden_folders"] = [fid for fid in entry["hidden_folders"]
                                   if fid != folder_id]
        self.save()
        return True

    def move_member(self, scene_name: str, member: str, folder_id: str | None) -> bool:
        """Place un élément dans un dossier, ou dans Non classés avec None."""
        changed = False
        target = self._folder(scene_name, folder_id) if folder_id else None
        if folder_id and target is None:
            return False
        for raw in self._scene_data(scene_name)["folders"]:
            if not isinstance(raw, dict):
                continue
            members = list(raw.get("members") or [])
            if member in members:
                raw["members"] = [m for m in members if m != member]
                changed = True
        if target is not None and member not in target["members"]:
            target.setdefault("members", []).append(member)
            changed = True
        if changed:
            self.save()
        return changed

    def folder_of(self, scene_name: str, member: str) -> str | None:
        for folder in self.folders(scene_name):
            if member in folder.members:
                return folder.id
        return None

    # ── Visibilité d'ÉDITION ───────────────────────────────────────

    def member_visible(self, scene_name: str, member: str) -> bool:
        """Visibilité dans le Canvas, indépendante des données de jeu.

        Un membre peut être masqué individuellement ; son dossier peut aussi
        l'être. Les deux informations restent dans le sidecar de l'éditeur.
        """
        entry = self._scene_data(scene_name)
        if member in entry["hidden_members"]:
            return False
        folder_id = self.folder_of(scene_name, member)
        return folder_id not in entry["hidden_folders"]

    def folder_visible(self, scene_name: str, folder_id: str) -> bool:
        return folder_id not in self._scene_data(scene_name)["hidden_folders"]

    def set_member_visible(self, scene_name: str, member: str, visible: bool) -> bool:
        entry = self._scene_data(scene_name)
        hidden = entry["hidden_members"]
        if visible:
            if member not in hidden:
                return False
            hidden.remove(member)
        elif member not in hidden:
            hidden.append(member)
        else:
            return False
        self.save()
        return True

    def set_folder_visible(self, scene_name: str, folder_id: str, visible: bool) -> bool:
        if self._folder(scene_name, folder_id) is None:
            return False
        hidden = self._scene_data(scene_name)["hidden_folders"]
        if visible:
            if folder_id not in hidden:
                return False
            hidden.remove(folder_id)
        elif folder_id not in hidden:
            hidden.append(folder_id)
        else:
            return False
        self.save()
        return True

    def set_folder_color(self, scene_name: str, folder_id: str, color: str) -> bool:
        """Couleur de repérage d'un dossier, vide pour revenir au neutre."""
        raw = self._folder(scene_name, folder_id)
        clean = color.strip()
        if raw is None or raw.get("color", "") == clean:
            return False
        raw["color"] = clean
        self.save()
        return True

    def rename_member(self, scene_name: str, before: str, after: str) -> None:
        if before == after:
            return
        changed = False
        for raw in self._scene_data(scene_name)["folders"]:
            if not isinstance(raw, dict):
                continue
            members = raw.get("members") or []
            rewritten = [after if m == before else m for m in members]
            if rewritten != members:
                raw["members"] = list(dict.fromkeys(rewritten))
                changed = True
        entry = self._scene_data(scene_name)
        hidden = entry["hidden_members"]
        rewritten_hidden = list(dict.fromkeys(after if m == before else m for m in hidden))
        if rewritten_hidden != hidden:
            entry["hidden_members"] = rewritten_hidden
            changed = True
        if changed:
            self.save()

    def prune(self, scene_name: str, valid_members: set[str]) -> None:
        """Oublie les références d'éléments supprimés, jamais les dossiers."""
        changed = False
        for raw in self._scene_data(scene_name)["folders"]:
            if not isinstance(raw, dict):
                continue
            members = list(raw.get("members") or [])
            kept = [m for m in members if m in valid_members]
            if kept != members:
                raw["members"] = kept
                changed = True
        entry = self._scene_data(scene_name)
        hidden = entry["hidden_members"]
        kept_hidden = [member for member in hidden if member in valid_members]
        if kept_hidden != hidden:
            entry["hidden_members"] = kept_hidden
            changed = True
        if changed:
            self.save()

    def _folder(self, scene_name: str, folder_id: str | None) -> dict | None:
        if not folder_id:
            return None
        return next((f for f in self._scene_data(scene_name)["folders"]
                     if isinstance(f, dict) and f.get("id") == folder_id), None)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self._path, project_json.dumps(self._data))
