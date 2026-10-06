# Le balisage rouvert — `[font=nom]`, changer de police en cours de texte — **LIVRÉ**

Réouverture de **v0.3.2** (le balisage), pas un jalon neuf : la grammaire, la piste
d'événements et le catalogue de balises existent déjà et sont clos. On y ajoute UNE balise. Pas
de numéro — le balisage a le sien.

### D'où vient la question (2026-09-04)

« Dans notre balisage, peut-on changer de police dynamiquement ? » La réponse était **non** : le
catalogue s'arrête à `speed`, `pause`, `icon`, `wave`, `shake`, `color`
([text_markup.py:66](editor/core/text_markup.py:66)). La seule bascule typographique en cours de
chaîne est l'ENCRE (`[color=n]`), dans la sous-palette de la police déjà en place — jamais un
autre jeu de glyphes. La police est fixée un cran au-dessus : une zone porte UN `font_name`
([ui_region.py:329](editor/core/models/ui_region.py:329)), et la mise en page prend UNE police
([text_layout.py:47](editor/core/engine_emulation/text_layout.py:47)). Une scène affiche déjà
plusieurs polices — mais par zones, jamais au sein d'une chaîne.

La lecture du runtime a montré que l'ajout est **incrémental**, pas un sous-système : le moteur a
déjà tout ce qu'il faut, on ne fait que le câbler à une balise.

### Décisions verrouillées

