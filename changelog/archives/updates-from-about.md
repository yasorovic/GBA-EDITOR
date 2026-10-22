# Les mises à jour depuis la fenêtre About — **LIVRÉ**

*Chantier important (0.2). Ancien nom : jalon v0.30.*

> **Livré le 2026-10-22** (ouvert le 2026-10-20). Voir *Reste à essayer* en fin de fichier.

### D'où vient la question

Le développement continu publie des releases (`release.yml` : installateur NSIS, ZIP portable,
AppImage), mais l'éditeur ne sait pas qu'une version plus récente existe. La fenêtre About envoie
vers GitHub pour les notes de version, et son rendu est incohérent : le texte des licences, coupé à
80 colonnes et centré à coups d'espaces, s'affiche en police proportionnelle, donc à la fois centré
et collé à gauche, avec la moitié droite de la fenêtre vide.

### Ce que ça livre

- **L'écran About garde ses boutons** (décision du 2026-10-21, qui remplace la fenêtre à onglets
  imaginée d'abord) : *Documentation*, *Release notes*, *Check for updates*, *Report an issue*,
  *Licenses*. *Release notes* et *Licenses* ouvrent chacune une fenêtre à onglets (`DocumentsDialog`) ;
  *Check for updates* sera sa propre fenêtre *Updates*.
- **Release notes** lit le `RELEASE_NOTES.md` livré avec l'application (hors ligne ; les notes de la
  version en cours seulement, le changelog complet n'est plus livré) ; plus de lien vers
  GitHub. Rendu Markdown, comme les notices tierces. Les textes de licence passent en police à
  chasse fixe.
- **Updates** : un bouton discret « Search for update », qui devient « Update to X » quand une
  version plus récente existe, avec ses notes au même format.
- **Une vérification automatique** au démarrage, en tâche de fond, au plus une fois par jour. Hors
  ligne, elle échoue sans bruit. Une mise à jour disponible se signale par un point discret, sans
  pop-up.
- **Une pop-up au lancement, seulement pour une mise à jour importante** (nouvelle fonctionnalité
  majeure, migration importante, changement d'API) : boutons *Voir*, *Plus tard*, *Ignorer cette
  version*, une seule fois par version, via le gabarit `ui/common/popup.py`.

### Décisions verrouillées (2026-10-20)

- **Le caractère « important » vient d'un `update.json`** attaché à la release
  (`{"importance": "major", "reasons": ["feature", "migration", "api"]}`), produit par
  `release.yml` à partir d'un fichier du dépôt. Pas de marqueur dans le corps de la release.
- **La vérification automatique est activée par défaut**, avec un réglage pour la couper. Chaque
  vérification est une requête HTTPS vers GitHub : GitHub voit l'adresse IP de l'utilisateur, la
  date et un `User-Agent` `Backstage/<version>`. Rien d'autre n'est envoyé (ni identifiant, ni
  chemin, ni contenu de projet, ni système). Il n'y a pas de serveur à nous, donc pas de
  télémétrie. L'onglet *Updates* le dit en une phrase.
- **`/releases/latest` ne convient pas** : il ignore les pré-versions, et nous sommes en `alpha`.
  On liste `/releases` et on filtre.
- **L'ordre des versions** suit `X.Y.Z-étiquette`, avec alpha < beta < stable à numéro égal.

### Déroulé

1. **Tranche 0, l'écran About** : **livrée le 2026-10-21** — fenêtres à onglets *Release notes* (le
   changelog embarqué par `nuitka_build.py`) et *Licenses* en chasse fixe, `LicensesDialog` devenue
   `DocumentsDialog`. Livré aussi : `core/update_check.py` (ordre des versions, lecture de `/releases`,
   `User-Agent`).
