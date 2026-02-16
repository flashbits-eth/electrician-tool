"""Test Platt scraping with correct URL and HTML parsing."""
import requests
import re
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
}

def test_search(query):
    print(f"\n{'='*60}")
    print(f"Searching Platt for: '{query}'")
    url = f"https://www.platt.com/s/search?q={requests.utils.quote(query)}"
    r = requests.get(url, headers=headers, timeout=15)
    print(f"  Status: {r.status_code}, Length: {len(r.text)}")

    soup = BeautifulSoup(r.text, 'html.parser')

    # Find product links - pattern /p/{id}/...
    product_links = soup.find_all('a', href=re.compile(r'^/p/\d+'))
    print(f"  Found {len(product_links)} product links")

    seen_urls = set()
    products = []
    for link in product_links:
        href = link.get('href', '')
        if href in seen_urls:
            continue
        seen_urls.add(href)

        # Extract item number from URL: /p/0065970/...
        id_match = re.search(r'/p/(\d+)/', href)
        item_id = id_match.group(1) if id_match else ''

        # Get product name from h2 inside the link
        h2 = link.find('h2')
        name = h2.get_text(strip=True) if h2 else ''

        if not name:
            continue

        # Walk up to find the product card container with price/stock
        parent = link
        price = 0
        price_unit = ''
        stock = ''
        for _ in range(12):
            parent = parent.parent
            if parent is None:
                break
            text = parent.get_text(' ', strip=True)
            price_match = re.search(r'\$\s*([\d,]+\.?\d*)\s*(FT|EA|C|M)', text)
            if price_match:
                price = float(price_match.group(1).replace(',', ''))
                price_unit = price_match.group(2)
                stock_match = re.search(r'([\d,]+)\s+in\s+stock', text)
                if stock_match:
                    stock = stock_match.group(1)
                break

        products.append({
            'item_id': item_id,
            'name': name,
            'price': price,
            'price_unit': price_unit,
            'stock': stock,
            'url': f"https://www.platt.com{href}",
        })

    for i, p in enumerate(products[:5]):
        print(f"\n  Product {i+1}:")
        print(f"    Name:  {p['name']}")
        print(f"    ID:    {p['item_id']}")
        print(f"    Price: ${p['price']:.2f} / {p['price_unit']}")
        print(f"    Stock: {p['stock']}")
        print(f"    URL:   {p['url']}")

    return products


if __name__ == '__main__':
    test_search("3/4 emt")
    test_search("beam clamp")
    test_search("0013209")  # Direct item number
    test_search("#10 thhn wire")
