"""
Electrical Supply Cost Estimation System
Main CLI entry point.

Usage:
    python main.py                          # Run full pipeline with defaults
    python main.py --parts myparts.csv      # Specify parts list
    python main.py --no-scrape              # Skip price scraping
    python main.py --extract-pdf            # Re-extract labor DB from PDF
    python main.py --labor-rate 95          # Set hourly labor rate
    python main.py --condition Difficult    # Set working condition
    python main.py --search "3/4 emt"       # Search labor DB interactively
"""

import argparse
import logging
import sys
from pathlib import Path

# Setup logging
Path("data").mkdir(exist_ok=True)
logging.basicConfig(
    filename='data/process.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Also log to console
console = logging.StreamHandler()
console.setLevel(logging.WARNING)
logging.getLogger('').addHandler(console)


def main():
    parser = argparse.ArgumentParser(
        description="Electrical Supply Cost Estimation System"
    )
    parser.add_argument('--parts', default=r"C:\Users\Patrick\Downloads\testest - Sheet1.csv",
                        help="Path to parts list CSV")
    parser.add_argument('--pdf', default=r"Labor_Units_Manual_2025 (1).pdf",
                        help="Path to Labor Units Manual PDF")
    parser.add_argument('--labor-db', default="data/labor_units_db.csv",
                        help="Path to labor units database CSV")
    parser.add_argument('--output', default="data/project_estimate.csv",
                        help="Output estimate CSV path")
    parser.add_argument('--labor-rate', type=float, default=85.0,
                        help="Hourly labor rate in dollars (default: 85)")
    parser.add_argument('--condition', default="Average",
                        choices=['Easy', 'Average', 'Difficult', 'Remodel', 'Old_Work'],
                        help="Working condition for labor units (default: Average)")
    parser.add_argument('--no-scrape', action='store_true',
                        help="Skip price scraping")
    parser.add_argument('--extract-pdf', action='store_true',
                        help="Force re-extraction of PDF labor units")
    parser.add_argument('--search', type=str,
                        help="Search labor DB for a part (interactive mode)")
    args = parser.parse_args()

    print("=" * 60)
    print("  ELECTRICAL SUPPLY COST ESTIMATION SYSTEM")
    print("=" * 60)

    # Step 1: Ensure labor DB exists
    labor_db_path = Path(args.labor_db)
    if args.extract_pdf or not labor_db_path.exists():
        print("\n[Phase 1] Extracting labor units from PDF...")
        from pdf_extractor import extract_labor_units
        extract_labor_units(args.pdf, args.labor_db)
    else:
        import csv
        with open(args.labor_db, encoding='utf-8') as f:
            count = sum(1 for _ in csv.reader(f)) - 1
        print(f"\n[Phase 1] Labor DB exists: {count} entries in {args.labor_db}")

    # Interactive search mode
    if args.search:
        from labor_matcher import LaborMatcher
        matcher = LaborMatcher(args.labor_db)
        results = matcher.search(args.search, top_n=10)
        print(f"\nSearch results for: '{args.search}'")
        print("-" * 80)
        for entry, score, reason in results:
            print(f"  Score: {score:>6.1f}  "
                  f"{entry['Section']} > {entry['Category']} > {entry['Item']}  "
                  f"Avg: {entry['Average']} per {entry['Unit']}")
        return

    # Step 2: Run estimation
    print(f"\n[Phase 2] Running cost estimation...")
    print(f"  Parts list:  {args.parts}")
    print(f"  Labor rate:  ${args.labor_rate}/hr")
    print(f"  Condition:   {args.condition}")
    print(f"  Scraping:    {'ON' if not args.no_scrape else 'OFF'}")

    from cost_calculator import run_estimation
    results = run_estimation(
        parts_csv=args.parts,
        labor_db=args.labor_db,
        output_csv=args.output,
        labor_rate=args.labor_rate,
        condition=args.condition,
        fetch_prices=not args.no_scrape,
    )

    # Step 3: Generate reports
    print(f"\n[Phase 3] Generating reports...")
    from report_generator import generate_summary_report, generate_price_comparison
    generate_summary_report(results, "data/summary_report.txt", args.labor_rate)
    generate_price_comparison(results, "data/price_comparison.csv")

    print(f"\n{'=' * 60}")
    print("  ESTIMATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Estimate:         {args.output}")
    print(f"  Summary report:   data/summary_report.txt")
    print(f"  Price comparison: data/price_comparison.csv")
    print(f"  Process log:      data/process.log")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
