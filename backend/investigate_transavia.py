#!/usr/bin/env python3
"""Investigate Transavia website structure - how does the real search work?"""
import signal
from curl_cffi import requests as cffi_requests

# Timeout handler
def timeout_handler(signum, frame):
    raise TimeoutError("Request timed out")

signal.signal(signal.SIGALRM, timeout_handler)

def test_transavia_search():
    """Test real Transavia search flow"""
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        print("curl_cffi not installed")
        return
    
    session = cffi_requests.Session(impersonate="chrome")
    
    # Test 1: Load homepage to see what happens
    print("\n" + "="*60)
    print("TEST 1: Loading Transavia homepage")
    print("="*60)
    
    signal.alarm(15)
    try:
        r = session.get("https://www.transavia.com/accueil/fr-fr", timeout=12)
        signal.alarm(0)
        print(f"Status: {r.status_code}")
        print(f"URL after redirect: {r.url}")
        print(f"Content-Type: {r.headers.get('content-type', 'N/A')}")
        print(f"Content length: {len(r.text)} chars")
        
        # Look for booking form or search API
        if "book-a-flight" in r.text:
            print("✓ Found 'book-a-flight' in HTML")
        if "reserver" in r.text or "réserver" in r.text:
            print("✓ Found 'reserver' in HTML")
        if "api" in r.text.lower():
            print("✓ Found 'api' mentions in HTML")
        
        # Check for Next.js data or React
        if "__NEXT_DATA__" in r.text:
            print("✓ Uses Next.js")
        if "react" in r.text.lower():
            print("✓ Uses React")
        if "_next" in r.text:
            print("✓ Next.js assets found")
            
    except Exception as e:
        signal.alarm(0)
        print(f"Error: {e}")
    
    # Test 2: Try booking page directly
    print("\n" + "="*60)
    print("TEST 2: Try booking page with specific route")
    print("="*60)
    
    # Try the new booking URL format
    booking_url = "https://www.transavia.com/fr-FR/reserver-un-vol/vols/"
    signal.alarm(15)
    try:
        r = session.get(booking_url, timeout=12)
        signal.alarm(0)
        print(f"Status: {r.status_code}")
        print(f"Final URL: {r.url}")
        print(f"Content length: {len(r.text)} chars")
        
        # Save for inspection
        with open("/tmp/transavia_booking.html", "w") as f:
            f.write(r.text)
        print("✓ Saved to /tmp/transavia_booking.html")
        
        # Look for form fields or API endpoints
        if 'data-api' in r.text or 'apiUrl' in r.text:
            print("✓ Found API URL references")
        if 'flightSearch' in r.text or 'flight-search' in r.text:
            print("✓ Found flight search component")
            
    except Exception as e:
        signal.alarm(0)
        print(f"Error: {e}")
    
    # Test 3: Check for calendar/availability API
    print("\n" + "="*60)
    print("TEST 3: Look for calendar/availability endpoint")
    print("="*60)
    
    # Common API patterns for airlines
    api_patterns = [
        "https://www.transavia.com/api/",
        "https://www.transavia.com/_next/data/",
        "https://booking.transavia.com/",
        "https://www.transavia.com/fr-FR/api/",
    ]
    
    for api_url in api_patterns:
        try:
            signal.alarm(10)
            r = session.get(api_url, timeout=8)
            signal.alarm(0)
            if r.status_code < 500:
                print(f"  {api_url} → {r.status_code}")
        except:
            signal.alarm(0)
            pass
    
    print("\n" + "="*60)
    print("Analyzing HTML structure...")
    print("="*60)
    
    # Re-read the saved HTML
    try:
        with open("/tmp/transavia_booking.html", "r") as f:
            html = f.read()
        
        # Extract script sources
        import re
        scripts = re.findall(r'<script[^>]*src=["\'](.*?)["\']', html)
        print(f"\nFound {len(scripts)} script tags")
        
        # Look for bundle or main JS files
        relevant_scripts = [s for s in scripts if any(x in s.lower() for x in ['bundle', 'main', 'app', 'flight', 'search'])]
        if relevant_scripts:
            print("\nRelevant JS files:")
            for s in relevant_scripts[:10]:
                print(f"  {s}")
        
        # Look for inline data
        next_data = re.search(r'__NEXT_DATA__\s*=\s*({.*?})</script>', html, re.DOTALL)
        if next_data:
            print("\n✓ Found __NEXT_DATA__ (Next.js app)")
            data_snippet = next_data.group(1)[:200]
            print(f"  Data preview: {data_snippet}...")
        
        # Look for window.__INITIAL_STATE__ or similar
        initial_state = re.search(r'window\.__[A-Z_]+__\s*=\s*({.*?});', html, re.DOTALL)
        if initial_state:
            print("\n✓ Found initial state data")
            
    except Exception as e:
        print(f"Error analyzing HTML: {e}")
    
    session.close()

if __name__ == "__main__":
    test_transavia_search()
