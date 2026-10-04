"""
codegen/c_names.py — fabriquer un identifiant C à partir d'un nom d'auteur.

Un nom de scène, de sprite ou de police est écrit par un humain : il peut
contenir des espaces, des accents, de la ponctuation, commencer par un chiffre.
Le C, lui, n'accepte que lettres, chiffres et tirets bas, et pas en tête. Tout
ce qui traverse cette frontière passe donc par ici.

Deux fonctions, parce qu'il y a deux destinations et qu'elles ne se
substituent pas l'une à l'autre :

    sym("Mon Fond 2")      -> "Mon_Fond_2"     un SYMBOLE (variable, fonction)
    c_ident("Ruin At Last") -> "RUIN_AT_LAST"  un fragment de #define

**Une seule définition de chacune, ici.** `sym` a longtemps existé en trois
copies — celle-ci, un doublon octet pour octet dans le pipeline d'assets, et une
méthode statique qui rappelait la première — importée sous trois alias
différents (`_sym`, `_sym_fn`, `c_sym`). `c_ident` en avait deux. Une fonction
dupliquée ne diverge pas tout de suite : elle attend qu'on corrige un seul des
exemplaires.

`sym` s'importe sous le nom `c_sym` chez ses appelants (`from codegen.c_names
import sym as c_sym`) : « sym » est un nom de variable locale très courant dans
la génération (`sym = bg_layer_sym(...)`), et une locale masquerait la fonction
dans toute la portée où elle apparaît — au point que `sym = sym(x)` lèverait
UnboundLocalError.
"""


def sym(s: str) -> str:
    """Convertit un nom arbitraire en identifiant C valide, casse préservée."""
    r = "".join(c if (c.isalnum() or c == "_") else "_" for c in s)
    return ("_" + r) if r and r[0].isdigit() else r


def scene_actor_sym(scene_name: str, actor_name: str) -> str:
    """Symbole C d'un acteur POSÉ, qualifié par sa scène : ``<Scène>_<Acteur>``.

    Un acteur appartient à sa scène (ROADMAP « L'acteur appartient à sa scène ») :
    son NOM est local à la scène — deux scènes peuvent chacune poser un
    « Cursor » — tandis que son SYMBOLE C, lui, est qualifié, exactement comme un
    prefab poolé l'est déjà (``<Scène>_<Prefab>``). C'est ce qui empêche deux
    « Cursor » de collisionner sur un seul ``ACTOR_CURSOR`` / ``actor_Cursor.c``.

    À employer partout où l'on forme le TAG, le nom de fichier ou le préfixe de
    fonction d'un acteur de scène — jamais `sym(actor.name)` nu."""
    return f"{sym(scene_name)}_{sym(actor_name)}"


def c_ident(name: str) -> str:
    """Assainit un nom de ressource en fragment de #define, EN MAJUSCULES :
    'Ruin At Last DX' -> 'RUIN_AT_LAST_DX'.

    Sans ça, un nom de Sfx ou de Music contenant un espace génère un `#define`
    invalide — le préprocesseur C coupe le nom de macro au premier espace et
    traite le reste comme du texte de substitution."""
    r = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    return r.upper()
