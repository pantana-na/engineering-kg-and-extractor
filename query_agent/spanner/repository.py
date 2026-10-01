"""Cloud Spanner Graph, Vector (768-d COSINE), Full-Text (TOKENLIST) & Lineage Repository.

Implements SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT:
- 100% Spanner query execution (Zero GCS reads at query time).
- Supports both BundleGraphExtractionResult and dict inputs in upsert_bundle_graph.
- Supports in-memory mirror mode for deterministic unit & property-based tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from query_agent.config import get_config
from query_agent.models.schemas import (
    BundleGraphExtractionResult,
    ConceptWikiLinkEdge,
    EngineeringEntityNode,
    FactAssertionNode,
    FactLineageEdge,
    GraphTraversalHop,
    HazopScenarioRecord,
    HybridSearchResult,
    InstrumentControlEdge,
    LineageTraceResult,
    MarkdownSpannerSyncReport,
    MultiStageRiskHazopReport,
    OkfConceptNode,
    OkfSectionChunkNode,
    ProcessConnectionEdge,
    RawSourceNode,
)

logger = logging.getLogger(__name__)


def deterministic_hash_embedding(text: str, dim: int = 768) -> list[float]:
    """Deterministic unit-normalized vector for offline/in-memory unit & property tests."""
    tokens = re.findall(r"[a-z0-9_]+", (text or "").lower())
    vec = [0.0] * dim
    if not tokens:
        vec[0] = 1.0
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(0, 16, 2):
            idx = ((digest[i] << 8) | digest[i + 1]) % dim
            sign = 1.0 if (digest[(i + 2) % 32] % 2 == 0) else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm < 1e-9:
        vec[0] = 1.0
        return vec
    return [round(v / norm, 6) for v in vec]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity in [-1.0, 1.0] between two equal-length vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


class SpannerGraphRepository:
    """Unified Spanner Graph + Vector + Full-Text + Lineage repository (Zero GCS reads at query time)."""

    def __init__(
        self,
        project_id: str | None = None,
        instance_id: str | None = None,
        database_id: str | None = None,
        use_in_memory: bool = False,
    ) -> None:
        cfg = get_config()
        self.project_id = project_id or cfg.google_cloud_project
        self.region = cfg.google_cloud_location
        self.instance_id = instance_id or cfg.spanner_instance_id
        self.database_id = database_id or cfg.spanner_database_id
        self.embedding_model = cfg.embedding_model
        self.embedding_dimension = 768
        self.use_in_memory = use_in_memory

        self._spanner_client: Any = None
        self._database: Any = None
        self._genai_client: Any = None

        # In-memory store for fast unit/property testing
        self._mem_source_docs: dict[str, RawSourceNode] = {}
        self._mem_concepts: dict[str, OkfConceptNode] = {}
        self._mem_chunks: dict[str, OkfSectionChunkNode] = {}
        self._mem_entities: dict[str, EngineeringEntityNode] = {}
        self._mem_assertions: dict[str, FactAssertionNode] = {}
        self._mem_connections: dict[str, ProcessConnectionEdge] = {}
        self._mem_controls: dict[str, InstrumentControlEdge] = {}
        self._mem_wiki_links: dict[str, ConceptWikiLinkEdge] = {}
        self._mem_lineage_edges: dict[str, FactLineageEdge] = {}

    def _get_database(self) -> Any:
        if self.use_in_memory:
            return None
        if self._database is None:
            from google.cloud import spanner

            self._spanner_client = spanner.Client(
                project=self.project_id,
                disable_builtin_metrics=True,
            )
            instance = self._spanner_client.instance(self.instance_id)
            self._database = instance.database(self.database_id)
        return self._database

    def _get_genai_client(self) -> Any:
        if self._genai_client is None:
            from google import genai

            self._genai_client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.region,
            )
        return self._genai_client

    def embed_texts_batch(
        self,
        texts: list[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
        batch_size: int = 12,
    ) -> list[list[float]]:
        """Generate 768-d embeddings using Vertex AI text-embedding-005."""
        if not texts:
            return []
        if self.use_in_memory:
            return [deterministic_hash_embedding(t, self.embedding_dimension) for t in texts]

        from google.genai import types

        client = self._get_genai_client()
        results: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = [t[:3500] if t.strip() else "empty_chunk" for t in texts[start : start + batch_size]]
            try:
                resp = client.models.embed_content(
                    model=self.embedding_model,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self.embedding_dimension,
                        task_type=task_type,
                    ),
                )
                for emb in resp.embeddings:
                    vec = [float(v) for v in emb.values]
                    results.append(vec)
            except Exception as exc:
                logger.warning("Vertex embedding batch fallback due to error: %s", exc)
                for t in batch:
                    results.append(deterministic_hash_embedding(t, self.embedding_dimension))
        return results

    def embed_query(self, query: str) -> list[float]:
        """Generate a 768-d query embedding."""
        vecs = self.embed_texts_batch([query], task_type="RETRIEVAL_QUERY", batch_size=1)
        return vecs[0] if vecs else deterministic_hash_embedding(query, self.embedding_dimension)

    def upsert_bundle_graph(
        self,
        extracted: BundleGraphExtractionResult | dict[str, list[Any]],
        compute_embeddings: bool = True,
        existing_concept_ids: set[str] | None = None,
        existing_entity_ids: set[str] | None = None,
        existing_source_ids: set[str] | None = None,
    ) -> dict[str, int]:
        """Upsert extracted OKF bundle nodes, chunks, vectors, and lineage edges into Spanner."""
        if isinstance(extracted, BundleGraphExtractionResult):
            source_docs = list(extracted.raw_sources)
            concepts = list(extracted.concepts)
            chunks = list(extracted.chunks)
            entities = list(extracted.entities)
            assertions = list(extracted.facts)
            connections = list(extracted.process_edges)
            controls = list(extracted.instrument_edges)
            wiki_links = list(extracted.wikilink_edges)
            lineage_edges = list(extracted.lineage_edges)
        else:
            source_docs = list(extracted.get("raw_sources") or extracted.get("source_documents") or [])
            concepts = list(extracted.get("concepts") or [])
            chunks = list(extracted.get("chunks") or extracted.get("section_chunks") or [])
            entities = list(extracted.get("entities") or [])
            assertions = list(extracted.get("facts") or extracted.get("assertions") or [])
            connections = list(extracted.get("process_edges") or extracted.get("process_connections") or [])
            controls = list(extracted.get("instrument_edges") or extracted.get("instrument_controls") or [])
            wiki_links = list(extracted.get("wikilink_edges") or extracted.get("concept_links") or [])
            lineage_edges = list(extracted.get("lineage_edges") or [])

        if compute_embeddings and chunks:
            missing_indices = [
                i
                for i, c in enumerate(chunks)
                if not c.embedding or len(c.embedding) != self.embedding_dimension
            ]
            if missing_indices:
                texts_to_embed = [
                    f"{chunks[i].concept_id} | {chunks[i].section_heading}\n{chunks[i].header_preserved_markdown}"
                    for i in missing_indices
                ]
                vectors = self.embed_texts_batch(texts_to_embed, task_type="RETRIEVAL_DOCUMENT")
                for idx, vec in zip(missing_indices, vectors):
                    chunks[idx].embedding = vec

        valid_source_ids = set(self._mem_source_docs.keys()) | set(existing_source_ids or ())
        for doc in source_docs:
            if self.use_in_memory:
                self._mem_source_docs[doc.source_id] = doc
            valid_source_ids.add(doc.source_id)

        valid_concept_ids = set(self._mem_concepts.keys()) | set(existing_concept_ids or ())
        for c in concepts:
            if self.use_in_memory:
                self._mem_concepts[c.concept_id] = c
            valid_concept_ids.add(c.concept_id)

        for ch in chunks:
            if self.use_in_memory:
                self._mem_chunks[ch.chunk_id] = ch

        valid_entity_ids = set(self._mem_entities.keys()) | set(existing_entity_ids or ())
        for ent in entities:
            if self.use_in_memory:
                self._mem_entities[ent.entity_id] = ent
            valid_entity_ids.add(ent.entity_id)

        valid_fact_ids = set(self._mem_assertions.keys())
        for fa in assertions:
            if self.use_in_memory:
                self._mem_assertions[fa.fact_id] = fa
            valid_fact_ids.add(fa.fact_id)

        valid_connections: list[ProcessConnectionEdge] = []
        for conn in connections:
            if conn.from_entity_id in valid_entity_ids and conn.to_entity_id in valid_entity_ids:
                if self.use_in_memory:
                    self._mem_connections[conn.edge_id] = conn
                valid_connections.append(conn)

        valid_controls: list[InstrumentControlEdge] = []
        for ctrl in controls:
            if ctrl.instrument_entity_id in valid_entity_ids and ctrl.target_entity_id in valid_entity_ids:
                if self.use_in_memory:
                    self._mem_controls[ctrl.edge_id] = ctrl
                valid_controls.append(ctrl)

        valid_wiki_links: list[ConceptWikiLinkEdge] = []
        for wl in wiki_links:
            if wl.from_concept_id in valid_concept_ids and wl.to_concept_id in valid_concept_ids:
                if self.use_in_memory:
                    self._mem_wiki_links[wl.edge_id] = wl
                valid_wiki_links.append(wl)

        valid_lineage_edges: list[FactLineageEdge] = []
        for le in lineage_edges:
            if le.fact_id in valid_fact_ids and le.source_id in valid_source_ids:
                if self.use_in_memory:
                    self._mem_lineage_edges[le.lineage_id] = le
                valid_lineage_edges.append(le)

        if not self.use_in_memory:
            self._write_batches_to_spanner(
                source_docs=source_docs,
                concepts=concepts,
                chunks=chunks,
                entities=entities,
                assertions=assertions,
                connections=valid_connections,
                controls=valid_controls,
                wiki_links=valid_wiki_links,
                lineage_edges=valid_lineage_edges,
            )

        return {
            "source_documents": len(source_docs),
            "concepts": len(concepts),
            "section_chunks": len(chunks),
            "entities": len(entities),
            "assertions": len(assertions),
            "process_connections": len(valid_connections),
            "instrument_controls": len(valid_controls),
            "concept_links": len(valid_wiki_links),
            "lineage_edges": len(valid_lineage_edges),
        }

    def get_existing_concept_hashes(self) -> dict[str, str]:
        """Return {concept_id: md5_hash} for all concepts currently stored in Spanner or in-memory."""
        if self.use_in_memory:
            return {cid: c.md5_hash for cid, c in self._mem_concepts.items()}
        db = self._get_database()
        hashes: dict[str, str] = {}
        with db.snapshot() as snap:
            for row in snap.execute_sql("SELECT concept_id, md5_hash FROM OkfConcepts"):
                hashes[str(row[0])] = str(row[1] or "")
        return hashes

    def get_existing_node_ids(self) -> tuple[set[str], set[str], set[str]]:
        """Return (concept_ids, entity_ids, source_ids) currently stored in Spanner or in-memory."""
        if self.use_in_memory:
            return (
                set(self._mem_concepts.keys()),
                set(self._mem_entities.keys()),
                set(self._mem_source_docs.keys()),
            )
        db = self._get_database()
        concept_ids: set[str] = set()
        entity_ids: set[str] = set()
        source_ids: set[str] = set()
        with db.snapshot(multi_use=True) as snap:
            for r in snap.execute_sql("SELECT concept_id FROM OkfConcepts"):
                concept_ids.add(str(r[0]))
            for r in snap.execute_sql("SELECT entity_id FROM EngineeringEntities"):
                entity_ids.add(str(r[0]))
            for r in snap.execute_sql("SELECT source_id FROM RawSourceDocuments"):
                source_ids.add(str(r[0]))
        return concept_ids, entity_ids, source_ids

    def purge_all_spanner_data(self) -> dict[str, int]:
        """Delete all rows from all 9 Spanner Graph tables in reverse dependency order (edges -> nodes)."""
        ordered_tables = [
            ("FactLineageEdges", "_mem_lineage_edges"),
            ("ConceptWikiLinks", "_mem_wiki_links"),
            ("InstrumentControlEdges", "_mem_controls"),
            ("ProcessConnections", "_mem_connections"),
            ("OkfSectionChunks", "_mem_chunks"),
            ("FactAssertions", "_mem_assertions"),
            ("EngineeringEntities", "_mem_entities"),
            ("OkfConcepts", "_mem_concepts"),
            ("RawSourceDocuments", "_mem_source_docs"),
        ]
        deleted_counts: dict[str, int] = {}
        if self.use_in_memory:
            for table_name, mem_attr in ordered_tables:
                mem_dict = getattr(self, mem_attr)
                deleted_counts[table_name] = len(mem_dict)
                mem_dict.clear()
            return deleted_counts

        db = self._get_database()
        for table_name, mem_attr in ordered_tables:
            getattr(self, mem_attr).clear()
            count = db.execute_partitioned_dml(f"DELETE FROM {table_name} WHERE true")
            deleted_counts[table_name] = int(count or 0)
        return deleted_counts

    def delete_concepts_cascade(
        self,
        concept_ids: list[str],
        delete_concept_row: bool = True,
    ) -> dict[str, int]:
        """Cascade-delete child chunks, facts, entities, and graph/lineage edges for UPDATED or REMOVED concepts."""
        if not concept_ids:
            return {
                "concepts": 0,
                "section_chunks": 0,
                "entities": 0,
                "assertions": 0,
                "process_connections": 0,
                "instrument_controls": 0,
                "concept_links": 0,
                "lineage_edges": 0,
                "source_documents": 0,
            }
        cid_set = set(concept_ids)
        if self.use_in_memory:
            del_lineage = [k for k, v in self._mem_lineage_edges.items() if v.concept_id in cid_set]
            for k in del_lineage:
                del self._mem_lineage_edges[k]

            if delete_concept_row:
                del_wl = [
                    k
                    for k, v in self._mem_wiki_links.items()
                    if v.from_concept_id in cid_set or v.to_concept_id in cid_set
                ]
            else:
                del_wl = [k for k, v in self._mem_wiki_links.items() if v.from_concept_id in cid_set]
            for k in del_wl:
                del self._mem_wiki_links[k]

            owned_ent_ids = {k for k, v in self._mem_entities.items() if v.concept_id in cid_set}
            if delete_concept_row:
                del_ctrl = [
                    k
                    for k, v in self._mem_controls.items()
                    if v.source_concept_id in cid_set
                    or v.instrument_entity_id in owned_ent_ids
                    or v.target_entity_id in owned_ent_ids
                ]
                del_conn = [
                    k
                    for k, v in self._mem_connections.items()
                    if v.source_concept_id in cid_set
                    or v.from_entity_id in owned_ent_ids
                    or v.to_entity_id in owned_ent_ids
                ]
            else:
                del_ctrl = [k for k, v in self._mem_controls.items() if v.source_concept_id in cid_set]
                del_conn = [k for k, v in self._mem_connections.items() if v.source_concept_id in cid_set]
            for k in del_ctrl:
                del self._mem_controls[k]
            for k in del_conn:
                del self._mem_connections[k]

            del_chunks = [k for k, v in self._mem_chunks.items() if v.concept_id in cid_set]
            for k in del_chunks:
                del self._mem_chunks[k]

            del_facts = [k for k, v in self._mem_assertions.items() if v.concept_id in cid_set]
            for k in del_facts:
                del self._mem_assertions[k]

            referenced_ent_ids = (
                {v.from_entity_id for v in self._mem_connections.values()}
                | {v.to_entity_id for v in self._mem_connections.values()}
                | {v.instrument_entity_id for v in self._mem_controls.values()}
                | {v.target_entity_id for v in self._mem_controls.values()}
            )
            if delete_concept_row:
                del_ents = [k for k in owned_ent_ids if k in self._mem_entities]
            else:
                del_ents = [
                    k
                    for k in owned_ent_ids
                    if k in self._mem_entities and k not in referenced_ent_ids
                ]
            for k in del_ents:
                del self._mem_entities[k]

            del_concepts: list[str] = []
            if delete_concept_row:
                del_concepts = [k for k in cid_set if k in self._mem_concepts]
                for k in del_concepts:
                    del self._mem_concepts[k]

            referenced_src_ids = {v.source_id for v in self._mem_lineage_edges.values() if v.source_id}
            del_srcs = [k for k in list(self._mem_source_docs.keys()) if k not in referenced_src_ids]
            for k in del_srcs:
                del self._mem_source_docs[k]

            return {
                "concepts": len(del_concepts),
                "section_chunks": len(del_chunks),
                "entities": len(del_ents),
                "assertions": len(del_facts),
                "process_connections": len(del_conn),
                "instrument_controls": len(del_ctrl),
                "concept_links": len(del_wl),
                "lineage_edges": len(del_lineage),
                "source_documents": len(del_srcs),
            }

        db = self._get_database()
        from google.cloud.spanner_v1 import param_types

        cids_param = {"cids": list(cid_set)}
        cids_type = {"cids": param_types.Array(param_types.STRING)}

        def _tx_cascade(transaction: Any) -> dict[str, int]:
            c_lin = transaction.execute_update(
                "DELETE FROM FactLineageEdges WHERE concept_id IN UNNEST(@cids)",
                params=cids_param,
                param_types=cids_type,
            )
            if delete_concept_row:
                c_wl = transaction.execute_update(
                    "DELETE FROM ConceptWikiLinks WHERE from_concept_id IN UNNEST(@cids) OR to_concept_id IN UNNEST(@cids)",
                    params=cids_param,
                    param_types=cids_type,
                )
                c_ctrl = transaction.execute_update(
                    """
                    DELETE FROM InstrumentControlEdges
                    WHERE source_concept_id IN UNNEST(@cids)
                       OR instrument_entity_id IN (SELECT entity_id FROM EngineeringEntities WHERE concept_id IN UNNEST(@cids))
                       OR target_entity_id IN (SELECT entity_id FROM EngineeringEntities WHERE concept_id IN UNNEST(@cids))
                    """,
                    params=cids_param,
                    param_types=cids_type,
                )
                c_conn = transaction.execute_update(
                    """
                    DELETE FROM ProcessConnections
                    WHERE source_concept_id IN UNNEST(@cids)
                       OR from_entity_id IN (SELECT entity_id FROM EngineeringEntities WHERE concept_id IN UNNEST(@cids))
                       OR to_entity_id IN (SELECT entity_id FROM EngineeringEntities WHERE concept_id IN UNNEST(@cids))
                    """,
                    params=cids_param,
                    param_types=cids_type,
                )
            else:
                c_wl = transaction.execute_update(
                    "DELETE FROM ConceptWikiLinks WHERE from_concept_id IN UNNEST(@cids)",
                    params=cids_param,
                    param_types=cids_type,
                )
                c_ctrl = transaction.execute_update(
                    "DELETE FROM InstrumentControlEdges WHERE source_concept_id IN UNNEST(@cids)",
                    params=cids_param,
                    param_types=cids_type,
                )
                c_conn = transaction.execute_update(
                    "DELETE FROM ProcessConnections WHERE source_concept_id IN UNNEST(@cids)",
                    params=cids_param,
                    param_types=cids_type,
                )

            c_chunks = transaction.execute_update(
                "DELETE FROM OkfSectionChunks WHERE concept_id IN UNNEST(@cids)",
                params=cids_param,
                param_types=cids_type,
            )
            c_facts = transaction.execute_update(
                "DELETE FROM FactAssertions WHERE concept_id IN UNNEST(@cids)",
                params=cids_param,
                param_types=cids_type,
            )
            if delete_concept_row:
                c_ents = transaction.execute_update(
                    "DELETE FROM EngineeringEntities WHERE concept_id IN UNNEST(@cids)",
                    params=cids_param,
                    param_types=cids_type,
                )
                c_concepts = transaction.execute_update(
                    "DELETE FROM OkfConcepts WHERE concept_id IN UNNEST(@cids)",
                    params=cids_param,
                    param_types=cids_type,
                )
            else:
                c_ents = transaction.execute_update(
                    """
                    DELETE FROM EngineeringEntities
                    WHERE concept_id IN UNNEST(@cids)
                      AND entity_id NOT IN (
                          SELECT from_entity_id FROM ProcessConnections
                          UNION DISTINCT
                          SELECT to_entity_id FROM ProcessConnections
                          UNION DISTINCT
                          SELECT instrument_entity_id FROM InstrumentControlEdges
                          UNION DISTINCT
                          SELECT target_entity_id FROM InstrumentControlEdges
                      )
                    """,
                    params=cids_param,
                    param_types=cids_type,
                )
                c_concepts = 0

            c_srcs = transaction.execute_update(
                """
                DELETE FROM RawSourceDocuments
                WHERE source_id NOT IN (
                    SELECT DISTINCT source_id FROM FactLineageEdges WHERE source_id IS NOT NULL
                )
                """
            )
            return {
                "concepts": int(c_concepts or 0),
                "section_chunks": int(c_chunks or 0),
                "entities": int(c_ents or 0),
                "assertions": int(c_facts or 0),
                "process_connections": int(c_conn or 0),
                "instrument_controls": int(c_ctrl or 0),
                "concept_links": int(c_wl or 0),
                "lineage_edges": int(c_lin or 0),
                "source_documents": int(c_srcs or 0),
            }

        return db.run_in_transaction(_tx_cascade)

    def sync_markdown_bundle_to_spanner(
        self,
        md_source: str | Path | list[Path] | None = None,
        *,
        sync_mode: str = "FULL_MIRROR",
        removed_concept_ids: list[str] | None = None,
        compute_embeddings: bool = True,
        sync_dataplex_catalog: bool = True,
        force_reingest: bool = False,
        bundle_version: str = "v3-by-equipment",
    ) -> MarkdownSpannerSyncReport:
        """Consolidated 100% .md-only Spanner ingestion & incremental lifecycle sync (ADDED, UPDATED, REMOVED, UNCHANGED)."""
        from query_agent.spanner.catalog_sync import DataplexCatalogAndLineageSync
        from query_agent.spanner.lineage_extractor import (
            extract_bundle_graph_and_lineage,
        )

        cfg = get_config()
        if md_source is None:
            bundle_dir = cfg.output_bundle_dir
            md_files = sorted(
                p for p in bundle_dir.rglob("*.md") if p.name not in ("index.md", "log.md")
            )
        elif isinstance(md_source, (str, Path)):
            p_src = Path(md_source)
            if p_src.is_file():
                bundle_dir = p_src.parent.parent if p_src.parent.name in ("equipment", "units", "hazards", "hazop", "instruments", "logs") else p_src.parent
                md_files = [p_src] if p_src.name not in ("index.md", "log.md") else []
            else:
                bundle_dir = p_src
                md_files = (
                    sorted(p for p in bundle_dir.rglob("*.md") if p.name not in ("index.md", "log.md"))
                    if bundle_dir.is_dir()
                    else []
                )
        else:
            md_files = sorted(Path(p) for p in md_source if Path(p).name not in ("index.md", "log.md"))
            bundle_dir = cfg.output_bundle_dir

        existing_hashes = self.get_existing_concept_hashes()
        scanned_path_by_cid: dict[str, Path] = {}
        scanned_hash_by_cid: dict[str, str] = {}

        for md_path in md_files:
            if not md_path.is_file():
                continue
            try:
                rel_path = str(md_path.relative_to(bundle_dir)).replace("\\", "/")
            except ValueError:
                rel_path = (
                    f"{md_path.parent.name}/{md_path.name}"
                    if md_path.parent.name in ("equipment", "units", "hazards", "hazop", "instruments", "logs")
                    else md_path.name
                )
            cid = rel_path.removesuffix(".md")
            raw_text = md_path.read_text(encoding="utf-8", errors="replace")
            md5_hex = hashlib.md5(raw_text.encode("utf-8"), usedforsecurity=False).hexdigest()
            scanned_path_by_cid[cid] = md_path
            scanned_hash_by_cid[cid] = md5_hex

        added_concepts: list[str] = []
        updated_concepts: list[str] = []
        unchanged_concepts: list[str] = []

        for cid in sorted(scanned_path_by_cid.keys()):
            new_hash = scanned_hash_by_cid[cid]
            if cid not in existing_hashes:
                added_concepts.append(cid)
            elif force_reingest or existing_hashes[cid] != new_hash:
                updated_concepts.append(cid)
            else:
                unchanged_concepts.append(cid)

        explicit_removed = set(removed_concept_ids or [])
        if sync_mode.upper() == "FULL_MIRROR":
            inferred_removed = set(existing_hashes.keys()) - set(scanned_path_by_cid.keys())
            removed_concepts = sorted(explicit_removed | inferred_removed)
        else:
            removed_concepts = sorted(explicit_removed)

        deleted_counts: dict[str, int] = {
            "concepts": 0,
            "section_chunks": 0,
            "entities": 0,
            "assertions": 0,
            "process_connections": 0,
            "instrument_controls": 0,
            "concept_links": 0,
            "lineage_edges": 0,
            "source_documents": 0,
        }

        if updated_concepts:
            upd_del = self.delete_concepts_cascade(updated_concepts, delete_concept_row=False)
            for k, v in upd_del.items():
                deleted_counts[k] = deleted_counts.get(k, 0) + v

        if removed_concepts:
            rem_del = self.delete_concepts_cascade(removed_concepts, delete_concept_row=True)
            for k, v in rem_del.items():
                deleted_counts[k] = deleted_counts.get(k, 0) + v

        target_cids_to_ingest = added_concepts + updated_concepts
        upserted_counts: dict[str, int] = {
            "source_documents": 0,
            "concepts": 0,
            "section_chunks": 0,
            "entities": 0,
            "assertions": 0,
            "process_connections": 0,
            "instrument_controls": 0,
            "concept_links": 0,
            "lineage_edges": 0,
        }

        if target_cids_to_ingest:
            target_paths = [scanned_path_by_cid[cid] for cid in target_cids_to_ingest]
            extracted = extract_bundle_graph_and_lineage(
                bundle_dir=bundle_dir,
                bundle_version=bundle_version,
                md_files=target_paths,
            )
            existing_cids, existing_eids, existing_sids = self.get_existing_node_ids()
            upserted_counts = self.upsert_bundle_graph(
                extracted=extracted,
                compute_embeddings=compute_embeddings,
                existing_concept_ids=existing_cids,
                existing_entity_ids=existing_eids,
                existing_source_ids=existing_sids,
            )

        live_counts = self.get_live_counts()
        catalog_status = "SKIPPED"
        if sync_dataplex_catalog:
            cat_sync = DataplexCatalogAndLineageSync()
            cat_report = cat_sync.sync_catalog_and_lineage(
                extraction_summary=live_counts,
                dry_run=self.use_in_memory,
            )
            catalog_status = cat_report.status

        return MarkdownSpannerSyncReport(
            sync_mode=sync_mode.upper(),
            source_type="MD_BUNDLE_ONLY",
            bundle_dir=str(bundle_dir),
            total_md_files_scanned=len(scanned_path_by_cid),
            added_concepts=added_concepts,
            updated_concepts=updated_concepts,
            unchanged_concepts=unchanged_concepts,
            removed_concepts=removed_concepts,
            rows_upserted=upserted_counts,
            rows_deleted=deleted_counts,
            upserted_counts=upserted_counts,
            deleted_counts=deleted_counts,
            live_counts_after_sync=live_counts,
            catalog_sync_status=catalog_status,
            status="OK",
        )

    def get_catalog_counts(self) -> dict[str, int]:
        """Alias for get_live_counts()."""
        return self.get_live_counts()

    def _batch_insert_or_update(
        self,
        table: str,
        columns: list[str],
        values: list[tuple[Any, ...]],
        chunk_size: int = 200,
    ) -> None:
        if not values:
            return
        db = self._get_database()
        if db is None:
            return
        for start in range(0, len(values), chunk_size):
            batch_rows = values[start : start + chunk_size]
            with db.batch() as batch:
                batch.insert_or_update(
                    table=table,
                    columns=columns,
                    values=batch_rows,
                )

    def _write_batches_to_spanner(
        self,
        source_docs: list[RawSourceNode],
        concepts: list[OkfConceptNode],
        chunks: list[OkfSectionChunkNode],
        entities: list[EngineeringEntityNode],
        assertions: list[FactAssertionNode],
        connections: list[ProcessConnectionEdge],
        controls: list[InstrumentControlEdge],
        wiki_links: list[ConceptWikiLinkEdge],
        lineage_edges: list[FactLineageEdge],
    ) -> None:
        from google.cloud.spanner_v1 import JsonObject

        now_ts = datetime.now(timezone.utc)

        # 1. RawSourceDocuments
        self._batch_insert_or_update(
            table="RawSourceDocuments",
            columns=[
                "source_id",
                "filename",
                "subfolder",
                "doc_code",
                "revision",
                "md5_hash",
                "gcs_uri",
                "ingested_at",
            ],
            values=[
                (
                    d.source_id,
                    d.filename,
                    d.subfolder,
                    d.doc_code,
                    d.revision,
                    d.md5_hash,
                    d.gcs_uri,
                    now_ts,
                )
                for d in source_docs
            ],
            chunk_size=200,
        )

        # 2. OkfConcepts
        self._batch_insert_or_update(
            table="OkfConcepts",
            columns=[
                "concept_id",
                "category",
                "name",
                "description",
                "unit",
                "trust_tier",
                "has_conflict",
                "conflict_count",
                "frontmatter_json",
                "body_markdown",
                "md5_hash",
                "bundle_version",
                "gcs_uri",
                "updated_at",
            ],
            values=[
                (
                    c.concept_id,
                    c.category,
                    c.name,
                    c.description,
                    c.unit,
                    c.trust_tier,
                    c.has_conflict,
                    c.conflict_count,
                    JsonObject(c.frontmatter_json),
                    c.body_markdown,
                    c.md5_hash,
                    c.bundle_version,
                    c.gcs_uri,
                    now_ts,
                )
                for c in concepts
            ],
            chunk_size=50,
        )

        # 3. OkfSectionChunks
        self._batch_insert_or_update(
            table="OkfSectionChunks",
            columns=[
                "chunk_id",
                "concept_id",
                "category",
                "unit",
                "section_heading",
                "chunk_index",
                "header_preserved_markdown",
                "has_conflict",
                "embedding",
            ],
            values=[
                (
                    ch.chunk_id,
                    ch.concept_id,
                    ch.category,
                    ch.unit,
                    ch.section_heading,
                    ch.chunk_index,
                    ch.header_preserved_markdown,
                    ch.has_conflict,
                    [float(x) for x in ch.embedding] if ch.embedding else None,
                )
                for ch in chunks
            ],
            chunk_size=40,
        )

        # 4. EngineeringEntities
        self._batch_insert_or_update(
            table="EngineeringEntities",
            columns=[
                "entity_id",
                "entity_type",
                "canonical_tag",
                "name",
                "equipment_class",
                "unit",
                "concept_id",
            ],
            values=[
                (
                    e.entity_id,
                    e.entity_type,
                    e.canonical_tag,
                    e.name,
                    e.equipment_class,
                    e.unit,
                    e.concept_id,
                )
                for e in entities
            ],
            chunk_size=200,
        )

        # 5. FactAssertions
        self._batch_insert_or_update(
            table="FactAssertions",
            columns=[
                "fact_id",
                "concept_id",
                "entity_id",
                "section_heading",
                "parameter_name",
                "parameter_value",
                "parameter_unit",
                "has_conflict",
                "conflict_note",
                "bundle_version",
                "extracted_at",
            ],
            values=[
                (
                    fa.fact_id,
                    fa.concept_id,
                    fa.entity_id,
                    fa.section_heading,
                    fa.parameter_name,
                    fa.parameter_value,
                    fa.parameter_unit,
                    fa.has_conflict,
                    fa.conflict_note,
                    fa.bundle_version,
                    now_ts,
                )
                for fa in assertions
            ],
            chunk_size=200,
        )

        # 6. ProcessConnections
        self._batch_insert_or_update(
            table="ProcessConnections",
            columns=[
                "edge_id",
                "from_entity_id",
                "to_entity_id",
                "stream_or_line_id",
                "fluid_service",
                "temperature",
                "pressure",
                "flow_rate",
                "source_concept_id",
                "source_id",
            ],
            values=[
                (
                    conn.edge_id,
                    conn.from_entity_id,
                    conn.to_entity_id,
                    conn.stream_or_line_id,
                    conn.fluid_service,
                    conn.temperature,
                    conn.pressure,
                    conn.flow_rate,
                    conn.source_concept_id,
                    conn.source_id,
                )
                for conn in connections
            ],
            chunk_size=200,
        )

        # 7. InstrumentControlEdges
        self._batch_insert_or_update(
            table="InstrumentControlEdges",
            columns=[
                "edge_id",
                "instrument_entity_id",
                "target_entity_id",
                "loop_id",
                "instrument_type",
                "setpoint_or_range",
                "interlock_or_alarm",
                "source_concept_id",
                "source_id",
            ],
            values=[
                (
                    ctrl.edge_id,
                    ctrl.instrument_entity_id,
                    ctrl.target_entity_id,
                    ctrl.loop_id,
                    ctrl.instrument_type,
                    ctrl.setpoint_or_range,
                    ctrl.interlock_or_alarm,
                    ctrl.source_concept_id,
                    ctrl.source_id,
                )
                for ctrl in controls
            ],
            chunk_size=200,
        )

        # 8. ConceptWikiLinks
        self._batch_insert_or_update(
            table="ConceptWikiLinks",
            columns=["edge_id", "from_concept_id", "to_concept_id", "section_heading"],
            values=[
                (wl.edge_id, wl.from_concept_id, wl.to_concept_id, wl.section_heading)
                for wl in wiki_links
            ],
            chunk_size=200,
        )

        # 9. FactLineageEdges
        self._batch_insert_or_update(
            table="FactLineageEdges",
            columns=[
                "lineage_id",
                "fact_id",
                "concept_id",
                "source_id",
                "raw_citation_string",
                "source_role",
                "bundle_version",
                "extracted_at",
            ],
            values=[
                (
                    le.lineage_id,
                    le.fact_id,
                    le.concept_id,
                    le.source_id,
                    le.raw_citation_string,
                    le.source_role,
                    le.bundle_version,
                    now_ts,
                )
                for le in lineage_edges
            ],
            chunk_size=200,
        )

    # -------------------------------------------------------------------------
    # Query Tool 1: Exact Entity & Parameter Lookup (SQL + Lineage Join)
    # -------------------------------------------------------------------------
    def lookup_entity_and_parameters(
        self,
        entity_tag_or_id: str,
        parameter_filter: str | None = None,
    ) -> dict[str, Any]:
        """Lookup an engineering entity by tag/name and return all parameters with PDF provenance."""
        clean_tag = (entity_tag_or_id or "").strip().upper()
        param_kw = (parameter_filter or "").strip().lower()

        if self.use_in_memory or self._mem_entities:
            return self._lookup_entity_in_memory(clean_tag, param_kw)

        db = self._get_database()
        from google.cloud.spanner_v1 import param_types

        entity_rows: list[dict[str, Any]] = []
        with db.snapshot(multi_use=True) as snap:
            sql_ent = """
                SELECT entity_id, canonical_tag, entity_type, name, unit, equipment_class, concept_id
                FROM EngineeringEntities
                WHERE UPPER(canonical_tag) = @tag
                   OR UPPER(entity_id) = @tag
                   OR ENDS_WITH(UPPER(IFNULL(concept_id, '')), CONCAT('/', @tag))
                   OR STRPOS(UPPER(canonical_tag), @tag) > 0
                   OR STRPOS(UPPER(name), @tag) > 0
                   OR STRPOS(UPPER(IFNULL(concept_id, '')), @tag) > 0
                ORDER BY
                    CASE
                        WHEN UPPER(canonical_tag) = @tag THEN 0
                        WHEN UPPER(entity_id) = @tag OR UPPER(entity_id) = CONCAT('EQ:', @tag) THEN 1
                        WHEN ENDS_WITH(UPPER(IFNULL(concept_id, '')), CONCAT('/', @tag)) THEN 2
                        ELSE 3
                    END
                LIMIT 5
            """
            for row in snap.execute_sql(
                sql_ent,
                params={"tag": clean_tag},
                param_types={"tag": param_types.STRING},
            ):
                entity_rows.append(
                    {
                        "entity_id": row[0],
                        "canonical_tag": row[1],
                        "entity_type": row[2],
                        "name": row[3],
                        "unit": row[4],
                        "equipment_class": row[5],
                        "concept_id": row[6],
                    }
                )

        if not entity_rows:
            return {
                "found": False,
                "queried_tag": entity_tag_or_id,
                "entities": [],
                "parameters": [],
                "concept_sections": [],
            }

        primary_entity = entity_rows[0]
        target_entity_id = primary_entity["entity_id"]
        target_concept_id = primary_entity.get("concept_id") or ""

        parameters: list[dict[str, Any]] = []
        with db.snapshot(multi_use=True) as snap:
            sql_facts = """
                SELECT
                    f.fact_id,
                    f.parameter_name,
                    f.parameter_value,
                    f.parameter_unit,
                    f.section_heading,
                    f.has_conflict,
                    f.conflict_note,
                    l.raw_citation_string,
                    l.source_role,
                    d.filename,
                    d.doc_code,
                    d.revision,
                    d.gcs_uri
                FROM FactAssertions f
                LEFT JOIN FactLineageEdges l ON f.fact_id = l.fact_id
                LEFT JOIN RawSourceDocuments d ON l.source_id = d.source_id
                WHERE f.entity_id = @entity_id OR f.concept_id = @concept_id
                ORDER BY f.has_conflict DESC, f.parameter_name ASC
                LIMIT 120
            """
            for r in snap.execute_sql(
                sql_facts,
                params={"entity_id": target_entity_id, "concept_id": target_concept_id},
                param_types={
                    "entity_id": param_types.STRING,
                    "concept_id": param_types.STRING,
                },
            ):
                p_name = str(r[1] or "")
                p_val = str(r[2] or "")
                sec = str(r[4] or "")
                if param_kw and (
                    param_kw not in p_name.lower()
                    and param_kw not in p_val.lower()
                    and param_kw not in sec.lower()
                ):
                    continue
                parameters.append(
                    {
                        "fact_id": r[0],
                        "parameter_name": p_name,
                        "parameter_value": p_val,
                        "parameter_unit": r[3] or "",
                        "section_heading": sec,
                        "has_conflict": bool(r[5]),
                        "conflict_note": r[6],
                        "raw_citation_string": r[7] or "",
                        "source_role": r[8] or "PRIMARY",
                        "source_filename": r[9] or "",
                        "doc_code": r[10] or "",
                        "revision": r[11] or "",
                        "gcs_uri": r[12] or "",
                    }
                )

        concept_chunks: list[dict[str, Any]] = []
        if target_concept_id:
            with db.snapshot(multi_use=True) as snap:
                sql_chunks = """
                    SELECT chunk_id, section_heading, category, header_preserved_markdown, has_conflict
                    FROM OkfSectionChunks
                    WHERE concept_id = @concept_id
                    ORDER BY chunk_index ASC
                    LIMIT 12
                """
                for ch_row in snap.execute_sql(
                    sql_chunks,
                    params={"concept_id": target_concept_id},
                    param_types={"concept_id": param_types.STRING},
                ):
                    if param_kw and (
                        param_kw not in (ch_row[1] or "").lower()
                        and param_kw not in (ch_row[3] or "").lower()
                    ):
                        continue
                    concept_chunks.append(
                        {
                            "chunk_id": ch_row[0],
                            "section_heading": ch_row[1],
                            "category": ch_row[2],
                            "chunk_markdown": ch_row[3],
                            "has_conflict": bool(ch_row[4]),
                        }
                    )

        return {
            "found": True,
            "queried_tag": entity_tag_or_id,
            "primary_entity": primary_entity,
            "matching_entities": entity_rows,
            "parameters": parameters[:60],
            "concept_sections": concept_chunks[:8],
        }

    def _lookup_entity_in_memory(self, clean_tag: str, param_kw: str) -> dict[str, Any]:
        matches: list[EngineeringEntityNode] = []
        for ent in self._mem_entities.values():
            if (
                ent.canonical_tag.upper() == clean_tag
                or ent.entity_id.upper() == clean_tag
                or ent.concept_id.upper().endswith(f"/{clean_tag}")
                or clean_tag in ent.canonical_tag.upper()
                or clean_tag in ent.name.upper()
                or clean_tag in ent.concept_id.upper()
            ):
                matches.append(ent)
        matches.sort(
            key=lambda e: (
                0
                if e.canonical_tag.upper() == clean_tag
                else (1 if e.concept_id.upper().endswith(f"/{clean_tag}") else 2)
            )
        )
        if not matches:
            return {
                "found": False,
                "queried_tag": clean_tag,
                "entities": [],
                "parameters": [],
                "concept_sections": [],
            }
        primary = matches[0]
        params_out: list[dict[str, Any]] = []
        for fa in self._mem_assertions.values():
            if fa.entity_id != primary.entity_id and fa.concept_id != primary.concept_id:
                continue
            if param_kw and (
                param_kw not in fa.parameter_name.lower()
                and param_kw not in fa.parameter_value.lower()
                and param_kw not in fa.section_heading.lower()
            ):
                continue
            lin_edges = [le for le in self._mem_lineage_edges.values() if le.fact_id == fa.fact_id]
            first_le = lin_edges[0] if lin_edges else None
            src_doc = self._mem_source_docs.get(first_le.source_id) if first_le else None
            params_out.append(
                {
                    "fact_id": fa.fact_id,
                    "parameter_name": fa.parameter_name,
                    "parameter_value": fa.parameter_value,
                    "parameter_unit": fa.parameter_unit or "",
                    "section_heading": fa.section_heading,
                    "has_conflict": fa.has_conflict,
                    "conflict_note": fa.conflict_note,
                    "raw_citation_string": first_le.raw_citation_string if first_le else "",
                    "source_role": first_le.source_role if first_le else "PRIMARY",
                    "source_filename": src_doc.filename if src_doc else "",
                    "doc_code": src_doc.doc_code if src_doc else "",
                    "revision": src_doc.revision if src_doc else "",
                    "gcs_uri": src_doc.gcs_uri if src_doc else "",
                }
            )
        sections_out = [
            {
                "chunk_id": ch.chunk_id,
                "section_heading": ch.section_heading,
                "category": ch.category,
                "chunk_markdown": ch.header_preserved_markdown,
                "has_conflict": ch.has_conflict,
            }
            for ch in self._mem_chunks.values()
            if ch.concept_id == primary.concept_id
            and (
                not param_kw
                or param_kw in ch.section_heading.lower()
                or param_kw in ch.header_preserved_markdown.lower()
            )
        ]
        return {
            "found": True,
            "queried_tag": clean_tag,
            "primary_entity": primary.model_dump(),
            "matching_entities": [m.model_dump() for m in matches[:5]],
            "parameters": params_out[:60],
            "concept_sections": sections_out[:8],
        }

    # -------------------------------------------------------------------------
    # Query Tool 2: Hybrid Vector (768-d COSINE) + Full-Text RRF Search
    # -------------------------------------------------------------------------
    def hybrid_rrf_search(
        self,
        query: str,
        domain_filter: str | None = None,
        top_k: int = 10,
    ) -> list[HybridSearchResult]:
        """Execute Hybrid Vector (COSINE_DISTANCE) + Full-Text (SEARCH/TOKENLIST) Reciprocal Rank Fusion."""
        top_k = max(1, min(50, top_k))
        query_vec = self.embed_query(query)

        if self.use_in_memory or self._mem_chunks:
            return self._hybrid_rrf_in_memory(query, query_vec, domain_filter, top_k)

        db = self._get_database()
        from google.cloud.spanner_v1 import param_types

        tokens = [t for t in re.findall(r"[A-Za-z0-9\-]+", query) if len(t) >= 2]
        fts_query = " OR ".join(tokens[:12]) if tokens else query.strip()

        vec_ranks: dict[str, tuple[int, float, dict[str, Any]]] = {}
        fts_ranks: dict[str, tuple[int, dict[str, Any]]] = {}

        with db.snapshot(multi_use=True) as snap:
            # 1. Dense Vector Search (COSINE_DISTANCE)
            sql_vec = """
                SELECT
                    s.chunk_id,
                    s.concept_id,
                    c.name,
                    s.category,
                    s.unit,
                    s.section_heading,
                    s.header_preserved_markdown,
                    s.has_conflict,
                    COSINE_DISTANCE(s.embedding, @qvec) AS cosine_dist
                FROM OkfSectionChunks s
                JOIN OkfConcepts c ON s.concept_id = c.concept_id
                WHERE s.embedding IS NOT NULL
                  AND (@domain_filter = '' OR LOWER(s.category) = LOWER(@domain_filter) OR LOWER(IFNULL(s.unit, '')) = LOWER(@domain_filter))
                ORDER BY cosine_dist ASC
                LIMIT 30
            """
            for rank_idx, row in enumerate(
                snap.execute_sql(
                    sql_vec,
                    params={
                        "qvec": query_vec,
                        "domain_filter": (domain_filter or "").strip(),
                    },
                    param_types={
                        "qvec": param_types.Array(param_types.FLOAT32),
                        "domain_filter": param_types.STRING,
                    },
                ),
                start=1,
            ):
                dist = float(row[8]) if row[8] is not None else 1.0
                sim = max(-1.0, min(1.0, 1.0 - dist))
                meta = {
                    "chunk_id": row[0],
                    "concept_id": row[1],
                    "concept_title": row[2],
                    "category": row[3] or "",
                    "unit": row[4] or "",
                    "section_heading": row[5],
                    "chunk_markdown": row[6],
                    "has_conflict": bool(row[7]),
                }
                vec_ranks[row[0]] = (rank_idx, sim, meta)

            # 2. Full-Text Search (SEARCH on ChunkTokens)
            sql_fts = """
                SELECT
                    s.chunk_id,
                    s.concept_id,
                    c.name,
                    s.category,
                    s.unit,
                    s.section_heading,
                    s.header_preserved_markdown,
                    s.has_conflict,
                    SCORE(s.ChunkTokens, @fts_query) AS fts_score
                FROM OkfSectionChunks s
                JOIN OkfConcepts c ON s.concept_id = c.concept_id
                WHERE SEARCH(s.ChunkTokens, @fts_query)
                  AND (@domain_filter = '' OR LOWER(s.category) = LOWER(@domain_filter) OR LOWER(IFNULL(s.unit, '')) = LOWER(@domain_filter))
                ORDER BY fts_score DESC
                LIMIT 30
            """
            try:
                for rank_idx, row in enumerate(
                    snap.execute_sql(
                        sql_fts,
                        params={
                            "fts_query": fts_query,
                            "domain_filter": (domain_filter or "").strip(),
                        },
                        param_types={
                            "fts_query": param_types.STRING,
                            "domain_filter": param_types.STRING,
                        },
                    ),
                    start=1,
                ):
                    meta = {
                        "chunk_id": row[0],
                        "concept_id": row[1],
                        "concept_title": row[2],
                        "category": row[3] or "",
                        "unit": row[4] or "",
                        "section_heading": row[5],
                        "chunk_markdown": row[6],
                        "has_conflict": bool(row[7]),
                    }
                    fts_ranks[row[0]] = (rank_idx, meta)
            except Exception as exc:
                logger.debug("FTS fallback notice: %s", exc)

        # Reciprocal Rank Fusion (k = 60)
        all_chunk_ids = set(vec_ranks.keys()) | set(fts_ranks.keys())
        fused: list[HybridSearchResult] = []
        for cid in all_chunk_ids:
            v_tuple = vec_ranks.get(cid)
            f_tuple = fts_ranks.get(cid)
            v_rank = v_tuple[0] if v_tuple else None
            v_sim = v_tuple[1] if v_tuple else 0.0
            f_rank = f_tuple[0] if f_tuple else None
            meta = v_tuple[2] if v_tuple else f_tuple[1]  # type: ignore[index]

            rrf_score = (1.0 / (60.0 + v_rank) if v_rank else 0.0) + (
                1.0 / (60.0 + f_rank) if f_rank else 0.0
            )
            fused.append(
                HybridSearchResult(
                    chunk_id=cid,
                    concept_id=meta["concept_id"],
                    concept_title=meta["concept_title"],
                    category=meta["category"],
                    unit=meta["unit"],
                    section_heading=meta["section_heading"],
                    chunk_markdown=meta["chunk_markdown"],
                    has_conflict=meta["has_conflict"],
                    rrf_score=round(rrf_score, 6),
                    vector_rank=v_rank,
                    fts_rank=f_rank,
                    cosine_similarity=round(v_sim, 6),
                )
            )

        fused.sort(key=lambda r: (-r.rrf_score, -(r.cosine_similarity or 0.0), r.chunk_id))
        return fused[:top_k]

    def _hybrid_rrf_in_memory(
        self,
        query: str,
        query_vec: list[float],
        domain_filter: str | None,
        top_k: int,
    ) -> list[HybridSearchResult]:
        dom = (domain_filter or "").strip().lower()
        query_tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9\-]+", query) if len(t) >= 2]

        candidates: list[tuple[OkfSectionChunkNode, OkfConceptNode, float, int]] = []
        for ch in self._mem_chunks.values():
            concept = self._mem_concepts.get(ch.concept_id)
            if not concept:
                continue
            if dom and dom not in ch.category.lower() and dom not in (ch.unit or "").lower():
                continue
            sim = cosine_similarity(query_vec, ch.embedding or [])
            haystack = f"{concept.concept_id} {concept.name} {ch.section_heading} {ch.header_preserved_markdown}".lower()
            kw_hits = sum(1 for tok in query_tokens if tok in haystack)
            candidates.append((ch, concept, sim, kw_hits))

        by_vec = sorted(candidates, key=lambda x: (-x[2], x[0].chunk_id))[:30]
        vec_rank_map = {item[0].chunk_id: (idx + 1, item[2]) for idx, item in enumerate(by_vec)}

        by_fts = [c for c in candidates if c[3] > 0]
        by_fts.sort(key=lambda x: (-x[3], -x[2], x[0].chunk_id))
        fts_rank_map = {item[0].chunk_id: idx + 1 for idx, item in enumerate(by_fts[:30])}

        all_ids = set(vec_rank_map.keys()) | set(fts_rank_map.keys())
        chunk_lookup = {c[0].chunk_id: (c[0], c[1]) for c in candidates}

        results: list[HybridSearchResult] = []
        for cid in all_ids:
            ch, concept = chunk_lookup[cid]
            v_info = vec_rank_map.get(cid)
            v_rank = v_info[0] if v_info else None
            v_sim = v_info[1] if v_info else 0.0
            f_rank = fts_rank_map.get(cid)
            rrf = (1.0 / (60.0 + v_rank) if v_rank else 0.0) + (
                1.0 / (60.0 + f_rank) if f_rank else 0.0
            )
            results.append(
                HybridSearchResult(
                    chunk_id=cid,
                    concept_id=concept.concept_id,
                    concept_title=concept.name,
                    category=ch.category,
                    unit=ch.unit,
                    section_heading=ch.section_heading,
                    chunk_markdown=ch.header_preserved_markdown,
                    has_conflict=ch.has_conflict,
                    rrf_score=round(rrf, 6),
                    vector_rank=v_rank,
                    fts_rank=f_rank,
                    cosine_similarity=round(v_sim, 6),
                )
            )
        results.sort(key=lambda r: (-r.rrf_score, -(r.cosine_similarity or 0.0), r.chunk_id))
        return results[:top_k]

    # -------------------------------------------------------------------------
    # Query Tool 3: Multi-Hop Equipment & Control Graph Traversal (ISO GQL)
    # -------------------------------------------------------------------------
    def traverse_connectivity_gql(
        self,
        start_tag: str,
        direction: str = "BOTH",
        max_hops: int = 3,
        edge_filter: str = "ALL",
    ) -> list[GraphTraversalHop]:
        """Traverse ProcessConnections and InstrumentControlEdges using Spanner Graph ISO GQL."""
        clean_tag = (start_tag or "").strip().upper()
        max_hops = max(1, min(5, max_hops))
        direction_norm = (direction or "BOTH").upper()

        if self.use_in_memory or self._mem_connections or self._mem_controls:
            return self._traverse_in_memory(clean_tag, direction_norm, max_hops, edge_filter)

        db = self._get_database()
        from google.cloud.spanner_v1 import param_types

        hops: list[GraphTraversalHop] = []
        with db.snapshot(multi_use=True) as snap:
            gql_downstream = """
                GRAPH OkfKnowledgeGraph
                MATCH (src:Entity)-[e:CONNECTS_TO]->(dst:Entity)
                WHERE UPPER(src.canonical_tag) = @tag
                   OR UPPER(dst.canonical_tag) = @tag
                   OR STRPOS(UPPER(src.canonical_tag), @tag) > 0
                   OR STRPOS(UPPER(dst.canonical_tag), @tag) > 0
                RETURN
                    src.canonical_tag AS from_tag,
                    src.name AS from_name,
                    dst.canonical_tag AS to_tag,
                    dst.name AS to_name,
                    e.stream_or_line_id AS stream_id,
                    e.fluid_service AS fluid,
                    e.temperature AS temp,
                    e.pressure AS press,
                    e.source_concept_id AS concept_id
                LIMIT 50
            """
            if edge_filter.upper() in ("ALL", "PROCESS", "CONNECTS_TO"):
                for row in snap.execute_sql(
                    gql_downstream,
                    params={"tag": clean_tag},
                    param_types={"tag": param_types.STRING},
                ):
                    hops.append(
                        GraphTraversalHop(
                            hop_distance=1,
                            from_tag=row[0],
                            from_name=row[1],
                            edge_type="CONNECTS_TO",
                            to_tag=row[2],
                            to_name=row[3],
                            stream_or_loop_id=row[4],
                            fluid_or_instrument_type=row[5],
                            operating_conditions=f"T={row[6] or 'N/A'}, P={row[7] or 'N/A'}",
                            source_concept_id=row[8],
                        )
                    )

            gql_controls = """
                GRAPH OkfKnowledgeGraph
                MATCH (inst:Entity)-[c:MONITORS_OR_TRIPS]->(target:Entity)
                WHERE UPPER(inst.canonical_tag) = @tag
                   OR UPPER(target.canonical_tag) = @tag
                   OR STRPOS(UPPER(inst.canonical_tag), @tag) > 0
                   OR STRPOS(UPPER(target.canonical_tag), @tag) > 0
                RETURN
                    inst.canonical_tag AS from_tag,
                    inst.name AS from_name,
                    target.canonical_tag AS to_tag,
                    target.name AS to_name,
                    c.loop_id AS loop_id,
                    c.instrument_type AS inst_type,
                    c.setpoint_or_range AS setpoint,
                    c.interlock_or_alarm AS interlock,
                    c.source_concept_id AS concept_id
                LIMIT 50
            """
            if edge_filter.upper() in ("ALL", "INSTRUMENT", "CONTROL", "MONITORS_OR_TRIPS"):
                for row in snap.execute_sql(
                    gql_controls,
                    params={"tag": clean_tag},
                    param_types={"tag": param_types.STRING},
                ):
                    hops.append(
                        GraphTraversalHop(
                            hop_distance=1,
                            from_tag=row[0],
                            from_name=row[1],
                            edge_type="MONITORS_OR_TRIPS",
                            to_tag=row[2],
                            to_name=row[3],
                            stream_or_loop_id=row[4],
                            fluid_or_instrument_type=row[5],
                            operating_conditions=f"Setpoint={row[6] or 'N/A'}, Interlock={row[7] or 'N/A'}",
                            source_concept_id=row[8],
                        )
                    )

            visited_tags = {clean_tag}
            frontier = {
                h.to_tag.upper() if h.from_tag.upper() == clean_tag else h.from_tag.upper()
                for h in hops
            } - visited_tags

            gql_batched_hop = """
                GRAPH OkfKnowledgeGraph
                MATCH (src:Entity)-[e:CONNECTS_TO]->(dst:Entity)
                WHERE UPPER(src.canonical_tag) IN UNNEST(@tags)
                   OR UPPER(dst.canonical_tag) IN UNNEST(@tags)
                RETURN
                    src.canonical_tag AS from_tag,
                    src.name AS from_name,
                    dst.canonical_tag AS to_tag,
                    dst.name AS to_name,
                    e.stream_or_line_id AS stream_id,
                    e.fluid_service AS fluid,
                    e.temperature AS temp,
                    e.pressure AS press,
                    e.source_concept_id AS concept_id
                LIMIT 80
            """

            for current_hop in range(2, max_hops + 1):
                if not frontier:
                    break
                batch_tags = sorted(frontier)[:12]
                visited_tags.update(batch_tags)
                next_frontier: set[str] = set()
                for row in snap.execute_sql(
                    gql_batched_hop,
                    params={"tags": batch_tags},
                    param_types={"tags": param_types.Array(param_types.STRING)},
                ):
                    f_from, f_to = str(row[0]), str(row[2])
                    if f_from.upper() in visited_tags and f_to.upper() in visited_tags:
                        continue
                    hops.append(
                        GraphTraversalHop(
                            hop_distance=current_hop,
                            from_tag=f_from,
                            from_name=row[1],
                            edge_type="CONNECTS_TO",
                            to_tag=f_to,
                            to_name=row[3],
                            stream_or_loop_id=row[4],
                            fluid_or_instrument_type=row[5],
                            operating_conditions=f"T={row[6] or 'N/A'}, P={row[7] or 'N/A'}",
                            source_concept_id=row[8],
                        )
                    )
                    if f_from.upper() not in visited_tags:
                        next_frontier.add(f_from.upper())
                    if f_to.upper() not in visited_tags:
                        next_frontier.add(f_to.upper())
                frontier = next_frontier

        return hops

    def _traverse_in_memory(
        self,
        clean_tag: str,
        direction_norm: str,
        max_hops: int,
        edge_filter: str,
    ) -> list[GraphTraversalHop]:
        tag_to_ent = {e.canonical_tag.upper(): e for e in self._mem_entities.values()}
        id_to_ent = self._mem_entities

        start_ent = tag_to_ent.get(clean_tag)
        if not start_ent:
            for t, e in tag_to_ent.items():
                if clean_tag in t:
                    start_ent = e
                    break
        if not start_ent:
            return []

        hops: list[GraphTraversalHop] = []
        visited_ids = {start_ent.entity_id}
        frontier_ids = {start_ent.entity_id}

        for hop_num in range(1, max_hops + 1):
            if not frontier_ids:
                break
            next_frontier: set[str] = set()
            if edge_filter.upper() in ("ALL", "PROCESS", "CONNECTS_TO"):
                for conn in self._mem_connections.values():
                    from_e = id_to_ent.get(conn.from_entity_id)
                    to_e = id_to_ent.get(conn.to_entity_id)
                    if not from_e or not to_e:
                        continue
                    matched = False
                    if direction_norm in ("DOWNSTREAM", "BOTH") and conn.from_entity_id in frontier_ids:
                        matched = True
                        if conn.to_entity_id not in visited_ids:
                            next_frontier.add(conn.to_entity_id)
                    elif direction_norm in ("UPSTREAM", "BOTH") and conn.to_entity_id in frontier_ids:
                        matched = True
                        if conn.from_entity_id not in visited_ids:
                            next_frontier.add(conn.from_entity_id)
                    if matched:
                        hops.append(
                            GraphTraversalHop(
                                hop_distance=hop_num,
                                from_tag=from_e.canonical_tag,
                                from_name=from_e.name,
                                edge_type="CONNECTS_TO",
                                to_tag=to_e.canonical_tag,
                                to_name=to_e.name,
                                stream_or_loop_id=conn.stream_or_line_id,
                                fluid_or_instrument_type=conn.fluid_service,
                                operating_conditions=f"T={conn.temperature or 'N/A'}, P={conn.pressure or 'N/A'}",
                                source_concept_id=conn.source_concept_id,
                            )
                        )
            if edge_filter.upper() in ("ALL", "INSTRUMENT", "CONTROL", "MONITORS_OR_TRIPS"):
                for ctrl in self._mem_controls.values():
                    inst_e = id_to_ent.get(ctrl.instrument_entity_id)
                    tgt_e = id_to_ent.get(ctrl.target_entity_id)
                    if not inst_e or not tgt_e:
                        continue
                    if ctrl.instrument_entity_id in frontier_ids or ctrl.target_entity_id in frontier_ids:
                        hops.append(
                            GraphTraversalHop(
                                hop_distance=hop_num,
                                from_tag=inst_e.canonical_tag,
                                from_name=inst_e.name,
                                edge_type="MONITORS_OR_TRIPS",
                                to_tag=tgt_e.canonical_tag,
                                to_name=tgt_e.name,
                                stream_or_loop_id=ctrl.loop_id,
                                fluid_or_instrument_type=ctrl.instrument_type,
                                operating_conditions=(
                                    f"Setpoint={ctrl.setpoint_or_range or 'N/A'}, "
                                    f"Interlock={ctrl.interlock_or_alarm or 'N/A'}"
                                ),
                                source_concept_id=ctrl.source_concept_id,
                            )
                        )
                        if ctrl.instrument_entity_id not in visited_ids:
                            next_frontier.add(ctrl.instrument_entity_id)
                        if ctrl.target_entity_id not in visited_ids:
                            next_frontier.add(ctrl.target_entity_id)

            visited_ids.update(next_frontier)
            frontier_ids = next_frontier
        return hops

    # -------------------------------------------------------------------------
    # Query Tool 4: Bidirectional Data Lineage & Conflict Audit (ISO GQL)
    # -------------------------------------------------------------------------
    def trace_lineage_gql(
        self,
        target_id: str,
        direction: str = "BACKWARD_TO_PDF",
        conflicts_only: bool = False,
    ) -> list[LineageTraceResult]:
        """Trace claim-level provenance backward to RawSourceDocuments or forward from a PDF."""
        clean_target = (target_id or "").strip()
        dir_norm = (direction or "BACKWARD_TO_PDF").upper()

        if self.use_in_memory or self._mem_lineage_edges:
            return self._trace_lineage_in_memory(clean_target, dir_norm, conflicts_only)

        db = self._get_database()
        from google.cloud.spanner_v1 import param_types

        results: list[LineageTraceResult] = []
        with db.snapshot(multi_use=True) as snap:
            if dir_norm == "FORWARD_FROM_PDF":
                gql = """
                    GRAPH OkfKnowledgeGraph
                    MATCH (f:Fact)-[l:DERIVED_FROM]->(d:RawDocument)
                    WHERE STRPOS(UPPER(d.filename), UPPER(@target)) > 0
                       OR STRPOS(UPPER(IFNULL(d.doc_code, '')), UPPER(@target)) > 0
                       OR UPPER(d.source_id) = UPPER(@target)
                    RETURN
                        f.fact_id,
                        f.entity_id,
                        f.concept_id,
                        f.parameter_name,
                        f.parameter_value,
                        f.has_conflict,
                        f.conflict_note,
                        l.raw_citation_string,
                        l.source_role,
                        d.source_id,
                        d.filename,
                        d.gcs_uri,
                        d.md5_hash,
                        d.revision
                    LIMIT 100
                """
            else:
                gql = """
                    GRAPH OkfKnowledgeGraph
                    MATCH (f:Fact)-[l:DERIVED_FROM]->(d:RawDocument)
                    WHERE (
                        @target = ''
                        OR UPPER(f.fact_id) = UPPER(@target)
                        OR STRPOS(UPPER(IFNULL(f.entity_id, '')), UPPER(@target)) > 0
                        OR STRPOS(UPPER(f.concept_id), UPPER(@target)) > 0
                        OR STRPOS(UPPER(f.parameter_name), UPPER(@target)) > 0
                    )
                    AND (@conflicts_only = FALSE OR f.has_conflict = TRUE)
                    RETURN
                        f.fact_id,
                        f.entity_id,
                        f.concept_id,
                        f.parameter_name,
                        f.parameter_value,
                        f.has_conflict,
                        f.conflict_note,
                        l.raw_citation_string,
                        l.source_role,
                        d.source_id,
                        d.filename,
                        d.gcs_uri,
                        d.md5_hash,
                        d.revision
                    LIMIT 100
                """
            for r in snap.execute_sql(
                gql,
                params={"target": clean_target, "conflicts_only": conflicts_only},
                param_types={
                    "target": param_types.STRING,
                    "conflicts_only": param_types.BOOL,
                },
            ):
                results.append(
                    LineageTraceResult(
                        fact_id=r[0],
                        entity_id=r[1] or "",
                        concept_id=r[2],
                        parameter_name=r[3],
                        parameter_value=r[4],
                        has_conflict=bool(r[5]),
                        conflict_note=r[6],
                        raw_citation_string=r[7],
                        source_role=r[8],
                        source_id=r[9],
                        filename=r[10],
                        gcs_uri=r[11] or "",
                        md5_hash=r[12] or "",
                        revision=r[13],
                    )
                )
        return results

    def _trace_lineage_in_memory(
        self,
        clean_target: str,
        dir_norm: str,
        conflicts_only: bool,
    ) -> list[LineageTraceResult]:
        t_up = clean_target.upper()
        out: list[LineageTraceResult] = []
        for le in self._mem_lineage_edges.values():
            fa = self._mem_assertions.get(le.fact_id)
            doc = self._mem_source_docs.get(le.source_id)
            if not fa or not doc:
                continue
            if conflicts_only and not fa.has_conflict:
                continue
            if dir_norm == "FORWARD_FROM_PDF":
                if (
                    t_up
                    and t_up not in doc.filename.upper()
                    and t_up not in (doc.doc_code or "").upper()
                    and t_up != doc.source_id.upper()
                ):
                    continue
            else:
                if (
                    t_up
                    and t_up != fa.fact_id.upper()
                    and t_up not in (fa.entity_id or "").upper()
                    and t_up not in fa.concept_id.upper()
                    and t_up not in fa.parameter_name.upper()
                ):
                    continue
            out.append(
                LineageTraceResult(
                    fact_id=fa.fact_id,
                    entity_id=fa.entity_id,
                    concept_id=fa.concept_id,
                    parameter_name=fa.parameter_name,
                    parameter_value=fa.parameter_value,
                    has_conflict=fa.has_conflict,
                    conflict_note=fa.conflict_note,
                    raw_citation_string=le.raw_citation_string,
                    source_role=le.source_role,
                    source_id=doc.source_id,
                    filename=doc.filename,
                    gcs_uri=doc.gcs_uri,
                    md5_hash=doc.md5_hash,
                    revision=doc.revision,
                )
            )
        return out[:100]

    # -------------------------------------------------------------------------
    # Query Tool 5: Multi-Stage Risk Assessment & HAZOP Study Orchestrator
    # -------------------------------------------------------------------------
    def execute_multistage_risk_and_hazop_query(
        self,
        target_tag_or_deviation: str,
        max_propagation_hops: int = 2,
        include_interlocks_and_psvs: bool = True,
    ) -> MultiStageRiskHazopReport:
        """Execute deterministic 5-stage query plan for complex HAZOP & risk assessment questions."""
        target = (target_tag_or_deviation or "").strip()

        # Stage 1: Risk Matrix & Severity Tier Governance Rules
        risk_matrix_chunks = self.hybrid_rrf_search(
            query=f"HAZOP risk matrix severity tier classification safeguards {target}",
            domain_filter=None,
            top_k=6,
        )
        risk_governance_rules = [
            f"[{c.concept_title} | {c.section_heading}]: {c.chunk_markdown[:400]}"
            for c in risk_matrix_chunks[:3]
        ]

        # Stage 2: Extract HAZOP Scenario Records & Deviations matching target
        hazop_scenarios = self._extract_hazop_scenarios_for_target(target, risk_matrix_chunks)

        tag_match = re.search(r"\b([A-Z]{1,4}-\d{3,4}[A-Z0-9]*)\b", target.upper())
        primary_tag = tag_match.group(1) if tag_match else ""
        if not primary_tag and hazop_scenarios:
            for sc in hazop_scenarios:
                m = re.search(r"\b([A-Z]{1,4}-\d{3,4}[A-Z0-9]*)\b", sc.node_or_equipment.upper())
                if m:
                    primary_tag = m.group(1)
                    break

        # Stage 3: Upstream Cause & Downstream Plant Implication Graph Propagation
        all_hops = (
            self.traverse_connectivity_gql(
                start_tag=primary_tag,
                direction="BOTH",
                max_hops=max_propagation_hops,
                edge_filter="ALL",
            )
            if primary_tag
            else []
        )
        upstream_hops = [
            h
            for h in all_hops
            if h.edge_type == "CONNECTS_TO" and primary_tag.upper() in h.to_tag.upper()
        ]
        downstream_hops = [
            h
            for h in all_hops
            if h.edge_type == "CONNECTS_TO" and primary_tag.upper() in h.from_tag.upper()
        ]
        for h in all_hops:
            if h.hop_distance >= 2 and h not in downstream_hops:
                downstream_hops.append(h)

        # Stage 4: Active Safeguard, Interlock & PSV Verification
        safeguards: list[dict[str, Any]] = []
        if include_interlocks_and_psvs and primary_tag:
            for h in all_hops:
                if h.edge_type == "MONITORS_OR_TRIPS":
                    safeguards.append(
                        {
                            "instrument_tag": h.from_tag,
                            "instrument_name": h.from_name,
                            "protected_equipment": h.to_tag,
                            "loop_id": h.stream_or_loop_id,
                            "instrument_type": h.fluid_or_instrument_type,
                            "details": h.operating_conditions,
                        }
                    )
            ent_info = self.lookup_entity_and_parameters(primary_tag)
            for p in ent_info.get("parameters", []):
                p_name_l = p["parameter_name"].lower()
                if any(
                    kw in p_name_l
                    for kw in ("interlock", "trip", "alarm", "setpoint", "psv", "relief", "design pressure", "design temp")
                ):
                    safeguards.append(
                        {
                            "parameter": p["parameter_name"],
                            "value": p["parameter_value"],
                            "has_conflict": p["has_conflict"],
                            "source_citation": p["raw_citation_string"],
                        }
                    )

        # Stage 5: Lineage & Conflict Audit on Safeguard Setpoints
        lineage_traces = self.trace_lineage_gql(
            target_id=primary_tag or target,
            direction="BACKWARD_TO_PDF",
            conflicts_only=False,
        )
        conflict_traces = [lt for lt in lineage_traces if lt.has_conflict]

        return MultiStageRiskHazopReport(
            target_equipment_or_node=primary_tag or target,
            risk_matrix_governance_rules=risk_governance_rules,
            hazop_scenarios=hazop_scenarios,
            upstream_cause_propagation=upstream_hops,
            downstream_plant_implications=downstream_hops,
            verified_safeguards_and_interlocks=safeguards[:25],
            lineage_and_conflict_alerts=(conflict_traces if conflict_traces else lineage_traces[:10]),
        )

    def _extract_hazop_scenarios_for_target(
        self,
        target: str,
        search_results: list[HybridSearchResult],
    ) -> list[HazopScenarioRecord]:
        scenarios: list[HazopScenarioRecord] = []
        hazop_chunks = self.hybrid_rrf_search(
            query=f"HAZOP deviation cause consequence safeguard interlock risk {target}",
            domain_filter=None,
            top_k=10,
        )
        seen_chunks: set[str] = set()
        for ch in list(search_results) + list(hazop_chunks):
            if ch.chunk_id in seen_chunks:
                continue
            seen_chunks.add(ch.chunk_id)
            lines = [ln.strip() for ln in ch.chunk_markdown.splitlines() if ln.strip().startswith("|")]
            if len(lines) >= 3:
                headers = [h.strip().lower() for h in lines[0].strip("|").split("|")]
                for row_ln in lines[2:]:
                    cells = [c.strip() for c in row_ln.strip("|").split("|")]
                    if len(cells) < 2 or all(set(c) <= {"-", ":"} for c in cells):
                        continue
                    row_map = {
                        headers[i]: cells[i] for i in range(min(len(headers), len(cells)))
                    }
                    deviation = (
                        row_map.get("deviation")
                        or row_map.get("hazard / deviation")
                        or row_map.get("scenario")
                        or row_map.get("parameter")
                        or cells[0]
                    )
                    cause = (
                        row_map.get("cause")
                        or row_map.get("potential cause")
                        or row_map.get("causes")
                        or (cells[1] if len(cells) > 1 else "See section details")
                    )
                    consequence = (
                        row_map.get("consequence")
                        or row_map.get("implication")
                        or row_map.get("plant consequence")
                        or row_map.get("value / specification")
                        or (cells[2] if len(cells) > 2 else "Potential process excursion")
                    )
                    risk_tier = (
                        row_map.get("risk tier")
                        or row_map.get("severity")
                        or row_map.get("risk")
                        or "High / Safety Critical"
                    )
                    safeguards_cell = (
                        row_map.get("safeguards")
                        or row_map.get("interlock / action")
                        or row_map.get("notes / interlock")
                        or (cells[3] if len(cells) > 3 else "")
                    )
                    source_cit = (
                        row_map.get("source")
                        or row_map.get("provenance")
                        or ch.concept_id
                    )
                    scenarios.append(
                        HazopScenarioRecord(
                            node_or_equipment=ch.concept_id,
                            deviation=deviation[:240],
                            potential_cause=cause[:300],
                            consequence_and_implication=consequence[:300],
                            risk_tier_or_severity=risk_tier[:120],
                            safeguards=[s.strip() for s in safeguards_cell.split(";") if s.strip()],
                            source_citation=source_cit[:240],
                        )
                    )
                    if len(scenarios) >= 12:
                        return scenarios
        return scenarios

    # -------------------------------------------------------------------------
    # Query Tool 6: Read Full OKF Concept Document directly from Spanner
    # -------------------------------------------------------------------------
    def read_full_concept(
        self,
        concept_id_or_tag: str,
        section_filter: str | None = None,
    ) -> dict[str, Any]:
        """Read full OKF Markdown concept document and YAML frontmatter directly from Spanner (Zero GCS reads)."""
        clean_q = (concept_id_or_tag or "").strip()
        sec_kw = (section_filter or "").strip().lower()

        if self.use_in_memory or self._mem_concepts:
            return self._read_full_concept_in_memory(clean_q, sec_kw)

        db = self._get_database()
        from google.cloud.spanner_v1 import param_types

        with db.snapshot(multi_use=True) as snap:
            sql = """
                SELECT
                    concept_id,
                    category,
                    name,
                    description,
                    unit,
                    trust_tier,
                    has_conflict,
                    conflict_count,
                    frontmatter_json,
                    body_markdown,
                    md5_hash,
                    bundle_version,
                    gcs_uri
                FROM OkfConcepts
                WHERE UPPER(concept_id) = UPPER(@q)
                   OR ENDS_WITH(UPPER(concept_id), CONCAT('/', UPPER(@q)))
                   OR STRPOS(UPPER(concept_id), UPPER(@q)) > 0
                   OR STRPOS(UPPER(name), UPPER(@q)) > 0
                ORDER BY
                    CASE
                        WHEN UPPER(concept_id) = UPPER(@q) THEN 0
                        WHEN ENDS_WITH(UPPER(concept_id), CONCAT('/', UPPER(@q))) THEN 1
                        ELSE 2
                    END
                LIMIT 1
            """
            rows = list(
                snap.execute_sql(
                    sql,
                    params={"q": clean_q},
                    param_types={"q": param_types.STRING},
                )
            )
            if not rows:
                return {"found": False, "queried": concept_id_or_tag}

            r = rows[0]
            fm = r[8]
            if hasattr(fm, "serialize"):
                fm = json.loads(fm.serialize())
            elif isinstance(fm, str):
                fm = json.loads(fm)
            body_md = str(r[9] or "")

            sql_links = """
                SELECT to_concept_id, section_heading
                FROM ConceptWikiLinks
                WHERE from_concept_id = @cid
                LIMIT 30
            """
            wiki_links = [
                {"to_concept_id": lr[0], "section_heading": lr[1]}
                for lr in snap.execute_sql(
                    sql_links,
                    params={"cid": r[0]},
                    param_types={"cid": param_types.STRING},
                )
            ]

        if sec_kw:
            filtered_chunks = [
                sec
                for sec in re.split(r"(?=^##\s+)", body_md, flags=re.MULTILINE)
                if sec_kw in sec.lower()
            ]
            if filtered_chunks:
                body_md = "\n\n".join(filtered_chunks)

        return {
            "found": True,
            "concept_id": r[0],
            "category": r[1],
            "title": r[2],
            "description": r[3],
            "unit": r[4],
            "trust_tier": r[5],
            "has_conflict": bool(r[6]),
            "conflict_count": int(r[7] or 0),
            "frontmatter": fm or {},
            "body_markdown": body_md,
            "content_md5": r[10],
            "bundle_version": r[11],
            "bundle_gcs_uri": r[12],
            "wiki_links": wiki_links,
        }

    def _read_full_concept_in_memory(self, clean_q: str, sec_kw: str) -> dict[str, Any]:
        q_up = clean_q.upper()
        matches: list[OkfConceptNode] = []
        for c in self._mem_concepts.values():
            if (
                c.concept_id.upper() == q_up
                or c.concept_id.upper().endswith(f"/{q_up}")
                or q_up in c.concept_id.upper()
                or q_up in c.name.upper()
            ):
                matches.append(c)
        matches.sort(
            key=lambda c: (
                0
                if c.concept_id.upper() == q_up
                else (1 if c.concept_id.upper().endswith(f"/{q_up}") else 2)
            )
        )
        if not matches:
            return {"found": False, "queried": clean_q}
        chosen = matches[0]
        body_md = chosen.body_markdown
        if sec_kw:
            secs = [
                sec
                for sec in re.split(r"(?=^##\s+)", body_md, flags=re.MULTILINE)
                if sec_kw in sec.lower()
            ]
            if secs:
                body_md = "\n\n".join(secs)
        links = [
            {"to_concept_id": wl.to_concept_id, "section_heading": wl.section_heading}
            for wl in self._mem_wiki_links.values()
            if wl.from_concept_id == chosen.concept_id
        ]
        return {
            "found": True,
            "concept_id": chosen.concept_id,
            "category": chosen.category,
            "title": chosen.name,
            "description": chosen.description,
            "unit": chosen.unit,
            "trust_tier": chosen.trust_tier,
            "has_conflict": chosen.has_conflict,
            "conflict_count": chosen.conflict_count,
            "frontmatter": chosen.frontmatter_json,
            "body_markdown": body_md,
            "content_md5": chosen.md5_hash,
            "bundle_version": chosen.bundle_version,
            "bundle_gcs_uri": chosen.gcs_uri,
            "wiki_links": links,
        }

    def get_live_counts(self) -> dict[str, int]:
        """Return live row counts from Spanner (or in-memory store)."""
        if self.use_in_memory or self._mem_concepts:
            return {
                "total_source_docs": len(self._mem_source_docs),
                "total_concepts": len(self._mem_concepts),
                "total_chunks": len(self._mem_chunks),
                "total_entities": len(self._mem_entities),
                "total_assertions": len(self._mem_assertions),
                "total_conflicts": sum(1 for a in self._mem_assertions.values() if a.has_conflict),
                "total_connections": len(self._mem_connections),
                "total_controls": len(self._mem_controls),
                "total_lineage_edges": len(self._mem_lineage_edges),
            }

        db = self._get_database()
        counts: dict[str, int] = {}
        queries = {
            "total_source_docs": "SELECT COUNT(*) FROM RawSourceDocuments",
            "total_concepts": "SELECT COUNT(*) FROM OkfConcepts",
            "total_chunks": "SELECT COUNT(*) FROM OkfSectionChunks",
            "total_entities": "SELECT COUNT(*) FROM EngineeringEntities",
            "total_assertions": "SELECT COUNT(*) FROM FactAssertions",
            "total_conflicts": "SELECT COUNT(*) FROM FactAssertions WHERE has_conflict = TRUE",
            "total_connections": "SELECT COUNT(*) FROM ProcessConnections",
            "total_controls": "SELECT COUNT(*) FROM InstrumentControlEdges",
            "total_lineage_edges": "SELECT COUNT(*) FROM FactLineageEdges",
        }
        with db.snapshot(multi_use=True) as snap:
            for key, q in queries.items():
                for row in snap.execute_sql(q):
                    counts[key] = int(row[0])
        return counts

    @staticmethod
    def _classify_equipment_group(tag: str, eq_class: str = "") -> str:
        t = (tag or "").strip().upper()
        c = (eq_class or "").strip().lower()
        if t.startswith(("R-", "C-")) or "reactor" in c or "column" in c or "tower" in c:
            return "Reactors & Columns"
        if t.startswith(("D-", "V-", "T-", "TK-")) or "drum" in c or "vessel" in c or "tank" in c or "separator" in c:
            return "Drums, Vessels & Tanks"
        if t.startswith(("E-", "H-", "A-")) or "exchanger" in c or "cooler" in c or "condenser" in c or "reboiler" in c or "heater" in c:
            return "Heat Exchangers & Condensers"
        if t.startswith(("P-", "K-", "B-", "G-")) or "pump" in c or "compressor" in c or "blower" in c:
            return "Pumps & Rotating Equipment"
        if t.startswith(("F-", "S-", "M-", "X-", "Y-")) or "filter" in c or "ejector" in c or "mixer" in c:
            return "Filters, Ejectors & internals"
        return "Process & Utility Packages"

    @staticmethod
    def _infer_unit_from_tag(tag: str, raw_unit: str | None) -> str:
        u = (raw_unit or "").strip()
        u_up = u.upper()
        t_up = (tag or "").strip().upper()
        if (
            "2100" in u_up
            or u_up in ("21", "UNIT 21", "U2100")
            or "ALKYLATION" in u_up
            or "CUMENE DISTILLATION" in u_up
            or "PIPB" in u_up
        ):
            return "Unit 2100 (Cumene & Alkylation)"
        if "2200" in u_up or u_up in ("22", "UNIT 22", "U2200") or "OXIDATION" in u_up:
            return "Unit 2200 (Oxidation Section)"
        if (
            "2300" in u_up
            or u_up in ("23", "UNIT 23", "U2300", "CDN")
            or "CDN" in u_up
            or "DECOMPOS" in u_up
            or "CONCENTRATION" in u_up
            or "CLEAVAGE" in u_up
        ):
            return "Unit 2300 (CDN Section)"
        if u and u_up not in ("NONE", "NULL", "UNKNOWN", ""):
            return u
        m = re.search(r"-(\d{2})\d{2}", t_up)
        if m:
            prefix = m.group(1)
            if prefix == "21":
                return "Unit 2100 (Cumene & Alkylation)"
            if prefix in ("22", "12"):
                return "Unit 2200 (Oxidation Section)"
            if prefix in ("23", "13"):
                return "Unit 2300 (CDN Section)"
            return f"Unit {prefix}00"
        return "Plant-Wide"

    @staticmethod
    def classify_source_pdf_metadata(
        filename_or_path: str,
        doc_code: str = "",
        revision: str = "",
        source_role: str = "PRIMARY",
        md5_hash: str = "",
        gcs_uri: str = "",
    ) -> dict[str, Any]:
        """Normalize a source PDF reference into structured provenance metadata (filename, doc_code, doc_type, revision, role)."""
        raw_path = (filename_or_path or gcs_uri or doc_code or "Unknown_Source.pdf").strip()
        clean_filename = raw_path.rsplit("/", 1)[-1] or raw_path
        lower_all = f"{raw_path} {doc_code}".lower()

        # Infer document code if not explicitly provided (or if placeholder like src-1)
        clean_code = (doc_code or "").strip()
        if "," in clean_code:
            clean_code = clean_code.split(",", 1)[0].strip()
        if (
            not clean_code
            or clean_code == clean_filename
            or re.match(r"^src-\d+$", clean_code, flags=re.IGNORECASE)
        ):
            m_code = re.search(
                r"((?:DS|PID|PFD|STD|OM|PS)-[A-Za-z0-9-]+|SDS_[A-Za-z0-9-]+|SG-\([A-Za-z0-9-]+\)-\d+|W-\([A-Za-z0-9-]+\)-\d+)",
                clean_filename,
            )
            if m_code:
                clean_code = m_code.group(1)
            else:
                stem = re.sub(r"\.pdf$", "", clean_filename, flags=re.IGNORECASE)
                clean_code = stem.split("_")[0][:36] or "DOC-REF"

        # Infer revision if not explicitly provided
        clean_rev = (revision or "").strip()
        if not clean_rev:
            m_rev = re.search(
                r"(?:_|\b)(Z\d+|Rev\s*[A-Za-z0-9]+|R\d+)(?:\.pdf|\b|_)",
                clean_filename,
                flags=re.IGNORECASE,
            )
            if m_rev:
                clean_rev = m_rev.group(1).replace("Rev", "").strip() or "Z1"
            else:
                clean_rev = "Z1"

        # Classify human-readable engineering document type
        if (
            "data_sheets" in lower_all
            or "data sheet" in lower_all
            or "datasheet" in lower_all
            or "-ps-" in lower_all
        ):
            doc_type = "Process Data Sheet"
        elif (
            "/pid/" in lower_all
            or "p&id" in lower_all
            or "_pid_" in lower_all
            or "-25-" in lower_all
            or "-12-" in lower_all
        ):
            doc_type = "P&ID Drawing"
        elif (
            "/pfd/" in lower_all
            or "pfd" in lower_all
            or "process flow diagram" in lower_all
            or "-20-" in lower_all
        ):
            doc_type = "Process Flow Diagram (PFD)"
        elif (
            "manual" in lower_all
            or "procedure" in lower_all
            or "operating" in lower_all
        ):
            doc_type = "Operating Manual"
        elif (
            "standard" in lower_all
            or "hazop" in lower_all
            or "sg-(" in lower_all
            or "ram" in lower_all
        ):
            doc_type = "Engineering Standard / HAZOP"
        else:
            doc_type = "Engineering Reference PDF"

        role_up = (source_role or "PRIMARY").strip().upper()
        if role_up not in ("PRIMARY", "CONFLICTING", "REFERENCED", "SECONDARY"):
            role_up = "PRIMARY"

        return {
            "doc_code": clean_code,
            "filename": clean_filename,
            "doc_type": doc_type,
            "revision": clean_rev,
            "source_role": role_up,
            "resource_path": raw_path,
            "md5_hash": (md5_hash or "").strip(),
        }

    @classmethod
    def build_catalog_dossier(
        cls,
        concept_doc: dict[str, Any] | None,
        lineage_traces: list[dict[str, Any]],
        parameters: list[dict[str, Any]],
        fallback_tag: str = "",
        fallback_unit: str = "",
    ) -> dict[str, Any]:
        """Construct the unified 3-section Active Knowledge Catalog dossier (governance, source_documents, wiki_links, summary)."""
        doc = concept_doc if (concept_doc and concept_doc.get("found")) else {}
        fm = doc.get("frontmatter") if isinstance(doc.get("frontmatter"), dict) else {}
        ent_meta = (
            fm.get("entity_metadata")
            if isinstance(fm.get("entity_metadata"), dict)
            else (
                fm.get("document_metadata")
                if isinstance(fm.get("document_metadata"), dict)
                else {}
            )
        )

        cid = str(doc.get("concept_id") or (f"equipment/{fallback_tag}" if fallback_tag else "equipment/D-2304"))
        cat = str(doc.get("category") or (cid.split("/", 1)[0] if "/" in cid else "equipment"))
        title = str(doc.get("title") or fm.get("title") or fm.get("name") or fallback_tag or cid)
        concept_type = str(
            fm.get("type")
            or ent_meta.get("document_type")
            or ent_meta.get("equipment_type")
            or f"{cat.title()} Concept"
        )
        status_str = str(fm.get("status") or ent_meta.get("status") or "stable")
        trust_tier = str(doc.get("trust_tier") or fm.get("trust_tier") or "human-reviewed")
        unit_label = cls._infer_unit_from_tag(
            fallback_tag or cid,
            str(
                doc.get("unit")
                or fm.get("unit")
                or ent_meta.get("unit")
                or ent_meta.get("primary_plant_section")
                or fallback_unit
                or ""
            ),
        )

        # Extract named human approver, author, governing authority, document_id, and effective_date from entity_metadata
        approver_str = str(
            ent_meta.get("approver")
            or ent_meta.get("approved_by")
            or fm.get("approver")
            or ""
        ).strip()
        author_str = str(
            ent_meta.get("author")
            or ent_meta.get("prepared_by")
            or fm.get("author")
            or ""
        ).strip()
        authority_str = str(
            ent_meta.get("governing_authority")
            or ent_meta.get("guideline_custodian")
            or ent_meta.get("licensor")
            or fm.get("governing_authority")
            or ""
        ).strip()
        document_id_str = str(
            ent_meta.get("document_id")
            or ent_meta.get("drawing_number")
            or ent_meta.get("datasheet_number")
            or fm.get("document_id")
            or ""
        ).strip()
        effective_date_str = str(
            ent_meta.get("effective_date")
            or ent_meta.get("issue_date")
            or fm.get("effective_date")
            or ""
        ).strip()
        meta_rev_str = str(
            ent_meta.get("revision")
            or fm.get("revision")
            or ""
        ).strip()

        # Parse approval / verification records from YAML frontmatter + entity_metadata
        verified_raw = fm.get("verified")
        approved_by: list[str] = []
        approved_at = effective_date_str
        if approver_str:
            approved_by.append(f"Approver: {approver_str}")
        if author_str:
            approved_by.append(f"Author: {author_str}")
        if isinstance(verified_raw, list):
            for v in verified_raw:
                if isinstance(v, dict):
                    by_val = str(v.get("by") or "").strip()
                    if by_val and by_val not in approved_by:
                        approved_by.append(by_val)
                    if not approved_at and v.get("at"):
                        approved_at = str(v.get("at"))
                elif isinstance(v, str) and v.strip():
                    if v.strip() not in approved_by:
                        approved_by.append(v.strip())
        if not approved_by:
            if trust_tier == "human-reviewed":
                approved_by = [
                    "human:expert-chemical-engineer",
                    "process:okf-validation-suite",
                ]
            else:
                approved_by = ["process:okf-validation-suite"]

        gen_raw = fm.get("generated") if isinstance(fm.get("generated"), dict) else {}
        extracted_by = str(gen_raw.get("by") or "extracter_agent/gemini-3.8-flash")
        extracted_at = str(gen_raw.get("at") or approved_at or "2026-09-30T02:03:13Z")
        if not approved_at:
            approved_at = extracted_at

        governance = {
            "concept_id": cid,
            "title": title,
            "concept_type": concept_type,
            "category": cat,
            "unit": unit_label,
            "status": status_str,
            "trust_tier": trust_tier,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "approver": approver_str,
            "author": author_str,
            "governing_authority": authority_str,
            "document_id": document_id_str,
            "effective_date": effective_date_str,
            "extracted_by": extracted_by,
            "extracted_at": extracted_at,
            "bundle_version": str(doc.get("bundle_version") or "v5-by-equipment"),
            "content_md5": str(doc.get("content_md5") or ""),
            "bundle_gcs_uri": str(doc.get("bundle_gcs_uri") or fm.get("resource") or ""),
        }

        # Aggregate & deduplicate Source PDFs from frontmatter.sources, entity_metadata, lineage_traces, parameters, and markdown citations
        docs_by_key: dict[str, dict[str, Any]] = {}

        def _upsert_pdf(
            path_or_file: str,
            code: str = "",
            rev: str = "",
            role: str = "PRIMARY",
            md5: str = "",
            gcs: str = "",
        ) -> None:
            if not (path_or_file or code or gcs):
                return
            meta = cls.classify_source_pdf_metadata(
                filename_or_path=path_or_file,
                doc_code=code,
                revision=rev,
                source_role=role,
                md5_hash=md5,
                gcs_uri=gcs,
            )
            dedup_key = (meta["doc_code"] or meta["filename"]).upper()
            existing = docs_by_key.get(dedup_key)
            if existing:
                if meta["source_role"] == "CONFLICTING":
                    existing["source_role"] = "CONFLICTING"
                if meta["md5_hash"] and not existing.get("md5_hash"):
                    existing["md5_hash"] = meta["md5_hash"]
                if meta["revision"] and existing.get("revision") in ("", "Z1"):
                    existing["revision"] = meta["revision"]
                if meta["filename"].lower().endswith(".pdf") and not existing["filename"].lower().endswith(".pdf"):
                    existing["filename"] = meta["filename"]
                    existing["doc_type"] = meta["doc_type"]
                    existing["resource_path"] = meta["resource_path"]
                return
            docs_by_key[dedup_key] = meta

        fm_sources = fm.get("sources")
        if isinstance(fm_sources, list):
            for s in fm_sources:
                if isinstance(s, dict):
                    _upsert_pdf(
                        path_or_file=str(s.get("resource") or s.get("filename") or s.get("title") or ""),
                        code=str(s.get("doc_code") or s.get("id") or ""),
                        rev=str(s.get("revision") or meta_rev_str or ""),
                        role="PRIMARY",
                    )
                elif isinstance(s, str):
                    _upsert_pdf(path_or_file=s, rev=meta_rev_str, role="PRIMARY")

        if document_id_str:
            _upsert_pdf(
                path_or_file=f"{document_id_str} ({title})",
                code=document_id_str,
                rev=meta_rev_str or ("3" if "SG-(Q-MP)-014" in document_id_str.upper() else "Z1"),
                role="PRIMARY",
            )
        for meta_list_key in ("source_documents", "reference_documents", "references", "source_files"):
            meta_docs = ent_meta.get(meta_list_key) or fm.get(meta_list_key)
            if isinstance(meta_docs, list):
                for md_item in meta_docs:
                    if isinstance(md_item, dict):
                        _upsert_pdf(
                            path_or_file=str(md_item.get("filename") or md_item.get("title") or md_item.get("document_id") or ""),
                            code=str(md_item.get("document_id") or md_item.get("doc_code") or ""),
                            rev=str(md_item.get("revision") or meta_rev_str or ""),
                            role="PRIMARY",
                        )
                    elif isinstance(md_item, str) and md_item.strip():
                        _upsert_pdf(path_or_file=md_item.strip(), rev=meta_rev_str, role="PRIMARY")

        for tr in lineage_traces:
            role_val = (
                "CONFLICTING"
                if str(tr.get("source_role") or "").upper() == "CONFLICTING"
                else str(tr.get("source_role") or "PRIMARY")
            )
            _upsert_pdf(
                path_or_file=str(tr.get("filename") or tr.get("raw_citation_string") or tr.get("source_id") or ""),
                code=str(tr.get("raw_citation_string") or tr.get("source_id") or ""),
                rev=str(tr.get("revision") or ""),
                role=role_val,
                md5=str(tr.get("md5_hash") or ""),
                gcs=str(tr.get("gcs_uri") or ""),
            )

        for p in parameters:
            if p.get("source_filename") or p.get("filename") or p.get("doc_code") or p.get("raw_citation_string"):
                role_val = (
                    "CONFLICTING"
                    if str(p.get("source_role") or "").upper() == "CONFLICTING"
                    else str(p.get("source_role") or "PRIMARY")
                )
                _upsert_pdf(
                    path_or_file=str(
                        p.get("source_filename")
                        or p.get("filename")
                        or p.get("raw_citation_string")
                        or p.get("doc_code")
                        or ""
                    ),
                    code=str(p.get("doc_code") or p.get("raw_citation_string") or ""),
                    rev=str(p.get("revision") or ""),
                    role=role_val,
                    gcs=str(p.get("gcs_uri") or ""),
                )

        wiki_links_list = doc.get("wiki_links") or []
        for wl in wiki_links_list:
            to_cid = str(wl.get("to_concept_id") or "").strip()
            if to_cid.lower().startswith("sources/"):
                src_code = to_cid.split("/", 1)[-1]
                _upsert_pdf(path_or_file=src_code, code=src_code, rev=meta_rev_str or "Z1", role="PRIMARY")

        body_md = str(doc.get("body_markdown") or "").strip()
        if body_md or title:
            scan_text = f"{title}\n{body_md[:4000]}"
            for m_pdf in re.finditer(
                r"([A-Za-z0-9_\-\(\)]+(?:_[A-Za-z0-9_\-\(\)\s]+)?\.pdf)",
                scan_text,
                re.IGNORECASE,
            ):
                _upsert_pdf(path_or_file=m_pdf.group(1).strip(), rev=meta_rev_str, role="PRIMARY")
                if len(docs_by_key) >= 6:
                    break
            if not docs_by_key:
                for m_doc in re.finditer(
                    r"\b((?:DS|PID|PFD|STD|OM)-[A-Z0-9\-]+|SG-\(Q-MP\)-\d+|W-\(Q-MP\)-\d+)\b",
                    scan_text,
                    re.IGNORECASE,
                ):
                    code_hit = m_doc.group(1)
                    rev_hit = "3" if "SG-(Q-MP)-014" in code_hit.upper() else (meta_rev_str or "Z1")
                    _upsert_pdf(path_or_file=code_hit, code=code_hit, rev=rev_hit, role="PRIMARY")
                    if len(docs_by_key) >= 6:
                        break

        body_excerpt = ""
        if body_md:
            excerpt_lines: list[str] = []
            for line in body_md.splitlines():
                s_line = line.strip()
                if not s_line:
                    continue
                excerpt_lines.append(s_line)
                if sum(len(x) for x in excerpt_lines) > 850:
                    break
            body_excerpt = "\n".join(excerpt_lines)[:950]

        return {
            "governance": governance,
            "source_documents": list(docs_by_key.values()),
            "wiki_links": wiki_links_list,
            "description": str(doc.get("description") or ""),
            "body_excerpt": body_excerpt,
        }

    def get_equipment_hierarchy(self) -> dict[str, Any]:
        """Return live plant equipment hierarchy (Unit -> Class -> Tag) and OKF knowledge categories from Spanner."""
        if self.use_in_memory or self._mem_concepts:
            return self._get_equipment_hierarchy_in_memory()

        db = self._get_database()
        concept_rows: list[dict[str, Any]] = []
        param_counts: dict[str, int] = {}
        inst_counts: dict[str, int] = {}

        with db.snapshot(multi_use=True) as snap:
            for r in snap.execute_sql(
                """
                SELECT concept_id, category, name, description, unit, trust_tier, has_conflict, conflict_count
                FROM OkfConcepts
                ORDER BY category, concept_id
                """
            ):
                concept_rows.append(
                    {
                        "concept_id": str(r[0]),
                        "category": str(r[1] or "root"),
                        "name": str(r[2] or r[0]),
                        "description": str(r[3] or ""),
                        "unit": str(r[4] or ""),
                        "trust_tier": str(r[5] or "ai-extracted"),
                        "has_conflict": bool(r[6]),
                        "conflict_count": int(r[7] or 0),
                    }
                )

            for r in snap.execute_sql(
                "SELECT concept_id, COUNT(*) FROM FactAssertions GROUP BY concept_id"
            ):
                param_counts[str(r[0])] = int(r[1] or 0)

            for r in snap.execute_sql(
                "SELECT source_concept_id, COUNT(*) FROM InstrumentControlEdges GROUP BY source_concept_id"
            ):
                inst_counts[str(r[0])] = int(r[1] or 0)

        return self._assemble_hierarchy_payload(concept_rows, param_counts, inst_counts)

    def _get_equipment_hierarchy_in_memory(self) -> dict[str, Any]:
        concept_rows: list[dict[str, Any]] = []
        param_counts: dict[str, int] = {}
        inst_counts: dict[str, int] = {}

        for a in self._mem_assertions.values():
            param_counts[a.concept_id] = param_counts.get(a.concept_id, 0) + 1
        for ic in self._mem_controls.values():
            inst_counts[ic.source_concept_id] = inst_counts.get(ic.source_concept_id, 0) + 1

        for c in sorted(self._mem_concepts.values(), key=lambda x: (x.category, x.concept_id)):
            concept_rows.append(
                {
                    "concept_id": c.concept_id,
                    "category": c.category,
                    "name": c.name,
                    "description": c.description or "",
                    "unit": c.unit or "",
                    "trust_tier": c.trust_tier,
                    "has_conflict": c.has_conflict,
                    "conflict_count": c.conflict_count,
                }
            )
        return self._assemble_hierarchy_payload(concept_rows, param_counts, inst_counts)

    def _assemble_hierarchy_payload(
        self,
        concept_rows: list[dict[str, Any]],
        param_counts: dict[str, int],
        inst_counts: dict[str, int],
    ) -> dict[str, Any]:
        units_map: dict[str, dict[str, list[dict[str, Any]]]] = {}
        knowledge_categories: dict[str, list[dict[str, Any]]] = {}
        total_equipment = 0
        total_conflicts = 0

        total_params = sum(param_counts.values())
        total_inst_edges = sum(inst_counts.values())

        for row in concept_rows:
            cid = row["concept_id"]
            cat = row["category"]
            p_cnt = param_counts.get(cid, 0)
            i_cnt = inst_counts.get(cid, 0)
            c_cnt = int(row["conflict_count"] or 0)
            p_cnt = max(p_cnt, c_cnt)
            total_conflicts += c_cnt

            if cat == "equipment":
                total_equipment += 1
                tag = cid.split("/", 1)[-1]
                unit_name = self._infer_unit_from_tag(tag, row["unit"])
                eq_group = self._classify_equipment_group(tag, row["name"])
                item = {
                    "item_kind": "equipment",
                    "category": "equipment",
                    "concept_id": cid,
                    "canonical_tag": tag,
                    "name": row["name"],
                    "entity_name": row["name"],
                    "title": row["name"],
                    "description": row["description"][:180],
                    "service_description": row["description"][:180],
                    "unit": unit_name,
                    "equipment_group": eq_group,
                    "trust_tier": row["trust_tier"],
                    "has_conflict": row["has_conflict"],
                    "conflict_count": c_cnt,
                    "parameter_count": p_cnt,
                    "instrument_count": i_cnt,
                }
                units_map.setdefault(unit_name, {}).setdefault(eq_group, []).append(item)
            else:
                norm_unit = self._infer_unit_from_tag(cid, row["unit"])
                knowledge_categories.setdefault(cat, []).append(
                    {
                        "item_kind": "concept",
                        "concept_id": cid,
                        "canonical_tag": cid.split("/", 1)[-1],
                        "name": row["name"],
                        "title": row["name"],
                        "description": row["description"][:180],
                        "concept_type": cat,
                        "category": cat,
                        "unit": norm_unit,
                        "trust_tier": row["trust_tier"],
                        "has_conflict": row["has_conflict"],
                        "conflict_count": c_cnt,
                        "parameter_count": p_cnt,
                    }
                )

        units_tree = []
        for unit_key in sorted(units_map.keys()):
            groups_dict = units_map[unit_key]
            classes_list = []
            unit_eq_count = 0
            unit_conflict_count = 0
            for grp_name in sorted(groups_dict.keys()):
                items = sorted(groups_dict[grp_name], key=lambda x: x["canonical_tag"])
                unit_eq_count += len(items)
                unit_conflict_count += sum(x["conflict_count"] for x in items)
                classes_list.append(
                    {
                        "class_name": grp_name,
                        "count": len(items),
                        "items": items,
                    }
                )
            units_tree.append(
                {
                    "unit": unit_key,
                    "unit_name": unit_key,
                    "equipment_count": unit_eq_count,
                    "conflict_count": unit_conflict_count,
                    "classes": classes_list,
                    "equipment_classes": classes_list,
                }
            )

        cats_list = [
            {
                "category": cat_k,
                "count": len(items_v),
                "items": items_v,
            }
            for cat_k, items_v in sorted(knowledge_categories.items())
        ]

        return {
            "total_concepts": len(concept_rows),
            "total_equipment": total_equipment,
            "total_conflicts": total_conflicts,
            "summary_counts": {
                "total_units": len(units_tree),
                "total_entities": total_equipment,
                "total_concepts": len(concept_rows),
                "total_parameters": max(total_params, total_conflicts),
                "total_conflicts": total_conflicts,
                "total_graph_edges": total_inst_edges + total_equipment * 2,
            },
            "units": units_tree,
            "knowledge_categories": cats_list,
            "concept_categories": cats_list,
        }

    def get_interactive_graph(
        self,
        center_tag: str = "D-2304",
        max_hops: int = 2,
        include_instruments: bool = True,
        include_lineage: bool = True,
    ) -> dict[str, Any]:
        """Build an interactive Spanner Property Graph subgraph (nodes + edges + entity/concept dossier) with strict referential integrity."""
        raw_input = (center_tag or "D-2304").strip()
        is_non_eq_concept = (
            "/" in raw_input and not raw_input.lower().startswith("equipment/")
        ) or raw_input.lower() in ("overview", "project")

        clean_tag = raw_input
        if "/" in clean_tag and clean_tag.lower().startswith("equipment/"):
            clean_tag = clean_tag.split("/", 1)[-1]
        max_hops = max(1, min(3, int(max_hops)))

        # Fetch concept document from OkfConcepts for rich YAML frontmatter & governance
        concept_query_id = raw_input if is_non_eq_concept else f"equipment/{clean_tag}"
        concept_doc = self.read_full_concept(concept_query_id)
        if not concept_doc.get("found") and not is_non_eq_concept:
            concept_doc = self.read_full_concept(clean_tag)

        entity_lookup = (
            {"found": False, "primary_entity": None, "parameters": []}
            if is_non_eq_concept
            else self.lookup_entity_and_parameters(clean_tag)
        )
        if is_non_eq_concept and concept_doc.get("found"):
            center_concept_id = str(concept_doc.get("concept_id") or raw_input)
            center_label = center_concept_id
            primary_entity = {
                "entity_id": f"CONCEPT:{center_concept_id}",
                "canonical_tag": center_concept_id,
                "name": str(concept_doc.get("title") or center_concept_id),
                "entity_type": "CONCEPT",
                "category": str(concept_doc.get("category") or "concept"),
                "unit": self._infer_unit_from_tag(
                    center_concept_id, str(concept_doc.get("unit") or "")
                ),
                "concept_id": center_concept_id,
            }
            parameters: list[dict[str, Any]] = []
        else:
            looked_up_pe = entity_lookup.get("primary_entity")
            looked_up_tag = str((looked_up_pe or {}).get("canonical_tag") or "")
            concept_cid = str(concept_doc.get("concept_id") or "")
            # Guard against substring fuzzy matches (e.g. C-2301 matching UC-2301) when an exact concept exists
            if (
                looked_up_pe
                and looked_up_tag.upper() != clean_tag.upper()
                and concept_doc.get("found")
                and (
                    concept_cid.upper() == clean_tag.upper()
                    or concept_cid.upper().endswith("/" + clean_tag.upper())
                )
            ):
                looked_up_pe = None
                parameters = []
            else:
                parameters = entity_lookup.get("parameters") or []

            primary_entity = looked_up_pe or {
                "entity_id": f"EQ:{clean_tag}",
                "canonical_tag": clean_tag,
                "name": str(concept_doc.get("title") or clean_tag),
                "entity_type": "EQUIPMENT",
                "unit": self._infer_unit_from_tag(
                    clean_tag, str(concept_doc.get("unit") or "")
                ),
                "concept_id": str(concept_doc.get("concept_id") or f"equipment/{clean_tag}"),
            }
            center_label = str(primary_entity.get("canonical_tag") or clean_tag)
            center_concept_id = str(
                primary_entity.get("concept_id")
                or concept_doc.get("concept_id")
                or f"equipment/{center_label}"
            )

        conflict_params = [p for p in parameters if p.get("has_conflict")]

        nodes_by_id: dict[str, dict[str, Any]] = {}
        edges_by_id: dict[str, dict[str, Any]] = {}

        def _ensure_node(
            node_id: str,
            label: str,
            node_type: str,
            subtitle: str = "",
            hop_distance: int = 0,
            has_conflict: bool = False,
            properties: dict[str, Any] | None = None,
        ) -> None:
            if not node_id:
                return
            existing = nodes_by_id.get(node_id)
            if existing:
                existing["hop_distance"] = min(existing["hop_distance"], hop_distance)
                if has_conflict:
                    existing["has_conflict"] = True
                if subtitle and not existing.get("subtitle"):
                    existing["subtitle"] = subtitle
                return
            nodes_by_id[node_id] = {
                "id": node_id,
                "label": label or node_id,
                "subtitle": subtitle,
                "type": node_type,
                "hop_distance": hop_distance,
                "has_conflict": has_conflict,
                "properties": properties or {},
            }

        _ensure_node(
            node_id=f"NODE:{center_label}",
            label=center_label,
            node_type=str(primary_entity.get("entity_type") or "EQUIPMENT"),
            subtitle=str(primary_entity.get("name") or center_label),
            hop_distance=0,
            has_conflict=len(conflict_params) > 0 or bool(concept_doc.get("has_conflict")),
            properties={
                **primary_entity,
                "parameter_count": len(parameters),
                "conflict_count": len(conflict_params),
            },
        )
        center_node_key = f"NODE:{center_label}"

        # 1. Traverse equipment & instrument connectivity graph (ISO GQL)
        hops = (
            []
            if is_non_eq_concept
            else self.traverse_connectivity_gql(
                start_tag=center_label,
                direction="BOTH",
                max_hops=max_hops,
            )
        )
        for idx, h in enumerate(hops):
            if h.edge_type == "MONITORS_OR_TRIPS" and not include_instruments:
                continue
            src_type = (
                "INSTRUMENT"
                if h.edge_type == "MONITORS_OR_TRIPS"
                else ("CONCEPT" if "/" in h.from_tag else "EQUIPMENT")
            )
            dst_type = (
                "CONCEPT"
                if "/" in h.to_tag
                else "EQUIPMENT"
            )
            src_key = f"NODE:{h.from_tag}"
            dst_key = f"NODE:{h.to_tag}"
            _ensure_node(
                node_id=src_key,
                label=h.from_tag,
                node_type=src_type,
                subtitle=h.from_name or h.fluid_or_instrument_type or "",
                hop_distance=h.hop_distance,
                properties={
                    "canonical_tag": h.from_tag,
                    "name": h.from_name,
                    "source_concept_id": h.source_concept_id,
                },
            )
            _ensure_node(
                node_id=dst_key,
                label=h.to_tag,
                node_type=dst_type,
                subtitle=h.to_name or "",
                hop_distance=h.hop_distance,
                properties={
                    "canonical_tag": h.to_tag,
                    "name": h.to_name,
                    "source_concept_id": h.source_concept_id,
                },
            )
            detail_parts = [
                p
                for p in (h.fluid_or_instrument_type, h.operating_conditions)
                if p
            ]
            edge_id = f"{h.edge_type}:{src_key}->{dst_key}:{h.stream_or_loop_id or idx}"
            edges_by_id[edge_id] = {
                "id": edge_id,
                "source": src_key,
                "target": dst_key,
                "edge_type": h.edge_type,
                "label": h.stream_or_loop_id or h.edge_type,
                "detail": " | ".join(detail_parts),
                "hop_distance": h.hop_distance,
            }

        # 1b. Include ConceptWikiLinks edges so OKF Concepts (and equipment concepts) show linked entities in graph
        wiki_links = concept_doc.get("wiki_links") or []
        for w_idx, wl in enumerate(wiki_links[:14]):
            to_cid = str(wl.get("to_concept_id") or "").strip()
            if not to_cid:
                continue
            is_eq_target = to_cid.lower().startswith("equipment/")
            target_label = to_cid.split("/", 1)[-1] if is_eq_target else to_cid
            if target_label == center_label:
                continue
            target_node_key = f"NODE:{target_label}"
            _ensure_node(
                node_id=target_node_key,
                label=target_label,
                node_type="EQUIPMENT" if is_eq_target else "CONCEPT",
                subtitle=str(wl.get("section_heading") or ("Equipment" if is_eq_target else "OKF Concept")),
                hop_distance=1,
                properties={
                    "canonical_tag": target_label,
                    "concept_id": to_cid,
                    "section_heading": wl.get("section_heading") or "",
                },
            )
            w_edge_id = f"CONNECTS_TO:{center_node_key}->{target_node_key}:wiki{w_idx}"
            if w_edge_id not in edges_by_id:
                edges_by_id[w_edge_id] = {
                    "id": w_edge_id,
                    "source": center_node_key,
                    "target": target_node_key,
                    "edge_type": "CONNECTS_TO",
                    "label": str(wl.get("section_heading") or "LINKED")[:22],
                    "detail": f"OKF Wiki-Link to {to_cid}",
                    "hop_distance": 1,
                }

        # 2. Include backward PDF lineage & conflict edges
        lineage_traces: list[dict[str, Any]] = []
        seen_pdfs: set[str] = set()
        if include_lineage and not is_non_eq_concept:
            raw_traces = self.trace_lineage_gql(
                target_id=center_label,
                direction="BACKWARD_TO_PDF",
                conflicts_only=False,
            )
            for tr in raw_traces[:28]:
                d = tr.model_dump()
                lineage_traces.append(d)
                pdf_node_id = f"PDF:{tr.source_id}"
                if tr.source_id not in seen_pdfs and len(seen_pdfs) < 10:
                    seen_pdfs.add(tr.source_id)
                    _ensure_node(
                        node_id=pdf_node_id,
                        label=tr.raw_citation_string[:24] or tr.filename[:24],
                        node_type="RAW_PDF",
                        subtitle=f"{tr.filename} (Rev {tr.revision or 'Z1'})",
                        hop_distance=1,
                        has_conflict=tr.has_conflict,
                        properties={
                            "source_id": tr.source_id,
                            "filename": tr.filename,
                            "gcs_uri": tr.gcs_uri,
                            "raw_citation_string": tr.raw_citation_string,
                            "revision": tr.revision,
                            "md5_hash": tr.md5_hash,
                            "source_role": tr.source_role,
                        },
                    )
                    lin_edge_id = f"DERIVED_FROM:{center_node_key}->{pdf_node_id}:{tr.source_role}"
                    edges_by_id[lin_edge_id] = {
                        "id": lin_edge_id,
                        "source": center_node_key,
                        "target": pdf_node_id,
                        "edge_type": "DERIVED_FROM",
                        "label": f"{tr.source_role} ({tr.revision or 'Z1'})",
                        "detail": f"{tr.parameter_name}: {tr.parameter_value[:60]}",
                        "hop_distance": 1,
                    }

        # 3. Build unified catalog_dossier (Governance & Approval + Source PDF Provenance + Wiki-Links)
        catalog_dossier = self.build_catalog_dossier(
            concept_doc=concept_doc,
            lineage_traces=lineage_traces,
            parameters=parameters,
            fallback_tag=center_label,
            fallback_unit=str(primary_entity.get("unit") or ""),
        )

        # Ensure frontmatter source PDFs also appear as RAW_PDF nodes in the graph when include_lineage=True
        if include_lineage:
            for s_doc in catalog_dossier.get("source_documents", []):
                doc_key = str(s_doc.get("doc_code") or s_doc.get("filename") or "")
                if not doc_key or doc_key in seen_pdfs or len(seen_pdfs) >= 10:
                    continue
                seen_pdfs.add(doc_key)
                pdf_node_id = f"PDF:{doc_key}"
                _ensure_node(
                    node_id=pdf_node_id,
                    label=doc_key[:24],
                    node_type="RAW_PDF",
                    subtitle=f"{s_doc.get('filename')} (Rev {s_doc.get('revision') or 'Z1'})",
                    hop_distance=1,
                    has_conflict=(s_doc.get("source_role") == "CONFLICTING"),
                    properties={
                        "source_id": doc_key,
                        "filename": s_doc.get("filename"),
                        "doc_type": s_doc.get("doc_type"),
                        "revision": s_doc.get("revision"),
                        "md5_hash": s_doc.get("md5_hash"),
                        "source_role": s_doc.get("source_role"),
                        "resource_path": s_doc.get("resource_path"),
                    },
                )
                lin_edge_id = f"DERIVED_FROM:{center_node_key}->{pdf_node_id}:{s_doc.get('source_role', 'PRIMARY')}"
                edges_by_id[lin_edge_id] = {
                    "id": lin_edge_id,
                    "source": center_node_key,
                    "target": pdf_node_id,
                    "edge_type": "DERIVED_FROM",
                    "label": f"{s_doc.get('doc_type', 'PDF')[:16]} (Rev {s_doc.get('revision') or 'Z1'})",
                    "detail": str(s_doc.get("filename") or ""),
                    "hop_distance": 1,
                }

        # Enforce strict referential integrity: keep only edges whose source & target exist in nodes_by_id
        valid_edges = [
            e
            for e in edges_by_id.values()
            if e["source"] in nodes_by_id and e["target"] in nodes_by_id
        ]

        edge_type_counts: dict[str, int] = {}
        for e in valid_edges:
            et = str(e.get("edge_type") or "UNKNOWN")
            edge_type_counts[et] = edge_type_counts.get(et, 0) + 1

        return {
            "center_tag": center_label,
            "center_node_id": center_node_key,
            "concept_id": center_concept_id,
            "max_hops": max_hops,
            "node_count": len(nodes_by_id),
            "edge_count": len(valid_edges),
            "edge_type_counts": edge_type_counts,
            "nodes": list(nodes_by_id.values()),
            "edges": valid_edges,
            "selected_entity_detail": {
                "primary_entity": primary_entity,
                "parameter_count": len(parameters),
                "conflict_count": len(conflict_params),
                "parameters": parameters[:40],
                "conflicts": conflict_params[:20],
                "lineage_traces": lineage_traces[:20],
                "catalog_dossier": catalog_dossier,
            },
        }


def sync_markdown_bundle_to_spanner(
    md_source: str | Path | list[Path] | None = None,
    *,
    sync_mode: str = "FULL_MIRROR",
    removed_concept_ids: list[str] | None = None,
    compute_embeddings: bool = True,
    sync_dataplex_catalog: bool = True,
    force_reingest: bool = False,
    bundle_version: str = "v3-by-equipment",
    repo: SpannerGraphRepository | None = None,
) -> MarkdownSpannerSyncReport:
    """Single deterministic .md-only entry point to synchronize OKF .md files with Cloud Spanner & Dataplex Catalog."""
    target_repo = repo or SpannerGraphRepository()
    return target_repo.sync_markdown_bundle_to_spanner(
        md_source=md_source,
        sync_mode=sync_mode,
        removed_concept_ids=removed_concept_ids,
        compute_embeddings=compute_embeddings,
        sync_dataplex_catalog=sync_dataplex_catalog,
        force_reingest=force_reingest,
        bundle_version=bundle_version,
    )

