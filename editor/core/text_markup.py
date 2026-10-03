"""
core/text_markup.py — le langage de balisage des entrées de la table de textes.

Syntaxe à la BBCode (décision ROADMAP v0.3.2, sur le modèle du `RichTextLabel`
de Godot) : `[speed=4]`, `[pause=3]`, `[wave]…[/wave]`. Elle est **fermée** —
sans borne de fin, `/S12` serait indécidable —, les crochets n'apparaissent pas
en prose là où `/` le fait (« et/ou », « 12/05 »), et elle a des **balises de
portée**, ce dont un effet par caractère a besoin puisqu'il s'applique à un
intervalle et pas à un point.

**Tout se résout au build, le moteur n'embarque aucun parseur.** Ce module est
donc le point unique : l'aperçu de l'éditeur et l'encodeur lisent la même
analyse, sinon l'éditeur promettrait un rendu que la ROM ne tiendrait pas.

Ce qui sort d'une analyse :
  • `display` — le texte AFFICHÉ, balises retirées. C'est exactement ce que
    l'encodeur sort en codepoints, donc ce dont `text.length` donne la longueur.
    Un marqueur de valeur y tient UNE place (`SENTINEL`) : `resolve()` la
    remplace par des chiffres pour l'aperçu, le runtime pour de vrai.
  • `markers` — les effets, repérés en coordonnées d'AFFICHAGE (pas de source) :
    c'est ce que la piste d'événements émettra, et le runtime ne connaît que ces
    positions-là.
  • `issues` — ce qui n'a pas été compris, repéré en coordonnées de SOURCE pour
    être souligné dans l'atelier.

Rien n'est deviné : une balise inconnue ou mal formée reste du TEXTE (elle
s'affichera telle quelle) et produit un avertissement. Mais l'avertissement est
réservé à ce qui RESSEMBLE à une tentative de balise — nom voisin d'une balise
connue, casse fautive, valeur portée, paire ouverte/fermée. « Touche [A] »
s'écrit donc sans rien échapper ET sans être signalée : même compromis que le
checker de scripts, qui n'avertit sur une chaîne que si elle a la forme d'une
clé sans en matcher aucune.

Seul `[` s'échappe, en le doublant (`[[`), parce que seul `[` ouvre quelque
chose ; un `]` isolé n'est jamais ambigu et passe toujours tel quel. Idem pour
le dollar : `$$` écrit un dollar littéral.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Catalogue des balises ─────────────────────────────────────────
# Point unique, comme `scripting.api.RUNTIME_API` : l'analyse, la validation et
# (à venir) la coloration de l'atelier le lisent, aucune n'en tient une copie.

VALUE_NONE = ""     # la balise ne prend pas de valeur
VALUE_INT  = "int"
VALUE_NAME = "name"


@dataclass(frozen=True)
class TagSpec:
    name:   str
    scoped: bool         # True = [x]…[/x], False = ponctuelle
    value:  str          # VALUE_NONE | VALUE_INT | VALUE_NAME
    doc:    str
    # Bornes d'un entier, quand le matériel en impose. None = pas de plafond.
    vmin:   int = 0
    vmax:   Optional[int] = None


TAGS: dict[str, TagSpec] = {t.name: t for t in (
    # ── Tempo — ponctuelles, elles marquent un INSTANT de la lecture ──
    TagSpec("speed", False, VALUE_INT,
            "Sets the reading speed from this point, in frames per character. "
            "0 shows the text instantly."),
    TagSpec("pause", False, VALUE_INT,
            "Waits n frames before going on, like a comma in the rhythm."),
    # ── Insertion ─────────────────────────────────────────────────
    TagSpec("icon", False, VALUE_NAME,
            "Inserts the named glyph of the font. "
            "It is the same as typing its sequence of characters, but the "
            "editor can check that the font has it."),
    # ── Effets — de PORTÉE, ils s'appliquent à un intervalle ───────
    TagSpec("wave",  True, VALUE_NONE, "Makes each character wave."),
    TagSpec("shake", True, VALUE_NONE, "Makes each character shake."),
    # 1..15 n'est pas un choix : une police est en 4bpp, l'index 0 y est la
    # transparence et il ne reste que quinze encres. Hors de cette plage, le
    # remappage du runtime déborderait son mot de 32 bits.
    TagSpec("color", True, VALUE_INT,
            "Uses ink colour n of the font's sub-palette (1..15). "
            "Needs a sheet that already carries several shades.",
            vmin=1, vmax=15),
    TagSpec("font", True, VALUE_NAME,
            "Uses the named font for this piece of text."),
)}

# Marqueur de valeur — pas une balise : il désigne un global ou une const, dont
# la valeur est substituée à la lecture. `$$` écrit un dollar littéral.
KIND_VALUE = "value"

# Un marqueur de valeur occupe UNE place dans le texte affiché, tenue par un
# non-caractère Unicode : U+FFFF est réservé à perpétuité par le standard, donc
# aucun texte ni aucun glyphe ne peut légitimement le porter. C'est ce que
# l'encodeur émet, et ce que `resolve` remplace par des chiffres.
SENTINEL = "￿"
VALUE_CP = 0xFFFF

# Balises de portée qui coûtent des glyphes ANIMÉS, donc de l'OAM : c'est ce que
# `Project.region_animated_glyphs` compte pour réserver la place.
ANIMATED_TAGS = frozenset({"wave", "shake"})


@dataclass(frozen=True)
class Marker:
    """Un effet posé sur le texte affiché.

    `at`/`end` sont des index dans `display` (`end` exclu, `end == at` pour une
    balise ponctuelle) ; `src` est le fragment de source correspondant, pour
    pouvoir le désigner dans l'atelier."""
    kind:  str
    at:    int
    end:   int
    value: Optional[object] = None
    src:   tuple[int, int] = (0, 0)
    limit: int = 0                 # `$nom!3` → au plus 3 caractères, 0 = libre

    @property
    def scoped(self) -> bool:
        return self.end > self.at


