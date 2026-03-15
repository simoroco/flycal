#!/usr/bin/env python3
"""Test that Google Flights finds Transavia flights Paris->Fez"""
import asyncio
from datetime import date
from scraper.google_flights import google_flights_bulk_search

async def main():
    print("\n" + "="*70)
    print("Testing Google Flights for Transavia: Paris -> Fez")
    print("Dates: 2026-03-05 to 2026-03-28 (roundtrip)")
    print("="*70 + "\n")
    
    # Test Google Flights bulk search with Transavia
    results = await google_flights_bulk_search(
        airline_names=["Transavia"],
        origin_city="Paris",
        destination_city="Fez",
        date_from=date(2026, 3, 5),
        date_to=date(2026, 3, 28),
        trip_type="roundtrip"
    )
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    if "Transavia" in results:
        flights = results["Transavia"]
        outbound = [f for f in flights if f.direction == "outbound"]
        return_flights = [f for f in flights if f.direction == "return"]
        not_served = [f for f in flights if getattr(f, "route_not_served", False)]
        
        print(f"\nTotal results: {len(flights)}")
        print(f"Outbound flights: {len(outbound)}")
        print(f"Return flights: {len(return_flights)}")
        print(f"Route not served: {len(not_served)}")
        
        if outbound and not not_served:
            print("\n✓ SUCCESS: Google Flights found Transavia flights!")
            print("\nSample outbound flights:")
            for f in outbound[:5]:
                print(f"  {f.flight_date} {f.departure_time}->{f.arrival_time} {f.origin_airport}->{f.destination_airport} €{f.price}")
            
            if return_flights:
                print("\nSample return flights:")
                for f in return_flights[:5]:
                    print(f"  {f.flight_date} {f.departure_time}->{f.arrival_time} {f.origin_airport}->{f.destination_airport} €{f.price}")
        else:
            print("\n⚠️  No real flights found (only route_not_served)")
    else:
        print("\n❌ No Transavia results returned")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())
