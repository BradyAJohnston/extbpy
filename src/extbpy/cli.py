"""
CLI interface for extbpy - Blender Extension Builder.
"""

import sys
from pathlib import Path
from typing import List
import click
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install
import logging

from . import __version__
from .builder import ExtensionBuilder
from .exceptions import ExtbpyError

install(show_locals=True)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Setup rich logging with appropriate level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, version: bool) -> None:
    """
    🔧 extbpy - Build Blender extensions with Python dependencies

    A minimal tool for building Blender extensions that include Python packages
    as wheels, with cross-platform support and intelligent dependency management.
    """
    setup_logging(verbose)

    if version:
        console.print(
            f"[bold blue]extbpy[/bold blue] version [bold green]{__version__}[/bold green]"
        )
        sys.exit(0)

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@cli.command()
@click.option(
    "--source-dir",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Source directory containing extension files",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=Path.cwd(),
    help="Output directory for built extensions",
)
@click.option(
    "--platform",
    "-p",
    multiple=True,
    type=click.Choice(["windows-x64", "linux-x64", "macos-arm64", "macos-x64", "all"]),
    help='Target platforms (can be specified multiple times). Use "all" for all supported platforms',
)
@click.option(
    "--python-version", default="3.11", help="Python version for dependency resolution"
)
@click.option(
    "--clean/--no-clean", default=True, help="Clean wheel directory before downloading"
)
@click.option(
    "--split-platforms/--no-split-platforms",
    default=True,
    help="Create separate builds for each platform",
)
@click.option(
    "--exclude-package",
    multiple=True,
    help="Exclude specific packages from wheels (can be specified multiple times)",
)
@click.option(
    "--ignore-platform-errors/--fail-on-platform-errors",
    default=True,
    help="Continue building even if some platforms fail (default: true)",
)
@click.option(
    "--wheel-url",
    multiple=True,
    help="Additional wheel URLs to download (can be specified multiple times)",
)
def build(
    source_dir: Path,
    output_dir: Path,
    platform: List[str],
    python_version: str,
    clean: bool,
    split_platforms: bool,
    exclude_package: List[str],
    ignore_platform_errors: bool,
    wheel_url: List[str],
) -> None:
    """
    🏗️  Build a Blender extension with Python dependencies

    Downloads Python wheels for specified platforms and builds the extension.
    If no platforms are specified, builds for the current platform.
    Use "--platform all" to build for all supported platforms.
    """
    try:
        builder = ExtensionBuilder(
            source_dir=source_dir,
            output_dir=output_dir,
            python_version=python_version,
            excluded_packages=set(exclude_package),
        )

        # Handle platform selection
        if "all" in platform:
            if len(platform) > 1:
                console.print(
                    "[yellow]Warning: 'all' specified with other platforms. Using configured platforms.[/yellow]"
                )
            configured_platforms = builder.get_configured_platforms()
            if configured_platforms:
                console.print(
                    f"[blue]Building for configured platforms: {', '.join(configured_platforms)}[/blue]"
                )
                platform = configured_platforms
            else:
                console.print(
                    "[blue]No platforms configured, using all supported platforms...[/blue]"
                )
                platform = ["windows-x64", "linux-x64", "macos-arm64", "macos-x64"]
        elif not platform:
            configured_platforms = builder.get_configured_platforms()
            if configured_platforms:
                console.print(
                    f"[blue]Using configured platforms: {', '.join(configured_platforms)}[/blue]"
                )
                platform = configured_platforms
            else:
                console.print(
                    "[yellow]No platforms configured, detecting current platform...[/yellow]"
                )
                platform = builder.detect_current_platform()
        else:
            # Validate specified platforms
            valid_platforms = {"windows-x64", "linux-x64", "macos-arm64", "macos-x64"}
            invalid_platforms = [p for p in platform if p not in valid_platforms]
            if invalid_platforms:
                console.print(
                    f"[bold red]❌ Invalid platforms:[/bold red] {', '.join(invalid_platforms)}"
                )
                console.print(
                    f"Valid platforms are: {', '.join(sorted(valid_platforms))}"
                )
                sys.exit(1)

        builder.build(
            platforms=platform,
            clean=clean,
            split_platforms=split_platforms,
            ignore_platform_errors=ignore_platform_errors,
            additional_urls=list(wheel_url) if wheel_url else None,
        )

        console.print("[bold green]✅ Build completed successfully![/bold green]")

    except ExtbpyError as e:
        console.print(f"[bold red]❌ Build failed:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]❌ Unexpected error:[/bold red] {e}")
        if logging.getLogger().level <= logging.DEBUG:
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.option(
    "--source-dir",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Source directory to clean",
)
@click.option(
    "--pattern",
    "-p",
    multiple=True,
    default=[".blend1", ".MNSession"],
    help="File patterns to clean (can be specified multiple times)",
)
def clean(source_dir: Path, pattern: List[str]) -> None:
    """
    🧹 Clean temporary files from extension directory

    Removes temporary files like .blend1 and .MNSession files.
    """
    try:
        builder = ExtensionBuilder(source_dir=source_dir)
        cleaned_count = builder.clean_files(patterns=pattern)

        if cleaned_count > 0:
            console.print(f"[bold green]✅ Cleaned {cleaned_count} files[/bold green]")
        else:
            console.print("[yellow]No files to clean[/yellow]")

    except ExtbpyError as e:
        console.print(f"[bold red]❌ Clean failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--source-dir",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Source directory containing pyproject.toml",
)
@click.option(
    "--platform",
    "-p",
    multiple=True,
    type=click.Choice(["windows-x64", "linux-x64", "macos-arm64", "macos-x64", "all"]),
    help='Target platforms (can be specified multiple times). Use "all" for all supported platforms',
)
@click.option(
    "--python-version", default="3.11", help="Python version for dependency resolution"
)
@click.option(
    "--clean/--no-clean", default=True, help="Clean wheel directory before downloading"
)
@click.option(
    "--wheel-url",
    multiple=True,
    help="Additional wheel URLs to download (can be specified multiple times)",
)
def download(
    source_dir: Path,
    platform: List[str],
    python_version: str,
    clean: bool,
    wheel_url: List[str],
) -> None:
    """
    📦 Download Python wheels for specified platforms

    Downloads wheels without building the extension.
    """
    try:
        builder = ExtensionBuilder(source_dir=source_dir, python_version=python_version)

        # Handle platform selection
        if "all" in platform:
            if len(platform) > 1:
                console.print(
                    "[yellow]Warning: 'all' specified with other platforms. Using configured platforms.[/yellow]"
                )
            configured_platforms = builder.get_configured_platforms()
            if configured_platforms:
                console.print(
                    f"[blue]Downloading wheels for configured platforms: {', '.join(configured_platforms)}[/blue]"
                )
                platform = configured_platforms
            else:
                console.print(
                    "[blue]No platforms configured, using all supported platforms...[/blue]"
                )
                platform = ["windows-x64", "linux-x64", "macos-arm64", "macos-x64"]
        elif not platform:
            configured_platforms = builder.get_configured_platforms()
            if configured_platforms:
                console.print(
                    f"[blue]Using configured platforms: {', '.join(configured_platforms)}[/blue]"
                )
                platform = configured_platforms
            else:
                console.print(
                    "[yellow]No platforms configured, detecting current platform...[/yellow]"
                )
                platform = builder.detect_current_platform()
        else:
            # Validate specified platforms
            valid_platforms = {"windows-x64", "linux-x64", "macos-arm64", "macos-x64"}
            invalid_platforms = [p for p in platform if p not in valid_platforms]
            if invalid_platforms:
                console.print(
                    f"[bold red]❌ Invalid platforms:[/bold red] {', '.join(invalid_platforms)}"
                )
                console.print(
                    f"Valid platforms are: {', '.join(sorted(valid_platforms))}"
                )
                sys.exit(1)

        builder.download_wheels(
            platforms=platform,
            clean=clean,
            additional_urls=list(wheel_url) if wheel_url else None,
        )
        console.print("[bold green]✅ Wheels downloaded successfully![/bold green]")

    except ExtbpyError as e:
        console.print(f"[bold red]❌ Download failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--source-dir",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Source directory containing extension",
)
@click.option(
    "--url",
    "-u",
    multiple=True,
    required=True,
    help="Wheel URLs to download (can be specified multiple times)",
)
@click.option(
    "--clean/--no-clean", default=True, help="Clean wheel directory before downloading"
)
def download_urls(source_dir: Path, url: List[str], clean: bool) -> None:
    """
    🌐 Download wheels from specific URLs

    Downloads wheels directly from provided URLs without platform resolution.
    """
    try:
        builder = ExtensionBuilder(source_dir=source_dir)

        # Create wheels directory
        builder.wheels_dir.mkdir(parents=True, exist_ok=True)

        if clean:
            builder._clean_wheels_dir()

        console.print(f"[blue]Downloading {len(url)} wheels from URLs...[/blue]")

        # Download all URLs (treat as universal)
        builder._download_wheels_multithreaded(list(url), "universal")

        console.print("[bold green]✅ Wheels downloaded successfully![/bold green]")

    except ExtbpyError as e:
        console.print(f"[bold red]❌ Download failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--source-dir",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    default=Path.cwd(),
    help="Source directory containing extension",
)
def info(source_dir: Path) -> None:
    """
    📋 Show information about the extension project

    Displays project metadata, dependencies, and configuration.
    """
    try:
        builder = ExtensionBuilder(source_dir=source_dir)
        info_data = builder.get_project_info()

        console.print("[bold blue]📋 Project Information[/bold blue]")
        console.print(f"Name: [bold]{info_data.get('name', 'Unknown')}[/bold]")
        console.print(f"Version: [bold]{info_data.get('version', 'Unknown')}[/bold]")
        console.print(f"Description: {info_data.get('description', 'No description')}")

        # Show configured platforms
        configured_platforms = info_data.get("configured_platforms", [])
        if configured_platforms:
            console.print(
                f"\n[bold blue]🎯 Configured Platforms ({len(configured_platforms)}):[/bold blue]"
            )
            for platform in configured_platforms:
                console.print(f"  • {platform}")
        else:
            console.print(
                "\n[yellow]No platforms configured (will use current platform)[/yellow]"
            )

        deps = info_data.get("dependencies", [])
        if deps:
            console.print(f"\n[bold blue]📦 Dependencies ({len(deps)}):[/bold blue]")
            for dep in deps:
                console.print(f"  • {dep}")
        else:
            console.print("\n[yellow]No dependencies found[/yellow]")

    except ExtbpyError as e:
        console.print(f"[bold red]❌ Info failed:[/bold red] {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
