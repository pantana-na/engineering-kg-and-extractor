"""Purge all data from Cloud Spanner & Dataplex Catalog and reload from an OKF v0.2 Markdown bundle.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/purge_and_reload_spanner.py \\
        --bundle-dir build/okf_bundle \\
        --bundle-version v1-acme-demo
"""

from __future__ import annotations

import sys

from scripts.ingest_okf_bundle_to_spanner import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], default_purge=True))
