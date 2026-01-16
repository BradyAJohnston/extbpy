# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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