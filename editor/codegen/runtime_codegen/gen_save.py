"""codegen/runtime_codegen/gen_save.py — émission des tables de sauvegarde (SRAM).

Extrait de `main_gen` (A3, découpe du fichier-dieu) : `main_gen` reste la façade
et l'orchestrateur (`generate_main`), les domaines vivent dans des sous-modules
`gen_*`. Ce module n'expose au reste du build que `save_fatal` (le contrôle
bloquant) et `save_lines` (les tables C), tous deux appelés par `generate_main`.

Trois tableaux parallèles, une entrée par variable globale marquée persistante :
son id (l'identité qui traverse les versions du jeu), son index GLOBAL_* (par où
le moteur la lit et l'écrit) et son défaut (ce qu'elle vaut si le fichier chargé
ne la contient pas).
"""
from __future__ import annotations

# `save_bits` vit dans scripting (la couche compilation) ; codegen a le droit de
# l'importer (cf. check_architecture, INTERDITS). Import de haut niveau : plus de
# cycle depuis que scripting ne remonte plus vers codegen (le paquet).
from scripting.globals import save_bits

SAVE_HEADER_BYTES = 12
# En-tête d'UN enregistrement : id (4) + taille de la charge (4). La charge
# suit, de longueur variable depuis la v0.20 — cf. `save_var_bytes`.
SAVE_RECORD_HEAD_BYTES = 8
SRAM_BYTES        = 32768


def save_vars(p) -> list[tuple[int, object]]:
    """Les globales persistantes, avec leur INDEX dans `p.globals` — celui-là
    même dont `globals.h` tire `GLOBAL_<NOM>`. Les deux listes doivent voir le
    même ordre ou l'index désigne une autre variable."""
    return [(i, g) for i, g in enumerate(getattr(p, "globals", []))
            if getattr(g, "persist", False)]


def save_id32(vid: int) -> int:
    """L'id opaque replié sur 32 bits. Il en fait 12 chiffres (jusqu'à ~2^40) et
    la SRAM se lit par mots de 32 bits : c'est un repli DÉTERMINISTE, pas un
    hachage — deux builds du même projet donnent le même. Une collision entre
    deux variables persistantes bloque le build (cf. `save_fatal`), sinon elle
    ne se verrait qu'en jeu, sous la forme d'une variable qui prend la valeur
    d'une autre."""
    return int(vid) & 0xFFFFFFFF


