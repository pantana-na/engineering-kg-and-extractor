"""Automated Dataplex Universal Catalog (`dataplex_v1`) & GCP OpenLineage API Sync Engine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from query_agent.config import get_config
from query_agent.models.schemas import CatalogSyncReport

logger = logging.getLogger(__name__)


def _to_dataplex_id(raw_id: str) -> str:
    """Normalize an identifier to Dataplex Universal Catalog resource ID syntax ([a-z][a-z0-9-]*[a-z0-9])."""
    cleaned = (raw_id or "").strip().lower().replace("_", "-")
    return cleaned or "okf-default"


class DataplexCatalogAndLineageSync:
    """Synchronizes OKF Knowledge Graph & Bundle metadata to Google Cloud Dataplex Universal Catalog & Lineage API."""

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        entry_group_id: str | None = None,
        tag_template_id: str | None = None,
    ) -> None:
        cfg = get_config()
        self.project_id = project_id or cfg.google_cloud_project
        raw_loc = location or cfg.google_cloud_location
        self.location = "asia-southeast1" if raw_loc == "global" else raw_loc
        self.catalog_location = self.location
        self.entry_group_id = entry_group_id or cfg.dataplex_entry_group_id
        self.tag_template_id = tag_template_id or cfg.dataplex_tag_template_id
        self.dataplex_entry_group_id = _to_dataplex_id(self.entry_group_id)
        self.dataplex_aspect_type_id = _to_dataplex_id(self.tag_template_id)
        self.dataplex_entry_type_id = "okf-knowledge-asset"
        self.spanner_instance_id = cfg.spanner_instance_id
        self.spanner_database_id = cfg.spanner_database_id
        self.gcs_bucket = cfg.destination_gcs_bucket
        self.okf_prefix = cfg.destination_gcs_prefix

    def sync_catalog_and_lineage(
        self,
        extraction_summary: dict[str, Any],
        dry_run: bool = False,
    ) -> CatalogSyncReport:
        """Create or update Dataplex Universal Catalog EntryGroup, AspectType, EntryType, Entries, and OpenLineage Run Events."""
        total_concepts = int(extraction_summary.get("total_concepts", 0))
        total_entities = int(extraction_summary.get("total_entities", 0))
        total_assertions = int(extraction_summary.get("total_assertions", 0))
        total_conflicts = int(extraction_summary.get("total_conflicts", 0))
        total_lineage_edges = int(extraction_summary.get("total_lineage_edges", 0))
        domain_profile = str(extraction_summary.get("domain_profile", "process_manufacturing_plant"))

        entries_synced = 3
        lineage_events_emitted = 2
        status = "SYNCED_DRY_RUN" if dry_run else "SYNCED_LIVE"

        if not dry_run:
            entries_synced = self._sync_dataplex_entries(
                total_concepts=total_concepts,
                total_entities=total_entities,
                total_assertions=total_assertions,
                total_conflicts=total_conflicts,
                total_lineage_edges=total_lineage_edges,
                domain_profile=domain_profile,
            )
            lineage_events_emitted = self._emit_openlineage_events()

        return CatalogSyncReport(
            entry_group_id=self.entry_group_id,
            tag_template_id=self.tag_template_id,
            entries_synced=entries_synced,
            lineage_events_emitted=lineage_events_emitted,
            total_concepts=total_concepts,
            total_entities=total_entities,
            total_assertions=total_assertions,
            total_conflicts=total_conflicts,
            total_lineage_edges=total_lineage_edges,
            status=status,
        )

    def purge_catalog_entries(
        self,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Delete all governed OKF entries in Dataplex Universal Catalog EntryGroup before a clean re-ingestion."""
        eg_parent = (
            f"projects/{self.project_id}/locations/{self.catalog_location}/"
            f"entryGroups/{self.dataplex_entry_group_id}"
        )
        deleted_entries: list[str] = []
        system_eg_entry_suffix = f"/entries/{self.dataplex_entry_group_id}_entry"
        if not dry_run:
            from google.api_core import exceptions as gcp_exceptions
            from google.cloud import dataplex_v1

            client = dataplex_v1.CatalogServiceClient()
            try:
                existing_entries = list(client.list_entries(parent=eg_parent))
                for entry in existing_entries:
                    if entry.name.endswith(system_eg_entry_suffix):
                        continue
                    client.delete_entry(name=entry.name)
                    deleted_entries.append(entry.name)
            except gcp_exceptions.NotFound:
                deleted_entries = []

        return {
            "entry_group": eg_parent,
            "deleted_entries": deleted_entries,
            "deleted_count": len(deleted_entries),
            "status": "PURGED_DRY_RUN" if dry_run else "PURGED_LIVE",
        }

    def inspect_catalog_state(
        self,
        live_counts: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Inspect current Dataplex Universal Catalog governance aspects and OpenLineage pipeline topology."""
        now_iso = datetime.now(timezone.utc).isoformat()
        spanner_fqn = (
            f"spanner:{self.project_id}.regional-{self.location}."
            f"{self.spanner_instance_id}.{self.spanner_database_id}"
        )
        gcs_bundle_fqn = f"gcs:{self.gcs_bucket}.{self.okf_prefix}"
        gcs_raw_fqn = f"gcs:{self.gcs_bucket}.raw-engineering-docs"

        live_dataplex_entry_names: list[str] = []
        system_eg_entry_suffix = f"/entries/{self.dataplex_entry_group_id}_entry"
        if not dry_run:
            from google.api_core import exceptions as gcp_exceptions
            from google.cloud import dataplex_v1

            client = dataplex_v1.CatalogServiceClient()
            eg_parent = (
                f"projects/{self.project_id}/locations/{self.catalog_location}/"
                f"entryGroups/{self.dataplex_entry_group_id}"
            )
            try:
                for entry in client.list_entries(parent=eg_parent):
                    if not entry.name.endswith(system_eg_entry_suffix):
                        live_dataplex_entry_names.append(entry.name)
            except gcp_exceptions.NotFound:
                live_dataplex_entry_names = []

        catalog_entries = [
            {
                "entry_id": "okf_spanner_knowledge_graph",
                "dataplex_entry_name": (
                    f"projects/{self.project_id}/locations/{self.catalog_location}/"
                    f"entryGroups/{self.dataplex_entry_group_id}/entries/okf-spanner-knowledge-graph"
                ),
                "fully_qualified_name": spanner_fqn,
                "linked_resource": (
                    f"//spanner.googleapis.com/projects/{self.project_id}/instances/"
                    f"{self.spanner_instance_id}/databases/{self.spanner_database_id}"
                ),
                "display_name": "OKF Spanner Knowledge Graph, Vector & Lineage DB",
                "governance_tags": {
                    "template": self.tag_template_id,
                    "aspect_type": self.dataplex_aspect_type_id,
                    "domain_profile": "process_manufacturing_plant",
                    "okf_version": "3.0-spanner-graph",
                    "total_concepts": live_counts.get("total_concepts", 0),
                    "total_entities": live_counts.get("total_entities", 0),
                    "total_fact_assertions": live_counts.get("total_assertions", 0),
                    "conflict_count": live_counts.get("total_conflicts", 0),
                    "total_lineage_edges": live_counts.get("total_lineage_edges", 0),
                    "source_doc_count": live_counts.get("total_source_docs", 0),
                    "embedding_model": "text-embedding-005 (768-d COSINE)",
                    "last_synced_at": now_iso,
                },
            },
            {
                "entry_id": "okf_gcs_markdown_bundle_v3",
                "dataplex_entry_name": (
                    f"projects/{self.project_id}/locations/{self.catalog_location}/"
                    f"entryGroups/{self.dataplex_entry_group_id}/entries/okf-gcs-markdown-bundle-v3"
                ),
                "fully_qualified_name": gcs_bundle_fqn,
                "linked_resource": f"//storage.googleapis.com/{self.gcs_bucket}/{self.okf_prefix}",
                "display_name": "OKF Equipment-Centric Markdown Bundle V3",
                "governance_tags": {
                    "template": self.tag_template_id,
                    "aspect_type": self.dataplex_aspect_type_id,
                    "domain_profile": "process_manufacturing_plant",
                    "okf_version": "3.0",
                    "total_concepts": live_counts.get("total_concepts", 0),
                },
            },
            {
                "entry_id": "raw_engineering_docs_archive",
                "dataplex_entry_name": (
                    f"projects/{self.project_id}/locations/{self.catalog_location}/"
                    f"entryGroups/{self.dataplex_entry_group_id}/entries/raw-engineering-docs-archive"
                ),
                "fully_qualified_name": gcs_raw_fqn,
                "linked_resource": f"//storage.googleapis.com/{self.gcs_bucket}/reference/raw",
                "display_name": "Immutable Raw Engineering PDFs (Datasheets, P&IDs, Manuals, Standards)",
                "governance_tags": {
                    "template": self.tag_template_id,
                    "aspect_type": self.dataplex_aspect_type_id,
                    "source_doc_count": live_counts.get("total_source_docs", 0),
                    "immutability_policy": "READ_ONLY_ENFORCED",
                },
            },
        ]

        openlineage_topology = [
            {
                "process_name": "extracter_agent_synthesis_v3",
                "source_fqn": gcs_raw_fqn,
                "target_fqn": gcs_bundle_fqn,
                "description": "Autonomous multimodal synthesis of raw PDFs into 150 OKF Markdown files with inline provenance citations.",
            },
            {
                "process_name": "okf_spanner_graph_and_lineage_ingestion",
                "source_fqn": gcs_bundle_fqn,
                "target_fqn": spanner_fqn,
                "description": (
                    "Automated extraction of Spanner Graph nodes/edges, 768-d text-embedding-005 vectors, "
                    "TOKENLIST full-text indexes, and claim-level DERIVED_FROM FactLineageEdges."
                ),
            },
        ]

        return {
            "project_id": self.project_id,
            "location": self.location,
            "entry_group_id": self.entry_group_id,
            "tag_template_id": self.tag_template_id,
            "entry_group": (
                f"projects/{self.project_id}/locations/{self.catalog_location}/"
                f"entryGroups/{self.dataplex_entry_group_id}"
            ),
            "aspect_type": (
                f"projects/{self.project_id}/locations/{self.catalog_location}/"
                f"aspectTypes/{self.dataplex_aspect_type_id}"
            ),
            "entry_type": (
                f"projects/{self.project_id}/locations/{self.catalog_location}/"
                f"entryTypes/{self.dataplex_entry_type_id}"
            ),
            "live_dataplex_entries": live_dataplex_entry_names,
            "catalog_entries": catalog_entries,
            "openlineage_pipeline_topology": openlineage_topology,
            "live_spanner_metrics": live_counts,
        }

    def _sync_dataplex_entries(
        self,
        total_concepts: int,
        total_entities: int,
        total_assertions: int,
        total_conflicts: int,
        total_lineage_edges: int,
        domain_profile: str,
    ) -> int:
        from google.api_core import exceptions as gcp_exceptions
        from google.cloud import dataplex_v1
        from google.protobuf import struct_pb2

        client = dataplex_v1.CatalogServiceClient()
        parent = f"projects/{self.project_id}/locations/{self.catalog_location}"
        eg_name = f"{parent}/entryGroups/{self.dataplex_entry_group_id}"
        at_name = f"{parent}/aspectTypes/{self.dataplex_aspect_type_id}"
        et_name = f"{parent}/entryTypes/{self.dataplex_entry_type_id}"

        # 1. Ensure EntryGroup exists
        try:
            client.get_entry_group(name=eg_name)
        except gcp_exceptions.NotFound:
            op = client.create_entry_group(
                parent=parent,
                entry_group_id=self.dataplex_entry_group_id,
                entry_group=dataplex_v1.EntryGroup(
                    display_name="OKF Knowledge Assets & Spanner Graph",
                    description="Automated Dataplex Universal Catalog group for OKF Markdown bundles, Spanner Graph, and Raw Engineering PDFs",
                ),
            )
            op.result(timeout=60)

        # 2. Ensure AspectType exists
        try:
            client.get_aspect_type(name=at_name)
        except gcp_exceptions.NotFound:
            record_fields = [
                dataplex_v1.AspectType.MetadataTemplate(index=1, name="domain_profile", type_="string"),
                dataplex_v1.AspectType.MetadataTemplate(index=2, name="total_concepts", type_="int"),
                dataplex_v1.AspectType.MetadataTemplate(index=3, name="total_entities", type_="int"),
                dataplex_v1.AspectType.MetadataTemplate(index=4, name="total_assertions", type_="int"),
                dataplex_v1.AspectType.MetadataTemplate(index=5, name="conflict_count", type_="int"),
                dataplex_v1.AspectType.MetadataTemplate(index=6, name="total_lineage_edges", type_="int"),
            ]
            op = client.create_aspect_type(
                parent=parent,
                aspect_type_id=self.dataplex_aspect_type_id,
                aspect_type=dataplex_v1.AspectType(
                    display_name="OKF Governance & Lineage Template",
                    description="Governance metrics for OKF Spanner Graph & Bundles",
                    metadata_template=dataplex_v1.AspectType.MetadataTemplate(
                        name="OkfGovernanceTemplate",
                        type_="record",
                        record_fields=record_fields,
                    ),
                ),
            )
            op.result(timeout=60)

        # 3. Ensure EntryType exists
        try:
            client.get_entry_type(name=et_name)
        except gcp_exceptions.NotFound:
            op = client.create_entry_type(
                parent=parent,
                entry_type_id=self.dataplex_entry_type_id,
                entry_type=dataplex_v1.EntryType(
                    display_name="OKF Knowledge Asset",
                    description="Governed OKF Knowledge Graph, Markdown Bundle, or Raw PDF Archive",
                ),
            )
            op.result(timeout=60)

        # 4. Upsert all 3 governed Entries with Aspect metadata
        aspect_key = f"{self.project_id}.{self.catalog_location}.{self.dataplex_aspect_type_id}"
        aspect_struct = struct_pb2.Struct()
        aspect_struct.update(
            {
                "domain_profile": domain_profile,
                "total_concepts": int(total_concepts),
                "total_entities": int(total_entities),
                "total_assertions": int(total_assertions),
                "conflict_count": int(total_conflicts),
                "total_lineage_edges": int(total_lineage_edges),
            }
        )

        entries_spec = [
            (
                "okf-spanner-knowledge-graph",
                f"spanner:{self.project_id}.regional-{self.location}.{self.spanner_instance_id}.{self.spanner_database_id}",
                f"//spanner.googleapis.com/projects/{self.project_id}/instances/{self.spanner_instance_id}/databases/{self.spanner_database_id}",
                "cloud_spanner",
                "OKF Spanner Knowledge Graph, Vector & Lineage DB",
                (
                    f"Spanner Graph & Vector DB ({total_concepts} concepts, {total_entities} entities, "
                    f"{total_assertions} assertions, {total_conflicts} conflicts, {total_lineage_edges} lineage edges)"
                ),
            ),
            (
                "okf-gcs-markdown-bundle-v3",
                f"gcs:{self.gcs_bucket}.{self.okf_prefix}",
                f"//storage.googleapis.com/{self.gcs_bucket}/{self.okf_prefix}",
                "cloud_storage",
                "OKF Equipment-Centric Markdown Bundle V3",
                f"OKF Markdown Bundle V3 ({total_concepts} concepts)",
            ),
            (
                "raw-engineering-docs-archive",
                f"gcs:{self.gcs_bucket}.raw-engineering-docs",
                f"//storage.googleapis.com/{self.gcs_bucket}/reference/raw",
                "cloud_storage",
                "Immutable Raw Engineering PDFs (Datasheets, P&IDs, Manuals, Standards)",
                "Immutable raw engineering PDF source archive",
            ),
        ]

        synced_count = 0
        for entry_id, fqn, resource_uri, system_name, disp_name, desc in entries_spec:
            entry_name = f"{eg_name}/entries/{entry_id}"
            entry = dataplex_v1.Entry(
                name=entry_name,
                entry_type=et_name,
                fully_qualified_name=fqn,
                entry_source=dataplex_v1.EntrySource(
                    resource=resource_uri,
                    system=system_name,
                    platform="GCP",
                    display_name=disp_name,
                    description=desc,
                ),
                aspects={
                    aspect_key: dataplex_v1.Aspect(
                        aspect_type=at_name,
                        data=aspect_struct,
                    )
                },
            )
            try:
                client.get_entry(name=entry_name)
                client.update_entry(entry=entry)
            except gcp_exceptions.NotFound:
                client.create_entry(parent=eg_name, entry_id=entry_id, entry=entry)
            synced_count += 1

        return synced_count

    def _emit_openlineage_events(self) -> int:
        from google.cloud.datacatalog_lineage_v1 import LineageClient

        client = LineageClient()
        parent = f"projects/{self.project_id}/locations/{self.location}"
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        bucket_ns = f"gs://{self.gcs_bucket}"

        events = [
            {
                "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
                "eventType": "COMPLETE",
                "eventTime": now_iso,
                "run": {"runId": "018f5a00-0000-7000-8000-000000000002"},
                "job": {
                    "namespace": self.project_id,
                    "name": "extracter_agent_synthesis_v3",
                },
                "producer": "https://github.com/openlineage/OpenLineage/tree/1.0.0/client/python",
                "inputs": [{"namespace": bucket_ns, "name": "reference/raw"}],
                "outputs": [{"namespace": bucket_ns, "name": self.okf_prefix}],
            },
            {
                "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
                "eventType": "COMPLETE",
                "eventTime": now_iso,
                "run": {"runId": "018f5a00-0000-7000-8000-000000000003"},
                "job": {
                    "namespace": self.project_id,
                    "name": "okf_spanner_graph_and_lineage_ingestion",
                },
                "producer": "https://github.com/openlineage/OpenLineage/tree/1.0.0/client/python",
                "inputs": [{"namespace": bucket_ns, "name": self.okf_prefix}],
                "outputs": [
                    {
                        "namespace": bucket_ns,
                        "name": f"spanner-{self.spanner_instance_id}-{self.spanner_database_id}",
                    }
                ],
            },
        ]
        import time

        emitted = 0
        for ev in events:
            for attempt in range(3):
                try:
                    client.process_open_lineage_run_event(
                        request={"parent": parent, "open_lineage": ev}
                    )
                    emitted += 1
                    break
                except Exception as exc:
                    if attempt < 2:
                        time.sleep(1.0 * (attempt + 1))
                    else:
                        logger.warning("OpenLineage event emission warning after retries: %s", exc)
        return emitted

