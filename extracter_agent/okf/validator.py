"""OKF v0.2 Bundle Validation Engine.

Verifies conformance to Open Knowledge Format v0.2 standards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from extracter_agent.models.okf import derive_trust_tier
from extracter_agent.okf.document import OKFDocument, OKFDocumentError


class OKFValidationError(Exception):
    pass


def validate_okf_document(doc_path: Path | str) -> dict[str, Any]:
    """Validate a single OKF document file.

    Returns a dict with validation status, errors, warnings, and trust tier.
    """
    path = Path(doc_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return {
            "valid": False,
            "file": str(path),
            "errors": ["File not found"],
            "warnings": [],
        }

    try:
        text = path.read_text(encoding="utf-8")
        doc = OKFDocument.parse(text)
    except OKFDocumentError as e:
        return {"valid": False, "file": str(path), "errors": [str(e)], "warnings": []}
    except Exception as e:
        return {
            "valid": False,
            "file": str(path),
            "errors": [f"Read error: {e}"],
            "warnings": [],
        }

    # OKF v0.2 §11: type is required
    doc_type = doc.frontmatter.get("type")
    if not doc_type or not str(doc_type).strip():
        errors.append("Missing required frontmatter key: 'type'")

    # Validate sources
    sources = doc.frontmatter.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            errors.append("'sources' must be a YAML list")
        else:
            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    errors.append(f"sources[{idx}] must be a mapping")
                elif not src.get("resource"):
                    errors.append(
                        f"sources[{idx}] is missing required 'resource' field"
                    )

    # Validate generated
    generated = doc.frontmatter.get("generated")
    if generated is not None and (
        not isinstance(generated, dict) or not generated.get("by")
    ):
        errors.append("'generated' must be a mapping with a 'by' actor string")

    trust_tier = derive_trust_tier(doc.frontmatter)

    return {
        "valid": len(errors) == 0,
        "file": str(path),
        "type": str(doc_type or ""),
        "trust_tier": trust_tier,
        "errors": errors,
        "warnings": warnings,
    }


def validate_okf_bundle(bundle_dir: Path | str) -> dict[str, Any]:
    """Validate all documents in an OKF bundle directory."""
    root = Path(bundle_dir)
    if not root.exists():
        return {
            "valid": False,
            "bundle_dir": str(root),
            "total_documents": 0,
            "errors": [f"Directory does not exist: {root}"],
            "trust_tiers": {},
        }

    results: list[dict[str, Any]] = []
    trust_tiers: dict[str, int] = {
        "human-reviewed": 0,
        "machine-confirmed": 0,
        "unverified": 0,
    }
    all_errors: list[dict[str, Any]] = []

    for md_file in root.rglob("*.md"):
        if md_file.name in ("index.md", "log.md"):
            continue

        res = validate_okf_document(md_file)
        results.append(res)
        tier = res.get("trust_tier", "unverified")
        trust_tiers[tier] = trust_tiers.get(tier, 0) + 1

        if not res["valid"]:
            all_errors.append(
                {"file": str(md_file.relative_to(root)), "errors": res["errors"]}
            )

    # Check root index.md
    has_root_index = (root / "index.md").exists()
    has_root_log = (root / "log.md").exists()

    is_valid = len(all_errors) == 0 and has_root_index

    return {
        "valid": is_valid,
        "bundle_dir": str(root),
        "total_documents": len(results),
        "has_root_index": has_root_index,
        "has_root_log": has_root_log,
        "trust_tiers": trust_tiers,
        "errors": all_errors,
    }
