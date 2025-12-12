"""Tests for builder functionality."""

import tempfile
from pathlib import Path
import pytest
import tomlkit

from extbpy.builder import ExtensionBuilder
from extbpy.exceptions import ConfigurationError


@pytest.fixture
def temp_project():
    """Create a temporary project structure for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        # Create pyproject.toml
        pyproject = {
            "project": {
                "name": "test-extension",
                "version": "1.0.0",
                "dependencies": ["click>=8.0.0", "rich>=13.0.0"],
            },
            "tool": {"extbpy": {"platforms": ["windows-x64", "linux-x64"]}},
        }

        with open(project_dir / "pyproject.toml", "w") as f:
            tomlkit.dump(pyproject, f)

        # Create extension directory
        ext_dir = project_dir / "test-extension"
        ext_dir.mkdir()

        # Create minimal blender_manifest.toml
        manifest = {
            "schema_version": "1.0.0",
            "id": "test-extension",
            "version": "1.0.0",
            "name": "Test Extension",
        }

        with open(ext_dir / "blender_manifest.toml", "w") as f:
            tomlkit.dump(manifest, f)

        with open(ext_dir / "__init__.py", "w") as f:
            f.write("# Test extension\n")

        yield project_dir


@pytest.fixture
def temp_project_no_platforms():
    """Create a temporary project without platform configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        # Create pyproject.toml without platform config
        pyproject = {
            "project": {
                "name": "test-extension",
                "version": "1.0.0",
                "dependencies": ["click>=8.0.0"],
            }
        }

        with open(project_dir / "pyproject.toml", "w") as f:
            tomlkit.dump(pyproject, f)

        # Create extension directory
        ext_dir = project_dir / "test-extension"
        ext_dir.mkdir()

        # Create minimal blender_manifest.toml
        manifest = {
            "schema_version": "1.0.0",
            "id": "test-extension",
            "version": "1.0.0",
            "name": "Test Extension",
        }

        with open(ext_dir / "blender_manifest.toml", "w") as f:
            tomlkit.dump(manifest, f)

        yield project_dir


def test_builder_initialization(temp_project):
    """Test builder initialization with valid project."""
    builder = ExtensionBuilder(source_dir=temp_project)
    assert builder.source_dir.resolve() == temp_project.resolve()
    assert builder.extension_dir.name == "test-extension"
    assert builder.pyproject_path.exists()
    assert builder.manifest_path.exists()


def test_builder_no_pyproject():
    """Test builder with missing pyproject.toml."""
    with tempfile.TemporaryDirectory() as temp_dir:
        with pytest.raises(ConfigurationError, match="No pyproject.toml found"):
            ExtensionBuilder(source_dir=temp_dir)


def test_builder_no_extension_dir():
    """Test builder with missing extension directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        # Create pyproject.toml but no extension directory
        pyproject = {"project": {"name": "test", "dependencies": []}}
        with open(project_dir / "pyproject.toml", "w") as f:
            tomlkit.dump(pyproject, f)

        with pytest.raises(ConfigurationError, match="No extension directory found"):
            ExtensionBuilder(source_dir=project_dir)


def test_get_configured_platforms(temp_project):
    """Test getting configured platforms from pyproject.toml."""
    builder = ExtensionBuilder(source_dir=temp_project)
    platforms = builder.get_configured_platforms()
    assert platforms == ["windows-x64", "linux-x64"]


def test_get_configured_platforms_empty(temp_project_no_platforms):
    """Test getting configured platforms when none are set."""
    builder = ExtensionBuilder(source_dir=temp_project_no_platforms)
    platforms = builder.get_configured_platforms()
    assert platforms == []


def test_get_configured_platforms_invalid():
    """Test invalid platform configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        # Create pyproject.toml with invalid platform
        pyproject = {
            "project": {"name": "test-extension", "dependencies": []},
            "tool": {"extbpy": {"platforms": ["invalid-platform"]}},
        }

        with open(project_dir / "pyproject.toml", "w") as f:
            tomlkit.dump(pyproject, f)

        # Create extension directory
        ext_dir = project_dir / "test-extension"
        ext_dir.mkdir()

        # Create minimal blender_manifest.toml
        manifest = {
            "schema_version": "1.0.0",
            "id": "test-extension",
            "version": "1.0.0",
            "name": "Test Extension",
        }

        with open(ext_dir / "blender_manifest.toml", "w") as f:
            tomlkit.dump(manifest, f)

        builder = ExtensionBuilder(source_dir=project_dir)
        with pytest.raises(ConfigurationError, match="Invalid platforms"):
            builder.get_configured_platforms()


def test_get_project_info(temp_project):
    """Test getting project information."""
    builder = ExtensionBuilder(source_dir=temp_project)
    info = builder.get_project_info()

    assert info["name"] == "test-extension"
    assert info["version"] == "1.0.0"
    assert "click>=8.0.0" in info["dependencies"]
    assert "rich>=13.0.0" in info["dependencies"]
    assert info["configured_platforms"] == ["windows-x64", "linux-x64"]


def test_detect_current_platform(temp_project):
    """Test current platform detection."""
    builder = ExtensionBuilder(source_dir=temp_project)
    current = builder.detect_current_platform()
    assert len(current) == 1
    assert current[0] in ["windows-x64", "linux-x64", "macos-arm64", "macos-x64"]


def test_clean_files(temp_project):
    """Test cleaning temporary files."""
    builder = ExtensionBuilder(source_dir=temp_project)

    # Create some temporary files
    (builder.extension_dir / "test.blend1").touch()
    (builder.extension_dir / "session.MNSession").touch()

    # Clean them
    count = builder.clean_files()
    assert count == 2

    # Verify they're gone
    assert not (builder.extension_dir / "test.blend1").exists()
    assert not (builder.extension_dir / "session.MNSession").exists()


def test_excluded_packages(temp_project):
    """Test excluded packages functionality."""
    # Test with custom excluded packages
    builder = ExtensionBuilder(
        source_dir=temp_project, excluded_packages={"custom-package", "another-package"}
    )
    assert "custom-package" in builder.excluded_packages
    assert "another-package" in builder.excluded_packages

    # Test with default excluded packages
    builder_default = ExtensionBuilder(source_dir=temp_project)
    assert "numpy" in builder_default.excluded_packages
    assert "requests" in builder_default.excluded_packages
