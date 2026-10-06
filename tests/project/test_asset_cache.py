"""Contrats du cache de conversion des assets."""

from pathlib import Path

from codegen.asset_cache import AssetBuildCache


def test_cache_requires_matching_fingerprint_and_outputs(tmp_path: Path):
    output = tmp_path / "sprite.c"
    output.write_text("asset", encoding="utf-8")

    cache = AssetBuildCache(tmp_path)
    cache.store("sprite:Hero", "source-and-options")
    cache.save()

    reloaded = AssetBuildCache(tmp_path)
    assert reloaded.hit("sprite:Hero", "source-and-options", [output])
    assert not reloaded.hit("sprite:Hero", "different-options", [output])

    output.unlink()
    assert not reloaded.hit("sprite:Hero", "source-and-options", [output])
