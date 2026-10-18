# Packaging, distribution et environnement de dev

Nuitka, NSIS, GitHub Releases, venv de dev figé sur la version CI. Extrait d'ARCHITECTURE.md.

## Packaging & distribution (Nuitka + NSIS + GitHub Releases)

À ne pas confondre avec le pipeline ROM ci-dessus : ceci construit l'**éditeur lui-même** en exécutable distribuable, pas une ROM GBA.

- **`packaging/nuitka_build.py`** — définition unique de la commande de build, utilisée à l'identique par la CI et en local (`python packaging/nuitka_build.py --version 0.3.2 --output-dir build-out`). Nuitka en mode **standalone** (dossier), pas onefile : l'installateur pose de toute façon un dossier, et le onefile ne ferait que ré-extraire à chaque lancement. Sortie : `build-out/Backstage/`.
- **`packaging/check_deps.py`** — relève les imports réels du code par AST et vérifie que `requirements.txt` les couvre tous. Lancé en CI **avant** le build : c'est le filet qui manquait quand `luaparser` est parti en release sans être déclaré.
- **`packaging/windows/installer.nsi`** — installateur NSIS **par utilisateur** (`%LOCALAPPDATA%\Programs\Backstage`, aucune élévation UAC, désinstallation sous HKCU). La désinstallation laisse volontairement en place les projets (`~/BackstageProjects`) et la config toolchain (`%APPDATA%\Backstage`).
- **`editor/core/app_paths.py`** — source unique de vérité pour « où tourne-t-on ». `IS_FROZEN` s'appuie sur `__compiled__` (le
  marqueur Nuitka ; **`sys._MEIPASS` n'existe pas** hors PyInstaller), et `APP_DIR` vaut le dossier de l'exe en distribution, la
  racine du repo depuis les sources. `RUNTIME_DIR` en dérive : tout module ayant besoin d'un chemin de données passe par ici.
