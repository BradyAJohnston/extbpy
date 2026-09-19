"""Wheel tag parsing and platform compatibility."""

import hashlib

import pytest

from extbpy.extyp import BLPlatform
from extbpy.pydeps import Wheel, best_wheel
from extbpy.pydeps.wheel import normalize_platform_tag

PY313 = (3, 13)


def w(filename: str) -> Wheel:
    return Wheel(url=f"https://example.com/{filename}")


def compat(filename: str, platform: BLPlatform, py=PY313):
    return w(filename).compatible_tag(
        platform, py, min_glibc_version=(2, 28), min_macos_version=(12, 0)
    )


def test_normalize_legacy_manylinux():
    assert normalize_platform_tag("manylinux2014_x86_64") == "manylinux_2_17_x86_64"
    assert normalize_platform_tag("manylinux1_i686") == "manylinux_2_5_i686"
    assert normalize_platform_tag("manylinux_2_28_x86_64") == "manylinux_2_28_x86_64"


def test_universal_wheel_matches_everywhere():
    for p in BLPlatform:
        assert compat("pkg-1.0-py3-none-any.whl", p) is not None
        assert compat("pkg-1.0-py2.py3-none-any.whl", p) is not None
    assert w("pkg-1.0-py3-none-any.whl").is_universal


@pytest.mark.parametrize(
    ("filename", "platform", "expected"),
    [
        ("pkg-1.0-cp313-cp313-win_amd64.whl", BLPlatform.windows_x64, True),
        ("pkg-1.0-cp313-cp313-win_arm64.whl", BLPlatform.windows_x64, False),
        ("pkg-1.0-cp313-cp313-win32.whl", BLPlatform.windows_x64, False),
        ("pkg-1.0-cp313-cp313-manylinux_2_28_x86_64.whl", BLPlatform.linux_x64, True),
        ("pkg-1.0-cp313-cp313-manylinux2014_x86_64.whl", BLPlatform.linux_x64, True),
        ("pkg-1.0-cp313-cp313-manylinux_2_34_x86_64.whl", BLPlatform.linux_x64, False),
        ("pkg-1.0-cp313-cp313-manylinux_2_28_aarch64.whl", BLPlatform.linux_x64, False),
        ("pkg-1.0-cp313-cp313-musllinux_1_2_x86_64.whl", BLPlatform.linux_x64, False),
        ("pkg-1.0-cp313-cp313-macosx_11_0_arm64.whl", BLPlatform.macos_arm64, True),
        (
            "pkg-1.0-cp313-cp313-macosx_10_13_universal2.whl",
            BLPlatform.macos_arm64,
            True,
        ),
        ("pkg-1.0-cp313-cp313-macosx_10_13_x86_64.whl", BLPlatform.macos_arm64, False),
        ("pkg-1.0-cp313-cp313-macosx_14_0_arm64.whl", BLPlatform.macos_arm64, False),
        ("pkg-1.0-cp313-cp313-macosx_10_13_x86_64.whl", BLPlatform.macos_x64, True),
    ],
)
def test_platform_tags(filename, platform, expected):
    assert (compat(filename, platform) is not None) is expected


@pytest.mark.parametrize(
    ("filename", "py", "expected"),
    [
        ("pkg-1.0-cp313-cp313-win_amd64.whl", (3, 13), True),
        ("pkg-1.0-cp311-cp311-win_amd64.whl", (3, 13), False),
        ("pkg-1.0-cp313-cp313-win_amd64.whl", (3, 11), False),
        ("pkg-1.0-cp39-abi3-win_amd64.whl", (3, 13), True),
        ("pkg-1.0-cp314-abi3-win_amd64.whl", (3, 13), False),
        ("pkg-1.0-cp313-cp313t-win_amd64.whl", (3, 13), False),
        ("pkg-1.0-py311-none-any.whl", (3, 13), True),
        ("pkg-1.0-py314-none-any.whl", (3, 13), False),
        ("pkg-1.0-pp310-pypy310_pp73-win_amd64.whl", (3, 13), False),
    ],
)
def test_python_and_abi_tags(filename, py, expected):
    assert (compat(filename, BLPlatform.windows_x64, py=py) is not None) is expected


def test_prefers_native_newest_floor_over_fat_and_old():
    wheels = [
        w("pkg-1.0-cp313-cp313-macosx_10_13_universal2.whl"),
        w("pkg-1.0-cp313-cp313-macosx_11_0_arm64.whl"),
        w("pkg-1.0-py3-none-any.whl"),
    ]
    best = best_wheel(
        wheels,
        BLPlatform.macos_arm64,
        PY313,
        min_glibc_version=(2, 28),
        min_macos_version=(12, 0),
    )
    assert best is not None
    assert best.filename == "pkg-1.0-cp313-cp313-macosx_11_0_arm64.whl"


def test_prefers_highest_compatible_glibc():
    wheels = [
        w("pkg-1.0-cp313-cp313-manylinux_2_17_x86_64.whl"),
        w("pkg-1.0-cp313-cp313-manylinux_2_28_x86_64.whl"),
        w("pkg-1.0-cp313-cp313-manylinux_2_34_x86_64.whl"),
    ]
    best = best_wheel(
        wheels,
        BLPlatform.linux_x64,
        PY313,
        min_glibc_version=(2, 28),
        min_macos_version=(12, 0),
    )
    assert best is not None
    assert best.filename == "pkg-1.0-cp313-cp313-manylinux_2_28_x86_64.whl"


def test_download_validation(tmp_path):
    data = b"hello"
    path = tmp_path / "pkg-1.0-py3-none-any.whl"
    path.write_bytes(data)
    good = Wheel(
        url="https://x/pkg-1.0-py3-none-any.whl",
        hash="sha256:" + hashlib.sha256(data).hexdigest(),
        size=len(data),
    )
    assert good.is_download_valid(path)
    assert not Wheel(url=good.url, hash="sha256:" + "0" * 64, size=5).is_download_valid(
        path
    )
    assert not Wheel(url=good.url, hash=good.hash, size=99).is_download_valid(path)
    assert not good.is_download_valid(tmp_path / "missing.whl")
