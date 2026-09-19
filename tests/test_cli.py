"""CLI smoke tests (no network)."""

from click.testing import CliRunner

from extbpy import build as build_mod
from extbpy.cli import cli


def test_info(project):
    result = CliRunner().invoke(cli, ["info", "-s", str(project)])
    assert result.exit_code == 0, result.output
    assert "Demo Extension" in result.output
    assert "linux-x64" in result.output


def test_manifest_for_platform(project):
    result = CliRunner().invoke(
        cli, ["manifest", "-s", str(project), "-p", "windows-x64"]
    )
    assert result.exit_code == 0, result.output
    assert 'id = "demo_ext"' in result.output
    assert "winonly-1.0.0-py3-none-any.whl" in result.output
    assert "binpkg-3.0.0-cp313-cp313-win_amd64.whl" in result.output


def test_unknown_platform_fails(project):
    result = CliRunner().invoke(cli, ["manifest", "-s", str(project), "-p", "amiga"])
    assert result.exit_code == 1
    assert "Unsupported platform" in result.output


def test_build_command(project, tmp_path, monkeypatch):
    def fake(wheels, wheels_dir, **kwargs):
        wheels_dir.mkdir(parents=True, exist_ok=True)
        return {
            w: (wheels_dir / w.filename, (wheels_dir / w.filename).write_bytes(b"PK"))[
                0
            ]
            for w in wheels
        }

    monkeypatch.setattr(build_mod, "download_wheels", fake)
    result = CliRunner().invoke(
        cli,
        [
            "build",
            "-s",
            str(project),
            "-o",
            str(tmp_path),
            "-p",
            "linux-x64",
            "--no-check",
            "--skip-lock-check",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo_ext-1.2.3-linux_x64.zip").is_file()


def test_clean(project):
    result = CliRunner().invoke(cli, ["clean", "-s", str(project)])
    assert result.exit_code == 0, result.output
    assert "Removed 1 file(s)" in result.output
    assert not (project / "demo_ext" / "scene.blend1").exists()
