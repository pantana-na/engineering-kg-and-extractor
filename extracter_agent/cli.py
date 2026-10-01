"""Command-line interface and batch execution engine for the Extracter Agent.

Supports extracting raw PDFs, compiling OKF v0.2 bundles, and publishing to GCS.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from extracter_agent.config import get_config
from extracter_agent.okf.validator import validate_okf_bundle
from extracter_agent.tools.gcs_tools import export_bundle_to_gcs_tool
from extracter_agent.tools.okf_tools import (
    build_okf_indexes_and_validate_tool,
    generate_equipment_okf_tool,
)


def run_batch_extraction(
    output_dir: Path | str | None = None,
    publish_gcs: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Execute batch extraction on reference/raw documents and compile an OKF v0.2 bundle."""
    cfg = get_config()
    target_dir = Path(output_dir) if output_dir else cfg.output_bundle_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Starting knowledge extraction pipeline into: {target_dir}")

    from extracter_agent.pdf.processor import (
        extract_equipment_tag_candidates,
        extract_pdf_pages,
        get_pdf_metadata,
    )

    ds_dir = cfg.reference_raw_dir / "data_sheets"
    if ds_dir.exists() and not any((target_dir / "equipment").glob("*.md")):
        for pdf_file in sorted(ds_dir.glob("*.pdf"))[:3]:
            meta = get_pdf_metadata(pdf_file)
            pages = extract_pdf_pages(pdf_file)
            text = "\n".join(p.get("text", "") for p in pages)
            candidates = extract_equipment_tag_candidates(f"{pdf_file.name} {text}")
            tag = candidates[0] if candidates else pdf_file.stem.split("_")[0]
            lines = [ln.strip() for ln in text.splitlines() if ":" in ln or "mm" in ln][:8]
            design_rows = [
                {
                    "parameter": f"Extracted Specification {idx + 1}",
                    "value": ln[:80],
                    "unit": "—",
                    "source": pdf_file.name,
                }
                for idx, ln in enumerate(lines)
            ] or [
                {
                    "parameter": "Document Page Count",
                    "value": str(meta.get("page_count", 1)),
                    "unit": "pages",
                    "source": pdf_file.name,
                }
            ]
            generate_equipment_okf_tool(
                tag=tag,
                name=str(meta.get("title") or pdf_file.stem),
                equipment_class="Equipment",
                unit="PLANT",
                function_summary=f"Dynamically extracted from {pdf_file.name}.",
                design_data=design_rows,
                operating_conditions=[],
                connections=[],
                hazards=[],
                source_files=[f"data_sheets/{pdf_file.name}"],
                output_bundle_dir=str(target_dir),
            )

    # 2. Build OKF progressive disclosure indexes
    print("[2/4] Generating OKF progressive disclosure indexes (index.md & log.md)...")
    idx_res = build_okf_indexes_and_validate_tool(bundle_dir=str(target_dir))
    print(
        f"  Generated {idx_res['total_indexes']} index files. Valid OKF: {idx_res['is_valid_okf']}"
    )

    # 3. Validate bundle
    print("[3/4] Validating bundle conformance against OKF v0.2...")
    val_res = validate_okf_bundle(target_dir)
    print(
        f"  Total concepts: {val_res['total_documents']}. Trust tiers: {val_res['trust_tiers']}"
    )

    # 4. Export to GCS
    gcs_res: dict[str, Any] = {}
    if publish_gcs:
        print(
            f"[4/4] Publishing bundle to Google Cloud Storage ({cfg.destination_gcs_bucket})..."
        )
        gcs_res = export_bundle_to_gcs_tool(
            bundle_dir=str(target_dir),
            destination_bucket=cfg.destination_gcs_bucket,
            destination_prefix=cfg.destination_gcs_prefix,
            dry_run=dry_run,
        )
        print(
            f"  Uploaded {gcs_res['files_count']} objects to {gcs_res['destination_root_uri']} (dry_run={dry_run})."
        )
    else:
        print("[4/4] Skipping GCS upload (run with --publish-gcs to upload).")

    return {
        "bundle_dir": str(target_dir),
        "validation": val_res,
        "gcs_export": gcs_res,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extracter Agent Batch Pipeline")
    parser.add_argument(
        "--out", type=str, default=None, help="Output OKF bundle directory"
    )
    parser.add_argument(
        "--publish-gcs", action="store_true", help="Publish bundle to GCS"
    )
    parser.add_argument(
        "--live-gcs", action="store_true", help="Perform live GCS upload (not dry run)"
    )
    args = parser.parse_args()

    res = run_batch_extraction(
        output_dir=args.out,
        publish_gcs=args.publish_gcs,
        dry_run=not args.live_gcs,
    )
    print("\nExtraction & OKF Compilation Summary:")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
