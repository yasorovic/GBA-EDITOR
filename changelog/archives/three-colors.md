# Les trois couleurs de l'interface — **LIVRÉ**

> **Ouvert le 2026-08-24, livré le 2026-09-05** (commit `e3be21d`). Chantier technique : rien de
> visible pour qui joue, une réparation de fond côté code — une seule notion en portait trois.
>
> **Audit de clôture (2026-09-08).** Vérifié de bout en bout. Un seul écart au plan, et c'est un
> nom : le contrôle de banque annoncé `_check_ui_text_fill_bank` a été implémenté sous
> `_check_ui_container_fill` ([validator.py](../../editor/core/validator.py)) — même contrat, autre
> nom, comme `gba_engine.h` resté inchangé contre son plan en v0.25. Tout le reste est en place :
> `UIText.highlight_color` ([ui_region.py](../../editor/core/models/ui_region.py)), `RegionFill` /
> `scene_region_colors` / `region_fill_container` dérivés des fonds émis
> ([gen_text.py](../../editor/codegen/runtime_codegen/gen_text.py),
> [main_gen.py](../../editor/codegen/runtime_codegen/main_gen.py)), les surfaces composées et le
> surlignement côté runtime ([gba_engine.h](../../runtime/include/gba_engine.h)), *Ink* / *Highlight*
> dans l'inspecteur ([ui_inspector.py](../../editor/ui/scene_manager/inspectors/ui_inspector.py)).

## D'où vient la question (2026-08-24)

Un conteneur en fond couleur ne colorait qu'une partie de sa zone. Le diagnostic n'a pas trouvé
un bug de géométrie mais **deux chemins qui ne s'accordaient pas sur ce qui est émis** :
`scene_color_fills` écarte un panneau dont la palette n'est pas dans les palettes BG actives de la
scène (il lui faut une banque matérielle), tandis que `_region_bg_fills` — qui donnait aux zones
de texte ENFANTS la couleur de leur panneau ancêtre — n'appliquait aucune de ces conditions.
Résultat : le panneau ne dessinait rien, mais sa couleur apparaissait quand même dans la boîte de
son texte enfant. Un échec **partiel et joli**, bien plus difficile à lire qu'un fond franchement
absent.

La cause profonde n'est pas la condition manquante, c'est qu'**une seule notion en portait
trois** : le fond d'un conteneur, l'encre d'un texte, et la couleur posée sous ce texte étaient
réglées à deux endroits pour trois effets.

## Décisions verrouillées

- **Trois couleurs nommées, trois champs distincts.** Le fond (`FillMixin.fill_palette` +
  `fill_index`), l'encre (`UIText.text_color`) et le **surlignement** (`UIText.highlight_color`,
  nouveau). Trois mots dans l'interface — *Color*, *Ink*, *Highlight* — parce que trois effets
  différents réglés sous le même mot est précisément ce qui a produit le défaut.
- **Un texte prend le fond de son conteneur, par défaut et sans rien déclarer.** Écrire ne doit
  jamais PERCER ce qu'il y a dessous : le chemin tilemap remplacerait la cellule par une tuile de
  glyphe, dont l'index 0 est transparent. C'est une règle de non-destruction, pas une teinte — la
  zone ne s'approprie pas la couleur, elle refuse de l'effacer.
- **Le surlignement SURCHARGE ce fond**, sur l'étendue que le texte écrit. Le fond dit ce qu'il y
  a dessous, le surlignement ce que l'auteur veut y voir à la place. Les deux coexistent sur une
  même zone, y compris sous un cadre nine-slice : le marqueur se pose SUR le cadre, il ne le troue
  pas.
- **Composer est décidé par le FOND autant que par la police.** Une zone à fond ou surlignée se
  compose même en police MONO. Le cas nine-slice était déjà censé le faire et ne le faisait pas
  (`text_is_composited` ne regardait pas la table des fonds) : un texte mono posé sur un cadre le
  trouait, alors que la donnée pour le recomposer existait. Fermé ici.
- **Le fond d'un texte est de l'état de SCÈNE, jamais de la table projet.** `RegionFill` est posée
  par `scene_init`, et son contenu DÉRIVE de `scene_color_fills` / `scene_image_fills` —
  c'est-à-dire de ce que le build émet réellement. C'est la correction de fond du chantier :
  l'ancien `_region_bg_fills`, table projet-globale, ne connaissait aucune des conditions
  d'émission, d'où un panneau écarté du build dont la couleur apparaissait quand même dans la boîte
  de son texte.
- **Deux formes de fond, UNE table.** Une carte de tuiles (nine-slice / background) ou un aplat
  (couleur), distingués par `se == NULL`. C'est une seule question — « qu'y a-t-il sous cette
  zone ? » — et deux tables auraient permis à une zone d'avoir deux fonds, ou aucun. Même raison
  pour `region_fill_panel()` : la règle « le fond le plus proche gagne » s'écrit une fois et se lit
  des deux côtés.
