#!/usr/bin/env python3
"""Analyze real Transavia search flow - how does the website actually work?"""
import json
import re
from curl_cffi import requests as cffi_requests

def analyze_homepage():
    """Analyze the homepage to find the search mechanism"""
    session = cffi_requests.Session(impersonate="chrome")
    
    print("\n" + "="*70)
    print("ANALYZING TRANSAVIA HOMEPAGE")
    print("="*70)
    
    r = session.get("https://www.transavia.com/accueil/fr-fr", timeout=15)
    print(f"Status: {r.status_code}")
    
    # Save full HTML
    with open("/tmp/transavia_home.html", "w") as f:
        f.write(r.text)
    print(f"✓ Saved {len(r.text)} chars to /tmp/transavia_home.html")
    
    # Extract Next.js data
    next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
    if next_data_match:
        try:
            data = json.loads(next_data_match.group(1))
            with open("/tmp/transavia_next_data.json", "w") as f:
                json.dump(data, f, indent=2)
            print("✓ Extracted __NEXT_DATA__ to /tmp/transavia_next_data.json")
            
            # Look for API endpoints in the data
            data_str = json.dumps(data)
            api_matches = re.findall(r'https?://[^"]+api[^"]+', data_str)
            if api_matches:
                print(f"\n✓ Found {len(api_matches)} API URLs in Next.js data:")
                for url in set(api_matches[:10]):
                    print(f"  - {url}")
        except Exception as e:
            print(f"Error parsing __NEXT_DATA__: {e}")
    
    # Look for flight search widget/component
    print("\n" + "="*70)
    print("SEARCHING FOR FLIGHT WIDGET")
    print("="*70)
    
    # Common patterns
    patterns = {
        "Flight search form": r'<form[^>]*flight[^>]*>',
        "Search button": r'<button[^>]*search[^>]*>.*?</button>',
        "Origin/destination inputs": r'<input[^>]*(?:origin|departure|from)[^>]*>',
        "Date picker": r'<input[^>]*(?:date|calendar)[^>]*>',
        "Booking widget": r'data-widget[^>]*booking',
    }
    
    for name, pattern in patterns.items():
        matches = re.findall(pattern, r.text, re.IGNORECASE | re.DOTALL)
        if matches:
            print(f"\n✓ Found {name}: {len(matches)} matches")
            if len(matches) <= 3:
                for m in matches[:3]:
                    snippet = m[:150].replace('\n', ' ')
                    print(f"  {snippet}...")
    
    # Look for Next.js page data URLs
    print("\n" + "="*70)
    print("LOOKING FOR NEXT.JS DATA URLS")
    print("="*70)
    
    # Extract buildId from __NEXT_DATA__
    if next_data_match:
        try:
            data = json.loads(next_data_match.group(1))
            build_id = data.get('buildId', 'unknown')
            print(f"Build ID: {build_id}")
            
            # Try to fetch page data
            page_data_url = f"https://www.transavia.com/_next/data/{build_id}/accueil/fr-fr.json"
            print(f"\nTrying: {page_data_url}")
            r2 = session.get(page_data_url, timeout=10)
            print(f"Status: {r2.status_code}")
            
            if r2.status_code == 200:
                try:
                    page_data = r2.json()
                    with open("/tmp/transavia_page_data.json", "w") as f:
                        json.dump(page_data, f, indent=2)
                    print("✓ Saved page data to /tmp/transavia_page_data.json")
                except:
                    pass
        except:
            pass
    
    # Look for embedded booking/search endpoints
    print("\n" + "="*70)
    print("SEARCHING FOR BOOKING ENDPOINTS IN HTML")
    print("="*70)
    
    # Common endpoint patterns
    endpoint_patterns = [
        r'https://www\.transavia\.com/[^"]*book[^"]*',
        r'https://www\.transavia\.com/[^"]*flight[^"]*',
        r'https://www\.transavia\.com/[^"]*search[^"]*',
        r'https://www\.transavia\.com/[^"]*availability[^"]*',
        r'https://booking\.transavia\.com[^"]*',
        r'/api/[^"]+',
        r'apiUrl["\']:\s*["\']([^"\']+)',
    ]
    
    all_endpoints = set()
    for pattern in endpoint_patterns:
        matches = re.findall(pattern, r.text, re.IGNORECASE)
        all_endpoints.update(matches)
    
    if all_endpoints:
        print(f"\nFound {len(all_endpoints)} unique endpoints:")
        for ep in sorted(all_endpoints)[:20]:
            print(f"  - {ep}")
    
    # Check if there's a separate booking domain
    print("\n" + "="*70)
    print("TESTING BOOKING SUBDOMAIN")
    print("="*70)
    
    try:
        r3 = session.get("https://booking.transavia.com", timeout=10, allow_redirects=True)
        print(f"https://booking.transavia.com → {r3.status_code}")
        print(f"Final URL: {r3.url}")
    except Exception as e:
        print(f"booking.transavia.com: {e}")
    
    session.close()
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print("Next step: Manually inspect the saved files to find the actual search mechanism")
    print("Files saved:")
    print("  - /tmp/transavia_home.html")
    print("  - /tmp/transavia_next_data.json (if found)")
    print("  - /tmp/transavia_page_data.json (if found)")

if __name__ == "__main__":
    analyze_homepage()
