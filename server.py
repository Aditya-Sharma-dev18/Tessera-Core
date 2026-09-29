from mcp.server.fastmcp import FastMCP

from tools.flight_tool import search_flights
from tools.bus_tool import search_buses
from tools.rails_tool import search_trains

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
    # Maps 'from_station' to 'from_station_code' as expected by search_trains
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


if __name__ == "__main__":
    mcp.run(transport="stdio")