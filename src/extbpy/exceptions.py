"""
Custom exceptions for extbpy.
"""


class ExtbpyError(Exception):
    """Base exception for all extbpy errors."""

    pass


class ConfigurationError(ExtbpyError):
    """Raised when there's an issue with project configuration."""

    pass


class DependencyError(ExtbpyError):
    """Raised when there's an issue with dependencies."""

    pass


class BuildError(ExtbpyError):
    """Raised when there's an issue during the build process."""

    pass


class BlenderError(ExtbpyError):
    """Raised when there's an issue with Blender execution."""

    pass


class PlatformError(ExtbpyError):
    """Raised when there's an issue with platform detection or handling."""

    pass
