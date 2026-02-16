# ABM Electrical Estimator

**Internal prototype tool for electrical project cost estimation.**

Combines a 4,396-entry labor units database (sourced from the 2025 Labor Units Manual) with optional Platt.com product lookups to generate detailed cost estimates for electrical work.

---

## Quick Start (Executable Version)

1. Unzip the folder
2. Double-click **`ABM Electrical Estimator.exe`**
3. The app opens automatically in your default browser at `http://localhost:5000`
4. Close the console window to stop the server

No installation required. Python and all dependencies are bundled into the executable.

---

## How It Works

The tool has three tabs:

### 1. Labor Database
Browse and search the full labor units database (4,396 entries across categories like conduit, wiring, boxes, breakers, etc.). Each entry includes labor hour values for five working conditions: Easy, Average, Difficult, Remodel, and Old Work.

- **Search** by keyword (e.g., "3/4 emt", "beam clamp", "#10 wire")
- **Filter** by section
- **Select** items with checkboxes, then add them to the Estimate Builder

### 2. Estimate Builder
Configure your estimate parameters and build your parts list:

- **Estimate Name** &mdash; label for history tracking (e.g., "Building A - 2nd Floor")
- **Labor Rate** &mdash; hourly rate in $/hr (default: $175)
- **Condition** &mdash; working condition affects labor hour multipliers
- **Fetch Platt Prices** &mdash; optionally look up product info from Platt.com
- **Parts List** &mdash; add parts manually, paste from a spreadsheet, or import from the database

### 3. Results & Reports
After running an estimate, view:

- **Summary stats** &mdash; total cost, labor hours, material cost, match quality
- **Line-item breakdown** &mdash; each part with labor match, confidence score, hours, and cost
- **Platt product links** &mdash; clickable links to matching products on Platt.com
- **Action items** &mdash; flagged parts that need manual review (low-confidence matches)
- **Export** &mdash; download as CSV or generate a text summary report
- **History** &mdash; all previous estimates are saved locally in your browser and can be recalled

---

## Architecture

### Overview

This is a self-contained, single-user web application. It runs a local Python web server (Flask) and serves a browser-based UI. All processing happens locally on the user's machine.

```
User's Browser  <-->  Local Flask Server (localhost:5000)  <-->  Labor DB (CSV file)
                                |
                                +--> Platt.com (optional, for product lookups)
```

### File Structure

| File | Purpose |
|---|---|
| `ABM Electrical Estimator.exe` | Application launcher (PyInstaller bundle) |
| `_internal/` | Bundled Python runtime and dependencies |
| `data/labor_units_db.csv` | Labor units database (4,396 entries, ~330 KB) |
| `static/index.html` | Complete UI &mdash; single-page application (HTML/CSS/JS) |

#### Source Files (for development only, not included in exe distribution)

| File | Purpose |
|---|---|
| `app.py` | Flask web server, API endpoints, static file serving |
| `labor_matcher.py` | Fuzzy matching engine &mdash; maps part descriptions to labor DB entries |
| `cost_calculator.py` | Quantity parsing, labor hour extension calculations |
| `price_scraper.py` | Platt.com product search with caching and rate limiting |
| `report_generator.py` | CSV and text report export |
| `pdf_extractor.py` | One-time PDF-to-CSV extraction (already run, not needed at runtime) |
| `launcher.py` | Entry point for the PyInstaller executable build |

---

## Security & Privacy Review

### Network Activity

| What | Where | Why | Risk |
|---|---|---|---|
| **Labor matching & cost calculation** | Local only | All computation runs on the user's machine | None |
| **Platt.com product lookup** | `www.platt.com` | Optional &mdash; searches for matching products when "Fetch Platt Prices" is checked | Low &mdash; standard HTTP GET requests, same as visiting the site in a browser |
| **Google Fonts** | `fonts.googleapis.com` | Loads the Titillium Web font for ABM brand consistency | None &mdash; standard CDN, no data sent |
| **ABM Logo** | `cdn.brandfetch.io` | Loads the ABM logo SVG &mdash; fails gracefully if unavailable | None &mdash; read-only CDN fetch |

### What Does NOT Happen

- **No data is sent to any external server** (except optional Platt.com product searches)
- **No user accounts or authentication** &mdash; the tool runs locally, no login required
- **No telemetry, analytics, or tracking** of any kind
- **No cookies or third-party scripts** beyond the Google Fonts stylesheet
- **No database server** &mdash; the labor database is a flat CSV file
- **No cloud storage** &mdash; estimate history is saved in the browser's localStorage
- **No file system writes** beyond `data/` directory (logs and exported reports)

### Server Binding

The application binds to `127.0.0.1` (localhost only). It is **not accessible** from other machines on the network. Only the user's own browser can connect.

### Dependencies

All dependencies are well-known, widely-used open-source Python libraries:

| Package | Version | Purpose | License |
|---|---|---|---|
| Flask | 3.x | Web server framework | BSD-3 |
| flask-cors | 6.x | Cross-origin resource sharing | MIT |
| pdfplumber | 0.11.x | PDF text extraction (build-time only) | MIT |
| rapidfuzz | 3.x | Fast fuzzy string matching | MIT |
| thefuzz | 0.22.x | Fuzzy matching wrapper | MIT |
| requests | 2.x | HTTP client (for Platt lookups) | Apache-2.0 |
| beautifulsoup4 | 4.x | HTML parsing (for Platt lookups) | MIT |
| Levenshtein | 0.25.x | String distance calculations | MIT |

### Data

The labor units database (`data/labor_units_db.csv`) contains only labor hour values extracted from the 2025 Labor Units Manual. It contains no proprietary pricing, employee data, customer data, or credentials of any kind.

---

## Offline Usage

The tool works fully offline for labor-based estimation. The only feature that requires internet is **Fetch Platt Prices** (which can be unchecked). If offline, the Google Font and ABM logo will not load, but the UI falls back to system fonts and hides the logo gracefully.

---

## Development Setup (for modifying the source)

```bash
# Install Python 3.10+
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

### Rebuilding the Executable

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --onedir --console \
    --name "ABM Electrical Estimator" \
    --add-data "static;static" \
    --add-data "data/labor_units_db.csv;data" \
    --hidden-import flask_cors \
    --hidden-import pdfplumber \
    --hidden-import rapidfuzz \
    --hidden-import Levenshtein \
    --hidden-import bs4 \
    launcher.py

# Copy data and static folders next to the exe:
cp -r static dist/"ABM Electrical Estimator"/
cp data/labor_units_db.csv dist/"ABM Electrical Estimator"/data/
```

---

## Limitations

- **Prototype / internal tool** &mdash; not hardened for public-facing deployment
- **Single user** &mdash; designed for one person running locally, not multi-user
- **Platt pricing** &mdash; Platt.com renders prices client-side after login; this tool retrieves product names and links but not live pricing
- **Fuzzy matching** &mdash; labor lookups use approximate string matching; low-confidence matches are flagged for manual review
- **Estimate history** &mdash; stored in browser localStorage, not backed up; clearing browser data will erase history
