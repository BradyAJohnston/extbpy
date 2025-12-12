"""
Core builder functionality for extbpy.
"""

from __future__ import annotations

import json
import subprocess
import sys
import shutil
import logging
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import tomlkit
from urllib.parse import urlparse
from rich.progress import (
    Progress,
    TaskID,
    SpinnerColumn,
    TextColumn,
    BarColumn,
)

from .platforms import (
    get_platforms,
    detect_current_platform,
    match_wheel_to_platforms,
)
from .exceptions import (
    ConfigurationError,
    DependencyError,
    BuildError,
    BlenderError,
)

logger = logging.getLogger(__name__)


class ExtensionBuilder:
    """Main builder class for Blender extensions."""

    def __init__(
        self,
        source_dir: Path,
        output_dir: Path | None = None,
        python_version: str = "3.11",
        excluded_packages: set[str] | None = None,
    ):
        self.source_dir = Path(source_dir).resolve()
        self.output_dir = Path(output_dir or Path.cwd()).resolve()
        self.python_version = python_version
        self.excluded_packages = excluded_packages or {
            "pyarrow",
            "certifi",
            "charset_normalizer",
            "idna",
            "numpy",
            "requests",
            "urllib3",
        }

        # Validate source directory structure
        self._validate_source_dir()

        # Set up paths
        self.extension_dir = self._find_extension_dir()
        self.wheels_dir = self.extension_dir / "wheels"
        self.manifest_path = self.extension_dir / "blender_manifest.toml"
        self.pyproject_path = self.source_dir / "pyproject.toml"
        self.uv_lock_path = self.source_dir / "uv.lock"

        # Load project configuration
        self.project_config = self._load_project_config()
        self.lock_data = self._load_uv_lock() if self.uv_lock_path.exists() else None

    def _validate_source_dir(self) -> None:
        """Validate that source directory exists and has required structure."""
        if not self.source_dir.exists():
            raise ConfigurationError(
                f"Source directory does not exist: {self.source_dir}"
            )

        pyproject_path = self.source_dir / "pyproject.toml"
        if not pyproject_path.exists():
            raise ConfigurationError(f"No pyproject.toml found in {self.source_dir}")

    def _find_extension_dir(self) -> Path:
        """Find the extension directory within source directory."""
        # Look for directories with blender_manifest.toml
        for item in self.source_dir.iterdir():
            if item.is_dir():
                manifest_path = item / "blender_manifest.toml"
                if manifest_path.exists():
                    return item

        # Fallback: look for common extension directory names
        for name in ["extension", "addon", "warbler"]:
            candidate = self.source_dir / name
            if candidate.exists() and candidate.is_dir():
                return candidate

        raise ConfigurationError(
            f"No extension directory found in {self.source_dir}. "
            "Expected a directory containing blender_manifest.toml"
        )

    def _load_project_config(self) -> dict[str, Any]:
        """Load and validate project configuration."""
        try:
            with open(self.pyproject_path, "r", encoding="utf-8") as f:
                raw_config = tomlkit.parse(f.read())

            # Convert tomlkit document to regular dict to avoid type issues
            config = dict(raw_config)

            # Validate required sections
            if "project" not in config:
                raise ConfigurationError("No [project] section in pyproject.toml")

            # Convert all tomlkit objects to standard Python types
            config = json.loads(json.dumps(dict(config)))

            # Validate and fix project section
            project = config.get("project", {})
            if "dependencies" not in project:
                logger.warning("No dependencies found in pyproject.toml")
                project["dependencies"] = []
                config["project"] = project
            return config

        except FileNotFoundError:
            raise ConfigurationError(f"pyproject.toml not found: {self.pyproject_path}")
        except Exception as e:
            raise ConfigurationError(f"Error reading pyproject.toml: {e}")

    def _load_uv_lock(self) -> dict[str, Any]:
        """Load and parse uv.lock file."""
        try:
            with open(self.uv_lock_path, "r", encoding="utf-8") as f:
                raw_lock_data = tomlkit.parse(f.read())

            # Convert tomlkit document to regular dict using JSON serialization
            lock_data = json.loads(json.dumps(dict(raw_lock_data)))

            # Debug: log the structure we're getting
            logger.debug(f"Lock data type: {type(lock_data)}")
            logger.debug(f"Lock data keys: {list(lock_data.keys())}")

            # Count packages properly
            package_count = 0
            if "package" in lock_data:
                packages = lock_data.get("package", [])
                package_count = len(packages) if isinstance(packages, list) else 0
            else:
                # Check for direct list access
                for key, value in lock_data.items():
                    if (
                        isinstance(value, list)
                        and len(value) > 0
                        and isinstance(value[0], dict)
                        and "name" in value[0]
                    ):
                        logger.debug(f"Found potential package list under key: {key}")

            logger.debug(f"Loaded uv.lock with {package_count} packages")
            return lock_data
        except Exception as e:
            logger.warning(f"Could not load uv.lock: {e}")
            return {}

    def _get_all_dependencies_from_lock(self, package_name: str | None = None) -> set:
        """Get all transitive dependencies for a package from uv.lock.

        Args:
            package_name: The root package to start from. If None, uses project name.

        Returns:
            A set of all package names (including transitive dependencies)
        """
        if package_name is None:
            project_section = self.project_config.get("project", {})
            package_name = project_section.get("name", "")

        if not package_name:
            logger.warning("No package name provided and none found in project config")
            return set()

        # Build a dependency graph
        dep_graph = {}
        if self.lock_data:
            packages = self.lock_data.get("package", [])
            for package in packages:
                name = package.get("name", "")
                deps = package.get("dependencies", [])
                dep_names = [d.get("name", "") for d in deps if isinstance(d, dict)]
                dep_graph[name] = dep_names

        # BFS to get all transitive dependencies
        all_deps = set()
        to_visit = [package_name]
        visited = set()

        while to_visit:
            current = to_visit.pop(0)
            if current in visited:
                continue
            visited.add(current)

            if current in dep_graph:
                for dep in dep_graph[current]:
                    if dep not in visited:
                        all_deps.add(dep)
                        to_visit.append(dep)

        logger.debug(f"Resolved {len(all_deps)} dependencies for {package_name}")
        return all_deps

    def _get_wheel_urls_from_lock(self, platforms: list[str]) -> dict[str, list[str]]:
        """Extract wheel URLs from uv.lock for specified platforms."""
        if not self.lock_data:
            return {}

        wheel_urls: dict[str, list[str]] = {platform: [] for platform in platforms}

        # Get only the dependencies we need (not all packages in lock file)
        required_dependencies = self._get_all_dependencies_from_lock()

        # Filter out excluded packages
        if self.excluded_packages:
            excluded_count = len(required_dependencies & self.excluded_packages)
            required_dependencies = required_dependencies - self.excluded_packages
            if excluded_count > 0:
                logger.debug(
                    f"Excluded {excluded_count} packages already available in Blender"
                )

        packages = self.lock_data.get("package", [])

        logger.debug(f"Found {len(packages)} packages in uv.lock")
        logger.info(f"Resolving wheels for {len(required_dependencies)} dependencies")

        wheel_count = 0
        matched_wheels = 0

        for package in packages:
            package_name = package.get("name", "unknown")

            # Skip packages that are not in our required dependencies
            if package_name not in required_dependencies:
                continue

            source = package.get("source", {})
            # In uv.lock, registry packages have source = { registry = "..." }
            is_registry = "registry" in source

            if not is_registry:
                continue

            wheels = package.get("wheels", [])

            for wheel in wheels:
                wheel_url = wheel.get("url", "")
                # Extract filename from URL since there's no filename field
                filename = wheel_url.split("/")[-1] if wheel_url else ""
                wheel_count += 1

                # Use flexible platform matching
                matched_platforms = match_wheel_to_platforms(filename)

                # Add wheel to all matching platforms that we're building for
                for matched_platform in matched_platforms:
                    if matched_platform in platforms:
                        wheel_urls[matched_platform].append(wheel_url)
                        matched_wheels += 1

        logger.debug(
            f"Processed {wheel_count} total wheels, {matched_wheels} matched our platforms"
        )

        for platform in platforms:
            logger.debug(
                f"Platform {platform}: {len(wheel_urls[platform])} wheels found"
            )

        return wheel_urls

    def get_configured_platforms(self) -> list[str]:
        """Get platforms configured in pyproject.toml."""
        tool_config = self.project_config.get("tool", {})
        extbpy_config = tool_config.get("extbpy", {})
        platforms = extbpy_config.get("platforms", [])

        # Validate platforms
        valid_platforms = {"windows-x64", "linux-x64", "macos-arm64", "macos-x64"}
        invalid_platforms = [p for p in platforms if p not in valid_platforms]
        if invalid_platforms:
            raise ConfigurationError(
                f"Invalid platforms in pyproject.toml: {invalid_platforms}. "
                f"Valid platforms are: {', '.join(sorted(valid_platforms))}"
            )

        return platforms

    def get_project_info(self) -> dict[str, Any]:
        """Get project information for display."""
        project = self.project_config.get("project", {})
        configured_platforms = self.get_configured_platforms()

        return {
            "name": project.get("name", "Unknown"),
            "version": project.get("version", "Unknown"),
            "description": project.get("description", "No description"),
            "dependencies": project.get("dependencies", []),
            "configured_platforms": configured_platforms,
            "extension_dir": str(self.extension_dir),
            "wheels_dir": str(self.wheels_dir),
        }

    def detect_current_platform(self) -> list[str]:
        """Detect current platform."""
        return detect_current_platform()

    def _run_python_command(self, args: list[str]) -> None:
        """Run a Python command with proper error handling."""
        python_exe = sys.executable
        cmd = [python_exe] + args

        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, check=True, capture_output=True, text=True, cwd=self.source_dir
            )

            if result.stdout:
                logger.debug(f"Command output: {result.stdout}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"Exit code: {e.returncode}")
            logger.error(f"Stdout: {e.stdout}")
            logger.error(f"Stderr: {e.stderr}")
            raise DependencyError(f"Python command failed: {e.stderr or e.stdout}")

    def _ensure_tomlkit_available(self) -> None:
        """Ensure tomlkit is available, install if needed."""
        try:
            import tomlkit  # noqa: F401
        except ImportError:
            logger.info("Installing tomlkit...")
            self._run_python_command(["-m", "pip", "install", "tomlkit"])

    def download_wheels(
        self,
        platforms: list[str],
        clean: bool = True,
        ignore_platform_errors: bool = True,
        additional_urls: list[str] | None = None,
    ) -> list[str]:
        """Download wheels for specified platforms using uv.lock URLs and pooch."""
        self._ensure_tomlkit_available()

        if not self.lock_data and not additional_urls:
            # Fallback to pip-based approach if no uv.lock and no additional URLs
            return self._download_wheels_with_pip(
                platforms, clean, ignore_platform_errors
            )

        # Create wheels directory
        self.wheels_dir.mkdir(parents=True, exist_ok=True)

        if clean:
            self._clean_wheels_dir()

        logger.info(
            f"Downloading wheels from uv.lock for platforms: {', '.join(platforms)}"
        )

        # Get wheel URLs from uv.lock
        wheel_urls = (
            self._get_wheel_urls_from_lock(platforms)
            if self.lock_data
            else {platform: [] for platform in platforms}
        )

        # Add additional URLs to all platforms
        if additional_urls:
            logger.info(f"Adding {len(additional_urls)} additional wheel URLs")
            for platform in platforms:
                wheel_urls[platform].extend(additional_urls)

        # Collect all unique wheel URLs across all platforms to avoid duplicates
        all_wheel_urls = set()
        platform_wheel_counts = {}

        for platform in platforms:
            platform_urls = wheel_urls.get(platform, [])
            platform_wheel_counts[platform] = len(platform_urls)

            if not platform_urls:
                logger.warning(f"No wheels found in uv.lock for platform: {platform}")
            else:
                all_wheel_urls.update(platform_urls)

        # Check if we have any platforms with wheels
        platforms_with_wheels = [p for p in platforms if platform_wheel_counts[p] > 0]
        failed_platforms = [p for p in platforms if platform_wheel_counts[p] == 0]

        if not platforms_with_wheels:
            logger.error("No wheels found for any requested platforms")
        else:
            # Log summary of wheel counts
            total_needed = sum(platform_wheel_counts[p] for p in platforms_with_wheels)
            platform_summary = ", ".join(
                f"{p}:{platform_wheel_counts[p]}" for p in platforms_with_wheels
            )
            logger.info(
                f"Wheels needed: {platform_summary} (total: {total_needed}, unique: {len(all_wheel_urls)})"
            )

            # Download all unique wheels once
            try:
                self._download_wheels_multithreaded(
                    list(all_wheel_urls), f"{len(platforms_with_wheels)} platforms"
                )
                successful_platforms = platforms_with_wheels
            except Exception as e:
                failed_platforms.extend(platforms_with_wheels)
                logger.error(f"❌ Failed to download wheels: {e}")

        if failed_platforms and not successful_platforms:
            raise DependencyError(
                f"Failed to download wheels for all platforms: {', '.join(failed_platforms)}"
            )
        elif failed_platforms:
            if ignore_platform_errors:
                logger.warning(
                    f"Some platforms failed: {', '.join(failed_platforms)}. Continuing with: {', '.join(successful_platforms)}"
                )
            else:
                raise DependencyError(
                    f"Failed to download wheels for platforms: {', '.join(failed_platforms)}"
                )

        return successful_platforms

    def _download_wheels_multithreaded(
        self, urls: list[str], platform: str, max_workers: int = 8
    ) -> None:
        """Download wheels using multithreaded urllib from provided URLs with progress bar."""
        if not urls:
            return

        def download_wheel(
            url: str, task_id: TaskID, progress: Progress
        ) -> tuple[str, bool, str]:
            """Download a single wheel file. Returns (filename, success, message)."""
            try:
                # Extract filename from URL
                parsed_url = urlparse(url)
                filename = Path(parsed_url.path).name

                if not filename.endswith(".whl"):
                    progress.update(task_id, advance=1)
                    return (filename, False, "Not a wheel file")

                output_path = self.wheels_dir / filename

                # Skip if file already exists
                if output_path.exists():
                    progress.update(task_id, advance=1)
                    return (filename, True, "Already exists")

                # Download using urllib
                urllib.request.urlretrieve(url, output_path)
                progress.update(task_id, advance=1)
                return (filename, True, "Downloaded successfully")

            except Exception as e:
                progress.update(task_id, advance=1)
                return (filename if "filename" in locals() else url, False, str(e))

        # Download wheels in parallel with progress bar
        success_count = 0
        failed_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=None,  # Use default console
        ) as progress:
            # Create progress task
            if "platforms" in platform:
                description = (
                    f"[cyan]Downloading {len(urls)} unique wheels for {platform}[/cyan]"
                )
            else:
                description = f"[cyan]Downloading wheels for {platform}[/cyan]"

            task_id = progress.add_task(description, total=len(urls))

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all download tasks
                future_to_url = {
                    executor.submit(download_wheel, url, task_id, progress): url
                    for url in urls
                }

                # Process completed downloads
                for future in as_completed(future_to_url):
                    filename, success, message = future.result()
                    if success:
                        if message != "Already exists":
                            logger.debug(f"✓ {filename}")
                        success_count += 1
                    else:
                        logger.error(f"✗ {filename}: {message}")
                        failed_count += 1

        if failed_count > 0:
            logger.warning(
                f"Download completed: {success_count} succeeded, {failed_count} failed"
            )
            raise DependencyError(f"{failed_count} wheels failed to download")
        else:
            if "platforms" in platform:
                logger.info(
                    f"✅ Successfully downloaded {success_count} unique wheels for {platform}"
                )
            else:
                logger.info(
                    f"✅ Successfully downloaded {success_count} wheels for {platform}"
                )

    def _download_wheels_with_pip(
        self,
        platforms: list[str],
        clean: bool = True,
        ignore_platform_errors: bool = True,
    ) -> list[str]:
        """Fallback method: download wheels using pip (original implementation)."""
        logger.info("No uv.lock found, falling back to pip download...")

        platform_objects = get_platforms(platforms)
        project_section = self.project_config.get("project", {})
        dependencies = project_section.get("dependencies", [])

        if not dependencies:
            logger.warning("No dependencies to download")
            return []

        # Create wheels directory
        self.wheels_dir.mkdir(parents=True, exist_ok=True)

        if clean:
            self._clean_wheels_dir()

        logger.info(f"Downloading wheels for platforms: {', '.join(platforms)}")
        logger.info(f"Dependencies: {', '.join(dependencies)}")

        failed_platforms = []
        successful_platforms = []

        for platform_obj in platform_objects:
            logger.info(f"Downloading wheels for {platform_obj.name}...")

            cmd = [
                "-m",
                "pip",
                "download",
                *dependencies,
                "--dest",
                str(self.wheels_dir),
                "--only-binary=:all:",
                f"--python-version={self.python_version}",
                f"--platform={platform_obj.pypi_suffix}",
            ]

            try:
                self._run_python_command(cmd)
                successful_platforms.append(platform_obj.name)
                logger.info(
                    f"✅ Successfully downloaded wheels for {platform_obj.name}"
                )
            except DependencyError as e:
                failed_platforms.append(platform_obj.name)
                logger.error(
                    f"❌ Failed to download wheels for {platform_obj.name}: {e}"
                )

        if failed_platforms and not successful_platforms:
            raise DependencyError(
                f"Failed to download wheels for all platforms: {', '.join(failed_platforms)}"
            )
        elif failed_platforms:
            if ignore_platform_errors:
                logger.warning(
                    f"Some platforms failed: {', '.join(failed_platforms)}. Continuing with: {', '.join(successful_platforms)}"
                )
            else:
                raise DependencyError(
                    f"Failed to download wheels for platforms: {', '.join(failed_platforms)}"
                )

        return successful_platforms

    def _clean_wheels_dir(self) -> None:
        """Clean the wheels directory."""
        if self.wheels_dir.exists():
            shutil.rmtree(self.wheels_dir)
        self.wheels_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Cleaned wheels directory: {self.wheels_dir}")

    def _filter_wheels(self) -> list[Path]:
        """Filter out excluded packages from wheels."""
        wheel_files = list(self.wheels_dir.glob("*.whl"))
        wheel_files.sort()

        to_keep = []
        to_remove = []

        for whl_path in wheel_files:
            whl_name = whl_path.name.lower()
            should_exclude = any(
                pkg.lower() in whl_name for pkg in self.excluded_packages
            )

            if should_exclude:
                to_remove.append(whl_path)
                logger.debug(f"Excluding wheel: {whl_path.name}")
            else:
                to_keep.append(whl_path)

        # Remove excluded wheels
        for whl_path in to_remove:
            whl_path.unlink()
            logger.debug(f"Removed excluded wheel: {whl_path.name}")

        if len(to_remove) > 0:
            logger.info(
                f"Excluded {len(to_remove)} wheels already available in Blender, keeping {len(to_keep)}"
            )
        else:
            logger.debug(f"Keeping all {len(to_keep)} wheels")
        return to_keep

    def update_manifest(self, platforms: list[str]) -> None:
        """Update the Blender manifest with wheels and platform info."""
        platform_objects = get_platforms(platforms)
        wheel_files = self._filter_wheels()

        # Load existing manifest or create new one
        if self.manifest_path.exists():
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                manifest = tomlkit.parse(f.read())
        else:
            manifest = tomlkit.document()
            logger.warning(f"Creating new manifest at {self.manifest_path}")

        # Update wheels list
        wheel_paths = [f"./wheels/{whl.name}" for whl in wheel_files]
        manifest["wheels"] = wheel_paths

        # Update platforms
        platform_names = [p.metadata for p in platform_objects]
        manifest["platforms"] = platform_names

        logger.debug(
            f"Updated manifest with {len(wheel_paths)} wheels for platforms: {', '.join(platform_names)}"
        )

        # Write updated manifest with nice formatting
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            content = tomlkit.dumps(manifest)
            # Format arrays nicely
            content = (
                content.replace('["', '[\n\t"')
                .replace('", "', '",\n\t"')
                .replace('"]', '",\n]')
                .replace("\\\\", "/")
            )
            f.write(content)

    def clean_files(self, patterns: list[str] | None = None) -> int:
        """Clean temporary files from extension directory."""
        if patterns is None:
            patterns = [".blend1", ".MNSession"]

        cleaned_count = 0

        for pattern in patterns:
            pattern_path = f"**/*{pattern}"
            for file_path in self.extension_dir.rglob(pattern_path):
                if file_path.is_file():
                    file_path.unlink()
                    logger.debug(f"Removed: {file_path}")
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.debug(f"Cleaned {cleaned_count} temporary files")
        return cleaned_count

    def _find_blender_executable(self) -> str:
        """Find Blender executable."""
        try:
            import bpy  # type: ignore

            return bpy.app.binary_path
        except ImportError:
            # Try to find Blender in PATH
            blender_names = ["blender", "blender.exe"]
            for name in blender_names:
                blender_path = shutil.which(name)
                if blender_path:
                    return blender_path

            raise BlenderError(
                "Blender executable not found. Please ensure Blender is installed "
                "and available in PATH, or run this tool from within Blender."
            )

    def build_extension(self, split_platforms: bool = True) -> None:
        """Build the Blender extension."""
        # Clean temporary files first
        self.clean_files()

        blender_exe = self._find_blender_executable()

        cmd = [
            blender_exe,
            "--command",
            "extension",
            "build",
            "--source-dir",
            str(self.extension_dir),
            "--output-dir",
            str(self.output_dir),
        ]

        if split_platforms:
            cmd.append("--split-platforms")

        logger.info(f"Building extension with command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, check=True, capture_output=True, text=True, cwd=self.source_dir
            )

            if result.stdout:
                logger.info(f"Build output: {result.stdout}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Build failed: {e.stderr}")
            raise BuildError(f"Extension build failed: {e.stderr or 'Unknown error'}")

    def build(
        self,
        platforms: list[str],
        clean: bool = True,
        split_platforms: bool = True,
        ignore_platform_errors: bool = True,
        additional_urls: list[str] | None = None,
    ) -> None:
        """Complete build process: download wheels, update manifest, and build extension."""
        logger.info(f"Starting build for platforms: {', '.join(platforms)}")

        try:
            # Download wheels for all platforms
            successful_platforms = self.download_wheels(
                platforms,
                clean=clean,
                ignore_platform_errors=ignore_platform_errors,
                additional_urls=additional_urls,
            )

            if not successful_platforms:
                raise BuildError("No platforms were successfully processed")

            # Update manifest with wheels and platform info for successful platforms only
            self.update_manifest(successful_platforms)

            # Build the extension
            self.build_extension(split_platforms=split_platforms)

            # Look for created extension files
            extension_files = list(self.output_dir.glob("*.zip"))
            if extension_files:
                logger.info(f"✅ Built {len(extension_files)} extension packages:")
                for ext_file in extension_files:
                    size_mb = ext_file.stat().st_size / (1024 * 1024)
                    logger.info(f"  📦 {ext_file.name} ({size_mb:.1f} MB)")
            else:
                logger.info(
                    f"Build completed successfully for platforms: {', '.join(successful_platforms)}"
                )

        except Exception as e:
            logger.error(f"Build failed: {e}")
            raise
