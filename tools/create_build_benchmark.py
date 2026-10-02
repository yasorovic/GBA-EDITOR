"""Crée le projet reproductible ``Project Demo/BuildBenchmark``.

Le fixture sert à mesurer le coût de conversion des assets de la v0.24 :
120 sprites distincts et 80 effets WAV, répartis sur quatre scènes de 30
acteurs. Les sprites restent volontairement en 16×16 (quatre tuiles chacun) :
le projet exerce grit et mmutil sans dépasser les budgets GBA (480 tuiles OBJ
au total ; 30 OAM/scène).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import wave
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Project Demo" / "MyGame"
TARGET = ROOT / "Project Demo" / "BuildBenchmark"
SPRITE_COUNT = 120
SFX_COUNT = 80
SCENE_COUNT = 4
SPRITES_PER_SCENE = SPRITE_COUNT // SCENE_COUNT


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def sprite_palette(index: int) -> list[str]:
    """Cinq couleurs déterministes, distinctes pour chaque source PNG."""
    hue = (index * 47) % 256
    return [
        "#101018",
        f"#{(hue + 48) % 256:02X}{(hue * 3 + 96) % 256:02X}{(hue * 5 + 144) % 256:02X}",
        f"#{(hue + 112) % 256:02X}{(hue * 7 + 160) % 256:02X}{(hue * 11 + 192) % 256:02X}",
        f"#{(hue + 176) % 256:02X}{(hue * 13 + 208) % 256:02X}{(hue * 17 + 224) % 256:02X}",
        "#F8F8F8",
    ]


def make_sprite(index: int, sprite_dir: Path) -> str:
    name = f"BenchmarkSprite{index:03d}"
    png_path = sprite_dir / f"{name}.png"
    colors = sprite_palette(index)
    rgb = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colors]

    image = Image.new("RGB", (16, 16), rgb[0])
    pixels = image.load()
    for y in range(16):
        for x in range(16):
            # Un motif dépendant de l'index évite 200 empreintes identiques.
            band = ((x // 4) + (y // 4) + index) % 4
            pixels[x, y] = rgb[band + 1]
    image.save(png_path)

    data = png_path.read_bytes()
    stamp = f"{len(data)}:{hashlib.sha1(data).hexdigest()[:16]}"
    palette16 = colors + ["#000000"] * (16 - len(colors))
    sidecar = {
        "name": name,
        "asset": f"assets/sprites/{name}.png",
        "frame_w": 16,
        "frame_h": 16,
        "source_stamp": stamp,
        "own_palette": colors,
        "quantize_method": "median_cut",
        "palettes": [palette16],
        "source_palettes": [palette16],
        "states": [{
            "name": "Idle",
            "speed": 8,
            "loop": True,
            "directions": [{
                "dir": 0,
                "frames": [{"tiles": [
                    {"src_col": x, "src_row": y, "dst_col": x, "dst_row": y}
                    for y in range(2) for x in range(2)
                ]}],
            }],
        }],
    }
    write_json(sprite_dir / f"{name}.json", sidecar)
    return name


def make_sfx(index: int, sfx_dir: Path) -> str:
    """Produit un bip PCM court mais distinct, accepté par mmutil."""
    name = f"BenchmarkSfx{index:03d}"
    wav_path = sfx_dir / f"{name}.wav"
    rate, samples = 8_000, 320
    frequency = 180 + index * 13
    frames = bytearray()
    for sample in range(samples):
        phase = (sample * frequency // rate) % 2
        frames.extend(struct.pack("<h", 8_000 if phase else -8_000))
    with wave.open(str(wav_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)
    write_json(sfx_dir / f"{name}.json", {
        "name": name,
        "asset": f"assets/sfx/{name}.wav",
        "volume": 100,
        "sample_rate": 0,
    })
    return name


def actor(name: str, index: int, sfx_name: str | None) -> dict:
    components = [{
        "component_type": "sprite", "id": "sprite", "active": True,
        "sprite_name": name, "initial_state": "Idle", "auto_dir": True,
        "affine_transform": False, "scale_x": 1.0, "scale_y": 1.0,
        "rotation": 0, "offset_x": 0, "offset_y": 0,
    }]
    if sfx_name:
        components.append({
            "component_type": "sound_fx", "id": "sound_fx", "active": True,
            "sfx_name": sfx_name, "trigger": "manual",
        })
    return {
        "name": f"Actor{index:03d}",
        "prefab_name": None,
        "active": True,
        "components": components,
        "x": (index % 10) * 20,
        "y": ((index // 10) % 8) * 20,
        "flip_h": False, "flip_v": False, "priority": 0, "pal_bank": 0,
        "visible": True, "obj_mode": 0, "rotation": 0, "scale_x": 1.0,
        "scale_y": 1.0, "screen_space": False, "dir_x": 0, "dir_y": 0,
        "notes": "Benchmark asset conversion fixture.",
    }


def scene(name: str, actors: list[dict]) -> dict:
    return {
        "name": name,
        "background_layers": [{
            "background_name": "", "bg_slot": 0, "scroll_speed": 1.0,
            "pal_bank": -1,
        }],
        "actors": actors,
        "actor_slots": len(actors),
        "cameras": [], "camera": "", "windows": [], "render_mode": 0,
        "scroll_h": False, "scroll_v": False, "script": "", "text_bg": 0,
        "ui_layouts": [], "font_name": "Basic", "collision_layer": 0,
        "collision_map": [[0] * 30 for _ in range(20)],
        "active_obj_palettes": ["DMG (GB Default)"],
        "active_bg_palettes": ["DMG (GB Default) (BG)"],
        "backdrop_color": 32767, "notes": "Asset conversion benchmark.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true",
                        help="remplace le fixture existant")
    args = parser.parse_args()
    if TARGET.exists() and not args.replace:
        raise SystemExit(f"Le fixture existe déjà : {TARGET}")
    if not SOURCE.exists():
        raise SystemExit(f"Démo source introuvable : {SOURCE}")
    if TARGET.exists():
        shutil.rmtree(TARGET)

    shutil.copytree(SOURCE, TARGET, ignore=shutil.ignore_patterns("build", "__pycache__"))
    (TARGET / "MyGame.project").rename(TARGET / "BuildBenchmark.project")

    # MyGame apporte les palettes et polices minimales. Tout ce qui pourrait
    # biaiser la mesure (scènes, UI, textes, scripts, sprites et fonds de la
    # démo) est retiré : le fixture ne doit mesurer que ses 200 assets.
    project_dir = TARGET / "project"
    for directory in (project_dir / "scenes", project_dir / "ui_layouts",
                      project_dir / "data", project_dir / "prefab",
                      TARGET / "assets" / "scripts",
                      TARGET / "assets" / "backgrounds"):
        if directory.exists():
            shutil.rmtree(directory)
    (project_dir / "scenes").mkdir(parents=True)
    for text_file in project_dir.glob("texts*.json"):
        text_file.unlink()
    for sprite_file in (TARGET / "assets" / "sprites").glob("*"):
        sprite_file.unlink()

    manifest_path = TARGET / "BuildBenchmark.project"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["start_scene"] = "BenchmarkScene01"
    manifest["last_scene"] = "BenchmarkScene01"
    manifest["author"] = "Backstage benchmark fixture"
    manifest["languages"] = []
    manifest["fallback_font"] = "Basic"
    write_json(manifest_path, manifest)

    sprite_dir = TARGET / "assets" / "sprites"
    names = [make_sprite(i + 1, sprite_dir) for i in range(SPRITE_COUNT)]
    sfx_dir = TARGET / "assets" / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    sfx_names = [make_sfx(i + 1, sfx_dir) for i in range(SFX_COUNT)]
    scenes_dir = TARGET / "project" / "scenes"
    for scene_index in range(SCENE_COUNT):
        first = scene_index * SPRITES_PER_SCENE
        batch = [actor(name, first + offset + 1,
                       sfx_names[first + offset] if first + offset < SFX_COUNT else None)
                 for offset, name in enumerate(names[first:first + SPRITES_PER_SCENE])]
        write_json(scenes_dir / f"BenchmarkScene{scene_index + 1:02d}.json",
                   scene(f"BenchmarkScene{scene_index + 1:02d}", batch))

    (TARGET / "README.md").write_text(
        "# BuildBenchmark\n\n"
        "Fixture reproductible pour mesurer la conversion d'assets de la v0.24. "
        "Il contient 120 sprites PNG distincts et 80 effets WAV, répartis sur "
        "quatre scènes de 30 acteurs : 480 tuiles OBJ au total, 30 entrées OAM "
        "par scène.\n\n"
        "Mesures prévues : build froid, rebuild inchangé, modification d'un PNG, "
        "puis modification d'une option de conversion.\n",
        encoding="utf-8")
    print(f"Créé : {TARGET}")


if __name__ == "__main__":
    main()
