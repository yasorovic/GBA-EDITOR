# Sonde de dépassement de frame

**Question.** Quand le travail d'une image dure plus longtemps qu'une image (≈ 16,74 ms),
le jeu *ralentit* (la logique avance moins vite que l'affichage), *saute* des images, ou
*rattrape* (rejoue plusieurs tours d'affilée) ?

Elle compte parce que tout ce que les scripts mesurent « en images » (`scene.frame`,
`wait(30)`, les compteurs d'invincibilité, les vitesses en sous-pixels par image) suppose
la réponse.

## Résultat mesuré (mGBA 0.10.5, BIOS émulé)

**Le jeu ralentit, par paliers, et ne rattrape jamais.** Un tour de logique dure un
nombre entier de rafraîchissements d'écran : `ceil(travail / 16 743 µs)`.

| Travail d'un tour | Rafraîchissements avant le tour suivant | Cadence de la logique |
| --- | --- | --- |
| jusqu'à 16,7 ms (1 image) | 1 | ≈ 60 par seconde |
| 16,7 à 33,5 ms | 2 | ≈ 30 |
| 33,5 à 50,2 ms | 3 | ≈ 20 |
| 50,2 à 67,0 ms | 4 | ≈ 15 |
| 67,0 à 83,7 ms | 5 | ≈ 12 |

Sur deux séries indépendantes (248 puis 336 tours, mêmes valeurs aux mêmes tours car
l'émulateur est déterministe) :

- **Aucun rattrapage** : 0 tour pour lequel zéro VBlank s'est écoulé.
- **Aucun tour trop rapide** : 0 tour plus court que son travail ne le permet.
- **Concordance** : `dv = ceil(travail / 16 743 µs)` sur 311 tours sur 335. Les 24 autres
  durent une image de plus, toujours à 14–495 µs *sous* une frontière : c'est le temps de
  la boucle hors de la fenêtre chronométrée (le budget de frame ne mesure que du
  `VBlankIntrWait` à la fin du tick).

Extrait (travail du tour N → VBlanks écoulés avant le tour N+1) :

```
 2 420 µs (0,14 image) → 1        29 546 µs (1,76) → 2        49 596 µs (2,96) → 3
14 864 µs (0,89 image) → 1        33 283 µs (1,99) → 3        53 988 µs (3,22) → 4
18 906 µs (1,13 image) → 2        38 003 µs (2,27) → 3        68 060 µs (4,06) → 5
```

**Conséquences pour un script.** `scene.frame` compte les tours de boucle, pas les
rafraîchissements : si un tour dépasse l'image, `scene.frame`, `wait(n)`, tous les
compteurs et les vitesses « par image » ralentissent avec le jeu. L'affichage, lui,
continue de se rafraîchir et répète le dernier état. Il n'y a pas de `dt` à compenser,
mais il faut tenir le travail d'un tour sous 16,7 ms (le build debug affiche
`frame us=N` à chaque tour pour le vérifier).

## Ce que le code établit (indépendamment de la mesure)

Lu dans la boucle principale générée (`editor/codegen/runtime_codegen/main_gen.py`) :

```c
while (1) {
    ...                       // changement de scène éventuel
    VBlankIntrWait();         // attend le rafraîchissement d'écran
    _g_frame++;               // UN incrément par tour de boucle
    ...
    g_scene_vtable[g_current_scene].tick();   // tous les on_update, la physique, l'OAM
}
```

`scene.frame` lit `_g_frame`. Chaque tour exécute exactement un `tick()`, et aucune
boucle de rattrapage n'existe : le moteur ne peut pas jouer deux tours d'affilée sans
repasser par `VBlankIntrWait()`.

## Limites

- **BIOS émulé.** Sans fichier BIOS, mGBA émule `VBlankIntrWait` en logiciel
  (« GBA BIOS: SWI: 05 » dans son journal). Le résultat vaut pour cette émulation ; une
  console réelle, ou mGBA avec le vrai BIOS, le confirmerait.
- **Un seul type de charge.** Du calcul entier (modulo logiciel). Ni la musique (la sonde
  remplace le gestionnaire VBlank, que maxmod occuperait), ni les DMA, ni les
  interruptions rapprochées n'ont été testés.
- **Un seul émulateur, un seul jeu.** Projet `Platformer` de démo, un acteur.

## Les fichiers

| Fichier | Rôle |
| --- | --- |
| `FrameOverrun.lua` | Script d'acteur qui brûle de plus en plus de temps (un palier toutes les 20 images). Vérifié par le checker et le codegen. |
| `instrument_main_c.py` | Patche le `main.c` **généré** d'un projet pour compter les VBlanks réels et écrire `PROBE tick=… dv=…` dans le journal de mGBA. |
| `analyze_probe_log.py` | Lit le journal et compare le travail de chaque tour (`frame us=`) au nombre de VBlanks écoulés ensuite. |
| `frame_overrun_probe.gba` | ROM du projet `Platformer` avec `FrameOverrun.lua`, **sans** l'instrumentation (build debug). |
| `mgba_frame_probe.lua` | Variante pour la console de scripts de mGBA (lit `_g_frame` à chaque rafraîchissement). **Jamais exécutée** : mGBA 0.10.5 n'a pas d'option pour charger un script en ligne de commande, et je ne sais pas piloter son interface graphique. |

## Rejouer la mesure

1. Construire un projet avec `FrameOverrun.lua` attaché à un acteur, **sans musique**,
   avec « build debug » coché.
2. Instrumenter puis recompiler, sans repasser par l'éditeur (il régénérerait `main.c`) :

   ```
   python tools/frame_overrun_probe/instrument_main_c.py <projet>/build/src/main.c
   cd <projet>/build
   make EXTRA_CFLAGS=-DGBA_DEBUG_BUILD
   ```

   Le drapeau est nécessaire : sans lui le `make` direct compile les fonctions de log en
   fonctions vides.
3. Lancer `mgba-sdl -l 8 <projet>/build/rom.gba > journal.txt`. **Fermer la fenêtre**
   (ne pas tuer le processus) : la sortie est mise en tampon par paquets d'environ 130
   lignes, et un arrêt brutal perd le dernier.
4. `python tools/frame_overrun_probe/analyze_probe_log.py journal.txt`

La mesure à l'horloge murale (lignes par seconde) n'est **pas** fiable : l'émulateur ne
tourne pas toujours en temps réel, et la sortie arrive par paquets. C'est pour cela que
la sonde compte les VBlanks dans la ROM elle-même.
