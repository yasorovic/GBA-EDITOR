# PongAdvanced — assets: origin and licence

Fonts are documented by their own notices in this folder (`Font8x8.txt`, `GNU-Unifont-JP.txt`,
`Misaki.txt`). This file covers everything else the project ships.

**Status: draft.** The origin and licence of each line below are NOT yet confirmed. A cell reading
`TO CONFIRM` must be filled in by the person who made or obtained the asset before this project is
distributed as a template. Nothing here is assumed: only what can be read from the files is stated.

## Redistribution warning

The music and the sound effects were taken, as far as the author remembers, from the Spriters
Resource network of sites (exact pages not recorded). Those sites collect assets extracted from
commercial games: the copyright stays with the original game's rights holder, and the site does not
grant a licence to redistribute them. **They must not ship in a publicly distributed template as
they are.** Before release, replace them with assets whose licence allows redistribution (own work,
CC0, CC-BY with credit, …) and record the new origin below.

## Music — `assets/music/` (17 modules, 3 tracks)

Tracker modules (`.mod`) built on a Game Boy–style instrument set (pulse, wave and noise channels).
The module title is the only metadata they carry; they name no author and no licence.

| Track | Variants shipped | Author | Licence / terms | Source |
| --- | --- | --- | --- | --- |
| Claimed DX | normal, FAST, SLOW, DRUMLESS, DRUMLESS FAST, DRUMLESS SLOW | TO CONFIRM | None granted (see warning) | Spriters Resource network, page not recorded |
| Admin Rights - Full DX | normal, FAST, SLOW, DRUMLESS, DRUMLESS FAST, DRUMLESS SLOW | TO CONFIRM | None granted (see warning) | Spriters Resource network, page not recorded |
| Crystal Clear DX | normal, FAST, SLOW, Loop FAST, Loop SLOW | TO CONFIRM | None granted (see warning) | Spriters Resource network, page not recorded |

If a variant (tempo change, drumless mix) was made from someone else's module, the original
author's terms apply to it as well, and the modification should be stated here.

## Sound effects — `assets/sfx/` (5 files)

`GOAL.wav`, `GoalTaken.wav`, `GAMEOVER.wav`, `PADDLEBOUNCE.wav`, `WALLBOUNCE.wav`.

| Author | Licence / terms | Source |
| --- | --- | --- |
| Original game's rights holder (game not recorded) | None granted: extracted from a commercial game | Spriters Resource network, page not recorded |

## Sprites and background — `assets/sprites/`, `assets/backgrounds/`

`Ball.png`, `Paddle.png`, `Background.png`.

| Author | Licence / terms |
| --- | --- |
| TO CONFIRM | TO CONFIRM |

## Palettes — `assets/palettes/` (5 palettes)

The palettes left are the ones the author considers free to redistribute. The others were removed.

| Palette | Origin |
| --- | --- |
| DMG (GB Default), DMG (GB Default) (BG) | Created for Backstage |
| _Microsoft Windows 16 | Historical system palette (the 16 standard VGA/Windows colours) |
| _Commodore 64 | Historical system palette |
| _PICO-8 | Lexaloffle Games (the PICO-8 fantasy console palette) |

## Scripts, scenes, interface

`assets/scripts/*.lua`, `project/scenes`, `project/ui_layouts` and the other project data are the
project's own work and are shared under the same terms as the project itself: TO CONFIRM
(the engine in `runtime/` is zlib; the editor is GPL-3.0; a game made with them is not bound by
either — see the editor's `THIRD-PARTY-NOTICES.md`).
