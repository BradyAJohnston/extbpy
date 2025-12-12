"""
Utility functions for extbpy.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Any

from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def validate_python_version(min_version: str = "3.11") -> bool:
    """Validate that current Python version meets minimum requirements."""
    from packaging import version

    current = version.parse(f"{sys.version_info.major}.{sys.version_info.minor}")
    minimum = version.parse(min_version)

    return current >= minimum


def find_project_root(start_path: Path | None = None) -> Path | None:
    """Find the project root by looking for pyproject.toml."""
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    # Look up the directory tree for pyproject.toml
    for parent in [current] + list(current.parents):
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            return parent

    return None


def ensure_directory(path: Path) -> None:
    """Ensure a directory exists, creating it if necessary."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created directory: {path}")
    except OSError as e:
        raise ConfigurationError(f"Failed to create directory {path}: {e}")


def safe_remove_file(path: Path) -> bool:
    """Safely remove a file, returning True if successful."""
    try:
        if path.exists():
            path.unlink()
            logger.debug(f"Removed file: {path}")
            return True
        return False
    except OSError as e:
        logger.warning(f"Failed to remove file {path}: {e}")
        return False


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0B"

    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    size_float = float(size_bytes)

    while size_float >= 1024.0 and i < len(size_names) - 1:
        size_float = size_float / 1024.0
        i += 1

    return f"{size_float:.1f}{size_names[i]}"


def get_wheel_info(wheel_path: Path) -> dict[str, Any]:
    """Extract basic information from a wheel filename."""
    name = wheel_path.name
    parts = name.replace(".whl", "").split("-")

    if len(parts) < 5:
        return {"name": name, "version": "unknown", "platform": "unknown"}

    package_name = parts[0]
    version = parts[1]
    # Platform info is typically in the last few parts
    platform_parts = parts[-3:]
    platform = "-".join(platform_parts)

    return {
        "name": package_name,
        "version": version,
        "platform": platform,
        "full_name": name,
        "size": wheel_path.stat().st_size if wheel_path.exists() else 0,
    }
