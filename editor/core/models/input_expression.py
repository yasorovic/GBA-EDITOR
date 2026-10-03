"""Parseur pur du mini-langage d'expressions d'input (ROADMAP : « Les inputs
personnalisés »). Source unique de la grammaire : l'écran des actions (barre +
aperçu), le checker et le codegen appellent CE module — il n'existe pas de
seconde grammaire.

    expression := pas ( "-" pas )*          -- "-" : puis (séquence)
    pas        := atome ( "+" atome )*      -- "+" : en même temps (accord)
    atome      := bouton | direction | mouvement | alternance
    alternance := "(" atome ( "|" atome )* ")"   -- jusqu'à 4 branches, pas d'imbrication,
                                                     branches limitées à bouton/direction

Un mouvement (built-in ou déclaré par le projet, cf. `compile_movement`) doit être
le premier atome de l'EXPRESSION ENTIÈRE ; un `+ atome` qui le suit rejoint son
DERNIER pas au lieu d'en ouvrir un nouveau. Un mouvement ne référence jamais un
autre mouvement (pas de cycle possible par construction) : `compile_movement`
compile ses pas sans aucune table de mouvements.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.models.settings import BUTTON_NAMES

MAX_ALTERNATIVES = 4
MAX_ALTERNATION_BRANCHES = 4

_BUTTONS = frozenset(BUTTON_NAMES)
_WORD_RE = re.compile(r"[a-z_][a-z_0-9]*")
_TOKEN_RE = re.compile(r"[a-z_][a-z_0-9]*|[-+()|]")


class InputExpressionError(Exception):
    """Une expression invalide, avec sa colonne fautive (1-based, dans le texte saisi)."""

    def __init__(self, message: str, column: int):
        super().__init__(message)
        self.message = message
        self.column = column


@dataclass(frozen=True)
class InputStep:
    buttons: frozenset

    def __repr__(self) -> str:
        return "+".join(sorted(self.buttons))


@dataclass(frozen=True)
class InputExpression:
    steps: tuple  # tuple[InputStep, ...]

    @property
    def is_sequence(self) -> bool:
        return len(self.steps) > 1


def _mirror(step: frozenset) -> frozenset:
    swap = {"left": "right", "right": "left"}
    return frozenset(swap.get(b, b) for b in step)


def _mirror_steps(steps: tuple) -> tuple:
    return tuple(_mirror(s) for s in steps)


_QUARTER_RIGHT = (frozenset({"down"}), frozenset({"down", "right"}), frozenset({"right"}))
_HALF_RIGHT = (
    frozenset({"left"}),
    frozenset({"down", "left"}),
    frozenset({"down"}),
    frozenset({"down", "right"}),
    frozenset({"right"}),
)
_DRAGON_RIGHT = (frozenset({"right"}), frozenset({"down"}), frozenset({"down", "right"}))

BUILTIN_MOVEMENTS: dict = {
    "quarter_circle_right": _QUARTER_RIGHT,
    "quarter_circle_left": _mirror_steps(_QUARTER_RIGHT),
    "half_circle_right": _HALF_RIGHT,
    "half_circle_left": _mirror_steps(_HALF_RIGHT),
    "dragon_punch_right": _DRAGON_RIGHT,
    "dragon_punch_left": _mirror_steps(_DRAGON_RIGHT),
}


def _tokenize(text: str) -> list:
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        m = _TOKEN_RE.match(text, i)
        if not m:
            raise InputExpressionError(f"unexpected character \"{c}\"", i + 1)
        tokens.append((m.group(0), i + 1))
        i = m.end()
    return tokens


class _Parser:
    """Un passage = une expression. `movements` mappe un nom de mouvement à ses
    pas déjà compilés ; vide pour `compile_movement` (aucune référence permise)."""

    def __init__(self, tokens: list, movements: dict):
        self._tokens = tokens
        self._pos = 0
        self._movements = movements

    def _peek(self):
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self):
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _error_here(self, message: str) -> InputExpressionError:
        tok = self._peek()
        col = tok[1] if tok else (self._tokens[-1][1] + 1 if self._tokens else 1)
        return InputExpressionError(message, col)

    def _expect(self, text: str):
        tok = self._peek()
        if tok is None or tok[0] != text:
            raise self._error_here(f"\"{text}\" expected")
        self._advance()

    def _parse_word_atome(self) -> list:
        """bouton | direction, pour une branche d'alternance (jamais mouvement)."""
        tok = self._peek()
        if tok is None or not _WORD_RE.fullmatch(tok[0]):
            raise self._error_here("a button or direction name is expected")
        word, col = self._advance()
        if word not in _BUTTONS:
            raise InputExpressionError(
                f"\"{word}\" is neither a button nor a valid direction", col)
        return [frozenset({word})]

    def _parse_alternance(self) -> list:
        self._expect("(")
        branches = self._parse_word_atome()
        while self._peek() is not None and self._peek()[0] == "|":
            self._advance()
            branches = branches + self._parse_word_atome()
        self._expect(")")
        if len(branches) > MAX_ALTERNATION_BRANCHES:
            raise InputExpressionError(
                f"too many branches in \"(...)\" ({len(branches)} > {MAX_ALTERNATION_BRANCHES})", 1)
        return branches

    def _parse_atome(self) -> list:
        """bouton | direction | alternance — un mouvement ici est une erreur :
        il n'est valide qu'en tête de l'expression entière."""
        tok = self._peek()
        if tok is None:
            raise self._error_here("an atom is expected")
        text, col = tok
        if text == "(":
            return self._parse_alternance()
        if not _WORD_RE.fullmatch(text):
            raise self._error_here(f"unexpected token \"{text}\"")
        if text in self._movements:
            raise InputExpressionError(
                f"\"{text}\" is a motion: it must be the first atom of the expression", col)
        self._advance()
        if text in _BUTTONS:
            return [frozenset({text})]
        raise InputExpressionError(
            f"\"{text}\" is neither a button, a direction nor a declared motion", col)

    def _parse_pas(self) -> list:
        branches = self._parse_atome()
        while self._peek() is not None and self._peek()[0] == "+":
            self._advance()
            next_branches = self._parse_atome()
            branches = [a | b for a in branches for b in next_branches]
        return branches

    def _parse_first_pas(self) -> list:
        """Rend une liste de candidats, chacun un tuple de pas (>1 seulement
        pour un mouvement qui s'étend sur plusieurs pas)."""
        tok = self._peek()
        if tok is not None and tok[0] in self._movements:
            self._advance()
            expansion = self._movements[tok[0]]
            last_candidates = [expansion[-1]]
            while self._peek() is not None and self._peek()[0] == "+":
                self._advance()
                next_branches = self._parse_atome()
                last_candidates = [a | b for a in last_candidates for b in next_branches]
            return [expansion[:-1] + (last,) for last in last_candidates]
        return [(step,) for step in self._parse_pas()]

    def parse(self) -> list:
        sequences = [list(cand) for cand in self._parse_first_pas()]
        while self._peek() is not None and self._peek()[0] == "-":
            self._advance()
            pas_branches = self._parse_pas()
            sequences = [seq + [b] for seq in sequences for b in pas_branches]
            if len(sequences) > MAX_ALTERNATIVES:
                raise InputExpressionError(
                    f"too many alternatives in total ({len(sequences)} > {MAX_ALTERNATIVES}) — use two separate "
                    "actions", 1)
        if self._peek() is not None:
            tok, col = self._peek()
            raise InputExpressionError(f"unexpected token \"{tok}\"", col)
        if len(sequences) > MAX_ALTERNATIVES:
            raise InputExpressionError(
                f"too many alternatives in total ({len(sequences)} > {MAX_ALTERNATIVES}) — use two separate "
                "actions", 1)
        return [InputExpression(steps=tuple(InputStep(s) for s in seq)) for seq in sequences]


