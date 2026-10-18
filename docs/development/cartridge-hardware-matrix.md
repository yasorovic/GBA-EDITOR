# Cartouches GBA — correspondances matérielles et photos à réunir

État de recherche : **17 octobre 2026**. Le tableau a précédé la collecte ; les photos des six
profils sont maintenant réunies dans [research/cartridges](../../research/cartridges/README.md).
La collection contient 31 images : 12 vues de cartes nues et 19 assemblages, variantes ou
détails de composants. Les détourages individuels restent à préparer.

Ce document prépare le catalogue visuel du panneau Build : cartes nues recto/verso, composants à superposer, puis photographie d'un assemblage réel pour contrôler le résultat.

**Périmètre retenu pour l'interface** : six profils — sans sauvegarde, SRAM, EEPROM, Flash,
FRAM et Flash + horloge. Le détail historique ci-dessous sert de référence pour les images ;
il n'est pas présenté comme une liste de révisions à choisir dans le panneau.
Les six aperçus sont consultables depuis les sources avec photos réelles recto/verso,
variantes EEPROM/Flash et crédits. Les cartes nues de recherche sont consultables
uniquement en développement lorsqu’un scan de la même révision est disponible. Ce choix n'est pas enregistré dans le projet et ne modifie pas
la compilation. Les versions distribuées n'exposent que SRAM en attendant les pilotes réels.

