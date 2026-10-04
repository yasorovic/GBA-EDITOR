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
  - *Fait* : boîte « Construction impossible pour l'instant » (outils manquants, liens, accès aux réglages). *Reste* : la rejouer de bout en bout sur une machine réellement sans devkitPro (ici la détection retombe sur `C:/devkitPro`).
- [ ] Aucun scénario courant ne perd du travail : modifications non enregistrées, fermeture, crash, fichier de projet incomplet ou asset manquant ont un comportement décidé et testé
  - *Fait* : fermeture (écritures en attente vidées), manifeste illisible, sidecar illisible, projet trop récent. Sidecar corrompu : la réconciliation l'écrasait avec un asset vierge, désormais copie `.corrupt` avant écriture (`tests/test_corrupt_sidecar_survives.py`). Asset source manquant (PNG de sprite, son, musique) : avertissement, l'acteur se joue sans sprite et le son n'est pas joué ; le build a été rejoué avec ces fichiers supprimés et produit une ROM. *Reste* : crash en pleine écriture (test) ; une erreur bloquante le jour où un script pourra citer directement le fichier source (impossible en Lua aujourd'hui).
- [ ] Un projet créé par l'alpha possède une version de format et s'ouvrira dans la beta (migration testée)
  - *Fait* : `format_version` = 1 écrit à chaque sauvegarde, refus clair d'un projet plus récent. *Reste* : projet-fixture alpha commité, rejoué à l'ouverture dès que la beta change un format.
- [ ] La CI est verte sur le commit exact de la release, tests natifs inclus ; les binaires Windows et Linux produits par la release démarrent au moins une fois
  - *Fait* : `--smoke-test` (crée un projet, visite les 8 écrans, valide, enregistre, contrôle les données embarquées) et son étape dans `release.yml`, Windows et Linux (xvfb). Joué depuis les sources : 10 sorties propres sur 10. *Reste* : premier passage CI réel sur un binaire Nuitka, et le test sur le commit exact du tag (point E).
- [ ] Installation et mise à jour validées : installation vierge, mise à jour sur une version antérieure, désinstallation sans toucher aux projets ni aux préférences
  - *Fait* : `packaging/windows/test_installer.ps1` (installation vierge, mise à jour par-dessus avec fichier obsolète et plugin utilisateur, désinstallation épargnant projets et config) et son étape CI. *Reste* : première exécution réelle ; je ne l'ai pas lancé ici (il écrit dans le registre et le menu Démarrer, et refuse de tourner hors CI sans `-AllowLocal`).
- [ ] Le contenu livré est réellement buildable : Starter et chaque démo publique ouvrent et produisent une ROM
- [ ] Version, nom, licences, notices tierces, limitations connues et canal de retour sont cohérents dans l'application, l'installateur et les notes de release
  - *Fait* : version, nom et auteur (source unique `app_info.py`, alignés par test dans l'application, l'installateur, le build et le workflow). Le nom est passé dans README, docs, ARCHITECTURE et notices. *Reste* : notices tierces à comparer à la distribution réelle, limitations connues, canal de retour (aucune adresse publique pour l'instant).

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
  - *Fait* : `CleanPreviousInstall` dans `installer.nsi` (purge avant copie, garde-fous : n'agit que si l'exe attendu est là, **conserve `plugins\`** où l'utilisateur dépose les siens, demande de fermer l'application si elle tourne). *Reste* : première exécution du test CI.
- [ ] **(+)** Désinstallation testée : enlève l'application et ses raccourcis, conserve explicitement projets et configuration utilisateur
  - Couvert par `test_installer.ps1` (applic., raccourci, clés, ProgID supprimés ; projets et config conservés). *Reste* : première exécution.
- [ ] **(+)** Vérifier les artefacts publiés, pas seulement le dossier de build : téléchargement, intégrité/antivirus si disponible, installation et lancement
- [ ] **(+)** `THIRD-PARTY-NOTICES.md` à jour avec le contenu réel de l'installateur
  - *Fait* : `freetype-py` (absent) et FreeType ajoutés avec la mention exigée par sa licence ; polices du Starter ; test qui compare `requirements.txt` aux notices. *Reste* : comparer à la distribution RÉELLE (DLL embarquées par Nuitka : Qt multimédia et FFmpeg éventuel, runtime Python), impossible sans un build Nuitka.
- [ ] **(+)** Dépôt propre, tag `v1.0.0-alpha` (égal à `APP_VERSION`, sinon la release échoue), notes de release

## Ordre proposé
1. Protection du travail et erreurs lisibles : sauvegarde/récupération, corruption, assets manquants, migration de format
2. Parcours de première heure : Starter, documentation, absence de toolchain et retours d'erreur Build & Run
3. Distribution : mise à jour propre, tests des artefacts empaquetés et machine propre
4. Porte CI/release : faire tourner les contrôles sur le tag publié et cocher la porte de sortie
5. Nom, marque, splash et notes de release ; puis les raccourcis et enrichissements de démos non bloquants
