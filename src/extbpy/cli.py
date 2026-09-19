"""Command-line interface for extbpy."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from . import __version__, build as build_mod
from .exceptions import ExtbpyError
from .extyp import BLPlatform
from .pydeps import LockFile
from .pydeps.download import download_wheels
from .spec import ExtensionSpec

console = Console()
err_console = Console(stderr=True)
logger = logging.getLogger("extbpy")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=err_console, show_path=False, show_time=False)],
    )


def _fail(message: str) -> None:
    err_console.print(f"[bold red]error:[/bold red] {message}")
    sys.exit(1)


# ----------------------------------------------------------------------
# Shared options
# ----------------------------------------------------------------------
def _common_options(f):  # type: ignore[no-untyped-def]
    f = click.option(
        "-s",
        "--source-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=".",
        show_default=True,
        help="Project directory containing pyproject.toml and uv.lock.",
    )(f)
    f = click.option(
        "--package-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        help="Extension package directory (defaults to <source-dir>/<id> or src/<id>).",
    )(f)
    return f


def _platform_option(f):  # type: ignore[no-untyped-def]
    return click.option(
        "-p",
        "--platform",
        "platforms",
        multiple=True,
        help="Target platform(s). Repeatable. 'all' = configured platforms, "
        "'current' = this machine. Default: configured platforms.",
    )(f)


def _wheels_dir_option(f):  # type: ignore[no-untyped-def]
    return click.option(
        "--wheels-dir",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        help=f"Wheel cache directory. Default: <source-dir>/{build_mod.DEFAULT_WHEELS_DIRNAME}",
    )(f)


def _load_spec(source_dir: Path, package_dir: Path | None) -> ExtensionSpec:
    return ExtensionSpec.from_pyproject(source_dir, package_dir=package_dir)


def _select_platforms(
    spec: ExtensionSpec, requested: tuple[str, ...]
) -> tuple[BLPlatform, ...]:
    if not requested or "all" in requested:
        return spec.platforms
    selected: list[BLPlatform] = []
    for value in requested:
        p = BLPlatform.detect() if value == "current" else BLPlatform.parse(value)
        if p not in spec.platforms:
            configured = ", ".join(x.value for x in spec.platforms)
            _fail(f"{p} is not in tool.extbpy.platforms ({configured})")
        if p not in selected:
            selected.append(p)
    return tuple(selected)


def _wheels_dir(spec: ExtensionSpec, override: Path | None) -> Path:
    return (override or spec.source_dir / build_mod.DEFAULT_WHEELS_DIRNAME).resolve()


class _DownloadUI:
    """Rich progress bars driven by the download callbacks."""

    def __init__(self) -> None:
        self.progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
            transient=True,
        )
        self.tasks: dict[str, TaskID] = {}

    def __enter__(self) -> _DownloadUI:
        self.progress.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        self.progress.__exit__(*exc)  # type: ignore[arg-type]

    def on_progress(self, wheel, nbytes: int) -> None:  # type: ignore[no-untyped-def]
        task = self.tasks.get(wheel.filename)
        if task is None:
            task = self.progress.add_task(wheel.filename, total=wheel.size)
            self.tasks[wheel.filename] = task
        self.progress.update(task, advance=nbytes)

    def on_finish(self, wheel, path: Path) -> None:  # type: ignore[no-untyped-def]
        task = self.tasks.pop(wheel.filename, None)
        if task is not None:
            self.progress.remove_task(task)
        console.print(f"  downloaded {wheel.filename}")


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------
@click.group()
@click.version_option(__version__, prog_name="extbpy")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """Build Blender extensions from a uv project."""
    _setup_logging(verbose)


@cli.command()
@_common_options
@_platform_option
@_wheels_dir_option
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=".",
    show_default=True,
    help="Where to write the extension zip(s).",
)
@click.option(
    "--blender",
    type=str,
    default=None,
    help="Blender executable used to validate the zips.",
)
@click.option("--no-check", is_flag=True, help="Skip validating the zips with Blender.")
@click.option(
    "--skip-lock-check",
    is_flag=True,
    help="Do not verify uv.lock matches pyproject.toml.",
)
def build(
    source_dir: Path,
    package_dir: Path | None,
    platforms: tuple[str, ...],
    wheels_dir: Path | None,
    output_dir: Path,
    blender: str | None,
    no_check: bool,
    skip_lock_check: bool,
) -> None:
    """Resolve, download and pack the extension for each platform."""
    try:
        spec = _load_spec(source_dir, package_dir)
        selected = _select_platforms(spec, platforms)

        if not skip_lock_check:
            uv_exe = build_mod.find_uv()
            if uv_exe is None:
                logger.warning("uv not found; skipping the uv.lock freshness check")
            else:
                build_mod.check_lock_current(spec, uv_exe)

        console.print(
            f"[bold]{spec.name}[/bold] {spec.version} for Blender {spec.release.pretty_version}+ "
            f"({', '.join(p.value for p in selected)})"
        )
        with _DownloadUI() as ui:
            results = build_mod.build(
                spec,
                platforms=selected,
                output_dir=output_dir.resolve(),
                wheels_dir=_wheels_dir(spec, wheels_dir),
                on_download_progress=ui.on_progress,
                on_download_finish=ui.on_finish,
                on_status=lambda msg: console.print(msg),
            )

        blender_exe = None if no_check else build_mod.find_blender(blender)
        if not no_check and blender_exe is None:
            logger.info(
                "Blender not found; skipping `blender --command extension validate`"
            )

        console.print()
        for r in results:
            size_mb = r.zip_path.stat().st_size / 1e6
            if blender_exe is not None:
                build_mod.validate_with_blender(blender_exe, r.zip_path)
                status = "[green]validated[/green]"
            else:
                status = "built"
            console.print(
                f"  {status} {r.zip_path} ({size_mb:.1f} MB, {len(r.target.wheels)} wheels)"
            )
    except ExtbpyError as e:
        _fail(str(e))


@cli.command()
@_common_options
@_platform_option
@_wheels_dir_option
def download(
    source_dir: Path,
    package_dir: Path | None,
    platforms: tuple[str, ...],
    wheels_dir: Path | None,
) -> None:
    """Download the wheels for the selected platforms into the cache."""
    try:
        spec = _load_spec(source_dir, package_dir)
        selected = _select_platforms(spec, platforms)
        lock = LockFile.load(spec.uv_lock_path, spec.id)
        resolutions = build_mod.resolve_all(spec, lock, selected)
        needed = {w for r in resolutions.values() for w in r.wheels.values()}
        target = _wheels_dir(spec, wheels_dir)
        with _DownloadUI() as ui:
            download_wheels(
                needed, target, on_progress=ui.on_progress, on_finish=ui.on_finish
            )
        console.print(f"{len(needed)} wheel(s) available in {target}")
    except ExtbpyError as e:
        _fail(str(e))


@cli.command()
@_common_options
@click.option(
    "-p",
    "--platform",
    "platform",
    default=None,
    help="Platform whose manifest to show.",
)
def manifest(source_dir: Path, package_dir: Path | None, platform: str | None) -> None:
    """Print the blender_manifest.toml that would be generated."""
    try:
        spec = _load_spec(source_dir, package_dir)
        selected = _select_platforms(spec, (platform,) if platform else ())
        lock = LockFile.load(spec.uv_lock_path, spec.id)
        resolutions = build_mod.resolve_all(spec, lock, selected)
        targets = build_mod.plan_targets(spec, resolutions)
        if platform is not None:
            targets = [
                t for t in targets if t.platform is None or t.platform.value == platform
            ]
        for i, target in enumerate(targets):
            if i:
                console.print()
            if len(targets) > 1:
                console.print(f"# {target.platform}")
            console.print(
                target.manifest(spec).to_toml(), end="", highlight=False, markup=False
            )
    except ExtbpyError as e:
        _fail(str(e))


@cli.command()
@_common_options
def info(source_dir: Path, package_dir: Path | None) -> None:
    """Show the extension specification parsed from pyproject.toml."""
    try:
        spec = _load_spec(source_dir, package_dir)
    except ExtbpyError as e:
        _fail(str(e))
        return
    table = Table(show_header=False, box=None)
    table.add_row("id", spec.id)
    table.add_row("name", spec.name)
    table.add_row("version", spec.version)
    table.add_row("tagline", spec.tagline)
    table.add_row("maintainer", spec.maintainer)
    table.add_row("license", ", ".join(spec.license))
    table.add_row(
        "blender",
        f">= {spec.blender_version_min}"
        + (f", < {spec.blender_version_max}" if spec.blender_version_max else ""),
    )
    table.add_row("python", ".".join(str(v) for v in spec.release.python_version))
    table.add_row("platforms", ", ".join(p.value for p in spec.platforms))
    table.add_row("package dir", str(spec.package_dir))
    table.add_row("excluded", ", ".join(sorted(spec.excluded_packages)))
    if spec.extras:
        table.add_row("extras", ", ".join(spec.extras))
    console.print(table)


@cli.command()
@_common_options
@click.option(
    "--pattern",
    "patterns",
    multiple=True,
    default=("*.blend1", "*.MNSession"),
    show_default=True,
    help="Glob of files to delete inside the package directory. Repeatable.",
)
def clean(
    source_dir: Path, package_dir: Path | None, patterns: tuple[str, ...]
) -> None:
    """Delete stray files (backup blends, sessions) from the package directory."""
    try:
        spec = _load_spec(source_dir, package_dir)
    except ExtbpyError as e:
        _fail(str(e))
        return
    removed = 0
    for pattern in patterns:
        for path in spec.package_dir.rglob(pattern):
            if path.is_file():
                path.unlink()
                removed += 1
                logger.debug("removed %s", path)
    console.print(f"Removed {removed} file(s)")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
