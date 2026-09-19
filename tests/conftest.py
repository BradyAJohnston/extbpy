"""Shared fixtures: a tiny fake project with a hand-written uv.lock."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

PYPI = "https://files.pythonhosted.org/packages/x"


def wheel_entry(filename: str, size: int = 1000) -> str:
    return f'{{ url = "{PYPI}/{filename}", hash = "sha256:{"0" * 64}", size = {size} }}'


UV_LOCK = f"""
version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "demo-ext"
version = "1.2.3"
source = {{ editable = "." }}
dependencies = [
    {{ name = "purepkg" }},
    {{ name = "binpkg" }},
    {{ name = "winonly", marker = "sys_platform == 'win32'" }},
    {{ name = "numpy" }},
]

[package.optional-dependencies]
extra-feature = [
    {{ name = "extrapkg" }},
]

[package.metadata]
requires-dist = [
    {{ name = "purepkg" }},
    {{ name = "binpkg" }},
]

[[package]]
name = "purepkg"
version = "2.0.0"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [
    {{ name = "subdep" }},
]
wheels = [
    {wheel_entry("purepkg-2.0.0-py3-none-any.whl")},
]

[[package]]
name = "subdep"
version = "0.1.0"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [
    {wheel_entry("subdep-0.1.0-py2.py3-none-any.whl")},
]

[[package]]
name = "binpkg"
version = "3.0.0"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [
    {{ name = "numpy" }},
]
wheels = [
    {wheel_entry("binpkg-3.0.0-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl")},
    {wheel_entry("binpkg-3.0.0-cp313-cp313-manylinux_2_28_x86_64.whl")},
    {wheel_entry("binpkg-3.0.0-cp313-cp313-macosx_11_0_arm64.whl")},
    {wheel_entry("binpkg-3.0.0-cp313-cp313-macosx_10_13_universal2.whl")},
    {wheel_entry("binpkg-3.0.0-cp313-cp313-win_amd64.whl")},
    {wheel_entry("binpkg-3.0.0-cp311-cp311-win_amd64.whl")},
    {wheel_entry("binpkg-3.0.0-pp310-pypy310_pp73-win_amd64.whl")},
]

[[package]]
name = "winonly"
version = "1.0.0"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [
    {wheel_entry("winonly-1.0.0-py3-none-any.whl")},
]

[[package]]
name = "numpy"
version = "2.2.0"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [
    {wheel_entry("numpy-2.2.0-cp313-cp313-win_amd64.whl")},
]

[[package]]
name = "extrapkg"
version = "9.0.0"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [
    {wheel_entry("extrapkg-9.0.0-py3-none-any.whl")},
]

[[package]]
name = "sdistonly"
version = "1.0.0"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "{PYPI}/sdistonly-1.0.0.tar.gz", hash = "sha256:{"1" * 64}", size = 10 }}
"""

PYPROJECT = """
[project]
name = "demo-ext"
version = "1.2.3"
description = "A demo extension"
license = "GPL-3.0-or-later"
requires-python = ">=3.13"
maintainers = [{ name = "Jane Doe", email = "jane@example.com" }]
dependencies = ["purepkg", "binpkg", "numpy", "winonly; sys_platform == 'win32'"]

[project.urls]
Homepage = "https://example.com/demo"

[tool.extbpy]
pretty_name = "Demo Extension"
blender_version_min = "5.2.0"
platforms = ["linux-x64", "windows-x64", "macos-arm64"]
tags = ["Development"]
copyright = ["2026 Jane Doe"]
paths_exclude_pattern = ["*.blend[1-9]", "secret/"]

[tool.extbpy.permissions]
network = "Fetching demo data"
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent(PYPROJECT))
    (tmp_path / "uv.lock").write_text(UV_LOCK)
    pkg = tmp_path / "demo_ext"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("def register():\n    pass\n")
    (pkg / "blender_manifest.toml").write_text("# stale, must not be packed\n")
    (pkg / "scene.blend").write_bytes(b"BLENDER")
    (pkg / "scene.blend1").write_bytes(b"BACKUP")
    (pkg / ".hidden").write_text("x")
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "m.pyc").write_bytes(b"\x00")
    (pkg / "secret").mkdir()
    (pkg / "secret" / "key.txt").write_text("x")
    (pkg / "wheels").mkdir()
    (pkg / "wheels" / "old-0.0.1-py3-none-any.whl").write_bytes(b"old")
    (pkg / "sub").mkdir()
    (pkg / "sub" / "mod.py").write_text("x = 1\n")
    return tmp_path
