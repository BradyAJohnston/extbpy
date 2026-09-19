class ExtbpyError(Exception):
    """Base class for all extbpy errors."""


class ConfigurationError(ExtbpyError):
    """pyproject.toml or the generated manifest is invalid."""


class DependencyError(ExtbpyError):
    """uv.lock is missing, stale, or has no usable wheel for a target."""


class BuildError(ExtbpyError):
    """A required file is missing or packing failed."""


class BlenderError(ExtbpyError):
    """Blender rejected a built zip."""


class PlatformError(ExtbpyError):
    """Unknown or undetectable platform."""
