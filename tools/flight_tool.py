import sys
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

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
    departure_time: str = Field(description="Departure timestamp (HH:MM) from origin")
    arrival_time: str = Field(description="Arrival timestamp (HH:MM) at FINAL destination")
    duration_minutes: int = Field(description="Total journey time in minutes (incl. layovers)")
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
# 2. Parsing Helpers
# ==========================================
def _time_tuple(time_obj) -> Optional[tuple]:
    """Extracts (H, M) from a SimpleDatetime-like object. Returns None if unavailable."""
    try:
        if hasattr(time_obj, "time") and isinstance(time_obj.time, (tuple, list)) and len(time_obj.time) >= 2:
            return int(time_obj.time[0]), int(time_obj.time[1])
    except Exception:
        pass
    return None


def _parse_time_tuple(time_obj) -> str:
    """Converts SimpleDatetime tuple (H, M) into HH:MM formatted string."""
    t = _time_tuple(time_obj)
    return f"{t[0]:02d}:{t[1]:02d}" if t else "N/A"


def _minutes_of_day(time_obj) -> Optional[int]:
    t = _time_tuple(time_obj)
    return t[0] * 60 + t[1] if t else None


def _total_journey_minutes(legs) -> int:
    """
    Total journey = sum of every leg's flight time + layover gaps between legs.
    Layover = (next departure − previous arrival) wrapped to a 24h clock.
    """
    total = 0
    for leg in legs:
        try:
            total += int(getattr(leg, "duration", 0) or 0)
        except (TypeError, ValueError):
            pass

    for prev_leg, next_leg in zip(legs, legs[1:]):
        arr = _minutes_of_day(getattr(prev_leg, "arrival", None))
        dep = _minutes_of_day(getattr(next_leg, "departure", None))
        if arr is not None and dep is not None:
            total += (dep - arr) % 1440

    # Fallback: if leg durations were missing, use clock difference first→last
    if total <= 0 and legs:
        dep = _minutes_of_day(getattr(legs[0], "departure", None))
        arr = _minutes_of_day(getattr(legs[-1], "arrival", None))
        if dep is not None and arr is not None:
            total = (arr - dep) % 1440
    return total


# ==========================================
# 3. Domestic / International Detection
# ==========================================
# Known Indian airports — domestic ONLY if BOTH ends are in this set.
_INDIAN_AIRPORTS = {
    "DEL", "BOM", "BLR", "MAA", "CCU", "HYD", "AMD", "PNQ", "GOI", "GOX",
    "COK", "TRV", "CCJ", "IXE", "JAI", "LKO", "PAT", "IXC", "ATQ", "SXR",
    "IXJ", "IXL", "BBI", "GAU", "IXB", "IMF", "IXA", "AJL", "IXZ", "VNS",
    "IDR", "BHO", "NAG", "RPR", "IXR", "STV", "RAJ", "UDR", "JDH", "JSA",
    "DED", "KNU", "TRZ", "IXM", "VGA", "VTZ", "CJB", "IXG", "HBX", "GAY",
    "AGR", "GWL", "KLH", "ISK", "BDQ", "IXU", "DIB", "DMU", "JRH", "TEZ",
    "PGH", "KUU", "DHM", "SLV", "HSR", "TIR", "IXD", "AIP", "BEK", "PBD",
    "HJR", "IXS", "SHL", "RGH", "BHJ", "IXY", "NMB", "MYQ", "LTU", "IXP",
}

# Common international hubs (kept for clarity / logging)
_INTERNATIONAL_HUBS = {
    "DXB", "AUH", "DOH", "SIN", "BKK", "HKG", "KUL",
    "LHR", "CDG", "FRA", "AMS", "IST", "ZRH",
    "JFK", "EWR", "LAX", "SFO", "ORD", "YYZ",
    "NRT", "HND", "ICN", "PEK", "PVG",
    "SYD", "MEL", "AKL",
    "MLE", "CMB", "KTM", "DAC", "RGN",
}


def _is_domestic(origin: str, dest: str) -> bool:
    """True only if BOTH airports are known Indian airports (unknown codes are NOT assumed domestic)."""
    return origin in _INDIAN_AIRPORTS and dest in _INDIAN_AIRPORTS


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

        # Domestic sanity cap: higher prices usually mean bad/connecting-international data
        max_price_threshold = 20000 if domestic else 500000

        for item in raw_results:
            try:
                legs = list(item.flights) if (hasattr(item, "flights") and item.flights) else []
                first_leg = legs[0] if legs else None
                last_leg = legs[-1] if legs else None

                dep_time = _parse_time_tuple(first_leg.departure) if first_leg else "N/A"
                # FIX: arrival of the LAST leg = actual arrival at final destination
                arr_time = _parse_time_tuple(last_leg.arrival) if last_leg else "N/A"

                aircraft = (
                    first_leg.plane_type
                    if (first_leg and getattr(first_leg, "plane_type", None))
                    else "Commercial Jet"
                )

                airline_name = (
                    item.airlines[0]
                    if (hasattr(item, "airlines") and item.airlines)
                    else str(getattr(item, "type", "Airline"))
                )
                fare = float(item.price)

                if fare <= 0:
                    continue

                if domestic and fare > max_price_threshold:
                    print(f"[Warning] Skipping high price INR {fare:,.0f} for domestic {origin} to {dest}")
                    continue

                num_stops = max(0, len(legs) - 1)
                flight_type_desc = "Non-stop" if num_stops == 0 else f"{num_stops} Stop"

                # FIX: total journey (all legs + layovers), not just first leg
                duration = _total_journey_minutes(legs)

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

        # If ALL flights were filtered out, return empty
        if not parsed_list:
            return json.dumps({
                "origin": origin,
                "destination": dest,
                "travel_date": travel_date,
                "total_found": 0,
                "cheapest_inr": None,
                "recommended_flights": [],
                "message": (
                    f"All flights for {origin}→{dest} were filtered out "
                    f"(price above ₹{max_price_threshold:,} or unparseable)."
                )
            })

        # 4. Sort by price ascending
        parsed_list.sort(key=lambda x: x.price_inr)

        # Second-layer filter: drop outliers far above the cheapest fare
        cheapest = parsed_list[0].price_inr
        cutoff = cheapest * 3 if domestic else cheapest * 10
        filtered_list = [f for f in parsed_list if f.price_inr <= cutoff]
        if filtered_list:
            parsed_list = filtered_list

        output = FlightSearchOutput(
            origin=origin,
            destination=dest,
            travel_date=travel_date,
            total_found=len(raw_results),
            cheapest_inr=parsed_list[0].price_inr,
            recommended_flights=parsed_list[:6]
        )

        return output.model_dump_json(indent=2)

    except Exception as e:
        return json.dumps({
            "total_found": 0,
            "recommended_flights": [],
            "error": f"Flight retrieval failed: {str(e)}"
        })


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