# Ce que la coloration de l'atelier a besoin de savoir : où sont les tokens
# RECONNUS dans la source. Le parseur les connaît déjà — les redire en regex
# côté vue aurait donné deux grammaires à tenir d'accord, et la seconde aurait
# menti au premier ajout de balise.
TOK_TAG    = "tag"      # [wave], [speed=4]
TOK_CLOSE  = "close"    # [/wave]
TOK_VALUE  = "value"    # $nom ou $nom!3
TOK_ESCAPE = "escape"   # [[ et $$


@dataclass(frozen=True)
class Token:
    kind: str
    at:   int
    end:  int


@dataclass(frozen=True)
class Issue:
    """Ce que l'analyse n'a pas compris, situé dans la SOURCE."""
    at:      int
    end:     int
    message: str


@dataclass
class ParsedText:
    display: str = ""
    markers: list[Marker] = field(default_factory=list)
    issues:  list[Issue] = field(default_factory=list)
    tokens:  list[Token] = field(default_factory=list)   # spans SOURCE, pour la vue

    @property
    def length(self) -> int:
        """Longueur AFFICHÉE — ce que rend `text.length`."""
        return len(self.display)

    def of_kind(self, *kinds: str) -> list[Marker]:
        return [m for m in self.markers if m.kind in kinds]

    @property
    def animated_glyphs(self) -> int:
        """Caractères couverts par un effet animé — à confronter au budget
        déclaré par la zone qui affichera ce texte."""
        covered: set[int] = set()
        for m in self.markers:
            if m.kind in ANIMATED_TAGS:
                covered.update(range(m.at, m.end))
        return len(covered)


# ── Projection d'édition ─────────────────────────────────────────

PROJ_CONTENT = "content"
PROJ_MARKUP = "markup"
PROJ_VALUE = "value"


