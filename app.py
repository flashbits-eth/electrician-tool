"""
Flask API server for the Electrical Supply Cost Estimation System.
Serves the HTML frontend and provides API endpoints.
"""

import csv
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Setup paths — when running as a PyInstaller exe, use the exe's directory
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Setup logging
logging.basicConfig(
    filename=str(DATA_DIR / 'process.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=str(BASE_DIR / 'static'))
CORS(app)

# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------
_labor_matcher = None
LABOR_DB_PATH = str(DATA_DIR / "labor_units_db.csv")


def get_matcher():
    global _labor_matcher
    if _labor_matcher is None:
        from labor_matcher import LaborMatcher
        _labor_matcher = LaborMatcher(LABOR_DB_PATH)
    return _labor_matcher


def load_labor_db():
    """Load entire labor DB as list of dicts."""
    with open(LABOR_DB_PATH, encoding='utf-8') as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return send_from_directory(str(BASE_DIR / 'static'), 'index.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


# ---------------------------------------------------------------------------
# API: Labor Database
# ---------------------------------------------------------------------------
@app.route('/api/labor/sections', methods=['GET'])
def labor_sections():
    """Return list of unique sections from labor DB."""
    rows = load_labor_db()
    sections = sorted(set(r['Section'] for r in rows))
    return jsonify(sections)


@app.route('/api/labor/categories', methods=['GET'])
def labor_categories():
    """Return categories for a given section."""
    section = request.args.get('section', '')
    rows = load_labor_db()
    cats = sorted(set(r['Category'] for r in rows if r['Section'] == section))
    return jsonify(cats)


@app.route('/api/labor/items', methods=['GET'])
def labor_items():
    """Return items for a given section+category."""
    section = request.args.get('section', '')
    category = request.args.get('category', '')
    rows = load_labor_db()
    items = [r for r in rows
             if r['Section'] == section and r['Category'] == category]
    return jsonify(items)


@app.route('/api/labor/search', methods=['GET'])
def labor_search():
    """Fuzzy search the labor DB."""
    query = request.args.get('q', '')
    top_n = int(request.args.get('n', 10))
    if not query:
        return jsonify([])
    matcher = get_matcher()
    results = matcher.search(query, top_n=top_n)
    out = []
    for entry, score, reason in results:
        out.append({
            **entry,
            'score': score,
            'reason': reason,
            'display': f"{entry['Section']} > {entry['Category']} > {entry['Item']}"
        })
    return jsonify(out)


@app.route('/api/labor/browse', methods=['GET'])
def labor_browse():
    """Browse labor DB with optional filters, for the data table."""
    section = request.args.get('section', '')
    category = request.args.get('category', '')
    search = request.args.get('search', '').lower()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    rows = load_labor_db()

    if section:
        rows = [r for r in rows if r['Section'] == section]
    if category:
        rows = [r for r in rows if r['Category'] == category]
    if search:
        rows = [r for r in rows if search in
                f"{r['Section']} {r['Category']} {r['Item']}".lower()]

    total = len(rows)
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'data': page_rows
    })


# ---------------------------------------------------------------------------
# API: Estimation
# ---------------------------------------------------------------------------
@app.route('/api/estimate', methods=['POST'])
def run_estimate():
    """
    Run estimation on a parts list.
    Expects JSON body: {
        parts: [{description, quantity, platt_id}, ...],
        labor_rate: 85.0,
        condition: "Average",
        fetch_prices: false
    }
    """
    body = request.get_json()
    parts = body.get('parts', [])
    labor_rate = float(body.get('labor_rate', 175.0))
    condition = body.get('condition', 'Average')
    fetch_prices = body.get('fetch_prices', False)

    if not parts:
        return jsonify({'error': 'No parts provided'}), 400

    matcher = get_matcher()
    from cost_calculator import parse_quantity, calculate_labor_extension
    from price_scraper import scrape_vendor

    results = []
    for part in parts:
        desc = part.get('description', '').strip()
        if not desc:
            continue

        qty_raw = str(part.get('quantity', '0'))
        qty, qty_unit = parse_quantity(qty_raw)
        platt_id = re.sub(r'^Platt#', '', str(part.get('platt_id', ''))).strip()

        # Labor match
        labor_entry, confidence, match_reason = matcher.best_match(desc)

        row = {
            'part': desc,
            'quantity': qty,
            'qty_unit': qty_unit,
            'platt_id': platt_id,
        }

        if labor_entry and confidence > 30:
            labor_val = float(labor_entry.get(condition, labor_entry.get('Average', 0)))
            labor_unit = labor_entry['Unit']
            labor_ext = calculate_labor_extension(qty, qty_unit, labor_val, labor_unit)
            row.update({
                'labor_match': f"{labor_entry['Section']} > {labor_entry['Category']} > {labor_entry['Item']}",
                'labor_section': labor_entry['Section'],
                'labor_category': labor_entry['Category'],
                'labor_item': labor_entry['Item'],
                'labor_confidence': confidence,
                'labor_value': labor_val,
                'labor_unit': labor_unit,
                'labor_hours': round(labor_ext, 2),
                'labor_cost': round(labor_ext * labor_rate, 2),
            })
        else:
            row.update({
                'labor_match': 'NEEDS MANUAL LOOKUP',
                'labor_confidence': confidence,
                'labor_value': 0,
                'labor_unit': '',
                'labor_hours': 0,
                'labor_cost': 0,
            })

        # Price
        if fetch_prices and desc:
            price_result = scrape_vendor(desc, "platt", platt_id)
            row.update({
                'platt_price': price_result['price'],
                'platt_price_str': price_result['price_str'],
                'platt_name': price_result['name'],
                'platt_url': price_result['url'],
                'platt_stock': price_result['stock'],
                'price_error': price_result['error'] or '',
                'material_cost': round(price_result['price'] * qty, 2) if price_result['price'] > 0 else 0,
            })
        else:
            row.update({
                'platt_price': 0,
                'platt_price_str': '',
                'platt_name': '',
                'platt_url': '',
                'platt_stock': '',
                'price_error': '',
                'material_cost': 0,
            })

        row['total_cost'] = round(row.get('labor_cost', 0) + row.get('material_cost', 0), 2)
        results.append(row)

    # Compute totals
    totals = {
        'total_labor_hours': round(sum(r.get('labor_hours', 0) for r in results), 2),
        'total_labor_cost': round(sum(r.get('labor_cost', 0) for r in results), 2),
        'total_material_cost': round(sum(r.get('material_cost', 0) for r in results), 2),
        'total_cost': round(sum(r.get('total_cost', 0) for r in results), 2),
        'good_matches': sum(1 for r in results if r.get('labor_confidence', 0) > 50),
        'low_confidence': sum(1 for r in results if 30 < r.get('labor_confidence', 0) <= 50),
        'needs_review': sum(1 for r in results if r.get('labor_confidence', 0) <= 30),
        'part_count': len(results),
    }

    return jsonify({'results': results, 'totals': totals})


@app.route('/api/estimate/export', methods=['POST'])
def export_estimate():
    """Export estimation results to CSV files and return download paths."""
    body = request.get_json()
    results = body.get('results', [])
    totals = body.get('totals', {})
    labor_rate = float(body.get('labor_rate', 175.0))

    if not results:
        return jsonify({'error': 'No results to export'}), 400

    # Write project_estimate.csv
    est_path = str(DATA_DIR / 'project_estimate.csv')
    fieldnames = list(results[0].keys())
    with open(est_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Write summary_report.txt
    report_path = str(DATA_DIR / 'summary_report.txt')
    from report_generator import generate_summary_report
    # Convert keys to match what report_generator expects
    mapped = []
    for r in results:
        mapped.append({
            'Part': r.get('part', ''),
            'Quantity': r.get('quantity', 0),
            'Labor_Hours': r.get('labor_hours', 0),
            'Labor_Cost': r.get('labor_cost', 0),
            'Material_Cost': r.get('material_cost', 0),
            'Labor_Confidence': r.get('labor_confidence', 0),
            'Labor_Match': r.get('labor_match', ''),
            'Platt_Price': r.get('platt_price', 0),
            'Platt_Price_Str': r.get('platt_price_str', ''),
            'Price_Error': r.get('price_error', ''),
            'Platt_Stock': r.get('platt_stock', ''),
            'Platt_URL': r.get('platt_url', ''),
        })
    generate_summary_report(mapped, report_path, labor_rate)

    return jsonify({
        'estimate_csv': est_path,
        'summary_report': report_path,
        'message': 'Files exported successfully'
    })


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    # Ensure labor DB exists
    if not Path(LABOR_DB_PATH).exists():
        print("Labor DB not found. Run 'python pdf_extractor.py' first.")
        sys.exit(1)

    print("Starting Electrical Estimator Web UI...")
    print("Open http://localhost:5000 in your browser")
    app.run(host='127.0.0.1', port=5000, debug=True)
