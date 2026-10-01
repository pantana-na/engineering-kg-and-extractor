"""OKF v0.2 Document model and serializer/deserializer.

Implements Open Knowledge Format v0.2 §4 and §11 specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

_FRONTMATTER_DELIM = "---"
REQUIRED_FRONTMATTER_KEYS = ("type",)


class _TimestampPreservingLoader(yaml.SafeLoader):
    """SafeLoader preserving timestamps as strings matching YAML 1.2 core schema."""


# Remove PyYAML's automatic conversion of ISO strings to python datetimes
_TimestampPreservingLoader.yaml_implicit_resolvers = {
    ch: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:timestamp"
    ]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class _OKFSafeDumper(yaml.SafeDumper):
    """SafeDumper guaranteeing round-trip string integrity without unintentional scalar coercion."""


def _str_representer(dumper: Any, data: str) -> Any:
    style = None
    if any(data.endswith(ch) for ch in (" ", "\t", "\xa0")) or any(
        data.startswith(ch) for ch in (" ", "\t", "\xa0")
    ) or data.lower() in ("true", "false", "yes", "no", "null", "~") or data.isdigit():
        style = '"'
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_OKFSafeDumper.add_representer(str, _str_representer)


class OKFDocumentError(ValueError):
    """Error in OKF document formatting or validation."""



@dataclass
class OKFDocument:
    """Represents an Open Knowledge Format (OKF v0.2) concept document."""

    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @classmethod
    def parse(cls, text: str) -> OKFDocument:
        """Parse a markdown file containing YAML frontmatter into an OKFDocument."""
        lines = text.split("\n")
        if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
            return cls(frontmatter={}, body=text)

        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == _FRONTMATTER_DELIM:
                end_idx = i
                break

        if end_idx is None:
            raise OKFDocumentError("Unterminated YAML frontmatter block in document")

        fm_text = "\n".join(lines[1:end_idx])
        try:
            fm = yaml.load(fm_text, Loader=_TimestampPreservingLoader) or {}  # nosec B506: Inherits from yaml.SafeLoader
        except yaml.YAMLError as e:
            raise OKFDocumentError(f"Invalid YAML syntax in frontmatter: {e}") from e

        if not isinstance(fm, dict):
            raise OKFDocumentError("Frontmatter must be a YAML mapping")

        body = "\n".join(lines[end_idx + 1 :])
        body = body.removeprefix("\n")
        return cls(frontmatter=fm, body=body)

    def serialize(self) -> str:
        """Serialize the OKF document to a standard markdown string with frontmatter."""
        fm_text = yaml.dump(
            self.frontmatter,
            Dumper=_OKFSafeDumper,
            sort_keys=False,
            allow_unicode=True,
        ).rstrip()
        body_clean = self.body if self.body.endswith("\n") else self.body + "\n"
        return f"{_FRONTMATTER_DELIM}\n{fm_text}\n{_FRONTMATTER_DELIM}\n\n{body_clean}"


    def validate(self) -> None:
        """Validate against OKF v0.2 §11 conformance."""
        for req in REQUIRED_FRONTMATTER_KEYS:
            if not self.frontmatter.get(req):
                raise OKFDocumentError(f"Missing required frontmatter key: '{req}'")
