# Textes de l’interface

Les textes de l’éditeur vivent dans `editor/ui/common/labels/labels.json`
(libellés) et `notices/notices.json` (messages avec un ton). Le moteur commun
est `catalog.py`. Les textes des jeux restent dans les données du projet.

## Ajouter un texte

1. Ajouter une clé descriptive `<écran>.<message>` dans le maître anglais.
2. Appeler `label("clé", name=value)` à la construction ou au rafraîchissement
   du widget. Si une variable s'appelle déjà `label`, importer
   `from ui.common import labels as ui_labels` et appeler `ui_labels.label()`.
3. Écrire une phrase entière avec des paramètres nommés. Pour un compte,
   employer `singular` et `plural`, et fournir `n`, sans suffixe grammatical calculé.
4. Exécuter `python tools/check_ui_text.py`, puis les tests concernés.

Une entrée contient `text`, ou les deux formes `singular` / `plural`. Une notice
source possède aussi `tone` (`info`, `accent`, `build`, `render`) et peut porter
`code`, une expression technique non traduite. Une traduction ne remplace que
les textes et conserve leurs formes et paramètres. Une traduction manquante
est autorisée et revient à la source.

## Infobulles

L'affichage et le comportement passent par `ui/common/tooltip_controller.py`,
installé une seule fois au démarrage par `install_tooltips(app)`. Le style commun
fixe le délai de survol à **600 ms**, y compris entre deux contrôles ; la bulle
expire après **10 secondes**. Elle se ferme au clic, à la saisie clavier, au
défilement, à la désactivation de l'application, au masquage/destruction du
contrôle et quand le pointeur sort de l'élément concerné. Elle ne prend ni le
focus ni les événements de souris.

Une seule surface utilise les couleurs du thème, la police `T.SM`, un contour
arrondi et les mêmes marges. Le texte brut conserve ses retours à la ligne ; les
chemins sans espaces passent à la ligne. Largeur maximale : **420 pixels logiques**,
limitée à l'écran disponible. Une note dépassant sa hauteur est abrégée par « … ».
Le positionnement reste dans l'écran du pointeur, y compris près des bords.

