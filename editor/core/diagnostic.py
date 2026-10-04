"""Le diagnostic : l'unique forme d'un avertissement ou d'une erreur de build.

Module de BASE — il n'importe rien du projet. Le validateur, le checker Lua, les générateurs de C et
les étapes d'outils le construisent tous ; s'il vivait dans `core.validator` (qui lit le modèle et
appelle le codegen), chaque générateur qui émet un diagnostic fermerait une boucle d'import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DiagnosticTarget:
    """Où mène un diagnostic quand on le clique (cf. panneau Diagnostics).

    Volontairement en CHAÎNES, pas en références de modèle : le message reste de
    la donnée pure, et c'est l'interface qui résout le nom au moment du clic (par
    `Project.all_elements`), comme le journal résout un `fichier.lua:ligne`.

    Un seul `kind` pour l'instant — `ui_element` : la zone/le panneau/l'image
    d'une mise en page, que rien ne rendait cliquable jusqu'ici (un acteur passe
    déjà par son nom, un script par le `fichier.lua:ligne` de son message). Le
    vocabulaire s'étendra si un autre écran gagne une cible (cf. TodoTechnique)."""
    kind: str            # "ui_element"
    name: str = ""       # nom de l'élément
    layout: str = ""     # mise en page qui le contient (désambiguïse `all_elements`)


@dataclass
class ValidationMessage:
    """Un diagnostic : ce que le validateur, le checker Lua, le codegen ou un outil
    reproche au projet. C'est l'UNIQUE forme d'un avertissement ou d'une erreur de build
    (chantier « La fiabilité du journal de build ») : la console, l'onglet Diagnostics et
    `build.log` en sont tous rendus, et l'événement `diagnostic` du `BuildWorker` le porte."""
    level: str      # "warning" | "error"
    actor: str      # nom de l'actor (ou du propriétaire du script) ; "" si global
    message: str
    target: Optional[DiagnosticTarget] = None   # cible cliquable, ou None
    source: str = ""    # qui le dit : "validator", "script", "checker", "codegen", un outil…
    file: str = ""      # fichier fautif (nom seul), ou ""
    line: int = 0       # ligne dans ce fichier, ou 0 si elle est inconnue
    scene: str = ""     # scène contrôlée quand le message vient d'un contrôle PAR scène

    def __str__(self):
        return f"{'⚠' if self.level == 'warning' else '✖'}  {self._where()}{self._owner()}{self.message}"

    def _owner(self) -> str:
        """`[Scène/Acteur] `, `[Scène] ` ou `[Acteur] ` : de qui l'on parle."""
        if self.scene and self.actor:
            return f"[{self.scene}/{self.actor}] "
        if self.scene or self.actor:
            return f"[{self.scene or self.actor}] "
        return ""

    def _where(self) -> str:
        """`Hit.lua:3: ` ; sans fichier, le nom de l'étape ou de l'outil qui parle (jamais
        « validator », qui est le cas ordinaire)."""
        if self.file:
            return f"{self.file}:{self.line}: " if self.line else f"{self.file}: "
        return f"{self.source}: " if self.source not in ("", "validator") else ""

    def console_line(self) -> str:
        """La ligne du journal : `[error] Hit.lua:3: [Ball] message`. Le format
        `fichier:ligne` est garanti par les champs, pas deviné dans un texte libre — c'est ce
        que le clic de la console relit."""
        tag = "[warn] " if self.level == "warning" else "[error]"
        return f"{tag} {self._where()}{self._owner()}{self.message}"


def build_error(message: str, source: str, file: str = "", line: int = 0,
                actor: str = "") -> ValidationMessage:
    """Une erreur de build émise hors du validateur (étape, outil, générateur)."""
    return ValidationMessage("error", actor, message, None, source, file, line)


def build_warning(message: str, source: str, file: str = "", line: int = 0,
                  actor: str = "") -> ValidationMessage:
    """Un avertissement de build émis hors du validateur."""
    return ValidationMessage("warning", actor, message, None, source, file, line)
