"""ResourceStore — collection générique de Resource persistée sur disque
(un fichier JSON par item, dans un dossier). Utilitaire d'I/O générique,
réutilisé par Project pour chacune de ses collections (scenes, sprites,
backgrounds, prefabs, sfx, music, fonts, palettes)."""

import json
import shutil
import time
from pathlib import Path
from typing import Generic, Iterator, Optional, Type, TypeVar

from core.models.ids import is_id, new_id
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
    Gère une collection de Resource d'un type donné, persistée dans des
    `<name><extension du type>` n'importe où sous `root` (tout `assets/` pour un projet : l'extension dit
    le type, l'auteur range ses assets comme il veut, `assets/sfx/platformer/coin.sfx` comme
    `assets/Persos/coin.sfx`), le contenu étant du JSON. Un NOUVEL asset naît dans `directory`. Se comporte
    comme une liste (itération, len, indexation, append) pour rester un drop-in
    replacement des anciennes `list[Actor]` / `list[Background]` etc.

    Le nom d'une ressource est le stem de son fichier et reste UNIQUE dans la
    collection, quel que soit le dossier : cf. `ResourceIndex` pour les homonymes.
    """

    def __init__(self, directory: Path, cls: Type[T], root: Optional[Path] = None):
        # `directory` : le dossier où naît un NOUVEL asset de ce type. `root` : sous quoi on cherche les assets
        # existants — tout `assets/` pour un projet, car l'extension dit le type et l'auteur range où il veut ;
        # le dossier seul si rien d'autre n'est dit.
        self.dir = directory
        self.root = root or directory
        self.cls = cls
        # Inventaire disque, indépendant des objets déjà matérialisés dans
        # ``items``. Aujourd'hui ``load`` continue de tout lire ; la phase
        # suivante pourra ne charger que l'entrée demandée sans changer le
        # contrat de nommage ni les chemins.
        self.suffix = cls.sidecar_extension
        self.index = ResourceIndex(self.root, self.suffix)
        self.items: list[T] = []
        self._pending_delete: list[T] = []
        # `.temp/` du projet : où partent les fichiers d'une ressource supprimée
        # (cf. core/resources/deleted_files). Absent, la suppression reste
        # différée jusqu'à la fermeture.
        self._bin = None
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

    def attach_bin(self, bin_) -> None:
        self._bin = bin_

    def _files_of(self, item: T) -> list[Path]:
        """Ce qui, sur le disque, fait exister `item` : son fichier d'asset. Sa SOURCE n'en fait pas partie :
        l'asset la pointe, supprimer l'asset ne la supprime pas."""
        return [self._path(item.name)]

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

    def id_of(self, name: str) -> str:
        """L'id de l'asset chargé nommé `name`, "" s'il n'est pas chargé. C'est la clé sous laquelle les
        dossiers d'éditeur rangent un asset : le nom change au renommage, l'id jamais."""
        item = next((i for i in self.items if i.name == name), None)
        return item.id if item is not None else ""

    def name_of(self, asset_id: str) -> str:
        """Le nom de l'asset chargé qui porte `asset_id`, "" s'il n'est pas chargé."""
        item = next((i for i in self.items if i.id == asset_id), None) if asset_id else None
        return item.name if item is not None else ""

    def scan_index(self, listing: list[Path] | None = None) -> None:
        """Actualise l'inventaire disque sans matérialiser les ressources."""
        self.index.scan(listing)

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
    def _path(self, name: str, folder: Optional[Path] = None) -> Path:
        """Le fichier de `name` : là où l'index le connaît, sinon un NOUVEAU fichier à la racine
        du dossier de la collection — ou dans `folder`, pour un asset qu'on y pose."""
        known = self.index.path_for(name)
        if known is not None:
            return known
        return (folder or self.dir) / f"{safe_filename(name)}{self.suffix}"

    # -- identité --
    def _ensure_id(self, item: T) -> None:
        """Donne un id à `item` s'il n'en a pas, ou s'il porte celui d'un AUTRE item de la collection
        (un duplicata qui a gardé l'id de son original)."""
        taken = {i.id for i in self.items if i is not item and is_id(i.id)}
        if not is_id(item.id) or item.id in taken:
            item.id = new_id(taken)

    @staticmethod
    def _with_id(data: dict, identity: str) -> dict:
        """`data` avec l'id juste après le nom (ou en tête) : le début d'un sidecar se lit « nom, id »."""
        out: dict = {}
        for key, value in data.items():
            if key == "id":
                continue
            out[key] = value
            if key == "name":
                out["id"] = identity
        return out if "id" in out else {"id": identity, **out}

    def _repair_ids(self) -> None:
        """Fin d'un chargement complet : un id manquant, invalide ou répété est remplacé, et le sidecar
        réécrit. C'est ce qui donne un id aux assets d'avant, et un nouveau à la copie d'un fichier faite
        dans l'Explorateur (le premier dans l'ordre des noms garde le sien)."""
        taken = {i.id for i in self.items if is_id(i.id)}
        seen: set[str] = set()
        changed: list[T] = []
        for item in self.items:
            if not is_id(item.id) or item.id in seen:
                item.id = new_id(taken)
                taken.add(item.id)
                changed.append(item)
            seen.add(item.id)
        for item in changed:
            try:
                self.save(item)
            except OSError:
                pass            # fichier verrouillé : l'id vit en mémoire, le prochain chargement réessaie

    def _give_id_if_missing(self, item: T) -> None:
        """Un asset lu seul (chargement paresseux) et sans id en reçoit un tout de suite : `_repair_ids`
        ne passe que sur un chargement complet, et l'asset ne doit pas rester sans identité en attendant."""
        if is_id(item.id):
            return
        try:
            self.save(item)
        except OSError:
            pass

    def _key(self, path: Path) -> str:
        """Comment on désigne un fichier dans `unreadable` et `preserved` : son chemin sous le dossier de
        la collection (`platformer/coin.sfx`), jamais son seul nom — deux dossiers peuvent avoir un `coin.sfx`."""
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.name

    def ignored_duplicates(self) -> dict[str, str]:
        """`{fichier: raison}` des sidecars que l'inventaire a ignorés parce qu'un homonyme moins profond
        l'emporte. Rien n'est renommé ni écrit : l'application les signale, l'auteur tranche."""
        out: dict[str, str] = {}
        for name, extras in self.index.duplicates.items():
            kept = self.index.path_for(name)
            for extra in extras:
                out[self._key(extra)] = (f"another sidecar named \"{name}\" is at \"{self._key(kept)}\" "
                                         f"and is the one in use")
        return out

    def path_of(self, item: T) -> Path:
        """Le JSON dans lequel CET item se sauvegarde.

        `item.name` décide du nom de fichier (cf. `_path`) : un appelant qui
        veut savoir si le sidecar d'une ressource existe doit le demander ici,
        et non le déduire du nom d'un fichier source voisin — les deux se
        ressemblent tant que personne n'a renommé, puis divergent en silence."""
        return self._path(item.name)

    def save(self, item: T, folder: Optional[Path] = None):
        """Écrit `item`. Un item déjà connu reste là où il est ; `folder` ne sert qu'à poser un NOUVEL
        asset ailleurs qu'à la racine du dossier de la collection (par exemple à côté de sa source)."""
        if folder is not None and self.index.path_for(item.name) is None:
            try:
                Path(folder).resolve().relative_to(self.root.resolve())
            except ValueError:
                raise ValueError(f"{folder} is outside {self.root}") from None
        path = self._path(item.name, folder)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._keep_unreadable(path)
        self._ensure_id(item)
        atomic_write(path, project_json.dumps(self._with_id(item.to_dict(), item.id)))
        self.index.record(item.name, path)

    def _keep_unreadable(self, path: Path) -> None:
        """Avant d'écrire PAR-DESSUS un fichier qu'on n'a pas su lire, en garde
        une copie à côté (`<nom>.json.corrupt`, numérotée si elle existe déjà).

        Le cas réel : le sidecar d'un sprite est abîmé, la planche PNG existe, la
        réconciliation recrée un sprite par défaut — et la sauvegarde suivante
        l'écrirait sur le fichier abîmé, dont le découpage et les animations
        auraient pu être récupérés à la main."""
        if self.unreadable.pop(self._key(path), None) is None or not path.exists():
            return
        backup = path.with_name(path.name + ".corrupt")
        n = 2
        while backup.exists():
            backup = path.with_name(f"{path.name}.corrupt{n}")
            n += 1
        shutil.copy2(path, backup)
        self.preserved[self._key(path)] = backup.name

    def save_all(self):
        # Un sidecar effacé HORS de l'éditeur (Explorateur, git) pendant que sa
        # ressource vivait en mémoire n'est pas à réécrire : chaque édition
        # écrit déjà son item (`save`), donc ce balayage ne ferait que
        # ressusciter, à la fermeture, ce que l'auteur vient de supprimer.
        for item in list(self.items):
            if self.drop_if_deleted_on_disk(item.name):
                continue
            self.save(item)

    def drop_if_deleted_on_disk(self, name: str) -> bool:
        """Oublie l'item `name` si son sidecar, connu de l'index, a disparu du
        disque. Rend True s'il a été retiré de la mémoire (rien n'est écrit)."""
        path = self.index.path_for(name)
        if path is None or path.exists():
            return False
        item = next((i for i in self.items if i.name == name), None)
        if item is None:
            return False
        self.remove(item)
        self.index.forget(name)
        return True

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
                item.id = str(d.get("id") or "")
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
                self.unreadable[self._key(f)] = f"{type(e).__name__}: {e}"
                print(f"[project] read error {self.cls.__name__} {f.name}: {e}")
        self._repair_ids()

    def load_one(self, name: str) -> Optional[T]:
        """Recharge un seul item depuis le disque et met à jour la liste en place."""
        path = self.index.path_for(name) or self._path(name)
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            new_item = self.cls.from_dict(d)
            new_item.id = str(d.get("id") or "")
            self.unreadable.pop(self._key(path), None)
            # Même règle qu'à `load` : le fichier nomme la ressource. Sans ça,
            # un sidecar dont le champ `name` a dérivé n'est jamais reconnu
            # comme celui qu'on recharge, et vient s'AJOUTER à la liste.
            if safe_filename(new_item.name) != safe_filename(name):
                new_item.name = name
            for i, item in enumerate(self.items):
                if item.name == name:
                    self.items[i] = new_item = self._adopt(item, new_item)
                    self.index.record(name, path)
                    self._give_id_if_missing(new_item)
                    return new_item
            self.items.append(new_item)
            self.index.record(name, path)
            self._give_id_if_missing(new_item)
            return new_item
        except Exception as e:
            self.unreadable[self._key(path)] = f"{type(e).__name__}: {e}"
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
        """Renomme `item` ET son fichier, qui reste dans son dossier."""
        old_path = self._path(item.name)
        if old_path.exists():
            old_path.unlink()
        self.index.forget(item.name)
        item.name = new_name
        self.save(item, old_path.parent)
