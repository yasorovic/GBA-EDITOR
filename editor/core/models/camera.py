"""Camera — comment l'écran regarde le monde.

Une caméra APPARTIENT à sa scène (`Scene.cameras`, inline dans le JSON de la
scène — comme `Actor`/`BackgroundLayer`) : ce n'est plus un asset de projet
partagé entre scènes (révisé le 2026-08-24, cf. `changelog-archive/v0.6.md`).

**Une seule caméra est active à la fois.** La GBA n'a qu'un écran et le
multijoueur est hors périmètre : une scène peut posséder plusieurs caméras,
mais « plusieurs caméras » veut dire plusieurs configurations nommées dont une
est active, jamais plusieurs vues simultanées. La scène désigne sa caméra de
démarrage ; un script en change par appel explicite (`camera.switch`), il
n'existe pas de bascule automatique par zone — un script déclenché par une
collision suffit à en faire une.

Le nom d'une caméra reste unique à l'échelle du PROJET (pas seulement de sa
scène) : `camera:switch("Nom")` n'est pas qualifié par scène côté Lua, et
chaque caméra reçoit une constante C globale `CAM_<NOM>` — deux scènes ne
peuvent donc pas nommer leur caméra pareil.

Ce que la caméra ne porte PAS, et pourquoi :

- **le défilement horizontal/vertical** reste une propriété de la scène. Deux
  concepts distincts : la caméra décide *comment* la position est calculée, le
  défilement dit *si le niveau lui-même* est censé défiler dans cet axe.
  Changer de caméra ne doit pas changer ça ;
- **la rotation, le zoom, une projection** : un calque régulier ne sait ni
  tourner ni se mettre à l'échelle. Ce sont des calques affines, donc la v2.0.
  Les proposer ici promettrait un rendu que le matériel ne sait pas produire ;
- **les paramètres de secousse** : une secousse est un événement, pas un état.
  Ses valeurs vivent à l'appel (`camera:shake(amplitude, frames)`).

**Le viewport (`frame_w`/`frame_h`) est réglé le 2026-08-24** — la caméra PEUT
rendre dans une zone plus petite que 240×160. Ce n'était pas possible avant que
la caméra devienne possédée par sa scène (une seule active à la fois, cf.
ci-dessus) : découper l'écran est une window matérielle, il n'y en a que deux
(WIN0/WIN1), et l'allocation est désormais fixe — **WIN0 appartient à la
caméra active** (`camera_switch()` la pilote), **WIN1 reste à la scène**
(`Scene.windows`, panneau Windows). Pas de négociation à l'exécution : une
seule caméra active à la fois veut dire un seul propriétaire de WIN0. Le vrai
« écran partagé » (plusieurs caméras actives SIMULTANÉMENT) reste v2.0 — cf.
ARCHITECTURE.md « Windows — le pochoir » et ROADMAP.md (Caméra2D).
"""

from dataclasses import dataclass
from typing import Optional

from core.models.field_value import (
    FieldValue, Raw, make_resolver, var_names_from_project,
)
from core.models.resource import Resource

# Modes — QUI écrit la position de la caméra pendant la frame.
CAM_FIXED  = "fixed"    # personne : elle reste là où l'activation l'a posée
CAM_FOLLOW = "follow"   # le suivi déclaratif, sur `follow_target`
CAM_SCRIPT = "script"   # le script seul (le déclaratif ne calcule rien)
CAM_MODES = (CAM_FIXED, CAM_FOLLOW, CAM_SCRIPT)

# Le mode tel que le runtime le reçoit — un entier dans la table des caméras.
CAM_MODE_IDS = {CAM_FIXED: 0, CAM_FOLLOW: 1, CAM_SCRIPT: 2}


@dataclass
class Camera(Resource):
    name: str = "Camera"
    # Cadrage appliqué À L'ACTIVATION (démarrage de scène ou camera.switch).
    # Une caméra fixe ne bouge plus ensuite ; une caméra en suivi se recale
    # dans la frame même.
    x: Raw = 0
    y: Raw = 0
    # Taille du rendu à l'ÉCRAN (WIN0), en pixels — 240×160 = plein écran, la
    # window matérielle reste éteinte (comportement identique à avant que ce
    # champ existe). Plus petit que l'écran → `camera_switch()` pose WIN0 à
    # (0,0,frame_w,frame_h) et l'active. Ancré à l'origine écran : pas de
    # frame_x/frame_y, non demandé.
    frame_w: Raw = 240
    frame_h: Raw = 160
    mode: str = CAM_FIXED
    # Acteur suivi, par NOM — résolu dans les acteurs de SA scène (une caméra
    # n'en possède qu'une). Un nom qui n'y correspond à aucun acteur laisse la
    # caméra immobile, et le validateur le dit.
    follow_target: str = ""
    # Zone morte : la caméra ne bouge que lorsque la cible s'éloigne de plus de
    # ça du bord de l'écran. 0 = recentrage permanent.
    margin_x: Raw = 40
    margin_y: Raw = 20
    # Bornes du monde en pixels, appliquées à l'activation ; None = axe
    # illimité. La zone scrollable est un RECTANGLE : l'origine (bounds_x/y,
    # presque toujours 0) et la taille (bounds_w/h). Un script peut les
    # redéfinir ensuite (camera.bound), et une réactivation les repose.
    bounds_x: Optional[Raw] = None
    bounds_y: Optional[Raw] = None
    bounds_w: Optional[Raw] = None
    bounds_h: Optional[Raw] = None
    # Script Lua de la caméra, mêmes points d'entrée qu'une scène. Les réglages
    # déclaratifs ci-dessus sont TOUJOURS calculés avant qu'il ne s'exécute :
    # l'usage peut donc être purement déclaratif, purement scripté, ou les
    # deux, sans réglage de bascule dédié.
    script: str = ""
    # Note libre de l'auteur — éditeur uniquement, JAMAIS compilée. Même champ
    # que l'Actor et la Scène, et ce que le survol de l'icône caméra affiche.
    notes: str = ""

    def px(self, name: str, project=None) -> int:
        """Valeur EN PIXELS du champ `name` (`x`, `frame_w`, `bounds_x`…).

        Ces champs sont stockés sous la forme sérialisable d'un `FieldValue`
        (px = `int` nu, tiles = `{"unit": "t", "n": N}`, constante du projet =
        `{"var": <id>, "src": "const"}`) : tout lecteur qui veut des pixels
        passe par ici. Jamais de variable globale — la table des caméras est
        figée à la compilation (`const Camera g_cam_table[]`), l'éditeur ne
        propose donc que px / tile / constante. La constante se résout ICI en
        sa valeur (`project` requis pour la lire) : `static const int CONST_X`
        n'est pas une expression constante C, elle ne peut pas entrer dans
        l'initialiseur de la table. `None` (bornes illimitées) → 0."""
        raw = getattr(self, name) or 0
        return FieldValue.parse(raw, var_names_from_project(project)).px(
            make_resolver(project))

    def mode_id(self) -> int:
        return CAM_MODE_IDS.get(self.mode, 0)
