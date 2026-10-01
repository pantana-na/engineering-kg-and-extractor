"""Unit tests for GCS bundle exporter."""

import tempfile
from pathlib import Path

import pytest

from extracter_agent.gcs.exporter import GCSExporter, get_blob_name, infer_content_type


def test_get_blob_name():
    """Test blob name normalization."""
    assert (
        get_blob_name("my-prefix", "equipment/V-2301.md")
        == "my-prefix/equipment/V-2301.md"
    )
    assert (
        get_blob_name("/my-prefix/", "/equipment/V-2301.md")
        == "my-prefix/equipment/V-2301.md"
    )
    assert get_blob_name("", "index.md") == "index.md"


def test_infer_content_type():
    """Test MIME content type inference for OKF files."""
    assert infer_content_type(Path("index.md")) == "text/markdown; charset=utf-8"
    assert infer_content_type(Path("config.yaml")) == "text/yaml; charset=utf-8"
    assert infer_content_type(Path("data.json")) == "application/json; charset=utf-8"


def test_export_bundle_dry_run():
    """Test dry-run export calculation without calling live GCP APIs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "index.md").write_text("# Index", encoding="utf-8")
        (root / "equipment").mkdir()
        (root / "equipment" / "V-2301.md").write_text(
            "---\ntype: Equipment\n---\n# V-2301", encoding="utf-8"
        )

        exporter = GCSExporter(bucket_name="test-bucket")
        res = exporter.export_bundle(root, prefix="bundles/test", dry_run=True)

        assert res["bucket"] == "test-bucket"
        assert res["prefix"] == "bundles/test"
        assert res["dry_run"] is True
        assert res["files_count"] == 2
        assert res["total_bytes"] > 0
        assert "gs://test-bucket/bundles/test/index.md" in res["uploaded_uris"]
        assert (
            "gs://test-bucket/bundles/test/equipment/V-2301.md" in res["uploaded_uris"]
        )


def test_export_bundle_missing_dir_raises():
    """Test error on nonexistent directory."""
    exporter = GCSExporter(bucket_name="test-bucket")
    with pytest.raises(FileNotFoundError):
        exporter.export_bundle("nonexistent/dir/path")


def test_exporter_uploads_same_size_modified_content():
    """Verify GCSExporter re-uploads a file when its content changes in-place even if byte size is identical."""
    from unittest.mock import MagicMock

    from extracter_agent.gcs.exporter import compute_file_md5_b64

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        eq_dir = root / "equipment"
        eq_dir.mkdir()
        eq_file = eq_dir / "item.md"
        eq_file.write_text("Design Pressure: 0.5 kg/cm2g", encoding="utf-8")
        orig_size = eq_file.stat().st_size
        orig_md5 = compute_file_md5_b64(eq_file)

        remote_blob = MagicMock()
        remote_blob.name = "bundles/test/equipment/item.md"
        remote_blob.size = orig_size
        remote_blob.md5_hash = orig_md5

        uploaded_blobs: list[str] = []

        def make_blob(bname: str):
            b = MagicMock()
            b.upload_from_filename.side_effect = lambda *_a, **_kw: uploaded_blobs.append(
                bname
            )
            return b

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [remote_blob]
        mock_bucket.blob.side_effect = make_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        exporter = GCSExporter(bucket_name="test-bucket", client=mock_client)

        # 1. Identical size + identical MD5 -> skipped
        exporter.export_bundle(root, prefix="bundles/test", dry_run=False)
        assert uploaded_blobs == []

        # 2. Same byte size (0.5 -> 3.9), modified content -> MD5 differs -> MUST upload!
        eq_file.write_text("Design Pressure: 3.9 kg/cm2g", encoding="utf-8")
        assert eq_file.stat().st_size == orig_size
        exporter.export_bundle(root, prefix="bundles/test", dry_run=False)
        assert uploaded_blobs == ["bundles/test/equipment/item.md"]

