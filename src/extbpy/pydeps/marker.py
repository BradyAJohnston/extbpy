"""Evaluate PEP 508 environment markers against a target Blender environment."""

from __future__ import annotations

import functools

import packaging.markers

from ..extyp import BLPlatform, BLRelease

MarkerEnv = dict[str, str]


def marker_environments(
    platform: BLPlatform, release: BLRelease
) -> tuple[MarkerEnv, ...]:
    """Every marker environment a user of ``platform`` + ``release`` may have.

    ``platform_machine`` can take several values on one platform, so one
    environment per value is produced; a marker holds if it holds for any.
    ``extra`` is empty since extras are resolved explicitly from the lockfile.
    """
    major, minor = release.python_version
    return tuple(
        {
            "implementation_name": "cpython",
            "implementation_version": f"{major}.{minor}.0",
            "os_name": platform.marker_os_name,
            "platform_machine": machine,
            "platform_release": "",
            "platform_system": platform.marker_platform_system,
            "platform_version": "",
            "python_full_version": f"{major}.{minor}.0",
            "platform_python_implementation": "CPython",
            "python_version": f"{major}.{minor}",
            "sys_platform": platform.marker_sys_platform,
            "extra": "",
        }
        for machine in sorted(platform.marker_platform_machines)
    )


@functools.cache
def _parse(marker: str) -> packaging.markers.Marker:
    return packaging.markers.Marker(marker)


def marker_holds(marker: str | None, environments: tuple[MarkerEnv, ...]) -> bool:
    """Whether ``marker`` (``None`` means unconditional) holds in any environment."""
    if marker is None:
        return True
    parsed = _parse(marker)
    return any(parsed.evaluate(environment=env) for env in environments)
