"""
Cost calculation engine.
Loads parts list, matches to labor DB, fetches prices, calculates totals.
"""

import csv
import re
import logging
from pathlib import Path
from labor_matcher import LaborMatcher
from price_scraper import batch_scrape, scrape_vendor

logger = logging.getLogger(__name__)


def parse_quantity(qty_str: str) -> tuple:
    """
    Parse quantity string like '240 feet', '2500 feet', '40', '1'.
    Returns (numeric_value, unit_suffix).
    """
    qty_str = str(qty_str).strip()
    match = re.match(r'([\d,]+\.?\d*)\s*(feet|ft|foot|ea|each|lot|box)?', qty_str, re.I)
    if match:
        val = float(match.group(1).replace(',', ''))
        unit = (match.group(2) or '').lower()
        return val, unit
    # Try just a number
    try:
        return float(qty_str.replace(',', '')), ''
    except ValueError:
        return 0, ''


def calculate_labor_extension(qty: float, qty_unit: str, labor_value: float, labor_unit: str) -> float:
    """
    Calculate labor hours extension.
    Labor units: E=each, C=per hundred, M=per thousand
    """
    if labor_unit == 'E':
        return qty * labor_value
    elif labor_unit == 'C':
        return (qty / 100) * labor_value
    elif labor_unit == 'M':
        return (qty / 1000) * labor_value
    return qty * labor_value


def load_parts_list(csv_path: str) -> list:
    """Load the parts list CSV file."""
    parts = []
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle the specific column names from the user's CSV
            part = {}
            for key, val in row.items():
                if key is None:
                    continue
                key_clean = key.strip()
                if key_clean:
                    part[key_clean] = val.strip() if val else ''
            if part:
                parts.append(part)
    return parts


def run_estimation(parts_csv: str, labor_db: str = "data/labor_units_db.csv",
                   output_csv: str = "data/project_estimate.csv",
                   labor_rate: float = 85.0,
                   condition: str = "Average",
                   fetch_prices: bool = True) -> list:
    """
    Run the full estimation pipeline.

    Args:
        parts_csv: Path to parts list CSV
        labor_db: Path to labor units database CSV
        output_csv: Output path for estimate CSV
        labor_rate: Hourly labor rate in dollars
        condition: Working condition (Easy/Average/Difficult/Remodel/Old_Work)
        fetch_prices: Whether to fetch prices from vendors

    Returns:
        List of estimate row dicts
    """
    print(f"\nLoading parts from {parts_csv}...")
    parts = load_parts_list(parts_csv)
    print(f"  Found {len(parts)} parts")

    print(f"\nLoading labor database from {labor_db}...")
    matcher = LaborMatcher(labor_db)

    results = []

    print("\nMatching parts to labor units...")
    for part in parts:
        # Get part description - try various column names
        desc = (part.get('Part', '') or
                part.get('Part Description', '') or
                part.get('Description', '') or
                list(part.values())[0] if part else '')

        if not desc:
            continue

        # Get quantity
        qty_str = (part.get('Quantity', '') or
                   part.get('Qty', '') or '')
        qty, qty_unit = parse_quantity(qty_str)

        # Get Platt ID if available
        platt_id = (part.get('Exact Item Number Platt', '') or
                    part.get('Exact_Platt_ID', '') or
                    part.get('Platt_ID', '') or '')
        # Clean platt ID - remove "Platt#" prefix
        if platt_id:
            platt_id = re.sub(r'^Platt#', '', platt_id).strip()

        # Match to labor database
        labor_entry, confidence, match_reason = matcher.best_match(desc)

        row = {
            'Part': desc,
            'Quantity': qty,
            'Qty_Unit': qty_unit,
            'Platt_ID': platt_id,
        }

        if labor_entry and confidence > 30:
            labor_val = float(labor_entry.get(condition, labor_entry.get('Average', 0)))
            labor_unit = labor_entry['Unit']
            labor_ext = calculate_labor_extension(qty, qty_unit, labor_val, labor_unit)

            row.update({
                'Labor_Match': f"{labor_entry['Section']} > {labor_entry['Category']} > {labor_entry['Item']}",
                'Labor_Confidence': confidence,
                'Labor_Value': labor_val,
                'Labor_Unit': labor_unit,
                'Labor_Hours': round(labor_ext, 2),
                'Labor_Cost': round(labor_ext * labor_rate, 2),
            })
        else:
            row.update({
                'Labor_Match': 'NEEDS MANUAL LOOKUP',
                'Labor_Confidence': confidence,
                'Labor_Value': 0,
                'Labor_Unit': '',
                'Labor_Hours': 0,
                'Labor_Cost': 0,
            })

        # Price lookup
        if fetch_prices:
            price_result = scrape_vendor(desc, "platt", platt_id)
            row.update({
                'Platt_Price': price_result['price'],
                'Platt_Price_Str': price_result['price_str'],
                'Platt_Name': price_result['name'],
                'Platt_URL': price_result['url'],
                'Platt_Stock': price_result['stock'],
                'Price_Error': price_result['error'] or '',
            })
            # Calculate material extension
            if price_result['price'] > 0:
                row['Material_Cost'] = round(price_result['price'] * qty, 2)
            else:
                row['Material_Cost'] = 0
        else:
            row.update({
                'Platt_Price': 0,
                'Platt_Price_Str': 'SKIPPED',
                'Platt_Name': '',
                'Platt_URL': '',
                'Platt_Stock': '',
                'Price_Error': '',
                'Material_Cost': 0,
            })

        row['Total_Cost'] = round(row.get('Labor_Cost', 0) + row.get('Material_Cost', 0), 2)
        results.append(row)

        # Print progress
        status = "OK" if confidence > 50 else "LOW CONFIDENCE" if confidence > 30 else "NEEDS REVIEW"
        print(f"  [{status}] {desc[:40]:40s} -> Labor: {row['Labor_Hours']:>8.2f} hrs")

    # Write output CSV
    if results:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(results[0].keys())
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nEstimate written to {output_csv}")

    return results


if __name__ == '__main__':
    import sys
    parts_file = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Patrick\Downloads\testest - Sheet1.csv"
    run_estimation(parts_file, fetch_prices=False)
