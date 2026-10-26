# PoolIngame

Projet de test du **pool partagé d'acteurs**. Ses scripts jouent eux-mêmes un scénario et écrivent `PASS` ou
`FAIL` dans le log de mGBA : aucune manette n'est nécessaire.

## Lancer

```
python tools/run_pool_ingame.py
```

Le script copie le projet dans un dossier temporaire, le construit, lance `mgba-sdl -l 8` une quinzaine de secondes
et affiche les verdicts (code de sortie 0 si tout passe). À la main : construire le projet dans l'éditeur (build
debug), lancer la ROM avec `mgba-sdl -l 8 rom.gba`, puis **fermer la fenêtre** pour vider le tampon du log.

## Ce que le scénario vérifie (`assets/scripts/Tests.lua`)

| Test | Vérification |
| --- | --- |
| A | Un boss né (racine et deux parties) existe ; il perd son bras (`self.Canon:destroy()`) à sa 15e image. |
| B | Trois balles spawnées pendant que le bras est détruit ne prennent pas sa place. |
| C | 600 spawns d'un coup : le pool en tient 509 (512 moins les trois du boss), le suivant rend `nil`, tout se détruit. |
| D | Une référence conservée d'une image à l'autre devient `nil` quand l'emplacement change de main. |
| E | Détruire le boss rend son groupe tout de suite (des balles le reprennent), un nouveau boss trouve une série libre. |
| F | Un héros né avance vers un mur né qui bloque : il s'arrête à `x = 134` (le mur est à 150, le héros fait 16 de large). |
| G | 40 spinners affines nés : 32 prennent une matrice, les 8 derniers sont dessinés sans rotation (avertissement debug). |

Le compteur `oam=` du log suit aussi le scénario : 3 sprites pour le boss, 2 après la perte du bras, 128 pendant la rafale
(l'OAM est pleine), 38 avec les spinners (ceux qui sortent de l'écran sont écartés).

## Ce qu'il ne couvre pas

- **L'interaction** (`Interactive`, `on_interact`) : elle demande un appui sur un bouton, que mGBA en ligne de commande
  ne sait pas simuler. Elle est vérifiée par des sondes C natives (`tests/scene/test_interact_native.py`).
- **Le rendu visuel** de la rotation et de la recomposition des parties : le scénario compte, il ne regarde pas.
  Pour le voir, ouvrir la ROM dans mGBA avec sa fenêtre.
- Un prefab né a besoin d'un script, même vide (`Wall.lua`) : sans lui, l'édition de liens échoue.
