"""Build orchestration with downloads stubbed out."""

import zipfile

import pytest

from extbpy import build as build_mod
from extbpy.exceptions import BuildError, DependencyError
from extbpy.extyp import BLPlatform
from extbpy.pydeps import LockFile
from extbpy.spec import ExtensionSpec


@pytest.fixture
def fake_downloads(monkeypatch, tmp_path):
    def fake(wheels, wheels_dir, **kwargs):
        wheels_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        for w in wheels:
            p = wheels_dir / w.filename
            p.write_bytes(b"PK")
            paths[w] = p
        return paths

    monkeypatch.setattr(build_mod, "download_wheels", fake)


def test_plan_targets_is_per_platform_when_binary(project):
    spec = ExtensionSpec.from_pyproject(project)
    lock = LockFile.load(spec.uv_lock_path, spec.id)
    targets = build_mod.plan_targets(
        spec, build_mod.resolve_all(spec, lock, spec.platforms)
    )
    assert [t.platform for t in targets] == list(spec.platforms)


def test_build_writes_one_zip_per_platform(project, tmp_path, fake_downloads):
    spec = ExtensionSpec.from_pyproject(project)
    results = build_mod.build(
        spec,
        platforms=(BLPlatform.linux_x64, BLPlatform.windows_x64),
        output_dir=tmp_path / "dist",
        wheels_dir=tmp_path / "cache",
    )
    assert [r.zip_path.name for r in results] == [
        "demo_ext-1.2.3-linux_x64.zip",
        "demo_ext-1.2.3-windows_x64.zip",
    ]
    with zipfile.ZipFile(results[1].zip_path) as zf:
        wheels = sorted(n for n in zf.namelist() if n.startswith("wheels/"))
        manifest = zf.read("blender_manifest.toml").decode()
    assert wheels == [
        "wheels/binpkg-3.0.0-cp313-cp313-win_amd64.whl",
        "wheels/purepkg-2.0.0-py3-none-any.whl",
        "wheels/subdep-0.1.0-py2.py3-none-any.whl",
        "wheels/winonly-1.0.0-py3-none-any.whl",
    ]
    assert 'platforms = [\n    "windows-x64",\n]' in manifest
    assert "numpy" not in manifest


def test_missing_wheel_aborts_before_download(project, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(build_mod, "download_wheels", lambda *a, **k: called.append(1))
    lock_text = (project / "uv.lock").read_text()
    lock_text = lock_text.replace(
        '{ name = "binpkg" },', '{ name = "binpkg" },\n    { name = "sdistonly" },', 1
    )
    (project / "uv.lock").write_text(lock_text)
    spec = ExtensionSpec.from_pyproject(project)
    with pytest.raises(DependencyError, match="sdistonly.*\n.*\n.*source distribution"):
        build_mod.build(
            spec,
            platforms=(BLPlatform.linux_x64,),
            output_dir=tmp_path,
            wheels_dir=tmp_path,
        )
    assert not called


def test_required_files(project, tmp_path, fake_downloads):
    (project / "pyproject.toml").write_text(
        (project / "pyproject.toml")
        .read_text()
        .replace(
            "[tool.extbpy]\n",
            '[tool.extbpy]\nrequired_files = ["demo_ext/assets/nodes.blend"]\n',
        )
    )
    spec = ExtensionSpec.from_pyproject(project)
    with pytest.raises(BuildError, match="nodes.blend"):
        build_mod.build(
            spec,
            platforms=(BLPlatform.linux_x64,),
            output_dir=tmp_path,
            wheels_dir=tmp_path,
        )


def test_build_syncs_package_for_local_platform(
    project, tmp_path, fake_downloads, monkeypatch
):
    monkeypatch.setattr(build_mod, "local_platform", lambda: BLPlatform.windows_x64)
    spec = ExtensionSpec.from_pyproject(project)
    build_mod.build(
        spec,
        platforms=(BLPlatform.linux_x64, BLPlatform.windows_x64),
        output_dir=tmp_path / "dist",
        wheels_dir=tmp_path / "cache",
    )
    manifest = (spec.package_dir / "blender_manifest.toml").read_text()
    assert 'platforms = [\n    "windows-x64",\n]' in manifest
    wheels = sorted(p.name for p in (spec.package_dir / "wheels").glob("*.whl"))
    assert wheels == [
        "binpkg-3.0.0-cp313-cp313-win_amd64.whl",
        "purepkg-2.0.0-py3-none-any.whl",
        "subdep-0.1.0-py2.py3-none-any.whl",
        "winonly-1.0.0-py3-none-any.whl",
    ]


def test_build_skips_sync_when_local_platform_not_built(
    project, tmp_path, fake_downloads, monkeypatch
):
    monkeypatch.setattr(build_mod, "local_platform", lambda: BLPlatform.macos_arm64)
    spec = ExtensionSpec.from_pyproject(project)
    build_mod.build(
        spec,
        platforms=(BLPlatform.linux_x64,),
        output_dir=tmp_path,
        wheels_dir=tmp_path,
    )
    assert (
        spec.package_dir / "blender_manifest.toml"
    ).read_text() == "# stale, must not be packed\n"
    assert list((spec.package_dir / "wheels").glob("*.whl")) == [
        spec.package_dir / "wheels" / "old-0.0.1-py3-none-any.whl"
    ]


def test_sync_replaces_stale_wheels(project, tmp_path, fake_downloads, monkeypatch):
    monkeypatch.setattr(build_mod, "local_platform", lambda: BLPlatform.linux_x64)
    spec = ExtensionSpec.from_pyproject(project)
    manifest_path = build_mod.sync(spec, wheels_dir=tmp_path / "cache")
    assert manifest_path == spec.package_dir / "blender_manifest.toml"
    wheels = sorted(p.name for p in (spec.package_dir / "wheels").glob("*.whl"))
    assert wheels == [
        "binpkg-3.0.0-cp313-cp313-manylinux_2_28_x86_64.whl",
        "purepkg-2.0.0-py3-none-any.whl",
        "subdep-0.1.0-py2.py3-none-any.whl",
    ]


def test_sync_rejects_unsupported_local_platform(project, tmp_path, monkeypatch):
    from extbpy.exceptions import PlatformError

    monkeypatch.setattr(build_mod, "local_platform", lambda: BLPlatform.linux_arm64)
    spec = ExtensionSpec.from_pyproject(project)
    with pytest.raises(PlatformError, match="linux-arm64"):
        build_mod.sync(spec, wheels_dir=tmp_path)
