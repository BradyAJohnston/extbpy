"""Tests for platform functionality."""

import pytest
from extbpy.platforms import (
    get_platforms,
    detect_current_platform,
    match_wheel_to_platforms,
    PLATFORMS,
)
from extbpy.exceptions import PlatformError


def test_get_platforms():
    """Test platform retrieval."""
    platforms = get_platforms(["windows-x64", "linux-x64"])
    assert len(platforms) == 2
    assert platforms[0].name == "windows-x64"
    assert platforms[1].name == "linux-x64"


def test_get_platforms_invalid():
    """Test invalid platform handling."""
    with pytest.raises(PlatformError, match="Unsupported platform"):
        get_platforms(["invalid-platform"])


def test_detect_current_platform():
    """Test current platform detection."""
    current = detect_current_platform()
    assert len(current) == 1
    assert current[0] in PLATFORMS.keys()


def test_match_wheel_to_platforms():
    """Test wheel filename matching."""
    # Universal wheel
    universal = match_wheel_to_platforms("somepackage-1.0-py3-none-any.whl")
    assert len(universal) == 4
    assert set(universal) == set(PLATFORMS.keys())

    # Windows wheel
    windows = match_wheel_to_platforms("somepackage-1.0-py3-none-win_amd64.whl")
    assert "windows-x64" in windows

    # Linux wheel (manylinux format)
    linux = match_wheel_to_platforms(
        "somepackage-1.0-py3-none-manylinux2014_x86_64.whl"
    )
    assert "linux-x64" in linux

    # macOS Intel wheel
    macos_intel = match_wheel_to_platforms(
        "somepackage-1.0-py3-none-macosx_10_15_x86_64.whl"
    )
    assert "macos-x64" in macos_intel

    # macOS ARM wheel
    macos_arm = match_wheel_to_platforms(
        "somepackage-1.0-py3-none-macosx_11_0_arm64.whl"
    )
    assert "macos-arm64" in macos_arm

    # Universal2 wheel (should match both macOS platforms)
    macos_universal = match_wheel_to_platforms(
        "somepackage-1.0-py3-none-macosx_10_15_universal2.whl"
    )
    assert "macos-x64" in macos_universal
    assert "macos-arm64" in macos_universal


def test_platforms_structure():
    """Test that all platforms have required structure."""
    for platform_name, platform in PLATFORMS.items():
        assert hasattr(platform, "name")
        assert hasattr(platform, "pypi_suffix")
        assert hasattr(platform, "metadata")
        assert platform.name == platform_name
        assert isinstance(platform.metadata, str)
        assert isinstance(platform.pypi_suffix, str)
