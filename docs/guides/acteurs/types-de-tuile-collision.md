# Types de tuile de collision

La carte de collision d'une scène est une grille de tuiles de 8 × 8 pixels. Chaque case porte un
**index de type** : un entier de `0` à `25`. C'est cet entier que le jeu lit pour savoir si un acteur
est arrêté, s'il se pose sur une pente ou s'il peut traverser une face.

Il y a **26 types**, un index chacun. Les pentes en demandent beaucoup parce que chaque angle existe
en plusieurs morceaux : une pente douce s'étale sur deux tuiles, une pente raide sur deux tuiles
superposées, et chaque pente de sol a son miroir pour le plafond.

## Voir les index et les normales

Deux boutons de la barre du canvas aident à lire la carte :

- **Index des tuiles de collision** écrit sur chaque tuile non vide l'index du tableau ci-dessous ;
- **Normales de collision** trace, depuis le centre de chaque face, une ligne qui part dans le sens
  opposé à la matière : c'est le côté d'où un acteur arrive pour se poser ou se cogner. Un bloc plein
  n'en porte que sur ses faces exposées.

Chacun rend la carte visible, même si le bouton **Collisions de la scène** est éteint. Les trois
vues se combinent.

## Les familles

- **Vide** : rien n'arrête l'acteur.
- **Plein** : le seul type qui repousse un acteur de côté (un mur).
- **Sol** : la matière est sous la droite de la surface. L'acteur marche dessus ; une pente de sol ne
  le repousse pas de côté, il la monte.
- **Plafond** : la matière est au-dessus de la droite. L'acteur s'y cogne la tête.
- **Sens unique** : une face plate qu'on ne franchit que dans un sens (voir plus bas).

## Tableau des index

| Index | Constante | Famille | Forme |
|------:|-----------|---------|-------|
| 0 | `TILE_EMPTY` | Vide | Case vide. |
| 1 | `TILE_SOLID` | Plein | Bloc plein. |
| 2 | `TILE_SLOPE_L` | Sol | Pente à 45°, montante. |
| 3 | `TILE_SLOPE_R` | Sol | Pente à 45°, descendante. |
| 4 | `TILE_SLOPE_L_LO` | Sol | Pente à 26°, montante : tuile de gauche (la plus basse). |
| 5 | `TILE_SLOPE_L_HI` | Sol | Pente à 26°, montante : tuile de droite (la plus haute). |
| 6 | `TILE_SLOPE_R_LO` | Sol | Pente à 26°, descendante : tuile de droite (la plus basse). |
| 7 | `TILE_SLOPE_R_HI` | Sol | Pente à 26°, descendante : tuile de gauche (la plus haute). |
| 8 | `TILE_SLOPE_L_INV` | Plafond | Pente à 45°, montante. |
| 9 | `TILE_SLOPE_R_INV` | Plafond | Pente à 45°, descendante. |
| 10 | `TILE_SLOPE_L_LO_INV` | Plafond | Pente à 26°, montante : tuile de gauche. |
| 11 | `TILE_SLOPE_L_HI_INV` | Plafond | Pente à 26°, montante : tuile de droite. |
| 12 | `TILE_SLOPE_R_LO_INV` | Plafond | Pente à 26°, descendante : tuile de droite. |
| 13 | `TILE_SLOPE_R_HI_INV` | Plafond | Pente à 26°, descendante : tuile de gauche. |
| 14 | `TILE_SLOPE_R_STEEP_HI` | Sol | Pente raide à 63°, descendante : tuile du haut (petit triangle). |
| 15 | `TILE_SLOPE_R_STEEP_LO` | Sol | Pente raide à 63°, descendante : tuile du bas (grand quadrilatère). |
| 16 | `TILE_SLOPE_L_STEEP_HI` | Sol | Pente raide à 63°, montante : tuile du haut (petit triangle). |
| 17 | `TILE_SLOPE_L_STEEP_LO` | Sol | Pente raide à 63°, montante : tuile du bas (grand quadrilatère). |
| 18 | `TILE_SLOPE_R_STEEP_HI_INV` | Plafond | Pente raide à 63°, descendante : tuile du bas. |
| 19 | `TILE_SLOPE_R_STEEP_LO_INV` | Plafond | Pente raide à 63°, descendante : tuile du haut. |
| 20 | `TILE_SLOPE_L_STEEP_HI_INV` | Plafond | Pente raide à 63°, montante : tuile du bas. |
| 21 | `TILE_SLOPE_L_STEEP_LO_INV` | Plafond | Pente raide à 63°, montante : tuile du haut. |
| 22 | `TILE_ONEWAY_UP` | Sens unique | Face du haut : porte par le dessus. |
| 23 | `TILE_ONEWAY_DOWN` | Sens unique | Face du bas : porte par le dessous. |
| 24 | `TILE_ONEWAY_LEFT` | Sens unique | Face de gauche : arrête par la gauche. |
| 25 | `TILE_ONEWAY_RIGHT` | Sens unique | Face de droite : arrête par la droite. |

Dans le nom, `L` et `R` disent si la pente monte ou descend vers la droite, `LO` et `HI` la tuile
basse ou haute d'une pente qui en occupe deux, `STEEP` une pente raide et `INV` le miroir pour le
plafond. Vous n'avez normalement pas à choisir un index à la main : les pinceaux et les pentes de la
barre d'outils posent le bon.

## Les faces à sens unique

Une face à sens unique n'arrête un acteur que s'il vient du côté vers lequel elle regarde (sa
normale). Un acteur qui arrive de l'autre côté passe au travers.

- **Haut (22)** : la plateforme classique. On la traverse par en dessous et on se pose dessus.
- **Bas (23)** : on la traverse par le dessus et on bute dessous.
- **Gauche (24)** et **droite (25)** : une porte qu'on ne franchit que dans un sens, vers le côté de
  la face.

Pour descendre à travers une face qui vous porte, appelez `body:drop_through(frames)` : le corps
ignore les faces à sens unique pendant ce nombre de frames. Une boîte de collision d'acteur peut
aussi offrir une face à sens unique (réglage **Sens unique** du composant) ; elle suit les mêmes
règles.
