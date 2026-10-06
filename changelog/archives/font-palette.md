# La police, une palette d'asset comme les autres — **LIVRÉ**

> **Ouvert le 2026-09-03, livré le 2026-09-05** (commit `e3be21d`). Chantier technique : il
> referme le point resté « Ouvert » de [Les trois couleurs de l'interface](three-colors.md) — « la
> banque d'UI reste implicite quand `scene.ui_pal_bank` vaut -1 ». Une police possède ses couleurs
> comme un sprite ; elle entre désormais dans la même allocation et la même grille.
>
> **Audit de clôture (2026-09-08).** Le cœur était complet et testé
> ([test_font_palette_tracking.py](../../tests/text/test_font_palette_tracking.py)) — `Scene.font_pal_banks`
> et sa migration ([scene.py](../../editor/core/models/scene.py)), l'entrée de la police dans
> l'allocation BG ([palette_alloc.py](../../editor/codegen/palette_alloc.py)), la banque d'encre
> résolue par zone et la table par police (`g_font_bank` / `g_font_own` / `text_set_font_pal`,
> [gba_engine.h](../../runtime/include/gba_engine.h)), la grille d'override et le picker « UI colors »
> ([scene_inspector.py](../../editor/ui/scene_manager/inspectors/scene_inspector.py)).
> **Un trou trouvé et corrigé à la clôture** : `rename_font`
> ([project_renames.py](../../editor/core/project_renames.py)) ne suivait PAS `font_pal_banks` — cette
> map étant keyée par NOM de police, renommer une police non-défaut overridée orphelinait son
> override en silence (retour à la palette propre). Le geste manquait, alors même que « Ce que ça
> touche » l'annonçait. Corrigé sur le patron de `rename_palette` (balayage des scènes, `save_scene`
> quand touché), gardé par `test_renommer_une_police_suit_son_override_de_banque`. La police par
> défaut passe par la clé `""`, stable au renommage, donc jamais concernée.

## D'où vient la question (2026-09-03)

La carte **Palettes** de l'inspecteur de scène traque deux pools : OBJ (les sprites) et BCK (les
fonds). Chacun montre les palettes de la scène (éditables), puis les palettes **propres** des
assets — grisées, comptées dans les seize banques, et remplaçables par une palette de scène d'un
clic. La **police** manquait à l'appel.

Elle ne devrait pas. Une police possède ses couleurs exactement comme un sprite : `g_font_*_pal`,
seize entrées, index 0 transparent. En mode automatique elle les chargeait en silence dans la
banque 15 (`FONT_PAL_BANK`) — une banque que la grille ne montrait pas et ne comptait pas.
L'auteur ne voyait pas la banque que la police prenait, et ne pouvait pas la rediriger avec le
geste qui sert à tous les autres assets.

## Ce que la lecture du code a trouvé (2026-09-03)

- **La banque de police était décidée par le runtime, pas par l'allocateur.** `FONT_PAL_BANK = 15`
  était cuit dans `text_set_font`, alors que `scene_bank_layout` est la source de vérité des seize
  banques. Elle ignorait donc qu'une police en occupe une, et la grille ne pouvait pas l'afficher.
- **Le runtime était déjà paramétré par la banque.** `text_set_pal_bank(bg, obj)` pose où le texte
  lit son encre ; négatif = automatique (palette propre → 15). Seule la banque automatique était en
  dur — le reste du chemin savait déjà lire n'importe quel slot.
- **La table par police existait déjà, pour la VRAM.** `text_set_font_base(f, base)` + `g_font_base[]`
  donnent à un titre et à un corps de texte chacun leur base de tuiles. La palette réclamait
  **exactement la même forme** — une banque par police — et c'est parce qu'elle ne l'avait pas que
  deux polices se repeignaient l'une l'autre dans la banque 15.
- **L'override existait déjà, mais à côté.** Le scalaire `Scene.ui_pal_bank`, câblé à un sélecteur
  séparé (le slot « UI colors »), à l'échelle de la scène entière et aveugle à *quelle* police il
  concernait.

## Décisions verrouillées

- **Parité totale avec les sprites.** Une police en mode propre entre dans la **même** allocation
  ascendante que les acteurs et les calques, dédupliquée par couleurs, et reçoit une banque libre —
  pas un 15 épinglé. Plusieurs polices → plusieurs banques, chacune une entrée grisée dans BCK.
