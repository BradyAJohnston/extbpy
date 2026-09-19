"""Hash-verified, parallel wheel downloads into a cache directory."""

from __future__ import annotations

import concurrent.futures
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

from ..exceptions import DependencyError
from .wheel import Wheel

_CHUNK_BYTES = 64 * 1024
_MAX_WORKERS = 8

ProgressCallback = Callable[[Wheel, int], None]
"""Called with the wheel and the number of bytes just received."""
FinishCallback = Callable[[Wheel, Path], None]
"""Called once a wheel is verified and in place."""


def download_wheel(
    wheel: Wheel, wheels_dir: Path, *, on_progress: ProgressCallback | None = None
) -> Path:
    """Download one wheel to ``wheels_dir``, verifying its hash before keeping it."""
    target = wheels_dir / wheel.filename
    partial = wheels_dir / (wheel.filename + ".part")
    try:
        with (
            urllib.request.urlopen(wheel.url, timeout=30) as response,
            partial.open("wb") as f,
        ):
            for chunk in iter(lambda: response.read(_CHUNK_BYTES), b""):
                f.write(chunk)
                if on_progress is not None:
                    on_progress(wheel, len(chunk))
    except (urllib.error.URLError, OSError) as e:
        partial.unlink(missing_ok=True)
        raise DependencyError(f"Failed to download {wheel.filename}: {e}") from e

    if not wheel.is_download_valid(partial):
        partial.unlink(missing_ok=True)
        raise DependencyError(
            f"Downloaded {wheel.filename} does not match the hash recorded in uv.lock"
        )
    os.replace(partial, target)
    return target


def download_wheels(
    wheels: Iterable[Wheel],
    wheels_dir: Path,
    *,
    on_progress: ProgressCallback | None = None,
    on_finish: FinishCallback | None = None,
) -> dict[Wheel, Path]:
    """Download every wheel not already valid in ``wheels_dir``.

    Returns a mapping of every requested wheel to its path on disk.
    """
    wheels = list(wheels)
    wheels_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        w: wheels_dir / w.filename
        for w in wheels
        if w.is_download_valid(wheels_dir / w.filename)
    }
    todo = [w for w in wheels if w not in paths]
    if not todo:
        return paths

    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(download_wheel, w, wheels_dir, on_progress=on_progress): w
            for w in sorted(todo, key=lambda w: w.size or 0, reverse=True)
        }
        errors: list[str] = []
        for future in concurrent.futures.as_completed(futures):
            wheel = futures[future]
            try:
                paths[wheel] = future.result()
            except DependencyError as e:
                errors.append(str(e))
                continue
            if on_finish is not None:
                on_finish(wheel, paths[wheel])
    if errors:
        raise DependencyError(
            f"{len(errors)} wheel download(s) failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return paths
