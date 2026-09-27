import os
import json
import httpx
from typing import List
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from utils.deep_links import DeepLinkGenerator

load_dotenv()


# ==========================================
# 1. Output Data Contracts
# ==========================================
class TrainOption(BaseModel):
    train_number: str = Field(description="5-digit train number")
    train_name: str = Field(description="Official train name")
    departure_time: str = Field(description="Departure timestamp (HH:MM)")
    arrival_time: str = Field(description="Arrival timestamp (HH:MM)")
    travel_time_hours: str = Field(description="Total duration")
    classes: List[str] = Field(description="Available seat classes, e.g., 1A, 2A, 3A, SL")
    origin_station: str
    destination_station: str
    booking_url: str = Field(description="Pre-filled direct booking deep link")


class RailSearchOutput(BaseModel):
    from_station: str
    to_station: str
    travel_date: str
    total_trains: int
    trains: List[TrainOption]


# ==========================================
# 2. LangChain Rail Tool
# ==========================================
@tool
def search_trains(from_station_code: str, to_station_code: str, travel_date: str) -> str:
    """
    Search Indian Railways trains between two station codes for a given date.
    
    Args:
        from_station_code: Origin railway station code (e.g., 'NDLS', 'CSMT', 'HWH').
        to_station_code: Destination railway station code (e.g., 'CNB', 'BOM', 'MAS').
        travel_date: Travel date in YYYY-MM-DD format (e.g., '2026-10-15').
        
    Returns:
        JSON string listing available trains, schedules, classes, and 1-click booking URLs.
    """
    api_key = os.getenv("RAPIDAPI_KEY")
    host = os.getenv("RAPIDAPI_RAIL_HOST", "railkit-indian-railway-data.p.rapidapi.com")

    if not api_key:
        return json.dumps({"error": "RAPIDAPI_KEY not found in environment."})

    from_stn = from_station_code.strip().upper()
    to_stn = to_station_code.strip().upper()

    url = f"https://{host}/api/v1/trainBetweenStations"
    params = {
        "fromStationCode": from_stn,
        "toStationCode": to_stn,
        "date": travel_date
    }
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": host
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return json.dumps({
                    "error": f"Rail API failed with status code {response.status_code}",
                    "details": response.text[:200]
                })

            data = response.json()
            raw_trains = data.get("data", []) or data.get("trains", [])

            if not raw_trains:
                return json.dumps({
                    "from_station": from_stn,
                    "to_station": to_stn,
                    "travel_date": travel_date,
                    "total_trains": 0,
                    "trains": [],
                    "message": "No direct trains found for this route on the given date."
                })

            booking_link = DeepLinkGenerator.get_train_link(from_stn, to_stn, travel_date)
            parsed_trains: List[TrainOption] = []

            # Optimize LLM context window by selecting top 6 options
            for item in raw_trains[:6]:
                try:
                    classes_avail = item.get("classes", [])
                    if isinstance(classes_avail, str):
                        classes_avail = [c.strip() for c in classes_avail.split(",") if c.strip()]

                    parsed_trains.append(
                        TrainOption(
                            train_number=str(item.get("train_number") or item.get("trainNumber", "N/A")),
                            train_name=str(item.get("train_name") or item.get("trainName", "Express")),
                            departure_time=str(item.get("from_time") or item.get("departureTime", "N/A")),
                            arrival_time=str(item.get("to_time") or item.get("arrivalTime", "N/A")),
                            travel_time_hours=str(item.get("travel_time") or item.get("duration", "N/A")),
                            classes=classes_avail if classes_avail else ["SL", "3A", "2A"],
                            origin_station=from_stn,
                            destination_station=to_stn,
                            booking_url=booking_link
                        )
                    )
                except Exception:
                    continue

            output = RailSearchOutput(
                from_station=from_stn,
                to_station=to_stn,
                travel_date=travel_date,
                total_trains=len(raw_trains),
                trains=parsed_trains
            )

            return output.model_dump_json(indent=2)

    except httpx.RequestError as exc:
        return json.dumps({"error": f"Network error connecting to Rail API: {str(exc)}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected failure in rail processing: {str(e)}"})


# ==========================================
# 3. Direct Test Execution
# ==========================================
if __name__ == "__main__":
    print("Testing Rail Search Tool directly...")
    res = search_trains.invoke({
        "from_station_code": "NDLS",
        "to_station_code": "CNB",
        "travel_date": "2026-10-15"
    })
    print(res)