Le contrôleur lit les `ToolTipRole` des cellules et des en-têtes, les aides des
onglets et les notes des items graphiques avant de consommer `QEvent.ToolTip`.
Ne pas se limiter à `obj.toolTip()` : cela masquait les infobulles des tableaux
et du canvas. Le mécanisme de rôles est celui de la
[documentation Qt](https://doc.qt.io/qt-6/qabstractitemdelegate.html#helpEvent).
Les contrôles conservent `setToolTip()` et les vues conservent leurs rôles Qt.

Pour un contenu calculé au survol (métadonnées Disk, segment de jauge ROM),
enregistrer `set_tooltip_provider(widget, callback)`. Le callback reçoit le point
local et renvoie `TooltipContent(texte, rectangle)` ; `None` revient au contenu
standard, un texte vide supprime la bulle. Le calcul reste paresseux, hors des
déplacements de souris. **Aucun appel direct à `QToolTip.showText/hideText` dans
les écrans** : ces appels contournaient le rendu commun et produisaient des bulles
natives au style et aux délais différents. La bulle commune est créée uniquement
au premier survol, sans fenêtre parasite à la construction des réglages.

Les tests `tests/ui/test_tooltips.py` couvrent les sources de contenu, les règles
de fermeture, le délai commun, les propriétaires détruits, les bords d'écran et
les textes longs. Le test de micro-fenêtre des Project Settings reste applicable.

Le catalogue porte du texte brut ; `ui/common/tooltip.py` compose le balisage
commun. Une infobulle courte emploie `tooltip(title=..., body=...)`. Si un
raccourci existe, `shortcut=...` le place avant l'effet : le raccourci est en
gras et l'effet en italique, séparés par une barre verticale (**Ctrl+F** | *Rechercher*).
`note=...` rend une précision en italique ; `warning=...` ajoute `⚠` pour une
perte, un remplacement ou une action difficile à annuler.

Sans raccourci, le titre est l'action ou le réglage, en gras. Le corps explique l'effet avec
des phrases courtes, à la troisième personne : le texte décrit un usage
(« Crée une zone de texte », « Un clic assigne un sprite ») et ne s'adresse
jamais à l'utilisateur (ni impératif, ni « vous »). Un geste se décrit par son
effet : « Glisser déplace la vue », pas « Faites glisser ». Une barre verticale ne sépare que des éléments autonomes,
notamment un raccourci et une action. Les tirets cadratins ne sont pas employés
dans les infobulles : une phrase complète, deux-points ou point-virgule exprime
la relation voulue.

Les noms techniques restent en anglais dans toutes les langues : types
d’assets et de composants du moteur (`MusicBox`, `JingleBox`, `SoundBox`,
`prefab`…), termes matériels (`OAM`, `VRAM`, `charblock`) et noms d’API. La
traduction ne porte que sur le vocabulaire courant autour d’eux.

Les tables de menus, directions, transitions et modes conservent des clés,
résolues à l’affichage. Les valeurs par défaut des fonctions sont résolues à
l’appel, pas à l’import. Dans les sélecteurs, `AssetKind.label` reste
l’identifiant de famille utilisé dans les signaux ; `label_key` donne le titre
affiché. `add_tooltip_key` et `empty_text_key` donnent les infobulles et états
vides. Les textes fournis par les plugins restent acceptés.

## Contrôles

`check_ui_text.py` ne dépend pas de Qt. Il est appelé par le contrôle
d’architecture, déjà exécuté en CI, et possède ses propres tests. Il vérifie :

- JSON valide, absence de doublons, structure des maîtres et traductions ;
- formes, paramètres nommés et métadonnées autorisées ;
- existence des clés traduites et correspondance de leurs paramètres ;
- paramètres manquants ou superflus des appels statiques à `label`, `text` et
  `tip`, y compris les alias importés ;
- clés des principales tables d’affichage et descriptions de familles ;
- textes directs dans les points d’entrée Qt et helpers recensés, y compris
  listes, conditions, concaténations et `.format()` ;
- justification et utilisation effective des exceptions explicites.

Le contrôle d’architecture conserve son contrôle des références et des entrées
inutilisées pour les deux catalogues.

La détection est ciblée : elle ne suit pas toutes les valeurs à travers les
variables, retours de fonctions et signaux. Elle ne prouve donc pas que toute
chaîne affichable est extraite. Les notices différées (`note` / `notice`, puis
`show_text`) ne font pas l’objet d’une inférence de paramètres entre méthodes.
Lors de l’ajout d’un helper, ajouter ses arguments d’affichage à `display_args`
et ses tables à `KEY_TABLES` si nécessaire, sans inclure les arguments de données.

## Exceptions assumées

`tools/ui_text_exceptions.json` recense chaque exception détectée : fichier,
texte exact et raison. Une exception devenue inutile fait échouer le contrôle.

Restent hors de cette extraction de l’interface :

- noms et contenus des ressources de l’utilisateur, noms créés dans le projet,
  code Lua et expressions d’API ;
- identifiants de signaux, de stockage ou de types (`int`, `bool`, familles,
  catégories), distincts de leur présentation lorsqu’elle doit être traduite ;
- notations matérielles, formats, unités, marques, glyphes et styles HTML/CSS ;
- libellés des commandes d’annulation, corpus séparé de l’historique ;
- messages produits par `core`, le validateur, le compilateur et les outils
  externes, affichés tels que reçus : leur extraction exige un contrat de
  diagnostic indépendant de l’UI, pas un import de `ui` dans `core` ;
- textes fournis par les plugins tiers.

## Choix de langue

Les réglages enregistrent la préférence sans modifier la langue active.
`main.py` l’applique au prochain démarrage, avant la construction des widgets.
Un panneau ouvert ou un message rafraîchi après le changement reste dans la
langue de la session. La traduction française est en attente. Le moteur de
pluriels conserve sa règle actuelle `n == 1` / autres cas ; les règles propres
aux langues restent un chantier distinct.
