"""Property-Based Tests (PBT) for GCS exporter using Hypothesis."""

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from extracter_agent.gcs.exporter import get_blob_name, infer_content_type

safe_path_chars = st.characters(whitelist_categories=("L", "N"))


@given(
    prefix=st.text(alphabet=safe_path_chars, min_size=1, max_size=20),
    part1=st.text(alphabet=safe_path_chars, min_size=1, max_size=20),
    part2=st.text(alphabet=safe_path_chars, min_size=1, max_size=20),
)
def test_pbt_get_blob_name_invariants(prefix, part1, part2):
    """Invariant: get_blob_name combines prefix and parts without double slashes."""
    rel_path = f"{part1}/{part2}.md"
    blob_name = get_blob_name(prefix, rel_path)

    assert "//" not in blob_name
    assert blob_name.startswith(prefix)
    assert blob_name.endswith(f"{part2}.md")


@given(
    ext=st.sampled_from([".md", ".yaml", ".yml", ".json", ".txt", ".bin", ""]),
    filename=st.text(alphabet=safe_path_chars, min_size=1, max_size=15),
)
def test_pbt_infer_content_type_invariants(ext, filename):
    """Invariant: infer_content_type returns a valid non-empty MIME string with a slash."""
    content_type = infer_content_type(Path(f"{filename}{ext}"))
    assert isinstance(content_type, str)
    assert "/" in content_type
    if ext == ".md":
        assert "text/markdown" in content_type
    elif ext in (".yaml", ".yml"):
        assert "text/yaml" in content_type
    elif ext == ".json":
        assert "application/json" in content_type


@given(
    payload=st.binary(min_size=1, max_size=256),
    mut_idx=st.integers(min_value=0, max_value=255),
    delta=st.integers(min_value=1, max_value=255),
)
def test_pbt_md5_cache_invalidation_on_any_mutation(
    payload: bytes, mut_idx: int, delta: int
):
    """Invariant: Any single-byte mutation (preserving exact file size) alters the base64 MD5 fingerprint."""
    import tempfile

    from extracter_agent.gcs.exporter import compute_file_md5_b64

    idx = mut_idx % len(payload)
    mutated = bytearray(payload)
    mutated[idx] = (mutated[idx] + delta) % 256
    mutated_bytes = bytes(mutated)
    assert len(mutated_bytes) == len(payload)
    assert mutated_bytes != payload

    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = Path(tmpdir) / "v1.bin"
        f2 = Path(tmpdir) / "v2.bin"
        f1.write_bytes(payload)
        f2.write_bytes(mutated_bytes)
        assert f1.stat().st_size == f2.stat().st_size
        assert compute_file_md5_b64(f1) != compute_file_md5_b64(f2)