- **Balise de PORTÉE, symétrique à `[color]`.** `[font=nom]…[/font]`, valeur `VALUE_NAME`. Elle
  entre au catalogue `TAGS` et rien d'autre : l'analyse est générique, `_close_scope`,
  l'imbrication croisée et l'avertissement de portée non refermée la couvrent déjà. Une balise
  ponctuelle (« change jusqu'à nouvel ordre ») est **écartée** plus bas.
- **Un ÉVÉNEMENT de plus, pas un mécanisme de plus.** `[font]` sort un `TEXT_EV_FONT` sur
  `[at, end)`, exactement comme `wave`/`shake`/`color`
  ([font_emit.py:972](editor/codegen/font_emit.py:972)). `value` = index de la police LOGIQUE
  (ordre de `project_fonts()`, le même que `g_fonts` et `g_lang_font`), résolu au build comme
  `[icon]` résout son glyphe.
- **La bascule passe par `text_set_font`, donc honore la LANGUE.** Franchir un `TEXT_EV_FONT`
  appelle `text_set_font(value)`, qui remappe déjà par langue
  (`f = g_lang_font[g_lang][f]`, [gba_engine.h:1686](runtime/include/gba_engine.h:1686)). Une
  `[font=titre]` suit donc la traduction sans une ligne de plus — même brique que `text.set_font`
  (v0.9). Aucun nouveau chemin de chargement.
- **Le coût est un RE-POINTAGE, pas une recopie.** Les polices sont co-résidentes en VRAM :
  chacune a sa base (`g_font_base[f]`) et un bit dans `g_font_loaded`
  ([gba_engine.h:1699](runtime/include/gba_engine.h:1699),
  [1708](runtime/include/gba_engine.h:1708)). Revenir à une police déjà chargée ne coûte qu'un
  test et une copie de palette (64 o). Le seul coût MATÉRIEL réel, ce sont les tuiles du
  sous-ensemble de la police appelée, comptées au build comme n'importe quelle police. C'est ce
  qui rend la balise abordable : sans co-résidence, elle aurait recopié la VRAM par segment.
- **La police citée devient RÉSIDENTE de la scène.** `scene_font_names` gagne une QUATRIÈME
  source, après la défaut, les zones et les scripts
  ([font_emit.py:461](editor/codegen/font_emit.py:461)) : les `[font=nom]` des textes que la
  scène peut afficher. Pas de nouvel allocateur — le sous-ensemble et la base par scène hébergent
  déjà N polices.
- **Le sous-ensemble suit la police ACTIVE, glyphe par glyphe.** Le glyphe du caractère `i`
  appartient à la police en vigueur en `i` (défaut de zone, ou dernière `[font]` ouverte). Le
  constructeur de sous-ensemble parcourt donc la piste d'événements — le même parcours que la
  mise en page. Chaque police n'embarque que les glyphes réellement atteints sous elle.
- **L'imbrication tombe juste toute seule.** `[color=3]` sous `[font=X]` = encre 3 de la
  sous-palette de X (la couleur se résout à la frappe contre la police courante). `[icon=y]` sous
  `[font=X]` = glyphe y de X (l'icône devient des codepoints, appariés à la mise en page sous la
  police active). Rien de spécial à écrire : les deux se résolvent déjà par position.

### Ce qui a été écarté, et pourquoi

- **Une balise PONCTUELLE `[font=X]` sans fermeture** (changer jusqu'à nouvel ordre). Elle
  rouvrirait ce que la portée a résolu : un effet sans borne est indécidable côté sous-ensemble
  (jusqu'où réserver ?) et laisse l'état d'un texte fuir sur le suivant. La forme fermée dit
  exactement où la police revient.
- **Recharger la VRAM à chaque bascule** (le chemin naïf où `text_set_font` recopie les
  glyphes). La co-résidence déjà en place l'écarte : inutile de payer une DMA par segment quand
  chaque police a sa place.
- **Une police par langue portée par la BALISE** (`[font=X:ja]`). La langue REMAPPE déjà la
  police (`g_lang_font`) — la substitution vit là, pas dans la source balisée. Même règle que
  « une langue n'a pas de police, elle a éventuellement un remplacement » (v0.9).

### Ce que ça touche

- [text_markup.py](editor/core/text_markup.py) : une entrée `TagSpec("font", True, VALUE_NAME, …)`
  au catalogue. Rien d'autre — l'analyse ne connaît pas les balises une à une.
- [font_emit.py](editor/codegen/font_emit.py) : `_EV_KIND` gagne `"font": "TEXT_EV_FONT"` ;
  l'émission résout le nom en index de `project_fonts()` et VALIDE que la police existe (comme
  `[icon]` valide son glyphe) ; `scene_font_names` scanne les `[font]` des textes de la scène ;
  le constructeur de sous-ensemble attribue chaque glyphe à la police active.
- [text_layout.py](editor/core/engine_emulation/text_layout.py) : `layout_text` devient conscient
  de la police PAR POSITION — chasse et appariement au plus long (ligatures) lus dans la police
  active, pas dans un unique argument. C'est le vrai travail : l'aperçu de l'éditeur doit tomber
  juste, sinon il ment sur le rendu ROM (la raison d'être du point unique `text_markup`).
- [gba_engine.h](runtime/include/gba_engine.h) : `TEXT_EV_FONT` à l'énum ; la boucle de dessin
  appelle `text_set_font(value)` en franchissant l'événement et REPOSE la police de zone en
  sortie de portée. `text_color_at`/`text_fx_at` ont déjà le modèle « quel événement couvre `i` »
  à recopier.
- l'écran Texte : la barre de balisage (`markup_toolbar`) et la coloration (`markup_highlighter`)
  prennent la balise gratuitement (dérivées de `TAGS`) ; l'aperçu écran doit charger la 2ᵉ police.

### Décisions finalisées

- **L'interligne reste celui de la zone.** La portée change la police et sa chasse, pas le rythme
  vertical du paragraphe : le texte ne saute pas d'une ligne à l'autre. Une police plus grande qui
  déborde le cadre est signalée par le diagnostic de débordement, comme toute autre police de zone.
- **La couverture est vérifiée par segment et par langue.** Chaque caractère est contrôlé contre la
  police active au point où il apparaît ; une constante insérée dans une portée hérite elle aussi de
  cette police.
- **Une portée `[font]` force le chemin de composition.** `[color]` continue donc de s'appliquer
  dans un fragment en police bitmap comme en police composée, sans ambiguïté entre l'aperçu et la
  ROM.
- **Les polices citées sont connues avant le build.** Les textes appelés par les scripts, ceux posés
  dans l'interface et leurs traductions alimentent `scene_font_names`; un script impossible à
  analyser retombe, par sûreté, sur la réservation de toutes les polices du projet.

