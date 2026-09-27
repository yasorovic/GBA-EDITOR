# Archive du changelog

Le détail complet de chaque entrée du [CHANGELOG](../CHANGELOG.md) : le pourquoi, les
décisions verrouillées, les pièges rencontrés, les mesures — extrait de la roadmap au moment
où chaque version a été livrée, pour que ni l'un ni l'autre ne devienne illisible.

Un fichier par version — et un par [chantier technique](../ROADMAP.md#chantiers-techniques)
refermé, référencé par son nom plutôt que par un numéro : un chantier technique ne touche ni le
CHANGELOG ni le README, mais sa discussion se range ici comme les autres. Rien n'est perdu :
c'est ici qu'on vient rouvrir une décision passée avec le contexte complet qui l'a motivée,
plutôt que de la retrancher à l'aveugle.

Pour un résumé court, voir le [CHANGELOG](../CHANGELOG.md). Pour ce qui reste à faire, voir
[ROADMAP.md](../ROADMAP.md).

| Version | Sujet |
| --- | --- |
| [v0.2](v0.2.md) | Gestion des palettes de couleurs |
| [v0.3](v0.3.md) | Background vivant, texte et interface in-game |
| [v0.4](v0.4.md) | Animation de décor |
| [v0.5](v0.5.md) | Sauvegarde (SRAM) |
| [v0.6](v0.6.md) | Polish de la boucle de jeu |
| [v0.7](v0.7.md) | Structures de données |
| [v0.8](v0.8.md) | Son : la musique par scène, les transitions, le mixage |
| [v0.9](v0.9.md) | Traduction des jeux créés avec l'éditeur |
| [v0.10](v0.10.md) | Distribution élargie — format `.gba-project`, associations OS |
| [v0.11](v0.11.md) | Traduction de l'interface de l'éditeur (infra ; FR reportée à v2.0) |
| [v0.12](v0.12.md) | Vue d'ensemble — le graphe des scènes |
| [v0.14](v0.14.md) | Diagnostic — ce que le jeu fait, et ce qu'il coûte |
| [v0.15](v0.15.md) | Visibilité des éléments d'interface |
| [v0.16](v0.16-api-construction.md) | L'API : la règle de construction, et le rangement |
| [v0.17](v0.17.md) | Le pool par scène |
| [v0.18](v0.18.md) | La valeur affichée : d'où elle vient |
| [v0.19](v0.19.md) | Le sous-pixel |
| [v0.20](v0.20.md) | L'état du monde : les collections persistantes |
| [v0.21](v0.21.md) | Le texte adressable : le dialogue piloté par la donnée |
| [v0.22](v0.22.md) | Menus, listes et curseur |
| [v0.23](v0.23.md) | Ce qu'un boss demande |
| [v0.24](v0.24.md) | Le projet à l'échelle d'une équipe |
| [v0.25](v0.25.md) | L'interface possède son chemin matériel |
| [v0.26](v0.26.md) | Les polices : sources, assets et aperçu |
| [v0.27](v0.27.md) | L'éditeur souffle le mot juste (autocomplétion du Script Editor) |
| [v0.28](v0.28.md) | Les inputs personnalisés |

### Chantiers techniques

| Chantier | Sujet |
| --- | --- |
| [La grammaire de la struct `Actor`](actor-struct-grammar.md) | L'API C tient les trois concepts de l'éditeur (acteur/prefab/scène) |
| [Les trois couleurs de l'interface](three-colors.md) | Une seule notion de banque de palette en portait trois |
| [`global.nom` / `const.nom`](global-const.md) | L'accès pointé remplace les accesseurs |
| [L'identité d'un asset et son fichier](asset-identity.md) | Le nom de fichier fait foi, et un renommage n'est pas une suppression |
| [Les formats acceptés à l'import](import-formats.md) | `.png` pour les images, `.fnt` en plus pour les polices — rien d'autre |
| [La police, une palette d'asset comme les autres](font-palette.md) | Une police possède ses propres couleurs, comme un fond ou un sprite |
| [L'écran construit à sa première visite](lazy-screen-build.md) | Le lazy loading étendu au widget : seul le Scene Manager est bâti au démarrage |
| [L'ouverture d'un projet, et l'écran blanc](open-white-screen.md) | Ouvrir avant `show()`, inspecteur paresseux, aperçu de police pré-chauffé hors écran |
| [Les palettes, rangées avec les assets](palettes-in-assets.md) | Le catalogue quitte `project/palettes/` pour `assets/palettes/` |
| [L'acteur appartient à sa scène](actor-scene-local.md) | Noms d'acteurs locaux à la scène, symbole C qualifié, `get_actor` nullable |
| [Les exports de script, câblés au jeu](script-exports.md) | Paramétrer une instance (posée ou poolée) depuis l'éditeur, jusqu'au C |
| [Un seul type de script](single-script-type.md) | Le propriétaire donne le contexte — plus de « type » de script choisi par l'auteur |
| [Le balisage rouvert — `[font=nom]`](font-markup-reopened.md) | Changer de police en cours de texte (réouverture de v0.3.2) |
| [Raccordement build vectoriel](build-vector-linkage.md) | Le build matérialise un `FontAsset` en tuiles via `RasterGlyph` |
| [L'écran resynchronisé à sa revisite](screen-resync-revisit.md) | `refresh()` central à la revisite remplace les colmatages `showEvent` par écran |
| [La struct `Actor` allégée](actor-struct-lightening.md) | `g_oam_entries[]` réserve l'OAM, `g_actors[]` ne porte que des acteurs — 1 sprite affiché = 1 slot |
| [Correctifs trouvés en marchant](fixes-in-passing.md) | Dix bugs réels sans jalon à qui les rattacher, tous corrigés et testés |
