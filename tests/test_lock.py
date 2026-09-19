"""Lockfile parsing and per-platform resolution."""

import pytest

from extbpy.exceptions import DependencyError
from extbpy.extyp import BLPlatform, release_for
from extbpy.pydeps import LockFile

REL = release_for("5.2.0")


@pytest.fixture
def lock(project):
    return LockFile.load(project / "uv.lock", "demo-ext")


def names(resolution):
    return sorted(resolution.wheels)


def test_root_is_found(lock):
    assert lock.root.name == "demo-ext"
    assert lock.root.version == "1.2.3"


def test_missing_lock_is_clear(tmp_path):
    with pytest.raises(DependencyError, match="uv lock"):
        LockFile.load(tmp_path / "uv.lock", "x")


def test_marker_edges_follow_platform(lock):
    linux = lock.resolve(BLPlatform.linux_x64, REL, excluded=frozenset({"numpy"}))
    win = lock.resolve(BLPlatform.windows_x64, REL, excluded=frozenset({"numpy"}))
    assert names(linux) == ["binpkg", "purepkg", "subdep"]
    assert names(win) == ["binpkg", "purepkg", "subdep", "winonly"]


def test_best_wheel_per_platform(lock):
    ex = frozenset({"numpy"})
    linux = lock.resolve(BLPlatform.linux_x64, REL, excluded=ex)
    mac = lock.resolve(BLPlatform.macos_arm64, REL, excluded=ex)
    win = lock.resolve(BLPlatform.windows_x64, REL, excluded=ex)
    assert (
        linux.wheels["binpkg"].filename
        == "binpkg-3.0.0-cp313-cp313-manylinux_2_28_x86_64.whl"
    )
    assert (
        mac.wheels["binpkg"].filename
        == "binpkg-3.0.0-cp313-cp313-macosx_11_0_arm64.whl"
    )
    assert win.wheels["binpkg"].filename == "binpkg-3.0.0-cp313-cp313-win_amd64.whl"


def test_vendored_package_is_reported_missing_when_not_excluded(lock):
    linux = lock.resolve(BLPlatform.linux_x64, REL)
    (missing,) = linux.missing
    assert missing.package.name == "numpy"
    assert set(missing.required_by) == {"demo-ext", "binpkg"}
    assert "numpy-2.2.0-cp313-cp313-win_amd64.whl" in missing.explain(REL)


def test_extras_are_opt_in(lock):
    ex = frozenset({"numpy"})
    plain = lock.resolve(BLPlatform.linux_x64, REL, excluded=ex)
    with_extra = lock.resolve(
        BLPlatform.linux_x64, REL, excluded=ex, extras=("extra-feature",)
    )
    assert "extrapkg" not in plain.wheels
    assert "extrapkg" in with_extra.wheels
    with pytest.raises(DependencyError, match="not an optional-dependency"):
        lock.resolve(BLPlatform.linux_x64, REL, excluded=ex, extras=("nope",))


def test_glibc_override_changes_selection(lock):
    ex = frozenset({"numpy"})
    old = lock.resolve(
        BLPlatform.linux_x64, REL, excluded=ex, min_glibc_version=(2, 17)
    )
    assert old.wheels["binpkg"].filename.endswith(
        "manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    )
