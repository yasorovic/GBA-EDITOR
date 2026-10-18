"""Une empreinte d'asset doit changer avec le code qui le convertit."""
import codegen.asset_cache as asset_cache


def test_fingerprint_follows_the_pipeline_signature(monkeypatch):
    first = asset_cache.AssetBuildCache.fingerprint({"source": "abc"})
    assert first == asset_cache.AssetBuildCache.fingerprint({"source": "abc"})
    monkeypatch.setattr(asset_cache, "pipeline_signature", lambda: "another conversion code")
    assert asset_cache.AssetBuildCache.fingerprint({"source": "abc"}) != first


def test_signature_reads_the_conversion_sources(tmp_path, monkeypatch):
    before = asset_cache.pipeline_signature()
    source = tmp_path / "fake_conversion.py"
    source.write_text("X = 1\n", encoding="utf-8")
    fake = type("Fake", (), {"__file__": str(source)})
    monkeypatch.setattr(asset_cache.importlib, "import_module", lambda name: fake)
    asset_cache.pipeline_signature.cache_clear()
    try:
        first = asset_cache.pipeline_signature()
        source.write_text("X = 2\n", encoding="utf-8")
        asset_cache.pipeline_signature.cache_clear()
        assert asset_cache.pipeline_signature() != first != before
    finally:
        monkeypatch.undo()
        asset_cache.pipeline_signature.cache_clear()
