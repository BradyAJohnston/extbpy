"""Write an extension zip from the package source, a manifest and wheels."""

from __future__ import annotations

import functools
import re
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from .extyp import BLManifest

MANIFEST_FILENAME = "blender_manifest.toml"
WHEELS_DIRNAME = "wheels"


@functools.lru_cache(maxsize=None)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob to a regex where ``*`` and ``?`` never cross ``/``."""
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(ch))
            else:
                body = pattern[i + 1 : j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                i = j
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("".join(out) + r"\Z")


def is_excluded(
    rel_path: PurePosixPath, *, is_dir: bool, patterns: Iterable[str]
) -> bool:
    """Gitignore-style matching as used by Blender's ``paths_exclude_pattern``.

    - A trailing ``/`` matches directories only.
    - A leading ``/`` anchors the pattern to the package root.
    - A pattern containing ``/`` elsewhere is matched against the whole
      relative path; otherwise it is matched against the file name at any depth.
    """
    path_str = rel_path.as_posix()
    for pattern in patterns:
        dir_only = pattern.endswith("/")
        pattern = pattern.rstrip("/")
        if dir_only and not is_dir:
            continue
        if pattern.startswith("/"):
            subject, pattern = path_str, pattern[1:]
        elif "/" in pattern:
            subject = path_str
        else:
            subject = rel_path.name
        if _glob_regex(pattern).match(subject):
            return True
    return False


def collect_package_files(
    package_dir: Path, patterns: Iterable[str]
) -> list[tuple[Path, str]]:
    """``(source path, archive name)`` pairs for every file to ship."""
    patterns = tuple(patterns)
    files: list[tuple[Path, str]] = []

    def walk(directory: Path) -> None:
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            rel = PurePosixPath(entry.relative_to(package_dir).as_posix())
            if entry.is_dir():
                # Wheels are bundled from the cache, never from a stale source tree.
                if rel == PurePosixPath(WHEELS_DIRNAME):
                    continue
                if is_excluded(rel, is_dir=True, patterns=patterns):
                    continue
                walk(entry)
            else:
                if rel == PurePosixPath(MANIFEST_FILENAME):
                    continue
                if is_excluded(rel, is_dir=False, patterns=patterns):
                    continue
                files.append((entry, rel.as_posix()))

    walk(package_dir)
    return files


def pack_extension(
    *,
    package_dir: Path,
    manifest: BLManifest,
    wheel_paths: Iterable[Path],
    exclude_patterns: Iterable[str],
    output_path: Path,
) -> Path:
    """Write ``output_path`` containing the manifest, package files and wheels."""
    files = collect_package_files(package_dir, exclude_patterns)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_FILENAME, manifest.to_toml())
        for source, arcname in files:
            zf.write(source, arcname)
        # Wheels are already compressed; store them as-is.
        for wheel_path in sorted(wheel_paths, key=lambda p: p.name):
            zf.write(
                wheel_path, f"{WHEELS_DIRNAME}/{wheel_path.name}", zipfile.ZIP_STORED
            )
    tmp.replace(output_path)
    return output_path
