"""Parse ``uv.lock`` and resolve the wheels an extension needs per platform."""

from __future__ import annotations

import dataclasses
import tomllib
from collections import deque
from pathlib import Path
from typing import Any

import packaging.utils

from ..exceptions import DependencyError
from ..extyp import BLPlatform, BLRelease
from .marker import marker_environments, marker_holds
from .wheel import Wheel

PackageKey = tuple[str, str]  # (canonical name, version)


@dataclasses.dataclass(frozen=True)
class DepEdge:
    """A dependency declared by one locked package on another."""

    name: str
    version: str | None
    marker: str | None


@dataclasses.dataclass(frozen=True)
class PyDep:
    """One ``[[package]]`` entry of ``uv.lock``."""

    name: str
    version: str
    source: dict[str, Any]
    wheels: tuple[Wheel, ...]
    deps: tuple[DepEdge, ...]
    optional_deps: dict[str, tuple[DepEdge, ...]]
    resolution_markers: tuple[str, ...]

    @property
    def key(self) -> PackageKey:
        return (self.name, self.version)

    @property
    def is_registry(self) -> bool:
        return "registry" in self.source

    def select_wheel(
        self,
        platform: BLPlatform,
        release: BLRelease,
        *,
        min_glibc_version: tuple[int, int],
        min_macos_version: tuple[int, int],
    ) -> Wheel | None:
        """The best wheel for the target, or ``None`` if nothing fits."""
        kwargs = dict(
            min_glibc_version=min_glibc_version if platform.is_linux else None,
            min_macos_version=min_macos_version if platform.is_macos else None,
        )
        compatible = [
            w
            for w in self.wheels
            if w.compatible_tag(platform, release.python_version, **kwargs) is not None
        ]
        if not compatible:
            return None
        return min(
            compatible,
            key=lambda w: w.sort_key(platform, release.python_version, **kwargs),
        )


@dataclasses.dataclass(frozen=True)
class MissingWheel:
    """Why a required package has no usable wheel for a platform."""

    package: PyDep
    platform: BLPlatform
    required_by: tuple[str, ...]

    def explain(self, release: BLRelease) -> str:
        lines = [
            f"{self.package.name}=={self.package.version} has no wheel for {self.platform}"
        ]
        if self.required_by:
            lines.append(f"  required by: {', '.join(sorted(self.required_by))}")
        if not self.package.is_registry:
            lines.append(f"  source is not a registry: {self.package.source}")
        elif not self.package.wheels:
            lines.append("  the lockfile only records a source distribution")
        else:
            lines.append(
                f"  target: Python {release.python_version[0]}.{release.python_version[1]}"
            )
            lines.append("  available wheels:")
            for w in sorted(self.package.wheels, key=lambda w: w.filename):
                lines.append(f"    - {w.filename}")
        return "\n".join(lines)


@dataclasses.dataclass(frozen=True)
class Resolution:
    """Wheels chosen for one platform."""

    platform: BLPlatform
    wheels: dict[str, Wheel]
    missing: tuple[MissingWheel, ...]
    excluded: frozenset[str]

    @property
    def ok(self) -> bool:
        return not self.missing


