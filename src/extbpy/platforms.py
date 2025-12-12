"""
Platform definitions and utilities for extbpy.
"""

import platform
import sys
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

# Supported platforms
PLATFORMS = {
    'windows-x64': Platform(
        name='windows-x64',
        pypi_suffix='win_amd64', 
        metadata='windows-x64'
    ),
    'linux-x64': Platform(
        name='linux-x64',
        pypi_suffix='manylinux2014_x86_64',
        metadata='linux-x64'
    ),
    'macos-arm64': Platform(
        name='macos-arm64',
        pypi_suffix='macosx_12_0_arm64',
        metadata='macos-arm64'
    ),
    'macos-x64': Platform(
        name='macos-x64',
        pypi_suffix='macosx_10_16_x86_64',
        metadata='macos-x64'
    ),
}

def get_platform(name: str) -> Platform:
    """Get platform by name."""
    if name not in PLATFORMS:
        available = ', '.join(PLATFORMS.keys())
        raise PlatformError(f"Unsupported platform '{name}'. Available: {available}")
    return PLATFORMS[name]

def get_platforms(names: List[str]) -> List[Platform]:
    """Get multiple platforms by name."""
    return [get_platform(name) for name in names]

def detect_current_platform() -> List[str]:
    """Detect the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == 'darwin':  # macOS
        if machine in ('arm64', 'aarch64'):
            return ['macos-arm64']
        else:
            return ['macos-x64']
    elif system == 'linux':
        if machine in ('x86_64', 'amd64'):
            return ['linux-x64']
        else:
            raise PlatformError(f"Unsupported Linux architecture: {machine}")
    elif system == 'windows':
        if machine in ('x86_64', 'amd64'):
            return ['windows-x64']
        else:
            raise PlatformError(f"Unsupported Windows architecture: {machine}")
    else:
        raise PlatformError(f"Unsupported operating system: {system}")

def list_available_platforms() -> List[str]:
    """List all available platform names."""
    return list(PLATFORMS.keys())