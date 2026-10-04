# Checklist avant la sortie de la v1.0-alpha

Document de travail (suivi par git : à publier ou non, à décider). La référence produit reste `ROADMAP.md`
(section « Ce qu'une v1.0-alpha exige »). Ici : le concret à cocher.

Légende : **(+)** = point ajouté par Claude, à valider.

## Porte de sortie — « on peut publier »

Ces points sont des **bloquants** : tous doivent être cochés avant le tag. Les
rubriques suivantes servent à les rendre vérifiables ; elles ne sont pas toutes
du même niveau d'urgence.

- [ ] Parcours complet sur machine propre : installer → créer ou ouvrir Starter → modifier → sauvegarder → fermer/réouvrir → Build & Run
- [ ] Même parcours sans devkitPro : l'éditeur démarre et explique clairement comment rendre le Build possible, sans trace Python ni impasse
  - *Fait* : boîte « Construction impossible pour l'instant » (outils manquants, liens, accès aux réglages), alignée sur la boîte d'erreur inattendue (`ui/common/toolchain_dialog.py`, même mascotte et même disposition). Le bouton Build, grisé quand devkitPro ou mGBA manque, reste cliquable : le clic ouvre cette boîte puis les réglages de la toolchain (sans scène, il reste désactivé). Trois états pour devkitPro (`Toolchain.devkitpro_state`) : ✓ complet, **✗ jaune** si le dossier est trouvé mais que des outils manquent (installation interrompue : cas réellement rencontré, paquets GBA jamais téléchargés), ✗ rouge si introuvable ; le jaune apparaît dans la barre (avec une infobulle qui nomme les outils manquants), l'accueil et les réglages, où un bouton « Vérifier l'installation » relance la détection et la consigne de réparation est affichée (pas de bouton dans la barre : une infobulle n'est pas cliquable). La boîte a été vue en vrai avec les outils manquants (grit, make, arm-none-eabi-gcc) lors du test de l'installateur. La détection (`Toolchain.check()`, ~220 ms) est mise en cache, invalidée par `recheck()` (réglages modifiés, boutons « Vérifier l'installation », clic sur Build quand des outils manquent) : l'interface la relisait à chaque rafraîchissement, jusqu'à ~600 ms de blocage par changement de l'arbre du projet. *Reste* : rejouer le parcours complet (installer → ouvrir Starter → clic sur Build → réglages) sur une machine réellement sans devkitPro, et revoir l'aspect de la nouvelle boîte avec les vraies polices (capture hors écran sans polices seulement).
- [ ] Aucun scénario courant ne perd du travail : modifications non enregistrées, fermeture, crash, fichier de projet incomplet ou asset manquant ont un comportement décidé et testé
  - *Fait* : fermeture (écritures en attente vidées), manifeste illisible, sidecar illisible, projet trop récent. Sidecar corrompu : la réconciliation l'écrasait avec un asset vierge, désormais copie `.corrupt` avant écriture (`tests/test_corrupt_sidecar_survives.py`). Asset source manquant (PNG de sprite, son, musique) : avertissement, l'acteur se joue sans sprite et le son n'est pas joué ; le build a été rejoué avec ces fichiers supprimés et produit une ROM. *Reste* : crash en pleine écriture (test) ; une erreur bloquante le jour où un script pourra citer directement le fichier source (impossible en Lua aujourd'hui).
- [ ] Un projet créé par l'alpha possède une version de format et s'ouvrira dans la beta (migration testée)
  - *Fait* : `format_version` = 1 écrit à chaque sauvegarde, refus clair d'un projet plus récent. *Reste* : projet-fixture alpha commité, rejoué à l'ouverture dès que la beta change un format.
- [ ] La CI est verte sur le commit exact de la release, tests natifs inclus ; les binaires Windows et Linux produits par la release démarrent au moins une fois
  - *Fait* : `--smoke-test` (crée un projet, visite les 8 écrans, valide, enregistre, contrôle les données embarquées) et son étape dans `release.yml`, Windows et Linux (xvfb). Joué depuis les sources : 10 sorties propres sur 10. *Reste* : premier passage CI réel sur un binaire Nuitka, et le test sur le commit exact du tag (point E).
- [ ] Installation et mise à jour validées : installation vierge, mise à jour sur une version antérieure, désinstallation sans toucher aux projets ni aux préférences
  - *Fait* : `packaging/windows/test_installer.ps1` (installation vierge, mise à jour par-dessus avec fichier obsolète et plugin utilisateur, désinstallation épargnant projets et config) et son étape CI. *Vérifié à la main par l'auteur sur l'installateur Nuitka* : installation vierge et désinstallation. *Reste* : **la mise à jour par-dessus une version antérieure (non testée)** et la première exécution réelle du script (il écrit dans le registre et le menu Démarrer, et refuse de tourner hors CI sans `-AllowLocal`).
- [ ] Le contenu livré est réellement buildable : Starter et chaque démo publique ouvrent et produisent une ROM
- [ ] Version, nom, licences, notices tierces, limitations connues et canal de retour sont cohérents dans l'application, l'installateur et les notes de release
  - *Fait* : version, nom et auteur (source unique `app_info.py`, alignés par test dans l'application, l'installateur, le build et le workflow). Le nom est passé dans README, docs, ARCHITECTURE et notices. *Reste* : notices tierces (comparées au build installé, il reste les textes de licence manquants), limitations connues, canal de retour (aucune adresse publique pour l'instant).

## B. Premier contact
- [ ] **(+)** Smoke test du binaire empaqueté : lancement, création/ouverture de projet et affichage correct avant de publier l'artefact
  - Écrit et branché en CI (cf. porte de sortie). Il a révélé un vrai défaut : le processus **plantait à la sortie** (violation d'accès) 4 fois sur 6, la fenêtre étant détruite après la `QApplication`. Corrigé dans `main.py` (`_shutdown_qt`) : 10 sorties propres sur 10. *Reste* : l'exécuter sur le binaire Nuitka. Le rendu « affichage correct » n'est pas vérifié par ce test.
- [ ] **(+)** Projets récents sur le splash (avec chemin manquant géré proprement)
- [ ] **(+)** Temps de démarrage : le coût de ~1,65 s mesuré venait d'Inter ; remesurer maintenant qu'on est sur la police système

## C. Contenu qui enseigne
- [ ] Améliorer le projet Starter : sprite de base, nine-slice, background
- [ ] Refaire la démo Pong
- [ ] Faire la démo Platformer, chaque chapitre du guide pointe vers une scène/un script précis
- [ ] **(+)** Test automatisé : ouvrir et builder chaque projet livré (Starter, Pong, Platformer) jusqu'à la ROM
- [ ] **(+)** Définir la liste exacte des démos publiques ; ne pas citer ni embarquer une démo qui n'a pas passé le test d'ouverture et de build
- [ ] Licence des assets des démos (Starter, Pong, Platformer) : origine et droits de redistribution notés pour chaque sprite, son et police
  - *Décision* : ces licences vivent dans les dossiers des projets template et démo (comme `licenses/` du Starter), pas dans le dépôt de l'éditeur ni dans `THIRD-PARTY-NOTICES.md`. *Reste* : les écrire dans chaque projet, au moment de les refaire.
  - *PongAdvanced* : `project/licenses/ASSETS.md` écrit en brouillon. **Bloquant pour la diffusion** : musiques et effets viennent du réseau Spriters Resource (extraits de jeux commerciaux, aucun droit de redistribution) → à remplacer par des assets libres avant de publier le modèle. Sprites, fond, palettes, scripts : origine à confirmer.
- [ ] **(+)** Décider si la démo tactique est livrée au public ou reste un banc d'essai interne

## D. Documentation
- [ ] Guide utilisateur relu de bout en bout depuis un Starter vierge
- [ ] Notice IA cohérente avec `SCRIPTING.md` et `api_reference`
- [ ] Où vivent les notices : `docs/` n'est pas embarqué dans l'installateur, donc les liens du splash pointent en ligne ou on embarque `docs/`
- [ ] **(+)** README / CHANGELOG / ROADMAP alignés sur la même version (aucun chantier technique au README/CHANGELOG)
- [ ] **(+)** Page « Limitations connues » : ce qui n'existe pas encore, pour éviter les faux bugs
- [ ] Modèle de rapport de bug : version, journal, projet minimal

## E. Robustesse
- [ ] **(+)** Vérification sur émulateur des chantiers en attente (acteur allégé) ; idéalement 2e émulateur ou vraie cartouche
- [ ] **(+)** Vérification à l'échelle sur un projet réel (dernier point ROADMAP)
- [ ] Format de projet versionné + chemin de migration alpha → beta (un projet alpha doit s'ouvrir en beta)
  - *Fait* : versionnage et refus d'un format plus récent (`format_version`, `ProjectFileError`). *Reste* : le chemin de migration lui-même, rien à migrer tant que la beta ne change pas de format.
- [ ] **(+)** Test de non-régression pour chacun de ces cas d'erreur : message actionnable, journal conservé, application encore utilisable
  - *Fait* : `tests/test_project_robustness.py` (manifeste, sidecar, format récent), `tests/test_missing_assets.py` (sprite disparu, sidecars sprite/audio/palette abîmés, `.hex` illisible), `tests/test_corrupt_sidecar_survives.py`, `tests/test_build_failures.py` (7 cas : images illisibles, panne imprévue sans trace, étape et code d'un outil en échec, ROM verrouillée). *Reste* : vérifier que l'application reste utilisable après un build raté (test interface : bouton Build ré-armé, panneau hors état « en cours »).
- [ ] **(+)** Décider et tester la récupération : auto-save, sauvegarde de secours ou message explicite ; vérifier qu'elle ne remplace jamais silencieusement la dernière sauvegarde valide
  - *Décision proposée, à valider* : pas de dossier `.recovery/` (autosave + écriture atomique suffisent). *Reste* : valider la décision, tester l'interruption en pleine écriture.
- [ ] **(+)** CI verte (Python 3.12, tests natifs compris)
- [ ] **(+)** La release relance ou exige ces contrôles sur le commit/tag exact publié (tests, contrôle d'architecture et dépendances), pas seulement sur une ancienne poussée de branche

## F. Distribution
- [ ] **(+)** Installateur testé sur machine propre (sans Python ni devkitPro) : lancement, création, build
  - Le runner CI est la machine propre : installation + smoke test (lancement et création de projet) en CI. Le *build* n'y est pas testé (devkitPro absent par construction) ; il est couvert hors installateur par les builds ROM headless.
- [ ] Mise à jour par-dessus une version existante : ne pas laisser de fichiers obsolètes de l'ancienne version (nettoyer avant copie), puis vérifier lancement et ouverture d'un projet existant
  - *Fait* : `CleanPreviousInstall` dans `installer.nsi` (purge avant copie, garde-fous : n'agit que si l'exe attendu est là, **conserve `plugins\`** où l'utilisateur dépose les siens, demande de fermer l'application si elle tourne). *Reste* : **jamais testé à la main** (installer deux fois, l'ancienne avec un fichier obsolète et un plugin utilisateur) ; première exécution du test CI.
- [x] **(+)** Désinstallation testée : enlève l'application et ses raccourcis, conserve explicitement projets et configuration utilisateur
  - Couvert par `test_installer.ps1` (applic., raccourci, clés, ProgID supprimés ; projets et config conservés). Essayée à la main par l'auteur : OK. *Reste* (non bloquant) : première exécution du script en CI.
- [ ] **(+)** Build depuis l'installé sans fenêtres de console parasites
  - *Constat* : sur la version installée (Nuitka, `--windows-console-mode=disable`, donc sans console), chaque outil lancé par un build (make, grit, gcc, bin2s, objdump) ouvrait puis fermait une fenêtre de console, en rafale. *Fait* : `core/tool_process.run_tool` (`CREATE_NO_WINDOW`, `stdin` fermé) utilisé par `rom_build._run_cmd`, l'étape `bin2s` et `rom_report` ; les `Popen` de mGBA et de l'éditeur externe, graphiques, ne sont pas concernés. *Reste* : **non vérifié sur un installé** (reconstruire l'installateur, lancer un build, constater l'absence de fenêtres).
- [ ] **(+)** Vérifier les artefacts publiés, pas seulement le dossier de build : téléchargement, intégrité/antivirus si disponible, installation et lancement
- [ ] **(+)** `THIRD-PARTY-NOTICES.md` à jour avec le contenu réel de l'installateur
  - *Fait* : `freetype-py` (absent) et FreeType ajoutés avec la mention exigée par sa licence ; polices du Starter ; test qui compare `requirements.txt` aux notices. *Comparé à l'installateur Windows réel* : ajoutés Python (PSF), FFmpeg (LGPL-2.1+, via Qt Multimédia), OpenSSL, libffi, OpenBLAS/LAPACK/GCC runtime (dans NumPy), runtime Visual C++, et les trois familles de polices QtAwesome oubliées (Material Design Icons, Phosphor, Remix Icon) ; Qt corrigé en 6.11.2. *Fait ensuite* : dossier `licenses/` livré par le build (LGPL-3.0, LGPL-2.1, Apache-2.0, PSF, textes des paquets Python), avec son index. *Revu sur le dossier du build Nuitka installé* (4 oct.) : les `.dll` et plugins correspondent au tableau ; ajoutés les bibliothèques liées dans les modules compilés (Pillow : brotli, FreeType, HarfBuzz, lcms2, libavif, libjpeg-turbo, libpng, libtiff, libwebp, OpenJPEG, xz, zlib-ng ; Python : expat, libmpdec, bzip2, liblzma ; Qt). **Constat** : ce build installé n'a PAS de dossier `licenses/` (il date d'avant l'ajout du `--include-data-dir` dans `nuitka_build.py`, et `licenses/` n'est pas encore suivi par git) : à revérifier sur le prochain build. *Reste* : (1) les textes encore absents, listés dans `licenses/README.md` (antlr4, libffi, expat/libmpdec/bzip2/liblzma, polices de QtAwesome, runtime Visual C++) ; (2) les versions du tableau « Bibliothèques Python » viennent d'un environnement local, seule celle de Qt est confirmée par le binaire : les générer depuis le build ou ne garder que la série ; (3) comparer l'AppImage Linux, qui embarque des bibliothèques système en plus.
- [ ] Habillage de l'installateur : image de la page d'accueil/fin (BMP 164×314, `MUI_WELCOMEFINISHPAGE_BITMAP` + `MUI_UNWELCOMEFINISHPAGE_BITMAP`), éventuellement bannière d'en-tête (BMP 150×57, `MUI_HEADERIMAGE_BITMAP`) ; en attente du visuel. *Fait* : titre de bienvenue raccourci (le nom seul ; la version passe dans le texte), titre de fin idem, `installer.nsi` compile ; rendu à regarder au prochain installateur.
- [ ] **(+)** Dépôt propre, tag `v1.0.0-alpha` (égal à `APP_VERSION`, sinon la release échoue), notes de release

## Hors périmètre de l'alpha
Défauts connus, non bloquants, volontairement laissés pour après l'alpha.

- **(+)** Flash blanc à l'ouverture de l'accueil et de la fenêtre principale (sources et installé ; les autres fenêtres ne sont pas touchées ; antérieur au diff de la toolchain, constaté par l'auteur). *Piste, non vérifiée* : Windows affiche le cadre natif (blanc) avant le premier rendu Qt, que la grosse feuille `GLOBAL_QSS` retarde ; la palette sombre est pourtant posée sur l'application (`main.py`). Rien dans `editor/` ne préchauffe ni ne masque ce premier affichage (`setWindowOpacity`, `grab`). *Correctif envisagé* : afficher à opacité 0, laisser Qt faire son premier rendu (`processEvents`), puis passer à 1 ; si le blanc persiste, regarder la barre de titre native (claire sur thème sombre).

## Ordre proposé
1. Protection du travail et erreurs lisibles : sauvegarde/récupération, corruption, assets manquants, migration de format
2. Parcours de première heure : Starter, documentation, absence de toolchain et retours d'erreur Build & Run
3. Distribution : mise à jour propre, tests des artefacts empaquetés et machine propre
4. Porte CI/release : faire tourner les contrôles sur le tag publié et cocher la porte de sortie
5. Nom, marque, splash et notes de release ; puis les raccourcis et enrichissements de démos non bloquants
