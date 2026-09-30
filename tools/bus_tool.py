# ═══════════════════════════════════════════════════════════════════════════
#  🚌  BUS SEARCH TOOL — Tavily + LLM (manual JSON parse, no tool calling)
# ═══════════════════════════════════════════════════════════════════════════
import os
import json
from typing import List, Optional
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from tavily import TavilyClient
from dotenv import load_dotenv

from utils.deep_links import DeepLinkGenerator

load_dotenv()


# ═══════════════════════════════════════════════════════════════════════════
#  🚌  search_buses — Tavily + LLM extraction with manual JSON parsing
# ═══════════════════════════════════════════════════════════════════════════
@tool
def search_buses(origin_city: str, destination_city: str, travel_date: str) -> str:
    """
    Search intercity bus schedules, operators, and ticket fare estimates across India.

    Args:
        origin_city: Departure city name (e.g., 'Delhi', 'Bangalore', 'Mumbai').
        destination_city: Arrival city name (e.g., 'Manali', 'Hyderabad', 'Pune').
        travel_date: Date of travel in YYYY-MM-DD format.

    Returns:
        JSON string with bus operators, bus types, estimated prices, and booking links.
    """
    tavily_key = os.getenv("TAVILY_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    if not tavily_key or not groq_key:
        return json.dumps({"error": "TAVILY_API_KEY or GROQ_API_KEY missing"})

    from_city = origin_city.strip().title()
    to_city = destination_city.strip().title()
    deep_link = DeepLinkGenerator.get_bus_link(from_city, to_city, travel_date)

    raw_text = ""

    try:
        # ─── Step 1: Tavily search ───
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
                "cheapest_inr": None,
                "recommended_buses": [],
                "message": "No bus transit options found for this route.",
                "booking_url": deep_link
            })

        # ─── Step 2: LLM extracts JSON (manual parse) ───
        llm = ChatGroq(
            model="openai/gpt-oss-20b",
            api_key=groq_key,
            temperature=0,
            max_tokens=2048,
        )

        extraction_prompt = f"""You are a bus data extractor. Extract intercity bus options between {from_city} and {to_city}.

SEARCH RESULTS:
{context_snippets[:3500]}

RULES:
1. Extract bus OPERATOR NAMES (e.g., "Zingbus", "IntrCity SmartBus", "SRS Travels", "VRL")
2. Extract BUS TYPE (e.g., "AC Sleeper 2+1", "Multi-Axle Volvo", "Non-AC Seater")
3. Extract DEPARTURE TIME (HH:MM format, estimate if needed)
4. Extract DURATION (e.g., "8h 30m")
5. Extract PRICE in INR (numeric, e.g., 1200)
   - Look for "₹1,200", "Rs 1,500", "1200/-"
   - If multiple prices, use the LOWEST
   - If no price found → estimate ₹1,200 for short, ₹2,000 for medium, ₹2,500 for long routes
6. NEVER return 0 price — always estimate

OUTPUT — respond ONLY with valid JSON, no markdown:

{{
  "buses": [
    {{
      "operator_name": "Zingbus",
      "bus_type": "AC Sleeper 2+1",
      "departure_time": "20:30",
      "duration_hours": "11h 15m",
      "estimated_price_inr": 1200
    }}
  ]
}}

Extract UP TO 5 buses. Return {{"buses": []}} if truly none found.

JSON RESPONSE:"""

        response = llm.invoke(extraction_prompt)
        raw_text = response.content.strip()

        # Clean markdown fences
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        # Extract JSON block
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            raw_text = raw_text[json_start:json_end]

        parsed = json.loads(raw_text)
        raw_buses = parsed.get("buses", [])

        # ─── Step 3: Normalize ───
        buses = []
        for b in raw_buses[:5]:
            buses.append({
                "operator_name": b.get("operator_name") or "Bus Operator",
                "bus_type": b.get("bus_type") or "AC Seater",
                "departure_time": b.get("departure_time") or "N/A",
                "duration_hours": b.get("duration_hours") or "N/A",
                "estimated_price_inr": float(b.get("estimated_price_inr") or 1200),
                "booking_url": deep_link,
            })

        prices = [b["estimated_price_inr"] for b in buses]

        return json.dumps({
            "origin": from_city,
            "destination": to_city,
            "travel_date": travel_date,
            "total_found": len(buses),
            "cheapest_inr": min(prices) if prices else None,
            "recommended_buses": buses,
        }, indent=2)

    except json.JSONDecodeError as e:
        print(f"⚠️ Bus JSON parse failed: {e}")
        print(f"Raw LLM output: {raw_text[:500]}")
        return json.dumps({
            "origin": from_city,
            "destination": to_city,
            "travel_date": travel_date,
            "error": f"JSON parse failed: {str(e)}",
            "fallback_booking_url": deep_link
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "origin": from_city,
            "destination": to_city,
            "travel_date": travel_date,
            "error": f"Bus search adapter error: {str(e)}",
            "fallback_booking_url": deep_link
        })


# ═══════════════════════════════════════════════════════════════════════════
#  🧪  Test
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Testing Bus Search Tool directly (Delhi -> Manali)...")
    res = search_buses.invoke({
        "origin_city": "Delhi",
        "destination_city": "Manali",
        "travel_date": "2026-12-15"
    })
    print(res)