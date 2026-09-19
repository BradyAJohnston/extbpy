# extbpy

Build Blender extensions from a standard `uv` project.

`pyproject.toml` is the single source of truth: `[project]` supplies the
generic metadata and `[tool.extbpy]` supplies what is specific to Blender.
`extbpy` generates `blender_manifest.toml`, picks the right wheel for every
dependency and platform from `uv.lock`, downloads them into a cache, and
writes one installable zip per platform. No Blender install is needed to
build; if one is on `PATH` the zips are validated with
`blender --command extension validate`.

## Quick start

```bash
uv init my-extension && cd my-extension
uv add numpy scipy          # any dependencies with wheels on PyPI
uv lock
```

Add the Blender-specific fields to `pyproject.toml`:

```toml
[project]
name = "my_extension"            # becomes the extension id
version = "1.0.0"
description = "Does something useful in Blender"   # becomes the tagline
license = "GPL-3.0-or-later"
requires-python = "~=3.13.0"
maintainers = [{ name = "Jane Doe", email = "jane@example.com" }]
dependencies = ["numpy", "scipy"]

[project.urls]
Homepage = "https://example.com/my-extension"

[tool.extbpy]
pretty_name = "My Extension"
blender_version_min = "5.2.0"
platforms = ["windows-x64", "linux-x64", "macos-arm64"]
tags = ["Geometry Nodes"]
copyright = ["2026 Jane Doe"]

[tool.extbpy.permissions]
network = "Downloads example data"
```

Put the extension package at `my_extension/__init__.py` (or `src/my_extension/`), then:

```bash
uvx extbpy build
```

This writes `my_extension-1.0.0-<platform>.zip` for every configured platform.

## Commands

| Command | What it does |
| --- | --- |
| `extbpy build` | Resolve, download, pack and (if Blender is found) validate. |
| `extbpy sync` | Write the manifest and wheels into the package for local development. |
| `extbpy download` | Only fill the wheel cache. |
| `extbpy manifest` | Print the generated `blender_manifest.toml`. |
| `extbpy info` | Show the parsed extension specification. |
| `extbpy clean` | Delete stray `*.blend1` and similar files from the package. |

Useful `build` options:

- `-p/--platform` selects platforms (`-p linux-x64 -p windows-x64`, `-p current`, `-p all`).
- `-o/--output-dir` chooses where zips go (default: current directory).
- `--wheels-dir` overrides the cache (default: `<project>/.extbpy/wheels`, add it to `.gitignore`).
- `--blender PATH` / `--no-check` control validation with Blender.
- `--no-sync` skips writing the local manifest and wheels into the package.
- `--skip-lock-check` skips verifying that `uv.lock` matches `pyproject.toml`.

## Local development

Blender loads an extension from a source directory only if that directory
holds `blender_manifest.toml` and the wheels it lists. `extbpy sync` (also run
at the end of `extbpy build`) writes both into the package for this machine's
platform, hard-linking wheels from the cache. Point Blender or the Blender VS
Code extension at the package directory and iterate. Add these to `.gitignore`:

```
.extbpy/
my_extension/blender_manifest.toml
my_extension/wheels/
```

## `[tool.extbpy]` reference

| Key | Required | Meaning |
| --- | --- | --- |
| `blender_version_min` | yes | Minimum Blender version, e.g. `"5.2.0"`. Determines Python version, supported platforms and vendored packages. |
| `pretty_name` | no | Human-readable name (default: `project.name`). |
| `tagline` | no | Overrides `project.description`. At most 64 characters, no trailing punctuation. |
| `id` | no | Extension id (default: `project.name` with `-` replaced by `_`). |
| `blender_version_max` | no | Exclusive upper Blender version. |
| `platforms` | no | Subset of the platforms Blender ships for (default: all of them). |
| `tags` | no | Blender extension tags. |
| `copyright` | no | List of `"YEAR Name"` entries. |
| `permissions` | no | Table of `files`, `network`, `clipboard`, `camera`, `microphone` with a short reason each. |
| `license` | no | Overrides `project.license`; SPDX identifiers. |
| `maintainer` | no | Overrides the first entry of `project.maintainers`. |
| `website` | no | Overrides `project.urls.Homepage`. |
| `package_dir` | no | Where the extension package lives, if not `<id>/` or `src/<id>/`. |
| `exclude_packages` | no | Extra packages never to bundle, on top of what Blender vendors (`numpy`, `requests`, ...). |
| `extras` | no | Optional-dependency groups to bundle as well. |
| `min_glibc_version` | no | `[MAJOR, MINOR]` floor for Linux wheels (default from Blender version). |
| `min_macos_version` | no | `[MAJOR, MINOR]` floor for macOS wheels (default from Blender version). |
| `paths_exclude_pattern` | no | Extra gitignore-style patterns; `__pycache__/`, `.*` and `/*.zip` are always excluded. |
| `required_files` | no | Paths relative to the project that must exist before building. |

## How wheels are chosen

For each platform, `extbpy` walks the dependency graph in `uv.lock` starting
from your project's dependencies, following only edges whose environment
markers hold on that platform and Blender's Python version. For every package
it keeps one wheel: the interpreter, ABI and platform tags must match, Linux
wheels must not need a newer glibc than Blender supports, macOS wheels must
not need a newer macOS, and among the remaining candidates the newest OS
floor and the most specific ABI win. Packages Blender ships itself are
skipped. Anything without a usable wheel stops the build with a message that
names the package, the platform, the packages that pull it in and the wheels
that were rejected.

## Acknowledgements

The architecture (a `pyproject.toml`-driven spec, tag-based wheel selection
against a per-platform marker environment, hash-verified wheel cache, and an
in-process packer) follows [blext](https://codeberg.org/so-rose/blext) by
Sofus Albert Høgsbro Rose. The code here is an independent implementation.

## Development

```bash
uv sync --all-extras
uvx pre-commit install      # ruff format, ruff check and ty run on every commit
uv run pytest
```

CI runs the same ruff and ty checks plus the test suite on Linux, macOS and Windows.

## License

MIT
