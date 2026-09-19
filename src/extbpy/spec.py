"""The extension specification, parsed from ``pyproject.toml``.

``[project]`` supplies the generic metadata (id, version, tagline, maintainer,
license, homepage) and ``[tool.extbpy]`` supplies what is specific to Blender.
"""

from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path
from typing import Any

import packaging.utils
import pydantic

from .exceptions import ConfigurationError
from .extyp import BLManifest, BLPlatform, BLRelease, parse_blender_version, release_for

DEFAULT_PATHS_EXCLUDE_PATTERN: tuple[str, ...] = ("__pycache__/", ".*", "/*.zip")
_VALID_PERMISSIONS = ("files", "network", "clipboard", "camera", "microphone")


@dataclasses.dataclass(frozen=True)
class ExtensionSpec:
    """Everything needed to build an extension, independent of platform."""

    source_dir: Path
    package_dir: Path
    id: str
    version: str
    name: str
    tagline: str
    maintainer: str
    license: tuple[str, ...]
    blender_version_min: str
    release: BLRelease
    platforms: tuple[BLPlatform, ...]
    blender_version_max: str | None = None
    website: str | None = None
    copyright: tuple[str, ...] | None = None
    tags: tuple[str, ...] | None = None
    permissions: dict[str, str] | None = None
    min_glibc_version: tuple[int, int] | None = None
    min_macos_version: tuple[int, int] | None = None
    exclude_packages: frozenset[str] = frozenset()
    extras: tuple[str, ...] = ()
    paths_exclude_pattern: tuple[str, ...] = DEFAULT_PATHS_EXCLUDE_PATTERN
    required_files: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Derived
    # ------------------------------------------------------------------
    @property
    def pyproject_path(self) -> Path:
        return self.source_dir / "pyproject.toml"

    @property
    def uv_lock_path(self) -> Path:
        return self.source_dir / "uv.lock"

    @property
    def excluded_packages(self) -> frozenset[str]:
        """Packages never bundled: Blender's vendored set plus project overrides."""
        return self.release.vendored_packages | self.exclude_packages

    @property
    def effective_min_glibc_version(self) -> tuple[int, int]:
        return self.min_glibc_version or self.release.min_glibc_version

    @property
    def effective_min_macos_version(self) -> tuple[int, int]:
        return self.min_macos_version or self.release.min_macos_version

    def zip_filename(self, platform: BLPlatform | None) -> str:
        """Matches the names ``blender --command extension build`` produces."""
        if platform is None:
            return f"{self.id}-{self.version}.zip"
        return f"{self.id}-{self.version}-{platform.zip_suffix}.zip"

    def manifest(
        self,
        *,
        platforms: tuple[BLPlatform, ...] | None,
        wheels: tuple[str, ...] | None,
    ) -> BLManifest:
        """The manifest for one build. ``platforms=None`` means universal."""
        try:
            return BLManifest(
                id=self.id,
                version=self.version,
                name=self.name,
                tagline=self.tagline,
                maintainer=self.maintainer,
                blender_version_min=self.blender_version_min,
                blender_version_max=self.blender_version_max,
                website=self.website,
                platforms=platforms,
                tags=self.tags,
                license=self.license,
                copyright=self.copyright,
                permissions=self.permissions,  # type: ignore[arg-type]
                wheels=wheels,
            )
        except pydantic.ValidationError as e:
            raise ConfigurationError(
                "Generated blender_manifest.toml is invalid:\n" + _format_validation(e)
            ) from None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def from_pyproject(
        cls, source_dir: Path, *, package_dir: Path | None = None
    ) -> ExtensionSpec:
        source_dir = Path(source_dir).resolve()
        path = source_dir / "pyproject.toml"
        if not path.is_file():
            raise ConfigurationError(f"No pyproject.toml found in {source_dir}")
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data, source_dir=source_dir, package_dir=package_dir)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        source_dir: Path,
        package_dir: Path | None = None,
    ) -> ExtensionSpec:
        project = data.get("project")
        if not isinstance(project, dict):
            raise ConfigurationError("pyproject.toml has no [project] table")
        cfg = data.get("tool", {}).get("extbpy", {})
        if not isinstance(cfg, dict):
            raise ConfigurationError("[tool.extbpy] must be a table")

        errors: list[str] = []

        def require(table: dict[str, Any], key: str, label: str) -> Any:
            value = table.get(key)
            if value is None:
                errors.append(f"{label} is not defined")
            return value

        project_name = require(project, "name", "project.name")
        version = require(project, "version", "project.version")
        if version is None and "version" in project.get("dynamic", []):
            errors.append(
                "project.version is dynamic; extbpy needs a literal version to write the manifest"
            )
        blender_version_min = require(
            cfg, "blender_version_min", "tool.extbpy.blender_version_min"
        )
        license_value = _parse_license(project, cfg, errors)
        tagline = cfg.get("tagline") or project.get("description")
        if not tagline:
            errors.append("project.description (or tool.extbpy.tagline) is not defined")
        maintainer = _parse_maintainer(project, cfg, errors)
        if errors:
            raise ConfigurationError(
                "pyproject.toml is missing fields required for a Blender extension:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        ext_id = cfg.get("id") or packaging.utils.canonicalize_name(
            project_name
        ).replace("-", "_")
        release = release_for(str(blender_version_min))

        platforms = _parse_platforms(cfg.get("platforms"), release)
        website = cfg.get("website") or _homepage(project)
        permissions = cfg.get("permissions")
        if permissions is not None:
            if not isinstance(permissions, dict):
                raise ConfigurationError("tool.extbpy.permissions must be a table")
            bad = [k for k in permissions if k not in _VALID_PERMISSIONS]
            if bad:
                raise ConfigurationError(
                    f"Unknown permissions {bad}; valid keys: {', '.join(_VALID_PERMISSIONS)}"
                )

        blender_version_max = cfg.get("blender_version_max")
        if blender_version_max is not None:
            parse_blender_version(str(blender_version_max))

        resolved_package_dir = _find_package_dir(
            source_dir, ext_id, package_dir or cfg.get("package_dir")
        )

        return cls(
            source_dir=source_dir,
            package_dir=resolved_package_dir,
            id=ext_id,
            version=str(version),
            name=str(cfg.get("pretty_name") or project_name),
            tagline=str(tagline),
            maintainer=maintainer,
            license=license_value,
            blender_version_min=str(blender_version_min),
            blender_version_max=str(blender_version_max)
            if blender_version_max
            else None,
            release=release,
            platforms=platforms,
            website=website,
            copyright=_str_tuple(cfg.get("copyright"), "tool.extbpy.copyright"),
            tags=_str_tuple(cfg.get("tags", cfg.get("bl_tags")), "tool.extbpy.tags"),
            permissions=dict(permissions) if permissions else None,
            min_glibc_version=_version_pair(
                cfg.get("min_glibc_version"), "min_glibc_version"
            ),
            min_macos_version=_version_pair(
                cfg.get("min_macos_version"), "min_macos_version"
            ),
            exclude_packages=frozenset(
                packaging.utils.canonicalize_name(n)
                for n in _str_tuple(
                    cfg.get("exclude_packages"), "tool.extbpy.exclude_packages"
                )
                or ()
            ),
            extras=tuple(
                packaging.utils.canonicalize_name(e)
                for e in _str_tuple(cfg.get("extras"), "tool.extbpy.extras") or ()
            ),
            paths_exclude_pattern=DEFAULT_PATHS_EXCLUDE_PATTERN
            + (
                _str_tuple(
                    cfg.get("paths_exclude_pattern"),
                    "tool.extbpy.paths_exclude_pattern",
                )
                or ()
            ),
            required_files=_str_tuple(
                cfg.get("required_files"), "tool.extbpy.required_files"
            )
            or (),
        )


# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------
def _format_validation(e: pydantic.ValidationError) -> str:
    return "\n".join(
        f"  - {'.'.join(str(p) for p in err['loc']) or 'manifest'}: {err['msg']}"
        for err in e.errors()
    )


def _str_tuple(value: Any, label: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigurationError(f"{label} must be a list of strings")
    return tuple(value)


def _version_pair(value: Any, label: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.split(".")
    try:
        parts = [int(v) for v in value]
    except (TypeError, ValueError):
        parts = []
    if len(parts) != 2:
        raise ConfigurationError(
            f"tool.extbpy.{label} must be [MAJOR, MINOR], got {value!r}"
        )
    return (parts[0], parts[1])


def _parse_license(
    project: dict[str, Any], cfg: dict[str, Any], errors: list[str]
) -> tuple[str, ...]:
    override = cfg.get("license")
    if override is not None:
        if isinstance(override, str):
            override = [override]
        return tuple(v if v.startswith("SPDX:") else f"SPDX:{v}" for v in override)
    value = project.get("license")
    if isinstance(value, dict):
        value = value.get("text")
    if not isinstance(value, str) or not value.strip():
        errors.append(
            'project.license must be an SPDX expression string, e.g. license = "GPL-3.0-or-later"'
        )
        return ()
    return (f"SPDX:{value.strip()}",)


def _parse_maintainer(
    project: dict[str, Any], cfg: dict[str, Any], errors: list[str]
) -> str:
    if cfg.get("maintainer"):
        return str(cfg["maintainer"])
    people = project.get("maintainers") or project.get("authors") or []
    if not people or not isinstance(people, list) or not isinstance(people[0], dict):
        errors.append(
            "project.maintainers (or project.authors) must list at least one person"
        )
        return ""
    person = people[0]
    name, email = person.get("name"), person.get("email")
    if name and email:
        return f"{name} <{email}>"
    return str(name or email)


def _homepage(project: dict[str, Any]) -> str | None:
    urls = project.get("urls")
    if not isinstance(urls, dict):
        return None
    for key, value in urls.items():
        if key.lower() == "homepage" and isinstance(value, str):
            return value
    return None


def _parse_platforms(value: Any, release: BLRelease) -> tuple[BLPlatform, ...]:
    if value is None:
        return tuple(sorted(release.platforms))
    platforms = tuple(
        BLPlatform.parse(str(v))
        for v in _str_tuple(value, "tool.extbpy.platforms") or ()
    )
    if not platforms:
        raise ConfigurationError("tool.extbpy.platforms must not be empty")
    unsupported = [p for p in platforms if p not in release.platforms]
    if unsupported:
        raise ConfigurationError(
            f"Blender {release.pretty_version} does not ship for "
            f"{', '.join(p.value for p in unsupported)}. "
            f"Supported: {', '.join(sorted(p.value for p in release.platforms))}"
        )
    return platforms


def _find_package_dir(source_dir: Path, ext_id: str, override: Any) -> Path:
    candidates: list[Path]
    if override is not None:
        p = Path(str(override))
        candidates = [p if p.is_absolute() else source_dir / p]
    else:
        candidates = [source_dir / ext_id, source_dir / "src" / ext_id]
    for candidate in candidates:
        if (candidate / "__init__.py").is_file():
            return candidate.resolve()
    tried = ", ".join(str(c) for c in candidates)
    raise ConfigurationError(
        f"Could not find the extension package (a directory with __init__.py). Tried: {tried}. "
        "Set tool.extbpy.package_dir to point at it."
    )
