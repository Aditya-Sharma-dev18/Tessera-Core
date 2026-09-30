import json
from typing import List, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from fast_flights import FlightQuery, Passengers, create_query, get_flights


from utils.deep_links import DeepLinkGenerator


# ==========================================
# 1. Output Data Contracts (Pydantic Schemas)
# ==========================================
class FlightLeg(BaseModel):
    airline: str = Field(description="Operating airline name")
    flight_type: str = Field(description="Direct or Connecting leg")
    departure_time: str = Field(description="Departure timestamp (HH:MM)")
    arrival_time: str = Field(description="Arrival timestamp (HH:MM)")
    duration_minutes: int = Field(description="Flight duration in minutes")
    aircraft: str = Field(description="Aircraft model, e.g., Boeing 787, A320neo")
    stops: int = Field(description="Number of layovers/stops")
    price_inr: float = Field(description="Total ticket price in INR")
    booking_url: str = Field(description="Pre-filled 1-click booking link")


class FlightSearchOutput(BaseModel):
    origin: str
    destination: str
    travel_date: str
    total_found: int
    cheapest_inr: Optional[float]
    recommended_flights: List[FlightLeg]


# ==========================================
# 2. Parsing Helper
# ==========================================
def _parse_time_tuple(time_obj) -> str:
    """Converts SimpleDatetime tuple (H, M) into HH:MM formatted string."""
    try:
        if hasattr(time_obj, "time") and isinstance(time_obj.time, (tuple, list)):
            return f"{time_obj.time[0]:02d}:{time_obj.time[1]:02d}"
    except Exception:
        pass
    return "N/A"


# ==========================================
# 3. Domestic / International Detection
# ==========================================
# Non-Indian airport IATA codes (main international hubs)
_INTERNATIONAL_HUBS = {
    "DXB", "AUH", "DOH", "SIN", "BKK", "HKG", "KUL",
    "LHR", "CDG", "FRA", "AMS", "IST", "ZRH",
    "JFK", "EWR", "LAX", "SFO", "ORD", "YYZ",
    "NRT", "HND", "ICN", "PEK", "PVG",
    "SYD", "MEL", "AKL",
    "MLE", "CMB", "KTM", "DAC", "RGN",
}


def _is_domestic(origin: str, dest: str) -> bool:
    """Returns True if both airports are likely in India."""
    return origin not in _INTERNATIONAL_HUBS and dest not in _INTERNATIONAL_HUBS


# ==========================================
# 4. LangChain Agent Tool
# ==========================================
@tool
def search_flights(origin_iata: str, destination_iata: str, travel_date: str) -> str:
    """
    Search real-time domestic and international flight options, schedules, aircraft types, and pricing.
    
    Args:
        origin_iata: 3-letter IATA code for the departure airport (e.g., 'DEL', 'BOM', 'BLR').
        destination_iata: 3-letter IATA code for the destination airport (e.g., 'BOM', 'CCU', 'GOI').
        travel_date: Departure date in YYYY-MM-DD format (e.g., '2026-10-15').
        
    Returns:
        JSON string containing the cheapest fare and top curated flight options.
    """
    try:
        origin = origin_iata.strip().upper()
        dest = destination_iata.strip().upper()
        domestic = _is_domestic(origin, dest)
        
        # Deep Link generate karein
        booking_link = DeepLinkGenerator.get_flight_link(origin, dest, travel_date)
        
        # 1. Build Query Object
        query = create_query(
            flights=[
                FlightQuery(
                    date=travel_date,
                    from_airport=origin,
                    to_airport=dest
                )
            ],
            seat="economy",
            trip="one-way",
            passengers=Passengers(adults=1),
            currency="INR"
        )
        
        # 2. Fetch Live Google Flights Data
        raw_results = get_flights(query)
        
        if not raw_results:
            return json.dumps({
                "origin": origin,
                "destination": dest,
                "travel_date": travel_date,
                "total_found": 0,
                "cheapest_inr": None,
                "recommended_flights": [],
                "message": f"No flights found between {origin} and {dest} on {travel_date}."
            })

        parsed_list: List[FlightLeg] = []
        prices: List[float] = []

        # 3. Parse flights
        # ⚠️ DOMESTIC SANITY: For domestic India routes, flight should be ≤ ₹20,000
        # Prices higher = likely connecting international carrier data
        max_price_threshold = 20000 if domestic else 500000

        for item in raw_results:
            try:
                first_leg = item.flights[0] if (hasattr(item, "flights") and item.flights) else None
                dep_time = _parse_time_tuple(first_leg.departure) if first_leg else "N/A"
                arr_time = _parse_time_tuple(first_leg.arrival) if first_leg else "N/A"
                
                aircraft = (
                    first_leg.plane_type 
                    if (first_leg and hasattr(first_leg, "plane_type") and first_leg.plane_type) 
                    else "Commercial Jet"
                )
                
                airline_name = item.airlines[0] if (hasattr(item, "airlines") and item.airlines) else item.type
                fare = float(item.price)

                # ⚠️ SKIP: Absurd prices for domestic routes
                if domestic and fare > max_price_threshold:
                    print(f"⚠️ Skipping absurd price ₹{fare:,.0f} for domestic {origin}→{dest}")
                    continue
                
                prices.append(fare)
                
                num_stops = len(item.flights) - 1 if hasattr(item, "flights") else 0
                flight_type_desc = "Non-stop" if num_stops == 0 else f"{num_stops} Stop"

                duration = int(first_leg.duration) if (first_leg and hasattr(first_leg, "duration")) else 0

                parsed_list.append(
                    FlightLeg(
                        airline=airline_name,
                        flight_type=flight_type_desc,
                        departure_time=dep_time,
                        arrival_time=arr_time,
                        duration_minutes=duration,
                        aircraft=aircraft,
                        stops=num_stops,
                        price_inr=fare,
                        booking_url=booking_link
                    )
                )
            except Exception:
                continue

        # ⚠️ If ALL flights were filtered out (all absurd), return empty
        if not parsed_list:
            return json.dumps({
                "origin": origin,
                "destination": dest,
                "travel_date": travel_date,
                "total_found": 0,
                "cheapest_inr": None,
                "recommended_flights": [],
                "message": f"All flights for {origin}→{dest} were above threshold (₹{max_price_threshold:,}) — likely connecting international routes."
            })

        # 4. Sort by price ascending
        parsed_list.sort(key=lambda x: x.price_inr)

        # ⚠️ SECOND-LAYER FILTER: Remove flights > 3x cheapest (outliers)
        if parsed_list:
            cheapest = parsed_list[0].price_inr
            # Keep only flights within reasonable range
            cutoff = cheapest * 3 if domestic else cheapest * 10
            filtered_list = [f for f in parsed_list if f.price_inr <= cutoff]
            if filtered_list:
                parsed_list = filtered_list

        output = FlightSearchOutput(
            origin=origin,
            destination=dest,
            travel_date=travel_date,
            total_found=len(raw_results),
            cheapest_inr=parsed_list[0].price_inr if parsed_list else None,
            recommended_flights=parsed_list[:6]
        )

        return output.model_dump_json(indent=2)

    except Exception as e:
        return json.dumps({"error": f"Flight retrieval failed: {str(e)}"})


# ==========================================
# 5. Standalone Test Execution
# ==========================================
if __name__ == "__main__":
    print("Testing flight search tool directly...")
    test_result = search_flights.invoke({
        "origin_iata": "DEL",
        "destination_iata": "BOM",
        "travel_date": "2026-10-15"
    })
    print(test_result)