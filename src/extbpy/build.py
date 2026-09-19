"""Orchestrate resolve, download and pack into finished extension zips."""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

from .exceptions import BlenderError, BuildError, ConfigurationError, DependencyError
from .extyp import BLManifest, BLPlatform
from .pack import pack_extension
from .pydeps import LockFile, Resolution, Wheel
from .pydeps.download import download_wheels
from .spec import ExtensionSpec

DEFAULT_WHEELS_DIRNAME = ".extbpy/wheels"


@dataclasses.dataclass(frozen=True)
class BuildTarget:
    """One zip to produce: a platform, or ``None`` for a universal build."""

    platform: BLPlatform | None
    platforms: tuple[BLPlatform, ...]
    wheels: tuple[Wheel, ...]

    def manifest(self, spec: ExtensionSpec) -> BLManifest:
        return spec.manifest(
            platforms=self.platforms if self.platform is not None else None,
            wheels=tuple(f"./wheels/{w.filename}" for w in self.wheels) or None,
        )


@dataclasses.dataclass(frozen=True)
class BuildResult:
    target: BuildTarget
    zip_path: Path


# ----------------------------------------------------------------------
# Resolution
# ----------------------------------------------------------------------
def resolve_all(
    spec: ExtensionSpec, lock: LockFile, platforms: tuple[BLPlatform, ...]
) -> dict[BLPlatform, Resolution]:
    resolutions = {
        p: lock.resolve(
            p,
            spec.release,
            excluded=spec.excluded_packages,
            extras=spec.extras,
            min_glibc_version=spec.min_glibc_version,
            min_macos_version=spec.min_macos_version,
        )
        for p in platforms
    }
    problems = [m for r in resolutions.values() for m in r.missing]
    if problems:
        raise DependencyError(
            "Some dependencies have no usable wheel:\n\n"
            + "\n\n".join(m.explain(spec.release) for m in problems)
            + "\n\nRemedies: drop the platform from tool.extbpy.platforms, pin a different "
            "version, or add the package to tool.extbpy.exclude_packages if Blender provides it."
        )
    return resolutions


def plan_targets(
    spec: ExtensionSpec, resolutions: dict[BLPlatform, Resolution]
) -> list[BuildTarget]:
    """One target per platform, collapsed to a single universal target when possible."""
    platforms = tuple(resolutions)
    wheel_sets = [frozenset(r.wheels.values()) for r in resolutions.values()]
    all_universal = all(w.is_universal for ws in wheel_sets for w in ws)
    if all_universal and all(ws == wheel_sets[0] for ws in wheel_sets):
        platforms_full = tuple(sorted(spec.release.platforms))
        if set(platforms) == set(platforms_full):
            return [BuildTarget(None, platforms, _sorted(wheel_sets[0]))]
    return [
        BuildTarget(p, (p,), _sorted(r.wheels.values())) for p, r in resolutions.items()
    ]


def _sorted(wheels: Iterable[Wheel]) -> tuple[Wheel, ...]:
    return tuple(sorted(wheels, key=lambda w: w.filename))


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------
def check_required_files(spec: ExtensionSpec) -> None:
    missing = [f for f in spec.required_files if not (spec.source_dir / f).exists()]
    if missing:
        raise BuildError(
            "Required files are missing (tool.extbpy.required_files):\n"
            + "\n".join(f"  - {f}" for f in missing)
        )


def find_uv() -> str | None:
    return os.environ.get("UV") or shutil.which("uv")


def check_lock_current(spec: ExtensionSpec, uv_exe: str) -> None:
    """Fail if ``uv.lock`` does not match ``pyproject.toml``."""
    result = subprocess.run(
        [uv_exe, "lock", "--check"],
        cwd=spec.source_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ConfigurationError(
            "uv.lock is out of date with pyproject.toml. Run `uv lock` and retry.\n"
            + result.stderr.strip()
        )


def find_blender(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    for candidate in (os.environ.get("BLENDER"), shutil.which("blender")):
        if candidate:
            return candidate
    mac_app = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if mac_app.is_file():
        return str(mac_app)
    return None


def validate_with_blender(blender_exe: str, zip_path: Path) -> None:
    result = subprocess.run(
        [blender_exe, "--command", "extension", "validate", str(zip_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BlenderError(
            f"Blender rejected {zip_path.name}:\n{result.stdout}\n{result.stderr}".strip()
        )


# ----------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------
def build(
    spec: ExtensionSpec,
    *,
    platforms: tuple[BLPlatform, ...],
    output_dir: Path,
    wheels_dir: Path,
    on_download_progress: Callable[[Wheel, int], None] | None = None,
    on_download_finish: Callable[[Wheel, Path], None] | None = None,
    on_status: Callable[[str], None] = lambda _: None,
) -> list[BuildResult]:
    check_required_files(spec)
    lock = LockFile.load(spec.uv_lock_path, spec.id)
    resolutions = resolve_all(spec, lock, platforms)
    targets = plan_targets(spec, resolutions)
    # Validate every manifest up front, before any download happens.
    manifests = {t: t.manifest(spec) for t in targets}

    needed = {w for t in targets for w in t.wheels}
    on_status(f"Resolved {len(needed)} wheel(s) across {len(platforms)} platform(s)")
    paths = download_wheels(
        needed,
        wheels_dir,
        on_progress=on_download_progress,
        on_finish=on_download_finish,
    )

    results: list[BuildResult] = []
    for target in targets:
        zip_path = output_dir / spec.zip_filename(target.platform)
        on_status(f"Packing {zip_path.name}")
        pack_extension(
            package_dir=spec.package_dir,
            manifest=manifests[target],
            wheel_paths=[paths[w] for w in target.wheels],
            exclude_patterns=spec.paths_exclude_pattern,
            output_path=zip_path,
        )
        results.append(BuildResult(target, zip_path))
    return results