class LockFile:
    """A parsed ``uv.lock``."""

    def __init__(self, packages: dict[PackageKey, PyDep], root_name: str) -> None:
        self.packages = packages
        self.root_name = packaging.utils.canonicalize_name(root_name)
        roots = [p for p in packages.values() if p.name == self.root_name]
        if not roots:
            raise DependencyError(
                f"uv.lock has no entry for the project '{root_name}'. "
                "Run `uv lock` in the project directory."
            )
        self.root = roots[0]

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path, root_name: str) -> LockFile:
        if not path.is_file():
            raise DependencyError(
                f"No uv.lock found at {path}. Run `uv lock` to create one."
            )
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data, root_name)

    @classmethod
    def from_dict(cls, data: dict[str, Any], root_name: str) -> LockFile:
        packages: dict[PackageKey, PyDep] = {}
        for entry in data.get("package", []):
            dep = _parse_package(entry)
            packages[dep.key] = dep
        return cls(packages, root_name)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    def resolve(
        self,
        platform: BLPlatform,
        release: BLRelease,
        *,
        excluded: frozenset[str] = frozenset(),
        extras: tuple[str, ...] = (),
        min_glibc_version: tuple[int, int] | None = None,
        min_macos_version: tuple[int, int] | None = None,
    ) -> Resolution:
        """Walk the dependency graph from the root and pick one wheel per package.

        Edges whose markers do not hold on the target are not followed.
        Excluded (Blender-vendored) packages are walked through but never
        bundled, so their own dependencies still get considered.
        """
        envs = marker_environments(platform, release)
        min_glibc = min_glibc_version or release.min_glibc_version
        min_macos = min_macos_version or release.min_macos_version

        for extra in extras:
            if extra not in self.root.optional_deps:
                raise DependencyError(
                    f"Extra '{extra}' is not an optional-dependency group of "
                    f"'{self.root.name}' in uv.lock"
                )

        start_edges = list(self.root.deps)
        for extra in extras:
            start_edges.extend(self.root.optional_deps[extra])

        queue: deque[tuple[DepEdge, str]] = deque(
            (e, self.root.name) for e in start_edges
        )
        visited: set[PackageKey] = set()
        required_by: dict[PackageKey, set[str]] = {}
        wheels: dict[str, Wheel] = {}
        missing: list[PyDep] = []
        excluded_hit: set[str] = set()

        while queue:
            edge, parent = queue.popleft()
            if not marker_holds(edge.marker, envs):
                continue
            for dep in self._targets(edge, envs):
                required_by.setdefault(dep.key, set()).add(parent)
                if dep.key in visited:
                    continue
                visited.add(dep.key)
                queue.extend((e, dep.name) for e in dep.deps)

                if dep.name in excluded:
                    excluded_hit.add(dep.name)
                    continue
                wheel = dep.select_wheel(
                    platform,
                    release,
                    min_glibc_version=min_glibc,
                    min_macos_version=min_macos,
                )
                if wheel is None:
                    missing.append(dep)
                else:
                    wheels[dep.name] = wheel

        return Resolution(
            platform=platform,
            wheels=wheels,
            missing=tuple(
                MissingWheel(dep, platform, tuple(sorted(required_by[dep.key])))
                for dep in missing
            ),
            excluded=frozenset(excluded_hit),
        )

    def _targets(self, edge: DepEdge, envs: tuple[dict[str, str], ...]) -> list[PyDep]:
        if edge.version is not None:
            key = (edge.name, edge.version)
            if key not in self.packages:
                raise DependencyError(
                    f"uv.lock references {edge.name}=={edge.version} but has no such package"
                )
            return [self.packages[key]]
        candidates = [p for p in self.packages.values() if p.name == edge.name]
        if not candidates:
            raise DependencyError(
                f"uv.lock references '{edge.name}' but has no such package. "
                "Run `uv lock` to refresh the lockfile."
            )
        if len(candidates) == 1:
            return candidates
        # Several versions: keep those whose resolution markers hold.
        applicable = [
            p
            for p in candidates
            if not p.resolution_markers
            or any(marker_holds(m, envs) for m in p.resolution_markers)
        ]
        return applicable or candidates


# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------
def _parse_edge(entry: dict[str, Any]) -> DepEdge:
    return DepEdge(
        name=packaging.utils.canonicalize_name(entry["name"]),
        version=entry.get("version"),
        marker=entry.get("marker"),
    )


def _parse_package(entry: dict[str, Any]) -> PyDep:
    wheels = tuple(
        Wheel(url=w["url"], hash=w.get("hash"), size=w.get("size"))
        for w in entry.get("wheels", [])
        if "url" in w
    )
    return PyDep(
        name=packaging.utils.canonicalize_name(entry["name"]),
        version=str(entry.get("version", "0")),
        source=dict(entry.get("source", {})),
        wheels=wheels,
        deps=tuple(_parse_edge(d) for d in entry.get("dependencies", [])),
        optional_deps={
            packaging.utils.canonicalize_name(extra): tuple(
                _parse_edge(d) for d in deps
            )
            for extra, deps in entry.get("optional-dependencies", {}).items()
        },
        resolution_markers=tuple(entry.get("resolution-markers", [])),
    )