- **Le surlignement est un index dans la banque d'UI de la scène**, comme l'encre — même
  référentiel, même plage 0-15, `0` = aucun. Ce n'est PAS une palette + index comme le fond : la
  surface composée reçoit `g_pal_bank_bg` (une seule banque par tuile, le matériel l'impose), donc
  une couleur venue d'ailleurs devrait de toute façon être recopiée dans cette banque. Le champ
  dirait « n'importe quelle couleur » là où le matériel n'en offre que seize.
- **Le surlignement couvre l'étendue RENDUE du texte**, pas la boîte authorée : un surlignement est
  un trait de marqueur. La boîte entière reste PRÉPARÉE (c'est ce qui empêche un texte plus court
  que le précédent de laisser l'encre de l'ancien), mais seule l'étendue écrite reçoit la couleur —
  origine comprise, de sorte qu'un texte centré ne surligne pas sa marge gauche.
- **Où vit la couleur d'un aplat dépend de `scene.ui_pal_bank`, et le build tranche seul.** En mode
  AUTOMATIQUE la banque d'UI appartient à la police : le build y loge la couleur du conteneur,
  depuis le HAUT (15, 14, …) et en sautant les index que l'encre et les surlignements de la scène
  occupent déjà — la réservation est PAR SCÈNE, là où l'ancienne était projet-globale et ne pouvait
  éviter aucune collision. En banque DÉSIGNÉE le build n'écrit rien (ce serait remplacer en douce
  les couleurs choisies) : l'index du conteneur passe tel quel, et le contrôle de banque exige que
  la banque désignée soit celle du conteneur — même contrat que le cadre nine-slice, pour la même
  raison matérielle.
- **Cible OBJ : pas de surlignement.** Une zone en bande de sprites ne passe pas par la surface
  BG ; le champ est masqué plutôt que proposé sans effet — même règle que `_FILL_TARGETS`, qui dit
  ce que le build ÉMET.
- **Le fond d'un conteneur se choisit dans les palettes BG ACTIVES de la scène**, par le slot de
  sélection partagé (`pickers.palette_picker_slot`) et non par une liste de tout le catalogue.
  Proposer une palette que le build écartera est exactement le défaut d'origine, déplacé dans le
  widget.
- **Pas de migration de données, et il n'en faut aucune** : le fond redevenant automatique, les
  textes qui héritaient retrouvent leur rendu sans qu'un champ soit écrit nulle part.
  `highlight_color` naît à 0 et ne dit que ce que l'auteur y a mis.

## Ce que ça a touché

| Fichier | Nature |
| --- | --- |
| [ui_region.py](../../editor/core/models/ui_region.py) | `UIText.highlight_color` |
| [gba_engine.h](../../runtime/include/gba_engine.h) | `UIRegionInfo.bg_fill` → `highlight`, rectangle surligné, `text_layout` rend son origine |
| [font_emit.py](../../editor/codegen/font_emit.py) | la table lit le champ de la zone, plus une table annexe |
| [main_gen.py](../../editor/codegen/runtime_codegen/main_gen.py) | `_region_bg_fills` remplacé par `region_fill_panel` + `scene_region_colors`, dérivés des fonds émis |
| [validator.py](../../editor/core/validator.py) | le contrat de banque (`_check_ui_container_fill`, cf. l'audit), étendu à l'aplat |
| [ui_inspector.py](../../editor/ui/scene_manager/inspectors/ui_inspector.py) | *Ink* / *Highlight*, slot de sélection filtré pour le fond |
| [scene_canvas.py](../../editor/ui/scene_manager/scene_canvas.py) | aperçu du surlignement, composition sous un conteneur à fond |
| [text_layout_probe.c](../../tests/native/text_layout_probe.c) + [gba_shim_common.h](../../tests/native/libgba_shim/gba_shim_common.h) | la sonde suit la signature — et les stubs que la liste (v0.22) lui devait |

**Le test d'équivalence Python/C était déjà rouge avant ce chantier**, et il ne le disait à
personne : la sonde ne compilait plus contre `gba_engine.h` depuis que la navigation de liste lit
les touches (`KEY_*` absents du shim libgba) et que six globales plus récentes (`g_ui_list_*`,
`g_ui_element*`, `g_save_bits`, `g_save_len`, `global_read_at/write_at`) n'avaient pas de stub. Le
fichier de test lui-même prévient qu'« un saut n'est pas un succès » — ici ce n'était même pas un
saut, c'était une erreur de compilation avalée par 37 `ERROR` de setup. Les stubs sont complétés
dans ce chantier parce que c'est exactement `text_layout` que la sonde garde, et que sa signature
venait de changer.

## Ouvert

- **La banque d'UI reste implicite quand `scene.ui_pal_bank` vaut -1** : encre et surlignement
  désignent alors des index de la banque de police, que l'auteur ne choisit pas. L'inspecteur
  montre les pastilles quand la banque est désignée, et rien sinon. *(Ce point est ce qui a ouvert
  le chantier jumeau [La police, une palette d'asset comme les autres](font-palette.md), qui le
  referme.)*
- **Huit fonds de zone par scène** (`TEXT_REGION_FILL_MAX`), aplats et cadres confondus — ils
  partagent désormais la table. Au-delà, les zones en trop n'ont pas de fond et le percent. Rien ne
  le signale encore ; le plafond n'a jamais été atteint, mais il est plus facile à atteindre
  maintenant que le fond est automatique.
- **Le surlignement n'est pas scriptable.** Comme l'encre, il est authoré. Un menu qui surligne sa
  ligne courante se fait via la sélection de liste (v0.22, `selected_highlight_color`) ; un
  surlignement piloté librement au script reste à faire.
