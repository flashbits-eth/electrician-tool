"""
Extract labor units from Labor_Units_Manual_2025 PDF into a structured CSV.
Parses the consistent text format: SIZE values... PER_UNIT
"""

import pdfplumber
import csv
import re
import logging
from pathlib import Path

logging.basicConfig(
    filename='data/process.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_labor_units(pdf_path: str, output_path: str = "data/labor_units_db.csv"):
    """Extract all labor unit tables from the PDF."""
    pdf = pdfplumber.open(pdf_path)
    all_rows = []
    current_section = ""
    current_category = ""
    page_header_pattern = re.compile(
        r'^(.+?)\s+LABOR\s+UNITS\s*$', re.IGNORECASE
    )
    # Pattern for the column header line
    header_pattern = re.compile(
        r'SIZE\s+CONDITIONS\s+EASY\s+AVERAGE\s+DIFFICULT\s+REMODEL\s+OLD\s+WORK\s*PER',
        re.IGNORECASE
    )
    # Pattern for a data row: item/size followed by numeric values and unit letter
    # Handles rows like: 1/2" 3.50 4.00 4.50 5.00 5.50 C
    # And rows like: BOX MOUNTING BRACKETS 0.15 0.20 0.25 0.28 0.30 E
    data_pattern = re.compile(
        r'^(.+?)\s+'
        r'(\d+\.?\d*)\s+'
        r'(\d+\.?\d*)\s+'
        r'(\d+\.?\d*)\s+'
        r'(\d+\.?\d*)\s+'
        r'(\d+\.?\d*)\s+'
        r'([ECM])\s*$'
    )
    # Section markers from page footers like "1-1", "8-22", etc.
    section_footer = re.compile(r'^(\d+)-(\d+)\s*$')
    # Category headers - all caps lines that aren't data rows
    category_pattern = re.compile(r'^([A-Z][A-Z\s&\-\/\(\)]+(?:\*)?)\s*$')

    skipped_pages = 0
    total_pages = len(pdf.pages)

    for page_num in range(total_pages):
        page = pdf.pages[page_num]
        text = page.extract_text()
        if not text:
            skipped_pages += 1
            continue

        lines = text.split('\n')
        page_section = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for page header (section title)
            header_match = page_header_pattern.match(line)
            if header_match:
                page_section = header_match.group(1).strip()
                current_section = page_section
                continue

            # Skip column header lines
            if header_pattern.search(line):
                continue

            # Skip copyright lines
            if '1988' in line and 'Durand' in line:
                continue

            # Skip footer page numbers
            if section_footer.match(line):
                continue

            # Check for category subheader
            cat_match = category_pattern.match(line)
            if cat_match:
                potential_cat = cat_match.group(1).strip()
                # Make sure it's not a data row (shouldn't have numbers)
                if not re.search(r'\d', potential_cat) and len(potential_cat) > 2:
                    # Filter out noise
                    if potential_cat not in ('SIZE CONDITIONS EASY AVERAGE DIFFICULT REMODEL OLD WORK PER',
                                             'PER', 'SIZE', 'LABOR UNITS'):
                        current_category = potential_cat.rstrip('*').strip()
                        continue

            # Try to parse as data row
            data_match = data_pattern.match(line)
            if data_match:
                item = data_match.group(1).strip()
                easy = data_match.group(2)
                average = data_match.group(3)
                difficult = data_match.group(4)
                remodel = data_match.group(5)
                old_work = data_match.group(6)
                unit = data_match.group(7)

                all_rows.append({
                    'Section': current_section,
                    'Category': current_category,
                    'Item': item,
                    'Easy': float(easy),
                    'Average': float(average),
                    'Difficult': float(difficult),
                    'Remodel': float(remodel),
                    'Old_Work': float(old_work),
                    'Unit': unit
                })

    # Write to CSV
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['Section', 'Category', 'Item', 'Easy', 'Average', 'Difficult',
                  'Remodel', 'Old_Work', 'Unit']
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    logger.info(f"Extracted {len(all_rows)} labor unit entries from {total_pages} pages "
                f"({skipped_pages} skipped)")
    print(f"Extracted {len(all_rows)} labor unit entries to {output_path}")
    return all_rows


if __name__ == '__main__':
    extract_labor_units(r'Labor_Units_Manual_2025 (1).pdf')
