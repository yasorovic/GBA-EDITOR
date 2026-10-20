# Allocateurs — pistes d'amélioration

Recensement des améliorations possibles des allocateurs (`vram_alloc.py`,
`palette_alloc.py`, `oam_alloc.py`, `window_alloc.py`). Rien ici n'est engagé :
chaque entrée dit d'où elle vient, ce qu'elle apporte et ce qu'elle coûte.

## VRAM — tuile vide dédiée au calque d'UI (option B)

**Origine.** Les cellules vides de la map d'un calque d'UI valent 0 (`bg_maps_clear`),
donc pointent sur la tuile 0 du charblock du texte. L'allocateur suppose cette tuile
vide (`text_clear`). Quand le texte partage son charblock avec un fond ancré à la base,
la tuile 0 est celle du fond : elle s'affiche, opaque, devant toute la scène
(démo PongAdvanced, `SCR_Arena` : UI sur BG0, Space sur BG2, texte placé en CBB2).

**Correctif retenu (A).** À l'étape 4 de `vram_alloc.py`, ne pas poser le texte dans un
charblock dont la tuile 0 appartient à un fond. Petit, local, et une solution existe
toujours (le slot d'UI ne porte jamais d'image).

**Piste (B).** Réserver une tuile vide dédiée dans le bloc du texte et remplir les maps
d'UI avec son index au lieu de 0.

- Apport : supprime l'invariant « tuile 0 vide » ; le texte peut partager n'importe
  quel charblock, y compris au-dessus d'un fond qui déborde.
- Coût : touche `gba_engine.h`, `bg_maps_clear` et tout ce qui efface ou remplace une
  map d'UI au runtime (échange de SBB, `text_clear`) ; une tuile réservée par scène ;
  le repli `text_base = 1` disparaît au profit de la tuile réservée.
- À envisager si d'autres cas de partage de charblock posent problème après le
  correctif A.

## OAM — liste libre d'entrées au spawn

**Origine.** Le pool ne dépend plus de l'OAM (ROADMAP, « Le pool ne dépend plus de l'OAM »,
2026-10-20). Les entrées se distribuent à la construction du layout : les `granted` premières
instances d'un pool ont leurs entrées OAM, les suivantes vivent sur l'entrée poubelle et ne
s'affichent jamais. Le spawn prend le premier slot libre, donc les instances affichées sont
celles de tête.

**Limite.** Une instance née dans un slot au-delà de `granted` reste invisible toute sa vie,
même si une entrée se libère ailleurs (une instance de tête meurt).

**Piste.** Lier l'entrée OAM à l'instance au spawn, dans une réserve commune : une instance en
prend une en naissant, la rend en mourant (`active = false`, destruction de la racine). Le slot
d'acteur n'a plus d'importance pour l'affichage.

- Apport : seules les instances nées quand l'OAM est déjà pleine restent invisibles, au lieu de
  celles des derniers slots. Utile surtout si un pool déborde souvent de l'OAM.
- Coût : le writer OAM, aujourd'hui déroulé slot par slot avec l'indice d'entrée écrit en dur,
  devrait lire `oam_entry` à chaque frame ; la prise et la restitution des entrées s'ajoutent
  au spawn et à la destruction ; la matrice affine suivrait la même liaison. Des cycles par
  frame, **à mesurer sur ROM** avant de s'y engager.
- À envisager si un vrai jeu se plaint d'instances invisibles alors que l'OAM n'est pas saturée
  en permanence.