def save_var_bytes(g) -> int:
    """Ce qu'UNE variable persistante occupe dans un emplacement : l'en-tête de
    son enregistrement, plus ses cases empaquetées arrondies au mot de 32 bits
    (ROADMAP v0.20). Un scalaire retombe sur 8 + 4 octets ; un tableau de 400
    booléens sur 8 + 52, et non 8 + 1600."""
    n = max(1, int(getattr(g, "count", 1) or 1))
    payload = ((n * save_bits(g) + 31) // 32) * 4
    return SAVE_RECORD_HEAD_BYTES + payload


def save_slot_size(p) -> int:
    return SAVE_HEADER_BYTES + sum(save_var_bytes(g) for _i, g in save_vars(p))


def save_total_bytes(p) -> int:
    """Octets de SRAM que la sauvegarde occupe : emplacements × taille d'un
    emplacement. 0 sans variable persistante — le moteur ne touche alors pas la
    SRAM (cf. `save_fatal`, même formule)."""
    if not save_vars(p):
        return 0
    return max(1, int(getattr(p.settings, "save_slots", 1))) * save_slot_size(p)


def save_fatal(p) -> list[str]:
    """Ce qui rend la sauvegarde impossible à émettre. Bloquant, comme le budget
    de tuiles : une sauvegarde qui déborde de la SRAM n'échouerait qu'à
    l'exécution, chez le joueur."""
    out: list[str] = []
    vars_ = save_vars(p)
    if not vars_:
        return out
    seen: dict[int, str] = {}
    for _i, g in vars_:
        k = save_id32(g.id)
        if k in seen:
            out.append(
                f"[error] les variables persistantes « {seen[k]} » et "
                f"« {g.name} » retombent sur le même identifiant de sauvegarde. "
                f"Renommer n'y changera rien — recréer l'une des deux lui donne "
                f"un nouvel identifiant.")
        seen[k] = g.name
    slots = max(1, int(getattr(p.settings, "save_slots", 1)))
    total = save_total_bytes(p)
    if total > SRAM_BYTES:
        # Depuis la v0.20, une variable peut valoir des centaines de cases :
        # nommer LA plus grosse vaut mieux qu'un conseil général, parce que
        # c'est presque toujours elle qui fait déborder, et que l'auteur ne
        # peut pas deviner le coût empaqueté depuis l'écran des variables.
        biggest = max(vars_, key=lambda iv: save_var_bytes(iv[1]))[1]
        n_big = max(1, int(getattr(biggest, "count", 1) or 1))
        lever = (f" La plus grosse est « {biggest.name} » "
                 f"({n_big} cases, {save_var_bytes(biggest)} octets par "
                 f"emplacement)." if n_big > 1 else "")
        out.append(
            f"[error] {slots} emplacement(s) de sauvegarde × {len(vars_)} "
            f"variable(s) demandent {total} octets, soit plus que les "
            f"{SRAM_BYTES} de la SRAM. Réduire le nombre d'emplacements, le "
            f"nombre de cases d'un tableau, ou le nombre de variables "
            f"persistantes.{lever}")
    return out


def save_lines(p, emit=None) -> list[str]:
    """Tables de sauvegarde + chaîne de détection du support.

    Les tableaux sont émis MÊME VIDES (une entrée neutre) : le pilote de
    `gba_engine.h` les déclare `extern` sans condition, et un projet sans
    variable persistante doit tout de même se lier. C'est `g_save_count == 0`
    qui dit au moteur de ne pas toucher la SRAM."""
    vars_ = save_vars(p)
    slots = max(1, int(getattr(p.settings, "save_slots", 1)))
    L = ["", "/* Sauvegarde — variables globales marquées persistantes */"]
    if vars_:
        # La chaîne que cherchent émulateurs et linkers pour savoir de quel type
        # de sauvegarde la cartouche dispose. Émise SEULEMENT si le projet sauve
        # quelque chose : un jeu sans sauvegarde ne doit pas faire naître un
        # fichier .sav vide chez le joueur. `used` parce que rien ne la
        # référence — sans ça l'éditeur de liens la retire et la détection
        # échoue silencieusement.
        L += ['static const char __attribute__((used, aligned(4)))',
              '    g_save_type[] = "SRAM_V113";', ""]
        L.append("const unsigned int g_save_id[] = {"
                 + ", ".join(f"0x{save_id32(g.id):08X}" for _i, g in vars_) + "};")
        L.append("const unsigned short g_save_idx[] = {"
                 + ", ".join(str(i) for i, _g in vars_) + "};")
        L.append("const int g_save_def[] = {"
                 + ", ".join(str(int(g.default)) for _i, g in vars_) + "};")
        # ROADMAP v0.20 : le nombre de cases, et ce qu'une case coûte en SRAM.
        # C'est ce couple qui rend l'enregistrement auto-descriptif — donc
        # relisible par une version du jeu où le tableau a changé de taille.
        L.append("const unsigned short g_save_len[] = {"
                 + ", ".join(str(max(1, int(getattr(g, "count", 1) or 1)))
                             for _i, g in vars_) + "};")
        L.append("const unsigned char g_save_bits[] = {"
                 + ", ".join(str(save_bits(g)) for _i, g in vars_) + "};")
    else:
        L += ["const unsigned int   g_save_id[]  = {0};",
              "const unsigned short g_save_idx[] = {0};",
              "const int            g_save_def[] = {0};",
              "const unsigned short g_save_len[] = {0};",
              "const unsigned char  g_save_bits[] = {0};"]
    L.append(f"const int g_save_count = {len(vars_)};")
    L.append(f"const int g_save_slots = {slots if vars_ else 0};")
    L.append(f"const int g_save_slot_size = {save_slot_size(p) if vars_ else 0};")
    L.append("")
    if emit and vars_:
        emit("log_line",
             f"[save] {len(vars_)} variable(s) persistante(s), {slots} "
             f"emplacement(s) de {save_slot_size(p)} octets "
             f"({slots * save_slot_size(p)} sur {SRAM_BYTES} de SRAM)")
    return L
