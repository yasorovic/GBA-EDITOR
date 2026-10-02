"""
Système de plugins Backstage.

Un plugin est un dossier dans plugins/ contenant un fichier editor.py.
Il est chargé automatiquement au démarrage via load_all_plugins().

Structure minimale d'un plugin :
    plugins/
      mon_plugin/
        editor.py          ← enrichit un des registres ci-dessous

Trois surfaces d'extension, par ordre de portée :

  - un COMPOSANT      `COMPONENT_REGISTRY["x"] = XComponent` + `@register("x")`
                      pour son éditeur       — plugins/example_path/editor.py
  - une RÈGLE de build `@register_validator` — core/validator.py
  - un ÉCRAN entier    `register_screen(nom, fabrique)` — ui/screens.py,
                       exemple dans plugins/example_screen/editor.py

Les plugins sont chargés AVANT la QApplication : un editor.py ne doit donc
construire aucun widget au moment de son import — d'où la *fabrique* passée à
`register_screen`, appelée plus tard par la fenêtre.
"""
import importlib
import importlib.util
from pathlib import Path


def load_all_plugins():
    """Charge tous les editor.py trouvés dans les sous-dossiers de plugins/."""
    plugins_dir = Path(__file__).parent
    loaded = []
    errors = []
    # main.py appelle cette fonction avant même de créer la QApplication :
    # une exception ici tuerait l'éditeur au lancement, sans fenêtre ni
    # message. Le dossier peut manquer dans une distribution compilée (il y
    # est embarqué comme données, pas comme code) — dans ce cas on démarre
    # simplement sans plugin.
    if not plugins_dir.is_dir():
        return loaded, errors
    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
            continue
        entry = plugin_dir / "editor.py"
        if not entry.exists():
            continue
        module_name = f"plugins.{plugin_dir.name}.editor"
        try:
            spec = importlib.util.spec_from_file_location(module_name, entry)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            loaded.append(plugin_dir.name)
        except Exception as exc:
            errors.append((plugin_dir.name, exc))
    return loaded, errors
