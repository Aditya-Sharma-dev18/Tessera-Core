import json
from typing import List, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from fast_flights import FlightQuery, Passengers, create_query, get_flights


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
# 3. LangChain Agent Tool
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
                "error": f"No flights found between {origin} and {dest} on {travel_date}."
            })

        parsed_list: List[FlightLeg] = []
        prices: List[float] = []

        # 3. Parse and prioritize top 6 flights to optimize LLM context window
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
                        price_inr=fare
                    )
                )
            except Exception:
                continue

        # Sort by price ascending
        parsed_list.sort(key=lambda x: x.price_inr)

        output = FlightSearchOutput(
            origin=origin,
            destination=dest,
            travel_date=travel_date,
            total_found=len(raw_results),
            cheapest_inr=min(prices) if prices else None,
            recommended_flights=parsed_list[:6]
        )

        return output.model_dump_json(indent=2)

    except Exception as e:
        return json.dumps({"error": f"Flight retrieval failed: {str(e)}"})


# ==========================================
# 4. Standalone Test Execution
# ==========================================
if __name__ == "__main__":
    print("Testing flight search tool directly...")
    test_result = search_flights.invoke({
        "origin_iata": "DEL",
        "destination_iata": "BOM",
        "travel_date": "2026-10-15"
    })
    print(test_result)