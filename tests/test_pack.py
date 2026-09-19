"""Zip packing and exclude patterns."""

import zipfile
from pathlib import PurePosixPath

import pytest

from extbpy.extyp import BLPlatform
from extbpy.pack import collect_package_files, is_excluded, pack_extension
from extbpy.spec import ExtensionSpec


@pytest.mark.parametrize(
    ("path", "is_dir", "pattern", "expected"),
    [
        ("__pycache__", True, "__pycache__/", True),
        ("__pycache__", False, "__pycache__/", False),
        ("a/b/__pycache__", True, "__pycache__/", True),
        (".git", True, ".*", True),
        ("a/.DS_Store", False, ".*", True),
        ("out.zip", False, "/*.zip", True),
        ("sub/out.zip", False, "/*.zip", False),
        ("x.blend1", False, "*.blend[1-9]", True),
        ("x.blend", False, "*.blend[1-9]", False),
        ("nodes/_generation/x.py", False, "nodes/_generation/*", True),
    ],
)
def test_is_excluded(path, is_dir, pattern, expected):
    assert (
        is_excluded(PurePosixPath(path), is_dir=is_dir, patterns=[pattern]) is expected
    )


def test_collect_package_files(project):
    spec = ExtensionSpec.from_pyproject(project)
    names = sorted(
        arc
        for _, arc in collect_package_files(
            spec.package_dir, spec.paths_exclude_pattern
        )
    )
    assert names == ["__init__.py", "scene.blend", "sub/mod.py"]


def test_pack_extension_layout(project, tmp_path):
    spec = ExtensionSpec.from_pyproject(project)
    wheel = tmp_path / "purepkg-2.0.0-py3-none-any.whl"
    wheel.write_bytes(b"PK")
    manifest = spec.manifest(
        platforms=(BLPlatform.linux_x64,), wheels=(f"./wheels/{wheel.name}",)
    )
    out = pack_extension(
        package_dir=spec.package_dir,
        manifest=manifest,
        wheel_paths=[wheel],
        exclude_patterns=spec.paths_exclude_pattern,
        output_path=tmp_path / "out" / "demo.zip",
    )
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == [
            "__init__.py",
            "blender_manifest.toml",
            "scene.blend",
            "sub/mod.py",
            "wheels/purepkg-2.0.0-py3-none-any.whl",
        ]
        assert zf.read("blender_manifest.toml").decode() == manifest.to_toml()
        assert (
            zf.getinfo("wheels/purepkg-2.0.0-py3-none-any.whl").compress_type
            == zipfile.ZIP_STORED
        )
