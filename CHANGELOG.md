# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-09-19

### Added
- `extbpy sync` writes `blender_manifest.toml` and `wheels/` into the package for this machine's platform, so Blender can load the add-on straight from the source directory. `extbpy build` does the same at the end of a build unless `--no-sync` is given.

## [0.3.0] - 2026-09-19

### Changed
- Rewritten around a `pyproject.toml`-driven extension specification. `blender_manifest.toml` is now generated at build time from `[project]` and `[tool.extbpy]`; a hand-written manifest in the package is ignored.
- Wheel selection is tag-based: interpreter, ABI and platform tags, glibc and macOS floors, and PEP 508 markers are all evaluated per target platform. One best wheel is chosen per package and platform.
- Zips are written by extbpy itself, so Blender is no longer required to build. When Blender is available the zips are validated with `blender --command extension validate`.
- Downloads are hash-verified and cached in `.extbpy/wheels`.
- `uv.lock` is checked against `pyproject.toml` before building.

### Added
- `extbpy manifest` prints the generated manifest.
- `[tool.extbpy]` keys: `pretty_name`, `tagline`, `blender_version_min/max`, `tags`, `copyright`, `permissions`, `exclude_packages`, `extras`, `min_glibc_version`, `min_macos_version`, `paths_exclude_pattern`, `required_files`, `package_dir`.
- Support for `linux-arm64` and `windows-arm64`.

### Removed
- `extbpy download-urls`, the pip fallback, and the `--extension-path` option (use `--package-dir` or `tool.extbpy.package_dir`).

## [0.2.0] - 2026-01-16

### Added
- Support for extensions located in `src/` directory
- New `--extension-path` CLI option to specify custom extension directory paths
- Enhanced extension discovery that searches in source directory, src/ subdirectory, and custom paths
- Better error messages when extension directories cannot be found

### Changed
- Extension finder now prioritizes custom paths, then src/ directory, then source directory root
- Improved debugging output with location information when extensions are found

## [0.1.0] - Initial Release

### Added
- Core Blender extension building functionality
- Multi-platform wheel downloading and management
- Support for uv.lock dependency resolution
- CLI interface with build, download, clean, and info commands
- Cross-platform support (Windows x64, Linux x64, macOS ARM64/x64)
- Automatic dependency exclusion for packages already available in Blender
- Rich console output with progress bars and colored logging
- Extension manifest updating with wheel and platform information
