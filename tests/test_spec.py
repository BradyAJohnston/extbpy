"""pyproject.toml -> ExtensionSpec -> manifest."""

import tomllib

import pytest

from extbpy.exceptions import ConfigurationError
from extbpy.extyp import BLPlatform
from extbpy.spec import ExtensionSpec


def test_spec_from_pyproject(project):
    spec = ExtensionSpec.from_pyproject(project)
    assert spec.id == "demo_ext"
    assert spec.name == "Demo Extension"
    assert spec.tagline == "A demo extension"
    assert spec.maintainer == "Jane Doe <jane@example.com>"
    assert spec.license == ("SPDX:GPL-3.0-or-later",)
    assert spec.website == "https://example.com/demo"
    assert spec.release.pretty_version == "5.2"
    assert spec.release.python_version == (3, 13)
    assert spec.platforms == (
        BLPlatform.linux_x64,
        BLPlatform.windows_x64,
        BLPlatform.macos_arm64,
    )
    assert spec.package_dir == project / "demo_ext"
    assert "numpy" in spec.excluded_packages
    assert spec.paths_exclude_pattern[-2:] == ("*.blend[1-9]", "secret/")


def test_manifest_toml_round_trips(project):
    spec = ExtensionSpec.from_pyproject(project)
    manifest = spec.manifest(
        platforms=(BLPlatform.linux_x64,),
        wheels=("./wheels/purepkg-2.0.0-py3-none-any.whl",),
    )
    data = tomllib.loads(manifest.to_toml())
    assert data == {
        "schema_version": "1.0.0",
        "id": "demo_ext",
        "version": "1.2.3",
        "name": "Demo Extension",
        "tagline": "A demo extension",
        "maintainer": "Jane Doe <jane@example.com>",
        "type": "add-on",
        "website": "https://example.com/demo",
        "tags": ["Development"],
        "blender_version_min": "5.2.0",
        "license": ["SPDX:GPL-3.0-or-later"],
        "copyright": ["2026 Jane Doe"],
        "platforms": ["linux-x64"],
        "wheels": ["./wheels/purepkg-2.0.0-py3-none-any.whl"],
        "permissions": {"network": "Fetching demo data"},
    }


def _spec(project, mutate):
    data = tomllib.loads((project / "pyproject.toml").read_text())
    mutate(data)
    return ExtensionSpec.from_dict(data, source_dir=project)


def test_missing_required_fields_are_listed_together(project):
    def mutate(d):
        del d["project"]["license"]
        del d["project"]["maintainers"]
        del d["tool"]["extbpy"]["blender_version_min"]

    with pytest.raises(ConfigurationError) as e:
        _spec(project, mutate)
    msg = str(e.value)
    assert "project.license" in msg
    assert "project.maintainers" in msg
    assert "blender_version_min" in msg


def test_platform_unsupported_by_release(project):
    def mutate(d):
        d["tool"]["extbpy"]["platforms"] = ["macos-x64"]

    with pytest.raises(ConfigurationError, match="does not ship for macos-x64"):
        _spec(project, mutate)


def test_default_platforms_are_all_for_release(project):
    spec = _spec(project, lambda d: d["tool"]["extbpy"].pop("platforms"))
    assert set(spec.platforms) == spec.release.platforms


def test_tagline_too_long_is_rejected_at_manifest_time(project):
    spec = _spec(project, lambda d: d["project"].__setitem__("description", "x" * 70))
    with pytest.raises(ConfigurationError, match="tagline"):
        spec.manifest(platforms=None, wheels=None)


def test_package_dir_override_and_src_layout(project):
    (project / "demo_ext").rename(project / "elsewhere")
    with pytest.raises(ConfigurationError, match="package_dir"):
        ExtensionSpec.from_pyproject(project)
    spec = ExtensionSpec.from_pyproject(project, package_dir=project / "elsewhere")
    assert spec.package_dir == project / "elsewhere"
    (project / "src").mkdir()
    (project / "elsewhere").rename(project / "src" / "demo_ext")
    assert (
        ExtensionSpec.from_pyproject(project).package_dir
        == project / "src" / "demo_ext"
    )
