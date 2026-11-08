# Lecteur web

Lecteur HTML que **Game > Build WEB** recopie dans le ZIP de chaque jeu, à côté de la
ROM. Sous licence zlib (voir `LICENSE`), comme le moteur `runtime/`. Les composants
tiers gardent leurs licences : `vendor/` (mGBA, MPL-2.0), `shaders/` (MPL-2.0 ou MIT),
polices Sniglet et Balsamiq Sans (SIL OFL 1.1).

## Essayer le lecteur

Depuis la racine du dépôt :

```powershell
node tools/web_player_server.mjs
```

Ouvrir ensuite `http://localhost:8000`, choisir une ROM `.gba`, puis cliquer sur
**Jouer**. Le lecteur se charge depuis HTTP sur localhost ou depuis HTTPS sur un
hébergement web.

## Essayer le ZIP de l'éditeur

**Game > Build WEB** compile le projet et écrit `<nom du projet>-web.zip` dans son
dossier `build/`. Le ZIP contient une copie du lecteur et la ROM du projet. Une fois
extrait, `index.html` se lance d'un double-clic : le navigateur refuse les modules ES
et `fetch` depuis le disque (file://), donc l'export réunit les modules dans
`player.js` (shaders compris) et écrit la ROM (`rom.js`) et le moteur
(`vendor/mgba.wasm.js`) en base64, environ un tiers de plus que les fichiers bruts.
Seules les formes `import { … } from "./…"` et `export` nommées ou par défaut sont
acceptées par cet assemblage.

Le même dossier peut aussi être servi en HTTP, comme sur itch.io :

```powershell
node tools/web_player_server.mjs "chemin/du/ZIP/extrait"
```

Ouvrir `http://localhost:8000` et cliquer sur **Jouer**. La ROM est déjà chargée par
la page. Les modifications de ce dossier sont prises en compte au prochain build
web. La variable `BACKSTAGE_WEB_PORT` permet de servir le lecteur et le ZIP extrait
sur deux ports distincts.

## Ce qui est testé

- démarrage d'une ROM locale dans mGBA WebAssembly ;
- son activé uniquement après le clic sur **Jouer** ;
- affichage entier sans lissage et plein écran ;
- lecture et écriture des sauvegardes GBA dans le volume IndexedDB des exports
  précédents, restaurées avant la première frame ;
- manette : croix directionnelle ou stick gauche, mapping bouton par bouton stocké
  localement dans le navigateur ;
- mobile : commandes tactiles sous le jeu en mode vertical et sur les côtés en mode
  horizontal si le cadre est assez large. Le bouton Vue mobile permet de tester les
  deux dispositions sur ordinateur.

Le lecteur fonctionne sur itch.io sans l'option **SharedArrayBuffer support**. Les
gabarits éjectés qui utilisent encore l'ancien moteur gardent ce prérequis.

## Personnaliser le contour

Le menu **Contour** propose **Made with Backstage**, **Aucun** ou **Image
personnalisée**. Pour du pixel art, dessiner par exemple un PNG carré de 64 × 64 px.
Réserver 16 × 16 px à chaque coin, dessiner les bords entre les coins et laisser le
carré central transparent. Le lecteur étire les bords pour suivre sa taille.

## Le moteur mGBA

`vendor/` vient de `@wasm-gaming/mgba-wasm` **0.1.1** (MPL-2.0), intégrité npm
`sha512-PviwdUQGasp6QlXa0cl0ccUj0z5zGMITkwmAsZy9yOVpJpO4IYRmMQUBlwLvnpDMh9EhqbED+bgXyPheb3zL1Q==`.
Deux fichiers sont modifiés, et leur source modifiée est livrée :

- `mgba.sdk.js` (source : `mgba.sdk.ts`) : commandes fournies par la page et
  chargement/lecture de la sauvegarde ;
- `mgba.js` et `mgba.wasm`, recompilés avec `mgba_shim.c` : une sauvegarde GBA
  restaurée avant la première frame est attachée comme fichier de sauvegarde de la
  cartouche. Le moteur d'origine la restaurait avant que la cartouche ait choisi sa
  puce, et rien n'était écrit.

Pour recompiler `mgba.js` et `mgba.wasm` (sous Linux ou WSL, avec emsdk 6.0.12 et
CMake 3.31 dans le `PATH`) :

```bash
git clone --branch v0.1.1 https://github.com/wasm-gaming/mGBA-wasm.git
cp web_player/vendor/mgba_shim.c mGBA-wasm/scripts/shim/mgba_shim.c
cd mGBA-wasm && bash scripts/build-mgba.sh
```

Le script clone mGBA au commit `c034660f007c543233f1cadeb0ca13c71afd8f41`. Copier
ensuite `dist/mgba/mgba.js` et `dist/mgba/mgba.wasm` dans `web_player/vendor/`.
