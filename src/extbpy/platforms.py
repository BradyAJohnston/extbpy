"""
Platform definitions and utilities for extbpy.
"""

import platform
from dataclasses import dataclass
from typing import List

from .exceptions import PlatformError


@dataclass
class Platform:
    """Platform configuration for building extensions."""

    name: str
    pypi_suffix: str
    metadata: str

    def __str__(self) -> str:
        return self.name


# Supported platforms with pattern lists for flexible matching
PLATFORMS = {
    "windows-x64": Platform(
        name="windows-x64", pypi_suffix="win_amd64", metadata="windows-x64"
    ),
    "linux-x64": Platform(
        name="linux-x64", pypi_suffix="manylinux2014_x86_64", metadata="linux-x64"
    ),
    "macos-arm64": Platform(
        name="macos-arm64", pypi_suffix="macosx_12_0_arm64", metadata="macos-arm64"
    ),
    "macos-x64": Platform(
        name="macos-x64", pypi_suffix="macosx_10_16_x86_64", metadata="macos-x64"
    ),
}

# Platform patterns for flexible wheel filename matching
PLATFORM_PATTERNS = {
    "windows-x64": ["win_amd64"],
    "linux-x64": ["manylinux", "x86_64"],  # Must contain both parts
    "macos-arm64": ["macosx", "arm64"],  # Must contain both parts
    "macos-x64": ["macosx", "x86_64"],  # Must contain both parts
}


def get_platform(name: str) -> Platform:
    """Get platform by name."""
    if name not in PLATFORMS:
        available = ", ".join(PLATFORMS.keys())
        raise PlatformError(f"Unsupported platform '{name}'. Available: {available}")
    return PLATFORMS[name]


def get_platforms(names: List[str]) -> List[Platform]:
    """Get multiple platforms by name."""
    return [get_platform(name) for name in names]


def detect_current_platform() -> List[str]:
    """Detect the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":  # macOS
        if machine in ("arm64", "aarch64"):
            return ["macos-arm64"]
        else:
            return ["macos-x64"]
    elif system == "linux":
        if machine in ("x86_64", "amd64"):
            return ["linux-x64"]
        else:
            raise PlatformError(f"Unsupported Linux architecture: {machine}")
    elif system == "windows":
        if machine in ("x86_64", "amd64"):
            return ["windows-x64"]
        else:
            raise PlatformError(f"Unsupported Windows architecture: {machine}")
    else:
        raise PlatformError(f"Unsupported operating system: {system}")


def list_available_platforms() -> List[str]:
    """List all available platform names."""
    return list(PLATFORMS.keys())


def match_wheel_to_platforms(filename: str) -> List[str]:
    """Match a wheel filename to supported platforms using Blender's matching logic."""
    matched_platforms = []

    # Skip PyPy wheels - Blender doesn't support them
    if "-pp3" in filename or "pypy" in filename:
        return []

    # Check universal wheels first
    if any(pattern in filename for pattern in ["py3-none-any", "py2.py3-none-any"]):
        return list(PLATFORMS.keys())  # Universal wheels work on all platforms

    # Check each platform using Blender's platform matching logic from bl_extension_ops.py
    for platform_name, platform_obj in PLATFORMS.items():
        matched = False

        # For macOS, match any compatible macOS version with the same architecture
        if "macos" in platform_obj.metadata:
            if "universal2" in filename and "macosx" in filename:
                # Universal2 wheels work for both arm64 and x64 on macOS
                matched = True
            elif "arm64" in platform_obj.metadata and (
                "macosx" in filename and "arm64" in filename
            ):
                matched = True
            elif "x64" in platform_obj.metadata and (
                "macosx" in filename and "x86_64" in filename
            ):
                matched = True

        # For Linux, match any manylinux wheel with the correct architecture
        # Blender accepts manylinux1, manylinux2010, manylinux2014, manylinux_2_XX, etc.
        elif "linux" in platform_obj.metadata:
            # Extract architecture from pypi_suffix (e.g., "manylinux2014_x86_64" -> "x86_64")
            arch = platform_obj.pypi_suffix.split("_", 1)[
                -1
            ]  # Get everything after first underscore
            if "manylinux" in filename and ("_" + arch in filename):
                matched = True

        # For Windows, use exact suffix matching
        elif (
            "windows" in platform_obj.metadata and platform_obj.pypi_suffix in filename
        ):
            matched = True

        if matched:
            matched_platforms.append(platform_name)

    return matched_platforms
