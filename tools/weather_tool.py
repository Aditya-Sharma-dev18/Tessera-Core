import json
import httpx
from langchain_core.tools import tool

# Mapping WMO Weather interpretation codes (WW) to human-readable strings
WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
}


@tool
def get_weather(city: str) -> str:
    """Fetches real-time weather and forecast for destination packing and activity suggestions."""
    try:
        clean_city = city.strip()
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={clean_city}&count=5"
        with httpx.Client(timeout=6.0) as client:
            geo_res = client.get(geo_url).json()

        results = geo_res.get("results", [])
        if not results:
            return json.dumps({"city": clean_city, "error": f"City '{clean_city}' not found"})

        # Prefer high population or primary administrative division match
        best_match = results[0]
        for r in results:
            if r.get("population", 0) > best_match.get("population", 0):
                best_match = r

        lat = best_match["latitude"]
        lon = best_match["longitude"]
        matched_name = best_match.get("name", clean_city)
        admin1 = best_match.get("admin1", "")
        country = best_match.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        with httpx.Client(timeout=6.0) as client:
            w_res = client.get(weather_url).json()

        current = w_res.get("current_weather", {})
        code = current.get("weathercode", 0)
        condition = WMO_WEATHER_CODES.get(code, "Pleasant")

        return json.dumps({
            "city": matched_name,
            "region": f"{admin1}, {country}".strip(", "),
            "temperature_c": current.get("temperature"),
            "windspeed_kmh": current.get("windspeed"),
            "condition": condition,
            "current_weather": current
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"city": city, "error": f"Weather fetch failed: {str(e)}"}, ensure_ascii=False)