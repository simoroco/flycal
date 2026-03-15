#!/usr/bin/env python3
"""Find the real Transavia API by analyzing JavaScript bundles"""
import re
import json
from curl_cffi import requests as cffi_requests

def find_api_in_js():
    """Extract API endpoints from JavaScript bundles"""
    session = cffi_requests.Session(impersonate="chrome")
    
    # Load homepage
    print("Loading homepage...")
    r = session.get("https://www.transavia.com/accueil/fr-fr", timeout=15)
    html = r.text
    
    # Extract all script sources
    scripts = re.findall(r'<script[^>]*src=["\'](.*?)["\']', html)
    print(f"Found {len(scripts)} script tags\n")
    
    # Download and analyze relevant bundles
    api_patterns = [
        r'https?://[^"\']+/api/[^"\']+',
        r'apiUrl["\']?\s*[:=]\s*["\']([^"\']+)',
        r'endpoint["\']?\s*[:=]\s*["\']([^"\']+)',
        r'/fr-FR/[^"\']*api[^"\']*',
        r'baseURL["\']?\s*[:=]\s*["\']([^"\']+)',
    ]
    
    all_endpoints = set()
    
    for script_url in scripts[:20]:  # Limit to first 20 scripts
        if not script_url.startswith('http'):
            script_url = 'https://www.transavia.com' + script_url
        
        if any(x in script_url for x in ['_next', 'chunk', 'bundle']):
            try:
                print(f"Analyzing: {script_url[:80]}...")
                r2 = session.get(script_url, timeout=10)
                js_content = r2.text
                
                # Search for API patterns
                for pattern in api_patterns:
                    matches = re.findall(pattern, js_content)
                    if matches:
                        all_endpoints.update(matches)
                        print(f"  ✓ Found {len(matches)} matches for pattern")
            except Exception as e:
                print(f"  Error: {e}")
    
    if all_endpoints:
        print("\n" + "="*70)
        print("FOUND API ENDPOINTS:")
        print("="*70)
        for ep in sorted(all_endpoints):
            print(f"  {ep}")
    
    # Try common Transavia API patterns
    print("\n" + "="*70)
    print("TESTING COMMON API PATTERNS:")
    print("="*70)
    
    test_apis = [
        "https://www.transavia.com/api/flights/availability?origin=ORY&destination=FEZ&outboundDate=2026-03-05&inboundDate=2026-03-28",
        "https://www.transavia.com/api/booking/availability?from=ORY&to=FEZ&outbound=2026-03-05&inbound=2026-03-28",
        "https://www.transavia.com/fr-FR/api/flights?origin=ORY&destination=FEZ&departureDate=2026-03-05",
    ]
    
    for api_url in test_apis:
        try:
            print(f"\nTrying: {api_url[:80]}...")
            r = session.get(api_url, timeout=8)
            print(f"  Status: {r.status_code}")
            if r.status_code == 200:
                print(f"  Content-Type: {r.headers.get('content-type')}")
                print(f"  Length: {len(r.text)}")
                if 'json' in r.headers.get('content-type', ''):
                    try:
                        data = r.json()
                        print(f"  ✓ Valid JSON with {len(str(data))} chars")
                        with open(f"/tmp/transavia_api_{test_apis.index(api_url)}.json", "w") as f:
                            json.dump(data, f, indent=2)
                    except:
                        pass
        except Exception as e:
            print(f"  Error: {e}")
    
    session.close()

if __name__ == "__main__":
    find_api_in_js()
