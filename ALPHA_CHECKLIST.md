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
  - *Fait* : fermeture (écritures en attente vidées), manifeste illisible, sidecar illisible, projet trop récent. Sidecar corrompu : la réconciliation l'écrasait avec un asset vierge, désormais copie `.corrupt` avant écriture (`tests/test_corrupt_sidecar_survives.py`). *Reste* : asset source manquant (PNG/audio), crash en pleine écriture (test).
- [ ] Un projet créé par l'alpha possède une version de format et s'ouvrira dans la beta (migration testée)
  - *Fait* : `format_version` = 1 écrit à chaque sauvegarde, refus clair d'un projet plus récent. *Reste* : projet-fixture alpha commité, rejoué à l'ouverture dès que la beta change un format.
- [ ] La CI est verte sur le commit exact de la release, tests natifs inclus ; les binaires Windows et Linux produits par la release démarrent au moins une fois
  - *Fait* : `--smoke-test` (crée un projet, visite les 8 écrans, valide, enregistre, contrôle les données embarquées) et son étape dans `release.yml`, Windows et Linux (xvfb). Joué depuis les sources : 10 sorties propres sur 10. *Reste* : premier passage CI réel sur un binaire Nuitka, et le test sur le commit exact du tag (point E).
- [ ] Installation et mise à jour validées : installation vierge, mise à jour sur une version antérieure, désinstallation sans toucher aux projets ni aux préférences
  - *Fait* : `packaging/windows/test_installer.ps1` (installation vierge, mise à jour par-dessus avec fichier obsolète et plugin utilisateur, désinstallation épargnant projets et config) et son étape CI. *Reste* : première exécution réelle ; je ne l'ai pas lancé ici (il écrit dans le registre et le menu Démarrer, et refuse de tourner hors CI sans `-AllowLocal`).