2. **Tranche 1 (livrée le 2026-10-21)** : `core/update_check.py` (délai d'un jour),
   `ui/common/update_checker.py` (état de la session, fil réseau, mémoire d'un lancement à l'autre
   dans le groupe de réglages `Updates`), vérification au démarrage lancée par `main.py` 5 s après
   l'affichage, point discret sur *Help ▸ About* et sur la ligne *Check for updates*, fenêtre *Updates*
   (`ui/common/updates_dialog.py` : notes de la version, « Update to X » qui ouvre la page de la release,
   case pour couper la vérification automatique, phrase sur ce qui est envoyé).
3. **Tranche 2 (livrée le 2026-10-21)** : `packaging/update.json` (`importance` `normal` ou `major`,
   `reasons` parmi `feature`, `migration`, `api`, obligatoire pour `major`), versionné avec
   `APP_VERSION`, validé par le job `version` de `release.yml` puis attaché à la release. La
   vérification **automatique** d'une version `major` ouvre une pop-up *View / Later / Ignore this
   version*, une seule fois par version ; *Ignore* retire le point de cette version. Un
   `update.json` absent ou illisible côté client = version ordinaire. **À ne pas oublier** : remettre
   le fichier à `normal` après une version importante.
4. **Tranche 3, « Update » (décidée et écrite le 2026-10-21, jamais essayée sur une vraie release)** :
   le bouton télécharge en tâche de fond (barre de progression), vérifie le SHA-256 contre un
   `SHA256SUMS` publié par `release.yml` (sans lui, rien n'est installé), puis : **installateur
   Windows** : ferme l'éditeur par son chemin normal (question « enregistrer ? » comprise), lance
   `setup.exe /S` détaché, qui attend la libération de `Backstage.exe`, installe et relance (drapeau
   d'environnement `BACKSTAGE_RELAUNCH`, `installer.nsi`) ; **ZIP portable et AppImage** : déposés dans
   « Téléchargements », dossier ouvert, rien de remplacé (ils ne peuvent pas se remplacer eux-mêmes) ;
   **lancé depuis les sources** : ouvre la page de la release. Code : `core/update_install.py`.
5. **Essayé le 2026-10-22** : la vérification, le point discret, la fenêtre *Updates* (rendu
   remanié : zone centrale de taille fixe, texte de confidentialité qui ne déplace plus rien) et
   « Update to X » lancé depuis les sources (ouvre la page de la release, comme prévu). **Jamais
   essayés** : la pop-up au lancement pour une version `major`, et le téléchargement réel depuis un
   build empaqueté.
6. **À faire avant de s'y fier** : publier une release de test (`0.1.1-alpha`) et dérouler le chemin
   complet (pop-up comprise) ; compiler `installer.nsi` (non compilé depuis la modification) ; vérifier SmartScreen
   sur un installateur téléchargé (non signé) ; remplacement automatique du ZIP portable et de
   l'AppImage, laissé de côté.
7. **Tests ciblés** : ordre des versions, lecture de `update.json`, délai entre deux vérifications.
   Pas de suite complète.
8. **Documentation et traductions** : ARCHITECTURE.md, libellés EN et FR, infobulles selon la
   charte. Le détail part ensuite dans `changelog/archives/v0.30.md`, une ligne au CHANGELOG et au
   README.

### Fichiers annoncés

`ui/common/about_dialog.py`, `core/app_info.py` (adresses), `window.py` (démarrage, signal),
`packaging/nuitka_build.py`, `.github/workflows/release.yml`, les deux `labels*.json`, ARCHITECTURE.md ;
création : le module de vérification, l'onglet *Updates*, ses tests.

### Questions laissées ouvertes

- **Jusqu'où va « Update »** (voir le déroulé, point 4).
- **Le binaire Nuitka sous Linux** : `urllib` en HTTPS y trouve-t-il les certificats ? Non
  vérifié ; le téléchargement des modèles utilise déjà `urllib` sans que ce point soit testé.

### Reste à essayer

Jamais essayés sur une vraie release : la pop-up au lancement pour une version `major`, et le
téléchargement réel depuis un build empaqueté (depuis les sources, « Update to X » ouvre la page
de la release). À faire aussi : compiler `installer.nsi`, vérifier SmartScreen sur un installateur
téléchargé. Une release de test (`0.1.1-alpha`) couvrira le tout.