@dataclass(frozen=True)
class ProjectionSpan:
    """Un fragment de la surface Texte unifiée.

    Les bornes restent toujours dans la chaîne source : une balise masquée ne
    prend aucune place à l'écran, mais le curseur peut tout de même se poser de
    part et d'autre sans perdre sa vraie position. ``atomic`` protège les
    valeurs calculées : les chiffres affichés pour ``$score`` ne sont pas du
    texte que l'on peut couper ou modifier individuellement.
    """
    source_start: int
    source_end: int
    text: str
    kind: str = PROJ_CONTENT
    font_name: str = ""
    atomic: bool = False


@dataclass(frozen=True)
class MarkupProjection:
    """Correspondance pure entre une source BBCode et sa surface visible."""
    source: str
    spans: tuple[ProjectionSpan, ...]

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    def source_to_visible(self, position: int, *, right: bool = False) -> int:
        """Positionne une borne source dans le texte projeté.

        ``right`` choisit le côté droit d'un fragment non visible (une balise
        masquée). C'est la règle employée respectivement par Début/Fin de
        sélection et empêche un caret de rebondir sur une balise invisible.
        """
        pos = max(0, min(position, len(self.source)))
        visible = 0
        for span in self.spans:
            if pos < span.source_start:
                return visible
            if span.source_start <= pos <= span.source_end:
                if not span.text:
                    return visible
                if span.atomic:
                    return visible + (len(span.text) if right and pos == span.source_end else 0)
                width = max(1, span.source_end - span.source_start)
                offset = min(len(span.text), max(0, pos - span.source_start))
                # Un échappement a deux caractères source pour un seul rendu :
                # sa borne intérieure reste du côté demandé, jamais au milieu
                # d'un pseudo-caractère.
                if len(span.text) == 1 and width > 1:
                    offset = 1 if right and pos > span.source_start else 0
                return visible + offset
            visible += len(span.text)
        return visible

    def visible_to_source(self, position: int, *, right: bool = False) -> int:
        """Inverse de :meth:`source_to_visible`, avec la même règle de biais."""
        pos = max(0, min(position, len(self.text)))
        visible = 0
        for span in self.spans:
            end = visible + len(span.text)
            if pos <= end:
                if not span.text:
                    return span.source_end if right else span.source_start
                if span.atomic:
                    return span.source_end if right and pos == end else span.source_start
                return min(span.source_end, span.source_start + (pos - visible))
            visible = end
        return len(self.source)


def project(source: str, values: Optional[dict] = None, *, show_markup: bool = False) -> MarkupProjection:
    """Construit la surface de l'atelier sans changer la grammaire du build.

    Les balises reconnues deviennent des fragments ``markup`` seulement quand
    elles sont demandées. Le reste garde exactement le texte que le joueur lit,
    y compris les échappements, les icônes et les valeurs résolues.
    """
    source = source or ""
    parsed = parse(source)
    markers_at_src = {m.src: m for m in parsed.markers}
    spans: list[ProjectionSpan] = []
    pos = display_pos = 0

    def font_at(index: int) -> str:
        active = [m for m in parsed.of_kind("font") if m.at <= index < m.end]
        return str(active[-1].value) if active else ""

    def append(a: int, b: int, text: str, kind=PROJ_CONTENT, *, atomic=False):
        if text or kind == PROJ_MARKUP:
            spans.append(ProjectionSpan(a, b, text, kind, font_at(display_pos), atomic))

    for token in parsed.tokens:
        if pos < token.at:
            raw = source[pos:token.at]
            append(pos, token.at, raw)
            display_pos += len(raw)
        raw = source[token.at:token.end]
        marker = markers_at_src.get((token.at, token.end))
        if token.kind == TOK_ESCAPE:
            append(token.at, token.end, raw[0])
            display_pos += 1
        elif token.kind == TOK_VALUE and marker is not None:
            value = str((values or {}).get(marker.value, f"${marker.value}"))
            value = value[:marker.limit] if marker.limit else value
            append(token.at, token.end, value, PROJ_VALUE, atomic=True)
            display_pos += 1
        else:
            if show_markup:
                append(token.at, token.end, raw, PROJ_MARKUP, atomic=True)
            if marker is not None and marker.kind == "icon":
                icon = str(marker.value)
                append(token.at, token.end, icon)
                display_pos += len(icon)
        pos = token.end
    if pos < len(source):
        append(pos, len(source), source[pos:])
    return MarkupProjection(source, tuple(spans))


