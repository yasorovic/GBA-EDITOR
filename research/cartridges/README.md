# Photos des six profils de cartouches

Collecte du **17 octobre 2026** : **31 images, environ 14,3 Mio**. Les fichiers sont intacts ; seuls leurs noms et leur classement ont changé.

## Accès rapide

| Profil | Carte nue | Référence assemblée | Compléments |
| --- | --- | --- | --- |
| Sans sauvegarde | [Recto](boards/none/AGB-E01-10--front.jpg) · [Verso](boards/none/AGB-E01-10--back.jpg) | [Pac-Man Collection](assembled/none/AGB-E01-10--front.jpg) | [Verso assemblé](assembled/none/AGB-E01-10--back.jpg) |
| SRAM 32 Kio | [Recto](boards/sram/AGB-E06-01--front.jpg) · [Verso](boards/sram/AGB-E06-01--back.jpg) | [F-Zero, pile retirée](assembled/sram/AGB-E06-01--front.jpg) | [Castlevania, pile déposée à côté](assembled/sram/AGB-E06-01--battery-detached--front.jpg) |
| EEPROM | [Recto](boards/eeprom/AGB-E03-20--front.jpg) · [Verso](boards/eeprom/AGB-E03-20--back.jpg) | [8 Kio, The Minish Cap](assembled/eeprom/AGB-E03-20--front.jpg) | [512 octets, Disney Princesse + Le Roi Lion](assembled/eeprom/AGB-E03-20--512b--front.jpg) |
| Flash | [Recto](boards/flash/AGB-E02-30--front.jpg) · [Verso](boards/flash/AGB-E02-30--back.jpg) | [128 Kio, Rouge Feu](assembled/flash/AGB-E02-30--front.jpg) | [64 Kio, Sonic Advance 3](assembled/flash/AGB-E02-30--64kib--front.jpg) |
| FRAM 32 Kio | [Recto](boards/fram/AGB-E11-01--front.jpg) · [Verso](boards/fram/AGB-E11-01--back.jpg) | [Aria of Sorrow](assembled/fram/AGB-E11-01--front.jpg) | [Autre assemblage de la fiche Archive.org](assembled/fram/AGB-E11-01--archive-assembled.jpg), à garder distinct d'Aria of Sorrow |
| Flash + horloge | [Recto](boards/flash_rtc/AGB-E05-01--front.jpg) · [Verso](boards/flash_rtc/AGB-E05-01--back.jpg) | [Émeraude, pile déposée à côté](assembled/flash_rtc/AGB-E05-01--front.jpg) | [Gros plan de la ROM](assembled/flash_rtc/AGB-E05-01--rom-closeup.jpg) |

Les **12 vues de cartes nues** couvrent les six profils. Les **19 autres images** comprennent les assemblages recto/verso, les variantes de mémoire, les vues avec pile déposée et un gros plan de ROM. Une photo SRAM déjà présente dans l'éditeur a été copiée intacte dans cette collection.

## Composants : sources récupérées, détourage à faire

Les photos assemblées montrent les ROM, SRAM, EEPROM 9853/9854, Flash 64/128 Kio, FRAM, superviseur/reset, RTC, quartz et piles. Leur correspondance est enregistrée dans [component-sources.json](component-sources.json).

Ces composants ne sont **pas encore des images isolées sur fond transparent**. Il reste à préparer les détourages, puis vérifier les contours, l'orientation, l'échelle et la compatibilité avec le fond choisi. Les passifs et les variantes de boîtier doivent être contrôlés sur l'exemplaire retenu. Aucune image générée ni modification des marquages n'a été faite.

## Provenance et réutilisation

- `boards/` : JPEG d'accompagnement des fiches **Archive.org**, contrôlés par les empreintes SHA-1 publiées. Ce sont les images JPEG disponibles séparément, pas les scans PNG maîtres des ZIP 1 200/4 800 DPI. Leurs dimensions exactes figurent dans le manifeste.
- `assembled/` : photographies de la **Game Boy hardware database**, sauf le fichier explicitement nommé `archive-assembled`. Les auteurs sont crédités individuellement dans [inventory.md](inventory.md). Les photos de la base matérielle sont annoncées sous [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) ; conserver les crédits, la source, la licence et signaler les modifications lors de la réutilisation.
- Les métadonnées Archive.org consultées ne précisent pas de licence de réutilisation. Ces fichiers restent des **sources de travail** dont les droits de redistribution sont à clarifier.

Ce dossier `research/` est **extérieur aux images empaquetées avec l'application**. Les vues assemblées sélectionnées sous CC BY-SA 4.0 ont été copiées dans le [catalogue intégré](../../editor/ui/common/images/cartridges/README.md) et remplacent les schémas des six profils. Le catalogue ajoute le recto/verso SRAM AGB-E06-10 déjà utilisé par l’application. Les scans nus restent ici : ils sont consultables en développement, sans être distribués. Aucun nouveau pilote de sauvegarde n’est activé.

## Inventaires

- [inventory.md](inventory.md) : chaque image, ses dimensions, son auteur, sa licence et sa fiche source.
- [manifest.json](manifest.json) : URL exacte, nom d'origine, empreinte, taille et dimensions de chaque fichier.
- [component-sources.json](component-sources.json) : photos de référence où trouver les composants.
- [Matrice matérielle](../../docs/development/cartridge-hardware-matrix.md) : associations observées entre cartes, composants et jeux.
