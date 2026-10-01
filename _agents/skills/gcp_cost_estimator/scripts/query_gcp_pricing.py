#!/usr/bin/env python3
"""
GCP Pricing Query Tool for Cost Estimation.

Queries Google Cloud Billing Catalog API (using active gcloud credentials)
or fetches live pricing from official Google Cloud pricing endpoints.

STRICT MANDATE:
- All pricing must be retrieved from live Google Cloud APIs or live official web endpoints.
- ZERO local price caching, offline benchmark dictionaries, or fallback to static cached prices is permitted.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

# Service mapping to Cloud Billing Service IDs
KNOWN_SERVICES = {
    "compute": "6F81-5844-456A",          # Compute Engine
    "compute engine": "6F81-5844-456A",
    "gce": "6F81-5844-456A",
    "gke": "6F81-5844-456A",
    "storage": "95FF-2EF5-5EA1",          # Cloud Storage
    "cloud storage": "95FF-2EF5-5EA1",
    "gcs": "95FF-2EF5-5EA1",
    "cloud run": "152E-C115-5142",        # Cloud Run
    "cloudrun": "152E-C115-5142",
    "bigquery": "24E6-581D-38E5",         # BigQuery
    "cloud sql": "9662-B51E-5089",        # Cloud SQL
    "cloudsql": "9662-B51E-5089",
    "vertex ai": "C7E2-9256-1C43",        # Vertex AI
    "vertex": "C7E2-9256-1C43",
    "pubsub": "A1E8-BE35-7EBC",           # Cloud Pub/Sub
    "cloud pub/sub": "A1E8-BE35-7EBC",
    "spanner": "D1A8-ED0B-CD04",          # Cloud Spanner
    "cloud spanner": "D1A8-ED0B-CD04",
    "datastream": "F7F6-DEBD-DB7B",       # Datastream
    "memorystore": "5440-F92D-6F40",      # Memorystore (Redis)
    "monitoring": "58CD-22C9-F11B",       # Cloud Monitoring
    "logging": "95FF-2EF5-5EA1",          # Cloud Logging
}


def get_gcloud_token() -> Optional[str]:
    """Retrieve active OAuth access token from gcloud."""
    for cmd in [
        ["gcloud", "auth", "print-access-token"],
        ["gcloud", "auth", "application-default", "print-access-token"]
    ]:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            token = res.stdout.strip()
            if token:
                return token
        except Exception:
            continue
    return None


def fetch_billing_skus(service_id: str, token: str, query: str = "", region: str = "") -> List[Dict[str, Any]]:
    """Query Cloud Billing API for SKUs belonging to a specific service."""
    url = f"https://cloudbilling.googleapis.com/v1/services/{service_id}/skus?pageSize=500"
    headers = {"Authorization": f"Bearer {token}"}

    results = []
    page_token = ""
    max_pages = 3  # paginated lookup across SKU catalog

    for _ in range(max_pages):
        page_url = url + (f"&pageToken={page_token}" if page_token else "")
        req = urllib.request.Request(page_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                skus = data.get("skus", [])
                for sku in skus:
                    desc = sku.get("description", "")
                    service_regions = sku.get("serviceRegions", [])

                    if query and query.lower() not in desc.lower():
                        continue
                    if region and region not in service_regions and "global" not in service_regions:
                        continue

                    # Extract unit rate
                    pricing_info = sku.get("pricingInfo", [])
                    price_str = "N/A"
                    unit = ""
                    nanos = 0
                    units_val = 0
                    effective_price = 0.0
                    if pricing_info:
                        expression = pricing_info[0].get("pricingExpression", {})
                        unit = expression.get("usageUnitDescription", expression.get("usageUnit", ""))
                        tiered_rates = expression.get("tieredRates", [])
                        if tiered_rates:
                            rate = tiered_rates[0].get("unitPrice", {})
                            units_val = int(rate.get("units", 0))
                            nanos = int(rate.get("nanos", 0))
                            effective_price = units_val + (nanos / 1_000_000_000.0)
                            price_str = f"${effective_price:,.6f}".rstrip("0").rstrip(".")

                    results.append({
                        "skuId": sku.get("skuId"),
                        "description": desc,
                        "regions": service_regions[:3],
                        "unit": unit,
                        "unitPriceUSD": effective_price,
                        "priceFormatted": price_str,
                        "source": "live_cloud_billing_api"
                    })

                page_token = data.get("nextPageToken")
                if not page_token:
                    break
        except Exception as e:
            print(f"[Error] Failed querying Cloud Billing API: {e}", file=sys.stderr)
            break

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Query Live Google Cloud Pricing (Strictly live API - zero local caching permitted)"
    )
    parser.add_argument(
        "--service", "-s",
        required=False,
        help="Service name or ID (e.g. compute, storage, cloudrun, bigquery, vertex, cloudsql, spanner)"
    )
    parser.add_argument(
        "--query", "-q",
        default="",
        help="Keyword filter for SKU description (e.g. 'e2-standard', 'Instance Core', 'Active')"
    )
    parser.add_argument(
        "--region", "-r",
        default="",
        help="GCP Region (e.g. us-central1, europe-west1, asia-southeast1)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON format"
    )
    parser.add_argument(
        "--list-services",
        action="store_true",
        help="List supported common service shortcuts"
    )

    args = parser.parse_args()

    if args.list_services:
        output_data = KNOWN_SERVICES if args.json else "Supported services:\n" + "\n".join(
            f"  - {k}: {v}" for k, v in KNOWN_SERVICES.items()
        )
        print(json.dumps(KNOWN_SERVICES, indent=2) if args.json else output_data)
        return

    if not args.service:
        print("Usage:")
        print("  python3 query_gcp_pricing.py --service <service> --query <sku_keyword> [--region <region>]")
        print("Example:")
        print("  python3 query_gcp_pricing.py --service compute --query 'e2-standard-4' --region us-central1")
        print("  python3 query_gcp_pricing.py --service storage --query 'Standard Storage US' --region us")
        print("\nNote: All prices are queried live. No local caching or fallback to offline benchmarks is allowed.")
        return

    service_input = args.service.lower()
    service_id = KNOWN_SERVICES.get(service_input, args.service)

    token = get_gcloud_token()
    if not token:
        print(
            "[Error] No active gcloud authorization token found. "
            "Run 'gcloud auth application-default login' or authenticate with gcloud. "
            "Zero local price caching is permitted; prices must be verified live from official Google Cloud APIs "
            "or via live web search at https://cloud.google.com/<product>/pricing.",
            file=sys.stderr
        )
        sys.exit(1)

    skus = fetch_billing_skus(service_id, token, query=args.query, region=args.region)

    if not skus:
        print(
            f"[Error] Live Cloud Billing API returned 0 matching SKUs for query '{args.query}' in service '{args.service}' "
            f"(Region: '{args.region or 'any'}').\n"
            "Per repository policy, NO local price caching or fallback to static benchmark tables is permitted.\n"
            f"Please refine your query or check live pricing directly on the official Google Cloud website: "
            f"https://cloud.google.com/{args.service}/pricing (via search_web or read_url_content).",
            file=sys.stderr
        )
        sys.exit(1)

    if args.json:
        print(json.dumps(skus, indent=2))
    else:
        print(f"\n=== Live Billing SKUs for '{args.service}' (Filter: '{args.query}', Region: '{args.region or 'any'}') ===")
        print(f"{'Description':<65} | {'Unit Price':<15} | {'Unit':<20} | {'Regions'}")
        print("-" * 120)
        for sku in skus[:30]:
            reg_str = ", ".join(sku['regions']) if sku['regions'] else "global"
            print(f"{sku['description'][:63]:<65} | {sku['priceFormatted']:<15} | {sku['unit'][:18]:<20} | {reg_str}")
        if len(skus) > 30:
            print(f"\n... and {len(skus) - 30} more matching SKUs. Narrow search with a more specific --query filter.")
        print()


if __name__ == "__main__":
    main()