Les pastilles numérotées de la photo ont chacune une infobulle complémentaire :
rôle de la ROM, accès et conservation des données selon le type de sauvegarde,
alimentation de la SRAM ou de l'horloge par la pile, rôle du RTC. Elles ne répètent
pas les capacités de la légende. Le reste de la photo, le verso et la carte nue
n'ont pas d'infobulle de composant. Les zones de survol utilisent la même géométrie
que les repères dessinés, y compris après redimensionnement.
Référence fonctionnelle : [GBATEK, cartouches et mémoires de sauvegarde](https://www.akkit.org/info/gbatek.htm).

## Comment lire les correspondances

- **Observé** signifie qu'un exemplaire identifié associe effectivement ces composants et cette révision de carte. Le lien de source permet de retrouver le jeu, sa région et son relevé.
- Les exemples décrivent **le profil de composition de la ligne**. Ils peuvent utiliser des capacités ROM, des fabricants ou des révisions de PCB différents, précisés dans les sources. Ils ne désignent pas trois assemblages strictement identiques.
- Plusieurs références dans une cellule sont des variantes observées, **pas une autorisation de les combiner librement**. Pour dessiner une cartouche, choisir un exemplaire complet comme référence.
- Un jeu existe parfois sur plusieurs cartes, selon sa région, son tirage et sa révision. Ne jamais déduire le matériel du seul titre.
- Les associations ci-dessous servent à une représentation fidèle. Elles ne constituent pas une validation de remplacement de puces : brochage, alimentation, boîtier et câblage doivent être vérifiés séparément pour une fabrication.
- Capacités en **Mio/Kio/octets** ; une mémoire de 256 Kbit contient 32 Kio, pas 256 Kio.
- La capacité ROM désigne le composant du montage, à distinguer de l'espace occupé par le jeu et de la taille d'un fichier extrait éventuellement rembourré.

## 1. Configurations ordinaires documentées

Les références de ROM sont indiquées sans toutes leurs variantes de vitesse. Les relevés sources conservent les suffixes exacts.

| ID | Composition et cartes observées | Références de composants observées | Pile et rôle | 2 ou 3 jeux d'exemple | Photos à prévoir |
| --- | --- | --- | --- | --- | --- |
| C01 | **ROM seule** — E01-10, E01-40 dans les exemples | ROM MX23L3206-12B ou MR26V6415G ; aucune puce de sauvegarde | Aucune | Pac-Man Collection (Europe, 4 Mio) ; Alienators: Evolution Continues (Europe, 4 Mio) ; SpongeBob: Revenge of the Flying Dutchman (USA, 8 Mio) | Carte E01 de la bonne révision ; ROM correspondante. [Relevés E01](https://gbhwdb.gekkio.fi/cartridges/AGB-E01.html) |
| C02 | **SRAM 32 Kio, ancienne implantation** — E06-01 | ROM MX23L3206-12B (4 Mio) ou MX23L6406-12B (8 Mio) ; SRAM GM76V256CLLFW10 ; U3 SN74LV2416 relevé sur les deux exemplaires ; U4 à inclure | CR1616 : conserve la SRAM | F-Zero: Maximum Velocity (Europe, 4 Mio) ; Castlevania / Circle of the Moon (Europe, 8 Mio) | Carte E06-01 ; ROM ; SRAM ; U3 ; U4 ; pile à languettes ; petits composants. [Relevés E06](https://gbhwdb.gekkio.fi/cartridges/AGB-E06.html) |
| C03 | **SRAM 32 Kio, implantation E06-10** | ROM MX23L6406-12B (8 Mio) ; SRAM HY62WT081ED70C ; U3 SN74LV2416 relevé ; U4 PST3425 documenté sur la carte de réparation | CR1616 : conserve la SRAM | Wario Land 4 (Europe, 8 Mio) ; Mega Man Battle Network (Europe, 8 Mio) | Carte E06-10 ; ROM ; SRAM Hynix ; U3 ; U4 ; pile ; petits composants. [Relevés E06](https://gbhwdb.gekkio.fi/cartridges/AGB-E06.html), [nomenclature de réparation](https://github.com/jrharbort/AGB-E06-10-PCB) |
| C04 | **EEPROM 512 octets** — E03-01, E03-10, E03-21 dans les exemples | ROM MX23L3206 / MX23L6406 ; EEPROM ROHM **9853** | Aucune pour conserver la sauvegarde | Super Mario Advance (Europe, 4 Mio, E03-10) ; Rayman Advance (Europe, 8 Mio, E03-01) ; Alien Hominid (Europe, 8 Mio, E03-21) | Carte E03 choisie ; ROM ; petite EEPROM 9853. [Relevés E03](https://gbhwdb.gekkio.fi/cartridges/AGB-E03.html) |
| C05 | **EEPROM 8 Kio** — E03-20 dans les exemples | EEPROM ROHM **9854** ; ROM MX23L6406 (8 Mio) ou MX23L12806 (16 Mio) sur les exemplaires retenus | Aucune pour conserver la sauvegarde | Zelda: A Link to the Past & Four Swords (USA, 8 Mio) ; Zelda: The Minish Cap (Europe, 16 Mio) ; Mario & Luigi: Superstar Saga (Europe, 16 Mio) | Carte E03-20 ; ROM ; EEPROM 9854 distincte de 9853 dans les métadonnées. [Relevés E03](https://gbhwdb.gekkio.fi/cartridges/AGB-E03.html) |
| C06 | **Flash 64 Kio** — E02-10 dans les exemples | ROM MX23L6406-12B / -12B1 (8 Mio) ; Flash **SST39VF512-70-4C-WH** | Aucune | Advance Wars (Europe) ; Golden Sun (France) ; Sonic Advance (Europe/UKV) | Carte E02-10 ; ROM ; Flash SST. [Relevés E02](https://gbhwdb.gekkio.fi/cartridges/AGB-E02.html) |
| C07 | **Flash 128 Kio** — E02-30 dans les exemples | Flash **MX29L010TC-15A1** ; ROM MX23L12806-12C (16 Mio) ou MX23L25607-12D2 (32 Mio) | Aucune | Pokémon Rouge Feu (France, 16 Mio) ; Pokémon Vert Feuille (France, 16 Mio) ; Pokémon Mystery Dungeon: Red Rescue Team (USA, 32 Mio) | Carte E02-30 ; ROM 16/32 Mio ; Flash Macronix. [Relevés E02](https://gbhwdb.gekkio.fi/cartridges/AGB-E02.html) |
| C08 | **FRAM 32 Kio** — E11-01, E11-10 | FRAM **MB85R256 / MB85R256A** ; ROM MX23L6406 (8 Mio) / MX23L12806 (16 Mio) | Aucune : mémoire non volatile | Castlevania: Aria of Sorrow (Europe, E11-01, 8 Mio) ; Hamtaro: Ham-Ham Heartbreak (Europe, E11-01, 16 Mio) ; Kirby & The Amazing Mirror (Europe, E11-10, 16 Mio) | Carte E11 de la bonne révision ; ROM ; FRAM Fujitsu et son boîtier exact. [Relevés E11](https://gbhwdb.gekkio.fi/cartridges/AGB-E11.html) |
| C09 | **FRAM 32 Kio, variantes Y11** — Y11-01, Y11-02 | FRAM **MB85R256A / MB85R256S** ; ROM AC23V128111, MX23L12806 ou MX23L6406 selon l'exemplaire | Aucune | Final Fantasy I & II: Dawn of Souls (Europe, Y11-01) ; Castlevania Double Pack (Europe, Y11-02) ; Final Fantasy IV Advance (Europe, Y11-02) | Carte Y11 correspondante ; ROM ; FRAM A/S. [Relevés Y11](https://gbhwdb.gekkio.fi/cartridges/AGB-Y11.html) |
| C10 | **ROM 32 Mio + EEPROM 512 octets** — E24-01 | ROM **MX23L25607-12D2** ; EEPROM **9853** | Aucune | Happy Feet ; Harry Potter and the Goblet of Fire ; Shamu's Deep Sea Adventures (exemplaires Europe) | Carte E24-01 ; ROM 32 Mio ; EEPROM 9853. [Relevés E24](https://gbhwdb.gekkio.fi/cartridges/AGB-E24.html) |
| C11 | **ROM 32 Mio + EEPROM 8 Kio** — E24-01 | ROM **MX23L25607-12D2** ; EEPROM **9854** | Aucune | Harry Potter Collection ; My Animal Centre in Africa (Europe) | Même référence de PCB que C10 ; EEPROM 9854, composition à enregistrer séparément. [Relevés E24](https://gbhwdb.gekkio.fi/cartridges/AGB-E24.html) |
| C12 | **Flash 128 Kio + horloge RTC** — E05-01 | ROM **MX23L12807-12C** (16 Mio sur les versions françaises retenues) ; Flash **MX29L010TC-15A1** ; RTC **S-3511A** ; quartz | Pile pour **l'horloge**, pas pour conserver la Flash ; format exact à relever sur l'exemplaire photo | Pokémon Rubis ; Pokémon Saphir ; Pokémon Émeraude (France) | Carte E05-01 ; ROM avec GPIO ; Flash ; RTC ; quartz ; pile et languettes ; composants de support. [Relevés E05](https://gbhwdb.gekkio.fi/cartridges/AGB-E05.html) |

**Portée de C12 :** la famille E05 ne signifie pas toujours Flash 128 Kio. Le relevé de Rockman EXE 4.5 (Japon) associe cette carte à une SST39VF512 de 64 Kio et à un RTC. C'est une variante à traiter séparément si elle entre dans le catalogue. Une photo de « Flash générique » ne doit pas masquer cette différence.

Les identifications **9853 = 512 octets** et **9854 = 8 Kio** sont également documentées par [GBATEK](https://akkit.org/info/gbatek.htm#gbacartbackupeeprom).

## 2. Cartes spéciales et références encore incomplètes

Un seul titre est indiqué quand le matériel est propre à ce jeu. Deux noms régionaux d'un même jeu ne comptent pas comme deux jeux différents. « À relever » signifie que le rôle est connu mais que la référence exacte ou le montage complet n'est pas encore confirmé dans cette recherche.

| ID | Carte / composition | Composants identifiés et éléments à confirmer | Jeux / usages | Photos supplémentaires nécessaires | État |
| --- | --- | --- | --- | --- | --- |
| S01 | **E18-01 / E18-02 : solaire + RTC + EEPROM** | ROM 16 Mio MX23L12807 ou MR27V12813M ; EEPROM 9854 (8 Kio) ; RTC S-3511A ; capteur solaire, quartz, pile et circuits auxiliaires à relever | Boktai ; Boktai 2 (E18-01) ; Shin Bokura no Taiyou / Boktai 3 (E18-02) | Carte ; capteur solaire et sa fenêtre ; RTC/quartz ; pile ; autres composants. [Relevés E18](https://gbhwdb.gekkio.fi/cartridges/AGB-E18.html) | Composition principale observée ; références auxiliaires incomplètes. E18-02 non retrouvée dans l'index Archive.org consulté. |
| S02 | **E12-01 / E12-02 : inclinaison + EEPROM** | E12-02 observée : ROM MX23L6407-12C1 ou MR27V6416M (8 Mio) ; EEPROM 9853 (512 octets) ; accéléromètre **ADXL202JE** ; U1 non identifié | Yoshi's Universal Gravitation / Yoshi Topsy-Turvy : un seul jeu | Accéléromètre ; U1 ; ROM ; EEPROM ; composants de support. [Relevés E12](https://gbhwdb.gekkio.fi/cartridges/AGB-E12.html) | E12-02 documentée ; montage E12-01 à confirmer séparément. |
| S03 | **E08-01 / E08-10 : cartes de jeux à inclinaison** | Ne pas reporter automatiquement la nomenclature E12 : puces, mémoire de sauvegarde et capteur à identifier par révision | Koro Koro Puzzle: Happy Panechu! (E08-01) ; Yoshi no Banyuu Inryoku (E08-10, nom japonais du jeu Yoshi) | Carte et assemblage de chaque révision, puis capteur et puces | Usage indiqué par les fiches [E08-01](https://archive.org/details/agb-e-08-01) et [E08-10](https://archive.org/details/agb-e-08-10) ; nomenclature ouverte. |
| S04 | **M0M-01 + carte auxiliaire M0G-01 : gyroscope + vibration** | ROM **MX23L12807-12C** (16 Mio) ; FRAM **MB85R256S** (32 Kio) ; gyroscope, convertisseur analogique/numérique et moteur à relever | WarioWare Twisted! : un seul jeu | Deux PCB recto/verso ; gyroscope ; convertisseur ; moteur ; interconnexion ; FRAM | ROM/FRAM observées dans la [base matérielle](https://gbhwdb.gekkio.fi/cartridges/AGB-M0M.html). Les deux cartes partagent [une fiche Archive.org](https://archive.org/details/agb-mom-01). Fonctions gyro/vibration : [GBATEK](https://akkit.org/info/gbatek.htm#gbacartgyrosensor). |
| S05 | **ARC-01 : vibration + FRAM** | ROM **MX23L6407-12C1** (8 Mio) ; FRAM **MB85R256S** (32 Kio) ; moteur et commande à relever | Drill Dozer / Screw Breaker : un seul jeu | Carte ; moteur ; commande ; ROM ; FRAM | [Exemplaire USA observé](https://gbhwdb.gekkio.fi/cartridges/AGB-ARC.html). **ARC-30 non confirmée** ; le lien du catalogue comparatif renvoie à ARC-01. |
| S06 | **E17-01 : JoyCarry / cartouche réinscriptible DACS** | Flash NOR Sharp **LH28F320BJHE** et ASIC DACS ; ne pas confondre Flash de programme et Flash de sauvegarde. Capacité physique et zone exposée à la GBA à distinguer | Mini-jeu associé à Hikaru no Go 3 sur GameCube ; pas trois jeux commerciaux distincts identifiés | Carte E17 ; NOR ; ASIC ; autres composants | [Scan E17](https://archive.org/details/agb-e-17-01), [étude sur matériel réel](https://retrointernals.github.io/gba-joycarry-cartridge-reference/). Révision E17-01 et nomenclature complète à recouper avant assemblage visuel définitif. |
| S07 | **PEC-01 / PES-10 : e-Reader** | Lecteur optique, mémoires et contrôleurs : nomenclature à établir par modèle | Accessoire e-Reader japonais d'origine / modèle occidental ; les cartes de jeux lues ne constituent pas des variantes de PCB | Deux modèles recto/verso ; capteur optique ; mécanisme ; puces principales | [PEC-01](https://archive.org/details/agb-pec-01), [PES-10](https://archive.org/details/agb-pes-10). À garder hors du premier catalogue de cartouches ordinaires. |
| S08 | **E31-02 : GBA Video** | Mémoire vidéo/programme et logique de sélection à relever ; ne pas assimiler le montage 64 Mio à une ROM GBA ordinaire adressée directement | Cartouches GBA Video ; titres exacts par exemplaire à documenter, ce ne sont pas des jeux | Carte ; puces mémoire ; logique supplémentaire ; assemblage témoin | [Fiche E31-02](https://archive.org/details/agb-e-31-02) : utilisée pour certaines cartouches vidéo 32 Mo et les modèles 64 Mo selon sa description. |
| R01 | **Y06-01 / Y06-10** | Cartes nues trouvées ; ne pas déduire automatiquement les composants de la famille E06 | Pas d'exemplaire assemblé avec jeu et nomenclature confirmé dans cette recherche | Carte nue + exemplaire assemblé identifié avant toute superposition | [Y06-01](https://archive.org/details/agb-y-06-01), [Y06-10](https://archive.org/details/agb-y-06-10). À compléter. |
| R02 | **E06-20** | Révision à traiter à part de E06-01/-10 ; nomenclature exacte à établir | Pas de liste de 2–3 exemplaires confirmée ici | Carte nue + assemblage documenté + puces | [Scan E06-20](https://archive.org/details/agb-e-06-20). Le [projet de réparation E06-10](https://github.com/jrharbort/AGB-E06-10-PCB) exclut explicitement le remplacement des cartes E06-20. |

## 3. Exemplaires de référence à figer avant les superpositions

Ces exemplaires permettent de choisir un ensemble cohérent, au lieu de mélanger les variantes des tableaux précédents.

| Profil | Exemplaire choisi | PCB | ROM physique | Sauvegarde physique | Référence vérifiable |
| --- | --- | --- | --- | --- | --- |
| C01 | Pac-Man Collection, AGB-APCP, UKV | E01-10 | MX23L3206-12B, 4 Mio | Aucune | [ikk5-1](https://gbhwdb.gekkio.fi/cartridges/AGB-APCP-0/ikk5-1.html) |
| C02 | F-Zero Maximum Velocity, AGB-AFZP, EUR | E06-01 | MX23L3206-12B, 4 Mio | GM76V256CLLFW10, SRAM 32 Kio | [3615retro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-AFZP-0/3615retro-1.html) |
| C03 | Wario Land 4, AGB-AWAP, EUR | E06-10 | MX23L6406-12B, 8 Mio | HY62WT081ED70C, SRAM 32 Kio | [gekkio-1](https://gbhwdb.gekkio.fi/cartridges/AGB-AWAP-0/gekkio-1.html) |
| C04 | Super Mario Advance, AGB-AMAP, EUR-1 | E03-10 | MX23L3206-12B, 4 Mio | ROHM 9853, EEPROM 512 octets | [3615retro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-AMAP-0/3615retro-1.html) |
| C05 | The Minish Cap, AGB-BZMP, EUR | E03-20 | MX23L12806-12C, 16 Mio | ROHM 9854, EEPROM 8 Kio | [granmastro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-BZMP-0/granmastro-1.html) |
| C06 | Advance Wars, AGB-AWRP, EUR | E02-10 | MX23L6406-12B, 8 Mio | SST39VF512-70-4C-WH, Flash 64 Kio | [ikk5-1](https://gbhwdb.gekkio.fi/cartridges/AGB-AWRP-0/ikk5-1.html) |
| C07 | Rouge Feu, AGB-BPRF, FRA | E02-30 | MX23L12806-12C, 16 Mio | MX29L010TC-15A1, Flash 128 Kio | [3615retro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-BPRF-0/3615retro-1.html) |
| C08 | Aria of Sorrow, AGB-A2CP, EUR | E11-01 | MX23L6406-12C, 8 Mio | MB85R256, FRAM 32 Kio | [3615retro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-A2CP-0/3615retro-1.html) |
| C09 | Castlevania Double Pack, AGB-BXKP, EUR | Y11-02 | MX23L12806-12C, 16 Mio | MB85R256S, FRAM 32 Kio | [3615retro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-BXKP-0/3615retro-1.html) |
| C10 | Happy Feet, AGB-BH3P, EUR | E24-01 | MX23L25607-12D2, 32 Mio | ROHM 9853, EEPROM 512 octets | [3615retro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-BH3P-0/3615retro-1.html) |
| C11 | Harry Potter Collection, AGB-BJPP, EUR | E24-01 | MX23L25607-12D2, 32 Mio | ROHM 9854, EEPROM 8 Kio | [Relevé E24, Granmastro](https://gbhwdb.gekkio.fi/cartridges/AGB-E24.html) |
| C12 | Émeraude, AGB-BPEF, FRA | E05-01 | MX23L12807-12C, 16 Mio | MX29L010TC-15A1, Flash 128 Kio ; RTC S-3511A | [3615retro-1](https://gbhwdb.gekkio.fi/cartridges/AGB-BPEF-0/3615retro-1.html) |

Pour C11, le relevé figure dans la page actuelle consultée par l'API HTTP ; certaines versions mises en cache du site affichent moins d'exemplaires. Garder le lien de famille en attendant de figer la fiche individuelle.

## 4. Liste des photos de composants

Une photo distincte par **référence et boîtier réellement retenus**. Un même visuel peut être réutilisé entre profils lorsque c'est exactement la même pièce ; conserver la capacité et la référence dans ses métadonnées. Ne pas changer simplement le texte imprimé sur une puce pour simuler une capacité différente.

| Lot | Pièces à photographier ou trouver séparément | Utilisation | État |
| --- | --- | --- | --- |
| P01 | ROM MX23L3206-12B ; MX23L6406-12B ; MX23L6406-12C ; MX23L12806-12C ; MX23L25607-12D2 | ROM 4/8/16/32 Mio des exemplaires ordinaires | À rechercher, sans télécharger pour l'instant |
| P02 | ROM MX23L12807-12C ; MX23L6407-12C1 | Montages avec périphériques ; GPIO à respecter. Ne pas les substituer automatiquement aux variantes 06 | À rechercher |
| P03 | SRAM GM76V256CLLFW10 et HY62WT081ED70C | C02 et C03 | À rechercher ; les cartes assemblées sont déjà documentées |
| P04 | EEPROM ROHM 9853 et 9854 | C04/C05/C10/C11/S01/S02 | Deux identités distinctes malgré un aspect proche |
| P05 | Flash SST39VF512-70-4C-WH et MX29L010TC-15A1 | C06/C07/C12 | Deux photos / références, 64 et 128 Kio |
| P06 | FRAM MB85R256, MB85R256A, MB85R256S | C08/C09/S04/S05 | Capturer les variantes de boîtier pertinentes, sans présumer leur interchangeabilité |
| P07 | Superviseur U3 et reset U4 de l'exemplaire SRAM | C02/C03 | SN74LV2416 observé sur les cartes retenues ; BU9803F et PST3425 documentés dans la nomenclature de réparation. Choisir la variante exacte de l'exemplaire photographié |
| P08 | Pile CR1616 à languettes ; pile RTC après identification ; languettes seules si nécessaires | SRAM / RTC | Distinguer pile montée, pile déposée et configuration sans pile |
| P09 | RTC S-3511A ; quartz ; éléments associés | C12/S01 | Référence du quartz et pile à relever avant choix des images |
| P10 | Résistances, condensateurs et autres composants de support | Tous les PCB nus | Relever une nomenclature par carte ; les scans dépouillés n'incluent pas ces éléments |
| P11 | Capteur solaire, accéléromètre ADXL202JE, gyroscope/convertisseur, moteur de vibration | S01 à S05 | Références partielles ; pas de substitution générique |
| P12 | Flash/ASIC DACS, lecteur optique e-Reader, mémoire/commande GBA Video | S06 à S08 | Recherche ultérieure, après documentation complète du montage |

**Point de départ SRAM :** la [nomenclature de réparation E06-10](https://github.com/jrharbort/AGB-E06-10-PCB) décrit ROM TSOP-44, SRAM SOIC-28, U3 SOIC-8, reset PST3425, pile CR1616 à languettes et composants passifs. Elle indique aussi que C5 n'est pas peuplé sur son exemplaire. Ne pas remplir tous les emplacements visibles par défaut.

## 5. Index des cartes nues à prévoir

Les liens ci-dessous pointent vers les **fiches**, pas vers un téléchargement automatique. Les ZIP et vignettes sont signalés par leurs métadonnées. Pour les cartes spéciales, vérifier visuellement si le scan est réellement dépouillé avant de l'utiliser comme fond d'assemblage.

| Famille | Révisions retrouvées sur Archive.org | Profils correspondants / contrôle restant |
| --- | --- | --- |
| E01 | [01](https://archive.org/details/agb-e-01-01), [10](https://archive.org/details/agb-e-01-10), [20](https://archive.org/details/agb-e-01-20), [30](https://archive.org/details/agb-e-01-30), [40](https://archive.org/details/agb-e-01-40), [41](https://archive.org/details/agb-e-01-41) | C01 ; rattacher chaque capacité et boîtier à sa révision réelle |
| E02 | [01](https://archive.org/details/agb-e-02-01), [10](https://archive.org/details/agb-e-02-10), [20](https://archive.org/details/agb-e-02-20), [30](https://archive.org/details/agb-e-02-30) | C06/C07 ; ne pas supposer que toutes les révisions acceptent les deux tailles de Flash |
| E03 | [01](https://archive.org/details/agb-e-03-01), [10](https://archive.org/details/agb-e-03-10), [20](https://archive.org/details/agb-e-03-20), [21](https://archive.org/details/agb-e-03-21) | C04/C05 ; ROM et EEPROM à sélectionner par exemplaire |
| E05 | [01](https://archive.org/details/agb-e-05-01) | C12 |
| E06 | [01](https://archive.org/details/agb-e-06-01), [10](https://archive.org/details/agb-e-06-10), [20](https://archive.org/details/agb-e-06-20) | C02/C03 ; R02 pour -20 |
| E08 | [01](https://archive.org/details/agb-e-08-01), [10](https://archive.org/details/agb-e-08-10) | S03 |
| E11 | [01](https://archive.org/details/agb-e-11-01), [10](https://archive.org/details/agb-e-11-10) | C08 |
| E12 | [01](https://archive.org/details/agb-e-12-01), [02](https://archive.org/details/agb-e-12-02) | S02 |
| E17 | [01](https://archive.org/details/agb-e-17-01) | S06 |
| E18 | [01](https://archive.org/details/agb-e-18-01) | S01 ; **E18-02 connue dans la base matérielle mais scan nu non retrouvé ici** |
| E24 | [01](https://archive.org/details/agb-e-24-01) | C10/C11 |
| E31 | [02](https://archive.org/details/agb-e-31-02) | S08 |
| Y06 | [01](https://archive.org/details/agb-y-06-01), [10](https://archive.org/details/agb-y-06-10) | R01 |
| Y11 | [01](https://archive.org/details/agb-y-11-01), [02](https://archive.org/details/agb-y-11-02) | C09 |
| ARC | [01](https://archive.org/details/agb-arc-01) | S05 ; ARC-30 non confirmée |
| M0M + M0G | [M0M-01 et auxiliaire M0G-01](https://archive.org/details/agb-mom-01) | S04 ; **deux cartes** dans une fiche ; confirmer quels fichiers du ZIP/vignettes contiennent chaque face |
| PEC | [01](https://archive.org/details/agb-pec-01) | S07 |
| PES | [10](https://archive.org/details/agb-pes-10) | S07 |

Cet index contient **36 fiches**, regroupées dans **18 lignes**, dont une fiche annonce deux cartes (M0M/M0G). Ce n'est pas une certification d'exhaustivité de toutes les révisions GBA. Les cas E18-02 et ARC-30 restent ouverts ; les cartes de prototypes, de développement, les reproductions et les fabricants indépendants ne sont pas inventoriés ici.

## 6. Priorité de collecte et état dans l'éditeur

Pour une première bibliothèque utile, commencer par les PCB **E01-10, E06-01, E06-10, E03-10, E03-20, E02-10, E02-30, E11-01, E24-01 et E05-01** : dix fonds recto/verso couvrent déjà la plupart des profils ordinaires de ce document. Ajouter Y11-02 pour C09, puis les familles spéciales lorsque leur nomenclature est complète.

Pour chaque composition retenue, prévoir les fichiers suivants :

| Type de fichier | Contenu requis | Critère de validation |
| --- | --- | --- |
| Fond recto | PCB de la **révision exacte**, sans composants si possible | Marquage de carte lisible ; orientation et échelle connues |
| Fond verso | Même exemplaire ou même révision vérifiée | Pas de mélange entre deux routages |
| Composants séparés | Puces, pile, quartz, passifs et périphériques nécessaires | Référence, boîtier, orientation et emplacement contrôlés |
| Photo assemblée témoin | Cartouche réelle correspondant au profil | Jeu, région, révision, ROM et sauvegarde identifiés |
| Fiche de provenance | Auteur, URL, licence et éventuelles transformations | Réutilisation et redistribution clarifiées avant intégration |

Les fonds ne suffisent donc pas : il faut aussi **une référence assemblée** pour chaque composition. Les scans Archive.org consultés n'indiquent pas de `licenseurl` dans leurs métadonnées ; la disponibilité au téléchargement n'établit pas l'autorisation de redistribution. Les données et photos de la Game Boy hardware database sont annoncées sous CC BY-SA 4.0.

L'éditeur compile actuellement en **SRAM 32 Kio**. Les autres profils sont des aperçus de développement ; une image ou un schéma ne suffit pas à les rendre sélectionnables comme cibles prises en charge par le moteur.
