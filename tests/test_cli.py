"""Tests for CLI functionality."""

import tempfile
from pathlib import Path
from click.testing import CliRunner
import pytest
import tomlkit

from extbpy.cli import cli


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
                "dependencies": ["click>=8.0.0"],
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


def test_cli_version():
    """Test version command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "extbpy" in result.output
    assert "version" in result.output


def test_cli_help():
    """Test help command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "extbpy" in result.output
    assert "Build Blender extensions" in result.output


def test_info_command(temp_project):
    """Test info command with valid project."""
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "--source-dir", str(temp_project)])
    assert result.exit_code == 0
    assert "Project Information" in result.output
    assert "test-extension" in result.output
    assert "Configured Platforms" in result.output
    assert "windows-x64" in result.output
    assert "linux-x64" in result.output


def test_info_command_no_extension():
    """Test info command with no extension directory."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create pyproject.toml but no extension directory
        pyproject = {"project": {"name": "test", "dependencies": []}}
        with open(Path(temp_dir) / "pyproject.toml", "w") as f:
            tomlkit.dump(pyproject, f)

        result = runner.invoke(cli, ["info", "--source-dir", temp_dir])
        assert result.exit_code == 1
        assert "No extension directory found" in result.output


def test_platform_validation():
    """Test platform validation in CLI."""
    runner = CliRunner()

    # Test invalid platform (should be caught by Click)
    result = runner.invoke(cli, ["build", "--platform", "invalid-platform"])
    assert result.exit_code == 2  # Click usage error
    assert "Invalid value" in result.output


def test_clean_command(temp_project):
    """Test clean command."""
    runner = CliRunner()

    # Create some temporary files to clean
    ext_dir = temp_project / "test-extension"
    (ext_dir / "test.blend1").touch()
    (ext_dir / "session.MNSession").touch()

    result = runner.invoke(cli, ["clean", "--source-dir", str(temp_project)])
    assert result.exit_code == 0
    assert "Cleaned" in result.output

    # Check files were removed
    assert not (ext_dir / "test.blend1").exists()
    assert not (ext_dir / "session.MNSession").exists()


def test_build_command_validation(temp_project):
    """Test build command validation without actually building."""
    runner = CliRunner()

    # Test with explicit valid platforms - this should fail since there's no Blender
    result = runner.invoke(
        cli,
        [
            "build",
            "--source-dir",
            str(temp_project),
            "--platform",
            "windows-x64",
            "--platform",
            "linux-x64",
        ],
    )

    # Should fail at some stage (no uv.lock, no Blender, etc.) but not at validation stage
    assert result.exit_code == 1
    assert "Build failed" in result.output
