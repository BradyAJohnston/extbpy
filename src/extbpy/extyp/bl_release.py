"""Facts about released Blender versions that affect wheel selection.

Keyed by the ``MAJOR.MINOR`` release series. ``min_glibc_version``,
``min_macos_version`` and ``exclude_packages`` can be overridden per project
in ``[tool.extbpy]``, so this table only has to be approximately right.

References:
    - https://developer.blender.org/docs/release_notes/compatibility/
    - https://projects.blender.org/blender/blender/src/branch/main/lib
"""

from __future__ import annotations

import dataclasses
import functools

from ..exceptions import ConfigurationError
from .bl_platform import BLPlatform

_PLATFORMS_4X = frozenset(
    {
        BLPlatform.linux_x64,
        BLPlatform.macos_x64,
        BLPlatform.macos_arm64,
        BLPlatform.windows_x64,
        BLPlatform.windows_arm64,
    }
)
_PLATFORMS_5X = _PLATFORMS_4X - {BLPlatform.macos_x64}

# Packages Blender ships inside its own site-packages. Wheels for these are
# never bundled, since Blender's copies take precedence anyway.
_VENDORED = frozenset(
    {
        "autopep8",
        "certifi",
        "charset-normalizer",
        "cython",
        "idna",
        "numpy",
        "pip",
        "pycodestyle",
        "requests",
        "setuptools",
        "urllib3",
        "zstandard",
    }
)


@dataclasses.dataclass(frozen=True)
class BLRelease:
    """A Blender release series (``MAJOR.MINOR``)."""

    version: tuple[int, int]
    python_version: tuple[int, int]
    platforms: frozenset[BLPlatform]
    min_glibc_version: tuple[int, int]
    min_macos_version: tuple[int, int]
    vendored_packages: frozenset[str]

    @property
    def pretty_version(self) -> str:
        return f"{self.version[0]}.{self.version[1]}"


_RELEASES: tuple[BLRelease, ...] = (
    BLRelease((4, 2), (3, 11), _PLATFORMS_4X, (2, 28), (11, 0), _VENDORED),
    BLRelease((4, 3), (3, 11), _PLATFORMS_4X, (2, 28), (11, 0), _VENDORED),
    BLRelease((4, 4), (3, 11), _PLATFORMS_4X, (2, 28), (12, 0), _VENDORED),
    BLRelease((4, 5), (3, 11), _PLATFORMS_4X, (2, 28), (12, 0), _VENDORED),
    BLRelease((5, 0), (3, 11), _PLATFORMS_5X, (2, 28), (12, 0), _VENDORED),
    BLRelease((5, 1), (3, 13), _PLATFORMS_5X, (2, 28), (12, 0), _VENDORED),
    BLRelease((5, 2), (3, 13), _PLATFORMS_5X, (2, 28), (12, 0), _VENDORED),
)
_BY_VERSION = {r.version: r for r in _RELEASES}


def parse_blender_version(value: str) -> tuple[int, int, int]:
    """Parse ``"5.2.0"`` into ``(5, 2, 0)``."""
    parts = value.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ConfigurationError(
            f"Blender version must look like 'MAJOR.MINOR.PATCH', got '{value}'"
        )
    return (int(parts[0]), int(parts[1]), int(parts[2]))


@functools.cache
def release_for(blender_version_min: str) -> BLRelease:
    """The release series ``blender_version_min`` belongs to.

    Versions newer than the table are treated like the latest known release.
    """
    major, minor, _ = parse_blender_version(blender_version_min)
    key = (major, minor)
    if key in _BY_VERSION:
        return _BY_VERSION[key]
    if key < _RELEASES[0].version:
        raise ConfigurationError(
            f"Blender {major}.{minor} predates the extension system; "
            f"blender_version_min must be at least {_RELEASES[0].pretty_version}.0"
        )
    return dataclasses.replace(_RELEASES[-1], version=key)
