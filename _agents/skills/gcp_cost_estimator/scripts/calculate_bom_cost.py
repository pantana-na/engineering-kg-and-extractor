#!/usr/bin/env python3
"""
GCP Bill of Materials (BoM) Cost Calculator.

Calculates itemized monthly and annual running costs from a structured
BoM JSON file, computing sub-totals, category breakdowns, CUD discounts,
and generating formatted markdown summary tables.
"""

import argparse
import json
import sys
from typing import Any, Dict, List


def calculate_bom(bom_data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate all items in the BoM dictionary."""
    items = bom_data.get("items") or bom_data.get("line_items", [])
    project_name = bom_data.get("project_name", "GCP Workload")
    currency = bom_data.get("currency", "USD")
    assumptions = bom_data.get("assumptions", [])

    total_monthly_ondemand = 0.0
    categories = {}

    processed_items = []

    for item in items:
        name = item.get("name") or item.get("component", "Unnamed Resource")
        category = item.get("category", "General")
        service = item.get("service", "GCP")
        sku = item.get("sku") or item.get("sku_id", "")
        quantity = float(item.get("quantity", 1.0))
        unit = item.get("unit", "units")
        unit_price = float(item.get("unit_price", 0.0))
        usage_per_month = float(item.get("usage_per_month", quantity))
        free_tier_allowance = float(item.get("free_tier_allowance", 0.0))
        rate_source = item.get("rate_source", "Live Billing API / Web")
        notes = item.get("notes") or item.get("description", "")

        billable_usage = max(0.0, usage_per_month - free_tier_allowance)
        monthly_cost = billable_usage * unit_price

        total_monthly_ondemand += monthly_cost
        categories[category] = categories.get(category, 0.0) + monthly_cost

        processed_items.append({
            "name": name,
            "category": category,
            "service": service,
            "sku": sku,
            "unit": unit,
            "unit_price": unit_price,
            "rate_source": rate_source,
            "usage_per_month": usage_per_month,
            "free_tier_allowance": free_tier_allowance,
            "billable_usage": billable_usage,
            "monthly_cost": monthly_cost,
            "annual_cost": monthly_cost * 12.0,
            "notes": notes
        })

    # CUD estimates (applied primarily to Compute / Cloud SQL / GKE baseline)
    compute_db_base = categories.get("Compute", 0.0) + categories.get("Database", 0.0)
    cud_1yr_savings = compute_db_base * 0.28
    cud_3yr_savings = compute_db_base * 0.52

    monthly_1yr_cud = total_monthly_ondemand - cud_1yr_savings
    monthly_3yr_cud = total_monthly_ondemand - cud_3yr_savings

    return {
        "project_name": project_name,
        "currency": currency,
        "total_monthly_ondemand": total_monthly_ondemand,
        "total_annual_ondemand": total_monthly_ondemand * 12.0,
        "monthly_1yr_cud": monthly_1yr_cud,
        "annual_1yr_cud": monthly_1yr_cud * 12.0,
        "monthly_3yr_cud": monthly_3yr_cud,
        "annual_3yr_cud": monthly_3yr_cud * 12.0,
        "category_breakdown": categories,
        "items": processed_items,
        "assumptions": assumptions
    }


def generate_markdown_report(result: Dict[str, Any]) -> str:
    """Generate a clean markdown report from calculation results."""
    md = []
    pname = result.get("project_name", "GCP Architecture")
    curr = result.get("currency", "USD")
    total_mo = result.get("total_monthly_ondemand", 0.0)
    total_yr = result.get("total_annual_ondemand", 0.0)
    mo_1yr = result.get("monthly_1yr_cud", 0.0)
    mo_3yr = result.get("monthly_3yr_cud", 0.0)

    md.append(f"# GCP Cloud Cost Estimate: {pname}\n")
    md.append("## 📊 Executive Summary\n")
    md.append(f"| Pricing Tier | Estimated Monthly Cost | Estimated Annual Cost | Estimated Savings |")
    md.append(f"| :--- | :--- | :--- | :--- |")
    md.append(f"| **On-Demand / Pay-as-you-go** | **${total_mo:,.2f} {curr}** | **${total_yr:,.2f} {curr}** | Baseline |")
    md.append(f"| **1-Year Committed Use (CUD)** | ${mo_1yr:,.2f} {curr} | ${mo_1yr*12:,.2f} {curr} | ~28% on eligible compute/DB |")
    md.append(f"| **3-Year Committed Use (CUD)** | ${mo_3yr:,.2f} {curr} | ${mo_3yr*12:,.2f} {curr} | ~52% on eligible compute/DB |\n")

    md.append("## 🧩 Cost Distribution by Category\n")
    categories = result.get("category_breakdown", {})
    md.append("| Category | Monthly Cost | % of Total |")
    md.append("| :--- | :--- | :--- |")
    for cat, cost in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        pct = (cost / total_mo * 100.0) if total_mo > 0 else 0.0
        md.append(f"| **{cat}** | ${cost:,.2f} | {pct:,.1f}% |")
    md.append("\n")

    md.append("## 📋 Itemized Bill of Materials (BoM)\n")
    md.append("| Component / Service | SKU / Configuration | Monthly Usage | Unit Price | Rate Source | Monthly Cost | Notes / Specifications |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for it in result.get("items", []):
        name = it["name"]
        sku = it["sku"]
        usage = f"{it['usage_per_month']:,.2f}".rstrip("0").rstrip(".") + f" {it['unit']}"
        unit_p = f"${it['unit_price']:,.6f}".rstrip("0").rstrip(".")
        rate_src = it.get("rate_source", "Live API / Web")
        mo_c = f"${it['monthly_cost']:,.2f}"
        notes = it["notes"]
        md.append(f"| **{name}** ({it['service']}) | {sku} | {usage} | {unit_p} | {rate_src} | **{mo_c}** | {notes} |")
    md.append("\n")

    assumptions = result.get("assumptions", [])
    if assumptions:
        md.append("## 📝 Confirmed Workload Parameters & Specifications\n")
        for idx, a in enumerate(assumptions, 1):
            md.append(f"{idx}. {a}")
        md.append("\n")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Calculate GCP BoM Costs from JSON")
    parser.add_argument("bom_file", help="Path to Bill of Materials JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    parser.add_argument("--markdown", action="store_true", help="Output Markdown report")

    args = parser.parse_args()

    try:
        with open(args.bom_file, "r") as f:
            bom_data = json.load(f)
    except Exception as e:
        print(f"Error reading BoM file: {e}", file=sys.stderr)
        sys.exit(1)

    result = calculate_bom(bom_data)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(generate_markdown_report(result))


if __name__ == "__main__":
    main()
