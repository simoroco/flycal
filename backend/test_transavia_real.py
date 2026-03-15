#!/usr/bin/env python3
"""Test Transavia scraper with real dates: Paris->Fez 05/03-28/03 roundtrip"""
import asyncio
import sys
from datetime import date
from scraper.transavia import TransaviaScraper

async def main():
    scraper = TransaviaScraper()
    
    # Test with real dates
    origin = "Paris"
    destination = "Fez"
    date_from = date(2026, 3, 5)
    date_to = date(2026, 3, 28)
    
    print(f"\n{'='*60}")
    print(f"Testing Transavia: {origin} -> {destination}")
    print(f"Dates: {date_from} to {date_to}")
    print(f"Trip type: roundtrip")
    print(f"{'='*60}\n")
    
    results = await scraper.search(
        origin_city=origin,
        destination_city=destination,
        date_from=date_from,
        date_to=date_to,
        trip_type="roundtrip"
    )
    
    print(f"\n{'='*60}")
    print(f"RESULTS: Found {len(results)} total results")
    print(f"{'='*60}\n")
    
    outbound = [r for r in results if r.direction == "outbound"]
    return_flights = [r for r in results if r.direction == "return"]
    
    print(f"Outbound flights: {len(outbound)}")
    print(f"Return flights: {len(return_flights)}")
    
    if outbound:
        print("\nSample outbound flights:")
        for f in outbound[:5]:
            print(f"  {f.flight_date} {f.departure_time}->{f.arrival_time} {f.origin_airport}->{f.destination_airport} €{f.price}")
    
    if return_flights:
        print("\nSample return flights:")
        for f in return_flights[:5]:
            print(f"  {f.flight_date} {f.departure_time}->{f.arrival_time} {f.origin_airport}->{f.destination_airport} €{f.price}")
    
    # Check for route_not_served
    not_served = [r for r in results if getattr(r, "route_not_served", False)]
    if not_served:
        print(f"\n⚠️  Route not served: {len(not_served)} results")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())