- [ ] Le contenu livré est réellement buildable : Starter et chaque démo publique ouvrent et produisent une ROM
- [ ] Version, nom, licences, notices tierces, limitations connues et canal de retour sont cohérents dans l'application, l'installateur et les notes de release
  - *Fait* : version, nom et auteur (source unique `app_info.py`, alignés par test dans l'application, l'installateur, le build et le workflow). Le nom est passé dans README, docs, ARCHITECTURE et notices. *Reste* : notices tierces à comparer à la distribution réelle, limitations connues, canal de retour (aucune adresse publique pour l'instant).

## A. Cohérence de l'UI
- [ ] Unifier la forme et la construction des tooltips, écran par écran
- [ ] Test sur les tooltips imposant le même modèle (échoue si un widget n'a pas de tooltip)
- [ ] Unifier les raccourcis clavier ; le tooltip de raccourci devient un type spécial, source unique de la liste
- [ ] **(+)** Écran/aide « Raccourcis clavier » généré depuis cette même source unique
- [ ] **(+)** Parité des libellés EN/FR (`labels_fr.json`), vérifiée par un test
- [ ] **(+)** Décider quels écrans restent en anglais seul pour l'alpha (v0.11 : 3/58 traduits au dernier état)
- [ ] **(+)** Vérifier l'affichage en mise à l'échelle Windows (125 %, 150 %) et en petite fenêtre

## B. Premier contact
- [x] Refaire le splash / sélecteur de projet : logo, numéro de version, lien de documentation
  - Accueil refait d'après maquette (`ui/home/project_picker.py`) : logo centré (`ui/common/logo.py`, texte du SVG converti en courbes, marge au cadre), onglets Projects / Templates centrés sur un filet de 2 px, projets en cartes, boutons Browse / Open / New project (icône `+`), bandeau Version · Created by · Online documentation. « Open project folder » est passé en clic droit sur un projet. *Reste* : lien notice IA (aucune adresse), captures d'écran de la doc.
- [x] **(+)** Mention « Alpha » visible (splash, titre de fenêtre) + lien de retour d'expérience
  - *Fait* : la version `1.0.0-alpha` (étiquette comprise) figure dans le bandeau de l'accueil et dans « À propos », qui porte « Report an issue » (`APP_ISSUES_URL`). *Reste* : rien dans le titre de fenêtre de l'éditeur ; à décider si nécessaire.
- [ ] Refaire l'écran « À propos » : version, licences (GPL éditeur / zlib runtime), liens
  - *Fait* (`ui/common/about_dialog.py`, remplace la boîte de message) : logo, pastille de version au thème, auteur, description, liens Documentation / Release notes / Report an issue (adresses dans `app_info.py`, un lien sans adresse n'est pas affiché). *Reste* : les licences (GPL éditeur / zlib runtime) et les notices tierces n'y figurent pas encore ; confirmer les adresses `APP_RELEASES_URL` et `APP_ISSUES_URL` (déduites du dépôt actuel).
- [x] État de la toolchain (devkitPro / mGBA) affiché dans la barre de l'éditeur ; sur l'accueil, seulement quand il manque quelque chose (le lien « Configure manually » disparaît alors quand tout est installé)
- [x] Build & Run sans devkitPro : message dédié qui explique pourquoi on ne peut pas builder maintenant et comment l'installer (au lieu d'une erreur de build)
  - `MainWindow._explain_missing_toolchain` : nomme ce qui manque, donne les deux liens, propose d'ouvrir les réglages (`tests/ui/test_missing_toolchain.py`). Avant, le bouton ouvrait les réglages sans un mot.
- [x] Installateur : rendre devkitPro visible à l'installation (à ce jour `installer.nsi` n'en parle pas), au minimum un lien ou une page d'information de fin d'installation
  - Page de fin : texte (devkitPro et mGBA non fournis) et lien « Installer devkitPro », FR et EN. Compilé avec `makensis` ; le rendu visuel n'a pas été regardé.
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
- [x] Polices du Starter (`misaki-gothic`, `unifont-jp`, `font8x8`) (l'éditeur utilise désormais la police système, plus rien à déclarer pour Inter) : licences déclarées dans `THIRD-PARTY-NOTICES.md` et livrées avec le binaire
  - Déclarées (tableau « Livrées dans le projet Starter ») et livrées : `project_starters/` est embarqué en entier, `licenses/` copié dans chaque projet. `tests/test_third_party_notices.py` exige que chaque notice du Starter soit citée.
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
- [ ] **(+)** Cas d'erreur lisibles : projet corrompu, asset manquant, build en échec (jamais de trace Python brute)
  - *Fait* : projet corrompu (manifeste), fichier illisible (avertissement à l'ouverture ET erreur bloquante du validateur, collections différées comprises), sprite cité mais disparu (erreur précise), palette au sidecar abîmé (palette gardée, copie `.corrupt`). Matrice de 19 scénarios rejouée. *Build en échec (rejoué avec de vraies pannes, devkitPro installé)* : PNG corrompu (n'était pas détecté, sortait en trace Python brute : refusé en validation), erreur de compilation C (lisible, ferme maintenant sur « [étape] a échoué (code N) »), ROM verrouillée (`Permission denied` cryptique : dite avant de compiler), panne imprévue (message + détail dans `crash.log`, plus de trace brute). *Reste* : fond manquant (avertissement « layer ignoré », choix de conception à confirmer), table de données supprimée, police dont la source a disparu (aucun message).
- [ ] **(+)** Test de non-régression pour chacun de ces cas d'erreur : message actionnable, journal conservé, application encore utilisable
  - *Fait* : `tests/test_project_robustness.py` (manifeste, sidecar, format récent), `tests/test_missing_assets.py` (sprite disparu, sidecars sprite/audio/palette abîmés, `.hex` illisible), `tests/test_corrupt_sidecar_survives.py`, `tests/test_build_failures.py` (7 cas : images illisibles, panne imprévue sans trace, étape et code d'un outil en échec, ROM verrouillée). *Reste* : vérifier que l'application reste utilisable après un build raté (test interface : bouton Build ré-armé, panneau hors état « en cours »).
- [x] Chemins Windows difficiles : espaces, accents, chemins longs, projet sur un autre disque (grit, make)
  - Builds ROM complets rejoués (sprite + fond + son) : espaces, symboles `( ) & ' # [ ] % $ !`, accents, japonais, projet sur C: avec éditeur sur E:. *Corrigé* : grit/mmutil/binutils reçoivent des chemins relatifs (le japonais échouait, le rapport de poids disparaissait), sortie d'outil non décodable (le thread de lecture mourait), chemin trop long (`WinError 267` + trace) → refus clair en amont (`path_too_long_message`, seuil mesuré : OK à 214, KO à 218). Tests : `tests/test_build_paths.py`.
  - *Limites connues* : un NOM DE FICHIER d'asset hors page de code (ex. `勇者.wav` passé à mmutil) n'est pas testé ; lecteur D: non testable ici (périphérique non prêt) ; l'ouverture de mGBA avec un chemin hors ASCII n'est pas testée ; à retester sur Linux.
- [x] Journal accessible depuis l'éditeur (pour les rapports de bug)
  - Menu Aide → « Ouvrir le dossier du journal » et « Copier les infos de diagnostic » (`core/diagnostics.py`, `tests/test_diagnostics.py`). Le rapport : machine, toolchain, projet (fichiers illisibles, sans contenu), fin de `crash.log`. La version vient maintenant de la source unique `app_info.py`.
- [x] **(+)** Sauvegarde : que se passe-t-il à la fermeture avec des modifications non enregistrées, ou après un crash ?
  - Autosave 400 ms + écriture atomique (`atomic_write`) ; à la fermeture `_confirm_close` vide les écritures en attente, et propose de rester si le disque refuse (`tests/ui/test_close_persists_pending.py`).
- [ ] **(+)** Décider et tester la récupération : auto-save, sauvegarde de secours ou message explicite ; vérifier qu'elle ne remplace jamais silencieusement la dernière sauvegarde valide
  - *Décision proposée, à valider* : pas de dossier `.recovery/` (autosave + écriture atomique suffisent). *Reste* : valider la décision, tester l'interruption en pleine écriture.
- [ ] **(+)** CI verte (Python 3.12, tests natifs compris)
- [ ] **(+)** La release relance ou exige ces contrôles sur le commit/tag exact publié (tests, contrôle d'architecture et dépendances), pas seulement sur une ancienne poussée de branche

## F. Distribution
- [x] **(+)** Nom et marque tranchés (risque Nintendo sur « GBA ») avant de figer logo et nom de l'installateur
  - **Backstage**, auteur **Yasorovic**, version **1.0.0-alpha** (`X.Y.Z-étiquette` : X version, Y jalon standard, Z chantier technique / correction / optimisation ; cf. ROADMAP). Source unique : `editor/core/app_info.py` (fenêtre, À propos, diagnostic, Nuitka, installateur, workflow, libellés). La version vit dans le dépôt, le tag la confirme : une release dont le tag diverge échoue (`nuitka_build.py`, job `version`). Tests : `tests/test_app_info.py`. Identifiants techniques renommés : dossier de config `%APPDATA%\Backstage`, `QSettings`, dossier de projets `~/BackstageProjects`, extension de projet `.project` (MIME `application/x-backstage-project`) ; README, docs, ARCHITECTURE et notices passés à « Backstage ». L'ancien nom du produit ne subsiste plus dans les fichiers (noms d'artefacts, changelogs, docs). Seul le nom du dépôt en ligne, dans les adresses, ne change qu'avec lui. Le dépôt reste le même : les liens du README et des docs, le menu Documentation et le téléchargement des modèles pointent vers lui ; les deux adresses de l'application vivent dans `app_info.py` (`APP_DOCS_URL`, `APP_TEMPLATES_URL`). **Aucune trace personnelle** : prénom, nom et e-mail retirés (35 mentions du prénom du code, de la ROADMAP et des changelogs, remplacées par « l'auteur »), vérifié par des recherches ponctuelles avant publication (aucun test dans le dépôt : un test de garde, même par empreintes, publierait de quoi confirmer un soupçon) ; les captures d'écran de la doc, qui montraient l'ancien nom dans la barre de titre, sont sorties du dépôt (déplacées dans un dossier voisin, hors de l'arbre publiable ; README sans image). *Reste* : logo, risque d'association `.project` avec Eclipse, **refaire des captures d'écran** avec la nouvelle interface, et **décider du sort de l'historique git** : ses 84 commits portent ton e-mail personnel en auteur, ce qui compte seulement si le dépôt est public (options : dépôt privé tel quel, réécriture de l'historique sur place, ou dépôt neuf — la CI tourne dans tous les cas).
- [ ] **(+)** Installateur testé sur machine propre (sans Python ni devkitPro) : lancement, création, build
  - Le runner CI est la machine propre : installation + smoke test (lancement et création de projet) en CI. Le *build* n'y est pas testé (devkitPro absent par construction) ; il est couvert hors installateur par les builds ROM headless.
- [ ] Mise à jour par-dessus une version existante : ne pas laisser de fichiers obsolètes de l'ancienne version (nettoyer avant copie), puis vérifier lancement et ouverture d'un projet existant
  - *Fait* : `CleanPreviousInstall` dans `installer.nsi` (purge avant copie, garde-fous : n'agit que si l'exe attendu est là, **conserve `plugins\`** où l'utilisateur dépose les siens, demande de fermer l'application si elle tourne). *Reste* : première exécution du test CI.
- [ ] **(+)** Désinstallation testée : enlève l'application et ses raccourcis, conserve explicitement projets et configuration utilisateur
  - Couvert par `test_installer.ps1` (applic., raccourci, clés, ProgID supprimés ; projets et config conservés). *Reste* : première exécution.
- [ ] **(+)** Vérifier les artefacts publiés, pas seulement le dossier de build : téléchargement, intégrité/antivirus si disponible, installation et lancement
- [x] Décider d'une page de licence à l'installation (non exigée par la GPL, `LICENSE` étant dans le dossier)
  - **Décision : pas de page de licence.** Elle ajouterait un clic sans rien exiger de plus ; `LICENSE` et `THIRD-PARTY-NOTICES.md` sont installés à la racine (vérifié par le test d'installateur et par le smoke test). À renverser si tu préfères la montrer.
- [ ] **(+)** `THIRD-PARTY-NOTICES.md` à jour avec le contenu réel de l'installateur
  - *Fait* : `freetype-py` (absent) et FreeType ajoutés avec la mention exigée par sa licence ; polices du Starter ; test qui compare `requirements.txt` aux notices. *Reste* : comparer à la distribution RÉELLE (DLL embarquées par Nuitka : Qt multimédia et FFmpeg éventuel, runtime Python), impossible sans un build Nuitka.
- [ ] **(+)** Dépôt propre, tag `v1.0.0-alpha` (égal à `APP_VERSION`, sinon la release échoue), notes de release

## Ordre proposé
1. Protection du travail et erreurs lisibles : sauvegarde/récupération, corruption, assets manquants, migration de format
2. Parcours de première heure : Starter, documentation, absence de toolchain et retours d'erreur Build & Run
3. Distribution : mise à jour propre, tests des artefacts empaquetés et machine propre
4. Porte CI/release : faire tourner les contrôles sur le tag publié et cocher la porte de sortie
5. Nom, marque, splash et notes de release ; puis les tooltips, raccourcis et enrichissements de démos non bloquants
