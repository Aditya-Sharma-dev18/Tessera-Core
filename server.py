from mcp.server.fastmcp import FastMcp


from tools.flight_tool import search_flights
from tools.bus_tool import search_buses
from tools.rails_tool import search_trains

mcp=FastMcp("Tessera-Travel-Engine")


@mcp_tool
def find_flights(origin_iata:str,destination_iata:str,travel_date:str)->str:
    """ live flight search tool"""
    return search_flights.invoke(
        {
        "origin_iata":origin_iata,
        "destination_iata":destination_iata,
        "travel_date":travel_date
    }
    )

@mcp_tool
def find_trains(from_station:str,to_station:str,travel_date:str)->str:
    """ live train search tool"""
    search_trains.invoke(
        {
        "from_station":from_station,
        "to_station":to_station,
        "travel_date":travel_date
    }
    )

@mcp_tool()
def find_buses(origin_city:str,destination_city:str,travel_date:str)->str:
    """ live search tool for buses"""
    search_buses.invoke(
        {
          "origin_city":origin_city,
          "destination_city":destination_city,
          "travel_date":travel_date

        }
    )