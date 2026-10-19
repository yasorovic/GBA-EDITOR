"""Un renommage audio répare aussi les références enregistrées hors des scripts."""
import pytest

from core.models.audio import Sfx, Music, Jingle, MusicCue, CUE_KINDS
from core.models.components import SoundFxComponent
from core.models.data_table import DataColumn, DataTable
from core.models.scene import Actor, Prefab
from core.models.sound_box import SoundBox, JingleBox, MusicBox, MusicState, ActionState
from core.models.sprite import SpriteAsset, AnimState, StateDirection, AnimFrame
from core.project import Project


@pytest.mark.parametrize("kind", ["sfx", "music", "jingles"])
def test_sound_rename_updates_every_reference_and_survives_reopening(tmp_path, kind):
    p = Project.create(tmp_path / "Game", "Game")
    for folder in ((p.assets_dir / "sprites"), (p.assets_dir / "backgrounds"), (p.assets_dir / "sfx"), (p.assets_dir / "scripts")):
        folder.mkdir(parents=True, exist_ok=True)
    for store, cls in ((p.sfx, Sfx), (p.music, Music), (p.jingles, Jingle)):
        store.append(cls(name="Old"))
    for module in p.audio_modules():
        module.cues = [MusicCue(kind=k, target="Old") for k in CUE_KINDS]
    scene = p.active_scene
    scene.music = "Old"
    scene.actors = [Actor(name="Player", components=[
        SoundFxComponent(sfx_name="Old"), SoundFxComponent(id="disabled", active=False, sfx_name="Old"),
        SoundFxComponent(id="other", sfx_name="Other")])]
    p.prefabs.append(Prefab(name="Enemy", actor=Actor(components=[SoundFxComponent(sfx_name="Old")]),
                           children=[Actor(name="Child", components=[SoundFxComponent(sfx_name="Old")])]))
    p.sprites.append(SpriteAsset(name="Hero", states=[AnimState(directions=[StateDirection(frames=[
        AnimFrame(direct_sfx_name="Old", action_name="Old", event_name="Old")])])]))
    p.sound_boxes.append(SoundBox(name="Effects", actions=["Old"], states=[ActionState(mapping={"Old": "Old"})]))
    p.jingle_boxes.append(JingleBox(name="Jingles", actions=["Old"], states=[ActionState(mapping={"Old": "Old"})]))
    p.music_boxes.append(MusicBox(name="Tracks", states=[MusicState(name="Old", music="Old")]))
    p.data_tables.append(DataTable(name="Audio", columns=[DataColumn("effect", "sfx"),
        DataColumn("track", "music"), DataColumn("label", "text")],
        rows=[{"effect": "Old", "track": "Old", "label": "Old"}, {}]))
    script = (p.assets_dir / "scripts") / "Sounds.lua"
    script.write_text('function on_start()\n sfx:play("Old")\n music:play("Old")\n music:jingle("Old")\nend\n', encoding="utf-8")
    p.save()
    # Rouvre avant le geste : sprites et modules peuvent encore être différés.
    p = Project(p.root)
    p.load()
    p.rename_sound(getattr(p, kind).get("Old"), " New ")
    p = Project(p.root)
    p.load()
    p.load_all_resources()

    sound = "New" if kind == "sfx" else "Old"
    music = "New" if kind == "music" else "Old"
    jingle = "New" if kind == "jingles" else "Old"
    assert getattr(p, kind).get("New") is not None
    assert getattr(p, kind).get("Old") is None
    assert p.active_scene.music == music
    components = p.active_scene.actors[0].components
    assert [c.sfx_name for c in components] == [sound, sound, "Other"]
    prefab = p.prefabs.get("Enemy")
    assert prefab.components[0].sfx_name == prefab.children[0].components[0].sfx_name == sound
    frame = p.sprites.get("Hero").states[0].directions[0].frames[0]
    assert frame.direct_sfx_name == sound
    assert frame.action_name == frame.event_name == "Old"
    assert p.sound_boxes[0].states[0].mapping == {"Old": sound}
    assert p.jingle_boxes[0].states[0].mapping == {"Old": jingle}
    assert p.music_boxes[0].states[0].music == music
    assert p.music_boxes[0].states[0].name == "Old"
    for module in p.audio_modules():
        assert {c.kind: c.target for c in module.cues} == {
            "sfx": sound, "jingle": jingle, "sound_action": "Old", "jingle_action": "Old"}
    assert p.data_tables[0].rows == [{"effect": sound, "track": music, "label": "Old"}, {}]
    text = script.read_text(encoding="utf-8")
    assert f'sfx:play("{sound}")' in text
    assert f'music:play("{music}")' in text
    assert f'music:jingle("{jingle}")' in text
