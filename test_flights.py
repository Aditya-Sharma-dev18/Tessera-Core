# test_flights.py
from fast_flights import FlightQuery, Passengers, create_query, get_flights

query = create_query(
    flights=[FlightQuery(date="2026-11-15", from_airport="DEL", to_airport="GOI")],
    seat="economy",
    trip="one-way",
    passengers=Passengers(adults=1),
    currency="INR"
)

raw = get_flights(query)
print(f"Total results: {len(raw)}\n")

for i, item in enumerate(raw[:5]):
    print(f"--- Result {i} ---")
    print(f"  type: {type(item)}")
    print(f"  attrs: {[a for a in dir(item) if not a.startswith('_')]}")
    print(f"  price: {getattr(item, 'price', 'NO PRICE ATTR')}")
    print(f"  price type: {type(getattr(item, 'price', None))}")
    print(f"  airlines: {getattr(item, 'airlines', 'NO AIRLINES')}")
    print(f"  flights count: {len(getattr(item, 'flights', []))}")
    print()