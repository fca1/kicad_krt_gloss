"""Validate the installation layout without generating a distribution ZIP."""
import json
import runpy
import package_pcm


def test_staging_preserves_runtime_and_version_contract(tmp_path, monkeypatch):
    def binaries(destination):
        destination.mkdir(parents=True)
        for name in package_pcm.BINARIES:
            (destination / name).write_bytes(b"test binary")

    monkeypatch.setattr(package_pcm, "_download_binaries", binaries)
    staged = package_pcm.build(tmp_path, stage_only=True)
    plugin = staged / "plugins"
    metadata = json.loads((staged / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["versions"][0]["version"] == package_pcm.VERSION
    assert runpy.run_path(str(plugin / "version.py"))["__version__"] == package_pcm.VERSION
    assert not list(tmp_path.rglob("*.zip"))
    assert (plugin / "KRT/VERSION").read_text().strip() == package_pcm.KRT_VERSION
    for name in package_pcm.BINARIES:
        assert (plugin / "KRT/rust_router" / name).is_file()
    assert not (plugin / "KRT/rust_router/grid_router.pyd").exists()
    # KRT 0.23's GUI dependency gate now delegates to this shared module.
    assert (plugin / "KRT/py_router/startup_checks.py").is_file()
    assert (plugin / "KRT/requirements.txt").is_file()
    assert (plugin / "KRT/kicad_routing_plugin/deps_check.py").is_file()
    assert (plugin / "dgloss/krt_api.py").is_file()

