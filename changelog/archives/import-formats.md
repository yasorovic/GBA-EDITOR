# Les formats acceptés à l'import — **LIVRÉ**

> **Chantier technique** — il ne livre rien de visible pour qui joue au jeu produit avec
> l'éditeur, seulement une porte d'entrée qui cesse de promettre ce que la doc et le modèle
> démentaient. Il n'a donc ni numéro `vX.Y`, ni ligne au [README](../../README.md), ni entrée au
> [CHANGELOG](../CHANGELOG.md) : c'est la convention des
> [chantiers techniques](../../ROADMAP.md#chantiers-techniques).

> **Livré le 2026-09-03.** L'éditeur n'accepte plus que `.png` pour les images et, en plus,
> `.fnt` pour les polices. Le troisième point d'entrée des polices (FreeType) et le `.bmp`
> sont supprimés — 115 lignes et une dépendance en moins, aucune migration de projet.

## D'où vient la question

Posée le 2026-09-03 : quels fichiers l'éditeur accepte-t-il, et qui le dit ? La réponse
tenait en deux constantes — `IMAGE_FILE_EXTS` (`core/models/sprite.py`) et `FONT_FILE_EXTS`
(`core/models/font.py`) — dont tout le reste dérive : le `ProjectWatcher`, la table de
routage de `window.py`, les passes `reconcile_*`. Cette dérivation est saine et ne bouge pas.

Ce qui bouge, c'est leur CONTENU, parce qu'il ne dit plus la même chose que le reste du dépôt :

- [ARCHITECTURE](../../ARCHITECTURE.md) annonce, pour les polices, « deux formats acceptés,
  **volontairement pas plus** : PNG nu ou BMFont `.fnt` ». Le code en acceptait **six** —
  `.bdf`, `.pcf`, `.dfont` et `.ttf` étaient arrivés ensuite, par un troisième point d'entrée
  (`import_font_freetype`) que le document n'a jamais décrit.
- `Font.source_format` se documente lui-même `"png" | "fnt"`. Le chemin FreeType y écrivait
  `"ttf"`, `"bdf"`… — une valeur que ni `font_emit.advance_source` ni l'inspecteur de police
  ne savent lire, et qui traversait donc l'éditeur en silence jusqu'au sidecar.
- `.bmp` était accepté côté images sans qu'aucun document, aucun test ni aucun écran ne s'y
  réfère : une seconde porte d'entrée dans la chaîne d'encodage, jamais empruntée, jamais
  vérifiée.

Le troisième point d'entrée n'était pas seulement non documenté : il **fabrique** la planche
au lieu de la lire (rendu FreeType, empaquetage en étagères, PNG écrit à côté du conteneur).
C'est la seule voie d'import du dépôt qui produise un asset au lieu d'en accueillir un, et
elle tient à une dépendance de plus (`freetype-py`) pour un cas qu'un auteur couvre déjà en
exportant une planche depuis son outil de police.

## Décisions verrouillées

- **Deux formats d'entrée, un par famille de fichier** : `.png` pour toute image (sprites,
  fonds, planches de police), `.fnt` en plus pour les polices. Rien d'autre.
- **Les deux constantes restent la seule source.** Tout ce qui aiguille sur une extension
  en dérive déjà : `ProjectWatcher._ASSET_SUFFIXES`, la table `_ASSET_ROUTES` de
  `window.py`, les passes `reconcile_*`, le rechargement à chaud d'une image retouchée.
  **Sauf** les quatre filtres `QFileDialog` des écrans Sprite et Fond, qui épelaient
  `Images (*.png *.bmp)` à la main et disent maintenant `Images (*.png)` — toujours à la
  main. C'est la seconde liste que le commentaire de `sprite.py` interdit, et c'est par elle
  que `.bmp` était entré. Elle est laissée telle quelle : la faire dériver demanderait de
  sortir `file_dialog_filter` de `core/models/audio.py`, où il est écrit pour l'audio, et
  ferait dépendre un écran d'image du modèle de son — un déplacement qui appelle sa propre
  décision, pas un passage en douce dans ce chantier. **Point à rouvrir**, pas un oubli.
- **L'audio et les palettes ne sont pas concernés.** `.wav` et les quatre modules maxmod
  répondent à leur propre règle (« on n'accepte que ce que la chaîne sait CONSTRUIRE et que
  l'éditeur sait FAIRE ÉCOUTER », cf. `core/models/audio.py`), et l'import de palette
  `.gpl`/`.pal` est un parseur de texte sans chaîne de build derrière. Resserrer là n'aurait
  retiré aucun risque, seulement de l'usage.
- **Aucune migration de projet.** Une police déjà importée d'un `.ttf` garde sa planche
  générée sur le disque et le sidecar qui la cite : elle redevient une police PNG ordinaire.
  Seul son `source_format` porte une valeur périmée, que `Font.from_dict` relit désormais
  comme `"png"` — le champ redevient vrai sans réécrire un seul fichier de projet.

## Ce que ça touche

| Fichier | Ce qui change |
| --- | --- |
| `core/models/sprite.py` | `IMAGE_FILE_EXTS` → `{".png"}` |
| `core/models/font.py` | `FONT_FILE_EXTS` → `{".png", ".fnt"}` ; `from_dict` normalise `source_format` |
| `core/font_import.py` | le point d'entrée FreeType supprimé (`FREETYPE_FONT_EXTS`, `_pack_glyphs`, `import_font_freetype`, `_BMP_MAX`) |
| `core/resources/asset_reconciliation.py` | `sync_font_file` n'aiguille plus que sur `.fnt` ou planche |
| `core/project_watcher.py` | commentaire : l'union dérivée ne porte plus six formats de police |
| `codegen/font_emit.py` | commentaire citant la fonction supprimée |
| `ui/background_editor/`, `ui/sprite_editor/` | les quatre filtres de dialogue : `*.png *.bmp` → `*.png` |
| `requirements.txt` | `freetype-py` n'a plus d'importateur |


## Ce que ça a laissé derrière

Rien. `tools/check_architecture.py` ne relève aucun code mort neuf (ses deux signalements
portent sur `core.models.scene`, antérieurs à ce chantier), `packaging/check_deps.py` passe à
cinq dépendances, et les 465 tests passent.

Vérifié de bout en bout sur un projet neuf : une planche PNG déposée dans `assets/fonts/`
donne bien sa police (32 glyphes, cellule 8×8 déduite), et un `.ttf` déposé dans le même
dossier ne crée plus rien — sans avertissement non plus, puisque le fichier n'est plus un
asset aux yeux de l'éditeur.