def removable_markup_edits(source: str, start: int, end: int) -> list[tuple[int, int, str]]:
    """Suppressions sûres pour les balises qui entourent exactement ``[start,end]``.

    Le résultat est déjà ordonné de la fin vers le début et peut donc être
    passé directement à une surface d'édition dans une unique annulation.
    """
    parsed = parse(source)
    opened: list[tuple[str, int, int]] = []
    pairs: list[tuple[int, int, int, int]] = []
    for token in parsed.tokens:
        raw = source[token.at:token.end]
        if token.kind == TOK_TAG:
            match = re.match(r"\[([A-Za-z_][A-Za-z0-9_]*)", raw)
            name = match.group(1) if match else ""
            if name in TAGS and TAGS[name].scoped:
                opened.append((name, token.at, token.end))
        elif token.kind == TOK_CLOSE:
            match = re.match(r"\[/([A-Za-z_][A-Za-z0-9_]*)\]", raw)
            name = match.group(1) if match else ""
            for i in range(len(opened) - 1, -1, -1):
                if opened[i][0] == name:
                    _name, a, b = opened.pop(i)
                    pairs.append((a, b, token.at, token.end))
                    break
    def selected(a: int, b: int, c: int, d: int) -> bool:
        # Le contenu seul est la sélection naturelle en vue fidèle. En vue
        # balisage, le glisser peut aussi partir sur ``[font=…]`` et englober
        # les deux bornes : les deux gestes doivent retirer la même portée.
        return (b == start and c == end) or (start <= a and d <= end) or (
            # Sur la surface pixel, le clic peut tomber au milieu d'une
            # ligature ou sur le premier/dernier pixel d'une balise. Retirer
            # l'enveloppe doit rester un geste souple dès que la sélection
            # recouvre du contenu de cette portée.
            start < c and end > b
        )

    chosen = [(a, b, c, d) for a, b, c, d in pairs if selected(a, b, c, d)]
    edits = [(a, b, "") for a, b, _c, _d in chosen]
    edits += [(c, d, "") for _a, _b, c, d in chosen]
    return sorted(edits, reverse=True)


# ── Analyse ───────────────────────────────────────────────────────

# Un seul balayage : échappements, balises et marqueurs de valeur. Le reste du
# texte passe tel quel — y compris un crochet isolé, qui n'est une erreur que
# s'il ouvre quelque chose qui ressemble à une balise.
_TOKEN = re.compile(
    r"""\[\[                                  # [[ → [ littéral
      | \$\$                                  # $$ → $ littéral
      | \[ (?P<close>/)? (?P<name>[A-Za-z_][A-Za-z0-9_]*)
           (?: = (?P<value>[^\]]*) )? \]      # balise ouvrante ou fermante
      | \$ (?P<var>[A-Za-z_][A-Za-z0-9_]*)(?:!(?P<limit>[1-9]))? # valeur, limite optionnelle
    """,
    re.VERBOSE,
)


