"""A validated model of ``blender_manifest.toml`` (schema 1.0.0).

Validation mirrors what ``blender --command extension validate`` checks, so a
manifest generated here is accepted by Blender without surprises.
"""

from __future__ import annotations

import re
from typing import Literal

import pydantic

from .bl_platform import BLPlatform

_RE_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
_RE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RE_COPYRIGHT = re.compile(r"^\d{4}(-\d{4})? .+$")

PermissionKey = Literal["files", "network", "clipboard", "camera", "microphone"]


def _stripped_non_empty(value: str, field: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field} must not have leading or trailing whitespace")
    if not value:
        raise ValueError(f"{field} must not be empty")
    if any(ch in value for ch in "\n\r\t"):
        raise ValueError(f"{field} must not contain control characters")
    return value


def _terse(value: str, field: str) -> str:
    value = _stripped_non_empty(value, field)
    if len(value) > 64:
        raise ValueError(f"{field} must be at most 64 characters")
    if value[-1] in ".!?":
        raise ValueError(f"{field} must not end with punctuation")
    return value


def _toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class BLManifest(pydantic.BaseModel, frozen=True):
    schema_version: Literal["1.0.0"] = "1.0.0"
    id: str
    version: str
    name: str
    tagline: str
    maintainer: str
    type: Literal["add-on", "theme"] = "add-on"
    blender_version_min: str
    blender_version_max: str | None = None
    website: str | None = None
    platforms: tuple[BLPlatform, ...] | None = None
    tags: tuple[str, ...] | None = None
    license: tuple[str, ...]
    copyright: tuple[str, ...] | None = None
    permissions: dict[PermissionKey, str] | None = None
    wheels: tuple[str, ...] | None = None

    @pydantic.field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _RE_ID.match(value):
            raise ValueError(f"id '{value}' must be a valid Python identifier")
        if value.startswith("_") or value.endswith("_") or "__" in value:
            raise ValueError(f"id '{value}' must not start/end with or contain '__'")
        return value

    @pydantic.field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if not _RE_SEMVER.match(value):
            raise ValueError(f"version '{value}' is not a valid semantic version")
        return value

    @pydantic.field_validator("blender_version_min", "blender_version_max")
    @classmethod
    def _validate_bl_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Blender version '{value}' must be 'MAJOR.MINOR.PATCH'")
        if (int(parts[0]), int(parts[1])) < (4, 2):
            raise ValueError("Blender extensions require Blender 4.2 or newer")
        return value

    @pydantic.field_validator("name", "maintainer", "website")
    @classmethod
    def _validate_plain(
        cls, value: str | None, info: pydantic.ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _stripped_non_empty(value, info.field_name or "field")

    @pydantic.field_validator("tagline")
    @classmethod
    def _validate_tagline(cls, value: str) -> str:
        return _terse(value, "tagline")

    @pydantic.field_validator("permissions")
    @classmethod
    def _validate_permissions(
        cls, value: dict[PermissionKey, str] | None
    ) -> dict[PermissionKey, str] | None:
        if value is None:
            return None
        return {k: _terse(v, f"permissions.{k}") for k, v in value.items()}

    @pydantic.field_validator("license", "tags")
    @classmethod
    def _validate_str_list(
        cls, value: tuple[str, ...] | None, info: pydantic.ValidationInfo
    ) -> tuple[str, ...] | None:
        if value is None:
            return None
        if info.field_name == "license" and not value:
            raise ValueError("license must list at least one SPDX identifier")
        for item in value:
            _stripped_non_empty(item, info.field_name or "field")
        return value

    @pydantic.field_validator("copyright")
    @classmethod
    def _validate_copyright(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is None:
            return None
        for item in value:
            if not _RE_COPYRIGHT.match(item):
                raise ValueError(
                    f"copyright entry '{item}' must look like 'YEAR Name' or 'YEAR-YEAR Name'"
                )
        return value

    @pydantic.field_validator("wheels")
    @classmethod
    def _validate_wheels(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        for item in value:
            if '"' in item or "\\" in item:
                raise ValueError(
                    f"wheel path '{item}' must not contain quotes or backslashes"
                )
            if not item.lower().endswith(".whl"):
                raise ValueError(f"wheel path '{item}' must end with .whl")
            if item.rsplit("/", 1)[-1].count("-") not in (4, 5):
                raise ValueError(f"'{item}' is not a valid wheel filename")
        return value

    def to_toml(self) -> str:
        """Render as TOML in the layout Blender's own template uses."""
        lines: list[str] = []

        def scalar(key: str, value: str) -> None:
            lines.append(f"{key} = {_toml_str(value)}")

        def array(key: str, values: tuple[str, ...] | list[str]) -> None:
            if not values:
                lines.append(f"{key} = []")
                return
            lines.append(f"{key} = [")
            for v in values:
                lines.append(f"    {_toml_str(v)},")
            lines.append("]")

        scalar("schema_version", self.schema_version)
        scalar("id", self.id)
        scalar("version", self.version)
        scalar("name", self.name)
        scalar("tagline", self.tagline)
        scalar("maintainer", self.maintainer)
        scalar("type", self.type)
        if self.website is not None:
            scalar("website", self.website)
        if self.tags is not None:
            array("tags", self.tags)
        scalar("blender_version_min", self.blender_version_min)
        if self.blender_version_max is not None:
            scalar("blender_version_max", self.blender_version_max)
        array("license", self.license)
        if self.copyright is not None:
            array("copyright", self.copyright)
        if self.platforms is not None:
            array("platforms", [p.value for p in self.platforms])
        if self.wheels is not None:
            array("wheels", self.wheels)
        if self.permissions:
            lines.append("")
            lines.append("[permissions]")
            for key, value in self.permissions.items():
                scalar(key, value)
        return "\n".join(lines) + "\n"
