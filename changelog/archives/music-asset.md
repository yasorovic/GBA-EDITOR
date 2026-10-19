# L'asset `.music` (sections, boucle surchargée, indépendant du format source) — **LIVRÉ**

**Ouvert et livré le 2026-10-11** (étapes 1 à 7, plus le contrôle `1b`). Chantier technique : l'asset `.music` et l'écran Son qui le reflète. Détail déplacé tel quel depuis la roadmap.

## D'où vient la question (2026-10-11)

Deux maquettes de l'écran Son : l'une pour un module tracker (`.mod` `.s3m` `.xm` `.it`), l'autre pour un `.wav`.
Avant d'écrire l'écran, il faut dire **ce que contient** un `.music`, ce qui s'y règle, et comment il se structure
à partir de son fichier d'entrée. Le but : un seul asset, quel que soit le fichier source. L'écran n'est que le
reflet de ce modèle ; il vient après.

## Ce que Maxmod tient (lu dans `maxmod.h` et le code, 2026-10-11)

| Demande des maquettes | Verdict |
| --- | --- |
| Volume, boucle oui/non | Déjà là (`mmSetModuleVolume`, `MM_PLAY_LOOP` / `ONCE`). |
| Boucle sur une zone | **Tracker : au motif près**, `mmGetPosition()` surveillé à chaque frame, `mmPosition(début)` au dépassement ; même mécanisme que la coupe à la position (`music_transition_tick`). **WAV : à l'échantillon près**, par la boucle d'échantillon du XM encapsulé (`wav_to_xm` écrit aujourd'hui `loop_start=0, loop_len=0`). |
| Plusieurs boucles nommées | Tracker oui (plages d'ordres, une active à la fois). WAV : *non en v1* (une seule boucle d'échantillon), **oui depuis l'étape 7** (un échantillon par section). |
| Intro → boucle → outro | Tracker seulement, avec une sortie de boucle commandée. WAV : *l'outro était inatteignable* en v1 (une boucle d'échantillon ne se termine pas), **atteignable depuis l'étape 7**. |
| Tempo | Un FACTEUR 0,5 à 2,0 (`mmSetModuleTempo`), pas un BPM. Le BPM du fichier est de l'information. |
| Hauteur | Idem, facteur 0,5 à 2,0 (`mmSetModulePitch`). |
| Priorité | **N'existe pas** : une seule couche de module. Pas de champ. |
| Fondu d'entrée / de sortie | Pas natif ; c'est un pas de volume par frame (le même que les transitions de la MusicBox). |
| « Budget GBA 184 Ko / 256 Ko » | Faux : 256 Ko est l'EWRAM, un module vit en ROM. Le budget est le poids ROM, plus la RAM des canaux. |
| Waveform stéréo | Le build est mono 8 bits ; l'écran montre ce que le build produit. |

Un fait qui pèse : `MAX_SAMPLE_FRAMES` plafonne un WAV à ~62,7 s à 16 726 Hz. Le titre de 1:18 de la maquette serait
refusé tel quel ; un taux de build par musique (comme `Sfx.sample_rate`) le fait passer (à 13 kHz, ~78 s).

## Décisions verrouillées (2026-10-11)

- **Le fichier source n'est jamais modifié.** Tout ce que l'auteur règle vit dans le sidecar `.music` ; le build
  applique, le fichier reste intact.
