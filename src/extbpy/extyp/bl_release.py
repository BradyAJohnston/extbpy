"""Facts about released Blender versions that affect wheel selection.

Everything an extension build needs to know about its target Blender is keyed
by the ``MAJOR.MINOR`` release series. Values here can be overridden per
project in ``[tool.extbpy]`` (``min_glibc_version``, ``min_macos_version``,
``exclude_packages``), so the table only has to be *approximately* right to be
useful, and *exactly* right to be convenient.

References:
    - https://developer.blender.org/docs/release_notes/compatibility/
    - https://projects.blender.org/blender/blender/src/branch/main/lib
"""

from __future__ import annotations

import dataclasses
import functools

from ..exceptions import ConfigurationError
from .bl_platform import BLPlatform

_ALL_PLATFORMS_INCL_INTEL_MAC = frozenset(
    {
        BLPlatform.linux_x64,
        BLPlatform.macos_x64,
        BLPlatform.macos_arm64,
        BLPlatform.windows_x64,
        BLPlatform.windows_arm64,
    }
)
_ALL_PLATFORMS_5X = frozenset(
    {
        BLPlatform.linux_x64,
        BLPlatform.macos_arm64,
        BLPlatform.windows_x64,
        BLPlatform.windows_arm64,
    }
)

# Packages Blender ships inside its own site-packages. Wheels for these are
# never bundled, since Blender's copies take precedence anyway.
_VENDORED_311 = frozenset(
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
_VENDORED_313 = _VENDORED_311


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

    @property
    def python_tag(self) -> str:
        """CPython interpreter tag, e.g. ``cp311``."""
        return f"cp{self.python_version[0]}{self.python_version[1]}"


_RELEASES: tuple[BLRelease, ...] = (
    BLRelease(
        (4, 2), (3, 11), _ALL_PLATFORMS_INCL_INTEL_MAC, (2, 28), (11, 0), _VENDORED_311
    ),
    BLRelease(
        (4, 3), (3, 11), _ALL_PLATFORMS_INCL_INTEL_MAC, (2, 28), (11, 0), _VENDORED_311
    ),
    BLRelease(
        (4, 4), (3, 11), _ALL_PLATFORMS_INCL_INTEL_MAC, (2, 28), (12, 0), _VENDORED_311
    ),
    BLRelease(
        (4, 5), (3, 11), _ALL_PLATFORMS_INCL_INTEL_MAC, (2, 28), (12, 0), _VENDORED_311
    ),
    BLRelease((5, 0), (3, 11), _ALL_PLATFORMS_5X, (2, 28), (12, 0), _VENDORED_311),
    BLRelease((5, 1), (3, 13), _ALL_PLATFORMS_5X, (2, 28), (12, 0), _VENDORED_313),
    BLRelease((5, 2), (3, 13), _ALL_PLATFORMS_5X, (2, 28), (12, 0), _VENDORED_313),
)

RELEASES: dict[tuple[int, int], BLRelease] = {r.version: r for r in _RELEASES}
LATEST_RELEASE: BLRelease = _RELEASES[-1]


def parse_blender_version(value: str) -> tuple[int, int, int]:
    """Parse ``"5.2.0"`` into ``(5, 2, 0)``."""
    parts = value.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ConfigurationError(
            f"Blender version must look like 'MAJOR.MINOR.PATCH', got '{value}'"
        )
    return (int(parts[0]), int(parts[1]), int(parts[2]))


@functools.lru_cache(maxsize=None)
def release_for(blender_version_min: str) -> BLRelease:
    """The release series that ``blender_version_min`` belongs to.

    Versions newer than the table are treated like the latest known release,
    with a note that the facts may be out of date.
    """
    major, minor, _ = parse_blender_version(blender_version_min)
    key = (major, minor)
    if key in RELEASES:
        return RELEASES[key]
    if key < _RELEASES[0].version:
        raise ConfigurationError(
            f"Blender {major}.{minor} predates the extension system; "
            f"blender_version_min must be at least {_RELEASES[0].pretty_version}.0"
        )
    return dataclasses.replace(LATEST_RELEASE, version=key)
