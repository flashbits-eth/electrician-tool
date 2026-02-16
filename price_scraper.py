"""
Price scraper for electrical supply vendors.
Supports Platt.com with caching and rate limiting.

Platt.com is a Nuxt.js SPA that loads prices via client-side GraphQL.
Product names, IDs, and URLs are available in server-rendered HTML.
Prices require a logged-in session (GraphQL with session customerId),
so they are marked for manual lookup unless a browser-based approach is used.
"""

import requests
from bs4 import BeautifulSoup
import csv
import json
import time
import re
import logging
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "price_cache.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# Rate limiting
MIN_REQUEST_INTERVAL = 2.0  # seconds between requests
_last_request_time = 0


def _rate_limit():
    """Enforce minimum delay between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)


def _cache_key(vendor: str, query: str) -> str:
    return f"{vendor}::{query.lower().strip()}"


def scrape_platt(query: str, platt_id: str = "") -> dict:
    """
    Search Platt.com for a part by ID or description.
    Returns dict with: name, price, unit, stock, url, vendor

    NOTE: Platt renders prices client-side via GraphQL.
    This scraper retrieves product name, item ID, and URL from
    the server-rendered HTML. Prices show as "Login for pricing"
    unless fetched via browser automation.
    """
    cache = _load_cache()

    # Use platt_id if available, otherwise search by description
    search_term = platt_id if platt_id else query
    key = _cache_key("platt", search_term)

    if key in cache:
        logger.info(f"Cache hit for Platt: {search_term}")
        return cache[key]

    result = {
        'vendor': 'Platt',
        'name': '',
        'price': 0.0,
        'price_str': 'Login for pricing',
        'unit': '',
        'stock': 'Unknown',
        'url': '',
        'query': query,
        'platt_item_id': platt_id,
        'error': None,
    }

    try:
        _rate_limit()

        # Platt uses /s/search?q= for their search endpoint
        search_query = platt_id if platt_id else query
        search_url = f"https://www.platt.com/s/search?q={quote_plus(search_query)}"
        result['url'] = search_url

        response = requests.get(search_url, headers=HEADERS, timeout=15, allow_redirects=True)

        if response.status_code == 403:
            result['error'] = 'Access denied (403) - may need manual lookup'
            logger.warning(f"Platt 403 for: {search_term}")
        elif response.status_code == 200:
            _parse_platt_search(response.text, result, response.url, platt_id)
        else:
            result['error'] = f'HTTP {response.status_code}'
            logger.warning(f"Platt HTTP {response.status_code} for: {search_term}")

    except requests.RequestException as e:
        result['error'] = str(e)
        logger.error(f"Platt request error for {search_term}: {e}")

    cache[key] = result
    _save_cache(cache)
    return result


def _parse_platt_search(html: str, result: dict, final_url: str, platt_id: str = ""):
    """
    Parse Platt search results page.
    Product cards are rendered server-side as <a href="/p/{item_id}/...">
    with <h2> containing the product name.
    Prices are loaded client-side via GraphQL and won't be in the HTML.
    """
    result['url'] = final_url
    soup = BeautifulSoup(html, 'html.parser')

    # Find all product links: /p/{item_id}/slug/upc/cat
    product_links = soup.find_all('a', href=re.compile(r'^/p/\d+'))
    seen_urls = set()
    products = []

    for link in product_links:
        href = link.get('href', '')
        if href in seen_urls:
            continue
        seen_urls.add(href)

        # Extract item ID from URL
        id_match = re.search(r'/p/(\d+)/', href)
        item_id = id_match.group(1) if id_match else ''

        # Get product name from <h2> inside the link
        h2 = link.find('h2')
        name = h2.get_text(strip=True) if h2 else ''
        if not name:
            continue

        products.append({
            'item_id': item_id,
            'name': name,
            'url': f"https://www.platt.com{href}",
        })

    if not products:
        result['error'] = 'No products found - try different search terms'
        return

    # If we have a specific platt_id, find that exact product
    if platt_id:
        for p in products:
            if p['item_id'] == platt_id:
                result['name'] = p['name']
                result['url'] = p['url']
                result['platt_item_id'] = p['item_id']
                break
        else:
            # Platt ID not found in results, use first result
            result['name'] = products[0]['name']
            result['url'] = products[0]['url']
            result['platt_item_id'] = products[0]['item_id']
    else:
        # Use first result (most relevant)
        result['name'] = products[0]['name']
        result['url'] = products[0]['url']
        result['platt_item_id'] = products[0]['item_id']

    # Also look for item details in the HTML
    # Item #, CAT #, UPC are in text nodes near the product link
    text = html
    item_idx = text.find(f"/p/{result['platt_item_id']}/")
    if item_idx > 0:
        context = text[item_idx:item_idx + 2000]
        # Try to find "Item #: NNNNNNN"
        item_match = re.search(r'Item\s*#:\s*(\d+)', context)
        if item_match:
            result['platt_item_id'] = item_match.group(1)
        # Try to find CAT #
        cat_match = re.search(r'CAT\s*#:\s*([\w\-]+)', context)
        if cat_match:
            result['cat_number'] = cat_match.group(1)

    # Price note - Platt renders prices via client-side JS/GraphQL
    result['price_str'] = 'Login for pricing'
    result['error'] = None  # No error - product was found successfully

    logger.info(f"Platt found: {result['name']} (Item# {result.get('platt_item_id', 'N/A')})")


def scrape_vendor(query: str, vendor: str = "platt", platt_id: str = "") -> dict:
    """Generic vendor scrape dispatcher."""
    if vendor.lower() == "platt":
        return scrape_platt(query, platt_id)
    else:
        return {
            'vendor': vendor,
            'name': '',
            'price': 0.0,
            'price_str': 'NEEDS MANUAL LOOKUP',
            'unit': '',
            'stock': 'Unknown',
            'url': '',
            'query': query,
            'error': f'Vendor {vendor} not yet implemented',
        }


def batch_scrape(parts: list, vendor: str = "platt") -> list:
    """
    Scrape prices for a list of parts.
    Each part should be a dict with 'description' and optionally 'platt_id'.
    """
    from tqdm import tqdm
    results = []
    for part in tqdm(parts, desc=f"Fetching {vendor} prices"):
        desc = part.get('description', part.get('Part', ''))
        platt_id = part.get('platt_id', part.get('Exact Item Number Platt', ''))
        # Clean up platt_id
        if platt_id:
            platt_id = re.sub(r'[^0-9]', '', str(platt_id))
        result = scrape_vendor(desc, vendor, platt_id)
        result['original_description'] = desc
        results.append(result)
    return results


if __name__ == '__main__':
    # Test with a known Platt ID
    print("Testing Platt scraper with item ID...")
    r = scrape_platt("beam clamp", platt_id="0013209")
    print(f"  Name:    {r['name']}")
    print(f"  Item#:   {r.get('platt_item_id', '')}")
    print(f"  Price:   {r['price_str']}")
    print(f"  URL:     {r['url']}")
    print(f"  Error:   {r['error']}")

    print("\nTesting search by description...")
    r = scrape_platt("3/4 emt conduit")
    print(f"  Name:    {r['name']}")
    print(f"  Item#:   {r.get('platt_item_id', '')}")
    print(f"  Price:   {r['price_str']}")
    print(f"  URL:     {r['url']}")
    print(f"  Error:   {r['error']}")

    print("\nTesting wire search...")
    r = scrape_platt("#10 thhn wire")
    print(f"  Name:    {r['name']}")
    print(f"  Item#:   {r.get('platt_item_id', '')}")
    print(f"  URL:     {r['url']}")
    print(f"  Error:   {r['error']}")