- **`editor/core/app_info.py`** — source unique de « qui est ce logiciel » : `APP_NAME` (Backstage), `APP_AUTHOR` (Yasorovic), `APP_VERSION` (`X.Y.Z-alpha|beta|stable`, cf. ROADMAP, « La numérotation d'une release »). Stdlib seule, sans importation, pour que les scripts de packaging la lisent sur un Python nu. Y puisent la fenêtre, l'« À propos », le rapport de diagnostic, le dossier de config (`config_dir`), les `QSettings`, le build Nuitka (`--product-name`, `--company-name`, nom de l'exe), l'installateur et le workflow. **La version vit dans le dépôt, le tag la confirme** : `nuitka_build.py --version` échoue si le tag diverge, et le job `version` de la release lit `--print-version` ; un build qui écraserait le fichier d'après le tag ferait annoncer à un lancement depuis les sources une version qu'il n'a pas. `tests/packaging/test_app_info.py` garde l'alignement (installateur, build, workflow, libellés) et l'absence des anciens identifiants.
- **Disposition des données** — les données embarquées reproduisent l'arborescence des sources (`runtime/`, `plugins/`, `scripting/api_reference.json`), parce que les modules les résolvent via `Path(__file__).parent` et que Nuitka donne aux modules compilés un `__file__` cohérent dans la distribution. Les images référencées par les QSS ne sont **pas** embarquées : `ui/common/icons.py:qss_image()` les rend depuis qtawesome dans `%TEMP%/backstage_icons/` au démarrage (`ensure_qss_assets()`, appelé après la `QApplication` et avant `setStyleSheet`) — un cache en zone temporaire, donc toujours inscriptible même pour une installation en lecture seule.
- **`editor/plugins/`** est copié tel quel, **non compilé** : chargé dynamiquement via `importlib.util.spec_from_file_location`, ça nécessite des `.py` réels sur disque au runtime. Corollaire assumé : le code des plugins reste lisible dans la distribution, contrairement au reste.
- **`editor/smoke_test.py`** (`Backstage --smoke-test=<rapport>`) — ce que la CI exécute sur le binaire LIVRÉ avant de publier : crée un projet temporaire, le rouvre, **visite chaque écran** (importés paresseusement par leur nom : un module que Nuitka n'a pas vu n'échouerait qu'au premier clic), valide, enregistre, et contrôle les données embarquées (licences, runtime, starter, API, notices). Le verdict va dans un fichier : la distribution Windows est sans console. Sans devkitPro, il ne construit pas de ROM. **Sortie ordonnée** (`main._shutdown_qt`) : la fenêtre doit être détruite tant que la `QApplication` existe ; sinon le processus plantait à la sortie (violation d'accès, 4 fois sur 6 sous Windows) après avoir tout enregistré.
- **`packaging/windows/test_installer.ps1`** — joué par la CI sur le runner (machine propre) : installation silencieuse, mise à jour par-dessus (un fichier de l'ancienne version doit disparaître, un plugin de l'utilisateur rester), désinstallation (application, raccourci, clés supprimés ; projets et configuration conservés), smoke test après chaque installation. Il écrit dans HKCU et le menu Démarrer : il refuse de tourner hors CI sans `-AllowLocal`. Côté `installer.nsi`, `CleanPreviousInstall` purge l'ancienne installation avant la copie, **sauf `plugins\`**, et seulement si l'exécutable attendu est présent.
- **`.github/workflows/release.yml`** — se déclenche sur `release: published` (ou `workflow_dispatch` pour tester sans publier).
  Publie l'installateur Windows `.exe`, un ZIP portable et l'AppImage Linux (smoke test du fichier livré avant publication) ; le
  job `windows-rom-build` (build de ROM sous Windows, devkitPro installé en silence) est hors des `needs` tant qu'il n'a pas passé
  un `workflow_dispatch`. Le cache Nuitka est indispensable : un build à froid est nettement plus long.
- **mGBA / devkitPro ne sont jamais embarqués** — dépendances système externes, détectées à l'exécution par
  `editor/core/toolchain.py` (`resolve_mgba`, `resolve_grit`, `resolve_make`, `resolve_arm_gcc`). L'auto-téléchargement de mGBA a
  été tenté puis **abandonné délibérément** : flux 100% manuel par choix.

### Piège connu : Python de dev vs Python de CI

La CI et le build Nuitka figent Python 3.12 (évaluation immédiate des annotations) ; un poste en 3.14 les évalue
paresseusement (PEP 649). Une annotation non protégée vers une classe définie plus bas, ou un nom jamais importé, ne casse que
la CI. Remède : travailler dans le venv 3.12 ci-dessous, et citer entre guillemets toute référence en avant.

### Environnement de dev figé sur la version CI (`.venv-build312`)

Le poste tourne en Python 3.14, mais la CI **et** le build Nuitka figent 3.12 (bornes de `requirements.txt`). Pour travailler « avec ce qui sortira réellement au build » sans toucher à l'interpréteur du poste, on crée un venv 3.12 **dans le dossier du projet** — nom conventionnel `.venv-build312`, déjà ignoré par `.gitignore` (`.venv*/`) :

```powershell
py -3.12 -m venv .venv-build312
.venv-build312\Scripts\python.exe -m pip install --upgrade pip
.venv-build312\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

Deux variables d'environnement reproduisent la CI ; les omettre change le résultat :

- `QT_QPA_PLATFORM=offscreen` — PyQt6 sur une machine sans écran (sinon l'import échoue).
- `CC=C:\msys64\ucrt64\bin\gcc.exe` — sans compilateur C hôte, les tests d'équivalence Python/C sont **skippés**, et un skip natif est un **échec** en CI (`GBA_TESTS_REQUIRE_NATIVE=1`).

Contrôles locaux, identiques au job CI :

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:CC='C:\msys64\ucrt64\bin\gcc.exe'
.venv-build312\Scripts\python.exe tools\check_architecture.py --fresh
.venv-build312\Scripts\python.exe -m pytest tests -q
```

Un manque de **bibliothèque système Linux** (p. ex. `libpulse.so.0`, réclamée par `PyQt6.QtMultimedia` du mixer son) ne se voit **pas** dans ce venv Windows : il relève des workflows GitHub (listes `apt-get` de `tests.yml` / `release.yml`), pas de l'environnement Python local.

## Dépendances externes

- **Runtime Python** : PyQt6 (interface), Pillow (pipeline d'images), qtawesome (icônes, optionnel).
- **devkitPro** (toolchain GBA) : devkitARM (`arm-none-eabi-gcc`), grit (PNG → tuiles/palettes), libgba, mmutil (audio maxmod), make.
- **mGBA** : émulateur de Build & Run.

`PyQt6` et `Pillow` sont des paquets Python (voir `requirements.txt`). `devkitPro` et `mGBA` sont des outils système installés séparément — ils n'apparaissent pas dans un gestionnaire de paquets Python.
