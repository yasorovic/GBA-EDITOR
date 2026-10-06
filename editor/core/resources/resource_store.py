"""ResourceStore — collection générique de Resource persistée sur disque
(un fichier JSON par item, dans un dossier). Utilitaire d'I/O générique,
réutilisé par Project pour chacune de ses collections (scenes, sprites,
backgrounds, prefabs, sfx, music, fonts, palettes)."""

import json
import shutil
import time
from pathlib import Path
from typing import Generic, Iterator, Optional, Type, TypeVar

from core.models.resource import Resource
from core.models import project_json
from core.resources.resource_index import ResourceIndex, safe_filename

T = TypeVar("T", bound=Resource)


def atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Écrit `text` dans `path` de façon atomique (tmp → rename).

    Sous Windows, `os.replace` lève transitoirement PermissionError (WinError 5
    « accès refusé ») ou une sharing violation (WinError 32) quand un autre
    process tient brièvement un handle sur la cible : indexeur, antivirus, ou
    le QFileSystemWatcher qui ré-arme sa surveillance du dossier. C'est très
    probable lors de sauvegardes en rafale (maintien d'une flèche = nudge
    répété, molette continue sur un spinbox). Non rattrapée, l'exception
    remonte hors d'un slot Qt et PyQt6 abandonne le process → crash observé.
    On réessaie donc le rename quelques fois (le verrou transitoire se libère
    en quelques dizaines de ms) avant d'abandonner.

    Écriture SAUTÉE si le fichier contient déjà exactement `text` — même règle et
    même raison que `build_output.write` côté build. `project.save()` réécrit les
    quatorze collections à chaque Ctrl+S ; sur un projet réel, la quasi-totalité
    des assets n'a pas changé, et écrire à l'identique coûtait pour rien : un
    fichier temporaire et un rename par asset, chacun ré-armant le
    QFileSystemWatcher (donc rappelant la fenêtre de retry ci-dessus). Comparer
    au disque est une lecture, sans rename ni contention."""
    try:
        if path.read_text(encoding=encoding) == text:
            return
    except (OSError, UnicodeDecodeError):
        pass          # absent, illisible, ou d'un autre encodage : on écrit
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        for attempt in range(_REPLACE_RETRIES):
            try:
                tmp.replace(path)   # atomique sur NTFS/ext4
                return
            except PermissionError:
                if attempt == _REPLACE_RETRIES - 1:
                    raise
                time.sleep(_REPLACE_RETRY_DELAY)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# Rename atomique : nb de tentatives et délai entre elles (cf. atomic_write).
_REPLACE_RETRIES = 12
_REPLACE_RETRY_DELAY = 0.02   # 12 × 20 ms ≈ 240 ms de fenêtre de retry


class ResourceStore(Generic[T]):
    """
    Gère une collection de Resource d'un type donné, persistée dans
    `directory/<name>.json`. Se comporte comme une liste (itération,
    len, indexation, append) pour rester un drop-in replacement des
    anciennes `list[Actor]` / `list[Background]` etc.
    """

    def __init__(self, directory: Path, cls: Type[T]):
        self.dir = directory
        self.cls = cls
        # Inventaire disque, indépendant des objets déjà matérialisés dans
        # ``items``. Aujourd'hui ``load`` continue de tout lire ; la phase
        # suivante pourra ne charger que l'entrée demandée sans changer le
        # contrat de nommage ni les chemins.
        self.index = ResourceIndex(directory)
        self.items: list[T] = []
        self._pending_delete: list[T] = []
        # `.temp/` du projet : où partent les fichiers d'une ressource supprimée
        # (cf. core/resources/deleted_files). Absent, la suppression reste
        # différée jusqu'à la fermeture. `_extra_files` ajoute au sidecar les
        # fichiers SOURCES que seul le projet sait nommer.
        self._bin = None
        self._extra_files = None
        # {nom du fichier: raison} des JSON que `load` / `load_one` n'ont pas su
        # lire. Le fichier reste intact sur le disque ; l'application le dit
        # (cf. `Project.load_warnings`) au lieu de laisser l'asset disparaître.
        self.unreadable: dict[str, str] = {}
        # {nom du fichier: nom de la copie} des fichiers illisibles qu'une
        # écriture a remplacés : l'original vit dans la copie `.corrupt`.
        self.preserved: dict[str, str] = {}

    # -- accès liste --
    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx) -> T:
        return self.items[idx]

    def append(self, item: T) -> T:
        self.items.append(item)
        return item

    def remove(self, item: T):
        if item in self.items:
            self.items.remove(item)

    def __contains__(self, item) -> bool:
        return item in self.items

    def attach_bin(self, bin_, extra_files=None) -> None:
        self._bin = bin_
        self._extra_files = extra_files

    def _files_of(self, item: T) -> list[Path]:
        """Tout ce qui, sur le disque, fait exister `item`."""
        files = [self._path(item.name)]
        if self._extra_files is not None:
            files.extend(self._extra_files(item))
        return files

    # -- lookup --
    def _is_pending_delete(self, name: str) -> bool:
        return any(x.name == name for x in self._pending_delete)

    def get(self, name: str) -> Optional[T]:
        cached = next((i for i in self.items if i.name == name), None)
        if cached is not None:
            return cached
        # Un item en attente de suppression a son JSON ENCORE sur disque (effacé à
        # la fermeture) et son entrée dans l'index : sans cette garde, le premier
        # `get` l'y relisait — il revenait dans les listes, puis était réécrit à
        # la fermeture, d'où des « fausses suppressions » qui revenaient au
        # lancement suivant.
        if self._is_pending_delete(name):
            return None
        # L'index ne contient que les sidecars vus à l'ouverture ou lors d'une
        # écriture. Résoudre cette entrée seule est le chemin normal d'un canvas
        # qui cite un sprite ou un fond sans ouvrir son éditeur complet.
        return self.load_one(name) if self.index.path_for(name) else None

    def scan_index(self) -> None:
        """Actualise l'inventaire disque sans matérialiser les ressources."""
        self.index.scan()

    def known_names(self) -> tuple[str, ...]:
        """Noms vus au dernier scan ou à la dernière écriture du store."""
        return self.index.names()

    def ensure_loaded(self, name: str) -> Optional[T]:
        """Retourne ``name`` depuis le cache, ou le lit seul depuis le disque.

        Ce chemin est volontairement explicite : itérer un store ne doit jamais
        provoquer une lecture en masse cachée. ``Project`` l'emploie pour les
        références ponctuelles des collections différées.
        """
        if self._is_pending_delete(name):
            return None
        return self.get(name) or self.load_one(name)

    # -- I/O --
    def _path(self, name: str) -> Path:
        return self.dir / f"{safe_filename(name)}.json"

    def path_of(self, item: T) -> Path:
        """Le JSON dans lequel CET item se sauvegarde.

        `item.name` décide du nom de fichier (cf. `_path`) : un appelant qui
        veut savoir si le sidecar d'une ressource existe doit le demander ici,
        et non le déduire du nom d'un fichier source voisin — les deux se
        ressemblent tant que personne n'a renommé, puis divergent en silence."""
        return self._path(item.name)

    def save(self, item: T):
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(item.name)
        self._keep_unreadable(path)
        atomic_write(path, project_json.dumps(item.to_dict()))
        self.index.record(item.name, path)

    def _keep_unreadable(self, path: Path) -> None:
        """Avant d'écrire PAR-DESSUS un fichier qu'on n'a pas su lire, en garde
        une copie à côté (`<nom>.json.corrupt`, numérotée si elle existe déjà).

        Le cas réel : le sidecar d'un sprite est abîmé, la planche PNG existe, la
        réconciliation recrée un sprite par défaut — et la sauvegarde suivante
        l'écrirait sur le fichier abîmé, dont le découpage et les animations
        auraient pu être récupérés à la main."""
        if self.unreadable.pop(path.name, None) is None or not path.exists():
            return
        backup = path.with_name(path.name + ".corrupt")
        n = 2
        while backup.exists():
            backup = path.with_name(f"{path.name}.corrupt{n}")
            n += 1
        shutil.copy2(path, backup)
        self.preserved[path.name] = backup.name

    def save_all(self):
        for item in self.items:
            self.save(item)

    @staticmethod
    def _adopt(existing: T, fresh: T) -> T:
        """Fait de `existing` le reflet de `fresh`, SANS changer d'objet.

        Une ressource n'a qu'une identité en mémoire : l'écran qui l'édite, le
        canvas qui l'affiche et la sauvegarde globale tiennent tous LA MÊME
        instance. Remplacer l'objet au rechargement en créait une seconde, périmée
        pour ceux qui gardaient l'ancienne — l'éditeur modifiait l'une, la
        sauvegarde du projet écrivait l'autre par-dessus."""
        if not hasattr(existing, "__dict__") or not hasattr(fresh, "__dict__"):
            return fresh
        existing.__dict__.clear()
        existing.__dict__.update(fresh.__dict__)
        return existing

    def load(self):
        known = {item.name: item for item in self.items}
        self.items = []
        self.unreadable = {}
        self.scan_index()
        for name in self.index.names():
            f = self.index.path_for(name)
            if f is None:  # garde de type ; une entrée indexée a un chemin
                continue
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                item = self.cls.from_dict(d)
                # LE NOM DE FICHIER EST L'IDENTITÉ. `save` écrit toujours dans
                # `<name>.json` : un fichier qui ne porte pas le nom qu'il
                # contient a été renommé sur le disque, et c'est le champ qui
                # est périmé, pas le fichier. Le garder ferait exister la même
                # ressource sous deux identités — le rattrapage à l'ouverture
                # cherche l'asset par le STEM de son fichier source, ne le
                # trouverait pas, et en créerait un SECOND à côté du premier,
                # lequel pointe désormais dans le vide (cf.
                # asset_reconciliation.sync_font_file).
                if safe_filename(item.name) != f.stem:
                    item.name = f.stem
                if item.name in known:
                    item = self._adopt(known[item.name], item)
                self.items.append(item)
            except Exception as e:
                self.unreadable[f.name] = f"{type(e).__name__}: {e}"
                print(f"[project] read error {self.cls.__name__} {f.name}: {e}")

    def load_one(self, name: str) -> Optional[T]:
        """Recharge un seul item depuis le disque et met à jour la liste en place."""
        path = self.index.path_for(name) or self._path(name)
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            new_item = self.cls.from_dict(d)
            self.unreadable.pop(path.name, None)
            # Même règle qu'à `load` : le fichier nomme la ressource. Sans ça,
            # un sidecar dont le champ `name` a dérivé n'est jamais reconnu
            # comme celui qu'on recharge, et vient s'AJOUTER à la liste.
            if safe_filename(new_item.name) != safe_filename(name):
                new_item.name = name
            for i, item in enumerate(self.items):
                if item.name == name:
                    self.items[i] = new_item = self._adopt(item, new_item)
                    self.index.record(name, path)
                    return new_item
            self.items.append(new_item)
            self.index.record(name, path)
            return new_item
        except Exception as e:
            self.unreadable[path.name] = f"{type(e).__name__}: {e}"
            print(f"[project] reload error {self.cls.__name__} {name}: {e}")
            return None

    def delete(self, item: T):
        """Suppression immédiate (JSON effacé maintenant)."""
        path = self._path(item.name)
        if path.exists():
            path.unlink()
        self.index.forget(item.name)
        self.remove(item)
        self._pending_delete = [x for x in self._pending_delete if x is not item]

    def soft_delete(self, item: T):
        """Suppression différée : retire de la liste en mémoire, JSON effacé à la fermeture."""
        self.remove(item)
        if item not in self._pending_delete:
            self._pending_delete.append(item)
        if self._bin is not None:
            self._bin.stash(self._files_of(item))

    def restore(self, item: T):
        """Annule un soft_delete : remet l'item dans la liste et le resauvegarde."""
        self._pending_delete = [x for x in self._pending_delete if x is not item]
        if self._bin is not None:
            self._bin.restore(self._files_of(item))
        if item not in self.items:
            self.items.append(item)
        self.save(item)

    def pending_deletes(self) -> list[T]:
        """Les items `soft_delete`és pas encore committés — lecture seule.

        Une famille adossée à un fichier source les relit à la fermeture pour
        emporter AUSSI ce fichier, pas seulement le sidecar : sans quoi le
        `reconcile_*` le retrouverait au prochain lancement et recréerait la
        ressource (cf. project.commit_all_removals). Le store, lui, ne connaît
        que ses JSONs — il n'a pas à savoir ce qu'est un fichier source.

        Une suppression dont le NOM est repris depuis par un élément vivant
        n'est plus en attente : le fichier n'appartient plus à l'élément
        supprimé mais à son remplaçant. L'effacer à la fermeture détruisait le
        travail du remplaçant (supprimer `Scene_01`, en recréer une, fermer)."""
        live = {item.name for item in self.items}
        return [x for x in self._pending_delete if x.name not in live]

    def commit_deletes(self):
        """Efface définitivement les JSONs en attente (appeler à la fermeture)."""
        for item in self.pending_deletes():
            path = self._path(item.name)
            if path.exists():
                path.unlink()
            self.index.forget(item.name)
        self._pending_delete.clear()

    def rename(self, item: T, new_name: str):
        old_path = self._path(item.name)
        if old_path.exists():
            old_path.unlink()
        self.index.forget(item.name)
        item.name = new_name
        self.save(item)