- **Le fichier propose, le sidecar surcharge.** La position de restart d'un module est la valeur par défaut de la
  boucle ; une section bouclée la remplace. Cela **révise** la décision de la v0.8.1 (« le point de bouclage vient du
  fichier, jamais d'un champ ») : elle visait à ne pas inventer un réglage qui contredise le fichier, la surcharge
  explicite avec repli sur le fichier la respecte dans son esprit.
- **Ce qui vient du fichier n'est jamais stocké** : format, canaux, ordres, patterns, BPM, durée, waveform, poids.
  Lus par `load_module` et `Track.marks`, une seule source de vérité.
- **Tempo, hauteur, fondu d'entrée et de sortie entrent dans l'asset comme VALEURS PAR DÉFAUT, et l'API peut les
  surcharger à l'appel**, la règle du volume depuis la v0.8.6, appliquée aux trois autres. Pas de champ « priorité ».
- **L'unité des sections s'écrit dans le sidecar** (`unit: "order" | "ms"`). Remplacer un `.mod` par un `.wav` change
  l'unité : l'éditeur le dit et propose de réinitialiser les sections, jamais de les réinterpréter en silence.
- **WAV : millisecondes, calées sur le passage par zéro le plus proche au build** (pas de clic à la jointure).
  Tranché par défaut le 2026-10-11, l'auteur n'ayant pas d'avis : l'unité survit à un changement de taux.
- **Le WAV a eu UNE boucle native en v1** (pas d'outro, pas de découpe en sections). Découper un WAV en un
  échantillon par section était un chantier séparé, décidé le 2026-10-11, **ouvert et décidé le 2026-10-11 : voir
  l'étape 7**, qui REMPLACE la boucle d'échantillon.

## Le modèle

Stocké : `name`, `asset`, `volume` %, `loop`, **`unit`**, **`sections`** (`{name, color, start, end, loop}`),
**`loop_section`** (nom ; vide = tout le morceau), **`tempo`** % et **`pitch`** % (100 = neutre),
**`fade_in`** et **`fade_out`** (frames, comme les transitions), **`sample_rate`** (WAV seulement ; **0 = le taux de
`wav_module.WAV_MUSIC_RATE`**, 16 726 Hz, pas un réglage de projet : il n'y en a pas pour la musique). Les migrations
suivent `_MigrateVolumeMixin` : un sidecar sans ces champs relit les défauts, qui sont exactement l'ancien comportement.

**Précisé à l'écriture (2026-10-11).**
- **Les plages sont DEMI-OUVERTES, `[start, end)`, dans les deux unités** : la boucle saute dès que la position atteint
  `end`, et deux sections voisines (4–12 puis 12–16) se touchent sans se recouvrir. L'écran écrit « ordres 04–11 » pour
  `[4, 12)` ; le modèle n'a qu'une convention.
- **`order` = index BRUT de la table d'ordres** (cf. mesure 1) ; une section ne peut pas commencer sur un marqueur
  (`254` / `255`), un saut là ne tomberait pas sur de la musique.
- **Un WAV n'avait qu'une boucle native** (v1) ; depuis l'étape 7 il a des sections comme un module.
- **Bornes** : tempo et hauteur 50–200 % (le facteur Q10 de maxmod, 0x200–0x800), fondus 0–600 frames (10 s),
  `sample_rate` 0 ou 4 000–16 726 Hz. Hors bornes : avertissement, la valeur est ramenée dans la plage au build.
- **La durée qui tient dépend du taux** : `wav_module.max_seconds(rate)`, 62 s à 16 726 Hz, ~80 s à 13 kHz. Le
  validateur et `wav_too_long` la lisent à partir de `Music.sample_rate`.
- **Décidé à l'écriture du build (2026-10-11).**
  - **Une section de boucle boucle quel que soit le drapeau `loop`** : un module à section ne finit jamais (WAV : la
    boucle d'échantillon, tracker : `music_mode` force `MM_PLAY_LOOP`). Le drapeau ne règle plus que le morceau entier.
    Le validateur avertit quand les deux se contredisent.
  - **Un WAV n'a ni tempo ni hauteur** : ce sont des réglages du module, qui n'a qu'une note, calée sur la durée de la
    piste. Ignorés, et signalés. Ses fondus, eux, s'appliquent (c'est du volume).
  - **Un jingle n'applique que son volume** (et son taux, s'il est WAV) : il joue sur la seconde couche de maxmod.
  - **Le fondu de sortie s'applique à `music_stop`**, donc à `music.stop()`, au silence d'une scène et à un état de
    MusicBox sans musique. `music.is_playing()` reste vrai pendant le fondu. Les fondus d'une MusicBox gardent leurs
    propres `frames` : le fondu de l'asset n'intervient ni dans un `fade_to` ni dans un `cut_to`.
  - **Une boucle qui va jusqu'à la fin du morceau** passe par le restart du fichier : le module repart à son propre
    restart, sous le début de la section, et le tick le renvoie au début de la section. Il peut y entendre jusqu'à une
    frame du début du morceau ; poser le restart du fichier sur le début de la boucle, dans le tracker, l'évite.
  - **La section bouclée est celle de l'asset** (`loop_section`) : le choix à l'appel et la sortie de boucle commandée
    (jouer l'outro) sont l'étape 5.
- **Où ça vit** : le modèle dans `models/audio.py` (`MusicSection`, `Music`, `tempo_to_module`, `pitch_to_module`) ;
  le contrôle fichier ↔ réglages dans `core/music_structure.py`, appelé par `validator._check_music_structure`.

## Mesuré le 2026-10-11 (mmutil 1.10.1, maxmod du devkitPro, mGBA 0.10.5)

Méthode : des modules de test écrits à la main, convertis par `mmutil -m` (lecture de l'en-tête MAS), puis une ROM
de test qui s'auto-mesure, position, ligne, `mmActive()`, énergie et passages par zéro du tampon d'onde, une ligne
par frame dans la SRAM, lue dans le `.sav` après exécution sous mGBA. Les scripts sont jetables et ne sont pas dans
le dépôt ; les chiffres ci-dessous sont ce qu'on en retient.

1. **Numérotation des ordres : `mmutil` ne renumérote RIEN.** La séquence MAS est la table d'ordres du fichier, telle
   quelle, **séparateurs `254` et fin `255` d'un IT compris**, et le `order_count` les compte. Sur la ROM,
   `mmGetPosition()` rend cet index brut : avec `[0, 254, 1, 255]` il passe de `0` à **`2`** (le séparateur est sauté,
   mais il occupe l'index 1), puis `3` sur le `255` où la lecture s'arrête. Un `255` au milieu (`[0, 1, 255, 2, 3, 255]`)
   **termine le morceau** : les patterns 2 et 3 ne sonnent jamais, la lecture reboucle au restart. MOD et XM : 1 pour 1,
   y compris quand un même pattern revient dans plusieurs ordres.
   **Conséquence : l'éditeur et la ROM ne comptaient pas pareil** (corrigé le 2026-10-11, voir l'ordre d'implémentation) :
   `it_file` et `s3m_file` filtraient `o < 254`, donc sur un IT à séparateurs l'index de l'éditeur était décalé de la
   ROM, et un `255` au milieu laissait l'aperçu jouer des patterns que la ROM n'atteint pas. Les sections s'écrivent en
   **index brut de la table d'ordres**. **S3M mesuré ensuite** (fixture, 4 tables) : `mmutil` garde la table brute comme
   pour l'IT, `255` de fin compris, `[0, 254, 0, 255]` → `[0, 254, 0, 255]`. Seul le comportement au runtime du S3M
   n'a pas été relevé sur ROM (le format du soundbank est le même que pour l'IT).
2. **La position de restart passe.** `mmutil` l'écrit dans `repeat_position` (octet 8 de l'en-tête MAS) pour le MOD
   comme pour le XM ; un MOD à restart `127` (la valeur de ProTracker pour « aucun ») devient `0`. Au runtime,
   `MM_PLAY_LOOP` reboucle bien **à cette position** : restart 1 → `…2 → 1 → 2…`, restart 0 → `…2 → 0 → 1…`. L'IT n'a
   pas de champ restart : repli sur `0`. `mod_file` et `xm_file` la jetaient : l'aperçu rebouclait au début quand la ROM
   rebouclait au restart (corrigé le 2026-10-11).
3. **La boucle WAV tient.** Un XM d'un instrument (0,5 s de 300 Hz, puis une région de 4 180 échantillons bouclée
   (exactement 200 périodes, ~800 Hz)) avec un dernier ordre dont la dernière ligne porte `B01` (saut sur lui-même) :
   le module, qui dure ~1,2 s, reste actif et sur l'ordre 1 pendant les **14 s** observées, et le tampon reste à
   108 passages par zéro (~800 Hz) du début à la fin, sans trou ni retour de l'intro. Les témoins confirment que
   chaque pièce compte : **sans boucle d'échantillon**, le son tombe à zéro à 0,8 s alors que le module continue ;
   **sans `Bxx`**, le module s'arrête à 1,2 s (`mmActive() == 0`). Non mesuré, et à dire : l'absence de clic à la
   jointure à l'oreille (la région de test contient un nombre entier de périodes, donc la jointure est continue par
   construction). C'est ce que le calage sur un passage par zéro doit garantir pour un vrai morceau.
4. **`mmPosition()` sur un index qui ne désigne pas de pattern** (table `[0, 0, 254, 0, 0, 255]`, saut commandé depuis
   le pattern 0) : un **séparateur** (`254`), la lecture tombe sur le pattern **suivant** et continue ; un **`255`** ou une
   position **hors table**, avec `MM_PLAY_ONCE` la lecture **s'arrête** (`mmActive() == 0`, silence), avec
   `MM_PLAY_LOOP` elle **redémarre** à la position de restart. Le commentaire de `music_deck.py` (« retombe sur 0 »)
   n'était donc vrai que pour la boucle. Le mode de lecture d'une coupe est celui de la CIBLE (`Music.loop` pour un
   script, `MusicState.loop` pour une arête du graphe).
5. **Tempo et hauteur de module** : `mmSetModuleTempo` et `mmSetModulePitch` appelés **juste après `mmStart`** prennent
   effet. Tempo 200 % : les lignes passent deux fois plus vite ; 50 % : deux fois moins. Hauteur 150 % : un 300 Hz
   mesure 60 passages par zéro au lieu de 40, un 800 Hz 160 au lieu de 108 ; 200 % : le double. La hauteur change
   aussi la DURÉE d'un échantillon (il joue plus vite) sans changer celle du module, d'où leur refus pour un WAV.
6. **Le C réellement généré, compilé dans une ROM qui s'auto-mesure** (la table, `music_play` / `music_stop`, le tick de
   transition et le tick de boucle tels que `sound_emit` et `main_gen` les écrivent) : section `[2, 5)` d'un module de
   8 ordres joué avec `loop = 0` → positions `0, 1, 2, 3, 4, 2, 3, 4, 2…`, jamais au-delà de 4, lecture toujours active ;
   section `[4, 8)` jusqu'à la fin du morceau → `…, 6, 7, 4` (le retour arrière du module est rattrapé) ; fondu d'entrée
   de 60 frames → amplitude 0, 5, 11, 17, 23 puis stable ; `music_stop` avec un fondu de sortie de 60 frames → 23, 18,
   12, 6, 0 puis `mmActive() == 0` ; tempo 200 % posé par `music_play` → lignes deux fois plus rapides.
