"""Property-Based Tests (Hypothesis) for the OKF Spanner Graph-RAG & Data Lineage Query Agent.

Verifies mathematical and structural invariants across generative inputs per SDD Section 4.2.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from query_agent.guardrails import (
    QuerySecurityGuardrailError,
    query_agent_before_callback,
)
from query_agent.models.schemas import (
    BundleGraphExtractionResult,
    EngineeringEntityNode,
    OkfConceptNode,
    ProcessConnectionEdge,
    compute_deterministic_id,
)
from query_agent.spanner.lineage_extractor import chunk_markdown_preserving_headers
from query_agent.spanner.repository import (
    SpannerGraphRepository,
    cosine_similarity,
    deterministic_hash_embedding,
)


@settings(max_examples=40)
@given(
    part_a=st.text(min_size=1, max_size=50),
    part_b=st.text(min_size=1, max_size=50),
    prefix=st.sampled_from(["FACT", "LIN", "CONN", "CHUNK", ""]),
)
def test_property_deterministic_id_idempotence_and_prefix(
    part_a: str,
    part_b: str,
    prefix: str,
) -> None:
    """Property 1: compute_deterministic_id is strictly idempotent and honors prefix."""
    first = compute_deterministic_id(part_a, part_b, prefix=prefix)
    second = compute_deterministic_id(f"  {part_a}  ", f" {part_b} ", prefix=prefix)
    assert first == second
    if prefix:
        assert first.startswith(f"{prefix}:")


@settings(max_examples=25)
@given(
    num_rows=st.integers(min_value=1, max_value=90),
    max_rows=st.integers(min_value=5, max_value=25),
)
def test_property_header_preserving_table_chunking_invariant(
    num_rows: int,
    max_rows: int,
) -> None:
    """Property 2: Every table chunk produced by chunk_markdown_preserving_headers preserves the header and separator."""
    header = "| Parameter | Value | Unit | Source |"
    sep = "| :--- | :--- | :--- | :--- |"
    body_rows = [f"| P-{i} | {i} | bar | Doc-{i} |" for i in range(num_rows)]
    md = "## Design Table\n" + header + "\n" + sep + "\n" + "\n".join(body_rows)

    chunks = chunk_markdown_preserving_headers(
        concept_id="equipment/R-2301",
        category="equipment",
        unit="U2300",
        body_markdown=md,
        max_rows_per_chunk=max_rows,
    )
    assert len(chunks) >= 1
    for idx, ch in enumerate(chunks):
        assert ch.chunk_index == idx
        assert header in ch.header_preserved_markdown
        assert sep in ch.header_preserved_markdown


@settings(max_examples=35)
@given(
    text_a=st.text(min_size=1, max_size=200),
    text_b=st.text(min_size=1, max_size=200),
)
def test_property_embedding_unit_norm_and_cosine_symmetry(
    text_a: str,
    text_b: str,
) -> None:
    """Property 3: 768-d embeddings have unit L2 norm and cosine_similarity is symmetric and bounded in [-1, 1]."""
    vec_a = deterministic_hash_embedding(text_a, dim=768)
    vec_b = deterministic_hash_embedding(text_b, dim=768)
    assert len(vec_a) == 768
    assert len(vec_b) == 768

    norm_a = math.sqrt(sum(x * x for x in vec_a))
    assert abs(norm_a - 1.0) < 1e-3

    sim_ab = cosine_similarity(vec_a, vec_b)
    sim_ba = cosine_similarity(vec_b, vec_a)
    assert -1.0 <= sim_ab <= 1.0
    assert abs(sim_ab - sim_ba) < 1e-9


@settings(max_examples=20)
@given(
    query=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
        min_size=3,
        max_size=60,
    ),
    top_k=st.integers(min_value=1, max_value=10),
)
def test_property_hybrid_rrf_monotonic_score_ordering(
    query: str,
    top_k: int,
) -> None:
    """Property 4: Hybrid RRF search results are monotonically non-increasing in rrf_score and bounded by top_k."""
    repo = SpannerGraphRepository(use_in_memory=True)
    concepts = []
    chunks = []
    for i in range(6):
        cid = f"equipment/E-230{i}"
        md = f"## Section {i}\nHeat exchanger E-230{i} operating temperature {80 + i * 10} C pressure {i} bar."
        concepts.append(
            OkfConceptNode(
                concept_id=cid,
                category="equipment",
                name=f"Exchanger E-230{i}",
                body_markdown=md,
                md5_hash=f"md5_{i}",
            )
        )
        chunks.extend(
            chunk_markdown_preserving_headers(
                concept_id=cid,
                category="equipment",
                unit="U2300",
                body_markdown=md,
            )
        )
    repo.upsert_bundle_graph(
        BundleGraphExtractionResult(concepts=concepts, chunks=chunks),
        compute_embeddings=True,
    )
    results = repo.hybrid_rrf_search(query=query, top_k=top_k)
    assert len(results) <= top_k
    for i in range(len(results) - 1):
        assert results[i].rrf_score >= results[i + 1].rrf_score


@settings(max_examples=20)
@given(max_hops=st.integers(min_value=1, max_value=5))
def test_property_graph_traversal_hop_distance_bounds(max_hops: int) -> None:
    """Property 5: Graph traversal never returns hops exceeding max_hops."""
    repo = SpannerGraphRepository(use_in_memory=True)
    entities = [
        EngineeringEntityNode(
            entity_id=f"EQ:N-{i:04d}",
            entity_type="EQUIPMENT",
            canonical_tag=f"N-{i:04d}",
            name=f"Node {i}",
            concept_id=f"equipment/N-{i:04d}",
        )
        for i in range(7)
    ]
    edges = [
        ProcessConnectionEdge(
            edge_id=f"CONN:{i}",
            from_entity_id=f"EQ:N-{i:04d}",
            to_entity_id=f"EQ:N-{i + 1:04d}",
            stream_or_line_id=f"S-{i}",
            source_concept_id=f"equipment/N-{i:04d}",
        )
        for i in range(6)
    ]
    repo.upsert_bundle_graph(
        BundleGraphExtractionResult(entities=entities, process_edges=edges),
        compute_embeddings=False,
    )
    hops = repo.traverse_connectivity_gql("N-0000", direction="DOWNSTREAM", max_hops=max_hops)
    assert len(hops) == min(max_hops, 6)
    for h in hops:
        assert 1 <= h.hop_distance <= max_hops


@settings(max_examples=20)
@given(
    prefix_noise=st.text(min_size=0, max_size=30),
    suffix_noise=st.text(min_size=0, max_size=30),
    pair=st.sampled_from(
        [
            ("ignore", "instructions"),
            ("disregard", "instructions"),
            ("bypass", "security"),
            ("modify", "reference/raw"),
            ("overwrite", "reference/wiki"),
        ]
    ),
)
def test_property_guardrail_blocks_adversarial_directives(
    prefix_noise: str,
    suffix_noise: str,
    pair: tuple[str, str],
) -> None:
    """Property 6: Pre-flight guardrail deterministically blocks all adversarial injection/mutation pairs."""
    adversarial_prompt = f"{prefix_noise} {pair[0]} some words {pair[1]} {suffix_noise}"
    with pytest.raises(QuerySecurityGuardrailError):
        query_agent_before_callback(adversarial_prompt)


@settings(max_examples=30)
@given(raw_id=st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{1,30}[A-Za-z0-9]", fullmatch=True))
def test_property_dataplex_id_normalization_idempotence(raw_id: str) -> None:
    """Property 7: _to_dataplex_id is idempotent and produces lowercase hyphen-separated Dataplex resource IDs."""
    from query_agent.spanner.catalog_sync import _to_dataplex_id

    normalized = _to_dataplex_id(raw_id)
    assert "_" not in normalized
    assert normalized == normalized.lower()
    assert _to_dataplex_id(normalized) == normalized


@settings(max_examples=15)
@given(
    num_files=st.integers(min_value=2, max_value=6),
    pressure_delta=st.integers(min_value=10, max_value=500),
)
def test_property_markdown_sync_lifecycle_invariants(
    num_files: int,
    pressure_delta: int,
) -> None:
    """Property 8: sync_markdown_bundle_to_spanner satisfies ADDED -> UNCHANGED -> UPDATED -> REMOVED invariants."""
    import tempfile
    from pathlib import Path

    from query_agent.spanner.repository import sync_markdown_bundle_to_spanner

    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_dir = Path(tmp_dir) / "bundle"
        eq_dir = bundle_dir / "equipment"
        eq_dir.mkdir(parents=True)

        repo = SpannerGraphRepository(use_in_memory=True)
        paths: list[Path] = []
        for i in range(num_files):
            p = eq_dir / f"V-230{i}.md"
            p.write_text(
                f"---\ntitle: V-230{i} — Vessel {i}\ntags: [equipment, unit 2300]\n"
                f"sources:\n  - id: s-{i}\n    resource: reference/raw/data_sheets/DS-V230{i}_Z1.pdf\n---\n\n"
                f"## Design\n| Parameter | Value | Unit | Source |\n| :--- | :--- | :--- | :--- |\n"
                f"| Pressure | {100 + i} | kPag | DS-V230{i} |\n",
                encoding="utf-8",
            )
            paths.append(p)

        # Phase 1: Initial sync -> all ADDED
        r1 = sync_markdown_bundle_to_spanner(bundle_dir, compute_embeddings=False, sync_dataplex_catalog=False, repo=repo)
        assert len(r1.added_concepts) == num_files
        assert len(r1.unchanged_concepts) == 0
        assert repo.get_catalog_counts()["total_concepts"] == num_files

        # Phase 2: Re-sync without edits -> all UNCHANGED
        r2 = sync_markdown_bundle_to_spanner(bundle_dir, compute_embeddings=False, sync_dataplex_catalog=False, repo=repo)
        assert len(r2.added_concepts) == 0
        assert len(r2.updated_concepts) == 0
        assert len(r2.unchanged_concepts) == num_files

        # Phase 3: Mutate first file -> 1 UPDATED, (num_files - 1) UNCHANGED
        paths[0].write_text(
            f"---\ntitle: V-2300 — Vessel 0\ntags: [equipment, unit 2300]\n"
            f"sources:\n  - id: s-0\n    resource: reference/raw/data_sheets/DS-V2300_Z1.pdf\n---\n\n"
            f"## Design\n| Parameter | Value | Unit | Source |\n| :--- | :--- | :--- | :--- |\n"
            f"| Pressure | {100 + pressure_delta} | kPag | DS-V2300 |\n",
            encoding="utf-8",
        )
        r3 = sync_markdown_bundle_to_spanner(bundle_dir, compute_embeddings=False, sync_dataplex_catalog=False, repo=repo)
        assert r3.updated_concepts == ["equipment/V-2300"]
        assert len(r3.unchanged_concepts) == num_files - 1

        # Phase 4: Remove last file -> 1 REMOVED, (num_files - 1) remaining in Spanner
        paths[-1].unlink()
        r4 = sync_markdown_bundle_to_spanner(bundle_dir, compute_embeddings=False, sync_dataplex_catalog=False, repo=repo)
        assert r4.removed_concepts == [f"equipment/V-230{num_files - 1}"]
        assert repo.get_catalog_counts()["total_concepts"] == num_files - 1


@settings(max_examples=12)
@given(
    initial_count=st.integers(min_value=1, max_value=4),
    reload_count=st.integers(min_value=1, max_value=4),
)
def test_property_purge_and_reload_resets_stale_concepts(
    initial_count: int,
    reload_count: int,
) -> None:
    """Property 9: purge_and_reload_spanner(purge=True) completely removes stale concepts and reloads exact target bundle."""
    import tempfile
    from pathlib import Path

    from scripts.ingest_okf_bundle_to_spanner import purge_and_reload_spanner

    with tempfile.TemporaryDirectory() as tmp_dir:
        b1 = Path(tmp_dir) / "bundle_old"
        (b1 / "equipment").mkdir(parents=True)
        for i in range(initial_count):
            (b1 / "equipment" / f"OLD-{i:04d}.md").write_text(
                f"---\ntitle: OLD-{i:04d}\ntags: [equipment]\n---\n\n## Overview\nOld equipment {i}.\n",
                encoding="utf-8",
            )

        b2 = Path(tmp_dir) / "bundle_v5"
        (b2 / "equipment").mkdir(parents=True)
        for j in range(reload_count):
            (b2 / "equipment" / f"NEW-{j:04d}.md").write_text(
                f"---\ntitle: NEW-{j:04d}\ntags: [equipment]\n---\n\n## Overview\nNew equipment {j}.\n",
                encoding="utf-8",
            )

        repo = SpannerGraphRepository(use_in_memory=True)
        purge_and_reload_spanner(
            b1,
            purge=False,
            compute_embeddings=False,
            sync_dataplex_catalog=False,
            repo=repo,
        )
        assert repo.get_catalog_counts()["total_concepts"] == initial_count

        res = purge_and_reload_spanner(
            b2,
            purge=True,
            compute_embeddings=False,
            sync_dataplex_catalog=False,
            repo=repo,
        )
        assert res["purged_spanner_counts"]["OkfConcepts"] == initial_count
        assert all(v == 0 for v in res["post_purge_counts"].values())
        assert res["sync_report"]["live_counts_after_sync"]["total_concepts"] == reload_count
        for i in range(initial_count):
            assert f"equipment/OLD-{i:04d}" not in repo._mem_concepts
        for j in range(reload_count):
            assert f"equipment/NEW-{j:04d}" in repo._mem_concepts