def parse(source: str) -> ParsedText:
    """Analyse une entrée de la table. Ne lève jamais : ce qui n'est pas compris
    devient du texte et un `Issue`."""
    out = ParsedText()
    if not source:
        return out
    disp: list[str] = []
    open_scopes: list[tuple] = []   # (nom, valeur, at_display, src_debut, src_fin)
    pos = 0

    def literal(a: int, b: int):
        disp.append(source[a:b])

    for m in _TOKEN.finditer(source):
        literal(pos, m.start())
        pos = m.end()
        tok = m.group(0)

        if tok == "[[":
            disp.append("[")
            out.tokens.append(Token(TOK_ESCAPE, m.start(), m.end()))
            continue
        if tok == "$$":
            disp.append("$")
            out.tokens.append(Token(TOK_ESCAPE, m.start(), m.end()))
            continue

        if m.group("var"):
            at = len("".join(disp))
            # UNE place réservée, pas le nom : c'est ce que l'encodeur émet, et
            # ce qui garde `at`/`end` des marqueurs suivants justes quelle que
            # soit la valeur substituée derrière.
            disp.append(SENTINEL)
            out.markers.append(Marker(KIND_VALUE, at, at + 1,
                                      m.group("var"), (m.start(), m.end()),
                                      int(m.group("limit") or 0)))
            out.tokens.append(Token(TOK_VALUE, m.start(), m.end()))
            continue

        name = m.group("name")
        raw = m.group("value")
        spec = TAGS.get(name)
        span = (m.start(), m.end())

        if spec is None:
            msg = _unknown_issue(name, raw, bool(m.group("close")), source)
            if msg:
                out.issues.append(Issue(*span, msg))
            disp.append(tok)
            continue

        if m.group("close"):
            before = len(out.issues)
            _close_scope(out, disp, open_scopes, spec, raw, tok, span)
            if len(out.issues) == before:
                out.tokens.append(Token(TOK_CLOSE, *span))
            continue

        value, err = _read_value(spec, raw)
        if err:
            out.issues.append(Issue(*span, err))
            disp.append(tok)
            continue
        # Reconnue et bien formée : elle mérite d'être colorée. Une balise
        # inconnue ou fautive n'en est pas une — elle s'affichera, donc elle
        # se lit comme du texte.
        out.tokens.append(Token(TOK_TAG, *span))

        at = len("".join(disp))
        if spec.scoped:
            open_scopes.append((name, value, at, span[0], span[1]))
        elif name == "icon":
            # Un icône EST sa suite de caractères : l'insérer dans le texte
            # affiché laisse la correspondance au plus long (les ligatures)
            # faire son travail, sans second chemin de rendu.
            disp.append(str(value))
            out.markers.append(Marker(name, at, len("".join(disp)), value, span))
        else:
            out.markers.append(Marker(name, at, at, value, span))

    literal(pos, len(source))
    out.display = "".join(disp)

    # Portées jamais refermées : l'intention est claire (la balise est valide,
    # seule sa fin manque), on l'étend jusqu'au bout plutôt que de la dessiner —
    # mais on le dit, sinon un `[/wave]` oublié passerait en ROM sans un mot.
    for name, value, at, s0, s1 in open_scopes:
        out.issues.append(Issue(s0, s1, f"\"[{name}]\" is never closed — the effect runs to"
                                        " the end of the text."))
        out.markers.append(Marker(name, at, len(out.display), value, (s0, s1)))

    out.markers.sort(key=lambda mk: (mk.at, mk.end))
    out.issues.sort(key=lambda i: i.at)
    out.tokens.sort(key=lambda t: t.at)
    return out


def _unknown_issue(name: str, raw: Optional[str], closing: bool,
                   source: str) -> str:
    """Message pour une balise inconnue, ou "" s'il faut se taire.

    Un crochet en prose (« touche [A] », « [Start] ») n'est pas une faute : le
    signaler à chaque fois rendrait l'avertissement inutile. On ne parle donc
    que si la forme trahit une TENTATIVE de balise."""
    lower = name.lower()
    if lower in TAGS and lower != name:
        return f"\"[{name}]\": tags are written in lowercase — \"[{lower}]\"."
    near = difflib.get_close_matches(lower, list(TAGS), n=1, cutoff=0.7)
    if near:
        return f"Unknown tag \"{name}\" — did you mean \"{near[0]}\"?"
    if closing or raw is not None or f"[/{name}]" in source:
        return f"Unknown tag \"{name}\" — it will be displayed as is."
    return ""


