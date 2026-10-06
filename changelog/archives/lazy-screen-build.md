# L'écran construit à sa première visite — **LIVRÉ**

> **Ouvert et livré le 2026-09-13.** Chantier technique : suite directe du **chargement paresseux**
> (v0.24). Celui-ci avait différé la *donnée* d'un écran ; ce chantier étend le même principe au
> *widget* et à ses *imports*. Rien ne change pour qui joue au jeu produit — seulement le temps
> d'ouverture de l'éditeur. Ni README ni CHANGELOG, pas de numéro `vX.Y`.
>
> **Résultat mesuré.** `import window` : **2084 → 1699 ms**. Surtout, les sept écrans natifs
> différés (156–927 ms chacun) quittent le chemin de démarrage — `QtMultimedia` + `numpy` (moteur
> audio) et la grammaire `luaparser` ne sont plus chargés à l'ouverture. Suite verte
> (705 passed, 51 skipped).

## D'où vient la question (2026-09-13)

L'éditeur était devenu plus long à s'ouvrir. La mesure (`python -X importtime`, venv de CI) a montré
que le poids n'était pas dans l'I/O du projet — déjà paresseuse — mais dans l'**import du module
`window`** : ~2,1 s, dont l'essentiel dans des dépendances tirées au niveau `import` pour des écrans
jamais affichés au démarrage.

| Branche importée au démarrage | Coût | Tirée par |
| --- | --- | --- |
| `ui.sound_mixer.sound_panel` | **~1,1 s** | `window.py` (niveau module) |
| └ `PyQt6.QtMultimedia` (+ `QtNetwork`) | ~0,28 s | lecture audio, `box_playback` |
| └ `numpy` | ~0,27 s | `engine_emulation` (rendu s3m/it/mod) |
| `scripting.parser` (grammaire luaparser) | ~0,2–0,4 s | `script_editor`, `validator` |
| `PyQt6.QtWidgets` (base) | ~0,13 s | incompressible |

Seul le Scene Manager est visible à l'ouverture. Les sept autres écrans natifs étaient pourtant
**construits d'un coup** par `_build_screens()`, ce qui forçait l'import de tous leurs modules —
d'où la facture, payée même si l'onglet Sounds ou Scripts n'était jamais ouvert.

## Décisions verrouillées

- **L'écran se construit à sa PREMIÈRE VISITE, pas au démarrage.** Le catalogue
  (`_screen_catalogue`) reste la source unique ; ses fabriques existaient déjà. `_build_screens()`
  ne construit plus que le Scene Manager (index 0) et pose un **placeholder** (`_ScreenPlaceholder`)
  dans le `QStackedWidget` pour chaque autre écran natif. `_ensure_screen(index)` remplace le
  placeholder par le vrai widget au premier `_show_screen` / `_load_screen_for_project` /
  `open_script`. Les imports lourds (`sound_panel`, `script_editor`, `background_editor`…) descendent
  dans leurs fabriques `_make_*`, hors du chemin de démarrage.
- **Les écrans de PLUGIN restent construits au démarrage.** Le contrôle du contrat `ProjectScreen`
  ([ui/screens.py](../../editor/ui/screens.py)) est le seul qui doit se constater au démarrage — un
  écran tiers qui ne le remplit pas doit être signalé tout de suite. Les écrans natifs, eux,
  satisfont le contrat par construction : les différer ne perd aucun message d'erreur.
- **Un accès transversal ne construit rien.** Le build, les réglages de projet, l'undo et le watcher
  touchent parfois un écran non visité (la seconde console de build du Script Editor, le
  rafraîchissement du Text Editor…). La règle : `getattr(self, "_x", None)` — un écran non construit
  n'existe pas encore comme attribut, l'accès transversal le SAUTE, et l'écran lit l'état frais à sa
  construction (`load_project`). Helpers : `_call_if_built` (abonnements du dispatcher),
  `_script_build_panel` (la seconde console).
- **La seconde console de build devient optionnelle.** `_run_build` alimentait en dur
  `self.build_panel` ET `self._script_editor.build_panel`. Elle n'écrit désormais sur celle du
  Script Editor que si cet écran a été ouvert. Ouvrir Scripts après un build montre une console
  vierge — cohérent avec un écran neuf.

## Ce que ça a touché

| Fichier | Nature |
| --- | --- |
| [window.py](../../editor/window.py) | `_ScreenPlaceholder` ; `_build_screens` ne bâtit que Scene Manager + plugins ; `_ensure_screen` ; imports des 7 écrans descendus dans `_make_*` ; `_show_screen`/`_load_screen_for_project`/`open_script` construisent avant d'adresser ; accès transversaux gardés (`_call_if_built`, `_script_build_panel`, `getattr`) ; console de build du Script Editor optionnelle |
| [ui/screens.py](../../editor/ui/screens.py) | docstring de `EditorScreen.build` : « à la première visite » |
| [ARCHITECTURE.md](../../ARCHITECTURE.md) | section catalogue d'écrans : construction paresseuse, plugins eager |

Pas de nouveau test : le comportement se constate à l'usage (temps d'ouverture) et le smoke test
offscreen — au démarrage un seul écran réel + sept placeholders, puis visite de chacun sans erreur —
a servi de garde-fou pendant le chantier. La suite existante reste verte.

## Pièges

- **`_restore_layout` a besoin du Scene Manager construit** — il restaure l'état des trois splitters
  (`_h_split`, `_center_v_split`, `_left_v_split`), créés dans sa fabrique. Le Scene Manager reste
  donc construit *eagerly* : ce chantier ne diffère que les sept autres.
- **Le menu vit dans la fabrique du Scene Manager** (`_setup_menu`, appelé depuis
  `_build_scene_manager_screen`). Construire le Scene Manager au démarrage le préserve tel quel.
- **Les index du `QStackedWidget` doivent rester alignés sur le catalogue.** Le placeholder tient la
  place ; `_ensure_screen` insère le vrai widget à son index puis retire le placeholder, sans
  décaler les suivants.
