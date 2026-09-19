"""Blender platform identifiers and their mapping onto Python wheel tags.

The values of :class:`BLPlatform` are exactly the strings accepted by the
``platforms`` field of ``blender_manifest.toml``.
"""

from __future__ import annotations

import enum
import platform as _platform

from ..exceptions import PlatformError


class BLPlatform(enum.StrEnum):
    """An operating system / CPU architecture pair supported by Blender."""

    linux_x64 = "linux-x64"
    linux_arm64 = "linux-arm64"
    macos_x64 = "macos-x64"
    macos_arm64 = "macos-arm64"
    windows_x64 = "windows-x64"
    windows_arm64 = "windows-arm64"

    # ------------------------------------------------------------------
    # OS classification
    # ------------------------------------------------------------------
    @property
    def is_linux(self) -> bool:
        return self in (BLPlatform.linux_x64, BLPlatform.linux_arm64)

    @property
    def is_macos(self) -> bool:
        return self in (BLPlatform.macos_x64, BLPlatform.macos_arm64)

    @property
    def is_windows(self) -> bool:
        return self in (BLPlatform.windows_x64, BLPlatform.windows_arm64)

    # ------------------------------------------------------------------
    # Wheel platform tags
    # ------------------------------------------------------------------
    @property
    def wheel_tag_prefix(self) -> str:
        """Prefix of wheel platform tags that can run on this platform."""
        if self.is_linux:
            return "manylinux_"
        if self.is_macos:
            return "macosx_"
        return "win"

    @property
    def wheel_arches(self) -> frozenset[str]:
        """Wheel platform tag suffixes (CPU architectures) usable on this platform."""
        return {
            BLPlatform.linux_x64: frozenset({"x86_64"}),
            BLPlatform.linux_arm64: frozenset({"aarch64"}),
            BLPlatform.macos_x64: frozenset(
                {"x86_64", "universal2", "universal", "intel", "fat3", "fat64"}
            ),
            BLPlatform.macos_arm64: frozenset({"arm64", "universal2"}),
            BLPlatform.windows_x64: frozenset({"amd64"}),
            BLPlatform.windows_arm64: frozenset({"arm64"}),
        }[self]

    # ------------------------------------------------------------------
    # PEP 508 marker environment
    # ------------------------------------------------------------------
    @property
    def marker_os_name(self) -> str:
        return "nt" if self.is_windows else "posix"

    @property
    def marker_sys_platform(self) -> str:
        if self.is_linux:
            return "linux"
        if self.is_macos:
            return "darwin"
        return "win32"

    @property
    def marker_platform_system(self) -> str:
        if self.is_linux:
            return "Linux"
        if self.is_macos:
            return "Darwin"
        return "Windows"

    @property
    def marker_platform_machines(self) -> frozenset[str]:
        """Possible values of ``platform.machine()`` on this platform."""
        return {
            BLPlatform.linux_x64: frozenset({"x86_64"}),
            BLPlatform.linux_arm64: frozenset({"aarch64", "arm64"}),
            BLPlatform.macos_x64: frozenset({"x86_64"}),
            BLPlatform.macos_arm64: frozenset({"arm64"}),
            BLPlatform.windows_x64: frozenset({"AMD64"}),
            BLPlatform.windows_arm64: frozenset({"ARM64"}),
        }[self]

    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------
    @property
    def zip_suffix(self) -> str:
        """Suffix Blender uses in split-platform zip filenames (``linux_x64``)."""
        return self.value.replace("-", "_")

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def parse(cls, value: str) -> BLPlatform:
        try:
            return cls(value)
        except ValueError:
            valid = ", ".join(p.value for p in cls)
            raise PlatformError(
                f"Unsupported platform '{value}'. Valid platforms: {valid}"
            ) from None

    @classmethod
    def detect(cls) -> BLPlatform:
        """Detect the platform this process is running on."""
        system = _platform.system().lower()
        machine = _platform.machine().lower()
        is_arm = machine.startswith(("aarch64", "arm"))
        is_x64 = machine in ("x86_64", "amd64")

        if system == "linux":
            if is_x64:
                return cls.linux_x64
            if is_arm:
                return cls.linux_arm64
        elif system == "darwin":
            if is_x64:
                return cls.macos_x64
            if is_arm:
                return cls.macos_arm64
        elif system == "windows":
            if is_x64:
                return cls.windows_x64
            if is_arm:
                return cls.windows_arm64
        raise PlatformError(
            f"Could not map local platform to Blender: {system}/{machine}"
        )