def compile_movement(name: str, steps_text: str) -> tuple:
    """Compile un mouvement personnalisé (`InputMovement.steps`) en pas. Ne
    référence aucun mouvement, built-in ou personnalisé — pas de cycle possible
    par construction. Rend un tuple de `frozenset` (un mouvement ne s'écrit
    jamais avec `(a|b)` : l'alternance n'a de sens que pour une action)."""
    tokens = _tokenize(steps_text)
    parser = _Parser(tokens, movements={})
    alternatives = parser.parse()
    if len(alternatives) != 1:
        raise InputExpressionError(
            f"the motion \"{name}\" cannot use the alternation \"(a|b)\"", 1)
    return tuple(step.buttons for step in alternatives[0].steps)


def parse_input_expression(text: str, custom_movements: dict | None = None) -> list:
    """Parse l'expression d'une `InputBinding`. Rend la liste des `InputExpression`
    alternatives — une seule, sauf si l'expression utilise `(a|b)`."""
    movements = dict(BUILTIN_MOVEMENTS)
    for movement_name, steps_text in (custom_movements or {}).items():
        if movement_name in movements:
            raise InputExpressionError(
                f"\"{movement_name}\" is already a built-in motion", 1)
        movements[movement_name] = compile_movement(movement_name, steps_text)
    tokens = _tokenize(text)
    return _Parser(tokens, movements).parse()