def _read_value(spec: TagSpec, raw: Optional[str]) -> tuple[object, str]:
    """(valeur, message d'erreur) — la valeur n'a de sens que si le message est
    vide."""
    if spec.value == VALUE_NONE:
        if raw is not None:
            return None, f"\"[{spec.name}]\" takes no value."
        return None, ""
    if raw is None or not raw.strip():
        kind = "an integer" if spec.value == VALUE_INT else "a name"
        return None, f"\"[{spec.name}]\" expects {kind}: [{spec.name}=…]."
    raw = raw.strip()
    if spec.value == VALUE_INT:
        if not raw.isdigit():
            return None, (f"\"[{spec.name}={raw}]\" expects a positive integer.")
        n = int(raw)
        if n < spec.vmin or (spec.vmax is not None and n > spec.vmax):
            return None, (f"\"[{spec.name}={n}]\" is out of range — expected between {spec.vmin} and "
                          f"{spec.vmax}.")
        return n, ""
    return raw, ""


def _close_scope(out: ParsedText, disp: list[str], open_scopes: list,
                 spec: TagSpec, raw: Optional[str], tok: str,
                 span: tuple[int, int]):
    """Referme une portée ouverte, ou signale ce qui l'en empêche."""
    if raw is not None:
        out.issues.append(Issue(*span, "A closing tag carries no value: write "
                                       f"\"[/{spec.name}]\"."))
        disp.append(tok)
        return
    if not spec.scoped:
        out.issues.append(Issue(*span, f"\"[{spec.name}]\" is a one-shot tag, it is not closed."))
        disp.append(tok)
        return
    for i in range(len(open_scopes) - 1, -1, -1):
        if open_scopes[i][0] == spec.name:
            name, value, at, s0, s1 = open_scopes.pop(i)
            if i != len(open_scopes):
                # Mal imbriquée : on ferme quand même celle qui est nommée. La
                # refuser obligerait à choisir laquelle sacrifier.
                out.issues.append(Issue(*span, f"\"[/{name}]\" closes a scope opened before"
                                               " others that are still open — crossed"
                                               " nesting."))
            out.markers.append(Marker(name, at, len("".join(disp)), value, (s0, s1)))
            return
    out.issues.append(Issue(*span, f"\"[/{spec.name}]\" closes no open scope."))
    disp.append(tok)


def resolve(parsed: ParsedText, values: Optional[dict] = None) -> str:
    """Le texte tel qu'un joueur le lit : places réservées remplacées par les
    valeurs de `values`.

    Un nom absent de `values` rend `$nom` — l'anomalie reste donc VISIBLE dans
    l'aperçu au lieu de se traduire par un trou muet. Côté ROM c'est l'encodeur
    qui substitue les constantes et pose un pointeur pour les globals ; ici on
    montre les valeurs INITIALES, seules connues à l'édition."""
    if SENTINEL not in parsed.display:
        return parsed.display
    values = values or {}
    out, prev = [], 0
    for m in parsed.markers:
        if m.kind != KIND_VALUE:
            continue
        out.append(parsed.display[prev:m.at])
        value = str(values[m.value]) if m.value in values else f"${m.value}"
        out.append(value[:m.limit] if m.limit else value)
        prev = m.end
    out.append(parsed.display[prev:])
    return "".join(out)


def rename_value(source: str, old: str, new: str) -> str:
    """Réécrit les `$old` en `$new` dans une source balisée.

    Passe par l'ANALYSE et non par un remplacement de texte : seuls les
    marqueurs de valeur bougent. Un `$$old` échappé, un `[icon=old]` ou le mot
    « old » en prose restent intacts — c'est la même exigence que le repérage
    structurel de `scripting/refactor.py` pour les scripts."""
    parsed = parse(source)
    out, prev = [], 0
    for m in parsed.markers:
        if m.kind != KIND_VALUE or m.value != old:
            continue
        out.append(source[prev:m.src[0]])
        out.append("$" + new)
        prev = m.src[1]
    if not out:
        return source
    out.append(source[prev:])
    return "".join(out)


def display_text(source: str, values: Optional[dict] = None) -> str:
    """Analyse et résout d'un coup — raccourci pour tout ce qui n'a besoin que
    du texte lisible (ligne de table, extrait, mesure, charset)."""
    return resolve(parse(source), values)
