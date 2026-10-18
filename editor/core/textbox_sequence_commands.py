"""Ajouter une page à une TextBox : un nouveau texte dans sa séquence, en un pas d'historique.

Une boîte libre devient une séquence au premier ajout : son contenu actuel devient la page 1
(copié, le texte d'origine reste intact pour ses autres usages), la page 2 est vide.
Une boîte déjà liée reçoit simplement le texte suivant de sa séquence."""
from core.history import Command
from core.models.text import key_from_path as text_key_from_path
from core.text_sequences import next_key, group_texts, group_keys


def _free_prefix(project, scene_name, box_name) -> str:
    """Un préfixe de séquence que personne n'utilise encore."""
    taken = project.text_keys()
    root = text_key_from_path([scene_name, box_name] if scene_name else [box_name], taken=set())
    prefix, n = root, 1
    while prefix in taken or group_keys(project, prefix):
        n += 1
        prefix = f"{root}_{n}"
    return prefix


class AddTextboxPageCmd(Command):
    label = "Add TextBox page"

    def __init__(self, project, box, scene_name="", persist_fn=None):
        self.project, self.box, self._persist = project, box, persist_fn
        self._before = (box.sequence_prefix, box.text_key, box.preview_text, box.preview_is_literal)
        self.created = []
        self._prefix = box.sequence_prefix
        self._scene = scene_name

    def _make(self):
        p, box = self.project, self.box
        if self._prefix:
            pages = group_texts(p, self._prefix)
            anchor = list(pages[-1].path) if pages else [self._scene or box.name]
            new = p.new_text(content="", path=anchor)
            p.rename_text_key(new, next_key(p, self._prefix))
            self.created = [new]
            return
        current = p.region_text(box)
        content = current.content if current is not None else ""
        self._prefix = _free_prefix(p, self._scene, box.name)
        first = p.new_text(content=content, path=[self._scene, box.name] if self._scene else [box.name])
        p.rename_text_key(first, f"{self._prefix}_Page01")
        second = p.new_text(content="", path=list(first.path))
        p.rename_text_key(second, f"{self._prefix}_Page02")
        self.created = [first, second]

    def execute(self):
        if not self.created:
            self._make()
        else:
            for text in self.created:
                if text not in self.project.texts:
                    self.project.texts.append(text)
        self.box.sequence_prefix = self._prefix
        self.box.text_key = ""
        self.box.preview_text = ""
        if self._persist:
            self._persist()

    def undo(self):
        for text in self.created:
            if text in self.project.texts:
                self.project.texts.remove(text)
        (self.box.sequence_prefix, self.box.text_key,
         self.box.preview_text, self.box.preview_is_literal) = self._before
        if self._persist:
            self._persist()
