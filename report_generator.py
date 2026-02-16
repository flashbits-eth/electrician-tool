"""
Generate summary reports and price comparison CSVs from estimation results.
"""

import csv
from datetime import datetime
from pathlib import Path


def generate_summary_report(results: list, output_path: str = "data/summary_report.txt",
                            labor_rate: float = 85.0):
    """Generate a text summary report."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    total_labor_hours = sum(r.get('Labor_Hours', 0) for r in results)
    total_labor_cost = sum(r.get('Labor_Cost', 0) for r in results)
    total_material = sum(r.get('Material_Cost', 0) for r in results)
    total_platt = sum(r.get('Platt_Price', 0) * r.get('Quantity', 0)
                      for r in results if r.get('Platt_Price', 0) > 0)

    needs_review = [r for r in results if r.get('Labor_Confidence', 0) <= 30]
    low_confidence = [r for r in results
                      if 30 < r.get('Labor_Confidence', 0) <= 50]
    price_missing = [r for r in results
                     if r.get('Platt_Price', 0) == 0 and r.get('Platt_Price_Str', '') != 'SKIPPED']
    good_matches = [r for r in results if r.get('Labor_Confidence', 0) > 50]

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("ELECTRICAL PROJECT COST ESTIMATE - SUMMARY REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")

        f.write("LABOR SUMMARY\n")
        f.write("-" * 40 + "\n")
        f.write(f"  Total Labor Hours:    {total_labor_hours:>10.2f} hrs\n")
        f.write(f"  Labor Rate:           ${labor_rate:>9.2f}/hr\n")
        f.write(f"  Total Labor Cost:     ${total_labor_cost:>9.2f}\n\n")

        f.write("MATERIAL SUMMARY\n")
        f.write("-" * 40 + "\n")
        f.write(f"  Platt Material Total: ${total_platt:>9.2f}\n")
        f.write(f"  Total Material Cost:  ${total_material:>9.2f}\n\n")

        f.write("PROJECT TOTAL\n")
        f.write("-" * 40 + "\n")
        total = total_labor_cost + total_material
        f.write(f"  Labor + Material:     ${total:>9.2f}\n\n")

        f.write("MATCH QUALITY\n")
        f.write("-" * 40 + "\n")
        f.write(f"  Good matches (>50%):  {len(good_matches):>4d} parts\n")
        f.write(f"  Low confidence:       {len(low_confidence):>4d} parts\n")
        f.write(f"  Needs manual review:  {len(needs_review):>4d} parts\n")
        f.write(f"  Missing prices:       {len(price_missing):>4d} parts\n\n")

        if needs_review:
            f.write("ACTION ITEMS - NEEDS MANUAL LABOR LOOKUP\n")
            f.write("-" * 40 + "\n")
            for r in needs_review:
                f.write(f"  - {r['Part']}\n")
            f.write("\n")

        if low_confidence:
            f.write("ACTION ITEMS - LOW CONFIDENCE MATCHES (VERIFY)\n")
            f.write("-" * 40 + "\n")
            for r in low_confidence:
                f.write(f"  - {r['Part']:40s}  -> {r.get('Labor_Match', 'N/A')}\n")
            f.write("\n")

        if price_missing:
            f.write("ACTION ITEMS - MISSING PRICES\n")
            f.write("-" * 40 + "\n")
            for r in price_missing:
                err = r.get('Price_Error', '')
                f.write(f"  - {r['Part']:40s}  Error: {err}\n")
            f.write("\n")

        f.write("DETAILED LINE ITEMS\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'Part':<35s} {'Qty':>6s} {'Hrs':>8s} {'L.Cost':>10s} {'M.Cost':>10s}\n")
        f.write("-" * 70 + "\n")
        for r in results:
            f.write(f"{r['Part'][:35]:<35s} "
                    f"{r.get('Quantity', 0):>6.0f} "
                    f"{r.get('Labor_Hours', 0):>8.2f} "
                    f"${r.get('Labor_Cost', 0):>9.2f} "
                    f"${r.get('Material_Cost', 0):>9.2f}\n")

        f.write("-" * 70 + "\n")
        f.write(f"{'TOTALS':<35s} "
                f"{'':>6s} "
                f"{total_labor_hours:>8.2f} "
                f"${total_labor_cost:>9.2f} "
                f"${total_material:>9.2f}\n")

    print(f"Summary report written to {output_path}")


def generate_price_comparison(results: list,
                              output_path: str = "data/price_comparison.csv"):
    """Generate a price comparison CSV."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        'Part', 'Quantity', 'Platt_Price', 'Platt_Total',
        'Platt_Stock', 'Platt_URL', 'Best_Price', 'Best_Vendor', 'Notes'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            qty = r.get('Quantity', 0)
            platt_price = r.get('Platt_Price', 0)

            # Determine best price (currently only Platt)
            prices = {'Platt': platt_price}
            valid_prices = {k: v for k, v in prices.items() if v > 0}

            if valid_prices:
                best_vendor = min(valid_prices, key=valid_prices.get)
                best_price = valid_prices[best_vendor]
            else:
                best_vendor = 'NEEDS MANUAL LOOKUP'
                best_price = 0

            notes = ''
            if r.get('Price_Error'):
                notes = r['Price_Error']
            elif platt_price == 0 and r.get('Platt_Price_Str', '') != 'SKIPPED':
                notes = 'NEEDS MANUAL LOOKUP'

            writer.writerow({
                'Part': r['Part'],
                'Quantity': qty,
                'Platt_Price': platt_price if platt_price > 0 else 'N/A',
                'Platt_Total': round(platt_price * qty, 2) if platt_price > 0 else 'N/A',
                'Platt_Stock': r.get('Platt_Stock', ''),
                'Platt_URL': r.get('Platt_URL', ''),
                'Best_Price': best_price if best_price > 0 else 'N/A',
                'Best_Vendor': best_vendor,
                'Notes': notes,
            })

    print(f"Price comparison written to {output_path}")