7. **Le WAV avec boucle, produit par `wav_to_xm`** (intro 300 Hz, corps 800 Hz, final 1 200 Hz ; boucle 500–1 500 ms) :
   **724 frames consécutives (13,5 s) à 107–108 passages par zéro (800 Hz)**, jamais de 1 200 Hz (le final n'est pas
   dans l'échantillon), module actif sur l'ordre 1 tout du long. Sans boucle (témoin) : 300 → 800 → 1 200 Hz puis arrêt.
   Un 440 Hz rendu à 11 025 Hz mesure 60 passages par zéro (attendu : 59) : `_tuning` accorde bien la hauteur.
8. **Tempo et `Fxx`** (module de 20 ordres ; 10 ordres parcourus) : base 285 frames ; `Fxx` à 250 bpm 142 ; facteur
   200 % 141 ; **les deux 71**, le facteur se MULTIPLIE avec le tempo du morceau (×2 × ×2 = ×4), il ne le remplace pas
   et ne se perd pas après un `Fxx`. Le rendu de l'aperçu l'applique donc à chaque tick.

9. **Les surcharges d'API, sur le C réellement généré** (module de 8 ordres, 60 frames par seconde) :
   `music_set_section` à la frame 150 (sections A `[0, 2)` puis B `[4, 6)`) → `0, 1, 0, 1, 0, 1` puis `1, 2, 3, 4, 5, 4, 5…` (le
   module finit de jouer son ordre, rejoint la nouvelle section, et la boucle) ; `music_leave_loop` à la frame 150
   (section `[2, 5)`) → `…2, 3, 4, 2, 3, 4` puis `5, 6, 7` et **arrêt** au retour arrière (dernière frame active : 313) ;
   `music_fade_out(60)` sans fondu sur l'asset → 23, 18, 12, 6, 0 puis `mmActive() == 0` ; `music_fade_in` → 0, 5, 11, 17, 23 ;
   `music_set_tempo(2048)` → un ordre toutes les 14 frames au lieu de 29 ; `music_set_pitch(1536)` → 160 passages par zéro au
   lieu de 108. (Le banc passait d'abord `tempo = 0` pour « pas de réglage » : le plancher de 50 % a fait tourner à demi-vitesse
   les premières ROM de la série, sans toucher aux séquences de positions ni aux amplitudes consignées plus haut.)

## Ordre d'implémentation (proposé)

1. ~~Les trois mesures~~, faites (ci-dessus). ~~Les lecteurs alignés sur la ROM~~, **livré le 2026-10-11** :
   `Module.order` est la table brute (`ORDER_SKIP` 254, `ORDER_END` 255, `is_pattern_order`), `Module.restart` est lu
   par `mod_file` / `xm_file` (`effective_restart` : hors table → 0), le rendu s'arrête sur un `255`, `Track.restart`
   fait reboucler le deck à l'ordre de restart, l'import refuse une table qui ne porte que des marqueurs. Tests :
   `tests/audio/test_module_formats.py` § 3 et 4, fixtures paramétrées par `orders` / `restart`.
1b. ~~Le contrôle `cut_to`~~, **livré le 2026-10-11** : `music_structure.cut_problems` vérifie que chaque position où la
   source peut se trouver désigne un pattern dans la cible (au lieu de comparer des longueurs), nomme la première
   position fautive et la conséquence selon le mode de lecture, et sert à la fois les scripts
   (`_check_music_cut_compat`) et les arêtes `cut` d'une MusicBox (`_check_sound_boxes`, y compris « depuis n'importe
   quel état »). Une source WAV est signalée (la coupe attend la fin de son pattern, ~5 s), comme l'était déjà une cible
   WAV. L'aperçu fait la même chose que la ROM (`Track.start_of` rend `None` hors musique : redémarrage avec la
   boucle, arrêt sans). Limite connue du deck : un pattern jamais atteint par le rendu (sauts `Bxx`) y est traité comme
   un séparateur. Tests : `tests/audio/test_cut_compat.py`.
