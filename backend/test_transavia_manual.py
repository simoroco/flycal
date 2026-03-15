#!/usr/bin/env python3
"""Manually test Transavia search by inspecting the actual website flow"""
import re
import json
from curl_cffi import requests as cffi_requests

def find_search_mechanism():
    """Find how Transavia actually handles search requests"""
    session = cffi_requests.Session(impersonate="chrome")
    
    print("\n" + "="*70)
    print("STEP 1: Load homepage and extract search widget")
    print("="*70)
    
    r = session.get("https://www.transavia.com/accueil/fr-fr", timeout=15)
    html = r.text
    
    # Find the search form submission URL
    # The widget is a Next.js component, it might use JavaScript to redirect
    # Look for href patterns in the HTML
    
    search_patterns = [
        r'href="(/[^"]*(?:reserver|book|search|vols)[^"]*)"',
        r'window\.location.*?["\']([^"\']*(?:reserver|book)[^"\']*)',
    ]
    
    found_urls = set()
    for pattern in search_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        found_urls.update(matches)
    
    print(f"Found {len(found_urls)} potential search URLs:")
    for url in sorted(found_urls)[:15]:
        print(f"  {url}")
    
    # Try the most common booking URL pattern
    print("\n" + "="*70)
    print("STEP 2: Test booking URL with route parameters")
    print("="*70)
    
    # Based on airline patterns, try:
    # https://www.transavia.com/fr-FR/reserver-un-vol/vols/?origin=ORY&destination=FEZ&outbound=2026-03-05&inbound=2026-03-28
    
    test_urls = [
        "https://www.transavia.com/fr-FR/reserver-un-vol/vols/?origin=ORY&destination=FEZ&outbound=2026-03-05&inbound=2026-03-28&adults=1",
        "https://www.transavia.com/fr-FR/reserver-un-vol/vols/recherche/?origin=ORY&destination=FEZ&outbound=2026-03-05&inbound=2026-03-28&adults=1",
        "https://www.transavia.com/fr-FR/book-a-flight/flights/select/?origin=ORY&destination=FEZ&outbound=2026-03-05&inbound=2026-03-28&adults=1",
    ]
    
    for url in test_urls:
        try:
            print(f"\nTrying: {url}")
            r = session.get(url, timeout=12, allow_redirects=True)
            print(f"  Status: {r.status_code}")
            print(f"  Final URL: {r.url}")
            print(f"  Content-Length: {len(r.text)}")
            
            if r.status_code == 200 and len(r.text) > 50000:
                # Save it
                filename = f"/tmp/transavia_booking_{test_urls.index(url)}.html"
                with open(filename, "w") as f:
                    f.write(r.text)
                print(f"  ✓ Saved to {filename}")
                
                # Check for flight data
                if any(x in r.text.lower() for x in ['flight', 'vol', 'price', 'prix']):
                    print("  ✓ Contains flight-related content")
                
                # Look for __NEXT_DATA__ or API calls
                if "__NEXT_DATA__" in r.text:
                    print("  ✓ Has __NEXT_DATA__")
                    next_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
                    if next_match:
                        try:
                            data = json.loads(next_match.group(1))
                            data_file = f"/tmp/transavia_booking_{test_urls.index(url)}_data.json"
                            with open(data_file, "w") as f:
                                json.dump(data, f, indent=2)
                            print(f"  ✓ Saved Next.js data to {data_file}")
                        except:
                            pass
                break
        except Exception as e:
            print(f"  Error: {e}")
    
    session.close()
    
    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("1. Inspect the saved HTML/JSON files")
    print("2. Look for:")
    print("   - API endpoints in network requests")
    print("   - Flight data in __NEXT_DATA__")
    print("   - JavaScript that fetches availability")

if __name__ == "__main__":
    find_search_mechanism()