- **La palette suit l'ARBRE, pas seulement la police.** Comportement PAR DÉFAUT : un texte
  **enfant** d'un conteneur à fond (nine-slice / background / couleur) reprend la banque de CE
  conteneur — sa police ne prend alors **aucun** slot, elle lit son encre dans la palette du fond.
  La règle « le fond le plus proche gagne » existe déjà, c'est `region_fill_container`, partagée
  avec `scene_region_colors` / `scene_region_backdrops`. Un texte posé PAR-DESSUS un conteneur
  **sans en être l'enfant** garde sa propre palette et écrase le fond. Trois conséquences :
  - une police n'occupe une banque que pour ses usages **libres** ; utilisée seulement dans des
    conteneurs, elle n'apparaît pas dans la grille — le conteneur, lui, y est déjà ;
  - la banque d'encre est résolue **par zone** (imbriquée → banque du conteneur ; libre → banque de
    la police), et non plus par le scalaire scène-global qu'était `ui_pal_bank` — le runtime pose
    donc la banque au dessin de la zone, pas une fois pour tout l'écran ;
  - cela **renverse pour la BANQUE** la décision de [Les trois couleurs de l'interface](three-colors.md)
    (« le fond d'un conteneur ancêtre ne teinte pas ses textes enfants »). Le **surlignement**, lui,
    reste par-texte : c'est une couleur SOUS le texte, pas la banque de l'encre.
- **L'état vit sur la scène, par police : `Scene.font_pal_banks: dict[str, int]`.** L'analogue exact
  de `Actor.pal_bank` / `BackgroundLayer.pal_bank`, keyé par **nom de police** faute d'instance
  posée. Absent de la map (ou `OWN_PAL_BANK`) = palette propre dans une banque allouée ; un slot
  0-15 = lit l'encre dans cette palette de scène. Le scalaire `ui_pal_bank` est **migré à la
  lecture** (`from_dict`) sur la police par défaut de la scène (clé `""`) — les projets existants
  gardent leurs couleurs. *(Le renommage d'une police doit suivre ces clés — le geste manquait, cf.
  l'audit de clôture.)*
- **Une seule source, deux surfaces d'édition.** `font_pal_banks` est l'état. La grille de palettes
  override l'entrée de **n'importe quelle** police, exactement comme un sprite. Le sélecteur « UI
  colors » de la carte User Interface reste, désormais lié à l'entrée de la **police par défaut**
  (clé `""`) dans cette même map — un raccourci pour le cas le plus courant, jamais une seconde
  vérité.
- **Le runtime gagne une table banque+propre par police, jumelle de `g_font_base`.**
  `text_set_font(f)` lit la banque de la police et ne copie sa palette propre que si cette police
  est en mode propre ; l'override force le slot de scène sans copie. Le placement des couleurs de
  conteneur (`region_colors`) lit la banque **résolue** de la police au lieu de 15.

## Ce que ça a touché

| Fichier | Nature |
| --- | --- |
| [scene.py](../../editor/core/models/scene.py) | `font_pal_banks` remplace `ui_pal_bank` ; `font_pal_key` (clé `""` = défaut) ; migration à la lecture |
| [palette_alloc.py](../../editor/codegen/palette_alloc.py) | la police entre comme source de palette propre BG (`_scene_font_palettes`, `scene_bank_layout` + `scene_palette_view`) |
| [font_emit.py](../../editor/codegen/font_emit.py) | `FONT_PAL_BANK` n'est plus le défaut du chemin BG ; la police déclare son contenu de banque |
| [main_gen.py](../../editor/codegen/runtime_codegen/main_gen.py) | banque d'encre RÉSOLUE PAR ZONE (imbriquée → conteneur via `region_fill_container`, libre → police) ; table banque+propre par police |
| [gba_engine.h](../../runtime/include/gba_engine.h) | banque d'encre PAR ZONE + `g_font_bank` / `g_font_own` + `text_set_font_pal`, jumeaux de `g_font_base` |
| [validator.py](../../editor/core/validator.py) | les contrôles de banque d'UI lisent la map par police |
| [scene_inspector.py](../../editor/ui/scene_manager/inspectors/scene_inspector.py) | la grille override la police ; le picker « UI colors » édite l'entrée par défaut |
| [ui_inspector.py](../../editor/ui/scene_manager/inspectors/ui_inspector.py) / [scene_canvas.py](../../editor/ui/scene_manager/scene_canvas.py) | contexte d'élément et aperçu lisent la map |
| [pickers.py](../../editor/ui/common/pickers.py) | le sélecteur de banque d'UI cible une entrée de la map |
| [project_renames.py](../../editor/core/project_renames.py) | renommer une police suit ses clés dans `font_pal_banks` — **posé à la clôture** (cf. audit) |

Tests : [test_font_palette_tracking.py](../../tests/text/test_font_palette_tracking.py) (usage libre vs
imbriqué, banques runtime, override du picker, et le suivi du renommage ajouté à la clôture).

## Ouvert

- **La cible OBJ.** Une police se copie aussi dans `PAL_OBJ_RAM` pour le texte rendu en sprites ;
  ce chemin lit encore `FONT_PAL_BANK` ([font_emit.py](../../editor/codegen/font_emit.py), branche
  OBJ). La parité de banque décrite ici ne concerne pour l'instant que la cible BG.
