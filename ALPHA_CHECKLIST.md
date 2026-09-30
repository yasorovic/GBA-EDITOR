# Checklist avant la sortie de la v1.0-alpha

Document de travail, non suivi par git. La référence produit reste `ROADMAP.md`
(section « Ce qu'une v1.0-alpha exige »). Ici : le concret à cocher.

Légende : **(+)** = point ajouté par Claude, à valider.

## Porte de sortie — « on peut publier »

Ces points sont des **bloquants** : tous doivent être cochés avant le tag. Les
rubriques suivantes servent à les rendre vérifiables ; elles ne sont pas toutes
du même niveau d'urgence.

- [ ] Parcours complet sur machine propre : installer → créer ou ouvrir Starter → modifier → sauvegarder → fermer/réouvrir → Build & Run
- [ ] Même parcours sans devkitPro : l'éditeur démarre et explique clairement comment rendre le Build possible, sans trace Python ni impasse
- [ ] Aucun scénario courant ne perd du travail : modifications non enregistrées, fermeture, crash, fichier de projet incomplet ou asset manquant ont un comportement décidé et testé
- [ ] Un projet créé par l'alpha possède une version de format et s'ouvrira dans la beta (migration testée)
- [ ] La CI est verte sur le commit exact de la release, tests natifs inclus ; les binaires Windows et Linux produits par la release démarrent au moins une fois
- [ ] Installation et mise à jour validées : installation vierge, mise à jour sur une version antérieure, désinstallation sans toucher aux projets ni aux préférences
- [ ] Le contenu livré est réellement buildable : Starter et chaque démo publique ouvrent et produisent une ROM
- [ ] Version, nom, licences, notices tierces, limitations connues et canal de retour sont cohérents dans l'application, l'installateur et les notes de release

## A. Cohérence de l'UI
- [ ] Unifier la forme et la construction des tooltips, écran par écran
- [ ] Test sur les tooltips imposant le même modèle (échoue si un widget n'a pas de tooltip)
- [ ] Unifier les raccourcis clavier ; le tooltip de raccourci devient un type spécial, source unique de la liste
- [ ] **(+)** Écran/aide « Raccourcis clavier » généré depuis cette même source unique
- [ ] **(+)** Parité des libellés EN/FR (`labels_fr.json`), vérifiée par un test
- [ ] **(+)** Décider quels écrans restent en anglais seul pour l'alpha (v0.11 : 3/58 traduits au dernier état)
- [ ] **(+)** Vérifier l'affichage en mise à l'échelle Windows (125 %, 150 %) et en petite fenêtre

## B. Premier contact
- [ ] Refaire le splash / sélecteur de projet : logo, numéro de version, lien notice d'utilisation, lien notice IA
- [ ] **(+)** Mention « Alpha » visible (splash, titre de fenêtre) + lien de retour d'expérience
- [ ] Refaire l'écran « À propos » : version, licences (GPL éditeur / zlib runtime), liens
- [x] État de la toolchain (devkitPro / mGBA) affiché en permanence dans la barre de l'éditeur et sur le splash
- [ ] Build & Run sans devkitPro : message dédié qui explique pourquoi on ne peut pas builder maintenant et comment l'installer (au lieu d'une erreur de build)
- [ ] Installateur : rendre devkitPro visible à l'installation (à ce jour `installer.nsi` n'en parle pas), au minimum un lien ou une page d'information de fin d'installation
- [ ] **(+)** Smoke test du binaire empaqueté : lancement, création/ouverture de projet et affichage correct avant de publier l'artefact
- [ ] **(+)** Projets récents sur le splash (avec chemin manquant géré proprement)
- [ ] **(+)** Temps de démarrage : le coût de ~1,65 s mesuré venait d'Inter ; remesurer maintenant qu'on est sur la police système

## C. Contenu qui enseigne
- [ ] Améliorer le projet Starter : sprite de base, nine-slice, background
- [ ] Refaire la démo Pong
- [ ] Faire la démo Platformer, chaque chapitre du guide pointe vers une scène/un script précis
- [ ] **(+)** Test automatisé : ouvrir et builder chaque projet livré (Starter, Pong, Platformer) jusqu'à la ROM
- [ ] **(+)** Définir la liste exacte des démos publiques ; ne pas citer ni embarquer une démo qui n'a pas passé le test d'ouverture et de build
- [ ] Licence des assets des démos (Starter, Pong, Platformer) : origine et droits de redistribution notés pour chaque sprite, son et police
- [ ] Polices du Starter (`misaki-gothic`, `unifont-jp`, `font8x8`) (l'éditeur utilise désormais la police système, plus rien à déclarer pour Inter) : licences déclarées dans `THIRD-PARTY-NOTICES.md` et livrées avec le binaire
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
- [ ] **(+)** Cas d'erreur lisibles : projet corrompu, asset manquant, build en échec (jamais de trace Python brute)
- [ ] **(+)** Test de non-régression pour chacun de ces cas d'erreur : message actionnable, journal conservé, application encore utilisable
- [ ] Chemins Windows difficiles : espaces, accents, chemins longs, projet sur un autre disque (grit, make)
- [ ] Journal accessible depuis l'éditeur (pour les rapports de bug)
- [ ] **(+)** Sauvegarde : que se passe-t-il à la fermeture avec des modifications non enregistrées, ou après un crash ?
- [ ] **(+)** Décider et tester la récupération : auto-save, sauvegarde de secours ou message explicite ; vérifier qu'elle ne remplace jamais silencieusement la dernière sauvegarde valide
- [ ] **(+)** CI verte (Python 3.12, tests natifs compris)
- [ ] **(+)** La release relance ou exige ces contrôles sur le commit/tag exact publié (tests, contrôle d'architecture et dépendances), pas seulement sur une ancienne poussée de branche

## F. Distribution
- [ ] **(+)** Nom et marque tranchés (risque Nintendo sur « GBA ») avant de figer logo et nom de l'installateur
- [ ] **(+)** Installateur testé sur machine propre (sans Python ni devkitPro) : lancement, création, build
- [ ] Mise à jour par-dessus une version existante : ne pas laisser de fichiers obsolètes de l'ancienne version (nettoyer avant copie), puis vérifier lancement et ouverture d'un projet existant
- [ ] **(+)** Désinstallation testée : enlève l'application et ses raccourcis, conserve explicitement projets et configuration utilisateur
- [ ] **(+)** Vérifier les artefacts publiés, pas seulement le dossier de build : téléchargement, intégrité/antivirus si disponible, installation et lancement
- [ ] Décider d'une page de licence à l'installation (non exigée par la GPL, `LICENSE` étant dans le dossier)
- [ ] **(+)** `THIRD-PARTY-NOTICES.md` à jour avec le contenu réel de l'installateur
- [ ] **(+)** Dépôt propre, tag `v1.0-alpha`, notes de release

## Ordre proposé
1. Protection du travail et erreurs lisibles : sauvegarde/récupération, corruption, assets manquants, migration de format
2. Parcours de première heure : Starter, documentation, absence de toolchain et retours d'erreur Build & Run
3. Distribution : mise à jour propre, tests des artefacts empaquetés et machine propre
4. Porte CI/release : faire tourner les contrôles sur le tag publié et cocher la porte de sortie
5. Nom, marque, splash et notes de release ; puis les tooltips, raccourcis et enrichissements de démos non bloquants
