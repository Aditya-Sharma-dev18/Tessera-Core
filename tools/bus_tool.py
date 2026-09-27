import os
import json
from typing import List, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from tavily import TavilyClient
from langchain_groq import ChatGroq
from dotenv import load_dotenv

from utils.deep_links import DeepLinkGenerator

load_dotenv()


# ==========================================
# 1. Output Data Contracts
# ==========================================
class BusOption(BaseModel):
    operator_name: str = Field(description="Bus operator, e.g., Zingbus, IntrCity SmartBus, NueGo, VRL Travels")
    bus_type: str = Field(description="Bus configuration, e.g., AC Seater/Sleeper (2+1), Electric Luxury AC")
    departure_time: str = Field(description="Estimated departure time (HH:MM)")
    duration_hours: str = Field(description="Estimated travel duration")
    estimated_price_inr: float = Field(description="Starting ticket fare in INR")
    booking_url: str = Field(description="Pre-filled RedBus booking link")


class BusExtractionSchema(BaseModel):
    buses: List[BusOption]


class BusSearchOutput(BaseModel):
    origin: str
    destination: str
    travel_date: str
    total_found: int
    cheapest_inr: Optional[float]
    recommended_buses: List[BusOption]


# ==========================================
# 2. LangChain Bus Tool
# ==========================================
@tool
def search_buses(origin_city: str, destination_city: str, travel_date: str) -> str:
    """
    Search intercity bus schedules, operators, and ticket fare estimates across India.
    
    Args:
        origin_city: Departure city name (e.g., 'Delhi', 'Bangalore', 'Mumbai').
        destination_city: Arrival city name (e.g., 'Manali', 'Hyderabad', 'Pune').
        travel_date: Date of travel in YYYY-MM-DD format (e.g., '2026-10-15').
        
    Returns:
        JSON string with bus operators, bus types, estimated prices, and direct booking links.
    """
    tavily_key = os.getenv("TAVILY_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    if not tavily_key or not groq_key:
        return json.dumps({"error": "TAVILY_API_KEY or GROQ_API_KEY missing from environment."})

    from_city = origin_city.strip().title()
    to_city = destination_city.strip().title()
    deep_link = DeepLinkGenerator.get_bus_link(from_city, to_city, travel_date)

    try:
        # Step 1: Real-time search query targeting live aggregator pricing
        tavily = TavilyClient(api_key=tavily_key)
        query = f"bus tickets fare from {from_city} to {to_city} price Zingbus IntrCity Redbus timetable"
        
        search_res = tavily.search(query=query, search_depth="basic", max_results=3)
        context_snippets = "\n".join([r.get("content", "") for r in search_res.get("results", [])])

        if not context_snippets.strip():
            return json.dumps({
                "origin": from_city,
                "destination": to_city,
                "travel_date": travel_date,
                "total_found": 0,
                "message": "No bus transit options found for this specific route.",
                "booking_url": deep_link
            })

        # Step 2: Ultra-fast 20B Router Model parses unstructured data into typed schema
        llm = ChatGroq(
            model="openai/gpt-oss-20b",
            api_key=groq_key,
            temperature=0.0
        )
        
        prompt = f"""
        Extract bus transit options between {from_city} and {to_city} from the context below.
        For each valid bus service, extract:
        - operator_name (e.g., Zingbus, IntrCity SmartBus, SRS, State RTC)
        - bus_type (e.g., AC Sleeper 2+1, Multi-Axle Volvo)
        - departure_time (HH:MM format, estimate reasonable schedule if not exact)
        - duration_hours (e.g., "8h 30m")
        - estimated_price_inr (numeric price, e.g. 850.0)
        - booking_url: Set exactly to "{deep_link}"
        
        Context data:
        {context_snippets}
        """

        structured_llm = llm.with_structured_output(BusExtractionSchema)
        extracted: BusExtractionSchema = structured_llm.invoke(prompt)

        # Enforce deep link and clean values
        prices: List[float] = []
        for bus in extracted.buses:
            bus.booking_url = deep_link
            prices.append(bus.estimated_price_inr)

        output = BusSearchOutput(
            origin=from_city,
            destination=to_city,
            travel_date=travel_date,
            total_found=len(extracted.buses),
            cheapest_inr=min(prices) if prices else None,
            recommended_buses=extracted.buses[:5]
        )

        return output.model_dump_json(indent=2)

    except Exception as e:
        return json.dumps({
            "origin": from_city,
            "destination": to_city,
            "travel_date": travel_date,
            "error": f"Bus search adapter error: {str(e)}",
            "fallback_booking_url": deep_link
        })


# ==========================================
# 3. Direct Test Execution
# ==========================================
if __name__ == "__main__":
    print("Testing Bus Search Tool directly (Delhi -> Manali)...")
    res = search_buses.invoke({
        "origin_city": "Delhi",
        "destination_city": "Manali",
        "travel_date": "2026-10-15"
    })
    print(res)