2. ~~Modèle : champs, unité, migration, validateur~~, **livré le 2026-10-11** (voir « Précisé à l'écriture »).
   Tests : `tests/audio/test_music_model.py`. **Pas encore émis** : rien n'est lu par le build (étape 3), l'aperçu
   (étape 4) ni l'API (étape 5). Les champs s'écrivent et se relisent, c'est tout.
3. ~~Build : boucle de section au codegen (tracker), boucle d'échantillon dans `wav_module.py`, fondus et facteurs~~,
   **livré le 2026-10-11**. `wav_module` : taux choisi (`_tuning`), boucle d'échantillon calée sur un passage par zéro
   montant, module qui saute sur lui-même, échantillon tronqué à la fin de la boucle (la ROM n'y met pas le final).
   `sound_emit` : `music_info_row` / `music_runtime_lines` (table `g_music_info`, une ligne par module réglé,
   `music_play` / `music_stop` / `music_set_volume` définis dans `main.c` et plus `static inline`, `music_loop_tick`).
   `main_gen` : modes 3 (fondu d'entrée) et 4 (fondu de sortie) dans `music_transition_tick`, réglages réappliqués à
   chaque `mmStart` (transitions comprises). `grit_conversion` : taux et région passés à l'encapsulation. Tests :
   `test_wav_loop.py`, `test_music_runtime_emit.py`, `rom_build/test_music_settings_build.py` (build réel).
4. ~~Aperçu : `MusicDeck` apprend la région de boucle, le même code que la ROM, pas un repli de thème~~, **livré le
   2026-10-11**. `music_info_row` est dans `core/music_structure` : le build ET l'aperçu lisent la même ligne. `MusicDeck`
   rejoue la machine d'états du C, modes 3 et 4 (fondus d'entrée et de sortie), `music_stop` distinct de l'arrêt sec du
   lecteur, tick de section avec son retour arrière, boucle forcée, boucle d'échantillon d'un WAV, coupe sans musique
   (redémarrage ou arrêt selon la boucle). `render_module_marked` prend un tempo et une hauteur ; `render_wav` (supprimé à l'étape 7) passait par
   `wav_module.render_at_rate` / `loop_frames`, le taux, la quantification à 8 bits et la jointure sont ceux du
   build. `BoxPlayer` clé son cache par tout ce qui change le rendu (chemin, tempo, hauteur, taux, boucle) et pose les
   fondus et la section sur une copie du `Track`. Tests : `tests/audio/test_music_preview.py`, le deck rejoué contre les
   séquences mesurées sur ROM (mesures 5 à 8).
5. ~~API : surcharge à l'appel de tempo, hauteur, fondus, et choix de la section~~, **livré le 2026-10-11**, six appels
   (`music:set_tempo(p)`, `music:set_pitch(p)`, `music:fade_in("Nom", frames)`, `music:fade_out(frames)`,
   `music:set_section("Section")`, `music:leave_loop()`). Ils surchargent la LECTURE EN COURS ; une musique qui démarre
   reprend les réglages de son asset (`music_apply`). **Décidé le 2026-10-11 : `set_section` agit sur la musique en
   cours, sans la nommer**, d'où une table `g_music_sec` en ROM (module, rang du nom, début, fin) et un nouveau domaine
   `music_section`. Le rang d'un nom est son index dans la liste TRIÉE des noms de section de TOUTES les musiques du
   projet (`core/music_structure.music_section_names`) : c'est à la fois la constante `MSEC_*` du script et la clé de la
   table, tirées de la même liste. Une musique laissée hors de la ROM ne décale rien. Le vérificateur refuse un nom
   qu'AUCUNE musique ne porte ; un nom qui existe ailleurs mais pas dans la piste qui joue ne fait rien à l'exécution
   (dit dans la doc de l'appel). **Limites assumées** : renommer une section dans l'éditeur ne met pas les scripts à
   jour (le build annonce le nom inconnu) ; un nom de section est propre à SA musique, donc non suivi par le
   renommage global ; `set_section` sur un module démarré sans boucle ni section peut le voir finir avant que la section
   ne boucle, si elle va jusqu'à la fin du morceau. `leave_loop` joue la fin du morceau puis ARRÊTE (le module a été
   démarré en `MM_PLAY_LOOP` : un retour arrière de la position est la fin) ; sans effet sur un WAV, dont l'outro n'est
   jamais jouée. `music.fade_in` entre dans l'allowlist de la grammaire de l'API (`test_aucune_fonction_de_module…`) :
   c'est le verbe `music.play`, avec un fondu. Tests : `tests/scripting/test_music_api.py`, et le build réel
   (`test_music_settings_build.py`) compile et lie un script qui appelle les six.
6. ~~Écran Son : un écran, la zone de structure change selon le format ; maquettes corrigées (pas de priorité, budget
   ROM)~~, **livré le 2026-10-11**. Pour une musique, la colonne centrale montre un `MusicEditor` (en-tête avec son état
   « prête pour le build » ou « N à corriger », lu sur les mêmes contrôles que le validateur ; forme d'onde ; zone de
   structure du FORMAT). **Module** : la bande des ordres (une cellule par position de la table BRUTE, les séparateurs
   grisés et non sélectionnables, glisser pour choisir une plage) et le tableau des sections (boucle, par défaut,
   couleur, nom, début, fin, durée, écoute, retrait, tout en place, le « + » crée une ligne dont le nom prend le focus,
   et prend la plage choisie sur la bande). **WAV** : la boucle à deux poignées sur la forme d'onde, avec ses bornes en
   secondes. La forme d'onde est le `Track` du deck (`BoxPlayer.track_for`) : ce qu'on voit est ce qu'on entend, taux et
   quantification du build compris. L'inspecteur de droite gagne tempo, hauteur, fondus et taux (WAV seulement) ; tempo
   et hauteur sont grisés pour un WAV, et un jingle n'a ni ces réglages ni de sections. Le ▶ d'une ligne joue la musique
   depuis le début de la section et boucle dessus (`BoxPlayer.preview(…, section)`). Des sections écrites pour une autre
   famille de fichier (un `.mod` remplacé par un `.wav`) ne sont jamais réinterprétées : un bandeau le dit et propose de
   les réinitialiser. **Écarts assumés avec les maquettes** : ni priorité (Maxmod n'en a pas), ni budget « 256 Ko »
   (le poids ROM de l'inspecteur reste le seul chiffre), ni carte « Selected loop » (le tableau est l'unique lieu d'édition
   d'une section), ni marqueurs Intro/Outro sur un WAV (l'outro n'y est jamais jouée), ni « Create loop from selection »
   comme bouton séparé (le « + » prend la sélection). Tests : `tests/ui/test_music_editor.py` et
   `tests/ui/test_sound_screen_music.py`. **Le rendu a été regardé, pas seulement testé** : une capture a montré le
   tableau écrasé quand il est reconstruit alors que l'éditeur est caché (la demande de mise en page ne remonte pas),
   corrigé par un `updateGeometry()` après chaque reconstruction.

7. ~~**Le WAV en sections, un échantillon par section**~~, **livré le 2026-10-11**. Voir ci-dessous.

## Étape 7 (aligner le WAV sur le module)

**Le but** : un seul modèle pour tout le module musical. Un `.wav` a des sections nommées, une section de boucle,
un outro atteignable, et les widgets de l'écran Son sont ceux d'un module (tableau des sections, ▶ par ligne).
`set_section`, `leave_loop`, `cut_to` et les fondus marchent sans cas particulier : **le build écrit un VRAI module**
(un échantillon XM et un ou plusieurs patterns par segment, une position d'ordre par pattern), et tout ce qui lit des
positions d'ordre (`music_info_row`, `g_music_sec`, le tick de boucle, le deck) le lit tel quel.

**Décidé le 2026-10-11.**
- **L'unité d'un WAV reste la milliseconde** (`unit: "ms"`) : elle survit à un changement de taux. Le build convertit
  les millisecondes en positions d'ordre (`wav_module.plan_wav`), et c'est cette conversion que `music_info_row` et
  `music_section_rows` consultent pour un WAV.
- **Le segment est l'unité de découpe** : les frontières de toutes les sections (début et fin) découpent la piste en
  segments, un échantillon XM chacun ; une section est une plage de segments contigus. Des sections qui se recouvrent
  ou laissent des trous restent légales (comme pour un module).
- **Les frontières tombent sur la grille des lignes.** Une section qui change d'échantillon doit le faire PILE à la
  fin de celui d'avant (sinon un trou ou une reprise), et le module ne déclenche une note qu'au début d'une ligne : la
  frontière est donc arrondie à la ligne la plus proche, soit **±5,7 ms**. Le calage sur un passage par zéro de la v1
  disparaît (il déplaçait la frontière hors de la grille) ; une jointure de boucle n'est plus protégée du clic.
- **Vitesse 1, 219 BPM : une ligne = 180 échantillons de mixage = 11,4155 ms, exactement.** Mesuré sur ROM : à 255 BPM
  (l'ancien réglage) maxmod tronque le tick à un nombre entier d'échantillons de mixage (154 au lieu de 154,59), donc
  les lignes passent **0,4 % trop vite**, 33 ms de dérive sur 8 s, de quoi couper la queue d'un segment. À 219 BPM le
  tick tombe juste (15 768 Hz × 2,5 / 219 = 180) : cinq segments de 8 s enchaînés se suivent de 478 frames chacun, sans
  dérive ni trou.
- **L'échantillon est ré-échantillonné au taux RÉELLEMENT joué** : `_tuning` arrondit à 1/128 de demi-ton (jusqu'à
  0,27 % d'écart de hauteur), ce qui allongerait ou raccourcirait un segment par rapport aux lignes ; on rend donc la
  piste au taux accordé (le défaut, 16 726 Hz = 2 × 8 363, est exact).
- **Un segment trop long est coupé en morceaux** à une limite de ligne (`MAX_SAMPLE_FRAMES`, ~61 s à 16 726 Hz) : la
  limite de durée n'est plus celle d'un échantillon mais celle de la table d'ordres (256 positions de 256 lignes au
  plus, soit ~12 min).
- **La boucle d'une section WAV se fait comme celle d'un module : par la surveillance de la position**
  (`music_loop_tick`). Mesuré sur ROM le 2026-10-11 : à chaque tour, ~10 ms de la section suivante fuient avant que la
  position ne soit renvoyée (zéro-passages 112–124 au lieu de 108 sur trois frames) ; un saut `Bxx` écrit dans la
  dernière ligne de la section aurait été exact mais aurait interdit `leave_loop`. **Choix retenu** : le même
  comportement qu'un module, `leave_loop` compris.
- **Tempo et hauteur restent ignorés pour un WAV** (les lignes accélèrent, l'échantillon non : les segments se
  décaleraient). Les fondus s'appliquent.
- **La piste entière est maintenant dans la ROM** : l'ancien WAV à boucle jetait ce qui suit la boucle, qui est
  désormais l'outro. La pastille de poids le dit déjà (c'est le module que le build écrit).

**Ordre** : 7a `wav_module` (plan, grille, build multi-échantillon, constantes) · 7b `music_structure` (frontières,
ordres, lignes d'info et de sections, poids, problèmes) · 7c build (`grit_conversion`, `sound_emit`) · 7d aperçu (le
`Track` d'un WAV est celui du module généré ; `wav_render` et `sample_loop` supprimés) · 7e validateur et API (plus de
« une seule boucle », `leave_loop` documenté) · 7f écran (tableau des sections en secondes, bandes sur la forme
d'onde) · 7g documentation, test de build réel, mesure ROM du module généré. **Les sept sont livrés (2026-10-11).**

**Livré.**
- `wav_module` : `plan_wav` (frontières → lignes → segments → positions d'ordre), `wav_to_xm(path, rate, boundaries_ms)`,
  `played_rate`, `ROW_SECONDS`, `max_seconds()` (la table d'ordres, ~12 min, ne dépend plus du taux). Disparus : la boucle
  d'échantillon, le saut `Bxx`, le calage sur un passage par zéro, `loop_frames`, `render_at_rate`.
- `music_structure` : `wav_boundaries`, `wav_plan`, `wav_section_orders` (l'unique traduction ms → ordres) ;
  `music_info_row(m, path)` et `music_section_rows(m, path)` prennent le fichier ; `MIN_SECTION_MS` (50 ms) ; le validateur
  signale une section plus courte qu'une ligne ; plus d'erreur « une seule boucle ».
- Aperçu : `BoxPlayer` rend un WAV par `parse_xm(wav_to_xm(…))` puis `render_module_marked`, comme un module, le `Track`
  a ses repères et ses sections en ordres. Le rendu des modules reporte maintenant la durée de tick de la ROM (tronquée à un
  nombre entier d'échantillons du mixeur, fraction reportée d'un tick au suivant) ; le garde-fou `_MAX_VISITED` passe de
  4 096 à 65 537 lignes (il coupait un WAV à 47 s).
- Écran : le MÊME tableau des sections pour un WAV (début et fin en secondes, fin exclue) et pour un module (ordres) ;
  bandes colorées sur la forme d'onde ; les deux poignées déplacent la section de boucle par défaut ; la bande des ordres
  reste propre au module ; « + » ajoute une section après la dernière (le milieu de la piste pour la première).
- API : `set_section` et `leave_loop` valent pour un WAV (docs corrigées).

**Mesuré sur ROM (2026-10-11, banc jetable, C réellement généré).**
10. *Boucle d'une section par la surveillance* : à chaque tour, ~10 ms de la section suivante fuient (zéro-passages
    112–124 au lieu de 108 sur trois frames) ; avec un `Bxx` en dernière ligne : 108 partout. Choix retenu : la
    surveillance (le comportement d'un module, `leave_loop` compris).
11. *Dérive ligne ↔ échantillon* : cinq segments de 8 s à 255 BPM se suivent de 475,8 frames au lieu de 477,8 (0,4 % trop
    vite : maxmod tronque le tick à 154 échantillons de mixeur au lieu de 154,59). À 219 BPM : 478 frames chacun, exact.
12. *Le module que le build écrit, de bout en bout* (intro 300 Hz, boucle 800 Hz, outro 1 200 Hz ; `music_info_row` = [1, 2)) :
    l'intro joue une fois, la boucle tient (107–108 zéro-passages, jamais de 1 200 Hz) ; `music_leave_loop` à la frame 150
    finit la boucle, joue l'outro (160 zéro-passages, ~1 s) puis s'arrête (`mmActive() == 0`). Taux choisi de 11 025 Hz
    (accordé à 11 023,1) : cinq segments de 8 s enchaînés, 478 frames chacun, aucune dérive.

**La table de mixage (2026-10-11).** Volume, tempo et hauteur d'une musique ne sont plus dans l'inspecteur : ce sont
trois curseurs verticaux à droite des sections (`ui/sound_mixer/mix_faders.py`), un double-clic remet le neutre. **L'aperçu
les suit en direct, au tick près** : le volume passe tout de suite (`MusicDeck.set_volume`), et l'aperçu d'un module
n'est plus un rendu entier joué d'un trait mais un module joué TICK PAR TICK (`core/engine_emulation/module_stream.py`,
`StreamTrack`) : le tempo et la hauteur sont lus à chaque tick, donc un curseur qu'on bouge s'entend au tick suivant, sans
rendu à refaire ni saut. **Pourquoi** : une première version rendait le morceau en arrière-plan à chaque cran (0,3 à
0,7 s par rendu sur les modules de la démo) et figeait l'écran ; les pauses du curseur tenu relançaient aussi un
rendu synchrone et une écriture du JSON. **Comment** : `render_module_marked` est devenu `iter_module_ticks`, un
générateur qui rend un tick à la fois (sortie bit à bit identique au rendu précédent, vérifiée sur dix rendus) ; un
saut de position (`mmPosition`) y est demandé par `TickState.jump_to` et prend effet au tick suivant, canaux gardés.
`StreamTrack` est un `Track` pour le deck (mêmes réglages, mêmes questions) : la boucle d'une section, les fondus et
le volume restent ceux de `MusicDeck`, un seul endroit où la ROM est rejouée. Le rendu entier ne sert plus qu'à dessiner
l'onde (la frise sur laquelle la tête de lecture se situe) et aux boîtes. **Le JSON ne s'écrit qu'au relâchement** du
curseur (une molette ou une flèche du clavier attend 300 ms de calme) ; l'onde ne se redessine qu'au relâchement aussi.
L'onde elle-même est peinte une fois et gardée (`QPixmap`) : seule la tête de lecture se repeint à chaque image (mesuré :
la boucle d'événements passe de 44 à 6 ms par image pendant l'écoute). Un WAV grise tempo et hauteur, un jingle ne garde
que le volume ; l'infobulle du curseur grisé dit pourquoi. L'inspecteur garde les fondus et le taux.

**Tout tient à l'écran, sans défilement** : une musique propose au plus **6 sections** (`music_structure.MAX_SECTIONS` :
le « + » disparaît au maximum, le validateur avertit d'un fichier qui en porte plus), le tableau est dans une carte au fond
plus sombre, ferrée en bas et de hauteur constante (la place de six lignes), l'onde prend toute la hauteur que le reste ne
demande pas, et les curseurs remplissent la hauteur de la zone du bas. Les réglages d'une section ou d'un curseur n'ont
plus à recharger le Sound finder.

**Limites assumées.** Les frontières sont arrondies à la ligne (±5,7 ms) ; la jointure d'une boucle n'est plus calée
sur un passage par zéro (un clic est possible si l'auteur place mal ses bornes) ; ~10 ms de la section suivante fuient à
chaque tour de boucle ; tempo et hauteur restent ignorés pour un WAV ; la piste entière est dans la ROM (l'outro aussi) ;
`cut_to` depuis ou vers un WAV garde son avertissement (la coupe n'atterrit sur une note qu'au début d'un segment).

## Ce que ça ne fait pas

- Ne donne pas de tempo ni de hauteur à un WAV (voir l'étape 7).
- Ne modifie jamais le fichier source, et ne réécrit pas un module tracker.
- N'ajoute ni muet par canal ni solo : Maxmod n'a pas d'API pour ça, l'aperçu mentirait.
