"""A remote wheel and its compatibility with a Blender platform."""

from __future__ import annotations

import functools
import hashlib
import re
from pathlib import Path

import packaging.tags
import packaging.utils
import packaging.version
import pydantic

from ..extyp import BLPlatform

_LEGACY_MANYLINUX = {
    "manylinux1": (2, 5),
    "manylinux2010": (2, 12),
    "manylinux2014": (2, 17),
}
_RE_MANYLINUX = re.compile(r"^manylinux_(\d+)_(\d+)_(.+)$")
_RE_MACOS = re.compile(r"^macosx_(\d+)_(\d+)_(.+)$")


def normalize_platform_tag(tag: str) -> str:
    """Rewrite legacy ``manylinuxN`` tags into their PEP 600 form."""
    for legacy, (major, minor) in _LEGACY_MANYLINUX.items():
        prefix = legacy + "_"
        if tag.startswith(prefix):
            return f"manylinux_{major}_{minor}_{tag[len(prefix) :]}"
    return tag


class Wheel(pydantic.BaseModel, frozen=True):
    """A wheel as recorded in ``uv.lock``."""

    url: str
    hash: str | None = None
    size: int | None = None

    # ------------------------------------------------------------------
    # Filename parsing
    # ------------------------------------------------------------------
    @functools.cached_property
    def filename(self) -> str:
        name = self.url.rsplit("/", 1)[-1]
        if not name.endswith(".whl"):
            raise ValueError(f"URL does not point at a wheel: {self.url}")
        return name

    @functools.cached_property
    def _parsed(
        self,
    ) -> tuple[
        packaging.utils.NormalizedName,
        packaging.version.Version,
        tuple[()] | tuple[int, str],
        frozenset[packaging.tags.Tag],
    ]:
        return packaging.utils.parse_wheel_filename(self.filename)

    @property
    def package_name(self) -> str:
        return self._parsed[0]

    @property
    def package_version(self) -> packaging.version.Version:
        return self._parsed[1]

    @functools.cached_property
    def tags(self) -> frozenset[tuple[str, str, str]]:
        """``(interpreter, abi, platform)`` triples with normalized platform tags."""
        return frozenset(
            (t.interpreter, t.abi, normalize_platform_tag(t.platform))
            for t in self._parsed[3]
        )

    @functools.cached_property
    def is_universal(self) -> bool:
        return any(plat == "any" for _, _, plat in self.tags)

    # ------------------------------------------------------------------
    # Compatibility
    # ------------------------------------------------------------------
    def compatible_tag(
        self,
        platform: BLPlatform,
        python_version: tuple[int, int],
        *,
        min_glibc_version: tuple[int, int] | None,
        min_macos_version: tuple[int, int] | None,
    ) -> tuple[str, str, str] | None:
        """The best of this wheel's tags that runs on the target, or ``None``."""
        candidates = [
            tag
            for tag in self.tags
            if _python_ok(tag[0], tag[1], python_version)
            and _platform_ok(tag[2], platform, min_glibc_version, min_macos_version)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda t: _tag_sort_key(t, platform))

    def sort_key(
        self,
        platform: BLPlatform,
        python_version: tuple[int, int],
        *,
        min_glibc_version: tuple[int, int] | None,
        min_macos_version: tuple[int, int] | None,
    ) -> tuple:
        """Lower sorts first. Only meaningful for compatible wheels."""
        tag = self.compatible_tag(
            platform,
            python_version,
            min_glibc_version=min_glibc_version,
            min_macos_version=min_macos_version,
        )
        assert tag is not None
        return (*_tag_sort_key(tag, platform), self.filename)

    def os_version(self, platform_tag: str) -> tuple[int, int] | None:
        """glibc or macOS version a platform tag requires, if any."""
        return _os_version(platform_tag)

    # ------------------------------------------------------------------
    # Download validation
    # ------------------------------------------------------------------
    def is_download_valid(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if self.size is not None and path.stat().st_size != self.size:
            return False
        if self.hash is None:
            return True
        algo, _, expected = self.hash.partition(":")
        with path.open("rb") as f:
            digest = hashlib.file_digest(f, algo).hexdigest()
        return digest == expected


# ----------------------------------------------------------------------
# Tag checks
# ----------------------------------------------------------------------
def _python_ok(interp: str, abi: str, python_version: tuple[int, int]) -> bool:
    major, minor = python_version
    exact = f"cp{major}{minor}"
    if abi == "none":
        if interp in ("py3", f"py{major}", exact):
            return True
        m = re.fullmatch(rf"py{major}(\d+)", interp)
        return m is not None and int(m.group(1)) <= minor
    if abi == "abi3":
        m = re.fullmatch(rf"cp{major}(\d+)", interp)
        return m is not None and int(m.group(1)) <= minor
    return abi == exact and interp == exact


def _os_version(platform_tag: str) -> tuple[int, int] | None:
    m = _RE_MANYLINUX.match(platform_tag) or _RE_MACOS.match(platform_tag)
    if m is None:
        return None
    return (int(m.group(1)), int(m.group(2)))


def _tag_arch(platform_tag: str) -> str | None:
    m = _RE_MANYLINUX.match(platform_tag) or _RE_MACOS.match(platform_tag)
    if m is not None:
        return m.group(3)
    if platform_tag.startswith("win_"):
        return platform_tag[4:]
    return None


def _platform_ok(
    platform_tag: str,
    platform: BLPlatform,
    min_glibc_version: tuple[int, int] | None,
    min_macos_version: tuple[int, int] | None,
) -> bool:
    if platform_tag == "any":
        return True
    if not platform_tag.startswith(platform.wheel_tag_prefix):
        return False
    arch = _tag_arch(platform_tag)
    if arch is None or arch not in platform.wheel_arches:
        return False
    os_ver = _os_version(platform_tag)
    if platform.is_linux and min_glibc_version is not None:
        return os_ver is not None and os_ver <= min_glibc_version
    if platform.is_macos and min_macos_version is not None:
        return os_ver is not None and os_ver <= min_macos_version
    return True


def _tag_sort_key(tag: tuple[str, str, str], platform: BLPlatform) -> tuple:
    interp, abi, plat = tag
    is_any = plat == "any"
    os_ver = _os_version(plat) or (0, 0)
    abi_rank = (
        0 if abi.startswith("cp") and abi != "abi3" else (1 if abi == "abi3" else 2)
    )
    is_fat = platform.is_macos and _tag_arch(plat) not in ("arm64", "x86_64")
    # Prefer: native over universal, newest OS floor, most specific ABI, thin over fat.
    return (is_any, -os_ver[0], -os_ver[1], abi_rank, is_fat)
