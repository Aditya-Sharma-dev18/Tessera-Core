import json
import httpx
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Fetches real-time weather and forecast for packing suggestions."""
    try:
        # Open-Meteo free geocoding & weather API
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_res = httpx.get(geo_url, timeout=5.0).json()
        if not geo_res.get("results"):
            return json.dumps({"error": f"City '{city}' not found"})

        lat = geo_res["results"][0]["latitude"]
        lon = geo_res["results"][0]["longitude"]

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_res = httpx.get(weather_url, timeout=5.0).json()
        
        return json.dumps({
            "city": city,
            "current_weather": w_res.get("current_weather", {})
        })
    except Exception as e:
        return json.dumps({"error": f"Weather fetch failed: {str(e)}"})