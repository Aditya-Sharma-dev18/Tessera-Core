import sys
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

from mcp.server.fastmcp import FastMCP

from tools.flight_tool import search_flights
from tools.bus_tool import search_buses
from tools.rails_tool import search_trains
from tools.weather_tool import get_weather
from tools.tavily_tool import search_hotels

# Initialize server with uppercase FastMCP
mcp = FastMCP("Tessera-Travel-Engine")


@mcp.tool()
def find_flights(origin_iata: str, destination_iata: str, travel_date: str) -> str:
    """Live flight search tool returning cheapest fares and schedules."""
    return search_flights.invoke({
        "origin_iata": origin_iata,
        "destination_iata": destination_iata,
        "travel_date": travel_date
    })


@mcp.tool()
def find_trains(from_station: str, to_station: str, travel_date: str) -> str:
    """Live train search tool for Indian Railways trains between stations."""
    return search_trains.invoke({
        "from_station_code": from_station,
        "to_station_code": to_station,
        "travel_date": travel_date
    })


@mcp.tool()
def find_buses(origin_city: str, destination_city: str, travel_date: str) -> str:
    """Live bus search tool for intercity bus transit across India."""
    return search_buses.invoke({
        "origin_city": origin_city,
        "destination_city": destination_city,
        "travel_date": travel_date
    })


@mcp.tool()
def find_hotels(city: str, budget_tier: str = "moderate") -> str:
    """Live hotel search tool returning verified accommodation tariffs."""
    return search_hotels.invoke({
        "city": city,
        "budget_tier": budget_tier
    })


@mcp.tool()
def find_weather(city: str) -> str:
    """Live destination weather lookup for packing suggestions."""
    return get_weather.invoke({"city": city})


if __name__ == "__main__":
    mcp.run(transport="stdio")